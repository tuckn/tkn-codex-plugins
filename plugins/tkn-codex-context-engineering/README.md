# Tuckn Codex Context Engineering

English | [日本語](README_ja.md)

This plugin helps Codex pick up project work where it left off. It keeps lightweight notes about a
repository, active work, and important decisions, then uses those notes to make future chats easier
to resume.

When explicitly requested, it can also search older Codex chat logs and project notes stored under
`~/.tkn/codex-context`.

## Design Philosophy

The purpose of this plugin is not to preserve chat transcripts for their own sake. Its purpose is to
progressively distill temporary Codex conversations into resumable project context, durable
project decisions, concise current-state dashboards, and reusable knowledge that can cross project
boundaries.

Context has different lifetimes, scopes, confidence levels, and uses, so the plugin does not place
all context in one large file. Instead, context matures through the following pipeline:

```text
Codex chat transcript
  -> project session note
  -> project decision / project working context
  -> registered-project portfolio / user-global decision
  -> insight, Skill, automation, monthly review, durable note
```

This lifecycle treats raw chats as source evidence rather than current truth. Each layer compresses,
validates, and selects the material required by the next layer.

The project-scoped stages through project decisions and project working context are implemented by
the bundled Skills. Monthly all-project chat review and reusable-context candidate generation are
also implemented. Registered-project portfolio aggregation is implemented by
`write-global-working-context`. Final writes to user-global decisions remain an intended downstream
stage and are not currently exposed as a bundled write Skill.

### Three Usage Loops

The lifecycle is used through three related loops. They share artifacts but have different
purposes and activation boundaries.

#### Daily Project Work

Use this loop for normal work in one registered Codex Project.

```text
init-project-context (once)
  -> read-current-working-context or resume-session
  -> perform the work
  -> write-session-note for non-trivial or resumable work
  -> record-decision when a judgement must outlive the chat
  -> write-current-working-context when project current truth changed
```

Reading and writing are intentionally separate. A new chat can orient itself without changing
timestamps or context files. Trivial work does not require a session note, and routine work does
not create a decision or update the dashboard unless the corresponding durable state actually
changed.

#### Missed-Context Recovery

Use this loop when project context may be incomplete because earlier chats were not recorded or a
manual update was missed.

```text
current-project Codex JSONL chats
  -> refresh-project-context-from-chats
  -> reconcile one session note per thread
  -> create or update durable project decisions
  -> update the project working context once
```

This loop is limited to the current registered project. It uses chat logs as read-only evidence,
processes only new or changed source fingerprints after the first run, and does not sweep every
project in the registry.

Before rebuilding every registered project from Windows, WSL, or archived sessions, use
`plan-context-rebuild-from-chats`. It inventories existing artifacts and produces a read-only
assignment plan. Historical roots suggested only by repository URL remain review candidates until
explicitly approved.

#### Cross-Project Review And Materialization

Use this loop to understand work across registered projects and identify reusable knowledge.

```text
fresh project working contexts
  -> write-global-working-context
  -> registered-project portfolio

reviewed project decisions + monthly chat reviews
  -> audit and cross-project review
  -> global-decision, Skill, or automation candidates
  -> human review and approval
  -> external or future materialization
```

Project dashboards provide current portfolio inputs; monthly chat reviews provide historical
insight. Portfolio aggregation and candidate review are implemented, while final user-global
decision writes remain outside the current bundled write surface.

### Source-Of-Truth Precedence

When sources disagree, use the following order. A lower-priority source must not silently override
a higher-priority source.

1. **Current explicit user instruction:** the user's latest approval, correction, rejection, or
   constraint.
2. **Current primary evidence for the question:**
   - for observed implementation state, current repository files, Git state, tests, and runtime
     evidence;
   - for intended policy, an accepted decision and current durable repository guidance.
3. **Fresh project working context:** a concise orientation dashboard and index into relevant
   evidence, not an authority over current files or accepted decisions.
4. **Relevant project records:** decision records, session notes, and reviewed candidates that
   provide rationale, history, or handoff detail.
5. **Raw Codex chats and assistant proposals:** source evidence only; they are not current truth or
   user-approved decisions by themselves.

