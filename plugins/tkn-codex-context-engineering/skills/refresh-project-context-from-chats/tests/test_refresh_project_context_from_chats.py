from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
REFRESH_SCRIPTS = PLUGIN_ROOT / "skills" / "refresh-project-context-from-chats" / "scripts"
if str(REFRESH_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(REFRESH_SCRIPTS))

from refresh_project_context_from_chats import RefreshError, commit_refresh, scan_project


REPOSITORY_URL = "https://example.invalid/example/project.git"


def json_line(event_type: str, payload: dict, timestamp: str) -> str:
    return json.dumps({"timestamp": timestamp, "type": event_type, "payload": payload})


def write_session(
    path: Path,
    *,
    thread_id: str,
    cwd: Path,
    user_text: str,
    assistant_text: str = "done",
    repository_url: str = REPOSITORY_URL,
    second_cwd: Path | None = None,
    thread_source: str = "user",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    events = [
        json_line(
            "session_meta",
            {
                "id": thread_id,
                "timestamp": "2026-07-01T00:00:00Z",
                "cwd": str(cwd),
                "originator": "Codex Desktop",
                "source": "vscode",
                "thread_source": thread_source,
                "git": {"repository_url": repository_url},
            },
            "2026-07-01T00:00:00Z",
        ),
        json_line(
            "turn_context",
            {"turn_id": "turn-1", "cwd": str(cwd)},
            "2026-07-01T00:00:01Z",
        ),
        json_line(
            "response_item",
            {"role": "user", "content": [{"text": user_text}]},
            "2026-07-01T00:00:02Z",
        ),
        json_line(
            "event_msg",
            {"type": "user_message", "message": user_text},
            "2026-07-01T00:00:02Z",
        ),
        json_line(
            "response_item",
            {"role": "assistant", "content": [{"text": assistant_text}]},
            "2026-07-01T00:00:03Z",
        ),
    ]
    if second_cwd:
        events.extend(
            [
                json_line(
                    "turn_context",
                    {"turn_id": "turn-2", "cwd": str(second_cwd)},
                    "2026-07-01T00:00:04Z",
                ),
                json_line(
                    "response_item",
                    {"role": "user", "content": [{"text": "other project request"}]},
                    "2026-07-01T00:00:05Z",
                ),
                json_line(
                    "response_item",
                    {"role": "assistant", "content": [{"text": "other project response"}]},
                    "2026-07-01T00:00:06Z",
                ),
            ]
        )
    path.write_text("\n".join(events) + "\n", encoding="utf-8")


class RefreshProjectContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.sessions = self.root / "sessions"
        self.project_state = self.root / "project-state"
        self.registry = self.root / "index.jsonl"
        self.state_file = self.project_state / "chat-refresh-state.json"
        self.project_id = "20260701_example_project_abcd1234"
        (self.repo / ".tkn").mkdir(parents=True)
        (self.repo / ".tkn" / "codex-context.yaml").write_text(
            f'projectId: "{self.project_id}"\n', encoding="utf-8"
        )
        self.project_state.mkdir(parents=True)
        self.registry.write_text(
            json.dumps(
                {
                    "projectId": self.project_id,
                    "currentRoot": str(self.repo),
                    "projectContextPath": str(self.project_state),
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_fixture_sessions(self) -> dict[str, Path]:
        current = self.sessions / "2026" / "07" / "01" / "current.jsonl"
        mixed = self.sessions / "2026" / "07" / "01" / "mixed.jsonl"
        old = self.sessions / "2026" / "06" / "01" / "old.jsonl"
        other = self.sessions / "2026" / "07" / "01" / "other.jsonl"
        approval = self.sessions / "2026" / "07" / "01" / "approval.jsonl"
        internal = self.sessions / "2026" / "07" / "01" / "internal.jsonl"
        write_session(current, thread_id="thread-current", cwd=self.repo, user_text="current request")
        write_session(
            mixed,
            thread_id="thread-mixed",
            cwd=self.repo,
            user_text="mixed current request",
            second_cwd=self.root / "other-project",
        )
        write_session(old, thread_id="thread-old", cwd=self.root / "old-repo", user_text="old request")
        write_session(
            other,
            thread_id="thread-other",
            cwd=self.root / "other-repo",
            user_text="other request",
            repository_url="https://example.invalid/other/repo.git",
        )
        write_session(
            approval,
            thread_id="thread-approval",
            cwd=self.repo,
            user_text="The following is the Codex agent history whose request action you are assessing.",
        )
        write_session(
            internal,
            thread_id="thread-internal",
            cwd=self.repo,
            user_text="internal request",
            thread_source="subagent",
        )
        return {"current": current, "mixed": mixed, "old": old}

    def scan(self, **kwargs):
        return scan_project(
            self.repo,
            self.sessions,
            registry_path=self.registry,
            state_file=self.state_file,
            repository_url=REPOSITORY_URL,
            **kwargs,
        )

    def test_scan_filters_turns_and_lists_historical_root_candidate(self) -> None:
        self.create_fixture_sessions()
        scan = self.scan(include_messages=True)

        self.assertEqual(scan["counts"]["total"], 2)
        self.assertEqual(scan["counts"]["new"], 2)
        self.assertEqual(scan["skipped"]["approvalReview"], 1)
        self.assertEqual(scan["skipped"]["internal"], 1)
        self.assertEqual(len(scan["historicalRootCandidates"]), 1)
        self.assertEqual(scan["historicalRootCandidates"][0]["sessionCount"], 1)

        mixed = next(item for item in scan["sessions"] if item["threadId"] == "thread-mixed")
        self.assertTrue(mixed["mixedCwd"])
        self.assertEqual(mixed["messageCount"], 2)
        self.assertNotIn("other project request", [m["text"] for m in mixed["messages"]])

    def test_commit_is_incremental_and_detects_changed_source(self) -> None:
        paths = self.create_fixture_sessions()
        first_scan = self.scan()
        result = {
            "processed": [
                {
                    "threadId": item["threadId"],
                    "fingerprint": item["fingerprint"],
                    "sessionNote": f'sessions/{item["threadId"]}.md',
                    "decisionIds": [],
                }
                for item in first_scan["sessions"]
            ]
        }
        summary = commit_refresh(first_scan, result, state_file=self.state_file)
        self.assertEqual(summary["processedCount"], 2)
        second_scan = self.scan()
        self.assertEqual(second_scan["counts"]["unchanged"], 2)
        state_before_noop = self.state_file.read_bytes()
        noop = commit_refresh(second_scan, {"processed": []}, state_file=self.state_file)
        self.assertTrue(noop["noChange"])
        self.assertEqual(self.state_file.read_bytes(), state_before_noop)

        with paths["current"].open("a", encoding="utf-8") as handle:
            handle.write(
                json_line(
                    "event_msg",
                    {"type": "agent_message", "message": "later response"},
                    "2026-07-01T00:00:07Z",
                )
                + "\n"
            )
        changed_scan = self.scan()
        self.assertEqual(changed_scan["counts"]["changed"], 1)
        with self.assertRaises(RefreshError):
            commit_refresh(first_scan, result, state_file=self.state_file)

    def test_missing_source_fails_without_creating_state(self) -> None:
        paths = self.create_fixture_sessions()
        scan = self.scan()
        current = next(item for item in scan["sessions"] if item["threadId"] == "thread-current")
        result = {
            "processed": [
                {
                    "threadId": current["threadId"],
                    "fingerprint": current["fingerprint"],
                    "sessionNote": "sessions/thread-current.md",
                    "decisionIds": [],
                }
            ]
        }
        paths["current"].unlink()
        with self.assertRaises(RefreshError):
            commit_refresh(scan, result, state_file=self.state_file)
        self.assertFalse(self.state_file.exists())

    def test_root_approval_and_rejection_are_persisted(self) -> None:
        paths = self.create_fixture_sessions()
        old_root = str(paths["old"].parents[4] / "old-repo")
        approved_scan = self.scan(approve_roots=[old_root])
        self.assertEqual(approved_scan["counts"]["total"], 3)
        commit_refresh(approved_scan, {"processed": []}, state_file=self.state_file)
        persisted = self.scan()
        self.assertEqual(persisted["counts"]["total"], 3)
        self.assertFalse(persisted["historicalRootCandidates"])

        rejected_scan = self.scan(reject_roots=[old_root])
        self.assertEqual(rejected_scan["counts"]["total"], 2)
        commit_refresh(rejected_scan, {"processed": []}, state_file=self.state_file)
        persisted_rejection = self.scan()
        self.assertEqual(persisted_rejection["counts"]["total"], 2)
        self.assertFalse(persisted_rejection["historicalRootCandidates"])

    def test_corrupt_state_fails_closed(self) -> None:
        self.create_fixture_sessions()
        self.state_file.write_text("not json", encoding="utf-8")
        with self.assertRaises(RefreshError):
            self.scan()

    def test_search_cli_keeps_compact_json_message_shape(self) -> None:
        self.create_fixture_sessions()
        search_script = (
            PLUGIN_ROOT
            / "skills"
            / "search-all-codex-chats"
            / "scripts"
            / "search_all_codex_chats.py"
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(search_script),
                "--sessions-root",
                str(self.sessions),
                "--format",
                "json",
                "--messages-per-role",
                "0",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        rows = json.loads(completed.stdout)
        self.assertEqual(len(rows), 5)
        self.assertEqual(set(rows[0]["user_messages"][0]), {"role", "source", "text"})


if __name__ == "__main__":
    unittest.main()
