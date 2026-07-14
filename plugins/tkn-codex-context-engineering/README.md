# Tuckn Codex Context Engineering

[English](README.md) | [日本語](README_ja.md)

This plugin helps Codex pick up project work where it left off. It keeps lightweight notes about a
repository, active work, and important decisions, then uses those notes to make future chats easier
to resume.

When you ask it to, it can also look back through older Codex chat logs and project notes stored in
`~/.tkn/codex-context`.

## Local And Global Context

The plugin keeps a small repo-local project marker, while private project context lives in the
user-global store.

- The local marker is `.tkn/codex-context.yaml`; it contains `projectId`,
  `title`, `description`, `createdAt`, and `updatedAt`.
- Project context lives under `~/.tkn/codex-context/state/<projectId>/`.
- User-global artifacts live under `~/.tkn/codex-context/data/`.
- Project registry and state live under `~/.tkn/codex-context/state/`.
- Store configuration is `~/.tkn/codex-context/config/config.yaml`.
- The store root keeps an updated `README.md` describing the current layout.
- Global context writes are not exposed as bundled Skills.

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

- `init-project-context`:
  - Initializes or refreshes a repository's Codex project identity with a small local
    `.tkn/codex-context.yaml` marker and the private user-global project registry.
- `write-current-working-context`:
  - Creates or updates `~/.tkn/codex-context/state/<projectId>/working-context.md` as a lightweight
    dashboard of the project's current state.

### Active Work Records And Resume Flow

- `write-session-note`:
  - Creates or updates concise project `sessions/` notes for non-trivial work, handoffs, and
    resumable tasks.
- `resume-session`:
  - Continues an existing session note in a new chat instead of creating a duplicate session
    record.

### Durable Decisions And Review

- `record-decision`:
  - Writes durable decision records under project `decisions/` for choices that should outlive the
    current chat.
- `review-decisions`:
  - Reviews decision records for repository document updates, working-context changes, and
    reusable guidance candidates.

### All-Project Chat History Search, Review, And Distillation

- `search-all-codex-chats`:
  - Searches Codex JSONL chat history across all projects on the current computer and uses matched
    evidence to answer questions about past discussions, decisions, and outcomes.
- `review-all-codex-chats`:
  - Reviews Codex chat history across all projects on the current computer from `~/.codex/sessions`
    into monthly source review notes under `~/.tkn/codex-context/data/session-reviews`.
- `distill-session-context`:
  - Distills session notes into short reusable-context review candidates and finalizes their
    distillation metadata after review.

### Context Governance And Raw Idea Capture

- `audit-context-freshness`:
  - Audits repo-local or global context for stale metadata, pending distillation or promotion work,
    and reuse risks.
- `organize-brain-dump`:
  - Turns rough notes, idea dumps, or loose consultation material into structured Markdown advice
    under project `memos/` by default, while respecting explicit chat or repository destination
    instructions.

## Activation Model

Project initialization is a readiness gate, not an automatic trigger.

- A Skill should run because the user intent matches that Skill.
- For project-scoped context reads or writes, the current repository must also be intentionally
  registered: `.tkn/codex-context.yaml` exists and its `projectId` resolves in
  `~/.tkn/codex-context/state/index.jsonl` for the current workspace.
- Creating `.tkn/codex-context.yaml` does not by itself start session notes, decisions,
  working-context updates, distillation, review, or audits.
- If a project-scoped Skill is requested before registration, guide the user to
  `init-project-context`; only invoke initialization when the user explicitly asks to initialize,
  move, or update project context.
- `init-project-context` may run before registration because its purpose is to create or repair
  that readiness gate.
- Runtime and working-folder policy is intentionally not bundled as a Skill. Specify it in each
  project folder when needed.
