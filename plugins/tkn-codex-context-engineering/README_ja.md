# Tuckn Codex Context Engineering

[English](README.md) | 日本語

この plugin は、Codex が前回の作業の続きを理解しやすくするためのものです。リポジトリ
の状況、進行中の作業、重要な判断を軽量なメモとして残し、次の chat で同じ背景説明を
繰り返さずに再開できるようにします。

明示的に依頼した場合は、過去の Codex の会話ログや `~/.tkn/codex-context` に置いた
project note から役立つ内容を探せます。

## 設計思想

この plugin の目的は、chat transcript を保存すること自体ではありません。Codex Project で
生まれた一時的な会話を、再開可能な project context、長期的な decision、現在状態の
要約、project 横断の知識へ段階的に蒸留し、人間と生成 AI の両方が再利用できる形で維持する
ことです。

Context は、寿命、適用範囲、確度、用途が異なるため、1つの巨大なファイルには集約しません。
代わりに、source から durable context へ次の順序で成熟させます。

```text
Codex chat transcript
  -> project session note
  -> project decision / project working context
  -> all-project working context / global decision
  -> insight, Skill, automation, monthly review, durable note
```

この lifecycle は、raw data をそのまま current truth として扱わず、段階ごとに要約、検証、
選別する context pipeline です。

### 1. Project を登録する

最初に `init-project-context` を使い、Codex Project folder と private context store の間に
stable identity を作ります。

- Repository には、小さな `.tkn/codex-context.yaml` marker だけを置きます。
- Private な context は `~/.tkn/codex-context/state/<projectId>/` に置きます。
- Folder rename、move、別 checkout があっても、可能な限り同じ logical project identity を
  維持します。

Initialization は context lifecycle の readiness gate です。登録しただけで、session note、
decision、working context、review が自動的に生成されるわけではありません。

### 2. Chat を session note に変換する

`write-session-note` は、1つの Codex chat/thread で行った非自明な作業を、後から再開・確認できる
project-scoped record に変換します。

Session note は transcript の縮約版ではありません。次の chat が作業をやり直さずに済むための
handoff record です。

主に残すもの:

- 何を達成しようとしたか
- どこまで完了したか
- 現在の状態
- ユーザーが承認、拒否、修正した内容
- 変更した files と validation result
- 重要な decision candidates
- 有効だった方法と、再試行すべきでない failed approaches
- unresolved issues、next steps、exact next step

Session note は source に近い context であり、単独では project の current truth や durable rule
とは見なしません。

### 3. 長く残す判断を decision に昇格する

`record-decision` は、session note に含まれる判断のうち、現在の chat を超えて future human または
Codex が再利用すべきものを durable decision record にします。

Decision は architecture に限定しません。Project scope、solution、design、workflow、operation、
documentation、repository convention、collaboration process、重要な rejected alternative も対象です。

Decision record では、結論だけでなく次を明確にします。

- どの問題または trade-off に対する判断か
- 何を選択したか
- なぜその判断になったか
- 何が変わり、どのような consequence があるか
- どの alternatives を、どの根拠で採用しなかったか
- 適用範囲は project、user、global、mixed のどれか
- repository docs、working context、global context、Skill への反映が必要か

### 4. Project の current truth を working context に集約する

`write-current-working-context` は、session notes と decision records、current repository files、Git state
を材料に、その Codex Project の「今」を短い dashboard として維持します。

`working-context.md` は詳細な履歴ではなく、新しい chat が最初に読む orientation layer です。
すべての session notes や decisions を読まなくても、次を理解できることを目標にします。

- Project の目的と現在の到達点
- 現在 active な workstream
- 確定している current truth
- 重要な constraints と risks
- 最近有効になった decisions
- 再開時に読むべき key files
- 次に行う maintenance または exact resumption point

Session note が「その chat で何が起きたか」を扱うのに対し、working context は「今、何が真か」を
扱います。古くなった情報は追記で残さず、削除または置換します。

### 5. 全 Codex Project の現在状態を統合する

各 project の `working-context.md` を source of truth として、全 Codex Project の現在状態を次の
user-global dashboard に統合することを想定します。

```text
C:\tkn\home\personal\workspaces\managing\Codex\Windows\codex-context\state\working-context.md
```

この global working context は、chat transcript や全 session note を直接要約して作るものでは
ありません。各 project ですでに蒸留された current truth を集約し、project 間の関係、優先順位、
blocker、次に着手すべき work を把握するための portfolio-level dashboard です。

