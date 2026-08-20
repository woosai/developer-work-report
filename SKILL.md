---
name: developer-work-report
description: Configure, run, repair, or audit scheduled work-report collection that gathers documents, code diffs, and privacy-masked AI-session prompts from multiple local source folders and mirrors them to multiple Google Drive destinations.
---

# Developer Work Report

Use this skill to set up or operate a configurable daily work-report archive with a normal collection schedule and a failure-recovery schedule.

## Load the configuration

Use the configuration path supplied by the user. Otherwise use `~/.config/developer-work-report/config.json`.

If it does not exist, initialize it from `config/developer-work-report.example.json` with:

```bash
python3 scripts/developer_work_report_config.py init
```

Do not create automations or upload files until the user has reviewed the source folders, destinations, and schedules. Validate before every configuration-changing operation:

```bash
python3 scripts/developer_work_report_config.py validate --check-paths
```

Read [references/configuration.md](references/configuration.md) when creating, migrating, or troubleshooting a configuration. For ordinary runs, the validated configuration is authoritative.

## Route the request

- For Google Drive inspection or writes, load the `google-drive:google-drive` skill.
- For claims about scheduled-task behavior, missed runs, sleep, or desktop-app requirements, load `openai-docs` and verify current official documentation.
- For creating, updating, viewing, pausing, or deleting schedules, use the app automation tool. Inspect existing automation files first and update configured IDs rather than creating duplicates.
- For manual collection or backfill, do not change schedules unless the user also asks.

## Configure the schedules

Render validated prompts and recurrence values from the config:

```bash
python3 scripts/developer_work_report_config.py render
```

Use the rendered `collection` values for the normal automation and `recovery` values for the recovery automation. Preserve existing model, reasoning effort, project, execution environment, notification policy, and unrelated fields unless the user requests a change.

The recovery automation is recovery-only:

- Its upper bound is the previous day at 23:59:59 in the configured timezone.
- It creates nothing when all enabled destinations are complete through that bound.
- When any destination is missing, partial, or failed, it resumes after the last success common to every enabled destination.
- It repairs each destination independently and succeeds only when all enabled destinations are synchronized.
- It is a scheduled fallback, not an immediate power-on trigger.

## Collect a report

1. Resolve the time range in the configured timezone and apply each source's optional `from` and `until` bounds.
2. Inspect every enabled destination before writing. Compare completion markers, daily indexes, expected relative paths, and file presence; a date folder alone is not proof of success.
3. For each enabled source, collect only the configured categories:
   - `documents`: document-like artifacts, preserving source-relative directories. Assign each file to its actual filesystem modification date in the configured timezone; never assign it to the collection date merely because it was discovered then. Reconcile the staged date against the source mtime before upload.
   - `code`: repository-and-date UTF-8 patches and Markdown summaries, including committed, staged, unstaged, and untracked text changes. Also include one UTF-8 BOM `코드/commits.csv` per date, consolidating every selected committed change across repositories. Do not upload complete tracked source trees. Generate committed history with `scripts/collect_git_history.py`; do not hand-roll Git loops.
   - `prompts`: human-entered prompts from demonstrably related Codex, Claude, or Antigravity sessions. For Codex, accept only user-owned threads (`thread_source == "user"`) and reject guardian, approval-review, subagent, automation, and tool-generated events. For Claude, reject subagent transcripts, task notifications, tool/command output, environment blocks, and compaction continuations. Apply the equivalent human-only rule to Antigravity.
   - `other`: eligible non-document, non-code outputs while excluding caches and build intermediates.
4. Before uploading prompt exports, run `scripts/sanitize_prompt_exports.py --root /path/to/staging --from YYYY-MM-DD --until YYYY-MM-DD`. It removes known machine-generated sections and irreversibly masks personal data, home-directory usernames, login IDs, credentials, tokens, cookies, keys, and connection strings. Treat a nonzero exit as an upload blocker. Run a second independent inspection; withhold uncertain exports and report only counts.
5. Build the configured date/category hierarchy. Upload missing items to each destination independently and avoid duplicates by relative path, name, and content.
6. Continue safe work after an isolated destination failure and retry transient failures. Do not write a completion marker while any required item is missing.
7. Never modify, move, or delete local source files or original session logs. Never upload raw session logs, assistant output, system/developer text, tool output, or internal reasoning.

### Mandatory committed-code reconciliation

Run the deterministic collector for the exact report range before any code upload:

```bash
python3 scripts/collect_git_history.py \
  --config ~/.config/developer-work-report/config.json \
  --output /path/to/staging \
  --from YYYY-MM-DD \
  --until YYYY-MM-DD
```

The generated `git-collection-manifest.json` is authoritative. The collector:

- discovers nested repositories in every enabled `code` source;
- reads every reachable branch and tag with `git log --all` and de-duplicates commit hashes;
- groups by committer date in the configured timezone;
- accumulates the full repository/date group before writing, so a later commit cannot overwrite an earlier one;
- verifies that every selected hash occurs exactly once in both patch and summary;
- records commit counts, hash lists, and SHA-256 values for upload reconciliation.
- writes a date-level `코드/commits.csv` with Korean headers for time, repository, current containing branch refs, abbreviated commit, conventional-commit type/scope, subject, file/addition/deletion counts, merge flag, and repositories sharing the same full commit hash;
- records each CSV path, row count, and SHA-256 in the manifest and verifies that the total CSV rows equal the selected repository/commit rows.

The CSV `브랜치` field is the closest currently containing local or remote-tracking branch ref, derived from current reachability; Git does not retain the branch name on which a historical commit was created. Do not present it as historical certainty. Abort the upload if the manifest count differs from the daily index, a listed hash is absent, the CSV row count differs, or an output digest changes before upload. Current staged, unstaged, and untracked snapshots are separate run-time artifacts: never present them as reconstructable historical state.

## Regular and recovery behavior

A no-change normal collection still creates the date folder and daily index in every enabled destination, but no empty category folders. A recovery run that finds no gap creates nothing.

When a source has `until`, do not scan it after that boundary during regular runs. During backfill, include it only where the requested range intersects its configured bounds.

## Verify and report

After schedule changes, verify that both configured automations are active, their rendered schedules match the config, and every enabled destination appears in both prompts. After uploads, read back the destination roots, earliest and latest affected dates, at least one mixed-content sample date, and any completion marker. For code, also sample a multi-commit date and compare its Drive patch and summary against the manifest hash list and commit count, then download that date's `코드/commits.csv` and reconcile its row count and SHA-256 with the manifest. Do not trust a Drive preview or a cached folder listing as content proof: download the raw file and compare hashes/counts, and use file metadata `parents` to verify that every index and category folder belongs to the intended date folder.

Report in the user's language. Give per-destination links and counts for uploads, duplicates, masking/withholding, and failures. State the exact remaining blocker when synchronization is incomplete.
