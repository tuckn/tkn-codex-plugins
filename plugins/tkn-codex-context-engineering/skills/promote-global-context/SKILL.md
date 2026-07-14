---
name: promote-global-context
description: 登録済み current project の session、decision、working context またはユーザー指定の explicit source から reusable Codex context を抽出し、script 経由で ~/.tkn/codex-context へ promote する。context を global に save、write、update、promote する依頼や promotionStatus 更新で使う。current-project source は `.tkn/codex-context.yaml` が private registry で現在 workspace に解決できることが必要で、marker 生成だけでは使わない。
---

# Promote Global Context

ユーザーが現在の repository または chat knowledge を user-global Codex context に保存するよう依頼したときに、この skill を使う。

目的は、repo-specific または sensitive information の accidental promotion を避けつつ、repositories をまたぐ future Codex sessions を改善することだ。repo-local `.codex-context` の silver artifacts を、必要な範囲だけ user-global gold context へ昇格する。

## Activation Gate

この skill は、ユーザーが global context への save、write、update、promote、または promotionStatus 更新を明示した場合だけ使う。

Current project の session、decision、working context を source にする場合、現在の repository に `.tkn/codex-context.yaml` があり、その `projectId` が `~/.tkn/codex-context/state/index.jsonl` で現在の workspace に解決できる必要がある。ユーザーが explicit source path を指定した場合は、その path を検証して対象にできる。

`.tkn/codex-context.yaml` が存在する、または直前に生成された、という事実だけではこの skill を発動しない。未登録または registry 解決不能の場合は自動登録せず、source path の指定または `init-project-context` を案内する。

## Target

`~/.tkn/codex-context`

この directory は context store であり、Codex configuration ではない。ユーザーが Codex configuration の編集を明示的に依頼しない限り、generated context を `~/.codex` に書き込まない。

この Plugin では `~/.tkn/codex-context` への bridge scripts は plugin root の `scripts/context_bridge/` に bundled されている。この `SKILL.md` からは `../../scripts/context_bridge/promote_context.py` として解決できる。

## When to use

ユーザーが次のように依頼したときに、この skill を使う。

- "これをglobal contextに反映して"
- "この判断は他repoでも使う"
- "今回の学びを `~/.tkn/codex-context` に保存して"
- "write global context"
- "promote global context"
- "promotionStatus を更新して"
- `review-decisions` の global context candidates を昇格する

## What to promote

promote する content:

- 複数 repositories に適用できる内容。
- future Codex collaboration quality を改善する内容。
- durable user preferences または workflow decisions の記録。
- repeated failed approaches を防ぐ内容。
- session note、decision record、working context、`review-decisions` output、explicit user instruction へ trace できる内容。
- repo 固有情報を取り除いても reusable essence が残る `scope: mixed` の内容。

promote しない content:

- repo-only implementation details。
- unverified guesses。
- temporary task state。
- full chat transcripts。
- secrets、credentials、tokens、private keys、full env vars、large logs、不要な personal/customer data。

不確かな場合は `decision` ではなく `candidate` として書く。

## Source artifacts

Project context folder 全体を盲目的に読まない。対象は、ユーザー指定の source、現在の canonical session note、project `working-context.md`、relevant decision records、または `review-decisions` が示した候補に絞る。

Frontmatter を一次 index として使う。

session note:

- `type: session`
- `status`
- `distillationStatus`
- `distilledTo`
- `updated`
- `sessionId`

working context:

- `type: workingContext`
- `status`
- `promotionStatus`
- `promotedTo`
- `updated`

decision record:

- `type: decision`
- `status`
- `scope`
- `promotionStatus`
- `promotedTo`
- `updated`
- `decisionId`

`promotionStatus: promoted` で `promotedTo` が現状と合っている source は、再 promotion しない。`promotionStatus: no-action` は、ユーザーが再検討を依頼した場合だけ対象に戻す。

## Destination classes

使う分類:

- `working-context`: future global work に影響すべき small dashboard updates。
- `decision`: accepted global または user-level decisions。
- `candidate`: useful だが未 accepted の learnings または proposals。

ユーザーが decision を明確に accepted していない限り、`candidate` を優先する。

## Destination Frontmatter

`~/.tkn/codex-context` に新規作成する Markdown は Frontmatter を持つ。destination 側の metadata は source 側の metadata をそのままコピーせず、global context としての意味に合わせて再定義する。

global working context:

```yaml
---
type: globalWorkingContext
title: Global Codex Working Context
description: User-global Codex context dashboard.
generator: Codex
status: active
scope: global
sourceRefs: []
date: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
updated: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
contextId: global-working-context
---
```

global decision:

```yaml
---
type: globalDecision
title: <decision title>
description: ""
generator: Codex
status: accepted
reviewStatus: accepted
scope: global
sourceRefs:
  - <repo-relative source path when possible>
sourceRepo: <source repository name when known>
date: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
updated: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
contextId: <UUID>
---
```

global candidate:

```yaml
---
type: globalCandidate
title: <candidate title>
description: ""
generator: Codex
status: proposed
reviewStatus: reviewing
scope: global
sourceRefs:
  - <repo-relative source path when possible>
sourceRepo: <source repository name when known>
date: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
updated: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
contextId: <UUID>
---
```

Field policy:

