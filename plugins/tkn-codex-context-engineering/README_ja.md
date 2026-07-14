# Tuckn Codex Context Engineering

[English](README.md) | 日本語

この plugin は、Codex が前回の作業の続きを理解しやすくするためのものです。リポジトリ
の状況、進行中の作業、重要な判断を軽量なメモとして残し、次の chat で同じ背景説明を
繰り返さずに再開できるようにします。

明示的に依頼した場合は、過去の Codex の会話ログや `~/.tkn/codex-context` に置いた
project note から役立つ内容を探せます。

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

Context bridge scripts:

```text
plugins/tkn-codex-context-engineering/scripts/context_bridge/
```

## 含まれる Skills

含まれる Skills は、context lifecycle 上の役割ごとに分類しています。

### プロジェクト登録と現在の状況維持

- `init-project-context`:
  - repository の Codex project identity を初期化または更新し、小さな local marker
    `.tkn/codex-context.yaml` と private な user-global project registry に保存します。
- `maintain-working-context`:
  - `~/.tkn/codex-context/state/<projectId>/working-context.md` を active project context の
    lightweight dashboard として保守します。

### 作業記録と再開

- `maintain-session-note`:
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

### 過去 session の復元と要約

- `extract-codex-sessions`:
  - local Codex JSONL session logs から、themes、questions、decisions、outcomes、project history
    を抽出します。
- `review-codex-chats`:
  - `~/.codex/sessions` の local Codex session logs を review し、
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
- Project-scoped な context を読んだり書いたりする Skill では、現在の repository が意図的に
  登録済みであることも必要です。つまり `.tkn/codex-context.yaml` が存在し、その
  `projectId` が `~/.tkn/codex-context/state/index.jsonl` で現在の workspace に解決できる
  状態です。
- `.tkn/codex-context.yaml` が作成されただけで、session note、decision、
  working-context update、distillation、review、audit は開始しません。
- 未登録の状態で project-scoped Skill が必要になった場合は、`init-project-context` を
  案内します。初期化を実行するのは、ユーザーが initialize、move、project context 更新を
  明示的に依頼した場合だけです。
- `init-project-context` は readiness gate を作成または修復するため、未登録状態でも使えます。
- runtime や working folder の方針は Skill として bundle しません。必要な場合は、その
  project folder ごとの指示で都度指定します。