If accepted intent and observed implementation differ, preserve both facts explicitly, such as
"accepted but not yet implemented", instead of choosing one and hiding the mismatch. Stale or
unverifiable context must be revalidated before it is propagated to project or cross-project
artifacts.

### 1. Register The Project

Use `init-project-context` first to create a stable identity between a Codex Project folder and the
private context store.

- The repository keeps only a small `.tkn/codex-context.yaml` marker.
- Private context lives under `~/.tkn/codex-context/state/<projectId>/`.
- Folder renames, moves, and alternate checkouts should preserve the same logical project identity
  whenever the evidence is unambiguous.

Initialization is a readiness gate. It does not automatically create session notes, decisions,
working-context updates, reviews, or global context.

### 2. Convert A Chat Into A Session Note

`write-session-note` converts non-trivial work performed in one Codex chat or thread into a
project-scoped record that can be resumed and reviewed later.

A session note is a source-near factual digest. It is shorter than the chat, while preserving the
facts needed to understand what was requested, what changed, and where the work stopped.

It primarily records:

- user requests, clarifications, and corrections;
- actions actually performed and results actually reported;
- explicit decisions and validation results;
- the last known work state and latest user direction;
- material evidence and source limitations when needed.

A session note remains source-near context. By itself, it is not project current truth or a durable
rule.

### 3. Promote Durable Judgement Into A Decision

`record-decision` promotes a judgement from a session into a durable decision record when future
humans or Codex sessions should continue to reuse it after the current chat.

Decisions are not limited to architecture. They can cover project scope, product direction,
solution design, workflow, operations, documentation, repository conventions, collaboration
processes, and important rejected alternatives.

A decision record should make clear:

- the problem or trade-off being resolved;
- the selected decision and its rationale;
- consequences and operational implications;
- alternatives rejected and the evidence for rejecting them;
- whether the scope is `project`, `user`, `global`, or `mixed`;
- whether repository documentation, working context, global context, or a Skill must be updated.

### 4. Maintain Project Current Truth

`write-current-working-context` uses session notes, decisions, current repository files, and Git
state to maintain a concise dashboard of what is currently true for the Codex Project.

`working-context.md` is an orientation layer, not a detailed history. A new chat should be able to
understand the following without reading every session note and decision:

- the project purpose and current outcome;
- active workstreams;
- confirmed current truth;
- important constraints and risks;
- recently effective decisions;
- key files to read when resuming;
- the next maintenance action or exact resumption point.

A session note answers, “What happened in this chat?” Working context answers, “What is true now?”
When information becomes stale, working context replaces or removes it instead of preserving it as
a chronological append-only log.

### 5. Integrate The Current State Of Registered Codex Projects

`write-global-working-context` uses each registered project's `working-context.md` as the source
input for a portfolio dashboard at an explicitly configured private destination, for example:

```text
<portfolio-context-root>/state/working-context.md
```

The Skill resolves projects from the private registry and requires an explicit destination for
writes instead of embedding a machine- or user-specific path. It reads project working contexts
only; it does not read raw chats, session notes, or decision bodies.

The resulting user-global working context should not summarize raw chat transcripts or every
session note directly. It should aggregate already-distilled project current truth to provide a
portfolio-level view of project relationships, priorities, blockers, and next work.

Expected contents include:

- active, paused, blocked, and archived projects;
- each project's purpose, status, current focus, and next step;
- declared dependencies across projects;
- stale project context that requires review or maintenance.

Duplicated work and shared cross-project patterns require semantic review and remain candidates for
the review/materialization stage rather than being inferred by this deterministic writer.

### 6. Generate Cross-Project Knowledge And Insight

The intended design also reviews context across projects and promotes material that remains useful
after project-specific details are removed.

The bundled Skills can identify and review global decision candidates, but final materialization
into user-global decisions remains outside the current bundled write surface. An external or future
workflow should use an explicitly configured private destination, for example:

```text
<portfolio-context-root>/data/decisions/
```

Candidates include:

- working conventions reusable across projects;
- collaboration rules for working with Codex;
- durable user preferences;
- principles for context engineering, documentation, and repository management;
- negative knowledge that prevents repeated failures;
- repeated workflows that should become a Skill, script, template, or automation.

Codex chat transcripts can also be reviewed by month while separating Fact Extract, Insight
Synthesis, and Materialization Candidates. This supports questions such as:

