---
name: task-board
description: Turn user prompts or structured information from any channel into editable, auditable visual tasks. Create tasks directly, import channel task records, maintain project-local JSON, and open an auto-loading local HTML board. Works independently of mailbox or other channel skills.
metadata:
  short-description: Store tasks and open an auto-loading board
---

# Task Board

Maintain concrete task records in project-local JSON and render them into a self-contained HTML snapshot. The generated page embeds a safe copy of the current database, so it loads automatically under `file://` without a picker, fetch request, or server. Users can edit title, task content, assigner, deadline, status, and notes in the task drawer; these overrides persist automatically in that browser's local storage and are reapplied after regenerated snapshots. This skill does not access email and does not start a web server. Runtime files belong in the target project's shared `task-workspace/` directory; never modify skill templates during normal use.

Requires Python 3.9+ and no third-party packages.

Use a working Python executable on the current machine (`python`, `python3`, `py -3`, or a verified runtime path). Always resolve `--project-dir` to the user's target project, not the installed skill directory. Core JSON/HTML operations are cross-platform; Windows registry/Foxmail integration is optional. Headless environments should use `--no-open` and receive the resulting absolute file path.

## Use independently: tasks from user prompts

When the user describes work, extract concrete requirements, assigner, deadline, priority, and status from the prompt and create tasks directly. Do not ask for an email account or require the mail-reader skill. If a nonessential field is unspecified, leave it unknown; use `medium` and `pending` by default. Do not invent dates or completion evidence.

```powershell
python "<skill-dir>\scripts\task_board.py" --project-dir . --title "整理本周项目进展" --add-task "汇总各项目当前进展、风险与下一步安排。" --priority medium
```

Optional flags: `--assigner`, `--deadline YYYY-MM-DD`, `--task-status`, `--source-channel` (defaults to `manual`), and `--no-open`. Natural-language interpretation is performed by the Agent; the script stores the resulting concrete text and fields.

For multiple tasks or pasted channel information, create a project-local `task-workspace/audit/task-intake-YYYYMMDD-HHMMSS.json` with a `tasks` array and use `--import-tasks <file>`. Include `source_channel`, `source_reference`, `request_evidence`, and a stable `id` when the originating channel supplies one. Repeated IDs are rejected without partial writes; update an existing task rather than generating duplicate IDs. `parent_task_id` links follow-up tasks. Unknown channels are allowed as labels but do not imply a working connector. No access to WeCom or Teams is implemented by this skill.

## Task field writing contract

Apply this contract to tasks created from every channel. The board is the canonical place for these field-writing rules; channel adapters preserve raw provenance but must deliver records that follow them.

- `title`: required, Agent-authored one-sentence action title after reading the complete source and relevant context. Do not copy a message subject or mechanically truncate content. Normally use 8–24 Chinese characters, with a hard maximum of 60 characters.
- `task_content`: required, concise but complete human-readable scope. State the requested action, expected result, and material constraints; do not paste an entire message thread.
- `assigner`: human-readable person name or clear organizational role only, such as `项目负责人` or `HR`. Never put an email address, account ID, or channel label here. Keep addresses and handles in source provenance (`related_messages`, `source_reference`, or channel-specific fields). If the name cannot be established from reliable context, leave it empty instead of guessing from an address.
- `deadline`: normalized `YYYY-MM-DD` only when supported by the source or a documented interpretation. Keep ambiguous wording in `deadline_original`, explain normalization in `deadline_basis`, and leave the normalized value empty when it cannot be resolved safely.
- `priority`: use `high`, `medium`, or `low` with a concise `priority_reason`. Explicit low urgency is `low`; research without a deadline is normally `medium`; reserve `high` for near deadlines, blockers, or evidenced urgency.
- `status`: reflect execution state only. Communication belongs in `communication_status`; a reply or acknowledgement is not completion. Never add an acceptance stage.
- `request_evidence`, `response_evidence`, `completion_evidence`, and `review_reasoning`: keep concise, factual, and auditable. Separate requested work, communication, and verified delivery.
- `source_channel` and source identifiers: preserve the originating channel and stable provenance, but do not repeat the channel or raw account identifier in display fields merely to distinguish sources.
- `attachments`: use verified project-relative paths. `notes` remains user-managed. Use `parent_task_id` plus `relationship_reason` only for a genuinely new follow-up or revision task.

Read [database schema](references/schema.md) when constructing or validating an intake record.

## Initialize

```powershell
python "<skill-dir>\scripts\task_board.py" --project-dir . --init
```

This creates `task-workspace/`, copies the database template when absent, and renders the HTML template with the current database.

## Rebuild in a new or damaged project

```powershell
python "<skill-dir>\scripts\task_board.py" --project-dir . --rebuild
```

`--rebuild` regenerates the bundled HTML template with the current task data and repairs missing or invalid JSON. Replaced files are moved to `task-workspace/archive/` with timestamped `.bak-*` names. Valid task JSON is preserved; invalid JSON is backed up before a clean database template is restored. This works without the mailbox skill installed.

## Import reader tasks

Use the upstream `mail-reader-data.json` produced by the mailbox skill:

```powershell
python "<skill-dir>\scripts\task_board.py" --project-dir . --import-reader
```

The importer upserts by stable source task ID. It preserves workflow status, notes, and activity for existing tasks while refreshing source-derived fields. Agent-reviewed tasks may enter `acknowledged` when a reply exists but no completion evidence exists. Use `--prune-reader` after a complete mailbox re-review to remove stale mail-derived task records missing from the new reader set. After writing JSON, it regenerates the self-contained HTML and opens it by default. Use `--no-open` only for unattended or batch execution. The command always prints the absolute board path.

