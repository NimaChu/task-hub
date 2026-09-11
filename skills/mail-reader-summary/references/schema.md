# Reader data schema

`task-workspace/data/mail-reader-data.json` contains:

- `mailboxes`: cursor state keyed by privacy-preserving `source_id`; each value has `host`, `mailbox`, `uidvalidity`, and `last_uid`.
- `messages`: processed new-message records retained for provenance.
- `sync`: most recent sync status and counts.

Each message includes `message_key`, `source_id`, `uidvalidity`, `uid`, `is_new`, sender, recipients, subject, received time, body text, attachment metadata, and zero or more candidate `tasks`. Local Foxmail-cache records can additionally include `local_id`, `attachment_index_text`, `content_scope`, and `attachments_status`. Their attachment objects include `name`, `indexed_name`, `attachment_index`, `foxmail_container`, `container_position`, `encoded_size`, and `binary_status`; the container byte range is verified provenance, not an exported standalone file. Generic EML and supported local archives use a format-specific `source_type`, a SHA-256-based `message_key`, null UID fields, relative `source_file`, saved `eml_path`, and an auditable `date_basis`. Top-level `eml_sources` tracks their processed content hashes and older baseline hashes independently of IMAP cursors.

Each candidate task includes:

```json
{
  "id": "mail-<source>-<uidvalidity>-<uid>-task-1",
  "source_message_key": "<source>:<uidvalidity>:<uid>",
  "source_uid": 101,
  "source_subject": "邮件主题",
  "task_content": "具体任务要求",
  "assigner": "邮件派发人",
  "deadline": "2026-09-30",
  "attachments": [],
  "is_new": true,
  "extraction": "deterministic"
}
```

Downstream consumers must upsert by `id` or `source_message_key` plus candidate index, never by title alone.

Deterministic candidates do not invent a final title. Reviewed tasks require an Agent-authored `title` and additionally carry `suggested_status` (`pending`, `acknowledged`, `in_progress`, `completed`), `completion_state` (`not_completed`, `delivered`, `completed`), and `completion_evidence`. The title is written after reviewing the full mail/thread/attachment evidence, is distinct from `source_subject`, and is not a truncation of `task_content`. Board imports skip untitled candidates. Verified sent delivery sets `delivered` and completes the task. Approval adds evidence without changing status. Revision requests create a new task with `parent_task_id` (the original stable task ID) and `relationship_reason`; keep the original completed. Task reviews can locate IMAP messages by `primary_message_key`, `related_message_keys`, `attachment_message_keys`; local-cache reviews may use local IDs. Use explicit `message_roles` keyed by message key, without hard-coded user addresses.
