---
name: write-session-note
description: 登録済み current project の projectId-specific state sessions folder に、chat で確認できる request、correction、action、result、validation、last known state を source-near に整理した session note を作成または更新する。元 chat を読み直さない resume や、後続の semantic distillation に使える事実記録が必要で、`.tkn/codex-context.yaml` が private registry で現在 workspace に解決できる場合に使う。marker 生成だけでは使わない。
---

# Write Session Note

chat/thread の事実を、元 chat より短く、元 chat にない意味を足さない形で残すために、この skill を使う。

session note は完成された handoff、decision record、working context ではない。source chat に近い factual digest である。future human または Codex が会話全体を読み直さず、何が依頼され、何が変わり、最後にどの状態だったかを把握できることを目指す。

durable decision candidate の判定、project current truth の選別、rationale や exact next step の補完は、この skill では行わない。必要なら `distill-session-context` で事実をレビューし、`record-decision` または `write-current-working-context` へ昇格する。

## Activation Gate

次の両方を満たす場合だけ実行する。

- ユーザー意図が、非自明な作業記録、resume 可能な記録、chat の記録依頼、handoff、context compaction、または後続 distillation のための事実保存に一致する。
- 現在の repository に `.tkn/codex-context.yaml` があり、その `projectId` が `~/.tkn/codex-context/state/index.jsonl` で現在の workspace に解決できる。

marker が存在する、または直前に生成された、という事実だけでは発動しない。未登録または registry 解決不能の場合は session note を作成せず、`init-project-context` を案内する。登録を実行するのはユーザーが明示的に依頼した場合だけにする。

## File Location

chat/thread ごとに 1 file を作成または更新する。

`~/.tkn/codex-context/state/<projectId>/sessions/YYYYMMDDTHHMMSS<system-timezone-offset>-<task-purpose-slug>.md`

- OS/system clock の timestamp と timezone offset を使う。ただし repository instruction が別途ある場合はそちらを優先する。
- task purpose から短い kebab-case English slug を作る。
- 自動生成 pipeline では本文 title と独立した `fileSlug` を生成し、3～72文字の lowercase
  ASCII kebab-case として検証する。日本語 title が filename fallback に変換される設計にはしない。
- 同じ chat/thread では同じ session note を継続更新する。
- ユーザーが session note path を指定した場合、その file だけを読み更新する。
- current project は private registry から解決する。未登録の場合は自動登録しない。
- project `working-context.md` があり、今回の task に関係する current truth を含む可能性がある場合だけ確認する。

## When To Create

次のいずれかに該当する場合、作成または更新する。

- 非自明な file changes、investigation、analysis、classification、design、review がある。
- 複数 turn にまたがる、または別 chat から再開する可能性がある。
- user correction、重要な制約、判断、validation result を後で確認する価値がある。
- ユーザーが chat の記録を明示的に依頼した。
- handoff、compaction、長い中断、task switching が見込まれる。

simple one-off answer、state を残さない trivial check、future reference value のない casual discussion では通常作成しない。ユーザーの明示指示を優先する。

## Information Boundary

記録できるのは、次の source で確認できる事実に限る。

1. ユーザーの発言。
2. tool output、file content、test result、実際の repository state。
3. assistant が実行した action と、その観測可能な結果。
4. assistant proposal のうち、proposal であることを明示したもの。

source の強さを混同しない。

- ユーザーが承認した内容は `Explicit Decision` としてよい。
- assistant が提案しただけの内容は、承認済み decision として書かない。
- tool が成功を報告した場合は `Validation` または `Reported Result` としてよい。
- 未確認の推測は、必要な場合だけ `Source Notes` に uncertainty として書く。
- chat から一意に読めない purpose、done condition、rationale、priority、exact next step を補完しない。

## Required Structure

本文の必須 section は 3 つだけとする。

```md
---
type: session
schemaVersion: 2
title: <session-title>
description: <short factual summary>
generator: Codex
status: in-progress
distillationStatus: pending
distilledTo: []
date: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
updated: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
sessionId: YYYYMMDDTHHMMSS<system-timezone-offset>
---

# Session Note

## Summary

<何について、何が行われ、最後にどうなったかを 1～5 bullets で記録する>

## Key Developments

### Request

- <ユーザーが依頼したこと>

### Action

- <実際に行ったこと>

### Reported Result

- <観測または報告された結果>

## Last Known State

- Work State: <done | in-progress | blocked | waiting-for-user と、その根拠になる短い事実>
- Latest User Direction: <最後に確認できるユーザー指示。なければ「追加指示なし。」>
```

