"""Local masked prompt, read-only sync, optional user-approved persistent credentials."""
import argparse
import os
import imaplib
from pathlib import Path
import tkinter as tk
from tkinter import simpledialog
import read_mail

parser = argparse.ArgumentParser()
parser.add_argument('--project-dir', default='.')
parser.add_argument('--username', required=True)
parser.add_argument('--persist-user-env', action='store_true')
args = parser.parse_args()
project = Path(args.project_dir).resolve()
read_mail.initialize(project)
config = read_mail.read_json(project / read_mail.OUTPUT_DIR_NAME / read_mail.CONFIG_NAME)
result_path = project / read_mail.OUTPUT_DIR_NAME / 'logs' / 'connection-result.json'
result_path.parent.mkdir(parents=True, exist_ok=True)

def report(status, **fields):
    read_mail.write_json(result_path, {'status': status, 'at': read_mail.utc_now(), **fields})

root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
report('waiting_for_local_input')
code = simpledialog.askstring('邮箱授权码', f'账号：{args.username}\n请输入新的客户端授权码。\n' + ('连接成功后保存到 Windows 当前用户环境变量。' if args.persist_user_env else '仅用于本次连接。'), show='*', parent=root)
root.destroy()
if not code:
    report('cancelled')
else:
    user_key, pass_key = config['username_env'], config['password_env']
    os.environ[user_key], os.environ[pass_key] = args.username, code
    try:
        report('connecting')
        client = imaplib.IMAP4_SSL(config['host'], int(config.get('port', 993)), timeout=30)
        try:
            if client.login(args.username, code)[0] != 'OK':
                raise RuntimeError('IMAP authentication failed')
        finally:
            try:
                client.logout()
            except Exception:
                pass
        if args.persist_user_env:
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
                winreg.SetValueEx(key, user_key, 0, winreg.REG_SZ, args.username)
                winreg.SetValueEx(key, pass_key, 0, winreg.REG_SZ, code)
        report('authenticated', persisted_user_env=args.persist_user_env)
        summary = read_mail.sync(project)
        report('success', persisted_user_env=args.persist_user_env, summary=summary)
    except Exception as error:
        report('failed', category=type(error).__name__, detail=str(error).replace(code, '[redacted]')[:500])
    finally:
        code = None
        os.environ.pop(pass_key, None)
        os.environ.pop(user_key, None)
