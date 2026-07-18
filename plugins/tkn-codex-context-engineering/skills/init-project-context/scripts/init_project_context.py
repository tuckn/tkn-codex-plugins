#!/usr/bin/env python3
"""Initialize or refresh one repository in the private Codex context registry."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path


sys.dont_write_bytecode = True
PLUGIN_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from tkn_codex_context.common import (  # noqa: E402
    DEFAULT_CONTEXT_ROOT,
    LEGACY_CONTEXT_ROOT,
    LEGACY_LOCAL_MARKER,
    LOCAL_MARKER,
    Result,
    config_path,
    data_root,
    expand,
    expand_store_root,
    frontmatter,
    now_iso,
    print_result,
    project_state_path,
    registry_path,
    sha256_text,
    short_hash,
    slugify,
    state_root,
    yaml_key_present,
    yaml_line_value,
    yaml_string,
    yaml_value,
)
from tkn_codex_context.file_io import (  # noqa: E402
    ensure_dir,
    execute_non_destructive_copies,
    plan_non_destructive_copies,
    write_text,
)
from tkn_codex_context.frontmatter import (  # noqa: E402
    frontmatter_key_block,
    replace_frontmatter_scalar,
    split_frontmatter_lines,
)


DATA_CONTEXT_DIRS = [
    "decisions",
    "candidates",
    "patterns",
    "skill-candidates",
    "agents-candidates",
    "reviews",
    "session-reviews",
]
PROJECT_STATE_DIRS = ["sessions", "decisions", "memos"]
CONFIG_TEXT = "schemaVersion: 1\n"


def git_value(repo_root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()

def remote_display(remote: str) -> str:
    value = remote.strip()
    if not value:
        return ""
    if re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(("/", "\\", "file:")):
        return ""
    match = re.match(r"git@([^:]+):(.+)$", value)
    if match:
        value = f"{match.group(1)}/{match.group(2)}"
    else:
        value = re.sub(r"^[A-Za-z]+://", "", value)
        value = re.sub(r"^[^/@]+@", "", value)
    value = re.sub(r"\.git$", "", value)
    return value.strip("/")

def project_title(repo_root: Path, explicit_title: str | None, existing: str) -> str:
    if explicit_title:
        return explicit_title
    if existing:
        return existing
    return repo_root.name or "codex-project"

def workspace_id(existing: str) -> str:
    return existing or f"ws_{uuid.uuid4().hex}"

def short_random_id(length: int = 8) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    value = uuid.uuid4().int
    chars: list[str] = []
    while len(chars) < length:
        value, remainder = divmod(value, len(alphabet))
        chars.append(alphabet[remainder])
    return "".join(chars)

def project_id(title: str, created_at: str) -> str:
    date_part = re.sub(r"[^0-9]", "", created_at[:10]) or datetime.now(JST).strftime("%Y%m%d")
    slug = slugify(title)[:48].strip("-") or "codex-project"
    return f"{date_part}_{slug}_{short_random_id()}"

def normalize_registry_path(value: str | Path) -> str:
    if not value:
        return ""
    raw = str(value).strip().replace("\\", "/").rstrip("/")
    drive_match = re.match(r"^([A-Za-z]):/(.*)$", raw)
    if drive_match:
        return f"{drive_match.group(1).upper()}:/{drive_match.group(2)}".rstrip("/")
    wsl_match = re.match(r"^/mnt/([A-Za-z])/(.*)$", raw)
    if wsl_match:
        return f"{wsl_match.group(1).upper()}:/{wsl_match.group(2)}".rstrip("/")
    try:
        resolved = Path(value).expanduser().resolve().as_posix().rstrip("/")
    except OSError:
        return raw
    wsl_match = re.match(r"^/mnt/([A-Za-z])/(.*)$", resolved)
    if wsl_match:
        return f"{wsl_match.group(1).upper()}:/{wsl_match.group(2)}".rstrip("/")
    return resolved

def registry_path_exists(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    raw = value.strip().replace("\\", "/")
    candidates = [Path(raw).expanduser()]
    drive_match = re.match(r"^([A-Za-z]):/(.*)$", raw)
    if drive_match:
        candidates.append(Path(f"/mnt/{drive_match.group(1).lower()}/{drive_match.group(2)}"))
    wsl_match = re.match(r"^/mnt/([A-Za-z])/(.*)$", raw)
    if wsl_match:
        candidates.append(Path(f"{wsl_match.group(1).upper()}:/{wsl_match.group(2)}"))
    for candidate in candidates:
        try:
            if candidate.exists():
                return True
        except OSError:
            continue
    return False

def select_project_record(
    records: list[dict[str, object]],
    repo_root: Path,
    repo_id: str,
    local_project_id: str,
) -> tuple[dict[str, object] | None, str, int]:
    current_root = normalize_registry_path(repo_root)
    for record in records:
        if normalize_registry_path(str(record.get("currentRoot") or "")) == current_root:
            return record, "same-root", len(records)
    if local_project_id:
        project_records = [record for record in records if record.get("projectId") == local_project_id]
        if len(project_records) == 1:
            record = project_records[0]
            old_root = record.get("currentRoot")
            if not old_root or not registry_path_exists(old_root):
                return record, "moved-root", len(project_records)
            return None, "new-project-local-conflict", len(project_records)
        if len(project_records) > 1:
            return None, "new-project-local-conflict", len(project_records)
    repo_records = [record for record in records if repo_id and record.get("repoId") == repo_id]
    if len(repo_records) == 1:
        record = repo_records[0]
        old_root = record.get("currentRoot")
        if old_root and not registry_path_exists(old_root):
            return record, "moved-root", len(repo_records)
    return None, "new-project", len(repo_records)

def repo_id_from_remote_or_record(remote: str, record: dict[str, object] | None) -> str:
    if remote:
        return f"repo_{short_hash(remote)}"
    if record:
        existing = str(record.get("repoId") or "")
        if existing:
            return existing
    return f"repo_{uuid.uuid4().hex}"

def render_minimal_working_context(*, title: str, project_id: str, updated: str) -> str:
    metadata = frontmatter([
        ("type", "workingContext"),
        ("title", title),
        ("description", f"Current truth for {title}."),
        ("projectId", project_id),
        ("generator", "Codex"),
        ("status", "active"),
        ("promotionStatus", "pending"),
        ("promotedTo", []),
        ("date", updated),
        ("updated", updated),
    ])
    return f"""{metadata}

