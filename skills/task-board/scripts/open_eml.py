#!/usr/bin/env python3
"""Open a local EML received from the task-board protocol in Foxmail."""
from __future__ import annotations

import argparse
import ctypes
import os
import sys
import time
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _message_subject(eml: Path) -> str:
    try:
        with eml.open("rb") as handle:
            message = BytesParser().parse(handle, headersonly=True)
        return str(make_header(decode_header(message.get("Subject", "")))).strip()
    except (OSError, UnicodeError, ValueError):
        return ""


def _restore_matching_foxmail_window(subject: str, timeout_seconds: float = 5.0) -> bool:
    """Restore the Foxmail viewer that matches the EML subject when possible."""
    if sys.platform != "win32" or not subject:
        return False
    user32 = ctypes.windll.user32
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    deadline = time.monotonic() + timeout_seconds
    subject_folded = subject.casefold()
    while time.monotonic() < deadline:
        matches: list[int] = []

        def collect(hwnd: int, _lparam: int) -> bool:
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, len(buffer))
                if subject_folded in buffer.value.casefold():
                    matches.append(hwnd)
            return True

        user32.EnumWindows(enum_proc(collect), 0)
        if matches:
            hwnd = matches[-1]
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            return True
        time.sleep(0.2)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foxmail-exe", required=True)
    parser.add_argument("--audit-log")
    parser.add_argument("url")
    args = parser.parse_args()
    foxmail = Path(args.foxmail_exe).resolve()
    if not foxmail.is_file():
        raise FileNotFoundError(f"Foxmail executable not found: {foxmail}")
    parsed = urlparse(args.url)
    if parsed.scheme.casefold() != "mailtask-foxmail":
        raise ValueError("unsupported URL scheme")
    values = parse_qs(parsed.query)
    raw_path = values.get("path", [""])[0]
    if raw_path.startswith("/") and len(raw_path) > 2 and raw_path[2] == ":":
        raw_path = raw_path[1:]
    eml = Path(raw_path).resolve()
    if eml.suffix.casefold() != ".eml" or not eml.is_file():
        raise ValueError("the requested local EML file does not exist")
    # This is the same Windows Shell action as double-clicking the EML in
    # Explorer. It honors the verified current-user Foxmail.eml association
    # and handles Foxmail's existing single-instance process correctly.
    os.startfile(str(eml), "open")
    restored = _restore_matching_foxmail_window(_message_subject(eml))
    if args.audit_log:
        log = Path(args.audit_log).resolve()
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(
                f"{datetime.now(timezone.utc).isoformat()} opened {eml.name} via Windows Shell association; "
                f"viewer_restored={str(restored).lower()}\n"
            )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
