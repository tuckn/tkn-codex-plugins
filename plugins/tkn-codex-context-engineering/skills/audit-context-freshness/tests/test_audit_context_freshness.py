from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

import audit_context_freshness as audit  # noqa: E402


class AuditContextFreshnessTests(unittest.TestCase):
    def test_writes_report_to_explicit_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "project-state"
            sessions = source / "sessions"
            sessions.mkdir(parents=True)
            (source / "working-context.md").write_text(
                "---\ntype: workingContext\nupdated: 2026-01-01T00:00:00+09:00\n---\n",
                encoding="utf-8",
            )
            (sessions / "session.md").write_text(
                "---\ntype: session\nupdated: 2026-01-01T00:00:00+09:00\n"
                "distillationStatus: pending\n---\n",
                encoding="utf-8",
            )
            reports = root / "reports"
            output = io.StringIO()

            with redirect_stdout(output):
                result = audit.main(
                    ["--source", str(source), "--report-dest", str(reports), "--write"]
                )

            self.assertEqual(0, result)
            self.assertIn("needs-review", output.getvalue())
            self.assertEqual(1, len(list(reports.glob("*.md"))))

    def test_dry_run_does_not_require_report_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            output = io.StringIO()
            with redirect_stdout(output):
                result = audit.main(["--source", str(source), "--dry-run"])
            self.assertEqual(0, result)
            self.assertIn("report-dest: not written", output.getvalue())


if __name__ == "__main__":
    unittest.main()
