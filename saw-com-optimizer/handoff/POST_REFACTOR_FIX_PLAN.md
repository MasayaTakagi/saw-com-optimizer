# POST_REFACTOR_FIX_PLAN.md

## 目的

この指示書は、`saw-com-optimizer` の大規模リファクタリング完了後レビューで見つかった残課題のみを修正するためのものです。

**新しい設計変更・アルゴリズム変更・追加リファクタリングは行わないこと。**

対象は以下の5項目です。

1. Stage 3.1 experiment定義の誤参照修正
2. preproductionのfull regression gateを全pytest対象にする
3. experiment YAML自身をprovenanceへ含める
4. architecture testの相対import解決を修正する
5. 修正後にGitコミット可能な状態へ整理する

---

# 0. 最重要原則

今回の作業は **リファクタリング後の仕上げ修正** です。

以下を変更してはいけません。

- COM計算ロジック
- SAW物理モデル
- objective / metrics
- design-space定義
- candidate canonicalization
- integer/discrete変数処理
- seed生成規則
- RNG呼び出し順序
- evaluation order
- unique-design budget accounting
- adaptive frequency exchange
- checkpoint semantics
- promotion gateの判定ロジック
- Stage 3.2のDE再多様化/retry仕様
- L-SHADE内部アルゴリズム
- SciPy DE設定
- 過去run結果

「ついでのclean-up」「名前変更」「型整理」「API再設計」も禁止します。

---

# 1. 作業開始前

最初に以下を実施してください。

```bash
git status
git diff
```

現在の変更内容を把握してください。

続いて、

```bash
PYTHONPATH=src python -m pytest --collect-only -q
```

でテスト収集数を確認してください。

レビュー時点では **100 tests collected** がbaselineです。

さらに既存テストを変更前に実行してください。

```bash
PYTHONPATH=src python -m pytest -q
```

一括実行が環境上長すぎる場合は、テストディレクトリ/ファイル単位に分割して構いません。

ただし最終的には **収集された全テストがPASSすること** が必要です。

---

# 2. HIGH: Stage 3.1 experiment定義を修正

## 問題

現在、

```text
experiments/stage3_1_convergence/experiment.yaml
```

がStage 3.1のexperimentであるにもかかわらず、

```text
configs/studies/stage3_2_convergence_50ohm.yaml
```

をbase configとして参照しています。

Stage 3.1とStage 3.2は同一の実験条件ではありません。

元のStage 3.1設定である

```text
configs/studies/stage3_convergence_50ohm.yaml
```

にはStage 3.1固有の設定がありますが、現在は

```text
../../stage3_1_convergence_fragment.yaml
```

が欠損しているため、そのままではロード不能です。

## 修正方針

**欠損fragmentの内容を推測して再構築してはいけません。**

Git履歴に正しい

```text
stage3_1_convergence_fragment.yaml
```

が存在する場合のみ、それを復元してください。

確認例:

```bash
git log --all -- configs
git log --all -- '*stage3_1*'
git show <commit>:<path>
```

### ケースA: 正しいfragmentをGit履歴から復元できる場合

復元したうえで、

```text
experiments/stage3_1_convergence/experiment.yaml
```

が正しいStage 3.1 configを参照するよう修正してください。

### ケースB: 正しいfragmentを復元できない場合

Stage 3.2設定をStage 3.1として使い続けてはいけません。

以下のいずれかで「未移行」を明確にしてください。

推奨:

- `experiments/stage3_1_convergence/experiment.yaml` をcanonical execution targetから外す
- READMEに
  - legacy Stage 3.1 config fragment is missing
  - Stage 3.1 experiment is intentionally not migrated
  と明記する
- CLIやドキュメントから「Stage 3.1 canonical experiment」として案内しない

削除する場合も、履歴を失わないよう理由をREADME/commit messageに残してください。

## 禁止

絶対に以下をしないこと。

```yaml
base_config: ../../configs/studies/stage3_2_convergence_50ohm.yaml
```

を「Stage 3.1相当」として正当化すること。

Stage 3.1/3.2の設定差分を想像で埋めること。

## テスト

Stage 3.1 experimentが存在する場合、

- 正しいlegacy Stage 3.1 config chainを読む
- Stage 3.2 configを参照しない

ことをテストしてください。

fragment欠損のため未移行とした場合は、

- 誤ってStage 3.2へfallbackしない

ことをテストしてください。

---

# 3. HIGH: preproductionのfull regression gateを修正

## 問題

現在、

```text
src/sawopt/studies/preproduction.py
```

