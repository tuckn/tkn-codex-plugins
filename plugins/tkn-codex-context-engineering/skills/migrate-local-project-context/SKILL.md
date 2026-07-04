---
name: migrate-local-project-context
description: Move or safely migrate legacy repo-local Codex context from `.codex-context/working-context.md`, `.codex-context/sessions/`, and `.codex-context/decisions/` into the projectId-specific private global project context folder under `~/.codex-context/projects/` using the current project registry model. Entry Skill usable before registration when the user explicitly asks to upgrade, migrate, consolidate, or move old context to the latest `.codex-context/project.yaml` plus private global project context layout; marker creation alone is not a trigger.
---

# Migrate Local Project Context

Use this skill to upgrade legacy repo-local Codex context into the current private project context layout.

## Activation Boundary

This is an entry Skill and may run before `.codex-context/project.yaml` exists.

- Use this skill only when the user intends to migrate, consolidate, move, or upgrade legacy repo-local context.
- Do not run migration just because `.codex-context/project.yaml` exists or was generated.
- Running `register-project-context` during this workflow is allowed because migration/update intent is already explicit.
- After registration, continue only if `.codex-context/project.yaml` resolves through `~/.codex-context/projects/index.jsonl` for the current workspace.

The current layout keeps only the thin local marker in the repository:

```text
.codex-context/project.yaml
```

Private project context lives under:

```text
~/.codex-context/projects/<projectId>/
  working-context.md
  sessions/
  decisions/
```

## Source And Destination

Legacy source files may include:

```text
.codex-context/working-context.md
.codex-context/sessions/
.codex-context/decisions/
```

The destination must be resolved from the private registry:

```text
~/.codex-context/projects/index.jsonl
```

Do not infer the destination from folder name alone. Use `.codex-context/project.yaml` and the registry record to confirm `projectId`.

## Workflow

1. Check repository instructions and current git state.
2. Inspect `.codex-context/` narrowly:
   - list direct children;
   - count `sessions/*.md` and `decisions/*.md`;
   - do not read every session or decision unless needed for collision handling.
3. Use `register-project-context` first.
   - Run dry-run.
   - If the user explicitly asked to migrate or move context, run write.
   - Confirm `.codex-context/project.yaml` exists after registration.
4. Resolve `projectId` from `.codex-context/project.yaml`.
5. Read `~/.codex-context/projects/index.jsonl` and find the matching record.
   - Prefer a record with the same `projectId` and current root.
   - Use `projectContextPath`, `workingContextPath`, `sessionsPath`, and `decisionsPath` from the record when present.
   - Stop if the matching record is missing or points outside `~/.codex-context/projects/<projectId>/`.
6. Prepare a migration plan:
   - source paths;
   - destination paths;
   - files to move;
   - files that already exist at destination;
   - source cleanup to perform after verification.
7. Copy or move content only after the plan is clear.
   - Prefer copy to destination, verify counts/content, then remove legacy source files.
   - For explicit "move" requests, cleanup is allowed after verification.
   - Keep `.codex-context/project.yaml`.
8. Update project `working-context.md` or create a session note if the migration changes durable project state.

## Working Context Handling

Treat `working-context.md` as the riskiest file because it may already have been seeded by registration.

- If the destination `working-context.md` was just seeded from the local source, keep the destination and delete the legacy source after verification.
- If both source and destination exist and differ, merge manually:
  - preserve destination Frontmatter `projectId`;
  - preserve useful local body content;
  - update `updated`;
  - do not introduce `workspaceId`, `repoId`, or local root paths.
- Never overwrite a richer destination working context with a stale local one.

## Sessions And Decisions

For `sessions/` and `decisions/`:

- Move Markdown files into the corresponding destination folder.
- Preserve filenames when there is no collision.
- If the destination has the same filename:
  - if content is identical, treat the destination as already migrated and remove the source during cleanup;
  - if content differs, do not overwrite silently. Rename the source with a short suffix or ask the user when the right resolution is unclear.
- Preserve subdirectories only when they are clearly part of the context structure.

## Extra Local Files

Legacy `.codex-context/` may contain files such as migration summaries or temporary reports.

- Move them to the project context folder root only when they are durable project context.
- Leave or report files that look temporary, generated, or unrelated.
- Do not move secrets, credentials, tokens, private keys, full environment dumps, or large raw logs.

## Cleanup Rules

After verification:

- Remove migrated legacy files:
  - `.codex-context/working-context.md`
  - migrated files under `.codex-context/sessions/`
  - migrated files under `.codex-context/decisions/`
- Remove empty legacy `sessions/` and `decisions/` directories.
- Keep `.codex-context/project.yaml`.
- Keep `.codex-context/` if it contains `project.yaml` or any unresolved files.
- Report if `.gitignore` ignores `.codex-context/project.yaml`; do not change ignore rules unless the user asks.

## Safety

- Do not write to the real `~/.codex-context` unless the user explicitly asked to migrate, move, register, or update project context.
- On Windows, use PowerShell end-to-end for filesystem moves and deletes.
- Before deleting or moving recursively, resolve absolute source and destination paths and verify:
  - source is inside the current repository;
  - destination is inside `~/.codex-context/projects/<projectId>/`.
- Do not use broad cleanup commands against computed paths.
- Do not commit or expose private absolute paths in public repository files.

## Validation

Before finishing, verify:

- `.codex-context/project.yaml` exists and contains the expected `projectId`.
- `~/.codex-context/projects/index.jsonl` has the matching registry record.
- destination `working-context.md`, `sessions/`, and `decisions/` exist as expected.
- migrated session and decision file counts match the plan.
- no legacy `working-context.md`, migrated `sessions/*.md`, or migrated `decisions/*.md` remain locally.
- `.codex-context/project.yaml` remains local.
- git status is reviewed, including ignored `.codex-context/` when relevant.
