---
name: review-decisions
description: ~/.codex-context/projects/<projectId>/decisions を Frontmatter metadata と本文で review し、durable repository documents への updates、global context 候補、promotionStatus 更新案を提案または適用する。decision 棚卸し、documented すべき decisions 発見、global context 候補抽出、accepted decision records からの repository guidance 更新依頼で使う。
---

# Review Decisions

蓄積した decision records を maintained project documentation に反映するために、この skill を使う。

目的は、project `decisions/` が isolated archive になることを防ぐことだ。Accepted decisions は、future humans と Codex が実際に読む durable documents に定期的に反映するべきだ。

## Inputs

Typical inputs:

- `~/.codex-context/projects/<projectId>/decisions/DR-*.md`
- `~/.codex-context/projects/<projectId>/working-context.md`
- `AGENTS.md`
- `README.md`
- Specs、design docs、operation docs、plans、その他 durable repository documents。
- 必要な場合のみ relevant session notes。

Project context folder 全体を盲目的に読まない。

decision record の Frontmatter を一次 index として扱う。

必ず確認する metadata:

- `type`
- `title`
- `description`
- `status`
- `scope`
- `promotionStatus`
- `promotedTo`
- `updated`
- `decisionId`

本文を読む前に、filenames と Frontmatter で対象をできるだけ絞る。

## Workflow

1. repository guidance の事前確認。
   - `AGENTS.md`
   - project `working-context.md` が存在し、関連する場合
   - `README.md` が存在し、関連する場合
   - ユーザーが指定した specs または docs
2. decision record filenames の列挙。
   - project `decisions/DR-*.md`
3. decision Frontmatter index の作成。
   - `status`
   - `scope`
   - `promotionStatus`
   - `promotedTo`
   - `updated`
4. review scope の絞り込み。
   - ユーザーが full 棚卸しを依頼した場合の all decisions
   - recent decisions
   - topic または document に関連する decisions
   - accepted decisions only
   - `scope: global` / `scope: user` / `scope: mixed`
   - `promotionStatus: pending` / `promotionStatus: partial`
5. selected decision records のみの読み込み。
6. decision ごとの分類。
   - durable docs にすでに反映済み
   - `AGENTS.md` の更新対象
   - `README.md` の更新対象
   - spec/design/operation doc の更新対象
   - project `working-context.md` の更新対象
   - reusable skill または cross-repo template の更新対象
   - global context candidate
   - global context promoted already
   - `promotionStatus` / `promotedTo` metadata 更新候補
   - project `decisions/` のみに残す対象
   - obsolete、superseded、または user review が必要な対象
7. global context になり得る要素の抽出。
   - repo 固有情報を除いた reusable rule / preference / workflow / failed approach。
   - recommended destination class: `working-context`、`decision`、`candidate`。
   - source decision paths と根拠。
8. concise review result の作成。
9. ユーザーが edits を依頼した場合、target docs への scoped changes と validation の記録。
10. ユーザーが global promotion を依頼した場合、`promote-global-context` の workflow に従う。review だけで `~/.codex-context` へ書き込まない。
11. update が substantial または uncertain な場合、durable docs を直接編集する前に `_inbox/ai` または repository configured AI output folder へ proposal note を作成。

## Review criteria

decision が次に該当する場合、durable documentation updates を提案する。

- future work の進め方を変えるもの。
- project scope、architecture、solution direction、workflow を定義するもの。
- repeated judgment を reusable rule に置き換えるもの。
- onboarding または future Codex behavior に影響するもの。
- stale repository guidance を修正するもの。
- session notes または later decisions で繰り返し参照されるもの。
- `scope: global` または `scope: user` を持ち、reusable guidance へ copy すべきもの。
- `scope: mixed` で、repo 固有部分を除けば複数 repositories へ再利用できるもの。
- `promotionStatus: pending` または `promotionStatus: partial` で、global context への昇格可否が未整理のもの。
- future chats がすぐ見るべき current state を変えるもの。

次の場合、decision を promote しない。

- 1 task だけの temporary なもの。
- `Rejected`、`Deprecated`、`Superseded` であり、replacement の document 化が重要でないもの。
- broader document に広げるべきでない sensitive details を含むもの。
- target doc がすでに明確に covered しているもの。

## Global context candidate criteria

次に該当する場合、global context 候補として提案する。

- 複数 repositories で再利用できる Codex collaboration workflow。
- durable user preference または repository-independent working convention。
- context engineering、session note、decision record、working context、skill design の reusable pattern。
- repeated failed approach を避けるための negative knowledge。
- repo-local implementation detail ではなく、他 repo でも判断基準として使える principle。
- `scope: global` または `scope: user` の `Accepted` decision。
- `scope: mixed` の `Accepted` decision のうち、repo 固有情報を取り除いても価値が残る部分。

次の場合は global context 候補にしない。

- repository path、project 名、固有運用に依存し、一般化すると意味が失われるもの。
- sensitive、private、customer-specific な情報を含むもの。
- `status: Proposed` で、ユーザーが採用していないもの。ただし `candidate` として残す提案は可能。
- `promotionStatus: promoted` で `promotedTo` が現状と合っているもの。
- `promotionStatus: no-action` で、再検討理由がないもの。

global context 候補を出す場合は、次を含める。

- source decision path
- reusable essence
- repo-specific details to remove
- recommended destination class: `working-context` / `decision` / `candidate`
- suggested `promotionStatus` change after promotion
- unresolved questions or user approval needed

## Output format

review-only requests では次を使う。

```md
## Summary

## Decisions reviewed

## Recommended document updates

## Working context updates

## Reusable guidance updates

## Global context candidates

## Promotion metadata updates

## No-action decisions

## Open questions
```

edit requests では次を summarize する。

- updated files
- decisions reflected
- working context changes
- reusable guidance changes
- global context candidates or promotions
- promotion metadata changes
- decisions intentionally left unchanged
- validation performed

## Safety and style

- edits は review が示す documentation に限定。
- ユーザーが依頼しない限り、whole documents の rewrite 禁止。
- decision が明示的に変更しない限り、existing terminology の維持。
- secrets、credentials、tokens、private keys、full environment variables、large logs、不要な personal/customer data の露出禁止。
- repository instruction が別途ない限り、body は日本語。Markdown headings、paths、commands、identifiers は native form の維持。
