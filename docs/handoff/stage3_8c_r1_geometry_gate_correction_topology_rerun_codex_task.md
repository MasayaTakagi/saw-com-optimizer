# Codex 作業指示書
## Stage 3.8C-R1 — Geometry-Gate Correction & Dual-Material Topology Screen Rerun

## 0. Mission

Stage 3.8A/Bでは、以下の実装・物理検証に成功した。

- generalized topology framework
- T0 current 3-IDT parity
- T1 symmetric 5-IDT finite/passive/reciprocal behavior
- T2 parallel 3-IDT composition identity
- 6-cell fixed-design sanity
- full repository regression

一方、Stage 3.8Cの96k fast optimization screenでは、最終incumbentが全12 runsでgeometry-invalid candidateとなり、topology rankingが無効になった。

主因は、

> hard manufacturing geometry violationが、filter performance violationと同じscalar rankingへ入り、
> geometry-invalidだがboundaryへ非常に近い候補が、
> geometry-validだがfilter violationを持つ候補より良くrankされ得る

ことである。

本R1の目的は、

1. hard geometry feasibilityをfilter性能より上位のlexicographic conditionへ修正する。
2. geometry / physics / frequency countersを実際に計測する。
3. MLIT aperture upper boundをStage 3.7D推奨値180 µmへ復元する。
4. 6 material×topology cellsでsmall pilotを行い、全セルでphysics evaluatorへ到達することを確認する。
5. pilot PASS後のみ、8k×2seedの96k topology fast screenを再実行する。
6. 今回初めて有効なT0/T1/T2 rankingを生成する。

topology implementationそのものは原則変更しない。

---

# 1. Source of truth

開始時に以下を記録する。

- git branch
- git HEAD
- git status
- git diff summary
- Stage 3.8 review bundle / summary
- current generalized topology implementation
- current geometry evaluator
- current objective / ranking implementation
- current checkpoint/counter implementation
- current M0/MLIT configs
- Stage 3.7D aperture recommendation
- current full regression result

Stage 3.8A/Bのvalidated topology physicsはsource of truthとして保持する。

---

# 2. Preserve validated topology implementation

原則として以下を変更しない。

## T0
- current generalized 3-IDT topology
- existing parity behavior
- electrical mapping

## T1
- symmetric 5-IDT topology
- current polarity / electrical grouping
- current mirror-symmetric parameterization

## T2
- parallel 3-IDT ×2 topology
- current admittance summation / nodal behavior
- current aperture split policy
- current wavelength-offset parameterization

topology implementationへ変更が必要になった場合は、理由を明記し、Stage 3.8A/B physics testsを再実行する。

---

# 3. Root-cause confirmation

修正前に、旧Stage 3.8C objective/ranking pathを確認する。

少なくとも以下を特定する。

- geometry validity evaluation function
- hard layout constraint evaluation
- total length constraint
- total electrode-count constraint
- objective construction
- infeasible candidate rank construction
- L-SHADEへ返すscalar objective
- incumbent replacement rule
- checkpoint best-selection rule
- final common-grid candidate selection rule

確認したroot causeを `stage3_8c_r1_geometry_gate_root_cause.md` へ記載する。

---

# 4. Hard-feasibility ranking rule

## 4.1 Required principle

hard geometry feasibilityはfilter performanceより優先する。

次を保証すること。

```text
ANY geometry-valid candidate
    ALWAYS outranks
ANY geometry-invalid candidate
```

geometry violationの数値がどれだけ小さくても例外なし。

例:

```text
valid candidate:
  geometry_violation = 0
  filter_max_violation = 0.8

invalid candidate:
  geometry_violation = 1e-8
  filter physics not evaluated

=> valid candidate MUST rank better
```

---

# 5. Recommended ranking representation

可能なら内部rankingをlexicographic tupleとして表す。

```text
rank = (
    geometry_invalid_flag,
    geometry_violation,
    filter_feasibility_flag,
    filter_max_violation,
    filter_sum_violation,
    objective,
)
```

ただしL-SHADE implementationがscalar objectiveを要求する場合はscalar化してもよい。その場合も以下を必ず満たす。

```text
max score of any geometry-valid candidate
<
min score of any geometry-invalid candidate
```

単純な小さいpenalty additionは禁止。

---

# 6. Geometry-invalid candidate behavior

geometry-invalid candidateでは原則としてCOM/network physicsを実行しない。

