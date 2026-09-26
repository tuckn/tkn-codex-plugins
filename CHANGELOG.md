# Changelog

このファイルは、この marketplace に同梱する `tkn-codex-context-engineering` plugin の変更履歴です。
バージョンは plugin manifest と `pyproject.toml` で揃えます。
marketplace catalog 自体には独立したバージョンを設けていません。

0.x の間は、機能追加や利用方法・出力契約の変更を minor、互換性を保つ修正を patch として扱います。
日付はこのリポジトリでの変更日です。公開・インストール済みであることを示すものではありません。

## [0.18.0] - 2026-09-26

### Changed

- `organize-brain-dump` の既定保存先を、Codex Project Folder 直下の
  `./organize-brain-dump/` から `./.agents/organize-brain-dump/` に変更。
  ユーザーの明示指定と project instructions を優先する方針は維持。
- 新規ノートの Frontmatter を `noteId` から `id` に統一。
  `originCodexProjectId`・`originCodexProjectName`・`originCodexThreadId`・
  `originCodexLog`・`originService` を、用途に応じた `source*` 項目へ整理。
  `sourceThreadIds` は 1 件でも文字列配列として記録。
- Frontmatter を Obsidian 向けのトップレベルの scalar または文字列配列に制限し、
  入れ子の object や配列を使わない方針を明記。
- リポジトリと plugin の README を日本語の `README.md` に集約し、`README_ja.md` を削除。

### Added

- 入力素材の種類を示す `sourceType` と、対象入力を追跡する `sourceLocators`・
  `sourceExcerpts` の記録規則を追加。
- 入力元の参照、RAW capture、ハッシュの記録・検証規則を明確化。
  未確認の ID・参照・ハッシュは推測せず、出力先 Project と入力元 Project を区別。
- この `CHANGELOG.md` と、リポジトリ README からのリンクを追加。

### Fixed

- plugin manifest の保存先説明を、Skill と README の `./.agents/organize-brain-dump/` に同期。
- plugin manifest と Python package のバージョンを `0.18.0` に同期。

### Compatibility

- 保存先と出力プロパティの変更を含むため、`0.17.1` ではなく `0.18.0` とする。
- 旧保存先や `noteId`・`origin*` を参照する検索・取り込み処理は、新規出力に合わせて見直す必要がある。
- この更新で既存ノートを自動移動・一括変換しない。既存ノートを明示的に更新する場合は UUID を維持する。
- `type: plan` は維持し、session note の `schemaVersion` や生成 pipeline のバージョンは流用しない。

## [0.17.0] - 2026-09-18

Git 履歴で `0.17.0` が設定された `8fc8abd` を比較の基準とする。
以下はこの時点ですでに含まれていた変更であり、`0.18.0` の新機能ではない。

### Changed

- 公開 Skill を `organize-brain-dump` と `search-all-codex-chats` の 2 つに整理し、
  manifest と README を更新。
- Brain Dump を Project Folder 直下の `./organize-brain-dump/` に保存する構成へ変更。
- 共有 parser、既存 CLI、Windows Task Scheduler helper と関連テストを同梱。

### Removed

- Project 初期化、session note 作成、working context 更新・集約、decision 管理、
  context 再構築・鮮度監査などの旧 Skill と関連する専用 script・test を削除。
- session note の `distillationStatus`・`distilledTo` を生成・検証処理と fixture から削除。

[0.18.0]: https://github.com/tuckn/tkn-codex-plugins/compare/8fc8abd7facc29fb2c99be67e693f36c30ae1253...main
[0.17.0]: https://github.com/tuckn/tkn-codex-plugins/commit/8fc8abd7facc29fb2c99be67e693f36c30ae1253
