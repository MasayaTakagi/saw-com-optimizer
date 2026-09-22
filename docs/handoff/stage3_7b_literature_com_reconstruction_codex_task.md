# Codex 作業指示書
## Stage 3.7B — Literature COM Convention Reconstruction & Source-Device Validation

## 0. Mission

Stage 3.7Aでは、42°YX-LiTaO3 / Al系の文献COM profileをproduction simulationへ直接投入できるだけの
「solver conventionとの互換性確認済みCOM set」を確保できず、`COM_MAPPING_BLOCKED` 相当で停止した。

本Stageでは、文献に掲載されているnormalized COM parametersを
現在のsolver conventionへ安全に変換できるかを検証する。

本Stageの目的は、

1. 文献のnormalized COM parameter definitionsを現在solverの
   `v, kappa, alpha, C, loss`
   へ厳密にマッピングする。
2. 変換したCOM値で、文献元のresonator / 3-IDT DMSに相当するsource-deviceを再現する。
3. source-device再現が妥当な場合のみ、B28スケールへprofileを持ち込み、
   50 Ω・3-IDTで軽量re-optimizationを行う。
4. source-device再現が不十分なら、数値を調整して無理に合わせず、
   FEM-based COM extractionへ分岐する。

本Stageでは5-IDT、parallel DMS、hybrid、impedance sweepへ進まない。

---

# 1. Source of truth / repository audit

開始時に以下を記録する。

- git branch
- git HEAD
- git status
- current COM solver implementation
- current COM sign / phasor convention
- current provider implementations
- current COM config schema
- current Stage 3.7A artifacts / summary
- current B28 3-IDT baseline config
- current validation / passivity / reciprocity tests

Stage 3.6 / Stage 3.7Aの成果物を改変しない。

---

# 2. Literature source lock

今回のprimary sourceを1つに固定する。

対象:

- 42°YX-LiTaO3
- Al electrode
- literature source with normalized COM parameters
- approximately:
  - h/lambda ≈ 0.08
  - metallization ratio ≈ 0.65
  - room temperature / 25 °C
- same source must provide:
  - velocity
  - normalized coupling / kappa
  - normalized transduction / alpha
  - normalized capacitance
  - normalized attenuation/loss

Stage 3.7Aで見つかった2024年の42°YX-LT COM extraction paperをprimary candidateとする。

異なる論文から値を混成しない。

---

# 3. Literature values to record

文献表から以下を正確に転記する。

最低限:

- substrate / cut
- electrode material
- h
- lambda
- h/lambda
- metallization ratio / duty
- temperature
- `v`
- `kappa_p`
- `alpha_n`
- `C_n`
- `gamma_p`
- parameter units
- table / equation number
- DOI / bibliographic metadata

primary candidateの例として想定される値:

```text
v ≈ 4045 m/s
kappa_p ≈ -18.96 %
alpha_n ≈ 92.566e-5 Ohm^(-1/2)
C_n ≈ 52.80e-5 pF/um
gamma_p ≈ 0.002684
```

ただし、実装時には必ず原典の表・定義を再確認し、
この指示書の値を無条件にsource of truthにしないこと。

---

# 4. Current solver convention

現在solverのCOM equationsを明文化する。

```text
dR/dx = -jδ R + jκ S + jα V
dS/dx = -jκ* R + jδ S - jα* V
dI/dx = -2jα* R - 2jα S + jω C V
```

with:

```text
δ = ω/v - 2π/λ - jγ
```

current internal units:

- v: m/s
- kappa: 1/m
- alpha: sqrt(S)/m
- C: F/m
- gamma/loss: 1/m

phasor / power normalization / current directionも既存実装から記録する。

---

# 5. Literature normalization mapping

primary literatureのnormalized definitionsを原典から確認する。

想定される形式:

```text
kappa_p = kappa * lambda
alpha_p = alpha * lambda
alpha_n = alpha_p / sqrt(W/lambda)
C_n = C * lambda / W
gamma_p = gamma * lambda
```

この定義が原典と一致することを確認する。

原典と一致した場合、current solverへ以下の変換を実装する。

## 5.1 kappa

