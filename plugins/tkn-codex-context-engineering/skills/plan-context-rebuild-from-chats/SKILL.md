---
name: plan-context-rebuild-from-chats
description: Registry に登録された全 Codex Project と、Windows・WSL・archive など複数の Codex JSONL sessions source を照合し、既存 artifact の棚卸し、Project への直接割当、承認が必要な historical root 候補、未解決・未解析 log を読み取り専用の再構築 plan にする。全 Project の古い private context を chat 履歴から作り直す前の調査、移行計画、dry-run を依頼された場合に使う。Project context 自体は変更しない。
---

# Plan Context Rebuild From Chats

複数の Codex chat archive から全登録 Project の context を再構築する前に、source と割当結果を読み取り専用で棚卸しする。

## Boundary

- `~/.tkn/codex-context/state/index.jsonl` を対象 Project の正本とする。
- Source JSONL、既存 session note、decision、working context、refresh state を変更しない。
- この Skill が書くのは、ユーザーが指定した plan JSON だけ。
- 実際の artifact 再構築は plan の確認と root alias の承認後に別工程で行う。
- Current Project 1件の通常更新には `refresh-project-context-from-chats` を使う。

## Preflight

1. Registry と登録 Project 数を確認する。
2. Source archive ごとに安定した source ID を決める。通常は `windows` と `wsl`。
3. Output は OS temp または明示された private path に置く。Public repository へ実データを保存しない。
4. 本 Skill の `scripts/plan_context_rebuild_from_chats.py` を使う。

## Run

Windows sessions だけなら default source を利用できる。

```powershell
python -B <skill-root>/scripts/plan_context_rebuild_from_chats.py `
  --output "$env:TEMP\codex-context-rebuild-plan.json"
```

複数 archive は `--sessions-source ID=PATH` を繰り返す。

```powershell
python -B <skill-root>/scripts/plan_context_rebuild_from_chats.py `
  --sessions-source "windows=<windows-sessions-root>" `
  --sessions-source "wsl=<wsl-sessions-root>" `
  --output "$env:TEMP\codex-context-rebuild-plan.json"
```

Plan は次を区別する。

- `assignedSessions`: 承認済み root と一致した直接割当。
- `repositoryCandidates`: Git repository URL は一意に一致するが、root 承認が必要な候補。
- `unresolvedSessions`: 一致なし、または複数 Project に一致した source。
- `candidateRootSummary` / `unresolvedRootSummary`: review 用に cwd、reason、件数、期間を
  集約した一覧。
- `unparsedFiles`: 対応する session metadata を解析できなかった source。
- `duplicateThreadIds`: source をまたいで同じ thread ID が存在するケース。

## Approve historical roots

Repository candidate を自動採用しない。候補の `cwd`、Project、件数をユーザーへ提示する。承認された root だけを plan の再実行時に指定する。

```powershell
python -B <skill-root>/scripts/plan_context_rebuild_from_chats.py `
  --sessions-source "windows=<windows-sessions-root>" `
  --sessions-source "wsl=<wsl-sessions-root>" `
  --project-root-alias "<project-id>=<approved-historical-root>" `
  --output "$env:TEMP\codex-context-rebuild-plan-approved.json"
```

`/mnt/c/...` と `C:\...` は照合上同じ path として扱う。別 drive letter、別 repository、Git URLだけが同じ root は明示承認なしに同一視しない。

## Review

次をユーザーへ報告する。

- Registered Projects、source files、parsed/unparsed counts。
- Direct assignments、repository candidates、unresolved sessions。
- Source ごとの provenance を確認するための `sourceId/sourceRef`。
- Existing artifact の kind と schemaVersion の棚卸し。
- Duplicate thread IDs と、承認が必要な root aliases。

承認後も、いきなり既存 state を上書きしない。Shadow destination へ v2 artifact を生成し、件数、代表サンプル、機密情報混入、link、schema を検証してから切替工程を提案する。

## Materialize a shadow draft

Root alias と unresolved scope のreviewが完了したplanだけを使う。新規のshadow rootを指定し、
live context storeやsessions sourceの内側をoutputにしない。

```powershell
python -B <skill-root>/scripts/materialize_context_rebuild_shadow.py `
  --plan "$env:TEMP\codex-context-rebuild-plan-confirmed.json" `
  --output-root "<new-shadow-root>"
```

Materializerは次だけを作る。

- Assigned threadごとのschema v2 session note。
- Projectごとのschema v2 `working-context.md` shadow draft。
- 明示的な承認表現をreview用に集めた `decision-candidates.json`。
- 件数とreview gateを持つ `shadow-manifest.json`。

Assistantの報告をcurrent truthとして確定せず、working contextは`status: stale`、decision candidate
は`unclear`とする。Decision recordは自動作成しない。Current repository evidenceとの照合後に、
acceptedでdurableな候補だけを`record-decision`でschema v2へ昇格する。

生成後は全artifactを読み取り専用で再検証する。

```powershell
python -B <skill-root>/scripts/materialize_context_rebuild_shadow.py `
  --plan "$env:TEMP\codex-context-rebuild-plan-confirmed.json" `
  --output-root "<existing-shadow-root>" `
  --validate-only
```

## Safety

- Full message text、secret、credential、private key を plan に複製しない。
- Plan には metadata と source reference だけを含める。
- Registry にない Project を推測で追加しない。
- Git repository URL 一致だけで Project を確定しない。
- Source ID を省略して複数 archive を混ぜない。
- Existing output rootを上書き、merge、削除しない。
