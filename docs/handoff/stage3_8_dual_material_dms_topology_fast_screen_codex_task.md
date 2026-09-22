# Codex 作業指示書
## Stage 3.8 — Dual-Material DMS Topology Fast Screen

## 0. Mission

Stage 3.7までに以下を確認した。

### Material baselines

#### M0
- current hypothetical COM baseline
- Stage 3.6までのhistorical continuity用
- aperture range: 30–150 um

#### MLIT
- literature-derived normalized COM profile
- 42°YX-LiTaO3
- metal electrode: unspecified
- effective h/lambda ≈ 0.08
- effective duty ≈ 0.65
- signed-real source convention
- aperture range: 30–180 um

### Stage 3.7 conclusions

- M0とMLITで50 Ω最適geometryの方向が大きく変わる
- material direction is sensitive
- MLIT is preliminary usable
- FEM extraction is HOLD
- topology study should not rely on M0 only
- M0/MLIT dual baseline is preferred

本Stageの目的は、

> M0とMLITの両material profileで、3-IDT / 5-IDT / Parallel DMSを同条件でfast screenし、
> topology rankingがmaterial profileを変えても維持されるか確認すること。

本Stageはtopology screeningであり、最終性能・収束・global optimumを求めない。

---

# 1. Hard boundaries

本Stageでは以下を行わない。

- impedance sweep
- Zin/Zout optimization
- hybrid / ladder implementation
- 32k / 64k escalation
- 5-seed confirmation
- Stage 3.9 refinement
- FEM extraction
- material parameter fitting
- continuous h/lambda optimization
- continuous duty optimization
- topology-specific ad hoc COM tuning
- repeated bound expansion during screening

本Stage終了後に必ず停止する。

---

# 2. Repository / baseline audit

開始時に以下を保存する。

- git branch
- git HEAD
- git status
- git diff summary
- M0 profile snapshot
- MLIT profile snapshot
- current 3-IDT topology implementation
- current G1_G2 search-space definition
- current L-SHADE production implementation
- current validation methodology
- current common validation grid / hash
- Stage 3.7D aperture recommendation
- current material metadata schema

pre-existing unrelated dirty filesをStage 3.8 changesへ混ぜない。

commit / pushは本Stageの目的ではない。

---

# 3. Topologies under test

比較対象は3種類。

## T0 — Current 3-IDT baseline

構造:

```text
Reflector
Gap
Outer IDT
Gap
Center IDT
Gap
Outer IDT
Gap
Reflector
```

electrical mappingはcurrent `center_outer_same` production pathを維持。

役割:

- control
- Stage 3.6 / 3.7 continuity
- generalized topology frameworkのparity reference

---

## T1 — Symmetric 5-IDT DMS

構造:

```text
R - A - B - C - B - A - R
```

初回はmirror symmetryを強制する。

推奨electrical grouping:

```text
Port P: A + C + A
Port Q: B + B
```

polarityは文献で一般的な交互接続に合わせる。

実装時にpolarity assumptionを必ずmetadataへ保存する。

### DOF policy

完全5-IDT独立化は禁止。

初回は約10 DOFに制限する。

推奨:

- wavelength_A
- wavelength_B
- wavelength_C
- reflector_wavelength
- pairs_A
- pairs_B
- pairs_C
- common_idt_gap_lambda
- reflector_gap_lambda
- aperture_um

必要に応じて内部表現は変えてよいが、
自由度を不必要に増やさない。

---

## T2 — Parallel 3-IDT ×2

2つの3-IDT acoustic trackをelectrically parallelに接続する。

目的は単純なadmittance倍増ではなく、
2つの中心周波数を少しずらしたwideband構成の可能性を見ること。

### Shared DOFs

原則として2 trackで共有:

- pair counts
- normalized IDT gap
- reflector gap
- center/main wavelength ratio
- reflector/main wavelength ratio
- reflector count policy

### Independent DOFs

最低限:

- track A main wavelength
- track B main wavelength

### Aperture policy

2 trackそれぞれにfull apertureを与えない。

初回は:

```text
total acoustic aperture budget = one shared value
track A aperture = total / 2
track B aperture = total / 2
```

