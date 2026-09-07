#!/usr/bin/env python3
"""Register the task-board EML URL protocol for the current Windows user."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    if sys.platform != "win32":
        raise RuntimeError("the Foxmail EML protocol is supported only on Windows")
    import winreg

    parser = argparse.ArgumentParser()
    parser.add_argument("--foxmail-exe", required=True)
    parser.add_argument("--audit-log")
    args = parser.parse_args()
    foxmail = Path(args.foxmail_exe).resolve()
    launcher = Path(__file__).with_name("open_eml.py").resolve()
    if not foxmail.is_file():
        raise FileNotFoundError(f"Foxmail executable not found: {foxmail}")
    root_path = r"Software\Classes\mailtask-foxmail"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, root_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:Mail Task Foxmail EML Protocol")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, root_path + r"\DefaultIcon") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'"{foxmail}",0')
    log_argument = f' --audit-log "{Path(args.audit_log).resolve()}"' if args.audit_log else ""
    command = f'"{Path(sys.executable).resolve()}" "{launcher}" --foxmail-exe "{foxmail}"{log_argument} "%1"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, root_path + r"\shell\open\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
    print(f"Registered mailtask-foxmail for current user with {foxmail}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
