# Stage 3.8.5 Architecture Cleanup
## Review/Provenance分離・Fingerprint v2・DMS Topology共通化

## 1. 目的

Stage 3.8C Productionは正式にclose済みであり、次工程ではStage 3.9として、

- MLITを中心としたDMS候補継続
- DMS + ladder hybrid topology
- 将来のimpedance sweep

へ進む予定である。

その前に、今後の実験追加によるsource肥大化・重複実装を防ぐため、**小規模なarchitecture cleanup**を実施する。

今回の目的は数値性能改善ではない。

目的は以下の4点である。

1. Review Bundle生成をStage固有scriptから分離する
2. 計算コードとreportingコードのfingerprintを分離する
3. Stage 3.8で共通化可能になったsearch/accounting primitivesを整理する
4. DMS topology implementationをStage番号付きmoduleから独立させる

---

# 2. 最重要原則

今回の作業は、

```text
STRUCTURAL REFACTOR ONLY
```

とする。

以下を変更してはならない。

- COM physics
- network equations
- material COM parameters
- topology semantics
- geometry constraints
- manufacturing constraints
- objective
- filter specification
- violation calculation
- comparator ordering
- canonicalization semantics
- integer rounding semantics
- initializer distribution
- L-SHADE behavior
- RNG draw order
- seeds
- budgets
- checkpoint semantics
- common validation grid
- Stage 3.8 Production results

Stage 3.8の96k結果は**完全にhistorical/canonical dataとしてfreeze**する。

---

# 3. Stage 3.8再実行禁止

今回のrefactor確認目的で、

- 96k Production
- 8k run
- Stage 3.8 Pilot
- Final Confirmation
- Monte Carlo大量sampling

を再実行してはならない。

必要なのは、

- unit tests
- integration tests
- deterministic small smoke

のみ。

---

# 4. 作業開始時Inventory

コード変更前に現repository構造を調査する。

最低限以下を確認する。

```text
src/sawopt/core/
src/sawopt/problem/
src/sawopt/optimizers/
src/sawopt/optimization/
src/sawopt/studies/
src/sawopt/reporting/
src/sawopt/io/
```

またrepository全体で以下を検索する。

```text
review_bundle
bundle_manifest
REVIEW_ME
sha256
source_fingerprint
config_fingerprint
computation_fingerprint
EvaluationCounters
GeometryFirstComparator
checkpoint accounting
sample_independent_uniform_population
stage3_8
T0
T1
T2
```

---

# 5. 重複実装を作らない

既存の、

```text
src/sawopt/reporting/review_bundle.py
```

および既存の、

```text
optimization/counters.py
optimization/population.py
optimizers/selection.py
io/provenance.py
```

等が存在する場合、まず内容を確認する。

今回必要な機能と既存機能が重なる場合は、

**既存canonical implementationを拡張すること。**

同等機能の2個目を作ってはならない。

---

# 6. Baseline記録

変更前に以下を保存する。

```text
git rev-parse HEAD
git branch --show-current
git status --short
git diff --stat
```

またfull test suiteを実行し、baselineを記録する。

現在の期待baselineは概ね、

```text
242 passed + 14 subtests
```

であるが、実repositoryの結果をsource of truthとする。

pre-existing failureがあれば記録し、今回のrefactor failureと区別する。

---

# 7. Phase A — Review Bundle分離

## 7.1 問題

現在のStage 3.8系scriptには、

- optimization execution
- validation
- CSV/JSON generation
- Markdown summary
- plot generation
- Git metadata取得
- source snapshot
- SHA-256
- bundle manifest
- ZIP生成

が混在している。

Stage 3.9以降でこの構造をコピーしてはならない。

---

# 8. Generic Review Bundle Builder

Review Bundleのgeneric infrastructureを、

```text
src/sawopt/reporting/
```

配下へ集約する。

既存の

```text
src/sawopt/reporting/review_bundle.py
```

がある場合はそれをcanonical implementationとする。

最低限generic layerが担当するもの：

```text
required artifact validation
file collection
source snapshot
Git HEAD / status / diff
environment metadata
SHA-256 manifest
ZIP creation
post-ZIP hash validation
optional large artifact handling
```

---

# 9. Stage固有reportとの責務分離

Stage-specific layerは、

```text
何を出力するか
何をsummaryへ記載するか
どのartifactがrequiredか
```

