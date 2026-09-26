# C2C Secure Pilot Closeout・本運用移行 作業指示書

> **歴史的な引き継ぎ・作業指示の記録です。現行手順ではありません。** 本文中のブランチ名、コミット SHA、パス、件数、コマンド、停止条件は作成当時の状態を示します。実行前に現行状態と当該タスクの承認を確認してください。現在の開発方針は[ロードマップ](../project_roadmap.md)、[現行ベースライン](../history/current_baseline.md)、[アーキテクチャ概要](../architecture_overview.md)、C2C の運用・セキュリティ方針は[C2C documentation](../c2c/README.md)を参照してください。

## 1. 目的

C2C Secure Pilotの検証結果とChatGPTレビューを反映し、

1. Pilot報告書の不整合を修正する
2. Pilot判定を正式にcloseoutする
3. Reviewed Baselineを固定する
4. C2C Version Up時のSecurity Review Gateを正式運用化する
5. C2Cを今後の `saw-com-optimizer` 開発における通常レビュー経路として利用可能な状態にする

ことを目的とする。

この作業ではC2C本体、SAW optimizer本体、COMモデル、Optimizerアルゴリズムを変更しない。

---

# 2. 最終判定

Pilotの正式判定は以下とする。

```text
PASS WITH LIMITATIONS
```

本運用移行を許可する。

ただし、以下の制約を継続する。

```text
Reviewed SHA固定
自動update禁止
Version Up前Security Review必須
frozen dependency install
.c2cignore維持
```

---

# 3. Reviewed Baseline

C2C repository:

```text
https://github.com/XiaoDuoYa/codex-with-chatgpt
```

正式Reviewed Baseline:

```text
9663b88753e35c76796c5bce000293e0bd22cd9e
```

Package version:

```text
0.1.3
```

このSHAを、次回Security Reviewで新しいcommitが承認されるまで使用する。

---

# 4. 本作業の禁止事項

以下は禁止する。

1. C2C upstreamへ変更を加えない
2. C2Cを最新版へ更新しない
3. `git pull` しない
4. `git stash` しない
5. dependencyを更新しない
6. `pnpm-lock.yaml` を変更しない
7. C2C Skillをupstream版で上書きしない
8. `.c2cignore` のSecurity ruleを弱めない
9. SAW optimizer sourceを変更しない
10. Stage 3.8実験を開始しない
11. Mainへのmerge/pushを勝手に行わない

今回の目的はPilotのcloseoutと運用ルール確定のみ。

---

# 5. Phase 1 — 現在状態確認

`saw-com-optimizer` で以下を確認する。

```powershell
git status --short
git branch --show-current
git rev-parse HEAD
git diff -- .c2cignore
```

期待状態:

```text
branch:
codex/c2c-secure-pilot-20260925

HEAD:
52a9eb35db16f1cd252b5bbd5fca02ec785d59de

tracked change:
.c2cignore
```

開始前から存在している未追跡ファイルを勝手に削除・commitしない。

---

# 6. Phase 2 — Pilot報告書修正

対象:

```text
reports/c2c_secure_pilot_validation_20260925.md
```

実際の配置が異なる場合は既存ファイルを使用する。

新しい報告書を重複作成しない。

---

## 6.1 冒頭の状態説明を更新

現在の古い記述：

```text
ChatGPTのconnector作成、OAuth/pairing、
ChatGPT経由のMCP確認は手動手順の途中であり、
まだ完了していない。
```

は現在の結果と矛盾しているため修正する。

概ね以下の意味になるよう更新する。

```text
固定SHAでのローカル検証、Quick Tunnel、
ChatGPT connector/OAuth pairing、
ChatGPT経由MCP検証、
read-only tool surface確認、
C2C loop検証まで完了した。

未検証として残るのは、
C2C更新候補が実際に存在する場合の
update protection positive caseと、
Windows権限制約により作成できなかった
通常file symlink escape testである。
```

---

# 7. Phase 3 — Conclusion更新

現在の：

```text
PARTIAL
```

を、

```text
PASS WITH LIMITATIONS
```

へ変更する。

