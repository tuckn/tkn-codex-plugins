#!/usr/bin/env python3
"""Search local Codex conversation text and return traceable matching evidence."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from contextlib import redirect_stderr
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
PLUGIN_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from tkn_codex_context.chat_logs import (  # noqa: E402
    ChatMessage,
    SessionLog,
    default_sessions_root,
    is_approval_review,
    normalize_path_text,
    read_session,
)


def nonnegative(value: str) -> int:
    result = int(value)
    if result < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return result


def parse_offset(value: str) -> timezone:
    if not re.fullmatch(r"[+-](?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
        raise argparse.ArgumentTypeError("use a UTC offset such as +09:00 or -05:00")
    minutes = int(value[1:3]) * 60 + int(value[4:])
    return timezone(timedelta(minutes=minutes if value[0] == "+" else -minutes))


def timestamp(value: str) -> datetime | None:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except ValueError:
        return None


def latest_timestamp(session: SessionLog) -> str:
    values = [session.timestamp, *(m.timestamp for m in session.messages)]
    return max(values, key=lambda value: timestamp(value) or datetime.min.replace(tzinfo=timezone.utc))


def date_matches(value: str, args: argparse.Namespace) -> bool:
    if not args.date_from and not args.date_to:
        return True
    parsed = timestamp(value)
    if parsed is None:
        return False
    day = parsed.astimezone(args.utc_offset).date()
    return (not args.date_from or day >= args.date_from) and (not args.date_to or day <= args.date_to)


def cwd_matches(value: str, args: argparse.Namespace) -> bool:
    normalized = normalize_path_text(value)
    return all(normalize_path_text(part) in normalized for part in args.cwd_contains)


def clip(text: str, limit: int, center: int = 0) -> tuple[str, bool, int, int]:
    if limit == 0 or len(text) <= limit:
        return text, False, 0, len(text)
    start = min(max(0, center - limit // 2), len(text) - limit)
    end = start + limit
    return text[start:end], True, start, end


def message_data(message: ChatMessage, hits: list[tuple[str, re.Match[str]]], args: argparse.Namespace) -> dict[str, Any]:
    data = asdict(message)
    center = (hits[0][1].start() + hits[0][1].end()) // 2 if hits else 0
    text, truncated, start, end = clip(message.text, args.max_message_chars, center)
    data.update(text=text, truncated=truncated, text_start=start, text_end=end)
    data["matched_queries"] = [query for query, _ in hits]
    # Separate windows retain evidence when different queries occur far apart.
    data["matched_excerpts"] = []
    for query, match in hits:
        center = (match.start() + match.end()) // 2
        excerpt, shortened, first, last = clip(message.text, args.max_message_chars, center)
        data["matched_excerpts"].append({
            "query": query, "text": excerpt, "start": first, "end": last,
            "match_start": match.start(), "match_end": match.end(),
            "truncated": shortened,
        })
    return data


def search_session(session: SessionLog, args: argparse.Namespace) -> dict[str, Any] | None:
    if args.thread_id and session.id not in args.thread_id:
        return None
    if not args.include_approval_reviews and (
        session.thread_source in {"approval_review", "guardian_review"} or is_approval_review(session)
    ):
        return None
    if args.cwd_field == "session" and not cwd_matches(session.cwd, args):
        return None
    updated = latest_timestamp(session)
    if args.date_field != "message" and not date_matches(
        updated if args.date_field == "updated" else session.timestamp, args
    ):
        return None

    eligible: list[ChatMessage] = [
        m for m in session.messages
        if (args.cwd_field != "message" or cwd_matches(m.cwd or session.cwd, args))
        and (args.date_field != "message" or date_matches(m.timestamp, args))
    ]
    if not eligible:
        return None
    hits: dict[int, list[tuple[str, re.Match[str]]]] = {}
    matched_queries: set[str] = set()
    for index, message in enumerate(eligible):
        if args.query_user_only and message.role != "user":
            continue
        found = [(query, match) for query, pattern in args.patterns
                 if (match := pattern.search(message.text)) is not None]
        if found:
            hits[index] = found
            matched_queries.update(query for query, _ in found)
    if any(query not in matched_queries for query in args.query):
        return None

    visible = [i for i, m in enumerate(eligible) if args.include_assistant or m.role != "assistant"]
    visible_set = set(visible)
    required = set(hits) & visible_set
    if args.messages_per_role == 0:
        selected = visible_set
    else:
        selected = set(required)
        # Budgets are soft for matches: every matching message survives selection.
        nearby: set[int] = set()
        for index in required:
            nearby.update(range(max(0, index - args.context_messages),
                                min(len(eligible), index + args.context_messages + 1)))
        priorities = sorted(nearby & visible_set, key=lambda i: (min(abs(i - h) for h in required), i))
        # When there is no query, retain the earlier head/tail overview.
        for role in ("user", "assistant"):
            indices = [i for i in visible if eligible[i].role == role]
            head = (args.messages_per_role + 1) // 2
            tail = args.messages_per_role // 2
            priorities.extend(indices[:head] + (indices[-tail:] if tail else []))
        counts = {role: sum(eligible[i].role == role for i in selected) for role in ("user", "assistant")}
        for index in priorities:
            role = eligible[index].role
            if index not in selected and counts[role] < args.messages_per_role:
                selected.add(index)
                counts[role] += 1
    messages = [message_data(eligible[i], hits.get(i, []), args) for i in sorted(selected)]
    return {
        "id": session.id, "timestamp": session.timestamp, "updated": updated,
        "cwd": session.cwd, "path": session.path, "originator": session.originator,
        "source": session.source, "thread_source": session.thread_source,
        "matched_queries": [query for query in args.query if query in matched_queries],
        "eligible_message_count": len(eligible),
        "omitted_message_count": len(visible) - len(selected),
        "hidden_matching_message_count": len(set(hits) - visible_set),
        "messages": messages,
        "user_messages": [m for m in messages if m["role"] == "user"],
        "assistant_messages": [m for m in messages if m["role"] == "assistant"],
    }


def render_markdown(report: dict[str, Any]) -> str:
    coverage = report["coverage"]
    lines = ["# Codex Chat Search Results", "",
             f"Matched sessions: {coverage['matched_sessions']}; returned: {coverage['returned_sessions']}", "",
             "## Search coverage", "", f"- scope: {coverage['scope']}",
             f"- files scanned: {coverage['files_scanned']}",
             f"- unreadable files: {coverage['unreadable_files']}",
             f"- logs without metadata: {coverage['unrecognized_files']}",
             f"- parser warnings: {coverage['parser_warnings']}",
             "- Scope is local conversation text; remote/cloud history and tool outputs are not searched."]
    for root in coverage["roots"]:
        lines.append(f"- {root['kind']}: `{root['path']}` (exists: {root['exists']})")
    lines.extend(["", "Filters:", "", "```json", json.dumps(report["filters"], ensure_ascii=False, indent=2), "```"])
    for session in report["sessions"]:
        lines.extend(["", "---", "", f"## {session['id']}", "",
                      f"- path: `{session['path']}`", f"- cwd: `{session['cwd']}`",
                      f"- created: {session['timestamp']}; latest message: {session['updated']}",
                      f"- omitted visible messages: {session['omitted_message_count']}",
                      f"- matching messages hidden by role filter: {session['hidden_matching_message_count']}", ""])
        for message in session["messages"]:
            lines.extend([
                f"### {message['role']} | {message['timestamp']} | L{message['line_number']}", "",
                f"- turn: `{message['turn_id']}`; phase: `{message['phase']}`; cwd: `{message['cwd']}`", "",
            ])
            windows = message["matched_excerpts"] or [message]
            for window in windows:
                if "query" in window:
                    lines.append(f"Match: {window['query']}")
                if window["truncated"]:
                    lines.append("(excerpt; text shortened)")
                # Quote log content as evidence; preserve code and paragraph line breaks.
                lines.extend("> " + line for line in window["text"].splitlines())
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions-root", help="Active log root; defaults to CODEX_HOME/sessions.")
    parser.add_argument("--archived-root", help="Archive root; defaults to CODEX_HOME/archived_sessions.")
    parser.add_argument("--scope", choices=["active", "archived", "all"], default="active")
    parser.add_argument("--cwd-contains", action="append", default=[])
    parser.add_argument("--cwd-field", choices=["session", "message"], default="session")
    parser.add_argument("--query", action="append", default=[], help="Repeated queries use AND across eligible messages.")
    parser.add_argument("--regex", action="store_true")
    parser.add_argument("--query-user-only", action="store_true")
    parser.add_argument("--thread-id", action="append", default=[])
    parser.add_argument("--date-from", type=date.fromisoformat)
    parser.add_argument("--date-to", type=date.fromisoformat)
    parser.add_argument("--date-field", choices=["created", "updated", "message"], default="created")
    parser.add_argument("--utc-offset", type=parse_offset, default=parse_offset("+00:00"),
                        help="Offset for date boundaries, e.g. --utc-offset=+09:00. Default UTC.")
    parser.add_argument("--include-approval-reviews", action="store_true")
    parser.add_argument("--include-assistant", action=argparse.BooleanOptionalAction, default=True,
                        help="Controls display only; use --query-user-only to restrict matching.")
    parser.add_argument("--messages-per-role", type=nonnegative, default=8,
                        help="Soft display budget; matches always retained. 0 includes all eligible messages.")
    parser.add_argument("--context-messages", type=nonnegative, default=1)
    parser.add_argument("--max-message-chars", type=nonnegative, default=1200,
                        help="Characters per excerpt; 0 disables truncation.")
    parser.add_argument("--sort-by", choices=["created", "updated"], default="created")
    parser.add_argument("--order", choices=["asc", "desc"], default="asc")
    parser.add_argument("--limit", type=nonnegative, default=0, help="Session limit after sorting; 0 means unlimited.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output")
    return parser


def search(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict[str, Any]:
    if args.date_from and args.date_to and args.date_from > args.date_to:
        parser.error("--date-from must be on or before --date-to")
    try:
        args.patterns = [(q, re.compile(q if args.regex else re.escape(q), re.IGNORECASE | re.MULTILINE))
                         for q in dict.fromkeys(args.query)]
    except re.error as exc:
        parser.error(f"invalid query regex: {exc}")
    if any(not q for q in args.query):
        parser.error("--query must not be empty")
    if args.sessions_root and args.scope != "active" and not args.archived_root:
        parser.error("with a custom --sessions-root, supply --archived-root for archived/all scope")
    default_root = default_sessions_root()
    roots = {
        "active": Path(args.sessions_root).expanduser() if args.sessions_root else default_root,
        "archived": Path(args.archived_root).expanduser() if args.archived_root else default_root.parent / "archived_sessions",
    }
    kinds = ["active", "archived"] if args.scope == "all" else [args.scope]
    coverage: dict[str, Any] = {
        "scope": args.scope,
        "roots": [{"kind": kind, "path": str(roots[kind].absolute()), "exists": roots[kind].is_dir()} for kind in kinds],
        "files_scanned": 0, "unreadable_files": 0, "unrecognized_files": 0,
        "parser_warnings": 0, "matched_sessions": 0, "returned_sessions": 0,
        "excluded": ["remote/cloud history", "tool calls and outputs", "non-text content"],
    }
    # An absent archive is normal; an explicit typo must not look like a zero-result search.
    for kind in kinds:
        explicit = args.sessions_root if kind == "active" else args.archived_root
        if explicit and not roots[kind].is_dir():
            parser.error(f"{kind} root not found: {roots[kind]}")
    if not any(root["exists"] for root in coverage["roots"]):
        parser.error("no selected log roots exist")
    sessions: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()
    for kind in kinds:
        root = roots[kind]
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.jsonl")):
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            coverage["files_scanned"] += 1
            diagnostics = io.StringIO()
            try:
                with redirect_stderr(diagnostics):
                    session = read_session(path)
            except (OSError, UnicodeError) as exc:
                coverage["unreadable_files"] += 1
                print(f"warning: {path}: {exc}", file=sys.stderr)
                continue
            finally:
                warnings = diagnostics.getvalue()
                coverage["parser_warnings"] += len(warnings.splitlines())
                if warnings:
                    print(warnings, end="", file=sys.stderr)
            if session is None:
                coverage["unrecognized_files"] += 1
                continue
            result = search_session(session, args)
            if result is not None:
                result["archive_status"] = kind
                sessions.append(result)
    key = "updated" if args.sort_by == "updated" else "timestamp"
    sessions.sort(key=lambda s: (timestamp(s[key]) or datetime.min.replace(tzinfo=timezone.utc), s["id"], s["path"]),
                  reverse=args.order == "desc")
    coverage["matched_sessions"] = len(sessions)
    if args.limit:
        sessions = sessions[:args.limit]
    coverage["returned_sessions"] = len(sessions)
    filters = {key: getattr(args, key) for key in (
        "query", "regex", "query_user_only", "thread_id", "cwd_contains", "cwd_field",
        "date_field", "include_approval_reviews", "include_assistant", "messages_per_role",
        "context_messages", "max_message_chars", "sort_by", "order", "limit",
    )}
    filters.update(date_from=str(args.date_from or ""), date_to=str(args.date_to or ""), utc_offset=str(args.utc_offset))
    return {"schema_version": 2, "coverage": coverage, "filters": filters, "sessions": sessions}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = search(args, parser)
    output = (json.dumps(report, ensure_ascii=False, indent=2) + "\n"
              if args.format == "json" else render_markdown(report))
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
