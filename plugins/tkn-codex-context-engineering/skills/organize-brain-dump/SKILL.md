---
name: organize-brain-dump
description: ユーザーが思いつくままに書いた Brain-Dump、箇条書き、文の羅列、未整理メモを整理し、その上で Codex の意見・助言・次アクションを Frontmatter 付き Markdown に出力する依頼で使う。既定では Codex Project Folder 直下の organize-brain-dump フォルダに保存し、chat や AGENTS.md などの保存場所の指示を優先する。思考整理、壁打ち、相談、論点整理、仮説整理、作業記録案、運用案、ブログやSNSの素材化候補の整理に使う。
---

# Organize Brain Dump

Brain-Dump を、素材の勢いを失わせずに扱いやすい Markdown note へ整理するために、この skill を使う。

目的は、ユーザーが書き殴った断片を、後から読み返せる構造、問い、仮説、判断材料、次アクションに変換し、その上で Codex の助言を明確に分離して提示することだ。

## Output location

整理結果は、次の優先順で新規 Markdown file として作成する。

1. chat 内でユーザーが保存場所を指示した場合は、その場所に従う。
2. `AGENTS.md` などの project instructions が保存場所を指定している場合は、その場所に従う。
3. それ以外では、現在の Codex Project Folder を基準に `./.agents/organize-brain-dump/` に作成する。Skill のインストール先や一時的な作業サブフォルダを基準にしない。Project Folder を特定できない場合、ユーザーへ保存先を確認する。

既定の filename:

`YYYYMMDDTHHMMSS<system-timezone-offset>_<short-ja-or-en-title>.md`

- timestamp は system timezone の offset 付き local time を使い、filename title は短くする。
- 保存先フォルダがなければ作成する。
- 保存先に独自の規約がある場合は従う。移動や整理のために既存 note の日付を書き換えない。
- 既存 note を直接大きく変更しない。必要なら選択した保存場所に案を作る。
- chat reply では、作成 file path と要点だけを短く返す。

## Required Frontmatter

