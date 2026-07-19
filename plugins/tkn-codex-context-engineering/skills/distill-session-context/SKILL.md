---
name: distill-session-context
description: Distill a Codex Project session note from a projectId-specific sessions folder under `~/.tkn/codex-context/state/` or a user-specified explicit session note into a short review candidate for reusable context and finalize the source session's distillation metadata after review. Use when the user asks to distill, summarize, extract reusable learning, review or close pending distillationStatus, update distilledTo, or create decision/working-context/Skill/AGENTS candidates. Current-project resolution requires `.tkn/codex-context.yaml` to resolve in the private registry; marker creation alone is not a trigger.
---

# Distill Session Context

Use this skill to turn one session note into a reviewable context candidate, then close the source session metadata after the reviewed learning has an accepted destination.

Default to candidate generation. Do not mark the source session as distilled, update working context, create decision records, or edit AGENTS.md/Skills unless the user explicitly asks for that follow-up.

## Activation Gate

This skill runs only when the user asks to distill, summarize, review, or finalize a session note.

If the user provides an explicit session note path, use that file as the source after verifying it exists and is safe to read. If the source must be resolved from the current project, the repository must be intentionally registered: `.tkn/codex-context.yaml` exists and its `projectId` resolves through `~/.tkn/codex-context/state/index.jsonl` for the current workspace.

The marker file alone does not trigger distillation or finalization. If project registration is missing, ask for an explicit session path or guide the user to `init-project-context`; only invoke registration when the user explicitly asks to register or update project context.

## Workflow

1. Identify the source session note.
   - Prefer a user-specified `~/.tkn/codex-context/state/<projectId>/sessions/*.md` file.
   - If none is specified, inspect project `working-context.md` or ask for the intended session note when multiple candidates are plausible.
2. Optionally run `audit-context-freshness` first when the session is old or `distillationStatus` is pending/partial.
3. Treat a missing `schemaVersion` as legacy v1. Support v1 and v2, and refuse any other version. Metadata-only finalization keeps the source body schema unchanged and adds `schemaVersion: 1` only when a legacy source omitted it.
4. Run a dry-run distillation to confirm the output path and extracted sections.
5. Use `--write` only when a durable candidate file is useful.
6. Review the generated candidate before promoting anything.
7. After accepted content exists somewhere durable, finalize the source session metadata.

For v2, deterministic extraction follows the stable parent sections `Decision Candidates`,
`Reusable Learnings`, `Open Loops`, `Handoff`, `Outcome`, `Current State`, `User Confirmations`,
and `Evidence`, including their nested candidate IDs and fields. The default extraction bound is
40 non-empty lines per selected section. Semantic generalization still requires Codex review.

## Commands

Dry-run distillation:

```bash
python -B <skill-root>/scripts/distill_session_context.py \
  --session ~/.tkn/codex-context/state/<projectId>/sessions/<session-note>.md \
  --dest <project-working-root>/codex-context/distilled-session-candidates \
  --dry-run
```

Write a candidate to the destination specified by the current project folder instructions:

```bash
python -B <skill-root>/scripts/distill_session_context.py \
  --session ~/.tkn/codex-context/state/<projectId>/sessions/<session-note>.md \
  --dest <project-working-root>/codex-context/distilled-session-candidates \
  --write
```

Classify the candidate when the likely destination is already clear:

```bash
python -B <skill-root>/scripts/distill_session_context.py \
  --session ~/.tkn/codex-context/state/<projectId>/sessions/<session-note>.md \
  --dest <project-working-root>/codex-context/distilled-session-candidates \
  --kind decision-candidate \
  --write
```

Supported `--kind` values:

- `candidate`
- `decision-candidate`
- `working-context-update`
- `skill-candidate`
- `agents-candidate`

## Finalization Commands

Finalize after reusable context was accepted into a durable destination:

```bash
python -B <skill-root>/scripts/finalize_session_distillation.py \
  --session ~/.tkn/codex-context/state/<projectId>/sessions/<session-note>.md \
  --status distilled \
  --distilled-to ~/.tkn/codex-context/state/<projectId>/decisions/DR-0001-example.md \
  --write
```

Use `partial` when only some useful content was accepted:

```bash
python -B <skill-root>/scripts/finalize_session_distillation.py \
  --session ~/.tkn/codex-context/state/<projectId>/sessions/<session-note>.md \
  --status partial \
  --distilled-to <project-working-root>/codex-context/distilled-session-candidates/<candidate>.md \
  --write
```

Use `no-action` when review found nothing worth carrying forward:

```bash
python -B <skill-root>/scripts/finalize_session_distillation.py \
  --session ~/.tkn/codex-context/state/<projectId>/sessions/<session-note>.md \
  --status no-action \
  --write
```

Finalization updates only source Frontmatter fields: `distillationStatus`, `distilledTo`, and `updated`.

## Promotion Boundary

The generated file is only a review candidate. Promotion is a separate step.

- Use `record-decision` for accepted repository decisions.
- Use `write-current-working-context` for accepted repository current truth.
- Global context writes are outside this bundled Skill set; create a reviewed candidate or decision first.
- Update AGENTS.md or Skills only after checking current repository behavior and public/private path safety.
- Use finalization only after the accepted destination exists or after review decides `no-action`.

## Safety

- Treat session notes as raw or silver context, not current truth.
- Do not copy full chat transcripts or full session notes into candidates.
- Do not distill a session note that contains secrets, credentials, tokens, private keys, full env vars, large logs, or unnecessary personal/customer data.
- Do not put private absolute paths in `--distilled-to`; use project-context paths under `~/.tkn/codex-context/state/<projectId>/...`, project-specific relative refs, or another explicit stable destination.
- Keep candidate output under the destination specified by the current project folder instructions unless the user explicitly requests a repository artifact.