# Working Context

## Purpose

Describe the repository purpose.

## Current Truth

- Codex project identity is recorded in this file's Frontmatter as `projectId`.
- Project context is stored in the private global project folder for this `projectId`.

## Active Work

None.

## Important Constraints

None.

## Recent Decisions

None.

## Key Files

- `state:/working-context.md`
- `state:/sessions/`
- `state:/decisions/`

## Next Maintenance

- Update this dashboard when repository current truth changes.
"""

def update_working_context_identity(
    *,
    existing_text: str,
    title: str,
    project_id: str,
    updated: str,
) -> str:
    if not existing_text:
        return render_minimal_working_context(title=title, project_id=project_id, updated=updated)
    if existing_text.startswith("---"):
        lines, body = split_frontmatter_lines(existing_text)
        lines = replace_frontmatter_scalar(lines, "projectId", project_id)
        lines = replace_frontmatter_scalar(lines, "updated", updated)
        return "".join(lines) + body
    metadata = frontmatter([
        ("type", "workingContext"),
        ("title", title),
        ("description", f"Current truth for {title}."),
        ("projectId", project_id),
        ("generator", "Codex"),
        ("status", "active"),
        ("promotionStatus", "pending"),
        ("promotedTo", []),
        ("date", updated),
        ("updated", updated),
    ])
    return f"{metadata}\n\n{existing_text}"

def project_description(*, explicit_description: str | None, existing_project_text: str) -> str:
    if explicit_description is not None:
        return explicit_description
    if yaml_key_present(existing_project_text, "description"):
        return yaml_line_value(existing_project_text, "description")
    return ""

def render_local_project_yaml(
    *,
    project_id_value: str,
    title: str,
    description: str,
    created_at: str,
    updated_at: str,
) -> str:
    return "\n".join([
        f"projectId: {yaml_string(project_id_value)}",
        f"title: {yaml_string(title)}",
        f"description: {yaml_string(description)}",
        f"createdAt: {created_at}",
        f"updatedAt: {updated_at}",
        "",
    ])

def read_jsonl(path: Path, result: Result) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            result.warn(f"{path}:{line_number}: {exc}")
            continue
        if isinstance(value, dict):
            records.append(value)
        else:
            result.warn(f"{path}:{line_number}: ignoring non-object JSONL record")
    return records

def write_registry_record(index_path: Path, record: dict[str, object], write: bool, result: Result) -> None:
    records = read_jsonl(index_path, result)
    workspace = record["workspaceId"]
    kept = [item for item in records if item.get("workspaceId") != workspace]
    kept.append(record)
    text = "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in kept) + "\n"
    result.add("write", str(index_path))
    if write:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(text, encoding="utf-8")

def initialize_store_layout(
    target: Path,
    write: bool,
    result: Result,
    *,
    create_index: bool = True,
    create_working_context: bool = True,
    create_readme: bool = True,
) -> None:
    ensure_dir(target / "config", write, result)
    ensure_dir(data_root(target), write, result)
    ensure_dir(state_root(target), write, result)
    write_text(config_path(target), CONFIG_TEXT, write, result)
    for rel in DATA_CONTEXT_DIRS:
        ensure_dir(data_root(target) / rel, write, result)
    if create_index:
        write_text(registry_path(target), "", write, result)
    if create_working_context:
        write_text(data_root(target) / "working-context.md", global_working_context(), write, result)
    if create_readme:
        write_text(target / "README.md", store_readme(), write, result)

def init_project(args: argparse.Namespace) -> Result:
    target = expand_store_root(args.target)
    repo_root = expand(args.repo_root)
    now = now_iso()
    result = Result()

    initialize_store_layout(target, args.write, result)
    index_path = registry_path(target)

    local_project_path = repo_root / LOCAL_MARKER
    legacy_local_project_path = repo_root / LEGACY_LOCAL_MARKER
    existing_local_project_text = ""
    if local_project_path.exists():
        existing_local_project_text = local_project_path.read_text(encoding="utf-8", errors="replace")
    elif legacy_local_project_path.exists():
        existing_local_project_text = legacy_local_project_path.read_text(encoding="utf-8", errors="replace")
        result.add("legacy-marker", str(legacy_local_project_path))
    local_project_id = yaml_value(existing_local_project_text, "projectId")
    remote = git_value(repo_root, "config", "--get", "remote.origin.url")
    display = remote_display(remote)
    remote_identity = display or remote
    repo_id_from_remote = f"repo_{short_hash(remote_identity)}" if remote_identity else ""
    records = read_jsonl(index_path, result)
    legacy_root = expand(LEGACY_CONTEXT_ROOT)
    legacy_index_path = legacy_root / "projects" / "index.jsonl"
    legacy_records = read_jsonl(legacy_index_path, result)
    selection_records = [*records]
    known_workspaces = {str(record.get("workspaceId") or "") for record in selection_records}
    selection_records.extend(
        record
        for record in legacy_records
        if str(record.get("workspaceId") or "") not in known_workspaces
    )
    selected_record, project_reason, repo_record_count = select_project_record(
        selection_records,
        repo_root,
        repo_id_from_remote,
        local_project_id,
    )
    title = project_title(repo_root, args.title, str(selected_record.get("title") or "") if selected_record else "")
    project_id_value = str(selected_record.get("projectId") or "") if selected_record else ""
    if not project_id_value and local_project_id and project_reason != "new-project-local-conflict":
        project_id_value = local_project_id
    if not project_id_value:
        project_id_value = project_id(title, now)
    workspace_id_value = workspace_id(str(selected_record.get("workspaceId") or "") if selected_record else "")
    repo_id = repo_id_from_remote or repo_id_from_remote_or_record("", selected_record)
    status = args.status
    sensitivity = args.sensitivity
    project_context_path = project_state_path(target, project_id_value)
    working_context_path = project_context_path / "working-context.md"
    sessions_path = project_context_path / "sessions"
    decisions_path = project_context_path / "decisions"
    memos_path = project_context_path / "memos"
    local_seed_path = repo_root / ".codex-context" / "working-context.md"

    legacy_project_context_path = legacy_root / "projects" / project_id_value
    should_copy_legacy_project = not any(
        record.get("projectId") == project_id_value for record in records
    )
    planned_copies = plan_non_destructive_copies(
        [(legacy_project_context_path, project_context_path)] if should_copy_legacy_project else [],
        result,
    )
    execute_non_destructive_copies(planned_copies, args.write)

    ensure_dir(project_context_path, args.write, result)
    for path in (sessions_path, decisions_path, memos_path):
        ensure_dir(path, args.write, result)

    if working_context_path.exists():
        existing_text = working_context_path.read_text(encoding="utf-8", errors="replace")
    elif (legacy_project_context_path / "working-context.md").exists():
        existing_text = (legacy_project_context_path / "working-context.md").read_text(
            encoding="utf-8", errors="replace"
        )
    elif local_seed_path.exists():
        existing_text = local_seed_path.read_text(encoding="utf-8", errors="replace")
        result.add("seed", f"{local_seed_path} -> {working_context_path}")
    else:
        existing_text = ""

    working_context_text = update_working_context_identity(
        existing_text=existing_text,
        title=title,
        project_id=project_id_value,
        updated=now,
    )
    write_text(working_context_path, working_context_text, args.write, result, overwrite=True)

    keep_created_at = local_project_id == project_id_value
    local_project_text = render_local_project_yaml(
        project_id_value=project_id_value,
        title=title,
        description=project_description(
            explicit_description=args.description,
            existing_project_text=existing_local_project_text,
        ),
        created_at=(yaml_value(existing_local_project_text, "createdAt") if keep_created_at else "") or now,
        updated_at=now,
    )
    ensure_dir(local_project_path.parent, args.write, result)
    write_text(local_project_path, local_project_text, args.write, result, overwrite=True)

    if project_reason == "new-project-local-conflict":
        result.warn(
            f"creating a new projectId because local marker projectId {local_project_id} "
            "is already registered to an existing root or multiple registry records"
        )
    elif project_reason == "new-project" and repo_record_count:
        result.warn(
            f"creating a new projectId for repoId {repo_id}; "
            "existing registry root still exists or multiple project candidates matched"
        )
    elif project_reason == "moved-root":
        result.add("reuse-workspace", f"{workspace_id_value} (folder move detected)")
    elif project_reason == "same-root":
        result.add("reuse-workspace", f"{workspace_id_value} (same root)")

    registry_record = {
        "workspaceId": workspace_id_value,
        "projectId": project_id_value,
        "repoId": repo_id,
        "title": title,
        "currentRoot": repo_root.as_posix(),
        "projectContextPath": project_context_path.as_posix(),
        "workingContextPath": working_context_path.as_posix(),
        "sessionsPath": sessions_path.as_posix(),
        "decisionsPath": decisions_path.as_posix(),
        "memosPath": memos_path.as_posix(),
        "lastSeenAt": now,
        "status": status,
        "sensitivity": sensitivity,
    }
    write_registry_record(index_path, registry_record, args.write, result)
    return result

def global_working_context() -> str:
    created = now_iso()
    metadata = frontmatter([
        ("type", "globalWorkingContext"),
        ("title", "Global Codex Working Context"),
        ("description", "User-global Codex context dashboard."),
        ("generator", "Codex"),
        ("status", "active"),
        ("scope", "global"),
        ("sourceRefs", []),
        ("date", created),
        ("updated", created),
        ("contextId", "global-working-context"),
    ])
    return f"""{metadata}