を推奨。

これにより単純な2倍area advantageを避ける。

aperture split DOFはStage 3.8では追加しない。

---

# 4. Generalized topology framework

既存COM coreを変更せず、
topology definition / IDT section list / port mappingを一般化する。

目標:

```text
COM section core
        ↓
generic acoustic section chain
        ↓
generic IDT-to-electrical-port mapping
        ↓
2-port Y
```

禁止:

- T1/T2専用にCOM方程式を複製
- topologyごとに別solverを作る
- current T0 implementation parityを失う

---

# 5. Stage 3.8A — Implementation validation

optimization前に必ずphysics testsを通す。

## 5.1 T0 parity

same:

- geometry
- provider
- frequency grid
- wiring

で、

```text
legacy/current 3-IDT evaluator
==
generalized T0 evaluator
```

をstrict numerical toleranceで確認する。

比較:

- Y
- S
- IL
- VSWR
- metrics
- passivity diagnostics

---

## 5.2 T1 5-IDT sanity

最低限:

- finite Y
- reciprocal
- passive
- mirror geometry gives expected symmetry
- port mapping deterministic
- polarity metadata saved
- no singular network behavior over target band

1～2個のfixed designでresponseをplotする。

---

## 5.3 T2 parallel identity test

同一geometryの2 identical tracksの場合、

```text
Y_parallel ≈ Y_track1 + Y_track2
```

かつ同一なら、

```text
Y_parallel ≈ 2 * Y_single
```

を確認する。

さらに:

- reciprocal
- passive
- no hidden extra termination
- total aperture split correctly applied

を確認。

---

# 6. Full regression gate

実装後、optimization前に以下を実行。

- topology unit tests
- T0 parity tests
- T1 physics tests
- T2 parallel identity tests
- COM analytic tests
- network tests
- material metadata tests
- passivity / reciprocity tests
- full repository regression

保存:

- command
- passed
- failed
- skipped
- runtime

full regression fail時はscreenを開始しない。

---

# 7. Stage 3.8B — Fixed-design spectral sanity screen

各 material × topology について、
optimizerを使わず代表geometryを1つ評価する。

Total:

```text
2 materials × 3 topologies = 6 fixed cases
```

目的:

- B28 vicinityにmodeがあるか
- nonphysical responseがないか
- T1でadditional modesが出るか
- T2でtwo-track modesが適切に重なるか
- stop_1改善余地があるか
- topology implementation mistakeがないか

性能順位はつけない。

---

# 8. Initial geometry construction

## T0

Stage 3.7 material-specific representative 3-IDT geometryを利用。

- M0: Stage 3.6 / 3.7 reference
- MLIT: Stage 3.7C MLIT fast-screen representative

## T1

T0 geometryを基準に、
A/B/Cを物理的に妥当な範囲へ初期化する。

例えば:

- center C near T0 center wavelength
- B intermediate
- A near outer wavelength
- pair counts distribute T0 equivalent electrode budget

完全な手最適化は禁止。

## T2

T0を2 trackへ分け、
main wavelengthだけ小さく±offsetする。

初期offsetはB28 band coverageを意識するが、
過大にしない。

初期offset assumptionを保存する。

---

# 9. Material-specific bounds

## M0

```text
aperture: 30–150 um
```

その他はcurrent physically justified boundsをベースにする。

## MLIT

```text
aperture: 30–180 um
```

Stage 3.7D結果に基づく。

### Important

profile-specific boundsは許可する。

ただしfinal analysisでは、

> absolute performance M0 vs MLIT

を直接rankingしない。

比較は原則:

- topology ranking within M0
- topology ranking within MLIT

とする。

---

# 10. Topology-specific fairness rules

topology間で自由度数が異なるため、
以下を記録する。

- dimensions
- population size
- unique evaluations
- valid physics evaluations
- solved frequency points
- wall time
- COM section count

production L-SHADEのdimension scalingを使用する。

budgetはunique decoded evaluations基準。

---

# 11. Stage 3.8C — Main fast optimization screen

## Conditions

全セル共通:

