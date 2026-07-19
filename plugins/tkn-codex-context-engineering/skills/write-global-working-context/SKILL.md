---
name: write-global-working-context
description: Aggregate registered Codex Project working-context.md files into an explicitly chosen private portfolio working context. Use when the user asks for an all-project dashboard, global working context, portfolio status, cross-project blockers, dependencies, priorities, stale project context, or exact next actions across registered projects.
---

# Write Global Working Context

Create or refresh a user-global portfolio dashboard from registered project working contexts.

This Skill is a deterministic aggregation stage. It does not infer current state from chat
transcripts, session notes, or decision bodies.

## Activation Gate

Run only when the user explicitly asks to create, refresh, or write an all-project/global working
context or registered-project portfolio.

Do not use this Skill for:

- orienting within one project; use `read-current-working-context`;
- updating one project's dashboard; use `write-current-working-context`;
- historical chat review; use `review-all-codex-chats`;
- promoting reusable decisions; use the dedicated promotion workflow when available.

## Inputs And Destination

- Default source store: `~/.tkn/codex-context`
- Registry: `<source>/state/index.jsonl`
- Project inputs: `<source>/state/<projectId>/working-context.md`
- Output: one private Markdown file selected by the user, current instructions, or an explicit
  `--dest`

Never embed a machine- or user-specific destination in this Skill. For a public example, use a
generic path such as `C:\path\to\portfolio-context\state\working-context.md`.

Writing requires `--dest`. A dry run may omit it.

## Source Contract

1. Enumerate projects only from `state/index.jsonl`.
2. Read only each registered project's `working-context.md`.
3. Treat an unversioned project working context as v1.
4. Read explicit v1 and v2 project working contexts.
5. Reject unsupported schema versions without changing the destination.
6. Use registry metadata only as an identity/title fallback.
7. Never copy registry absolute paths into the portfolio artifact.
8. Preserve provenance with logical `state:/<projectId>/working-context.md` references.

Project working context remains authoritative for project status, health, priority, focus,
blockers, next action, activity/review dates, and dependencies. Do not invent missing values.

## Output Contract

Write `type: globalWorkingContext` with `schemaVersion: 1`.

Frontmatter contains aggregate counts, generation time, and logical source references. The body
contains:

- portfolio summary;
- active, blocked, paused, completed, and archived project groups;
- declared project dependencies;
- stale, legacy, missing, or review-due project context;
- provenance for every listed project.

This file is current portfolio state, not a chronological history. Regenerate it from current
project dashboards rather than appending prior snapshots.

## Workflow

1. Confirm the private source store and output destination from current instructions.
2. Run a dry run first:

   ```powershell
   python -X utf8 -B <skill-root>/scripts/write_global_working_context.py `
     --source ~/.tkn/codex-context `
     --dest C:\path\to\portfolio-context\state\working-context.md `
     --dry-run
   ```

3. Review missing contexts, legacy schemas, stale projects, dependency references, and unsupported
   versions.
4. When the user requested a write, rerun with `--write`.
5. Report the destination, registered/included counts, blocked and stale counts, and review items.

Do not modify the registry or any project artifact.
