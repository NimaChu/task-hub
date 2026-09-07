# Task database schema

`task-workspace/data/task-data.json` is the portable baseline. The companion mail-reader skill writes `mail-reader-data.json` into the same shared folder by default. `task-board.html` is a generated, self-contained snapshot containing an escaped copy of the current database; regenerate it after every database change and before opening. Front-end edits to `title`, `task_content`, `assigner`, `deadline`, `status`, and `notes` are stored as a browser-local override layer and can be exported from the page as `task-data.edited.json`.

Each task contains:

- `source_channel`: `manual`, `email`, `wecom`, `teams`, or another named channel. A label does not imply a connector exists.
- `source_reference`: original message/document ID or URL, or empty for direct prompts.
- Email-specific `source_uid`, `source_subject`, `source_message_key`, and `related_messages` are optional for non-email tasks.
- General import format is `{ "tasks": [{ "title": "一句话标题", "task_content": "完整任务内容", "source_channel": "manual", "request_evidence": "用户原始要求" }] }`. Both `title` and `task_content` are required. Each record may specify `id`, `status`, `priority`, `deadline`, `assigner`, `notes`, and parent linkage. Duplicate IDs fail the import rather than overwrite silently.

- `id`: stable board ID, normally copied from the reader's source task ID.
- `source_task_id`, `source_message_key`, `source_uid`, and `source_subject`: immutable mail provenance.
- `status`: `pending`, `acknowledged`, `in_progress`, or `completed`. Legacy `review` migrates to `completed`.
- `parent_task_id`: stable ID of the original task when this is a revision request; empty for original tasks. Links display in both directions.
- `relationship_reason`: concise revision-request evidence.
- `applied_completion_evidence`: last delivery/completion evidence applied to status; identical repeated imports do not override later manual changes.
- `title`: required Agent-authored one-sentence task title, written after understanding the complete source; distinct from the source subject and not a mechanical truncation. Cards display this field.
- `task_content`: fuller concrete requested work shown in task details.
- `assigner`: human-readable dispatcher name or organizational role. Never store an email address, account ID, or channel label here; those belong in provenance fields. If reliable source context does not reveal a name, leave this empty rather than guessing from the address.
- `deadline`: normalized deadline when available; empty means unknown.
- `priority`: `high`, `medium`, or `low`. Research/proposal work without a deadline defaults to `medium`; explicit low urgency maps to `low`; near deadlines or material blockers may map to `high`.
- `priority_reason`: concise evidence for the rating.
- `attachments`: project-relative attachment paths.
- `communication_status`: `not_replied`, `replied`, or `meeting_accepted`; it never implies completion.
- `completion_state` and `completion_evidence`: whether completion is evidenced and the audit basis.
- `request_evidence`, `response_evidence`, and `review_reasoning`: concise human-readable audit fields.
- `related_messages`: source and reply message records with stable IDs and excerpts.
- `received_at`, `created_at`, and `updated_at`.
- `notes`: user-managed notes.
- `activity`: timestamped workflow history.

The top-level `imports` list records source path, import time, number created, and number refreshed. Upsert by `source_task_id`; never deduplicate by title alone.
