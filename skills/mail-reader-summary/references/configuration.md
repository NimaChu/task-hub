# Configuration and UID behavior

The project-local `task-workspace/config/mail-reader-config.json` contains non-secret settings. Credentials come from environment variables named by `username_env` and `password_env`.

```json
{
  "host": "imap.example.com",
  "port": 993,
  "ssl": true,
  "mailbox": "INBOX",
  "username_env": "MAIL_TASK_IMAP_USER",
  "password_env": "MAIL_TASK_IMAP_PASS",
  "import_existing_on_first_sync": true,
  "initial_history_months": 1,
  "save_attachments": true,
  "max_attachment_bytes": 26214400,
  "max_extracted_text_chars": 40000
}
```

`new` means not previously processed by this skill, based on the tuple `(source_id, UIDVALIDITY, UID)`. It does not mean the server-side `\\Seen` flag is absent. The reader deliberately avoids changing `\\Seen`.

First sync defaults to one calendar month, calculated from the local date with month-end clamping (March 31 minus one month is February 28 or 29). Server-side `SINCE` uses IMAP internal delivery date, inclusive at day precision, not the sender's Date header. `initial_history_months` changes the default for uninitialized folders. `--history-months 2` explicitly requests two months and can backfill an already-initialized folder without removing its cursor or duplicating records. Later ordinary syncs query only UIDs above the cursor. Explicit legacy `import_existing_on_first_sync: false` still means baseline-only unless a CLI history or count option overrides it. Pending historical windows persist if a fetch fails, so retrying ordinary sync can finish them.

Optional `include_sent: true` enables a second read-only folder sync. `sent_mailbox` is discovered from IMAP LIST when absent; an ambiguous result fails with a request for an explicit verified name. Both folders use the same initial date window and CLI override. `sent_initial_latest: N` optionally caps the latest N Sent messages within that window; zero means no count cap. Inbox and Sent use distinct source hashes/cursors; new markers from both folders survive one combined sync. Threading fields and `direction` identify sent evidence for Agent review. No candidate tasks are auto-created from outgoing messages.

Credentials resolve from process environment first, then Windows HKCU Environment. Current-user persistence is opt-in through `connect_local.py --persist-user-env`; it is plaintext per-user storage, not an encrypted credential vault. No credential belongs in configuration JSON.

The mailbox cursor is scoped by a hash of host, username, and mailbox. The raw username is not stored. If the server changes `UIDVALIDITY`, prior UIDs cannot safely be compared with new UIDs; the reader records the change and establishes a new current baseline instead of replaying the mailbox.

Provider settings can change. Confirm current values with the provider. The current project was supplied with an IMAP host using SSL on port 993, but the reusable asset remains provider-neutral.
