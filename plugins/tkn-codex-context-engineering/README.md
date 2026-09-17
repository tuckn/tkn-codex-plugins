# Tuckn Codex Context Engineering

English | [日本語](README_ja.md)

This plugin organizes Brain Dumps into Markdown planning notes and searches local Codex chat
history. It bundles exactly two Skills.

## Included Skills

| Skill | Purpose |
| --- | --- |
| [organize-brain-dump](skills/organize-brain-dump/SKILL.md) | Structure rough ideas, separate facts from advice, and save a planning note. |
| [search-all-codex-chats](skills/search-all-codex-chats/SKILL.md) | Find past requests, decisions, and outcomes in local Codex JSONL logs. |

Brain Dump notes default to `./organize-brain-dump/` directly under the current Codex Project
Folder. Create the folder if needed. Follow an explicit user destination or project instructions
first, and keep confirmed source-project metadata in Frontmatter.

Chat search reads `$CODEX_HOME/sessions` or `~/.codex/sessions` by default. Use
`--sessions-root` for a specific archive. Its script depends on the shared parser
`lib/tkn_codex_context/chat_logs.py`.

## Plugin Files

- `.codex-plugin/plugin.json`: plugin manifest.
- `skills/`: the two supported Skills and search resources.
- `lib/tkn_codex_context/`: shared parser and existing CLI implementation.
- `scripts/windows_task_scheduler.ps1`: existing CLI scheduler helper.
- `tests/`: shared library and CLI tests.
