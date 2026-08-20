#!/usr/bin/env python3
"""Sanitize staged human prompt exports and fail closed on residual risk."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


MACHINE_TAGS = {
    "app-context",
    "command-message",
    "command-name",
    "environment_context",
    "interrupted-output",
    "local-command-caveat",
    "local-command-stdout",
    "recommended_plugins",
    "skills_instructions",
    "task-notification",
    "turn_aborted",
}
SECTION_RE = re.compile(r"(?m)(^## .+$\n+)")
OPEN_TAG_RE = re.compile(r"^<([A-Za-z0-9_-]+)>")
HOME_RE = re.compile(r"/Users/[^/\s]+")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:01[016789][- .]?\d{3,4}[- .]?\d{4}|"
    r"0\d{1,2}[- .]?\d{3,4}[- .]?\d{4})(?![A-Za-z0-9])"
)
LABELED_SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|비밀번호|api[_-]?key|access[_-]?key|"
    r"secret|token|cookie|connection[_-]?string|아이디|로그인[_ -]?id|user(?:name)?[_ -]?id)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
RESIDUAL_MACHINE_RE = re.compile(
    r"<(?:(?:" + "|".join(re.escape(tag) for tag in sorted(MACHINE_TAGS)) + r"))>"
)


def mask(text: str) -> str:
    text = HOME_RE.sub("/Users/[USER_REDACTED]", text)
    text = EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    text = PHONE_RE.sub("[PHONE_REDACTED]", text)
    return LABELED_SECRET_RE.sub(
        lambda match: match.group(1) + match.group(2) + "[SECRET_REDACTED]", text
    )


def sanitize(text: str) -> tuple[str, int, int, int]:
    parts = SECTION_RE.split(text)
    header = mask(parts[0])
    kept: list[str] = []
    removed = 0
    unwrapped = 0
    for index in range(1, len(parts), 2):
        heading = parts[index]
        body = parts[index + 1] if index + 1 < len(parts) else ""
        match = OPEN_TAG_RE.match(body.lstrip())
        if match and match.group(1) in MACHINE_TAGS:
            removed += 1
            continue
        if match and match.group(1) == "USER_REQUEST":
            body = re.sub(r"^\s*<USER_REQUEST>\s*", "", body)
            body = re.sub(r"\s*</USER_REQUEST>\s*$", "\n", body)
            unwrapped += 1
        kept.append(heading + mask(body))
    return (header + "".join(kept)).rstrip() + "\n", removed, unwrapped, len(kept)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--from", dest="date_from", required=True)
    parser.add_argument("--until", dest="date_until", required=True)
    parser.add_argument("--check", action="store_true", help="inspect without rewriting")
    args = parser.parse_args()

    stats: dict[str, object] = {
        "files": 0,
        "changed_files": 0,
        "removed_machine_sections": 0,
        "unwrapped_user_sections": 0,
        "empty_after_filter": [],
        "residual_findings": [],
    }
    pattern = "20??-??-??/프롬프트/**/*.md"
    for path in sorted(args.root.glob(pattern)):
        date = path.relative_to(args.root).parts[0]
        if not args.date_from <= date <= args.date_until:
            continue
        original = path.read_text(encoding="utf-8", errors="replace")
        cleaned, removed, unwrapped, kept = sanitize(original)
        stats["files"] = int(stats["files"]) + 1
        stats["removed_machine_sections"] = int(stats["removed_machine_sections"]) + removed
        stats["unwrapped_user_sections"] = int(stats["unwrapped_user_sections"]) + unwrapped
        if kept == 0:
            cast = stats["empty_after_filter"]
            assert isinstance(cast, list)
            cast.append(str(path.relative_to(args.root)))
        findings = []
        if EMAIL_RE.search(cleaned):
            findings.append("email")
        if PHONE_RE.search(cleaned):
            findings.append("phone")
        if re.search(r"/Users/(?!\[USER_REDACTED\])[^/\s]+", cleaned):
            findings.append("home_user")
        if RESIDUAL_MACHINE_RE.search(cleaned):
            findings.append("machine_tag")
        if findings:
            cast = stats["residual_findings"]
            assert isinstance(cast, list)
            cast.append({"path": str(path.relative_to(args.root)), "types": findings})
        if cleaned != original:
            stats["changed_files"] = int(stats["changed_files"]) + 1
            if not args.check:
                path.write_text(cleaned, encoding="utf-8")

    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))
    return 2 if stats["empty_after_filter"] or stats["residual_findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
