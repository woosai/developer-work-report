#!/usr/bin/env python3
"""Initialize, validate, and render work-report automation configuration."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SKILL_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_CONFIG = SKILL_ROOT / "config" / "developer-work-report.example.json"
DEFAULT_CONFIG = Path.home() / ".config" / "developer-work-report" / "config.json"
VALID_DAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
VALID_COLLECT = {"documents", "code", "prompts", "other"}
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
DRIVE_RE = re.compile(r"^/drive/folders/[^/]+/?$")


class ConfigError(Exception):
    pass


def load_config(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ConfigError("configuration root must be a JSON object")
    return data


def require_object(value: object, label: str, errors: list[str]) -> dict:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return {}
    return value


def require_nonempty_string(value: object, label: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be a non-empty string")
        return ""
    return value.strip()


def validate_date(value: object, label: str, errors: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        errors.append(f"{label} must be YYYY-MM-DD or null")
        return
    try:
        date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label} must be a valid YYYY-MM-DD date")


def validate_schedule(value: object, label: str, errors: list[str]) -> None:
    schedule = require_object(value, label, errors)
    require_nonempty_string(schedule.get("id"), f"{label}.id", errors)
    require_nonempty_string(schedule.get("name"), f"{label}.name", errors)
    if not isinstance(schedule.get("enabled"), bool):
        errors.append(f"{label}.enabled must be true or false")
    time_value = schedule.get("time")
    if not isinstance(time_value, str) or not TIME_RE.fullmatch(time_value):
        errors.append(f"{label}.time must use 24-hour HH:MM")
    weekdays = schedule.get("weekdays")
    if not isinstance(weekdays, list) or not weekdays:
        errors.append(f"{label}.weekdays must be a non-empty array")
    else:
        invalid = [day for day in weekdays if day not in VALID_DAYS]
        if invalid:
            errors.append(f"{label}.weekdays contains invalid values: {invalid}")
        if len(set(weekdays)) != len(weekdays):
            errors.append(f"{label}.weekdays must not contain duplicates")
    if not isinstance(schedule.get("skip_public_holidays"), bool):
        errors.append(f"{label}.skip_public_holidays must be true or false")


def validate_config(data: dict, check_paths: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if data.get("version") != 1:
        errors.append("version must be 1")

    timezone = require_nonempty_string(data.get("timezone"), "timezone", errors)
    if timezone:
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            errors.append(f"timezone is not recognized: {timezone}")

    execution = require_object(data.get("execution"), "execution", errors)
    if execution.get("environment") != "local":
        errors.append("execution.environment must currently be 'local'")
    project_path = require_nonempty_string(execution.get("project_path"), "execution.project_path", errors)
    if project_path and not Path(project_path).is_absolute():
        errors.append("execution.project_path must be absolute")
    if check_paths and project_path and not Path(project_path).is_dir():
        errors.append(f"execution.project_path is not an accessible directory: {project_path}")
    project_id = execution.get("project_id")
    if not isinstance(project_id, str):
        errors.append("execution.project_id must be a string, possibly empty before setup")
    elif not project_id:
        warnings.append("execution.project_id is empty; the desktop app may require it when creating automations")

    automations = require_object(data.get("automations"), "automations", errors)
    validate_schedule(automations.get("collection"), "automations.collection", errors)
    validate_schedule(automations.get("recovery"), "automations.recovery", errors)
    collection = automations.get("collection") if isinstance(automations.get("collection"), dict) else {}
    recovery = automations.get("recovery") if isinstance(automations.get("recovery"), dict) else {}
    if collection.get("id") and collection.get("id") == recovery.get("id"):
        errors.append("collection and recovery automation IDs must differ")

    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("sources must be a non-empty array")
        sources = []
    source_names: set[str] = set()
    enabled_sources = 0
    for index, raw_source in enumerate(sources):
        label = f"sources[{index}]"
        source = require_object(raw_source, label, errors)
        name = require_nonempty_string(source.get("name"), f"{label}.name", errors)
        if name in source_names:
            errors.append(f"duplicate source name: {name}")
        source_names.add(name)
        enabled = source.get("enabled")
        if not isinstance(enabled, bool):
            errors.append(f"{label}.enabled must be true or false")
        elif enabled:
            enabled_sources += 1
        source_path = require_nonempty_string(source.get("path"), f"{label}.path", errors)
        if source_path and not Path(source_path).is_absolute():
            errors.append(f"{label}.path must be absolute")
        if check_paths and enabled and source_path and not Path(source_path).is_dir():
            errors.append(f"{label}.path is not an accessible directory: {source_path}")
        collect = source.get("collect")
        if not isinstance(collect, list) or not collect:
            errors.append(f"{label}.collect must be a non-empty array")
        else:
            invalid = [item for item in collect if item not in VALID_COLLECT]
            if invalid:
                errors.append(f"{label}.collect contains invalid values: {invalid}")
            if len(set(collect)) != len(collect):
                errors.append(f"{label}.collect must not contain duplicates")
        validate_date(source.get("from"), f"{label}.from", errors)
        validate_date(source.get("until"), f"{label}.until", errors)
        if isinstance(source.get("from"), str) and isinstance(source.get("until"), str):
            if source["from"] > source["until"]:
                errors.append(f"{label}.from must not be after until")
    if enabled_sources == 0:
        errors.append("at least one source must be enabled")

    git_options = require_object(data.get("git"), "git", errors)
    author_emails = git_options.get("author_emails")
    if not isinstance(author_emails, list) or not author_emails:
        errors.append("git.author_emails must be a non-empty array")
    else:
        normalized_emails: set[str] = set()
        for index, email in enumerate(author_emails):
            value = require_nonempty_string(email, f"git.author_emails[{index}]", errors).lower()
            if value and "@" not in value:
                errors.append(f"git.author_emails[{index}] must be an email address")
            if value in normalized_emails:
                errors.append("git.author_emails must not contain duplicates")
            normalized_emails.add(value)

    session_sources = data.get("session_sources", [])
    if not isinstance(session_sources, list):
        errors.append("session_sources must be an array")
        session_sources = []
    for index, raw_session in enumerate(session_sources):
        label = f"session_sources[{index}]"
        session = require_object(raw_session, label, errors)
        require_nonempty_string(session.get("agent"), f"{label}.agent", errors)
        session_path = require_nonempty_string(session.get("path"), f"{label}.path", errors)
        require_nonempty_string(session.get("format"), f"{label}.format", errors)
        enabled = session.get("enabled")
        if not isinstance(enabled, bool):
            errors.append(f"{label}.enabled must be true or false")
        if session_path and not Path(session_path).is_absolute():
            errors.append(f"{label}.path must be absolute")
        if check_paths and enabled and session_path and not Path(session_path).exists():
            warnings.append(f"optional session path is not accessible: {session_path}")

    destinations = data.get("destinations")
    if not isinstance(destinations, list) or not destinations:
        errors.append("destinations must be a non-empty array")
        destinations = []
    destination_names: set[str] = set()
    enabled_destinations = 0
    for index, raw_destination in enumerate(destinations):
        label = f"destinations[{index}]"
        destination = require_object(raw_destination, label, errors)
        name = require_nonempty_string(destination.get("name"), f"{label}.name", errors)
        if name in destination_names:
            errors.append(f"duplicate destination name: {name}")
        destination_names.add(name)
        if destination.get("provider") != "google_drive":
            errors.append(f"{label}.provider must currently be 'google_drive'")
        enabled = destination.get("enabled")
        if not isinstance(enabled, bool):
            errors.append(f"{label}.enabled must be true or false")
        elif enabled:
            enabled_destinations += 1
        folder_url = require_nonempty_string(destination.get("folder_url"), f"{label}.folder_url", errors)
        if folder_url:
            parsed = urlparse(folder_url)
            if parsed.scheme != "https" or parsed.netloc != "drive.google.com" or not DRIVE_RE.fullmatch(parsed.path):
                errors.append(f"{label}.folder_url must be a Google Drive folder URL")
            if "REPLACE_WITH" in folder_url:
                errors.append(f"{label}.folder_url still contains a placeholder")
    if enabled_destinations == 0:
        errors.append("at least one destination must be enabled")

    privacy = require_object(data.get("privacy"), "privacy", errors)
    for key in ("mask_prompts", "mask_home_user", "exclude_secrets", "withhold_on_uncertainty"):
        if privacy.get(key) is not True:
            errors.append(f"privacy.{key} must be true")

    return errors, warnings


def schedule_rrule(schedule: dict) -> str:
    hour, minute = schedule["time"].split(":")
    days = ",".join(schedule["weekdays"])
    return f"RRULE:FREQ=WEEKLY;BYDAY={days};BYHOUR={int(hour)};BYMINUTE={int(minute)};BYSECOND=0"


def enabled(items: list[dict]) -> list[dict]:
    return [item for item in items if item.get("enabled")]


def render(data: dict, config_path: Path) -> dict:
    timezone = data["timezone"]
    sources = enabled(data["sources"])
    sessions = enabled(data.get("session_sources", []))
    destinations = enabled(data["destinations"])
    collection_schedule = data["automations"]["collection"]
    recovery_schedule = data["automations"]["recovery"]

    source_lines = "\n".join(
        f"- {item['name']}: {item['path']} | collect={','.join(item['collect'])} | from={item.get('from') or 'unbounded'} | until={item.get('until') or 'unbounded'}"
        for item in sources
    )
    destination_lines = "\n".join(f"- {item['name']}: {item['folder_url']}" for item in destinations)
    session_lines = "\n".join(
        f"- {item['agent']}: {item['path']} | format={item['format']}" for item in sessions
    ) or "- none"

    collector_script = SKILL_ROOT / "scripts" / "collect_git_history.py"
    shared_rules = f"""Configuration: {config_path}
