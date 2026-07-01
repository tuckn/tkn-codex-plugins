#!/usr/bin/env python3
"""Manage Codex context registration, loading, auditing, imports, and promotions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable


JST = timezone(timedelta(hours=9))
DEFAULT_INCLUDE = "working-context,decisions,candidates"
DEFAULT_LOAD_INCLUDE = "working-context,decisions,candidates,patterns,skill-candidates,agents-candidates"
DEFAULT_FRESHNESS_INCLUDE = (
    "working-context,project,decisions,sessions,candidates,patterns,skill-candidates,agents-candidates,reviews"
)
GLOBAL_CONTEXT_DIRS = [
    "decisions",
    "candidates",
    "projects",
    "patterns",
    "skill-candidates",
    "agents-candidates",
    "reviews",
]
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
]
FRONTMATTER_PATTERN = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n?", re.DOTALL)
SCALAR_FIELD_PATTERN = r"(?m)^\s*{key}:\s*['\"]?([^'\"\r\n#]+)"


@dataclass
class Operation:
    action: str
    detail: str


@dataclass
class Result:
    operations: list[Operation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add(self, action: str, detail: str) -> None:
        self.operations.append(Operation(action, detail))

    def warn(self, message: str) -> None:
        self.warnings.append(message)


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


def now_compact() -> str:
    return datetime.now(JST).strftime("%Y%m%dT%H%M%S%z")


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def expand(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "global-context"


def yaml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def yaml_string_list(values: Iterable[str]) -> str:
    items = [value for value in values if value]
    if not items:
        return "[]"
    return "\n".join(f"  - {yaml_string(value)}" for value in items)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def short_hash(value: str) -> str:
    return sha256_text(value)[:16]


def yaml_value(text: str, key: str) -> str:
    match = re.search(SCALAR_FIELD_PATTERN.format(key=re.escape(key)), text)
    if not match:
        return ""
    return match.group(1).strip()


def source_ref(path: Path) -> str:
    cwd = Path.cwd().resolve()
    try:
        return path.relative_to(cwd).as_posix()
    except ValueError:
        return str(path)


def source_repo(args: argparse.Namespace) -> str:
    if getattr(args, "source_repo", None):
        return args.source_repo
    return Path.cwd().resolve().name


def frontmatter(fields: list[tuple[str, str | list[str]]]) -> str:
    lines = ["---"]
    for key, value in fields:
        if isinstance(value, list):
            rendered = yaml_string_list(value)
            if rendered == "[]":
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                lines.append(rendered)
        else:
            lines.append(f"{key}: {yaml_string(value)}")
    lines.append("---")
    return "\n".join(lines)


def parse_include(value: str) -> set[str]:
    allowed = {"working-context", "decisions", "candidates"}
    parts = {part.strip() for part in value.split(",") if part.strip()}
    unknown = parts - allowed
    if unknown:
        raise SystemExit(f"Unknown include value(s): {', '.join(sorted(unknown))}")
    return parts or set(allowed)


def parse_load_include(value: str) -> set[str]:
    allowed = {
        "working-context",
        "decisions",
        "candidates",
        "patterns",
        "skill-candidates",
        "agents-candidates",
    }
    parts = {part.strip() for part in value.split(",") if part.strip()}
    unknown = parts - allowed
    if unknown:
        raise SystemExit(f"Unknown include value(s): {', '.join(sorted(unknown))}")
    return parts or set(allowed)


def parse_freshness_include(value: str) -> set[str]:
    allowed = {
        "working-context",
        "project",
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


def has_secret_like_content(text: str) -> list[str]:
    hits = []
    for pattern in SECRET_PATTERNS:
        match = pattern.search(text)
        if match:
            hits.append(pattern.pattern)
    return hits


def strip_frontmatter(text: str) -> str:
    return FRONTMATTER_PATTERN.sub("", text, count=1)


def parse_simple_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip() or line.startswith((" ", "\t")) or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        value = raw_value.strip()
        if value in {"", "[]"}:
            metadata[key.strip()] = ""
        else:
            metadata[key.strip()] = value.strip("'\"")
    return metadata


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
    if (source / "sessions").exists() or (source / "project.yml").exists():
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
    if category == "project":
        return args.project_days
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
        ("project", source / "project.yml", False),
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
- Project identity: {args.project_days} days
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


def update_frontmatter_field(text: str, key: str, value: str) -> str:
    if not text.startswith("---"):
        return text
    return re.sub(
        rf"(?m)^({re.escape(key)}): .*$",
        rf"\1: {yaml_string(value)}",
        text,
        count=1,
    )


def write_text(path: Path, text: str, write: bool, result: Result, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        result.add("skip-existing", str(path))
        return
    result.add("write", str(path))
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def ensure_dir(path: Path, write: bool, result: Result) -> None:
    result.add("mkdir", str(path))
    if write:
        path.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dest: Path, write: bool, result: Result) -> None:
    if not src.exists():
        result.warn(f"missing source: {src}")
        return
    text = src.read_text(encoding="utf-8", errors="replace")
    hits = has_secret_like_content(text)
    if hits:
        raise SystemExit(f"Sensitive-looking content detected in {src}; refusing to copy.")
    result.add("copy", f"{src} -> {dest}")
    if write:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def list_selected_files(folder: Path, selected: Iterable[str] | None) -> list[Path]:
    if selected:
        return [folder / name for name in selected]
    if not folder.exists():
        return []
    return sorted(path for path in folder.glob("*.md") if path.is_file())


def ensure_md_name(value: str) -> str:
    return value if value.endswith(".md") else f"{value}.md"


def list_named_files(folder: Path, names: Iterable[str] | None) -> list[Path]:
    if not names:
        return []
    return [folder / ensure_md_name(name) for name in names]


def compact_preview(text: str, max_lines: int) -> str:
    lines: list[str] = []
    for raw_line in strip_frontmatter(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#") or len(lines) < max_lines:
            lines.append(line)
        if len(lines) >= max_lines:
            break
    return " | ".join(lines) if lines else "(no preview text)"


def add_file_preview(path: Path, label: str, max_lines: int, result: Result) -> None:
    if not path.exists():
        result.warn(f"missing {label}: {path}")
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    hits = has_secret_like_content(text)
    if hits:
        raise SystemExit(f"Sensitive-looking content detected in {path}; refusing to preview.")
    result.add(f"preview {label}", compact_preview(text, max_lines))


def add_file_list(folder: Path, label: str, result: Result) -> None:
    files = list_selected_files(folder, None)
    if files:
        names = ", ".join(path.name for path in files)
    else:
        names = "(none)"
    result.add(f"list {label}", names)


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


def id_from_existing_or_remote(existing: str, prefix: str, remote: str) -> str:
    if existing:
        return existing
    if remote:
        return f"{prefix}_{short_hash(remote)}"
    return f"{prefix}_{uuid.uuid4().hex}"


def workspace_id(existing: str) -> str:
    return existing or f"ws_{uuid.uuid4().hex}"


def render_project_yml(
    *,
    title: str,
    project_id: str,
    workspace_id_value: str,
    repo_id: str,
    remote_hash: str,
    remote_display_value: str,
    branch: str,
    status: str,
    sensitivity: str,
    created: str,
    updated: str,
) -> str:
    return f"""---