記録:

- geometry_rejections += 1
- candidate geometry
- violated hard constraints
- normalized violation values

filter metric用の `max_violation`, `sum_violation`, `worst_il`, `VSWR` をfake valueで作成し、geometry-valid candidateと同じ意味で扱ってはならない。

明示的statusを持たせる。

```text
evaluation_status = GEOMETRY_REJECTED
```

---

# 7. Geometry-valid physics candidate behavior

geometry-validの場合のみ、

- COM solve
- Y generation
- network conversion
- metrics
- filter constraint violation

へ進む。

成功時:

```text
valid_physics_evaluations += 1
```

frequency solve数:

```text
solved_frequency_points += number_of_frequency_points_actually_solved
```

を実カウントする。

---

# 8. Required counters

各runで最低限以下を実測する。

- objective_calls
- canonical_candidates_seen
- unique_decoded_evaluations
- geometry_rejections
- geometry_valid_candidates
- valid_physics_evaluations
- physics_failures
- cache_hits
- solved_frequency_points
- search_frequency_points
- validation_frequency_points
- elapsed_s

以下は禁止。

- 未計測値を0で埋めて「実測」と表示
- missing keyをreport側で意味のあるcounterとして0補完

未計測の場合は `null` / `not_recorded` 等を明示する。

---

# 9. Counter invariants

testsで少なくとも確認する。

```text
unique_decoded_evaluations
=
geometry_rejections
+ geometry_valid_candidates
```

実装上のinvalid decode等を分離する場合は、完全なaccounting identityを定義する。

また:

```text
valid_physics_evaluations <= geometry_valid_candidates
```

```text
solved_frequency_points > 0
if valid_physics_evaluations > 0
```

を確認する。

---

# 10. Known-valid seed designs

各 material × topology cell について、Stage 3.8B fixed-design sanityでphysics評価できた既知valid designをinitial populationへ最低1個必ず含める。

6 cells:

```text
M0/T0
M0/T1
M0/T2
MLIT/T0
MLIT/T1
MLIT/T2
```

これによりpilot開始時点から、少なくとも1つのgeometry-valid physics candidateが存在することを保証する。

---

# 11. Valid initial population generation

random/jitter population生成時は、

1. candidate decode
2. geometry hard constraint check
3. geometry-valid only accept into initial population

とする。

必要ならrejection samplingを使用する。

無限loop防止のため、

- maximum attempts
- accepted count
- rejected count

を保存する。

initial population生成に失敗したcellはpilotを開始せず停止する。

---

# 12. Bound restoration

Stage 3.7Dレビュー結果を反映する。

## M0

```text
aperture_um = 30–150
```

維持。

## MLIT

```text
aperture_um = 30–180
```

へ復元。

Stage 3.8旧runでMLITが30–150へ戻っていた問題を修正する。

他boundはStage 3.8 baselineを原則維持。

---

# 13. Geometry hard limits

hard manufacturing/layout constraintsとsearch-space boundsを明確に分離する。

最低限report:

- max total acoustic length
- max total electrode count
- width / aperture-related hard limit
- topology-specific hard constraints

`search bound != manufacturing hard bound` であることをコードとreportで区別する。

---

# 14. Regression tests for geometry ranking bug

最低限、以下のunit testを追加する。

## Test A — tiny geometry violation cannot beat valid filter

```text
candidate_invalid:
    geometry_violation = 1e-10

candidate_valid:
    geometry_violation = 0
    filter_max_violation = 10

assert rank(valid) < rank(invalid)
```

## Test B — invalid vs invalid

geometry-invalid candidate同士では、geometry violationが小さい方を良くrankしてよい。

## Test C — valid vs valid

geometry-valid同士では、従来のfilter ranking semanticsを維持する。

## Test D — incumbent cannot regress to geometry-invalid

一度geometry-valid incumbentが存在したら、geometry-invalid candidateへbestが戻らないこと。

## Test E — final selector

common-grid final selectionも同じhard-feasibility priorityを守る。

---

# 15. Re-run all Stage 3.8A/B validation

ranking/counter修正後、最低限以下を再実行する。

- T0 parity
- T1 finite/passive/reciprocal tests
- T2 Y-parallel identity
- fixed-design sanity 6 cases
- COM tests
- network tests
- material metadata tests
- geometry-ranking tests
- full regression

