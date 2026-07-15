#!/usr/bin/env python3
"""Audit Codex context freshness without changing the source context."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


sys.dont_write_bytecode = True
PLUGIN_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from tkn_codex_context.common import (  # noqa: E402
    DEFAULT_CONTEXT_ROOT,
    JST,
    Result,
    data_root,
    expand,
    expand_store_root,
    global_data_source,
    is_versioned_store,
    now_compact,
    now_iso,
    print_result,
    source_ref,
)
from tkn_codex_context.file_io import require_explicit_output_dest, write_text  # noqa: E402
from tkn_codex_context.frontmatter import parse_simple_frontmatter  # noqa: E402
from tkn_codex_context.safety import has_secret_like_content  # noqa: E402


DEFAULT_FRESHNESS_INCLUDE = (
    "working-context,decisions,sessions,candidates,patterns,skill-candidates,agents-candidates,reviews"
)


@dataclass
class FreshnessItem:
    path: Path
    category: str
    type_name: str
    title: str
    updated_value: str
    age_days: int | None
    status: str
    severity: str
    flags: list[str]


def parse_freshness_include(value: str) -> set[str]:
    allowed = {
        "working-context",
        "decisions",
        "sessions",
        "candidates",
        "patterns",
        "skill-candidates",
        "agents-candidates",
        "reviews",
    }
    parts = {part.strip() for part in value.split(",") if part.strip()}
    unknown = parts - allowed
    if unknown:
        raise SystemExit(f"Unknown include value(s): {', '.join(sorted(unknown))}")
    return parts or set(allowed)

def parse_datetime_value(value: str) -> datetime | None:
    cleaned = value.strip().strip("'\"")
    if not cleaned:
        return None
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(cleaned, "%Y%m%dT%H%M%S%z")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)

def freshness_scope(source: Path, explicit_scope: str) -> str:
    if explicit_scope != "auto":
        return explicit_scope
    if (source / "sessions").exists() or (source / "working-context.md").exists():
        return "repo"
    return "global"

def context_relative_path(source: Path, path: Path) -> str:
    try:
        return path.relative_to(source).as_posix()
    except ValueError:
        return source_ref(path)

def context_source_label(source: Path, explicit_label: str | None) -> str:
    if explicit_label:
        return explicit_label
    try:
        return source.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return source.name or "context-source"

def freshness_threshold(category: str, args: argparse.Namespace) -> int:
    if category == "working-context":
        return args.working_context_days
    if category == "sessions":
        return args.session_days
    if category == "decisions":
        return args.decision_days
    if category in {"candidates", "skill-candidates", "agents-candidates"}:
        return args.candidate_days
    if category == "patterns":
        return args.pattern_days
    return args.default_days

def freshness_files(source: Path, include: set[str]) -> list[tuple[str, Path]]:
    specs = [
        ("working-context", source / "working-context.md", False),
        ("decisions", source / "decisions", True),
        ("sessions", source / "sessions", True),
        ("candidates", source / "candidates", True),
        ("patterns", source / "patterns", True),
        ("skill-candidates", source / "skill-candidates", True),
        ("agents-candidates", source / "agents-candidates", True),
        ("reviews", source / "reviews", True),
    ]
    found: list[tuple[str, Path]] = []
    for category, path, is_folder in specs:
        if category not in include:
            continue
        if is_folder:
            if path.exists():
                found.extend((category, item) for item in sorted(path.glob("*.md")) if item.is_file())
        elif path.exists():
            found.append((category, path))
    return found

def assess_freshness_file(
    source: Path,
    category: str,
    path: Path,
    args: argparse.Namespace,
    now: datetime,
) -> FreshnessItem:
    text = path.read_text(encoding="utf-8", errors="replace")
    metadata = parse_simple_frontmatter(text)
    updated_value = metadata.get("updated") or metadata.get("lastSeenAt") or metadata.get("date") or ""
    updated_at = parse_datetime_value(updated_value)
    age_days = (now - updated_at).days if updated_at else None
    flags: list[str] = []

    if not metadata:
        flags.append("missing-frontmatter")
    if not updated_value:
        flags.append("missing-updated")
    if updated_value and updated_at is None:
        flags.append("unparseable-updated")

    threshold = freshness_threshold(category, args)
    if age_days is not None and age_days > threshold:
        flags.append(f"stale>{threshold}d")

    status = metadata.get("status", "")
    if status in {"stale", "blocked", "waiting-for-user"}:
        flags.append(f"status={status}")

    distillation = metadata.get("distillationStatus", "")
    if category == "sessions" and distillation in {"pending", "partial"}:
        if age_days is None or age_days > args.session_pending_days:
            flags.append(f"distillation={distillation}")

    promotion = metadata.get("promotionStatus", "")
    if promotion in {"pending", "partial"} and category in {"working-context", "decisions"}:
        if age_days is None or age_days > args.promotion_pending_days:
            flags.append(f"promotion={promotion}")

    if has_secret_like_content(text):
        flags.append("secret-like-content")

    severity = "ok"
    if "secret-like-content" in flags:
        severity = "high"
    elif any(flag.startswith(("stale>", "missing-", "unparseable-")) for flag in flags):
        severity = "medium"
    elif flags:
        severity = "low"

    return FreshnessItem(
        path=path,
        category=category,
        type_name=metadata.get("type", category),
        title=metadata.get("title", path.stem),
        updated_value=updated_value,
        age_days=age_days,
        status=status,
        severity=severity,
        flags=flags,
    )

def render_freshness_report(
    *,
    source: Path,
    source_label: str,
    scope: str,
    items: list[FreshnessItem],
    args: argparse.Namespace,
) -> str:
    now = now_iso()
    needs_review = [item for item in items if item.flags]
    high = sum(1 for item in needs_review if item.severity == "high")
    medium = sum(1 for item in needs_review if item.severity == "medium")
    low = sum(1 for item in needs_review if item.severity == "low")

    rows = []
    for item in needs_review[: args.max_items]:
        age = "" if item.age_days is None else str(item.age_days)
        reasons = ", ".join(item.flags)
        rows.append(
            "| "
            + " | ".join(
                [
                    item.severity,
                    item.category,
                    age,
                    context_relative_path(source, item.path),
                    item.title.replace("|", "/"),
                    reasons.replace("|", "/"),
                ]
            )
            + " |"
        )
    if not rows:
        rows.append("| ok | - | - | - | No freshness issues found. | - |")

    return f"""# Context Freshness Audit

