# Claude Code Session Logs And Search Contract

This is the bundled reader's supported format, not a stable Claude Code API. The [official session documentation](https://code.claude.com/docs/en/sessions#where-transcripts-are-stored) explicitly calls the entry format internal and version dependent. The reader was checked against local records on 2026-11-02; tests use synthetic data only.

## Discovery And Identity

The default projects root is `Path(CLAUDE_CONFIG_DIR) / "projects"`, otherwise `Path.home() / ".claude/projects"`. The process environment is used; settings files and credentials are not inspected. Override with repeated `--projects-root` for other profiles or copied roots. An absent or invalid selected root/file is an error rather than an empty result.

Supported discovery locations relative to each projects root:

```text
<encoded-project>/<session-id>.jsonl
<encoded-project>/agent-<agent-id>.jsonl
<encoded-project>/<session-id>/subagents/agent-<agent-id>.jsonl
```

Main logs are included by default. Agent files and `isSidechain` messages require `--include-subagents`, including when an agent file is selected explicitly. `memory/`, `tool-results/`, `mcp-tasks/`, root-level `history.jsonl`, and other layouts are not searched. Known `.orphaned-*.jsonl` set-aside transcripts are excluded from root scans; an explicit `--session-file` can read one. Files ending in `.jsonl.superseded-*` are outside the discovered extension. This is not an archive search.

`--session-file` reads exactly the selected file(s), without a default-root scan. The same resolved file is read once across overlapping/duplicate selections. Separate files with the same session ID stay separate evidence sources. Do not merge by session ID alone.

- `id`: transcript filename stem (before `.orphaned-` for a set-aside file).
- `parent_session_id`: enclosing session directory for nested agents; first recorded session ID for a legacy agent file.
- `agent_id`: `agent-` filename suffix for agent files; message-level `agentId` is retained when present.
- `recorded_session_ids`: IDs observed on user/assistant records, including inherited records.
- `--session-id`: exact match against `id` or nonempty `parent_session_id`. For main logs this selects the destination transcript, not every fork containing an inherited record.

