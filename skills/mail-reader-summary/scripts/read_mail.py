#!/usr/bin/env python3
"""Read-only IMAP synchronizer with UID history, attachments, and task extraction."""
from __future__ import annotations

import argparse
import calendar
import base64
import email
import getpass
import hashlib
import html
import imaplib
import json
import os
import re
import shutil
import sys
import zipfile
from datetime import date, datetime, timezone
from email.header import decode_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree
from workspace_layout import CONFIG_NAME, READER_DATA_NAME, prepare_workspace, archive_dir

SKILL_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = SKILL_DIR / "assets"
OUTPUT_DIR_NAME = "task-workspace"
DATA_NAME = READER_DATA_NAME
ASSET_NAMES = {CONFIG_NAME: '.mail-reader-config.json', DATA_NAME: 'mail-reader-data.json'}
ATTACHMENTS_DIR = "attachments"
ACTION_RE = re.compile(r"请|麻烦|需要|务必|协助|帮忙|安排|处理|跟进|确认|完成|提交|准备|修改|回复|评审|审批|review|todo|action required", re.I)
DEADLINE_RE = re.compile(r"(?:截止(?:时间|日期)?|请于|在|before|by)\s*(20\d{2}[年./-]\d{1,2}[月./-]\d{1,2}日?|\d{1,2}[月./-]\d{1,2}日?|(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*)(?:\s*(?:前|之前|完成))?", re.I)
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm", ".log"}


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


def output_dir(project: Path) -> Path:
    return project / OUTPUT_DIR_NAME


def backup_invalid(path: Path) -> Path:
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


def initialize(project: Path) -> list[str]:
    workspace = output_dir(project)
    prepare_workspace(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    created = []
    for name in (CONFIG_NAME, DATA_NAME):
        target = workspace / name
        if not target.exists():
            shutil.copyfile(ASSETS_DIR / ASSET_NAMES[name], target)
            created.append(f"{OUTPUT_DIR_NAME}/{name}")
    return created


def rebuild(project: Path) -> list[str]:
    workspace = output_dir(project)
    prepare_workspace(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    actions = []
    contracts = {
        CONFIG_NAME: {"host", "port", "ssl", "mailbox", "username_env", "password_env"},
        DATA_NAME: {"version", "mailboxes", "messages", "sync"},
    }
    for name, required in contracts.items():
        target = workspace / name
        if not target.exists():
            shutil.copyfile(ASSETS_DIR / ASSET_NAMES[name], target)
            actions.append(f"created {OUTPUT_DIR_NAME}/{name}")
            continue
        try:
            value = read_json(target)
            if not isinstance(value, dict) or not required.issubset(value):
                raise ValueError("missing required keys")
            actions.append(f"preserved valid {OUTPUT_DIR_NAME}/{name}")
        except (OSError, ValueError, json.JSONDecodeError):
            backup = backup_invalid(target)
            shutil.copyfile(ASSETS_DIR / ASSET_NAMES[name], target)
            actions.append(f"repaired {OUTPUT_DIR_NAME}/{name}; backup={backup.name}")
    return actions


def decoded_header(value: str | None) -> str:
    if not value:
        return ""
    pieces = []
    for part, charset in decode_header(value):
        pieces.append(part.decode(charset or "utf-8", errors="replace") if isinstance(part, bytes) else part)
    return "".join(pieces).strip()


def address_text(values: list[str]) -> str:
    rendered = []
    for name, address in getaddresses(values):
        clean_name = decoded_header(name)
        rendered.append(f"{clean_name} <{address}>" if clean_name and address else clean_name or address)
    return ", ".join(item for item in rendered if item)


def decode_part(part: Message) -> str:
    payload = part.get_payload(decode=True) or b""
    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")


def strip_html(value: str) -> str:
    without_code = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", value, flags=re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", without_code))).strip()


def message_body(message: Message) -> str:
    plain, rich = [], []
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() == "text/plain":
            plain.append(decode_part(part))
        elif part.get_content_type() == "text/html":
            rich.append(strip_html(decode_part(part)))
    selected = plain or rich
    return re.sub(r"\s+", " ", "\n".join(selected)).strip()


def safe_filename(name: str, index: int) -> str:
    candidate = Path(decoded_header(name)).name if name else f"attachment-{index}"
    candidate = re.sub(r"[^\w.() -]", "_", candidate, flags=re.UNICODE).strip(" .")
    return candidate[:180] or f"attachment-{index}"


