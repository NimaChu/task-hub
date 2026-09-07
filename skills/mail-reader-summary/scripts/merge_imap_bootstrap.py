#!/usr/bin/env python3
"""Merge a credentialed IMAP bootstrap into an existing Foxmail-local history."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

OUTPUT_DIR_NAME = "task-workspace"
from workspace_layout import READER_DATA_NAME as DATA_NAME, prepare_workspace
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+", re.I)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def email_address(value: str) -> str:
    found = EMAIL_RE.search(str(value or ""))
    return (found.group(0) if found else str(value or "")).casefold()


def timestamp(value: str) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def attachment_name(value: dict) -> str:
    return str(value.get("filename") or value.get("name") or value.get("indexed_name") or "")


def safe_name(value: str) -> str:
    cleaned = "".join("_" if char in '<>:"/\\|?*' else char for char in value).strip(" .")
    return cleaned or "attachment.bin"


def match_local(remote: dict, candidates: list[dict], used: set[int]) -> dict | None:
    subject = str(remote.get("subject", "")).strip().casefold()
    sender = email_address(remote.get("sender", ""))
    scored = []
    for local in candidates:
        local_id = local.get("local_id")
        if not isinstance(local_id, int) or local_id in used:
            continue
        if str(local.get("subject", "")).strip().casefold() != subject:
            continue
        if email_address(local.get("sender", "")) != sender:
            continue
        delta = abs(timestamp(local.get("received_at", "")) - timestamp(remote.get("received_at", "")))
        if delta <= 2:
            scored.append((delta, -local_id, local))
    if not scored:
        return None
    return sorted(scored, key=lambda item: (item[0], item[1]))[0][2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge staged IMAP attachments and UID cursor into local Foxmail history.")
    parser.add_argument("--project-dir", default=".")
    parser.add_argument("--staging-project", required=True)
    args = parser.parse_args()
    project = Path(args.project_dir).expanduser().resolve()
    main_workspace = project / OUTPUT_DIR_NAME
    staging_project = Path(args.staging_project).expanduser().resolve()
    staging_workspace = staging_project / OUTPUT_DIR_NAME
    prepare_workspace(main_workspace)
    prepare_workspace(staging_workspace)
    main_path = main_workspace / DATA_NAME
    staging_path = staging_workspace / DATA_NAME
    main = read_json(main_path)
    staged = read_json(staging_path)
    local_messages = [message for message in main.get("messages", []) if message.get("local_id") is not None]
    used: set[int] = set()
    matched = copied = verified = 0
    for remote in staged.get("messages", []):
        local = match_local(remote, local_messages, used)
        if local is None:
            continue
        used.add(local["local_id"])
        matched += 1
        local["imap_provenance"] = {
            "message_key": remote.get("message_key", ""),
            "source_id": remote.get("source_id", ""),
            "uidvalidity": remote.get("uidvalidity"),
            "uid": remote.get("uid"),
        }
        local_attachments = local.get("attachments", [])
        remote_attachments = [item for item in remote.get("attachments", []) if not str(item.get("content_type", "")).startswith("image/")]
        remaining = list(remote_attachments)
        pairs: list[tuple[dict, dict]] = []
        for target in local_attachments:
            target_name = attachment_name(target).casefold()
            exact = next((item for item in remaining if attachment_name(item).casefold() == target_name), None)
            if exact is not None:
                pairs.append((target, exact))
                remaining.remove(exact)
        unmatched_targets = [item for item in local_attachments if all(item is not pair[0] for pair in pairs)]
        if len(unmatched_targets) == len(remaining):
            pairs.extend(zip(unmatched_targets, remaining))
        for target, source_meta in pairs:
            source_relative = source_meta.get("saved_path")
            if not source_relative:
                continue
            source_file = staging_workspace / source_relative
            if not source_file.is_file():
                continue
            file_hash = sha256(source_file)
            existing_relative = target.get("saved_path")
            existing_file = main_workspace / existing_relative if existing_relative else None
            if existing_file and existing_file.is_file() and sha256(existing_file) == file_hash:
                destination = existing_file
                verified += 1
            else:
                destination_dir = main_workspace / "attachments" / f"uid-{remote.get('uidvalidity')}-{remote.get('uid')}"
                destination_dir.mkdir(parents=True, exist_ok=True)
                destination = destination_dir / safe_name(attachment_name(target) or attachment_name(source_meta))
                shutil.copy2(source_file, destination)
                copied += 1
            target.update({
                "binary_status": "downloaded_and_verified_via_imap",
                "saved": True,
                "saved_path": destination.relative_to(main_workspace).as_posix(),
                "saved_size": destination.stat().st_size,
                "sha256": file_hash,
                "content_type": source_meta.get("content_type", ""),
                "imap_uid": remote.get("uid"),
                "imap_uidvalidity": remote.get("uidvalidity"),
            })
    main["mailboxes"] = staged.get("mailboxes", {})
    main["imap_bootstrap"] = {
        "matched_local_messages": matched,
        "staged_messages": len(staged.get("messages", [])),
        "attachments_copied": copied,
        "attachments_verified_existing": verified,
        "note": "Staged deterministic task candidates were intentionally not imported.",
    }
    write_json(main_path, main)
    print(f"Merged IMAP bootstrap: matched={matched}, copied={copied}, verified_existing={verified}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
