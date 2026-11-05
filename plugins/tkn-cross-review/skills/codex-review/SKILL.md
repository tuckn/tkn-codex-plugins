---
name: codex-review
description: コードを変更する作業を完了と判断した後、完了報告の前に、Codex CLI（GPT-6.1-Sol、推論xhigh）で変更をレビューさせ、指摘を検証して対応する。ユーザーが「Codexにレビューさせて」と頼んだときにも使う。会話だけのターンや、Markdown（.md）だけの変更では使わない。
---

# Codexによる完了前レビュー

Claude Codeが書いたコードを、完了報告の前にCodexにレビューさせる。Codexは読み取り専用で動かし、修正はClaude Codeが行う。

## 対象

- 対象：プログラム、スクリプト、設定ファイルなど、コードの変更。
- 対象外：会話だけのターン、Markdown（`.md`）だけの変更。コードとMarkdownが混ざる場合は、コードのファイルだけを対象にする。
- このSkillはClaude Code用。Codexからは使わない（Codexが自分の作業を自分でレビューすることになる）。
- ユーザーが別のレビュー方法（Orcaのorchestration Skillなど）を指定したときは、そちらに従う。

## 手順

### 1. 対象を決める

`git status --short` と `git log` で、この作業で変えたものを確かめ、次のどれかを選ぶ。

| 状況 | 指定 |
| --- | --- |
| 未commitの変更が、この作業の分だけ | `--uncommitted` |
| この作業を1つのcommitにした | `--commit <SHA>` |
| この作業をbranchで進めた | `--base <分岐元branch>` |
| 作業前からの変更やMarkdownが混ざる | 対象指定なし。PROMPTで対象ファイルを列挙する（下記） |

PROMPTを使う場合は、`git diff` で見るべきファイルを名指しし、それ以外の変更を無視するよう書く。`--uncommitted` などの対象指定とPROMPTは同時に使えない（指定するとエラーになる）。

### 2. 実行する

対象リポジトリのフォルダに移動してから実行する（`codex review` には `-C` がない）。数分かかることがあるため、`run_in_background` で実行し、完了の通知を待つ。出力はセッションのscratchpad（なければOS標準の一時フォルダ）へ書く。

例はPowerShell。bashなどでは、行の継続を `` ` `` から `\` に変える。

```powershell
Set-Location '<対象リポジトリ>'
codex review --uncommitted `
  -c 'model="gpt-6.1-sol"' -c 'model_reasoning_effort="xhigh"' -c 'review_model="gpt-6.1-sol"' `
  -c 'sandbox_mode="read-only"' -c 'approval_policy="never"' `
  > '<scratchpad>\codex-review.txt' 2> '<scratchpad>\codex-review.log'
```

- stdout（`codex-review.txt`）にレビュー結果が出る。指摘は `[P1]`・`[P2]` などの優先度、ファイル、行つきで並ぶ。
- stderr（`codex-review.log`）は数百行の実行ログになる。全文は読まず、冒頭の設定行（`model:`・`reasoning effort:`・`sandbox:`・`session id:`）だけを確かめる。PowerShellなら `Select-String -Pattern '^(model|reasoning effort|sandbox|session id):'`、bashなら `grep -E '^(model|reasoning effort|sandbox|session id):'` で取り出せる。`gpt-6.1-sol`・`xhigh`・`read-only` になっていなければ、結果を使わずにユーザーへ報告する。
- `session id` は手順3・4で使うので控えておく。
- モデルと推論量は `~/.codex/config.toml` の既定に頼らず、上の `-c` で固定する。
- 小さな変更でも1分ほどかかる。

### 3. 指摘を検証して対応する

Codexの指摘は正しいとは限らない。指摘ごとにコードを読んで確かめ、次のどれかにする。

- 直す：妥当な指摘。修正する。
- 退ける：誤り、または作業の範囲外。理由を一文で残す。
- ユーザーに確かめる：仕様や方針の判断が必要なもの。勝手に決めない。

指摘の意図が分からないときや、誤りだと考えるときは、同じセッションでCodexに聞ける。Codexは前のレビュー内容を覚えている。

```powershell
Set-Location '<対象リポジトリ>'
codex exec resume <session id> '<質問>' `
  -c 'model="gpt-6.1-sol"' -c 'model_reasoning_effort="xhigh"' `
  -c 'sandbox_mode="read-only"' -c 'approval_policy="never"' `
  > '<scratchpad>\codex-reply.txt' 2> '<scratchpad>\codex-reply.log'
```

Codexの答えも検証の材料の一つとして扱い、最終的な判断はClaude Codeがする。

ロジックに関わる修正をした場合は、修正後の状態でもう一度レビューする。レビューは合計2回までとし、それでも残る指摘は完了報告に書く。

### 4. 完了報告に載せる

完了報告に短い「Codexレビュー」の節を設け、次を書く。

- 対象（`--uncommitted` などの指定）、レビューの回数、Codexの `session id`（後から同じセッションを探すための手がかり）
- 直した指摘、退けた指摘（理由つき）、ユーザーに確かめたい指摘
- 指摘がなかった場合は、そのこと

Codexが動かなかった（未ログイン、エラー、時間切れなど）場合は、レビューしていないことと、その理由を報告する。レビューを省いたまま完了と報告しない。
