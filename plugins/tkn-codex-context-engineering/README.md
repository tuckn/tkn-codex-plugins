# Tkn Codex Context Engineering

Brain DumpをMarkdownの計画ノートに整理し、標準の履歴ツールとローカルの本文検索でCodex chat履歴を調べるpluginです。
同梱するSkillは次の2つです。

## 含まれるSkills

| Skill | 用途 |
| --- | --- |
| [organize-brain-dump](skills/organize-brain-dump/SKILL.md) | 未整理の考えを構造化し、事実と助言を分けて計画ノートへ保存する。 |
| [search-all-codex-chats](skills/search-all-codex-chats/SKILL.md) | 標準の履歴ツールとローカルの本文検索を使い分け、過去の依頼・判断・結果を探す。 |

Brain Dumpの既定保存先は、現在のCodex Project Folder直下の `./.agents/organize-brain-dump/` です。
保存先フォルダがなければ作成します。ユーザーの明示指定やprojectの
規約を優先し、確認できる作成元Project情報をFrontmatterに残します。

Chat検索は、既知のchatには利用可能な標準の一覧・履歴ツールを優先し、本文の横断検索や
ツールがない環境では同梱scriptを使います。Python 3.11以上と完全なplugin bundleが必要です。
scriptは共有parser `lib/tkn_codex_context/chat_logs.py` を使用し、追加packageの導入は不要です。

ローカル検索は既定で `$CODEX_HOME/sessions` または `~/.codex/sessions` を読みます。
`--scope all` で同じCodex homeの `archived_sessions` も対象にできます。
rootの変更は `--sessions-root` / `--archived-root` で指定します。
別ホスト・cloudの履歴やtool出力は、このscriptの検索範囲には入りません。

一致した発言と前後を会話順に表示し、日時・turn ID・行番号を残します。
`--cwd-field message` / `--date-field message` は各発言で絞り込み、
`--sort-by updated --order desc` は最近発言のあったchatから表示します。
従来の既定値（active・開始時点のcwd/日付・作成日の昇順）は維持しています。

JSONは `schema_version: 2` のobjectに変更し、`coverage`・`filters`・`sessions` を返します。
従来の配列を読むconsumerは `result["sessions"]` に切り替えてください。
全文取得には `--messages-per-role 0 --max-message-chars 0` の両方を指定します。
実行例は[Skill](skills/search-all-codex-chats/SKILL.md)、出力契約と互換性は
[schema reference](skills/search-all-codex-chats/references/session-log-schema.md)を参照してください。

## 検証

リポジトリ直下で次を実行します。testはOS標準一時領域に合成ログを作成し、実際のchatを変更しません。

```powershell
python -B -X utf8 -m unittest discover -s plugins/tkn-codex-context-engineering/tests -v
```

## Pluginの構成

- `.codex-plugin/plugin.json`: plugin manifest。
- `skills/`: 対応する2つのSkillと検索用resource。
- `lib/tkn_codex_context/`: 共有parserと既存CLI。
- `scripts/windows_task_scheduler.ps1`: 既存CLIのscheduler helper。
- `tests/`: 共有libraryとCLIのtest。
