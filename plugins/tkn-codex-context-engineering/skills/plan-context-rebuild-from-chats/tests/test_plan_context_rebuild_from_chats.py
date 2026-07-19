from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from plan_context_rebuild_from_chats import PlanError, build_plan, require_separate_output


def event(event_type: str, payload: dict, timestamp: str) -> str:
    return json.dumps({"timestamp": timestamp, "type": event_type, "payload": payload})


def write_session(
    path: Path,
    thread_id: str,
    cwd: str,
    repository_url: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        event(
            "session_meta",
            {
                "id": thread_id,
                "timestamp": "2026-01-01T00:00:00Z",
                "cwd": cwd,
                "thread_source": "user",
                "git": {"repository_url": repository_url},
            },
            "2026-01-01T00:00:00Z",
        ),
        event(
            "turn_context",
            {"turn_id": "turn-1", "cwd": cwd},
            "2026-01-01T00:00:01Z",
        ),
        event(
            "response_item",
            {"role": "user", "content": [{"text": "Please rebuild the context."}]},
            "2026-01-01T00:00:02Z",
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class PlanContextRebuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.context = self.root / "context"
        self.windows = self.root / "windows-sessions"
        self.wsl = self.root / "wsl-sessions"
        self.windows.mkdir()
        self.wsl.mkdir()
        registry = self.context / "state" / "index.jsonl"
        registry.parent.mkdir(parents=True)
        records = [
            {
                "projectId": "20260101_alpha_abcd1234",
                "title": "Alpha",
                "currentRoot": "C:/Users/ExampleUser/Projects/alpha",
            },
            {
                "projectId": "20260101_beta_efgh5678",
                "title": "Beta",
                "currentRoot": "D:/Projects/beta",
            },
        ]
        registry.write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )
        alpha_state = self.context / "state" / records[0]["projectId"]
        (alpha_state / "sessions").mkdir(parents=True)
        (alpha_state / "sessions" / "old.md").write_text(
            "---\ntype: session\n---\n# Old\n", encoding="utf-8"
        )
        (alpha_state / "working-context.md").write_text(
            "---\ntype: workingContext\nschemaVersion: 2\n---\n# Alpha\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def build(self, aliases: dict[str, list[str]] | None = None) -> dict:
        def repository_url(root: str) -> str:
            if root.endswith("alpha"):
                return "https://example.invalid/example/alpha.git"
            if root.endswith("beta"):
                return "https://example.invalid/example/beta.git"
            return ""

        with patch(
            "plan_context_rebuild_from_chats.discover_repository_url",
            side_effect=repository_url,
        ):
            return build_plan(
                self.context,
                [("windows", self.windows), ("wsl", self.wsl)],
                aliases,
            )

    def test_maps_windows_and_wsl_mount_paths_and_inventories_artifacts(self) -> None:
        write_session(
            self.windows / "current.jsonl",
            "thread-windows",
            "C:/Users/ExampleUser/Projects/alpha",
        )
        write_session(
            self.wsl / "legacy.jsonl",
            "thread-wsl",
            "/mnt/c/Users/ExampleUser/Projects/alpha",
        )
        plan = self.build()

        alpha = plan["projects"][0]
        self.assertEqual(2, alpha["counts"]["assigned"])
        self.assertEqual(
            {"2": 1, "unversioned": 1},
            alpha["artifactInventory"]["bySchemaVersion"],
        )
        self.assertEqual(2, plan["summary"]["directAssignments"])
        self.assertEqual("readOnlyPlan", plan["mode"])

    def test_repository_match_stays_candidate_until_root_is_approved(self) -> None:
        old_root = "C:/Archive/alpha"
        write_session(
            self.windows / "candidate.jsonl",
            "thread-candidate",
            old_root,
            "https://example.invalid/example/alpha.git",
        )
        first = self.build()
        self.assertEqual(0, first["summary"]["directAssignments"])
        self.assertEqual(1, first["summary"]["repositoryCandidates"])
        self.assertEqual(old_root, first["projects"][0]["candidateRootSummary"][0]["cwd"])
        self.assertEqual(
            "sameRepositoryUrlNeedsRootApproval",
            first["projects"][0]["candidateRootSummary"][0]["reason"],
        )

        approved = self.build({"20260101_alpha_abcd1234": [old_root]})
        self.assertEqual(1, approved["summary"]["directAssignments"])
        self.assertEqual(0, approved["summary"]["repositoryCandidates"])

    def test_reports_unparsed_unresolved_and_duplicate_thread_ids(self) -> None:
        write_session(
            self.windows / "duplicate.jsonl",
            "thread-duplicate",
            "C:/Unknown/project",
        )
        write_session(
            self.wsl / "duplicate.jsonl",
            "thread-duplicate",
            "/home/example/project",
        )
        (self.wsl / "invalid.jsonl").write_text(
            '{"record_type":"state"}\n', encoding="utf-8"
        )

        plan = self.build()
        self.assertEqual(1, plan["summary"]["unparsedFiles"])
        self.assertEqual(2, plan["summary"]["unresolvedSessions"])
        self.assertEqual(1, plan["summary"]["duplicateThreadIds"])
        self.assertEqual(2, len(plan["duplicateThreadIds"][0]["sourceRefs"]))
        self.assertEqual(2, len(plan["unresolvedRootSummary"]))

    def test_output_cannot_modify_context_or_source_trees(self) -> None:
        with self.assertRaises(PlanError):
            require_separate_output(
                self.context / "state" / "plan.json",
                self.context,
                [("windows", self.windows)],
            )
        with self.assertRaises(PlanError):
            require_separate_output(
                self.windows / "plan.json",
                self.context,
                [("windows", self.windows)],
            )
        require_separate_output(
            self.root / "output" / "plan.json",
            self.context,
            [("windows", self.windows)],
        )


if __name__ == "__main__":
    unittest.main()
