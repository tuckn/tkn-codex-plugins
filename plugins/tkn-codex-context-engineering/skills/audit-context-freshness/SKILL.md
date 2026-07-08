---
name: audit-context-freshness
description: Audit repo-local, current-project, or user-global Codex context for stale, pending, missing, or risky freshness metadata. Use when the user asks to review context freshness, stale context, outdated decisions, pending distillation, pending promotion, or whether context should be revalidated before reuse. Current-project audits require `.codex-context/project.yaml` to resolve in the private registry; marker creation alone is not a trigger.
---

# Audit Context Freshness

Use this skill to inspect whether Codex context is still fresh enough to reuse.

Default to read-only audit. Do not update context files, global context, AGENTS.md, or Skills unless the user explicitly asks for the follow-up changes after seeing the audit.

## Activation Gate

This skill runs only when the user asks for a freshness, stale-context, pending-review, or reuse-risk audit.

For current-project audits, the repository must be intentionally registered: `.codex-context/project.yaml` exists and its `projectId` resolves through `~/.codex-context/projects/index.jsonl` for the current workspace.

The marker file alone does not trigger an audit. Legacy repo-local `.codex-context` audits and explicit user-global `~/.codex-context` audits may run without a current project registration, but they remain read-only by default.

## Workflow

1. Confirm the target context source.
   - Repo-local default: `.codex-context`
   - User-global context: `~/.codex-context`
2. Run a dry-run freshness audit first.
3. Review the reported stale, missing, pending, or risky items.
4. Revalidate important stale context against current files, current user instructions, repository instructions, and git state before relying on it.
5. Write a report only when useful for handoff or review history.

## Commands

Audit the current repository context without writing files:

```bash
python <plugin-root>/scripts/context_bridge/audit_context_freshness.py \
  --source .codex-context \
  --dry-run
```

Audit user-global context without writing files:

```bash
python <plugin-root>/scripts/context_bridge/audit_context_freshness.py \
  --source ~/.codex-context \
  --scope global \
  --dry-run
```

Write a review report to the private Codex working root for the current registered project:

```bash
python <plugin-root>/scripts/context_bridge/audit_context_freshness.py \
  --source .codex-context \
  --write
```

The default report destination is `%USERPROFILE%\.codex-working\projects\<projectId>\context-bridge\freshness-reviews\`.

Use a global report destination only when the user explicitly asks to preserve the audit in the private global store:

```bash
python <plugin-root>/scripts/context_bridge/audit_context_freshness.py \
  --source ~/.codex-context \
  --scope global \
  --report-dest ~/.codex-context/reviews \
  --write
```

## Interpretation

- `stale>Nd`: the file's `updated`, `lastSeenAt`, or `date` metadata is older than the threshold.
- `missing-frontmatter` or `missing-updated`: freshness cannot be evaluated reliably.
- `distillation=pending` or `distillation=partial`: a session note still needs review before its reusable learning is treated as durable.
- `promotion=pending` or `promotion=partial`: a local context artifact may still need promotion review.
- `secret-like-content`: stop and inspect carefully; do not copy or promote that context.

## Safety

- Treat the audit as a signal, not a correctness verdict.
- Current user instructions, current repository instructions, current files, and git state take precedence over older context.
- Do not paste full context files into chat just to audit freshness.
- Keep generated audit reports under the private Codex working root unless the user explicitly requests a durable private global or repository report.
