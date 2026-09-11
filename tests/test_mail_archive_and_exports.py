import csv
import io
import json
import mailbox
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "mail-reader-summary" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import export_mail_summary
import read_mail_archive
from read_mail import DATA_NAME, output_dir, read_json


def sample_message(subject="Archive message"):
    message = EmailMessage()
    message["From"] = "Alice <alice@example.com>"
    message["To"] = "Bob <bob@example.com>"
    message["Subject"] = subject
    message["Date"] = format_datetime(datetime.now(timezone.utc))
    message["Message-ID"] = f"<{subject.replace(' ', '-')}@example.com>"
    message.set_content("Please review the attached evidence.")
    message.add_attachment(b"evidence", maintype="text", subtype="plain", filename="evidence.txt")
    return message


class MailArchiveAndExportTests(unittest.TestCase):
    def test_thunderbird_mbox_import(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mbox_path = root / "Inbox"
            box = mailbox.mbox(mbox_path)
            box.add(sample_message())
            box.flush()
            box.close()
            project = root / "project"
            argv = ["read_mail_archive.py", "--format", "thunderbird-mbox", "--path", str(mbox_path), "--project-dir", str(project)]
            with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
                self.assertEqual(read_mail_archive.main(), 0)
            database = read_json(output_dir(project) / DATA_NAME)
            self.assertEqual(len(database["messages"]), 1)
            self.assertEqual(database["messages"][0]["source_type"], "thunderbird-mbox")
            self.assertTrue(database["messages"][0]["attachments"][-1]["saved_path"].endswith("original.eml"))

    def test_apple_emlx_and_csv_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            emlx_root = root / "Mail"
            emlx_root.mkdir()
            raw = sample_message("Apple message").as_bytes()
            (emlx_root / "1.emlx").write_bytes(str(len(raw)).encode() + b"\n" + raw + b"\n<?xml version='1.0'?><plist/>")
            project = root / "project"
            argv = ["read_mail_archive.py", "--format", "apple-emlx", "--path", str(emlx_root), "--project-dir", str(project)]
            with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
                self.assertEqual(read_mail_archive.main(), 0)
            argv = ["export_mail_summary.py", "--project-dir", str(project), "--format", "csv", "--limit", "0"]
            with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
                self.assertEqual(export_mail_summary.main(), 0)
            export_path = project / "task-workspace" / "exports" / "mail-summary.csv"
            with export_path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["subject"], "Apple message")


if __name__ == "__main__":
    unittest.main()