Date: {now}
Source: `{source_label}`
Scope: `{scope}`

## Summary

- Scanned files: {len(items)}
- Needs review: {len(needs_review)}
- High severity: {high}
- Medium severity: {medium}
- Low severity: {low}

## Thresholds

- Working context: {args.working_context_days} days
- Session notes: {args.session_days} days
- Pending session distillation: {args.session_pending_days} days
- Decisions: {args.decision_days} days
- Candidates: {args.candidate_days} days
- Patterns: {args.pattern_days} days
- Pending promotion: {args.promotion_pending_days} days
- Default: {args.default_days} days

## Review Items

| Severity | Category | Age days | Path | Title | Reasons |
| --- | --- | ---: | --- | --- | --- |
{chr(10).join(rows)}

## Notes

- This audit is a freshness signal, not a correctness verdict.
- Current user instructions, repository instructions, current files, and git state still take precedence.
- Revalidate stale context against current evidence before promoting it to global context, AGENTS.md, or a Skill.
"""

def audit_freshness(args: argparse.Namespace) -> Result:
    source_root = expand_store_root(args.source)
    source = global_data_source(source_root) if is_versioned_store(source_root) else source_root
    include = parse_freshness_include(args.include)
    result = Result()

    if not source_root.exists():
        raise SystemExit(f"Source does not exist: {source_root}")

    scope = (
        "global"
        if args.scope == "auto" and is_versioned_store(source_root)
        else freshness_scope(source, args.scope)
    )
    now = datetime.now(JST)
    items = [
        assess_freshness_file(source, category, path, args, now)
        for category, path in freshness_files(source, include)
    ]
    needs_review = [item for item in items if item.flags]
    source_label = context_source_label(source, args.source_label)
    report = render_freshness_report(
        source=source,
        source_label=source_label,
        scope=scope,
        items=items,
        args=args,
    )
    report_path = None
    if args.report_dest:
        report_path = expand(args.report_dest) / f"{now_compact()}-freshness-audit.md"
    elif args.write:
        require_explicit_output_dest("--report-dest", "audit-freshness")

    result.add("source", str(source))
    result.add("source-label", source_label)
    result.add("scope", scope)
    result.add("scanned", str(len(items)))
    result.add("needs-review", str(len(needs_review)))
    for item in needs_review[: args.max_items]:
        detail = (
            f"{item.severity} {context_relative_path(source, item.path)} "
            f"({item.category}): {', '.join(item.flags)}"
        )
        result.add("review", detail)
    if len(needs_review) > args.max_items:
        result.warn(f"{len(needs_review) - args.max_items} review item(s) omitted from stdout")

    if report_path is not None:
        write_text(report_path, report, args.write, result, overwrite=True)
    else:
        result.add("report-dest", "not written; pass --report-dest with --write to save a report")
    return result

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DEFAULT_CONTEXT_ROOT)
    parser.add_argument("--source-label")
    parser.add_argument("--scope", choices=["auto", "repo", "global"], default="auto")
    parser.add_argument("--include", default=DEFAULT_FRESHNESS_INCLUDE)
    parser.add_argument("--report-dest")
    parser.add_argument("--max-items", type=int, default=50)
    parser.add_argument("--working-context-days", type=int, default=30)
    parser.add_argument("--session-days", type=int, default=90)
    parser.add_argument("--session-pending-days", type=int, default=14)
    parser.add_argument("--decision-days", type=int, default=180)
    parser.add_argument("--candidate-days", type=int, default=60)
    parser.add_argument("--pattern-days", type=int, default=120)
    parser.add_argument("--promotion-pending-days", type=int, default=30)
    parser.add_argument("--default-days", type=int, default=90)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--log")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.write and args.dry_run:
        parser.error("Use either --dry-run or --write, not both.")
    if not args.write:
        args.dry_run = True
    result = audit_freshness(args)
    print_result(result, args.write, args.log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
