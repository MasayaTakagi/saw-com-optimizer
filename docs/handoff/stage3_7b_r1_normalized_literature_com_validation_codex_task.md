# Codex 作業指示書
## Stage 3.7B-R1 — Normalized Literature COM Reconstruction

## 0. Mission

Stage 3.7Bでは、文献COM profileの数値そのものは取得できたが、

- native device aperture未記載
- electrode materialの明示不足
- normalized COM定義とcurrent solver conventionの接続確認不足
- native DMS polarity / reference-plane情報不足

を理由に `COM_MAPPING_BLOCKED` として停止した。

その停止判断は安全側として正しかったが、本R1では判定を整理し直す。

本Stageの目的は、

1. 2024年文献のnormalized COM数値を、同系列の2022年COM extraction論文で定義されたnormalization conventionを使ってcurrent solverへ接続する。
2. native resonatorについて、絶対admittance再現ではなく **resonance / mode frequency structure** を主目的に検証する。
3. passivity / reciprocity / unit round-tripを確認する。
4. native resonator reconstructionが妥当な場合のみ、B28 current 50 Ω reference designのfixed-geometry sensitivityを評価する。
5. それでも物理的整合性が取れない場合のみ `FEM_EXTRACTION_REQUIRED` とする。

本StageではB28 re-optimizationをまだ必須としない。
まず「このliterature-derived COM profileを使えるか」の判定を優先する。

---

# 1. Repository audit

開始時に以下を記録する。

- git branch
- git HEAD
- git status
- Stage 3.7Bで追加・変更されたsource files
- uncommitted diff summary
- current targeted test status
- existing full regression command
- Stage 3.7B artifacts
- current M0 provider/config
- current 50 Ω Stage 3.6 reference design

注意:

- 既存の `docs/handoff` 等の無関係なdirty changesを本Stageのcommit対象へ混ぜない。
- Stage 3.6 / 3.7A / 3.7B結果を上書きしない。

---

# 2. Literature reference chain

## 2.1 Numerical source

2024年の42°YX-LiTaO3 COM parameter extraction / temperature-dependent COM paperを
**numerical source** とする。

25 °Cの代表profileとして、原典から以下を再確認して転記する。

想定値:

```text
v ≈ 4045 m/s
kappa_p ≈ -18.96 %
alpha_n ≈ 92.566e-5 Ohm^(-1/2)
C_n ≈ 52.80e-5 [source-defined unit]
gamma_p ≈ 0.002684
h/lambda ≈ 0.08
metallization ratio ≈ 0.65
```

ただし、必ず原典表をsource of truthとする。

## 2.2 Definition source

2022年の "Full extraction of the COM parameters for Rayleigh type SAW" 系論文を
**normalization-definition source** とする。

この使い分けをsummaryに明記する。

禁止:

- 数値パラメータを2022年論文から混ぜる
- 2024年数値profileをAlと断定する
- reference chainを「same paper」と表現する

---

# 3. Profile naming

electrode materialが2024年原典で明示確認できない場合、
profile名に `Al` を含めない。

推奨:

```text
LI2024_42YX_LT_METAL_UNSPECIFIED_T25
```

metadataには、

- substrate = 42°YX-LiTaO3
- electrode_material = unspecified_metal
- h_over_lambda = source value
- duty = source value
- temperature_c = 25

を記録する。

---

# 4. Current solver convention

current solver equationsをsnapshotとして保存する。

```text
dR/dx = -jδ R + jκ S + jα V
dS/dx = -jκ* R + jδ S - jα* V
dI/dx = -2jα* R - 2jα S + jω C V
```

```text
δ = ω/v - 2π/λ - jγ
```

internal units:

- v: m/s
- kappa: 1/m
- alpha: sqrt(S)/m
- C: F/m
- gamma: 1/m

以下も記録する。

- phasor convention
- acoustic power normalization
- current sign convention
- voltage convention
- reciprocity convention

---

# 5. Normalized COM mapping

2022年definition sourceから以下を確認する。

```text
kappa_p = kappa * lambda

alpha_p = alpha * lambda

alpha_n = alpha_p / sqrt(W / lambda)

C_n = C * lambda / W

gamma_p = gamma * lambda
```

原典と一致した場合のみ以下を採用する。

## 5.1 kappa

```text
kappa = kappa_p / lambda
```

percent表記の場合:

```text
-18.96 % -> -0.1896
```

符号を保持する。

## 5.2 alpha

```text
alpha = alpha_n * sqrt(W/lambda) / lambda
```

`Ohm^(-1/2)` と solver `sqrt(S)` の同値性を明示する。

## 5.3 capacitance

```text
C = C_n * W / lambda
```

