---
name: write-session-note
description: 登録済み current project の projectId-specific state sessions folder に、evidence、decision candidates、reusable learnings、handoff を持つ蒸留可能な session note を作成または更新する。ユーザー意図が file changes、investigation、重要判断、multi-turn tasks、resumable work、handoff、compaction、または chat の記録依頼に一致し、`.tkn/codex-context.yaml` が private registry で現在 workspace に解決できる場合に使う。marker 生成だけでは使わない。
---

# Write Session Note

会話全文を保存せずに working state を chat 間で保持するために、この skill を使う。

目的は、future human または Codex の作業を DRY にすることだ。current state、うまくいったこと、failed approaches、decisions、open issues、exact next steps、validation results を引き継ぎ、同じ reasoning の繰り返しを避ける。

## Activation Gate

この skill は project-scoped な session note を書くため、次の両方を満たす場合だけ実行準備ができている。

- ユーザー意図がこの skill に一致する。例: 非自明な作業記録、handoff、resumable work、chat 記録依頼。
- 現在の repository に `.tkn/codex-context.yaml` があり、その `projectId` が `~/.tkn/codex-context/state/index.jsonl` で現在の workspace に解決できる。

`.tkn/codex-context.yaml` が存在する、または直前に生成された、という事実だけではこの skill を発動しない。

未登録または registry 解決不能の場合、session note を作成しない。`init-project-context` を案内し、登録を実行するのはユーザーが明示的に register/update を依頼した場合だけにする。

## File location

chat/thread ごとに 1 file を作成または更新する。

`~/.tkn/codex-context/state/<projectId>/sessions/YYYYMMDDTHHMMSS<system-timezone-offset>-<task-purpose-slug>.md`

- OS/system clock の timestamp と timezone offset の利用。ただし repository instruction が別途ある場合はその優先。
- task purpose から作る短い kebab-case English slug の利用。
- 同じ chat/thread では同じ session note の継続更新。
- ユーザーが session note path を指定した場合、その file だけの読み込みと更新。
- `~/.tkn/codex-context/state/index.jsonl` から project context folder を解決する。未登録の場合は自動登録せず、`init-project-context` を案内する。
- project `working-context.md` が存在し、非自明な task に関連する current project truth を含む可能性がある場合の確認。
- session note の生成日時が不明な既存 note を更新する場合、filename の timestamp を `date` と `sessionId` に使う。

## When to create

次のいずれかに該当する場合、session note を作成または更新する。

- 非自明な作業。
- file の作成、移動、編集、review の可能性。
- investigation、analysis、classification、design、judgment の関与。
- 複数 turn にまたがる可能性、または resumable である必要。
- 後で project `decisions/` へ promote する可能性がある decision。
- ユーザーによる chat 記録の明示依頼。
- handoff、context compaction、task switching の可能性。

通常、次の場合は作成しない。

- simple one-off answers。
- state を残さない trivial checks。
- repository changes と future reference value がなく、概ね 3 分未満の会話。
- 再開を意図していない casual discussion。

例外より user instruction を優先する。ユーザーが chat 記録を依頼した場合、session note を作成する。

## Required structure

```md
---
type: session
schemaVersion: 2
title: <session-title>
description: <short-summary>
generator: Codex
status: in-progress
distillationStatus: pending
distilledTo: []
date: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
updated: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
sessionId: YYYYMMDDTHHMMSS<system-timezone-offset>
---

# Session Note

## Objective

### Goal

### Done Criteria

## Outcome

## Current State

## User Confirmations

### Approved

### Rejected

### Preferences And Constraints

## Evidence

### Changed Files

### Validation

### Relevant Sources

## Decision Candidates

## Reusable Learnings

### What Worked

### Failed Approaches

### Skill And Automation Signals

## Open Loops

## Handoff

### Next Steps

### Exact Next Step
```

v2 では上記 headings を省略しない。該当内容がない section は `なし。` と明示する。

本文冒頭に `Session:`、`Task:`、`Status:`、`Last updated:` は置かない。これらの machine-readable metadata は Frontmatter に集約する。

### Frontmatter policy

- `type`: 必ず `session`。
- `schemaVersion`: 新規 session note は必ず `2`。この version は session note の Frontmatter と本文 section の構造契約を表す。
- `title`: session note の表示用タイトル。filename slug の単純な重複ではなく、作業内容が scan できる短い title を書く。
- `description`: session の概要。空欄は `""` とするが、後続の context distillation が判断できる短い説明をできるだけ書く。
- `generator`: 必ず `Codex`。
- `status`: chat/thread の作業状態。`in-progress`、`blocked`、`waiting-for-user`、`done` のいずれかを使う。
- `distillationStatus`: raw session note から silver context への反映状態。`pending`、`partial`、`distilled`、`no-action` のいずれかを使う。
- `distilledTo`: 反映先の paths。未反映なら `[]`。`../working-context.md`、`../decisions/DR-*.md` など同じ project context folder 内の path を優先する。
- `date`: session note の生成日時。既存 note で生成日時が不明な場合、filename の timestamp を ISO 8601 形式に変換して使う。
- `updated`: session note の内容を最後に更新した日時。Skill が本文または Frontmatter を更新したら必ず更新する。
- `sessionId`: filename 先頭の `YYYYMMDDTHHMMSS<system-timezone-offset>`。Vault の file-management metadata として `updated` の下に置く。

`status` は作業ライフサイクルだけを表す。session 内の raw context が decisions や working context に取り込まれたかは `distillationStatus` と `distilledTo` で表す。

