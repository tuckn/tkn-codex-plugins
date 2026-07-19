from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPT_ROOT))

import write_global_working_context as portfolio  # noqa: E402


FIXED_NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=portfolio.JST)


class WriteGlobalWorkingContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = self.root / "store"
        (self.store / "state").mkdir(parents=True)
        self.records: list[dict[str, object]] = []

    def tearDown(self) -> None:
        self.temp.cleanup()

    def fixture(self, name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    def add_project(
        self,
        *,
        project_id: str,
        title: str,
        text: str | None,
        status: str = "active",
    ) -> None:
        self.records.append(
            {
                "workspaceId": f"ws_{project_id}",
                "projectId": project_id,
                "title": title,
                "currentRoot": f"C:/Users/ExampleUser/Projects/{project_id}",
                "workingContextPath": (
                    f"C:/Users/ExampleUser/PrivateContext/{project_id}/working-context.md"
                ),
                "status": status,
            }
        )
        if text is not None:
            project_state = self.store / "state" / project_id
            project_state.mkdir()
            (project_state / "working-context.md").write_text(text, encoding="utf-8")

    def write_registry(self) -> None:
        registry = self.store / "state" / "index.jsonl"
        registry.write_text(
            "\n".join(json.dumps(record) for record in self.records) + "\n",
            encoding="utf-8",
        )

    def run_main(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        with patch.object(portfolio, "current_time", return_value=FIXED_NOW):
            with redirect_stdout(output):
                result = portfolio.main(list(args))
        return result, output.getvalue()

    def test_writes_portfolio_from_unversioned_v1_and_v2(self) -> None:
        legacy_id = "20260114_legacy_project_abcd1234"
        current_id = "20260203_current_project_ijkl9012"
        legacy = self.fixture("working-context-v1-unversioned.md").replace(
            "20260114_example_project_abcd1234",
            legacy_id,
        )
        current = self.fixture("working-context-v2.md").replace(
            "20260203_example_project_ijkl9012",
            current_id,
        )
        self.add_project(
            project_id=legacy_id,
            title="Legacy Project",
            text=legacy,
        )
        self.add_project(
            project_id=current_id,
            title="Current Project",
            text=current,
        )
        hidden_session = self.store / "state" / current_id / "sessions"
        hidden_session.mkdir()
        (hidden_session / "private.md").write_text(
            "This session body must not be aggregated.",
            encoding="utf-8",
        )
        self.write_registry()
        destination = self.root / "portfolio" / "working-context.md"

        result, output = self.run_main(
            "--source",
            str(self.store),
            "--dest",
            str(destination),
            "--stale-days",
            "999",
            "--write",
        )

        self.assertEqual(0, result)
        self.assertIn("registered-projects: 2", output)
        rendered = destination.read_text(encoding="utf-8")
        self.assertIn("type: \"globalWorkingContext\"", rendered)
        self.assertIn("schemaVersion: 1", rendered)
        self.assertIn("sourceProjectCount: 2", rendered)
        self.assertIn("includedProjectCount: 2", rendered)
        self.assertIn("Legacy Unversioned Working Context", rendered)
        self.assertIn("Current V2 Working Context", rendered)
        self.assertIn("legacy schema v1", rendered)
        self.assertIn(f"`state:/{legacy_id}/working-context.md`", rendered)
        self.assertNotIn("C:/Users/ExampleUser", rendered)
        self.assertNotIn("This session body must not be aggregated.", rendered)

    def test_classifies_blocked_paused_and_dependencies(self) -> None:
        blocked_id = "20260203_blocked_project_abcd1234"
        paused_id = "20260203_paused_project_efgh5678"
        blocked = (
            self.fixture("working-context-v2.md")
            .replace("20260203_example_project_ijkl9012", blocked_id)
            .replace("title: Current V2 Working Context", "title: Blocked Project")
            .replace("blocked: false", "blocked: true")
            .replace('mainBlocker: ""', 'mainBlocker: "Waiting for an external dependency."')
        )
        paused = (
            self.fixture("working-context-v2.md")
            .replace("20260203_example_project_ijkl9012", paused_id)
            .replace("title: Current V2 Working Context", "title: Paused Project")
            .replace("projectStatus: active", "projectStatus: paused")
            .replace(
                "dependencyProjectIds: []",
                f'dependencyProjectIds:\n  - "{blocked_id}"',
            )
        )
        self.add_project(project_id=blocked_id, title="Blocked Project", text=blocked)
        self.add_project(project_id=paused_id, title="Paused Project", text=paused)
        self.write_registry()

        with patch.object(portfolio, "current_time", return_value=FIXED_NOW):
            args = portfolio.build_parser().parse_args(
                ["--source", str(self.store), "--stale-days", "999"]
            )
            _, rendered = portfolio.build_portfolio(args)

        blocked_section = rendered.split("## Blocked Projects", 1)[1].split(
            "## Active Projects", 1
        )[0]
        paused_section = rendered.split("## Paused Projects", 1)[1].split(
            "## Completed Projects", 1
        )[0]
        self.assertIn("Blocked Project", blocked_section)
        self.assertIn("Paused Project", paused_section)
        self.assertIn("Paused Project -> Blocked Project", rendered)
        self.assertIn("Waiting for an external dependency.", rendered)
        self.assertIn("blockedProjectCount: 1", rendered)

    def test_missing_working_context_is_a_review_item(self) -> None:
        project_id = "20260719_missing_project_abcd1234"
        self.add_project(
            project_id=project_id,
            title="Missing Project",
            text=None,
        )
        self.write_registry()

        with patch.object(portfolio, "current_time", return_value=FIXED_NOW):
            args = portfolio.build_parser().parse_args(["--source", str(self.store)])
            _, rendered = portfolio.build_portfolio(args)

        self.assertIn("Included working contexts: 0", rendered)
        self.assertIn("Missing Project", rendered)
        self.assertIn("missing working context", rendered)
        self.assertIn(
            "Review or recreate the missing project working context.",
            rendered,
        )

    def test_rejects_unsupported_schema_without_changing_destination(self) -> None:
        project_id = "20260719_future_project_abcd1234"
        self.add_project(
            project_id=project_id,
            title="Future Project",
            text=self.fixture("working-context-v99.md"),
        )
        self.write_registry()
        destination = self.root / "working-context.md"
        destination.write_text("preserve me\n", encoding="utf-8")

        with self.assertRaisesRegex(
            SystemExit,
            "Unsupported working context state:/20260719_future_project_abcd1234/"
            "working-context.md schemaVersion: 99",
        ):
            self.run_main(
                "--source",
                str(self.store),
                "--dest",
                str(destination),
                "--write",
            )

        self.assertEqual("preserve me\n", destination.read_text(encoding="utf-8"))

    def test_write_requires_explicit_destination(self) -> None:
        self.write_registry()
        with self.assertRaisesRegex(
            SystemExit,
            "write-global-working-context requires --dest",
        ):
            self.run_main("--source", str(self.store), "--write")

    def test_refuses_to_overwrite_project_working_context(self) -> None:
        project_id = "20260203_current_project_ijkl9012"
        current = self.fixture("working-context-v2.md").replace(
            "20260203_example_project_ijkl9012",
            project_id,
        )
        self.add_project(
            project_id=project_id,
            title="Current Project",
            text=current,
        )
        self.write_registry()
        destination = self.store / "state" / project_id / "working-context.md"

        with self.assertRaisesRegex(
            SystemExit,
            "Destination must not overwrite",
        ):
            self.run_main(
                "--source",
                str(self.store),
                "--dest",
                str(destination),
                "--write",
            )

        self.assertEqual(current, destination.read_text(encoding="utf-8"))

    def test_dry_run_without_destination_is_read_only(self) -> None:
        self.write_registry()

        result, output = self.run_main("--source", str(self.store), "--dry-run")

        self.assertEqual(0, result)
        self.assertIn("mode: dry-run", output)
        self.assertIn("destination: not written", output)
        self.assertEqual(
            [self.store / "state" / "index.jsonl"],
            list(self.store.rglob("*.*")),
        )


if __name__ == "__main__":
    unittest.main()
