# Codex 作業指示書
## Stage 3.7B-R2 / Stage 3.7C — Literature COM B28 Fixed-Sensitivity + Lightweight Re-optimization

## 0. Mission

Stage 3.7B-R1では、literature-derived normalized COM profileについて以下を確認した。

- normalized COM mapping round-trip: PASS
- targeted tests: PASS
- full regression: PASS
- passivity / reciprocity: PASS
- native resonator dominant resonance:
  - source synchronous frequency `v/lambda ≈ 1.872685 GHz`
  - observed dominant resonance ≈ `1.814008 GHz`
  - COM couplingから予測されるlower stopband edge ≈ `1.816 GHz` と非常に近い
- alpha phase diagnostic ±π/2では≈1.931 GHz側へfeatureが移動し、upper edgeと整合
- native apertureは原典未記載
- absolute admittance / 50 Ω matchingのsource-device再現は未確認
- native 3-IDT DMSの完全再現は、polarity / reference-plane / geometry不足のため未確認

R1のレビュー結果として、

1. normalized literature COM profile自体は preliminary physical baselineとして使用可能性が高い。
2. `phase_sensitivity_robust=False` をproduction gateにするのは厳しすぎる。
3. 2024年表に掲載された negative real kappa / positive real alpha をprimary source conventionとして扱う。
4. alpha phase ±π/2はuncertainty diagnosticに降格する。
5. current antiresonance feature detectorには誤検出の疑いがある。
6. FEM extractionへ直行する必要はまだない。

本Stageでは、

- antiresonance診断修正
- native resonator再評価
- B28 current 50 Ω best designのfixed-geometry material sensitivity
- 問題がなければliterature COM profileによる8k × 2seed再最適化

まで進める。

---

# 1. Hard boundaries

本Stageでは以下を行わない。

- 5-IDT implementation
- parallel DMS
- pitch modulation
- shorted grating
- divided-center IDT
- ladder / hybrid optimization
- impedance sweep
- 32k / 64k escalation
- 5-seed confirmation
- continuous h/lambda optimization
- continuous duty optimization
- arbitrary COM coefficient fitting
- FEM extraction execution
- source-device absolute admittance calibration

本Stage終了後に必ず停止する。

---

# 2. Repository / source audit

開始時に以下を保存する。

- git branch
- git HEAD
- git status
- git diff summary
- Stage 3.7B-R1 source changes
- current literature COM provider implementation
- current antiresonance feature extractor
- current 50 Ω Stage 3.6 reference design
- current G1_G2 search-space snapshot
- current production L-SHADE implementation
- current validation-grid identity/hash

注意:

- pre-existing `docs/handoff` deletion等の無関係dirty stateを本Stageの変更に混ぜない。
- commit/pushは本Stageの目的ではない。
- Stage 3.6 / 3.7 artifactsを上書きしない。

---

# 3. Literature COM profile policy

primary profileはR1で作成したliterature-derived normalized profileを使用する。

profile label例:

```text
LI2024_42YX_LT_METAL_UNSPECIFIED_T25
```

必須metadata:

```text
substrate = 42°YX-LiTaO3
electrode_material = unspecified_metal
temperature_c = 25
h_over_lambda = source value (~0.08)
duty = source value (~0.65)
source_numeric = 2024 paper
normalization_definition = cited 2022 COM extraction paper
phase_policy = SIGNED_REAL_TABLE_ASSUMPTION
```

禁止表現:

- calibrated
- experimentally matched
- verified Al profile
- final physical model

推奨表現:

- literature-derived
- normalized-COM reconstructed
- signed-real source convention
- preliminary physical baseline

---

# 4. Phase / sign convention policy

本Stageでは、2024年のsource tableに掲載された符号をそのままprimary conventionとして採用する。

```text
kappa = negative real
alpha = positive real
```

R1で行ったalpha phase diagnostic `±pi/2` は残してよいが、

- production gatingに使わない
- optimization profileに使わない
- uncertainty diagnosticとしてのみreportする

phase sensitivityが大きいこと自体をFAIL条件にしない。

---

# 5. Fix antiresonance feature extraction

