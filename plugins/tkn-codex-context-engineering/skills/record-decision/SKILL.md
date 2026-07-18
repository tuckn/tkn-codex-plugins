---
name: record-decision
description: 登録済み current project の projectId-specific decisions folder に durable decision record を作成する。ユーザー意図が future humans または Codex が再利用すべき project、product、solution、design、workflow、operation、documentation、repository、collaboration decisions に一致し、`.tkn/codex-context.yaml` が private registry で現在 workspace に解決できる場合に使う。marker 生成だけでは使わない。
---

# Record Decision

chat をまたいで再利用すべき decisions を記録するために、この skill を使う。

decision record は architecture に限定しない。project、product、solution、design、workflow、operation、documentation、repository convention、collaboration process に関する durable decision を扱える。

decision records は project-scoped または repositories をまたいで reusable になり得る。重要な場合は scope を明示する。

## Activation Gate

この skill は project-scoped な decision record を書くため、次の両方を満たす場合だけ実行準備ができている。

- ユーザー意図がこの skill に一致する。例: chat を超えて残すべき decision、accepted workflow、reusable rejected alternative。
- 現在の repository に `.tkn/codex-context.yaml` があり、その `projectId` が `~/.tkn/codex-context/state/index.jsonl` で現在の workspace に解決できる。

`.tkn/codex-context.yaml` が存在する、または直前に生成された、という事実だけではこの skill を発動しない。

未登録または registry 解決不能の場合、decision record を作成しない。`init-project-context` を案内し、登録を実行するのはユーザーが明示的に register/update を依頼した場合だけにする。

## File location

decision ごとに 1 file を作成する。

`~/.tkn/codex-context/state/<projectId>/decisions/DR-NNNN-<decision-title-slug>.md`

- `DR-NNNN` は four-digit sequence number。
- `~/.tkn/codex-context/state/index.jsonl` から project context folder を解決する。未登録の場合は自動登録せず、`init-project-context` を案内する。
- 既存の project `decisions/DR-*.md` filenames を確認し、次に利用可能な number を使用。
- core decision から作る短い kebab-case English slug の利用。
- number を選ぶためだけにすべての decision files を読まないこと。通常は filenames で十分。

## When to record

decision が現在の session 後も有用であるべき場合、decision record を作成する。例:

- Problem definition または scope choice。
- Solution または approach selection。
- Design または architecture decision。
- Business または project decision。
- Workflow または operational convention。
- Testing、validation、release strategy。
- Documentation policy または update direction。
- Collaboration または repository convention。
- future work が繰り返すべきでない important rejected option。

次の場合、decision record は作成しない。

- Temporary session state。
- Routine implementation details。
- Command logs。
- Simple chat summaries。
- decision のない unresolved brainstorming。
- normal knowledge notes、specs、plans、source files に置く方が適切な content。

迷う場合は session note に decision candidate として残し、`Next steps` に promotion question を記載する。

## Required structure

```md
---
type: decision
schemaVersion: 1
title: <decision-title>
description: <short-summary>
generator: Codex
status: Proposed
scope: project
promotionStatus: pending
promotedTo: []
date: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
updated: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
decisionId: DR-NNNN
---

# DR-NNNN: Title

## Context

## Decision

## Consequences

## Alternatives considered

## Related files

## Notes
```

本文に `## Status` と `## Scope` は置かない。machine-readable metadata は Frontmatter に集約する。

### Frontmatter policy

- `type`: 必ず `decision`。
- `schemaVersion`: 必ず `1`。この version は decision record の Frontmatter と本文 section の構造契約を表す。
- `title`: decision の表示用タイトル。`DR-NNNN:` は含めず、H1 と対応する title を書く。
- `description`: decision の概要。空欄は `""` とするが、後続の review / promote が判断できる短い説明をできるだけ書く。
- `generator`: 必ず `Codex`。
- `status`: decision の状態。`Proposed`、`Accepted`、`Rejected`、`Deprecated`、`Superseded` のいずれかを使う。
- `scope`: decision の適用範囲。`project`、`global`、`user`、`mixed` のいずれかを使う。
- `promotionStatus`: silver artifact である project decision から gold global context への昇格状態。`pending`、`partial`、`promoted`、`no-action` のいずれかを使う。
- `promotedTo`: 昇格先の paths。未昇格なら `[]`。`~/.tkn/codex-context/data/decisions/DR-G-*.md` などを列挙する。
- `date`: decision record の生成日時。既存 file で生成日時が不明な場合、filesystem の生成日時または migration 時点の日時を使う。
- `updated`: decision record の内容を最後に更新した日時。Skill が本文または Frontmatter を更新したら必ず更新する。
- `decisionId`: filename 先頭の `DR-NNNN`。Vault の file-management metadata として `updated` の下に置く。

`status` は decision の採否・有効性だけを表す。global context へ取り込まれたかは `promotionStatus` と `promotedTo` で表す。

### Schema compatibility

- 新規 decision record には `schemaVersion: 1` を必ず書く。
- `schemaVersion` がない既存 decision record は legacy v1 として読める。
- Legacy v1 の本文または Frontmatter を更新する場合は、内容を維持したまま `schemaVersion: 1` を追加する。
- `schemaVersion` が `1` 以外の場合は、対応形式を推測して書き換えず、unsupported version として報告する。
- `schemaVersion` を上げるのは、field の意味、必須 field、本文 section、または downstream extraction contract に互換性のない変更を加える場合だけにする。

## Status values

- `Proposed`: まだ accepted されていない candidate decision。
- `Accepted`: explicit user approval により採用済み、またはすでに implemented/operational practice として成立済み。
- `Rejected`: 検討済みで不採用。
- `Deprecated`: 以前は valid だったが現在は非推奨。
- `Superseded`: 別の decision または durable document により置き換え済み。

ユーザーが明示的に decision を approved している場合、または implementation によりすでに成立している場合を除き、new records は `Proposed` を default とする。

## Scope values

有用な場合は次のいずれかを使う。

- `project`: この repository または project 固有。
- `global`: repositories をまたいで有用。
- `user`: durable user-level working preference。
- `mixed`: project-specific と reusable parts の両方を含む。

project repository 内で global または user decision を作成する場合、他 repository または global skill に copy すべき内容を記載する。

## Writing rules

- file ごとに central decision は 1 つ。
- records は concise かつ durable。
- whole conversation ではなく、decision が重要な理由の説明。
- repeated work を防ぐ rejected alternatives の記載。
- relevant files、session notes、specs、README、AGENTS.md、issues、PRs、source files の link または list。
- secrets、credentials、tokens、private keys、full environment variables、large logs、不要な personal/customer data の記載禁止。
- decision が `AGENTS.md`、`README.md`、specs、design docs、operation docs、project `working-context.md`、reusable skills を更新すべき場合、`Notes` への記載。
- repository instruction が別途ない限り、body は日本語。Markdown headings、paths、commands、identifiers は native form の維持。
