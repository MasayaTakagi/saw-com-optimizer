# SAW COM Optimizer
# プロジェクトルート再編・Git/Codex統合作業計画書

作成日: 2026-09-12  
対象: `saw-com-optimizer`  
目的: Git repository root、Codex project root、ソースコードroot、`.codex` Hookの適用rootを一致させる  
重要: この作業ではproduction最適化を開始しない

---

# 1. 結論

現在の

```text
ChatGPT/
└─ New Project/
   ├─ .git/                  ? 現在の親Git repo
   ├─ saw-com-optimizer/
   ├─ handoff/
   └─ review_bundle/
```

という構成は廃止し、最終的に以下へ整理することを推奨する。

```text
ChatGPT/
│
├─ saw-com-optimizer/        ★ Git repo / Codex project / source root
│  ├─ .git/
│  ├─ .codex/
│  │  ├─ hooks.json
│  │  ├─ hooks/
│  │  └─ runtime/            # gitignore
│  │
│  ├─ AGENTS.md
│  ├─ pyproject.toml
│  ├─ src/
│  ├─ tests/
│  │
│  ├─ docs/
│  │  ├─ architecture/
│  │  ├─ plans/
│  │  └─ handoff/
│  │
│  ├─ runs/                  # gitignore
│  │
│  └─ artifacts/             # gitignore
│     └─ review_bundles/
│
├─ scratch/                  # 任意。ChatGPT配下の一時作業
└─ archive/                  # 任意。旧成果物や退避物
```

`New Project`階層は原則不要。

Codexで開くフォルダも必ず:

```text
...\ChatGPT\saw-com-optimizer
```

とする。

---

# 2. この構成にする理由

最重要原則:

```text
1 Git repo
=
1 Codex project root
=
1 source root
=
1 .codex configuration root
```

これにより以下を一致させる。

```text
git rev-parse --show-toplevel
        =
Codex working directory
        =
saw-com-optimizer/
        =
.codex/hooks.json のroot
```

今回発生したSessionStart Hook未発火の原因は、
Codexが親Git repoをproject rootとして認識した一方、
`.codex/hooks.json`がその子ディレクトリに置かれていたため。

rootを統一すれば、この曖昧さをなくせる。

---

# 3. 各ディレクトリの役割

## 3.1 `.git/`

`saw-com-optimizer`専用Git repository。

他の無関係なChatGPT作業ファイルを含めない。

---

## 3.2 `.codex/`

このrepo専用のCodex設定。

```text
.codex/
├─ hooks.json
├─ hooks/
│  └─ capture_session.*
└─ runtime/
```

`.codex/runtime/`はsession ID等の実行時stateなのでGit管理しない。

---

## 3.3 `docs/handoff/`

現在`New Project/handoff`に置いているうち、

- Codexへの実装指示書
- リファクタリング計画
- 実験計画
- architecture変更指示
- 将来参照価値がある作業指示

を移動する。

これらはGit管理する。

例:

```text
docs/handoff/
├─ async_orchestration_initial_plan.md
├─ production_gate_a_instructions.md
└─ optimizer_refactor_plan.md
```

目的:

```text
どの指示書
→ どのコード変更
```

をGit履歴から追跡できるようにする。

---

## 3.4 `docs/plans/`

handoffより長期的な実験計画・ロードマップ。

例:

```text
docs/plans/
├─ optimizer_long_term_plan.md
└─ impedance_search_plan.md
```

handoffとplansが現時点で明確に分かれていなければ、
最初は`docs/handoff/`だけでもよい。

不要な分類を増やしすぎない。

---

## 3.5 `artifacts/review_bundles/`

現在の`review_bundle`または`review_bandle`相当。

ここには:

- review用ZIP
- 自動生成したレビューbundle
- 一時的な提出用成果物
- validation bundle

を保存する。

Git管理しない。

Codex workspace内に置く理由:

```text
Codex callback
↓
workspace_write sandbox
↓
runs/ と review_bundles/ の両方へ自然にアクセス
```

親ディレクトリ`../review_bundle`への依存をなくす。

---

## 3.6 `runs/`

Optimizerのrun output。

Git管理しない。

run manifest / status / logs / optimizer results等を現在の設計どおり保存する。

---

