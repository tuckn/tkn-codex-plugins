# Tkn Codex Context Engineering

Brain DumpをMarkdownの計画ノートに整理し、Codex・Claude Codeのchat履歴を調べるpluginです。
同梱するSkillは次の2つです。

## 含まれるSkills

| Skill | 用途 |
| --- | --- |
| [organize-brain-dump](skills/organize-brain-dump/SKILL.md) | 未整理の考えを構造化し、事実と助言を分けて計画ノートへ保存する。 |
| [search-genai-chats](skills/search-genai-chats/SKILL.md) | 共通の検索CLI `tkn-genai-chat-search` で、Codex・Claude Codeの過去の会話をタイトル・話題から探して読む。 |

`search-genai-chats` は、PCに別途インストールした [tkn-genai-chat-search](https://github.com/tuckn/tkn_genai_chat_search) を呼び出します。
Codexの圧縮ログ（`.jsonl.zst`）とCodexのタイトルも読み、どのAIの会話かが分からなくても1回の検索で探せます。
CLIがない場合、Skillは導入方法を伝えて止まります。
CLIは次で導入します。

```shell
uv tool install git+https://github.com/tuckn/tkn_genai_chat_search
```

以前のSkill `search-all-codex-chats`・`search-all-claude-code-chats` と、その検索scriptは0.20.0で削除しました。
代わりに `search-genai-chats` を使います（[変更履歴](../../CHANGELOG.md)）。

Brain Dumpの既定保存先は、現在のCodex Project Folder直下の `./.agents/organize-brain-dump/` です。
保存先フォルダがなければ作成します。ユーザーの明示指定やprojectの
規約を優先し、確認できる作成元Project情報をFrontmatterに残します。

## 検証

リポジトリ直下で次を実行します。testはOS標準一時領域に合成ログを作成し、実際のchatを変更しません。

```powershell
python -B -X utf8 -m unittest discover -s plugins/tkn-codex-context-engineering/tests -v
```

## Pluginの構成

- `.codex-plugin/plugin.json`: plugin manifest。
- `skills/`: 2つのSkill。
- `lib/tkn_codex_context/`: 既存CLIと、そのchat log parser。
- `scripts/windows_task_scheduler.ps1`: 既存CLIのscheduler helper。
- `tests/`: 共有libraryとCLIのtest。
