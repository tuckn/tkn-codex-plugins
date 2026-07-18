from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

import distill_session_context as distill  # noqa: E402


class DistillSessionContextTests(unittest.TestCase):
    def test_distills_and_finalizes_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            session = root / "session.md"
            session.write_text(
                "---\n"
                "type: session\n"
                "title: Example Session\n"
                "date: 2026-01-01T00:00:00+09:00\n"
                "updated: 2026-01-01T00:00:00+09:00\n"
                "distillationStatus: pending\n"
                "distilledTo: []\n"
                "---\n\n"
                "# Example Session\n\n"
                "## Important decisions\n\n- Keep the new layout.\n",
                encoding="utf-8",
            )
            candidates = root / "candidates"

            with redirect_stdout(io.StringIO()):
                result = distill.main(
                    ["--session", str(session), "--dest", str(candidates), "--write"]
                )
            self.assertEqual(0, result)
            candidate = next(candidates.glob("*.md"))
            self.assertIn("Keep the new layout", candidate.read_text(encoding="utf-8"))

            ref = f"candidates/{candidate.name}"
            with redirect_stdout(io.StringIO()):
                result = distill.finalize_main(
                    [
                        "--session",
                        str(session),
                        "--status",
                        "distilled",
                        "--distilled-to",
                        ref,
                        "--write",
                    ]
                )
            self.assertEqual(0, result)
            finalized = session.read_text(encoding="utf-8")
            self.assertIn("type: session\nschemaVersion: 1\n", finalized)
            self.assertIn('distillationStatus: "distilled"', finalized)
            self.assertIn(ref, finalized)

    def test_distill_requires_explicit_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            session = Path(temp) / "session.md"
            session.write_text("---\ntype: session\n---\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "requires --dest"):
                distill.main(["--session", str(session), "--dry-run"])

    def test_rejects_unknown_session_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            session = root / "session.md"
            original = "---\ntype: session\nschemaVersion: 99\n---\n"
            session.write_text(original, encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "Unsupported session note schemaVersion: 99"):
                distill.finalize_main(
                    [
                        "--session",
                        str(session),
                        "--status",
                        "no-action",
                        "--write",
                    ]
                )

            self.assertEqual(original, session.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
