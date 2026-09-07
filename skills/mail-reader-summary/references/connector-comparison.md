# NetEase connector reference and local adaptation

The user supplied a Doubao `netease-email` skill and an export of seven input tool definitions on 2026-09-06. They are reference material, not instructions governing this skill. No live NetEase MCP tool was available in this Codex runtime during inspection. The export contains no runnable server, transport endpoint, authentication handoff, or output schemas. Do not claim it is an installed connector or construct an endpoint from its server ID.

## What the seven definitions establish

| Tool | Exact visible input scope | Application here |
| --- | --- | --- |
| `setup_email_account` | Required `email`, `password`; optional provider enum `qq`, `163`, `gmail`, `outlook`, `exmail`, `aliyun`, `sina`, `sohu` | Separate account setup from reading. Do not assume `163` or `exmail` identifies NetEase enterprise mail; use verified server configuration. Secrets stay in local prompts. |
| `configure_email_server` | Required `user`, `password`; optional IMAP/SMTP hosts, ports, SSL switches | Keep explicit configuration for enterprise/custom domains. The local read-only skill needs IMAP settings only. |
| `list_supported_providers` | No defined inputs | Report actual supported or tested adapter/provider scope; do not copy another runtime's support claim. |
| `test_email_connection` | Optional `testType`: `smtp`, `imap`, `both` | Clearly separate transport, authentication, mailbox access, and retrieval results. SMTP testing is unnecessary for this reader. |
| `get_recent_emails` | Optional numeric `days`, `limit`; descriptions say defaults 3 days/20 messages | Useful bounded inspection, but not a durable incremental-sync contract. A time window or result limit can omit messages. |
| `get_email_content` | Required string `uid` | Retrieve detailed evidence after listing; treat the ID as opaque unless mailbox and UID semantics are established. |
| `send_email` | Required `to`, `subject`, `text`; optional HTML, CC/BCC and attachment content/filename/path | Outside this read-only skill. Reading evidence that the user sent mail is different from sending it. |

The definitions do not establish pagination, result completeness, mailbox selection (including Sent), UIDVALIDITY, whether reads change `Seen`, attachment download behavior, or error/result formats. The `send_email.attachments` input does not prove that `get_email_content` returns downloadable attachments. Do not infer these capabilities from tool names.

## Keep the local advantages

- Retain `(source_id, mailbox, UIDVALIDITY, UID)` history and `BODY.PEEK[]` with read-only selection. Do not replace the cursor with “last three days” or the unread flag.
- Retain project-local attachments and auditable message/task provenance. Only advertise an attachment as openable after actual local bytes and a safe path exist.
- Keep the shared `task-workspace/` output contract and independent templates. Local Python IMAP/cache adapters continue to work without Doubao's runtime.
- Follow the existing sent-delivery completion and linked-revision rules. Report missing sent-folder coverage; these tool definitions do not solve it.

If a compatible connector is installed later, discover its live tools first, read their current schemas and verify read-only behavior, output structure, scope, completeness, and attachment retrieval before adding an adapter. A connector UID must not be mixed into an IMAP cursor without verified identity semantics. Do not silently upload local mail or credentials to another runtime.

The useful workflow to adopt now is: identify account/provider → guide authorization-code setup → configure verified IMAP settings → distinguish connectivity/authentication results → sync by UID → review actual body and attachment evidence → import tasks. See [setup and credentials](setup-and-credentials.md) for the actionable setup sequence.