ただしC_nのsource unitを必ずSIへ変換してから使う。

## 5.4 attenuation

```text
gamma = gamma_p / lambda
```

current M0形式へ変換する場合:

```text
loss_db_per_lambda = gamma_p * 20 / ln(10)
```

amplitude attenuation conventionであることを確認する。

---

# 6. Critical policy change from Stage 3.7B

**native device apertureが不明でもCOM mapping自体をBLOCKしない。**

理由:

- alpha scales as sqrt(W)
- C scales as W
- normalized profile can be instantiated for any explicit evaluation aperture
- resonance/mode frequency validation can be performed without claiming absolute-admittance reproduction

ただし、

- absolute admittance magnitude
- impedance matching
- source-device absolute conductance

についてはnative aperture不明のため validation scope外とする。

---

# 7. Provider implementation

Stage 3.7Bで追加したproviderを必要最小限修正する。

推奨interface:

```text
NormalizedLiteratureCOMProfile
```

or existing equivalent.

provider inputs:

- wavelength_um
- aperture_um
- fixed normalized source values

provider outputs:

- velocity
- kappa
- alpha
- capacitance
- loss

Requirements:

1. normalized values are immutable source data
2. geometry-dependent dimensional conversion is explicit
3. no arbitrary fitting factor
4. no hidden sign flip
5. no thickness/duty interpolation
6. M0 behavior unchanged

---

# 8. Round-trip normalization tests

explicit test geometryを設定する。

例:

```text
lambda = 2.16 um
W = 80 um
```

W=80 µmは**source device apertureを意味しない**。
unit / normalization verification用のexplicit test apertureとする。

確認:

```text
(kappa * lambda) == kappa_p
```

```text
(alpha * lambda) / sqrt(W/lambda) == alpha_n
```

```text
C * lambda / W == C_n
```

```text
gamma * lambda == gamma_p
```

strict numerical toleranceでround-trip testを追加する。

---

# 9. Native resonator reconstruction

## 9.1 Geometry

2024年原典に記載されたnative resonator geometryを使用する。

確認可能な値を原典から記録する。

想定:

- lambda ≈ 2.16 um
- h ≈ 0.1728 um
- h/lambda = 0.08
- duty ≈ 0.65
- IDT ≈ 60 fingers
- reflector ≈ 30 gratings / side

finger count / pair countの解釈を明記する。

native apertureは不明なら任意の明示値を使う。

推奨:

```text
W = 80 um
```

ただしsummaryには

```text
evaluation aperture, not reported source aperture
```

と必ず記載する。

## 9.2 Frequency range

center estimate:

```text
f0 ≈ v / lambda
```

を含む十分広いrangeを評価する。

例:

```text
0.8*f0 to 1.2*f0
```

または文献plot rangeに合わせる。

## 9.3 Primary validation targets

absolute admittance magnitudeではなく以下を主評価とする。

- resonance frequency
- antiresonance frequency if identifiable
- stopband / coupling feature locations
- mode ordering
- number of dominant features
- qualitative shape
- passivity
- reciprocity

---

# 10. Resonator validation status

## `RESONATOR_FREQ_PASS`

以下を概ね満たす場合:

- dominant resonance lies near expected `v/lambda` scale
- resonance / antiresonance ordering is physically plausible
- no nonpassive response
- no arbitrary scaling/sign adjustment required
- feature positions qualitatively match published plot/report

absolute magnitude mismatchはPASSを妨げない。

## `RESONATOR_FREQ_INCONCLUSIVE`

- frequency scaleは妥当
- feature structureは概ね妥当
- but published detail不足で直接比較困難

→ B28 fixed-design sensitivityへ進んでもよいが、
profile statusを `PHYSICALLY_PLAUSIBLE_BUT_UNCERTAIN` とする。

## `RESONATOR_FREQ_FAIL`

- frequency structureが大きく異なる
- nonpassive
- feature ordering不自然
- sign flip / arbitrary coefficient correctionが必要

→ B28へ進まない。

---

# 11. Native DMS policy

native 3-IDT DMSの完全再現は本R1のGate条件にしない。

理由:

- IDT polarity
- exact terminal mapping
- acoustic reference plane
- missing geometry details

が不十分な可能性があるため。

可能な場合のみ **exploratory partial reconstruction** を行う。

保存:

- mode locations
- approximate S21 structure
- polarity assumptions
- missing geometry list

結果はproduction acceptance判定に使用しない。

---

# 12. Full regression before physics conclusion

Stage 3.7Bでsource codeに変更が入っているため、
本R1終了前にfull regressionを実行する。

必須:

- targeted COM/profile tests
- existing COM analytic tests
- network tests
- passivity / reciprocity tests
- full repository regression

以下を保存:

