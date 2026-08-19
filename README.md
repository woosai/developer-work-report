# developer-work-report

A configurable Codex skill for collecting developer work artifacts from multiple local folders, organizing them by date and category, mirroring them to multiple Google Drive folders, and recovering missed scheduled runs.

## Features

- Multiple local source folders with independent categories and date bounds
- Multiple Google Drive destinations with independent duplicate and failure checks
- Configurable collection and recovery weekdays/times
- Document collection, Git patches and summaries, and AI-session prompt exports
- Mandatory personal-data and credential masking for prompt exports
- Recovery through the end of the previous day without duplicating successful uploads

## Install from GitHub

Ask Codex to install the skill from this repository, or use the bundled skill installer:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo GITHUB_USER/developer-work-report \
  --path . \
  --name developer-work-report
```

The skill becomes available on the next Codex turn as `$developer-work-report`.

## Configure

Create a personal configuration outside the installed skill:

```bash
python3 ~/.codex/skills/developer-work-report/scripts/developer_work_report_config.py init
```

Edit `~/.config/developer-work-report/config.json`, then validate and preview the generated schedules and prompts:

```bash
python3 ~/.codex/skills/developer-work-report/scripts/developer_work_report_config.py validate --check-paths
python3 ~/.codex/skills/developer-work-report/scripts/developer_work_report_config.py render
```

The configuration uses arrays for both `sources` and `destinations`, so each can contain any number of enabled entries. Collection and recovery schedules have independent weekday arrays and `HH:MM` times.

The example configuration contains placeholders only. Do not commit a personal configuration containing local usernames, private paths, or Drive folder IDs.

## Publish this package to your GitHub account

Create an empty repository named `developer-work-report` in the GitHub account you want to use. Do not initialize it with a README, license, or `.gitignore`, because this package already contains those files. Then run from the prepared local folder:

```bash
git remote add origin https://github.com/GITHUB_USER/developer-work-report.git
git branch -M main
git push -u origin main
```

Replace `GITHUB_USER` in this README with the repository owner's account name after publishing so the copy-and-paste installation command points to the correct repository.

## Use

Ask Codex:

```text
Use $developer-work-report to create or update my collection and recovery schedules from the validated configuration.
```

Local scheduled tasks require the computer to be powered on and the desktop app to be running at the scheduled time. The recovery schedule is a later scheduled check, not an immediate power-on trigger.
