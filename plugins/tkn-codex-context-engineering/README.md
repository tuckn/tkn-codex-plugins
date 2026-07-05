# Tuckn Codex Context Engineering

[English](README.md) | [日本語](README_ja.md)

This plugin helps Codex pick up project work where it left off. It keeps lightweight notes about a
repository, active work, and important decisions, then uses those notes to make future chats easier
to resume.

When you ask it to, it can also look back through older Codex chat logs and reuse selected private
notes stored in `~/.codex-context`.

## Plugin Files

Plugin path:

```text
plugins/tkn-codex-context-engineering/
```

Plugin manifest:

```text
plugins/tkn-codex-context-engineering/.codex-plugin/plugin.json
```

Bundled Skills:

```text
plugins/tkn-codex-context-engineering/skills/
```

Context bridge scripts:

```text
plugins/tkn-codex-context-engineering/scripts/context_bridge/
```

## Included Skills

Included Skills are grouped by the role they play in the context lifecycle.

### Project Setup And Live Context

- `register-project-context`: Registers or refreshes a repository's Codex project
  identity with a small local `.codex-context/project.yaml` marker and the
  private user-global project registry.
- `migrate-local-project-context`: Moves legacy repo-local `.codex-context`
  working context, sessions, and decisions into the private project context folder.
- `use-project-working-root`: Chooses whether Python/Node runtime files belong in
  the project folder or in the private `.codex-working` project root, then records
  a short project `AGENTS.md` reminder when the private root is used.
- `maintain-working-context`: Maintains `~/.codex-context/projects/<projectId>/working-context.md`
  as a lightweight dashboard for active project context.

### Active Work Records And Resume Flow

- `maintain-session-note`: Creates or updates concise project `sessions/` notes
  for non-trivial work, handoffs, and resumable tasks.
- `resume-session`: Continues an existing session note in a new chat instead of
  creating a duplicate session record.

### Durable Decisions And Review

- `record-decision`: Writes durable decision records under project `decisions/`
  for choices that should outlive the current chat.
- `review-decisions`: Reviews decision records for repository document updates,
  working-context changes, and global-context promotion candidates.

### Past-Session Recovery And Distillation

- `extract-codex-sessions`: Extracts themes, questions, decisions, outcomes, or
  project history from local Codex JSONL session logs.
- `review-codex-chats`: Reviews local Codex session logs from `~/.codex/sessions`
  into monthly source review notes under `~/.codex-context/session-reviews`.
- `distill-session-context`: Distills session notes into short reusable-context review
  candidates and finalizes their distillation metadata after review.

### Global Context Import And Promotion

- `import-global-context`: Loads selected user-global Codex context into the current
  task, preferably read-only, with snapshots only on explicit request.
- `promote-global-context`: Promotes reusable lessons from project context into
  the private user-global context store.

### Context Governance And Raw Idea Capture

- `audit-context-freshness`: Audits repo-local or global context for stale metadata,
  pending distillation or promotion work, and reuse risks.
- `organize-brain-dump`: Turns rough notes, idea dumps, or loose consultation
  material into structured Markdown advice under project `memos/` by default,
  while respecting explicit chat or repository destination instructions.

## Local And Global Context

The plugin keeps a small repo-local project marker, while private project context lives in the
user-global store.

- The local marker is `.codex-context/project.yaml`; it contains `projectId`,
  `title`, `description`, `createdAt`, and `updatedAt`.
- Project context lives under `~/.codex-context/projects/<projectId>/`.
- User-global context lives under `~/.codex-context`.
- Global context loading should be read-only by default.
- Snapshot imports and global promotions should happen only when explicitly requested.

## Activation Model

Project registration is a readiness gate, not an automatic trigger.

- A Skill should run because the user intent matches that Skill.
- For project-scoped context reads or writes, the current repository must also be intentionally
  registered: `.codex-context/project.yaml` exists and its `projectId` resolves in
  `~/.codex-context/projects/index.jsonl` for the current workspace.
- Creating `.codex-context/project.yaml` does not by itself start session notes, decisions,
  working-context updates, distillation, review, import, promotion, or audits.
- If a project-scoped Skill is requested before registration, guide the user to
  `register-project-context`; only invoke registration when the user explicitly asks to register,
  migrate, move, or update project context.
- Entry Skills such as `register-project-context` and `migrate-local-project-context` may run before
  registration because their purpose is to create or repair that readiness gate.
- Runtime setup Skills such as `use-project-working-root` may use the project folder itself only
  when it is clearly a software Git repository outside sync folders with existing environment
  definitions and ignore rules. Otherwise they require registration and use the private
  `.codex-working` project root.
