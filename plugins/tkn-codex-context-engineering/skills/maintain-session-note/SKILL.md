---
name: maintain-session-note
description: 登録済み current project の projectId-specific state sessions folder に簡潔な session note を作成または更新する。ユーザー意図が file changes、investigation、重要判断、multi-turn tasks、resumable work、handoff、compaction、または chat の記録依頼に一致し、`.tkn/codex-context.yaml` が private registry で現在 workspace に解決できる場合に使う。marker 生成だけでは使わない。
---

# Maintain Session Note

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

## Goal

## Done criteria

## User intent / interaction summary

## Current state

## Working context

## Changed files

## Important decisions

## What worked

## Failed approaches

## Open issues

## Next steps

## Exact next step

## Constraints

## Validation
```

本文冒頭に `Session:`、`Task:`、`Status:`、`Last updated:` は置かない。これらの machine-readable metadata は Frontmatter に集約する。

### Frontmatter policy

- `type`: 必ず `session`。
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

## What to record

- `Goal`: この chat の intended outcome。
- `Done criteria`: 作業完了と判断するために満たすべき条件。
- `User intent / interaction summary`: durable requests、preferences、approvals、rejections のみ。
- `Current state`: 現在の作業状態。
- `Working context`: 関連する docs、files、searches、assumptions。paths と短い summary の利用。
- `Changed files`: created、edited、moved、proposed files。
- `Important decisions`: project `decisions/` の candidates を含む decisions。project、product、solution、design、workflow、operation、documentation、repository decisions を含む。
- `What worked`: 再利用すべき successful approaches、commands、patterns、prompts、checks。
- `Failed approaches`: 重要な negative knowledge。
- `Open issues`: 未解決の questions、blockers、risks。
- `Next steps`: decision records 作成や docs 更新を含む concrete next actions。
- `Exact next step`: future chat が broad planning の前に取るべき最初の concrete action。
- `Constraints`: repository rules、user instructions、safety constraints、validation limits。
- `Validation`: 簡潔な test/check status。

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
