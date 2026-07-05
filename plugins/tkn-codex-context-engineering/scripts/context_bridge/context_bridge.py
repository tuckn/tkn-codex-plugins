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
    "working-context,decisions,sessions,candidates,patterns,skill-candidates,agents-candidates,reviews"
)
DISTILL_REUSABLE_SECTIONS = [
    "important decisions",
    "what worked",
    "failed approaches",
    "constraints",
]
DISTILL_FOLLOW_UP_SECTIONS = [
    "open issues",
    "next steps",
    "exact next step",
]
DISTILL_EVIDENCE_SECTIONS = [
    "user intent / interaction summary",
    "working context",
    "changed files",
    "validation",
]
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


def yaml_key_present(text: str, key: str) -> bool:
    return re.search(rf"(?m)^\s*{re.escape(key)}:\s*", text) is not None


def yaml_line_value(text: str, key: str) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(key)}:\s*(.*)$", text)
    if not match:
        return ""
    raw = match.group(1).strip()
    if raw == "[]":
        return ""
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
        return raw[1:-1]
    if "#" in raw:
        raw = raw.split("#", 1)[0].strip()
    return raw


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


def split_frontmatter_lines(text: str) -> tuple[list[str], str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise SystemExit("Source file must have YAML frontmatter.")
    for index, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return lines[: index + 1], "".join(lines[index + 1 :])
    raise SystemExit("Source file has an opening frontmatter delimiter but no closing delimiter.")


def strip_yaml_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def frontmatter_key_block(lines: list[str], key: str) -> tuple[int, int] | None:
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.*)$")
    for index in range(1, len(lines) - 1):
        if pattern.match(lines[index].rstrip("\r\n")):
            end = index + 1
            while end < len(lines) - 1:
                candidate = lines[end]
                if candidate.startswith((" ", "\t")) or candidate.strip() == "":
                    end += 1
                    continue
                break
            return index, end
    return None


def frontmatter_list_value(lines: list[str], key: str) -> list[str]:
    block = frontmatter_key_block(lines, key)
    if not block:
        return []
    start, end = block
    match = re.match(rf"^{re.escape(key)}:\s*(.*)$", lines[start].rstrip("\r\n"))
    if not match:
        return []
    inline = match.group(1).strip()
    if inline == "[]":
        return []
    if inline:
        return [strip_yaml_quotes(inline)]
    values: list[str] = []
    for line in lines[start + 1 : end]:
        item = re.match(r"^\s*-\s*(.*?)\s*$", line.rstrip("\r\n"))
        if item:
            values.append(strip_yaml_quotes(item.group(1)))
    return values


def replace_frontmatter_scalar(lines: list[str], key: str, value: str) -> list[str]:
    replacement = [f"{key}: {yaml_string(value)}\n"]
    block = frontmatter_key_block(lines, key)
    if block:
        start, end = block
        return lines[:start] + replacement + lines[end:]
    return lines[:-1] + replacement + lines[-1:]


def replace_frontmatter_list(lines: list[str], key: str, values: list[str]) -> list[str]:
    if values:
        replacement = [f"{key}:\n", *[f"  - {yaml_string(value)}\n" for value in values]]
    else:
        replacement = [f"{key}: []\n"]
    block = frontmatter_key_block(lines, key)
    if block:
        start, end = block
        return lines[:start] + replacement + lines[end:]
    return lines[:-1] + replacement + lines[-1:]


def normalized_context_ref(value: str) -> str:
    return value.strip().replace("\\", "/")


def validate_distilled_to_ref(value: str) -> str:
    ref = normalized_context_ref(value)
    if not ref:
        raise SystemExit("distilledTo path cannot be empty.")
    if re.match(r"^[A-Za-z]:/", ref):
        raise SystemExit(f"Refusing Windows absolute distilledTo path: {value}")
    if ref.startswith("//"):
        raise SystemExit(f"Refusing UNC distilledTo path: {value}")
    if ref.startswith("/"):
        raise SystemExit(f"Refusing absolute distilledTo path: {value}")
    if ref == "~" or (ref.startswith("~/") and not ref.startswith("~/.codex-context/")):
        raise SystemExit(f"Only ~/.codex-context paths are allowed for home-relative distilledTo refs: {value}")
    if ref == ".." or ref.startswith("../") or "/../" in ref:
        raise SystemExit(f"Refusing parent-traversal distilledTo path: {value}")
    return ref