`Summary`、`Key Developments`、`Last Known State` は省略しない。必須 section の中に該当事実がない場合は、推測せず `確認できる記録なし。` とする。

本文冒頭に `Session:`、`Task:`、`Status:`、`Last updated:` は置かない。machine-readable metadata は Frontmatter に集約する。

### Key Developments Labels

各 label を heading とし、その配下に該当する facts を箇条書きで置く。1つの label に複数の fact を置いてよい。該当 fact がない label は省略する。

- `Request`: ユーザーが求めた作業、質問、変更。
- `Clarification / Correction`: ユーザーが追加した条件、訂正、方向転換。
- `Proposal`: assistant が提示したが、実行または承認が確認されていない案。later correction や decision の理解に必要な場合だけ残す。
- `Action`: 実際に行った調査、編集、実行。
- `Reported Result`: action や外部作業の結果として報告・観測された事実。test や check の成否だけなら `Validation` を使い、同じ結果を重複させない。
- `Validation`: test、check、inspection とその結果。
- `Explicit Decision`: ユーザーが明示承認・採用・拒否した判断、または source が decision として明示している既存判断。実装されたという事実だけなら `Action` または `Reported Result` とする。

同じ事実を複数 label で重複させない。later direction が earlier request を置き換えた事実は通常 `Clarification / Correction`、chat を超えて参照する必要がある明示判断は `Explicit Decision` を選ぶ。

単一 work item では、各 label を `Key Developments` 直下の H3 にする。

```md
## Key Developments

### Request

- <fact 1>
- <fact 2>

### Action

- <fact>
```

時系列 transcript を再現する必要はない。ただし、後の correction が前の request や proposal を上書きした場合は、その変化を落とさない。最終状態だけでは誤解を生む場合に限り、前後関係を短く残す。

### Multiple Work Items

1つの chat に独立した work item が複数ある場合、`Key Developments` を H3 で分ける。

```md
## Key Developments

### WI-01: <short title>

#### Request

- ...

#### Action

- ...

#### Reported Result

- ...

### WI-02: <short title>

#### Request

- ...

#### Clarification / Correction

- ...

#### Validation

- ...
```

複数 work item では work item を H3、各 label を H4 にする。単一 work item では `WI-NN` を付けない。別 topic でも相互依存が強い場合は無理に分けない。

### Last Known State Fields

- `Work State`: Frontmatter `status` と整合する短い事実。すべての明示 request の実行結果を確認でき、known unresolved item がなければ `done` としてよい。複数 work item の1つでも material な未完了作業が残れば、全体は `in-progress`、`blocked`、`waiting-for-user` の該当状態にする。user acceptance 自体が request に含まれる場合を除き、完了判定のためだけに追加承認を推測または要求しない。
- `Latest User Direction`: 最後に有効なユーザー指示、制約、承認、拒否。作業済みでも最後の指示は残す。source にユーザー指示がない場合だけ `追加指示なし。` とする。assistant の提案で代用しない。
- `Unresolved`: 未回答の質問、未確認事項、blocker が実際に残っている場合だけ追加する。
- `Unverified`: 明示 request は完了しているが、今回の依頼範囲外だった実環境確認や外部確認を
  区別して残す場合だけ追加する。`Unverified` だけを理由に `status: done` を変更しない。
- `Continuation Point`: chat が継続中で、次に着手する対象が明示または作業状態から直接確認できる場合だけ追加する。推奨 next step を新しく考案しない。

`status: done` の note に `Unresolved` または `Continuation Point` を置かない。未完了の
explicit request がある場合は `in-progress`、`blocked`、`waiting-for-user` のいずれかにする。

## Optional Sections

material な内容がある場合だけ追加する。空 section や `なし。` のために追加しない。

### Evidence

変更 file、参照 source、command、test、check など、summary や result を後で確認するために必要な evidence を短く記録する。

```md
## Evidence

- Changed: `project:/path/to/file`
- Validation: `<check>` — <result>
- Source: `project:/path/to/source`
```

full logs や長い引用は貼らない。public repository の session fixture や sample では private absolute path を使わない。

### Source Notes

source の欠落、conflict、uncertainty、復元時の制約など、note の読み方に影響する注意だけを書く。

```md
## Source Notes

- <どの事実が未確認か、どの source が欠けているか>
```

一般的な commentary、assistant の retrospective、昇格先の提案を書く場所にはしない。

## Frontmatter Policy

