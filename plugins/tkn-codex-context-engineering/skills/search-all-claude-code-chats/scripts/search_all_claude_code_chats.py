#!/usr/bin/env python3
"""Search local Claude Code conversation text without changing its source logs."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

# Session title records and the field that holds each title.
TITLE_RECORDS = {"custom-title": "customTitle", "ai-title": "aiTitle"}


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
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def normalize_path(value: str) -> str:
    return value.replace("\\", "/").rstrip("/").casefold()


def title_key(value: str) -> str:
    """Compare titles without case, full/half-width, or whitespace differences."""
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(block["text"] for block in content
                         if isinstance(block, dict) and block.get("type") == "text"
                         and isinstance(block.get("text"), str))
    return ""


def warning(coverage: dict[str, Any], message: str) -> None:
    coverage["parser_warnings"] += 1
    print(f"warning: {message}", file=sys.stderr)


def is_subagent_path(path: Path) -> bool:
    return path.parent.name == "subagents" or path.stem.startswith("agent-")


def discover(root: Path, coverage: dict[str, Any]):
    """Visit transcript locations, never spilled tool results or memory directories."""
    def on_error(exc: OSError) -> None:
        coverage["unreadable_directories"] += 1
        print(f"warning: cannot scan directory {exc.filename}: {exc.strerror}", file=sys.stderr)

    for current, directories, filenames in os.walk(root, onerror=on_error, followlinks=False):
        folder = Path(current)
        depth = len(folder.relative_to(root).parts)
        if depth == 1:
            directories[:] = [d for d in directories if d not in {"memory", "tool-results", "mcp-tasks"}]
        elif depth == 2:
            directories[:] = [d for d in directories if d == "subagents"]
        elif depth >= 3:
            directories[:] = []
        if depth == 1 or (depth == 3 and folder.name == "subagents"):
            yield from (folder / name for name in sorted(filenames) if name.endswith(".jsonl"))


def read_transcript(path: Path, coverage: dict[str, Any], include_subagents: bool) -> dict[str, Any] | None:
    messages: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    recorded_ids: set[str] = set()
    latest_titles = dict.fromkeys(TITLE_RECORDS, "")
    title_history: list[dict[str, Any]] = []
    agent_id = path.stem.removeprefix("agent-") if is_subagent_path(path) else ""
    parent_id = path.parent.parent.name if path.parent.name == "subagents" else ""
    transcript_id = path.stem.split(".orphaned-", 1)[0]
    with path.open(encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                warning(coverage, f"{path}:L{line_number}: invalid JSON record")
                continue
            if not isinstance(row, dict):
                warning(coverage, f"{path}:L{line_number}: expected an object")
                continue
            kind = string(row.get("type"))
            if kind in TITLE_RECORDS and row.get("sessionId") == transcript_id:
                value = string(row.get(TITLE_RECORDS[kind]))
                latest_titles[kind] = value
                if value and not any(t["source"] == kind and t["title"] == value for t in title_history):
                    title_history.append({"source": kind, "title": value, "line_number": line_number})
            if kind not in {"user", "assistant"}:
                coverage["ignored_record_types"][kind or "(missing type)"] += 1
                continue
            session_id = string(row.get("sessionId"))
            if session_id:
                recorded_ids.add(session_id)
            if not parent_id and is_subagent_path(path):
                parent_id = session_id
            if row.get("isSidechain") and not include_subagents:
                coverage["excluded_sidechain_messages"] += 1
                continue
            if row.get("isMeta") or row.get("isCompactSummary"):
                coverage["excluded_generated_messages"] += 1
                continue
            message = row.get("message")
            if not isinstance(message, dict) or message.get("role", kind) != kind:
                warning(coverage, f"{path}:L{line_number}: unsupported message envelope")
                continue
            text = content_text(message.get("content"))
            if not text.strip():
                coverage["non_text_messages"] += 1
                continue
            uuid = string(row.get("uuid"))
            key = (kind, uuid, text)
            if uuid and key in seen:
                coverage["duplicate_messages"] += 1
                continue
            seen.add(key)
            messages.append({
                "role": kind, "text": text, "timestamp": string(row.get("timestamp")),
                "uuid": uuid, "parent_uuid": string(row.get("parentUuid")),
                "session_id": session_id, "cwd": string(row.get("cwd")),
                "line_number": line_number, "is_sidechain": bool(row.get("isSidechain")),
                "agent_id": string(row.get("agentId")) or agent_id,
            })
    if not messages:
        return None
    dated = [m["timestamp"] for m in messages if timestamp(m["timestamp"]) is not None]
    subagent = is_subagent_path(path) or all(m["is_sidechain"] for m in messages)
    return {
        "id": transcript_id, "parent_session_id": parent_id,
        "agent_id": agent_id, "kind": "subagent" if subagent else "main",
        "recorded_session_ids": sorted(recorded_ids), "title": latest_titles["custom-title"],
        "ai_title": latest_titles["ai-title"], "title_history": title_history,
        "path": str(path.absolute()), "cwd": next((m["cwd"] for m in messages if m["cwd"]), ""),
        "created": min(dated, key=timestamp) if dated else "",
        "updated": max(dated, key=timestamp) if dated else "", "messages": messages,
    }


def date_matches(value: str, args: argparse.Namespace) -> bool:
    if not args.date_from and not args.date_to:
        return True
    parsed = timestamp(value)
    if parsed is None:
        return False
    day = parsed.astimezone(args.utc_offset).date()
    return (not args.date_from or day >= args.date_from) and (not args.date_to or day <= args.date_to)


def cwd_matches(value: str, args: argparse.Namespace) -> bool:
    return all(normalize_path(term) in normalize_path(value) for term in args.cwd_contains)


def clip(text: str, limit: int, match: re.Match[str] | None = None) -> dict[str, Any]:
    start, end = 0, len(text)
    if limit and len(text) > limit:
        center = (match.start() + match.end()) // 2 if match else 0
        start = min(max(0, center - limit // 2), len(text) - limit)
        end = start + limit
    return {"text": text[start:end], "text_start": start, "text_end": end,
            "truncated": start > 0 or end < len(text)}


def match_titles(session: dict[str, Any], keys: list[str]) -> list[dict[str, Any]] | None:
    """Return matching recorded titles when every key matches at least one of them."""
    entries = [(entry, title_key(entry["title"])) for entry in session["title_history"]]
    if not all(any(key in normalized for _, normalized in entries) for key in keys):
        return None
    return [entry for entry, normalized in entries if any(key in normalized for key in keys)]


def select_session(session: dict[str, Any], args: argparse.Namespace) -> dict[str, Any] | None:
    identities = {session["id"], session["parent_session_id"]} - {""}
    if args.session_id and not identities.intersection(args.session_id):
        return None
    matched_titles = match_titles(session, args.title_keys) if args.title_keys else []
    if matched_titles is None:
        return None
    if args.cwd_field == "session" and not cwd_matches(session["cwd"], args):
        return None
    if args.date_field != "message" and not date_matches(session[args.date_field], args):
        return None
    eligible = [m for m in session["messages"]
                if (args.cwd_field != "message" or cwd_matches(m["cwd"], args))
                and (args.date_field != "message" or date_matches(m["timestamp"], args))]
    if not eligible:
        return None
    hits: dict[int, list[tuple[str, re.Match[str]]]] = {}
    found: set[str] = set()
    for index, message in enumerate(eligible):
        if args.query_user_only and message["role"] != "user":
            continue
        matches = [(q, hit) for q, pattern in args.patterns if (hit := pattern.search(message["text"])) is not None]
        if matches:
            hits[index] = matches
            found.update(q for q, _ in matches)
    if any(q not in found for q in args.query):
        return None
    visible = {i for i, m in enumerate(eligible) if args.include_assistant or m["role"] == "user"}
    required = set(hits) & visible
    selected = set(required) if args.messages_per_role else set(visible)
    if args.messages_per_role:
        neighbors = {i for h in required for i in range(max(0, h - args.context_messages),
                                                       min(len(eligible), h + args.context_messages + 1))} & visible
        priority = sorted(neighbors, key=lambda i: (min(abs(i - h) for h in required), i))
        for role in ("user", "assistant"):
            indices = sorted(i for i in visible if eligible[i]["role"] == role)
            head, tail = (args.messages_per_role + 1) // 2, args.messages_per_role // 2
            priority.extend(indices[:head] + (indices[-tail:] if tail else []))
        counts = Counter(eligible[i]["role"] for i in selected)
        for index in priority:
            role = eligible[index]["role"]
            if index not in selected and counts[role] < args.messages_per_role:
                selected.add(index)
                counts[role] += 1
    messages = []
    for index in sorted(selected):
        original = eligible[index]
        matches = hits.get(index, [])
        result = {**original, **clip(original["text"], args.max_message_chars, matches[0][1] if matches else None)}
        result["matched_queries"] = [q for q, _ in matches]
        result["matched_excerpts"] = [
            {"query": q, **clip(original["text"], args.max_message_chars, hit),
             "match_start": hit.start(), "match_end": hit.end()} for q, hit in matches
        ]
        messages.append(result)
    return {**session, "messages": messages, "matched_queries": [q for q, _ in args.patterns if q in found],
            "matched_titles": matched_titles, "eligible_message_count": len(eligible), "omitted_message_count": len(visible - selected),
            "hidden_matching_message_count": len(set(hits) - visible)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    roots = parser.add_mutually_exclusive_group()
    roots.add_argument("--projects-root", action="append", help="Repeatable projects root; replaces default roots.")
    roots.add_argument("--session-file", action="append", help="Read only these transcript files instead of scanning roots.")
    parser.add_argument("--session-id", action="append", default=[], help="Exact transcript ID, or parent ID for subagents.")
    parser.add_argument("--title", action="append", default=[],
                        help="Substring of a recorded custom or AI session title, including earlier titles. "
                             "Ignores case, full/half-width and whitespace; repeated values use AND.")
    parser.add_argument("--include-subagents", action="store_true")
    parser.add_argument("--cwd-contains", action="append", default=[])
    parser.add_argument("--cwd-field", choices=["session", "message"], default="session")
    parser.add_argument("--query", action="append", default=[], help="Repeated queries use AND across eligible messages.")
    parser.add_argument("--regex", action="store_true")
    parser.add_argument("--query-user-only", action="store_true")
    parser.add_argument("--include-assistant", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--date-from", type=date.fromisoformat)
    parser.add_argument("--date-to", type=date.fromisoformat)
    parser.add_argument("--date-field", choices=["created", "updated", "message"], default="created")
    parser.add_argument("--utc-offset", type=parse_offset, default=parse_offset("+00:00"))
    parser.add_argument("--sort-by", choices=["created", "updated"], default="updated")
    parser.add_argument("--order", choices=["asc", "desc"], default="desc")
    parser.add_argument("--limit", type=nonnegative, default=10, help="Session limit after sorting; 0 means unlimited.")
    parser.add_argument("--messages-per-role", type=nonnegative, default=8, help="Soft budget; 0 retains all eligible messages.")
    parser.add_argument("--context-messages", type=nonnegative, default=1)
    parser.add_argument("--max-message-chars", type=nonnegative, default=1200, help="Characters per excerpt; 0 disables truncation.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    return parser


def search(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict[str, Any]:
    if args.date_from and args.date_to and args.date_from > args.date_to:
        parser.error("--date-from must be on or before --date-to")
    if any(not q for q in args.query):
        parser.error("--query must not be empty")
    args.title_keys = list(dict.fromkeys(title_key(t) for t in args.title))
    if any(not key for key in args.title_keys):
        parser.error("--title must contain non-space text")
    try:
        args.patterns = [(q, re.compile(q if args.regex else re.escape(q), re.IGNORECASE | re.MULTILINE))
                         for q in dict.fromkeys(args.query)]
    except re.error as exc:
        parser.error(f"invalid query regex: {exc}")
    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()
    paths = args.session_file or args.projects_root or [str(config_dir / "projects")]
    source_kind = "session-file" if args.session_file else "projects"
    roots = [Path(p).expanduser().absolute() for p in paths]
    for root in roots:
        if not (root.is_file() if args.session_file else root.is_dir()):
            parser.error(f"{source_kind} not found: {root}")
    coverage: dict[str, Any] = {
        "roots": [{"kind": source_kind, "path": str(root), "exists": True} for root in roots],
        "files_discovered": 0, "files_scanned": 0, "unreadable_files": 0, "unreadable_directories": 0,
        "files_without_messages": 0, "parser_warnings": 0, "excluded_subagent_files": 0,
        "excluded_sidechain_messages": 0, "excluded_generated_messages": 0, "excluded_set_aside_files": 0,
        "non_text_messages": 0, "duplicate_messages": 0, "ignored_record_types": Counter(),
        "matched_sessions": 0, "returned_sessions": 0,
        "excluded": ["other hosts/accounts unless explicitly selected", "cloud-only and claude.ai chats",
                     "tool calls/results and request blobs", "thinking, images and attachments",
                     "generated meta messages and compact summaries", "current-branch reconstruction"],
    }
    sessions = []
    seen_paths: set[Path] = set()
    for root in roots:
        candidates = [root] if args.session_file else discover(root, coverage)
        for path in candidates:
            try:
                resolved = path.resolve()
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                coverage["files_discovered"] += 1
                if not args.session_file and ".orphaned-" in path.name:
                    coverage["excluded_set_aside_files"] += 1
                    continue
                if is_subagent_path(path) and not args.include_subagents:
                    coverage["excluded_subagent_files"] += 1
                    continue
                coverage["files_scanned"] += 1
                session = read_transcript(path, coverage, args.include_subagents)
            except (OSError, UnicodeError) as exc:
                coverage["unreadable_files"] += 1
                print(f"warning: cannot read {path}: {type(exc).__name__}", file=sys.stderr)
                continue
            if session is None:
                coverage["files_without_messages"] += 1
                continue
            result = select_session(session, args)
            if result is not None:
                sessions.append(result)
    sessions.sort(key=lambda s: (timestamp(s[args.sort_by]) or datetime.min.replace(tzinfo=timezone.utc),
                                 s["id"], s["path"]), reverse=args.order == "desc")
    coverage["matched_sessions"] = len(sessions)
    if args.limit:
        sessions = sessions[:args.limit]
    coverage["returned_sessions"] = len(sessions)
    filters = {key: getattr(args, key) for key in (
        "query", "regex", "query_user_only", "title", "session_id", "include_subagents", "include_assistant",
        "cwd_contains", "cwd_field", "date_field", "sort_by", "order", "limit",
        "messages_per_role", "context_messages", "max_message_chars",
    )}
    filters.update(date_from=str(args.date_from or ""), date_to=str(args.date_to or ""), utc_offset=str(args.utc_offset))
    return {"schema_version": 1, "source": "claude-code", "coverage": coverage, "filters": filters, "sessions": sessions}


def format_titles(entries: list[dict[str, Any]]) -> str:
    return "; ".join(f"{json.dumps(e['title'], ensure_ascii=False)} ({e['source']}, L{e['line_number']})"
                     for e in entries) or "(none)"


def render_markdown(report: dict[str, Any]) -> str:
    coverage = report["coverage"]
    lines = ["# Claude Code Chat Search Results", "",
             f"Matched sessions: {coverage['matched_sessions']}; returned: {coverage['returned_sessions']}", "",
             "## Search coverage", "", "Local persisted conversation text only; see excluded sources below."]
    for root in coverage["roots"]:
        lines.append(f"- {root['kind']}: `{root['path']}`")
    for key, value in coverage.items():
        if key != "roots":
            lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False)}")
    lines.extend(["", "Filters:", "", "```json", json.dumps(report["filters"], ensure_ascii=False, indent=2), "```"])
    if not coverage["matched_sessions"] and report["filters"]["query"] and not report["filters"]["title"]:
        lines.extend(["", "Note: `--query` searches message text only, not session titles. "
                          "If the user named the session by its title, retry with `--title`."])
    for session in report["sessions"]:
        lines.extend(["", "---", "", f"## {session['id']}", "", f"- title (recorded): {json.dumps(session['title'], ensure_ascii=False)}",
                      f"- AI title (recorded): {json.dumps(session['ai_title'], ensure_ascii=False)}",
                      f"- recorded titles: {format_titles(session['title_history'])}"])
        if report["filters"]["title"]:
            lines.append(f"- matched titles: {format_titles(session['matched_titles'])}")
        lines.extend([f"- path: `{session['path']}`", f"- cwd: `{session['cwd']}`",
                      f"- kind: {session['kind']}; parent session: `{session['parent_session_id']}`; agent: `{session['agent_id']}`",
                      f"- created: {session['created']}; latest text: {session['updated']}",
                      f"- omitted visible messages: {session['omitted_message_count']}",
                      f"- matching messages hidden by role filter: {session['hidden_matching_message_count']}"])
        for message in session["messages"]:
            lines.extend(["", f"### {message['role']} | {message['timestamp']} | L{message['line_number']}", "",
                          f"- uuid: `{message['uuid']}`; parent: `{message['parent_uuid']}`",
                          f"- recorded session: `{message['session_id']}`; cwd: `{message['cwd']}`; sidechain: {message['is_sidechain']}", ""])
            for window in message["matched_excerpts"] or [message]:
                if "query" in window:
                    lines.append(f"Match: {json.dumps(window['query'], ensure_ascii=False)}")
                if window["truncated"]:
                    lines.append("(excerpt; text shortened)")
                lines.extend("> " + line for line in window["text"].splitlines())
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = search(args, parser)
    output = (json.dumps(report, ensure_ascii=False, indent=2) + "\n"
              if args.format == "json" else render_markdown(report))
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