def extract_docx(payload: bytes) -> str:
    from io import BytesIO
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
        return " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t")).strip()
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        return ""


def attachment_text(payload: bytes, filename: str, content_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return extract_docx(payload)
    if content_type.startswith("text/") or suffix in TEXT_SUFFIXES:
        text = payload.decode("utf-8", errors="replace")
        return strip_html(text) if suffix in {".html", ".htm"} or content_type == "text/html" else re.sub(r"\s+", " ", text).strip()
    return ""


def save_attachments(message: Message, workspace: Path, uidvalidity: int, uid: int, config: dict) -> tuple[list[dict], str]:
    records, extracted = [], []
    limit = int(config.get("max_attachment_bytes", 26214400))
    text_limit = int(config.get("max_extracted_text_chars", 40000))
    target_dir = workspace / ATTACHMENTS_DIR / str(config.get('_attachment_source', 'legacy')) / f"uid-{uidvalidity}-{uid}"
    used_names: set[str] = set()
    index = 0
    for part in message.walk():
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        if not filename and disposition != "attachment":
            continue
        index += 1
        payload = part.get_payload(decode=True) or b""
        filename = safe_filename(filename or "", index)
        stem, suffix = Path(filename).stem, Path(filename).suffix
        unique_name, counter = filename, 2
        while unique_name.casefold() in used_names:
            unique_name = f"{stem}-{counter}{suffix}"; counter += 1
        used_names.add(unique_name.casefold())
        record = {"filename": unique_name, "content_type": part.get_content_type(), "size": len(payload), "saved": False, "saved_path": "", "extracted_text_path": "", "skip_reason": ""}
        if len(payload) > limit:
            record["skip_reason"] = "attachment exceeds max_attachment_bytes"
            records.append(record); continue
        if config.get("save_attachments", True):
            target_dir.mkdir(parents=True, exist_ok=True)
            file_path = target_dir / unique_name
            file_path.write_bytes(payload)
            record["saved"] = True
            record["saved_path"] = file_path.relative_to(workspace).as_posix()
        text = attachment_text(payload, unique_name, part.get_content_type())[:text_limit]
        if text:
            target_dir.mkdir(parents=True, exist_ok=True)
            text_path = target_dir / f"{unique_name}.extracted.txt"
            text_path.write_text(text, encoding="utf-8")
            record["extracted_text_path"] = text_path.relative_to(workspace).as_posix()
            extracted.append(text)
        records.append(record)
    return records, "\n".join(extracted)[:text_limit]


def normalized_deadline(text: str) -> str:
    match = DEADLINE_RE.search(text)
    if not match:
        return ""
    return match.group(1).replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-").replace(".", "-")


def candidate_sentences(subject: str, body: str, attachment_content: str) -> list[str]:
    combined = "\n".join((body, attachment_content))[:80000]
    parts = [part.strip() for part in re.split(r"[\n。！？!?;；]+", combined) if part.strip()]
    matches = [part for part in parts if ACTION_RE.search(part) and len(part) >= 6]
    if not matches and ACTION_RE.search(subject):
        matches = [subject]
    unique = []
    for item in matches:
        if item not in unique:
            unique.append(item)
    return unique[:12]


def create_tasks(source_id: str, uidvalidity: int, uid: int, subject: str, assigner: str, body: str, attachment_content: str, attachments: list[dict]) -> list[dict]:
    combined = f"{subject}\n{body}\n{attachment_content}"
    tasks = []
    for index, content in enumerate(candidate_sentences(subject, body, attachment_content), start=1):
        tasks.append({
            "id": f"mail-{source_id}-{uidvalidity}-{uid}-task-{index}",
            "source_message_key": f"{source_id}:{uidvalidity}:{uid}",
            "source_uid": uid,
            "source_subject": subject,
            "task_content": content[:1000],
            "assigner": assigner,
            "deadline": normalized_deadline(content) or normalized_deadline(combined),
            "attachments": [item["saved_path"] for item in attachments if item.get("saved_path")],
            "is_new": True,
            "extraction": "deterministic"
        })
    return tasks


def uid_list(client: imaplib.IMAP4, criterion: str) -> list[int]:
    status, data = client.uid("search", None, criterion)
    if status != "OK":
        raise RuntimeError("IMAP UID search failed")
    return [int(value) for value in (data[0] or b"").split()]


def uidvalidity(client: imaplib.IMAP4) -> int:
    _status, values = client.response("UIDVALIDITY")
    if values and values[0]:
        return int(values[0])
    raise RuntimeError("Server did not provide UIDVALIDITY")


def credential_value(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    if sys.platform == 'win32':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
                return str(winreg.QueryValueEx(key, name)[0])
        except FileNotFoundError:
            pass
    return ''


def discover_sent(config: dict, username: str, password: str) -> str:
    client = imaplib.IMAP4_SSL(config['host'], int(config.get('port', 993)), timeout=30) if config.get('ssl', True) else imaplib.IMAP4(config['host'], int(config.get('port', 143)), timeout=30)
    try:
        client.login(username, password)
        status, rows = client.list()
        if status != 'OK':
            raise RuntimeError('Cannot list mailboxes to discover Sent')
        special, named = [], []
        for row in rows or []:
            if not isinstance(row, bytes):
                continue
            match = re.match(rb'\(([^)]*)\)\s+(?:"(?:[^"\\]|\\.)*"|NIL)\s+(.+)$', row)
            if not match:
                continue
            flags, wire = match.groups()
            name = wire.decode('ascii').strip('"')
            if b'\\noselect' in flags.lower():
                continue
            if b'\\sent' in flags.lower().split():
                special.append(name)
            elif re.sub(r'&([^-]*)-', lambda m: '&' if not m[1] else base64.b64decode(m[1].replace(',', '/') + '=' * (-len(m[1]) % 4)).decode('utf-16-be'), name).casefold() in {'sent', 'sent items', 'sent messages', '已发送', '已发送邮件'}:
                named.append(name)
        choices = special or named
        if len(choices) != 1:
            raise RuntimeError('Sent folder is missing or ambiguous; configure sent_mailbox using verified IMAP LIST output')
        return choices[0]
    finally:
        try:
            client.logout()
        except Exception:
            pass


def history_cutoff(months: int, today: date | None = None) -> str:
    if isinstance(months, bool) or not isinstance(months, int) or months < 1:
        raise ValueError('history months must be a positive integer')
    today = today or date.today()
    year, month0 = divmod(today.year * 12 + today.month - 1 - months, 12)
    return date(year, month0 + 1, min(today.day, calendar.monthrange(year, month0 + 1)[1])).isoformat()


def imap_since(iso_date: str) -> str:
    day = date.fromisoformat(iso_date)
    names = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
    return f'{day.day:02d}-{names[day.month - 1]}-{day.year}'


def sync(project: Path, prompt_credentials: bool = False, initial_latest: int = 0, history_months: int | None = None) -> str:
    initialize(project)
    path = output_dir(project) / CONFIG_NAME
    config = read_json(path)
    username = credential_value(config.get('username_env', 'MAIL_TASK_IMAP_USER'))
    password = credential_value(config.get('password_env', 'MAIL_TASK_IMAP_PASS'))
    if prompt_credentials:
        username = username or input('IMAP username: ').strip()
        password = password or getpass.getpass('IMAP password or client authorization code: ')
    if not username or not password:
        raise RuntimeError('Missing local IMAP credentials; use --prompt-credentials')
    folders = [(config.get('mailbox', 'INBOX'), initial_latest, 'inbound')]
    if config.get('include_sent', False):
        sent = config.get('sent_mailbox') or discover_sent(config, username, password)
        if sent == folders[0][0]:
            raise ValueError('Sent folder must differ from the inbox')
        if not config.get('sent_mailbox'):
            config['sent_mailbox'] = sent
            write_json(path, config)
        folders.append((sent, int(config.get('sent_initial_latest', 0)), 'sent'))
    reports = []
    for index, (mailbox, latest, direction) in enumerate(folders):
        current = dict(config, mailbox=mailbox, _direction=direction)
        reports.append(sync_one(project, initial_latest=latest, config_override=current, credentials=(username, password), reset_new=index == 0, history_months=history_months))
    state = read_json(output_dir(project) / DATA_NAME)
    state['sync']['mailbox_reports'] = reports
    state['sync']['new_message_count'] = sum(bool(m.get('is_new')) for m in state['messages'])
    state['sync']['new_task_count'] = sum(len(m.get('tasks', [])) for m in state['messages'] if m.get('is_new'))
    write_json(output_dir(project) / DATA_NAME, state)
    return '\n'.join(reports)


def sync_one(project: Path, prompt_credentials: bool = False, initial_latest: int = 0, config_override: dict | None = None, credentials: tuple | None = None, reset_new: bool = True, history_months: int | None = None) -> str:
    initialize(project)
    workspace = output_dir(project)
    config = config_override or read_json(workspace / CONFIG_NAME)
    state = read_json(workspace / DATA_NAME)
    host = str(config.get("host", ""))
    username, password = credentials or (credential_value(str(config.get('username_env', 'MAIL_TASK_IMAP_USER'))), credential_value(str(config.get('password_env', 'MAIL_TASK_IMAP_PASS'))))
    if prompt_credentials:
        if not username:
            username = input("IMAP username: ").strip()
        if not password:
            password = getpass.getpass("IMAP password or client authorization code: ")
    if not host or host == "imap.example.com" or not username or not password:
        raise RuntimeError("IMAP is not configured; set a real host and credential environment variables, or use --prompt-credentials")
    mailbox = str(config.get("mailbox", "INBOX"))
    source_id = hashlib.sha256(f"{host}\0{username}\0{mailbox}".encode()).hexdigest()[:16]
    config['_attachment_source'] = source_id
    client = imaplib.IMAP4_SSL(host, int(config.get("port", 993))) if config.get("ssl", True) else imaplib.IMAP4(host, int(config.get("port", 143)))
    try:
        if client.login(username, password)[0] != "OK":
            raise RuntimeError("IMAP login failed")
        if client.select('"' + mailbox.replace('\\', '\\\\').replace('"', '\\"') + '"', readonly=True)[0] != "OK":
            raise RuntimeError("Unable to open mailbox in read-only mode")
        current_validity = uidvalidity(client)
        # UID * returns at most the current highest UID, not the full history.
        highest_uid = max(uid_list(client, "UID *"), default=0)
        box = state.setdefault("mailboxes", {}).get(source_id)
        for message in state.setdefault("messages", []) if reset_new else []:
            message["is_new"] = False
            for task in message.get("tasks", []):
                task["is_new"] = False
        if box and int(box.get("uidvalidity", -1)) != current_validity:
            state["mailboxes"][source_id] = {"host": host, "mailbox": mailbox, "uidvalidity": current_validity, "last_uid": highest_uid}
            state["sync"] = {"status": "uidvalidity_reset", "updated_at": utc_now(), "message": "UIDVALIDITY changed; established a new safe baseline.", "new_message_count": 0, "new_task_count": 0}
            write_json(workspace / DATA_NAME, state)
            return state["sync"]["message"]
        if not box:
            import_existing = history_months is not None or initial_latest > 0 or bool(config.get("import_existing_on_first_sync", True))
            box = {"host": host, "mailbox": mailbox, "uidvalidity": current_validity, "last_uid": highest_uid}
            state["mailboxes"][source_id] = box
            if import_existing:
                box['history_since'] = history_cutoff(history_months or config.get('initial_history_months', 1))
                if initial_latest > 0:
                    box['history_limit'] = initial_latest
            if not import_existing:
                state["sync"] = {"status": "baseline_ready", "updated_at": utc_now(), "message": "Established the current UID baseline; future runs read only new mail.", "new_message_count": 0, "new_task_count": 0}
                write_json(workspace / DATA_NAME, state)
                return state["sync"]["message"]
        if history_months is not None:
            box['history_since'] = history_cutoff(history_months)
        cursor = int(box['last_uid'])
        new_uids = [uid for uid in uid_list(client, f'UID {cursor + 1}:*') if uid > cursor] if highest_uid > cursor else []
        if box.get('history_since'):
            historical = uid_list(client, 'SINCE ' + imap_since(box['history_since']))
            if box.get('history_limit'):
                historical = historical[-int(box['history_limit']):]
            new_uids = sorted(set(new_uids + historical))
        known = {item.get("message_key") for item in state["messages"]}
        new_messages, new_tasks = 0, 0
        advanced_uid = int(box["last_uid"])
        for uid in new_uids:
            key = f"{source_id}:{current_validity}:{uid}"
            if key in known:
                advanced_uid = max(advanced_uid, uid)
                continue
            status, data = client.uid("fetch", str(uid), "(BODY.PEEK[])")
            if status != "OK" or not data or not isinstance(data[0], tuple):
                break
            parsed = email.message_from_bytes(data[0][1])
            subject = decoded_header(parsed.get("Subject")) or "(无主题)"
            sender = address_text(parsed.get_all("From", [])) or "未知派发人"
            recipients = address_text(parsed.get_all("To", []))
            body = message_body(parsed)
            attachments, attachment_content = save_attachments(parsed, workspace, current_validity, uid, config)
            tasks = [] if config.get('_direction') == 'sent' else create_tasks(source_id, current_validity, uid, subject, sender, body, attachment_content, attachments)
            received = parsedate_to_datetime(parsed.get("Date")) if parsed.get("Date") else datetime.now(timezone.utc)
            if received.tzinfo is None:
                received = received.replace(tzinfo=timezone.utc)
            state["messages"].insert(0, {"message_key": key, "source_id": source_id, "uidvalidity": current_validity, "uid": uid, "is_new": True, "sender": sender, "recipients": recipients, "subject": subject, "received_at": received.isoformat(), "body_text": body[:80000], "attachments": attachments, "tasks": tasks, "recorded_at": utc_now()})
            state['messages'][0].update(mailbox=mailbox, direction=config.get('_direction', 'inbound'), message_id=str(parsed.get('Message-ID', '')), in_reply_to=str(parsed.get('In-Reply-To', '')), references=str(parsed.get('References', '')), review_required=True)
            known.add(key); new_messages += 1; new_tasks += len(tasks); advanced_uid = max(advanced_uid, uid)
        else:
            box.pop('history_since', None)
            box.pop('history_limit', None)
        box["last_uid"] = advanced_uid
        state["sync"] = {"status": "synced", "updated_at": utc_now(), "message": f"Scanned {len(new_uids)} new UID(s); recorded {new_messages} message(s) and extracted {new_tasks} task(s).", "new_message_count": new_messages, "new_task_count": new_tasks}
        write_json(workspace / DATA_NAME, state)
        return state["sync"]["message"]
    finally:
        try:
            client.logout()
        except Exception:
            pass


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="Read only new IMAP messages and extract task data.")
    parser.add_argument("--project-dir", default=".")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument('--summary', action='store_true', help='Print cached recent mail and candidate tasks as text; no board required')
    parser.add_argument('--summary-limit', type=int, default=10)
    parser.add_argument("--prompt-credentials", action="store_true", help="prompt locally for missing IMAP credentials without storing them")
    parser.add_argument("--initial-latest", type=int, default=0, metavar="N", help="on the first sync only, import the latest N existing messages")
    parser.add_argument('--history-months', type=int, help='Explicitly read/backfill this many calendar months; first sync defaults to one month')
    args = parser.parse_args()
    if args.initial_latest < 0:
        parser.error("--initial-latest must be zero or greater")
    if args.history_months is not None and args.history_months < 1:
        parser.error('--history-months must be a positive integer')
    if not args.init and not args.rebuild and not args.sync and not args.summary:
        parser.error("choose --init, --rebuild, or --sync")
    project = Path(args.project_dir).expanduser().resolve()
    if args.init:
        created = initialize(project)
        print("Created: " + (", ".join(created) if created else "nothing"))
    if args.rebuild:
        print("\n".join(rebuild(project)))
    if args.sync:
        print(sync(project, prompt_credentials=args.prompt_credentials, initial_latest=args.initial_latest, history_months=args.history_months))
    if args.summary:
        initialize(project)
        messages = read_json(output_dir(project) / DATA_NAME).get('messages', [])
        limit = max(0, args.summary_limit)
        recent = sorted(messages, key=lambda m: m.get('received_at', ''), reverse=True)[:limit]
        print(f'缓存邮件文本摘要：显示 {len(recent)} / {len(messages)} 封（不是未读数量）')
        for message in recent:
            print(f'\n主题：{message.get("subject", "无主题")}\n发件人：{message.get("sender", "")}\n时间：{message.get("received_at", "")}\n依据：{message.get("message_key", "")}')
            print('正文摘录：' + str(message.get('body_text', ''))[:600])
            for task in message.get('tasks', []):
                print(f'- 候选任务：{task.get("task_content", "")}；派发人：{task.get("assigner", "未知")}；截止：{task.get("deadline") or "未提供"}')
            if not message.get('tasks'):
                print('尚无已提取任务，需 Agent 结合正文和附件判断。')
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as error:
        if "ERR.LOGIN.REQCODE" in str(error).upper():
            print(
                "Error: ERR.LOGIN.REQCODE — the server requires a client authorization code, "
                "not the web-login password. Generate a code in the official mailbox's "
                "IMAP/client authorization settings (enterprise menus may differ), then enter it "
                "at the local hidden credential prompt. See references/setup-and-credentials.md. "
                "Do not paste the code into chat or at a bare PowerShell prompt.",
                file=sys.stderr,
            )
        else:
            print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
