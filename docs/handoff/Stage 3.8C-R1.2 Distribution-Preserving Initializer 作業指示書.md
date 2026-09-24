# Stage 3.8C-R1.2
## Distribution-Preserving Initializer Correction

## 1. 目的

Stage 3.8C-R1.1ではgeometry-aware conditional initializerによって、

- initial geometry rejection = 0%
- geometry-valid initial population = 100%
- 6/6 cellsでphysics evaluation成立
- fixed-design sanity 6/6 PASS
- full test suite PASS

を達成した。

一方、R1.1のinitializerはfeasible support自体は保持しているものの、

**元のindependent-uniform proposalをgeometry-valid条件で条件付けした確率分布とは異なるinitial population distribution**

を生成していることが確認された。

Stage 3.8の目的は、

> M0 / MLIT × T0 / T1 / T2 をできるだけ公平な探索条件で比較すること

である。

そのためR1.2では、initializer efficiencyよりも

**初期探索分布の公平性・再現性・解釈容易性**

を優先する。

---

# 2. R1.2の基本方針

R1.1で導入したconditional geometry-aware samplingをProduction用initializerとして使用しない。

代わりに、

```text
original independent-uniform proposal
    ↓
canonicalize discrete/integer variables
    ↓
geometry validation
    ↓
geometry-validならaccept
geometry-invalidならresample
```

という**rejection sampling方式**へ戻す。

ただし、R1で使用していた

```text
geometry rejection > 90% → FAIL
```

というGateは廃止する。

高rejection率そのものはFAIL理由にしない。

重要なのは、

- 必要populationを確実に生成できること
- geometry-valid populationを得られること
- generation overheadが実用上十分小さいこと
- diversityが維持されていること

である。

---

# 3. 今回変更してよい範囲

変更対象は原則として、

- initial population generation
- initializer diagnostics
- initializer Gate
- related tests
- Stage 3.8C R1.2 study/config/reporting

のみ。

以下は変更しない。

- COM physics model
- network model
- measurement logic
- B28 specification
- objective
- filter violation definition
- geometry constraints
- manufacturing constraints
- topology definitions
- L-SHADE evolution/update rule
- optimizer budget
- impedance
- material COM profiles
- common validation grid
- geometry-first comparator
- physics evaluator semantics
- counter semantics

---

# 4. Search spaceを変更しない

R1.2ではR1/R1.1と同じsearch spaceを維持する。

特に、

```text
M0 aperture   = 30–150 µm
MLIT aperture = 30–180 µm
```

を維持する。

また、

```text
max total acoustic length = 750 µm
max total electrode count = 500
```

も変更しない。

pair counts、reflector counts、pitch等のupper/lower boundsをrejection削減目的で変更してはならない。

---

# 5. Initializer implementation

## 5.1 Proposal distribution

各design variableは、R1以前の定義どおり独立proposalからsamplingする。

continuous variables：

```text
declared search interval内のuniform
```

integer/discrete variables：

```text
declared discrete domain内のuniform
```

を基本とする。

既存実装にcanonicalization ruleがある場合はそれを維持する。

---

## 5.2 Geometry rejection

candidate生成後、

```text
decode
→ geometry calculation
→ hard geometry validation
```

を行う。

geometry-valid：

```text
accept
```

geometry-invalid：

```text
reject
→ new independent sample
```

とする。

invalid candidateを、

- clamp
- project
- repair
- nearest feasible pointへ移動
- topology-dependent conditional resampling

してはならない。

---

# 6. Distribution preservation

R1.2で重要なのは、

**元のindependent-uniform proposal distributionを変更しないこと**

である。

したがって、

```text
Aを先にsampleして、
残り変数のfeasible intervalを計算して、
その中からBをsample
```

のようなR1.1 conditional samplingはProduction pathから外す。

R1.1 initializerは比較・diagnostic目的でコードを残してもよいが、

```text
production/default initializer
```

としては使用しない。

---

# 7. max_attempts

rejection samplingには明示的な安全上限を設定する。

