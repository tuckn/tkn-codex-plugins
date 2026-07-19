#!/usr/bin/env python3
"""Aggregate registered project working contexts into a private portfolio dashboard."""

from __future__ import annotations

import argparse
import json
import re
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
    expand,
    expand_store_root,
    frontmatter,
    print_result,
    registry_path,
    state_root,
)
from tkn_codex_context.file_io import (  # noqa: E402
    require_explicit_output_dest,
    write_text,
)
from tkn_codex_context.frontmatter import (  # noqa: E402
    frontmatter_list_value,
    parse_simple_frontmatter,
    require_supported_artifact_schema,
    split_frontmatter_lines,
)


GLOBAL_WORKING_CONTEXT_SCHEMA_VERSION = 1
VALID_PROJECT_STATUSES = {"active", "paused", "blocked", "completed", "archived"}
STATUS_ORDER = {
    "blocked": 0,
    "active": 1,
    "paused": 2,
    "completed": 3,
    "archived": 4,
}
PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2, "unknown": 3}


@dataclass
class PortfolioProject:
    project_id: str
    title: str
    purpose: str
    project_status: str
    health: str
    priority: str
    current_focus: str
    blocked: bool
    main_blocker: str
    exact_next_action: str
    last_meaningful_activity: str
    review_after: str
    dependency_project_ids: list[str]
    updated: str
    source_schema_version: str
    source_ref: str
    available: bool
    stale: bool
    review_reasons: list[str]


def current_time() -> datetime:
    return datetime.now(JST)


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


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "yes", "1", "blocked"}


def clean_inline(value: str, fallback: str = "Unknown") -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    return cleaned or fallback


def markdown_cell(value: str, fallback: str = "Unknown") -> str:
    return clean_inline(value, fallback).replace("|", "/")


def section_summary(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"(?ms)^##\s+{re.escape(heading)}\s*\r?\n(.*?)(?=^##\s+|\Z)"
    )
    match = pattern.search(text)
    if not match:
        return ""
    lines = []
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.lower() in {"none.", "none"}:
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^#+\s+", "", line)
        lines.append(line)
        if len(lines) == 2:
            break
    return clean_inline(" ".join(lines), "")


def normalize_project_status(raw_value: str) -> str:
    value = raw_value.strip().lower()
    aliases = {
        "inactive": "paused",
        "done": "completed",
        "complete": "completed",
    }
    value = aliases.get(value, value)
    return value if value in VALID_PROJECT_STATUSES else "active"


