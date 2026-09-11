#!/usr/bin/env python3
"""Export cached mail evidence as text, Markdown, CSV, or compact JSON."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from read_mail import DATA_NAME, initialize, output_dir, read_json


FIELDS = ("received_at", "direction", "sender", "subject", "message_key", "task_titles", "body_excerpt")


def rows(project: Path, limit: int, only_new: bool) -> list[dict]:
    initialize(project)
    messages = read_json(output_dir(project) / DATA_NAME).get("messages", [])
    if only_new:
        messages = [item for item in messages if item.get("is_new")]
    messages = sorted(messages, key=lambda item: item.get("received_at", ""), reverse=True)
    if limit:
        messages = messages[:limit]
    return [{
        "received_at": item.get("received_at", ""),
        "direction": item.get("direction", "inbound"),
        "sender": item.get("sender", ""),
        "subject": item.get("subject", ""),
        "message_key": item.get("message_key", ""),
        "task_titles": "；".join(task.get("title") or task.get("task_content", "") for task in item.get("tasks", [])),
        "body_excerpt": str(item.get("body_text", ""))[:600],
    } for item in messages]


def render_text(items: list[dict]) -> str:
    blocks = []
    for item in items:
        blocks.append(
            f"{item['received_at']} | {item['subject']}\n"
            f"发件人：{item['sender']}\n任务：{item['task_titles'] or '待 Agent 复核'}\n"
            f"正文摘录：{item['body_excerpt']}\n依据：{item['message_key']}"
        )
    return "\n\n".join(blocks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", default=".")
    parser.add_argument("--format", choices=("text", "markdown", "csv", "json"), default="text")
    parser.add_argument("--limit", type=int, default=10, help="0 means all cached messages")
    parser.add_argument("--only-new", action="store_true")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("limit must be nonnegative")
    project = Path(args.project_dir).expanduser().resolve()
    items = rows(project, args.limit, args.only_new)
    if args.format == "text":
        print(render_text(items))
        return 0
    export_dir = output_dir(project) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    suffix = "md" if args.format == "markdown" else args.format
    target = export_dir / f"mail-summary.{suffix}"
    if args.format == "markdown":
        target.write_text("# 邮件摘要\n\n" + render_text(items), encoding="utf-8")
    elif args.format == "json":
        target.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(items)
    print(target)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