出力 note は Obsidian で読むことを前提とする。Frontmatter はトップレベルのプロパティだけを使い、値は文字列・数値・真偽値・日付などの scalar、または文字列の配列にする。入れ子の object、object の配列、配列の配列は使わない。[Obsidian の Properties](https://obsidian.md/help/properties) は nested properties の編集に対応していない。

```yaml
---
type: plan
title: <note title>
description: <short description>
generator: Codex
reviewStatus: unreviewed
date: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
updated: YYYY-MM-DDTHH:mm:ss<system-timezone-offset-with-colon>
id: <UUID>
sourceType: <codexChat | chatgptChat | file | mixed>
sourceExcerpts:
  - "<ユーザー入力を識別できる短い原文抜粋>"
---
```

- `type` は `plan` を default とする。
- `reviewStatus` は通常 `unreviewed`。保存先の仕様があればそれを優先する。
- 新規作成時、`date` と `updated` は同じ作成時刻でよい。
- `id` は出力 note 自体の UUID v4。旧 `noteId` と同じ意味なので、新規出力では `id` に統一する。既存 note を明示的に更新する場合は UUID を維持する。
- `date`・`updated` は出力 note の日時。入力の発言日時は `sourceLocators` に記録する。
- `sourceType` と、対象入力を特定する `sourceLocators` または `sourceExcerpts` を下記の規則で記録する。例の placeholder は実値に置き換える。

## Source metadata

ユーザーの入力 raw material を後からたどれるよう、素材の出所と使用した範囲を Frontmatter に記録する。`tkn_codex_chat_note_pipeline` の session note と同じ意味の項目は、次の名前と型に揃える。

| 旧名 | 新規出力の名前 | 内容 |
| --- | --- | --- |
| `originCodexProjectId` | `sourceProjectId` | 入力元 Project の確認済み ID。 |
| `originCodexProjectName` | `sourceProjectName` | 入力元 Project の確認済み表示名。この Skill の補足項目。 |
| `originCodexThreadId` | `sourceThreadIds` | 入力元の thread ID の文字列配列。1 件でも配列にする。 |
| `originCodexLog` | `sourceCaptureRef` / `sourceCaptureRefs` | 保存済み RAW capture への参照。通常のログファイルしか確認できない場合は、その参照を `sourceRefs` に記録する。 |
| `originService` | `sourceType` | Codex chat は `codexChat`、ChatGPT chat は `chatgptChat`。 |

- `sourceType` は素材の種類。ファイル由来は `file`、異種の素材を併用する場合は `mixed` とする。`codexChat` 以外の値はこの Skill での拡張であり、session note の schema 互換性を意味しない。
- `sourceRefs` は入力元の論理参照・URL・ファイル参照の文字列配列。Codex thread は参照ノートと同じ `codex/<thread-id>` を使う。既存の生成物や管理データに正式な参照値がある場合は、その値を維持する。ファイル参照は基準を明記した相対パスか file URI とし、ローカル Windows パスは `/` 区切りにする。
- `sourceLocators` は実際に整理したユーザー入力の位置を示す文字列配列で、この Skill の追加項目。1 要素に入力元の参照と、確認できる message ID・turn ID・offset 付き発言日時、またはファイル内の見出し・1-based 行範囲をまとめる。参照部分は `sourceRefs` のいずれかと一致させる。例: "codex/<thread-id>; messageId=<confirmed-message-id>; timestamp=<confirmed-ISO-8601-timestamp>"。複数の発言やファイルを使った場合は、素材ごとに追加する。
- `sourceExcerpts` は識別に必要な短い原文抜粋の文字列配列で、この Skill の追加項目。対象入力を位置情報だけで特定できない場合に使う。複数の素材を使う場合は、各文字列に確認済みの入力元参照や発言 ID を添え、`sourceLocators` との対応を配列の順番だけに依存させない。ID・ログ・ファイル参照が取得できない chat 入力では、確認できる発言日時や原文抜粋を残し、参照の未確認を本文に明記する。抜粋は要約や Codex の返答で代用せず、秘密情報や不要な個人情報を含めない。安全に識別情報を残せない場合も、その限界を本文に明記する。
- `sourceCaptureRefs` は確認済みの RAW capture の参照配列。`sourceCaptureSha256s` を記録する場合は、各ファイルの実バイト列から計算した SHA-256 を同じ順序・件数で並べる。単数形の `sourceCaptureRef`・`sourceCaptureSha256` を併記する場合は、それぞれ配列の先頭と一致させる。`raw:/...` は既存の管理データから解決できる値だけを使い、通常のログパスから捏造しない。
- `sourceFingerprint`・`sourceSetSha256` は pipeline 固有の計算規則を持つ。対象となる入力集合が同じで、既存値または同じ計算規則を確認できる場合だけ記録する。原文抜粋やログファイルの単純なハッシュで代用しない。
- 不明な ID・Project・参照・ハッシュは省略し、folder 名や話題から推測しない。Project marker・registry・RAW capture を新規作成する必要はない。入力元が複数 Project にまたがる場合は、単一の `sourceProjectId`・`sourceProjectName` にまとめない。
- `source*` は入力素材の出所を示す。今回 note を生成・保存する Project や、本文で話題にする関連 Project と混同しない。`generator` は今回の出力を生成した Codex を示し、素材側の generator・日時は元資料で維持する。
- 新規出力で旧名と新名を重複させない。`type: plan` を維持し、session note 専用の `sessionNoteId`・`schemaVersion`・生成 pipeline の version 情報を流用しない。

Codex chat の入力元と対象発言を確認できた場合の例（各 placeholder を確認済みの値に置き換える）:

```yaml
sourceType: codexChat
sourceThreadIds:
  - "<thread-id>"
sourceRefs:
  - "codex/<thread-id>"
sourceProjectId: "<confirmed-project-id>"
sourceLocators:
  - "codex/<thread-id>; messageId=<confirmed-message-id>; timestamp=<confirmed-ISO-8601-timestamp>"
sourceExcerpts:
  - "codex/<thread-id>; messageId=<confirmed-message-id>; excerpt=<対象のユーザー入力を識別できる短い原文抜粋>"
```

## Workflow

1. 入力を raw material として読み、Source metadata に従って入力元と対象発言・ファイル内の範囲を確認する。
2. 主題、背景、目的、制約、問い、事実、推測、仮説、感情・違和感、候補案、望んでいる出力を分ける。
3. ユーザーの意図を、元の表現より少し抽象化して再構成する。
4. 必要なら不足観点、確認すべき情報、前提の揺れを補う。
5. Codex の意見を、整理結果と混ぜずに別 section で書く。
6. 次アクションを、すぐできるものと、調査・設計が必要なものに分ける。
7. ユーザーに確認すべき質問を、Markdown 内の独立 section として作る。
8. Output location の優先順に従って Markdown file を作成する。
9. 作成 file の Frontmatter と見出しを確認し、`sourceLocators`・`sourceExcerpts` が実際に整理したユーザー入力を指すこと、Frontmatter に入れ子の構造がないこと、参照・配列・ハッシュに未確認値や placeholder が残っていないことを検証する。

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