```text
Zin = 50 ohm
Zout = 50 ohm
optimizer = production L-SHADE
cold start = true
warm start = false
parent transfer = false
neighbor warm start = false
common validation methodology = true
bound expansion during run = false
```

## Matrix

```text
M0:
  T0
  T1
  T2

MLIT:
  T0
  T1
  T2
```

6 cells。

## Budget

```text
8,000 unique evaluations / seed
```

## Base seeds

```text
20260917
20260918
```

Base total:

```text
6 × 2 × 8k = 96k unique evaluations nominal
```

---

# 12. Checkpoints

各run:

```text
2k
4k
6k
8k
```

保存:

- best max violation
- best sum violation
- feasible
- geometry
- active constraint
- last meaningful improvement
- elapsed time
- unique evals
- solved frequency points

convergence claim禁止。

---

# 13. Primary ranking within each material

各material profileごとにtopologyを比較する。

優先順:

1. feasible fraction
2. median max violation
3. 75th percentile max violation
4. median sum violation
5. median worst IL
6. seed consistency
7. best single seedはtie-breakerのみ

2seedしかないため、
medianだけで過度に結論を出さない。

---

# 14. Conditional third seed

最初からthird seedを回さない。

以下の場合のみ候補:

- top 2 topology差 < 10%
- 2seedでwinnerが逆転
- one lucky outlier suspicion
- boundary hitがrankingへ強く影響
- one topology clearly underexplored at 8k

third seed:

```text
20260919
```

最大4 cellsまで。

追加実行前にautomatic ruleでpromotion対象を記録する。

---

# 15. Boundary diagnostics

各runで必ず記録:

- aperture lower/upper hit
- wavelength lower/upper hit
- center wavelength lower/upper hit
- reflector wavelength lower/upper hit
- pair-count lower/upper hit
- reflector count lower/upper hit
- gap lower/upper hit

分類:

```text
BOUNDARY_FREE
BOUNDARY_TOUCHING
BOUNDARY_LIMITED_PROMISING
BOUNDARY_LIMITED_UNRESOLVED
```

Stage 3.8内でboundを広げて再runしない。

---

# 16. Important topology metrics

performance metrics:

- max violation
- sum violation
- worst IL
- ripple
- input VSWR
- output VSWR
- stop_1 attenuation / violation
- stop_2 attenuation / violation
- active limiting constraint

structural metrics:

- total IDT pair count
- total reflector count
- total acoustic aperture
- number of acoustic sections
- approximate acoustic length
- approximate footprint
- topology DOF
- COM evaluation cost
- wall time

---

# 17. Stop_1 analysis

Stage 3.6では`stop_1` dominanceが強かった。

各topologyで:

- stop_1 remains dominant?
- stop_1 violation decreases?
- new bottleneck appears?
- 5-IDT / Parallel generates useful transmission-zero / mode shaping?

を明示的に比較する。

単純なoverall max violationだけでなく、
constraint bottleneckの変化を重視する。

---

# 18. Cross-material robustness analysis

M0とMLITを直接性能比較しない。

比較するのはtopology ranking pattern。

例:

```text
M0:
T1 > T2 > T0

MLIT:
T1 > T0 > T2
```

なら:

```text
T1 robust leader
```

別例:

```text
M0:
T0 > T1 > T2

MLIT:
T2 > T1 > T0
```

なら:

```text
topology ranking materially model-dependent
```

---

# 19. Final classification

以下のどれかに分類する。

## `ROBUST_TOPOLOGY_LEADER`

同じtopologyがM0/MLIT両方で有力。

→ Stage 3.9へprimary candidateとして進める。

---

## `ROBUST_SHORTLIST`

同じ2 topologyが両materialで上位。

→ 2候補をStage 3.9へ残す。

---

## `MATERIAL_DEPENDENT_TOPOLOGY`

M0とMLITでleader/orderが大きく変わる。

→ 各materialの有力topologyを保持。
最大2候補へ整理。

---

## `BOUNDARY_LIMITED`

topology rankingがbound pressureで決められない。

→ Stage 3.9でselected topologyのみbound確認。

---