- `type`: 必ず `session`。
- `schemaVersion`: 新規 note は必ず `2`。Frontmatter と本文構造の契約を表す。
- `title`: 作業内容を scan できる短い表示名。
- `description`: 1～2文の factual summary。後から判定できない intent を補わない。
- `generator`: 必ず `Codex`。
- `status`: `in-progress`、`blocked`、`waiting-for-user`、`done` のいずれか。
- `reviewStatus`: JSONL chat から自動生成または自動更新した note は必ず `unreviewed`。自動更新時は以前の値にかかわらず `unreviewed` に戻す。通常の current chat から直接作成する note では必須にしない。
- `distillationStatus`: `pending`、`partial`、`distilled`、`no-action` のいずれか。
- `distilledTo`: 未反映なら `[]`。反映済みなら同じ project context folder 内の relative path を優先する。
- `date`: note の生成日時。既存 note で不明な場合は filename timestamp を ISO 8601 へ変換する。
- `updated`: 本文または Frontmatter を更新した日時。更新時に必ず変える。
- `sessionId`: filename 先頭の `YYYYMMDDTHHMMSS<system-timezone-offset>`。

`status` は作業状態だけを表す。事実が downstream artifact に取り込まれたかは `distillationStatus` と `distilledTo` で表す。

### Codex Chat Provenance

Codex JSONL chat から再構築または対応付ける場合、次の optional Frontmatter を追加する。

```yaml
reviewStatus: unreviewed
sourceType: codexChat
sourceThreadIds:
  - <thread-id>
sourceRefs:
  - YYYY/MM/DD/rollout-....jsonl
```

- `sourceThreadIds`: source になった Codex thread IDs。通常は1件。明示的な継続関係がある場合だけ複数を許可する。
- `sourceRefs`: Codex sessions root からの相対 JSONL paths。absolute path は書かない。
- reconstructed note の `date` と filename timestamp は source chat 開始時刻を system timezone に変換した値。
- reconstructed note の `updated` は reconstruction または refresh の実行時刻。
- 自動生成 pipeline は `generatorModel`、`generatorReasoningEffort`、
  `generatorPromptVersion`、`rendererVersion`、`generatedAt`、`fileSlug`、
  `automatedValidation`、`sourceFingerprint` を追加し、生成方式と検証済みsourceを追跡する。
  `reviewStatus: unreviewed` はhuman reviewの有無だけを表し、`automatedValidation`と混同しない。
- direct chat で通常作成する note では必須にしない。
- 既存 note に provenance fields がある場合、通常更新で削除しない。

## Writing Workflow

1. current project と output file を解決する。
2. user messages、relevant assistant actions、tool results、必要な current files から material facts を集める。
3. 独立 work item が複数あるか判定する。
4. `Summary` に全体像、`Key Developments` に source-backed facts、`Last Known State` に最後の有効状態を書く。
5. 後で検証に必要な evidence または source limitation がある場合だけ optional section を加える。
6. goal、rationale、decision、done condition、next step を推測していないか確認する。
7. Frontmatter status と `Last Known State / Work State` の整合を確認する。
8. meaningful checkpoint、handoff、compaction、completion 時に同じ note を更新する。

更新時は古い事実を機械的に追記し続けない。現在の理解に必要な request、correction、action、result を保ち、重複を統合する。過去の記述が user correction により無効になった場合、無効な事実を current truth として残さない。

## Downstream Boundary

session note は downstream promotion の evidence source であり、promotion result そのものではない。

- resume では `Summary`、`Key Developments`、`Last Known State` と必要な evidence を読み、元 chat を読む前に作業状態を復元する。
- `distill-session-context` は複数の factual item を比較し、decision candidate、current truth candidate、reusable learning、follow-up を semantic に分類する。
- `record-decision` は採用された decision、rationale、applicability、consequences を別 artifact として作る。
- `write-current-working-context` は複数 source と現在の repository state を照合し、project current truth だけを反映する。

session note 内に promotion-ready field を無理に作らない。下流が判断できるよう、誰が何を述べ、何が実行され、何が確認されたかを正確に残す。

## Safety And Style

- full conversation transcript、full logs、long quotes を貼らない。
- secrets、credentials、tokens、private keys、full environment variables、large logs、不要な personal/customer data を記録しない。
- confirmed fact、reported fact、proposal、uncertainty を混同しない。
- assistant proposal を user approval に昇格しない。
- exact next step、rationale、done condition、priority を source なしで生成しない。
- resume のために context store 全体を読まない。指定 note と narrowly relevant files だけを読む。
- `working-context.md` は dashboard として扱い、detailed session log にしない。
- repository instruction が別途ない限り本文は日本語とし、headings、paths、commands、identifiers は native form を保つ。
- 日本語で自然に説明できる語を、`supplied events`、`actual execution`、`durable context`
  などの英語句のまま本文へ残さない。literal identifier、command、path、product name だけを
  必要に応じて原文のまま保つ。
