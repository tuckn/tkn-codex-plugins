---
name: maintain-working-context
description: 登録済み current project の ~/.codex-context/projects/<projectId>/working-context.md を lightweight Codex Project dashboard として作成、確認、更新する。ユーザー意図が非自明な作業開始、active work changes、important decision changes、または working context 更新依頼に一致し、`.codex-context/project.yaml` が private registry で現在 workspace に解決できる場合に使う。marker 生成だけでは使わない。
---

# Maintain Working Context

`~/.codex-context/projects/<projectId>/working-context.md` を Codex Project の lightweight current-truth dashboard として有用に保つために、この skill を使う。

目的は、future human または Codex session がすべての session notes や decision records を読まずに、現在の repository state を素早く理解できるようにすることだ。

## Activation Gate

この skill は project-scoped な working context を読むまたは書くため、次の両方を満たす場合だけ実行準備ができている。

- ユーザー意図がこの skill に一致する。例: working context 確認、更新、active work changes、important decision changes。
- 現在の repository に `.codex-context/project.yaml` があり、その `projectId` が `~/.codex-context/projects/index.jsonl` で現在の workspace に解決できる。

`.codex-context/project.yaml` が存在する、または直前に生成された、という事実だけではこの skill を発動しない。

未登録または registry 解決不能の場合、working context を作成または更新しない。`register-project-context` を案内し、登録を実行するのはユーザーが明示的に register/update を依頼した場合だけにする。

## File location

Default location:

`~/.codex-context/projects/<projectId>/working-context.md`

Project context folder は `~/.codex-context/projects/index.jsonl` の `projectId` と `workingContextPath` から解決する。未登録の場合は自動登録せず、`register-project-context` を案内する。

## Role

Project `working-context.md` は Codex Project の current working truth を要約する。

簡潔に記録する内容:

- current purpose
- active work
- important constraints
- recent decisions
- 次に確認すべき session notes、decision records、plans、specs

含めない内容:

- detailed chronological logs
- full conversation transcripts
- large command outputs
- secrets、credentials、tokens、private keys、full env vars、不要な personal/customer data

detail は同じ project context folder の `sessions/`、`decisions/`、または関連する repository notes に置き、working context からそれらの path へ link する。

## When to inspect

非自明な作業を始めるとき、かつ relevant current project truth を含む可能性がある場合、project `working-context.md` を確認する。

ユーザーが次を依頼した場合も確認する。

- work の resume
- repository context の利用
- current active work の確認
- context の更新
- decisions または session notes の review

Project を理解するためだけに `~/.codex-context/projects/<projectId>/` 全体を読まない。working context を dashboard として使い、関連する link だけをたどる。

## When to update

Project current truth が変わる場合、特に次の場合に project `working-context.md` を更新する。

- active work changes
- important decision の accepted、deprecated、superseded、promoted
- 新しい session note が最適な resumption point になる場合
- 新しい plan、spec、plugin、skill、script が key file になる場合
- important constraints changes
- ユーザーによる working context 更新の明示依頼

現在の task が非自明だが durable repository state を変えない場合、working context 更新が不要な理由を session note に記録する。

## Update workflow

1. repository `AGENTS.md` と必須の repository specs の確認。
2. `~/.codex-context/projects/index.jsonl` から project context folder を解決し、`working-context.md` が存在する場合の確認。
3. 直接関連する session notes、decisions、plans、specs だけの確認。
4. chronological log ではなく、concise current state として working context を更新。
5. detail の重複より path 参照の優先。
6. `maintain-session-note` を使う場合、session note も更新し、working context 変更有無を記録。

## Suggested structure

repository により良い構造がない限り、この構造を使う。

```md
---
type: workingContext
title: <working-context-title>
description: <short-summary>
generator: Codex
status: active
promotionStatus: pending
promotedTo: []
date: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
updated: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
---

# Working Context

## Purpose

## Current Truth

## Active Work

## Important Constraints

## Recent Decisions

## Key Files

## Next Maintenance
```

本文冒頭に `Last updated:` は置かない。machine-readable metadata は Frontmatter に集約する。

### Frontmatter policy

- `type`: 必ず `workingContext`。
- `title`: working context の表示用タイトル。
- `description`: repository current truth の概要。空欄は `""` とするが、scan できる短い説明をできるだけ書く。
- `generator`: 必ず `Codex`。
- `status`: working context の状態。`active`、`stale`、`archived` のいずれかを使う。
- `promotionStatus`: silver artifact である working context から gold global context への昇格状態。`pending`、`partial`、`promoted`、`no-action` のいずれかを使う。
- `promotedTo`: 昇格先の paths。未昇格なら `[]`。`~/.codex-context/working-context.md` などを列挙する。
- `date`: working context の生成日時。既存 file で生成日時が不明な場合、filesystem の生成日時または migration 時点の日時を使う。
- `updated`: working context の内容を最後に更新した日時。Skill が本文または Frontmatter を更新したら必ず更新する。

`status` は working context 自体の鮮度・有効性だけを表す。global context へ取り込まれたかは `promotionStatus` と `promotedTo` で表す。

各 section は短く保つ。dashboard であり detailed report ではない。

## Style

- repository の primary language での記述。
- future sessions が scan しやすい stable headings の維持。
- repository files には relative paths の利用。
- absolute paths は repository 外の file を意図的に参照する場合のみ。
- scanability のための bullets 優先。
- stale items が真でなくなった場合の削除または置換。
