# SAW COM Optimizer
# Git / Codex Root 移行 実行指示書

作成日: 2026-09-12  
対象: `saw-com-optimizer`  
目的: Git root / Codex project root / source root / `.codex` root を統一し、SessionStart Hookを正しく動作させる  
重要: 既存branch・旧root・remote履歴を壊さず、新rootをstaging検証してから切り替える

---

## 1. 現状認識

現在の主要状態:

```text
Current Git root:
C:\Users\sub\Documents\ChatGPT\New project

Current source root:
C:\Users\sub\Documents\ChatGPT\New project\saw-com-optimizer

Current branch:
codex/50ohm_DMS

Current remote:
https://github.com/MasayaTakagi/saw-com-optimizer.git

Rollback baseline commit:
201f9bf
```

現repoは実質SAW COM Optimizer専用であり、tracked filesの大半は
`saw-com-optimizer/`配下にある。

現在の問題は:

```text
Git root
!=
Codex project root
!=
.codex root
```

となっていること。

これによりproject-local `.codex/hooks.json` が実Codex環境で
SessionStart Hookとして認識されない。

---

# 2. 最終目標

最終的に:

```text
C:\Users\sub\Documents\ChatGPT\saw-com-optimizer
```

を唯一の:

```text
Git repository root
Codex project root
source root
.codex configuration root
```

とする。

目標構成:

```text
ChatGPT/
│
├─ saw-com-optimizer/
│  ├─ .git/
│  ├─ .codex/
│  │  ├─ hooks.json
│  │  ├─ hooks/
│  │  └─ runtime/                 [gitignored]
│  │
│  ├─ AGENTS.md
│  ├─ README.md
│  ├─ pyproject.toml
│  │
│  ├─ src/
│  ├─ tests/
│  ├─ configs/
│  ├─ experiments/
│  ├─ scripts/
│  │
│  ├─ docs/
│  │  ├─ architecture/
│  │  ├─ plans/
│  │  └─ handoff/
│  │
│  ├─ runs/                       [gitignored]
│  │
│  └─ artifacts/                  [gitignored]
│     └─ review_bundles/
│
├─ New project/                   [旧root。検証完了まで保全]
└─ archive/                       [後段で使用]
```

---

# 3. 最重要方針

## 3.1 既存branchを書き換えない

以下はそのまま保全する。

```text
codex/50ohm_DMS
201f9bf
origin/codex/50ohm_DMS
```

force push禁止。

---

## 3.2 いきなりhistory rewriteしない

今回の主目的は:

```text
Git root
=
Codex root
=
.codex root
```

を実現し、Hookを動かすこと。

過去commitすべてのpathを完全に美しく書き換えることではない。

まず新branch / 新working treeでroot統一を実現し、
Gate Aを通す。

完全なhistory rewriteは必要性を再評価してから別作業とする。

---

## 3.3 第一候補は `git subtree split`

現在のrepo構成に対して:

```bash
git subtree split --prefix=saw-com-optimizer -b codex/root-migration
```

を第一候補として検討する。

目的:

```text
old history:
saw-com-optimizer/src/...

new branch:
src/...
```

へroot化された履歴を作る。

利点:

- 既存branch非破壊
- force push不要
- git-filter-repo追加不要
- 元repoをそのままrollback基準として保持可能

---

# 4. 実施フェーズ

---

## Phase 0 — Preflight

変更前に必ず確認・記録する。

```bash
git rev-parse --show-toplevel
git status
git branch --show-current
git remote -v
git log --oneline --decorate -20
git ls-files
```

さらに確認:

- working tree clean
- rollback commit = `201f9bf`
- remote branch存在
- `saw-com-optimizer/`が通常tracked directory
- nested `.git`なし
- `handoff/`内容
- `.github/`内容
- `review_bundles/`がignored
- `runs/`がignored

この結果をログとして保存。

---

## Phase 1 — root migration branch生成

旧rootで:

```bash
git subtree split \
  --prefix=saw-com-optimizer \
  -b codex/root-migration
```

実行前にcommandと期待結果を表示する。

実行後:

```bash
git log --oneline codex/root-migration -20
git ls-tree --name-only codex/root-migration
```

期待:

```text
src/
tests/
configs/
...
```

がbranch rootに存在。

`saw-com-optimizer/` prefixが残っていないこと。

異常なら停止。

---

## Phase 2 — 新working copy構築

新root:

