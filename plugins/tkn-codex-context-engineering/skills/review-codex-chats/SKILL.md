---
name: review-codex-chats
description: Review local Codex JSONL chat logs from `~/.codex/sessions` and create monthly Codex chat source review notes under `~/.tkn/codex-context/data/session-reviews`. Use when the user asks for a Codex chat review, monthly Codex transcript review, AI collaboration review, or source review of local Codex sessions. This skill summarizes sessions into Fact Extract, Insight Synthesis, and Materialization Candidates without creating decisions, session notes, working-context updates, Skills, or actions.
---

# Review Codex Chats

Use this skill to review Codex chat transcripts as a source record of AI collaboration.

The source root is fixed to `~/.codex/sessions`. Do not use environment files, repository-local source-root config, or alternate archive roots for normal use.

The output root is fixed to `~/.tkn/codex-context/data/session-reviews`.

## Scope

Handle Codex chat source review only.

- If the user specifies a year/month, review that month.
- If the user specifies an ISO week or exact date range, use that period only when the user explicitly asks for a non-monthly review.
- If no period is specified, default to the previous calendar month.
- Do not perform integrated life review, project session-note maintenance, decision recording, working-context updates, Skill creation, action note creation, or materialization follow-up.

## Source And Parser

Use the bundled parser to summarize matching JSONL files before writing the review note.

```powershell
python plugins\tkn-codex-context-engineering\skills\review-codex-chats\scripts\parse_codex_chats.py `
  --month 2026-06 `
  --output "$env:TEMP\review-codex-chats\2026-06-summary.json"
```

Useful options:

- `--month YYYY-MM`: calendar month.
- `--week YYYY-Www`: ISO week.
- `--period-start YYYY-MM-DD --period-end YYYY-MM-DD`: explicit inclusive date range.
- `--sessions-root <path>`: testing override only. Do not use for normal review work.
- `--max-samples N`: maximum user and assistant text samples per session.
- `--sample-chars N`: maximum characters per sample before truncation.

The parser defaults to `~/.codex/sessions`, writes JSON only when `--output` is supplied, and records `sourceRefs` as paths relative to `~/.codex/sessions`. It redacts likely absolute paths from extracted text samples.

Read raw `.jsonl` files only when the summary is insufficient. Keep raw transcript excerpts short.

## Output Location

Write the monthly review note to:

```text
~/.tkn/codex-context/data/session-reviews/YYYY/YYYYMMDDTHHMMSS+0900_codex-chat-review-YYYY-MM.md
```

Use the system clock and timezone offset for the filename timestamp.

Create the destination folder if it does not exist.

## Required Frontmatter

```yaml
---
type: sourceReview
title: "Codex chat review YYYY-MM"
description: "Codex chat transcript review for YYYY-MM."
generator: Codex
reviewStatus: draft
reviewPeriod: YYYY-MM
periodStart: YYYY-MM-DD
periodEnd: YYYY-MM-DD
sourceType: codexSessions
sourceRoot: "~/.codex/sessions"
sourceRefs: []
sourceMaterialPolicy: quoteAllowed
privacyClass: sensitive
analysisLevel: sourceReview
date: YYYY-MM-DDTHH:mm:ss+09:00
updated: YYYY-MM-DDTHH:mm:ss+09:00
noteId: "<UUID>"
---
```

`generator: Codex`, `reviewStatus: draft`, `sourceType: codexSessions`, `sourceRoot: "~/.codex/sessions"`, and `privacyClass: sensitive` are required.

`sourceRefs` must contain only paths relative to `~/.codex/sessions`. Do not write private absolute source paths.

## Workflow

1. Determine the review period.
2. Run `parse_codex_chats.py` and write summary JSON under the OS temp directory.
3. Read the summary JSON.
4. Open only the specific raw `.jsonl` files needed to clarify unclear sessions.
5. Write one review note under `~/.tkn/codex-context/data/session-reviews`.
6. Verify frontmatter, period fields, `sourceRefs`, and heading hierarchy.
7. Reply with the created note path, period, session count, 2-4 major patterns, and a reminder that materialization was not performed.