想定する内容:

- Active、paused、blocked、archived projects
- Project ごとの目的、status、current focus、next step
- Project 間の dependency と duplicated work
- 共通する constraints、risks、open loops
- Review または maintenance が必要な stale project context

### 6. Project を超えた知識と洞察を生成する

全 project の context を横断的に review し、project 固有情報を除いても価値が残る内容を、
user-global context に昇格することを想定します。

Global decisions の保存先:

```text
C:\tkn\home\personal\workspaces\managing\Codex\Windows\codex-context\data\decisions
```

ここに残す候補:

- 複数 project で再利用できる working convention
- Codex との collaboration rule
- Durable な user preference
- Context engineering、documentation、repository management の principle
- 繰り返し発生した failure を避ける negative knowledge
- Skill、script、template、automation に materialize すべき repeated workflow

また、過去 chat transcript を月単位で review し、Fact Extract、Insight Synthesis、Materialization
Candidates を分離した source review note を作成します。これにより、次のような問いを扱えます。

- 前月にどのような work と相談を行ったか
- 同じ質問、friction、manual operation が繰り返されていないか
- 新しい Skill または automation にすべき workflow はないか
- Project を超えて残すべき decision、preference、reference note はないか
- 未完了の open loop や maintenance debt はないか

月次 chat review は historical insight の source です。一方、全 project の「現在状態」は、各 project
の `working-context.md` から作るべきであり、両者を混同しません。

## Context layers と責務

| Layer | Primary artifact | 主な問い | 更新特性 |
|---|---|---|---|
| Source | Codex JSONL chat | 実際に何が話されたか | append-only / read-only |
| Session | `sessions/*.md` | この chat で何を行い、どう再開するか | thread ごとに更新 |
| Project decision | `decisions/DR-*.md` | 今後も守る判断は何か | durable、status 管理 |
| Project current state | `working-context.md` | この project で今何が真か | stale content を置換 |
| Global current state | user-global `state/working-context.md` | 全 project の今はどうなっているか | project dashboards から集約 |
| Global knowledge | user-global `data/decisions/` 等 | project を超えて再利用すべきものは何か | reviewed promotion |
| Insight / Materialization | monthly reviews、Skill candidates 等 | 何を改善、自動化、体系化すべきか | periodic review |

この分離により、詳細な evidence を失わずに、日常利用では小さく信頼できる context だけを読める
ようにします。

## Context 品質の原則

すべての artifact は、人間が読んで理解でき、生成 AI が機械的に抽出・比較できる必要があります。
そのため、次を重視します。

- **Current truth と history の分離:** 現在状態を chronological log に埋めない。
- **Fact、decision、inference、candidate の分離:** Assistant proposal を user-approved fact として扱わない。
- **Evidence と provenance:** 重要な判断や洞察は source session、file、validation へ辿れるようにする。
- **One artifact, one responsibility:** Session、decision、working context、review の役割を混ぜない。
- **Explicit promotion:** 下流へ反映したかを status と destination で追跡する。
- **Negative knowledge:** 実際に失敗した方法と再試行条件を残し、同じ失敗を繰り返さない。
- **Progressive compression:** 下流へ進むほど短く、一般化され、安定した内容にする。
- **Human review boundary:** Global context、Skill、automation への materialization は review と承認を経る。
- **Privacy by default:** Private paths、customer data、secrets を public repository に書かない。
- **Current evidence wins:** Current user instructions、repository files、Git state を過去 context より優先する。

## Local context と Global context

この plugin は、repo-local には小さな project marker だけを置き、private な project context は
user-global store に置きます。

- Local marker は `.tkn/codex-context.yaml` です。`projectId`、`title`、
  `description`、`createdAt`、`updatedAt` だけを持ちます。
- Project context は `~/.tkn/codex-context/state/<projectId>/` に置きます。
- User-global artifacts は `~/.tkn/codex-context/data/` に置きます。
- Project registry と state は `~/.tkn/codex-context/state/` に置きます。
- Store configuration は `~/.tkn/codex-context/config/config.yaml` です。
- Store root には現行 layout を説明する更新済み `README.md` を置きます。
- Global context への write は bundled Skill としては提供しません。

## Plugin の構成

Plugin path:

```text
plugins/tkn-codex-context-engineering/
```

Plugin manifest:

