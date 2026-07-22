#!/usr/bin/env python3
"""Materialize schema-v2 draft artifacts into a new shadow context tree."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence


sys.dont_write_bytecode = True
PLUGIN_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from tkn_codex_context.chat_logs import read_session, select_messages_for_roots  # noqa: E402
from tkn_codex_context.common import yaml_string  # noqa: E402
from tkn_codex_context.frontmatter import parse_simple_frontmatter  # noqa: E402


SHADOW_SCHEMA_VERSION = 1
SUPPORTED_PLAN_SCHEMA_VERSION = 1
SESSION_HEADINGS = (
    "## Objective",
    "### Goal",
    "### Done Criteria",
    "## Outcome",
    "## Current State",
    "## User Confirmations",
    "### Approved",
    "### Rejected",
    "### Preferences And Constraints",
    "## Evidence",
    "### Changed Files",
    "### Validation",
    "### Relevant Sources",
    "## Decision Candidates",
    "## Reusable Learnings",
    "### What Worked",
    "### Failed Approaches",
    "### Skill And Automation Signals",
    "## Open Loops",
    "## Handoff",
    "### Next Steps",
    "### Exact Next Step",
)
WORKING_CONTEXT_HEADINGS = (
    "## Purpose",
    "## Current Outcome",
    "## Current Truth",
    "## Active Workstreams",
    "## Blockers And Risks",
    "## Important Constraints",
    "## Effective Decisions",
    "## Dependencies",
    "## Key Files And Evidence",
    "## Resumption",
    "### Recommended Session",
    "### Exact Next Action",
    "## Maintenance",
    "### Stale Items",
    "### Review Due",
)
APPROVAL_PATTERN = re.compile(
    r"^\s*(?:ok(?:ay)?(?:です)?|yes\b|はい\b|お願いします\b|それで\b|その内容で\b|承認)",
    re.IGNORECASE,
)
REJECTION_PATTERN = re.compile(
    r"^\s*(?:no\b|いいえ\b|違います\b|やめて\b|不要\b)",
    re.IGNORECASE,
)
SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)"
        r"\s*[:=]\s*([^\s,;]+)"
    ),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\b(?:sk|gh[pousr])_[A-Za-z0-9_-]{16,}\b"),
)
LEADING_SKILL_INVOCATION_PATTERN = re.compile(
    r"^\s*(?:\[\$[^\]]+\]\([^)]+\)|\$[A-Za-z0-9:_-]+)\s*",
    re.IGNORECASE,
)


class ShadowError(RuntimeError):
    pass


def now_local() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def parse_timestamp(value: str) -> datetime:
    cleaned = value.strip()
    if not cleaned:
        return now_local()
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ShadowError(f"invalid session timestamp: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone()


def iso_value(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def session_id(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S%z")


def redact(text: str) -> str:
    result = text
    for pattern in SECRET_PATTERNS:
        if pattern.groups:
            result = pattern.sub(lambda match: f"{match.group(1)}=<redacted>", result)
        else:
            result = pattern.sub("<redacted>", result)
    return result


def has_unredacted_secret(text: str) -> bool:
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            if match.groups and match.lastindex and match.group(match.lastindex) == "<redacted>":
                continue
            return True
    return False


def compact_text(text: str, limit: int = 500) -> str:
    cleaned = redact(re.sub(r"\s+", " ", text).strip())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)].rstrip() + "…"


def strip_leading_skill_invocations(text: str) -> str:
    result = text
    while True:
        cleaned = LEADING_SKILL_INVOCATION_PATTERN.sub("", result, count=1)
        if cleaned == result:
            return result.strip()
        result = cleaned


def skill_invocation_label(text: str) -> str:
    match = re.match(
        r"^\s*(?:\[\$([^\]]+)\]\([^)]+\)|\$([A-Za-z0-9:_-]+))",
        text,
        re.IGNORECASE,
    )
    if not match:
        return ""
    label = str(match.group(1) or match.group(2) or "")
    return label.rsplit(":", 1)[-1]


def markdown_text(text: str, limit: int = 500) -> str:
    cleaned = compact_text(text, limit).replace("`", "'")
    return cleaned or "なし。"


def slugify(text: str, fallback: str) -> str:
    ascii_words = re.findall(r"[A-Za-z0-9]+", text.lower())
    slug = "-".join(ascii_words[:8]).strip("-")
    return (slug[:64].rstrip("-") or fallback).lower()


def source_relative_ref(row: dict[str, Any], source_id: str) -> str:
    qualified = str(row.get("sourceRef") or "")
    prefix = f"{source_id}/"
    if not qualified.startswith(prefix):
        raise ShadowError(f"invalid sourceRef for {source_id}: {qualified}")
    relative = qualified[len(prefix) :]
    if not relative or ".." in Path(relative).parts:
        raise ShadowError(f"sourceRef escapes sessions source: {qualified}")
    return relative


def source_path(
    row: dict[str, Any],
    source_roots: dict[str, Path],
) -> Path:
    source_id = str(row.get("sourceId") or "")
    root = source_roots.get(source_id)
    if root is None:
        raise ShadowError(f"unknown sourceId in assigned session: {source_id}")
    relative = source_relative_ref(row, source_id)
    path = (root / relative).resolve(strict=False)
    try:
        path.relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise ShadowError(f"sourceRef escapes sessions source: {row.get('sourceRef')}") from exc
    if not path.is_file():
        raise ShadowError(f"source log not found: {row.get('sourceRef')}")
    return path


def yaml_list(key: str, values: Sequence[str]) -> list[str]:
    if not values:
        return [f"{key}: []"]
    return [f"{key}:", *[f"  - {yaml_string(value)}" for value in values]]


def approval_messages(messages: Sequence[Any]) -> tuple[list[str], list[str]]:
    approved: list[str] = []
    rejected: list[str] = []
    for message in messages:
        if message.role != "user":
            continue
        text = compact_text(strip_leading_skill_invocations(message.text), 300)
        if APPROVAL_PATTERN.match(text) and text not in approved:
            approved.append(text)
        elif REJECTION_PATTERN.match(text) and text not in rejected:
            rejected.append(text)
    return approved[:3], rejected[:3]


def bullet_lines(values: Sequence[str], empty: str = "なし。") -> list[str]:
    return [*[f"- {value}" for value in values]] if values else [empty]


def session_note(
    project_id: str,
    row: dict[str, Any],
    roots: Sequence[str],
    source_roots: dict[str, Path],
    generated_at: datetime,
) -> tuple[str, str, list[dict[str, str]], dict[str, Any]]:
    path = source_path(row, source_roots)
    session = read_session(path)
    if not session:
        raise ShadowError(f"source log has no session metadata: {row.get('sourceRef')}")
    if session.id != str(row.get("threadId") or ""):
        raise ShadowError(f"source threadId changed after planning: {row.get('sourceRef')}")
    if session.timestamp != str(row.get("timestamp") or ""):
        raise ShadowError(f"source timestamp changed after planning: {row.get('sourceRef')}")
    messages = list(select_messages_for_roots(session, roots))
    if not messages:
        raise ShadowError(f"assigned session has no messages under accepted roots: {session.id}")
    users = [message for message in messages if message.role == "user"]
    assistants = [message for message in messages if message.role == "assistant"]
    if not users:
        raise ShadowError(f"assigned session has no user message: {session.id}")

    started_at = parse_timestamp(session.timestamp)
    user_texts = [strip_leading_skill_invocations(message.text) for message in users]
    meaningful_user_texts = [text for text in user_texts if text]
    fallback_label = next(
        (skill_invocation_label(message.text) for message in users if skill_invocation_label(message.text)),
        "codex-chat",
    )
    fallback_goal = f"Skill invocation: {fallback_label}"
    first_goal = markdown_text(
        meaningful_user_texts[0] if meaningful_user_texts else fallback_goal,
        600,
    )
    last_request = markdown_text(
        meaningful_user_texts[-1] if meaningful_user_texts else fallback_goal,
        500,
    )
    final_outcome = (
        markdown_text(assistants[-1].text, 900)
        if assistants
        else "Assistant outcome は記録されていない。"
    )
    title = compact_text(first_goal, 90) or f"Codex chat {session.id[:8]}"
    fallback_slug = f"codex-chat-{session.id[-8:] or 'session'}"
    slug = slugify(title, fallback_slug)
    filename = f"{session_id(started_at)}-{slug}-{session.id[-8:]}.md"
    approved, rejected = approval_messages(messages)

    candidates: list[dict[str, str]] = []
    for index, text in enumerate(approved, 1):
        candidates.append(
            {
                "candidateId": f"DC-{index:02d}",
                "threadId": session.id,
                "sourceRef": str(row["sourceRef"]),
                "status": "unclear",
                "scope": "project",
                "decision": text,
                "promotionTarget": "decision",
            }
        )

    frontmatter = [
        "---",
        "type: session",
        "schemaVersion: 2",
        f"title: {yaml_string(title)}",
        f"description: {yaml_string(compact_text(first_goal, 240))}",
        "generator: Codex",
        f"status: {'done' if assistants else 'waiting-for-user'}",
        "distillationStatus: pending",
        "distilledTo: []",
        f"date: {iso_value(started_at)}",
        f"updated: {iso_value(generated_at)}",
        f"sessionId: {session_id(started_at)}",
        "sourceType: codexChat",
        *yaml_list("sourceThreadIds", [session.id]),
        *yaml_list("sourceRefs", [str(row["sourceRef"])]),
        "---",
    ]
    candidate_lines: list[str] = []
    if candidates:
        for candidate in candidates:
            candidate_lines.extend(
                [
                    f"### {candidate['candidateId']}: 明示的な承認表現のreview",
                    "",
                    "- Status: unclear",
                    "- Scope: project",
                    f"- Decision: {candidate['decision']}",
                    "- Rationale: Source chat の明示的な承認表現。durable decision かは未確認。",
                    f"- Evidence: `{candidate['sourceRef']}`",
                    "- Promotion Target: decision",
                    "",
                ]
            )
    else:
        candidate_lines = ["なし。", ""]

    validation_lines = ["なし（current repository evidence との照合前）。"]
    if assistants and re.search(
        r"(?i)(test|tests|validation|validated|検証|テスト|passed|成功)",
        assistants[-1].text,
    ):
        validation_lines = [
            "Source chat の assistant が次を報告。current evidence との再検証が必要。",
            f"- {markdown_text(assistants[-1].text, 500)}",
        ]

    body = [
        *frontmatter,
        "",
        "# Session Note",
        "",
        "## Objective",
        "",
        "### Goal",
        "",
        first_goal,
        "",
        "### Done Criteria",
        "",
        last_request,
        "",
        "## Outcome",
        "",
        "Source chat の assistant が報告した結果。current evidence との照合前。",
        "",
        final_outcome,
        "",
        "## Current State",
        "",
        f"- Source chat messages: user {len(users)} / assistant {len(assistants)}。",
        "- Current repository files、Git state、runtime evidence との照合が必要。",
        "",
        "## User Confirmations",
        "",
        "### Approved",
        "",
        *bullet_lines(approved),
        "",
        "### Rejected",
        "",
        *bullet_lines(rejected),
        "",
        "### Preferences And Constraints",
        "",
        "なし（自動抽出でdurable preferenceを推測しない）。",
        "",
        "## Evidence",
        "",
        "### Changed Files",
        "",
        "なし（source chatから自動確定しない）。",
        "",
        "### Validation",
        "",
        *validation_lines,
        "",
        "### Relevant Sources",
        "",
        f"- `{row['sourceRef']}`",
        "",
        "## Decision Candidates",
        "",
        *candidate_lines,
        "## Reusable Learnings",
        "",
        "### What Worked",
        "",
        "なし（review前）。",
        "",
        "### Failed Approaches",
        "",
        "なし（review前）。",
        "",
        "### Skill And Automation Signals",
        "",
        "なし（review前）。",
        "",
        "## Open Loops",
        "",
        "- Current repository evidence と source chat outcome の照合。",
        "- Decision candidates の durable decision review。",
        "",
        "## Handoff",
        "",
        "### Next Steps",
        "",
        "- Current files と Git state を確認する。",
        "- Accepted decision だけを decision record へ昇格する。",
        "- 検証後に working context を current truth として更新する。",
        "",
        "### Exact Next Step",
        "",
        "このsession noteをcurrent repository evidenceと照合する。",
        "",
    ]
    metadata = {
        "threadId": session.id,
        "timestamp": session.timestamp,
        "sourceRef": str(row["sourceRef"]),
        "file": f"state/{project_id}/sessions/{filename}",
        "title": title,
        "outcome": compact_text(final_outcome, 500),
        "candidateCount": len(candidates),
    }
    return filename, "\n".join(body), candidates, metadata


def working_context(
    project: dict[str, Any],
    sessions: Sequence[dict[str, Any]],
    generated_at: datetime,
) -> str:
    project_id = str(project["projectId"])
    title = str(project.get("title") or project_id)
    latest = sessions[-1] if sessions else None
    latest_title = str((latest or {}).get("title") or "")
    latest_outcome = str((latest or {}).get("outcome") or "")
    latest_timestamp = (
        parse_timestamp(str(latest["timestamp"])) if latest else generated_at
    )
    status = str(project.get("status") or "active").casefold()
    if status not in {"active", "paused", "blocked", "completed", "archived"}:
        status = "active"
    blocked = status == "blocked"
    exact_next = (
        "最新のshadow session noteをcurrent project filesと照合する。"
        if status in {"active", "blocked"}
        else ""
    )
    review_after = (generated_at.date() + timedelta(days=7)).isoformat()
    recent = list(sessions[-5:])

    frontmatter = [
        "---",
        "type: workingContext",
        "schemaVersion: 2",
        f"title: {yaml_string(f'{title} Working Context Draft')}",
        f"description: {yaml_string('Codex chat履歴から再構築したreview前のshadow draft。')}",
        f"projectId: {yaml_string(project_id)}",
        "generator: Codex",
        "status: stale",
        f"projectStatus: {status}",
        "health: unknown",
        "priority: normal",
        f"currentFocus: {yaml_string(latest_title)}",
        f"blocked: {'true' if blocked else 'false'}",
        f"mainBlocker: {yaml_string('Current evidence review required.' if blocked else '')}",
        f"exactNextAction: {yaml_string(exact_next)}",
        f"lastMeaningfulActivity: {iso_value(latest_timestamp)}",
        f"reviewAfter: {review_after}",
        "dependencyProjectIds: []",
        "promotionStatus: pending",
        "promotedTo: []",
        f"date: {iso_value(generated_at)}",
        f"updated: {iso_value(generated_at)}",
        "---",
    ]
    recent_titles = [f"- {item['title']}" for item in reversed(recent)] or ["None."]
    evidence = [
        f"- `state:/{Path(item['file']).relative_to(Path('state') / project_id).as_posix()}`"
        for item in reversed(recent)
    ] or ["None."]
    recommended = (
        f"`state:/{Path(latest['file']).relative_to(Path('state') / project_id).as_posix()}`"
        if latest
        else "None."
    )
    return "\n".join(
        [
            *frontmatter,
            "",
            "# Working Context",
            "",
            "## Purpose",
            "",
            f"{title} の登録済みCodex Project context。purposeはcurrent project evidenceで要確認。",
            "",
            "## Current Outcome",
            "",
            latest_outcome or "None.",
            "",
            "## Current Truth",
            "",
            "- Chat履歴から再構築したshadow draftであり、current truthとして未承認。",
            f"- Reconstructed sessions: {len(sessions)}。",
            "",
            "## Active Workstreams",
            "",
            *recent_titles,
            "",
            "## Blockers And Risks",
            "",
            "- Source chatのassistant報告とcurrent repository stateが異なる可能性。",
            "- Durable decisionsは未確定。",
            "",
            "## Important Constraints",
            "",
            "- Live stateへ切り替える前にcurrent evidence reviewを行う。",
            "- Assistant proposalをAccepted decisionとして扱わない。",
            "",
            "## Effective Decisions",
            "",
            "None.",
            "",
            "## Dependencies",
            "",
            "None.",
            "",
            "## Key Files And Evidence",
            "",
            *evidence,
            "",
            "## Resumption",
            "",
            "### Recommended Session",
            "",
            recommended,
            "",
            "### Exact Next Action",
            "",
            exact_next or "None.",
            "",
            "## Maintenance",
            "",
            "### Stale Items",
            "",
            "- 全項目がshadow review待ち。",
            "",
            "### Review Due",
            "",
            review_after,
            "",
        ]
    )


def load_plan(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShadowError(f"cannot read plan: {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schemaVersion") != SUPPORTED_PLAN_SCHEMA_VERSION:
        raise ShadowError("unsupported rebuild plan schemaVersion")
    if value.get("mode") != "readOnlyPlan":
        raise ShadowError("plan mode must be readOnlyPlan")
    if not isinstance(value.get("projects"), list) or not isinstance(value.get("sources"), list):
        raise ShadowError("plan must contain projects and sources")
    return value


def require_new_output(output_root: Path, plan: dict[str, Any]) -> None:
    if output_root.exists():
        raise ShadowError(f"shadow output already exists: {output_root}")
    protected = [
        Path(str(plan.get("contextRoot") or "")),
        *[Path(str(source.get("sourceRoot") or "")) for source in plan["sources"]],
    ]
    resolved_output = output_root.resolve(strict=False)
    for root in protected:
        if not str(root):
            continue
        try:
            resolved_output.relative_to(root.resolve(strict=False))
        except ValueError:
            continue
        raise ShadowError("shadow output must be outside the live context and source trees")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_shadow_tree(
    output_root: Path,
    *,
    expected_projects: int,
    expected_sessions: int,
) -> dict[str, Any]:
    if not output_root.is_dir():
        raise ShadowError(f"shadow output not found: {output_root}")
    state_root = output_root / "state"
    project_roots = sorted(path for path in state_root.iterdir() if path.is_dir())
    if len(project_roots) != expected_projects:
        raise ShadowError(
            f"shadow project count mismatch: expected {expected_projects}, found {len(project_roots)}"
        )

    session_files: list[Path] = []
    working_files: list[Path] = []
    candidate_files: list[Path] = []
    for project_root in project_roots:
        sessions = sorted((project_root / "sessions").glob("*.md"))
        session_files.extend(sessions)
        working = project_root / "working-context.md"
        candidates = project_root / "decision-candidates.json"
        if not working.is_file():
            raise ShadowError(f"working context is missing: {working}")
        if not candidates.is_file():
            raise ShadowError(f"decision candidates are missing: {candidates}")
        working_files.append(working)
        candidate_files.append(candidates)

    if len(session_files) != expected_sessions:
        raise ShadowError(
            f"shadow session count mismatch: expected {expected_sessions}, found {len(session_files)}"
        )

    for path in session_files:
        text = path.read_text(encoding="utf-8-sig")
        metadata = parse_simple_frontmatter(text)
        if metadata.get("type") != "session" or metadata.get("schemaVersion") != "2":
            raise ShadowError(f"invalid session schema: {path}")
        missing = [heading for heading in SESSION_HEADINGS if heading not in text]
        if missing:
            raise ShadowError(f"session headings are missing in {path}: {missing}")
        if has_unredacted_secret(text):
            raise ShadowError(f"possible unredacted secret in session note: {path}")

    for path in working_files:
        text = path.read_text(encoding="utf-8-sig")
        metadata = parse_simple_frontmatter(text)
        if metadata.get("type") != "workingContext" or metadata.get("schemaVersion") != "2":
            raise ShadowError(f"invalid working context schema: {path}")
        missing = [heading for heading in WORKING_CONTEXT_HEADINGS if heading not in text]
        if missing:
            raise ShadowError(f"working context headings are missing in {path}: {missing}")
        if has_unredacted_secret(text):
            raise ShadowError(f"possible unredacted secret in working context: {path}")

    decision_candidates = 0
    for path in candidate_files:
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise ShadowError(f"invalid decision candidate JSON: {path}: {exc}") from exc
        if value.get("schemaVersion") != 1 or value.get("reviewRequired") is not True:
            raise ShadowError(f"invalid decision candidate contract: {path}")
        candidates = value.get("candidates")
        if not isinstance(candidates, list):
            raise ShadowError(f"decision candidates must be a list: {path}")
        decision_candidates += len(candidates)

    decision_records = list(state_root.glob("*/decisions/DR-*.md"))
    if decision_records:
        raise ShadowError("shadow draft must not auto-create decision records")

    return {
        "passed": True,
        "projects": len(project_roots),
        "sessionNotes": len(session_files),
        "workingContexts": len(working_files),
        "decisionCandidates": decision_candidates,
        "decisionRecords": 0,
        "unredactedSecretMatches": 0,
    }


def materialize(plan: dict[str, Any], output_root: Path) -> dict[str, Any]:
    require_new_output(output_root, plan)
    generated_at = now_local()
    source_roots = {
        str(source["sourceId"]): Path(str(source["sourceRoot"]))
        for source in plan["sources"]
    }
    manifest_projects: list[dict[str, Any]] = []
    total_sessions = 0
    total_candidates = 0
    assigned_refs: set[str] = set()

    for project in plan["projects"]:
        project_id = str(project.get("projectId") or "")
        if not project_id:
            raise ShadowError("plan project is missing projectId")
        project_root = output_root / "state" / project_id
        session_root = project_root / "sessions"
        candidates: list[dict[str, str]] = []
        session_metadata: list[dict[str, Any]] = []
        used_filenames: set[str] = set()

        rows = [
            row
            for row in project.get("assignedSessions", [])
            if isinstance(row, dict)
        ]
        rows.sort(key=lambda row: (str(row.get("timestamp") or ""), str(row.get("sourceRef") or "")))
        for row in rows:
            assigned_ref = str(row.get("sourceRef") or "")
            if assigned_ref in assigned_refs:
                raise ShadowError(f"sourceRef is assigned more than once: {assigned_ref}")
            assigned_refs.add(assigned_ref)
            filename, text, row_candidates, metadata = session_note(
                project_id,
                row,
                [str(root) for root in project.get("acceptedRoots", [])],
                source_roots,
                generated_at,
            )
            if filename in used_filenames:
                raise ShadowError(f"duplicate generated session filename: {filename}")
            used_filenames.add(filename)
            atomic_write_text(session_root / filename, text)
            candidates.extend(row_candidates)
            session_metadata.append(metadata)

        atomic_write_text(
            project_root / "working-context.md",
            working_context(project, session_metadata, generated_at),
        )
        atomic_write_text(
            project_root / "decision-candidates.json",
            json.dumps(
                {
                    "schemaVersion": 1,
                    "projectId": project_id,
                    "generatedAt": iso_value(generated_at),
                    "reviewRequired": True,
                    "candidates": candidates,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        total_sessions += len(session_metadata)
        total_candidates += len(candidates)
        manifest_projects.append(
            {
                "projectId": project_id,
                "sessionNotes": len(session_metadata),
                "decisionCandidates": len(candidates),
                "decisionRecords": 0,
                "workingContext": f"state/{project_id}/working-context.md",
            }
        )

    validation = validate_shadow_tree(
        output_root,
        expected_projects=len(manifest_projects),
        expected_sessions=total_sessions,
    )
    manifest = {
        "schemaVersion": SHADOW_SCHEMA_VERSION,
        "generatedAt": iso_value(generated_at),
        "mode": "shadowDraft",
        "sourcePlanSummary": plan.get("summary", {}),
        "projects": manifest_projects,
        "summary": {
            "projects": len(manifest_projects),
            "sessionNotes": total_sessions,
            "decisionCandidates": total_candidates,
            "decisionRecords": 0,
            "workingContexts": len(manifest_projects),
            "unresolvedSessions": len(plan.get("unresolvedSessions", [])),
        },
        "reviewGate": {
            "liveStateModified": False,
            "decisionReviewRequired": True,
            "currentEvidenceReviewRequired": True,
        },
        "validation": validation,
    }
    atomic_write_text(
        output_root / "shadow-manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate an existing shadow tree against the supplied plan without writing.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plan = load_plan(args.plan)
        if args.validate_only:
            expected_sessions = sum(
                len(project.get("assignedSessions", []))
                for project in plan["projects"]
                if isinstance(project, dict)
            )
            validation = validate_shadow_tree(
                args.output_root.expanduser(),
                expected_projects=len(plan["projects"]),
                expected_sessions=expected_sessions,
            )
            print(
                json.dumps(
                    {"outputRoot": str(args.output_root), "validation": validation},
                    ensure_ascii=False,
                )
            )
            return 0
        manifest = materialize(plan, args.output_root.expanduser())
    except ShadowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {"outputRoot": str(args.output_root), "summary": manifest["summary"]},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
