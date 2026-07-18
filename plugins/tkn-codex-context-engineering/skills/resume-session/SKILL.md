---
name: resume-session
description: 新しい chat で既存の projectId-specific sessions note またはユーザー指定の explicit session note を継続対象として指定し、その chat では新規 session note を作成せず指定 session note を更新する。resume、continue、継続、再開、引き継ぎ、session path/name 指定で使う。current project から解決する場合は `.tkn/codex-context.yaml` が private registry で現在 workspace に解決できることが必要で、marker 生成だけでは使わない。
---

# Resume Session

新しい chat で既存 session note の続きを行うために、この skill を使う。

目的は、作業状態を別 session note に分散させず、指定された project `sessions/*.md` をこの chat の canonical session note として継続更新することだ。

## Activation Gate

この skill は、ユーザーが既存 session note の resume、continue、継続、再開、引き継ぎを依頼した場合だけ使う。

ユーザーが完全な session note path を指定した場合、その file を明示 source として扱える。filename、basename、または「最新の session」のように current project から解決する場合は、現在の repository に `.tkn/codex-context.yaml` があり、その `projectId` が `~/.tkn/codex-context/state/index.jsonl` で現在の workspace に解決できる必要がある。

`.tkn/codex-context.yaml` が存在する、または直前に生成された、という事実だけではこの skill を発動しない。未登録または registry 解決不能の場合は自動登録せず、明示 path の指定または `init-project-context` を案内する。

## Command shape

ユーザーは次のように指定できる。

```text
$resume-session ~/.tkn/codex-context/state/<projectId>/sessions/YYYYMMDDTHHMMSS+0900-task.md
$resume-session YYYYMMDDTHHMMSS+0900-task
$resume-session YYYYMMDDTHHMMSS+0900-task.md
$resume-session
```

自然文で「この session を継続」「この session note の続き」「最新の session を再開」などと依頼された場合も、この skill を使う。

## Session resolution

1. ユーザーが path を指定した場合、その file だけを読む。
2. ユーザーが filename または basename を指定した場合、`~/.tkn/codex-context/state/index.jsonl` から current project context folder を解決し、その `sessions/` 直下の filename として解決する。
3. `.md` が省略されている場合、`.md` を補って解決する。
4. ユーザーが session file を指定しなかった場合、current project `sessions/*.md` のうち Frontmatter `updated` が最も新しい session note を選ぶ。
5. `updated` がない、Frontmatter が壊れている、または日時 parse ができない file は、fallback として filesystem mtime を使って並べる。
6. 最新候補が複数あり一意に決められない場合だけ、候補を短く示してユーザーに確認する。
7. 解決のためだけに session note の本文を全探索しない。未指定時に読むのは Frontmatter と file metadata だけにする。

Project `sessions/` 全体を理解目的で読まない。読むのは指定 session note と、必要な場合の project `working-context.md`、および指定 session note から明示的に参照された relevant files だけにする。

## Resume workflow

1. repository `AGENTS.md` と必須の repository specs を確認する。
2. 指定 session note を解決して読む。
3. session note の Frontmatter を確認する。
   - `type: session` であること。
   - `schemaVersion: 1` であること。未記載なら legacy v1 として読み、実際に更新する場合は `1` を追加する。`1` 以外なら書き換えを停止する。
   - `sessionId` が filename 先頭と対応すること。
   - `status`、`distillationStatus`、`distilledTo` があること。
4. この chat の canonical session note path を、指定 session note として扱う。
5. 以後この chat では、新しい session note を作成しない。
6. `write-session-note` が必要な更新は、必ず指定 session note に書く。
7. 作業再開時点で、Frontmatter の `status` を `in-progress` にする。ただし user が閲覧のみを依頼している場合は変更しない。
8. Skill が session note を更新したら、Frontmatter の `updated` を OS/system clock の timestamp に更新する。
9. 再開した事実、現在の user intent、次の一手を既存 section に短く反映する。
10. 重要な current truth が変わる場合だけ、project `working-context.md` も更新する。

## What to update in the session note

必要な section だけ更新する。

- `User intent / interaction summary`: 新しい chat で resume 指定があったことと、追加依頼。
- `Current state`: resume 後の現在状態。
- `Working context`: 新たに確認した files や assumptions。
- `Changed files`: resume 後に変更した files。
- `Important decisions`: resume 後に増えた durable decisions。
- `Open issues`: 未解決の blocker や questions。
- `Next steps`: resume 後の concrete next actions。
- `Exact next step`: 次の chat または compaction 後に最初に取る action。
- `Validation`: resume 後に実施した checks。

chronological log は増やしすぎない。resume の事実は、後続作業に必要な範囲で短く書く。

## Relationship to write-session-note

この skill は `write-session-note` の代替ではない。対象 session note を固定するための entry skill である。

resume 後に非自明な作業、file changes、handoff、completion が発生した場合は、`write-session-note` の記録基準に従う。ただし output path は新規 session note ではなく、resume した指定 session note にする。

## Safety

- 指定 session note を上書きする前に、現在の内容と Frontmatter を確認する。
- secrets、credentials、tokens、private keys、full environment variables、large logs、不要な personal/customer data を追記しない。
- unrelated session notes を変更しない。
- user が明示しない限り、`distillationStatus`、`distilledTo`、`promotionStatus`、`promotedTo` は resume だけでは変更しない。
- status が `done` の session を resume する場合、作業を実際に継続するなら `in-progress` に戻してよい。完了後は `done` に戻す。