だけを定義する。

Generic bundle builderは、

```text
どう集めるか
どうhashするか
どうZIP化するか
```

を担当する。

概念的には、

```python
spec = ReviewBundleSpec(
    study_type="dual_material_dms_topology_screen",
    required_artifacts=[...],
    optional_artifacts=[...],
)

build_review_bundle(
    run_dir=run_dir,
    output_zip=output_zip,
    spec=spec,
)
```

程度の責務分離を目指す。

大規模frameworkは不要。

---

# 10. Review Bundle Generatorの独立実行

Stage scriptを再実行しなくても、

```text
既存run directory
        ↓
review bundle生成
```

できるようにする。

例えば、

```bash
python -m sawopt.reporting.review_bundle \
    --run <existing-run-dir> \
    --output <review.zip>
```

または既存CLI方式に合わせる。

重要：

**bundle生成のためにoptimizerをimport/runする必要がない構造**にする。

---

# 11. REVIEW_ME generation

Generic bundle builder自体にStage固有文章を大量に持たせない。

例えば、

```text
reporting/topology_screening.py
```

に、

- topology summary table
- seed summary
- limitation text
- gate summary

を置いてもよい。

ただし、

```text
ZIP / manifest / hashing
```

とは分離する。

---

# 12. Phase B — Fingerprint v2

## 12.1 問題

Stage 3.8ではreporting変更だけでもStage script全体のhashが変化し、

Production前に追加Pilotが必要になった。

今後これを避ける。

---

# 13. Fingerprintを2系統に分離

新schemaでは最低限、

```text
computation_fingerprint
reporting_fingerprint
```

を持つ。

---

# 14. computation_fingerprint

数値結果に影響するものだけを対象にする。

例えば：

```text
core/
problem/
optimizers/
relevant optimization modules
topology implementation
initializer implementation
comparator/selection
input config
material profiles
search-space config
specification config
```

ただしrepository全体をhashするのではなく、

**明示されたdependency setをhashする。**

---

# 15. reporting_fingerprint

以下を対象にする。

```text
reporting modules
plot generation
review bundle code
REVIEW_ME templates
bundle schema
```

reporting変更によって、

```text
computation_fingerprint
```

が変化してはならない。

---

# 16. Fingerprint schema version

新metadataでは、

```json
{
  "fingerprint_schema_version": 2,
  "computation_fingerprint": "...",
  "reporting_fingerprint": "..."
}
```

等を保存する。

Stage 3.8以前のlegacy fingerprintは書き換えない。

Historical artifactsはschema v1のまま保存する。

---

# 17. Production gateの意味論

今後のProduction gateは基本的に、

```text
computation_fingerprint
```

一致を要求する。

reporting fingerprint mismatchだけで、

```text
optimizer rerun required
```

にしてはならない。

ただしreporting artifact再生成は必要に応じて行ってよい。

---

# 18. Fingerprint tests

最低限以下をtestする。

### A. numerical source変更

COM / optimizer / topology source変更：

```text
computation_fingerprint changes
```

### B. config変更

search bounds等変更：

```text
computation_fingerprint changes
```

### C. reporting-only変更

review bundle template変更：

```text
computation_fingerprint unchanged
reporting_fingerprint changes
```

### D. historical schema

legacy run metadataを読み出せること。

---

# 19. Phase C — Shared Search Primitives整理

Stage 3.8 script内にある共通ロジックを調査する。

候補：

```text
GeometryFirstComparator
EvaluationCounters
population sampling
counter invariant validation
checkpoint lattice validation
common result validation
```

ただし、**すべてを必ず移す必要はない。**

今後Stage 3.9で再利用されることが明確なものだけ抽出する。

---

# 20. Comparator

geometry-first / feasibility-first comparatorのcanonical ownerを1つにする。

推奨：

```text
src/sawopt/optimizers/selection.py
```

既存implementationがある場合はそこへ統合する。

Stage-specific comparator copyを残さない。

重要：

rank tuple、tie-break、NaN handling等は一切変更しない。

---

# 21. Counter

Evaluation counter/invariantは、

```text
src/sawopt/optimization/counters.py
```

等へ集約する。

最低限、

- raw evaluation
- unique evaluation
- geometry rejected
- physics attempted
- physics successful
- physics failed

の既存意味論を保持する。