- `type`: global store 内での artifact kind。project context の `decision` / `workingContext` と区別する。
- `status`: artifact 自体の状態。decision は `accepted`、candidate は `proposed`、working context は `active` を基本にする。
- `reviewStatus`: human review state。accepted decision は `accepted`、candidate は `reviewing` を基本にする。
- `scope`: user-global store では原則 `global`。repo 固有情報が残る場合は promote せず、source artifact 側で整理する。
- `sourceRefs`: trace できる source paths。可能な限り source repository からの relative path を使い、不要な local absolute path や personal directory detail を残さない。
- `sourceRepo`: source repository 名または user が明示した source label。unknown の場合は空文字にしてよい。
- `date`: global artifact 作成日時。
- `updated`: global artifact 更新日時。append や metadata 変更時に更新する。
- `contextId`: global artifact の stable identifier。working context は固定 ID、decision / candidate は UUID を使う。

source body に既存 Frontmatter がある場合、destination Frontmatter と二重化させない。script は先頭 Frontmatter を除去してから本文を埋め込む。必要な source metadata は `sourceRefs` や本文の `Sources` section に要約する。

## Workflow

1. 現在の repository `AGENTS.md` と relevant specs の確認。
2. project `working-context.md` が存在し、関連する場合の確認。
3. 現在の canonical session note、relevant decision records、`review-decisions` output など、source artifacts を絞って確認。
4. source Frontmatter の `status`、`scope`、`promotionStatus`、`promotedTo` を確認。
5. reusable context の抽出と repo-specific details の除去。
6. `working-context`、`decision`、`candidate` の分類。
7. script に渡す body file を用意する。
   - synthesis や user review が必要な本文は `_inbox/ai/` に置く。
   - command log や一時検証出力は OS temp または private Codex working root に置く。
   - existing decision record をそのまま promote するより、必要な場合は repo-specific details を除いた concise body を作る。
8. script の dry-run mode での実行。
9. sensitive-looking content、unexpected destination、duplicate file を確認。
10. ユーザーが global context への write を依頼している場合のみ `--write` 付きで実行。
11. write が成功した場合、source artifact の `promotionStatus` / `promotedTo` 更新を検討。
12. promote した内容、location、metadata update の repository session note への記録。
13. promoted item が durable project state を変える場合、project `working-context.md` の更新または project decision record 作成の検討。

## Metadata updates after promotion

global write が成功した場合だけ、project context metadata を更新する。

decision record:

- reusable content 全体が global decision または candidate として昇格した場合、`promotionStatus: promoted`。
- 一部だけ昇格した場合、`promotionStatus: partial`。
- review の結果、昇格不要と判断した場合、`promotionStatus: no-action`。
- `promotedTo` には exact path を追加する。例: `~/.tkn/codex-context/data/decisions/DR-G-use-explicit-skill-bridge-for-global-context.md`。

working context:

- global dashboard へ反映した current truth が working context 全体の一部なら `promotionStatus: partial`。
- working context の reusable content がすべて反映済みなら `promotionStatus: promoted`。
- `promotedTo` には `~/.tkn/codex-context/data/working-context.md` などを追加する。

session note:

- `promotionStatus` は session note schema にはないため追加しない。
- session note の `distillationStatus` は raw session note から silver context への反映状態であり、global promotion の成功だけでは変更しない。
- global promotion により working context または decision record へ反映した場合だけ、必要に応じて `distillationStatus` / `distilledTo` を更新する。

共通:

- 既存の `promotedTo` を上書きせず、重複なしで追記する。
- metadata を更新したら、その file の `updated` を OS/system clock の timestamp に更新する。
- dry-run のみ、または user approval 待ちの場合は metadata を変更しない。

## Script

Candidate example:

```bash
python3 <plugin-root>/scripts/context_bridge/promote_context.py \
  --target ~/.tkn/codex-context \
  --kind candidate \
  --title "context loop import promote skills" \
  --body-file _inbox/ai/example.md \
  --source-repo notes \
  --dry-run \
  --log <temp-dir>/context-bridge/promote-candidate-dry-run.log
```

Decision example:

```bash
python3 <plugin-root>/scripts/context_bridge/promote_context.py \
  --target ~/.tkn/codex-context \
  --kind decision \
  --title "use explicit skill bridge for global context" \
  --body-file ~/.tkn/codex-context/state/<projectId>/decisions/DR-0008-use-explicit-skill-bridge-for-global-context.md \
  --source-repo notes \
  --write \
  --log <temp-dir>/context-bridge/promote-decision-write.log
```

Working context append example:

```bash
python3 <plugin-root>/scripts/context_bridge/promote_context.py \
  --target ~/.tkn/codex-context \
  --kind working-context \
  --title "Current global Codex context policy" \
  --body-file _inbox/ai/context-summary.md \
  --source-repo notes \
  --write \
  --log <temp-dir>/context-bridge/promote-working-context-write.log
```

`~/.tkn/codex-context` が repository 外にあるため、environment によっては `--write` 実行に user approval または filesystem permission escalation が必要になる。

## Safety

- ユーザーが direct write を明示しない限り、必ず dry-run first。
- script が sensitive-looking content を報告した場合の停止。
- copied repo notes より concise synthesized context の優先。
- useful な場合は generated file に source paths を残す。ただし sensitive local details の不要な埋め込みは避けること。
- imported snapshot `.codex-context/global-context/` は historical reference であり、promotion destination ではない。write destination は `~/.tkn/codex-context`。
- current user instructions、system/developer instructions、repository `AGENTS.md`、current file contents を global context より優先する。