```text
kappa = kappa_p / lambda
```

percent表記ならfractionへ変換する。

例:

```text
-18.96 % -> -0.1896
```

符号を消さない。

## 5.2 alpha

```text
alpha_p = alpha_n * sqrt(W/lambda)
alpha   = alpha_p / lambda
```

unitsを必ず追跡する。

文献の`alpha_n`がOhm^(-1/2)系の場合、
solverの`sqrt(S)/m`と等価かを単位解析で確認する。

## 5.3 capacitance

```text
C = C_n * W / lambda
```

ただし文献の`C_n` unitが
`pF/um`、`pF/mm`、dimensionless scaling等のどれかを原典で確認する。

SIへの変換過程を明記する。

## 5.4 attenuation

```text
gamma = gamma_p / lambda
```

current configの`loss_db_per_lambda`へ保存する場合は、

```text
loss_db_per_lambda = gamma * lambda * 20 / ln(10)
                   = gamma_p * 20 / ln(10)
```

を使用する。

amplitude attenuation conventionであることを確認する。

---

# 6. Conversion audit output

以下を作成する。

`com_conversion_audit.md`

必須内容:

- source equations
- source normalization definitions
- current solver equations
- variable-by-variable mapping
- unit derivation
- sign convention
- complex / real treatment
- remaining ambiguity
- confidence level

各parameterに対して:

- `CONFIRMED`
- `PROVISIONAL`
- `BLOCKED`

のstatusを付ける。

1つでもcritical parameterが`BLOCKED`ならproductionへ進まない。

---

# 7. Implement literature-profile adapter

新規providerまたは変換utilityを追加する。

推奨:

```text
NormalizedLiteratureCOMProfile
```

or

```text
LiteratureCOMProvider
```

profileにはnormalized source valuesを保存し、
geometry wavelength / apertureからphysical COM valuesへ変換する。

重要:

- raw literature normalized valuesを保存する
- derived physical valuesをruntimeで生成する
- h/lambdaとdutyはprofile metadataとして固定
- arbitrary interpolation禁止
- M0 FixedProviderは変更しない

---

# 8. Native-condition unit tests

literature native conditionで変換結果をtestする。

例:

```text
lambda ≈ 2.16 um
h ≈ 0.1728 um
h/lambda = 0.08
duty = 0.65
T = 25 C
```

代表apertureを文献デバイスから取得して使用する。

最低限:

1. `kappa * lambda == source kappa_p`
2. reverse-normalized alpha reproduces source alpha_n
3. reverse-normalized C reproduces source C_n
4. `gamma * lambda == source gamma_p`
5. finite values
6. expected signs
7. passivity/reciprocity
8. no NaN/Inf
9. profile metadata is immutable

---

# 9. Source resonator reconstruction

## 9.1 Goal

optimizerを使用せず、
文献元のone-port or equivalent resonator geometryを再構築する。

文献に記載された:

- wavelength
- IDT finger/pair count
- reflector finger count
- aperture
- gap
- metallization ratio
- thickness

を可能な限りそのまま使用する。

例として文献に

- IDT ≈ 60 fingers
- reflector ≈ 30 fingers / side

等が記載されている場合は原典値を使う。

## 9.2 Required evaluation

frequency rangeは文献中心周波数を十分含む。

保存:

- admittance
- conductance
- susceptance
- resonance frequency
- antiresonance frequency if meaningful
- reflection / transmission if applicable
- passivity diagnostics

## 9.3 Sanity criteria

最低限:

- dominant resonance near `v/lambda` order
- no nonphysical gain
- no numerical singularities
- resonance structure qualitatively consistent with literature
- frequency offset is documented

exact curve matchingは要求しない。

---

# 10. Source 3-IDT DMS reconstruction

source paperに3-IDT DMS exampleがある場合、可能な範囲で再構築する。

文献geometryが完全でない場合:

- missing dimensionsを推測してproduction validationに使わない
- available dimensionsだけでpartial reconstruction
- missing fieldsを明示

保存:

- S21 / IL
- S11 / S22
- mode / resonance locations
- passivity / reciprocity
- comparison against published plot / reported characteristic