full regression fail時はpilotへ進まない。

---

# 16. Stage 3.8C-R1 Pilot

96k本番前に必ずsmall pilotを実施する。

## Matrix

```text
M0/T0
M0/T1
M0/T2
MLIT/T0
MLIT/T1
MLIT/T2
```

6 cells。

## Pilot budget

推奨:

```text
256 unique evaluations / cell
```

最低128、最大512まで許可。

1 seedのみでよい。

推奨seed:

```text
20260917
```

---

# 17. Pilot acceptance criteria

各cellで必ず:

```text
geometry_valid_candidates > 0
valid_physics_evaluations > 0
solved_frequency_points > 0
finite filter metrics exist
best incumbent is geometry-valid
```

を満たす。

さらに:

```text
valid_physics_fraction =
valid_physics_evaluations / unique_decoded_evaluations
```

をreportする。

---

# 18. Pilot stop conditions

1 cellでも以下なら本番96kを開始しない。

- best incumbent geometry-invalid
- valid_physics_evaluations == 0
- solved_frequency_points == 0
- no finite filter metrics
- population initialization failed
- all candidates rejected by geometry
- hard constraint accounting inconsistent

停止marker:

```text
STAGE3_8C_R1_PILOT_FAIL_STOP
```

---

# 19. Pilot efficiency diagnostic

geometry rejection率も確認する。

```text
geometry_rejection_fraction =
geometry_rejections / unique_decoded_evaluations
```

極端に高い場合、本Stageでは即bound redesignしない。

ただし `>90% rejected` のようにphysics探索がほぼできないcellがある場合は、96k浪費回避のためSTOPしてsearch-space redesignをrecommendする。

---

# 20. Stage 3.8C-R1 Main rerun

全6 pilot PASS後のみ本番を実行。

条件は元Stage 3.8と同じ。

```text
Zin = 50 ohm
Zout = 50 ohm
optimizer = production L-SHADE
cold start = true
warm start = false
parent transfer = false
neighbor warm start = false
```

Matrix:

```text
M0 × T0,T1,T2
MLIT × T0,T1,T2
```

Budget:

```text
8,000 unique decoded evaluations / seed
```

Base seeds:

```text
20260917
20260918
```

Total:

```text
96,000 nominal unique evaluations
```

---

# 21. Checkpoints

各run:

```text
2k
4k
6k
8k
```

保存:

- best hard-feasibility status
- best max violation
- best sum violation
- geometry
- active filter constraint
- geometry rejection count
- valid physics count
- solved frequency points
- last meaningful improvement
- wall time

---

# 22. Main-run acceptance criteria

各run終了時、

```text
final incumbent geometry-valid
valid_physics_evaluations > 0
solved_frequency_points > 0
finite metrics present
```

を必須とする。

満たさないrunはtopology rankingから除外し、`INVALID_RUN` と表示する。

---

# 23. No reuse of invalid Stage 3.8 ranking

旧Stage 3.8の、

- M0 topology ordering
- MLIT topology ordering
- geometry-only max violation
- final invalid incumbent

を新rankingへ混ぜない。

旧結果は:

```text
INVALIDATED_BY_GEOMETRY_RANKING_BUG
```

と明示する。

---

# 24. Primary ranking within material

有効runのみでmaterialごとに比較する。

優先順:

1. feasible fraction
2. median max violation
3. 75th percentile max violation
4. median sum violation
5. median worst IL
6. seed consistency
7. best single seed as tie-breaker only

---

# 25. Conditional third seed

修正版2seed結果を見てからのみ判断。

third seed:

```text
20260919
```

条件:

- top2 difference <10%
- seed winner reverses
- lucky outlier suspicion
- boundary-limited ambiguity
- valid-physics count imbalance materially affects confidence

最大4 cells。

自動無条件実行は禁止。

---

# 26. Boundary diagnostics

filter topologyごとに:

- aperture bounds
- wavelength bounds
- IDT pair bounds
- reflector bounds
- gap bounds
- manufacturing total length
- manufacturing total electrode count

を分けてreportする。

特に:

```text
SEARCH_BOUND_HIT
HARD_GEOMETRY_REJECTION
```

を別カテゴリにする。

---

# 27. T0/T1/T2 comparison questions

最終summaryで回答:

