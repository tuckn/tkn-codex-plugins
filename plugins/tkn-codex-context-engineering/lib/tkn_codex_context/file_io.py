"""Filesystem helpers shared by context-engineering Skills."""

from __future__ import annotations

import shutil
from pathlib import Path

from .common import Result


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

def plan_non_destructive_copies(
    mappings: Iterable[tuple[Path, Path]],
    result: Result,
) -> list[tuple[Path, Path]]:
    planned: list[tuple[Path, Path]] = []
    for source, destination in mappings:
        if not source.exists():
            continue
        source_files = [source] if source.is_file() else sorted(path for path in source.rglob("*") if path.is_file())
        for source_file in source_files:
            relative = Path(source_file.name) if source.is_file() else source_file.relative_to(source)
            destination_file = destination if source.is_file() else destination / relative
            if destination_file.exists():
                if source_file.read_bytes() == destination_file.read_bytes():
                    result.add("skip-identical", str(destination_file))
                    continue
                raise SystemExit(
                    "Migration destination already exists with different content: "
                    f"{destination_file}"
                )
            result.add("copy", f"{source_file} -> {destination_file}")
            planned.append((source_file, destination_file))
    return planned

def execute_non_destructive_copies(
    planned: Iterable[tuple[Path, Path]],
    write: bool,
) -> None:
    if not write:
        return
    for source, destination in planned:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

def require_explicit_output_dest(option_name: str, command_name: str) -> Path:
    raise SystemExit(
        f"{command_name} requires {option_name}. "
        "Choose a destination from the current project folder instructions "
        "or pass an explicit path for this run."
    )

