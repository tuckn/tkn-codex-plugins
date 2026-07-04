# Context Bridge Scripts

These scripts connect repository `.codex-context/` context with the user-global Codex context store at `~/.codex-context`.

They are intentionally explicit. Codex should not silently sync global context into a repository or promote repository content globally.

## Windows and WSL shared store

This repository may be opened by two Codex runtimes:

- Codex CLI running inside WSL.
- Codex App running as a Windows native app.

Both runtimes should share one physical global context store.

Use the Windows user profile as the physical store:

```text
%USERPROFILE%\.codex-context
```

From WSL, expose the same directory as `~/.codex-context` with a symlink:

```bash
ln -s /mnt/c/Users/<UserName>/.codex-context ~/.codex-context
```

After this, the paths point to the same content:

```text
Windows native: %USERPROFILE%\.codex-context
WSL:            ~/.codex-context -> /mnt/c/Users/<UserName>/.codex-context
```

Why this is needed:

- On WSL, Python expands `~/.codex-context` from the WSL home, such as `/home/exampleuser/.codex-context`.
- On Windows native Python, `~/.codex-context` expands from the Windows home, such as `%USERPROFILE%\.codex-context`.
- Without the symlink, Codex CLI and Codex App may write to different global context stores.

Check from WSL:

```bash
ls -ld ~/.codex-context /mnt/c/Users/<UserName>/.codex-context
python3 - <<'PY'
from pathlib import Path
print(Path("~/.codex-context").expanduser().resolve())
PY
```

The Python output should resolve to:

```text
/mnt/c/Users/<UserName>/.codex-context
```

If `~/.codex-context` already exists as a real WSL directory, move its contents into `%USERPROFILE%\.codex-context` first, then replace the WSL directory with the symlink. Do not create two independent stores.

## Commands

Initialize the global store:

```bash
python3 <plugin-root>/scripts/context_bridge/context_bridge.py init --target ~/.codex-context --dry-run
python3 <plugin-root>/scripts/context_bridge/context_bridge.py init --target ~/.codex-context --write
```

The initialized store includes `projects/index.jsonl`, `projects/<projectId>/`,
`patterns/`, `skill-candidates/`,
`agents-candidates/`, and `reviews/` in addition to decisions and candidates.

Register this repository in the private project registry:

```bash
python3 <plugin-root>/scripts/context_bridge/register_project_context.py \
  --target ~/.codex-context \
  --repo-root . \
  --dry-run
```

Use `--write` to create or update the local `.codex-context/project.yaml`
marker, index the Codex Project folder in `~/.codex-context/projects/index.jsonl`,
and create private project context under `~/.codex-context/projects/<projectId>/`.

Load selected global context without writing files:

```bash
python3 <plugin-root>/scripts/context_bridge/load_global_context.py \
  --source ~/.codex-context
```

Audit context freshness without changing source context:

```bash
python3 <plugin-root>/scripts/context_bridge/audit_context_freshness.py \
  --source .codex-context \
  --dry-run
```

Use `--write` to save a freshness review report under
`.local/codex-context/freshness-reviews/`.

Distill a session note into a review candidate:

```bash
python3 <plugin-root>/scripts/context_bridge/distill_session_context.py \
  --session ~/.codex-context/projects/<projectId>/sessions/<session-note>.md \
  --dry-run
```

Use `--write` to save a candidate under
`.local/codex-context/distilled-session-candidates/`.

Finalize a reviewed session distillation:

```bash
python3 <plugin-root>/scripts/context_bridge/finalize_session_distillation.py \
  --session ~/.codex-context/projects/<projectId>/sessions/<session-note>.md \
  --status distilled \
  --distilled-to ~/.codex-context/projects/<projectId>/decisions/DR-0001-example.md \
  --dry-run
```

Use `--write` only after the accepted destination exists, or use
`--status no-action` when review found nothing to carry forward.

Create a local snapshot of global context:

```bash
python3 <plugin-root>/scripts/context_bridge/import_context.py \
  --source ~/.codex-context \
  --include working-context,decisions,candidates \
  --dry-run
```

The snapshot default destination is `.local/codex-context/global-context/`. Use
`--dest .codex-context/global-context` only when a repository snapshot is explicitly needed.

Promote a candidate or decision to the global store:

```bash
python3 <plugin-root>/scripts/context_bridge/promote_context.py \
  --target ~/.codex-context \
  --kind candidate \
  --title "example title" \
  --body-file _inbox/ai/example.md \
  --dry-run
```

Use `--write` to perform changes.

## Safety

The script scans body content for common secret-like strings and stops if they are found. This is a guardrail, not a complete security scanner.
