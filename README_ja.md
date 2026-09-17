# tkn-codex-plugins

[English](README.md) | 日本語

Tuckn の公開 Codex plugin marketplace です。

## インストール

このリポジトリを Codex plugin marketplace として追加します。

```sh
codex plugin marketplace add tuckn/tkn-codex-plugins --ref main
```

Codex は marketplace manifest を次の場所から読み込みます。

```text
.agents/plugins/marketplace.json
```

## Marketplace の構成

- `.agents/plugins/marketplace.json`: このリポジトリの marketplace catalog。
- `plugins/`: 公開可能な Codex plugin bundle。

このリポジトリには完成済みの plugin bundle を置きます。開発用の source tree は別の
リポジトリに置き、完成した bundle を `plugins/<plugin-name>/` に反映します。

## Plugins

### Tuckn Codex Context Engineering

この plugin は、Brain DumpをMarkdownの計画ノートに整理し、ローカルのCodex chat履歴を
検索します。同梱Skillは `organize-brain-dump` と `search-all-codex-chats` の2つです。

Path:

```text
plugins/tkn-codex-context-engineering/
```

詳細:

- [Plugin README](plugins/tkn-codex-context-engineering/README.md)
- [日本語 README](plugins/tkn-codex-context-engineering/README_ja.md)

## Plugin の追加

新しい plugin は次の場所に追加します。

```text
plugins/<plugin-name>/
```

各 plugin には次の manifest が必要です。

```text
plugins/<plugin-name>/.codex-plugin/plugin.json
```

次に、対応する entry を以下に追加します。

```text
.agents/plugins/marketplace.json
```

marketplace path には、次のような repo-relative path を使います。

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
