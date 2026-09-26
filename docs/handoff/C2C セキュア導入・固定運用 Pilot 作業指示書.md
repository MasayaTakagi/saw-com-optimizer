# C2C セキュア導入・固定運用 Pilot 作業指示書

> **歴史的な引き継ぎ・作業指示の記録です。現行手順ではありません。** 本文中のブランチ名、コミット SHA、パス、件数、コマンド、停止条件は作成当時の状態を示します。実行前に現行状態と当該タスクの承認を確認してください。現在の開発方針は[ロードマップ](../project_roadmap.md)、[現行ベースライン](../history/current_baseline.md)、[アーキテクチャ概要](../architecture_overview.md)、C2C の運用・セキュリティ方針は[C2C documentation](../c2c/README.md)を参照してください。

## 1. 目的

`saw-com-optimizer` に `codex-with-chatgpt`（以下 C2C）を導入し、ChatGPTを計画・レビュー層、Codexを実行層として利用できる状態を構築する。

ただし、C2C upstream の標準運用をそのまま採用せず、事前セキュリティレビュー結果に基づき以下を必須条件とする。

- レビュー済みcommitを固定して使用する
- C2Cの自動アップデートを禁止する
- Version Up前に必ずSecurity Reviewを挟む
- dependencyはlockfile固定でインストールする
- C2Cから見えるworkspaceを `saw-com-optimizer` のみに限定する
- `.git/` や不要な大容量・機密領域を `.c2cignore` で明示的に遮断する
- Windows実環境上でworkspace escapeができないことをcanary testする
- SAW optimizer本体の実験・Stage 3.8作業にはまだ着手しない

本作業完了後は結果を報告し、ChatGPTによるレビューを受けてから本採用可否を決定すること。

---

# 2. レビュー済みBaseline

今回使用を許可するC2C baselineは以下。

Repository:

```text
https://github.com/XiaoDuoYa/codex-with-chatgpt
```

Reviewed commit:

```text
9663b88753e35c76796c5bce000293e0bd22cd9e
```

このSHA以外へ勝手に更新してはならない。

作業開始時に upstream の `main` が先へ進んでいても、最新版へ更新してはならない。

必ず上記SHAへcheckoutすること。

---

# 3. 重要な禁止事項

本Pilot中は以下を禁止する。

1. C2Cを最新mainへ自動更新しない
2. `git pull` によりC2Cを更新しない
3. C2C Skillの標準update workflowを実行しない
4. `pnpm install` をlockfile更新可能な状態で実行しない
5. SAW optimizerのCOMモデルを変更しない
6. optimizerアルゴリズムを変更しない
7. Stage 3.8の実験を開始しない
8. 長時間optimizerを実行しない
9. SAW repositoryのMainへpushしない
10. GitHub credential、API key、SSH key等をログ・レビュー成果物へ出力しない
11. pairing code、OAuth token、refresh token、Cloudflare credentialを記録しない
12. 問題が起きた際にC2C sourceへ独自パッチを当てて無理に動かさない

本Pilotの目的は

```text
C2Cそのものを変更すること
```

ではなく、

```text
レビュー済みC2Cが
現在のWindows + saw-com-optimizer環境で
安全かつ実用的に動作すること
```

の確認である。

---

# 4. Phase 0 — 現在環境のBaseline取得

まず `saw-com-optimizer` の状態を記録する。

最低限以下を取得すること。

```powershell
git status --short
git branch --show-current
git rev-parse HEAD
git remote -v
python --version
git --version
node --version
```

既存repositoryに未commit変更がある場合は勝手に修正・stash・commitしない。

状態を報告書へ記録する。

このPilotによって既存SAW sourceに意図しない変更が発生していないことを、最後に比較できるようにすること。

---

# 5. Phase 1 — C2CをSAW repository外へ配置

C2C repositoryは `saw-com-optimizer` の内部へ置かない。

例えば以下のような兄弟directoryとする。

```text
...\ChatGPT\
├─ saw-com-optimizer\
└─ codex-with-chatgpt\
```

既存のディレクトリ構成に合わせて適切な場所を選択してよい。

clone後、必ず以下を確認する。

```powershell
git remote -v
git fetch origin
git checkout 9663b88753e35c76796c5bce000293e0bd22cd9e
git rev-parse HEAD
git status --short
```

期待値:

```text
HEAD = 9663b88753e35c76796c5bce000293e0bd22cd9e
working tree clean
```

この状態を `C2C Reviewed Baseline` とする。

---