- What work and consultations occurred during the previous month?
- Which questions, frictions, or manual operations repeated?
- Which workflows should become Skills or automations?
- Which decisions, preferences, or reference notes should outlive a project?
- Which open loops or maintenance debts remain unresolved?

Monthly chat review is a source for historical insight. The current state of all projects should
instead be derived from each project's `working-context.md`; the two responsibilities must not be
mixed.

## Context Layers And Responsibilities

| Layer | Primary artifact | Primary question | Update behavior | Current support |
|---|---|---|---|---|
| Source | Codex JSONL chat | What was actually discussed? | append-only / read-only | implemented |
| Session | `sessions/*.md` | What happened, and how can this work resume? | updated per thread | implemented |
| Project decision | `decisions/DR-*.md` | Which judgement must remain durable? | durable, status-managed | implemented |
| Project current state | `working-context.md` | What is true in this project now? | stale content replaced | implemented |
| Global current state | user-global `state/working-context.md` | What is the current state across registered projects? | aggregated from project dashboards | implemented |
| Global knowledge | user-global `data/decisions/` and related artifacts | What should be reused across projects? | reviewed promotion | candidate review implemented; final write external |
| Insight / materialization | monthly reviews, Skill candidates, and related notes | What should be improved, automated, or systematized? | periodic review | monthly source review implemented; materialization requires follow-up |

This separation preserves detailed evidence while allowing everyday work to read only small,
trustworthy context artifacts.

## Context Quality Principles

Every artifact should remain understandable to humans and predictable enough for AI-assisted
extraction and comparison.

- **Separate current truth from history:** do not bury current state in chronological logs.
- **Separate facts, decisions, inferences, and candidates:** assistant proposals are not user-approved facts.
- **Preserve evidence and provenance:** important decisions and insights should be traceable to source sessions, files, or validation.
- **One artifact, one responsibility:** do not merge the roles of sessions, decisions, working context, and reviews.
- **Use explicit promotion:** track whether context was propagated and where it was materialized.
- **Preserve negative knowledge:** record meaningful failures and the conditions required before retrying them.
- **Apply progressive compression:** downstream context should become shorter, more general, and more stable.
- **Keep a human review boundary:** global context, Skills, and automations require review and approval before materialization.
- **Default to privacy:** do not place private paths, customer data, or secrets in public repository files.
- **Prefer current evidence:** current user instructions, repository files, and Git state override historical context.

### Artifact Schema Versioning

New project session notes, decision records, and working contexts use `schemaVersion: 2`.
Session v2 is a source-near factual digest, decision v2 is a reusable unit of judgement, and
working-context v2 is a project control plane with portfolio metadata. Readers may retain support
for earlier artifacts, while writer Skills define only the current output contract. Unsupported
versions are rejected rather than guessed.

| Artifact | v2 role | Stable extraction signals |
|---|---|---|
| Session note | Source-near factual digest | summary, key developments, last known state, evidence, source notes |
| Decision record | Reusable unit of judgement | rationale, applicability, `implementationStatus`, verification, materialization, supersession |
| Working context | Project control plane | lifecycle, health, priority, focus, blocker, next action, activity/review dates, dependencies |

The canonical current field, section, and enum contracts live in the corresponding writer Skills.

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
- Portfolio working-context writes require an explicit private destination.
- Final user-global decision writes are not exposed as a bundled Skill.

### Working-context path references

In a schema v2 project `working-context.md`, file and directory references under
`Effective Decisions` and `Key Files And Evidence` use logical roots:

- `project:/<path>` resolves from the registered Codex Project folder.
- `state:/<path>` resolves from `~/.tkn/codex-context/state/<projectId>/`.

These references are written in backticks with `/` separators. They are logical references for
Codex, not filesystem URIs or Markdown link targets. New entries do not use unqualified relative
paths or `..` to escape a logical root.

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

Skill-specific scripts:

```text
plugins/tkn-codex-context-engineering/skills/<skill-name>/scripts/
```

Shared Python package and CLI implementation:

```text
plugins/tkn-codex-context-engineering/lib/tkn_codex_context/
```

Bundled Python entry points disable bytecode-cache writes. The plugin does not place
`__pycache__` under the repository or redirect Python bytecode into the user cache; a future
`~/.cache/net.tuckn/codex-context` area is reserved for rebuildable application data when needed.

