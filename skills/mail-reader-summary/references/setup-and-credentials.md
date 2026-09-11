# Local discovery and credential setup

## Inspect Foxmail without exposing credentials

1. Use the installation or storage directory supplied by the user. List immediate folders first; do not search unrelated application profiles or credential stores.
2. Foxmail 7.2 may store accounts under `Storage/<account>/Accounts/`. Inspect filenames such as `Account.cfg`, `Account.htb`, and `Account.rec0`. The small `.cfg` file may be an index; the readable account fields may reside in `.rec0`.
3. Treat these as binary files. Do not dump their raw contents or all strings: they may contain credentials. Extract only allowlisted fields for the chosen account: account address, incoming/outgoing server, port, and SSL setting. Do not decode the Password field as part of basic configuration discovery.
4. In one verified Foxmail 7.2 layout, ASCII field names occur in `Account.rec0`. `IncomingPort` and `OutgoingPort` are followed by little-endian type marker 3 and a 32-bit integer; `InComingSSL` and `OutgoingSSL` are followed by marker 11 and a boolean value. Treat this as a version-specific observation, not a universal file format. Validate markers before interpreting bytes; if ambiguous, use the client settings UI.
5. For server names, avoid screenshot transcription mistakes such as `q` versus `g`. Corroborate against the local record or provider documentation. Multiple or conflicting values may represent old records; do not silently choose the first match.
6. Test DNS and TCP/TLS with certificate validation enabled and bounded timeouts. Report connection success separately from authentication success. Change only the target project's non-secret configuration when authorized by the active setup task; do not modify Foxmail files.

The reusable skill must not contain an actual user's address, installation path, account records, or credentials. Keep provider-neutral assets. Put user-specific findings only in the project's private runtime folder.

## Browser-assisted authorization code setup

### When IMAP is selected: application link first

The intended users are company colleagues already using Foxmail with NetEase enterprise mail. First follow [source routing](source-routing.md): a sufficient credential-free local read does not require IMAP setup. Once IMAP is selected because the user needs complete attachments, Sent evidence, missing server mail, or continuous incremental sync, do not ask whether their mailbox is personal or enterprise and do not start with instructions to enable IMAP/SMTP. Existing Foxmail service configuration is the starting point; revisit protocol settings only if a concrete connection failure requires it.

