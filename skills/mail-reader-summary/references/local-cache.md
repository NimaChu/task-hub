# Foxmail local text indexes (experimental)

Use `scripts/read_foxmail_cache.py --account-dir "<Foxmail account storage folder>"` to probe without writing. This uses only Python standard-library code. The source folder must contain `Mails/Index` and `Indexes/`; do not pass the installation root. The script never opens `Accounts/` or `Index.key` and does not connect to a server.

Experimentally validated against Foxmail 7.2.25.563. Cross-version and large-store compatibility are not established. Header signature, record markers, bounds, UTF decoding, subject equality and snapshot stability are checked; unfamiliar layouts fail rather than silently guessing. Snapshot checks detect changed files but cannot guarantee Foxmail has completed a multi-file index update. Retry after client synchronization if validation fails.

For an authorized first-run sample:

```powershell
python "<skill-dir>/scripts/read_foxmail_cache.py" --account-dir "<account storage folder>" --project-dir "<project>" --sync --initial-latest 3
```

Without `--initial-latest`, the first sync baselines existing indexed messages. Later syncs process newly indexed records and changed imported records. The counter is a **local ID**, never an IMAP UID; `uid` and `uidvalidity` are null. Runtime state is `local_sources` in the shared `task-workspace/data/mail-reader-data.json`. The source currently uses account path plus store-generation bytes; moving the account changes its identity, so inspect migration/deduplication before switching paths.

To explicitly import a previously established local-history baseline, use:

```powershell
python "<skill-dir>/scripts/read_foxmail_cache.py" --account-dir "<account storage folder>" --project-dir "<project>" --sync --include-baseline
```

This clears only that local source's `baseline_ids`; it preserves already imported messages and their reviewed tasks, then upserts every cross-validated local ID.

Review new records and records marked `review_required`, derive tasks from their actual body text, and import using the task-board skill. The helper deliberately leaves new `tasks` empty for agent review. Distinguish top-level requests from quoted history and meeting responses. Sender in an invitation can differ from the person assigning the task in its forwarded body. Do not treat a meeting date as the deadline for a different task. Preserve stable task IDs and resolve duplicates semantically before creating tasks.

Attachment handling: `Indexes/attach/attach.idx` identifies messages with attachments, `attachInfo.rec0` supplies canonical Unicode filenames plus encoded byte position and size, and `Indexes/msgExt/exttxt_txt` cross-checks names against message IDs. Each attachment record is stored beside the message body with its filename, attachment ordinal, verified byte range, and project-independent Foxmail container reference such as `Mails/5/1/37`. Foxmail's binary payload remains inside that proprietary message container and is not copied or presented as a valid standalone file unless a later decoder can verify it. `binary_status: stored_in_foxmail_container_not_exported` makes this explicit.

Limitations: only cached search text and attachment metadata are directly available. Rich formatting, uncached messages, standalone attachment bytes, complete recipients, timezone semantics and server UID mapping are not proven. Any task dependent on an attachment must explicitly carry that limitation into its visible task record. This route archives the attachment relationship and storage provenance but does not claim byte-for-byte attachment export. If an independently exported local file has a unique exact filename and a size within eight bytes of the indexed size, `recover_local_attachments.py` can copy it to the shared project folder, hash it, and mark the recovery method; this is local-match recovery, not container decryption.

Format observations: `Mails/Index` has a 512-byte header and 512-byte records. The tested record strings start at byte 51, with four byte lengths at 45–48 and a 16-bit subject length at 49. Text `.map` files have a 32-byte header and 16-byte entries; entries store big-endian ID, offset and byte length after a marker. The corresponding `.rec0` UTF-16 text starts 12 bytes after the pointed-to offset. These are version-specific observations, not a vendor format guarantee.
