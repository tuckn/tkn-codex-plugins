from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

import context_bridge as bridge  # noqa: E402


class ContextBridgeIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.env = patch.dict(
            os.environ,
            {"HOME": str(self.home), "USERPROFILE": str(self.home)},
        )
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.temp.cleanup()

    def run_main(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            result = bridge.main(list(args))
        return result, output.getvalue()

    def create_flat_store(self, name: str = "flat-store") -> tuple[Path, str]:
        store = self.root / name
        project_id = "20260101_example_abcd1234"
        (store / "decisions").mkdir(parents=True)
        (store / "decisions" / "DR-G-example.md").write_text("legacy decision\n")
        (store / "working-context.md").write_text(
            "# Global Context\n\n- Global Codex context is stored in `~/.codex-context`.\n"
        )
        (store / "README.md").write_text("# Legacy layout\n")
        project = store / "projects" / project_id
        (project / "sessions").mkdir(parents=True)
        (project / "sessions" / "session.md").write_text("legacy session\n")
        (project / "working-context.md").write_text("# Project context\n")
        record = {
            "workspaceId": "ws_legacy",
            "projectId": project_id,
            "currentRoot": "C:/path/to/project",
            "projectContextPath": (store / "projects" / project_id).as_posix(),
            "workingContextPath": (project / "working-context.md").as_posix(),
            "sessionsPath": (project / "sessions").as_posix(),
            "decisionsPath": (project / "decisions").as_posix(),
        }
        (store / "projects" / "index.jsonl").write_text(json.dumps(record) + "\n")
        return store, project_id

    def test_init_creates_exact_versioned_layout(self) -> None:
        store = self.root / "store"

        result, output = self.run_main("init", "--target", str(store), "--write")

        self.assertEqual(0, result)
        self.assertIn("mode: write", output)
        self.assertEqual("schemaVersion: 1\n", (store / "config" / "config.yaml").read_text())
        self.assertTrue((store / "data" / "working-context.md").is_file())
        self.assertTrue((store / "state" / "index.jsonl").is_file())
        for folder in bridge.DATA_CONTEXT_DIRS:
            self.assertTrue((store / "data" / folder).is_dir())
        self.assertFalse((store / "data" / "promoted").exists())
        self.assertTrue((store / "README.md").is_file())

    def test_init_project_creates_marker_registry_and_state(self) -> None:
        store = self.root / "store"
        repo = self.root / "example-repo"
        repo.mkdir()

        result, _ = self.run_main(
            "init-project",
            "--target",
            str(store),
            "--repo-root",
            str(repo),
            "--write",
        )

        self.assertEqual(0, result)
        marker = repo / ".tkn" / "codex-context.yaml"
        self.assertTrue(marker.is_file())
        project_id = bridge.yaml_value(marker.read_text(), "projectId")
        project_state = store / "state" / project_id
        self.assertTrue((project_state / "working-context.md").is_file())
        for folder in bridge.PROJECT_STATE_DIRS:
            self.assertTrue((project_state / folder).is_dir())
        records = bridge.read_jsonl(store / "state" / "index.jsonl", bridge.Result())
        self.assertEqual(1, len(records))
        self.assertEqual((project_state / "memos").as_posix(), records[0]["memosPath"])

        _, second_output = self.run_main(
            "init-project",
            "--target",
            str(store),
            "--repo-root",
            str(repo),
            "--write",
        )
        second_marker = marker.read_text()
        self.assertEqual(project_id, bridge.yaml_value(second_marker, "projectId"))
        self.assertIn("reuse-workspace", second_output)

    def test_init_project_dry_run_and_deprecated_alias(self) -> None:
        store = self.root / "store"
        repo = self.root / "repo"
        repo.mkdir()

        _, dry_output = self.run_main(
            "init-project",
            "--target",
            str(store),
            "--repo-root",
            str(repo),
            "--dry-run",
        )
        self.assertIn("mode: dry-run", dry_output)
        self.assertFalse(store.exists())
        self.assertFalse((repo / ".tkn").exists())

        _, alias_output = self.run_main(
            "register-project",
            "--target",
            str(store),
            "--repo-root",
            str(repo),
            "--write",
        )
        self.assertIn("register-project is deprecated; use init-project", alias_output)
        self.assertTrue((repo / ".tkn" / "codex-context.yaml").exists())

    def test_init_project_reuses_identity_for_move_but_not_live_copy(self) -> None:
        store = self.root / "store"
        original = self.root / "original"
        original.mkdir()
        self.run_main(
            "init-project",
            "--target",
            str(store),
            "--repo-root",
            str(original),
            "--write",
        )
        original_marker = original / ".tkn" / "codex-context.yaml"
        original_id = bridge.yaml_value(original_marker.read_text(), "projectId")
        original_record = bridge.read_jsonl(store / "state" / "index.jsonl", bridge.Result())[0]

        copied = self.root / "copied"
        copied.mkdir()
        (copied / ".tkn").mkdir()
        (copied / ".tkn" / "codex-context.yaml").write_text(original_marker.read_text())
        self.run_main(
            "init-project",
            "--target",
            str(store),
            "--repo-root",
            str(copied),
            "--write",
        )
        copied_id = bridge.yaml_value((copied / ".tkn" / "codex-context.yaml").read_text(), "projectId")
        self.assertNotEqual(original_id, copied_id)

        moved = self.root / "moved"
        original.rename(moved)
        self.run_main(
            "init-project",
            "--target",
            str(store),
            "--repo-root",
            str(moved),
            "--write",
        )
        moved_id = bridge.yaml_value((moved / ".tkn" / "codex-context.yaml").read_text(), "projectId")
        moved_records = bridge.read_jsonl(store / "state" / "index.jsonl", bridge.Result())
        moved_record = next(record for record in moved_records if record["projectId"] == moved_id)
        self.assertEqual(original_id, moved_id)
        self.assertEqual(original_record["workspaceId"], moved_record["workspaceId"])

    def test_init_project_preserves_legacy_identity_and_files(self) -> None:
        repo = self.root / "repo"
        repo.mkdir()
        old_marker = repo / ".codex-context" / "project.yaml"
        old_marker.parent.mkdir()
        old_marker.write_text(
            'projectId: "20260101_example_abcd1234"\n'
            'title: "Example"\n'
            'description: ""\n'
            "createdAt: 2026-01-01T00:00:00+09:00\n"
            "updatedAt: 2026-01-01T00:00:00+09:00\n",
            encoding="utf-8",
        )
        legacy_root = self.home / ".codex-context"
        legacy_project = legacy_root / "projects" / "20260101_example_abcd1234"
        (legacy_project / "sessions").mkdir(parents=True)
        (legacy_project / "sessions" / "session.md").write_text("legacy session\n")
        (legacy_project / "working-context.md").write_text("# Legacy working context\n")
        record = {
            "workspaceId": "ws_legacy",
            "projectId": "20260101_example_abcd1234",
            "repoId": "repo_legacy",
            "title": "Example",
            "currentRoot": repo.as_posix(),
        }
        (legacy_root / "projects" / "index.jsonl").write_text(json.dumps(record) + "\n")
        store = self.root / "store"

        self.run_main(
            "init-project",
            "--target",
            str(store),
            "--repo-root",
            str(repo),
            "--write",
        )

        new_marker = repo / ".tkn" / "codex-context.yaml"
        self.assertEqual(
            "20260101_example_abcd1234",
            bridge.yaml_value(new_marker.read_text(), "projectId"),
        )
        self.assertTrue(old_marker.exists())
        self.assertTrue(
            (store / "state" / "20260101_example_abcd1234" / "sessions" / "session.md").exists()
        )
        new_records = bridge.read_jsonl(store / "state" / "index.jsonl", bridge.Result())
        self.assertEqual("ws_legacy", new_records[0]["workspaceId"])

    def test_store_migration_is_non_destructive_and_rewrites_registry_paths(self) -> None:
        legacy = self.root / "legacy"
        project_id = "20260101_example_abcd1234"
        (legacy / "decisions").mkdir(parents=True)
        (legacy / "decisions" / "DR-G-example.md").write_text("legacy decision\n")
        (legacy / "working-context.md").write_text("legacy global context\n")
        project = legacy / "projects" / project_id
        (project / "memos").mkdir(parents=True)
        (project / "memos" / "memo.md").write_text("legacy memo\n")
        record = {
            "workspaceId": "ws_legacy",
            "projectId": project_id,
            "currentRoot": "C:/path/to/project",
            "projectContextPath": (legacy / "projects" / project_id).as_posix(),
        }
        (legacy / "projects" / "index.jsonl").write_text(json.dumps(record) + "\n")
        store = self.root / "store"

        self.run_main(
            "init",
            "--target",
            str(store),
            "--migrate-from",
            str(legacy),
            "--write",
        )

        self.assertTrue((legacy / "decisions" / "DR-G-example.md").exists())
        self.assertEqual(
            "legacy decision\n",
            (store / "data" / "decisions" / "DR-G-example.md").read_text(),
        )
        self.assertTrue((store / "state" / project_id / "memos" / "memo.md").exists())
        for folder in bridge.PROJECT_STATE_DIRS:
            self.assertTrue((store / "state" / project_id / folder).is_dir())
        self.assertTrue((store / "state" / project_id / "working-context.md").is_file())
        migrated = bridge.read_jsonl(store / "state" / "index.jsonl", bridge.Result())[0]
        self.assertEqual((store / "state" / project_id).as_posix(), migrated["projectContextPath"])
        self.assertEqual((store / "state" / project_id / "memos").as_posix(), migrated["memosPath"])

        self.run_main(
            "init",
            "--target",
            str(store),
            "--migrate-from",
            str(legacy),
            "--write",
        )

    def test_store_migration_stops_on_different_destination_content(self) -> None:
        legacy = self.root / "legacy"
        store = self.root / "store"
        (legacy / "candidates").mkdir(parents=True)
        (legacy / "candidates" / "item.md").write_text("legacy\n")
        (store / "data" / "candidates").mkdir(parents=True)
        destination = store / "data" / "candidates" / "item.md"
        destination.write_text("new\n")

        with self.assertRaises(SystemExit):
            self.run_main(
                "init",
                "--target",
                str(store),
                "--migrate-from",
                str(legacy),
                "--write",
            )

        self.assertEqual("new\n", destination.read_text())
        self.assertEqual("legacy\n", (legacy / "candidates" / "item.md").read_text())

    def test_in_place_store_migration_dry_run_is_read_only(self) -> None:
        store, _ = self.create_flat_store()
        before = {
            path.relative_to(store).as_posix(): path.read_bytes()
            for path in store.rglob("*")
            if path.is_file()
        }

        _, output = self.run_main(
            "init",
            "--target",
            str(store),
            "--migrate-from",
            str(store),
            "--dry-run",
        )

        after = {
            path.relative_to(store).as_posix(): path.read_bytes()
            for path in store.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)
        self.assertIn("preflight", output)
        self.assertFalse((store / "data").exists())
        self.assertFalse((store / bridge.IN_PLACE_JOURNAL_NAME).exists())

    def test_in_place_store_migration_moves_without_backup(self) -> None:
        store, project_id = self.create_flat_store()

        self.run_main(
            "init",
            "--target",
            str(store),
            "--migrate-from",
            str(store),
            "--write",
        )

        self.assertFalse((store / "projects").exists())
        self.assertFalse((store / "working-context.md").exists())
        self.assertFalse((store / "decisions").exists())
        self.assertTrue((store / "data" / "decisions" / "DR-G-example.md").is_file())
        self.assertTrue((store / "state" / project_id / "sessions" / "session.md").is_file())
        self.assertEqual("schemaVersion: 1\n", (store / "config" / "config.yaml").read_text())
        self.assertIn("config/config.yaml", (store / "README.md").read_text())
        self.assertIn(
            "~/.tkn/codex-context/data",
            (store / "data" / "working-context.md").read_text(),
        )
        migrated = bridge.read_jsonl(store / "state" / "index.jsonl", bridge.Result())[0]
        self.assertEqual((store / "state" / project_id).as_posix(), migrated["projectContextPath"])
        self.assertEqual((store / "state" / project_id / "memos").as_posix(), migrated["memosPath"])
        self.assertFalse((store / bridge.IN_PLACE_JOURNAL_NAME).exists())
        self.assertFalse((store / "data" / "promoted").exists())
        self.assertEqual(
            {"README.md", "config", "data", "state"},
            {path.name for path in store.iterdir()},
        )

        _, second_output = self.run_main(
            "init",
            "--target",
            str(store),
            "--migrate-from",
            str(store),
            "--write",
        )
        self.assertIn("skip-versioned", second_output)

    def test_in_place_store_migration_rolls_back_rename_error(self) -> None:
        store, _ = self.create_flat_store()
        real_rename = bridge.rename_path
        calls = 0

        def fail_second(source: Path, destination: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated rename failure")
            real_rename(source, destination)

        with patch.object(bridge, "rename_path", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.run_main(
                    "init",
                    "--target",
                    str(store),
                    "--migrate-from",
                    str(store),
                    "--write",
                )

        self.assertTrue((store / "working-context.md").is_file())
        self.assertTrue((store / "decisions" / "DR-G-example.md").is_file())
        self.assertTrue((store / "projects" / "index.jsonl").is_file())
        self.assertFalse((store / "data").exists())
        self.assertFalse((store / bridge.IN_PLACE_JOURNAL_NAME).exists())

    def test_in_place_store_migration_resumes_after_interruption(self) -> None:
        store, project_id = self.create_flat_store()
        real_rename = bridge.rename_path
        calls = 0

        def interrupt_second(source: Path, destination: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt()
            real_rename(source, destination)

        with patch.object(bridge, "rename_path", side_effect=interrupt_second):
            with self.assertRaises(KeyboardInterrupt):
                self.run_main(
                    "init",
                    "--target",
                    str(store),
                    "--migrate-from",
                    str(store),
                    "--write",
                )

        self.assertTrue((store / bridge.IN_PLACE_JOURNAL_NAME).is_file())
        _, output = self.run_main(
            "init",
            "--target",
            str(store),
            "--migrate-from",
            str(store),
            "--write",
        )
        self.assertIn("resume", output)
        self.assertTrue((store / "state" / project_id / "working-context.md").is_file())
        self.assertFalse((store / bridge.IN_PLACE_JOURNAL_NAME).exists())

    def test_promotion_and_load_use_data_folder(self) -> None:
        store = self.root / "store"
        body = self.root / "candidate.md"
        body.write_text("# Candidate\n\nReusable content.\n")

        self.run_main("init", "--target", str(store), "--write")
        self.run_main(
            "promote",
            "--target",
            str(store),
            "--kind",
            "candidate",
            "--title",
            "Example Candidate",
            "--body-file",
            str(body),
            "--write",
        )

        candidates = list((store / "data" / "candidates").glob("*.md"))
        self.assertEqual(1, len(candidates))
        self.assertFalse((store / "data" / "promoted").exists())
        _, load_output = self.run_main(
            "load",
            "--source",
            str(store),
            "--include",
            "candidates",
            "--candidate",
            candidates[0].name,
        )
        self.assertIn("Example Candidate", load_output)

    def test_import_audit_distill_and_finalize_use_new_paths(self) -> None:
        repo = self.root / "repo"
        repo.mkdir()
        previous_cwd = Path.cwd()
        try:
            os.chdir(repo)
            self.run_main("init-project", "--repo-root", str(repo), "--write")
            store = self.home / ".tkn" / "codex-context"
            marker = repo / ".tkn" / "codex-context.yaml"
            project_id = bridge.yaml_value(marker.read_text(), "projectId")
            project_state = store / "state" / project_id
            session = project_state / "sessions" / "session.md"
            session.write_text(
                "---\n"
                "type: session\n"
                "title: Example Session\n"
                "date: 2026-01-01T00:00:00+09:00\n"
                "updated: 2026-01-01T00:00:00+09:00\n"
                "distillationStatus: pending\n"
                "distilledTo: []\n"
                "---\n\n"
                "# Example Session\n\n## Important decisions\n\n- Keep the new layout.\n",
                encoding="utf-8",
            )

            snapshot = self.root / "snapshot"
            self.run_main(
                "import",
                "--source",
                str(store),
                "--dest",
                str(snapshot),
                "--include",
                "working-context",
                "--write",
            )
            self.assertTrue((snapshot / "working-context.md").exists())

            report_dir = self.root / "reports"
            self.run_main(
                "audit-freshness",
                "--source",
                str(project_state),
                "--report-dest",
                str(report_dir),
                "--write",
            )
            self.assertEqual(1, len(list(report_dir.glob("*.md"))))

            self.run_main("distill-session", "--session", str(session), "--write")
            default_candidates = (
                self.home
                / ".codex-working"
                / "projects"
                / project_id
                / "context-bridge"
                / "distilled-session-candidates"
            )
            candidate = next(default_candidates.glob("*.md"))
            distilled_ref = f"~/.codex-working/projects/{project_id}/context-bridge/distilled-session-candidates/{candidate.name}"
            self.run_main(
                "finalize-session-distillation",
                "--session",
                str(session),
                "--status",
                "distilled",
                "--distilled-to",
                distilled_ref,
                "--write",
            )
            finalized = session.read_text()
            self.assertIn('distillationStatus: "distilled"', finalized)
            self.assertIn(distilled_ref, finalized)
        finally:
            os.chdir(previous_cwd)


if __name__ == "__main__":
    unittest.main()