population sizeを `N` としたとき、十分余裕のあるattempt budgetを設定する。

例えば、

```text
max_attempts = max(
    fixed_minimum,
    multiplier * population_size
)
```

等とする。

R1/R1.1で確認されたT2 acceptance ≈7%程度を考慮し、

180 population程度で正常に生成できる十分な余裕を持たせる。

ただし無限loopは禁止。

max_attempts超過時は、

```text
INITIALIZER_EXHAUSTED
```

等の明示的なfailureとして停止する。

---

# 8. Initializer Gateの変更

R1/R1.1に存在した、

```text
rejection fraction < 50%
```

または

```text
rejection fraction < 90%
```

をPASS/FAIL Gateとして使用しない。

rejection fractionは**diagnostic metric**とする。

---

# 9. 新しいMandatory Initializer Gates

以下を必須Gateとする。

## Gate A

```text
requested population size == accepted population size
```

## Gate B

```text
100% of accepted population is geometry-valid
```

## Gate C

```text
max_attempts not exceeded
```

## Gate D

```text
unique population count is sufficient
```

duplicate concentrationが異常でないこと。

## Gate E

initializer runtimeが実用上問題ないこと。

---

# 10. Runtime Gate

geometry evaluationはphysics evaluationより十分軽量であるため、rejection率ではなく実時間を見る。

各cellについて、

- population generation wall time
- total attempts
- accepted
- rejected
- rejection fraction
- attempts per accepted individual

を記録する。

absolute thresholdを設定する場合は、過度に厳しくしない。

まずPilotでは測定値を記録し、

**明らかな数十秒～分単位の異常増加がないこと**

を確認する。

通常の数秒以下のinitializer overheadであれば問題視しない。

---

# 11. Distribution validation

R1.2では、initializerが期待したproposal distributionになっていることを検証する。

各cellで少なくとも以下を保存する。

- variable min
- q05
- q25
- median
- q75
- q95
- max
- mean
- standard deviation

geometry metricsについても同様に、

- total electrode count
- total acoustic length

を出力する。

---

# 12. R1.1との比較

R1.2 reportには、

```text
R1
R1.1
R1.2
```

のinitializer比較を掲載する。

最低限、

- candidate attempts
- rejection fraction
- generation time
- variable medians
- total-electrode distribution
- total-length distribution

を比較する。

ただし、

**rejection率が増えたこと自体をregressionと扱わない。**

R1.2では分布保存が目的である。

---

# 13. Optional Monte Carlo reference

可能であれば、optimizerを動かさないinitializer-only Monte Carlo testを追加する。

十分大きなsample countで、

```text
independent uniform proposal
→ geometry rejection
```

を実行し、

R1.2 initializerが同じ分布を再現していることを確認する。

これはCOM physicsを実行しない。

例えば、

```text
10k–100k proposals
```

程度の軽量testでよい。

目的は、

- io_idt_pairs
- center_idt_pairs
- reflector_electrodes
- electrode count
- acoustic length

等の分布がR1.1 conditional samplerのようにorder-dependentになっていないことの確認である。

---

# 14. Sampling order independence

R1.2ではcandidateの全変数を元のproposal distributionから独立samplingするため、

**variable processing orderによってpopulation分布が変わらないこと**

を保証する。

もし内部実装上順序依存が残る場合は修正する。

---

# 15. Unit tests

最低限以下を追加・更新する。

## A. deterministic replay

同じseed/configで同じpopulationが生成される。

## B. geometry validity

accepted population 100% geometry-valid。

## C. declared bounds

全variableがdeclared search bounds内。

## D. rejection behavior

invalid candidateがrepair/clampされずrejectされる。

## E. max-attempt failure

極端なmock constraintでmax_attemptsを超えた場合に明示的にFAILする。

## F. diversity

populationのduplicate concentrationが異常でない。

## G. topology coverage

T0/T1/T2すべてでpopulation生成可能。

## H. distribution regression

R1.1 conditional samplingで発生した明確なorder biasがProduction initializerに存在しない。

## I. geometry-first ranking regression