# 6. Phase 2 — Dependency固定インストール

通常の

```text
pnpm install
```

だけを使用してはならない。

必ずlockfileを固定して、

```powershell
corepack pnpm install --frozen-lockfile
```

を使用する。

その後、

```powershell
corepack pnpm build
```

を実行する。

可能であれば続けて、

```powershell
corepack pnpm typecheck
corepack pnpm test
```

を実行する。

結果を記録する。

## STOP条件

以下の場合は作業を停止する。

- `--frozen-lockfile` が失敗し、lockfile更新を要求する
- package.json / pnpm-lock.yamlを書き換えないとbuildできない
- 新しいdependency追加が要求される
- install途中で想定外の外部script実行が要求される
- test failureがSecurity関連に見える

lockfileを変更して無理に進めないこと。

---

# 7. Phase 3 — C2C Skillを安全運用用に変更

Upstream `skill/SKILL.md` には自動Version Up workflowが含まれている。

このままCodexへインストールしてはならない。

## 方針

**C2C本体のsource codeは変更しない。**

CodexへコピーするSkillだけを、ローカル運用ポリシーに合わせて変更する。

upstream側の原本:

```text
codex-with-chatgpt\skill\SKILL.md
```

は可能な限り変更せず、

Codex Skill install先:

```text
%USERPROFILE%\.codex\skills\codex-with-chatgpt\SKILL.md
```

にコピーしたものだけを調整する。

## 自動更新ルールの置き換え

以下の標準動作を禁止する。

```text
updateAvailable
↓
git pull
↓
pnpm install
↓
build
↓
restart
```

代わりに次のルールを明記する。

```text
C2C Update Policy

- update-check may only detect an update.
- Never run git pull automatically.
- Never run git stash automatically.
- Never run pnpm install for a new revision automatically.
- Never reinstall SKILL.md automatically.
- Never switch C2C commit automatically.

If updateAvailable == true:

1. Report:
   "C2Cの更新が検出されました。現在のレビュー済みVersionを維持します。"
2. Report current commit SHA.
3. Report candidate remote commit SHA.
4. STOP the C2C update.
5. Continue the user's original task using the currently reviewed version where possible.
6. Wait until a separate Security Review approves the new SHA.
```

重要:

ユーザーが単に

```text
C2Cを使って作業して
```

と指示しただけでは更新してはならない。

「最新版へ更新して」というユーザー指示があっても、直接更新せず、

```text
Security Review required
```

として候補SHAを提示して止めること。

---

# 8. Phase 4 — `.c2cignore` の導入

`saw-com-optimizer` rootに `.c2cignore` を設ける。

既存ファイルが存在する場合は上書きせず内容を確認して追記する。

初期案:

```gitignore
# VCS metadata
.git/

# C2C should not consume archive/review bundles directly
**/*.zip

# Raw/heavy experiment data
runs/**/raw/
runs/**/checkpoints/
runs/**/*.ckpt
runs/**/*.checkpoint

# Temporary/cache data
tmp/
temp/
cache/
__pycache__/
.pytest_cache/

# Private / confidential material if present
private/
confidential/

# Licensed/reference material if redistribution/readout is undesirable
references/licensed/
```

ただし現在のSAW repository構造を確認し、

```text
ChatGPTレビューに必要なmd/csv/json
```

まで過剰に遮断しないこと。

例えば以下は原則読める状態を維持する。

```text
README
docs
handoff
review summaries
metrics CSV
JSON summaries
source code
tests
configuration without credentials
```

`.c2cignore` の目的は、

```text
必要なものだけChatGPTから見える
```

状態を作ることである。

---

# 9. Phase 5 — `.c2cignore` の動作テスト

本物の秘密情報を使ってテストしてはならない。

workspace内部に一時的なcanaryを作成してよい。

例:

```text
private/c2c_canary_private.txt
```

内容:

```text
C2C_PRIVATE_CANARY_20260925
```

通常領域にもcanaryを作成。

```text
c2c_canary_public.txt
```

内容:

```text
C2C_PUBLIC_CANARY_20260925
```

期待結果:

```text
public canary  → ChatGPT/MCPから読める
private canary → ChatGPT/MCPから読めない
```

テスト後はcanaryを削除する。

SAW source自体には変更を残さない。

---

# 10. Phase 6 — Windows workspace escape Canary

今回のSecurity Reviewでは、

- `../`
- absolute path
- Windows style traversal
- symlink escape

に対する実装とテストを確認済み。

