#!/usr/bin/env python3
"""Project-local JSON task store and self-contained local board generator."""
from __future__ import annotations

import argparse
import base64
import html
import re
import json
import shutil
import sys
import webbrowser
import uuid
from datetime import datetime, timezone
from pathlib import Path
from workspace_layout import READER_DATA_NAME, TASK_DATA_NAME, prepare_workspace, archive_dir

SKILL_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = SKILL_DIR / "assets"
OUTPUT_DIR_NAME = "task-workspace"
DATA_NAME = TASK_DATA_NAME
BOARD_NAME = "task-board.html"
EMBED_TOKEN = "__MAIL_TASK_DATA_JSON__"
STATUSES = {"pending", "acknowledged", "in_progress", "completed"}


def migrate_statuses(database: dict) -> bool:
    changed = False
    for task in database.get("tasks", []):
        if 'source_channel' not in task:
            task['source_channel'] = 'email' if task.get('source_task_id') or task.get('source_message_key') else 'manual'
            changed = True
        if task.get("status") == "review":
            task["status"] = "completed"
            task.setdefault("activity", []).insert(0, {"at": utc_now(), "text": "取消待验收阶段：已交付任务迁移为已完成"})
            changed = True
    if changed:
        database["updated_at"] = utc_now()
    return changed


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def write_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(value)
    temporary.replace(path)


def output_dir(project: Path) -> Path:
    return project / OUTPUT_DIR_NAME


