# Source routing

Choose the least burdensome source that satisfies the user's requested fidelity. Never replace a working initialized source merely because another adapter exists.

## Priority

1. **Existing working source** — run its ordinary incremental sync. This is simplest because its cursor and provenance already exist.
2. **Credential-free local source** — for a new Foxmail project, probe the verified cache adapter first. For Thunderbird mbox or Apple Mail `.emlx`, use the archive adapter. These avoid account setup but may lack server-only mail or complete attachment bytes.
3. **Exported EML** — use when the client can export selected messages and full body/attachments are needed without mailbox credentials. This requires a user export but is portable and auditable.
4. **Read-only IMAP** — use when the request requires automatic ongoing sync, authoritative UID history, complete decoded attachments, Sent-folder evidence, or mail absent from local storage. Only at this point request a provider-approved password or authorization code through a local hidden prompt.

Do not make the user try every tier. Move directly to the first tier that can meet explicit requirements. For example, continuous Inbox plus Sent monitoring needs an existing or newly configured IMAP connection; a one-off summary from synchronized Foxmail should start with local cache.

## Supported adapters

| Source | Entry point | Identity and limits |
|---|---|---|
| Foxmail 7.2 verified indexes | `read_foxmail_cache.py` | Local IDs and store generation; cached search body plus attachment metadata, not guaranteed attachment bytes |
| RFC 822 `.eml` folder | `read_eml_folder.py` | SHA-256 content identity; saves original and decoded attachments |
| Thunderbird mbox | `read_mail_archive.py --format thunderbird-mbox --path <mbox>` | Credential-free selected archive; caller labels `--direction inbound|sent` |
| Apple Mail `.emlx` tree | `read_mail_archive.py --format apple-emlx --path <folder>` | Credential-free selected archive; caller labels direction |
| Provider-neutral IMAP | `read_mail.py --sync` | UID + UIDVALIDITY, read-only `BODY.PEEK[]`, optional verified Sent folder |

Use `read_mail_archive.py --discover` to list supported Thunderbird/Apple Mail roots without reading messages. Then select the exact archive path; discovery is not authorization to scan every profile.

Outlook desktop COM and proprietary `.msg` are not currently supported adapters. Prefer generic EML export or IMAP until an implementation can preserve full bodies, attachments, stable identity, read-only behavior, and tests. Do not copy an adapter that merely truncates bodies or labels binary MSG as EML.

The database can retain multiple source hashes. Configure and verify one account/source at a time; use separate projects when account-level isolation is desired. Never merge sources by subject alone.

## Escalating to IMAP

Read [setup and credentials](setup-and-credentials.md). For the intended NetEase enterprise/Foxmail onboarding, provide the authorization-code application link only when IMAP is actually needed. Reuse locally available working credentials; otherwise let the user enter the code in a hidden prompt, not chat or a shell command.
