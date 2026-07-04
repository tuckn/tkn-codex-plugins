---
name: register-project-context
description: Register or refresh a Codex Project folder by writing repo-local `.codex-context/project.yaml`, indexing it in the private `~/.codex-context/projects/index.jsonl` registry, and creating private project context under `~/.codex-context/projects/<projectId>/`. Use when initializing context for a project folder, after a project folder move or rename, when connecting a folder to private Codex context, or when updating project registry metadata.
---

# Register Project Context

Use this skill to give a Codex Project folder a stable private context identity that does not depend on the current folder name.

The project folder has a small repo-local marker file for matching the local folder to the private global registry. Project context files are stored under the user's home directory because working context, sessions, and decisions can contain private details.

## Artifacts

Local project marker:

```text
.codex-context/project.yaml
```

Private global registry:

```text
~/.codex-context/projects/index.jsonl
```

Private project context folder:

```text
~/.codex-context/projects/<projectId>/
  working-context.md
  sessions/
  decisions/
```

Identity is split by privacy boundary:

- `projectId`: logical project identity. Generated as `yyyyMMdd_<slug>_<shortId>` and stored in `.codex-context/project.yaml` plus the private registry.
- `workspaceId`: this checkout or worktree on this machine. Stored only in the private global registry.
- `repoId`: repository identity derived from git remote when possible. Stored only in the private global registry.

Do not create new working context, session notes, or decision records inside the Codex Project folder by default.

## Workflow

1. Check repository instructions when relevant.
2. Resolve this skill's plugin root and use `../../scripts/context_bridge/register_project_context.py`.
3. Run dry-run first.
4. Confirm the planned `~/.codex-context/projects/index.jsonl` update and `projects/<projectId>/` context folder are expected.
5. Use `--write` only when the user asked to register or update the project context.
6. If this changes managed Skill behavior or current repository truth, update the session note and working context.

Registration behavior:

- Reuse an existing registry record for the same current root.
- If `.codex-context/project.yaml` already exists, use its `projectId` to match the private registry.
- If that local `projectId` exists in the registry and the old root no longer exists, treat it as a folder move and reuse `projectId` and `workspaceId`.
- If that local `projectId` is already attached to an existing root, create a new `projectId` for this folder and update `.codex-context/project.yaml`.
- If exactly one matching `repoId` record exists and its old root no longer exists, treat it as a folder move and reuse `projectId` and `workspaceId`.
- If an old root still exists, or multiple matching candidates exist, create a new `projectId` and `workspaceId`.
- Generate new `projectId` values as `yyyyMMdd_<slug>_<shortId>`, for example `20260704_tkn-codex-plugins_k92p7q1d`.
- Create or update `.codex-context/project.yaml` with `projectId`, `title`, `description`, `createdAt`, and `updatedAt`.
- Create `~/.codex-context/projects/<projectId>/working-context.md`, `sessions/`, and `decisions/`.
- Store `workspaceId`, `repoId`, local root, project context paths, status, sensitivity, and `lastSeenAt` in `~/.codex-context/projects/index.jsonl`.

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

- `--title <name>`: display title. Defaults to the repository folder name.
- `--status active|inactive|archived`: workspace lifecycle. Defaults to `active`.
- `--sensitivity private|internal|public`: context sensitivity. Defaults to `private`.
- `--log <path>`: write the operation summary.

## Safety

- Do not write to the real `~/.codex-context` unless the user explicitly asked for a write operation.
- Use `.local/` fake stores for tests.
- Keep real local absolute paths out of committed repository files.
- Keep working context, session notes, decision records, `workspaceId`, `repoId`, and local root paths out of repo-local context files by default.
- Keep `.codex-context/project.yaml` small; it is only a local/global project identity marker.
- Treat `~/.codex-context` as private; registry records and project context files may include real local paths and private project details.
- Current user instructions, repository `AGENTS.md`, current files, and git state override imported or registered context.
