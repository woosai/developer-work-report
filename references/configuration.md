# Configuration

The default configuration lives outside the installed skill at `~/.config/developer-work-report/config.json`. This prevents upgrades from overwriting personal paths and keeps local paths and private Drive IDs out of a public Git repository.

## Top-level fields

- `version`: Must be `1`.
- `timezone`: IANA timezone used for schedules and date grouping.
- `execution`: Local scheduled-task project information.
- `git`: Git author identities included in this personal work report.
- `automations`: Normal collection and failure-recovery schedule definitions.
- `sources`: One or more local business folders. Multiple entries are supported.
- `session_sources`: Optional AI session-log locations used only to extract human prompts.
- `destinations`: One or more upload targets. Multiple enabled Google Drive folders are supported.
- `privacy`: Prompt masking and secret-exclusion controls.

## Execution

`execution.project_path` is the local project directory used by the scheduled task. It must be an absolute path. `execution.project_id` is optional in the portable example but may be required by the desktop app when creating a project-scoped automation.

## Automations

Both `collection` and `recovery` accept:

- `id`: Stable automation ID used to update rather than duplicate the task.
- `name`: User-facing task name.
- `enabled`: Whether the automation should be active.
- `weekdays`: Array using `MO`, `TU`, `WE`, `TH`, `FR`, `SA`, `SU`.
- `time`: Local 24-hour `HH:MM`.
- `skip_public_holidays`: Whether the prompt should check holidays before writing.

The recovery task always limits collection to the end of the previous local day. Its schedule is independent of the normal collection time.

## Git

`git.author_emails` is a required non-empty array. Only commits whose author email matches an entry (case-insensitively) are collected. This prevents teammates' commits from entering a personal report while allowing multiple identities for the same developer. Email addresses are configuration-only and remain masked in exported patches and summaries.

## Sources

Each source accepts:

- `name`: Unique stable label.
- `path`: Absolute local folder path.
- `enabled`: Include or ignore this source.
- `collect`: Any combination of `documents`, `code`, `prompts`, `other`.
- `from`: Optional inclusive `YYYY-MM-DD` lower bound.
- `until`: Optional inclusive `YYYY-MM-DD` upper bound for historical-only sources.

Use separate entries when different folders need different date bounds or categories. Array order does not determine precedence.

## Session sources

Each session source accepts `agent`, `path`, `format`, and `enabled`. These paths are read-only and are never upload sources themselves. The collection must extract only human prompts linked to an enabled business source.

## Destinations

Each destination accepts:

- `name`: Unique label used in reports.
- `provider`: Currently `google_drive`.
- `folder_url`: Google Drive folder URL.
- `enabled`: Include or ignore this destination.

Every enabled destination is checked independently. Overall success requires all enabled destinations to contain the same required report set.

## Privacy

Keep `mask_prompts` and `exclude_secrets` enabled for ordinary use. `mask_home_user` anonymizes the user component of absolute home paths. `withhold_on_uncertainty` prevents uploads when a second privacy inspection cannot establish that the export is safe.

Never store credentials, access tokens, passwords, or session contents in this configuration.
