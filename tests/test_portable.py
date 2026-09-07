"""Offline distribution checks; all mail and tasks below are synthetic."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PortableSkills(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='task-hub-test-')
        self.base = Path(self.tmp.name)
        self.project = self.base / 'project with spaces'
        self.project.mkdir()
        self.packages = self.base / 'installed skills'
        shutil.copytree(ROOT / 'skills', self.packages, ignore=shutil.ignore_patterns('__pycache__'))
        self.original = self.digest()

    def tearDown(self):
        self.assertEqual(self.original, self.digest(), 'Runtime modified installed skills')
        self.tmp.cleanup()

    def digest(self):
        return {p.relative_to(self.packages).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.packages.rglob('*') if p.is_file()}

    def run_script(self, skill, script, *args, ok=True):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
        result = subprocess.run([sys.executable, str(self.packages / skill / 'scripts' / script),
                                 '--project-dir', str(self.project), *args],
                                env=env, cwd=self.base, capture_output=True, text=True, encoding='utf-8')
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def read(self, name):
        return json.loads((self.project / 'task-workspace' / name).read_text(encoding='utf-8'))

    def write(self, name, data):
        path = self.project / 'task-workspace' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding='utf-8')

    def test_board_independent_rebuild(self):
        shutil.rmtree(self.packages / 'mail-reader-summary')
        self.original = self.digest()
        self.run_script('task-board', 'task_board.py', '--add-task', 'Prepare a project summary.',
                        '--title', 'Prepare project summary', '--no-open')
        data = self.read('data/task-data.json')
        self.assertEqual(len(data['tasks']), 1)
        self.assertEqual(data['tasks'][0]['source_channel'], 'manual')
        board = self.project / 'task-workspace/task-board.html'
        board.unlink()
        self.run_script('task-board', 'task_board.py', '--rebuild')
        self.assertEqual(self.read('data/task-data.json'), data)
        self.assertIn('Prepare project summary', board.read_text(encoding='utf-8'))
        self.run_script('task-board', 'task_board.py', '--add-task', 'Example', '--title', 'Example',
                        '--assigner', 'person@example.invalid', '--no-open', ok=False)
        self.assertEqual(self.read('data/task-data.json'), data)

    def test_reader_independent_init(self):
        shutil.rmtree(self.packages / 'task-board')
        self.original = self.digest()
        self.run_script('mail-reader-summary', 'read_mail.py', '--init')
        self.run_script('mail-reader-summary', 'read_mail.py', '--summary')
        self.assertEqual(self.read('data/mail-reader-data.json')['messages'], [])
        self.assertEqual(self.read('config/mail-reader-config.json')['host'], 'imap.example.com')
        self.assertFalse((self.project / 'task-workspace/task-board.html').exists())

    def test_review_import_attachments_and_repeat(self):
        self.run_script('mail-reader-summary', 'read_mail.py', '--init')
        messages = []
        for uid in (1, 2):
            messages.append(dict(message_key=f'synthetic:1:{uid}', uid=uid, sender='Reviewer <reviewer@example.invalid>',
                                 subject='Synthetic request', body_text='Prepare a test summary.',
                                 review_required=True, tasks=[dict(id=f'draft-{uid}', extraction='deterministic')],
                                 attachments=[dict(filename=f'input-{uid}.txt', saved_path=f'attachments/input-{uid}.txt')]))
            path = self.project / f'task-workspace/attachments/input-{uid}.txt'
            path.write_text('Synthetic attachment.', encoding='utf-8')
        db = self.read('data/mail-reader-data.json')
        db['messages'] = messages
        self.write('data/mail-reader-data.json', db)
        review = dict(replace_all=False, reviewed_message_keys=['synthetic:1:1', 'synthetic:1:2'], tasks=[
            dict(id='synthetic-task-1', primary_message_key='synthetic:1:1', title='Prepare test summary',
                 task_content='Summarize both test inputs. </script><script>alert(1)</script>', assigner='Reviewer',
                 related_message_keys=['synthetic:1:1', 'synthetic:1:2'],
                 attachment_message_keys=['synthetic:1:1', 'synthetic:1:2'])])
        self.write('audit/review.json', review)
        for _ in range(2):
            self.run_script('mail-reader-summary', 'apply_task_review.py', '--review', 'task-workspace/audit/review.json')
            self.run_script('task-board', 'task_board.py', '--import-reader', '--no-open')
        tasks = self.read('data/task-data.json')['tasks']
        self.assertEqual(len(tasks), 1)
        self.assertEqual(len(tasks[0]['attachments']), 2)
        self.assertTrue(all(not m['review_required'] for m in self.read('data/mail-reader-data.json')['messages']))
        html = (self.project / 'task-workspace/task-board.html').read_text(encoding='utf-8')
        self.assertNotIn('</script><script>alert(1)</script>', html)
        self.assertIn('input-2.txt', html)


if __name__ == '__main__':
    unittest.main()
