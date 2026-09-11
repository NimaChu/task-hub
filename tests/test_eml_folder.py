import sys
import tempfile
import unittest
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "mail-reader-summary" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import read_eml_folder


class EmlFolderImportTests(unittest.TestCase):
    def make_message(self, when, subject="Action", attachment=True):
        message = EmailMessage()
        message["From"] = "Alice <alice@example.com>"
        message["To"] = "Bob <bob@example.com>"
        message["Subject"] = subject
        message["Date"] = format_datetime(when)
        message["Message-ID"] = f"<{subject.lower()}@example.com>"
        message.set_content("Please prepare the audited result.")
        if attachment:
            message.add_attachment(b"evidence", maintype="text", subtype="plain", filename="proof.txt")
        return message.as_bytes()

    def test_incremental_import_preserves_eml_and_attachment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            exported = root / "exported"
            exported.mkdir()
            raw = self.make_message(datetime.now(timezone.utc), "Current")
            (exported / "one.eml").write_bytes(raw)
            (exported / "duplicate.eml").write_bytes(raw)

            first = read_eml_folder.import_folder(project, exported)
            self.assertEqual(first["new_message_count"], 1)
            database = read_eml_folder.read_json(
                project / "task-workspace" / read_eml_folder.DATA_NAME
            )
            self.assertEqual(len(database["messages"]), 1)
            record = database["messages"][0]
            self.assertTrue((project / "task-workspace" / record["eml_path"]).is_file())
            self.assertTrue(record["attachments"][0]["saved"])
            self.assertTrue(
                (project / "task-workspace" / record["attachments"][0]["saved_path"]).is_file()
            )
            self.assertTrue(record["review_required"])

            second = read_eml_folder.import_folder(project, exported)
            self.assertEqual(second["new_message_count"], 0)

            moved_export = root / "moved-export"
            moved_export.mkdir()
            (moved_export / "same-message.eml").write_bytes(raw)
            moved = read_eml_folder.import_folder(project, moved_export)
            self.assertEqual(moved["new_message_count"], 0)
            moved_database = read_eml_folder.read_json(
                project / "task-workspace" / read_eml_folder.DATA_NAME
            )
            self.assertEqual(len(moved_database["messages"]), 1)

    def test_default_month_window_is_soft(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            exported = root / "exported"
            exported.mkdir()
            (exported / "old.eml").write_bytes(
                self.make_message(datetime(2020, 1, 1, tzinfo=timezone.utc), "Old", False)
            )
            first = read_eml_folder.import_folder(project, exported)
            self.assertEqual(first["new_message_count"], 0)
            wider = read_eml_folder.import_folder(project, exported, history_months=120)
            self.assertEqual(wider["new_message_count"], 1)


if __name__ == "__main__":
    unittest.main()
