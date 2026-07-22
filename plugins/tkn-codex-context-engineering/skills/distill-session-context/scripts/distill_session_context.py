#!/usr/bin/env python3
"""Distill one session note into a review candidate."""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from pathlib import Path


sys.dont_write_bytecode = True
PLUGIN_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from tkn_codex_context.common import (  # noqa: E402
    Result,
    expand,
    frontmatter,
    now_compact,
    now_iso,
    print_result,
    slugify,
    source_ref,
    source_repo,
    yaml_string,
)
from tkn_codex_context.file_io import require_explicit_output_dest, write_text  # noqa: E402
from tkn_codex_context.frontmatter import (  # noqa: E402
    ensure_artifact_schema_version,
    frontmatter_list_value,
    parse_simple_frontmatter,
    require_supported_artifact_schema,
    replace_frontmatter_list,
    replace_frontmatter_scalar,
    split_frontmatter_lines,
    strip_frontmatter,
    unique_ordered,
    validate_distilled_to_ref,
)
from tkn_codex_context.safety import has_secret_like_content  # noqa: E402


DISTILL_SECTION_GROUPS = {
    "1": {
        "digest": [
            "important decisions",
            "what worked",
            "failed approaches",
            "constraints",
        ],
        "continuation": [
            "open issues",
            "next steps",
            "exact next step",
        ],
        "evidence": [
            "user intent / interaction summary",
            "working context",
            "changed files",
            "validation",
        ],
    },
    "2": {
        "digest": [
            "summary",
            "key developments",
        ],
        "continuation": [
            "last known state",
            "source notes",
        ],
        "evidence": [
            "evidence",
        ],
    },
}


def normalize_heading(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())

def markdown_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    active: list[tuple[int, str]] = []
    for line in strip_frontmatter(text).splitlines():
        match = re.match(r"^(#{2,6})\s+(.+?)\s*$", line)
        if match:
            level = len(match.group(1))
            while active and active[-1][0] >= level:
                active.pop()
            for _, parent in active:
                sections[parent].append(line.rstrip())
            current = normalize_heading(match.group(2))
            sections.setdefault(current, [])
            active.append((level, current))
            continue
        for _, current in active:
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
    schema_version: str,
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
        ("sourceSchemaVersion", int(schema_version)),
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
- Source schema version: {schema_version}
- Review required before promotion: yes

## Usage Guidance

- Treat this file as a review candidate, not accepted repository or global context.
- Revalidate the extracted points against current user instructions, repository instructions, current files, and git state.
- Promote only the reusable parts to working context, decisions, global context, AGENTS.md, or a Skill.
- Do not promote raw chronological detail unless it prevents a repeated failure.

{render_distill_section_group("Factual Session Digest", DISTILL_SECTION_GROUPS[schema_version]["digest"], sections, args.max_section_lines)}

{render_distill_section_group("Continuation Evidence", DISTILL_SECTION_GROUPS[schema_version]["continuation"], sections, args.max_section_lines)}

{render_distill_section_group("Supporting Evidence", DISTILL_SECTION_GROUPS[schema_version]["evidence"], sections, args.max_section_lines)}

## Exclusions

- Full chat transcript was not copied.
- Full session note was not copied.
- The source session note was not modified.
"""

def distill_session(args: argparse.Namespace) -> Result:
    session_path = expand(args.session)
    result = Result()
    dest = expand(args.dest) if args.dest else require_explicit_output_dest("--dest", "distill-session")

    if not session_path.exists():
        raise SystemExit(f"Session note does not exist: {session_path}")
    text = session_path.read_text(encoding="utf-8", errors="replace")
    hits = has_secret_like_content(text)
    if hits:
        raise SystemExit(f"Sensitive-looking content detected in {session_path}; refusing to distill.")

    metadata = parse_simple_frontmatter(text)
    schema_version = require_supported_artifact_schema(metadata, "session note")
    if metadata.get("type") and metadata.get("type") != "session":
        result.warn(f"source type is {metadata.get('type')}, expected session")
    sections = markdown_sections(text)
    title = args.title or metadata.get("title") or session_path.stem
    out_name = f"{now_compact()}-{slugify(title)}-distillation.md"
    out_path = dest / out_name
    content = render_session_distillation(
        session_path=session_path,
        metadata=metadata,
        schema_version=schema_version,
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
    require_supported_artifact_schema(metadata, "session note")
    if metadata.get("type") and metadata.get("type") != "session":
        result.warn(f"source type is {metadata.get('type')}, expected session")

    existing_refs = [validate_distilled_to_ref(value) for value in frontmatter_list_value(header_lines, "distilledTo")]
    new_refs = [validate_distilled_to_ref(value) for value in args.distilled_to or []]
    if args.status == "no-action":
        distilled_refs: list[str] = []
    else:
        distilled_refs = unique_ordered([*existing_refs, *new_refs])

    updated = now_iso()
    updated_header = ensure_artifact_schema_version(header_lines, "session note")
    updated_header = replace_frontmatter_scalar(updated_header, "distillationStatus", args.status)
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

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--dest")
    parser.add_argument(
        "--kind",
        choices=["candidate", "decision-candidate", "working-context-update", "skill-candidate", "agents-candidate"],
        default="candidate",
    )
    parser.add_argument("--title")
    parser.add_argument("--source-repo")
    parser.add_argument("--max-section-lines", type=int, default=40)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--log")
    return parser


def build_finalize_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finalize session distillation metadata after review.")
    parser.add_argument("--session", required=True)
    parser.add_argument("--status", choices=["distilled", "partial", "no-action"], required=True)
    parser.add_argument("--distilled-to", action="append")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--log")
    return parser


def _run(parser: argparse.ArgumentParser, argv: list[str] | None, operation) -> int:
    args = parser.parse_args(argv)
    if args.write and args.dry_run:
        parser.error("Use either --dry-run or --write, not both.")
    if not args.write:
        args.dry_run = True
    result = operation(args)
    print_result(result, args.write, args.log)
    return 0


def main(argv: list[str] | None = None) -> int:
    return _run(build_parser(), argv, distill_session)


def finalize_main(argv: list[str] | None = None) -> int:
    return _run(build_finalize_parser(), argv, finalize_session_distillation)


if __name__ == "__main__":
    raise SystemExit(main())
