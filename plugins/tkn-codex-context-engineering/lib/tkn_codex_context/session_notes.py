"""Background Codex chat to session-note pipeline."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol, Sequence

from .chat_logs import (
    ChatEvent,
    default_sessions_root,
    fingerprint_events,
    has_clean_user_message,
    is_approval_review,
    is_known_internal_session,
    normalize_path_text,
    path_is_within,
    read_session,
    read_session_events,
    source_ref,
)
from .common import frontmatter, slugify
from .frontmatter import (
    frontmatter_list_value,
    parse_simple_frontmatter,
    split_frontmatter_lines,
)
from .safety import redact_secret_like_content


CONFIG_SCHEMA_VERSION = 1
STATE_SCHEMA_VERSION = 2
LEGACY_STATE_SCHEMA_VERSION = 1
SESSION_SCHEMA_VERSION = 2
CONFIG_FILENAME = "session-note-pipeline.json"
STATE_FILENAME = "chat-refresh-state.json"
DEFAULT_SOURCE_ID = "windows" if os.name == "nt" else "local"
DEFAULT_MODEL = "gpt-5.6-sol"
DEFAULT_REASONING_EFFORT = "high"
DEFAULT_IDLE_MINUTES = 30
DEFAULT_RUNTIME_MINUTES = 230
DEFAULT_MODEL_TIMEOUT_SECONDS = 1800
DEFAULT_CHUNK_CHARACTERS = 120_000
MAX_EVENT_TEXT_CHARACTERS = 8_000
ALLOWED_STATUS = {"in-progress", "blocked", "waiting-for-user", "done"}
ALLOWED_LABELS = {
    "Request",
    "Clarification",
    "Correction",
    "Action",
    "Result",
    "Decision",
    "Validation",
}


class PipelineError(RuntimeError):
    pass


class PartialPipelineError(PipelineError):
    pass


@dataclass(frozen=True)
class PipelineConfig:
    installed_at: str
    sessions_root: Path
    source_id: str
    codex_bin: str
    model: str = DEFAULT_MODEL
    reasoning_effort: str = DEFAULT_REASONING_EFFORT
    idle_minutes: int = DEFAULT_IDLE_MINUTES
    runtime_minutes: int = DEFAULT_RUNTIME_MINUTES
    model_timeout_seconds: int = DEFAULT_MODEL_TIMEOUT_SECONDS


@dataclass(frozen=True)
class Project:
    project_id: str
    title: str
    current_root: Path
    context_path: Path

    @property
    def sessions_path(self) -> Path:
        return self.context_path / "sessions"

    @property
    def state_path(self) -> Path:
        return self.context_path / STATE_FILENAME


@dataclass(frozen=True)
class Candidate:
    project: Project
    thread_id: str
    started_at: str
    source_path: Path
    source_ref: str
    source_relative_ref: str
    fingerprint: str
    events: tuple[ChatEvent, ...]
    source_mtime_ns: int
    source_size: int


@dataclass(frozen=True)
class PreparedEvent:
    id: str
    kind: str
    actor: str
    name: str
    text: str
    timestamp: str
    turn_id: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "kind": self.kind,
            "actor": self.actor,
            "name": self.name,
            "text": self.text,
            "timestamp": self.timestamp,
            "turnId": self.turn_id,
        }


class Summarizer(Protocol):
    def generate(self, candidate: Candidate) -> dict[str, Any]: ...


def now_local() -> datetime:
    return datetime.now().astimezone()


def now_iso() -> str:
    return now_local().isoformat(timespec="seconds")


def default_store_root() -> Path:
    return Path.home() / ".tkn" / "codex-context"


def default_config_path() -> Path:
    return default_store_root() / "config" / CONFIG_FILENAME


def default_registry_path() -> Path:
    return default_store_root() / "state" / "index.jsonl"


def default_cache_root() -> Path:
    override = os.environ.get("XDG_CACHE_HOME")
    base = Path(override).expanduser() if override else Path.home() / ".cache"
    return base / "net.tuckn" / "codex-context" / "session-note-pipeline"


def parse_datetime(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise PipelineError(f"invalid ISO 8601 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def resolve_codex_bin(value: str = "") -> str:
    candidate = value.strip() or shutil.which("codex") or ""
    if not candidate:
        raise PipelineError("standalone Codex CLI was not found")
    resolved = str(Path(candidate).expanduser().absolute())
    if "\\windowsapps\\" in resolved.casefold():
        raise PipelineError("the Codex App WindowsApps executable cannot be used for automation")
    if not Path(resolved).is_file():
        raise PipelineError(f"Codex CLI executable not found: {resolved}")
    return resolved


def make_config(
    *,
    existing: PipelineConfig | None = None,
    sessions_root: Path | None = None,
    codex_bin: str = "",
    installed_at: str | None = None,
) -> PipelineConfig:
    return PipelineConfig(
        installed_at=installed_at or (existing.installed_at if existing else now_iso()),
        sessions_root=(sessions_root or (existing.sessions_root if existing else default_sessions_root())).expanduser().absolute(),
        source_id=existing.source_id if existing else DEFAULT_SOURCE_ID,
        codex_bin=resolve_codex_bin(codex_bin or (existing.codex_bin if existing else "")),
        model=DEFAULT_MODEL,
        reasoning_effort=DEFAULT_REASONING_EFFORT,
        idle_minutes=existing.idle_minutes if existing else DEFAULT_IDLE_MINUTES,
        runtime_minutes=existing.runtime_minutes if existing else DEFAULT_RUNTIME_MINUTES,
        model_timeout_seconds=(
            existing.model_timeout_seconds if existing else DEFAULT_MODEL_TIMEOUT_SECONDS
        ),
    )


def config_json(config: PipelineConfig) -> dict[str, Any]:
    return {
        "schemaVersion": CONFIG_SCHEMA_VERSION,
        "installedAt": config.installed_at,
        "sessionsRoot": str(config.sessions_root),
        "sourceId": config.source_id,
        "codexBin": config.codex_bin,
        "model": config.model,
        "reasoningEffort": config.reasoning_effort,
        "idleMinutes": config.idle_minutes,
        "runtimeMinutes": config.runtime_minutes,
        "modelTimeoutSeconds": config.model_timeout_seconds,
    }


def load_config(path: Path | None = None) -> PipelineConfig:
    resolved = path or default_config_path()
    if not resolved.is_file():
        raise PipelineError(f"pipeline config not found; run configure first: {resolved}")
    try:
        value = json.loads(resolved.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"cannot read pipeline config: {resolved}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schemaVersion") != CONFIG_SCHEMA_VERSION:
        raise PipelineError("unsupported session-note pipeline config schemaVersion")
    if value.get("model") != DEFAULT_MODEL or value.get("reasoningEffort") != DEFAULT_REASONING_EFFORT:
        raise PipelineError(
            f"pipeline model must remain fixed at {DEFAULT_MODEL} with {DEFAULT_REASONING_EFFORT} reasoning"
        )
    config = PipelineConfig(
        installed_at=str(value.get("installedAt") or ""),
        sessions_root=Path(str(value.get("sessionsRoot") or "")).expanduser().absolute(),
        source_id=str(value.get("sourceId") or DEFAULT_SOURCE_ID),
        codex_bin=str(value.get("codexBin") or ""),
        model=str(value["model"]),
        reasoning_effort=str(value["reasoningEffort"]),
        idle_minutes=int(value.get("idleMinutes", DEFAULT_IDLE_MINUTES)),
        runtime_minutes=int(value.get("runtimeMinutes", DEFAULT_RUNTIME_MINUTES)),
        model_timeout_seconds=int(
            value.get("modelTimeoutSeconds", DEFAULT_MODEL_TIMEOUT_SECONDS)
        ),
    )
    parse_datetime(config.installed_at)
    if not config.sessions_root.is_dir():
        raise PipelineError(f"sessions root not found: {config.sessions_root}")
    if config.idle_minutes < 0 or config.runtime_minutes <= 0 or config.model_timeout_seconds <= 0:
        raise PipelineError("pipeline timing values must be positive")
    return config


def write_config(path: Path, config: PipelineConfig) -> None:
    atomic_write_json(path, config_json(config))


def load_active_projects(registry_path: Path | None = None) -> list[Project]:
    path = registry_path or default_registry_path()
    if not path.is_file():
        raise PipelineError(f"project registry not found: {path}")
    projects: list[Project] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PipelineError(f"invalid registry JSON at line {line_number}: {exc}") from exc
            if not isinstance(value, dict) or value.get("status") != "active":
                continue
            project_id = str(value.get("projectId") or "")
            current_root = str(value.get("currentRoot") or "")
            context_path = str(value.get("projectContextPath") or "")
            if not project_id or not current_root or not context_path:
                raise PipelineError(f"active registry record at line {line_number} is incomplete")
            if project_id in seen:
                raise PipelineError(f"duplicate active projectId in registry: {project_id}")
            seen.add(project_id)
            projects.append(
                Project(
                    project_id=project_id,
                    title=str(value.get("title") or project_id),
                    current_root=Path(current_root).expanduser().absolute(),
                    context_path=Path(context_path).expanduser().absolute(),
                )
            )
    return sorted(projects, key=lambda item: item.project_id)


def empty_refresh_state(project_id: str) -> dict[str, Any]:
    return {
        "schemaVersion": STATE_SCHEMA_VERSION,
        "projectId": project_id,
        "approvedHistoricalRoots": [],
        "rejectedHistoricalRoots": [],
        "lastRefreshAt": None,
        "sources": {},
    }


def load_refresh_state(project: Project, config: PipelineConfig) -> dict[str, Any]:
    path = project.state_path
    if not path.exists():
        value = empty_refresh_state(project.project_id)
    else:
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError(f"cannot read refresh state: {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise PipelineError(f"refresh state must be a JSON object: {path}")
        if value.get("schemaVersion") == LEGACY_STATE_SCHEMA_VERSION:
            legacy_root = str(value.get("sourceRoot") or config.sessions_root)
            value = {
                "schemaVersion": STATE_SCHEMA_VERSION,
                "projectId": value.get("projectId"),
                "approvedHistoricalRoots": value.get("approvedHistoricalRoots", []),
                "rejectedHistoricalRoots": value.get("rejectedHistoricalRoots", []),
                "lastRefreshAt": value.get("lastRefreshAt"),
                "sources": {
                    config.source_id: {
                        "sourceRoot": legacy_root,
                        "lastRefreshAt": value.get("lastRefreshAt"),
                        "threads": value.get("threads", {}),
                    }
                },
            }
    if value.get("schemaVersion") != STATE_SCHEMA_VERSION:
        raise PipelineError(f"unsupported refresh state schemaVersion: {path}")
    if value.get("projectId") != project.project_id:
        raise PipelineError(f"refresh state projectId mismatch: {path}")
    sources = value.get("sources")
    if not isinstance(sources, dict):
        raise PipelineError(f"refresh state sources must be an object: {path}")
    source = sources.setdefault(
        config.source_id,
        {"sourceRoot": str(config.sessions_root), "lastRefreshAt": None, "threads": {}},
    )
    if not isinstance(source, dict) or not isinstance(source.get("threads"), dict):
        raise PipelineError(f"refresh state source is invalid: {path}")
    existing_root = str(source.get("sourceRoot") or "")
    if existing_root and normalize_path_text(existing_root) != normalize_path_text(
        str(config.sessions_root)
    ):
        raise PipelineError(
            f"source id {config.source_id} is already bound to another sessions root"
        )
    source["sourceRoot"] = str(config.sessions_root)
    return value


def update_refresh_state(
    project: Project,
    config: PipelineConfig,
    candidate: Candidate,
    note_path: Path,
) -> None:
    state = load_refresh_state(project, config)
    source = state["sources"][config.source_id]
    relative_note = note_path.relative_to(project.context_path).as_posix()
    processed_at = now_iso()
    source["threads"][candidate.thread_id] = {
        "fingerprint": candidate.fingerprint,
        "sourceRefs": [candidate.source_ref],
        "sessionNotes": [relative_note],
        "decisionIds": [],
        "processedAt": processed_at,
    }
    source["lastRefreshAt"] = processed_at
    state["lastRefreshAt"] = processed_at
    atomic_write_json(project.state_path, state)


def project_roots(project: Project) -> tuple[str, ...]:
    values = [str(project.current_root)]
    try:
        values.append(str(project.current_root.resolve(strict=False)))
    except OSError:
        pass
    return tuple(dict.fromkeys(values))


def event_matches_project(event: ChatEvent, project: Project) -> bool:
    return any(path_is_within(event.cwd, root) for root in project_roots(project))


def candidate_for_project(
    path: Path,
    project: Project,
    config: PipelineConfig,
    *,
    backfill: bool,
) -> Candidate | None:
    stat = path.stat()
    if not backfill and datetime.fromtimestamp(stat.st_mtime, tz=now_local().tzinfo) < parse_datetime(
        config.installed_at
    ):
        return None
    idle_cutoff = now_local() - timedelta(minutes=config.idle_minutes)
    if datetime.fromtimestamp(stat.st_mtime, tz=idle_cutoff.tzinfo) > idle_cutoff:
        return None
    session = read_session(path)
    if not session or is_approval_review(session) or is_known_internal_session(session):
        return None
    if not has_clean_user_message(session):
        return None
    events = tuple(event for event in read_session_events(path) if event_matches_project(event, project))
    if not any(event.kind == "user_message" for event in events):
        return None
    relative_ref = source_ref(path, config.sessions_root)
    qualified_ref = f"{config.source_id}/{relative_ref}"
    return Candidate(
        project=project,
        thread_id=session.id,
        started_at=session.timestamp,
        source_path=path,
        source_ref=qualified_ref,
        source_relative_ref=relative_ref,
        fingerprint=fingerprint_events(session.id, events, qualified_ref),
        events=events,
        source_mtime_ns=stat.st_mtime_ns,
        source_size=stat.st_size,
    )


def round_robin(groups: dict[str, list[Candidate]]) -> list[Candidate]:
    ordered: list[Candidate] = []
    keys = sorted(groups)
    indexes = {key: 0 for key in keys}
    while True:
        added = False
        for key in keys:
            index = indexes[key]
            if index < len(groups[key]):
                ordered.append(groups[key][index])
                indexes[key] += 1
                added = True
        if not added:
            return ordered


def scan_candidates(
    config: PipelineConfig,
    projects: Sequence[Project],
    *,
    backfill: bool = False,
    project_ids: Sequence[str] = (),
    thread_ids: Sequence[str] = (),
) -> tuple[list[Candidate], dict[str, int]]:
    selected_projects = [
        project for project in projects if not project_ids or project.project_id in set(project_ids)
    ]
    missing = set(project_ids) - {project.project_id for project in selected_projects}
    if missing:
        raise PipelineError(f"unknown or inactive projectId: {', '.join(sorted(missing))}")
    groups: dict[str, list[Candidate]] = {project.project_id: [] for project in selected_projects}
    counts = {"files": 0, "eligible": 0, "unchanged": 0, "ignoredFiles": 0}
    states = {project.project_id: load_refresh_state(project, config) for project in selected_projects}
    thread_filter = set(thread_ids)
    for path in sorted(config.sessions_root.rglob("*.jsonl")):
        counts["files"] += 1
        stat = path.stat()
        if not backfill and datetime.fromtimestamp(
            stat.st_mtime, tz=now_local().tzinfo
        ) < parse_datetime(config.installed_at):
            counts["ignoredFiles"] += 1
            continue
        idle_cutoff = now_local() - timedelta(minutes=config.idle_minutes)
        if datetime.fromtimestamp(stat.st_mtime, tz=idle_cutoff.tzinfo) > idle_cutoff:
            counts["ignoredFiles"] += 1
            continue
        session = read_session(path)
        if (
            not session
            or is_approval_review(session)
            or is_known_internal_session(session)
            or not has_clean_user_message(session)
        ):
            counts["ignoredFiles"] += 1
            continue
        all_events = read_session_events(path)
        matched_file = False
        for project in selected_projects:
            events = tuple(event for event in all_events if event_matches_project(event, project))
            if not any(event.kind == "user_message" for event in events):
                continue
            relative_ref = source_ref(path, config.sessions_root)
            qualified_ref = f"{config.source_id}/{relative_ref}"
            candidate = Candidate(
                project=project,
                thread_id=session.id,
                started_at=session.timestamp,
                source_path=path,
                source_ref=qualified_ref,
                source_relative_ref=relative_ref,
                fingerprint=fingerprint_events(session.id, events, qualified_ref),
                events=events,
                source_mtime_ns=stat.st_mtime_ns,
                source_size=stat.st_size,
            )
            if thread_filter and candidate.thread_id not in thread_filter:
                continue
            matched_file = True
            source = states[project.project_id]["sources"][config.source_id]
            prior = source["threads"].get(candidate.thread_id, {})
            if prior.get("fingerprint") == candidate.fingerprint:
                counts["unchanged"] += 1
                continue
            groups[project.project_id].append(candidate)
            counts["eligible"] += 1
        if not matched_file:
            counts["ignoredFiles"] += 1
    for candidates in groups.values():
        candidates.sort(key=lambda item: (item.started_at, item.thread_id))
    return round_robin(groups), counts


def truncate_text(text: str, limit: int = MAX_EVENT_TEXT_CHARACTERS) -> str:
    if len(text) <= limit:
        return text
    marker = f"\n[TRUNCATED {len(text) - limit} CHARACTERS]\n"
    remaining = limit - len(marker)
    head = remaining // 2
    tail = remaining - head
    return text[:head] + marker + text[-tail:]


def prepare_events(events: Sequence[ChatEvent]) -> list[PreparedEvent]:
    return [
        PreparedEvent(
            id=event.id,
            kind=event.kind,
            actor=event.actor,
            name=event.name,
            text=truncate_text(redact_secret_like_content(event.text)),
            timestamp=event.timestamp,
            turn_id=event.turn_id,
        )
        for event in events
    ]


def chunk_events(
    events: Sequence[PreparedEvent],
    target_characters: int = DEFAULT_CHUNK_CHARACTERS,
) -> list[list[PreparedEvent]]:
    chunks: list[list[PreparedEvent]] = []
    current: list[PreparedEvent] = []
    current_size = 0
    for event in events:
        rendered_size = len(json.dumps(event.as_dict(), ensure_ascii=False)) + 1
        if current and current_size + rendered_size > target_characters:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(event)
        current_size += rendered_size
    if current:
        chunks.append(current)
    return chunks


NOTE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "summary": {"type": "string"},
        "summaryEventIds": {"type": "array", "items": {"type": "string"}},
        "keyDevelopments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string", "enum": sorted(ALLOWED_LABELS)},
                    "text": {"type": "string"},
                    "eventIds": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["label", "text", "eventIds"],
            },
        },
        "lastKnownState": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "workState": {"type": "string", "enum": sorted(ALLOWED_STATUS)},
                "detail": {"type": "string"},
                "latestUserDirection": {"type": "string"},
                "unresolved": {"type": "array", "items": {"type": "string"}},
                "continuationPoint": {"type": "string"},
                "eventIds": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "workState",
                "detail",
                "latestUserDirection",
                "unresolved",
                "continuationPoint",
                "eventIds",
            ],
        },
        "sourceLimitations": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title",
        "description",
        "summary",
        "summaryEventIds",
        "keyDevelopments",
        "lastKnownState",
        "sourceLimitations",
    ],
}


def validate_note_data(value: Any, allowed_event_ids: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PipelineError("Codex output must be a JSON object")
    required = set(NOTE_SCHEMA["required"])
    if not required.issubset(value):
        raise PipelineError(f"Codex output is missing fields: {', '.join(sorted(required - set(value)))}")
    if not all(isinstance(value.get(key), str) for key in ("title", "description", "summary")):
        raise PipelineError("Codex output title, description, and summary must be strings")
    developments = value.get("keyDevelopments")
    last_state = value.get("lastKnownState")
    if not isinstance(developments, list) or not isinstance(last_state, dict):
        raise PipelineError("Codex output has invalid keyDevelopments or lastKnownState")
    if last_state.get("workState") not in ALLOWED_STATUS:
        raise PipelineError("Codex output has invalid workState")
    cited: list[str] = list(value.get("summaryEventIds") or []) + list(last_state.get("eventIds") or [])
    for item in developments:
        if not isinstance(item, dict) or item.get("label") not in ALLOWED_LABELS:
            raise PipelineError("Codex output has an invalid key development")
        cited.extend(item.get("eventIds") or [])
    invalid = {str(item) for item in cited if str(item) not in allowed_event_ids}
    if invalid:
        raise PipelineError(f"Codex output cited unknown event ids: {', '.join(sorted(invalid))}")
    return value


class CodexSummarizer:
    def __init__(
        self,
        config: PipelineConfig,
        *,
        chunk_characters: int = DEFAULT_CHUNK_CHARACTERS,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.chunk_characters = chunk_characters
        self.sleeper = sleeper

    def _invoke(self, prompt: str) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="tkn-session-note-") as directory:
            temp = Path(directory)
            schema_path = temp / "schema.json"
            output_path = temp / "output.json"
            schema_path.write_text(
                json.dumps(NOTE_SCHEMA, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            command = [
                self.config.codex_bin,
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--model",
                self.config.model,
                "-c",
                f'model_reasoning_effort="{self.config.reasoning_effort}"',
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-",
            ]
            last_error = ""
            for attempt in range(3):
                try:
                    completed = subprocess.run(
                        command,
                        input=prompt,
                        cwd=temp,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=self.config.model_timeout_seconds,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    last_error = f"Codex timed out after {exc.timeout} seconds"
                else:
                    if completed.returncode == 0 and output_path.is_file():
                        try:
                            value = json.loads(output_path.read_text(encoding="utf-8-sig"))
                        except json.JSONDecodeError as exc:
                            last_error = f"Codex returned invalid JSON: {exc}"
                        else:
                            if isinstance(value, dict):
                                return value
                            last_error = "Codex output was not a JSON object"
                    else:
                        stderr = completed.stderr.strip()
                        last_error = f"Codex exited with {completed.returncode}: {stderr[-2000:]}"
                if attempt < 2:
                    self.sleeper(2**attempt)
            raise PipelineError(last_error or "Codex generation failed")

    def generate(self, candidate: Candidate) -> dict[str, Any]:
        prepared = prepare_events(candidate.events)
        allowed_ids = {event.id for event in prepared}
        chunks = chunk_events(prepared, self.chunk_characters)
        partials: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks, 1):
            prompt = json.dumps(
                {
                    "instruction": (
                        "Create a source-near factual digest from only the supplied events. "
                        "Do not infer goals, decisions, results, or next steps that are absent. "
                        "Preserve the user's language. Cite eventIds for every material fact. "
                        "Use an empty array or empty string when the source does not establish a field."
                    ),
                    "threadId": candidate.thread_id,
                    "part": index,
                    "partCount": len(chunks),
                    "events": [event.as_dict() for event in chunk],
                },
                ensure_ascii=False,
            )
            partials.append(validate_note_data(self._invoke(prompt), allowed_ids))
        if len(partials) == 1:
            return partials[0]
        reduction_prompt = json.dumps(
            {
                "instruction": (
                    "Merge these ordered partial factual digests into one session note. "
                    "Remove duplication, preserve corrections over superseded statements, retain eventIds, "
                    "and do not add facts or recommendations."
                ),
                "threadId": candidate.thread_id,
                "partials": partials,
            },
            ensure_ascii=False,
        )
        return validate_note_data(self._invoke(reduction_prompt), allowed_ids)


def source_timestamp(value: str) -> datetime:
    try:
        return parse_datetime(value).astimezone()
    except PipelineError:
        return now_local()


def find_note_matches(project: Project, thread_id: str) -> list[Path]:
    if not project.sessions_path.is_dir():
        return []
    matches: list[Path] = []
    for path in sorted(project.sessions_path.glob("*.md")):
        try:
            lines, _body = split_frontmatter_lines(path.read_text(encoding="utf-8-sig"))
        except (OSError, SystemExit):
            continue
        if frontmatter_list_value(lines, "sourceThreadIds") == [thread_id]:
            matches.append(path)
    return matches


def choose_note_path(candidate: Candidate, title: str) -> tuple[Path, dict[str, str], list[str]]:
    matches = find_note_matches(candidate.project, candidate.thread_id)
    if len(matches) > 1:
        raise PipelineError(
            f"multiple session notes match thread {candidate.thread_id}: "
            + ", ".join(str(path) for path in matches)
        )
    if matches:
        existing_text = matches[0].read_text(encoding="utf-8-sig")
        lines, _body = split_frontmatter_lines(existing_text)
        return (
            matches[0],
            parse_simple_frontmatter(existing_text),
            frontmatter_list_value(lines, "distilledTo"),
        )
    started = source_timestamp(candidate.started_at)
    session_id = started.strftime("%Y%m%dT%H%M%S%z")
    base = candidate.project.sessions_path / f"{session_id}-{slugify(title)}.md"
    if not base.exists():
        return base, {}, []
    suffix = re.sub(r"[^A-Za-z0-9]", "", candidate.thread_id)[:8] or "thread"
    return base.with_name(f"{base.stem}-{suffix}{base.suffix}"), {}, []


def render_note(
    candidate: Candidate,
    data: dict[str, Any],
    existing: dict[str, str],
    existing_distilled_to: list[str],
) -> str:
    started = source_timestamp(candidate.started_at)
    created = existing.get("date") or started.isoformat(timespec="seconds")
    session_id = existing.get("sessionId") or started.strftime("%Y%m%dT%H%M%S%z")
    distillation_status = "partial" if existing_distilled_to else "pending"
    last_state = data["lastKnownState"]
    fields: list[tuple[str, str | int | list[str]]] = [
        ("type", "session"),
        ("schemaVersion", SESSION_SCHEMA_VERSION),
        ("title", str(data["title"]).strip() or "Codex session"),
        ("description", str(data["description"]).strip()),
        ("generator", "Codex"),
        ("status", str(last_state["workState"])),
        ("reviewStatus", "unreviewed"),
        ("distillationStatus", distillation_status),
        ("distilledTo", existing_distilled_to),
        ("date", created),
        ("updated", now_iso()),
        ("sessionId", session_id),
        ("sourceType", "codexChat"),
        ("sourceThreadIds", [candidate.thread_id]),
        ("sourceRefs", [candidate.source_ref]),
    ]
    lines = [frontmatter(fields), "", f"# {str(data['title']).strip() or 'Codex session'}", ""]
    summary_ids = ", ".join(str(value) for value in data.get("summaryEventIds", []))
    lines.extend(["## Summary", "", str(data["summary"]).strip() or "確認できる記録なし。"])
    if summary_ids:
        lines.extend(["", f"Source events: `{summary_ids}`"])
    lines.extend(["", "## Key Developments", ""])
    developments = data.get("keyDevelopments") or []
    if not developments:
        lines.append("- 確認できる記録なし。")
    for item in developments:
        event_ids = ", ".join(str(value) for value in item.get("eventIds", []))
        citation = f" Source events: `{event_ids}`" if event_ids else ""
        lines.append(f"- {item['label']}: {str(item['text']).strip()}{citation}")
    lines.extend(
        [
            "",
            "## Last Known State",
            "",
            f"- Work State: {last_state['workState']} — {str(last_state['detail']).strip()}",
            "- Latest User Direction: "
            + (str(last_state["latestUserDirection"]).strip() or "追加指示なし。"),
        ]
    )
    for unresolved in last_state.get("unresolved", []):
        lines.append(f"- Unresolved: {str(unresolved).strip()}")
    continuation = str(last_state.get("continuationPoint") or "").strip()
    if continuation:
        lines.append(f"- Continuation Point: {continuation}")
    state_ids = ", ".join(str(value) for value in last_state.get("eventIds", []))
    if state_ids:
        lines.append(f"- Source Events: `{state_ids}`")
    limitations = [str(value).strip() for value in data.get("sourceLimitations", []) if str(value).strip()]
    if limitations:
        lines.extend(["", "## Source Notes", ""])
        lines.extend(f"- {value}" for value in limitations)
    return "\n".join(lines).rstrip() + "\n"


def revalidate_candidate(candidate: Candidate, config: PipelineConfig) -> None:
    try:
        candidate.source_path.stat()
    except OSError as exc:
        raise PipelineError(f"source log disappeared: {candidate.source_relative_ref}") from exc
    session = read_session(candidate.source_path)
    if not session:
        raise PipelineError(f"source log no longer has metadata: {candidate.source_relative_ref}")
    events = tuple(
        event
        for event in read_session_events(candidate.source_path)
        if event_matches_project(event, candidate.project)
    )
    current = fingerprint_events(session.id, events, candidate.source_ref)
    if current != candidate.fingerprint:
        raise PipelineError(f"source log changed during generation: {candidate.source_relative_ref}")


def write_candidate_note(
    candidate: Candidate,
    config: PipelineConfig,
    summarizer: Summarizer,
) -> Path:
    data = summarizer.generate(candidate)
    allowed_ids = {event.id for event in candidate.events}
    validate_note_data(data, allowed_ids)
    revalidate_candidate(candidate, config)
    note_path, existing, existing_distilled_to = choose_note_path(candidate, str(data["title"]))
    rendered = render_note(candidate, data, existing, existing_distilled_to)
    atomic_write_text(note_path, rendered)
    update_refresh_state(candidate.project, config, candidate, note_path)
    return note_path


def write_run_report(cache_root: Path, report: dict[str, Any]) -> Path:
    run_id = now_local().strftime("%Y%m%dT%H%M%S%z") + f"-{uuid.uuid4().hex[:8]}"
    path = cache_root / "runs" / f"{run_id}.json"
    atomic_write_json(path, report)
    return path


def execute_pipeline(
    config: PipelineConfig,
    projects: Sequence[Project],
    *,
    summarizer: Summarizer | None,
    dry_run: bool = False,
    backfill: bool = False,
    project_ids: Sequence[str] = (),
    thread_ids: Sequence[str] = (),
    limit: int | None = None,
    cache_root: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    started = now_local()
    deadline = started + timedelta(minutes=config.runtime_minutes)
    candidates, scan_counts = scan_candidates(
        config,
        projects,
        backfill=backfill,
        project_ids=project_ids,
        thread_ids=thread_ids,
    )
    if limit is not None:
        if limit <= 0:
            raise PipelineError("limit must be positive")
        candidates = candidates[-limit:] if backfill else candidates[:limit]
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "startedAt": started.isoformat(timespec="seconds"),
        "finishedAt": None,
        "mode": "backfill" if backfill else "daily",
        "dryRun": dry_run,
        "scan": scan_counts,
        "selectedCount": len(candidates),
        "processed": [],
        "failed": [],
        "deferred": [],
    }
    if dry_run:
        report["selected"] = [
            {
                "projectId": item.project.project_id,
                "threadId": item.thread_id,
                "sourceRef": item.source_ref,
                "startedAt": item.started_at,
            }
            for item in candidates
        ]
    else:
        if summarizer is None:
            raise PipelineError("a summarizer is required for a write run")
        for index, candidate in enumerate(candidates):
            if now_local() >= deadline:
                report["deferred"].extend(
                    {
                        "projectId": item.project.project_id,
                        "threadId": item.thread_id,
                        "reason": "runtime-deadline",
                    }
                    for item in candidates[index:]
                )
                break
            try:
                note_path = write_candidate_note(candidate, config, summarizer)
            except Exception as exc:  # Per-thread isolation is intentional.
                report["failed"].append(
                    {
                        "projectId": candidate.project.project_id,
                        "threadId": candidate.thread_id,
                        "error": str(exc),
                    }
                )
                continue
            report["processed"].append(
                {
                    "projectId": candidate.project.project_id,
                    "threadId": candidate.thread_id,
                    "sessionNote": note_path.relative_to(candidate.project.context_path).as_posix(),
                }
            )
    report["finishedAt"] = now_iso()
    report_path = write_run_report(cache_root or default_cache_root(), report)
    return report, report_path
