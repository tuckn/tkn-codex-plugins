#!/usr/bin/env python3
"""Sync Codex Context Engineering Skills to target repositories."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any


DEFAULT_SKILLS = [
    "audit-context-freshness",
    "distill-session-context",
    "extract-codex-sessions",
    "import-global-context",
    "maintain-session-note",
    "maintain-working-context",
    "migrate-local-project-context",
    "organize-brain-dump",
    "promote-global-context",
    "register-project-context",
    "record-decision",
    "resume-session",
    "review-decisions",
]


def repo_root_from_script() -> Path:
    return Path(__file__).absolute().parents[2]


def platform_path(path_value: str) -> Path:
    """Convert a Windows absolute path to WSL path when running under Linux."""
    normalized = path_value.replace("\\", "/")
    if len(normalized) >= 3 and normalized[1] == ":" and normalized[2] == "/":
        drive = normalized[0].lower()
        rest = normalized[3:]
        if os.name != "nt":
            return Path("/mnt") / drive / rest
    return Path(normalized)


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("targets"), list):
        raise ValueError("Manifest must be a JSON object with a 'targets' list.")
    return data


def resolve_targets(manifest: dict[str, Any], selected: str) -> list[dict[str, Any]]:
    targets = manifest["targets"]
    if selected == "all":
        return targets
    for target in targets:
        if target.get("name") == selected:
            return [target]
    names = ", ".join(str(target.get("name")) for target in targets)
    raise ValueError(f"Unknown target '{selected}'. Available targets: {names}")


def copy_skill(source: Path, destination: Path, dry_run: bool) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Source skill directory not found: {source}")
    if dry_run:
        print(f"DRY-RUN copy {source} -> {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    print(f"copied {source.name} -> {destination}")


def sync(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).absolute() if args.repo_root else repo_root_from_script()
    source_skills_root = (
        Path(args.skills_root).absolute()
        if args.skills_root
        else repo_root / "plugins" / "tkn-codex-context-engineering" / "skills"
    )
    manifest_path = Path(args.manifest).resolve()
    manifest = load_manifest(manifest_path)
    targets = resolve_targets(manifest, args.target)
    skills = args.skill or DEFAULT_SKILLS

    for target in targets:
        target_name = target.get("name")
        target_path = target.get("path")
        skills_path = target.get("skillsPath", ".agents\\skills")
        if not target_name or not target_path:
            raise ValueError(f"Target entries require name and path: {target}")

        target_root = platform_path(str(target_path))
        target_skills_root = target_root / Path(str(skills_path).replace("\\", "/"))
        print(f"target {target_name}: {target_skills_root}")

        for skill in skills:
            copy_skill(
                source_skills_root / skill,
                target_skills_root / skill,
                dry_run=args.dry_run,
            )

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync plugin-bundled skills from this repository to target repositories."
    )
    parser.add_argument(
        "--manifest",
        default=str(repo_root_from_script() / "scripts" / "sync_skills" / "targets.json"),
        help="JSON manifest containing distribution targets.",
    )
    parser.add_argument(
        "--target",
        default="all",
        help="Target name from manifest, or 'all'.",
    )
    parser.add_argument(
        "--skill",
        action="append",
        choices=DEFAULT_SKILLS,
        help="Skill name to sync. Repeat to sync multiple. Defaults to all managed skills.",
    )
    parser.add_argument(
        "--repo-root",
        help="Repository root override. Defaults to this script's repository root.",
    )
    parser.add_argument(
        "--skills-root",
        help=(
            "Source skills root override. Defaults to "
            "plugins/tkn-codex-context-engineering/skills under the repository root."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print copy operations without writing files.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return sync(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
