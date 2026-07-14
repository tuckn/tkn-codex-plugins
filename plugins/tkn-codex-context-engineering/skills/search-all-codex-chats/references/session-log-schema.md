# Codex Session Log Schema

Codex chat logs are newline-delimited JSON files under the Codex home sessions directory.

Common roots:

- Windows default: `%USERPROFILE%\.codex\sessions`
- Cross-platform default: `~/.codex/sessions`
- Override: `$CODEX_HOME/sessions`

Observed path shape:

```text
sessions/YYYY/MM/DD/rollout-YYYY-MM-DDTHH-MM-SS-<thread-id>.jsonl
```

## Core Events

Each line is a JSON object with at least `timestamp`, `type`, and usually `payload`.

Important event types:

- `session_meta`: first durable metadata for a thread. Key fields under `payload` include `id`, `timestamp`, `cwd`, `originator`, `source`, `thread_source`, `model`, and instruction snapshots.
- `turn_context`: per-turn execution context. Key fields include `turn_id`, `cwd`, `current_date`, `timezone`, sandbox and permission information.
- `response_item`: model-visible item. User and assistant messages usually appear here when `payload.type == "message"` and `payload.role` is `user` or `assistant`.
- `event_msg`: UI/status event. Visible user and assistant text may appear as `payload.type == "user_message"` or `payload.type == "agent_message"` with `payload.message`.
- `fileChange`, `tool`, `webSearch`, `contextCompaction`, `reasoning`, and related event types may appear. They are useful for reconstruction but should not be treated as chat text unless needed.

## Message Content Shapes

`response_item.payload.content` may be:

- a string
- a list of objects with `text`
- a list of objects with `input_text`

`event_msg.payload.message` is usually a string.

The same visible message can appear in both `response_item` and `event_msg`, so parsing should deduplicate exact normalized text.

## Matching Projects

Project association is usually best recovered from:

```text
session_meta.payload.cwd
turn_context.payload.cwd
```

After a project folder rename, old chats still keep the old `cwd`. Use `--cwd-contains <old-folder-name>` to recover those sessions.

Search by raw text alone can produce false positives because one chat can quote another chat or include approval-review transcripts. Prefer `cwd` or thread id filters when possible.

## Approval Review Sessions

Some JSONL files are not ordinary user chats. They contain prompts beginning like:

```text
The following is the Codex agent history whose request action you are assessing.
```

These sessions wrap another transcript for approval or safety review. They often duplicate real chat content and should usually be skipped for user-facing history summaries unless the user explicitly wants approval-review behavior.

## Practical Search Rules

- Start narrow: thread id, `cwd`, date range, then text query.
- Use user messages to identify the user's questions, pain points, and goals.
- Use assistant final messages plus action/status messages to identify proposed solutions and completed changes.
- Treat tool outputs as evidence, not prose to quote at length.
- Keep raw excerpts short because logs can contain private or copyrighted material.