の `run_full_test_suite()` が、

```bash
python -m unittest discover ...
```

相当だけを実行しています。

レビュー時点では、

- pytest collection: 100
- unittest discover: 74

でした。

つまり、**26件のpytest-onlyテストを実行しないままfull regression PASSになる可能性があります。**

## 要件

preproductionにおける

- `full test`
- `complete regression`
- `full regression suite`

等の名称を持つgateは、**CI/開発時に正規とみなす全テストを実行すること**。

このリポジトリではpytestをcanonical test runnerとしてください。

推奨実装:

```bash
python -m pytest -q
```

またはPythonから、

```python
subprocess.run(
    [sys.executable, "-m", "pytest", "-q", ...]
)
```

を実行してください。

## 注意

cwd、`PYTHONPATH`、timeout、stdout/stderr captureなど、既存preproductionの実行契約はできるだけ維持してください。

pytestを追加の必須依存にする場合は、プロジェクトの既存dependency管理に整合させてください。

## 必須テスト

**pytest-onlyテストが失敗するとpreproduction gateもFAILすること**を自動テストで確認してください。

単にmockで「pytestという文字列を呼んだ」ことだけを確認するテストでは不十分です。

少なくとも、

- subprocess commandがpytestを使うこと
- pytestのnon-zero return codeをgate failureとして扱うこと

を確認してください。

可能なら一時的な最小pytest testをfixture/tmpdirに作り、

```python
def test_failure():
    assert False
```

を走らせてgate failureになることを確認してください。

---

# 4. MEDIUM: experiment YAML自身をprovenanceへ含める

## 問題

現在、

```text
src/sawopt/io/config.py
```

の `load_experiment_config()` は、

- base config
- fragment

等を `cfg["inputs"]` に保存しますが、

**最上位の**

```text
experiments/.../experiment.yaml
```

**自身がprovenanceから抜けています。**

config-driven experimentでは最上位experiment YAMLも再現性に必要です。

## 要件

`load_experiment_config()` が、experiment YAML自身も入力provenanceとして保持するよう修正してください。

最低限保持するもの:

- experiment YAMLのpath
- experiment YAMLのraw content

可能であれば:

- relative path
- SHA-256

も既存provenance形式に合わせて保持してください。

## パス

basenameのみでは、

```text
experiment.yaml
```

が複数存在して衝突するため不十分です。

可能ならproject root基準のrelative pathを使ってください。

例:

```text
experiments/stage3_3_optimizer_ab/experiment.yaml
```

## review bundle / manifest

既存のreview bundleまたはmanifestが `cfg["inputs"]` を使用しているなら、

**experiment YAML自身もbundleに含まれること**

まで確認してください。

## 必須テスト

例えばStage 3.3 experimentをロードし、

```python
cfg = load_experiment_config(...)
```

したとき、

```text
experiments/stage3_3_optimizer_ab/experiment.yaml
```

がprovenance inputsに存在することを確認してください。

fragment/base configも従来通り残ることを確認してください。

---

# 5. MEDIUM: architecture testの相対import解決を修正

## 問題

現在、

```text
tests/unit/test_architecture.py
```

のimport解析では、

```python
from .convergence import _private
```

のような相対importを正しく

```text
sawopt.studies.convergence
```

へ解決できません。

そのため、

```python
from .other_study import _private_helper
```

のような **studies間private import** が将来追加されても見逃す可能性があります。

## 要件

ASTの `ImportFrom` に対して、

- `node.level`
- `node.module`
- current module/package

を用いて、正しいabsolute module nameへ解決してください。

推奨:

```python
import importlib.util

absolute = importlib.util.resolve_name(
    "." * node.level + (node.module or ""),
    current_package,
)
```

package/moduleの扱いは正しくしてください。

## architecture rule

少なくとも以下を検出してください。

```python
# NG
from .convergence import _private
from sawopt.studies.convergence import _private
from ..studies.convergence import _private
```

studies module間で `_` 始まりのsymbolをimportすることは禁止です。

互換shim等、計画上明示的に許可された例外がある場合のみ限定的allowlistにしてください。

## 必須テスト

fixture文字列またはtemporary moduleを使って、

```python
from .other import _private_helper
```

がarchitecture violationになることを必ずテストしてください。

absolute import版も維持してください。

---

# 6. Git / provenanceの整理

レビュー時点ではリファクタリング全体が未コミットでした。

今回の修正が終わったら、

```bash
git status
git diff --stat
git diff
```

を確認してください。

不要な

- temporary file
- pytest cache
- generated output
- review artifact
- local run output