Timezone: {timezone}

Enabled business sources:
{source_lines}

Enabled session sources (read-only; never upload raw logs):
{session_lines}

Enabled destinations:
{destination_lines}

Git author filter: {', '.join(data['git']['author_emails'])}

Collect only each source's configured categories. Organize artifacts by their actual work date under YYYY-MM-DD with a daily index, 프롬프트/<agent>, 문서/<source-relative path>, 코드/<repository>, and 기타 as applicable. Do not create empty category folders. Store code as date/repository patches and summaries rather than complete tracked source trees. For committed code, MUST run `{collector_script}` for the exact range and use its manifest as the source of truth. It scans `git log --all`, aggregates every unique commit before writing one repository/date patch and summary, and rejects count mismatches. Never replace this with a current-branch-only log or a per-commit overwrite loop. Reconcile manifest commit hashes and counts with every daily index before upload. Extract only human prompts demonstrably associated with an enabled business source. Never upload raw session logs, assistant/system/developer/tool content, internal reasoning, caches, build intermediates, environment files, certificates, keys, or credentials. Irreversibly mask personal data, home-directory usernames, and secrets, then perform a second privacy inspection and withhold uncertain exports. Never modify local source files or original session logs.

Treat destinations independently: inspect before writing, avoid duplicates by relative path/name/content, repair only missing items, continue after an isolated failure, and report overall success only when every enabled destination is synchronized. A normal no-change day still gets a date folder and daily index in every destination."""

    holiday_rule = (
        "Before writing, verify whether today is a public or substitute holiday in the configured locale; skip and report if it is."
        if collection_schedule.get("skip_public_holidays")
        else "Do not skip solely because today is a public holiday."
    )
    collection_prompt = f"""Run the normal work-report collection. {holiday_rule}