1. For the first IMAP connection, send [网易企业邮箱授权码申请](https://mail.qiye.163.com/static/commonweb/authcode.html?p=qiye-authcode). Ask the user to obtain a client authorization code through that page, completing any login/verification the page itself requests.
2. Prepare the reader command with the user's project path and an available Python runtime. Obtain non-secret account/server settings from the configured Foxmail account where available; ask only for missing information needed to identify that account.
3. Have the user enter the code at the local hidden credential prompt after the command is running. Do not ask them to paste it into chat or enter it as a PowerShell command. The authorization code replaces the web-login password for this connection.

Suggested first reply: “请先打开[网易企业邮箱授权码申请](https://mail.qiye.163.com/static/commonweb/authcode.html?p=qiye-authcode)，按网页提示申请授权码。我会准备好本机读取命令，你随后在隐藏输入框中输入授权码即可，不用发到聊天里。” Do not claim an input dialog is already open until it actually is. If working credentials are already available locally, reuse the configured connection rather than forcing code generation on every read.

On `ERR.LOGIN.REQCODE`, guide the same application-link and local-input flow; do not repeatedly try the web-login password. Explain session separation only if the user asks why the reader needs a credential despite Foxmail already being logged in.

Use the available browser automation interface and observe the page after navigation/actions. Select the provider from verified account configuration. Login and security settings vary by provider and enterprise policy; do not claim an exact menu path without observing it.

For NetEase enterprise mail, the public website is `https://qiye.163.com/`. In one user-confirmed 2026 setup, the provider help article was `https://office.163.com/helpCenter/mail/d/1892504942861234178.html` and the authorization-code page was `https://mail.qiye.163.com/static/commonweb/authcode.html?p=qiye-authcode`. Treat these as user-reported provider URLs rather than a universal or browser-verified menu sequence; enterprise policy and page paths can change. If the site or browser tool blocks access, stop that browser route and do not retry through another surface or an indirect route to bypass the restriction.

Let the user enter missing passwords, MFA codes, and other secrets locally. Follow the browser tool's confirmation requirements for creating authorization credentials, granting access, or changing authentication settings. Do not reset an existing password, revoke existing clients, disable protections, or broaden access merely to make IMAP work.

If a client authorization code is available, prefer a dedicated code that the user can later revoke independently. If the feature is absent, record that observation and ask the enterprise administrator which credentials and protocol permissions apply. Do not assume every account supports authorization codes.

Do not include passwords, authorization codes, cookies, recovery codes, or screenshots displaying them in logs or skill examples. Record only page/menu labels, outcome, and remaining steps. Clearly mark whether code creation and IMAP authentication were actually completed.

## Supply credentials to the process that runs the reader

The reader accepts the environment-variable names specified by the project configuration. Check only their presence, never print their values. Process, user, and machine scopes can differ; a running Codex session does not automatically inherit changes made in a separate terminal.

The reader now explicitly falls back to Windows current-user `HKCU\Environment` if a process variable is absent. When the user chooses persistence, use `scripts/connect_local.py --project-dir "<project>" --username "<verified-account>" --persist-user-env`. Login is verified before saving. The code stays out of commands, JSON, and skill assets; only the named current-user environment value stores it. This persists across restarts but is readable by other processes under the same user. Do not enable persistence without the user's choice. If an old process variable exists, it takes precedence; clear that process variable when replacing a stale code.

For a one-time run, the user can execute this in their own PowerShell window, substituting their account and the actual script path:

```powershell
$mailCredential = Get-Credential -UserName '<account>' -Message 'Enter email password or client authorization code'
$env:MAIL_TASK_IMAP_USER = $mailCredential.UserName
$env:MAIL_TASK_IMAP_PASS = $mailCredential.GetNetworkCredential().Password
try {
    python '<skill-dir>\scripts\read_mail.py' --project-dir '<project-dir>' --sync
} finally {
    Remove-Item Env:MAIL_TASK_IMAP_USER -ErrorAction SilentlyContinue
    Remove-Item Env:MAIL_TASK_IMAP_PASS -ErrorAction SilentlyContinue
    $mailCredential = $null
}
```

Run the reader in that same terminal. Use an available Python 3.9+ executable, including the bundled runtime if needed. This is temporary process configuration, not persistent credential storage. Never put a literal secret in a shell command, chat, JSON, or skill asset.

An even shorter interactive option is `python "<skill-dir>\scripts\read_mail.py" --project-dir "<project-dir>" --sync --prompt-credentials`. Run the whole command first and wait for `IMAP password or client authorization code:`; enter the authorization code only at that hidden prompt, never at a bare `PS ...>` prompt. If the configured credential environment variable already exists, the script uses it instead of prompting; clear only that process variable when deliberately replacing a stale credential. Do not copy Markdown escapes such as `\_`, `\@`, or `&#x20;` into PowerShell.

Troubleshooting: `ERR.LOGIN.REQCODE` means this server requires a client authorization code. Guide generation/replacement through the official page, then retry locally with the code; do not keep retrying the login password. Distinguish a DNS/TLS failure, rejected authentication, disabled IMAP access, successful login, UID-baseline creation, and actual body/attachment retrieval in the result report.

After a real successful sync, inspect the new-message records and refine tasks before importing them with the board skill. Default first sync reads only the most recent calendar month; honor an explicit wider request with `--history-months N`. Older configurations may explicitly select baseline-only mode: describe the actual result and do not claim a baseline-only connection read message bodies.

When a credential-free Foxmail history is already present and a later IMAP bootstrap is used to recover attachments, import historical IMAP mail in a project-local staging project first. Then use `merge_imap_bootstrap.py` to copy verified attachment files and the mailbox UID cursor into the main project without importing duplicate messages or deterministic draft tasks:

```powershell
python "<skill-dir>\scripts\merge_imap_bootstrap.py" --project-dir "<project>" --staging-project "<staging-project>"
```

Reapply the Agent review manifest after merging so its task attachment snapshots receive the new `saved_path` values, then import into the task board. Keep staging under the project's private archive area and never store credentials there.

## Credential-free local sources

Do not assume that finding Foxmail's `Storage/<account>/Mails` directory means its numbered message files are RFC 822/EML. Probe a sample without printing message content, then require recognizable MIME headers before parsing it as mail.

One observed Foxmail 7.2.25 layout stored individual messages as high-entropy binary files alongside `Index` and a 16-byte `Index.key`. Repeating XOR, RC4, common AES modes using `Index.key` directly, and standard compression signatures did not yield MIME data. Foxmail's Simple MAPI provider could create a session but returned `MAPI_E_NOT_SUPPORTED` for message enumeration. The bundled `Export_Foxmail.dll` initialized only as a legacy importer and returned no accounts for the active 7.2 storage. These observations justify rejecting those adapters for that build; they do not define a universal Foxmail format.

The previous probes did not examine the readable full-text indexes. Subsequent work verified a credential-free text-index adapter; see [local-cache.md](local-cache.md). Failure to decode numbered message files does not imply all cached content is inaccessible.

Other routes:

- IMAP with whichever credential the provider accepts: ordinary mailbox password, client authorization code, or another provider-approved app credential.
- A folder of genuine `.eml` files exported by the client, when the user accepts that export workflow. Track these by Message-ID plus a content hash, not IMAP UID.

Never recover or decrypt the saved Foxmail account password merely to avoid a local prompt. Never invent a decoder from `Index.key`; use a documented or independently verified format before adding a version-specific local adapter.
