---
name: migrate-local-project-context
description: Move or safely migrate legacy repo-local Codex context from `.codex-context/working-context.md`, `.codex-context/sessions/`, and `.codex-context/decisions/` into project state under `~/.tkn/codex-context/state/`. Entry Skill usable before initialization when the user explicitly asks to upgrade, migrate, consolidate, or move old context to the latest `.tkn/codex-context.yaml` plus private project state layout; marker creation alone is not a trigger.
---

# Migrate Local Project Context

Use this skill to upgrade legacy repo-local Codex context into the current private project context layout.

## Activation Boundary

This is an entry Skill and may run before `.tkn/codex-context.yaml` exists.

- Use this skill only when the user intends to migrate, consolidate, move, or upgrade legacy repo-local context.
- Do not run migration just because `.tkn/codex-context.yaml` exists or was generated.
- Running `init-project-context` during this workflow is allowed because migration/update intent is already explicit.
- After initialization, continue only if `.tkn/codex-context.yaml` resolves through `~/.tkn/codex-context/state/index.jsonl` for the current workspace.

The current layout keeps only the thin local marker in the repository:

```text
.tkn/codex-context.yaml
```

Private project context lives under:

```text
~/.tkn/codex-context/state/<projectId>/
  working-context.md
  sessions/
  decisions/
  memos/
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
~/.tkn/codex-context/state/index.jsonl
```

Do not infer the destination from folder name alone. Use `.tkn/codex-context.yaml` and the registry record to confirm `projectId`.

## Workflow

1. Check repository instructions and current git state.
2. Inspect `.codex-context/` narrowly:
   - list direct children;
   - count `sessions/*.md` and `decisions/*.md`;
   - read legacy session and decision notes enough to determine the earliest project context date.
3. Determine the projectId date prefix before registration.
   - Read the contents of notes under `.codex-context/sessions/` and `.codex-context/decisions/`; do not rely only on filenames or filesystem timestamps.
   - Prefer Frontmatter dates such as `date`, `created`, `createdAt`, or `updated` when they represent note creation or the recorded decision/session date.
   - If Frontmatter is missing, use a clear date in the note body; use the filename timestamp only as a fallback.
   - Use the oldest reliable date from sessions and decisions as the `projectId` date prefix in `yyyyMMdd` form.
   - Record which note supplied the oldest date in the migration plan.
4. Seed or correct project identity before registration when needed.
   - Check whether `~/.tkn/codex-context/state/index.jsonl` already has a current-root record for this repository.
   - If no local marker exists, create one with the oldest-note date prefix, repository slug, and a short random suffix, then run registration so the registry adopts that `projectId`.
   - If a marker exists but no registry record exists, and its date prefix is newer than the oldest reliable session/decision date, update the marker to preserve the slug and short suffix while replacing only the date prefix.
   - If a registry record already exists for the current root and its `projectId` date prefix is newer than the oldest reliable date, perform an identity rename instead of only editing the marker:
     - preserve the existing slug, short suffix, `workspaceId`, and `repoId`;
     - replace only the date prefix in `projectId`;
     - move the private project context folder to the new projectId name;
     - update registry `projectId`, `projectContextPath`, `workingContextPath`, `sessionsPath`, `decisionsPath`, and `memosPath`;
     - update `.tkn/codex-context.yaml` and destination `working-context.md` Frontmatter.
   - Set marker `createdAt` to the oldest reliable note timestamp and `updatedAt` to the current timestamp.
   - Preserve existing `title` and `description` when present.
5. Use `init-project-context`.
   - Run dry-run.
   - If the user explicitly asked to migrate or move context, run write.
   - Confirm `.tkn/codex-context.yaml` exists after initialization.
6. Resolve `projectId` from `.tkn/codex-context.yaml`.
7. Read `~/.tkn/codex-context/state/index.jsonl` and find the matching record.
   - Prefer a record with the same `projectId` and current root.
   - Use `projectContextPath`, `workingContextPath`, `sessionsPath`, and `decisionsPath` from the record when present.
   - Stop if the matching record is missing or points outside `~/.tkn/codex-context/state/<projectId>/`.
8. Prepare a migration plan:
   - source paths;
   - destination paths;
   - files to move;
   - files that already exist at destination;
   - oldest reliable note date and the resulting `projectId`;
   - source cleanup to perform after verification.
9. Copy or move content only after the plan is clear.
   - Prefer copy to destination, verify counts/content, then remove legacy source files.
   - For explicit "move" requests, cleanup is allowed after verification.
   - Keep `.tkn/codex-context.yaml`.
10. Update project `working-context.md` or create a session note if the migration changes durable project state.

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
- Use their content during planning to set the project identity date:
  - sessions and decisions are the authoritative evidence for when the project context began;
  - choose the oldest reliable note timestamp across both folders;
  - keep that date as the date prefix of `projectId`.
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
- Keep `.tkn/codex-context.yaml`.
- Do not delete a legacy `.codex-context/project.yaml`; report it as a preserved migration source.
- Keep `.codex-context/` if it contains the legacy marker or any unresolved files.
- Report marker-related ignore rules; do not change `.gitignore` unless the user asks.

## Safety

- Do not write to the real `~/.tkn/codex-context` unless the user explicitly asked to migrate, move, initialize, or update project context.
- On Windows, use PowerShell end-to-end for filesystem moves and deletes.
- Before deleting or moving recursively, resolve absolute source and destination paths and verify:
  - source is inside the current repository;
  - destination is inside `~/.tkn/codex-context/state/<projectId>/`.
- Do not use broad cleanup commands against computed paths.
- Do not commit or expose private absolute paths in public repository files.

## Validation

Before finishing, verify:

- `.tkn/codex-context.yaml` exists and contains the expected `projectId`.
- the `projectId` date prefix matches the oldest reliable date found in legacy `sessions/` and `decisions/` note content.
- `.tkn/codex-context.yaml` `createdAt` reflects that oldest reliable note timestamp when a new marker was created or corrected during migration.
- `~/.tkn/codex-context/state/index.jsonl` has the matching registry record.
- destination `working-context.md`, `sessions/`, and `decisions/` exist as expected.
- migrated session and decision file counts match the plan.
- no legacy `working-context.md`, migrated `sessions/*.md`, or migrated `decisions/*.md` remain locally.
- `.tkn/codex-context.yaml` remains local, and any legacy marker remains untouched.
- git status is reviewed, including ignored `.codex-context/` when relevant.