type: codexProjectContext
schemaVersion: 1
title: {yaml_string(title)}
generator: Codex
created: {yaml_string(created)}
updated: {yaml_string(updated)}
---

identity:
  projectId: {yaml_string(project_id)}
  workspaceId: {yaml_string(workspace_id_value)}
  repoId: {yaml_string(repo_id)}

paths:
  currentRoot: ""
  knownRoots: []

vcs:
  type: "git"
  primaryRemoteHash: {yaml_string(remote_hash)}
  primaryRemoteDisplay: {yaml_string(remote_display_value)}
  currentBranch: {yaml_string(branch)}

context:
  localContextPath: ".codex-context"
  workingContextPath: ".codex-context/working-context.md"
  decisionsPath: ".codex-context/decisions"
  sessionsPath: ".codex-context/sessions"

status:
  lifecycle: {yaml_string(status)}
  sensitivity: {yaml_string(sensitivity)}
  lastSeenAt: {yaml_string(updated)}
"""


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


def register_project(args: argparse.Namespace) -> Result:
    target = expand(args.target)
    repo_root = expand(args.repo_root)
    project_file = repo_root / Path(args.project_file.replace("\\", "/"))
    now = now_iso()
    result = Result()

    for rel in GLOBAL_CONTEXT_DIRS:
        ensure_dir(target / rel, args.write, result)
    write_text(target / "projects" / "index.jsonl", "", args.write, result)
    write_text(target / "README.md", global_readme(), args.write, result)
    write_text(target / "working-context.md", global_working_context(), args.write, result)

    existing_text = project_file.read_text(encoding="utf-8", errors="replace") if project_file.exists() else ""
    remote = git_value(repo_root, "config", "--get", "remote.origin.url")
    display = remote_display(remote)
    remote_hash = f"sha256:{sha256_text(display or remote)}" if remote else ""
    branch = git_value(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    title = project_title(repo_root, args.title, yaml_value(existing_text, "title"))
    created = yaml_value(existing_text, "created") or now
    project_id = id_from_existing_or_remote(yaml_value(existing_text, "projectId"), "prj", display or remote)
    workspace_id_value = workspace_id(yaml_value(existing_text, "workspaceId"))
    repo_id = id_from_existing_or_remote(yaml_value(existing_text, "repoId"), "repo", display or remote)
    status = args.status
    sensitivity = args.sensitivity

    project_text = render_project_yml(
        title=title,
        project_id=project_id,
        workspace_id_value=workspace_id_value,
        repo_id=repo_id,
        remote_hash=remote_hash,
        remote_display_value=display,
        branch=branch,
        status=status,
        sensitivity=sensitivity,
        created=created,
        updated=now,
    )
    write_text(project_file, project_text, args.write, result, overwrite=True)

    registry_record = {
        "workspaceId": workspace_id_value,
        "projectId": project_id,
        "repoId": repo_id,
        "title": title,
        "currentRoot": repo_root.as_posix(),
        "localContextPath": (repo_root / ".codex-context").as_posix(),
        "projectFilePath": project_file.as_posix(),
        "lastSeenAt": now,
        "status": status,
        "sensitivity": sensitivity,
    }
    write_registry_record(target / "projects" / "index.jsonl", registry_record, args.write, result)
    return result


def global_readme() -> str:
    return f"""# Codex Global Context

