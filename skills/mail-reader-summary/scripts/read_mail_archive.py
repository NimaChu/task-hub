#!/usr/bin/env python3
"""Import a Thunderbird mbox or Apple Mail emlx archive without credentials."""
from __future__ import annotations

import argparse
import json
import mailbox
import os
import sys
import tempfile
from pathlib import Path

from email import policy
from email.parser import BytesParser

from read_eml_folder import import_folder, message_datetime
from read_mail import history_cutoff


def discover() -> dict:
    thunderbird_roots = []
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        thunderbird_roots.append(Path(os.environ["APPDATA"]) / "Thunderbird" / "Profiles")
    elif sys.platform == "darwin":
        thunderbird_roots.append(Path.home() / "Library" / "Thunderbird" / "Profiles")
    else:
        thunderbird_roots.append(Path.home() / ".thunderbird")
    profiles = []
    for root in thunderbird_roots:
        if root.is_dir():
            profiles.extend(str(path.resolve()) for path in root.iterdir() if path.is_dir())
    apple = []
    apple_root = Path.home() / "Library" / "Mail"
    if sys.platform == "darwin" and apple_root.is_dir():
        apple = [str(path.resolve()) for path in apple_root.iterdir() if path.is_dir() and path.name.startswith("V")]
    return {"thunderbird_profiles": sorted(profiles), "apple_mail_roots": sorted(apple, reverse=True)}


def eligible(raw: bytes, source: Path, cutoff: str, max_message_bytes: int) -> bool:
    if len(raw) > max_message_bytes:
        return False
    message = BytesParser(policy=policy.default).parsebytes(raw)
    received, _basis = message_datetime(message, source)
    return received.astimezone().date().isoformat() >= cutoff


def export_mbox(source: Path, destination: Path, cutoff: str, max_message_bytes: int) -> int:
    count = 0
    box = mailbox.mbox(source, create=False)
    try:
        for message in box:
            raw = message.as_bytes()
            if not eligible(raw, source, cutoff, max_message_bytes):
                continue
            count += 1
            target = destination / f"message-{count:08d}.eml"
            target.write_bytes(raw)
            os.utime(target, (source.stat().st_atime, source.stat().st_mtime))
    finally:
        box.close()
    return count


def export_emlx(source: Path, destination: Path, cutoff: str, max_message_bytes: int) -> int:
    count = 0
    for path in sorted(source.rglob("*.emlx")):
        content = path.read_bytes()
        newline = content.find(b"\n")
        if newline < 1:
            continue
        try:
            length = int(content[:newline].strip())
        except ValueError:
            continue
        start = newline + 1
        raw = content[start : start + length]
        if not raw or not eligible(raw, path, cutoff, max_message_bytes):
            continue
        count += 1
        target = destination / f"message-{count:08d}.eml"
        target.write_bytes(raw)
        os.utime(target, (path.stat().st_atime, path.stat().st_mtime))
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("thunderbird-mbox", "apple-emlx"))
    parser.add_argument("--path", help="mbox file or directory containing .emlx files")
    parser.add_argument("--discover", action="store_true", help="list supported local client roots without reading mail")
    parser.add_argument("--project-dir", default=".")
    parser.add_argument("--history-months", type=int, help="Import this many months; defaults to one")
    parser.add_argument("--direction", choices=("inbound", "sent"), default="inbound")
    parser.add_argument("--max-message-bytes", type=int, default=104_857_600)
    args = parser.parse_args()
    if args.discover:
        print(json.dumps(discover(), ensure_ascii=False, indent=2))
        return 0
    if not args.format or not args.path:
        parser.error("--format and --path are required unless --discover is used")
    if args.history_months is not None and args.history_months < 1:
        parser.error("history-months must be positive")
    if args.max_message_bytes < 1:
        parser.error("max-message-bytes must be positive")
    source = Path(args.path).expanduser().resolve()
    if args.format == "thunderbird-mbox" and not source.is_file():
        parser.error("thunderbird-mbox requires an existing mbox file")
    if args.format == "apple-emlx" and not source.is_dir():
        parser.error("apple-emlx requires an existing directory")
    with tempfile.TemporaryDirectory(prefix="mail-archive-") as temporary:
        staging = Path(temporary)
        cutoff = history_cutoff(args.history_months or 1)
        count = (
            export_mbox(source, staging, cutoff, args.max_message_bytes)
            if args.format == "thunderbird-mbox"
            else export_emlx(source, staging, cutoff, args.max_message_bytes)
        )
        if not count:
            raise ValueError(f"No readable messages found on or after {cutoff}")
        result = import_folder(
            Path(args.project_dir).expanduser().resolve(),
            staging,
            args.history_months,
            args.direction,
            args.max_message_bytes,
            source_identity=f"{args.format}:{source}",
            source_type=args.format,
        )
    print(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
