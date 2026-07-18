from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path


LEGACY_REF = re.compile(
    r"(?<![~/A-Za-z0-9_.-])"
    r"\.codex-context/"
    r"(?P<suffix>(?:decisions|sessions|memos)"
    r"(?:/[^\s`,、。)）\]}]+)?/?)"
)


def replacement_for(note: Path, state_root: Path, match: re.Match[str]) -> str:
    suffix = match.group("suffix")
    keep_trailing_slash = suffix.endswith("/")
    target = state_root / suffix.rstrip("/")
    if not target.exists():
        return match.group(0)

    relative = os.path.relpath(target, start=note.parent).replace("\\", "/")
    if not relative.startswith("."):
        relative = f"./{relative}"
    if keep_trailing_slash:
        relative += "/"
    return relative


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("state_root", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    state_root = args.state_root.resolve()
    report: list[dict[str, object]] = []
    total_replacements = 0

    for note in sorted(state_root.rglob("*.md")):
        original = note.read_text(encoding="utf-8")
        replacements: list[dict[str, str]] = []

        def replace(match: re.Match[str]) -> str:
            nonlocal total_replacements
            updated = replacement_for(note, state_root, match)
            if updated != match.group(0):
                total_replacements += 1
                replacements.append({"from": match.group(0), "to": updated})
            return updated

        updated_text = LEGACY_REF.sub(replace, original)
        if updated_text == original:
            continue
        if args.write:
            note.write_text(updated_text, encoding="utf-8", newline="")
        report.append(
            {
                "file": note.relative_to(state_root).as_posix(),
                "replacementCount": len(replacements),
                "replacements": replacements,
            }
        )

    print(
        json.dumps(
            {
                "mode": "write" if args.write else "dry-run",
                "stateRoot": str(state_root),
                "changedFiles": len(report),
                "replacementCount": total_replacements,
                "files": report,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
