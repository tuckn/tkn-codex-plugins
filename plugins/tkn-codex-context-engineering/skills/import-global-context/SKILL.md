---
name: import-global-context
description: Load selected user-global Codex context from `~/.codex-context` into the current task, preferably read-only, and create repository snapshots only when explicitly requested. Use when the user asks to load, import, apply, reference, or use global Codex context, other-chat context, or cross-repository Codex context.
---

# Import Global Context

Use this skill when the user asks to use user-global Codex context in the current repository.

Default to read-only load. Do not copy global context into the repository unless the user explicitly asks for an import, snapshot, or write.

## Source

```text
~/.codex-context
```

This store is private historical context. It does not override current user instructions, system/developer instructions, repository `AGENTS.md`, current files, or git state.

## Default Workflow

1. Check repository instructions and project `working-context.md` under `~/.codex-context/projects/<projectId>/` when relevant.
2. Resolve this skill's plugin root and use `../../scripts/context_bridge/load_global_context.py`.
3. Run read-only load to inspect relevant global context.
4. Read only specific referenced files when the current task needs them.
5. Compare loaded context against current repository state before using it.
6. Record how loaded context was used in the session note when the task is non-trivial.

Read-only load:

```bash
python3 <plugin-root>/scripts/context_bridge/load_global_context.py \
  --source ~/.codex-context
```

Preview selected files:

```bash
python3 <plugin-root>/scripts/context_bridge/load_global_context.py \
  --source ~/.codex-context \
  --decision DR-G-example.md \
  --candidate example-candidate.md \
  --pattern example-pattern.md
```

The load command writes no files. It returns a short summary, category file lists, and short previews for explicitly selected files.

## Snapshot Import

Use snapshot import only when the user explicitly asks to copy, write, import, or snapshot global context into the repository.

Default snapshot destination:

```text
.local/codex-context/global-context/
```

Dry-run:

```bash
python3 <plugin-root>/scripts/context_bridge/import_context.py \
  --source ~/.codex-context \
  --include working-context,decisions,candidates \
  --dry-run
```

Write snapshot:

```bash
python3 <plugin-root>/scripts/context_bridge/import_context.py \
  --source ~/.codex-context \
  --include working-context,decisions,candidates \
  --write
```

Repository `.codex-context/global-context/` snapshots are allowed only when explicitly requested:

```bash
python3 <plugin-root>/scripts/context_bridge/import_context.py \
  --source ~/.codex-context \
  --dest .codex-context/global-context \
  --include working-context,decisions,candidates \
  --write
```

## Snapshot Contract

The snapshot import command writes:

```text
.local/codex-context/global-context/
  README.md
  working-context.md
  decisions/
  candidates/
  imports/
    YYYYMMDDTHHMMSS+0900-import-manifest.md
```

Snapshots are historical references. Validate them against current repository state before using them.

## Safety

- Do not blindly read all global context.
- Do not write snapshots unless the user explicitly requested a write/import/snapshot.
- Prefer `.local/` snapshots because `.local/` is ignored in this repository.
- If using `.codex-context/global-context/`, treat it as historical reference and avoid committing private or stale context accidentally.
- Stop if global context contains secrets, credentials, tokens, private keys, full env vars, large logs, or unnecessary personal/customer data.
