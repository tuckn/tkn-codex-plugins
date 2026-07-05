# Tuckn Codex Context Engineering

[English](README.md) | 日本語

この plugin は、Codex が前回の作業の続きを理解しやすくするためのものです。リポジトリ
の状況、進行中の作業、重要な判断を軽量なメモとして残し、次の chat で同じ背景説明を
繰り返さずに再開できるようにします。

明示的に依頼した場合は、過去の Codex の会話ログから役立つ内容を探したり、
`~/.codex-context` に置いた private な共通メモを読み込んだりできます。

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

- `register-project-context`: repository の Codex project identity を登録または更新し、
  小さな local marker `.codex-context/project.yaml` と private な user-global
  project registry に保存します。
- `migrate-local-project-context`: legacy な repo-local `.codex-context` の
  working context、sessions、decisions を private project context folder に移動します。
- `use-project-working-root`: Python / Node.js の runtime files を project folder に置くか、
  private な `.codex-working` project root に置くかを判定し、private root を使う場合は
  project `AGENTS.md` に短い reminder を残します。
- `maintain-working-context`: `~/.codex-context/projects/<projectId>/working-context.md` を
  active project context の lightweight dashboard として保守します。

### 作業記録と再開

- `maintain-session-note`: 非自明な作業、handoff、resumable task のために project
  `sessions/` の簡潔な note を作成または更新します。
- `resume-session`: 新しい session record を重複作成せず、既存の session note を新しい chat
  で継続します。

### 長く残す判断と見直し

- `record-decision`: 現在の chat を超えて残すべき判断を project `decisions/` 配下の
  durable decision record として記録します。
- `review-decisions`: decision records を review し、repository document updates、
  working-context changes、global-context promotion candidates を洗い出します。

### 過去 session の復元と要約

- `extract-codex-sessions`: local Codex JSONL session logs から、themes、questions、
  decisions、outcomes、project history を抽出します。
- `review-codex-chats`: `~/.codex/sessions` の local Codex session logs を review し、
  `~/.codex-context/session-reviews` に月間 source review note を作成します。
- `distill-session-context`: session note を短い reusable-context review candidate に
  distill し、review 後に distillation metadata を finalize します。

### Global context の読み込みと昇格

- `import-global-context`: 選択した user-global Codex context を現在の task に読み込みます。
  既定では read-only で扱い、snapshot 作成は明示依頼時だけ行います。
- `promote-global-context`: project context から再利用可能な学びを抽出し、private な
  user-global context store に promote します。

### Context の鮮度管理と思考メモの整理

- `audit-context-freshness`: repo-local または global context の stale metadata、pending
  distillation / promotion、再利用リスクを監査します。
- `organize-brain-dump`: rough notes、idea dump、相談メモを整理し、既定では project
  `memos/` 配下の structured Markdown advice に変換します。chat や repository instructions
  で保存場所が指定された場合は、その指示を優先します。

## Local context と Global context

この plugin は、repo-local には小さな project marker だけを置き、private な project context は
user-global store に置きます。

- Local marker は `.codex-context/project.yaml` です。`projectId`、`title`、
  `description`、`createdAt`、`updatedAt` だけを持ちます。
- Project context は `~/.codex-context/projects/<projectId>/` に置きます。
- User-global context は `~/.codex-context` に置きます。
- Global context の読み込みは、既定では read-only にします。
- Snapshot import や global promotion は、明示的に依頼された場合だけ行います。

## 発動モデル

Project 登録は readiness gate であり、自動発動の trigger ではありません。

- Skill は、ユーザーの意図がその Skill に一致した場合に使います。
- Project-scoped な context を読んだり書いたりする Skill では、現在の repository が意図的に
  登録済みであることも必要です。つまり `.codex-context/project.yaml` が存在し、その
  `projectId` が `~/.codex-context/projects/index.jsonl` で現在の workspace に解決できる
  状態です。
- `.codex-context/project.yaml` が作成されただけで、session note、decision、
  working-context update、distillation、review、import、promotion、audit は開始しません。
- 未登録の状態で project-scoped Skill が必要になった場合は、`register-project-context` を
  案内します。登録を実行するのは、ユーザーが register、migrate、move、project context 更新を
  明示的に依頼した場合だけです。
- `register-project-context` と `migrate-local-project-context` のような入口 Skill は、
  readiness gate を作成または修復するため、未登録状態でも使えます。
- `use-project-working-root` のような runtime setup Skill は、project folder が同期対象外の
  software Git repository で、環境定義と ignore rules が揃っている場合だけ project folder
  自体を使います。それ以外では登録済み projectId に基づく private `.codex-working` root を
  使います。