## 5.1 Problem

R1では、

```text
resonance ≈ 1.814008 GHz
antiresonance ≈ 1.814067 GHz
```

のように非常に近いfeatureが抽出されており、dominant resonatorとして不自然である。

保存済みresponseでは、より自然なantiresonance候補が約1.8786 GHz付近に存在する可能性がある。

## 5.2 New extraction rule

one-port resonatorについて、feature detectorを以下の考え方で修正する。

### Resonance candidate

- conductance `G = Re(Y)` のdominant local maximum
- または既存定義と整合するdominant resonance

### Antiresonance candidate

原則:

1. resonanceより高周波側
2. `|Y|` の局所最小候補
3. susceptance `B = Im(Y)` が近傍でzero-crossing
4. resonanceと同一点/隣接numerical sampleを選ばない
5. physically meaningful minimum separationを設ける

候補が複数ある場合は、

- dominant resonanceに対応する最初のstrong antiresonance
- `|Y|` minimum depth
- B zero-crossing proximity

を使って決定する。

保存:

- all G local maxima
- all |Y| local minima
- all B zero crossings
- selected resonance
- selected antiresonance
- selection reason
- frequency separation

既存COM physicsは変更しない。

---

# 6. Native resonator re-validation

R1と同じliterature native-condition reconstructionを再実行する。

原典値:

```text
lambda ≈ 2.16 um
h/lambda ≈ 0.08
duty ≈ 0.65
IDT ≈ 60 fingers
reflector ≈ 30 gratings/side
```

native aperture未記載の場合:

```text
W = 80 um
```

をevaluation apertureとして使用してよい。ただしsource-device apertureではないと明記する。

保存:

```text
f_sync = v / lambda
f_lower ≈ f_sync * (1 - |kappa_p|/(2*pi))
f_upper ≈ f_sync * (1 + |kappa_p|/(2*pi))
```

これらはsanity referenceであり厳密なacceptance criterionではない。

必須出力:

- selected resonance
- corrected antiresonance
- f_sync
- lower/upper coupling-edge references
- offset from nearest edge
- passivity
- reciprocity
- G peak
- |Y| minimum
- B zero-crossing
- alpha-phase diagnostic results

---

# 7. Native validation decision

### `NATIVE_RESONATOR_PASS`

- normalized round-trip PASS
- dominant featuresがphysically plausible
- resonance / antiresonance orderingが妥当
- no nonpassive response
- no arbitrary sign/fitting correction
- signed-real conventionでstable

### `NATIVE_RESONATOR_PROVISIONAL_PASS`

- frequency/mode structureは妥当
- absolute source-device comparisonは不完全
- aperture/polarity metadata不足

→ B28 fixed-design sensitivityへ進んでよい。

### `NATIVE_RESONATOR_FAIL`

- wrong frequency order
- severe mismatch unrelated to expected coupling
- nonpassive
- antiresonanceを物理的に識別できない
- arbitrary coefficient scaling required

→ B28へ進まずFEM branchをrecommendする。

---

# 8. Native DMS policy

native 3-IDT DMSの完全再現は本R2のGate条件にしない。

理由:

- IDT polarity
- exact terminal mapping
- acoustic reference plane
- missing geometry details

が不足している可能性があるため。

可能な場合のみexploratory partial reconstructionを行い、

- mode locations
- approximate S21 structure
- polarity assumptions
- missing geometry list

を保存する。

production acceptanceには使用しない。

---

# 9. Regression gate

feature detector変更後、必ず以下を実行する。

1. targeted antiresonance feature tests
2. normalization round-trip tests
3. literature provider tests
4. COM analytic-limit tests
5. network tests
6. passivity / reciprocity tests
7. full regression

保存:

- exact command
- passed
- failed
- skipped
- runtime

full regression失敗時はproduction experimentへ進まない。

---

# 10. Stage 3.7C-A — B28 fixed-design sensitivity

以下の場合のみ実行:

```text
native_status in {PASS, PROVISIONAL_PASS}
AND full_regression == PASS
```

## 10.1 Reference design

