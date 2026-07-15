---
name: search-all-codex-chats
description: Search and explain user-specified themes, questions, decisions, outcomes, or project history across all Codex JSONL chat logs stored on the current computer under CODEX_HOME or %USERPROFILE%\.codex\sessions. Use when the user asks what happened or was decided in a past Codex conversation, wants to recover prior chat contents, or needs to inspect chats across projects, folders, threads, or dates, including after a project rename.
---

# Search All Codex Chats

Use this skill to answer questions from the Codex chat history stored on the current computer without rereading every JSONL log by hand.

## Workflow

1. Clarify the search target from the user request:
   - topic or question, such as "what did I ask about Plugin distribution?"
   - project/cwd hint, such as an old or renamed folder name
   - thread id, date range, or known title
   - desired output shape, if specified
2. Use `scripts/search_all_codex_chats.py` to find and condense matching logs across projects.
3. Read only the matched evidence needed for the answer.
4. Summarize in the user's requested structure. If unspecified, use:
   - what the user was trying to solve or achieve
   - what answer, proposal, or implementation was given
   - important decisions, unresolved issues, and other notable points
5. State when a conclusion is inferred from logs rather than directly visible.

## Script

Run the bundled script from this skill directory or pass its absolute path.

Typical commands:

```powershell
python -B plugins\tkn-codex-context-engineering\skills\search-all-codex-chats\scripts\search_all_codex_chats.py --cwd-contains codex-context-engineering --query plugin --format markdown
```

```powershell
python -B plugins\tkn-codex-context-engineering\skills\search-all-codex-chats\scripts\search_all_codex_chats.py --thread-id 019e2ff0-6551-7493-81ca-b982158bc336 --messages-per-role 0
```

Useful filters:

- `--sessions-root`: override the log root. Default is `$CODEX_HOME\sessions` when `CODEX_HOME` is set, otherwise `~\.codex\sessions`.
- `--cwd-contains`: match `session_meta.payload.cwd`; use old folder names after project renames.
- `--query`: case-insensitive literal text search across parsed user/assistant text. Can be repeated.
- `--thread-id`: match one or more specific Codex thread ids.
- `--date-from` / `--date-to`: filter by `session_meta.payload.timestamp` date.
- `--messages-per-role 0`: include all parsed user and assistant messages for each matched session.
- `--format json`: emit structured JSON for further processing.
- `--include-approval-reviews`: include approval-review/autoreview sessions that are skipped by default.

The script finds and condenses matching chats; it does not perform final interpretation. Use its output as evidence, then answer the user's question yourself.

## Schema Reference

Read `references/session-log-schema.md` when:

- the script needs adjustment for a new log event shape
- a log appears empty despite matching a thread id or cwd
- you need to explain how Codex stores session logs
- you need to distinguish real user chats from approval-review wrapper sessions

## Privacy And Scope

- Codex chat logs may contain private prompts, file paths, tool outputs, and copied document text. Search narrowly.
- Do not paste large raw logs into the final answer.
- Prefer summaries with short evidence snippets.
- Do not write matched raw logs into committed files.
- If a durable local artifact is useful, place it under the working location specified by the current project folder instructions or another ignored/private location unless the user asks otherwise.
