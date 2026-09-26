# Historical Cleanup Final Closeout 作業指示書

> **歴史的な引き継ぎ・作業指示の記録です。現行手順ではありません。** 本文中のブランチ名、コミット SHA、パス、件数、コマンド、停止条件は作成当時の状態を示します。実行前に現行状態と当該タスクの承認を確認してください。現在の開発方針は[ロードマップ](../project_roadmap.md)、[現行ベースライン](../history/current_baseline.md)、[アーキテクチャ概要](../architecture_overview.md)、C2C の運用・セキュリティ方針は[C2C documentation](../c2c/README.md)を参照してください。

## 1. 目的

対象ブランチ:

`codex-historical-cleanup`

レビュー時点のHEAD:

`1282699b9c56a099b6fdb42b38ecba9009d91954`

今回までに、historical study runner / config / test / handoff / report の大規模削除は完了している。

現在のrepositoryは概ね以下まで縮小されている。

- tracked files: 約152
- Python source: 約65
- Python tests: 約40
- current study modules:
  - `src/sawopt/studies/dms_topology_common.py`
  - `src/sawopt/studies/dms_topology_screening.py`
  - `src/sawopt/studies/hybrid.py`
  - `src/sawopt/studies/lshade_records.py`
- current study configs:
  - `configs/studies/dms_topology_screening.yaml`
  - `configs/studies/hybrid_50ohm.yaml`

historical deletion自体の方向性は妥当であり、今回の作業は **cleanupをmainへ統合可能な状態までcloseすること** を目的とする。

今回の主対象は次の3点。

1. `docs/architecture_overview.md` を削除後の実構成に同期する
2. 残存compatibility shimをcurrent dependency auditし、不要なものだけ削除する
3. 削除後HEADでfull regressionを実施し、最終closeout記録を残す

---

# 2. 最重要方針

今回の作業は **final closeout** であり、新しいarchitecture refactorやoptimizer改善フェーズではない。

したがって、

- living implementationを壊さない
- current DMS topology workflowを変更しない
- Hybrid workflowを変更しない
- historical knowledgeを変更しない
- 数値semanticsを変更しない

ことを優先する。

特に current DMS topology screening が保持している以下のsemanticsは変更禁止。

- T0 / T1 / T2 topology
- geometry-first comparator
- independent uniform proposal
- geometry rejection / resampling
- geometry repairなし
- canonical population
- initializer diagnostics
- M0 / MLIT
- 2 seeds
- 8k unique evaluations
- 2k / 4k / 6k / 8k checkpoints
- 9,113-point common validation grid
- common-grid finalist validation
- checkpoint accounting

---

# 3. Safety / Recovery

削除直前snapshotとしてremote annotated tag:

`archive/pre-historical-deletion-2026-09-25`

が存在し、commit:

`3f88bf0be2a0ac651e35f9de678df1ca5023f387`

を指している。

このtagは変更しない。

また、cleanup開始前snapshot:

`archive/pre-historical-cleanup-2026-09-25`

も変更しない。

Git history rewrite、force push、tag付け替えは禁止する。

---

# 4. 禁止事項

以下は今回行わない。

- COM equation変更
- network calculation変更
- objective変更
- comparator semantics変更
- L-SHADE algorithm変更
- RNG順序変更
- geometry constraint変更
- search bounds変更
- material parameter変更
- impedance設定変更
- checkpoint semantics変更
- current DMS topology production run
- Stage 3.8C production rerun
- historical run再実行
- `runs/` のcanonical output変更
- review bundleのhistorical artifact変更
- experiment registerの科学的結論変更
- current baselineの科学的結論変更
- 新規Stage runner追加
- 新規大規模refactor
- historical fileの追加大量削除

compatibility shim削除は、current referenceが存在しないことを確認できたものだけに限定する。

---

# 5. Task A — `docs/architecture_overview.md` を現在構成へ更新

現在の `docs/architecture_overview.md` にはhistorical deletion前の過渡状態が残っている。

例えば以下のような記述は現在のrepository状態と一致しない。

- Stage 3.6がrelease schema / decoderを保持している
- old `studies/convergence_evidence.py` がtemporary re-export中
- Stage 3.8C runnerがcanonical moduleをimportしている
- `optimizer_ab.py` がL-SHADE record serializerをtemporary re-exportしている

これらのmoduleは既に削除済みである。

## 修正方針

文書を現在のliving architectureだけに合わせる。

最低限以下を明確にする。

### `core/`

- COM
- electrical/acoustic network
- metrics
- physical material calculation

### `problem/`

- reusable design-space representation
- DMS topology
- released DMS representation

canonical examples:

- `problem/dms_topologies.py`
- `problem/released_dms.py`

### `optimizers/`

- optimizer backend
- L-SHADE
- SciPy DE backend
- candidate selection/comparator
- optimizer-generic polish

### `optimization/`

- SAW/search orchestration primitives
- accounting
- adaptive frequency
- budget
- cache
- convergence evidence
- counters
- history
- population
- runner
- SAW-specific polish where applicable

