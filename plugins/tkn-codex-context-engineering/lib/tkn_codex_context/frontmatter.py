"""Small frontmatter helpers shared by project initialization and distillation."""

from __future__ import annotations

import re

from .common import yaml_string


FRONTMATTER_PATTERN = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n?", re.DOTALL)


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
    allowed_home_refs = (
        "~/.tkn/codex-context/",
        "~/.codex-context/",  # Legacy refs may be preserved while finalizing migrated sessions.
        "~/.codex-working/",
    )
    if ref == "~" or (ref.startswith("~/") and not ref.startswith(allowed_home_refs)):
        raise SystemExit(
            "Only ~/.tkn/codex-context, legacy ~/.codex-context, or explicit ~/.codex-working "
            "paths are allowed "
            f"for home-relative distilledTo refs: {value}"
        )
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