def backup_file(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = archive_dir(path)
    archive.mkdir(parents=True, exist_ok=True)
    backup = archive / f"{path.name}.bak-{stamp}"
    counter = 2
    while backup.exists():
        backup = archive / f"{path.name}.bak-{stamp}-{counter}"
        counter += 1
    path.replace(backup)
    return backup


def validate_database(value: dict) -> None:
    if not isinstance(value, dict) or not {"version", "tasks", "imports", "updated_at"}.issubset(value) or not isinstance(value["tasks"], list):
        raise ValueError("invalid task database schema")


def board_document(database: dict, workspace: Path | None = None) -> str:
    template = (ASSETS_DIR / BOARD_NAME).read_text(encoding="utf-8")
    brand_path = workspace / 'config/brand.json' if workspace else None
    brand = read_json(brand_path) if brand_path and brand_path.exists() else {}
    header = ''
    if brand:
        color = str(brand.get('primary', '#006cb4'))
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            raise ValueError('Brand primary must be a hex color')
        logo = (workspace / brand['logo']).resolve()
        logo.relative_to(workspace.resolve())
        if logo.suffix.lower() != '.png' or not logo.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Brand logo must be a local PNG')
        data_url = 'data:image/png;base64,' + base64.b64encode(logo.read_bytes()).decode('ascii')
        name = html.escape(str(brand.get('name', '')), quote=True)
        header = f'<style>:root{{--navy:{color};--blue:{color}}}</style><div class="brand-logo"><img src="{data_url}" alt="{name}" width="189" height="67"></div>'
        title = html.escape(str(brand.get('title', '任务工作台')))
        template = template.replace('<title>任务工作台</title>', f'<title>{title}</title>').replace('<h1>任务工作台</h1>', f'<h1>{title}</h1>')
    template = template.replace('<!-- PROJECT_BRAND -->', header)
    if template.count(EMBED_TOKEN) != 1:
        raise ValueError(f"board template must contain exactly one {EMBED_TOKEN} token")
    # Protocol registration belongs to the rendering machine, not the shared DB.
    foxmail_protocol = False
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\mailtask-foxmail\shell\open\command"):
                foxmail_protocol = True
        except OSError:
            pass
    payload = json.dumps({**database, "ui": {"foxmail_protocol": foxmail_protocol}}, ensure_ascii=False, separators=(",", ":"))
    # An email field can contain arbitrary HTML. Escaping markup-significant
    # characters prevents it from terminating the inert JSON script element.
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return template.replace(EMBED_TOKEN, payload, 1)


def render_board(project: Path) -> Path:
    workspace = output_dir(project)
    prepare_workspace(workspace)
    database = read_json(workspace / DATA_NAME)
    validate_database(database)
    if migrate_statuses(database):
        write_json(workspace / DATA_NAME, database)
    board = workspace / BOARD_NAME
    write_text(board, board_document(database, workspace))
    return board.resolve()


def open_board(project: Path) -> tuple[Path, bool]:
    initialize(project)
    board = render_board(project)
    return board, bool(webbrowser.open(board.as_uri()))


def initialize(project: Path) -> list[str]:
    workspace = output_dir(project)
    prepare_workspace(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    created = []
    database = workspace / DATA_NAME
    if not database.exists():
        shutil.copyfile(ASSETS_DIR / Path(DATA_NAME).name, database)
        created.append(f"{OUTPUT_DIR_NAME}/{DATA_NAME}")
    board = workspace / BOARD_NAME
    if not board.exists():
        render_board(project)
        created.append(f"{OUTPUT_DIR_NAME}/{BOARD_NAME}")
    return created


def rebuild(project: Path) -> list[str]:
    workspace = output_dir(project)
    prepare_workspace(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    actions = []
    database = workspace / DATA_NAME
    if not database.exists():
        shutil.copyfile(ASSETS_DIR / Path(DATA_NAME).name, database)
        actions.append(f"created {OUTPUT_DIR_NAME}/{DATA_NAME}")
    else:
        try:
            value = read_json(database)
            validate_database(value)
            actions.append(f"preserved valid {OUTPUT_DIR_NAME}/{DATA_NAME}")
        except (OSError, ValueError, json.JSONDecodeError):
            backup = backup_file(database)
            shutil.copyfile(ASSETS_DIR / Path(DATA_NAME).name, database)
            actions.append(f"repaired {OUTPUT_DIR_NAME}/{DATA_NAME}; backup={backup.name}")
    board = workspace / BOARD_NAME
    expected = board_document(read_json(database), workspace)
    if not board.exists():
        write_text(board, expected)
        actions.append(f"created {OUTPUT_DIR_NAME}/{BOARD_NAME}")
    elif board.read_text(encoding="utf-8") == expected:
        actions.append(f"preserved current {OUTPUT_DIR_NAME}/{BOARD_NAME}")
    else:
        backup = backup_file(board)
        write_text(board, expected)
        actions.append(f"rebuilt {OUTPUT_DIR_NAME}/{BOARD_NAME}; backup={backup.name}")
    return actions


def import_reader(project: Path, source: Path, prune_reader: bool = False) -> tuple[int, int, int]:
    initialize(project)
    reader = read_json(source)
    workspace = output_dir(project)
    database_path = workspace / DATA_NAME
    database = read_json(database_path)
    existing = {task.get("source_task_id") or task.get("id"): task for task in database.setdefault("tasks", [])}
    created = refreshed = 0
    imported_ids = set()
    for message in reader.get("messages", []):
        for candidate in message.get("tasks", []):
            source_task_id = candidate.get("id")
            if source_task_id:
                imported_ids.add(source_task_id)
            title = str(candidate.get("title", "")).strip()
            # Deterministic mail extraction only proposes task candidates. Do not
            # leak its unreviewed/overlong wording onto the board; an Agent review
            # must supply the human-readable card title first.
            if not source_task_id or not title:
                continue
            assigner = str(candidate.get("assigner", "")).strip()
            if "@" in assigner:
                raise ValueError(f"assigner must be a human-readable name, not an email address: {source_task_id}")
            imported_ids.add(source_task_id)
            timestamp = utc_now()
            source_fields = {
                "source_channel": "email",
                "id": source_task_id,
                "source_task_id": source_task_id,
                "source_message_key": candidate.get("source_message_key", message.get("message_key", "")),
                "source_uid": candidate.get("source_uid", message.get("uid")),
                "source_subject": candidate.get("source_subject", message.get("subject", "")),
                "title": title,
                "task_content": candidate.get("task_content", ""),
                "assigner": assigner,
                "deadline": candidate.get("deadline", ""),
                "deadline_original": candidate.get("deadline_original", ""),
                "deadline_basis": candidate.get("deadline_basis", ""),
                "priority": candidate.get("priority", "medium"),
                "priority_reason": candidate.get("priority_reason", ""),
                "communication_status": candidate.get("communication_status", "not_replied"),
                "completion_state": candidate.get("completion_state", "not_completed"),
                "request_evidence": candidate.get("request_evidence", ""),
                "response_evidence": candidate.get("response_evidence", ""),
                "completion_evidence": candidate.get("completion_evidence", ""),
                "review_reasoning": candidate.get("review_reasoning", ""),
                "related_messages": candidate.get("related_messages", []),
                "parent_task_id": candidate.get("parent_task_id", ""),
                "relationship_reason": candidate.get("relationship_reason", ""),
                "extraction": candidate.get("extraction", ""),
                "reviewed_at": candidate.get("reviewed_at", ""),
                "attachments": candidate.get("attachments", []),
                "received_at": message.get("received_at", ""),
                "updated_at": timestamp
            }
            if source_task_id in existing:
                record = existing[source_task_id]
                record.update(source_fields)
                if candidate.get("completion_state") in {"delivered", "completed"} and candidate.get("completion_evidence"):
                    event = candidate.get("completion_evidence")
                    if record.get("applied_completion_evidence") != event:
                        record["status"] = "completed"
                        record["applied_completion_evidence"] = event
                        record.setdefault("activity", []).insert(0, {"at": timestamp, "text": "邮件交付完成：" + event})
                refreshed += 1
            else:
                suggested = candidate.get("suggested_status", "pending")
                if suggested == "review" or (candidate.get("completion_state") in {"delivered", "completed"} and candidate.get("completion_evidence")):
                    suggested = "completed"
                if suggested not in STATUSES:
                    suggested = "pending"
                record = {**source_fields, "status": suggested, "notes": "", "created_at": timestamp, "activity": [{"at": timestamp, "text": "由 Agent 从邮件线程整理并导入"}]}
                if suggested == "completed":
                    record["applied_completion_evidence"] = candidate.get("completion_evidence", "")
                database["tasks"].insert(0, record)
                existing[source_task_id] = record
                created += 1
    try:
        source_label = source.relative_to(project).as_posix()
    except ValueError:
        source_label = source.name
    pruned = 0
    if prune_reader:
        kept = []
        for task in database["tasks"]:
            source_id = task.get("source_task_id")
            if task.get('source_channel', 'email') == 'email' and source_id and source_id not in imported_ids:
                pruned += 1
            else:
                kept.append(task)
        database["tasks"] = kept
    database.setdefault("imports", []).insert(0, {"source": source_label, "imported_at": utc_now(), "created": created, "refreshed": refreshed, "pruned": pruned})
    database["updated_at"] = utc_now()
    write_json(database_path, database)
    render_board(project)
    return created, refreshed, pruned


def set_status(project: Path, task_id: str, status: str, note: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"Unsupported status: {status}")
    initialize(project)
    path = output_dir(project) / DATA_NAME
    database = read_json(path)
    task = next((item for item in database.get("tasks", []) if item.get("id") == task_id), None)
    if task is None:
        raise KeyError(f"Task not found: {task_id}")
    timestamp = utc_now()
    task["status"] = status
    task["updated_at"] = timestamp
    task.setdefault("activity", []).insert(0, {"at": timestamp, "text": note or f"状态更新为 {status}"})
    database["updated_at"] = timestamp
    write_json(path, database)
    render_board(project)


def add_tasks(project: Path, items: list[dict]) -> int:
    initialize(project)
    path = output_dir(project) / DATA_NAME
    database = read_json(path)
    ids = {t['id'] for t in database['tasks']}
    records = []
    for item in items:
        content = str(item.get('task_content', '')).strip()
        if not content:
            raise ValueError('task_content is required')
        title = str(item.get('title', '')).strip()
        if not title:
            raise ValueError('title is required; write a concise one-sentence task title after understanding the source')
        assigner = str(item.get('assigner', '')).strip()
        if '@' in assigner:
            raise ValueError('assigner must be a human-readable name, not an email address; keep the address in source provenance')
        channel = str(item.get('source_channel', 'manual'))
        task_id = str(item.get('id') or f'{channel}-{uuid.uuid4().hex}')
        if task_id in ids:
            raise ValueError(f'Task already exists: {task_id}; use its existing record instead of duplicating')
        status = item.get('status', 'pending')
        priority = item.get('priority', 'medium')
        if status not in STATUSES or priority not in {'high', 'medium', 'low'}:
            raise ValueError('Invalid status or priority')
        deadline = item.get('deadline', '')
        if deadline:
            datetime.strptime(deadline, '%Y-%m-%d')
        timestamp = utc_now()
        record = {**item, 'id': task_id, 'title': title, 'task_content': content, 'source_channel': channel,
                  'status': status, 'priority': priority, 'deadline': deadline,
                  'assigner': assigner, 'notes': item.get('notes', ''),
                  'source_reference': item.get('source_reference', ''),
                  'request_evidence': item.get('request_evidence', content),
                  'attachments': item.get('attachments', []), 'created_at': timestamp,
                  'updated_at': timestamp, 'activity': [{'at': timestamp, 'text': '从用户描述或渠道信息创建任务'}]}
        records.append(record)
        ids.add(task_id)
    for record in records:
        if record.get('parent_task_id') and (record['parent_task_id'] not in ids or record['parent_task_id'] == record['id']):
            raise ValueError('Invalid parent_task_id')
    database['tasks'] = records + database['tasks']
    database['updated_at'] = utc_now()
    write_json(path, database)
    render_board(project)
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import task JSON, generate, and open a standalone local board.")
    parser.add_argument("--project-dir", default=".")
    parser.add_argument("--init", action="store_true")
    parser.add_argument('--add-task', help='Create a task directly from user-described content')
    parser.add_argument('--title', help='Concise Agent-authored task title (required with --add-task)')
    parser.add_argument('--import-tasks', help='JSON file with a tasks array from any channel')
    parser.add_argument('--assigner', default='')
    parser.add_argument('--deadline', default='')
    parser.add_argument('--priority', default='medium', choices=['high', 'medium', 'low'])
    parser.add_argument('--task-status', default='pending', choices=sorted(STATUSES))
    parser.add_argument('--source-channel', default='manual')
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--import-reader", nargs="?", const=READER_DATA_NAME)
    parser.add_argument("--prune-reader", action="store_true", help="remove previously imported mail tasks absent from the current reader data")
    parser.add_argument("--set-status")
    parser.add_argument("status", nargs="?")
    parser.add_argument("--note", default="")
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--no-open", action="store_true", help="do not open after importing or changing status")
    args = parser.parse_args()
    if not any((args.init, args.rebuild, args.import_reader, args.set_status, args.open, args.add_task, args.import_tasks)):
        parser.error("choose --init, --rebuild, --import-reader, --set-status, or --open")
    project = Path(args.project_dir).expanduser().resolve()
    if args.add_task:
        if not args.title:
            parser.error('--add-task requires --title')
        print(f'Created {add_tasks(project, [dict(title=args.title, task_content=args.add_task, assigner=args.assigner, deadline=args.deadline, priority=args.priority, status=args.task_status, source_channel=args.source_channel)])} task')
    if args.import_tasks:
        incoming = Path(args.import_tasks).expanduser()
        if not incoming.is_absolute():
            incoming = project / incoming
        payload = read_json(incoming)
        print(f'Created {add_tasks(project, payload["tasks"])} tasks')
    if args.init:
        created = initialize(project)
        print("Created: " + (", ".join(created) if created else "nothing"))
    if args.rebuild:
        print("\n".join(rebuild(project)))
    if args.import_reader:
        source = Path(args.import_reader).expanduser()
        if not source.is_absolute():
            shared_source = output_dir(project) / source
            source = shared_source if shared_source.exists() else project / source
        created, refreshed, pruned = import_reader(project, source.resolve(), args.prune_reader)
        print(f"Imported tasks: created={created}, refreshed={refreshed}, pruned={pruned}")
    if args.set_status:
        if not args.status:
            parser.error("--set-status requires a status argument")
        set_status(project, args.set_status, args.status, args.note)
        print(f"Updated {args.set_status} to {args.status}")
    if args.open:
        board, opened = open_board(project)
        print(f"Opened {board}" if opened else f"Could not open automatically. Board: {board}")
    elif (args.import_reader or args.set_status or args.add_task or args.import_tasks) and not args.no_open:
        board, opened = open_board(project)
        print(f"Opened {board}" if opened else f"Could not open automatically. Board: {board}")
    else:
        board = (output_dir(project) / BOARD_NAME).resolve()
        if board.exists():
            print(f"Board: {board}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
