---
name: distill-session-context
description: Distill a Codex Project session note from `~/.codex-context/projects/<projectId>/sessions` or a user-specified explicit session note into a short review candidate for reusable context and finalize the source session's distillation metadata after review. Use when the user asks to distill, summarize, extract reusable learning, review or close pending distillationStatus, update distilledTo, or create decision/working-context/Skill/AGENTS candidates. Current-project resolution requires `.codex-context/project.yaml` to resolve in the private registry; marker creation alone is not a trigger.
---

# Distill Session Context

Use this skill to turn one session note into a reviewable context candidate, then close the source session metadata after the reviewed learning has an accepted destination.

Default to candidate generation. Do not mark the source session as distilled, update working context, create decision records, promote global context, or edit AGENTS.md/Skills unless the user explicitly asks for that follow-up.

## Activation Gate

This skill runs only when the user asks to distill, summarize, review, or finalize a session note.

If the user provides an explicit session note path, use that file as the source after verifying it exists and is safe to read. If the source must be resolved from the current project, the repository must be intentionally registered: `.codex-context/project.yaml` exists and its `projectId` resolves through `~/.codex-context/projects/index.jsonl` for the current workspace.

The marker file alone does not trigger distillation or finalization. If project registration is missing, ask for an explicit session path or guide the user to `register-project-context`; only invoke registration when the user explicitly asks to register or update project context.

## Workflow

1. Identify the source session note.
   - Prefer a user-specified `~/.codex-context/projects/<projectId>/sessions/*.md` file.
   - If none is specified, inspect project `working-context.md` or ask for the intended session note when multiple candidates are plausible.
2. Optionally run `audit-context-freshness` first when the session is old or `distillationStatus` is pending/partial.
3. Run a dry-run distillation to confirm the output path and extracted sections.
4. Use `--write` only when a durable candidate file is useful.
5. Review the generated candidate before promoting anything.
6. After accepted content exists somewhere durable, finalize the source session metadata.

## Commands

Dry-run distillation:

```bash
python <plugin-root>/scripts/context_bridge/distill_session_context.py \
  --session ~/.codex-context/projects/<projectId>/sessions/<session-note>.md \
  --dry-run
```

Write a candidate under ignored local work files:

```bash
python <plugin-root>/scripts/context_bridge/distill_session_context.py \
  --session ~/.codex-context/projects/<projectId>/sessions/<session-note>.md \
  --write
```

The default destination is `.local/codex-context/distilled-session-candidates/`.

Classify the candidate when the likely destination is already clear:

```bash
python <plugin-root>/scripts/context_bridge/distill_session_context.py \
  --session ~/.codex-context/projects/<projectId>/sessions/<session-note>.md \
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
python <plugin-root>/scripts/context_bridge/finalize_session_distillation.py \
  --session ~/.codex-context/projects/<projectId>/sessions/<session-note>.md \
  --status distilled \
  --distilled-to ~/.codex-context/projects/<projectId>/decisions/DR-0001-example.md \
  --write
```

Use `partial` when only some useful content was accepted:

```bash
python <plugin-root>/scripts/context_bridge/finalize_session_distillation.py \
  --session ~/.codex-context/projects/<projectId>/sessions/<session-note>.md \
  --status partial \
  --distilled-to .local/codex-context/distilled-session-candidates/<candidate>.md \
  --write
```

Use `no-action` when review found nothing worth carrying forward:

```bash
python <plugin-root>/scripts/context_bridge/finalize_session_distillation.py \
  --session ~/.codex-context/projects/<projectId>/sessions/<session-note>.md \
  --status no-action \
  --write
```

Finalization updates only source Frontmatter fields: `distillationStatus`, `distilledTo`, and `updated`.

## Promotion Boundary

The generated file is only a review candidate. Promotion is a separate step.

- Use `record-decision` for accepted repository decisions.
- Use `maintain-working-context` for accepted repository current truth.
- Use `promote-global-context` for explicit global writes.
- Update AGENTS.md or Skills only after checking current repository behavior and public/private path safety.
- Use finalization only after the accepted destination exists or after review decides `no-action`.

## Safety

- Treat session notes as raw or silver context, not current truth.
- Do not copy full chat transcripts or full session notes into candidates.
- Do not distill a session note that contains secrets, credentials, tokens, private keys, full env vars, large logs, or unnecessary personal/customer data.
- Do not put private absolute paths in `--distilled-to`; use `.local/...`, project-context paths under `~/.codex-context/projects/<projectId>/...`, or other explicit `~/.codex-context/...` destinations.
- Keep candidate output in `.local/` unless the user explicitly requests a repository artifact.
