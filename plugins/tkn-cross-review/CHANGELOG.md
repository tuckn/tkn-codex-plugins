# Changelog

このファイルは、この marketplace に同梱する `tkn-cross-review` plugin の変更履歴です。
バージョンは plugin manifest（`.claude-plugin/plugin.json`）で管理します。

0.x の間は、機能追加や利用方法・出力契約の変更を minor、互換性を保つ修正を patch として扱います。
日付はこのリポジトリでの変更日です。公開・インストール済みであることを示すものではありません。

## [0.1.0] - 2026-11-05

### Added

- Skill `codex-review`。Claude Codeがコードの変更を完了と判断した後、完了報告の前に、
  Codex CLI（`gpt-6.1-sol`・推論 `xhigh`・読み取り専用）で変更をレビューさせ、指摘を検証して対応する。
- Claude Code用のplugin manifestと、Claude Code用catalogへの登録。Codex用catalogには載せない。

[0.1.0]: https://github.com/tuckn/tkn-codex-plugins/compare/e1cc0b2506d52845cfe968f7aec160127db231ce...main
