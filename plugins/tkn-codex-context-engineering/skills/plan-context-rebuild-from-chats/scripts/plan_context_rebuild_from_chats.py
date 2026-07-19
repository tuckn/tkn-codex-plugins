#!/usr/bin/env python3
"""Build a read-only, all-project context rebuild plan from Codex chat logs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


sys.dont_write_bytecode = True
PLUGIN_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from tkn_codex_context.chat_logs import (  # noqa: E402
    has_clean_user_message,
    is_approval_review,
    is_known_internal_session,
    normalize_path_text,
    normalize_repository_url,
    path_is_within,
    read_session,
    source_ref,
)
from tkn_codex_context.frontmatter import parse_simple_frontmatter  # noqa: E402


PLAN_SCHEMA_VERSION = 1
SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class PlanError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_registry(context_root: Path) -> list[dict[str, Any]]:
    registry = context_root / "state" / "index.jsonl"
    if not registry.is_file():
        raise PlanError(f"project registry not found: {registry}")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(
        registry.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PlanError(f"invalid registry JSON at line {line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise PlanError(f"registry line {line_number} is not an object")
        project_id = str(value.get("projectId") or "").strip()
        if not project_id:
            raise PlanError(f"registry line {line_number} is missing projectId")
        if project_id in seen:
            raise PlanError(f"duplicate projectId in registry: {project_id}")
        seen.add(project_id)
        records.append(value)
    return records


def parse_named_path(value: str, label: str) -> tuple[str, str]:
    name, separator, raw_path = value.partition("=")
    name = name.strip()
    raw_path = raw_path.strip()
    if not separator or not name or not raw_path:
        raise PlanError(f"{label} must use NAME=PATH: {value}")
    if label == "--sessions-source" and not SOURCE_ID_PATTERN.fullmatch(name):
        raise PlanError(f"invalid source ID: {name}")
    return name, raw_path


def parse_sources(values: Sequence[str]) -> list[tuple[str, Path]]:
    if not values:
        return [("windows", Path.home() / ".codex" / "sessions")]
    result: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for value in values:
        source_id, raw_path = parse_named_path(value, "--sessions-source")
        if source_id in seen:
            raise PlanError(f"duplicate source ID: {source_id}")
        root = Path(raw_path).expanduser()
        if not root.is_dir():
            raise PlanError(f"sessions source not found: {root}")
        seen.add(source_id)
        result.append((source_id, root))
    return result


def parse_aliases(
    values: Sequence[str], valid_project_ids: set[str]
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for value in values:
        project_id, root = parse_named_path(value, "--project-root-alias")
        if project_id not in valid_project_ids:
            raise PlanError(f"root alias has unknown projectId: {project_id}")
        result[project_id].append(root)
    return dict(result)


def unique_roots(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip().rstrip("\\/")
        key = normalize_path_text(text)
        if key and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def discover_repository_url(root: str) -> str:
    if not root:
        return ""
    completed = subprocess.run(
        ["git", "-C", root, "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def approved_roots_from_state(context_root: Path, project_id: str) -> list[str]:
    path = context_root / "state" / project_id / "chat-refresh-state.json"
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    roots = value.get("approvedHistoricalRoots", []) if isinstance(value, dict) else []
    return [str(item) for item in roots if isinstance(item, str) and item.strip()]


def artifact_kind(path: Path, project_root: Path, metadata: dict[str, str]) -> str:
    declared = metadata.get("type", "").strip()
    if declared:
        return declared
    relative = path.relative_to(project_root)
    if relative.parts and relative.parts[0].casefold() == "sessions":
        return "session"
    if relative.parts and relative.parts[0].casefold() == "decisions":
        return "decision"
    if relative.as_posix().casefold() == "working-context.md":
        return "workingContext"
    return "unknown"


def artifact_inventory(context_root: Path, project_id: str) -> dict[str, Any]:
    project_root = context_root / "state" / project_id
    by_kind: Counter[str] = Counter()
    by_schema: Counter[str] = Counter()
    if not project_root.is_dir():
        return {"total": 0, "byKind": {}, "bySchemaVersion": {}}
    for path in project_root.rglob("*.md"):
        try:
            metadata = parse_simple_frontmatter(path.read_text(encoding="utf-8-sig"))
        except OSError:
            continue
        by_kind[artifact_kind(path, project_root, metadata)] += 1
        by_schema[metadata.get("schemaVersion") or "unversioned"] += 1
    return {
        "total": sum(by_kind.values()),
        "byKind": dict(sorted(by_kind.items())),
        "bySchemaVersion": dict(sorted(by_schema.items())),
    }


def project_descriptors(
    context_root: Path,
    records: Sequence[dict[str, Any]],
    aliases: dict[str, list[str]],
) -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    for record in records:
        project_id = str(record["projectId"])
        current_root = str(record.get("currentRoot") or "").strip()
        accepted_roots = unique_roots(
            [
                current_root,
                *approved_roots_from_state(context_root, project_id),
                *aliases.get(project_id, []),
            ]
        )
        repository_url = discover_repository_url(current_root)
        projects.append(
            {
                "projectId": project_id,
                "title": str(record.get("title") or project_id),
                "status": str(record.get("status") or ""),
                "currentRoot": current_root,
                "acceptedRoots": accepted_roots,
                "repositoryUrl": repository_url,
                "normalizedRepositoryUrl": normalize_repository_url(repository_url),
                "artifactInventory": artifact_inventory(context_root, project_id),
                "assignedSessions": [],
                "repositoryCandidates": [],
            }
        )
    return projects


def session_matches_project(session: Any, project: dict[str, Any]) -> bool:
    roots = project["acceptedRoots"]
    if session.cwd and any(path_is_within(session.cwd, root) for root in roots):
        return True
    return any(
        message.cwd and any(path_is_within(message.cwd, root) for root in roots)
        for message in session.messages
    )


def session_summary(session: Any, source_id: str, relative_ref: str) -> dict[str, Any]:
    return {
        "threadId": session.id,
        "timestamp": session.timestamp,
        "sourceId": source_id,
        "sourceRef": f"{source_id}/{relative_ref}",
        "cwd": session.cwd,
        "repositoryUrl": session.repository_url,
        "messageCount": len(session.messages),
    }


def root_summary(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("cwd") or ""), str(row.get("reason") or ""))].append(row)
    result: list[dict[str, Any]] = []
    for (cwd, reason), items in grouped.items():
        timestamps = sorted(
            str(item.get("timestamp") or "") for item in items if item.get("timestamp")
        )
        repository_urls = sorted(
            {str(item.get("repositoryUrl")) for item in items if item.get("repositoryUrl")}
        )
        result.append(
            {
                "cwd": cwd,
                "reason": reason,
                "sessionCount": len(items),
                "sourceIds": sorted({str(item["sourceId"]) for item in items}),
                "firstTimestamp": timestamps[0] if timestamps else "",
                "lastTimestamp": timestamps[-1] if timestamps else "",
                "repositoryUrls": repository_urls,
            }
        )
    return sorted(result, key=lambda item: (-item["sessionCount"], item["cwd"].casefold()))


def build_plan(
    context_root: Path,
    sources: Sequence[tuple[str, Path]],
    aliases: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    records = read_registry(context_root)
    projects = project_descriptors(context_root, records, aliases or {})
    repo_projects: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for project in projects:
        if project["normalizedRepositoryUrl"]:
            repo_projects[project["normalizedRepositoryUrl"]].append(project)

    source_summaries: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    unparsed: list[dict[str, str]] = []
    excluded: Counter[str] = Counter()
    thread_refs: dict[str, list[str]] = defaultdict(list)
    direct_count = 0
    candidate_count = 0

    for source_id, source_root in sources:
        file_count = parsed_count = 0
        source_timestamps: list[str] = []
        for path in sorted(source_root.rglob("*.jsonl")):
            file_count += 1
            relative_ref = source_ref(path, source_root)
            session = read_session(path)
            if not session or not session.id:
                unparsed.append(
                    {"sourceId": source_id, "sourceRef": f"{source_id}/{relative_ref}"}
                )
                continue
            parsed_count += 1
            if session.timestamp:
                source_timestamps.append(session.timestamp)
            summary = session_summary(session, source_id, relative_ref)
            thread_refs[session.id].append(summary["sourceRef"])
            if is_approval_review(session):
                excluded["approvalReview"] += 1
                continue
            if is_known_internal_session(session):
                excluded["internal"] += 1
                continue
            if not has_clean_user_message(session):
                excluded["noUserMessage"] += 1
                continue

            direct_projects = [
                project for project in projects if session_matches_project(session, project)
            ]
            if len(direct_projects) == 1:
                direct_projects[0]["assignedSessions"].append(summary)
                direct_count += 1
                continue
            if len(direct_projects) > 1:
                summary["reason"] = "multipleAcceptedRoots"
                summary["candidateProjectIds"] = [
                    project["projectId"] for project in direct_projects
                ]
                unresolved.append(summary)
                continue

            repository_key = normalize_repository_url(session.repository_url)
            candidates = repo_projects.get(repository_key, []) if repository_key else []
            if len(candidates) == 1:
                summary["reason"] = "sameRepositoryUrlNeedsRootApproval"
                candidates[0]["repositoryCandidates"].append(summary)
                candidate_count += 1
            else:
                summary["reason"] = (
                    "ambiguousRepositoryUrl" if len(candidates) > 1 else "noProjectMatch"
                )
                if candidates:
                    summary["candidateProjectIds"] = [
                        project["projectId"] for project in candidates
                    ]
                unresolved.append(summary)

        source_summaries.append(
            {
                "sourceId": source_id,
                "sourceRoot": str(source_root),
                "fileCount": file_count,
                "parsedCount": parsed_count,
                "unparsedCount": file_count - parsed_count,
                "firstTimestamp": min(source_timestamps) if source_timestamps else "",
                "lastTimestamp": max(source_timestamps) if source_timestamps else "",
            }
        )

    for project in projects:
        project["assignedSessions"].sort(
            key=lambda item: (item["timestamp"], item["sourceRef"])
        )
        project["repositoryCandidates"].sort(
            key=lambda item: (item["timestamp"], item["sourceRef"])
        )
        project["counts"] = {
            "assigned": len(project["assignedSessions"]),
            "repositoryCandidates": len(project["repositoryCandidates"]),
        }
        project["candidateRootSummary"] = root_summary(project["repositoryCandidates"])
        project.pop("normalizedRepositoryUrl", None)

    duplicates = [
        {"threadId": thread_id, "sourceRefs": refs}
        for thread_id, refs in sorted(thread_refs.items())
        if len(refs) > 1
    ]
    return {
        "schemaVersion": PLAN_SCHEMA_VERSION,
        "generatedAt": now_iso(),
        "mode": "readOnlyPlan",
        "contextRoot": str(context_root),
        "sources": source_summaries,
        "summary": {
            "registeredProjects": len(projects),
            "sourceFiles": sum(source["fileCount"] for source in source_summaries),
            "parsedSessions": sum(source["parsedCount"] for source in source_summaries),
            "unparsedFiles": len(unparsed),
            "directAssignments": direct_count,
            "repositoryCandidates": candidate_count,
            "unresolvedSessions": len(unresolved),
            "duplicateThreadIds": len(duplicates),
            "excluded": dict(sorted(excluded.items())),
        },
        "projects": projects,
        "unresolvedSessions": unresolved,
        "unresolvedRootSummary": root_summary(unresolved),
        "unparsedFiles": unparsed,
        "duplicateThreadIds": duplicates,
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def path_is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def require_separate_output(
    output: Path,
    context_root: Path,
    sources: Sequence[tuple[str, Path]],
) -> None:
    protected_roots = [context_root, *(root for _source_id, root in sources)]
    if any(path_is_under(output, root) for root in protected_roots):
        raise PlanError("output must be outside the context store and sessions sources")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--context-root",
        type=Path,
        default=Path.home() / ".tkn" / "codex-context",
        help="Private Codex context store containing state/index.jsonl.",
    )
    parser.add_argument(
        "--sessions-source",
        action="append",
        default=[],
        metavar="ID=PATH",
        help="Codex sessions archive. Repeat for windows, wsl, or other sources.",
    )
    parser.add_argument(
        "--project-root-alias",
        action="append",
        default=[],
        metavar="PROJECT_ID=ROOT",
        help="Explicitly approved historical root. Repeat as needed.",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        context_root = args.context_root.expanduser()
        records = read_registry(context_root)
        project_ids = {str(record["projectId"]) for record in records}
        aliases = parse_aliases(args.project_root_alias, project_ids)
        sources = parse_sources(args.sessions_source)
        require_separate_output(args.output, context_root, sources)
        plan = build_plan(context_root, sources, aliases)
        write_json(args.output, plan)
    except PlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"output": str(args.output), "summary": plan["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