### `studies/`

現在のactive study adaptersのみ。

- `dms_topology_common.py`
- `dms_topology_screening.py`
- `hybrid.py`
- `lshade_records.py`

### `io/`, `reporting/`, `orchestration/`

- persistence
- checkpoint lifecycle
- provenance
- generic review bundle
- detached execution

## 重要

歴史的Stage番号はscientific historyとして

- `docs/history/current_baseline.md`
- `docs/history/experiment_register.md`

に残す。

architecture overviewでは、削除済みmoduleをcurrent architectureとして説明しない。

---

# 6. Task B — compatibility shim audit

現在 `optimization/` 配下には、historical compatibility由来と思われるmoduleが一部残っている。

最低限以下を確認する。

- `src/sawopt/optimization/lshade.py`
- `src/sawopt/optimization/selection.py`
- `src/sawopt/optimization/backends.py`
- `src/sawopt/optimization/__init__.py`

各moduleについてrepository全体のimport/referenceを検索する。

対象:

- `src/`
- `tests/`
- `scripts/`
- current docsの実行例

## 6.1 分類

各moduleを以下に分類する。

### A. Pure compatibility shim

実装を持たず、`optimizers/` からre-exportしているだけ。

かつcurrent source/testから参照されていない。

→ 削除候補。

### B. Current compatibility dependencyあり

current source/testが旧pathを使用している。

→ callerをcanonical `sawopt.optimizers...` へ変更できるか確認する。

変更が単純なimport-path修正のみであればcanonical pathへ移し、その後shimを削除する。

### C. Living implementation

単なるshimではなく、SAW-specific implementationを持つ。

→ 残す。

例:

`src/sawopt/optimization/polish.py`

は `mixed_variable_polish` を持つため、単純shimとして削除してはいけない。

## 6.2 `optimization/__init__.py`

現在の `optimization/__init__.py` がoptimizer compatibility exportだけを目的としている場合は、

- current import利用を確認
- 不要ならexportsを縮小または削除

する。

ただしpackage `optimization` 自体はliving packageなので、

`__init__.py` ファイルそのものを削除してpackage import semanticsを変更する必要はない。

必要ならempty/minimal package docstringのみ残してよい。

## 6.3 削除基準

以下を満たす場合のみshimを削除する。

- current implementationからimportされていない
- current testsから必要とされていない
- public workflow documented pathとして使われていない
- 削除後full testがPASSする

「過去コードから参照されていた」は維持理由にしない。

過去import pathの再実行互換性は今回のcleanup要件ではない。

---

# 7. Task C — Current workflow reference audit

historical module削除後にbroken referenceが残っていないことを確認する。

最低限以下の文字列 / import familyを検索する。

- `stage3_6_`
- `stage3_7`
- `stage3_8_`
- `stage3_8c`
- `optimizer_ab`
- `matched_protocol_parity`
- `phase_c_supplement`
- `phase_c_final_confirmation`
- `search_efficiency`
- `preproduction`
- `studies.convergence`
- `studies.continuation`
- `studies.convergence_evidence`
- `reporting.stage3_8_review_bundle`
- `reporting.search_space_diagnostics`
- deleted config filenames

## 分類

### Historical prose

`experiment_register.md` や `current_baseline.md` にStage名が出るのは正常。

### Frozen provenance reference

annotated tagやhistorical run pathへの説明上の参照は正常。

### Live code/config dependency

削除済みmodule/fileへのlive dependencyは修正必須。

### Stale current documentation

current architecture / execution guideから削除済みmoduleへの説明は修正する。

---

# 8. Task D — Hybrid workflow documentation

`README.md` はcurrent workflowとして

- DMS topology screening
- 50 Ω hybrid

を挙げている。

一方 `python -m sawopt run-study` は現在

`dms_topology_screening`

のみをdispatchする。

Hybridは独立CLI:

`python -m sawopt.studies.hybrid`

として実行可能である。

READMEにHybridの具体的な実行例を追加する。

例:

```powershell
python -m sawopt.studies.hybrid --config configs/studies/hybrid_50ohm.yaml --run runs/hybrid-study
```

必要なら既存launcher:

`scripts/launchers/hybrid-50ohm.ps1`

の案内も追加してよい。

## 注意

`run-study` dispatcherへHybridを無理に統合しない。

今回はdocumentation clarificationのみとする。

---

# 9. Task E — Characterization / focused regression

大規模な新規テストは追加しない。

既存testsでcurrent implementationが十分に保護されている。

最低限以下をfocused testとして実行する。

- architecture boundary
- current DMS topology screening
- DMS topology regression
- L-SHADE resume
- L-SHADE record serialization
- convergence evidence
- checkpoint lifecycle
- review bundle
- hybrid workflow

例:

