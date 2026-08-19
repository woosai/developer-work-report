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
   - `documents`: document-like artifacts, preserving source-relative directories.
   - `code`: repository-and-date UTF-8 patches and Markdown summaries, including committed, staged, unstaged, and untracked text changes. Do not upload complete tracked source trees.
   - `prompts`: human-entered prompts from demonstrably related Codex, Claude, or Antigravity sessions.
   - `other`: eligible non-document, non-code outputs while excluding caches and build intermediates.
4. Before uploading prompt exports, irreversibly mask personal data, home-directory usernames, credentials, tokens, cookies, keys, and connection strings. Run a second inspection; withhold uncertain exports and report only counts.
5. Build the configured date/category hierarchy. Upload missing items to each destination independently and avoid duplicates by relative path, name, and content.
6. Continue safe work after an isolated destination failure and retry transient failures. Do not write a completion marker while any required item is missing.
7. Never modify, move, or delete local source files or original session logs. Never upload raw session logs, assistant output, system/developer text, tool output, or internal reasoning.

## Regular and recovery behavior

A no-change normal collection still creates the date folder and daily index in every enabled destination, but no empty category folders. A recovery run that finds no gap creates nothing.

When a source has `until`, do not scan it after that boundary during regular runs. During backfill, include it only where the requested range intersects its configured bounds.

## Verify and report

After schedule changes, verify that both configured automations are active, their rendered schedules match the config, and every enabled destination appears in both prompts. After uploads, read back the destination roots, earliest and latest affected dates, at least one mixed-content sample date, and any completion marker.

Report in the user's language. Give per-destination links and counts for uploads, duplicates, masking/withholding, and failures. State the exact remaining blocker when synchronization is incomplete.
