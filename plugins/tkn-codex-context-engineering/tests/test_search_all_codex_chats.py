from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "skills/search-all-codex-chats/scripts/search_all_codex_chats.py"
SPEC = importlib.util.spec_from_file_location("search_all_codex_chats", SCRIPT)
assert SPEC and SPEC.loader
search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(search)


class ChatSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="codex-chat-search-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.active = self.root / "sessions"
        self.archived = self.root / "archived_sessions"
        self.active.mkdir()
        self.archived.mkdir()

    def write_log(self, name="example", messages=None, *, archived=False,
                  created="2026-09-01T00:00:00Z", cwd="C:/old", thread_source="user"):
        records = [{
            "type": "session_meta",
            "payload": {"id": name, "timestamp": created, "cwd": cwd, "thread_source": thread_source},
        }]
        for i, message in enumerate(messages or [{"text": "request"}]):
            turn = message.get("turn", str(i))
            records.extend([
                {"type": "turn_context", "payload": {"turn_id": turn, "cwd": message.get("cwd", cwd)}},
                {"type": "response_item", "timestamp": message.get("timestamp", "2026-11-01T02:00:00Z"),
                 "payload": {"type": "message", "role": message.get("role", "user"),
                             "phase": message.get("phase", ""),
                             "content": [{"type": "input_text", "text": message["text"]}]}},
            ])
        path = (self.archived if archived else self.active) / (name + ".jsonl")
        path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        return path

    def run_search(self, *options):
        parser = search.build_parser()
        args = parser.parse_args(["--sessions-root", str(self.active), "--archived-root", str(self.archived), *options])
        return search.search(args, parser)

    def test_middle_hit_and_conversation_context_survive_budget(self):
        self.write_log(messages=[{"text": "needle" if i == 5 else f"message {i}",
                                  "role": "assistant" if i % 2 else "user"} for i in range(12)])
        result = self.run_search("--query", "needle", "--messages-per-role", "1")["sessions"][0]
        self.assertIn("needle", [m["text"] for m in result["messages"]])
        self.assertEqual(sorted(m["line_number"] for m in result["messages"]),
                         [m["line_number"] for m in result["messages"]])
        self.assertGreater(result["omitted_message_count"], 0)
        self.assertIn("L13", search.render_markdown(self.run_search("--query", "needle")))

    def test_every_hit_survives_soft_budget(self):
        self.write_log(messages=[{"text": f"needle {i}"} for i in range(12)])
        result = self.run_search("--query", "needle", "--messages-per-role", "1")["sessions"][0]
        self.assertEqual(12, len(result["messages"]))

    def test_far_apart_queries_have_separate_evidence_windows(self):
        self.write_log(messages=[{"text": "x" * 2000 + "alpha" + "y" * 2000 + "omega"}])
        result = self.run_search("--query", "alpha", "--query", "omega", "--max-message-chars", "80")
        message = result["sessions"][0]["messages"][0]
        self.assertTrue(message["truncated"])
        for excerpt in message["matched_excerpts"]:
            self.assertIn(excerpt["query"], excerpt["text"])
            self.assertLessEqual(len(excerpt["text"]), 80)

    def test_no_assistant_output_in_either_format(self):
        self.write_log(messages=[{"text": "user text"}, {"role": "assistant", "text": "assistant secret"}])
        result = self.run_search("--no-include-assistant")
        self.assertEqual([], result["sessions"][0]["assistant_messages"])
        self.assertNotIn("assistant secret", json.dumps(result))
        self.assertNotIn("assistant secret", search.render_markdown(result))

    def test_excerpt_contains_a_long_query_that_fits_in_window(self):
        query = "n" * 60
        self.write_log(messages=[{"text": "x" * 1000 + query + "y" * 1000}])
        result = self.run_search("--query", query, "--max-message-chars", "80")
        message = result["sessions"][0]["messages"][0]
        self.assertIn(query, message["text"])
        self.assertIn(query, message["matched_excerpts"][0]["text"])

    def test_phase_and_multiline_text_are_preserved(self):
        self.write_log(messages=[{"role": "assistant", "phase": "final_answer", "text": "done\nverified"}])
        message = self.run_search()["sessions"][0]["messages"][0]
        self.assertEqual("final_answer", message["phase"])
        self.assertEqual("done\nverified", message["text"])

    def test_hidden_matches_are_reported_without_leaking_text(self):
        self.write_log(messages=[{"text": "user text"}, {"role": "assistant", "text": "needle private detail"}])
        result = self.run_search("--no-include-assistant", "--query", "needle")
        self.assertEqual(1, result["sessions"][0]["hidden_matching_message_count"])
        self.assertNotIn("private detail", json.dumps(result))
        self.assertEqual([], self.run_search("--query-user-only", "--query", "needle")["sessions"])

    def test_query_searches_text_not_metadata(self):
        self.write_log(name="needle")
        self.assertEqual([], self.run_search("--query", "needle")["sessions"])

    def test_literal_regex_and_and_matching(self):
        self.write_log(messages=[{"text": "A.B first"}, {"text": "SECOND"}])
        self.assertEqual(1, len(self.run_search("--query", "a.b", "--query", "second")["sessions"]))
        self.assertEqual([], self.run_search("--query", "A.B", "--query", "absent")["sessions"])
        self.assertEqual(1, len(self.run_search("--regex", "--query", r"A.B.*first")["sessions"]))

    def test_full_text_preserves_newlines(self):
        text = "line one\n\n" + "long text " * 400
        self.write_log(messages=[{"text": text}])
        result = self.run_search("--messages-per-role", "0", "--max-message-chars", "0")
        self.assertEqual(text.rstrip(), result["sessions"][0]["messages"][0]["text"])
        self.assertFalse(result["sessions"][0]["messages"][0]["truncated"])

    def test_active_archived_and_all_scopes(self):
        self.write_log("active")
        self.write_log("archived", archived=True)
        self.assertEqual(["active"], [s["id"] for s in self.run_search()["sessions"]])
        self.assertEqual(["archived"], [s["id"] for s in self.run_search("--scope", "archived")["sessions"]])
        result = self.run_search("--scope", "all")
        self.assertEqual(2, result["coverage"]["files_scanned"])
        self.assertEqual({"active", "archived"}, {s["archive_status"] for s in result["sessions"]})

    def test_missing_default_archive_is_disclosed(self):
        self.archived.rmdir()
        self.write_log()
        parser = search.build_parser()
        with patch.dict(os.environ, {"CODEX_HOME": str(self.root)}):
            result = search.search(parser.parse_args(["--scope", "all"]), parser)
        self.assertFalse(result["coverage"]["roots"][1]["exists"])
        self.assertEqual(1, result["coverage"]["returned_sessions"])

    def test_empty_result_still_has_coverage(self):
        self.write_log()
        result = self.run_search("--query", "absent")
        self.assertEqual(2, result["schema_version"])
        self.assertEqual(1, result["coverage"]["files_scanned"])
        self.assertEqual([], result["sessions"])

    def test_overlapping_roots_scan_each_file_once(self):
        self.write_log()
        result = self.run_search("--scope", "all", "--archived-root", str(self.active))
        self.assertEqual(1, result["coverage"]["files_scanned"])
        self.assertEqual(1, len(result["sessions"]))

    def test_compressed_logs_are_counted_and_disclosed_but_not_read(self):
        self.write_log()
        (self.active / "2026").mkdir()
        for path in (self.active / "older.jsonl.zst", self.active / "2026" / "nested.jsonl.zst",
                     self.archived / "archived.jsonl.zst"):
            path.write_bytes(b"\x28\xb5\x2f\xfd needle")
        active = self.run_search("--query", "needle")
        self.assertEqual(2, active["coverage"]["skipped_compressed_files"])
        self.assertEqual(1, active["coverage"]["files_scanned"])
        self.assertEqual([], active["sessions"])
        self.assertIn("2 compressed `.jsonl.zst` logs were not searched", search.render_markdown(active))
        self.assertEqual(3, self.run_search("--scope", "all")["coverage"]["skipped_compressed_files"])
        overlapping = self.run_search("--scope", "all", "--archived-root", str(self.active))
        self.assertEqual(2, overlapping["coverage"]["skipped_compressed_files"])
        for path in self.root.rglob("*.zst"):
            path.unlink()
        clean = self.run_search()
        self.assertEqual(0, clean["coverage"]["skipped_compressed_files"])
        self.assertNotIn("were not searched", search.render_markdown(clean))

    def test_custom_active_root_requires_explicit_archive_root(self):
        parser = search.build_parser()
        args = parser.parse_args(["--sessions-root", str(self.active), "--scope", "all"])
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            search.search(args, parser)

    def test_message_date_cwd_and_query_use_same_subset(self):
        self.write_log(messages=[
            {"text": "old needle", "cwd": "C:/old", "timestamp": "2026-09-01T00:00:00Z"},
            {"text": "new topic", "cwd": "C:/new", "timestamp": "2026-11-01T00:00:00Z"},
        ])
        self.assertEqual([], self.run_search("--cwd-contains", "new")["sessions"])
        flags = ["--cwd-field", "message", "--cwd-contains", "new",
                 "--date-field", "message", "--date-from", "2026-11-01"]
        self.assertEqual(1, len(self.run_search(*flags)["sessions"]))
        self.assertEqual([], self.run_search(*flags, "--query", "needle")["sessions"])
        message = self.run_search(*flags)["sessions"][0]["messages"][0]
        self.assertEqual("C:/new", message["cwd"])
        self.assertEqual("1", message["turn_id"])
        self.assertEqual(5, message["line_number"])

    def test_created_updated_and_message_dates(self):
        self.write_log()
        self.assertEqual([], self.run_search("--date-from", "2026-11-01")["sessions"])
        for field in ("updated", "message"):
            self.assertEqual(1, len(self.run_search("--date-field", field, "--date-from", "2026-11-01")["sessions"]))

    def test_date_boundary_uses_explicit_offset(self):
        self.write_log(messages=[{"text": "late", "timestamp": "2026-10-31T15:01:00Z"}])
        flags = ["--date-field", "message", "--date-from", "2026-11-01"]
        self.assertEqual([], self.run_search(*flags)["sessions"])
        self.assertEqual(1, len(self.run_search(*flags, "--utc-offset=+09:00")["sessions"]))

    def test_sort_then_limit_and_total_count(self):
        self.write_log("older", created="2026-09-01T00:00:00Z",
                       messages=[{"text": "recent", "timestamp": "2026-11-01T00:00:00Z"}])
        self.write_log("newer", created="2026-10-01T00:00:00Z",
                       messages=[{"text": "older activity", "timestamp": "2026-10-01T00:00:00Z"}])
        self.assertEqual("older", self.run_search("--limit", "1")["sessions"][0]["id"])
        self.assertEqual("newer", self.run_search("--order", "desc", "--limit", "1")["sessions"][0]["id"])
        result = self.run_search("--sort-by", "updated", "--order", "desc", "--limit", "1")
        self.assertEqual("older", result["sessions"][0]["id"])
        self.assertEqual(2, result["coverage"]["matched_sessions"])

    def test_reviews_excluded_by_metadata_and_legacy_prefix(self):
        self.write_log("review", thread_source="guardian_review")
        self.write_log("wrapper", messages=[{"text": "The following is the Codex agent history wrapped"}])
        self.assertEqual([], self.run_search()["sessions"])
        self.assertEqual(2, len(self.run_search("--include-approval-reviews")["sessions"]))

    def test_duplicate_events_and_repeated_turns_preserve_provenance(self):
        path = self.write_log(messages=[{"text": "same", "turn": "one"}, {"text": "same", "turn": "two"}])
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"type": "event_msg", "payload": {"type": "user_message", "message": "same"}}) + "\n")
        result = self.run_search()["sessions"][0]
        self.assertEqual(2, len(result["messages"]))
        self.assertEqual([3, 5], [m["line_number"] for m in result["messages"]])

    def test_legacy_log_still_searchable(self):
        fixture = PLUGIN_ROOT / "tests/fixtures/chat-legacy-session.jsonl"
        (self.active / "legacy.jsonl").write_bytes(fixture.read_bytes())
        self.assertEqual("legacy-thread-0001", self.run_search()["sessions"][0]["id"])

    def test_parser_warnings_and_unknown_logs_disclosed(self):
        path = self.write_log()
        with path.open("a", encoding="utf-8") as handle:
            handle.write("{invalid\n")
        (self.active / "unknown.jsonl").write_text('{}\n', encoding="utf-8")
        with redirect_stderr(io.StringIO()) as errors:
            result = self.run_search()
        self.assertIn("warning:", errors.getvalue())
        self.assertEqual(1, result["coverage"]["parser_warnings"])
        self.assertEqual(1, result["coverage"]["unrecognized_files"])

    def test_invalid_inputs_fail_clearly(self):
        for flags in (["--regex", "--query", "["], ["--limit", "-1"], ["--query", ""],
                      ["--date-from", "2026-11-02", "--date-to", "2026-11-01"],
                      ["--utc-offset", "invalid"], ["--sessions-root", str(self.root / "absent")]):
            with self.subTest(flags=flags), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.run_search(*flags)

    def test_unreadable_encoding_does_not_hide_other_results(self):
        self.write_log()
        (self.active / "invalid-encoding.jsonl").write_bytes(b"\xff\xfe")
        with redirect_stderr(io.StringIO()):
            result = self.run_search()
        self.assertEqual(1, result["coverage"]["unreadable_files"])
        self.assertEqual(1, len(result["sessions"]))

    def test_cli_runs_from_unrelated_directory_and_only_prints_json(self):
        self.write_log()
        proc = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPT),
                               "--sessions-root", str(self.active), "--format", "json"],
                              cwd=self.root, capture_output=True, text=True, encoding="utf-8", check=True)
        self.assertEqual(2, json.loads(proc.stdout)["schema_version"])
        self.assertEqual("", proc.stderr)

    def test_output_file_matches_stdout_contract(self):
        self.write_log()
        output = self.root / "result.json"
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(0, search.main(["--sessions-root", str(self.active),
                                            "--format", "json", "--output", str(output)]))
        self.assertEqual("", stdout.getvalue())
        self.assertEqual(1, len(json.loads(output.read_text(encoding="utf-8"))["sessions"]))


if __name__ == "__main__":
    unittest.main()