## 3.7 `scratch/` と `archive/`

これはrepo外、`ChatGPT/`直下に置く。

```text
ChatGPT/
├─ saw-com-optimizer/
├─ scratch/
└─ archive/
```

用途:

`scratch/`
- 一時展開
- 比較用ファイル
- 一回限りの検証
- repoに入れる必要がないもの

`archive/`
- 移行前backup
- 古いreview bundle
- 廃止したフォルダ
- 長期保存するがactive projectから分離したいもの

必須ではない。

---

# 4. `.gitignore`推奨

既存内容を確認した上で、最低限以下を考慮する。

```gitignore
# Runtime
.codex/runtime/

# Optimizer outputs
runs/

# Generated review artifacts
artifacts/

# Python
__pycache__/
*.py[cod]
.pytest_cache/

# Virtual environment
.venv/

# Local tooling / temporary
*.tmp
*.log
```

注意:

既に追跡済みの重要ログやartifactがある場合は、
機械的に削除しないこと。

---

# 5. Git移行で最も重要な注意

現在:

```text
ChatGPT/New Project/.git
```

が存在する可能性がある。

その場合、単純に

```text
saw-com-optimizer/.git
```

を追加してnested repositoryにしてはならない。

最初に必ずGit状態を調査する。

確認項目:

```bash
git rev-parse --show-toplevel
git status
git remote -v
git log --oneline --decorate -20
git ls-files
```

さらに:

- `saw-com-optimizer/`が現在の親repoでtrackedか
- `handoff/`がtrackedか
- `review_bundle/`がtrackedか
- remote GitHub repositoryが存在するか
- 現履歴を維持する価値があるか
- uncommitted changesがあるか

を確認する。

---

# 6. Git移行方式の判断

調査結果に応じて以下から選択する。

## Case A: 親repoが実質`saw-com-optimizer`専用

親repoの主目的がこのプロジェクトであり、
他に重要な独立projectを含まない場合。

推奨:

- 既存履歴を最大限維持
- project rootを`saw-com-optimizer`へ移す方法を検討
- 必要なら一時clone / branchを使う
- root path変更による履歴への影響を確認

ただし`.git`を単純移動するだけで済むとは決めつけない。

---

## Case B: 親repoに複数の独立projectがある

`saw-com-optimizer`だけを独立repoへ抽出する。

履歴を維持する必要がある場合:

- temporary clone
- `git filter-repo`等によるsubdirectory抽出

を候補とする。

`git filter-repo`が未導入なら、
ユーザー許可なく追加導入しない。

履歴維持が不要または履歴が浅い場合は:

- 現状態をbackup
- `saw-com-optimizer`で新規repo初期化
- clean initial commit

も選択肢。

---

## Case C: 親Git履歴がほぼ不要

最も単純。

```text
backup
↓
saw-com-optimizerをChatGPT直下へ移動
↓
新規git init
↓
remote設定
↓
initial commit
```

ただしこれは履歴を失うため、
Codexが勝手に判断して実行してはならない。

---

# 7. 移行前バックアップ

変更前に必ずバックアップを作成する。

例:

```text
ChatGPT/archive/
└─ pre_repo_restructure_20260912/
```

最低限:

- 現在の`.git`関連情報
- `saw-com-optimizer`
- `handoff`
- review bundle
- uncommitted changes

を失わないようにする。

巨大なrun dataがある場合は、
無意味な全コピーを避けてもよいが、
何をbackup対象外にしたか報告する。

---

# 8. 推奨移行フロー

## Phase 0: 調査のみ

この段階ではファイルを移動しない。

確認:

1. `ChatGPT/New Project`のtree
2. Git root
3. tracked files
4. Git remote
5. uncommitted changes
6. `.codex`
7. `AGENTS.md`
8. hard-coded path
9. scripts / configs / tests内の`New Project`
10. handoff / review_bundleの内容

結果をユーザーへ短く報告。

---

## Phase 1: 移行方式決定

調査に基づき:

```text
A: 履歴維持してrepo分離
B: fresh repo
C: その他
```

から推奨案を提示。

**Git履歴を破壊する可能性のある変更は、実行前にユーザー承認を得る。**

ファイル配置の整理自体は、
安全にbackup済みであれば計画に従って進めてよい。

