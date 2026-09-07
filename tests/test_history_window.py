"""Synthetic IMAP coverage: date limits, backfill, retries, and UID continuity."""
import json
from datetime import date, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/mail-reader-summary/scripts'
sys.path.insert(0, str(SCRIPTS))
previous_bytecode = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    import read_mail
finally:
    sys.dont_write_bytecode = previous_bytecode
    sys.path.pop(0)


class FakeMailbox:
    def __init__(self):
        today = date.today()
        self.dates = {1: today - timedelta(days=10), 2: today - timedelta(days=40),
                      3: today - timedelta(days=80), 99: today - timedelta(days=100)}
        self.searches = []
        self.fetched = []
        self.fail_uid = None

    def login(self, *args):
        return 'OK', []

    def select(self, mailbox, readonly=False):
        assert readonly
        return 'OK', []

    def response(self, name):
        return 'OK', [b'1']

    def logout(self):
        pass

    def uid(self, operation, *args):
        if operation == 'fetch':
            uid = int(args[0])
            assert args[1] == '(BODY.PEEK[])'
            if uid == self.fail_uid:
                return 'NO', []
            self.fetched.append(uid)
            return 'OK', [(b'BODY', b'From: Sample <sample@example.invalid>\r\nSubject: Synthetic mail\r\n\r\nA test message.')]
        criterion = args[1]
        self.searches.append(criterion)
        if criterion == 'UID *':
            ids = [max(self.dates)] if self.dates else []
        elif criterion.startswith('UID '):
            lower = int(criterion.split()[1].split(':')[0])
            ids = [u for u in self.dates if u >= lower]
        elif criterion.startswith('SINCE '):
            from datetime import datetime
            cutoff = datetime.strptime(criterion[6:], '%d-%b-%Y').date()
            ids = [u for u, day in self.dates.items() if day >= cutoff]
        else:
            raise AssertionError('Unbounded search: ' + criterion)
        return 'OK', [' '.join(str(u) for u in sorted(ids)).encode()]


class HistoryWindow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        self.mailbox = FakeMailbox()
        self.config = dict(host='imap.example.invalid', ssl=True, mailbox='INBOX')

    def tearDown(self):
        self.temp.cleanup()

    def sync(self, **kwargs):
        with patch.object(read_mail.imaplib, 'IMAP4_SSL', return_value=self.mailbox):
            read_mail.sync_one(self.project, config_override=dict(self.config),
                               credentials=('sample', 'synthetic'), **kwargs)
        return json.loads((self.project / 'task-workspace/data/mail-reader-data.json').read_text(encoding='utf-8'))

    def test_default_and_backfill_keep_cursor_and_deduplicate(self):
        db = self.sync()
        self.assertEqual(self.mailbox.fetched, [1])
        self.assertEqual(next(iter(db['mailboxes'].values()))['last_uid'], 99)
        self.mailbox.dates[100] = date.today() - timedelta(days=100)
        self.sync()
        self.assertEqual(self.mailbox.fetched, [1, 100])
        db = self.sync(history_months=2)
        self.assertEqual(self.mailbox.fetched, [1, 100, 2])
        self.assertEqual(next(iter(db['mailboxes'].values()))['last_uid'], 100)
        self.sync(history_months=2)
        self.assertEqual(self.mailbox.fetched, [1, 100, 2])

    def test_first_two_months_and_failed_fetch_retry(self):
        self.mailbox.fail_uid = 2
        db = self.sync(history_months=2)
        self.assertIn('history_since', next(iter(db['mailboxes'].values())))
        self.mailbox.fail_uid = None
        db = self.sync()
        self.assertEqual(self.mailbox.fetched, [1, 2])
        self.assertNotIn('history_since', next(iter(db['mailboxes'].values())))

    def test_empty_window_does_not_import_older_mail(self):
        self.mailbox.dates = {99: date.today() - timedelta(days=100)}
        db = self.sync()
        self.assertEqual(db['messages'], [])
        self.assertEqual(next(iter(db['mailboxes'].values()))['last_uid'], 99)

    def test_legacy_baseline_override(self):
        self.config['import_existing_on_first_sync'] = False
        self.sync()
        self.assertEqual(self.mailbox.fetched, [])
        self.sync(history_months=2)
        self.assertEqual(self.mailbox.fetched, [1, 2])

    def test_month_end(self):
        self.assertEqual(read_mail.history_cutoff(1, date(2024, 3, 31)), '2024-02-29')
        self.assertEqual(read_mail.history_cutoff(2, date(2026, 1, 31)), '2025-11-30')
        with self.assertRaises(ValueError):
            read_mail.history_cutoff(0)

    def test_inbox_and_sent_share_requested_window(self):
        read_mail.initialize(self.project)
        config = dict(self.config, include_sent=True, sent_mailbox='Sent',
                      username_env='SYNTHETIC_USER', password_env='SYNTHETIC_PASS')
        read_mail.write_json(self.project / 'task-workspace/config/mail-reader-config.json', config)
        with patch.object(read_mail, 'credential_value', return_value='synthetic'), \
             patch.object(read_mail.imaplib, 'IMAP4_SSL', return_value=self.mailbox):
            read_mail.sync(self.project, history_months=2)
        db = read_mail.read_json(self.project / 'task-workspace/data/mail-reader-data.json')
        self.assertEqual(len(db['mailboxes']), 2)
        self.assertEqual(len(db['messages']), 4)
        self.assertEqual({m['direction'] for m in db['messages']}, {'inbound', 'sent'})
