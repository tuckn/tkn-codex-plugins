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

The initialized store includes `projects/index.jsonl`, `patterns/`, `skill-candidates/`,
`agents-candidates/`, and `reviews/` in addition to decisions and candidates.

Register this repository in the private project registry:

```bash
python3 <plugin-root>/scripts/context_bridge/register_project_context.py \
  --target ~/.codex-context \
  --repo-root . \
  --dry-run
```

Use `--write` to create or update `.codex-context/project.yml` and
`~/.codex-context/projects/index.jsonl`.

Import global context into this repository:

```bash
python3 <plugin-root>/scripts/context_bridge/import_context.py \
  --source ~/.codex-context \
  --dest .codex-context/global-context \
  --include working-context,decisions,candidates \
  --dry-run
```

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
