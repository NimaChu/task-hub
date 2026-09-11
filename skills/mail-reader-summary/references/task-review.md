# Agent task review

Review records marked `is_new` or `review_required`; a later sync must not hide unfinished review. Read the complete body, relevant thread messages, and available attachment text. Keep non-actionable mail with an empty task list.

Apply a project-local manifest with `scripts/apply_task_review.py --project-dir <project> --review <manifest>`. Routine reviews use `replace_all: false`, list every reviewed message in `reviewed_message_keys`, and preserve stable task IDs. Use message keys for IMAP/EML/archive records or local IDs where supported. Record each related message role as request, response, delivery, or feedback.

Every reviewed task needs:

- an Agent-authored `title`, normally 8–24 Chinese characters or at most 60 characters; it is not the email subject or a truncation;
- fuller `task_content` with scope, deliverables, and constraints;
- a human name or organizational role in `assigner`; keep addresses in provenance;
- only evidenced deadlines, priority, status, and reasoning.

A sent message completes the original task only when it verifiably delivers the requested work to the intended recipient. A promise, draft, acknowledgement, filename, or quoted text is insufficient. Positive feedback leaves the task completed. A concrete revision request creates a new stable task linked by `parent_task_id`; do not reopen the original merely for revisions. Other-channel delivery remains a manual status change unless that channel provides evidence.

When importing into task-board, follow that skill's full field-writing contract. Reapplying a stable task ID updates rather than duplicates it.
