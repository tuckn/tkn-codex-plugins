# Tuckn Codex Context Engineering

[English](README.md) | 日本語

Brain DumpをMarkdownの計画ノートに整理し、ローカルのCodex chat履歴を検索するpluginです。
同梱するSkillは次の2つです。

## 含まれるSkills

| Skill | 用途 |
| --- | --- |
| [organize-brain-dump](skills/organize-brain-dump/SKILL.md) | 未整理の考えを構造化し、事実と助言を分けて計画ノートへ保存する。 |
| [search-all-codex-chats](skills/search-all-codex-chats/SKILL.md) | ローカルのCodex JSONLから過去の依頼・判断・結果を探す。 |

Brain Dumpの既定保存先は、現在のCodex Project Folder直下の `./organize-brain-dump/` です。
保存先フォルダがなければ作成します。ユーザーの明示指定やprojectの
規約を優先し、確認できる作成元Project情報をFrontmatterに残します。

Chat検索は既定で `$CODEX_HOME/sessions` または `~/.codex/sessions` を読みます。
別のarchiveは `--sessions-root` で指定します。検索scriptは共有parser
`lib/tkn_codex_context/chat_logs.py` を使用します。

## Pluginの構成

- `.codex-plugin/plugin.json`: plugin manifest。
- `skills/`: 対応する2つのSkillと検索用resource。
- `lib/tkn_codex_context/`: 共有parserと既存CLI。
- `scripts/windows_task_scheduler.ps1`: 既存CLIのscheduler helper。
- `tests/`: 共有libraryとCLIのtest。
