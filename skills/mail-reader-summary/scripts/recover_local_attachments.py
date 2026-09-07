#!/usr/bin/env python3
"""Recover already-exported Foxmail attachments by exact name and size."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

OUTPUT_DIR_NAME = "task-workspace"
from workspace_layout import READER_DATA_NAME as DATA_NAME, prepare_workspace


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def safe_name(name: str) -> str:
    cleaned = "".join("_" if char in '<>:"/\\|?*' else char for char in name).strip(" .")
    return cleaned or "attachment.bin"


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy matching local attachment exports into the shared workspace.")
    parser.add_argument("--project-dir", default=".")
    parser.add_argument("--search-root", action="append", required=True)
    args = parser.parse_args()
    project = Path(args.project_dir).expanduser().resolve()
    workspace = project / OUTPUT_DIR_NAME
    prepare_workspace(workspace)
    path = workspace / DATA_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    wanted: dict[str, list[tuple[dict, dict]]] = {}
    for message in data.get("messages", []):
        for attachment in message.get("attachments", []):
            if attachment.get("saved_path"):
                continue
            name = attachment.get("name") or attachment.get("indexed_name")
            if name:
                wanted.setdefault(name.casefold(), []).append((message, attachment))
    candidates: dict[str, list[Path]] = {}
    for raw_root in args.search_root:
        root = Path(raw_root).expanduser().resolve()
        if not root.is_dir():
            continue
        for candidate in root.rglob("*"):
            if candidate.is_file() and candidate.name.casefold() in wanted:
                candidates.setdefault(candidate.name.casefold(), []).append(candidate)
    recovered = 0
    for name_key, records in wanted.items():
        for message, attachment in records:
            expected = attachment.get("encoded_size")
            matches = [p for p in candidates.get(name_key, []) if expected is None or abs(p.stat().st_size - int(expected)) <= 8]
            if len(matches) != 1:
                continue
            source = matches[0]
            folder = workspace / "attachments" / f"mail-{message.get('local_id', 'unknown')}"
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / safe_name(source.name)
            shutil.copy2(source, target)
            attachment.update({
                "binary_status": "recovered_from_local_export",
                "saved_path": target.relative_to(workspace).as_posix(),
                "saved_size": target.stat().st_size,
                "sha256": digest(target),
                "recovery_source": str(source),
                "recovery_confidence": "high_exact_name_unique_size_match",
            })
            recovered += 1
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(f"Recovered attachments: {recovered}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