## `NO_GAIN_OVER_3IDT`

T1/T2に明確な価値がなく、
両materialでT0が十分優位。

→ T0をhybrid baseline候補とする。

---

# 20. Promotion to Stage 3.9

Stage 3.9へ残すtopologyは最大2個。

選定基準:

- material robustness
- median performance
- seed consistency
- stop_1 improvement
- boundary status
- implementation complexity
- wall-time cost

ただしcomplexityだけで良いtopologyを落とさない。

Stage 3.8でwinnerを1つに無理に絞る必要はない。

---

# 21. Required outputs

## Data

- `stage3_8_all_seed_results.csv`
- `stage3_8_topology_summary_by_material.csv`
- `stage3_8_cross_material_ranking.csv`
- `stage3_8_boundary_diagnostics.csv`
- `stage3_8_constraint_bottlenecks.csv`
- `stage3_8_compute_cost.csv`
- `stage3_8_geometry_summary.csv`
- `stage3_8_third_seed_promotions.csv` if used

## Metadata

- M0 profile snapshot
- MLIT profile snapshot
- T0 topology definition
- T1 topology definition
- T2 topology definition
- topology-port mapping
- polarity assumptions
- search-space snapshots
- validation grid identity/hash
- git head / branch / status
- exact test commands
- exact run configs

## Markdown

- `stage3_8_implementation_validation.md`
- `stage3_8_fixed_design_sanity.md`
- `stage3_8_topology_fast_screen_summary.md`
- `test_summary.md`

## Plots

minimum:

1. topology median max violation by material
2. seed-level max violation by topology
3. stop_1 / stop_2 comparison
4. normalized geometry comparison
5. boundary-hit summary
6. compute cost / wall-time comparison
7. representative S21 / IL response for each material × topology

---

# 22. Summary questions

最終summaryで必ず回答:

1. T0/T1/T2 implementationはphysics/regressionを通ったか？
2. 5-IDTは3-IDTより有望か？
3. Parallel DMSはwideband化の兆候を示したか？
4. topology rankingはM0/MLITで一致するか？
5. material modelによってleaderが変わるか？
6. stop_1 dominanceはどのtopologyで最も改善したか？
7. boundary-limited candidateはあるか？
8. third seedは必要だったか？
9. Stage 3.9へ残すtopologyは何か？
10. FEM extractionをStage 3.9前に行う必要はあるか？
11. hybridへ進む前に追加DMS topologyが必要か？

---

# 23. Reporting cautions

禁止表現:

- global optimum
- converged topology
- final DMS
- experimentally validated
- calibrated material model
- best real-world topology

推奨:

- fast-screen leader
- preliminary topology ranking
- material-robust candidate
- material-sensitive ranking
- model-dependent result
- boundary-limited candidate

---

# 24. Repository hygiene

終了時に分類:

- Stage 3.8 source changes
- topology framework changes
- tests
- generated results
- pre-existing unrelated dirty files

commit / pushはしない。

---

# 25. Hard stop

成功:

```text
STAGE3_8_DUAL_MATERIAL_TOPOLOGY_FAST_SCREEN_COMPLETE_STOP
```

implementation / physics failure:

```text
STAGE3_8_TOPOLOGY_VALIDATION_FAIL_STOP
```

material/topology ranking unresolved due boundaries:

```text
STAGE3_8_BOUNDARY_LIMITED_STOP
```

いずれの場合も:

- Stage 3.9を自動開始しない
- hybridを自動開始しない
- impedance sweepへ戻らない

---

# 26. Philosophy

Stage 3.8の目的は、
5-IDTやParallel DMSで最大性能を出すことではない。

本当に確認したいのは、

> M0というhypothetical baselineと、
> MLITというliterature-derived baselineの両方で、
> 同じDMS topologyが有望に見えるか

である。

両materialで同じleaderが出れば、
そのtopologyをhybrid baselineへ進める根拠は強い。

順位が大きく変われば、
topology選択自体がmaterial-model-dependentであることが重要な知見となる。

96k程度のfast screenでこの情報を得ることを優先し、
高budget convergence studyはStage 3.9まで温存する。