1. 修正後、全6 cellsでphysics evaluatorへ到達したか？
2. geometry rejection率はtopologyごとにどの程度か？
3. T0/T1/T2のrankingはM0でどうなったか？
4. T0/T1/T2のrankingはMLITでどうなったか？
5. M0/MLITで同じleaderか？
6. T1 5-IDTはT0を上回る兆候があるか？
7. T2 Parallel DMSはwideband / stop_1改善を示すか？
8. stop_1 dominanceはどのtopologyで弱まるか？
9. topology rankingはmaterial-sensitiveか？
10. Stage 3.9へ残すtopologyは最大2つのうち何か？
11. third seedが必要か？
12. FEM extractionを今すぐ行う必要があるか？

---

# 28. Required outputs

## Root cause / validation

- `stage3_8c_r1_geometry_gate_root_cause.md`
- `stage3_8c_r1_geometry_ranking_tests.md`
- `stage3_8c_r1_pilot_summary.md`

## CSV

- `stage3_8c_r1_pilot_results.csv`
- `stage3_8c_r1_all_seed_results.csv`
- `stage3_8c_r1_topology_summary_by_material.csv`
- `stage3_8c_r1_cross_material_ranking.csv`
- `stage3_8c_r1_geometry_rejections.csv`
- `stage3_8c_r1_counter_accounting.csv`
- `stage3_8c_r1_boundary_diagnostics.csv`
- `stage3_8c_r1_constraint_bottlenecks.csv`
- `stage3_8c_r1_compute_cost.csv`
- `stage3_8c_r1_third_seed_promotions.csv` if used

## Metadata

- M0 profile snapshot
- MLIT profile snapshot
- M0 aperture bound
- MLIT aperture bound = 180 um
- topology definitions
- search-space snapshots
- hard geometry constraints
- validation grid/hash
- git branch/head/status
- exact commands
- test output

## Markdown

- `stage3_8c_r1_topology_fast_screen_summary.md`
- `test_summary.md`

---

# 29. Required plots

最低限:

1. valid physics fraction by material/topology
2. geometry rejection fraction
3. median max violation by material/topology
4. seed-level max violation
5. stop_1 / stop_2 comparison
6. boundary diagnostics
7. representative validated responses
8. compute cost / wall time

---

# 30. Final classification

修正版実験結果から以下を選ぶ。

### `ROBUST_TOPOLOGY_LEADER`
同一topologyがM0/MLITで有力。

### `ROBUST_SHORTLIST`
同一2候補が両materialで上位。

### `MATERIAL_DEPENDENT_TOPOLOGY`
materialによってleader/orderが変わる。

### `BOUNDARY_LIMITED`
valid optimizationはできたが、search/manufacturing boundaryがrankingを支配。

### `SEARCH_SPACE_INVALID`
geometry rejectionが極端で、topology比較に必要なphysics探索ができない。

---

# 31. Promotion rule

Stage 3.9へ残すtopologyは最大2個。

旧invalid Stage 3.8結果はpromotionに使わない。

Stage 3.9は本Stage終了後、ChatGPT reviewを挟んでから別指示で開始する。

---

# 32. Repository hygiene

終了時:

- R1 source changes
- counter changes
- ranking changes
- config changes
- generated artifacts
- unrelated pre-existing dirty files

を分類。

commit / pushは禁止。

---

# 33. Hard stop

Pilot failure:

```text
STAGE3_8C_R1_PILOT_FAIL_STOP
```

Main run complete:

```text
STAGE3_8C_R1_VALID_TOPOLOGY_SCREEN_COMPLETE_STOP
```

Search-space invalid:

```text
STAGE3_8C_R1_SEARCH_SPACE_REDESIGN_REQUIRED_STOP
```

いずれの場合も:

- Stage 3.9を開始しない
- hybridへ進まない
- impedance sweepを開始しない

---

# 34. Philosophy

今回の修正の本質は、geometry constraintのpenalty magnitudeを調整することではない。

重要なのは、

> hard geometry feasibilityとfilter performanceは別階層の条件であり、
> geometry-invalid candidateはfilter optimizationのwinnerになれない

という問題構造をoptimizerへ正しく反映することである。

96k evaluationsを再投入する前に、small pilotで「本当にphysicsを探索している」ことを必ず確認する。

Stage 3.8A/Bでtopology physicsは既にvalidatedされているため、本R1ではoptimizer/constraint integrationだけを必要最小限修正し、有効なtopology rankingを取得することに集中する。