This directory stores user-global Codex context.

It is not Codex configuration. Keep generated context here, and keep `~/.codex` focused on Codex settings.
This store is intended to be private.

## Structure

- `working-context.md`: lightweight user-global current truth.
- `decisions/`: accepted global or user-level decisions.
- `candidates/`: useful context that is not accepted as a decision yet.
- `projects/index.jsonl`: registry of local Codex project workspaces.
- `projects/<workspaceId>/`: optional per-workspace registry metadata.
- `patterns/`: reusable cross-project patterns.
- `skill-candidates/`: candidates for reusable Skills or Plugins.
- `agents-candidates/`: candidates for global or repository AGENTS.md guidance.
- `reviews/`: explicit global context review outputs.

## Safety

Do not store secrets, credentials, tokens, private keys, full env vars, large logs, or unnecessary personal/customer data here.

Created: {now_iso()}
"""


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

- Global Codex context is stored in `~/.codex-context`.
- Generated context is kept separate from Codex configuration in `~/.codex`.
- Project workspaces are tracked in `projects/index.jsonl` by stable workspace IDs.
- Repositories should load selected global context read-only by default.
- Repository snapshots should go under `.local/codex-context/global-context/` unless explicitly requested elsewhere.
- Snapshot global context is historical reference, not an override for repository rules or current user instructions.

## Active Work

- Establish explicit bridges for repository context registration, import, and promotion.

## Important Constraints

- Do not store secrets, credentials, tokens, private keys, full env vars, large logs, or unnecessary personal/customer data.
- This store is private, so project registry records may include local absolute paths.
- Prefer candidates for unaccepted learnings.
- Promote only reusable decisions and user-level working preferences.

## Key Files

- `projects/index.jsonl`
- `decisions/`
- `candidates/`
- `patterns/`
- `skill-candidates/`
- `agents-candidates/`
"""