```text
C:\Users\sub\Documents\ChatGPT\saw-com-optimizer
```

を作成する。

推奨:

- temporary clone
- worktree
- branch checkout

のいずれか安全な方法を選ぶ。

重要:

旧:

```text
ChatGPT\New project
```

は削除・移動しない。

新working copyで:

```text
branch = codex/root-migration
```

をcheckout。

---

## Phase 3 — 親rootに残っていた必要ファイルを移植

旧親rootにある必要ファイルを確認し、
新repoへ整理して追加する。

### 3.1 handoff

旧:

```text
New project/handoff/
```

から:

```text
saw-com-optimizer/docs/handoff/
```

へ移す。

分類:

```text
docs/handoff/
    Codexへの具体的実装指示

docs/plans/
    長期実験計画・ロードマップ

docs/architecture/
    現行設計仕様
```

分類が曖昧なら無理に分けず、
まず`docs/handoff/`へ置いてよい。

---

### 3.2 `.github`

旧:

```text
New project/.github/
```

から必要なworkflowを新rootへ移す。

特にCI内の:

```text
working-directory: saw-com-optimizer
```

等を検索。

新root化後は不要になる可能性が高い。

---

### 3.3 README / `.gitignore`

親root側のREADME / `.gitignore`のうち、
projectに必要な内容を新root側へ統合。

重複を整理。

---

# 5. review bundle構成変更

旧:

```text
New project/review_bundles/
```

新:

```text
saw-com-optimizer/artifacts/review_bundles/
```

とする。

`artifacts/`はGit管理しない。

---

## 5.1 review bundle code修正

現在の:

```text
src/sawopt/reporting/review_bundle.py
```

を確認。

以下のようなロジックがあれば修正:

```text
repo rootの親に.gitがあれば
その親をworkspace rootにする
```

新しい原則:

```text
repo_root
=
git root
=
project root
```

review bundle既定出力:

```text
<repo_root>/artifacts/review_bundles
```

とする。

必要ならCLI/configで出力先override可能とする。

---

## 5.2 path依存全検索

検索対象:

```text
New project
../handoff
../review_bundle
../review_bundles
review_bundle
review_bandle
saw-com-optimizer/review_bundles
working-directory
```

対象:

- source
- tests
- scripts
- README
- AGENTS.md
- docs
- CI
- callback prompt
- review bundle生成処理

ユーザー固有のabsolute Windows pathをsourceへ固定しない。

---

# 6. `.gitignore`整理

最低限:

```gitignore
.codex/runtime/
runs/
artifacts/
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
```

既存追跡済みファイルを誤って消さない。

---

# 7. root統一確認

新rootで:

```bash
git rev-parse --show-toplevel
```

期待:

```text
C:\Users\sub\Documents\ChatGPT\saw-com-optimizer
```

さらにCodex起動directoryも同じにする。

不変条件:

```text
git root
=
Codex cwd
=
project root
=
.codex root
```

---

# 8. まずコード回帰試験

Hook検証前に以下を実行。

```text
pytest
unittest discovery
orchestration tests
short SAW integration
```

期待:

- 既存test regressionなし
- COM Core変更なし
- Optimizer Core数値変更なし

失敗した場合はHook検証へ進まない。

---

# 9. Codex / Hook検証

新root:

```text
C:\Users\sub\Documents\ChatGPT\saw-com-optimizer
```

からCodexを起動。

---

## 9.1 Hook review / trust

project-local:

```text
.codex/hooks.json
```

をCodexが認識することを確認。

Hookをreview/trust。

---

## 9.2 real SessionStart

新しいCodex sessionを開始。

期待:

```text
SessionStart
→ .codex/hooks.json
→ capture_session
→ .codex/runtime/current_session.json
```

確認:

```text
session_id
cwd
project_root
timestamp
```

特に:

```text
cwd == project root
```

またはproject root配下。

---

# 10. Gate A callback再試験

Hook成功後にdummy async callbackを実行。

production SAW禁止。

フロー:

```text
Session A
↓
Hook capture
↓
async dummy
↓
Codexターン終了
↓
worker継続
↓
result生成
↓
codex exec resume A
↓
Aへcallback
↓
REVIEWED
```

---

# 11. Multi-session再試験

Session A / Bで:

```text
run A → A
run B → B
```

を確認。

manifestとactual resumed thread IDが一致すること。

---

# 12. Production Gate A

以下すべてPASSでGate A通過。

