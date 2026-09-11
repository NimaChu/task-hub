#!/usr/bin/env python3
"""Import RFC 822 .eml files into the shared mail-reader database."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

from read_mail import (
    CONFIG_NAME,
    DATA_NAME,
    address_text,
    decoded_header,
    history_cutoff,
    initialize,
    message_body,
    output_dir,
    read_json,
    save_attachments,
    utc_now,
    write_json,
)


def message_datetime(message, fallback: Path) -> tuple[datetime, str]:
    """Return an aware UTC timestamp and an auditable date basis."""
    try:
        value = parsedate_to_datetime(message.get("Date", ""))
    except (TypeError, ValueError, OverflowError):
        value = None
    if value is None:
        return datetime.fromtimestamp(fallback.stat().st_mtime, timezone.utc), "file_mtime"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
        basis = "date_header_assumed_utc"
    else:
        basis = "date_header"
    return value.astimezone(timezone.utc), basis


def source_identifier(folder: Path, identity: str | None = None) -> str:
    value = identity or str(folder.resolve())
    return hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()[:16]


def import_folder(
    project: Path,
    folder: Path,
    history_months: int | None = None,
    direction: str = "inbound",
    max_message_bytes: int = 104_857_600,
    source_identity: str | None = None,
    source_type: str = "eml_folder",
    reset_new_flags: bool = True,
) -> dict:
    if not folder.is_dir():
        raise ValueError(f"EML folder does not exist: {folder}")
    initialize(project)
    workspace = output_dir(project)
    database_path = workspace / DATA_NAME
    config = read_json(workspace / CONFIG_NAME)
    state = read_json(database_path)
    source_id = source_identifier(folder, source_identity)
    sources = state.setdefault("eml_sources", {})
    source = sources.setdefault(source_id, {"processed_sha256": {}, "baseline_sha256": []})
    processed = source.setdefault("processed_sha256", {})
    baseline = set(source.setdefault("baseline_sha256", []))
    cutoff = history_cutoff(history_months or int(config.get("initial_history_months", 1)))
    known = {item.get("message_key"): item for item in state.get("messages", [])}
    known_content = {
        item.get("content_sha256") for item in state.get("messages", []) if item.get("content_sha256")
    }
    if reset_new_flags:
        for item in state.get("messages", []):
            item["is_new"] = False
            for task in item.get("tasks", []):
                task["is_new"] = False

    candidates = []
    errors = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix.casefold() != ".eml":
            continue
        relative = path.relative_to(folder).as_posix()
        try:
            size = path.stat().st_size
            if size > max_message_bytes:
                raise ValueError(f"message exceeds max-message-bytes ({size})")
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            message = BytesParser(policy=policy.default).parsebytes(raw)
            received, date_basis = message_datetime(message, path)
            candidates.append((received, relative, digest, raw, message, date_basis))
        except (OSError, ValueError, TypeError) as error:
            errors.append({"file": relative, "error": str(error)[:500]})

    new_count = 0
    unchanged_count = 0
    baseline_count = 0
    imported_hashes = set(processed)
    for received, relative, digest, raw, message, date_basis in sorted(candidates):
        if digest in imported_hashes or digest in known_content:
            processed.setdefault(digest, {"source_file": relative, "recorded_at": utc_now()})
            imported_hashes.add(digest)
            unchanged_count += 1
            continue
        if received.astimezone().date().isoformat() < cutoff:
            baseline.add(digest)
            baseline_count += 1
            continue
        baseline.discard(digest)
        token = int(digest[:15], 16)
        attachment_config = dict(config)
        attachment_config["_attachment_source"] = f"eml-{source_id}"
        attachments, attachment_text = save_attachments(
            message, workspace, 0, token, attachment_config
        )
        message_dir = workspace / "attachments" / f"eml-{source_id}" / f"uid-0-{token}"
        message_dir.mkdir(parents=True, exist_ok=True)
        eml_path = message_dir / "original.eml"
        eml_path.write_bytes(raw)
        attachments.append({
            "filename": "original.eml",
            "content_type": "message/rfc822",
            "size": len(raw),
            "saved": True,
            "saved_path": eml_path.relative_to(workspace).as_posix(),
            "extracted_text_path": "",
            "skip_reason": "",
            "role": "source_email",
        })
        key = f"eml:{source_id}:{digest}"
        record = {
            "message_key": key,
            "source_id": source_id,
            "source_type": source_type,
            "uid": None,
            "uidvalidity": None,
            "local_id": digest[:20],
            "is_new": key not in known,
            "sender": address_text(message.get_all("From", [])),
            "recipients": address_text(message.get_all("To", []) + message.get_all("Cc", [])),
            "subject": decoded_header(message.get("Subject")),
            "received_at": received.isoformat(),
            "date_basis": date_basis,
            "body_text": message_body(message)[:80000],
            "attachment_text": attachment_text,
            "attachments": attachments,
            "eml_path": eml_path.relative_to(workspace).as_posix(),
            "source_file": relative,
            "content_sha256": digest,
            "message_id": str(message.get("Message-ID", "")),
            "in_reply_to": str(message.get("In-Reply-To", "")),
            "references": str(message.get("References", "")),
            "direction": direction,
            "tasks": [],
            "review_required": True,
            "recorded_at": utc_now(),
        }
        if key in known:
            record["tasks"] = known[key].get("tasks", [])
            state["messages"].remove(known[key])
        else:
            new_count += 1
        state["messages"].insert(0, record)
        processed[digest] = {"source_file": relative, "recorded_at": record["recorded_at"]}
        imported_hashes.add(digest)

    source.update({
        "folder_fingerprint": source_id,
        "direction": direction,
        "processed_sha256": processed,
        "baseline_sha256": sorted(baseline),
        "last_scan_at": utc_now(),
    })
    state["sync"] = {
        "status": "eml_folder_synced",
        "updated_at": utc_now(),
        "message": (
            f"Scanned {len(candidates)} EML files; new={new_count}, unchanged={unchanged_count}, "
            f"older_baseline={baseline_count}, errors={len(errors)}; cutoff={cutoff}. Agent review required."
        ),
        "new_message_count": new_count,
        "new_task_count": 0,
        "error_count": len(errors),
    }
    write_json(database_path, state)
    error_path = workspace / "logs" / "eml-import-errors.json"
    write_json(error_path, {"updated_at": utc_now(), "source_id": source_id, "errors": errors})
    return state["sync"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eml-dir", required=True, help="Folder recursively containing .eml files")
    parser.add_argument("--project-dir", default=".")
    parser.add_argument("--history-months", type=int, help="Import this many months; defaults to one")
    parser.add_argument("--direction", choices=("inbound", "sent"), default="inbound")
    parser.add_argument("--max-message-bytes", type=int, default=104_857_600)
    args = parser.parse_args()
    if args.history_months is not None and args.history_months < 1:
        parser.error("history-months must be positive")
    if args.max_message_bytes < 1:
        parser.error("max-message-bytes must be positive")
    result = import_folder(
        Path(args.project_dir).expanduser().resolve(),
        Path(args.eml_dir).expanduser().resolve(),
        args.history_months,
        args.direction,
        args.max_message_bytes,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
