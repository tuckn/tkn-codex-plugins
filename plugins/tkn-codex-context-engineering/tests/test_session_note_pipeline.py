from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_LIB = PLUGIN_ROOT / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from tkn_codex_context.chat_logs import read_session_events
from tkn_codex_context.session_notes import (
    Candidate,
    CodexSummarizer,
    PipelineConfig,
    Project,
    chunk_events,
    execute_pipeline,
    load_config,
    make_config,
    prepare_events,
    scan_candidates,
    write_config,
)


def json_line(event_type: str, payload: dict, timestamp: str) -> str:
    return json.dumps({"timestamp": timestamp, "type": event_type, "payload": payload})


def write_chat(path: Path, *, thread_id: str, cwd: Path, request: str = "do work") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json_line(
            "session_meta",
            {
                "id": thread_id,
                "timestamp": "2026-07-01T00:00:00Z",
                "cwd": str(cwd),
                "thread_source": "user",
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
            {"type": "message", "role": "user", "content": [{"text": request}]},
            "2026-07-01T00:00:02Z",
        ),
        json_line(
            "event_msg",
            {"type": "user_message", "message": request},
            "2026-07-01T00:00:02Z",
        ),
        json_line(
            "response_item",
            {"type": "custom_tool_call", "name": "exec", "input": {"cmd": "test"}},
            "2026-07-01T00:00:03Z",
        ),
        json_line(
            "response_item",
            {
                "type": "custom_tool_call_output",
                "call_id": "call-1",
                "output": "password=0123456789abcdef and tests passed",
            },
            "2026-07-01T00:00:04Z",
        ),
        json_line(
            "response_item",
            {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"text": "completed"}],
            },
            "2026-07-01T00:00:05Z",
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    old = (datetime.now().astimezone() - timedelta(hours=1)).timestamp()
    os.utime(path, (old, old))


def note_data(candidate: Candidate, *, title: str = "Automated session") -> dict:
    ids = [event.id for event in candidate.events]
    return {
        "title": title,
        "description": "A factual session digest.",
        "summary": "The requested work was completed.",
        "summaryEventIds": ids[:1],
        "keyDevelopments": [
            {"label": "Request", "text": "The user requested work.", "eventIds": ids[:1]},
            {"label": "Result", "text": "The work completed.", "eventIds": ids[-1:]},
        ],
        "lastKnownState": {
            "workState": "done",
            "detail": "The assistant reported completion.",
            "latestUserDirection": "Complete the work.",
            "unresolved": [],
            "continuationPoint": "",
            "eventIds": ids[-1:],
        },
        "sourceLimitations": [],
    }


class FakeSummarizer:
    def __init__(self, *, fail_thread: str = "") -> None:
        self.fail_thread = fail_thread
        self.calls: list[str] = []

    def generate(self, candidate: Candidate) -> dict:
        self.calls.append(candidate.thread_id)
        if candidate.thread_id == self.fail_thread:
            raise RuntimeError("simulated failure")
        return note_data(candidate)


class MutatingSummarizer:
    def generate(self, candidate: Candidate) -> dict:
        with candidate.source_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json_line(
                    "event_msg",
                    {"type": "agent_message", "message": "changed during generation"},
                    "2026-07-01T00:00:06Z",
                )
                + "\n"
            )
        return note_data(candidate)


class SessionNotePipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.context = self.root / "context"
        self.sessions = self.root / "codex-sessions"
        self.sessions.mkdir()
        self.cache = self.root / "cache"
        self.project = Project("project-1", "Project 1", self.repo, self.context)
        self.config = PipelineConfig(
            installed_at="2026-01-01T00:00:00+00:00",
            sessions_root=self.sessions,
            source_id="windows",
            codex_bin=str(Path(sys.executable)),
            idle_minutes=30,
            runtime_minutes=230,
            model_timeout_seconds=30,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_event_parser_deduplicates_messages_and_keeps_tool_evidence(self) -> None:
        path = self.sessions / "2026" / "07" / "01" / "chat.jsonl"
        write_chat(path, thread_id="thread-1", cwd=self.repo)
        events = read_session_events(path)

        self.assertEqual(1, sum(event.kind == "user_message" for event in events))
        self.assertEqual(1, sum(event.kind == "assistant_message" for event in events))
        self.assertEqual(1, sum(event.kind == "tool_call" for event in events))
        self.assertEqual(1, sum(event.kind == "tool_result" for event in events))
        prepared = prepare_events(events)
        tool_result = next(event for event in prepared if event.kind == "tool_result")
        self.assertIn("[REDACTED]", tool_result.text)
        self.assertNotIn("0123456789abcdef", tool_result.text)

    def test_chunking_preserves_event_boundaries(self) -> None:
        path = self.sessions / "chat.jsonl"
        write_chat(path, thread_id="thread-1", cwd=self.repo)
        prepared = prepare_events(read_session_events(path))
        chunks = chunk_events(prepared, target_characters=150)

        self.assertGreater(len(chunks), 1)
        self.assertEqual([item.id for item in prepared], [item.id for chunk in chunks for item in chunk])

    def test_config_preserves_watermark_and_fixed_model(self) -> None:
        config_path = self.root / "config.json"
        write_config(config_path, self.config)
        loaded = load_config(config_path)
        updated = make_config(existing=loaded, codex_bin=sys.executable)

        self.assertEqual(self.config.installed_at, updated.installed_at)
        self.assertEqual("gpt-5.6-sol", updated.model)
        self.assertEqual("high", updated.reasoning_effort)

    def test_codex_path_preserves_stable_launcher_path(self) -> None:
        launcher = self.root / "codex.exe"
        launcher.write_bytes(Path(sys.executable).read_bytes())
        configured = make_config(existing=self.config, codex_bin=str(launcher))

        self.assertEqual(str(launcher.absolute()), configured.codex_bin)

    def test_daily_scan_skips_preinstallation_history_but_backfill_finds_it(self) -> None:
        path = self.sessions / "2025" / "12" / "31" / "old.jsonl"
        write_chat(path, thread_id="thread-old", cwd=self.repo)
        old = datetime(2025, 12, 31).astimezone().timestamp()
        os.utime(path, (old, old))

        daily, _counts = scan_candidates(self.config, [self.project])
        backfill, _counts = scan_candidates(self.config, [self.project], backfill=True)

        self.assertEqual([], daily)
        self.assertEqual(["thread-old"], [item.thread_id for item in backfill])

    def test_daily_scan_requires_idle_source(self) -> None:
        path = self.sessions / "chat.jsonl"
        write_chat(path, thread_id="thread-1", cwd=self.repo)
        current = datetime.now().astimezone().timestamp()
        os.utime(path, (current, current))

        active, _counts = scan_candidates(self.config, [self.project])
        old = (datetime.now().astimezone() - timedelta(hours=1)).timestamp()
        os.utime(path, (old, old))
        idle, _counts = scan_candidates(self.config, [self.project])

        self.assertEqual([], active)
        self.assertEqual(["thread-1"], [item.thread_id for item in idle])

    def test_scan_has_no_daily_item_cap(self) -> None:
        for index in range(25):
            write_chat(
                self.sessions / "2026" / "07" / "01" / f"chat-{index:02d}.jsonl",
                thread_id=f"thread-{index:02d}",
                cwd=self.repo,
            )

        candidates, _counts = scan_candidates(self.config, [self.project])

        self.assertEqual(25, len(candidates))

    def test_write_run_creates_live_note_then_state_and_updates_exact_match(self) -> None:
        path = self.sessions / "2026" / "07" / "01" / "chat.jsonl"
        write_chat(path, thread_id="thread-1", cwd=self.repo)
        first, _report_path = execute_pipeline(
            self.config,
            [self.project],
            summarizer=FakeSummarizer(),
            cache_root=self.cache,
        )

        self.assertEqual(1, len(first["processed"]))
        notes = list(self.project.sessions_path.glob("*.md"))
        self.assertEqual(1, len(notes))
        text = notes[0].read_text(encoding="utf-8")
        self.assertIn('reviewStatus: "unreviewed"', text)
        self.assertIn('sourceThreadIds:\n  - "thread-1"', text)
        state = json.loads(self.project.state_path.read_text(encoding="utf-8"))
        self.assertIn("thread-1", state["sources"]["windows"]["threads"])

        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json_line(
                    "event_msg",
                    {"type": "agent_message", "message": "a later result"},
                    "2026-07-01T00:00:06Z",
                )
                + "\n"
            )
        old = (datetime.now().astimezone() - timedelta(hours=1)).timestamp()
        os.utime(path, (old, old))
        second, _report_path = execute_pipeline(
            self.config,
            [self.project],
            summarizer=FakeSummarizer(),
            cache_root=self.cache,
        )

        self.assertEqual(1, len(second["processed"]))
        self.assertEqual(1, len(list(self.project.sessions_path.glob("*.md"))))
        self.assertIn('reviewStatus: "unreviewed"', notes[0].read_text(encoding="utf-8"))

    def test_failure_is_isolated_and_does_not_commit_failed_thread(self) -> None:
        for thread in ("thread-good", "thread-bad"):
            write_chat(self.sessions / f"{thread}.jsonl", thread_id=thread, cwd=self.repo)
        report, _report_path = execute_pipeline(
            self.config,
            [self.project],
            summarizer=FakeSummarizer(fail_thread="thread-bad"),
            cache_root=self.cache,
        )

        self.assertEqual(1, len(report["processed"]))
        self.assertEqual(1, len(report["failed"]))
        state = json.loads(self.project.state_path.read_text(encoding="utf-8"))
        self.assertIn("thread-good", state["sources"]["windows"]["threads"])
        self.assertNotIn("thread-bad", state["sources"]["windows"]["threads"])

    def test_source_change_during_generation_is_not_written(self) -> None:
        write_chat(self.sessions / "chat.jsonl", thread_id="thread-1", cwd=self.repo)
        report, _report_path = execute_pipeline(
            self.config,
            [self.project],
            summarizer=MutatingSummarizer(),
            cache_root=self.cache,
        )

        self.assertEqual([], report["processed"])
        self.assertEqual(1, len(report["failed"]))
        self.assertFalse(self.project.sessions_path.exists())
        self.assertFalse(self.project.state_path.exists())

    def test_duplicate_exact_note_matches_fail_without_overwrite(self) -> None:
        source = self.sessions / "chat.jsonl"
        write_chat(source, thread_id="thread-1", cwd=self.repo)
        execute_pipeline(
            self.config,
            [self.project],
            summarizer=FakeSummarizer(),
            cache_root=self.cache,
        )
        note = next(self.project.sessions_path.glob("*.md"))
        duplicate = note.with_name("duplicate.md")
        shutil.copy2(note, duplicate)
        before = {path.name: path.read_bytes() for path in (note, duplicate)}
        with source.open("a", encoding="utf-8") as handle:
            handle.write(
                json_line(
                    "event_msg",
                    {"type": "agent_message", "message": "later"},
                    "2026-07-01T00:00:06Z",
                )
                + "\n"
            )
        old = (datetime.now().astimezone() - timedelta(hours=1)).timestamp()
        os.utime(source, (old, old))

        report, _report_path = execute_pipeline(
            self.config,
            [self.project],
            summarizer=FakeSummarizer(),
            cache_root=self.cache,
        )

        self.assertEqual(1, len(report["failed"]))
        self.assertEqual(before, {path.name: path.read_bytes() for path in (note, duplicate)})

    def test_dry_run_does_not_create_live_state(self) -> None:
        write_chat(self.sessions / "chat.jsonl", thread_id="thread-1", cwd=self.repo)
        report, report_path = execute_pipeline(
            self.config,
            [self.project],
            summarizer=None,
            dry_run=True,
            cache_root=self.cache,
        )

        self.assertEqual(1, report["selectedCount"])
        self.assertTrue(report_path.is_file())
        self.assertFalse(self.project.sessions_path.exists())
        self.assertFalse(self.project.state_path.exists())

    def test_codex_runner_uses_ephemeral_fixed_model_and_schema(self) -> None:
        path = self.sessions / "chat.jsonl"
        write_chat(path, thread_id="thread-1", cwd=self.repo)
        candidate = scan_candidates(self.config, [self.project])[0][0]
        captured: list[str] = []

        def fake_run(command, **kwargs):
            captured.extend(command)
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text(json.dumps(note_data(candidate)), encoding="utf-8")
            return SimpleNamespace(returncode=0, stderr="", stdout="")

        runner = CodexSummarizer(self.config, sleeper=lambda _seconds: None)
        with patch("tkn_codex_context.session_notes.subprocess.run", side_effect=fake_run):
            result = runner.generate(candidate)

        self.assertEqual("Automated session", result["title"])
        self.assertIn("--ephemeral", captured)
        self.assertIn("--ignore-user-config", captured)
        self.assertEqual("gpt-5.6-sol", captured[captured.index("--model") + 1])
        self.assertIn('model_reasoning_effort="high"', captured)


if __name__ == "__main__":
    unittest.main()