### Schema compatibility

- 新規 session note には `schemaVersion: 2` を必ず書く。
- `schemaVersion` がない既存 session note は legacy v1 として読める。
- v1 session note は read-only 利用または metadata-only finalization では v1 のまま扱う。version 未記載なら `schemaVersion: 1` を明示してよい。
- v1 の本文を更新する場合は、v1 section の意味を v2 section へ移し、情報を失わずに全体を v2 へ migrate する。本文を変えず番号だけ `2` にしない。
- `schemaVersion` が `1` または `2` 以外の場合は、対応形式を推測して書き換えず、unsupported version として報告する。
- `schemaVersion` を上げるのは、field の意味、必須 field、本文 section、または downstream extraction contract に互換性のない変更を加える場合だけにする。

v1 から v2 への migration mapping:

- `Goal` + `Done criteria` → `Objective`
- confirmed な `User intent / interaction summary` → `User Confirmations`。goal や follow-up は `Objective` / `Handoff`
- `Current state` + durable assumptions → `Current State`
- `Working context`、`Changed files`、`Validation` → `Evidence`
- `Important decisions` → stable `DC-NN` を持つ `Decision Candidates`
- `What worked`、`Failed approaches` → `Reusable Learnings`
- durable constraints → `User Confirmations / Preferences And Constraints`
- `Open issues` → `Open Loops`
- `Next steps` + `Exact next step` → `Handoff`

### Codex chat provenance

`refresh-project-context-from-chats` などが Codex JSONL chat から session note を再構築または対応付ける場合、次の optional Frontmatter を追加する。

```yaml
sourceType: codexChat
sourceThreadIds:
  - <thread-id>
sourceRefs:
  - YYYY/MM/DD/rollout-....jsonl
```

- `sourceThreadIds`: note の source になった Codex thread ids。通常は1件。既存 `resume-session` による明示的な継続関係がある場合だけ複数を許可する。
- `sourceRefs`: Codex sessions root からの相対 JSONL paths。absolute path は書かない。
- Reconstructed note の `date` と filename timestamp: source chat 開始時刻を system timezone に変換した値。
- Reconstructed note の `updated`: reconstruction または refresh を実行した時刻。
- Direct chat で通常作成する note では、これらの field を必須にしない。
- Existing note にこれらの field がある場合、通常更新で削除しない。

## What to record

- `Objective`: この chat の goal と done criteria。意図と完了条件を結果から分離する。
- `Outcome`: この session で実際に得られた結果。予定や作業ログを書かない。
- `Current State`: session 終了時点で成立している事実、残っている状態、重要な assumptions。
- `User Confirmations`: durable な approved、rejected、preferences、constraints。assistant proposal を approval として扱わない。
- `Evidence`: changed files、validation、判断に使った relevant sources。full logs ではなく path と短い結果を書く。
- `Decision Candidates`: chat 後も残す可能性がある判断。候補ごとに stable ID と固定 field を使う。
- `Reusable Learnings`: 成功した方法、negative knowledge、Skill / automation signals。
- `Open Loops`: 未解決の questions、blockers、risks、未完了 follow-up。
- `Handoff`: concrete next steps と、future chat が最初に取る exact next step。

### Decision candidate format

Decision candidate は次の形式を使う。該当がなければ `なし。` と書く。

```md
### DC-01: <candidate-title>

- Status: accepted | proposed | rejected | unclear
- Scope: project | user | global | mixed
- Decision:
- Rationale:
- Evidence:
- Promotion Target: decision | working-context | global-decision | skill | automation | none
```

- `DC-NN` は note 内の two-digit sequence。
- `accepted` は user approval または成立済み実装の evidence がある場合だけ使う。
- 1 candidate に central decision を1つだけ書く。
- Promotion target は最も直接的な destination を1つ選ぶ。複数 destination が必要なら `Handoff` に follow-up を書く。

### Skill and automation signal format

Skill または automation candidate は次の形式を使う。該当がなければ `なし。` と書く。

```md
#### SA-01: <signal-title>

- Kind: skill | automation
- Signal:
- Evidence:
- Reuse Scope: project | user | global | mixed
- Suggested Follow-up:
```

## Failed approaches policy

実際に試した、evidence により否定された、または decision で明示的に rejected された approach だけを記録する。

各 item に含める内容:

- `試したこと`: attempted approach。
- `結果/根拠`: minimal evidence。
- `失敗理由`: unsuitable な理由。
- `再試行条件`: retry 前に変わる必要がある条件。

該当がない場合は `なし。` と書く。

## Update checkpoints

meaningful checkpoints で session note を更新する。

- initial plan 後。
- file changes 後。
- important decisions または rejected options 後。
- failed approaches または blockers 後。
- validation state changes 後。
- handoff、compaction、long interruption 前。
- completion 時。

task が project の durable current state を変える場合、project `working-context.md` を更新するか、更新不要の理由を記録する。

## Safety and style

- full logs、long quotes、full conversation transcripts の貼り付け禁止。
- secrets、credentials、tokens、private keys、full environment variables、large logs、不要な personal/customer data の記載禁止。
- chronological logs より current state の優先。
- resume のために `.codex-context/` 全体を読まないこと。user-specified session note または narrowly searched relevant files のみ。
- project `working-context.md` は dashboard として使い、detailed log として使わないこと。detail には session notes と decision records への link。
- repository instruction が別途ない限り、body は日本語。Markdown headings、paths、commands、identifiers は native form の維持。