```text
Git root alignment
Codex root alignment
.codex root alignment
real SessionStart Hook
explicit session ID
real callback
actual resumed thread validation
multi-session A/B
regression tests
short SAW
```

結果:

```text
Production Gate A: PASS
```

または:

```text
Production Gate A: FAIL
```

と明記。

---

# 13. Medium-duration test

Gate A PASS後のみ実施。

15～30分程度のcontrolled run。

目的:

- detached worker長時間生存
- callback timeout
- stale lock
- duplicate callback
- worker/optimizer PID
- Codex session解放

を確認。

同時workerは必要に応じ2本まで。

production最大探索はまだ禁止。

---

# 14. 旧rootの扱い

以下完了まで:

```text
ChatGPT/New project
```

は削除しない。

条件:

- new root tests PASS
- Hook PASS
- callback PASS
- multi-session PASS
- Gate A PASS
- medium-duration test PASS
- Git/remote確認済み

その後:

```text
New project
→ archive/New project_pre_root_migration_20260912
```

へ移動可。

削除はさらに後。

---

# 15. remote運用

旧branch:

```text
origin/codex/50ohm_DMS
```

は保全。

新branch:

```text
codex/root-migration
```

をremoteへpushして検証可能。

禁止:

- force push
- old branch rewrite
- main rewrite
- tag削除

Gate A PASS後に、
新branchを今後のdevelopment lineへ切り替えるか別途判断。

---

# 16. 完全history rewriteについて

今回の作業には含めない。

必要性がある場合のみ別途:

- git-filter-repo
- path rename history
- handoff history統合

を検討。

Gate A通過前に実施しない。

---

# 17. 停止条件

以下の場合は即停止して報告。

- `git subtree split`結果が期待と違う
- existing historyが欠落
- working treeがcleanでない
- remote/branch状態が想定外
- untracked重要ファイルが見つかる
- COM / Optimizerの数値差分が出る
- test regression
- Hook未認識
- callback cross-session
- Git履歴書き換えが必要になった
- force pushが必要になった

---

# 18. 作業完了報告

以下を報告。

## Git

```text
old root:
new root:
old branch:
new branch:
rollback commit:
remote:
force push used: NO
```

## File migration

```text
handoff:
.github:
README:
.gitignore:
review bundles:
```

## Path fixes

修正したfile一覧。

## Tests

```text
pytest:
unittest:
orchestration:
short SAW:
real Hook:
dummy callback:
multi-session:
```

## Gate

```text
Production Gate A: PASS / FAIL
```

## Risks

残存リスク。

## Next

Gate A PASSならmedium-duration test案。

---

# 19. Codexへ最初に入力するプロンプト

以下をそのまま使用する。

```text
添付/指定した
「Git / Codex Root 移行 実行指示書」
に従って作業してください。

今回の方針は、
既存branch `codex/50ohm_DMS` とrollback commit `201f9bf`
を完全に保全したまま、新しいroot化branchを作って検証することです。

第一候補として
`git subtree split --prefix=saw-com-optimizer`
を使い、新branch `codex/root-migration` を作る方針を検討してください。

重要:
- 既存branchを書き換えない
- force pushしない
- git-filter-repoは今回使わない
- 旧 `New project` を削除しない
- production runを開始しない
- COM / Optimizer数値アルゴリズムを変更しない

作業は以下の順序で行ってください。

1. Preflight Git状態確認
2. subtree splitの安全性確認
3. root migration branch生成
4. 新working root構築
5. handoff / .github / README / .gitignore整理
6. review bundleを`artifacts/review_bundles`へ統一
7. 古いpath依存修正
8. Git root確認
9. 全回帰test
10. 新rootからCodexを起動してHook review/trust
11. real SessionStart Hook
12. dummy callback
13. multi-session A/B
14. Production Gate A再判定

Git履歴破壊、remote rewrite、force pushが必要になった場合は、
そこで停止して承認を求めてください。

最後に、
- old/new root
- branch
- Git履歴
- 移動ファイル
- path修正
- test結果
- Hook結果
- callback結果
- Production Gate A
をまとめて報告してください。
```

---

# 20. 完成条件

最終的に:

```text
C:\Users\sub\Documents\ChatGPT\saw-com-optimizer
```

が:

```text
Git root
Codex root
source root
.codex root
```

として一致し、

```text
SessionStart Hook
→ async execution
→ original Codex session resume
```

まで実環境で動作すること。

これを本移行作業の完成条件とする。
