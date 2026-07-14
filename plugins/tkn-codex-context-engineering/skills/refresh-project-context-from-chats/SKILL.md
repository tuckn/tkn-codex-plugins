---
name: refresh-project-context-from-chats
description: 登録済み current project に属する Codex JSONL chat 履歴を初回は全件、以後は差分で読み、thread ごとの session note、durable decision records、working-context.md を順番に作成または最新化する。ユーザーが chat 履歴から project context を refresh、sync、再構築、取りこぼし補完したい場合に使う。旧 project root は候補確認後だけ対象へ加え、project marker の生成だけでは使わない。
---

# Refresh Project Context From Chats

Codex chat 履歴を source evidence として、登録済み project の private context を再構築または最新化する。

## Activation gate

次の両方を満たす場合だけ実行する。

- ユーザーが project context の refresh、sync、再構築、または取りこぼし補完を依頼している。
- Current repository の `.tkn/codex-context.yaml` が `~/.tkn/codex-context/state/index.jsonl` で現在 workspace に解決できる。

未登録または registry 解決不能の場合は何も作成せず、`init-project-context` を案内する。自動初期化しない。

## Source and state

- Source root は `$CODEX_HOME/sessions`。`CODEX_HOME` 未設定時は `~/.codex/sessions`。
- Source JSONL は read-only とし、編集、移動、削除しない。
- 差分 state は `~/.tkn/codex-context/state/<projectId>/chat-refresh-state.json`。
- Scan output と result JSON は OS temp に置く。repository `.local/` を作らない。

## Preflight

1. Repository instructions と current files の確認。
2. この Skill と同じ `skills/` directory にある次の3ファイルを完全に読む。
   - `write-session-note/SKILL.md`
   - `record-decision/SKILL.md`
   - `write-current-working-context/SKILL.md`
3. `scripts/refresh_project_context_from_chats.py scan` を実行する。
4. `historicalRootCandidates` がある場合、root、理由、session count を提示し、承認または拒否を確認する。確認前に project context を変更しない。
5. 承認後は `--approve-root`、拒否後は `--reject-root` を付けて scan を再実行する。

Typical scan:

```powershell
python <skill-root>/scripts/refresh_project_context_from_chats.py scan `
  --repo-root . `
  --output "$env:TEMP\refresh-project-context-from-chats\scan.json"
```

初回は対象全履歴が `new` になる。通常の再実行では `new` と `changed` だけを処理する。全件再評価を明示された場合だけ `--full` を使う。

## Read one source thread

対象 thread を1件ずつ時系列に処理する。全文が必要な thread だけを絞り、project に属する turn のみを出力する。

```powershell
python <skill-root>/scripts/refresh_project_context_from_chats.py scan `
  --repo-root . `
  --thread-id <thread-id> `
  --include-messages `
  --output "$env:TEMP\refresh-project-context-from-chats\thread.json"
```

Approval-review、known internal thread、cleaned user message のない session は対象外とする。複数 cwd を含む thread では、承認済み root に属する turn だけを材料にする。

## Reconcile session notes

各対象 thread を session note へ対応付ける。

1. Existing `sourceThreadIds` の exact match を優先。
2. 次に source timestamp、goal、changed files、重要判断の一致を比較。
3. High-confidence match の場合だけ existing note を更新し、provenance を追加。
4. 不確実な場合は上書きも新規作成もせず、確認対象として報告。
5. Match がなければ、source chat 開始時刻を system timezone に変換した timestamp で新規 note を作成。

原則は 1 Codex thread = 1 session note。既存 `resume-session` の明示的な継続関係が確認できる場合だけ、複数 thread を同じ note に関連付けてよい。

Chat 由来の note には次の optional Frontmatter を付ける。

```yaml
sourceType: codexChat
sourceThreadIds:
  - <thread-id>
sourceRefs:
  - YYYY/MM/DD/rollout-....jsonl
```

- `sourceRefs` は sessions root 相対 path のみ。
- `date` と filename timestamp は source chat 開始時刻。
- `updated` は refresh 実行時刻。
- 軽微な chat も最小 note を作成し、反映先がなければ `distillationStatus: no-action`。
- Current files と Git state が過去 chat と矛盾する場合、current state を正とする。

## Reconcile decisions

Session notes の後に decision records を処理する。

- Existing decisions と central decision の意味で重複排除する。
- User が明示承認した、または current files で実装済みと確認できる decision だけを `Accepted` にする。
- Assistant proposal だけなら `Proposed`。
- Durable でない implementation detail や unresolved brainstorming は session note に残す。
- New decision は next available `DR-NNNN` を使い、関連 session note を `Related files` に記載。

## Update working context

全 session notes と decisions の処理後に1回だけ更新する。

- Current repository files、Git state、Accepted decisions を優先。
- Chronological log ではなく current truth dashboard として保つ。
- 新しい note/decision への相対 link を追加し、stale facts を削除または置換。
- 実質的な current truth change がなければ file と `updated` を変更しない。

## Commit refresh state

成功した thread だけを result JSON に書く。

```json
{
  "processed": [
    {
      "threadId": "<thread-id>",
      "fingerprint": "<fingerprint-from-scan>",
      "sessionNotes": ["sessions/<note>.md"],
      "decisionIds": ["DR-0001"]
    }
  ]
}
```

Materialization と確認が完了した後だけ commit する。

```powershell
python <skill-root>/scripts/refresh_project_context_from_chats.py commit `
  --repo-root . `
  --scan "$env:TEMP\refresh-project-context-from-chats\scan.json" `
  --result "$env:TEMP\refresh-project-context-from-chats\result.json"
```

Commit は source fingerprint を再検証し、成功分だけ state へ atomic に反映する。Source が scan 後に変化、消失、または result が不正な場合は state を更新しない。

## Completion report

次を簡潔に報告する。

- Scanned、new、changed、unchanged session counts。
- Created/updated session notes と decisions。
- Working context の変更有無。
- Approved/rejected/pending historical roots。
- Ambiguous matches、failed threads、次回再処理対象。

変更対象がゼロなら、project context files と timestamp を変更せず no-op と報告する。

## Safety

- Full transcripts、large tool outputs、secrets、credentials、tokens、private keys、不要な personal/customer data を project context に複製しない。
- Public repository files に real local roots、private chat text、state values を書かない。
- Source logs の assistant output を user-confirmed fact として扱わない。
- Removed source logs に対応する notes や state entries を自動削除しない。