{shared_rules}

Use the last success common to all enabled destinations as the lower bound and the current run time as the upper bound. Apply each source's from/until bounds. Write completion state only after every required item is present in every enabled destination. Report per-destination links, upload/duplicate/masking/withholding/failure counts, and exact blockers."""

    recovery_holiday_rule = (
        "If today is a public or substitute holiday in the configured locale, make no changes and report that recovery was skipped."
        if recovery_schedule.get("skip_public_holidays")
        else "Do not skip solely because today is a public holiday."
    )
    recovery_prompt = f"""Run failure recovery for the normal work-report automation. {recovery_holiday_rule}

{shared_rules}

Set the upper bound to the previous day at 23:59:59 in {timezone}; never include same-day changes. Inspect every enabled destination and make no changes when all are complete through that bound. If any run is absent, partial, or failed, resume after the last success common to every enabled destination, apply each source's from/until bounds, and repair only missing items. Succeed only when all enabled destinations are synchronized through the recovery bound. Report per-destination links, upload/duplicate/masking/withholding/failure counts, and exact blockers."""

    return {
        "collection": {
            "id": collection_schedule["id"],
            "name": collection_schedule["name"],
            "enabled": collection_schedule["enabled"],
            "rrule": schedule_rrule(collection_schedule),
            "prompt": collection_prompt,
        },
        "recovery": {
            "id": recovery_schedule["id"],
            "name": recovery_schedule["name"],
            "enabled": recovery_schedule["enabled"],
            "rrule": schedule_rrule(recovery_schedule),
            "prompt": recovery_prompt,
        },
        "execution": data["execution"],
    }


def command_init(output: Path) -> int:
    if output.exists():
        print(f"refusing to overwrite existing configuration: {output}", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(EXAMPLE_CONFIG, output)
    print(output)
    return 0


def command_validate(config_path: Path, check_paths: bool) -> int:
    try:
        data = load_config(config_path)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    errors, warnings = validate_config(data, check_paths)
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"valid: {config_path}")
    return 0


def command_render(config_path: Path) -> int:
    try:
        data = load_config(config_path)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    errors, warnings = validate_config(data, False)
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(render(data, config_path.resolve()), ensure_ascii=False, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="copy the example configuration")
    init_parser.add_argument("--output", type=Path, default=DEFAULT_CONFIG)

    validate_parser = subparsers.add_parser("validate", help="validate configuration")
    validate_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    validate_parser.add_argument("--check-paths", action="store_true")

    render_parser = subparsers.add_parser("render", help="render automation prompts and schedules")
    render_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)

    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "init":
        return command_init(args.output.expanduser())
    if args.command == "validate":
        return command_validate(args.config.expanduser(), args.check_paths)
    if args.command == "render":
        return command_render(args.config.expanduser())
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