Stage 3.8 counter schemaを変更しない。

---

# 22. Checkpoint Accounting

今回実際に、

```text
12 seed runs
vs
48 checkpoint rows
```

を混同するbugが発生した。

これを再発させないため、共通validatorを用意する。

概念例：

```python
validate_checkpoint_lattice(
    rows,
    expected_runs,
    expected_checkpoints,
)
```

最低限確認するもの：

```text
missing run
missing checkpoint
duplicate checkpoint
unexpected checkpoint
counter invariant
final checkpoint presence
```

---

# 23. Population Sampler

R1.2で確定した、

```text
independent uniform proposal
→ canonicalize
→ geometry rejection
```

のgeneric部分が再利用可能であれば、

```text
optimization/population.py
```

へ移す。

ただしtopology-specific geometry判断はproblem層に残す。

RNG draw orderは絶対に変更しない。

既存seed replay testで完全に確認する。

---

# 24. Phase D — DMS TopologyのStage依存解消

## 24.1 問題

T0/T1/T2のDMS physical/topology implementationが、

```text
stage3_8_...
```

というhistorical experiment moduleに置かれている場合、

Stage 3.9 hybrid implementationからStage 3.8をimportする構造になる。

これは避ける。

---

# 25. Canonical DMS Topology module

推奨移動先：

```text
src/sawopt/problem/dms_topologies.py
```

または、

```text
src/sawopt/problem/topologies/dms.py
```

既存package architectureに自然な方を選ぶ。

---

# 26. 移動候補

Stage 3.8 moduleから、再利用可能なら以下を移す。

```text
DMS design structures
T0 definition
T1 definition
T2 definition
decode logic
section construction
topology simulation wiring
fixed-design/reference constructors
geometry-related topology metadata
```

---

# 27. 移動してはいけないもの

以下はtopology moduleへ入れない。

```text
Stage 3.8 budget
Stage 3.8 seeds
Pilot gate
Production gate
REVIEW_ME
CSV writer
plotting
review bundle
Stage 3.8 historical decisions
```

---

# 28. Compatibility wrapper

既存のStage 3.8 import pathは削除しない。

例えば旧moduleから、

```python
from sawopt.problem.dms_topologies import (
    ...
)
```

としてre-exportする。

過去test / script / historical commandとの互換性を維持する。

---

# 29. Stage chronologyを新sourceへ持ち込まない

今後新しいcanonical source名として、

```text
stage3_9_...
stage4_...
```

を増やさないことを基本ルールとする。

Reusable behaviorは、

```text
topology_screening
hybrid
impedance_sweep
continuation
```

のように**役割で命名**する。

Stage番号は、

```text
experiment config
run directory
artifact metadata
documentation
```

に残す。

---

# 30. 今回はStudy Frameworkを全面再設計しない

以前の長期refactor planには、

```text
core
problem
optimizers
optimization
studies
reporting
io
runtime
experiments
```

という最終architectureがある。

今回すべてを完成させる必要はない。

特に、

- experiments/全面移行
- 全Stage module rename
- config schema全面変更
- CLI全面変更
- plugin architecture
- dependency injection framework

は行わない。

---

# 31. Stage 3.8 giant scriptの扱い

`stage3_8c_r1_geometry_gate.py` 等のhistorical scriptを完全分解しなくてよい。

目標は、

```text
今後コピーしたくない共通機能を外へ出す
```

ことである。

Stage 3.8 historical runner自体はcompatibility/historical implementationとして残してよい。

無理にLOCを小さくすることを目的にしない。

---

# 32. Dependency方向

今回のrefactor後は最低限、

```text
studies
   ↓
optimization
   ↓
problem
   ↓
core
```

および、

```text
studies → reporting
studies → io
```

を基本方向とする。

逆方向、

```text
core → studies
optimization → studies
reporting → studiesのprivate function
```

は避ける。

---

# 33. Reporting dependency rule

reporting codeは可能な限り、

```text
result artifact
metadata
run directory
```

だけを読む。

Stage runnerのprivate functionsをimportしてreport生成してはならない。

---

# 34. Stage 3.9へのAcceptance Criteria

今回のcleanup完了後、Stage 3.9 implementationは以下を満たせる状態にする。

### Review

Stage 3.9専用のZIP/hashing codeを書かなくてよい。

### DMS

