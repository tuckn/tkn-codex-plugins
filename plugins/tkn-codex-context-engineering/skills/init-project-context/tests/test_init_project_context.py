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


SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

import init_project_context as project  # noqa: E402


class InitProjectContextTests(unittest.TestCase):
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
            result = project.main(list(args))
        return result, output.getvalue()

    def test_init_project_creates_marker_registry_and_state(self) -> None:
        store = self.root / "store"
        repo = self.root / "example-repo"
        repo.mkdir()

        result, _ = self.run_main(
            "--target", str(store), "--repo-root", str(repo), "--write"
        )

        self.assertEqual(0, result)
        marker = repo / ".tkn" / "codex-context.yaml"
        project_id = project.yaml_value(marker.read_text(), "projectId")
        project_state = store / "state" / project_id
        self.assertTrue((project_state / "working-context.md").is_file())
        working_context = (project_state / "working-context.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("`state:/working-context.md`", working_context)
        self.assertIn("`state:/sessions/`", working_context)
        self.assertIn("`state:/decisions/`", working_context)
        self.assertNotIn("- `working-context.md`", working_context)
        for folder in project.PROJECT_STATE_DIRS:
            self.assertTrue((project_state / folder).is_dir())
        records = project.read_jsonl(store / "state" / "index.jsonl", project.Result())
        self.assertEqual(1, len(records))
        self.assertEqual((project_state / "memos").as_posix(), records[0]["memosPath"])

        _, second_output = self.run_main(
            "--target", str(store), "--repo-root", str(repo), "--write"
        )
        self.assertEqual(project_id, project.yaml_value(marker.read_text(), "projectId"))
        self.assertIn("reuse-workspace", second_output)

    def test_dry_run_is_read_only(self) -> None:
        store = self.root / "store"
        repo = self.root / "repo"
        repo.mkdir()

        _, output = self.run_main(
            "--target", str(store), "--repo-root", str(repo), "--dry-run"
        )

        self.assertIn("mode: dry-run", output)
        self.assertFalse(store.exists())
        self.assertFalse((repo / ".tkn").exists())

    def test_reuses_identity_for_move_but_not_live_copy(self) -> None:
        store = self.root / "store"
        original = self.root / "original"
        original.mkdir()
        self.run_main("--target", str(store), "--repo-root", str(original), "--write")
        original_marker = original / ".tkn" / "codex-context.yaml"
        original_id = project.yaml_value(original_marker.read_text(), "projectId")
        original_record = project.read_jsonl(
            store / "state" / "index.jsonl", project.Result()
        )[0]

        copied = self.root / "copied"
        copied.mkdir()
        (copied / ".tkn").mkdir()
        (copied / ".tkn" / "codex-context.yaml").write_text(original_marker.read_text())
        self.run_main("--target", str(store), "--repo-root", str(copied), "--write")
        copied_id = project.yaml_value(
            (copied / ".tkn" / "codex-context.yaml").read_text(), "projectId"
        )
        self.assertNotEqual(original_id, copied_id)

        moved = self.root / "moved"
        original.rename(moved)
        self.run_main("--target", str(store), "--repo-root", str(moved), "--write")
        moved_id = project.yaml_value(
            (moved / ".tkn" / "codex-context.yaml").read_text(), "projectId"
        )
        moved_records = project.read_jsonl(
            store / "state" / "index.jsonl", project.Result()
        )
        moved_record = next(record for record in moved_records if record["projectId"] == moved_id)
        self.assertEqual(original_id, moved_id)
        self.assertEqual(original_record["workspaceId"], moved_record["workspaceId"])

    def test_preserves_legacy_identity_and_files(self) -> None:
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

        self.run_main("--target", str(store), "--repo-root", str(repo), "--write")

        new_marker = repo / ".tkn" / "codex-context.yaml"
        self.assertEqual(
            "20260101_example_abcd1234",
            project.yaml_value(new_marker.read_text(), "projectId"),
        )
        self.assertTrue(old_marker.exists())
        self.assertTrue(
            (store / "state" / "20260101_example_abcd1234" / "sessions" / "session.md").exists()
        )
        records = project.read_jsonl(store / "state" / "index.jsonl", project.Result())
        self.assertEqual("ws_legacy", records[0]["workspaceId"])


if __name__ == "__main__":
    unittest.main()
