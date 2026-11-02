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

SCRIPT = Path(__file__).resolve().parents[1] / "skills/search-all-claude-code-chats/scripts/search_all_claude_code_chats.py"
SPEC = importlib.util.spec_from_file_location("search_all_claude_code_chats", SCRIPT)
assert SPEC and SPEC.loader
search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(search)


class ClaudeCodeChatSearchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="claude-chat-search-test-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / "projects"
        self.project = self.root / "encoded-project"
        self.project.mkdir(parents=True)

    def message(self, text="request", *, role="user", uuid="u1", **metadata):
        return {"type": role, "message": {"role": role, "content": text}, "uuid": uuid,
                "sessionId": "example", "parentUuid": None, "isSidechain": False,
                "timestamp": "2026-11-01T00:00:00Z", "cwd": "C:/work/example-project", **metadata}

    def write_log(self, records=None, *, relative="example.jsonl", project=None):
        path = (project or self.project) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in
                                 (records if records is not None else [self.message()])) + "\n", encoding="utf-8")
        return path

    def run_search(self, *options):
        parser = search.build_parser()
        return search.search(parser.parse_args(["--projects-root", str(self.root), *options]), parser)

    def first(self, *options):
        return self.run_search(*options)["sessions"][0]

    def test_text_blocks_and_provenance_without_nested_tool_or_thinking_text(self):
        path = self.write_log([
            {"type": "api-request-blob", "message": {"role": "assistant", "content": "hidden request"}},
            self.message("構成\n```python\nprint(1)\n```"),
            self.message([
                {"type": "thinking", "thinking": "hidden reasoning", "text": "hidden thinking text"},
                {"type": "text", "text": "Answer"},
                {"type": "tool_use", "input": {"text": "hidden input"}},
                {"type": "text", "text": "Done"},
            ], role="assistant", uuid="a1", parentUuid="u1"),
            self.message([{"type": "tool_result", "content": [{"type": "text", "text": "hidden output"}]}], uuid="tool"),
        ])
        result = self.first()
        self.assertEqual(str(path.absolute()), result["path"])
        self.assertEqual([2, 3], [m["line_number"] for m in result["messages"]])
        self.assertEqual("u1", result["messages"][1]["parent_uuid"])
        self.assertEqual("Answer\nDone", result["messages"][1]["text"])
        self.assertIn("\n```python\n", result["messages"][0]["text"])
        self.assertNotIn("hidden ", json.dumps(result))
        self.assertEqual([], self.run_search("--query", "hidden")["sessions"])

    def test_exact_duplicate_uuid_only_and_physical_order(self):
        first = self.message("same", timestamp="2026-11-02T00:00:00Z")
        self.write_log([first, first, self.message("same", uuid="u2", timestamp="2026-11-01T00:00:00Z"),
                        self.message("changed", uuid="u1"), self.message("no id", uuid=None),
                        self.message("no id", uuid=None)])
        result = self.run_search()
        messages = result["sessions"][0]["messages"]
        self.assertEqual([1, 3, 4, 5, 6], [m["line_number"] for m in messages])
        self.assertEqual(1, result["coverage"]["duplicate_messages"])
        self.assertEqual("2026-11-01T00:00:00Z", result["sessions"][0]["created"])
        self.assertEqual("2026-11-02T00:00:00Z", result["sessions"][0]["updated"])

    def test_generated_context_and_compaction_are_not_original_user_requests(self):
        self.write_log([self.message("meta needle", isMeta=True),
                        self.message("compact needle", uuid="c", isCompactSummary=True),
                        {"type": "system", "subtype": "compact_boundary"}, self.message("ordinary", uuid="u2")])
        result = self.run_search()
        self.assertEqual(2, result["coverage"]["excluded_generated_messages"])
        self.assertEqual(1, result["coverage"]["ignored_record_types"]["system"])
        self.assertEqual([], self.run_search("--query", "needle")["sessions"])

    def test_queries_are_and_across_messages_and_do_not_match_metadata(self):
        self.write_log([self.message("ALPHA"), self.message("beta", role="assistant", uuid="a1")])
        self.assertEqual(1, len(self.run_search("--query", "alpha", "--query", "beta")["sessions"]))
        self.assertEqual([], self.run_search("--query", "example-project")["sessions"])
        self.assertEqual([], self.run_search("--query", "alpha", "--query", "absent")["sessions"])
        self.assertEqual([], self.run_search("--query", "beta", "--query-user-only")["sessions"])

    def test_regex_is_opt_in(self):
        self.write_log([self.message("alpha\nBETA")])
        self.assertEqual([], self.run_search("--query", "^beta$")["sessions"])
        self.assertEqual(1, len(self.run_search("--query", "^beta$", "--regex")["sessions"]))

    def test_hidden_assistant_hits_do_not_leak_in_either_format(self):
        self.write_log([self.message("public"), self.message("private needle", role="assistant", uuid="a")])
        report = self.run_search("--query", "needle", "--no-include-assistant")
        self.assertEqual(1, report["sessions"][0]["hidden_matching_message_count"])
        self.assertEqual(["user"], [m["role"] for m in report["sessions"][0]["messages"]])
        self.assertNotIn("private needle", json.dumps(report))
        self.assertNotIn("private needle", search.render_markdown(report))

    def test_middle_match_and_neighbor_have_priority_over_overview(self):
        self.write_log([self.message("needle" if i == 5 else f"message {i}", uuid=str(i),
                                     role="user" if i % 2 else "assistant") for i in range(12)])
        result = self.first("--query", "needle", "--messages-per-role", "1")
        self.assertEqual([5, 6], [m["line_number"] for m in result["messages"]])
        self.assertEqual(10, result["omitted_message_count"])
        self.assertIn("L6", search.render_markdown(self.run_search("--query", "needle")))

    def test_all_matches_survive_soft_budget_and_distant_queries_have_windows(self):
        self.write_log([self.message("needle " + str(i), uuid=str(i)) for i in range(12)])
        self.assertEqual(12, len(self.first("--query", "needle", "--messages-per-role", "1")["messages"]))
        self.write_log([self.message("x" * 2000 + "alpha" + "y" * 2000 + "omega")])
        message = self.first("--query", "alpha", "--query", "omega", "--max-message-chars", "80")["messages"][0]
        self.assertTrue(message["truncated"])
        for window in message["matched_excerpts"]:
            self.assertIn(window["query"], window["text"])
            self.assertLessEqual(len(window["text"]), 80)
            self.assertEqual(window["query"], ("x" * 2000 + "alpha" + "y" * 2000 + "omega")[window["match_start"]:window["match_end"]])

    def test_full_retrieval_disables_both_budgets(self):
        records = [self.message("long " + "x" * 1500, uuid=str(i)) for i in range(20)]
        self.write_log(records)
        result = self.first("--session-id", "example", "--messages-per-role", "0", "--max-message-chars", "0")
        self.assertEqual(20, len(result["messages"]))
        self.assertFalse(any(m["truncated"] for m in result["messages"]))
        self.assertEqual(0, result["omitted_message_count"])

    def test_recorded_title_and_inherited_session_ids_do_not_reassign_destination(self):
        self.write_log([self.message("inherited", sessionId="old"),
                        {"type": "custom-title", "sessionId": "example", "customTitle": "First title"},
                        {"type": "custom-title", "sessionId": "old", "customTitle": "Wrong title"},
                        {"type": "custom-title", "sessionId": "example", "customTitle": "Recorded title"},
                        self.message("new", uuid="u2")])
        result = self.first("--session-id", "example")
        self.assertEqual("Recorded title", result["title"])
        self.assertEqual([("First title", 2), ("Recorded title", 4)],
                         [(t["title"], t["line_number"]) for t in result["title_history"]])
        self.assertEqual(["example", "old"], result["recorded_session_ids"])
        self.assertEqual("old", result["messages"][0]["session_id"])
        self.assertEqual([], self.run_search("--session-id", "old")["sessions"])
        self.assertEqual([], self.run_search("--query", "Recorded title")["sessions"])
        self.assertEqual([], self.run_search("--title", "Wrong title")["sessions"])

    def write_titled(self, name, records):
        return self.write_log([self.message(f"{name} body", sessionId=name), *[
            {"type": kind, "sessionId": name, field: value} for kind, field, value in records]],
            relative=f"{name}.jsonl")

    def test_title_matches_custom_ai_and_earlier_titles_ignoring_case_width_and_spaces(self):
        self.write_titled("shared", [("ai-title", "aiTitle", "Share plugin settings"),
                                     ("custom-title", "customTitle", "Plugin設定をチームに共有する方法")])
        self.write_titled("renamed", [("custom-title", "customTitle", "起動後の重い処理"),
                                      ("custom-title", "customTitle", "Plugin起動エラー")])
        self.write_titled("side", [("custom-title", "customTitle", "btw: エラーになります…")])
        self.write_titled("untitled", [])
        ids = lambda *options: sorted(s["id"] for s in self.run_search(*options)["sessions"])
        self.assertEqual(["shared"], ids("--title", "PLUGIN設定"))
        self.assertEqual(["shared"], ids("--title", "Ｐｌｕｇｉｎ　設定を チーム"))
        self.assertEqual(["shared"], ids("--title", "share plugin"))
        self.assertEqual(["renamed", "shared"], ids("--title", "plugin"))
        self.assertEqual(["shared"], ids("--title", "plugin", "--title", "共有"))
        self.assertEqual(["side"], ids("--title", "エラーになります..."))
        self.assertEqual([], ids("--title", "absent"))
        renamed = self.first("--title", "起動後 の")
        self.assertEqual("Plugin起動エラー", renamed["title"])
        self.assertEqual("", renamed["ai_title"])
        self.assertEqual([{"source": "custom-title", "title": "起動後の重い処理", "line_number": 2}],
                         renamed["matched_titles"])
        shared = self.first("--title", "share")
        self.assertEqual(("Plugin設定をチームに共有する方法", "Share plugin settings"),
                         (shared["title"], shared["ai_title"]))
        self.assertEqual(["ai-title"], [t["source"] for t in shared["matched_titles"]])

    def test_title_combines_with_query_and_query_still_ignores_titles(self):
        self.write_titled("shared", [("custom-title", "customTitle", "Plugin設定をチームに共有する方法")])
        self.assertEqual(1, len(self.run_search("--title", "plugin", "--query", "shared body")["sessions"]))
        self.assertEqual([], self.run_search("--title", "plugin", "--query", "absent")["sessions"])
        report = self.run_search("--query", "Plugin設定")
        self.assertEqual([], report["sessions"])
        self.assertIn("retry with `--title`", search.render_markdown(report))
        titled = self.run_search("--title", "Plugin設定")
        self.assertEqual(["Plugin設定"], titled["filters"]["title"])
        markdown = search.render_markdown(titled)
        self.assertIn('- matched titles: "Plugin設定をチームに共有する方法" (custom-title, L2)', markdown)
        self.assertNotIn("retry with", markdown)

    def test_nested_and_legacy_agents_are_separate_and_opt_in(self):
        self.write_log()
        self.write_log([self.message("nested", isSidechain=True, agentId="a")], relative="example/subagents/agent-a.jsonl")
        self.write_log([self.message("legacy", isSidechain=True)], relative="agent-b.jsonl")
        result = self.run_search()
        self.assertEqual(1, len(result["sessions"]))
        self.assertEqual(2, result["coverage"]["excluded_subagent_files"])
        included = self.run_search("--include-subagents", "--session-id", "example")
        self.assertEqual(3, len(included["sessions"]))
        agents = {s["agent_id"]: s for s in included["sessions"] if s["kind"] == "subagent"}
        self.assertEqual({"a", "b"}, set(agents))
        self.assertEqual("example", agents["a"]["parent_session_id"])
        self.assertEqual("example", agents["b"]["parent_session_id"])

    def test_inline_sidechains_are_excluded_and_tagged_when_included(self):
        self.write_log([self.message("main"), self.message("side needle", uuid="s", isSidechain=True)])
        self.assertEqual(1, self.run_search()["coverage"]["excluded_sidechain_messages"])
        self.assertEqual([], self.run_search("--query", "needle")["sessions"])
        result = self.first("--include-subagents", "--query", "needle")
        self.assertTrue(result["messages"][1]["is_sidechain"])

    def test_discovery_does_not_search_spilled_tools_memory_or_history(self):
        self.write_log()
        self.write_log([self.message("hidden")], relative="example/tool-results/spilled.jsonl")
        self.write_log([self.message("hidden")], relative="memory/copied.jsonl")
        self.write_log([self.message("hidden")], relative="example/mcp-tasks/copied.jsonl")
        self.write_log([self.message("hidden")], project=self.root, relative="history.jsonl")
        result = self.run_search("--include-subagents")
        self.assertEqual(1, result["coverage"]["files_scanned"])
        self.assertEqual([], self.run_search("--query", "hidden")["sessions"])

    def test_set_aside_logs_need_explicit_file_selection(self):
        self.write_log()
        path = self.write_log([self.message("parked needle")], relative="example.orphaned-123-ab.jsonl")
        result = self.run_search("--query", "needle")
        self.assertEqual([], result["sessions"])
        self.assertEqual(1, result["coverage"]["excluded_set_aside_files"])
        parser = search.build_parser()
        selected = search.search(parser.parse_args(["--session-file", str(path)]), parser)
        self.assertEqual("example", selected["sessions"][0]["id"])
        self.assertEqual(1, selected["coverage"]["files_scanned"])

    def test_message_cwd_and_date_filters_apply_to_the_same_message(self):
        self.write_log([self.message("old needle", cwd="C:/old", timestamp="2026-10-31T14:59:59Z"),
                        self.message("new needle", uuid="u2", cwd="C:\\new", timestamp="2026-10-31T15:00:00Z")])
        options = ("--date-field", "message", "--date-from", "2026-11-01", "--date-to", "2026-11-01", "--utc-offset=+09:00")
        self.assertEqual([], self.run_search(*options, "--cwd-field", "message", "--cwd-contains", "old")["sessions"])
        result = self.first(*options, "--cwd-field", "message", "--cwd-contains", "c:/NEW/")
        self.assertEqual(["new needle"], [m["text"] for m in result["messages"]])
        self.assertEqual([], self.run_search(*options, "--query", "old")["sessions"])

    def test_created_updated_and_ordering_before_limit(self):
        self.write_log([self.message(timestamp="2026-10-01T00:00:00Z"),
                        self.message("recent", uuid="u2", timestamp="2026-11-02T00:00:00Z")])
        self.write_log([self.message("second", timestamp="2026-11-01T00:00:00Z")], relative="second.jsonl")
        result = self.run_search("--limit", "1")
        self.assertEqual(2, result["coverage"]["matched_sessions"])
        self.assertEqual("example", result["sessions"][0]["id"])
        self.assertEqual("second", self.first("--sort-by", "created", "--order", "desc", "--limit", "1")["id"])
        self.assertEqual(1, len(self.run_search("--date-field", "updated", "--date-from", "2026-11-02")["sessions"]))
        self.assertEqual([], self.run_search("--date-from", "2026-11-02")["sessions"])

    def test_missing_values_stay_missing_and_invalid_dates_do_not_match(self):
        self.write_log([{"type": "user", "message": {"content": "bare"}},
                        self.message("invalid", uuid="u2", timestamp="invalid")])
        result = self.first()
        for field in ("timestamp", "uuid", "parent_uuid", "cwd", "session_id"):
            self.assertEqual("", result["messages"][0][field])
        self.assertEqual([], self.run_search("--date-field", "message", "--date-from", "2026-01-01")["sessions"])

    def test_bad_records_warn_without_exposing_raw_data_or_breaking_json_stdout(self):
        path = self.write_log()
        with path.open("a", encoding="utf-8") as stream:
            stream.write('bad private raw record\n[]\n{"type":"user","message":null}\n')
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(0, search.main(["--projects-root", str(self.root), "--format", "json"]))
        report = json.loads(out.getvalue())
        self.assertEqual(3, report["coverage"]["parser_warnings"])
        self.assertIn(":L2:", err.getvalue())
        self.assertNotIn("private raw", err.getvalue())
        self.assertEqual(1, len(report["sessions"][0]["messages"]))

    def test_unreadable_file_is_counted_and_does_not_abort_other_results(self):
        self.write_log()
        path = self.write_log(relative="bad.jsonl")
        path.write_bytes(b'\xff\xfe\xfd')
        with redirect_stderr(io.StringIO()):
            report = self.run_search()
        self.assertEqual(1, report["coverage"]["unreadable_files"])
        self.assertEqual(1, len(report["sessions"]))

    def test_bom_and_files_without_supported_messages(self):
        path = self.write_log([self.message("日本語")])
        path.write_bytes(b'\xef\xbb\xbf' + path.read_bytes())
        self.write_log([{"type": "future-record", "text": "not conversation"}], relative="future.jsonl")
        report = self.run_search()
        self.assertEqual("日本語", report["sessions"][0]["messages"][0]["text"])
        self.assertEqual(1, report["coverage"]["files_without_messages"])

    def test_multiple_roots_and_duplicate_selection_keep_distinct_sources(self):
        self.write_log()
        second = self.base / "other-projects"
        self.write_log(project=second / "encoded-project")
        parser = search.build_parser()
        args = parser.parse_args(["--projects-root", str(self.root), "--projects-root", str(second),
                                  "--projects-root", str(self.root)])
        report = search.search(args, parser)
        self.assertEqual(2, report["coverage"]["files_scanned"])
        self.assertEqual(2, len(report["sessions"]))
        self.assertNotEqual(report["sessions"][0]["path"], report["sessions"][1]["path"])

    def test_environment_default_and_explicit_file_ignore_other_home(self):
        path = self.write_log()
        parser = search.build_parser()
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.base)}):
            self.assertEqual(1, len(search.search(parser.parse_args([]), parser)["sessions"]))
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.base / "missing")}):
            args = parser.parse_args(["--session-file", str(path), "--session-file", str(path)])
            self.assertEqual(1, search.search(args, parser)["coverage"]["files_scanned"])

    def test_invalid_arguments_fail_clearly(self):
        cases = [("--query", ""), ("--title", ""), ("--title", " 　 "), ("--regex", "--query", "["), ("--limit", "-1"),
                 ("--utc-offset=+24:00",), ("--date-from", "2026-11-02", "--date-to", "2026-11-01"),
                 ("--projects-root", str(self.base / "missing"))]
        for options in cases:
            with self.subTest(options=options), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                self.run_search(*options)
            self.assertEqual(2, raised.exception.code)
        parser = search.build_parser()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["--projects-root", str(self.root), "--session-file", "file.jsonl"])

    def test_standalone_cli_is_read_only_and_works_from_unrelated_cwd(self):
        path = self.write_log([self.message("local evidence")])
        before = {p.relative_to(self.base): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        completed = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPT), "--session-file", str(path),
                                    "--query", "evidence", "--format", "json"], cwd=self.base,
                                   capture_output=True, text=True, encoding="utf-8", check=True)
        report = json.loads(completed.stdout)
        self.assertEqual("claude-code", report["source"])
        self.assertEqual(1, report["schema_version"])
        self.assertEqual("local evidence", report["sessions"][0]["messages"][0]["text"])
        self.assertEqual("", completed.stderr)
        after = {p.relative_to(self.base): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