ただし未検証事項を消してはならない。

Conclusionには少なくとも以下を含める。

```text
PASS WITH LIMITATIONS

本Pilotでは以下を確認した。

- Reviewed SHA固定
- frozen-lockfile dependency install
- build/typecheck/test成功
- read-only MCP
- workspace containment
- .c2cignore enforcement
- .git/config拒否
- sensitive file拒否
- OAuth / connector接続
- C2C loop
- SAW repositoryへの不要なsource変更なし

本運用開始を許可する。

残余項目:
1. updateAvailable=true のpositive case
2. Windows通常file symlink escape

これらは本運用開始のBlockerとはしない。
```

---

# 8. Phase 4 — Limitations整理

`Limitations` sectionを保持する。

特に以下を明記する。

### 8.1 Update positive case

現在は、

```text
updateAvailable:false
```

のみ確認済み。

したがって、

```text
updateAvailable:true
↓
通知のみ
↓
自動pullしない
↓
install/build/restartしない
```

という実地検証は未完了。

これは**最初に新しいupstream commitが検出された時点で検証する。**

それまではReviewed SHAを維持する。

---

## 8.2 File symlink

Windows権限制約により通常file symlinkは作成できなかった。

ただし、

```text
../ traversal
absolute outside path
Windows-style traversal
junction escape
```

については拒否を確認済み。

管理者権限を付与してまで追加テストしない。

---

# 9. Phase 5 — 正式Security Baseline記録

報告書または適切なhandoff documentに以下を明記する。

```text
C2C Security Baseline

Reviewed repository:
XiaoDuoYa/codex-with-chatgpt

Reviewed SHA:
9663b88753e35c76796c5bce000293e0bd22cd9e

Package:
0.1.3

Status:
APPROVED WITH LIMITATIONS

Automatic update:
PROHIBITED

Dependency update:
PROHIBITED WITHOUT REVIEW

Required before upgrade:
ChatGPT Security Review
```

今後のC2C Security ReviewはこのSHAを比較基準とする。

---

# 10. Phase 6 — Version Up Policy正式化

現在インストール済みのCodex Skillに設定した安全運用ルールを維持する。

Version Upフローは以下に固定する。

```text
C2C update candidate検出
        ↓
更新しない
        ↓
current Reviewed SHAを取得
        ↓
candidate SHAを取得
        ↓
ユーザーへ通知
        ↓
ChatGPT Security Review
        ↓
current..candidate diffレビュー
        ↓
dependency / lockfileレビュー
        ↓
Security PASS
        ↓
ユーザー承認
        ↓
初めてcheckout/update
        ↓
pnpm install --frozen-lockfile
        ↓
build
typecheck
test
Windows canary
        ↓
新SHAをReviewed Baseline化
```

---

# 11. Candidate検出時のCodex動作

新しいC2C versionを検出した場合、

Codexは以下だけを報告する。

```text
C2Cの更新候補が検出されました。

Current Reviewed SHA:
<current>

Candidate SHA:
<candidate>

Security Reviewが必要なため、
現在のReviewed Versionを維持します。
```

その後、

**C2C更新処理を実行しない。**

元のユーザー作業は、現在のReviewed Versionで継続可能なら継続する。

---

# 12. Phase 7 — `.c2cignore` 正式採用

現在追加されたSecurity ruleを正式採用候補とする。

最低限以下が含まれていること。

```gitignore
.git/
.env
.env.*

runs/**/raw/
runs/**/checkpoints/
runs/**/*.ckpt
runs/**/*.checkpoint

tmp/
temp/
cache/

private/
secrets/
credentials/
confidential/

references/licensed/

**/*.zip
```

不要に広すぎるruleがないことも確認する。

特に以下が引き続きChatGPTから利用可能であること。

```text
src/
tests/
docs/
handoff/
README
Markdown summaries
CSV summaries
JSON summaries
```

---

# 13. Phase 8 — 最終MCP健全性確認

C2C connectorを使って最終的に以下を確認する。

```text
workspace_info
git_status
```

期待:

