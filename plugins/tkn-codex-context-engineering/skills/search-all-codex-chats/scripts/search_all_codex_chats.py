#!/usr/bin/env python3
"""Search all Codex JSONL chats stored on this computer and return concise matching evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
PLUGIN_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from tkn_codex_context.chat_logs import (  # noqa: E402
    APPROVAL_REVIEW_PREFIX,
    default_sessions_root,
    normalize_message_text,
    normalize_path_text,
    read_session as read_session_log,
)


@dataclass
class Message:
    role: str
    source: str
    text: str


@dataclass
class ChatMatch:
    id: str
    timestamp: str
    cwd: str
    path: str
    originator: str
    source: str
    user_messages: list[Message]
    assistant_messages: list[Message]
    matched_queries: list[str]


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def parse_timestamp_date(value: str) -> date | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return None


def read_session(path: Path) -> ChatMatch | None:
    session = read_session_log(path)
    if not session:
        return None
    return ChatMatch(
        id=session.id,
        timestamp=session.timestamp,
        cwd=session.cwd,
        path=session.path,
        originator=session.originator,
        source=session.source,
        user_messages=[Message(m.role, m.source, m.text) for m in session.user_messages],
        assistant_messages=[Message(m.role, m.source, m.text) for m in session.assistant_messages],
        matched_queries=[],
    )


def is_approval_review(session: ChatMatch) -> bool:
    return any(
        message.text.lstrip().startswith(APPROVAL_REVIEW_PREFIX)
        for message in session.user_messages
    )


def all_text(session: ChatMatch, include_assistant: bool) -> str:
    parts = [session.cwd, session.id, session.timestamp]
    parts.extend(message.text for message in session.user_messages)
    if include_assistant:
        parts.extend(message.text for message in session.assistant_messages)
    return "\n".join(parts)


def query_matches(text: str, queries: list[str], regex: bool) -> list[str]:
    if not queries:
        return []
    matched: list[str] = []
    if regex:
        for query in queries:
            if re.search(query, text, flags=re.IGNORECASE | re.MULTILINE):
                matched.append(query)
    else:
        folded = text.casefold()
        for query in queries:
            if query.casefold() in folded:
                matched.append(query)
    return matched


def passes_filters(session: ChatMatch, args: argparse.Namespace) -> bool:
    if args.thread_id and session.id not in args.thread_id:
        return False
    if args.cwd_contains:
        cwd = normalize_path_text(session.cwd)
        if not all(normalize_path_text(value) in cwd for value in args.cwd_contains):
            return False
    session_date = parse_timestamp_date(session.timestamp)
    if args.date_from and (not session_date or session_date < args.date_from):
        return False
    if args.date_to and (not session_date or session_date > args.date_to):
        return False
    if not args.include_approval_reviews and is_approval_review(session):
        return False
    haystack = all_text(session, include_assistant=not args.query_user_only)
    matched = query_matches(haystack, args.query, args.regex)
    if args.query and len(matched) != len(args.query):
        return False
    session.matched_queries = matched
    return True


def truncate(text: str, limit: int) -> str:
    text = normalize_message_text(text)
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "..."


def select_messages(messages: list[Message], per_role: int) -> list[Message]:
    if per_role == 0:
        return messages
    if per_role < 0:
        return []
    if len(messages) <= per_role:
        return messages
    head = max(1, per_role // 2)
    tail = per_role - head
    if tail <= 0:
        return messages[:head]
    return messages[:head] + messages[-tail:]


def render_markdown(sessions: list[ChatMatch], args: argparse.Namespace) -> str:
    lines = [
        "# Codex Chat Search Results", "", f"Matched sessions: {len(sessions)}", "", "Filters:",
        f"- sessions_root: `{args.sessions_root}`", f"- cwd_contains: {args.cwd_contains or []}",
        f"- query: {args.query or []}", f"- thread_id: {args.thread_id or []}",
        f"- date_from: {args.date_from or ''}", f"- date_to: {args.date_to or ''}", "",
    ]
    for index, session in enumerate(sessions, 1):
        lines.extend([
            "---", "", f"## {index}. {session.timestamp or '(no timestamp)'}", "",
            f"- id: `{session.id}`", f"- cwd: `{session.cwd}`", f"- path: `{session.path}`",
            f"- originator: `{session.originator}`", f"- source: `{session.source}`",
            f"- matched_queries: {session.matched_queries}", "", "### User Messages", "",
        ])
        for message in select_messages(session.user_messages, args.messages_per_role):
            lines.append(f"- {truncate(message.text, args.max_message_chars)}")
        if not session.user_messages:
            lines.append("- (none found)")
        if args.include_assistant:
            lines.extend(["", "### Assistant Messages", ""])
            for message in select_messages(session.assistant_messages, args.messages_per_role):
                lines.append(f"- {truncate(message.text, args.max_message_chars)}")
            if not session.assistant_messages:
                lines.append("- (none found)")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def to_jsonable(session: ChatMatch, args: argparse.Namespace) -> dict[str, Any]:
    data = asdict(session)
    data["user_messages"] = [
        asdict(Message(m.role, m.source, truncate(m.text, args.max_message_chars)))
        for m in select_messages(session.user_messages, args.messages_per_role)
    ]
    data["assistant_messages"] = [
        asdict(Message(m.role, m.source, truncate(m.text, args.max_message_chars)))
        for m in select_messages(session.assistant_messages, args.messages_per_role)
    ]
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions-root", default=str(default_sessions_root()))
    parser.add_argument("--cwd-contains", action="append", default=[])
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--regex", action="store_true", help="Treat --query values as regular expressions.")
    parser.add_argument("--query-user-only", action="store_true", help="Search only user messages for --query.")
    parser.add_argument("--thread-id", action="append", default=[])
    parser.add_argument("--date-from", type=parse_date)
    parser.add_argument("--date-to", type=parse_date)
    parser.add_argument("--include-approval-reviews", action="store_true")
    parser.add_argument("--include-assistant", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--messages-per-role", type=int, default=8, help="0 means all messages.")
    parser.add_argument("--max-message-chars", type=int, default=1200)
    parser.add_argument("--limit", type=int, default=0, help="0 means no limit.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.sessions_root = str(Path(args.sessions_root).expanduser())
    sessions_root = Path(args.sessions_root)
    if not sessions_root.is_dir():
        parser.error(f"sessions root not found: {sessions_root}")
    matches: list[ChatMatch] = []
    for path in sorted(sessions_root.rglob("*.jsonl")):
        session = read_session(path)
        if session and passes_filters(session, args):
            matches.append(session)
    matches.sort(key=lambda item: item.timestamp)
    if args.limit > 0:
        matches = matches[: args.limit]
    if args.format == "json":
        output = json.dumps([to_jsonable(session, args) for session in matches], ensure_ascii=False, indent=2) + "\n"
    else:
        output = render_markdown(matches, args)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
