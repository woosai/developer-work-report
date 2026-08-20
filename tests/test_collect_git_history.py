import csv
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from collect_git_history import CommitCsvEntry, conventional_parts, write_daily_commit_csv


class DailyCommitCsvTest(unittest.TestCase):
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
