#!/usr/bin/env python3
"""Collect complete, date-grouped Git history from configured work-report sources."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from developer_work_report_config import DEFAULT_CONFIG, ConfigError, load_config, validate_config


EXCLUDED_DIRS = {
    ".cache", ".gradle", ".idea", ".next", ".nuxt", ".output", ".venv",
    "build", "coverage", "dist", "node_modules", "target", "vendor",
}
EMAIL_RE = re.compile(r"(?<![\w.+-])([\w.+-]+)@([\w-]+(?:\.[\w-]+)+)")
HOME_RE = re.compile(r"/Users/[^/\s]+")
SECRET_RE = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|secret)\b"
    r"\s*[:=]\s*)([^\s,;]+)"
)


class CollectionError(Exception):
    pass


@dataclass(frozen=True)
class Commit:
    oid: str
    committed_at: str
    work_date: str
    work_time: str
    author: str
    email: str
    subject: str


@dataclass(frozen=True)
class Repository:
    source_name: str
    root: Path
    label: str
    source_from: date | None
    source_until: date | None


@dataclass(frozen=True)
class CommitCsvEntry:
    work_date: str
    work_time: str
    repository: str
    branches: tuple[str, ...]
    oid: str
    subject: str
    file_count: int | None
    additions: int | None
    deletions: int | None
    is_merge: bool


def run_git(repo: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", "-C", os.fspath(repo), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode:
        raise CollectionError(
            f"git failed in {repo}: git {' '.join(args)}\n{process.stderr.strip()}"
        )
    return process.stdout


def parse_optional_date(value: object) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) else None


def discover_git_roots(source_path: Path) -> list[Path]:
    roots: set[Path] = set()
    if (source_path / ".git").exists():
        roots.add(source_path.resolve())
    for current, dirs, _files in os.walk(source_path):
        dirs[:] = [item for item in dirs if item not in EXCLUDED_DIRS and item != ".git"]
        current_path = Path(current)
        if current_path != source_path and (current_path / ".git").exists():
            roots.add(current_path.resolve())
            dirs[:] = []
    return sorted(roots, key=lambda item: os.fspath(item))


def configured_repositories(config: dict) -> list[Repository]:
    raw: list[tuple[str, Path, date | None, date | None]] = []
    for source in config["sources"]:
        if not source.get("enabled") or "code" not in source.get("collect", []):
            continue
        source_path = Path(source["path"]).expanduser()
        for root in discover_git_roots(source_path):
            raw.append((source["name"], root, parse_optional_date(source.get("from")), parse_optional_date(source.get("until"))))

    basename_counts: dict[str, int] = defaultdict(int)
    for _source_name, root, _start, _end in raw:
        basename_counts[root.name] += 1

    repositories: list[Repository] = []
    for source_name, root, source_from, source_until in raw:
        label = root.name if basename_counts[root.name] == 1 else f"{source_name}__{root.name}"
        repositories.append(Repository(source_name, root, label, source_from, source_until))
    return repositories


def mask_text(text: str) -> str:
    text = EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    text = HOME_RE.sub("/Users/[USER_REDACTED]", text)
    return SECRET_RE.sub(r"\1[SECRET_REDACTED]", text)


def commits_for_repo(repo: Repository, timezone: ZoneInfo, author_emails: set[str]) -> list[Commit]:
    # --all is mandatory: current-branch-only collection silently loses work.
    raw = run_git(
        repo.root,
        "log", "--all", "--no-color", "--date=iso-strict",
        "--format=%H%x00%cI%x00%an%x00%ae%x00%s%x1e",
    )
    commits: list[Commit] = []
    seen: set[str] = set()
    for record in raw.split("\x1e"):
        record = record.strip("\r\n")
        if not record:
            continue
        fields = record.split("\x00", 4)
        if len(fields) != 5:
            raise CollectionError(f"could not parse git log record in {repo.root}")
        oid, committed_at, author, email, subject = fields
        if oid in seen:
            continue
        seen.add(oid)
        if email.lower() not in author_emails:
            continue
        parseable_time = committed_at[:-1] + "+00:00" if committed_at.endswith("Z") else committed_at
        instant = datetime.fromisoformat(parseable_time).astimezone(timezone)
        commits.append(
            Commit(
                oid,
                committed_at,
                instant.date().isoformat(),
                instant.strftime("%H:%M"),
                author,
                email,
                subject,
            )
        )
    return commits


def branch_membership(repo: Repository, commits: list[Commit]) -> dict[str, tuple[str, ...]]:
    """Return current local/remote branch refs containing each selected commit.

    Git commits do not record the branch on which they were created. These values
    therefore describe current reachability, not historical authorship.
    """
    if not commits:
        return {}
    selected = {commit.oid for commit in commits}
    membership: dict[str, dict[str, tuple[int, bool]]] = {oid: {} for oid in selected}
    raw_refs = run_git(
        repo.root,
        "for-each-ref",
        "--format=%(refname:short)%00%(refname)",
        "refs/heads",
        "refs/remotes",
    )
    for line in raw_refs.splitlines():
        if "\x00" not in line:
            continue
        short_name, full_name = line.split("\x00", 1)
        if full_name.endswith("/HEAD"):
            continue
        is_remote = full_name.startswith("refs/remotes/")
        for distance, oid in enumerate(run_git(repo.root, "rev-list", full_name).splitlines()):
            if oid in selected:
                membership[oid][mask_text(short_name)] = (distance, is_remote)

    result: dict[str, tuple[str, ...]] = {}
    for oid, candidates in membership.items():
        if not candidates:
            result[oid] = ()
            continue
        closest_distance = min(value[0] for value in candidates.values())
        closest = {
            name: value for name, value in candidates.items() if value[0] == closest_distance
        }
        local_names = {name for name, (_distance, is_remote) in closest.items() if not is_remote}
        names = []
        for name, (_distance, is_remote) in closest.items():
            remote_tail = name.split("/", 1)[1] if is_remote and "/" in name else name
            if is_remote and remote_tail in local_names:
                continue
            names.append(name)
        result[oid] = tuple(sorted(names))
    return result


def commit_patch(repo: Repository, oid: str) -> str:
    return run_git(
        repo.root,
        "show", "--no-color", "--no-ext-diff", "--find-renames",
        "--format=fuller", oid,
    ).rstrip() + "\n"


def commit_name_status(repo: Repository, oid: str) -> str:
    return run_git(
        repo.root,
        "show", "--no-color", "--no-ext-diff", "--find-renames",
        "--format=", "--name-status", oid,
    ).strip()


def commit_parent_count(repo: Repository, oid: str) -> int:
    line = run_git(repo.root, "rev-list", "--parents", "-n", "1", oid).strip()
    return max(0, len(line.split()) - 1)


def commit_numstat(repo: Repository, oid: str) -> tuple[int, int, int]:
    raw = run_git(
        repo.root,
        "show", "--no-color", "--no-ext-diff", "--find-renames",
        "--format=", "--numstat", oid,
    )
    file_count = additions = deletions = 0
    for line in raw.splitlines():
        fields = line.split("\t", 2)
        if len(fields) != 3:
            continue
        file_count += 1
        if fields[0].isdigit():
            additions += int(fields[0])
        if fields[1].isdigit():
            deletions += int(fields[1])
    return file_count, additions, deletions


CONVENTIONAL_SUBJECT_RE = re.compile(
    r"^(?P<type>[A-Za-z][A-Za-z0-9_-]*)(?:\((?P<scope>[^)]+)\))?!?:\s+.+$"
)


def conventional_parts(subject: str) -> tuple[str, str]:
    match = CONVENTIONAL_SUBJECT_RE.match(subject)
    if not match:
        return "", ""
    return match.group("type"), match.group("scope") or ""


def csv_entry(
    repo: Repository,
    commit: Commit,
    branches: tuple[str, ...],
) -> CommitCsvEntry:
    is_merge = commit_parent_count(repo, commit.oid) > 1
    if is_merge:
        file_count = additions = deletions = None
    else:
        file_count, additions, deletions = commit_numstat(repo, commit.oid)
    return CommitCsvEntry(
        work_date=commit.work_date,
        work_time=commit.work_time,
        repository=mask_text(repo.label),
        branches=branches,
        oid=commit.oid,
        subject=mask_text(commit.subject),
        file_count=file_count,
        additions=additions,
        deletions=deletions,
        is_merge=is_merge,
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_daily_commit_csv(output: Path, entries: list[CommitCsvEntry]) -> list[dict]:
    by_date: dict[str, list[CommitCsvEntry]] = defaultdict(list)
    repositories_by_oid: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        by_date[entry.work_date].append(entry)
        repositories_by_oid[entry.oid].add(entry.repository)

    results: list[dict] = []
    header = [
        "시각", "저장소", "브랜치", "커밋", "타입", "영역", "제목",
        "파일수", "추가", "삭제", "머지", "동일커밋 존재 저장소",
    ]
    for work_date in sorted(by_date):
        target = output / work_date / "코드" / "commits.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        date_entries = sorted(
            by_date[work_date],
            key=lambda item: (item.work_time, item.repository, item.oid),
        )
        for entry in date_entries:
            commit_type, scope = conventional_parts(entry.subject)
            duplicates = sorted(repositories_by_oid[entry.oid] - {entry.repository})
            writer.writerow([
                entry.work_time,
                entry.repository,
                " | ".join(entry.branches),
                entry.oid[:10],
                commit_type,
                scope,
                entry.subject,
                "" if entry.file_count is None else entry.file_count,
                "" if entry.additions is None else entry.additions,
                "" if entry.deletions is None else entry.deletions,
                "Y" if entry.is_merge else "",
                " | ".join(duplicates),
            ])
        data = b"\xef\xbb\xbf" + stream.getvalue().encode("utf-8")
        target.write_bytes(data)
        results.append({
            "date": work_date,
            "path": os.fspath(target.relative_to(output)),
            "row_count": len(date_entries),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    if sum(item["row_count"] for item in results) != len(entries):
        raise CollectionError("daily commits.csv reconciliation failed")
    return results


def validate_occurrences(text: str, commits: list[Commit], label: str, kind: str) -> None:
    def count(commit: Commit) -> int:
        if kind == "patch":
            pattern = rf"^commit {re.escape(commit.oid)}$"
        else:
            pattern = rf"^### `{re.escape(commit.oid)}`"
        return len(re.findall(pattern, text, flags=re.MULTILINE))

    failures = [(commit.oid, count(commit)) for commit in commits if count(commit) != 1]
    if failures:
        detail = ", ".join(f"{oid}:{count}" for oid, count in failures[:10])
        raise CollectionError(f"{label} commit reconciliation failed ({detail})")


def write_group(output: Path, repo: Repository, work_date: str, commits: list[Commit]) -> dict:
    target = output / work_date / "코드" / repo.label
    target.mkdir(parents=True, exist_ok=True)
    patch_path = target / f"{repo.label}_{work_date}.patch"
    summary_path = target / f"{repo.label}_{work_date}_변경요약.md"

    patch_parts = [commit_patch(repo, commit.oid) for commit in commits]
    patch_text = mask_text("\n".join(patch_parts))

    summary_lines = [
        f"# {repo.label} — {work_date}", "",
        f"- 저장소: `{repo.root}`", f"- 소스: `{repo.source_name}`",
        f"- 커밋 수: **{len(commits)}**", "- 범위: `git log --all`의 모든 참조", "",
        "## 커밋", "",
    ]
    for commit in commits:
        status = commit_name_status(repo, commit.oid)
        summary_lines.extend([
            f"### `{commit.oid}` {mask_text(commit.subject)}", "",
            f"- 커밋 시각: {commit.committed_at}",
            f"- 작성자: {mask_text(commit.author)} <[EMAIL_REDACTED]>", "",
            "```text", mask_text(status) if status else "(변경 파일 없음)", "```", "",
        ])
    summary_text = "\n".join(summary_lines).rstrip() + "\n"

    # Files are written only after the complete date group exists in memory.
    # A mismatch aborts before any manifest can declare the group complete.
    validate_occurrences(patch_text, commits, f"{repo.label}/{work_date} patch", "patch")
    validate_occurrences(summary_text, commits, f"{repo.label}/{work_date} summary", "summary")
    patch_path.write_text(patch_text, encoding="utf-8")
    summary_path.write_text(summary_text, encoding="utf-8")
    return {
        "date": work_date,
        "source": repo.source_name,
        "repository": repo.label,
        "repository_path": mask_text(os.fspath(repo.root)),
        "commit_count": len(commits),
        "commits": [commit.oid for commit in commits],
        "patch": os.fspath(patch_path.relative_to(output)),
        "patch_sha256": sha256_text(patch_text),
        "summary": os.fspath(summary_path.relative_to(output)),
        "summary_sha256": sha256_text(summary_text),
    }


def collect(config_path: Path, output: Path, requested_from: date | None, requested_until: date | None) -> dict:
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        raise CollectionError(str(exc)) from exc
    errors, warnings = validate_config(config, True)
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if errors:
        raise CollectionError("invalid configuration:\n" + "\n".join(errors))

    timezone = ZoneInfo(config["timezone"])
    repositories = configured_repositories(config)
    author_emails = {email.lower() for email in config["git"]["author_emails"]}
    groups: list[dict] = []
    csv_entries: list[CommitCsvEntry] = []
    selected_total = 0
    for repo in repositories:
        by_date: dict[str, list[Commit]] = defaultdict(list)
        lower = max(item for item in (repo.source_from, requested_from) if item is not None) if (repo.source_from or requested_from) else None
        upper = min(item for item in (repo.source_until, requested_until) if item is not None) if (repo.source_until or requested_until) else None
        if lower and upper and lower > upper:
            continue
        selected_commits: list[Commit] = []
        for commit in commits_for_repo(repo, timezone, author_emails):
            commit_date = date.fromisoformat(commit.work_date)
            if lower and commit_date < lower:
                continue
            if upper and commit_date > upper:
                continue
            selected_commits.append(commit)
            by_date[commit.work_date].append(commit)
        branches = branch_membership(repo, selected_commits)
        for work_date in sorted(by_date):
            commits = sorted(by_date[work_date], key=lambda item: (item.committed_at, item.oid))
            selected_total += len(commits)
            groups.append(write_group(output, repo, work_date, commits))
            csv_entries.extend(
                csv_entry(repo, commit, branches.get(commit.oid, ())) for commit in commits
            )

    daily_commit_csv = write_daily_commit_csv(output, csv_entries)

    manifest = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone).isoformat(),
        "timezone": config["timezone"],
        "requested_from": requested_from.isoformat() if requested_from else None,
        "requested_until": requested_until.isoformat() if requested_until else None,
        "repository_count": len(repositories),
        "author_filter_count": len(author_emails),
        "group_count": len(groups),
        "commit_count": selected_total,
        "daily_commit_csv": daily_commit_csv,
        "groups": groups,
    }
    if sum(group["commit_count"] for group in groups) != selected_total:
        raise CollectionError("global commit reconciliation failed")
    manifest_path = output / "git-collection-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--from", dest="date_from", type=date.fromisoformat)
    result.add_argument("--until", dest="date_until", type=date.fromisoformat)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        manifest = collect(
            args.config.expanduser(), args.output.expanduser(), args.date_from, args.date_until
        )
    except CollectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({key: manifest[key] for key in ("repository_count", "group_count", "commit_count")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
