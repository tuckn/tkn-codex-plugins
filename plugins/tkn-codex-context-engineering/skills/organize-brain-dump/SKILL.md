---
name: organize-brain-dump
description: ユーザーが思いつくままに書いた Brain-Dump、箇条書き、文の羅列、未整理メモを整理し、その上で Codex の意見・助言・次アクションを Frontmatter 付き Markdown に出力する依頼で使う。既定では登録済み Codex Project の project memos folder に保存し、chat や AGENTS.md などに保存場所の指示がある場合はそれを優先する。思考整理、壁打ち、相談、論点整理、仮説整理、作業記録案、運用案、ブログやSNSの素材化候補の整理に使う。
---

# Organize Brain Dump

Brain-Dump を、素材の勢いを失わせずに扱いやすい Markdown note へ整理するために、この skill を使う。

目的は、ユーザーが書き殴った断片を、後から読み返せる構造、問い、仮説、判断材料、次アクションに変換し、その上で Codex の助言を明確に分離して提示することだ。

## Output location

整理結果は、次の優先順で新規 Markdown file として作成する。

1. chat 内でユーザーが保存場所を指示した場合は、その場所に従う。
2. `AGENTS.md` などの repository instructions が保存場所を指定している場合は、その場所に従う。
3. それ以外では、登録済み current project の `~/.codex-context/projects/<projectId>/memos/` に作成する。

既定の filename:

`~/.codex-context/projects/<projectId>/memos/YYYYMMDDTHHMMSS<system-timezone-offset>_<short-ja-or-en-title>.md`

- timestamp は system timezone の offset 付き local time を使う。
- filename title は内容が scan できる短い名前にする。
- current project に保存する場合は、`.codex-context/project.yaml` と `~/.codex-context/projects/index.jsonl` から `projectId` と project context folder を解決する。
- `memos/` が存在しない場合は作成する。
- current project を解決できず、明示的な保存場所もない場合は、保存前にユーザーへ保存場所の指定または project registration を依頼する。
- `sessions/` や `decisions/` には保存しない。それらが必要な場合は、対応する session / decision Skill を使う。
- `_inbox/ai/` は、chat または repository instructions が明示した場合だけ使う。
- 既存 note を直接大きく変更しない。必要なら選択した保存場所に案を作る。
- chat reply では、作成 file path と要点だけを短く返す。

## Required Frontmatter

```yaml
---
type: plan
title: <note title>
description: <short description>
generator: Codex
reviewStatus: draft
date: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
updated: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
noteId: <UUID>
---
```

- `type` は repository instruction に従い、当面は `plan` を default とする。
- `reviewStatus` は通常 `draft`。
- `date` と `updated` は同じ作成時刻でよい。
- `noteId` は UUID v4 を使う。

## Workflow

1. 入力を raw material として読む。
2. 主題、背景、目的、制約、問い、事実、推測、仮説、感情・違和感、候補案、望んでいる出力を分ける。
3. ユーザーの意図を、元の表現より少し抽象化して再構成する。
4. 必要なら不足観点、確認すべき情報、前提の揺れを補う。
5. Codex の意見を、整理結果と混ぜずに別 section で書く。
6. 次アクションを、すぐできるものと、調査・設計が必要なものに分ける。
7. ユーザーに確認すべき質問を、Markdown 内の独立 section として作る。
8. Output location の優先順に従って Markdown file を作成する。
9. 必要に応じて作成 file の内容を確認し、frontmatter と見出しを検証する。

## Recommended structure

出力 note は、内容に合わせて見出しを増減してよい。迷う場合は次の順序を使う。

```md
# <Title>

## 元の相談の要約

## 整理した論点

## 背景と目的

## 事実・前提

## 問い

## 仮説

## 選択肢

## Codex の意見

## 懸念点

## ユーザーへの確認事項

## 次アクション

## 将来の素材化候補
```

### Section guidance

- `元の相談の要約`: Brain-Dump の主旨を短く再構成する。
- `整理した論点`: 論点を箇条書きで並べる。重要度順が望ましい。
- `背景と目的`: なぜこの相談が出ているか、何を得たいかを書く。
- `事実・前提`: 入力に明示された facts と、明示されていない assumptions を分ける。
- `問い`: ユーザーが明示した問いと、暗黙の問いを分ける。
- `仮説`: まだ確定していないが検討に値する考えを書く。
- `選択肢`: 実行方針、運用案、分類案などを比較する。
- `Codex の意見`: 賛成点、懸念点、推奨案を明確に書く。
- `懸念点`: リスク、未確認事項、誤解されやすい点を書く。
- `ユーザーへの確認事項`: 誤認、情報不足、意図の曖昧さ、優先順位の不明点を質問として書く。
- `次アクション`: 具体的で小さな一歩を書く。
- `将来の素材化候補`: ブログ、SNS、docs、decision record、project note などへの展開候補を書く。

## User questions policy

出力 note には、原則として `## ユーザーへの確認事項` を含める。

- Brain-Dump から確信できない点、漏れていそうな前提、誤認の可能性がある点を質問にする。
- 回答品質を上げるための質問に絞る。多すぎる質問で review を重くしない。
- 通常は 3-7 個を目安にする。明確な不足がない場合でも、`現時点で大きな確認事項はありません。` と書く。
- 質問は、ユーザーが Markdown file を開いて追記しやすい形にする。
- Codex が勝手に決めてよい軽微な表現や順序は質問にしない。

## Writing rules

- ユーザーの raw text を過度に浄化しない。未整理な熱量や問題意識は残す。
- 事実、推測、Codex の意見を混ぜない。
- Codex の意見は遠慮しすぎず、ただし断定の根拠が弱い場合はその弱さを明示する。
- ユーザーがまだ考え切っていない可能性がある点は、結論ではなく問いとして残す。
- 文章は日本語を基本にする。paths、commands、identifiers、framework names は原文を維持する。
- 長文を chat に貼り返さず、Markdown file に集約する。
- secrets、credentials、tokens、private keys、full environment variables、不要な個人情報は書かない。

## When external information is needed

ユーザーが best practice、法令、規格、製品仕様、価格、現行サービス、最新情報を求めている場合は、必要に応じて primary source または信頼できる sources を確認する。

- Azure、OpenAI、GitHub などの製品仕様は公式 docs を優先する。
- 参照した sources は note 内に `## 参考` を設けて link する。
- 未確認の一般論は `一般的には` として扱い、公式根拠のある内容と分ける。

## Chat reply

最終 reply は短くする。

- 作成した file path。
- note の要点 2-4 個。
- 追加確認や次に実行できることがあれば 1 個だけ。

本文全体を chat に再掲しない。