- command
- passed count
- failed count
- skipped count
- runtime
- failure details

full regression failure時はB28 sensitivityへ進まない。

---

# 13. B28 fixed-design sensitivity

以下を満たした場合のみ実行する。

- round-trip mapping PASS
- resonator status = PASS or INCONCLUSIVE
- full regression PASS

## 13.1 Reference geometry

Stage 3.6 Gate 2B-Bの50/50 Ω代表best designを使用する。

geometryを再最適化しない。

## 13.2 Material profile

literature normalized profileを使用する。

profile metadata:

- h/lambda = source profile value
- duty = source profile value
- electrode material = unspecified if not confirmed

## 13.3 Conditions

- current 3-IDT topology
- current production wiring
- Zin = 50 Ω
- Zout = 50 Ω
- same common validation grid where applicable

## 13.4 Compare

M0 vs literature-derived profileについて:

- max violation
- worst IL
- ripple
- input VSWR
- output VSWR
- stop_1
- stop_2
- active limiting constraint
- resonance/mode locations

を比較する。

---

# 14. Optional 8k re-optimization decision

本R1では8k optimizationを**自動実行しない**。

B28 fixed-design sensitivityの結果を見て、
summaryで次のどちらかを判定する。

### `GO_STAGE3_7C_8K_REOPT`

literature profileでresponseが物理的に安定し、
geometry re-optimizationに進む価値がある。

### `NO_REOPT_FEM_REQUIRED`

fixed-design response自体が不自然、
またはCOM mapping ambiguityが性能解釈に大きく影響する。

この場合FEM extractionへ分岐。

---

# 15. FEM trigger

以下の場合のみFEM extractionを推奨する。

- normalized mapping identities fail
- resonator frequency structure fails
- passivity / reciprocity fails
- alpha/C convention remains materially ambiguous
- literature profile produces nonphysical B28 response
- arbitrary fit factors are required

FEM executionそのものは本Stageでは行わない。

---

# 16. Required outputs

## Data

- `normalized_com_source_values.csv`
- `normalization_roundtrip_tests.csv`
- `native_resonator_results.csv`
- `native_resonator_features.csv`
- `native_dms_partial_results.csv` if attempted
- `b28_fixed_design_sensitivity.csv` if executed

## Metadata

- exact numerical source citation
- exact definition source citation
- profile JSON/YAML
- solver convention snapshot
- git head / branch / status
- git diff summary
- targeted test result
- full regression result

## Markdown

- `stage3_7b_r1_mapping_notes.md`
- `stage3_7b_r1_native_resonator_validation.md`
- `stage3_7b_r1_summary.md`
- `test_summary.md`

## Plots

minimum:

1. native resonator admittance / conductance / susceptance
2. native resonator feature-frequency plot
3. literature vs simulation feature-location comparison
4. M0 vs literature-profile B28 fixed-design response if executed

---

# 17. Final decision labels

最終summaryでは以下のどれかを明示する。

### `LITERATURE_COM_MAPPING_PASS`

normalized COM mappingはcurrent solverと整合。

### `LITERATURE_COM_USABLE_PRELIMINARY`

mapping + native resonator + B28 fixed-designが概ね妥当。
Stage 3.7Cへ進める。

### `LITERATURE_COM_PHYSICALLY_PLAUSIBLE_BUT_UNCERTAIN`

周波数構造は妥当だがabsolute device reconstructionは未検証。
preliminary topology studyには使用可能。

### `FEM_EXTRACTION_REQUIRED`

literature profileだけでは物理解釈に必要な確度を得られない。

---

# 18. Hard stop

以下を開始してはならない。

- 8k optimization unless separately instructed after review
- 5-IDT
- parallel DMS
- hybrid
- ladder
- impedance sweep
- 32k / 64k
- 5 seeds
- arbitrary COM coefficient fitting
- FEM execution

終了時:

成功:

```text
STAGE3_7B_R1_NORMALIZED_COM_VALIDATION_COMPLETE_STOP
```

失敗:

```text
STAGE3_7B_R1_VALIDATION_FAIL_STOP
```

---

# 19. Philosophy

本Stageでは、source deviceの完全再現を要求しない。

まず確認すべきなのは、

> normalized COM parameter setをcurrent solverへ数式・単位・符号の整合した形で接続できるか、
> そしてそのprofileが正しい周波数スケールと物理的mode structureを生成するか

である。

native apertureが不明だからといってnormalized COM mapping全体をBLOCKしない。

一方で、absolute admittanceや50 Ω matchingの一致を
native device validationとして主張してはならない。

このR1でliterature profileの物理的妥当性が十分確認できれば、
次StageでB28 50 Ωの8k×2seed re-optimizationへ進む。
