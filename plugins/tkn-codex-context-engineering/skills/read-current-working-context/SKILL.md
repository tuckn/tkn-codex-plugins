---
name: read-current-working-context
description: 登録済み current project の projectId-specific working-context.md を読み、新しい chat で project purpose、current truth、active work、constraints、recent decisions、key files、next maintenance を把握する。ユーザーが current project の状況確認、orientation、context 利用、resume または handoff 前の把握を依頼し、`.tkn/codex-context.yaml` が private registry で現在 workspace に解決できる場合に使う。read-only とし、marker 生成だけでは使わない。
---

# Read Current Working Context

`~/.tkn/codex-context/state/<projectId>/working-context.md` を新しい chat の read-only orientation dashboard として読むために、この skill を使う。

目的は、同じ Codex Project の別 chat が会話内容を自動継承しない場合でも、保存済みの project current truth を明示的に読み、現在の作業状況を短時間で把握することだ。

## Activation Gate

次の両方を満たす場合だけ実行する。

- ユーザー意図が current project の状況確認、orientation、保存済み context の利用、resume または handoff 前の把握に一致する。
- 現在の workspace に `.tkn/codex-context.yaml` があり、その `projectId` が `~/.tkn/codex-context/state/index.jsonl` で同じ workspace に解決できる。

marker の存在や chat の開始だけでは発動しない。すべての非自明な作業で自動実行しない。

working context の作成または更新依頼には `write-current-working-context` を使う。特定の session note を継続する依頼には `resume-session` を使う。

## Project Resolution

読み取り前に、次の順序で current project を解決する。

1. repository instructions と現在の workspace root を確認する。Git repository では原則として Git root を project root とする。
2. `<project-root>/.tkn/codex-context.yaml` を読み、空でない `projectId` を取得する。
3. `~/.tkn/codex-context/state/index.jsonl` から同じ `projectId` の registry record を一意に特定する。
4. path separator、末尾 separator、Windows の大文字小文字を正規化し、record の `currentRoot` が現在の project root と一致することを確認する。解決可能な symlink または junction がある場合は、双方の physical path も比較してよい。
5. registry record の `workingContextPath` を取得し、同じ `projectId` の state folder にある `working-context.md` を指すことを確認する。

次の場合は読み取りを停止し、別 project の state を推測して読まない。

- marker がない。
- marker に `projectId` がない。
- registry record がない、複数ある、または壊れている。
- `currentRoot` が現在の project root と一致しない。
- `workingContextPath` がない、期待する project state の外を指す、または file が存在しない。

未登録または root 不一致を自動修復しない。ユーザーが登録、移動、修復を望む場合だけ `init-project-context` を案内する。登録済みだが working context だけがない場合は、作成依頼に `write-current-working-context` を案内する。

## Read Workflow

1. 解決した `working-context.md` を Frontmatter から本文末尾まで全体で読む。
2. Frontmatter の `type`、`status`、`updated` を確認する。`projectId` がある場合は marker と一致することも確認する。
3. purpose、current truth、active work、important constraints、recent decisions、key files、next maintenance を抽出する。
4. 現在の依頼の理解に必要な link だけを選び、関連する session note、decision record、plan、spec を選択的に読む。
5. `project:/<path>` は registry で検証済みの `currentRoot`、`state:/<path>` は検証済み `workingContextPath` の親 folder を基準に解決する。
6. logical reference は `/` separator を使い、`..` で logical root の外へ出る path は解決しない。

`project:/` と `state:/` は filesystem URI や Markdown link target ではない。Legacy working context に root のない relative path が残る場合は、既存の意味に従って repository-relative path を project root、project-context-relative path を project state folder から read-only で解決してよい。ただし、その working context を後で更新する場合は `write-current-working-context` の規則で logical reference に正規化し、legacy notation を新しい記述へ引き継がない。

Project state folder 全体、`sessions/` 全体、`decisions/` 全体、Codex JSONL chat 履歴を orientation のために走査しない。chat 履歴から context を再構築する依頼には `refresh-project-context-from-chats` を使う。

## Freshness And Conflict Handling

次を freshness warning として明示する。

- `status` が `stale` または `archived`。
- Frontmatter にある `projectId` が marker の `projectId` と一致しない。
- `updated` がない、解釈できない、または現在の task に対して古い可能性が高い。
- stored context が現在の user instruction、repository instruction、repository file、または Git state と明白に矛盾する。
- link 先が missing、moved、または内容と一致しない。

矛盾時は、現在の user instruction、repository instruction、現在の file と Git evidence を優先する。stored context は stale な参考情報として扱い、自動修正しない。

## Response

保存済み記述をそのまま長く転載せず、次を簡潔に返す。

- project purpose と current truth
- active work と現在の到達点
- important constraints
- recent decisions
- key files と必要な関連 note
- next maintenance または resumption point
- freshness warning と、現在の証拠を優先した箇所

不足している section は推測で埋めず、保存済み context に記載がないと示す。

## Read-only Boundary

この skill の実行中は次を変更しない。

- `.tkn/codex-context.yaml`
- `~/.tkn/codex-context/state/index.jsonl` と registry metadata
- `working-context.md` の本文、Frontmatter、timestamp、status
- session notes、decision records、plans、specs
- repository files と Git state

読み取りによって `lastSeenAt`、`updated`、hash、fingerprint を更新しない。stale や missing を発見しても自動修正せず、必要な Skill と次の選択肢を案内する。