ただしWindowsではsymlink作成権限によりupstreamテストがskipされる可能性がある。

そのため実環境でも追加確認する。

## 通常path escape

C2C workspaceを

```text
...\saw-com-optimizer
```

として起動した状態で、MCP経由のアクセスについて以下が拒否されることを確認する。

```text
../
..\..\

C:\Users\<current-user>\
C:\Users\<current-user>\Documents\
```

ただしMainUserの実ファイルを読み取るテストはしない。

可能ならSAW workspaceの外側に一時canaryを作る。

例:

```text
...\c2c_outside_canary.txt
```

内容:

```text
C2C_OUTSIDE_CANARY_20260925
```

期待:

```text
MCP read_file → PATH_OUTSIDE_WORKSPACE
```

テスト後canaryを削除する。

---

# 11. Phase 7 — Symlink / Junction escape

Windows環境で安全に実施可能であれば、

workspace内のlinkからworkspace外canaryへアクセスできないことを確認する。

例:

```text
saw-com-optimizer\c2c_escape_link
    ↓
workspace外canary
```

期待:

```text
C2C → PATH_OUTSIDE_WORKSPACE
```

ただしsymlink/junction作成に管理者権限が必要な場合、

**管理者昇格してまでテストしない。**

その場合は、

```text
SKIPPED — Windows privilege unavailable
```

と報告書へ記録する。

---

# 12. Phase 8 — C2C Setup

ここまでPASSした後でC2C setupへ進む。

以下を確認する。

```powershell
node "<C2C checkout>\bin\c2c.js" workspace -w "<saw-com-optimizer>" --json
```

Workspace rootが正確に `saw-com-optimizer` になっていること。

次に、

```powershell
c2c sandbox-allow --json
```

を実行する。

この処理が変更するのは、

```text
Codex config.toml
```

のC2C state directory writable rootのみであることを確認する。

変更前後の差分を記録する。

---

# 13. Phase 9 — Tunnel / Connector setup

Pilotでは安定性優先でQuick Tunnelを使用してよい。

ただし以下を理解した上で進める。

```text
Bridge本体 = localhostのみ
Cloudflare Tunnel = 公開MCP endpoint
```

公開endpointが存在する時間を必要最小限にする。

ChatGPT connectorへ接続し、OAuth pairingを行う。

以下の情報を報告書に保存してはならない。

```text
pairing code
access token
refresh token
OAuth authorization code
admin token
Cloudflare cert
Cloudflare tunnel credential
```

public URLも報告書では必要ならhostnameを伏せる。

---

# 14. Phase 10 — MCP Read-only確認

ChatGPT側から最低限以下を確認する。

```text
workspace_info
list_directory
read_file
search_workspace
git_status
git_diff
```

確認項目:

1. workspace名が正しい
2. rootが `saw-com-optimizer` に限定されている
3. source codeを読める
4. public canaryを読める
5. `.c2cignore`対象を読めない
6. workspace外canaryを読めない
7. `.git/config` を読めない
8. `.env` 等を読めない
9. Git status/diffにsensitive pathが出ない

---

# 15. Phase 11 — MCP Tool surface確認

ChatGPTに公開されるMCP tool一覧を確認する。

期待:

```text
workspace_info
list_directory
read_file
search_workspace
git_status
git_diff
test_status
execution_summary
execution_output
```

以下が存在しないこと。

```text
write_file
delete_file
execute_shell
git_commit
install_package
```

もしwrite/exec系toolが存在する場合は、

**即STOP。**

その状態では本採用しない。

---

# 16. Phase 12 — 小規模C2C Loop Test

SAW本体を変更する作業はまだしない。

Pilot専用の無害な一時Markdown等を用いて、

```text
INIT
↓
PLAN
↓
Codex execution
↓
EXECUTED
↓
ChatGPT independent review
↓
DONE
```

を1回通す。

ChatGPTがCodexの説明を信用するだけでなく、

```text
git_status
git_diff
test_status
```

等から実際の状態を確認できているか確認する。

テスト終了後、一時ファイル・差分を元に戻す。

---

# 17. Phase 13 — C2C update protection test

今回最重要のGate。

現在commit:

```text
9663b88753e35c76796c5bce000293e0bd22cd9e
```

からremote HEADが進んでいる場合でも、

```text
c2c update-check
```

を実行した際に、

```text
update detected
↓
通知のみ
↓
git pullしない
↓
buildしない
↓
restartしない
```

ことを確認する。

以下が勝手に実行された場合はFAIL。

