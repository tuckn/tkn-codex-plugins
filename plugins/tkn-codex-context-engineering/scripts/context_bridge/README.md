# Context Bridge Scripts

These scripts connect a repository marker at `.tkn/codex-context.yaml` with the private Codex context store at `~/.tkn/codex-context`.

They are intentionally explicit. Codex should not silently sync global context into a repository or promote repository content globally.

The root has fixed `config/`, `data/`, and `state/` areas. Scripts accept an explicit root for tests, but their production default is `~/.tkn/codex-context`.

## Commands

Initialize the global store:

```powershell
python <plugin-root>/scripts/context_bridge/context_bridge.py init --dry-run
python <plugin-root>/scripts/context_bridge/context_bridge.py init --write
```

The initialized store includes `README.md`, `config/config.yaml`, global context categories
under `data/`, and `state/index.jsonl`. Project state is stored under `state/<projectId>/`.

Preview a non-destructive migration from the legacy flat store:

```powershell
python <plugin-root>/scripts/context_bridge/context_bridge.py init `
  --migrate-from ~/.codex-context `
  --dry-run
```

To migrate a flat store already located at the production root, pass the same source and
target. This mode renames entries in place, keeps no backup, and resumes from a temporary
migration journal if interrupted:

```powershell
python <plugin-root>/scripts/context_bridge/context_bridge.py init `
  --target ~/.tkn/codex-context `
  --migrate-from ~/.tkn/codex-context `
  --dry-run
```

Review the dry-run first, then replace `--dry-run` with `--write` to perform the move.

Initialize this repository in the private project registry:

```powershell
python <plugin-root>/scripts/context_bridge/init_project_context.py `
  --target ~/.tkn/codex-context `
  --repo-root . `
  --dry-run
```

Use `--write` to create or update `.tkn/codex-context.yaml`, index the Codex
Project folder in `~/.tkn/codex-context/state/index.jsonl`, and create
private project state under `~/.tkn/codex-context/state/<projectId>/`.

Load selected global context without writing files:

```powershell
python <plugin-root>/scripts/context_bridge/load_global_context.py `
  --source ~/.tkn/codex-context
```

Audit context freshness without changing source context:

```powershell
python <plugin-root>/scripts/context_bridge/audit_context_freshness.py `
  --source ~/.tkn/codex-context `
  --dry-run
```

Use `--write` to save a freshness review report under the private Codex
working root for the current registered project.

Distill a session note into a review candidate:

```powershell
python <plugin-root>/scripts/context_bridge/distill_session_context.py `
  --session ~/.tkn/codex-context/state/<projectId>/sessions/<session-note>.md `
  --dry-run
```

Use `--write` to save a candidate under the private Codex working root for
the current registered project.

Finalize a reviewed session distillation:

```powershell
python <plugin-root>/scripts/context_bridge/finalize_session_distillation.py `
  --session ~/.tkn/codex-context/state/<projectId>/sessions/<session-note>.md `
  --status distilled `
  --distilled-to ~/.tkn/codex-context/state/<projectId>/decisions/DR-0001-example.md `
  --dry-run
```

Use `--write` only after the accepted destination exists, or use
`--status no-action` when review found nothing to carry forward.

Create a local snapshot of global context:

```powershell
python <plugin-root>/scripts/context_bridge/import_context.py `
  --source ~/.tkn/codex-context `
  --include working-context,decisions,candidates `
  --dry-run
```

The snapshot default destination is the private Codex working root:
`%USERPROFILE%\.codex-working\projects\<projectId>\context-bridge\global-context\`.
Use `--dest .codex-context/global-context` only when a repository snapshot is
explicitly needed.

Promote a candidate or decision to the global store:

```powershell
python <plugin-root>/scripts/context_bridge/promote_context.py `
  --target ~/.tkn/codex-context `
  --kind candidate `
  --title "example title" `
  --body-file _inbox/ai/example.md `
  --dry-run
```

Use `--write` to perform changes.

## Safety

The script scans body content for common secret-like strings and stops if they are found. This is a guardrail, not a complete security scanner.