Stage 3.9がStage 3.8 historical moduleをimportしなくてよい。

### Search

counter / comparator / population primitiveを再コピーしなくてよい。

### Fingerprint

report修正だけではProduction computation gateが閉じない。

---

# 35. Tests — Existing Behavior Preservation

最低限以下を維持する。

- fixed-seed reproducibility
- geometry-first comparator
- initializer distribution
- integer canonicalization
- counter invariants
- checkpoint accounting
- fixed-design sanity
- common validation
- source/config fingerprint logic
- GPT-6 Sol routing
- existing Stage 3.8 regression

---

# 36. Review Bundle tests

追加または更新する。

### Generic builder

- missing required file → FAIL
- manifest generation
- all hashes valid
- source snapshot inclusion
- config inclusion
- optional artifact inclusion
- existing run directoryからbundle生成可能

### Decoupling

Stage 3.8 runnerを実行しなくても、既存fixture runからbundleを生成できること。

---

# 37. Fingerprint v2 tests

必須：

```text
report-only edit
→ computation fingerprint unchanged
```

をautomated regression testにする。

今回のrefactorで最重要なacceptance testの一つである。

---

# 38. DMS Topology parity test

旧Stage 3.8 implementationと新canonical moduleについて、

同一design・frequency grid・material profileで、

```text
S-parameter / metrics / geometry result
```

が同一になることをtestする。

可能ならstrictまたは既存numerical toleranceで比較する。

---

# 39. Deterministic Small Smoke

full tests PASS後、小さなsmokeだけを実行する。

例えば、

```text
1 material
1 topology
small evaluation budget
fixed seed
```

程度。

目的：

```text
import path
optimizer invocation
report generation
review bundle generation
fingerprint v2
```

のend-to-end確認。

性能判断には使用しない。

---

# 40. Stage 3.8 Production結果との数値比較

96kを再実行する必要はない。

ただし既存Stage 3.8 saved winnerの1つ程度を読み込み、

新canonical DMS implementationで再評価して、

保存済みvalidated metricと一致することを確認してよい。

これはoptimizer rerunではなく、

```text
single-design deterministic validation
```

である。

---

# 41. No behavior bug fixes during refactor

作業中に数値behaviorのbugを見つけても、原則今回その場で修正しない。

手順：

1. 現behaviorをrefactorで保存
2. issue/notesへ記録
3. refactorを完了
4. 必要なら別作業で修正

例外は、refactor自体を成立させるための明らかなreporting/infrastructure bugのみ。

---

# 42. GPT-6 Sol routing

現在の、

```text
gpt6sol
```

routingを維持する。

今回のrefactorで旧、

```text
gpt5.6sol
```

へ戻してはならない。

新しいSol review実行は必須ではない。

既存routing regression testを通すだけでよい。

---

# 43. Repository保護

禁止：

```text
git reset --hard
git clean -fd
unrelated user changes削除
無断stash
無断commit
無断push
```

pre-existing dirty stateがあれば保持する。

今回の変更だけをscoped diffとして記録する。

---

# 44. 推奨実行順

```text
Phase 0
Repository inventory / baseline
        ↓
Phase A
Review bundle / provenance separation
        ↓
Phase B
Fingerprint v2
        ↓
Phase C
Comparator / counters / accounting / population整理
        ↓
Phase D
DMS topology canonicalization
        ↓
Compatibility wrappers
        ↓
Targeted tests
        ↓
Full regression
        ↓
Small deterministic smoke
        ↓
Refactor review bundle
        ↓
STOP
```

---

# 45. 各PhaseごとのStop Gate

各Phase完了時にtargeted testsを実行する。

failureが出た場合、

次Phaseへ進まず原因を修正する。

数値behavior変更でtestを通すことは禁止。

---

# 46. Full Regression Gate

最終的に、

```bash
python -m pytest -q
```

等のrepository standard full suiteを実行する。

BaselineでPASSしていたtestはすべてPASSすること。

test数が増えるのは問題ない。

---

# 47. Source Fingerprint Compatibility

Stage 3.8 historical runのlegacy fingerprintを、

schema v2へ変換・上書きしてはならない。

新しいfingerprint v2は、

```text
Stage 3.9以降
```

をcanonical targetとする。

Stage 3.8 bundleはhistorical v1としてそのまま読めるようにする。

---

# 48. Documentation

最低限以下を更新する。

