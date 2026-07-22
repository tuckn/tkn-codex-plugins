from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from materialize_context_rebuild_shadow import (
    SESSION_HEADINGS,
    WORKING_CONTEXT_HEADINGS,
    ShadowError,
    materialize,
    skill_invocation_label,
    strip_leading_skill_invocations,
)


def event(event_type: str, payload: dict, timestamp: str) -> str:
    return json.dumps({"timestamp": timestamp, "type": event_type, "payload": payload})


class MaterializeContextRebuildShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sessions = self.root / "sessions"
        self.sessions.mkdir()
        self.source = self.sessions / "2026" / "01" / "01" / "session.jsonl"
        self.source.parent.mkdir(parents=True)
        cwd = "C:/Users/ExampleUser/Projects/example"
        lines = [
            event(
                "session_meta",
                {
                    "id": "thread-example",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "cwd": cwd,
                    "thread_source": "user",
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
                {
                    "role": "user",
                    "content": [
                        {
                            "text": "[$example-skill](C:\\Users\\ExampleUser\\.codex\\skills\\example\\SKILL.md) "
                            "OKです。API_KEY=top-secret-value を保存せず再構築してください。"
                        }
                    ],
                },
                "2026-01-01T00:00:02Z",
            ),
            event(
                "response_item",
                {
                    "role": "assistant",
                    "content": [{"text": "実装し、tests passed と確認しました。"}],
                },
                "2026-01-01T00:00:03Z",
            ),
        ]
        self.source.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.plan = {
            "schemaVersion": 1,
            "mode": "readOnlyPlan",
            "contextRoot": str(self.root / "live-context"),
            "sources": [
                {
                    "sourceId": "windows",
                    "sourceRoot": str(self.sessions),
                }
            ],
            "summary": {"directAssignments": 1},
            "unresolvedSessions": [],
            "projects": [
                {
                    "projectId": "20260101_example_abcd1234",
                    "title": "Example",
                    "status": "active",
                    "acceptedRoots": [cwd],
                    "assignedSessions": [
                        {
                            "threadId": "thread-example",
                            "timestamp": "2026-01-01T00:00:00Z",
                            "sourceId": "windows",
                            "sourceRef": "windows/2026/01/01/session.jsonl",
                        }
                    ],
                }
            ],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_materializes_v2_session_and_working_context_without_live_write(self) -> None:
        output = self.root / "shadow"
        source_before = self.source.read_bytes()
        manifest = materialize(self.plan, output)

        sessions = list(
            (output / "state" / "20260101_example_abcd1234" / "sessions").glob("*.md")
        )
        self.assertEqual(1, len(sessions))
        session_text = sessions[0].read_text(encoding="utf-8")
        self.assertIn("schemaVersion: 2", session_text)
        self.assertIn(
            'sourceRefs:\n  - "windows/2026/01/01/session.jsonl"', session_text
        )
        self.assertNotIn("top-secret-value", session_text)
        self.assertNotIn(".codex\\\\skills", session_text)
        self.assertIn("api_key=<redacted>", session_text.casefold())
        for heading in SESSION_HEADINGS:
            self.assertIn(heading, session_text)

        working = (
            output
            / "state"
            / "20260101_example_abcd1234"
            / "working-context.md"
        ).read_text(encoding="utf-8")
        self.assertIn("type: workingContext", working)
        self.assertIn("schemaVersion: 2", working)
        for heading in WORKING_CONTEXT_HEADINGS:
            self.assertIn(heading, working)

        self.assertEqual(1, manifest["summary"]["sessionNotes"])
        self.assertEqual(1, manifest["summary"]["decisionCandidates"])
        self.assertEqual(0, manifest["summary"]["decisionRecords"])
        self.assertTrue(manifest["validation"]["passed"])
        self.assertEqual(0, manifest["validation"]["unredactedSecretMatches"])
        self.assertEqual(source_before, self.source.read_bytes())
        self.assertFalse((self.root / "live-context").exists())

    def test_refuses_existing_or_protected_output(self) -> None:
        existing = self.root / "existing"
        existing.mkdir()
        with self.assertRaises(ShadowError):
            materialize(self.plan, existing)
        with self.assertRaises(ShadowError):
            materialize(self.plan, self.sessions / "shadow")

    def test_skill_only_invocation_uses_label_without_local_path(self) -> None:
        invocation = (
            "[$plugin:refresh-project-context-from-chats]"
            "(C:\\Users\\ExampleUser\\.codex\\plugins\\skill\\SKILL.md)"
        )
        self.assertEqual("", strip_leading_skill_invocations(invocation))
        self.assertEqual(
            "refresh-project-context-from-chats", skill_invocation_label(invocation)
        )


if __name__ == "__main__":
    unittest.main()