```powershell
.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  tests/unit/test_architecture.py `
  tests/unit/studies/test_dms_topology_screening.py `
  tests/unit/problem/test_dms_topologies.py `
  tests/unit/optimizers/test_lshade.py `
  tests/unit/optimization/test_lshade_record_serialization.py `
  tests/unit/optimization/test_convergence_evidence.py `
  tests/unit/io/test_checkpoints.py `
  tests/unit/reporting/test_review_bundle.py `
  tests/integration/test_hybrid_study.py `
  tests/integration/test_study.py `
  -q
```

shell環境に合わせて1行でもよい。

---

# 10. Task F — Full regression

最重要ゲート。

削除後HEADでfull suiteを実行する。

推奨:

```powershell
.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
```

削除前baseline:

`297 passed, 14 subtests passed`

これは `archive/pre-historical-deletion-2026-09-25` 直前のbaselineである。

削除後はtest自体を整理しているため、pass数が減ること自体は問題ではない。

必須条件は:

- failure = 0
- error = 0
- unexpected skip/xfailed増加なし
- architecture test PASS
- current DMS tests PASS
- hybrid integration PASS
- optimizer resume test PASS
- checkpoint tests PASS

とする。

---

# 11. Task G — Optional smoke check

full pytestが十分であればproduction runは不要。

ただし非常に軽量なCLI/config smokeが既存testでカバーされていない場合のみ、以下を確認してよい。

- `configs/studies/dms_topology_screening.yaml` がload可能
- MLIT profileがload可能
- common validation grid hashが一致
- current initial designsがload可能
- `python -m sawopt --help` 相当のCLI importが壊れていない

数値optimizer本体を長時間走らせない。

---

# 12. Task H — Final closeout report

新規:

`reports/historical_cleanup_final_closeout_20260925.md`

を作成する。

内容は短くてよい。

最低限以下を記載する。

## Repository state

- branch
- starting HEAD
- ending commitは自己参照固定SHAにしない
- pre-deletion tag
- pre-deletion tag target

ending commitについては例えば:

`The closeout changes were committed on codex-historical-cleanup; Git history is the canonical source for the resulting commit SHA.`

とし、自分自身のSHAをreport本文へ固定しない。

## Inventory

closeout後の:

- tracked files
- Python source files
- Python tests
- configs
- study modules

を記録する。

## Removed historical implementation

高レベルに、

- Stage-numbered runners removed
- historical configs removed
- historical tests removed
- historical handoffs/reports pruned
- knowledge retained in history docs
- exact source retained by annotated Git tag

と記録する。

## Current workflows

- DMS topology screening
- 50 Ω hybrid
- prototype simulate / optimize / sweep / report

## Compatibility cleanup

削除したshimと残したmoduleを記録する。

例:

- removed: pure compatibility re-exports with zero living references
- kept: `optimization/polish.py` because it contains living SAW-specific logic

実際の結果に合わせる。

## Verification

focused tests:

`N passed`

full suite:

`N passed, ...`

GitHub Actions:

branch pushでworkflowが走らない場合はその旨を記載し、workflow変更は不要。

## Numerical impact

以下を明記する。

`NO PRODUCTION OPTIMIZATION RERUN`

`NO COM/NETWORK/OBJECTIVE/OPTIMIZER NUMERICAL SEMANTICS CHANGE`

`NO CANONICAL SAVED RUN MODIFICATION`

## Final status

すべてPASSなら:

`HISTORICAL_CLEANUP_COMPLETE`

と記録する。

blockerが残る場合:

`HISTORICAL_CLEANUP_NOT_COMPLETE`

として理由を記録する。

---

# 13. 完了条件

以下をすべて満たすこと。

- [ ] `docs/architecture_overview.md` が削除後architectureと一致
- [ ] 削除済みStage runnerをcurrent architectureとして説明していない
- [ ] `optimizer_ab.py` をcurrent moduleとして説明していない
- [ ] old `studies/convergence_evidence.py` をcurrent compatibility pathとして説明していない
- [ ] compatibility shim audit完了
- [ ] pure compatibility shimはliving referenceがなければ削除
- [ ] living implementationは誤削除していない
- [ ] deleted moduleへのlive import 0
- [ ] Hybrid実行方法がREADMEで明確
- [ ] focused regression PASS
- [ ] full pytest PASS
- [ ] production optimizerを再実行していない
- [ ] canonical run dataを変更していない
- [ ] final closeout report作成済み
- [ ] final status = `HISTORICAL_CLEANUP_COMPLETE`

---

# 14. Commit方針

今回の変更は1～2コミットにまとめる。

推奨例:

1. `Remove remaining cleanup compatibility shims`
2. `Close historical cleanup`

または変更量が小さければ1コミット:

`Complete historical cleanup closeout`

でよい。

---

# 15. 作業完了後

`codex-historical-cleanup` へpushする。

最後に以下を報告する。

- ending branch state
- changed files
- removed compatibility shims
- retained compatibility/living modulesと理由
- focused test result
- full pytest result
- final tracked file count
- Python source/test count
- final closeout status

**この作業ではmainへmergeしない。**

push後に一度レビューを挟み、問題なければmainへの統合判断を行う。