既存testを維持。

## J. gpt6sol routing regression

R1.1で追加したtestを維持。

---

# 16. gpt6sol設定

R1.1で行った

```text
gpt5.6sol
→
gpt6sol
```

へのSol review target migrationを維持する。

active runtime/config/testを旧モデルへ戻してはならない。

historical artifact内の旧model記録は変更しない。

R1.2でもrouting testを実施する。

---

# 17. Repository保護

作業開始時に以下を保存する。

```text
git status --short
git diff --stat
git diff --cached --stat
git rev-parse HEAD
git branch --show-current
```

禁止：

- git reset --hard
- unrelated user modificationsの削除
- repository全体のrestore
- 無断stash
- 無断commit
- 無断push

R1.2による変更とpre-existing changesを区別する。

---

# 18. Preflight

Pilot前に以下をPASSさせる。

1. initializer unit tests
2. geometry ranking regression
3. fixed-design sanity
4. counter accounting tests
5. gpt6sol routing tests
6. known-seed replay
7. full repository test suite

---

# 19. R1.2 Pilot条件

R1/R1.1と比較可能な条件を維持する。

## Materials

```text
M0
MLIT
```

## Topologies

```text
T0
T1
T2
```

合計6 cells。

## Seed

```text
20260917
```

## Evaluation budget

```text
256 optimizer evaluations / cell
```

---

# 20. Pilot Mandatory Gates

各6 cellsについて以下を要求する。

### Initializer

- requested population生成成功
- accepted population 100% geometry-valid
- max_attempts未到達
- diversity正常
- runtime正常

### Physics

- geometry-valid incumbent
- successful physics evaluations > 0
- solved frequency points > 0
- finite search-grid metrics
- finite common-grid metrics

### Accounting

- counter accounting成立

### Regression

- fixed-design sanity 6/6 PASS
- full test suite PASS

---

# 21. Rejection fractionの扱い

以下のような結果でも、

```text
T0 rejection ≈ 85–90%
T2 rejection ≈ 90–95%
```

それだけではFAILにしない。

代わりに、

```text
population successfully generated
AND
generation time acceptable
AND
geometry-valid population 100%
```

ならPASS候補とする。

rejection率はoptimization performance metricではない。

---

# 22. Pilot性能値の扱い

256 evaluations × 1 seedのため、

今回も正式rankingに使用しない。

以下は禁止：

```text
T0が最良
T1が優位
T2をdrop
```

等のProduction/Stage 3.9決定。

結果は、

```text
diagnostic only
promotion_eligible = false
seed_consistency = N/A_single_seed
```

として扱う。

---

# 23. R1.1との性能差を過剰解釈しない

R1.1とR1.2はinitial population distributionが異なるため、256-eval結果が変化しても、

```text
optimizer性能が改善/悪化した
```

と即断しない。

今回の目的はdistribution semantics修正である。

---

# 24. Cross-material limitation

以下は維持する。

```text
M0:
aperture = 30–150 µm

MLIT:
aperture = 30–180 µm
```

したがってM0 vs MLIT差を純粋なmaterial effectとして扱わない。

metadataとsummaryに明記する。

---

# 25. Production

今回もProductionは実行しない。

Pilot PASS時：

```text
STAGE3_8C_R1_2_PILOT_PASS_AWAITING_REVIEW
```

Pilot FAIL時：

```text
STAGE3_8C_R1_2_PILOT_FAIL_STOP
```

を作成し停止する。

予定Production：

```text
8k evaluations
× 2 seeds
× 6 cells
= 96k evaluations
```

はChatGPTレビュー後まで開始禁止。

---

# 26. Review bundle

推奨ファイル名：

```text
stage3_8c_r1_2_pilot_review.zip
```

最低限以下を含める。

## Summary

```text
REVIEW_ME.md
stage3_8c_r1_2_pilot_summary.md
stage3_8c_r1_2_pilot_gate.json
test_summary.md
```

## Initializer