目的はabsolute dB agreementではなく、

- mode count
- mode ordering
- approximate frequency placement
- qualitative passband structure

の整合を見る。

---

# 11. Source-device validation decision

## `SOURCE_RECONSTRUCTION_PASS`

以下を概ね満たす場合:

- conversion identities pass
- resonator resonance appears at correct frequency order
- DMS mode structure is qualitatively plausible
- passivity / reciprocity pass
- no convention contradiction
- no arbitrary fitting was required

→ B28 scalingへ進む。

## `SOURCE_RECONSTRUCTION_INCONCLUSIVE`

- frequency scale is reasonable
- but published structure lacks enough geometry
- magnitude differs materially
- convention still has small ambiguity

→ B28 optimizationを開始しない。
FEM extractionまたは追加文献確認へ分岐。

## `SOURCE_RECONSTRUCTION_FAIL`

- wrong resonance ordering
- severe frequency mismatch
- nonpassive behavior
- required sign flipping / arbitrary scaling to fit
- alpha/C normalization inconsistent

→ implementation tuningで無理に合わせない。

`STAGE3_7B_SOURCE_RECONSTRUCTION_FAIL_STOP`

で停止する。

---

# 12. B28-scale profile creation

`SOURCE_RECONSTRUCTION_PASS`の場合のみ実施。

同じnormalized COM profileをB28 scaleへ適用する。

重要:

- normalized COM valuesを維持
- B28 wavelength / apertureに応じてphysical kappa/alpha/C/gammaを再計算
- h/lambda = source profile value
- duty = source profile value
- current M0の0.04/0.50へ戻さない

target wavelengthはoptimizer search spaceへ委ねるが、
initial sanityとして:

```text
lambda ~ v / 780 MHz
```

がcurrent wavelength domainと整合することを確認する。

---

# 13. Fixed-design B28 sensitivity

Stage 3.6 current 50 Ω best geometryを
literature profileでそのまま評価する。

ただしmaterial profileに合わせて

- h/lambda
- metallization ratio

はprofile側metadataとして扱う。

geometry dimensionsは固定する。

比較:

- M0 response
- literature-profile response

保存:

- max violation
- worst IL
- ripple
- VSWR
- each stopband
- active constraint
- resonance / mode locations

---

# 14. Lightweight B28 re-optimization

source reconstructionがPASSした場合のみ実施。

## Conditions

- topology: current 3-IDT DMS
- wiring: current production wiring
- Zin = 50 Ω
- Zout = 50 Ω
- search space: current `G1_G2`
- provider: literature profile
- optimizer: production L-SHADE
- cold starts
- warm start disabled
- no bound expansion
- no DOF release

## Budget

```text
8,000 unique evaluations / seed
```

## Seeds

```text
20260917
20260918
```

Total:

```text
16k evaluations
```

今回はM0の再計算を必須にしない。
既存Stage 3.6 M0 referenceと比較してよい。

必要なら公平性確認用にM0を同budgetで2seed追加できるが、
自動実行禁止。
summaryで必要性だけ判断する。

---

# 15. B28 result analysis

比較する項目:

- wavelength
- center wavelength
- reflector wavelength
- io_idt_pairs
- center_idt_pairs
- reflector_electrodes
- aperture
- aperture/lambda
- IDT gap/lambda
- reflector gap/lambda
- max violation
- worst IL
- ripple
- VSWR
- stopband limiting constraint

特に確認:

1. `io_idt_pairs=8` hard-bound pressureが残るか
2. reflector countがM0より増えるか
3. aperture/lambdaが~20から文献寄りへ移動するか
4. stop_1 dominanceが変わるか
5. wavelength remains B28-consistent

---

# 16. Decision labels

## `LITERATURE_COM_USABLE_FOR_TOPOLOGY_SCREEN`

- source reconstruction PASS
- B28 scaled solver stable
- 2-seed reoptimization produces physically plausible designs
- no convention ambiguity that changes ranking

→ Stage 3.8でこのprofileをmaterial baselineとして使用する。

## `LITERATURE_COM_PHYSICALLY_PLAUSIBLE_BUT_UNCERTAIN`

