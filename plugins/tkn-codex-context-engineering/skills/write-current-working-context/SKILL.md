---
name: write-current-working-context
description: 登録済み current project の projectId-specific working-context.md を、current truth と portfolio metadata を持つ lightweight project control plane として作成または更新する。ユーザーが working context の作成・更新を依頼した場合、または lifecycle、health、priority、focus、blocker、active work、effective decision、dependency、resumption point の変更により project current truth の更新が必要で、`.tkn/codex-context.yaml` が private registry で現在 workspace に解決できる場合に使う。read-only orientation には read-current-working-context を使い、marker 生成だけでは使わない。
---

# Write Current Working Context

`~/.tkn/codex-context/state/<projectId>/working-context.md` を Codex Project の lightweight current-truth dashboard として作成または更新するために、この skill を使う。

目的は、future human または Codex session がすべての session notes や decision records を読まずに、現在の repository state を素早く理解できるようにすることだ。

## Activation Gate

この skill は project-scoped な working context を作成または更新するため、次の両方を満たす場合だけ実行準備ができている。

- ユーザー意図がこの skill に一致する。例: working context の作成・更新、active work changes、important decision changes。
- 現在の repository に `.tkn/codex-context.yaml` があり、その `projectId` が `~/.tkn/codex-context/state/index.jsonl` で現在の workspace に解決できる。

`.tkn/codex-context.yaml` が存在する、または直前に生成された、という事実だけではこの skill を発動しない。

状況確認や新しい chat の orientation だけが目的なら、この skill で timestamp を更新せず、`read-current-working-context` を使う。

未登録または registry 解決不能の場合、working context を作成または更新しない。`init-project-context` を案内し、登録を実行するのはユーザーが明示的に register/update を依頼した場合だけにする。

## File location

Default location:

`~/.tkn/codex-context/state/<projectId>/working-context.md`

Project context folder は `~/.tkn/codex-context/state/index.jsonl` の `projectId` と `workingContextPath` から解決する。未登録の場合は自動登録せず、`init-project-context` を案内する。

## Role

Project `working-context.md` は Codex Project の current working truth を要約する。

簡潔に記録する内容:

- current purpose
- current outcome と active workstreams
- project lifecycle status、health、priority
- current focus、blocker、exact next action
- important constraints
- effective decisions
- dependencies
- 次に確認すべき session notes、decision records、plans、specs

含めない内容:

- detailed chronological logs
- full conversation transcripts
- large command outputs
- secrets、credentials、tokens、private keys、full env vars、不要な personal/customer data

detail は同じ project context folder の `sessions/`、`decisions/`、または関連する repository notes に置き、working context からそれらの path へ link する。

## Read before write

作成または更新の前に、既存の project `working-context.md` があれば全体を読み、現在の内容を保った上で必要な箇所だけを更新する。

現在の変更を判断するため、直接関連する session notes、decisions、plans、specs だけを確認する。

read-only orientation は `read-current-working-context` に委譲する。更新前の確認でも `~/.tkn/codex-context/state/<projectId>/` 全体や chat 履歴を走査しない。

## When to update

Project current truth が変わる場合、特に次の場合に project `working-context.md` を更新する。

- active work changes
- important decision の accepted、deprecated、superseded、promoted
- project lifecycle status、health、priority、blocker、dependency の変更
- 新しい session note が最適な resumption point になる場合
- 新しい plan、spec、plugin、skill、script が key file になる場合
- important constraints changes
- ユーザーによる working context 更新の明示依頼

task が非自明という理由だけでは更新しない。project current truth が変わらない場合は、この skill を発動せず working context を変更しない。

## Update workflow

1. repository `AGENTS.md` と必須の repository specs の確認。
2. `~/.tkn/codex-context/state/index.jsonl` から project context folder を解決し、`working-context.md` が存在する場合の確認。
3. 直接関連する session notes、decisions、plans、specs だけの確認。
4. chronological log ではなく、concise current state として working context を更新。
5. detail の重複より path 参照の優先。
6. `write-session-note` を使う場合、session note も更新し、working context 変更有無を記録。

## Suggested structure

repository により良い構造がない限り、この構造を使う。

```md
---
type: workingContext
schemaVersion: 2
title: <working-context-title>
description: <short-summary>
projectId: <projectId>
generator: Codex
status: active
projectStatus: active
health: healthy
priority: normal
currentFocus: <short-current-focus>
blocked: false
mainBlocker: ""
exactNextAction: <one-concrete-action>
lastMeaningfulActivity: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
reviewAfter: YYYY-MM-DD
dependencyProjectIds: []
promotionStatus: pending
promotedTo: []
date: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
updated: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
---

# Working Context

## Purpose

## Current Outcome

## Current Truth

## Active Workstreams

## Blockers And Risks

## Important Constraints

## Effective Decisions

## Dependencies

## Key Files And Evidence

## Resumption

### Recommended Session

### Exact Next Action

## Maintenance

### Stale Items

### Review Due
```

v2 では上記 headings を省略しない。該当内容がない section は `None.` と明示する。

本文冒頭に `Last updated:` は置かない。machine-readable metadata は Frontmatter に集約する。

### Frontmatter policy