```text
stage3_8c_r1_2_initializer_summary.csv
stage3_8c_r1_2_initializer_attempts.csv
stage3_8c_r1_2_initializer_distribution.csv
stage3_8c_r1_2_geometry_rejections.csv
stage3_8c_r1_2_population_preflight.csv
```

## R1/R1.1/R1.2 comparison

```text
stage3_8c_initializer_generation_comparison.csv
stage3_8c_initializer_distribution_comparison.csv
```

可能ならMonte Carlo referenceも含める。

```text
stage3_8c_r1_2_initializer_reference_mc.csv
```

## Optimization / Physics

```text
stage3_8c_r1_2_pilot_results.csv
stage3_8c_r1_2_counter_accounting.csv
stage3_8c_r1_2_fixed_design_sanity.csv
stage3_8c_r1_2_boundary_diagnostics.csv
stage3_8c_r1_2_validated_responses.csv
```

## Sol routing

```text
gpt6sol_routing_test_results.*
```

## Metadata

```text
metadata/input_config.yaml
metadata/run_source_metadata.json
metadata/resolved_search_space_snapshots.json
metadata/material_profile_snapshots.json
metadata/common_validation_grid.csv
```

## Reproducibility

- git HEAD
- branch
- pre/post status
- scoped source diff
- source/config fingerprint
- SHA-256 manifest

---

# 27. REVIEW_ME.md必須事項

冒頭に、

```text
Stage 3.8C-R1.2 Pilot:
PASS_AWAITING_REVIEW
or
FAIL_STOP
```

を記載する。

続いて、

1. R1.2 initializer方式
2. R1.1 conditional samplerをProductionから外したこと
3. R1/R1.1/R1.2 rejection比較
4. generation runtime
5. distribution comparison
6. population geometry validity
7. physics-valid cells
8. fixed-design sanity
9. full tests
10. gpt6sol routing
11. Production未実行
12. known limitations

を記載する。

---

# 28. 禁止事項

- R1.1 conditional samplerをProduction defaultとして残す
- rejection率を下げるためsearch boundsを縮小
- geometry constraints緩和
- invalid candidateのclamp/repair
- objective変更
- COM変更
- topology変更
- L-SHADE変更
- specification変更
- Pilot後の自動Production
- Stage 3.9開始
- hybrid topology追加
- impedance sweep開始
- historical artifactsの書き換え
- gpt5.6solへのsilent fallback
- 無断commit
- 無断push

---

# 29. 完了条件

以下すべてを満たすこと。

## Initializer

- independent-uniform proposalを維持
- invalid candidateはrejection
- repair/clampなし
- accepted population 100% geometry-valid
- max_attempts内にpopulation生成
- diversity正常
- runtime実用範囲

## Tests

- initializer tests PASS
- distribution regression PASS
- geometry-ranking regression PASS
- fixed-design sanity 6/6 PASS
- counter accounting PASS
- gpt6sol routing PASS
- full repository tests PASS

## Pilot

- 6/6 cells実行
- physics evaluation成立
- finite search-grid/common-grid metrics
- 256 evaluations/cell
- seed 20260917

## Stop

- Production NOT STARTED
- PASS_AWAITING_REVIEW または FAIL_STOP marker
- review bundle生成
- レビュー待ちで停止

---

# 30. 作業終了時の報告形式

チャットには以下だけを簡潔に報告する。

```text
1. R1.2 Pilot:
   PASS_AWAITING_REVIEW / FAIL_STOP

2. Initializer:
   independent-uniform rejection sampling restored

3. Initial population:
   geometry-valid x / x

4. Initial rejection:
   M0/T0:
   M0/T1:
   M0/T2:
   MLIT/T0:
   MLIT/T1:
   MLIT/T2:

5. Generation time:
   max:
   median:

6. Physics-valid cells:
   x / 6

7. Fixed-design sanity:
   x / 6

8. Test suite:
   PASS / FAIL

9. gpt6sol routing:
   VERIFIED / NOT VERIFIED / FAILED

10. Production:
    NOT STARTED

11. Review bundle:
    <path>
```

その後、作業を停止すること。