## Automated Session Notes

The plugin's Python package also provides a CLI that generates session notes for every registered
active project without reopening the source chats. Marketplace installation does not add this CLI
to `PATH`, so install the same source separately:

```powershell
uv tool install ./plugins/tkn-codex-context-engineering
tkn-codex-context session-notes configure
tkn-codex-context session-notes run --dry-run
```

The daily run processes chats created or updated after the installation watermark and idle for at
least 30 minutes. There is no item-count cap. It stops starting new threads after 3 hours and 50
minutes and leaves the rest for the next run. Successfully generated notes are written directly to
the project's `sessions/` folder with `reviewStatus: unreviewed`; there is no review queue, and the
pipeline does not update decisions or working context.

Older chats are processed only through explicit backfill:

```powershell
tkn-codex-context session-notes backfill --project-id <projectId> --limit 1 --dry-run
tkn-codex-context session-notes backfill --project-id <projectId> --limit 1
```

On Windows, use the bundled script to inspect, preview, install, or remove the daily 03:00 Task
Scheduler task. It runs only while the user is logged on and does not wake the computer.

```powershell
pwsh -File ./plugins/tkn-codex-context-engineering/scripts/windows_task_scheduler.ps1 -Action Status
pwsh -File ./plugins/tkn-codex-context-engineering/scripts/windows_task_scheduler.ps1 -Action Install -WhatIf
pwsh -File ./plugins/tkn-codex-context-engineering/scripts/windows_task_scheduler.ps1 -Action Install
pwsh -File ./plugins/tkn-codex-context-engineering/scripts/windows_task_scheduler.ps1 -Action Remove
```

## Included Skills

Included Skills are grouped by the role they play in the context lifecycle.

### Project Setup And Live Context

- `init-project-context`:
  - Initializes or refreshes a repository's Codex project identity with a small local
    `.tkn/codex-context.yaml` marker and the private user-global project registry.
- `read-current-working-context`:
  - Reads the registered current project's `working-context.md` as read-only orientation for a new
    chat, project status check, resume, or handoff.
- `write-current-working-context`:
  - Creates or updates `~/.tkn/codex-context/state/<projectId>/working-context.md` as a lightweight
    dashboard of the project's current state.
- `write-global-working-context`:
  - Aggregates registered project working contexts into a source-linked portfolio dashboard at an
    explicitly selected private destination.

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

- `plan-context-rebuild-from-chats`:
  - Compares all registry projects with multiple named Codex sessions sources, inventories existing
    artifact schema versions, and writes a read-only rebuild plan containing direct assignments,
    root-approval candidates, unresolved sessions, parser gaps, and duplicate thread IDs. After
    review, it can materialize schema-v2 session notes and stale working-context drafts into a new
    shadow tree while keeping decision candidates behind a review gate.
- `search-all-codex-chats`:
  - Searches Codex JSONL chat history across all projects on the current computer and uses matched
    evidence to answer questions about past discussions, decisions, and outcomes.
- `refresh-project-context-from-chats`:
  - Scans Codex chat history for the registered current project, reconciles one session note per
    thread, materializes durable decisions, and updates the working-context dashboard. The first
    run reviews all matched chats; later runs process only new or changed source fingerprints.
    Named Windows, WSL, or archive sources keep separate state and source-qualified references.
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
- Use `read-current-working-context` when a new chat needs project orientation; registration alone
  does not read the dashboard automatically.
- For project-scoped context reads or writes, the current repository must also be intentionally
  registered: `.tkn/codex-context.yaml` exists and its `projectId` resolves in
  `~/.tkn/codex-context/state/index.jsonl` for the current workspace.
- Creating `.tkn/codex-context.yaml` does not by itself start session notes, decisions,
  working-context updates, chat-history refresh, distillation, review, or audits.
- If a project-scoped Skill is requested before registration, guide the user to
  `init-project-context`; only invoke initialization when the user explicitly asks to initialize,
  move, or update project context.
- `init-project-context` may run before registration because its purpose is to create or repair
  that readiness gate.
- Runtime and working-folder policy is intentionally not bundled as a Skill. Specify it in each
  project folder when needed.