- source resonator is plausible
- but DMS reconstruction incomplete
- B28 response stable
- absolute performance uncertain

→ topology fast screeningへの使用は可能だが、
results must be labeled model-dependent.

## `FEM_EXTRACTION_REQUIRED`

- source reconstruction cannot validate alpha/C/kappa convention
- critical literature geometry missing
- magnitude behavior materially inconsistent

→ 次StageをFEM COM extractionとする。

---

# 17. FEM branch definition

FEMが必要になった場合、本StageではFEMそのものを実行しない。

代わりに次の作業計画をsummaryへ記載する。

抽出対象:

- short-circuit periodic dispersion
- stopband edges
- open/short velocity
- static capacitance
- harmonic admittance
- resonance Q / loss
- kappa_p
- alpha_n
- C_n
- gamma_p
- v

候補ツール:

- COMSOL
- FEM package already available locally
- equivalent validated eigenmode / harmonic solver

必要geometry:

- 42°YX-LiTaO3
- Al
- candidate h/lambda
- candidate duty
- B28-scale lambda

---

# 18. Required outputs

## Data

- `literature_source_values.csv`
- `normalized_to_solver_conversion.csv`
- `native_resonator_results.csv`
- `native_dms_results.csv` if applicable
- `b28_fixed_design_sensitivity.csv` if source reconstruction passes
- `b28_reoptimization_results.csv` if executed
- `b28_geometry_comparison.csv` if executed

## Config / metadata

- literature profile YAML/JSON
- exact source citation metadata
- solver convention snapshot
- current git head / branch / status
- test command/results

## Markdown

- `com_conversion_audit.md`
- `source_device_reconstruction.md`
- `stage3_7b_literature_com_reconstruction_summary.md`
- `test_summary.md`

## Plots

minimum:

1. native resonator response
2. native DMS response if reconstructable
3. published-vs-simulated mode/frequency comparison
4. B28 M0 vs literature-profile fixed-design response if executed
5. B28 reoptimized geometry comparison if executed

---

# 19. Final summary requirements

`stage3_7b_literature_com_reconstruction_summary.md` must include:

1. source paper
2. exact normalized COM values used
3. exact normalization definitions
4. mapping equations
5. mapping confidence per parameter
6. native-condition converted values
7. resonator reconstruction result
8. DMS reconstruction result
9. passivity/reciprocity result
10. whether arbitrary fitting was required
11. source reconstruction status
12. whether B28 scaling was executed
13. B28 fixed-design result
14. B28 8k×2seed result
15. change from M0 geometry
16. recommendation:
   - use literature COM for Stage 3.8
   - use with caution
   - FEM extraction required
17. unresolved uncertainties

禁止表現:

- calibrated
- experimentally matched
- validated material model

unless actual experimental calibration was performed.

Use:

- literature-derived
- source-reconstructed
- convention-checked
- preliminary physical baseline

---

# 20. Hard stop

以下を開始してはならない。

- 5-IDT implementation
- parallel DMS
- pitch modulation
- shorted grating
- hybrid DMS + ladder
- impedance sweep
- 32k/64k optimization
- 5-seed confirmation
- continuous thickness optimization
- continuous duty optimization
- arbitrary COM fitting
- FEM extraction execution

Success stop:

`STAGE3_7B_LITERATURE_COM_RECONSTRUCTION_COMPLETE_STOP`

Source reconstruction failure:

`STAGE3_7B_SOURCE_RECONSTRUCTION_FAIL_STOP`

Mapping blocked:

`STAGE3_7B_COM_MAPPING_BLOCKED_STOP`

---

# 21. Philosophy

今回の目的は、文献表の数値を無理にsolverへ入れることではない。

成功条件は、

> 文献のnormalized COM定義と現在solverのCOM conventionを、
> 数式・単位・符号の3点で説明可能な形で接続し、
> source-deviceの挙動が物理的に妥当であることを確認すること。

source-deviceを再現できないprofileをB28 optimizationへ使用してはならない。

一方で、absolute responseの完全一致も要求しない。

まずは少ない計算量で、
「このliterature-derived COM profileをtopology screeningの物理baselineとして使えるか」
を判断する。