Stage 3.6 Gate 2B-Bの50/50 Ω representative best designを自動取得する。

- current production 3-IDT
- current production wiring
- G1_G2
- best validated 50/50 Ω geometry

手入力しない。

## 10.2 Compare two material profiles

### M0
current hypothetical COM baseline

### MLIT
literature-derived signed-real profile

geometryは完全に同一。

termination:

```text
Zin = 50 ohm
Zout = 50 ohm
```

validation gridも可能な限り同一。

## 10.3 Modeling note

MLITの `h/lambda` と `duty` はsource profile metadataとして保持する。

current solverでこれらがCOM係数以外に別作用しない場合は二重適用しない。

---

# 11. B28 fixed-design metrics

保存:

- max violation
- sum violation
- worst passband IL
- ripple
- input VSWR
- output VSWR
- each stopband attenuation
- active limiting constraint
- resonance / mode locations
- passivity / reciprocity
- response curve

metricごとに:

```text
delta = MLIT - M0
```

を計算する。

目的は優劣ではなくmaterial-model sensitivity。

---

# 12. Fixed-design sanity gate

### `B28_FIXED_PROFILE_STABLE`

- simulation completes normally
- passive / reciprocal
- B28 vicinityにmode structureあり
- finite response
- no catastrophic numerical behavior
- no unexplained frequency-scale collapse

性能がM0より悪くてもFAILではない。

→ 8k × 2seedへ進む。

### `B28_FIXED_PROFILE_UNSTABLE`

- nonphysical gain
- extreme numerical singularity
- unexplained large frequency displacement
- pathological response incompatible with source profile

→ optimizationを開始しない。FEM / convention auditへ戻る。

---

# 13. Stage 3.7C-B — Lightweight 50 Ω re-optimization

`B28_FIXED_PROFILE_STABLE`の場合のみ実行。

```text
topology = current 3-IDT DMS
wiring = current production wiring
Zin = 50 ohm
Zout = 50 ohm
search space = G1_G2
provider = MLIT
optimizer = production L-SHADE
cold start = true
warm start = false
bound expansion = false
DOF expansion = false
```

Budget:

```text
8,000 unique evaluations / seed
```

Seeds:

```text
20260917
20260918
```

Total nominal:

```text
16,000 unique evaluations
```

自動seed追加禁止。

---

# 14. Checkpoints

各seed:

```text
2k
4k
6k
8k
```

保存:

- best max violation
- best objective
- geometry
- active constraint
- feasible flag
- last meaningful improvement
- elapsed time

convergence claimは禁止。

---

# 15. Geometry comparison

MLIT optimized bestとStage 3.6 M0 50 Ω referenceを比較する。

## Absolute

- wavelength_um
- center_wavelength_um
- reflector_wavelength_um
- io_idt_pairs
- center_idt_pairs
- reflector_electrodes
- aperture_um
- idt_gap_lambda
- reflector_gap_lambda

## Normalized

- aperture / main wavelength
- center wavelength / main wavelength
- reflector wavelength / main wavelength
- io / center pair ratio
- reflector electrodes / side
- IDT gap / wavelength
- reflector gap / wavelength

---

# 16. Questions this experiment must answer

1. normalized literature COM profileはsolver内で安定しているか？
2. corrected native resonator featuresは物理的に妥当か？
3. M0とMLITでfixed B28 geometryのresponseはどの程度変わるか？
4. MLITでreoptimizationするとwavelengthはB28相当へ戻るか？
5. `io_idt_pairs=8` hard-bound pressureは残るか？
6. reflector countは増えるか？
7. aperture/lambdaはM0の≈20λから動くか？
8. IDT gap≈0.5λ傾向は残るか？
9. `stop_1` dominanceは維持されるか？
10. Stage 3.6のdesign directionはCOM profileを変えても概ねrobustか？
11. Stage 3.8 topology screeningにMLITを採用すべきか？
12. FEM extractionを今すぐ行う必要があるか？

---

# 17. Decision logic

### `MATERIAL_DIRECTION_ROBUST`

