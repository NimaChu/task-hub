"""Shared runtime layout contract; identical copy in each independently installable skill."""
from pathlib import Path

CONFIG_NAME = "config/mail-reader-config.json"
READER_DATA_NAME = "data/mail-reader-data.json"
TASK_DATA_NAME = "data/task-data.json"

def prepare_workspace(workspace: Path) -> None:
    workspace = workspace.resolve()
    legacy = workspace.parent / 'mail-task-workspace'
    if not workspace.exists() and legacy.is_dir():
        legacy.resolve().relative_to(workspace.parent)
        legacy.replace(workspace)
    elif legacy.is_dir() and workspace.exists():
        raise ValueError('Both legacy and new workspaces exist; resolve before continuing')
    workspace.mkdir(parents=True, exist_ok=True)
    for name in ("config", "data", "attachments", "audit", "logs", "archive"):
        (workspace / name).mkdir(exist_ok=True)
    moves = {
        'data/mail-task-data.json': TASK_DATA_NAME,
        'mail-task-data.json': TASK_DATA_NAME,
        'mail-task-board.html': 'task-board.html',
        ".mail-reader-config.json": CONFIG_NAME,
        "mail-reader-data.json": READER_DATA_NAME,
        "task-data.json": TASK_DATA_NAME,
        "setup-log.md": "logs/setup-log.md",
        "audit/connection-result.json": "logs/connection-result.json",
        "audit/reconnect-result.json": "logs/reconnect-result.json",
        "audit/eml-handler.log": "logs/eml-handler.log",
    }
    for old, new in moves.items():
        source, target = workspace / old, workspace / new
        # Resolve both targets before any migration; refuse links out of this workspace.
        source.resolve().relative_to(workspace)
        target.resolve().relative_to(workspace)
        if source.is_file():
            if target.exists():
                if source.read_bytes() != target.read_bytes():
                    raise ValueError(f"Conflicting legacy/current files: {source} and {target}")
                # Preserve identical legacy copies as a migration backup.
                target = workspace / "archive" / (source.name + ".legacy")
                if target.exists():
                    continue
            source.replace(target)

def archive_dir(path: Path) -> Path:
    workspace = next((p for p in path.parents if p.name == "task-workspace"), path.parent)
    return workspace / "archive" / "backups"
