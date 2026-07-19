from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
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

    def test_reports_fixture_schema_compatibility_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "project-state"
            decisions = source / "decisions"
            decisions.mkdir(parents=True)
            for fixture_name in ("decision-v1.md", "decision-v2.md", "decision-v99.md"):
                fixture_text = (FIXTURES / fixture_name).read_text(encoding="utf-8")
                if fixture_name == "decision-v2.md":
                    fixture_text = fixture_text.replace(
                        "promotionStatus: pending",
                        "promotionStatus: no-action",
                    ).replace(
                        "updated: 2026-02-02T10:00:00+09:00",
                        f"updated: {audit.now_iso()}",
                    )
                (decisions / fixture_name).write_text(fixture_text, encoding="utf-8")
            reports = root / "reports"

            with redirect_stdout(io.StringIO()):
                result = audit.main(
                    ["--source", str(source), "--report-dest", str(reports), "--write"]
                )

            self.assertEqual(0, result)
            report = next(reports.glob("*.md")).read_text(encoding="utf-8")
            self.assertIn("legacy-schema=1", report)
            self.assertIn("unsupported-schema=99", report)
            self.assertNotIn("| decisions/decision-v2.md |", report)


if __name__ == "__main__":
    unittest.main()
