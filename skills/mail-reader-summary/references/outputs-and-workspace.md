# Outputs and workspace

Initialize with `read_mail.py --project-dir <project> --init`; repair missing/invalid templates with `--rebuild`. Valid configuration and records are preserved, while invalid JSON is archived before template restoration.

All runtime content stays below `<project>/task-workspace/`:

- `config/mail-reader-config.json`: non-secret settings;
- `data/mail-reader-data.json`: source state, messages, evidence, and reviewed task candidates;
- `attachments/`: decoded files and retained original EML;
- `audit/`: Agent review manifests;
- `logs/`: setup and per-file errors;
- `exports/`: optional Markdown, CSV, or compact JSON summaries.

Choose output by request:

- **Direct answer:** synthesize a concise human-readable summary with important mail, requests, assigners, deadlines, delivery evidence, and coverage limitations. Cite subjects/message keys. No board is required.
- **Text cache view:** `read_mail.py --summary --summary-limit N`.
- **Markdown/CSV/compact JSON:** `export_mail_summary.py --project-dir <project> --format markdown|csv|json [--only-new] [--limit N]`. These may contain private mail content and remain project-local.
- **Canonical structured source:** `data/mail-reader-data.json`.
- **Visual tasks:** use task-board only when requested; import reviewed tasks and regenerate/open its local HTML. Do not write task-board data directly from this skill.

Both independently installed skills agree on `task-workspace/`. Templates stay in skill `assets/`; user mail and outputs never do. Preserve attachment filenames, stable IDs, and existing browser storage compatibility during migrations.
