"""Shared primitives used by multiple context-engineering Skills."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


JST = timezone(timedelta(hours=9))
DEFAULT_CONTEXT_ROOT = "~/.tkn/codex-context"
LEGACY_CONTEXT_ROOT = "~/.codex-context"
LOCAL_MARKER = Path(".tkn") / "codex-context.yaml"
LEGACY_LOCAL_MARKER = Path(".codex-context") / "project.yaml"
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


def now_compact() -> str:
    return datetime.now(JST).strftime("%Y%m%dT%H%M%S%z")

def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")

def expand(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()

def expand_store_root(path: str | Path) -> Path:
    """Expand a store path without resolving a user-facing junction or symlink."""
    return Path(path).expanduser().absolute()

def config_path(root: Path) -> Path:
    return root / "config" / "config.yaml"

def data_root(root: Path) -> Path:
    return root / "data"

def state_root(root: Path) -> Path:
    return root / "state"

def registry_path(root: Path) -> Path:
    return state_root(root) / "index.jsonl"

def project_state_path(root: Path, project_id_value: str) -> Path:
    return state_root(root) / project_id_value

def is_versioned_store(root: Path) -> bool:
    return config_path(root).exists() or (root / "data").exists() or (root / "state").exists()

def global_data_source(root: Path) -> Path:
    """Resolve a v0.6 store root to data/, while retaining explicit flat legacy reads."""
    return data_root(root) if is_versioned_store(root) else root

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

def frontmatter(fields: list[tuple[str, str | int | list[str]]]) -> str:
    lines = ["---"]
    for key, value in fields:
        if isinstance(value, list):
            rendered = yaml_string_list(value)
            if rendered == "[]":
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                lines.append(rendered)
        elif type(value) is int:
            lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {yaml_string(value)}")
    lines.append("---")
    return "\n".join(lines)

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
