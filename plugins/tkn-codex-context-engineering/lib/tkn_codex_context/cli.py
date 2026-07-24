"""Command-line interface for Tuckn Codex Context Engineering."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from .session_notes import (
    CodexSummarizer,
    PipelineError,
    default_cache_root,
    default_config_path,
    default_registry_path,
    execute_pipeline,
    execute_rebuild,
    load_active_projects,
    load_config,
    make_config,
    now_iso,
    resolve_codex_bin,
    write_config,
)


def path_value(value: str) -> Path:
    return Path(value).expanduser().absolute()


def add_common_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=path_value, default=default_config_path())
    parser.add_argument("--registry", type=path_value, default=default_registry_path())
    parser.add_argument("--cache-root", type=path_value, default=default_cache_root())
    parser.add_argument("--dry-run", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tkn-codex-context")
    commands = parser.add_subparsers(dest="command", required=True)
    session_notes = commands.add_parser(
        "session-notes", description="Generate project session notes from Codex JSONL chats."
    )
    actions = session_notes.add_subparsers(dest="session_notes_command", required=True)

    configure = actions.add_parser("configure")
    configure.add_argument("--config", type=path_value, default=default_config_path())
    configure.add_argument("--sessions-root", type=path_value)
    configure.add_argument("--codex-bin", default="")
    configure.add_argument("--reset-watermark", action="store_true")
    configure.add_argument("--dry-run", action="store_true")

    run = actions.add_parser("run")
    add_common_run_options(run)

    backfill = actions.add_parser("backfill")
    add_common_run_options(backfill)
    selector = backfill.add_mutually_exclusive_group(required=True)
    selector.add_argument("--project-id", action="append", default=[])
    selector.add_argument("--all", action="store_true")
    backfill.add_argument("--thread-id", action="append", default=[])
    backfill.add_argument("--limit", type=int)

    rebuild = actions.add_parser("rebuild")
    add_common_run_options(rebuild)
    rebuild.add_argument("--project-id", required=True)
    rebuild.add_argument("--approve-root", type=path_value, action="append", default=[])
    rebuild.add_argument("--force", action="store_true")
    return parser


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def print_progress(event: dict[str, object]) -> None:
    event_type = str(event.get("type") or "")
    if event_type == "thread-start":
        print(
            f"[{event['index']}/{event['total']}] START {event['threadId']}",
            file=sys.stderr,
            flush=True,
        )
    elif event_type == "thread-complete":
        print(
            f"[{event['index']}/{event['total']}] DONE "
            f"{event['durationSeconds']}s",
            file=sys.stderr,
            flush=True,
        )
    elif event_type == "thread-resumed":
        print(
            f"[{event['index']}/{event['total']}] RESUME",
            file=sys.stderr,
            flush=True,
        )
    elif event_type == "thread-failed":
        print(
            f"[{event['index']}/{event['total']}] FAILED {event['error']}",
            file=sys.stderr,
            flush=True,
        )
    elif event_type == "chunk-start":
        print(
            f"  CHUNK {event['chunk']}/{event['chunkCount']}",
            file=sys.stderr,
            flush=True,
        )


def run_configure(args: argparse.Namespace) -> int:
    existing = load_config(args.config) if args.config.is_file() else None
    config = make_config(
        existing=existing,
        sessions_root=args.sessions_root,
        codex_bin=args.codex_bin,
        installed_at=now_iso() if args.reset_watermark else None,
    )
    if not args.dry_run:
        write_config(args.config, config)
    print_json(
        {
            "dryRun": args.dry_run,
            "config": str(args.config),
            "settings": {
                "installedAt": config.installed_at,
                "sessionsRoot": str(config.sessions_root),
                "sourceId": config.source_id,
                "codexBin": config.codex_bin,
                "model": config.model,
                "reasoningEffort": config.reasoning_effort,
                "idleMinutes": config.idle_minutes,
                "runtimeMinutes": config.runtime_minutes,
            },
        }
    )
    return 0


def run_pipeline(args: argparse.Namespace, *, backfill: bool) -> int:
    config = load_config(args.config)
    projects = load_active_projects(args.registry)
    summarizer = None
    if not args.dry_run:
        config = replace(config, codex_bin=resolve_codex_bin(config.codex_bin))
        summarizer = CodexSummarizer(config, observer=print_progress)
    report, report_path = execute_pipeline(
        config,
        projects,
        summarizer=summarizer,
        dry_run=args.dry_run,
        backfill=backfill,
        project_ids=(() if getattr(args, "all", False) else getattr(args, "project_id", ())),
        thread_ids=getattr(args, "thread_id", ()),
        limit=getattr(args, "limit", None),
        cache_root=args.cache_root,
        progress=print_progress,
    )
    print_json({"report": str(report_path), **report})
    return 1 if report["failed"] else 0


def run_rebuild(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    projects = load_active_projects(args.registry)
    matches = [item for item in projects if item.project_id == args.project_id]
    if len(matches) != 1:
        raise PipelineError(f"unknown or inactive projectId: {args.project_id}")
    summarizer = None
    if not args.dry_run:
        config = replace(config, codex_bin=resolve_codex_bin(config.codex_bin))
        summarizer = CodexSummarizer(config, observer=print_progress)
    report, report_path = execute_rebuild(
        config,
        matches[0],
        summarizer=summarizer,
        approve_roots=args.approve_root,
        force=args.force,
        dry_run=args.dry_run,
        cache_root=args.cache_root,
        progress=print_progress,
    )
    print_json({"report": str(report_path), **report})
    return 1 if report["failed"] or report["deferred"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.session_notes_command == "configure":
            return run_configure(args)
        if args.session_notes_command == "run":
            return run_pipeline(args, backfill=False)
        if args.session_notes_command == "backfill":
            return run_pipeline(args, backfill=True)
        if args.session_notes_command == "rebuild":
            return run_rebuild(args)
        raise PipelineError(f"unsupported command: {args.session_notes_command}")
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