# Global Codex Working Context

## Purpose

This file is the lightweight dashboard for user-global Codex context.

## Current Truth

- Global Codex context is stored in `~/.tkn/codex-context/data`.
- Generated context is kept separate from Codex configuration in `~/.codex`.
- Project working contexts are stored in `state/<projectId>/`; Codex project folders are tracked in `state/index.jsonl`.
- Repositories should load selected global context read-only by default.
- Repository snapshots require an explicit destination chosen from current project folder instructions.
- Snapshot global context is historical reference, not an override for repository rules or current user instructions.

## Active Work

- Establish explicit bridges for project initialization, context import, and promotion.

## Important Constraints

- Do not store secrets, credentials, tokens, private keys, full env vars, large logs, or unnecessary personal/customer data.
- This store is private, so project registry records may include local absolute paths.
- Prefer candidates for unaccepted learnings.
- Promote only reusable decisions and user-level working preferences.

## Key Files

- `../state/index.jsonl`
- `../state/<projectId>/working-context.md`
- `../state/<projectId>/sessions/`
- `../state/<projectId>/decisions/`
- `../state/<projectId>/memos/`
- `decisions/`
- `candidates/`
- `patterns/`
- `skill-candidates/`
- `agents-candidates/`
"""

def store_readme() -> str:
    return """# Codex Global Context

This directory stores private user-global and project Codex context. It is not Codex configuration.

## Structure

- `config/config.yaml`: store schema version.
- `data/working-context.md`: user-global working context dashboard.
- `data/decisions/`, `data/candidates/`, and related folders: reusable global context.
- `state/index.jsonl`: project registry.
- `state/<projectId>/`: project working context, sessions, decisions, and memos.

## Safety

Do not store secrets, credentials, tokens, private keys, full environment variables, large logs, or unnecessary personal or customer data here.
"""

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=DEFAULT_CONTEXT_ROOT)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--title")
    parser.add_argument("--description")
    parser.add_argument("--status", choices=["active", "inactive", "archived"], default="active")
    parser.add_argument("--sensitivity", choices=["private", "internal", "public"], default="private")
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
    result = init_project(args)
    print_result(result, args.write, args.log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