def repo_global_readme() -> str:
    return f"""# Imported Global Context

This folder contains selected context imported from `~/.codex-context`.

Imported context is a historical snapshot reference. It does not override:

- current user instructions
- repository `AGENTS.md`
- repository specs
- current file contents
- git state

Use `imports/` manifests to see when and why context was imported.

Prefer read-only load for routine work. Write snapshots only when explicitly requested.

Created: {now_iso()}
"""


def init_store(args: argparse.Namespace) -> Result:
    target = expand(args.target)
    result = Result()
    for rel in GLOBAL_CONTEXT_DIRS:
        ensure_dir(target / rel, args.write, result)
    write_text(target / "projects" / "index.jsonl", "", args.write, result)
    write_text(target / "README.md", global_readme(), args.write, result)
    write_text(target / "working-context.md", global_working_context(), args.write, result)
    return result


def import_context(args: argparse.Namespace) -> Result:
    source = expand(args.source)
    dest = expand(args.dest)
    include = parse_include(args.include)
    result = Result()

    if not source.exists():
        raise SystemExit(f"Source does not exist: {source}")

    for rel in ["decisions", "candidates", "imports"]:
        ensure_dir(dest / rel, args.write, result)
    write_text(dest / "README.md", repo_global_readme(), args.write, result)

    imported: list[str] = []

    if "working-context" in include:
        src = source / "working-context.md"
        out = dest / "working-context.md"
        copy_file(src, out, args.write, result)
        if src.exists():
            imported.append(str(out))

    if "decisions" in include:
        for src in list_selected_files(source / "decisions", args.decision):
            out = dest / "decisions" / src.name
            copy_file(src, out, args.write, result)
            if src.exists():
                imported.append(str(out))

    if "candidates" in include:
        for src in list_selected_files(source / "candidates", args.candidate):
            out = dest / "candidates" / src.name
            copy_file(src, out, args.write, result)
            if src.exists():
                imported.append(str(out))

    manifest = make_manifest(source, dest, imported, result)
    write_text(dest / "imports" / f"{now_compact()}-import-manifest.md", manifest, args.write, result, overwrite=True)
    return result


def load_context(args: argparse.Namespace) -> Result:
    source = expand(args.source)
    include = parse_load_include(args.include)
    result = Result()

    if not source.exists():
        raise SystemExit(f"Source does not exist: {source}")

    result.add("source", str(source))
    result.add("mode", "read-only load; no files are written")

    if "working-context" in include:
        path = source / "working-context.md"
        if path.exists():
            add_file_preview(path, "working-context", args.preview_lines, result)
        else:
            result.warn(f"missing working-context: {path}")

    category_folders = [
        ("decisions", "decisions", args.decision),
        ("candidates", "candidates", args.candidate),
        ("patterns", "patterns", args.pattern),
        ("skill-candidates", "skill-candidates", args.skill_candidate),
        ("agents-candidates", "agents-candidates", args.agents_candidate),
    ]
    for include_name, folder_name, selected in category_folders:
        if include_name not in include:
            continue
        folder = source / folder_name
        add_file_list(folder, folder_name, result)
        for path in list_named_files(folder, selected):
            add_file_preview(path, folder_name, args.preview_lines, result)

    return result