def read_registry(source: Path, result: Result) -> list[dict[str, object]]:
    path = registry_path(source)
    if not path.is_file():
        raise SystemExit(f"Project registry does not exist: {path}")
    records: dict[str, dict[str, object]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            result.warn(f"registry line {line_number}: {exc}")
            continue
        if not isinstance(record, dict):
            result.warn(f"registry line {line_number}: ignoring non-object value")
            continue
        project_id = str(record.get("projectId") or "").strip()
        if not project_id:
            result.warn(f"registry line {line_number}: missing projectId")
            continue
        if project_id in records:
            result.warn(f"duplicate projectId {project_id}: using the last registry record")
        records[project_id] = record
    return list(records.values())


def missing_project(
    project_id: str,
    record: dict[str, object],
) -> PortfolioProject:
    source_ref = f"state:/{project_id}/working-context.md"
    raw_status = str(record.get("status") or "active")
    return PortfolioProject(
        project_id=project_id,
        title=str(record.get("title") or project_id),
        purpose="",
        project_status=normalize_project_status(raw_status),
        health="unknown",
        priority="unknown",
        current_focus="",
        blocked=False,
        main_blocker="",
        exact_next_action="Review or recreate the missing project working context.",
        last_meaningful_activity="",
        review_after="",
        dependency_project_ids=[],
        updated="",
        source_schema_version="missing",
        source_ref=source_ref,
        available=False,
        stale=False,
        review_reasons=["missing working context"],
    )


def load_project(
    source: Path,
    record: dict[str, object],
    *,
    stale_days: int,
    now: datetime,
) -> PortfolioProject:
    project_id = str(record["projectId"]).strip()
    source_ref = f"state:/{project_id}/working-context.md"
    path = state_root(source) / project_id / "working-context.md"
    if not path.is_file():
        return missing_project(project_id, record)

    text = path.read_text(encoding="utf-8", errors="replace")
    metadata = parse_simple_frontmatter(text)
    if metadata.get("type") != "workingContext":
        raise SystemExit(f"Expected type workingContext in {source_ref}.")
    schema_version = require_supported_artifact_schema(
        metadata,
        f"working context {source_ref}",
    )
    declared_project_id = metadata.get("projectId", "")
    if declared_project_id and declared_project_id != project_id:
        raise SystemExit(
            f"ProjectId mismatch in {source_ref}: expected {project_id}, "
            f"found {declared_project_id}."
        )

    header, _ = split_frontmatter_lines(text)
    dependencies = frontmatter_list_value(header, "dependencyProjectIds")
    raw_status = (
        metadata.get("projectStatus")
        or metadata.get("status")
        or str(record.get("status") or "active")
    )
    blocked = parse_bool(metadata.get("blocked", "")) or raw_status.lower() == "blocked"
    project_status = "blocked" if blocked else normalize_project_status(raw_status)
    last_activity = metadata.get("lastMeaningfulActivity", "")
    updated = metadata.get("updated") or last_activity or metadata.get("date", "")
    updated_at = parse_datetime_value(updated)
    stale = updated_at is not None and (now - updated_at).days > stale_days
    review_after = metadata.get("reviewAfter", "")
    review_at = parse_datetime_value(review_after)

    review_reasons: list[str] = []
    if schema_version == "1":
        review_reasons.append("legacy schema v1")
    if not updated:
        review_reasons.append("missing updated timestamp")
    elif updated_at is None:
        review_reasons.append("unparseable updated timestamp")
    if stale:
        review_reasons.append(f"stale > {stale_days} days")
    if review_after and review_at is None:
        review_reasons.append("unparseable reviewAfter")
    elif review_at is not None and review_at.date() <= now.date():
        review_reasons.append("review due")
    health = metadata.get("health", "unknown").lower()
    if health in {"attention", "at-risk"}:
        review_reasons.append(f"health {health}")

    return PortfolioProject(
        project_id=project_id,
        title=metadata.get("title") or str(record.get("title") or project_id),
        purpose=section_summary(text, "Purpose") or metadata.get("description", ""),
        project_status=project_status,
        health=health if health in {"healthy", "attention", "at-risk", "unknown"} else "unknown",
        priority=(
            metadata.get("priority", "unknown").lower()
            if metadata.get("priority", "unknown").lower() in PRIORITY_ORDER
            else "unknown"
        ),
        current_focus=metadata.get("currentFocus", ""),
        blocked=blocked,
        main_blocker=metadata.get("mainBlocker", ""),
        exact_next_action=metadata.get("exactNextAction", ""),
        last_meaningful_activity=last_activity,
        review_after=review_after,
        dependency_project_ids=dependencies,
        updated=updated,
        source_schema_version=schema_version,
        source_ref=source_ref,
        available=True,
        stale=stale,
        review_reasons=review_reasons,
    )


def project_sort_key(project: PortfolioProject) -> tuple[int, int, str, str]:
    return (
        STATUS_ORDER.get(project.project_status, 99),
        PRIORITY_ORDER.get(project.priority, 99),
        project.title.casefold(),
        project.project_id,
    )


def render_project_table(projects: list[PortfolioProject]) -> str:
    if not projects:
        return "None."
    rows = [
        "| Project | Purpose | Health | Priority | Current focus | Main blocker | Exact next action | Last activity | Source |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for project in sorted(projects, key=project_sort_key):
        rows.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(project.title),
                    markdown_cell(project.purpose),
                    markdown_cell(project.health),
                    markdown_cell(project.priority),
                    markdown_cell(project.current_focus),
                    markdown_cell(project.main_blocker, "None"),
                    markdown_cell(project.exact_next_action),
                    markdown_cell(project.last_meaningful_activity or project.updated),
                    f"`{project.source_ref}`",
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def render_dependencies(
    projects: list[PortfolioProject],
    by_id: dict[str, PortfolioProject],
) -> str:
    rows: list[str] = []
    for project in sorted(projects, key=project_sort_key):
        for dependency_id in project.dependency_project_ids:
            dependency = by_id.get(dependency_id)
            dependency_title = dependency.title if dependency else f"{dependency_id} (unregistered)"
            rows.append(f"- {project.title} -> {dependency_title}")
    return "\n".join(rows) if rows else "None."


def render_review_items(projects: list[PortfolioProject]) -> str:
    review_projects = [project for project in projects if project.review_reasons]
    if not review_projects:
        return "None."
    rows = [
        "| Project | Reasons | Source |",
        "| --- | --- | --- |",
    ]
    for project in sorted(review_projects, key=project_sort_key):
        rows.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(project.title),
                    markdown_cell(", ".join(project.review_reasons)),
                    f"`{project.source_ref}`",
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def render_portfolio(
    projects: list[PortfolioProject],
    *,
    generated_at: str,
) -> str:
    by_status = {
        status: [project for project in projects if project.project_status == status]
        for status in STATUS_ORDER
    }
    available = [project for project in projects if project.available]
    stale = [project for project in projects if project.stale]
    blocked = by_status["blocked"]
    source_refs = ["state:/index.jsonl", *[project.source_ref for project in projects]]
    metadata = frontmatter(
        [
            ("type", "globalWorkingContext"),
            ("schemaVersion", GLOBAL_WORKING_CONTEXT_SCHEMA_VERSION),
            ("title", "Registered Codex Project Portfolio"),
            (
                "description",
                "Current portfolio state aggregated from registered project working contexts.",
            ),
            ("generator", "Codex"),
            ("status", "active"),
            ("scope", "global"),
            ("sourceProjectCount", len(projects)),
            ("includedProjectCount", len(available)),
            ("blockedProjectCount", len(blocked)),
            ("staleProjectCount", len(stale)),
            ("sourceRefs", source_refs),
            ("date", generated_at),
            ("updated", generated_at),
            ("contextId", "registered-project-portfolio"),
        ]
    )
    by_id = {project.project_id: project for project in projects}
    return f"""{metadata}

# Registered Codex Project Portfolio

## Purpose

Provide a current, source-linked view across registered Codex Projects without reading raw chats,
session notes, or decision bodies.

## Summary

- Registered projects: {len(projects)}
- Included working contexts: {len(available)}
- Active projects: {len(by_status["active"])}
- Blocked projects: {len(blocked)}
- Paused projects: {len(by_status["paused"])}
- Completed projects: {len(by_status["completed"])}
- Archived projects: {len(by_status["archived"])}
- Stale project contexts: {len(stale)}

## Blocked Projects

{render_project_table(blocked)}

## Active Projects

{render_project_table(by_status["active"])}

## Paused Projects

{render_project_table(by_status["paused"])}

## Completed Projects

{render_project_table(by_status["completed"])}

## Archived Projects

{render_project_table(by_status["archived"])}

## Dependencies

{render_dependencies(projects, by_id)}

## Review Items

{render_review_items(projects)}

## Maintenance

- Regenerate this file from the registry and project working contexts when project current truth
  changes.
- Resolve review items in their source project artifacts; do not patch inferred truth directly into
  this portfolio.
"""


def build_portfolio(args: argparse.Namespace) -> tuple[Result, str]:
    source = expand_store_root(args.source)
    if not source.exists():
        raise SystemExit(f"Context store does not exist: {source}")
    if args.stale_days < 0:
        raise SystemExit("--stale-days must be zero or greater.")

    result = Result()
    records = read_registry(source, result)
    now = current_time()
    projects = [
        load_project(
            source,
            record,
            stale_days=args.stale_days,
            now=now,
        )
        for record in records
    ]
    projects.sort(key=project_sort_key)
    output = render_portfolio(
        projects,
        generated_at=now.isoformat(timespec="seconds"),
    )
    blocked_count = sum(project.project_status == "blocked" for project in projects)
    stale_count = sum(project.stale for project in projects)
    review_count = sum(bool(project.review_reasons) for project in projects)

    result.add("source", str(source))
    result.add("registered-projects", str(len(projects)))
    result.add("included-working-contexts", str(sum(project.available for project in projects)))
    result.add("blocked-projects", str(blocked_count))
    result.add("stale-projects", str(stale_count))
    result.add("review-items", str(review_count))

    if args.dest:
        destination = expand(args.dest)
        protected_paths = {
            registry_path(source).resolve(),
            *[
                (state_root(source) / project.project_id / "working-context.md").resolve()
                for project in projects
            ],
        }
        if destination in protected_paths:
            raise SystemExit(
                "Destination must not overwrite the project registry or a project working context."
            )
        write_text(destination, output, args.write, result, overwrite=True)
    elif args.write:
        require_explicit_output_dest("--dest", "write-global-working-context")
    else:
        result.add("destination", "not written; pass --dest with --write to save the portfolio")
    return result, output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DEFAULT_CONTEXT_ROOT)
    parser.add_argument("--dest")
    parser.add_argument("--stale-days", type=int, default=30)
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
    result, _ = build_portfolio(args)
    print_result(result, args.write, args.log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