---

## Phase 2: 新しいrootへ配置

目標:

```text
ChatGPT/saw-com-optimizer/
```

へprojectを配置。

移行:

```text
New Project/saw-com-optimizer
→ ChatGPT/saw-com-optimizer
```

handoff:

```text
New Project/handoff
→ saw-com-optimizer/docs/handoff
```

review bundles:

```text
New Project/review_bundle
→ saw-com-optimizer/artifacts/review_bundles
```

ただし内容を確認してから分類する。

---

## Phase 3: project内パス更新

検索:

```text
New Project
../handoff
../review_bundle
review_bundle
review_bandle
absolute Windows paths
```

コード・config・docsに古い絶対/相対パスが残っていないか確認。

可能な限り:

```python
project_root / "runs"
project_root / "artifacts" / "review_bundles"
```

のようなproject-relative pathへ統一。

ユーザー個人の絶対パスをsource codeへ固定しない。

---

## Phase 4: Codex root確認

新rootで:

```bash
cd ...\ChatGPT\saw-com-optimizer
git rev-parse --show-toplevel
```

期待:

```text
...\ChatGPT\saw-com-optimizer
```

Codexも同じdirectoryから起動。

期待する状態:

```text
Codex cwd
=
Git root
=
project root
=
.codex root
```

---

## Phase 5: Hook再検証

Codex側でproject-local Hookをreview/trust。

その後、新しいCodex sessionを開始して:

```text
SessionStart
↓
.codex/hooks.json
↓
capture_session
↓
.codex/runtime/current_session.json
```

を実確認。

公式Codex Hooksのproject-local configuration/trustの仕様に従うこと。

---

## Phase 6: 回帰テスト

移行後:

- pytest
- unittest
- orchestration tests
- short SAW run
- async dummy callback
- real SessionStart Hook
- explicit session ID callback
- A/B multi-session

を再実行。

COM / Optimizerの数値結果に差分が出ないこと。

---

## Phase 7: Production Gate A再判定

期待:

```text
Git/Codex root alignment: PASS
SessionStart Hook: PASS
Explicit callback: PASS
Multi-session: PASS
Async orchestration: PASS
```

すべて通れば:

```text
Production Gate A: PASS
```

その後初めて15～30分程度のmedium-duration testへ進む。

production最大runはまだ実行しない。

---

# 9. `New Project`削除条件

以下をすべて確認するまで旧`New Project`を削除しない。

- [ ] 新repoから全test成功
- [ ] Git status正常
- [ ] remote正常
- [ ] 必要なGit履歴が保持されている
- [ ] handoff移行完了
- [ ] review bundles移行完了
- [ ] runs / artifactsへのpath正常
- [ ] Hook実発火
- [ ] callback成功
- [ ] backup存在

削除は最後。

できれば一度:

```text
New Project
→ archive/New Project_pre_restructure
```

へ退避し、
数日問題がないことを確認してから削除してもよい。

---

# 10. Codex運用ルール

今後Codexは必ず:

```text
...\ChatGPT\saw-com-optimizer
```

をprojectとして開く。

親:

```text
...\ChatGPT
```

からプロジェクト作業を開始しない。

旧:

```text
...\ChatGPT\New Project
```

も使用しない。

Codexへ作業を依頼するときは、
このrepo root内の:

```text
AGENTS.md
docs/handoff/
.codex/
```

を基準とする。

---

# 11. 推奨最終構成

```text
ChatGPT/
│
├─ saw-com-optimizer/
│  │
│  ├─ .git/
│  │
│  ├─ .codex/
│  │  ├─ hooks.json
│  │  ├─ hooks/
│  │  │  └─ capture_session.*
│  │  └─ runtime/                  [ignored]
│  │
│  ├─ AGENTS.md
│  ├─ pyproject.toml
│  ├─ README.md
│  │
│  ├─ src/
│  │  └─ sawopt/
│  │
│  ├─ tests/
│  │
│  ├─ docs/
│  │  ├─ architecture/
│  │  ├─ plans/
│  │  └─ handoff/
│  │
│  ├─ runs/                        [ignored]
│  │
│  └─ artifacts/                   [ignored]
│     └─ review_bundles/
│
├─ scratch/                         [optional]
│
└─ archive/                         [optional]
   └─ pre_repo_restructure_20260912/
```