Read [database schema](references/schema.md) when adding fields or diagnosing imports.

## Update workflow status

```powershell
python "<skill-dir>\scripts\task_board.py" --project-dir . --set-status <task-id> in_progress --note "已确认需求"
```

Allowed statuses are `pending`, `acknowledged`, `in_progress`, and `completed`. There is no acceptance column. Legacy `review` tasks migrate to `completed`. A verified sent delivery email completes a task; ordinary acknowledgement does not. Positive recipient feedback leaves completion unchanged. Revision requests become new tasks with `parent_task_id` pointing to the original, which stays completed. On import, newly evidenced `delivered`/`completed` events update existing workflow status once; repeating the same evidence preserves subsequent manual status changes.

Status changes also regenerate and open the board by default. Add `--no-open` when no visible browser window is wanted.

## Open locally

```powershell
python "<skill-dir>\scripts\task_board.py" --project-dir . --open
```

This first regenerates `task-workspace/task-board.html` from `task-data.json`, then opens it as a local file without starting a server. The page reads its embedded snapshot automatically; do not ask the user to select or import JSON manually. Always report the absolute HTML path as a clickable file link when operating in Codex. If the browser cannot be launched, return that path so the user can open it directly.

Change priority and deadline directly on a card. Drag the card into another column to change status; the card also provides a status select for keyboard and touch use. Click its title to inspect evidence, attachments, editable details, and linked original/revision tasks. Changes save automatically in browser-local storage. Use **导出修改后 JSON** for a portable edited database. Browser-local changes stay on that browser profile and machine.

Each task requires an Agent-authored `title` plus a fuller `task_content`. The card displays only `title`; the detail drawer shows and edits both. Write the title after understanding the complete user prompt or channel evidence. It must summarize the actionable work in one concise sentence (normally 8–24 Chinese characters or at most 60 characters), and must not be a copied source subject or an automatic truncation. For direct creation use `--title "一句话标题" --add-task "完整任务内容"`; general JSON imports must also provide both fields.

Reader imports intentionally skip candidates that do not yet have `title`. This keeps deterministic extraction drafts off the visual board until an Agent has reviewed the underlying source and written the final title/task pair.

The task drawer displays the curated request excerpt, reply excerpt, completion evidence, Agent reasoning, related message audit trail, and attachment state. Only attachments with a project-relative `saved_path` are rendered as clickable links. Container-only records remain visible but are labeled as not directly openable.

Within each status column, order tasks by `high`, `medium`, then `low`; within one priority, show the nearest normalized deadline first and tasks without a deadline last. Research, exploration, and proposal work without a stated deadline normally starts at `medium`; reserve `high` for a near explicit deadline, material blocker, or separately evidenced urgency. Preserve a concise `priority_reason` so users can audit the rating.

On Windows, browsers may preview or download `.eml` files instead of handing them to the system file association. When the user asks to open board EML attachments in Foxmail, register the current-user protocol once:

```powershell
python "<skill-dir>\scripts\register_eml_handler.py" --foxmail-exe "<Foxmail.exe>"
```

The renderer enables `mailtask-foxmail:` only when it detects the current user's Windows protocol registration. Other machines get ordinary file links and an EML download fallback. Regenerate the HTML after registering the protocol or moving the workspace to another machine. The launcher accepts only an existing local file with an `.eml` suffix, invokes the Windows Shell `open` action (equivalent to double-clicking the file), and restores the matching Foxmail message window when Windows leaves it minimized or behind the browser. The browser may ask for external-application confirmation on first use. Each EML row also keeps a **下载 EML** fallback. Re-register after moving the skill or Python runtime; never hard-code one user's installation path in the skill template.

## Boundaries

- Do not read or connect to a mailbox from this skill.
- Keep database and HTML outputs in the shared project folder `task-workspace/`; keep this skill folder unchanged.
- Treat project JSON as the portable baseline and HTML as a generated snapshot. Browser-local overrides are the interactive layer and take precedence in that browser; export them when they must become a portable database. Regenerate HTML after every project-JSON mutation and immediately before opening it.
- Render imported strings as untrusted text, never executable HTML.
- Treat `task-data.json` as private project data. Do not commit, upload, or share it without explicit user direction.

## Shared workspace layout

Optional project branding lives in `task-workspace/config/brand.json`: `name`, `title`, `subtitle`, `website` (HTTPS), `primary` (six-digit hex), and `logo` (workspace-relative PNG path, normally `assets/brand/`). The renderer embeds the PNG into the HTML so offline viewing needs no network. Keep company-specific assets/configuration in the project; an independently installed skill without branding renders a neutral board. Record the official logo source in the project brand config. Brand changes must go through this configuration/template and regeneration, not only edits to the generated HTML.

Both skills use `task-workspace/config/mail-reader-config.json`, `task-workspace/data/mail-reader-data.json`, `task-workspace/data/task-data.json`, and the root `task-board.html`. Attachments retain workspace-relative `attachments/...` paths. Put logs/outcomes in `logs/`, reviews in `audit/`, verification scripts in `audit/tests/`, backups in `archive/backups/`, and retired diagnostics in `archive/diagnostics/`. The bundled `workspace_layout.py` migrates legacy root files, preserving conflicting versions for explicit resolution. Keep this module identical in both skill packages. Each package bundles its own templates under `assets/`; task-board templates use channel-neutral names. New managed names use lowercase kebab-case; dated review snapshots use `<purpose>-YYYYMMDD-HHMMSS.json`. Preserve original attachment names. Retain the legacy browser storage key; when the user requests a path rename, explain that browser-local edits may require export from the previous page.