def audit_freshness(args: argparse.Namespace) -> Result:
    source = expand(args.source)
    include = parse_freshness_include(args.include)
    result = Result()

    if not source.exists():
        raise SystemExit(f"Source does not exist: {source}")

    scope = freshness_scope(source, args.scope)
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
    report_path = expand(args.report_dest) / f"{now_compact()}-freshness-audit.md"

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

    write_text(report_path, report, args.write, result, overwrite=True)
    return result


def make_manifest(source: Path, dest: Path, imported: list[str], result: Result) -> str:
    imported_lines = "\n".join(f"- `{path}`" for path in imported) or "- None"
    warning_lines = "\n".join(f"- {warning}" for warning in result.warnings) or "- None"
    return f"""# Global Context Import Manifest

Date: {now_iso()}

## Source

`{source}`

## Destination

`{dest}`

## Imported Files

{imported_lines}

## Warnings

{warning_lines}

## Notes

This snapshot is historical reference only. Repository instructions, current user instructions,
current files, and git state take precedence. Validate imported context against current repository
state before use.
"""


def promote_context(args: argparse.Namespace) -> Result:
    target = expand(args.target)
    body_file = expand(args.body_file)
    if not body_file.exists():
        raise SystemExit(f"Body file does not exist: {body_file}")
    raw_body = body_file.read_text(encoding="utf-8", errors="replace")
    hits = has_secret_like_content(raw_body)
    if hits:
        raise SystemExit(f"Sensitive-looking content detected in {body_file}; refusing to promote.")
    body = strip_frontmatter(raw_body)

    result = Result()
    for rel in GLOBAL_CONTEXT_DIRS:
        ensure_dir(target / rel, args.write, result)
    write_text(target / "projects" / "index.jsonl", "", args.write, result)
    write_text(target / "README.md", global_readme(), args.write, result)
    write_text(target / "working-context.md", global_working_context(), args.write, result)

    updated = now_iso()
    ref = source_ref(body_file)
    repo = source_repo(args)

    if args.kind == "working-context":
        entry = f"""

## {args.title}

Source: `{ref}`
Source repo: `{repo}`
Updated: {updated}

{body.strip()}
"""
        path = target / "working-context.md"
        result.add("append", str(path))
        if args.write:
            existing = path.read_text(encoding="utf-8") if path.exists() else global_working_context()
            existing = update_frontmatter_field(existing, "updated", updated)
            path.write_text(existing.rstrip() + entry + "\n", encoding="utf-8")
        return result

    prefix = "DR-G" if args.kind == "decision" else now_compact()
    name = f"{prefix}-{slugify(args.title)}.md"
    folder = "decisions" if args.kind == "decision" else "candidates"
    path = target / folder / name
    content_type = "globalDecision" if args.kind == "decision" else "globalCandidate"
    status = "accepted" if args.kind == "decision" else "proposed"
    review_status = "accepted" if args.kind == "decision" else "reviewing"
    metadata = frontmatter([
        ("type", content_type),
        ("title", args.title),
        ("description", ""),
        ("generator", "Codex"),
        ("status", status),
        ("reviewStatus", review_status),
        ("scope", "global"),
        ("sourceRefs", [ref]),
        ("sourceRepo", repo),
        ("date", updated),
        ("updated", updated),
        ("contextId", str(uuid.uuid4())),
    ])
    content = f"""{metadata}

# {args.title}

{body.strip()}
"""
    write_text(path, content, args.write, result)
    return result