```text
architecture overview
review bundle usage
fingerprint semantics
new experiment implementation guidance
```

特に次のルールを明記する。

> New experiments should reuse study/reporting/search infrastructure instead of adding Stage-specific copies.

および、

> Reporting-only changes do not invalidate computation fingerprints.

---

# 49. 推奨最終構成

厳密に同じである必要はないが、概念的に以下を目標とする。

```text
src/sawopt/
├─ core/
│
├─ problem/
│   ├─ dms_topologies.py
│   └─ ...
│
├─ optimizers/
│   ├─ lshade.py
│   ├─ selection.py
│   └─ ...
│
├─ optimization/
│   ├─ population.py
│   ├─ counters.py
│   ├─ accounting.py
│   └─ ...
│
├─ studies/
│   └─ ...
│
├─ reporting/
│   ├─ review_bundle.py
│   ├─ topology_screening.py
│   └─ ...
│
└─ io/
    ├─ provenance.py
    └─ ...
```

---

# 50. 今回やらないもの

明示的にscope外：

- Stage 3.9実装
- ladder追加
- hybrid simulation
- impedance sweep
- optimizer tuning
- new optimizer導入
- COM calibration
- material model変更
- Stage 3.8追加探索
- T1/T2延長
- repository history rewrite
- config体系全面刷新

---

# 51. Review Bundle

今回のrefactor自体についてreview bundleを作成する。

推奨：

```text
stage3_8_5_architecture_cleanup_review.zip
```

---

# 52. Bundleに含めるもの

最低限：

```text
REVIEW_ME.md
architecture_before_after.md
module_move_map.md
test_summary.md
smoke_test_summary.md
fingerprint_v2_validation.json
review_bundle_validation.json
dms_topology_parity.json
```

および、

```text
git HEAD
git status
scoped diff
source tree
SHA-256 manifest
```

---

# 53. REVIEW_ME.md

冒頭で、

```text
Stage 3.8.5 Architecture Cleanup:
PASS_AWAITING_REVIEW
or
FAIL_STOP
```

を記載する。

続けて、

1. changed modules
2. Review Bundle separation result
3. fingerprint v2 result
4. reporting-only fingerprint test
5. shared primitives extracted
6. DMS topology move result
7. compatibility wrappers
8. Stage 3.8 behavioral parity
9. targeted tests
10. full tests
11. smoke test
12. known deferred cleanup

を記載する。

---

# 54. Acceptance Criteria

## Review Bundle

- generic bundle builderがcanonical
- Stage runnerからZIP/hash logicが分離
- existing run directoryからbundle生成可能

## Fingerprint

- computation/reporting fingerprint分離
- report-only editでcomputation fingerprint不変
- legacy fingerprint読み取り可能

## Search infrastructure

- comparator canonical ownerが1つ
- counters canonical ownerが1つ
- checkpoint lattice validator共通化
- duplicate implementationを増やしていない

## DMS

- canonical DMS topology moduleがStage番号に依存しない
- Stage 3.8 old import pathはcompatibility保持
- deterministic parity PASS

## Regression

- targeted PASS
- full suite PASS
- small smoke PASS

## Historical integrity

- Stage 3.8 96k results変更なし
- legacy artifacts変更なし
- optimizer rerunなし

---

# 55. 今回の成功条件

今回のcleanup後に、Stage 3.9を実装するとき、

```text
review bundle codeをコピーしない
fingerprint codeをコピーしない
counter accounting codeをコピーしない
DMS topologyをStage 3.8からimportしない
```

状態になっていれば成功とする。

---

# 56. 作業終了時の報告形式

```text
Stage 3.8.5 Architecture Cleanup:
PASS_AWAITING_REVIEW / FAIL_STOP

Review bundle separation:
PASS / FAIL

Fingerprint v2:
PASS / FAIL

Reporting-only fingerprint isolation:
PASS / FAIL

Shared search primitives:
PASS / PARTIAL / FAIL

DMS topology canonicalization:
PASS / FAIL

Compatibility wrappers:
PASS / FAIL

Stage 3.8 numerical parity:
PASS / FAIL

Targeted tests:
PASS / FAIL

Full suite:
<result>

Small smoke:
PASS / FAIL

96k rerun:
NO

Stage 3.9:
NOT STARTED

Review bundle:
<path>
```

その後停止すること。