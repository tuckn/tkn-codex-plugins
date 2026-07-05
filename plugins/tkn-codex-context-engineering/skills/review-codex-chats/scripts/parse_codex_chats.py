#!/usr/bin/env python3
"""Summarize Codex JSONL chat transcripts for source reviews."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Iterable


APPROVAL_REVIEW_PREFIX = "The following is the Codex agent history"
SOURCE_ROOT_LABEL = "~/.codex/sessions"


def default_sessions_root() -> Path:
    return Path.home() / ".codex" / "sessions"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sessions-root",
        default=str(default_sessions_root()),
        help="Testing override for the Codex sessions root. Defaults to ~/.codex/sessions.",
    )
    parser.add_argument("--month", help="Calendar month like 2026-06.")
    parser.add_argument("--week", help="ISO week like 2026-W27.")
    parser.add_argument("--period-start", help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--period-end", help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument("--output", help="Write JSON summary to this path. Defaults to stdout.")
    parser.add_argument("--max-samples", type=int, default=8, help="Max text samples per role per session.")
    parser.add_argument("--sample-chars", type=int, default=500, help="Max chars per text sample.")
    return parser.parse_args()


def parse_week(value: str) -> tuple[dt.date, dt.date, str]:
    match = re.fullmatch(r"(\d{4})-?W(\d{1,2})", value)
    if not match:
        raise SystemExit("--week must look like 2026-W27")
    year = int(match.group(1))
    week = int(match.group(2))
    start = dt.date.fromisocalendar(year, week, 1)
    end = start + dt.timedelta(days=6)
    return start, end, f"{year}-W{week:02d}"


def parse_month(value: str) -> tuple[dt.date, dt.date, str]:
    match = re.fullmatch(r"(\d{4})-(\d{2})", value)
    if not match:
        raise SystemExit("--month must look like 2026-06")
    year = int(match.group(1))
    month = int(match.group(2))
    start = dt.date(year, month, 1)
    if month == 12:
        end = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
    else:
        end = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    return start, end, f"{year}-{month:02d}"


def resolve_period(args: argparse.Namespace) -> tuple[dt.date, dt.date, str]:
    supplied = [bool(args.month), bool(args.week), bool(args.period_start or args.period_end)]
    if sum(supplied) > 1:
        raise SystemExit("Use only one period selector: --month, --week, or --period-start/--period-end.")

    if args.month:
        return parse_month(args.month)
    if args.week:
        return parse_week(args.week)
    if args.period_start or args.period_end:
        if not args.period_start or not args.period_end:
            raise SystemExit("--period-start and --period-end must be supplied together.")
        start = dt.date.fromisoformat(args.period_start)
        end = dt.date.fromisoformat(args.period_end)
        if end < start:
            raise SystemExit("--period-end must be on or after --period-start.")
        iso = start.isocalendar()
        label = f"{iso.year}-W{iso.week:02d}" if (end - start).days == 6 else f"{start}_{end}"
        return start, end, label

    today = dt.date.today()
    first_this_month = today.replace(day=1)
    end = first_this_month - dt.timedelta(days=1)
    start = end.replace(day=1)
    return start, end, f"{start.year}-{start.month:02d}"


def parse_session_date(path: Path) -> dt.date | None:
    text = str(path)
    path_match = re.search(r"[\\/](20\d{2})[\\/](\d{2})[\\/](\d{2})[\\/]", text)
    if path_match:
        return dt.date(int(path_match.group(1)), int(path_match.group(2)), int(path_match.group(3)))
    name_match = re.search(r"rollout-(20\d{2})-(\d{2})-(\d{2})T", path.name)
    if name_match:
        return dt.date(int(name_match.group(1)), int(name_match.group(2)), int(name_match.group(3)))
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime).date()
    except OSError:
        return None


def iter_jsonl_files(root: Path, start: dt.date, end: dt.date) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.jsonl"):
        session_date = parse_session_date(path)
        if session_date and start <= session_date <= end:
            files.append(path)
    return sorted(files)


def iter_json_lines(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                yield {"type": "__parse_error__"}


def content_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [content_to_text(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        parts: list[str] = []
        for key in ("text", "input_text", "message", "content", "output", "summary"):
            if key in value:
                part = content_to_text(value[key])
                if part:
                    parts.append(part)
        return "\n".join(parts)
    return ""


def clean_user_text(text: str) -> str:
    for marker in ("## My request for Codex:", "## My request for Codex"):
        if marker in text:
            return text.split(marker, 1)[1].strip()

    if text.lstrip().startswith("# AGENTS.md instructions for"):
        return ""

    if "<INSTRUCTIONS>" in text and "</INSTRUCTIONS>" in text:
        text = text.split("</INSTRUCTIONS>", 1)[-1]

    if "<environment_context>" in text:
        text = text.split("<environment_context>", 1)[0]

    return text.strip()


def sanitize_private_paths(text: str) -> str:
    home = str(Path.home())
    variants = {home, home.replace("\\", "/")}
    for variant in variants:
        if variant:
            text = text.replace(variant, "~")

    text = re.sub(r"\\\\[^\s`'\"<>|]+[\\/][^\s`'\"<>|]+(?:[\\/][^\s`'\"<>|]+)*", "<absolute-path>", text)
    text = re.sub(r"\b[A-Za-z]:[\\/][^\s`'\"<>|]+(?:[\\/][^\s`'\"<>|]+)*", "<absolute-path>", text)
    text = re.sub(r"(?<!\w)/(?:mnt/[a-z]|home|Users)/[^\s`'\"<>|]+(?:/[^\s`'\"<>|]+)*", "<absolute-path>", text)
    return text


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def truncate(text: str, max_chars: int) -> str:
    text = normalize_text(sanitize_private_paths(text))
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def collect_mentions(text: str) -> tuple[list[str], list[str]]:
    sanitized = sanitize_private_paths(text)
    file_pattern = re.compile(r"(?<![<\w./\\-])[\w./\\-]+\.(?:md|py|jsonl|json|ya?ml|toml|txt|csv|ps1)", re.IGNORECASE)
    skill_pattern = re.compile(r"(?:^|[^\w-])([a-z][a-z0-9]+(?:-[a-z0-9]+)+)(?:$|[^\w-])")
    files = sorted({match for match in file_pattern.findall(sanitized) if "<absolute-path>" not in match})[:30]
    skills = sorted({match.group(1) for match in skill_pattern.finditer(sanitized)})[:30]
    return files, skills


def counter_items(counter: collections.Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def append_sample(
    samples: dict[str, list[str]],
    seen: set[tuple[str, str]],
    role: str,
    text: str,
    max_samples: int,
    sample_chars: int,
) -> None:
    if role == "user":
        text = clean_user_text(text)
    text = sanitize_private_paths(text).strip()
    if not text:
        return
    normalized = normalize_text(text)
    key = (role, normalized)
    if key in seen:
        return
    seen.add(key)
    if len(samples[role]) < max_samples:
        samples[role].append(truncate(text, sample_chars))


def is_approval_review(samples: dict[str, list[str]]) -> bool:
    return any(sample.lstrip().startswith(APPROVAL_REVIEW_PREFIX) for sample in samples["user"])


def summarize_file(path: Path, root: Path, max_samples: int, sample_chars: int) -> dict[str, Any]:
    event_types: collections.Counter[str] = collections.Counter()
    payload_types: collections.Counter[str] = collections.Counter()
    roles: collections.Counter[str] = collections.Counter()
    function_calls: collections.Counter[str] = collections.Counter()
    file_mentions: collections.Counter[str] = collections.Counter()
    skill_mentions: collections.Counter[str] = collections.Counter()
    samples: dict[str, list[str]] = {"user": [], "assistant": []}
    seen_samples: set[tuple[str, str]] = set()

    parse_errors = 0
    line_count = 0
    first_timestamp = None
    last_timestamp = None
    meta: dict[str, Any] = {}

    for record in iter_json_lines(path):
        line_count += 1
        if record.get("type") == "__parse_error__":
            parse_errors += 1
            continue

        timestamp = record.get("timestamp")
        if timestamp:
            first_timestamp = first_timestamp or timestamp
            last_timestamp = timestamp

        top_type = str(record.get("type") or "")
        if top_type:
            event_types[top_type] += 1

        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        if top_type == "session_meta":
            meta = payload

        payload_type = str(payload.get("type") or "")
        if payload_type:
            payload_types[payload_type] += 1

        role = str(payload.get("role") or "")
        if role:
            roles[role] += 1

        if payload_type == "function_call":
            function_calls[str(payload.get("name") or "(unknown)")] += 1

        text = ""
        sample_role = ""
        if top_type == "response_item" and payload_type == "message" and role in {"user", "assistant"}:
            text = content_to_text(payload.get("content"))
            sample_role = role
        elif top_type == "event_msg" and payload_type in {"user_message", "agent_message"}:
            text = content_to_text(payload.get("message"))
            sample_role = "user" if payload_type == "user_message" else "assistant"

        if text:
            sanitized = sanitize_private_paths(clean_user_text(text) if sample_role == "user" else text)
            files, skills = collect_mentions(sanitized)
            file_mentions.update(files)
            skill_mentions.update(skills)
            if sample_role in samples:
                append_sample(samples, seen_samples, sample_role, text, max_samples, sample_chars)

    relative = path.relative_to(root).as_posix()
    cwd = sanitize_private_paths(str(meta.get("cwd") or ""))
    return {
        "sourceRef": relative,
        "sessionId": str(meta.get("id") or ""),
        "sessionDate": str(parse_session_date(path) or ""),
        "timestamp": str(meta.get("timestamp") or first_timestamp or ""),
        "cwd": cwd,
        "originator": str(meta.get("originator") or ""),
        "source": str(meta.get("source") or ""),
        "threadSource": str(meta.get("thread_source") or ""),
        "firstTimestamp": first_timestamp,
        "lastTimestamp": last_timestamp,
        "sizeBytes": path.stat().st_size,
        "lineCount": line_count,
        "parseErrors": parse_errors,
        "looksLikeApprovalReview": is_approval_review(samples),
        "eventTypes": counter_items(event_types),
        "payloadTypes": counter_items(payload_types),
        "roles": counter_items(roles),
        "functionCalls": counter_items(function_calls, 20),
        "fileMentions": counter_items(file_mentions, 20),
        "skillMentions": counter_items(skill_mentions, 20),
        "samples": samples,
    }


def main() -> None:
    args = parse_args()
    start, end, label = resolve_period(args)
    root = Path(args.sessions_root).expanduser().resolve()
    default_root = default_sessions_root().resolve()
    override = root != default_root

    if not root.exists():
        raise SystemExit(f"Codex sessions root not found: {SOURCE_ROOT_LABEL if not override else '<sessions-root>'}")
    if not root.is_dir():
        raise SystemExit(f"Codex sessions root is not a directory: {SOURCE_ROOT_LABEL if not override else '<sessions-root>'}")

    sessions = [
        summarize_file(path, root, args.max_samples, args.sample_chars)
        for path in iter_jsonl_files(root, start, end)
    ]

    totals = {
        "sessionCount": len(sessions),
        "sourceRefs": [session["sourceRef"] for session in sessions],
        "lineCount": sum(session["lineCount"] for session in sessions),
        "sizeBytes": sum(session["sizeBytes"] for session in sessions),
        "parseErrors": sum(session["parseErrors"] for session in sessions),
        "approvalReviewLikeCount": sum(1 for session in sessions if session["looksLikeApprovalReview"]),
    }

    report = {
        "generatedAt": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "periodLabel": label,
        "periodStart": start.isoformat(),
        "periodEnd": end.isoformat(),
        "sourceRoot": SOURCE_ROOT_LABEL,
        "sessionsRootOverride": override,
        "totals": totals,
        "sessions": sessions,
    }

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