```text
plugins/tkn-codex-context-engineering/.codex-plugin/plugin.json
```

Bundled Skills:

```text
plugins/tkn-codex-context-engineering/skills/
```

Skill固有のscripts:

```text
plugins/tkn-codex-context-engineering/skills/<skill-name>/scripts/
```

複数Skillで共有するimport専用Python helper:

```text
plugins/tkn-codex-context-engineering/lib/tkn_codex_context/
```

同梱Python entry pointはbytecode cacheの書き込みを無効化します。repository内に
`__pycache__`を作らず、Python bytecodeをuser cacheへ移しません。将来
`~/.cache/net.tuckn/codex-context`を使う場合は、再生成可能なapplication data専用とします。

## 含まれる Skills

含まれる Skills は、context lifecycle 上の役割ごとに分類しています。

### プロジェクト登録と現在の状況維持

- `init-project-context`:
  - repository の Codex project identity を初期化または更新し、小さな local marker
    `.tkn/codex-context.yaml` と private な user-global project registry に保存します。
- `read-current-working-context`:
  - 登録済み current project の `working-context.md` を、新しい chat、project 状況確認、resume、
    handoff のための read-only orientation として読みます。
- `write-current-working-context`:
  - `~/.tkn/codex-context/state/<projectId>/working-context.md` を project の現在状態を示す
    lightweight dashboard として作成または更新します。

### 作業記録と再開

- `write-session-note`:
  - 非自明な作業、handoff、resumable task のために project `sessions/` の簡潔な note を作成
    または更新します。
- `resume-session`:
  - 新しい session record を重複作成せず、既存の session note を新しい chat で継続します。

### 長く残す判断と見直し

- `record-decision`:
  - 現在の chat を超えて残すべき判断を project `decisions/` 配下の durable decision record
    として記録します。
- `review-decisions`:
  - decision records を review し、repository document updates、working-context changes、
    reusable guidance candidates を洗い出します。

### このPCにある全projectのchat履歴の検索・review・要約

- `search-all-codex-chats`:
  - このPC上の全projectにまたがる Codex JSONL chat履歴を検索し、過去の会話、判断、
    outcome に関する問い合わせへ、見つかった根拠を使って回答します。
- `refresh-project-context-from-chats`:
  - 登録済み current project に属する Codex chat履歴をscanし、threadごとのsession note、
    durable decision、working-context dashboardを順番に最新化します。初回は全対象chat、
    2回目以降は新規またはsource fingerprintが変わったchatだけを処理します。
- `review-all-codex-chats`:
  - `~/.codex/sessions` にある、このPC上の全projectのCodex chat履歴を review し、
    `~/.tkn/codex-context/data/session-reviews` に月間 source review note を作成します。
- `distill-session-context`:
  - session note を短い reusable-context review candidate に distill し、review 後に
    distillation metadata を finalize します。

### Context の鮮度管理と思考メモの整理

- `audit-context-freshness`:
  - repo-local または global context の stale metadata、pending distillation / promotion、
    再利用リスクを監査します。
- `organize-brain-dump`:
  - rough notes、idea dump、相談メモを整理し、既定では project `memos/` 配下の structured
    Markdown advice に変換します。chat や repository instructions で保存場所が指定された
    場合は、その指示を優先します。

## 発動モデル

Project 初期化は readiness gate であり、自動発動の trigger ではありません。

- Skill は、ユーザーの意図がその Skill に一致した場合に使います。
- 新しい chat で project orientation が必要な場合は `read-current-working-context` を使います。
  登録済みという理由だけで dashboard を自動的に読みません。
- Project-scoped な context を読んだり書いたりする Skill では、現在の repository が意図的に
  登録済みであることも必要です。つまり `.tkn/codex-context.yaml` が存在し、その
  `projectId` が `~/.tkn/codex-context/state/index.jsonl` で現在の workspace に解決できる
  状態です。
- `.tkn/codex-context.yaml` が作成されただけで、session note、decision、
  working-context update、chat-history refresh、distillation、review、audit は開始しません。
- 未登録の状態で project-scoped Skill が必要になった場合は、`init-project-context` を
  案内します。初期化を実行するのは、ユーザーが initialize、move、project context 更新を
  明示的に依頼した場合だけです。
- `init-project-context` は readiness gate を作成または修復するため、未登録状態でも使えます。
- runtime や working folder の方針は Skill として bundle しません。必要な場合は、その
  project folder ごとの指示で都度指定します。