def unique_ordered(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


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


def normalize_heading(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def markdown_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = ""
    for line in strip_frontmatter(text).splitlines():
        match = re.match(r"^(#{2,6})\s+(.+?)\s*$", line)
        if match:
            current = normalize_heading(match.group(2))
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line.rstrip())
    return sections


def bounded_section_text(sections: dict[str, list[str]], name: str, max_lines: int) -> str:
    lines = []
    for line in sections.get(name, []):
        stripped = line.strip()
        if not stripped:
            continue
        lines.append(stripped)
        if len(lines) >= max_lines:
            break
    if not lines:
        return "- None recorded."
    return "\n".join(lines)


def render_distill_section_group(
    title: str,
    section_names: list[str],
    sections: dict[str, list[str]],
    max_lines: int,
) -> str:
    blocks = [f"## {title}"]
    for name in section_names:
        blocks.append(f"### {name.title()}")
        blocks.append(bounded_section_text(sections, name, max_lines))
    return "\n\n".join(blocks)


def render_session_distillation(
    *,
    session_path: Path,
    metadata: dict[str, str],
    sections: dict[str, list[str]],
    args: argparse.Namespace,
) -> str:
    updated = now_iso()
    title = args.title or metadata.get("title") or session_path.stem
    source = source_ref(session_path)
    repo = source_repo(args)
    description = metadata.get("description", "")
    source_updated = metadata.get("updated") or metadata.get("date") or ""
    source_status = metadata.get("status", "")
    source_distillation = metadata.get("distillationStatus", "")
    candidate_title = f"Distilled session candidate: {title}"
    metadata_block = frontmatter([
        ("type", "sessionDistillationCandidate"),
        ("title", candidate_title),
        ("description", description),
        ("generator", "Codex"),
        ("status", "proposed"),
        ("reviewStatus", "reviewing"),
        ("distilledKind", args.kind),
        ("sourceRefs", [source]),
        ("sourceRepo", repo),
        ("sourceSessionStatus", source_status),
        ("sourceDistillationStatus", source_distillation),
        ("date", updated),
        ("updated", updated),
        ("contextId", str(uuid.uuid4())),
    ])
    return f"""{metadata_block}

# {candidate_title}

## Summary

- Source session: `{source}`
- Source repo: `{repo}`
- Proposed destination kind: `{args.kind}`
- Source updated: {source_updated or "unknown"}
- Source status: {source_status or "unknown"}
- Source distillation status: {source_distillation or "unknown"}
- Review required before promotion: yes

## Usage Guidance

- Treat this file as a review candidate, not accepted repository or global context.
- Revalidate the extracted points against current user instructions, repository instructions, current files, and git state.
- Promote only the reusable parts to working context, decisions, global context, AGENTS.md, or a Skill.
- Do not promote raw chronological detail unless it prevents a repeated failure.

{render_distill_section_group("Reusable Learnings", DISTILL_REUSABLE_SECTIONS, sections, args.max_section_lines)}

{render_distill_section_group("Follow-Up Candidates", DISTILL_FOLLOW_UP_SECTIONS, sections, args.max_section_lines)}

{render_distill_section_group("Evidence Snapshot", DISTILL_EVIDENCE_SECTIONS, sections, args.max_section_lines)}

## Exclusions

- Full chat transcript was not copied.
- Full session note was not copied.
- The source session note was not modified.
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

- `working-context.md`
- `sessions/`
- `decisions/`

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


def register_project(args: argparse.Namespace) -> Result:
    target = expand(args.target)
    repo_root = expand(args.repo_root)
    now = now_iso()
    result = Result()

    for rel in GLOBAL_CONTEXT_DIRS:
        ensure_dir(target / rel, args.write, result)
    registry_path = target / "projects" / "index.jsonl"
    write_text(registry_path, "", args.write, result)
    write_text(target / "README.md", global_readme(), args.write, result)
    write_text(target / "working-context.md", global_working_context(), args.write, result)

    local_project_path = repo_root / ".codex-context" / "project.yaml"
    existing_local_project_text = ""
    if local_project_path.exists():
        existing_local_project_text = local_project_path.read_text(encoding="utf-8", errors="replace")
    local_project_id = yaml_value(existing_local_project_text, "projectId")
    remote = git_value(repo_root, "config", "--get", "remote.origin.url")
    display = remote_display(remote)
    remote_identity = display or remote
    repo_id_from_remote = f"repo_{short_hash(remote_identity)}" if remote_identity else ""
    records = read_jsonl(registry_path, result)
    selected_record, project_reason, repo_record_count = select_project_record(
        records,
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
    project_context_path = target / "projects" / project_id_value
    working_context_path = project_context_path / "working-context.md"
    sessions_path = project_context_path / "sessions"
    decisions_path = project_context_path / "decisions"
    local_seed_path = repo_root / ".codex-context" / "working-context.md"

    ensure_dir(project_context_path, args.write, result)
    ensure_dir(sessions_path, args.write, result)
    ensure_dir(decisions_path, args.write, result)

    if working_context_path.exists():
        existing_text = working_context_path.read_text(encoding="utf-8", errors="replace")
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
            f"creating a new projectId because local project.yaml projectId {local_project_id} "
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
        "lastSeenAt": now,
        "status": status,
        "sensitivity": sensitivity,
    }
    write_registry_record(registry_path, registry_record, args.write, result)
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
- `projects/<projectId>/`: private project context folder with `working-context.md`, `sessions/`, and `decisions/`.
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
- Project working contexts are stored in `projects/<projectId>/`; Codex project folders are tracked in `projects/index.jsonl`.
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
- `projects/<projectId>/working-context.md`
- `projects/<projectId>/sessions/`
- `projects/<projectId>/decisions/`
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


def distill_session(args: argparse.Namespace) -> Result:
    session_path = expand(args.session)
    dest = expand(args.dest)
    result = Result()

    if not session_path.exists():
        raise SystemExit(f"Session note does not exist: {session_path}")
    text = session_path.read_text(encoding="utf-8", errors="replace")
    hits = has_secret_like_content(text)
    if hits:
        raise SystemExit(f"Sensitive-looking content detected in {session_path}; refusing to distill.")

    metadata = parse_simple_frontmatter(text)
    if metadata.get("type") and metadata.get("type") != "session":
        result.warn(f"source type is {metadata.get('type')}, expected session")
    sections = markdown_sections(text)
    title = args.title or metadata.get("title") or session_path.stem
    out_name = f"{now_compact()}-{slugify(title)}-distillation.md"
    out_path = dest / out_name
    content = render_session_distillation(
        session_path=session_path,
        metadata=metadata,
        sections=sections,
        args=args,
    )

    result.add("source", str(session_path))
    result.add("mode", "candidate distillation; source session is not modified")
    result.add("kind", args.kind)
    result.add("sections", ", ".join(sorted(sections)) if sections else "(none)")
    write_text(out_path, content, args.write, result, overwrite=True)
    return result


def finalize_session_distillation(args: argparse.Namespace) -> Result:
    session_path = expand(args.session)
    result = Result()

    if not session_path.exists():
        raise SystemExit(f"Session note does not exist: {session_path}")
    if args.status in {"distilled", "partial"} and not args.distilled_to:
        raise SystemExit(f"--status {args.status} requires at least one --distilled-to value.")

    text = session_path.read_text(encoding="utf-8", errors="replace")
    header_lines, body = split_frontmatter_lines(text)
    metadata = parse_simple_frontmatter(text)
    if metadata.get("type") and metadata.get("type") != "session":
        result.warn(f"source type is {metadata.get('type')}, expected session")

    existing_refs = [validate_distilled_to_ref(value) for value in frontmatter_list_value(header_lines, "distilledTo")]
    new_refs = [validate_distilled_to_ref(value) for value in args.distilled_to or []]
    if args.status == "no-action":
        distilled_refs: list[str] = []
    else:
        distilled_refs = unique_ordered([*existing_refs, *new_refs])

    updated = now_iso()
    updated_header = replace_frontmatter_scalar(header_lines, "distillationStatus", args.status)
    updated_header = replace_frontmatter_list(updated_header, "distilledTo", distilled_refs)
    updated_header = replace_frontmatter_scalar(updated_header, "updated", updated)
    updated_text = "".join(updated_header) + body

    result.add("source", str(session_path))
    result.add("mode", "finalize session distillation metadata; body is not modified")
    result.add("status", args.status)
    result.add("distilledTo", ", ".join(distilled_refs) if distilled_refs else "[]")
    result.add("update-frontmatter", str(session_path))
    if args.write:
        session_path.write_text(updated_text, encoding="utf-8")
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

    distill = sub.add_parser("distill-session", help="distill a session note into a review candidate")
    distill.add_argument("--session", required=True, help="session note markdown path")
    distill.add_argument("--dest", default=".local/codex-context/distilled-session-candidates")
    distill.add_argument(
        "--kind",
        choices=["candidate", "decision-candidate", "working-context-update", "skill-candidate", "agents-candidate"],
        default="candidate",
    )
    distill.add_argument("--title")
    distill.add_argument("--source-repo", help="source repository name or label for destination metadata")
    distill.add_argument("--max-section-lines", type=int, default=12)
    distill.add_argument("--dry-run", action="store_true")
    distill.add_argument("--write", action="store_true")
    distill.add_argument("--log")
    distill.set_defaults(func=distill_session)

    finalize = sub.add_parser(
        "finalize-session-distillation",
        help="update session note distillation metadata after review",
    )
    finalize.add_argument("--session", required=True, help="session note markdown path")
    finalize.add_argument("--status", choices=["distilled", "partial", "no-action"], required=True)
    finalize.add_argument(
        "--distilled-to",
        action="append",
        help="accepted destination path or candidate path. Repeat to add multiple refs.",
    )
    finalize.add_argument("--dry-run", action="store_true")
    finalize.add_argument("--write", action="store_true")
    finalize.add_argument("--log")
    finalize.set_defaults(func=finalize_session_distillation)

    register = sub.add_parser("register-project", help="register this repository in ~/.codex-context")
    register.add_argument("--target", default="~/.codex-context")
    register.add_argument("--repo-root", default=".")
    register.add_argument("--title")
    register.add_argument("--description")
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
