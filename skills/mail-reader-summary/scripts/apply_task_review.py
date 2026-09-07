#!/usr/bin/env python3
"""Apply an agent-reviewed task manifest to the cached-mail database."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

OUTPUT_DIR_NAME = "task-workspace"
from workspace_layout import READER_DATA_NAME as DATA_NAME, prepare_workspace


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def clean_excerpt(value: str, limit: int = 900) -> str:
    value = "\n".join(line.rstrip() for line in str(value or "").splitlines()).strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply agent-reviewed mail tasks with audit provenance.")
    parser.add_argument("--project-dir", default=".")
    parser.add_argument("--review", required=True)
    args = parser.parse_args()
    project = Path(args.project_dir).expanduser().resolve()
    prepare_workspace(project / OUTPUT_DIR_NAME)
    database_path = project / OUTPUT_DIR_NAME / DATA_NAME
    review_path = Path(args.review).expanduser()
    if not review_path.is_absolute():
        review_path = project / review_path
    database = read_json(database_path)
    review = read_json(review_path)
    messages = database.get("messages", [])
    by_local_id = {message.get("local_id"): message for message in messages}
    by_key = {message.get("message_key"): message for message in messages}
    reviewed_keys = set(review.get("reviewed_message_keys", []))
    if reviewed_keys - by_key.keys():
        raise ValueError("reviewed_message_keys contains unknown messages")
    known_tasks = {item.get("id") for item in review.get("tasks", [])}
    if not review.get("replace_all"):
        known_tasks.update(task.get("id") for message in messages for task in message.get("tasks", []))
    for item in review.get("tasks", []):
        parent = item.get("parent_task_id")
        if parent and (parent == item.get("id") or parent not in known_tasks):
            raise ValueError(f"invalid parent_task_id for {item.get('id')}: {parent}")
    if review.get("replace_all"):
        for message in messages:
            message["tasks"] = []
    else:
        # Remove only draft candidates from messages explicitly reviewed this run.
        # Existing reviewed tasks keep their stable IDs until explicitly updated.
        for key in reviewed_keys:
            message = by_key[key]
            message["tasks"] = [t for t in message.get("tasks", []) if t.get("extraction") != "deterministic"]
    applied = 0
    for item in review.get("tasks", []):
        title = str(item.get("title", "")).strip()
        if not title:
            raise ValueError(f"title is required for reviewed task: {item.get('id')}")
        assigner = str(item.get("assigner", "")).strip()
        if "@" in assigner:
            raise ValueError(f"assigner must be a human-readable name, not an email address: {item.get('id')}")
        primary_id = item.get("primary_local_id")
        primary = by_key.get(item.get("primary_message_key")) if item.get("primary_message_key") else by_local_id.get(primary_id)
        if primary is None:
            raise ValueError(f"unknown primary_local_id: {primary_id}")
        related_ids = item.get("related_message_keys") or item.get("related_local_ids") or [primary.get("message_key")]
        related = []
        for local_id in related_ids:
            message = by_key.get(local_id) or by_local_id.get(local_id)
            if message is None:
                raise ValueError(f"unknown related_local_id: {local_id}")
            sender = str(message.get("sender", ""))
            related.append({
                "local_id": message.get("local_id"),
                "message_key": message.get("message_key", ""),
                "subject": message.get("subject", ""),
                "sender": sender,
                "received_at": message.get("received_at", ""),
                "role": item.get("message_roles", {}).get(message.get("message_key", ""), "request"),
                "excerpt": clean_excerpt(message.get("body_text", "")),
            })
        attachment_ids = item.get("attachment_message_keys") or item.get("attachment_local_ids") or [primary.get("message_key")]
        attachments = []
        seen = set()
        for local_id in attachment_ids:
            message = by_key.get(local_id) or by_local_id.get(local_id)
            if message is None:
                raise ValueError(f"unknown attachment_local_id: {local_id}")
            for attachment in message.get("attachments", []):
                key = (attachment.get("saved_path"), attachment.get("filename") or attachment.get("name"), attachment.get("foxmail_container"), attachment.get("container_position"))
                if key not in seen:
                    attachments.append(dict(attachment))
                    seen.add(key)
        task = {
            "id": item["id"],
            "source_message_key": primary.get("message_key", ""),
            "source_uid": primary.get("uid"),
            "source_subject": primary.get("subject", ""),
            "title": title,
            "task_content": item["task_content"],
            "assigner": assigner,
            "deadline": item.get("deadline", ""),
            "deadline_original": item.get("deadline_original", ""),
            "deadline_basis": item.get("deadline_basis", ""),
            "priority": item.get("priority", "medium"),
            "priority_reason": item.get("priority_reason", ""),
            "suggested_status": item.get("suggested_status", "pending"),
            "communication_status": item.get("communication_status", "not_replied"),
            "completion_state": item.get("completion_state", "not_completed"),
            "request_evidence": item.get("request_evidence", ""),
            "response_evidence": item.get("response_evidence", ""),
            "completion_evidence": item.get("completion_evidence", "未发现可验证的完成证据"),
            "review_reasoning": item.get("review_reasoning", ""),
            "related_messages": related,
            "parent_task_id": item.get("parent_task_id", ""),
            "relationship_reason": item.get("relationship_reason", ""),
            "attachments": attachments,
            "is_new": primary.get("is_new", False),
            "extraction": "agent_reviewed_thread",
            "reviewed_at": review.get("reviewed_at") or utc_now(),
        }
        if task["suggested_status"] == "review":
            task["suggested_status"] = "completed"
        if task["completion_state"] in {"delivered", "completed"} and task["completion_evidence"]:
            task["suggested_status"] = "completed"
        # A repeat review updates a stable task, including when new mail provides evidence.
        for message in messages:
            message["tasks"] = [existing for existing in message.get("tasks", []) if existing.get("id") != task["id"]]
        primary.setdefault("tasks", []).append(task)
        applied += 1
    for key in reviewed_keys:
        by_key[key]["review_required"] = False
    database["task_review"] = {
        "reviewed_at": review.get("reviewed_at") or utc_now(),
        "reviewer": review.get("reviewer", "agent"),
        "manifest": str(review_path.relative_to(project)).replace("\\", "/"),
        "task_count": applied,
    }
    write_json(database_path, database)
    print(f"Applied reviewed tasks: {applied}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
