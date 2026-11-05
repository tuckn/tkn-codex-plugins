# Tkn Cross Review

AIが書いたコードを、完了報告の前に別のAIモデルにレビューさせるpluginです。
今は、Claude Codeが書いたコードをCodex CLIにレビューさせるSkillを1つ同梱します。

## 含まれるSkills

| Skill | 用途 |
| --- | --- |
| [codex-review](skills/codex-review/SKILL.md) | Claude Codeがコードの変更を完了と判断した後、完了報告の前に、Codex CLI（`gpt-6.1-sol`・推論 `xhigh`・読み取り専用）で変更をレビューさせ、指摘を検証して対応する。 |

会話だけのターンと、Markdown（`.md`）だけの変更では使いません。
Codexは読み取り専用で動かし、修正はClaude Codeが行います。

## 対応するAI

このpluginは、Claude Code用のcatalog（`.claude-plugin/marketplace.json`）にだけ載せています。
Codex用のcatalogには載せていません。Codexに読み込ませると、Codexが自分の作業を自分でレビューする手順を持つことになるためです。
Codexが書いたコードを別のAIにレビューさせる向きは、まだありません。

## 必要なもの

- Codex CLI（`codex`）。ログイン済みで、`codex review` と `codex exec resume` を使えること。
- 対象のコードがGitリポジトリにあること。レビューの対象は `git` の差分で決めます。

## インストール

```sh
claude plugin marketplace add tuckn/tkn-codex-plugins
claude plugin install tkn-cross-review@tkn-codex-plugins
```

## 確実に使わせる

Skillの説明だけに頼ると、使われないことがあります。
完了報告の前に必ず使わせるには、`~/.claude/CLAUDE.md` に次のような節を足します。

```markdown
## コーディング後のCodexレビュー

- コードを変更する作業を完了と判断したら、完了報告の前に `codex-review` Skillを使い、Codexにレビューさせる。
- 会話だけのターンと、Markdown（`.md`）だけの変更では使わない。
```

## Pluginの構成

- `.claude-plugin/plugin.json`: Claude Code用のplugin manifest。
- `skills/codex-review/`: Skill。
- `CHANGELOG.md`: 変更履歴。