- wavelength / gap / IDT relationshipが同じorder
- geometry trendが大崩れしない
- `io_idt_pairs` pressureが残る
- dominant constraintが概ね同じ

→ Stage 3.6 design directionはmaterial model変更に対して概ねrobust。

### `MATERIAL_DIRECTION_SENSITIVE`

- io pair boundary behavior disappears
- reflector count changes strongly
- aperture/lambda changes materially
- dominant constraint changes
- M0とMLITでmode/design strategyが大きく異なる

→ Stage 3.6結果はM0-specific。
MLITがstableならStage 3.8ではMLITを新baselineとする。

### `LITERATURE_PROFILE_NOT_READY`

- native or B28 fixed response unstable
- convention ambiguity materially affects response
- numerical pathology persists

→ topology studyへ進まず `FEM_EXTRACTION_REQUIRED` をrecommend。

---

# 18. Stage 3.8 material baseline recommendation

最終summaryで以下のどれかを必ず選ぶ。

### `USE_MLIT_AS_PRIMARY`

MLITをStage 3.8 primary material baselineにする。

### `USE_M0_AND_MLIT_AS_DUAL_BASELINE`

profile uncertaintyが大きいため、3-IDT / 5-IDT / Parallel-DMS fast screenをM0とMLITで小規模比較する。

### `FEM_BEFORE_STAGE3_8`

literature profile uncertaintyがtopology rankingを支配するため、FEM extractionを先行。

---

# 19. Required outputs

## Data

- `native_resonator_corrected_features.csv`
- `native_resonator_phase_diagnostics.csv`
- `b28_fixed_design_material_comparison.csv`
- `b28_literature_com_seed_results.csv`
- `b28_literature_com_geometry_comparison.csv`
- `b28_literature_com_convergence_lite.csv`
- `constraint_bottleneck_comparison.csv`

## Metadata

- numerical-source citation
- normalization-definition citation
- literature profile snapshot
- M0 profile snapshot
- Stage 3.6 reference design snapshot
- G1_G2 search-space snapshot
- validation grid identity/hash
- git head / branch / status
- git diff summary
- exact test output

## Markdown

- `stage3_7b_r2_native_feature_correction.md`
- `stage3_7c_b28_literature_com_summary.md`
- `test_summary.md`

## Plots

minimum:

1. corrected native resonator G / B / |Y|
2. native feature-location plot with sync/lower/upper references
3. B28 fixed-design M0 vs MLIT response
4. MLIT 8k seed comparison
5. M0-reference vs MLIT-optimized normalized geometry comparison

---

# 20. Reporting cautions

Do not claim:

- material calibration
- experimental validation
- real-device prediction accuracy
- global optimum
- converged 50 Ω design
- final B28 performance

Use:

- preliminary
- literature-derived
- model-dependent
- fast screening
- directional evidence

---

# 21. Repository hygiene

本Stage終了時に、

- Stage 3.7B/R2/C related modified files
- pre-existing unrelated deleted files
- generated artifacts
- untracked handoff docs

を分類してreportする。

commit / pushはしない。

特にpre-existing `docs/handoff`大量削除をStage 3.7変更へ混ぜない。

---

# 22. Final hard stop

成功時:

```text
STAGE3_7C_LITERATURE_COM_B28_FAST_SCREEN_COMPLETE_STOP
```

native/B28 profile failure時:

```text
STAGE3_7C_LITERATURE_COM_VALIDATION_FAIL_STOP
```

FEMが必要と判断した場合:

```text
STAGE3_7C_FEM_EXTRACTION_RECOMMENDED_STOP
```

いずれの場合もStage 3.8を自動開始しない。

---

# 23. Philosophy

本Stageの目的はliterature COM profileで最高性能を出すことではない。

重要なのは、

> material/COM modelをM0からliterature-derived profileへ変えたとき、
> これまで見えていた3-IDT設計方向が維持されるのか、
> それとも設計戦略自体が変わるのか

を少ない計算量で判定することである。

8k × 2seedはconvergence testではない。

結果が曖昧でも、Stage 3.8のtopology選択を直接妨げない限り高budget confirmationへ進まず、次の構造探索へ移ることを優先する。
