---
name: init-project-context
description: Initialize or refresh a Codex Project folder by writing repo-local `.tkn/codex-context.yaml`, indexing it in the private `~/.tkn/codex-context/state/index.jsonl` registry, and creating private project state under the projectId-specific folder. Use when the user explicitly wants to initialize, connect, move, rename, migrate, or update project context; initialization is a readiness gate and does not trigger other Skills by itself.
---

# Initialize Project Context

Use this skill to give a Codex Project folder a stable private context identity that does not depend on the current folder name.

The project folder has a small repo-local marker file for matching the local folder to the private global registry. Project context files are stored under the user's home directory because working context, sessions, and decisions can contain private details.

## Initialization Boundary

Initialization is a readiness gate, not an automatic trigger for other Skills.

- Creating or refreshing `.tkn/codex-context.yaml` only marks the repository as intentionally connected to private project context.
- Other project-scoped Skills still require matching user intent before they run.
- Do not start session notes, decisions, working-context updates, distillation, review, import, promotion, or audits just because this skill created the marker.
- After initialization, downstream Skills should verify that `.tkn/codex-context.yaml` resolves through `~/.tkn/codex-context/state/index.jsonl` for the current workspace before reading or writing project context.

## Artifacts

Local project marker:

```text
.tkn/codex-context.yaml
```

Private global registry:

```text
~/.tkn/codex-context/state/index.jsonl
```

Private project context folder:

```text
~/.tkn/codex-context/state/<projectId>/
  working-context.md
  sessions/
  decisions/
  memos/
```

Identity is split by privacy boundary:

- `projectId`: logical project identity. Generated as `yyyyMMdd_<slug>_<shortId>` and stored in `.tkn/codex-context.yaml` plus the private registry.
- `workspaceId`: this checkout or worktree on this machine. Stored only in the private global registry.
- `repoId`: repository identity derived from git remote when possible. Stored only in the private global registry.

In `.tkn/codex-context.yaml`, `description` describes the Codex Project folder itself. It is not the `working-context.md` dashboard description and must not be copied from working context Frontmatter by default.

Do not create new working context, session notes, or decision records inside the Codex Project folder by default.

## Workflow

1. Check repository instructions when relevant.
2. Resolve this skill's plugin root and use `../../scripts/context_bridge/init_project_context.py`.
3. Decide marker metadata before write:
   - use `--title` when the folder name is not the right display title;
   - use `--description` only when a short Codex Project folder description is known;
   - if the project is still blank or unclear, leave `description` empty rather than inventing one;
   - ask the user before registration only when the request needs a meaningful title or description now.
4. Run dry-run first.
5. Confirm the planned `~/.tkn/codex-context/state/index.jsonl` update and `state/<projectId>/` context folder are expected.
6. Use `--write` only when the user asked to register or update the project context.
7. If this changes managed Skill behavior or current repository truth, update the session note and working context.

Initialization behavior:

- Reuse an existing registry record for the same current root.
- If `.tkn/codex-context.yaml` already exists, use its `projectId` to match the private registry.
- During explicit initialization, use legacy `.codex-context/project.yaml` and `~/.codex-context/projects/` only to preserve an existing identity and state; do not delete or overwrite the legacy source.
- If that local `projectId` exists in the registry and the old root no longer exists, treat it as a folder move and reuse `projectId` and `workspaceId`.
- If that local `projectId` is already attached to an existing root, create a new `projectId` for this folder and update `.tkn/codex-context.yaml`.
- If exactly one matching `repoId` record exists and its old root no longer exists, treat it as a folder move and reuse `projectId` and `workspaceId`.
- If an old root still exists, or multiple matching candidates exist, create a new `projectId` and `workspaceId`.
- Generate new `projectId` values as `yyyyMMdd_<slug>_<shortId>`, for example `20260704_tkn-codex-plugins_k92p7q1d`.
- Create or update `.tkn/codex-context.yaml` with `projectId`, `title`, `description`, `createdAt`, and `updatedAt`.
- Preserve an existing local `description`, including an intentional empty string, unless `--description` is provided.
- Do not seed `.tkn/codex-context.yaml` `description` from `working-context.md`; when no marker description or `--description` is available, write `description: ""`.
- Create `~/.tkn/codex-context/state/<projectId>/working-context.md`, `sessions/`, `decisions/`, and `memos/`.
- Store `workspaceId`, `repoId`, local root, project state paths, status, sensitivity, and `lastSeenAt` in `~/.tkn/codex-context/state/index.jsonl`.

## Commands

Dry-run:

```powershell
python <plugin-root>/scripts/context_bridge/init_project_context.py `
  --target ~/.tkn/codex-context `
  --repo-root . `
  --dry-run
```

Write:

```powershell
python <plugin-root>/scripts/context_bridge/init_project_context.py `
  --target ~/.tkn/codex-context `
  --repo-root . `
  --write
```

Optional arguments:

- `--title <name>`: display title. Defaults to the repository folder name.
- `--description <text>`: short description of the Codex Project folder. Defaults to preserving the existing marker description or writing an empty string for new markers.
- `--status active|inactive|archived`: workspace lifecycle. Defaults to `active`.
- `--sensitivity private|internal|public`: context sensitivity. Defaults to `private`.
- `--log <path>`: write the operation summary.

## Safety

- Do not write to the real `~/.tkn/codex-context` unless the user explicitly asked for a write operation.
- Use OS temp or a project-specific test workspace for fake stores in tests.
- Keep real local absolute paths out of committed repository files.
- Keep working context, session notes, decision records, `workspaceId`, `repoId`, and local root paths out of repo-local context files by default.
- Keep `.tkn/codex-context.yaml` small; it is only a local/global project identity marker.
- Keep marker `description` short and project-folder-oriented; detailed current truth belongs in private `working-context.md`.
- Treat `~/.tkn/codex-context` as private; registry records and project context files may include real local paths and private project details.
- Current user instructions, repository `AGENTS.md`, current files, and git state override imported or registered context.
