# tkn-codex-plugins

Tuckn の公開 plugin marketplace です。Codex と Claude Code で使えます。

## インストール

このリポジトリを Codex plugin marketplace として追加します。

```sh
codex plugin marketplace add tuckn/tkn-codex-plugins --ref main
```

Codex は marketplace manifest を次の場所から読み込みます。

```text
.agents/plugins/marketplace.json
```

### Claude Code

同じ plugin bundle を Claude Code plugin としても使えます。
`tkn-cross-review` は Claude Code 専用です。

```sh
claude plugin marketplace add tuckn/tkn-codex-plugins
claude plugin install tkn-codex-context-engineering@tkn-codex-plugins
claude plugin install tkn-cross-review@tkn-codex-plugins
```

ローカルの clone を登録すると、bundle の変更は Claude Code の次回 session 開始時
または `/reload-plugins` で反映されます。

```sh
claude plugin marketplace add <path-to>/tkn-codex-plugins
```

Claude Code は marketplace manifest を `.claude-plugin/marketplace.json`、
plugin manifest を `plugins/<plugin-name>/.claude-plugin/plugin.json` から読み込みます。
Skill は Codex と共通の `plugins/<plugin-name>/skills/` を使います。

## Marketplace の構成

- `.agents/plugins/marketplace.json`: Codex 用の marketplace catalog。
- `.claude-plugin/marketplace.json`: Claude Code 用の marketplace catalog。
- `plugins/`: 公開可能な plugin bundle。両方で使う plugin には、Codex と Claude Code の manifest を併置する。
  片方だけで使う plugin には、その AI の manifest だけを置き、その AI の catalog にだけ載せる。

このリポジトリには完成済みの plugin bundle を置きます。開発用の source tree は別の
リポジトリに置き、完成した bundle を `plugins/<plugin-name>/` に反映します。

## Plugins

### Tuckn Codex Context Engineering

この plugin は、Brain DumpをMarkdownの計画ノートに整理し、共通の検索CLIで
Codex・Claude Codeのchat履歴を調べます。
同梱Skillは `organize-brain-dump`、`search-genai-chats` の2つです。`search-genai-chats` は別途インストールする
CLI [tkn-genai-chat-search](https://github.com/tuckn/tkn_genai_chat_search) を使います。

Path:

```text
plugins/tkn-codex-context-engineering/
```

詳細:

- [Plugin README](plugins/tkn-codex-context-engineering/README.md)
- [変更履歴](CHANGELOG.md)

### Tuckn Cross Review

この plugin は、AI が書いたコードを、完了報告の前に別の AI モデルにレビューさせます。
同梱Skillは `codex-review` の1つで、Claude Code が書いたコードを Codex CLI にレビューさせます。
Codex が自分の作業を自分でレビューしないよう、Claude Code 用の catalog にだけ載せています。

Path:

```text
plugins/tkn-cross-review/
```

詳細:

- [Plugin README](plugins/tkn-cross-review/README.md)
- [変更履歴](plugins/tkn-cross-review/CHANGELOG.md)

## Plugin の追加

新しい plugin は次の場所に追加します。

```text
plugins/<plugin-name>/
```

plugin を使う AI ごとに、manifest を置き、catalog に entry を追加します。
片方の AI だけで使う plugin は、その AI の分だけにします。

| AI | plugin manifest | catalog |
| --- | --- | --- |
| Codex | `plugins/<plugin-name>/.codex-plugin/plugin.json` | `.agents/plugins/marketplace.json` |
| Claude Code | `plugins/<plugin-name>/.claude-plugin/plugin.json` | `.claude-plugin/marketplace.json` |

Codex の catalog には、次のような repo-relative path を使います。

```json
{
  "name": "plugin-name",
  "source": {
    "source": "local",
    "path": "./plugins/plugin-name"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Productivity"
}
```

Claude Code の catalog には、次のように書きます。

```json
{
  "name": "plugin-name",
  "source": "./plugins/plugin-name",
  "description": "What the plugin does.",
  "category": "productivity"
}
```
