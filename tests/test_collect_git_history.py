import csv
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from collect_git_history import (
    CommitCsvEntry,
    configured_repositories,
    conventional_parts,
    write_daily_commit_csv,
)


class DailyCommitCsvTest(unittest.TestCase):
    def init_repository(self, path):
        path.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
        (path / "README.md").write_text("test\n")
        subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True)

    def test_nested_worktrees_with_same_basename_get_unique_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "rail-worktrees"
            for feature in ("risk-eval", "before-work"):
                repository = source / feature / "frontend"
                self.init_repository(repository)

            config = {
                "sources": [{
                    "name": "rail-worktrees",
                    "path": str(source),
                    "enabled": True,
                    "collect": ["code"],
                    "from": "2025-12-18",
                    "until": None,
                }]
            }
            repositories = configured_repositories(config)

            self.assertEqual(
                [repo.label for repo in repositories],
                [
                    "rail-worktrees__before-work__frontend",
                    "rail-worktrees__risk-eval__frontend",
                ],
            )

    def test_linked_worktree_history_is_collected_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "rail-project" / "frontend"
            worktree = root / "rail-worktrees" / "feature" / "frontend"
            self.init_repository(main)
            worktree.parent.mkdir(parents=True)
            subprocess.run(
                ["git", "-C", str(main), "worktree", "add", "-qb", "feature/test", str(worktree)],
                check=True,
            )
            config = {
                "sources": [
                    {
                        "name": "rail-project",
                        "path": str(main.parent),
                        "enabled": True,
                        "collect": ["code"],
                    },
                    {
                        "name": "rail-worktrees",
                        "path": str(root / "rail-worktrees"),
                        "enabled": True,
                        "collect": ["code"],
                    },
                ]
            }

            repositories = configured_repositories(config)

            self.assertEqual(len(repositories), 1)
            self.assertEqual(repositories[0].root, main.resolve())

    def test_conventional_subject_parts(self):
        self.assertEqual(conventional_parts("feat(ui): 목록을 개선한다"), ("feat", "ui"))
        self.assertEqual(conventional_parts("fix!: 호환성을 변경한다"), ("fix", ""))
        self.assertEqual(conventional_parts("일반 커밋 제목"), ("", ""))

    def test_writes_bom_rows_merge_and_duplicate_repository(self):
        shared_oid = "a" * 40
        entries = [
            CommitCsvEntry(
                "2026-08-19", "10:10", "backend", ("feature/report",), shared_oid,
                "feat(report): CSV를 추가한다", 2, 10, 1, False,
            ),
            CommitCsvEntry(
                "2026-08-19", "10:11", "frontend", ("feature/report",), shared_oid,
                "feat(report): CSV를 추가한다", 2, 10, 1, False,
            ),
            CommitCsvEntry(
                "2026-08-19", "10:12", "frontend", ("dev",), "b" * 40,
                "Merge branch 'feature/report' into dev", None, None, None, True,
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_rows = write_daily_commit_csv(root, entries)
            path = root / "2026-08-19" / "코드" / "commits.csv"
            data = path.read_bytes()

            self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(manifest_rows[0]["row_count"], 3)
            self.assertEqual(manifest_rows[0]["sha256"], hashlib.sha256(data).hexdigest())

            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["타입"], "feat")
            self.assertEqual(rows[0]["영역"], "report")
            self.assertEqual(rows[0]["동일커밋 존재 저장소"], "frontend")
            self.assertEqual(rows[1]["동일커밋 존재 저장소"], "backend")
            self.assertEqual(rows[2]["머지"], "Y")
            self.assertEqual(rows[2]["파일수"], "")
            self.assertEqual(rows[2]["추가"], "")
            self.assertEqual(rows[2]["삭제"], "")


if __name__ == "__main__":
    unittest.main()