---

# 12. Codexへの作業指示

このドキュメントを読んだ後、次の順序で作業すること。

## STEP 1 — 調査

**まだ移動・削除・git initしない。**

以下を確認して報告:

```text
1. 現在のfilesystem tree
2. current Git root
3. git status
4. remotes
5. recent history
6. tracked files
7. saw-com-optimizerが親repoでどう扱われているか
8. handoffの内容
9. review_bundle/review_bandleの内容
10. hard-coded pathの有無
11. .codex / AGENTS.mdの位置
```

---

## STEP 2 — 移行方式提案

調査結果に基づき:

```text
- 推奨Git移行方式
- 履歴への影響
- remoteへの影響
- rollback方法
```

を提示。

**履歴破壊またはremote変更を伴う場合は、ここで止まりユーザー承認を求める。**

---

## STEP 3 — 安全な移行

承認後:

```text
ChatGPT/saw-com-optimizer
```

を唯一のproject rootとして構築。

- `.git`
- `.codex`
- source
- tests
- AGENTS
- docs

を同一rootに揃える。

handoffを`docs/handoff/`へ整理。

review bundlesを`artifacts/review_bundles/`へ整理。

---

## STEP 4 — path修正

古い:

```text
New Project
../handoff
../review_bundle
```

等への依存を削除。

project-relative pathへ統一。

COM / Optimizerアルゴリズムは変更しない。

---

## STEP 5 — Git確認

必ず:

```text
git rev-parse --show-toplevel
```

が

```text
...\ChatGPT\saw-com-optimizer
```

を返すこと。

`git status`も確認。

---

## STEP 6 — Codex/Hook確認

この新rootからCodexを起動。

project-local Hookをreview/trust。

real SessionStart Hookを実行。

session capture成功を確認。

---

## STEP 7 — 全回帰試験

最低限:

```text
pytest
unittest
orchestration tests
short SAW
detached dummy
real callback
multi-session A/B
```

---

## STEP 8 — Gate再判定

以下を報告:

```text
Git root alignment: PASS/FAIL
Codex root alignment: PASS/FAIL
SessionStart Hook: PASS/FAIL
Async callback: PASS/FAIL
Multi-session: PASS/FAIL
Regression tests: PASS/FAIL

Production Gate A: PASS/FAIL
```

---

# 13. この作業で禁止すること

- 調査前の`git init`
- nested `.git`の作成
- backupなしの`.git`削除
- Git historyの無断rewrite
- remoteの無断変更
- userの未commit変更の破棄
- production optimizer実行
- COM / Optimizer数値コード変更
- Hook trust/security機構のbypass
- sandbox/approvalの恒久無効化
- 古い`New Project`の早期削除

---

# 14. Codexへ最初に入力するプロンプト

以下をそのまま使用する。

```text
添付/指定した
「プロジェクトルート再編・Git/Codex統合作業計画書」
に従って作業してください。

最終目標は、
ChatGPT\saw-com-optimizer
を唯一の
- Git repository root
- Codex project root
- source root
- .codex configuration root
として統一することです。

現在のNew Project階層は最終的には廃止予定ですが、
まずSTEP 1の現状調査だけを行ってください。

特に、
- 親Git repoの状態
- Git履歴
- remote
- uncommitted changes
- saw-com-optimizerのtracked状態
- handoff
- review_bundle / review_bandle
- .codex
- AGENTS.md
- 古いpathへの依存
を確認してください。

この段階では、
git init、.gitの移動/削除、history rewrite、remote変更、
production run、ファイルの大規模移動をしないでください。

調査後、
1. 推奨移行方式
2. Git履歴への影響
3. rollback方法
4. 実施予定の具体的変更
を提示してください。

履歴破壊やremote変更の可能性がある場合は、
実行前に必ず停止して承認を求めてください。
```

---

# 15. 完成条件

最終的に:

```text
ChatGPT/saw-com-optimizer
```

を開けば、

```text
Git
Codex
Hooks
Source
Tests
Docs
Runs
Review artifacts
```

がすべて一つのproject boundary内で一貫して動作すること。

これを今回のproject structure整理の完成条件とする。