```text
git pull
git stash
pnpm install
pnpm build
Skill overwrite
C2C revision変更
```

最終的に、

```powershell
git rev-parse HEAD
```

が

```text
9663b88753e35c76796c5bce000293e0bd22cd9e
```

のままであること。

---

# 18. Phase 14 — 最終Regression

C2C repository:

```powershell
git status --short
git rev-parse HEAD
```

SAW repository:

```powershell
git status --short
git rev-parse HEAD
```

をPhase 0と比較する。

許可された恒久変更は原則、

```text
.c2cignore
必要なら .c2c.json
Codex local Skill
Codex config.toml
C2C state
```

のみ。

SAW source code・optimizer・COM code・tests・Stage scriptに変更があってはならない。

---

# 19. PASS条件

以下をすべて満たせばPilot PASS。

- C2C SHAがReviewed Baselineのまま
- frozen lockfile install成功
- build成功
- test成功または合理的に説明可能
- workspace外アクセス拒否
- `.git/` 読み取り拒否
- `.c2cignore`対象拒否
- sensitive file拒否
- MCPがread-only
- OAuth接続成功
- Git diff/status確認成功
- C2C loop 1回成功
- update検出時に自動更新されない
- SAW sourceに意図しない変更なし
- credential漏洩なし

---

# 20. STOP / FAIL条件

以下のいずれかが発生したら、その時点で本採用へ進まず停止。

- workspace外ファイルを読めた
- `.c2cignore`対象を読めた
- `.git/config`を読めた
- MCPにwrite/exec toolが存在した
- C2Cが自動updateした
- Reviewed SHAが意図せず変わった
- frozen lockfileでinstallできない
- unexpected dependency追加が必要
- credential/tokenがlogへ露出
- ChatGPT connectorから別workspaceが見える
- WindowsでC2Cが不安定で実用にならない
- C2C導入がSAW optimizerの通常動作へ影響
- setupのためにC2C本体source修正が必要

FAIL時も独自修正を行わず、証拠をまとめて終了する。

---

# 21. Version Up運用ルール

Pilot PASS後もC2Cを自動更新してはならない。

以後のVersion Upは必ず以下。

```text
Reviewed SHA A
    ↓
update candidate SHA Bを検出
    ↓
更新しない
    ↓
A..B のdiff取得
    ↓
ChatGPT Security Review
    ↓
src/
skill/
package.json
pnpm-lock.yaml
workspace/auth/network/subprocess
dependency advisory
を確認
    ↓
PASS
    ↓
ユーザー承認
    ↓
SHA Bへ更新
    ↓
pnpm install --frozen-lockfile
build
test
Windows canary
    ↓
SHA Bを新Reviewed Baselineとする
```

Codexだけの判断で更新してはならない。

---

# 22. 作業報告書

Pilot完了後、以下の報告書を作成する。

推奨ファイル名:

```text
c2c_secure_pilot_validation_20260925.md
```

報告内容:

## Environment

- Windows version
- Codex version
- Node version
- pnpm version
- Git version
- cloudflared version

## C2C Baseline

```text
Repository
Commit SHA
package version
```

## Gates

各Phaseについて:

```text
PASS / FAIL / SKIPPED
```

を明記。

## Security Validation

- workspace containment
- absolute path
- traversal
- symlink/junction
- sensitive files
- `.c2cignore`
- `.git`
- MCP tool surface
- OAuth
- execution output
- update protection

## Git State

SAW repository:

```text
before HEAD
after HEAD
before dirty state
after dirty state
```

C2C repository:

```text
final HEAD
final status
```

## Issues

発生した問題を列挙。

## Conclusion

以下のいずれか。

```text
PASS
PARTIAL
FAIL
```

ただしCodex自身が、

```text
本番導入決定
```

をしてはならない。

---

# 23. 最終停止点

報告書を作成したら停止する。

**Stage 3.8へ進まない。**

**C2Cを本番運用へ切り替えない。**

**Mainへpushしない。**

次の工程は、

```text
ChatGPTによるPilot結果レビュー
```

とする。

---

# 24. 今回の最優先事項

今回のPilotでは機能の多さより、

```text
安全に限定されたworkspaceだけを
レビュー済みC2Cが
read-onlyでChatGPTへ公開できること
```

を優先する。

不明点が出た場合も、利便性のためにsecurity boundaryを緩めないこと。

特に、

```text
自動update禁止
Reviewed SHA固定
workspace containment
read-only MCP
.c2cignore
```

の5点はHard Gateとして扱うこと。