The file directory name is not decoded into cwd: path encoding is lossy and can be overridden. See [official directory documentation](https://code.claude.com/docs/en/claude-directory#application-data), [environment variables](https://code.claude.com/docs/en/env-vars), and [subagent persistence](https://code.claude.com/docs/en/sub-agents#resume-subagents).

## Parsed Records

| Record/content | Handling |
| --- | --- |
| Top-level `type: user` or `assistant`, with a `message` object | Use string `content` or list blocks with `type: text` and string `text`. Preserve newlines and text-block order. |
| `timestamp`, `cwd`, `uuid`, `parentUuid`, `sessionId`, `isSidechain`, `agentId` | Preserve provenance without inventing missing values. The physical JSONL line is 1-based. |
| `custom-title` / `customTitle`, `ai-title` / `aiTitle` | Session titles for the destination transcript, only when `sessionId` matches its ID. The last record of each kind gives `title` / `ai_title`; each distinct nonempty value is kept in `title_history` with its first line. Titles inherited from another session ID are not used. `agent-name` records (observed to mirror custom titles) are ignored. |
| `tool_use`, `tool_result`, `thinking`, images, other content blocks | Do not traverse or turn into conversation text, even if they contain nested `text` fields. Mixed records retain only their top-level text blocks. |
| `isMeta` or `isCompactSummary` | Exclude and count as generated messages. |
| System, summary, progress, request/blob, attachment, queue and other records | Ignore; count by record type. Request blobs are not assistant messages. |

Exact duplicate `(role, uuid, text)` messages are retained once; repeated text with different UUIDs and changed text with the same UUID remain distinct evidence. Without UUIDs there is no deduplication. A `parentUuid` is a recorded graph edge, not a reliable turn ID, and is not followed to discard alternate branches. Display order is physical record order.

UTF-8 and UTF-8 BOM are supported. Invalid JSON, non-object records, and malformed conversation envelopes produce warnings containing path/line and error category, never the raw record. Unknown records are ignored. A file with a read/decode failure contributes no result; partial messages are not returned. Files with no parsed conversation text are reported as `files_without_messages`.

## Filters And Selection

Queries are case-insensitive literal substrings, or Python regular expressions with IGNORECASE/MULTILINE when `--regex` is set. Repeated queries use AND across eligible messages within one transcript, not necessarily within a single message. The first match of each query in each message gets an excerpt window. Empty queries and invalid regexes are errors. Queries never match titles.

`--title` is a literal substring match against every entry in `title_history` (custom and AI titles, including earlier titles). Both sides are compared after Unicode NFKC normalization, case-folding, and removal of all whitespace, so `Ｐｌｕｇｉｎ　設定` matches `Plugin設定` and `…` matches `...`. Repeated values use AND: each value must match at least one recorded title of the transcript. `--regex` does not apply. A transcript without a recorded title never matches. The title filter is applied with `--session-id` before cwd/date/query selection. Empty or whitespace-only values are errors.

`--cwd-contains` values are AND substrings after case-folding, slash normalization, and removing a trailing slash. `--cwd-field session` (default) uses the first nonempty retained message cwd. `message` uses each message's own recorded cwd, without filling in missing values.

`created` is the earliest valid timestamp among retained conversation text messages; `updated` is the latest. They are evidence timestamps, not filesystem mtimes or authoritative session creation metadata. Missing/invalid timestamps do not satisfy date filters. `--date-field created` is the default; `updated` selects whole transcripts; `message` filters each message. Combined message cwd/date filters apply to the same messages before query matching.

Dates are inclusive in the supplied fixed `--utc-offset` (default `+00:00`), not daylight-saving timezone rules. Naive timestamps are treated as UTC. Sorting defaults to `--sort-by updated --order desc`, then transcript ID/path for ties, before the default `--limit 10` (`0` means unlimited).

Every visible matching message is retained. The soft per-role budget (default 8) adds nearby messages (`--context-messages`, default 1), then head/tail overview messages. Hidden assistant messages can still satisfy a query unless `--query-user-only` is supplied. `--no-include-assistant` removes their text from both formats and reports a hidden-match count.

Excerpts default to 1,200 characters. Separate windows retain distant query matches. Oversized queries or regex matches can exceed the text window; use `--max-message-chars 0` when full evidence is needed. Full retrieval requires `--messages-per-role 0 --max-message-chars 0`; a multi-session retrieval may also require `--limit 0`. Other filters and generated/non-text exclusions still apply.

## JSON Schema Version 1

The independent Claude Code output starts at version 1; it does not claim compatibility with the Codex search's version 2 schema.

```json
{
  "schema_version": 1,
  "source": "claude-code",
  "coverage": {"roots": [], "files_scanned": 0, "matched_sessions": 0, "returned_sessions": 0},
  "filters": {},
  "sessions": []
}
```

`coverage` includes selected absolute roots/file paths and their kind, discovered/scanned files, unreadable files/directories, files without messages, parser warnings, duplicate messages, non-text messages, excluded subagent files, sidechain/generated messages, set-aside files, ignored record-type counts, matched/returned sessions, and excluded-source descriptions. These counts describe this scan only. They cannot measure deleted or unpersisted history. Diagnostics go to stderr; JSON stdout remains parseable.

Each session contains identity/provenance fields described above, `title`, `ai_title`, `title_history`, `path`, `cwd`, `created`, `updated`, `matched_queries`, `matched_titles`, `eligible_message_count`, `omitted_message_count`, `hidden_matching_message_count`, and `messages`. Each `title_history` and `matched_titles` entry contains `source` (`custom-title` or `ai-title`), `title`, and `line_number`. `matched_titles` is empty without `--title`. These title fields were added without changing `schema_version`; existing fields keep their meaning.

When a `--query` search without `--title` matches no transcript, the Markdown output adds a note that titles need `--title`.

Each message contains `role`, `text`, `timestamp`, `uuid`, `parent_uuid`, `session_id`, `cwd`, `line_number`, `is_sidechain`, `agent_id`, `truncated`, `text_start`, `text_end`, `matched_queries`, and `matched_excerpts`. Each matched excerpt contains `query`, `text`, `text_start`, `text_end`, `match_start`, `match_end`, and `truncated`. Offsets are zero-based/end-exclusive character positions in the full parsed message, not raw JSON bytes. Markdown quotes the same evidence with source and omission information.

Read failures or skipped records do not make an otherwise successful scan fail; inspect coverage and stderr before making completeness claims. Invalid arguments or missing selected roots/files exit with code 2. Ordinary successful searches, including zero matches, exit with code 0. The script has no output-file or mutation option.