- `type`: 必ず `workingContext`。
- `schemaVersion`: 新規 working context は必ず `2`。この version は working context の Frontmatter と本文 section の構造契約を表す。
- `title`: working context の表示用タイトル。
- `description`: repository current truth の概要。空欄は `""` とするが、scan できる短い説明をできるだけ書く。
- `projectId`: marker と registry で検証した current project の ID。
- `generator`: 必ず `Codex`。
- `status`: working context の状態。`active`、`stale`、`archived` のいずれかを使う。
- `projectStatus`: project lifecycle。`active`、`paused`、`blocked`、`completed`、`archived` のいずれかを使う。
- `health`: project の現在の健全性。`healthy`、`attention`、`at-risk`、`unknown` のいずれかを使う。
- `priority`: project portfolio 内の相対優先度。`high`、`normal`、`low` のいずれかを使う。
- `currentFocus`: 現在の中心 workstream を1文で書く。なければ `""`。
- `blocked`: exact next action を妨げる blocker があれば `true`、なければ `false`。`projectStatus: blocked` と一致させる。
- `mainBlocker`: 最も重要な blocker の短い説明。`blocked: false` なら `""`。
- `exactNextAction`: broad plan ではなく、次に実行する concrete action を1文で書く。
- `lastMeaningfulActivity`: project current truth、deliverable、decision、または active workstream が最後に実質変化した日時。単なる read-only access では更新しない。
- `reviewAfter`: 次回 context review の ISO 8601 date。予定がなければ `""`。
- `dependencyProjectIds`: この project の進行に直接影響する登録済み Codex Project IDs。未登録・external dependency は本文に書く。
- `promotionStatus`: silver artifact である working context から gold global context への昇格状態。`pending`、`partial`、`promoted`、`no-action` のいずれかを使う。
- `promotedTo`: 昇格先の paths。未昇格なら `[]`。`~/.tkn/codex-context/data/working-context.md` などを列挙する。
- `date`: working context の生成日時。既存 file で生成日時が不明な場合、filesystem の生成日時または migration 時点の日時を使う。
- `updated`: working context の内容を最後に更新した日時。Skill が本文または Frontmatter を更新したら必ず更新する。

`status` は working context artifact 自体の鮮度・有効性、`projectStatus` は project lifecycle を表す。両者を混同しない。global context へ取り込まれたかは `promotionStatus` と `promotedTo` で表す。

### Schema compatibility

- 新規 working context には `schemaVersion: 2` を必ず書く。
- `schemaVersion` がない既存 working context は legacy v1 として読める。
- v1 working context は read-only orientation または identity-only refresh では v1 のまま扱う。version 未記載なら `schemaVersion: 1` を明示してよい。
- v1 の current truth を更新する場合は、portfolio metadata を根拠から設定し、既存本文を v2 sections へ移し、情報を失わずに全体を v2 へ migrate する。本文を変えず番号だけ `2` にしない。
- `schemaVersion` が `1` または `2` 以外の場合は、対応形式を推測して書き換えず、unsupported version として報告する。
- `schemaVersion` を上げるのは、field の意味、必須 field、本文 section、または downstream extraction contract に互換性のない変更を加える場合だけにする。

v1 から v2 への migration mapping:

- `Purpose` と `Current Truth` は意味を維持し、実際に得られた直近結果だけを `Current Outcome` へ分離する。
- `Active Work` → `Active Workstreams`
- blocker と risk を active work / constraints から `Blockers And Risks` へ分離する。
- `Recent Decisions` は現在有効な accepted decisions だけを `Effective Decisions` へ移す。recent でも proposed な項目を current truth にしない。
- `Key Files` → `Key Files And Evidence`
- `Next Maintenance` を `Resumption` と `Maintenance` に分類する。
- portfolio metadata は current user/repository/file/Git evidence から設定する。不明な値は `unknown` または `""` とし、推測で埋めない。

### Portfolio value semantics

- `projectStatus: active`: 現在進行中で、next action を実行できる。
- `projectStatus: paused`: 意図的に保留中。再開条件を `Maintenance` に書く。
- `projectStatus: blocked`: blocker を解消しないと進めない。`blocked: true` と `mainBlocker` を必須にする。
- `projectStatus: completed`: intended outcome を完了し、active workstream がない。
- `projectStatus: archived`: current portfolio から外れ、通常の maintenance 対象ではない。
- `health: healthy`: current plan と evidence に重大な懸念がない。
- `health: attention`: review、軽度の blocker、staleness、または近い期限への注意が必要。
- `health: at-risk`: outcome、期限、品質、または継続性に重大な risk がある。
- `health: unknown`: 判断できる evidence が不足している。

`exactNextAction` は `active` または `blocked` では必須とする。`paused`、`completed`、`archived` では concrete action がなければ `""` を許可する。

各 section は短く保つ。dashboard であり detailed report ではない。

### Path reference policy

`## Effective Decisions` と `## Key Files And Evidence` の file または directory reference は、次の logical root を付けて backtick 内に記載する。

- `project:/<path>`: registry で解決した current Codex Project folder を基準にする。
- `state:/<path>`: registry で検証した current project state folder、つまり `working-context.md` の親 folder を基準にする。

例:

```markdown
## Effective Decisions

- `state:/decisions/DR-0001-example.md`

## Key Files And Evidence

- `project:/README.md`
- `project:/.tkn/codex-context.yaml`
- `state:/working-context.md`
```

この2 section では、root のない relative path、Windows separator `\`、root 外へ出る `..` を生成しない。`project:/` と `state:/` は filesystem URI や Markdown link target ではなく、Codex が registry と verified state folder から解決する logical reference である。Project または state の外にある file を意図的に参照する場合だけ、明示的な external path を維持する。

## Style

- repository の primary language での記述。
- future sessions が scan しやすい stable headings の維持。
- `Effective Decisions` と `Key Files And Evidence` の project files には `project:/`、project state files には `state:/` の利用。
- physical absolute paths は project と state の外の file を意図的に参照する場合のみ。
- scanability のための bullets 優先。
- stale items が真でなくなった場合の削除または置換。