```text
workspaceName:
saw-com-optimizer

branch:
codex/c2c-secure-pilot-20260925
```

tool surfaceが引き続きread-onlyであること。

以下のtoolがないこと。

```text
write_file
delete_file
execute_shell
git_commit
install_package
```

---

# 14. Phase 9 — 最終Git Regression

SAW repository:

```powershell
git status --short
git diff
git diff --cached
git rev-parse HEAD
```

確認する。

Pilot canaryが残っていないこと。

```text
c2c_canary*
c2c_pilot_loop_canary*
```

等を検索し、残存があればPilotで作ったものだけ削除する。

ユーザー既存ファイルは削除しない。

---

# 15. 恒久変更として認めるもの

今回、SAW repositoryで正式採用候補とする変更は、

```text
.c2cignore
Pilot validation report
必要なC2C security handoff/documentation
```

のみ。

SAW計算コードには変更を入れない。

---

# 16. Commit方針

closeout内容が整理できたら、Pilot専用branch上でcommitしてよい。

ただしMainへmergeしない。

推奨commit単位:

```text
chore(c2c): close secure pilot and pin reviewed baseline
```

内容：

```text
.c2cignore
C2C pilot validation report
必要なsecurity policy documentation
```

既存の無関係な未追跡ファイルを含めない。

---

# 17. Commit前確認

必ず、

```powershell
git status --short
git diff --cached
```

を確認する。

意図しない、

```text
src/
tests/
runs/
optimizer code
COM code
large artifacts
credentials
```

がstageされていないこと。

問題があればcommitせず停止する。

---

# 18. Pilot Closeout判定

最終判定：

```text
C2C Secure Pilot
PASS WITH LIMITATIONS
```

Operational status:

```text
APPROVED FOR NORMAL SAW DEVELOPMENT USE
```

ただし、

```text
AUTO UPDATE = DISABLED
```

をHard Ruleとする。

---

# 19. 今後の利用方針

Pilot closeout後は、C2Cを以下の用途で通常利用してよい。

```text
ChatGPT
    ↓
plan / review
    ↓
C2C read-only MCP
    ↓
workspace / git / execution status
    ↑
Codex
    ↓
implementation / tests / experiments
```

従来のZIP reviewは完全廃止しない。

C2Cで読み取りにくい、

```text
large binary bundle
大量ログ
archive
特殊成果物
```

については、従来のreview bundle方式をfallbackとして利用可能。

---

# 20. 長時間Optimizerについて

C2C導入により長時間実験の実行方式は変更しない。

```text
Codex
↓
独立Python optimizer process
↓
runs/
↓
summary生成
↓
C2C経由でChatGPT review
```

とする。

C2C sessionやChatGPT conversationの存続を、
optimizer processの存続条件にしてはならない。

---

# 21. Phase 10 — Closeout Report

作業終了時、以下を報告する。

```text
C2C Secure Pilot Closeout

Final result:
PASS WITH LIMITATIONS

Reviewed SHA:
9663b88753e35c76796c5bce000293e0bd22cd9e

SAW HEAD:
<sha>

C2C HEAD:
<sha>

Update policy:
REVIEW-GATED / AUTO UPDATE DISABLED

MCP:
PASS

Read-only tool surface:
PASS

Workspace containment:
PASS

Remaining limitations:
- updateAvailable=true positive case
- normal Windows file symlink

Repository changes:
...

Commit:
<sha or NOT COMMITTED>

Main merge:
NOT PERFORMED
```

---

# 22. 最終停止点

Closeout commitまで完了したら停止する。

以下はまだ実施しない。

```text
Mainへのmerge
Mainへのpush
Stage 3.8再開
C2C Version Up
```

作業結果をChatGPTへ渡して最終確認を受けること。

---

# 23. 今後の最重要運用ルール

C2Cについて、

```text
動いているから更新する
```

ではなく、

```text
現在動いているReviewed Versionを維持する
```

ことをデフォルトとする。

新Versionは、

```text
Security Review
↓
承認
↓
更新
```

の順番を必ず守る。

**未レビューコードをMainUser権限で実行しないことが、この運用の最優先事項である。**