## Review Structure

```md
# Codex chat review: YYYY-MM

## 1. Fact Extract

### 1.1. Sessions

### 1.2. User Requests

### 1.3. Files / Artifacts

### 1.4. Decisions / Preferences

### 1.5. Tooling / Errors

### 1.6. Open Loops

## 2. Insight Synthesis

### 2.1. Themes

### 2.2. Collaboration Patterns

### 2.3. Skill / Automation Signals

### 2.4. Tensions / Frictions

### 2.5. Opportunities

### 2.6. Repeated Questions

### 2.7. Implications

## 3. Materialization Candidates

### 3.1. Skills

### 3.2. Decisions

### 3.3. Working Context

### 3.4. Actions / Operations / Plans

### 3.5. Reference Notes

### 3.6. Index / MoC

## 4. Needs Confirmation

## 5. Next Steps
```

Keep the three review layers separate:

- `Fact Extract`: facts explicitly visible in the chats.
- `Insight Synthesis`: patterns inferred from those facts.
- `Materialization Candidates`: proposed destinations for future work only.

## Extraction Rules

### Fact Extract

Write only facts directly supported by Codex chats.

Recommended categories:

- `Sessions`: transcript file, session date, broad task, and notable source refs.
- `User Requests`: explicit user requests, corrections, approvals, rejections, preferences, and constraints.
- `Files / Artifacts`: notes, Skills, decisions, scripts, reports, or other artifacts actually created or updated.
- `Decisions / Preferences`: adopted naming, destinations, workflow rules, review policies, and durable preferences.
- `Tooling / Errors`: important tool errors, file issues, validation failures, sandbox limits, permission issues, or repeated operational friction.
- `Open Loops`: unresolved questions, carried-over tasks, and assumptions needing confirmation.

Separate what the user said, what Codex proposed, what was actually changed, and what remained only a candidate.

### Insight Synthesis

Derive patterns from Fact Extract without immediately turning them into tasks.

Recommended categories:

- `Themes`: main work or consultation themes for the period.
- `Collaboration Patterns`: how the user and Codex divided work, corrected each other, or converged.
- `Skill / Automation Signals`: repeated workflows that may deserve reusable Skills, scripts, or operations.
- `Tensions / Frictions`: breakage, rework, excess structure, unclear boundaries, noisy context, or recurring tool problems.
- `Opportunities`: notes, Skills, decisions, operations, or context updates that would reduce future effort.
- `Repeated Questions`: questions or boundaries that appeared more than once.
- `Implications`: things to watch next month or changes that may affect priorities.

Add `confidence: low | medium | high` when an insight depends on sparse evidence.

### Materialization Candidates

List candidates only after Insight Synthesis.

Use destinations that match the private context model:

- `Skills`: reusable procedures or judgment rules.
- `Decisions`: durable decisions that should outlive one chat.
- `Working Context`: current-truth updates for a project or user-global context.
- `Actions / Operations / Plans`: concrete follow-up work, recurring checks, or planning notes.
- `Reference Notes`: self-model, lexicon, domain, or concept notes.
- `Index / MoC`: hubs or maps that would make related material easier to find.

Do not create these materials during this skill. Materialization is a separate user-approved step.

## Safety Rules

- Do not edit source `.jsonl` files.
- Do not use environment files or repository-local source-root config.
- Do not paste full transcripts or large raw excerpts into review notes.
- Do not expose secrets, credentials, tokens, private keys, full environment variables, large logs, or unnecessary personal/customer data.
- Do not write private absolute source paths into committed files or review notes.
- Treat Codex replies as assistant output, not as facts about the user unless the user confirmed them.
- Do not mix Fact Extract, Insight Synthesis, and Materialization Candidates.
- Do not turn low-confidence interpretation into fact.
- Do not create or update project decisions, project session notes, working context, Skills, actions, operations, plans, or reference notes unless the user explicitly asks for that follow-up after the review.
