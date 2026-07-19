#!/usr/bin/env python3
"""Scan Codex chats for one registered project and commit refresh checkpoints."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


sys.dont_write_bytecode = True
PLUGIN_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_LIB = PLUGIN_ROOT / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from tkn_codex_context.chat_logs import (  # noqa: E402
    ChatMessage,
    default_sessions_root,
    fingerprint_session,
    has_clean_user_message,
    is_approval_review,
    is_known_internal_session,
    normalize_path_text,
    normalize_repository_url,
    path_is_within,
    read_session,
    select_messages_for_roots,
    source_ref,
)


SCHEMA_VERSION = 2
LEGACY_STATE_SCHEMA_VERSION = 1
STATE_FILENAME = "chat-refresh-state.json"
DECISION_ID_PATTERN = re.compile(r"^DR-\d{4}$")
SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class RefreshError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RefreshError(f"cannot read JSON: {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        write_json(temporary, value)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def marker_value(path: Path, key: str) -> str:
    if not path.is_file():
        raise RefreshError(
            "project marker not found; run init-project-context only when the user explicitly requests initialization"
        )
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:\s*(.*?)\s*$")
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1).strip().strip('"\'')
    raise RefreshError(f"project marker is missing {key}: {path}")


def default_registry_path() -> Path:
    return Path.home() / ".tkn" / "codex-context" / "state" / "index.jsonl"


def find_registry_record(registry_path: Path, project_id: str) -> dict[str, Any]:
    if not registry_path.is_file():
        raise RefreshError(f"project registry not found: {registry_path}")
    matches: list[dict[str, Any]] = []
    with registry_path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RefreshError(f"invalid registry JSON at line {line_number}: {exc}") from exc
            if isinstance(value, dict) and value.get("projectId") == project_id:
                matches.append(value)
    if len(matches) != 1:
        raise RefreshError(f"expected one registry record for {project_id}; found {len(matches)}")
    return matches[0]


def absolute_path(value: str | Path, base: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base or Path.cwd()) / path
    return Path(os.path.abspath(path))


def physical_path(value: str | Path) -> Path:
    return absolute_path(value).resolve(strict=False)


def stable_root_text(value: str | Path, base: Path | None = None) -> str:
    raw = str(value).strip().rstrip("\\/")
    if not raw:
        return ""
    if re.match(r"^[A-Za-z]:[\\/]", raw) or raw.startswith(("/", "\\\\")):
        return raw
    return str(absolute_path(raw, base))


def unique_paths(
    values: Sequence[str | Path],
    *,
    base: Path | None = None,
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = stable_root_text(value, base)
        key = normalize_path_text(text)
        if key and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def equivalent_path(value: str | Path, candidates: Sequence[str | Path]) -> bool:
    direct = normalize_path_text(stable_root_text(value))
    resolved = ""
    try:
        resolved = normalize_path_text(str(physical_path(value)))
    except OSError:
        pass
    for candidate in candidates:
        candidate_keys = {normalize_path_text(stable_root_text(candidate))}
        try:
            candidate_keys.add(normalize_path_text(str(physical_path(candidate))))
        except OSError:
            pass
        if direct in candidate_keys:
            return True
        if resolved and resolved in candidate_keys:
            return True
    return False


def git_output(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def discover_repository_url(repo_root: Path) -> str:
    return git_output(repo_root, "remote", "get-url", "origin")


def resolve_project(
    repo_root: Path,
    registry_path: Path | None = None,
    state_file: Path | None = None,
) -> tuple[str, dict[str, Any], Path, list[str]]:
    repo_root = absolute_path(repo_root)
    project_id = marker_value(repo_root / ".tkn" / "codex-context.yaml", "projectId")
    record = find_registry_record(registry_path or default_registry_path(), project_id)
    current_root = str(record.get("currentRoot") or "")
    if not current_root or not equivalent_path(current_root, [repo_root, physical_path(repo_root)]):
        raise RefreshError("project registry record does not resolve to the current workspace")
    project_context_value = str(record.get("projectContextPath") or "")
    if not project_context_value:
        raise RefreshError("registry record is missing projectContextPath")
    project_context = Path(project_context_value)
    resolved_state = state_file or (project_context / STATE_FILENAME)
    git_root = git_output(repo_root, "rev-parse", "--show-toplevel")
    current_roots = unique_paths(
        [value for value in (repo_root, physical_path(repo_root), current_root, git_root) if str(value)]
    )
    return project_id, record, resolved_state, current_roots


def validate_source_id(source_id: str) -> str:
    if not SOURCE_ID_PATTERN.fullmatch(source_id):
        raise RefreshError(
            "source id must use lowercase letters, digits, dots, underscores, or hyphens"
        )
    return source_id


def empty_state(project_id: str) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "projectId": project_id,
        "approvedHistoricalRoots": [],
        "rejectedHistoricalRoots": [],
        "lastRefreshAt": None,
        "sources": {},
    }


def migrate_legacy_state(
    value: dict[str, Any],
    *,
    source_id: str,
    sessions_root: Path,
) -> dict[str, Any]:
    legacy_root = str(value.get("sourceRoot") or sessions_root)
    if normalize_path_text(legacy_root) == normalize_path_text(str(sessions_root)):
        legacy_source_id = source_id
    elif normalize_path_text(legacy_root) == normalize_path_text(
        str(default_sessions_root())
    ):
        legacy_source_id = "windows"
    else:
        legacy_source_id = "legacy"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "projectId": value.get("projectId"),
        "approvedHistoricalRoots": value.get("approvedHistoricalRoots", []),
        "rejectedHistoricalRoots": value.get("rejectedHistoricalRoots", []),
        "lastRefreshAt": value.get("lastRefreshAt"),
        "sources": {
            legacy_source_id: {
                "sourceRoot": legacy_root,
                "lastRefreshAt": value.get("lastRefreshAt"),
                "threads": value.get("threads", {}),
            }
        },
    }


def ensure_source_state(
    state: dict[str, Any],
    source_id: str,
    sessions_root: Path,
) -> dict[str, Any]:
    sources = state["sources"]
    source = sources.get(source_id)
    if source is None:
        source = {
            "sourceRoot": str(sessions_root),
            "lastRefreshAt": None,
            "threads": {},
        }
        sources[source_id] = source
        return source
    if not isinstance(source, dict) or not isinstance(source.get("threads"), dict):
        raise RefreshError(f"refresh state source {source_id} is invalid")
    existing_root = str(source.get("sourceRoot") or "")
    if existing_root and normalize_path_text(existing_root) != normalize_path_text(
        str(sessions_root)
    ):
        raise RefreshError(
            f"source id {source_id} is already bound to another sessions root"
        )
    source["sourceRoot"] = str(sessions_root)
    return source


def load_state(
    path: Path,
    project_id: str,
    sessions_root: Path,
    source_id: str,
) -> dict[str, Any]:
    source_id = validate_source_id(source_id)
    if not path.exists():
        value = empty_state(project_id)
        ensure_source_state(value, source_id, sessions_root)
        return value
    loaded = read_json(path)
    if not isinstance(loaded, dict):
        raise RefreshError(f"refresh state must be a JSON object: {path}")
    if loaded.get("schemaVersion") == LEGACY_STATE_SCHEMA_VERSION:
        value = migrate_legacy_state(
            loaded,
            source_id=source_id,
            sessions_root=sessions_root,
        )
    else:
        value = loaded
    if not isinstance(value, dict):
        raise RefreshError(f"refresh state must be a JSON object: {path}")
    if value.get("schemaVersion") != SCHEMA_VERSION:
        raise RefreshError(f"unsupported refresh state schemaVersion: {value.get('schemaVersion')}")
    if value.get("projectId") != project_id:
        raise RefreshError("refresh state projectId does not match the current project")
    for key in ("approvedHistoricalRoots", "rejectedHistoricalRoots"):
        if not isinstance(value.get(key), list):
            raise RefreshError(f"refresh state {key} must be a list")
    if not isinstance(value.get("sources"), dict):
        raise RefreshError("refresh state sources must be an object")
    ensure_source_state(value, source_id, sessions_root)
    return value


def message_json(message: ChatMessage) -> dict[str, str]:
    return {
        "role": message.role,
        "source": message.source,
        "text": message.text,
        "timestamp": message.timestamp,
        "turnId": message.turn_id,
        "cwd": message.cwd,
    }


def roots_contain_any(roots: Sequence[str], values: Sequence[str]) -> bool:
    return any(path_is_within(value, root) for value in values for root in roots)


def apply_root_choices(
    state: dict[str, Any],
    approve_roots: Sequence[str],
    reject_roots: Sequence[str],
    *,
    base: Path,
) -> tuple[list[str], list[str]]:
    approved_inputs = [*state["approvedHistoricalRoots"], *approve_roots]
    rejected_inputs = [*state["rejectedHistoricalRoots"], *reject_roots]
    approved = unique_paths(approved_inputs, base=base)
    rejected = unique_paths(rejected_inputs, base=base)
    approved_keys = {normalize_path_text(value) for value in approved}
    rejected_keys = {normalize_path_text(value) for value in rejected}
    for value in approve_roots:
        rejected_keys.discard(normalize_path_text(stable_root_text(value, base)))
    for value in reject_roots:
        approved_keys.discard(normalize_path_text(stable_root_text(value, base)))
    approved = [value for value in approved if normalize_path_text(value) in approved_keys]
    rejected = [value for value in rejected if normalize_path_text(value) in rejected_keys]
    return approved, rejected


def scan_project(
    repo_root: Path,
    sessions_root: Path,
    *,
    source_id: str = "windows",
    registry_path: Path | None = None,
    state_file: Path | None = None,
    approve_roots: Sequence[str] = (),
    reject_roots: Sequence[str] = (),
    full: bool = False,
    thread_ids: Sequence[str] = (),
    include_messages: bool = False,
    repository_url: str | None = None,
) -> dict[str, Any]:
    source_id = validate_source_id(source_id)
    repo_root = absolute_path(repo_root)
    sessions_root = absolute_path(sessions_root)
    if not sessions_root.is_dir():
        raise RefreshError(f"sessions root not found: {sessions_root}")
    project_id, _record, resolved_state, current_roots = resolve_project(
        repo_root, registry_path=registry_path, state_file=state_file
    )
    state = load_state(resolved_state, project_id, sessions_root, source_id)
    source_state = state["sources"][source_id]
    approved, rejected = apply_root_choices(state, approve_roots, reject_roots, base=repo_root)
    accepted_roots = unique_paths([*current_roots, *approved])
    normalized_repo_url = normalize_repository_url(
        repository_url if repository_url is not None else discover_repository_url(repo_root)
    )
    thread_filter = set(thread_ids)
    candidate_counts: dict[str, int] = {}
    candidate_display: dict[str, str] = {}
    session_rows: list[dict[str, Any]] = []
    matched_thread_ids: set[str] = set()
    skipped = {"approvalReview": 0, "internal": 0, "noUserMessage": 0}

    for path in sorted(sessions_root.rglob("*.jsonl")):
        session = read_session(path)
        if not session:
            continue
        if thread_filter and session.id not in thread_filter:
            continue
        if is_approval_review(session):
            skipped["approvalReview"] += 1
            continue
        if is_known_internal_session(session):
            skipped["internal"] += 1
            continue
        if not has_clean_user_message(session):
            skipped["noUserMessage"] += 1
            continue

        selected_messages = select_messages_for_roots(session, accepted_roots)
        session_repo_url = normalize_repository_url(session.repository_url)
        same_repository = bool(normalized_repo_url and session_repo_url == normalized_repo_url)

        if same_repository:
            for cwd in [session.cwd] if session.cwd else []:
                if roots_contain_any([*accepted_roots, *rejected], [cwd]):
                    continue
                key = normalize_path_text(cwd)
                candidate_display.setdefault(key, cwd)
                candidate_counts[key] = candidate_counts.get(key, 0) + 1
        if not selected_messages and same_repository:
            continue
        if not selected_messages:
            continue

        relative_ref = source_ref(path, sessions_root)
        qualified_ref = f"{source_id}/{relative_ref}"
        fingerprint = fingerprint_session(session, selected_messages, qualified_ref)
        prior = source_state["threads"].get(session.id, {})
        if full:
            status = "full"
        elif not prior:
            status = "new"
        elif prior.get("fingerprint") != fingerprint:
            status = "changed"
        else:
            status = "unchanged"
        row: dict[str, Any] = {
            "threadId": session.id,
            "timestamp": session.timestamp,
            "cwd": session.cwd,
            "repositoryUrl": session.repository_url,
            "sourceId": source_id,
            "sourceRef": qualified_ref,
            "sourceRelativeRef": relative_ref,
            "fingerprint": fingerprint,
            "status": status,
            "messageCount": len(selected_messages),
            "userMessageCount": sum(m.role == "user" for m in selected_messages),
            "assistantMessageCount": sum(m.role == "assistant" for m in selected_messages),
            "mixedCwd": len({normalize_path_text(m.cwd) for m in session.messages if m.cwd}) > 1,
        }
        if include_messages:
            row["messages"] = [message_json(message) for message in selected_messages]
        session_rows.append(row)
        matched_thread_ids.add(session.id)

    session_rows.sort(key=lambda item: (item["timestamp"], item["threadId"]))
    candidates = [
        {
            "root": candidate_display[key],
            "reason": "sameRepositoryUrl",
            "sessionCount": candidate_counts[key],
        }
        for key in sorted(candidate_counts, key=lambda item: candidate_display[item].casefold())
    ]
    counts = {
        "total": len(session_rows),
        "new": sum(row["status"] == "new" for row in session_rows),
        "changed": sum(row["status"] == "changed" for row in session_rows),
        "full": sum(row["status"] == "full" for row in session_rows),
        "unchanged": sum(row["status"] == "unchanged" for row in session_rows),
        "missingFromSource": (
            0
            if thread_filter
            else len(set(source_state["threads"]) - matched_thread_ids)
        ),
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": now_iso(),
        "projectId": project_id,
        "sourceId": source_id,
        "repoRoot": str(repo_root),
        "sourceRoot": str(sessions_root),
        "stateFile": str(resolved_state),
        "repositoryUrl": repository_url if repository_url is not None else discover_repository_url(repo_root),
        "currentRoots": current_roots,
        "approvedHistoricalRoots": approved,
        "rejectedHistoricalRoots": rejected,
        "historicalRootCandidates": candidates,
        "counts": counts,
        "skipped": skipped,
        "sessions": session_rows,
    }


def validate_relative_context_path(value: str) -> str:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise RefreshError(f"session note must be relative to the project context folder: {value}")
    if not path.parts or path.parts[0].casefold() != "sessions":
        raise RefreshError(f"session note must be under the sessions folder: {value}")
    return path.as_posix()


def result_session_notes(item: dict[str, Any]) -> list[str]:
    values = item.get("sessionNotes")
    if values is None and item.get("sessionNote"):
        values = [item["sessionNote"]]
    if not isinstance(values, list) or not values:
        raise RefreshError("each processed result needs sessionNote or sessionNotes")
    return [validate_relative_context_path(str(value)) for value in values]


def commit_refresh(
    scan: dict[str, Any],
    result: dict[str, Any],
    *,
    state_file: Path | None = None,
) -> dict[str, Any]:
    if scan.get("schemaVersion") != SCHEMA_VERSION:
        raise RefreshError("unsupported scan schemaVersion")
    if not isinstance(result, dict) or not isinstance(result.get("processed", []), list):
        raise RefreshError("result must contain a processed list")
    project_id = str(scan.get("projectId") or "")
    source_id = validate_source_id(str(scan.get("sourceId") or ""))
    sessions_root = Path(str(scan.get("sourceRoot") or ""))
    resolved_state = state_file or Path(str(scan.get("stateFile") or ""))
    state = load_state(resolved_state, project_id, sessions_root, source_id)
    source_state = state["sources"][source_id]
    scan_sessions = {
        str(item.get("threadId") or ""): item
        for item in scan.get("sessions", [])
        if isinstance(item, dict)
    }
    accepted_roots = [*scan.get("currentRoots", []), *scan.get("approvedHistoricalRoots", [])]
    updates: dict[str, dict[str, Any]] = {}

    for item in result.get("processed", []):
        if not isinstance(item, dict):
            raise RefreshError("processed entries must be JSON objects")
        thread_id = str(item.get("threadId") or "")
        scanned = scan_sessions.get(thread_id)
        if not scanned:
            raise RefreshError(f"processed thread was not present in the scan: {thread_id}")
        fingerprint = str(item.get("fingerprint") or "")
        if fingerprint != scanned.get("fingerprint"):
            raise RefreshError(f"result fingerprint does not match scan for thread {thread_id}")

        relative_ref = str(scanned.get("sourceRelativeRef") or "")
        qualified_ref = str(scanned.get("sourceRef") or "")
        if not relative_ref or qualified_ref != f"{source_id}/{relative_ref}":
            raise RefreshError(f"invalid source reference for thread {thread_id}")
        source_path = (sessions_root / relative_ref).resolve()
        try:
            source_path.relative_to(sessions_root.resolve())
        except ValueError as exc:
            raise RefreshError(f"sourceRef escapes sessions root: {relative_ref}") from exc
        if not source_path.is_file():
            raise RefreshError(f"source log no longer exists: {relative_ref}")
        source_session = read_session(source_path)
        if not source_session:
            raise RefreshError(f"source log no longer has session metadata: {relative_ref}")
        selected_messages = select_messages_for_roots(source_session, accepted_roots)
        current_fingerprint = fingerprint_session(
            source_session,
            selected_messages,
            qualified_ref,
        )
        if current_fingerprint != fingerprint:
            raise RefreshError(f"source log changed after scan for thread {thread_id}")

        decision_ids = item.get("decisionIds", [])
        if not isinstance(decision_ids, list) or any(
            not DECISION_ID_PATTERN.match(str(value)) for value in decision_ids
        ):
            raise RefreshError(f"invalid decisionIds for thread {thread_id}")
        updates[thread_id] = {
            "fingerprint": fingerprint,
            "sourceRefs": [qualified_ref],
            "sessionNotes": result_session_notes(item),
            "decisionIds": [str(value) for value in decision_ids],
            "processedAt": str(item.get("processedAt") or now_iso()),
        }

    approved_roots = unique_paths(scan.get("approvedHistoricalRoots", []))
    rejected_roots = unique_paths(scan.get("rejectedHistoricalRoots", []))
    root_choices_changed = (
        approved_roots != state["approvedHistoricalRoots"]
        or rejected_roots != state["rejectedHistoricalRoots"]
    )
    if not updates and not root_choices_changed:
        return {
            "stateFile": str(resolved_state),
            "sourceId": source_id,
            "processedCount": 0,
            "lastRefreshAt": state.get("lastRefreshAt"),
            "noChange": True,
        }

    state["approvedHistoricalRoots"] = approved_roots
    state["rejectedHistoricalRoots"] = rejected_roots
    source_state["sourceRoot"] = str(sessions_root)
    source_state["threads"].update(updates)
    refreshed_at = now_iso()
    source_state["lastRefreshAt"] = refreshed_at
    state["lastRefreshAt"] = refreshed_at
    atomic_write_json(resolved_state, state)
    return {
        "stateFile": str(resolved_state),
        "sourceId": source_id,
        "processedCount": len(updates),
        "lastRefreshAt": state["lastRefreshAt"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Scan registered-project chats without writing project context.")
    scan.add_argument("--repo-root", default=".")
    scan.add_argument("--sessions-root", default=str(default_sessions_root()))
    scan.add_argument(
        "--source-id",
        default="windows",
        help="Stable lowercase id for this sessions root, such as windows or wsl.",
    )
    scan.add_argument("--state-file", help="Testing override.")
    scan.add_argument("--approve-root", action="append", default=[])
    scan.add_argument("--reject-root", action="append", default=[])
    scan.add_argument("--thread-id", action="append", default=[])
    scan.add_argument("--include-messages", action="store_true")
    scan.add_argument("--full", action="store_true")
    scan.add_argument("--output", required=True)

    commit = subparsers.add_parser("commit", help="Commit successful materialization checkpoints.")
    commit.add_argument("--repo-root", default=".")
    commit.add_argument("--scan", required=True)
    commit.add_argument("--result", required=True)
    commit.add_argument("--state-file", help="Testing override.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            scan = scan_project(
                Path(args.repo_root),
                Path(args.sessions_root),
                source_id=args.source_id,
                state_file=Path(args.state_file) if args.state_file else None,
                approve_roots=args.approve_root,
                reject_roots=args.reject_root,
                full=args.full,
                thread_ids=args.thread_id,
                include_messages=args.include_messages,
            )
            write_json(Path(args.output), scan)
            print(json.dumps({"output": str(Path(args.output)), "counts": scan["counts"]}, ensure_ascii=False))
            return 0

        scan_data = read_json(Path(args.scan))
        result_data = read_json(Path(args.result))
        project_id, _record, resolved_state, _roots = resolve_project(
            Path(args.repo_root),
            state_file=Path(args.state_file) if args.state_file else None,
        )
        if scan_data.get("projectId") != project_id:
            raise RefreshError("scan projectId does not match the current registered project")
        summary = commit_refresh(
            scan_data,
            result_data,
            state_file=resolved_state,
        )
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    except RefreshError as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
