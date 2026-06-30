---
name: register-project-context
description: Register or refresh a repository's Codex project identity in repo-local `.codex-context/project.yml` and the private user-global `~/.codex-context/projects/index.jsonl` registry. Use when initializing context for a project, after a project folder move or rename, when connecting repo-local context to global context, or when updating project registry metadata.
---

# Register Project Context

Use this skill to give a repository a stable Codex context identity that does not depend on the current folder name.

The local project file is safe to keep in a repository because it avoids absolute local roots. The private global registry may store real local paths.

## Artifacts

Local project file:

```text
.codex-context/project.yml
```

Private global registry:

```text
~/.codex-context/projects/index.jsonl
```

The project identity has three IDs:

- `projectId`: logical project identity.
- `workspaceId`: this checkout or worktree on this machine.
- `repoId`: repository identity derived from git remote when possible.

Existing IDs must be preserved. Do not regenerate them when `.codex-context/project.yml` already exists.

## Workflow

1. Check repository instructions and `.codex-context/working-context.md` when relevant.
2. Resolve this skill's plugin root and use `../../scripts/context_bridge/register_project_context.py`.
3. Run dry-run first.
4. Confirm the planned local project file and global registry target are expected.
5. Use `--write` only when the user asked to register or update the project context.
6. If this changes managed Skill behavior or current repository truth, update the session note and working context.

## Commands

Dry-run:

```bash
python3 <plugin-root>/scripts/context_bridge/register_project_context.py \
  --target ~/.codex-context \
  --repo-root . \
  --dry-run
```

Write:

```bash
python3 <plugin-root>/scripts/context_bridge/register_project_context.py \
  --target ~/.codex-context \
  --repo-root . \
  --write
```

Optional arguments:

- `--project-file .codex-context/project.yml`: local project identity file path.
- `--title <name>`: display title. Defaults to the repository folder name.
- `--status active|inactive|archived`: workspace lifecycle. Defaults to `active`.
- `--sensitivity private|internal|public`: context sensitivity. Defaults to `private`.
- `--log <path>`: write the operation summary.

## Safety

- Do not write to the real `~/.codex-context` unless the user explicitly asked for a write operation.
- Use `.local/` fake stores for tests.
- Keep real local absolute paths out of committed repository files.
- Treat `~/.codex-context` as private; registry records may include real local paths there.
- Current user instructions, repository `AGENTS.md`, current files, and git state override imported or registered context.