をコミット対象へ入れないこと。

## 推奨コミット分割

既にリファクタリング全体が未コミットの場合、可能なら以下のように分けてください。

### Commit 1

```text
refactor: separate optimizer, study, problem, and runtime layers
```

主に構造変更。

### Commit 2

```text
refactor: migrate experiment configuration and compatibility shims
```

experiment/config/compatibility関連。

### Commit 3

```text
fix: close post-refactor regression and provenance gaps
```

今回の指摘修正。

ただし現在のworking treeから安全に分割できない場合は、**無理なhistory surgeryをしないこと。**

1コミットでも構いません。

重要なのは、次のproduction実験を走らせる前に、

- clean working tree
- 再現可能なcommit hash

を作ることです。

---

# 7. 最終検証

修正完了後、以下を実施してください。

## 7.1 compile

```bash
python -m compileall src
```

PASS必須。

## 7.2 全pytest

```bash
PYTHONPATH=src python -m pytest -q
```

**収集された全テストPASS必須。**

テスト数が100から増えるのは正常です。

減った場合は理由を確認してください。

## 7.3 CLI

canonical CLIとcompatibility CLIの両方について最低限、

```bash
python -m sawopt --help
```

および既存legacy entrypointの `--help` を実行してください。

## 7.4 Stage 3.2 characterization

Stage 3.2のretry characterization testsを明示的に実行してください。

以下が維持されること。

- first DE attempt
- max 3 diversification retries
- total max 4 attempts
- `segment_index` progression
- retry seed semantics
- previous population 1/4 retention
- successful retry exits immediately
- exhausted retries => `no_new_unique_designs`
- unique-design budget accounting unchanged

## 7.5 checkpoint

checkpoint/resume regression testsを実行してください。

resume後の結果/カウンタ/状態が従来通りであること。

## 7.6 frequency exchange

adaptive frequency exchange regression testsを実行してください。

## 7.7 experiment config merge

Stage 3.2 production/16000 configについて、

```text
stage3_2_convergence_fragment
    ↓
stage3_2_production_process5_fragment
    ↓
stage3_2_center16000_fragment
```

のmerge結果が維持され、

- production_workers = 5
- optional_max_budget = 16000

となること。

---

# 8. 完了条件

以下をすべて満たしたら完了です。

- [ ] Stage 3.1がStage 3.2 configを偽装参照していない
- [ ] Stage 3.1 fragmentを推測で再構築していない
- [ ] preproduction full regressionが全pytestを対象にする
- [ ] pytest-only failureでpreproduction gateがFAILする
- [ ] experiment YAML自身がprovenance inputsに含まれる
- [ ] review bundle/manifestにexperiment YAMLが残る
- [ ] relative private importをarchitecture testが検出する
- [ ] 全pytest PASS
- [ ] compileall PASS
- [ ] canonical CLI PASS
- [ ] compatibility CLI PASS
- [ ] Stage 3.2 retry characterization PASS
- [ ] checkpoint regression PASS
- [ ] frequency exchange regression PASS
- [ ] config merge regression PASS
- [ ] COM/optimization algorithmの変更なし
- [ ] 次の実験前にcommit hashが確定している

---

# 9. 作業終了時の報告フォーマット

作業終了時、以下を報告してください。

## Changes

変更したファイル一覧と、それぞれ何を修正したか。

## Stage 3.1 decision

以下のどちらだったか明記。

```text
A. Git historyから正しいfragmentを復元した
```

または

```text
B. fragmentを復元できず、Stage 3.1 experimentを未移行扱いにした
```

Aの場合は復元元commit/pathも記載。

## Tests

以下を報告。

```text
pytest collected:
pytest passed:
pytest failed:
compileall:
canonical CLI:
compatibility CLI:
```

加えて、

```text
Stage 3.2 retry:
checkpoint/resume:
frequency exchange:
experiment provenance:
architecture relative-import detection:
preproduction pytest gate:
```

の結果。

## Algorithm changes

必ず、

```text
Algorithmic behavior changed: NO
```

であること。

もしYESなら作業を完了扱いにせず、何が変わったかを報告して停止してください。

## Git

```text
commit:
git status:
```

cleanであることが望ましい。

---

# 10. 最後の注意

今回の修正目的は、

**「リファクタリングをさらに進めること」ではありません。**

目的は、

**現在の新アーキテクチャを安全にproduction実験へ使える状態まで仕上げること**

です。

4件のレビュー指摘以外に新しい大規模変更を見つけても、今回の作業には混ぜず、別issue/TODOとして報告してください。