def print_result(result: Result, write: bool, log: str | None) -> None:
    mode = "write" if write else "dry-run"
    lines = [f"mode: {mode}", "operations:"]
    lines.extend(f"- {op.action}: {op.detail}" for op in result.operations)
    lines.append("warnings:")
    lines.extend(f"- {warning}" for warning in result.warnings or ["None"])
    output = "\n".join(lines)
    print(output)
    if log:
        path = expand(log)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="initialize ~/.codex-context")
    init.add_argument("--target", default="~/.codex-context")
    init.add_argument("--dry-run", action="store_true")
    init.add_argument("--write", action="store_true")
    init.add_argument("--log")
    init.set_defaults(func=init_store)

    read = sub.add_parser("import", help="import global context into a repository")
    read.add_argument("--source", default="~/.codex-context")
    read.add_argument("--dest", default=".local/codex-context/global-context")
    read.add_argument("--include", default=DEFAULT_INCLUDE)
    read.add_argument("--decision", action="append", help="specific decision markdown filename to import")
    read.add_argument("--candidate", action="append", help="specific candidate markdown filename to import")
    read.add_argument("--dry-run", action="store_true")
    read.add_argument("--write", action="store_true")
    read.add_argument("--log")
    read.set_defaults(func=import_context)

    load = sub.add_parser("load", help="read selected global context without writing files")
    load.add_argument("--source", default="~/.codex-context")
    load.add_argument("--include", default=DEFAULT_LOAD_INCLUDE)
    load.add_argument("--decision", action="append", help="specific decision markdown filename to preview")
    load.add_argument("--candidate", action="append", help="specific candidate markdown filename to preview")
    load.add_argument("--pattern", action="append", help="specific pattern markdown filename to preview")
    load.add_argument("--skill-candidate", action="append", help="specific skill-candidate markdown filename to preview")
    load.add_argument("--agents-candidate", action="append", help="specific agents-candidate markdown filename to preview")
    load.add_argument("--preview-lines", type=int, default=8)
    load.set_defaults(func=load_context, write=False)

    audit = sub.add_parser("audit-freshness", help="audit context freshness without changing source context")
    audit.add_argument("--source", default=".codex-context")
    audit.add_argument("--source-label")
    audit.add_argument("--scope", choices=["auto", "repo", "global"], default="auto")
    audit.add_argument("--include", default=DEFAULT_FRESHNESS_INCLUDE)
    audit.add_argument("--report-dest", default=".local/codex-context/freshness-reviews")
    audit.add_argument("--max-items", type=int, default=50)
    audit.add_argument("--working-context-days", type=int, default=30)
    audit.add_argument("--project-days", type=int, default=30)
    audit.add_argument("--session-days", type=int, default=90)
    audit.add_argument("--session-pending-days", type=int, default=14)
    audit.add_argument("--decision-days", type=int, default=180)
    audit.add_argument("--candidate-days", type=int, default=60)
    audit.add_argument("--pattern-days", type=int, default=120)
    audit.add_argument("--promotion-pending-days", type=int, default=30)
    audit.add_argument("--default-days", type=int, default=90)
    audit.add_argument("--dry-run", action="store_true")
    audit.add_argument("--write", action="store_true")
    audit.add_argument("--log")
    audit.set_defaults(func=audit_freshness)

    register = sub.add_parser("register-project", help="register this repository in ~/.codex-context")
    register.add_argument("--target", default="~/.codex-context")
    register.add_argument("--repo-root", default=".")
    register.add_argument("--project-file", default=".codex-context/project.yml")
    register.add_argument("--title")
    register.add_argument("--status", choices=["active", "inactive", "archived"], default="active")
    register.add_argument("--sensitivity", choices=["private", "internal", "public"], default="private")
    register.add_argument("--dry-run", action="store_true")
    register.add_argument("--write", action="store_true")
    register.add_argument("--log")
    register.set_defaults(func=register_project)

    promote = sub.add_parser("promote", help="promote context into ~/.codex-context")
    promote.add_argument("--target", default="~/.codex-context")
    promote.add_argument("--kind", choices=["working-context", "decision", "candidate"], required=True)
    promote.add_argument("--title", required=True)
    promote.add_argument("--body-file", required=True)
    promote.add_argument("--source-repo", help="source repository name or label for destination metadata")
    promote.add_argument("--dry-run", action="store_true")
    promote.add_argument("--write", action="store_true")
    promote.add_argument("--log")
    promote.set_defaults(func=promote_context)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.write and getattr(args, "dry_run", False):
        parser.error("Use either --dry-run or --write, not both.")
    if not args.write:
        args.dry_run = True
    result = args.func(args)
    print_result(result, args.write, getattr(args, "log", None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
