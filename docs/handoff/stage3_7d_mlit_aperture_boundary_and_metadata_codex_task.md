# Codex 作業指示書
## Stage 3.7D — MLIT Aperture Boundary Probe & Material Metadata Cleanup

## 0. Mission

Stage 3.7Cのfast screenで、literature-derived COM profile（以下MLIT）を用いた
50 Ω・3-IDT・8k×2seed再最適化を実施した。

主要結果:

- MLIT fixed geometry:
  - max violation ≈ 82
  - current M0 geometryはMLITに対して強く不整合
- MLIT re-optimization:
  - seed 20260917: max violation ≈ 1.076
  - seed 20260918: max violation ≈ 1.129
- 両seedで主要geometryはかなり一致
- 一方で aperture ≈ 148.4 µm と、
  current upper bound 150 µmへほぼ張り付いた
- reflector countはseed間でまだ不安定
- 8k時点でも両seedとも最終盤まで改善中であり、未収束
- material directionはM0とMLITで明確に異なる
- MLITはpreliminary physical baselineとしてStage 3.8へ持ち込める可能性が高い

本Stageの目的は2つだけ。

1. MLITのaperture upper bound = 150 µmが人工的に設計を制限していないか、
   数点のforward evaluationだけで確認する。
2. MLIT使用時のreport / result metadataに、
   effective material profileの
   - h/lambda
   - duty / metallization ratio
   を明示し、
   `FilterDesign`上のlegacy値と混同されないよう修正する。

本Stageではoptimizerを再実行しない。

---

# 1. Hard boundaries

以下は禁止。

- 8k/16k/32k optimization再実行
- seed追加
- G1_G2以外へのDOF expansion
- io pair bound変更
- reflector bound変更
- wavelength bound変更
- 5-IDT implementation
- parallel DMS
- hybrid / ladder
- impedance sweep
- FEM
- COM coefficient tuning
- material profile interpolation
- h/lambda continuous optimization
- duty continuous optimization

本Stageはforward-evaluation + metadata cleanupのみ。

---

# 2. Repository audit

開始時に保存:

- git branch
- git HEAD
- git status
- git diff summary
- Stage 3.7C result bundle location
- MLIT provider/config
- Stage 3.7C best designs for both seeds
- current G1_G2 aperture bounds
- current physical/layout width constraints
- current result/report schema

pre-existing unrelated dirty changesを混ぜない。

---

# 3. Reference designs

Stage 3.7C MLIT 8k結果から、
両seedのbest geometryをそのまま読み込む。

最低限:

```text
seed 20260917
seed 20260918
```

について保存:

- wavelength_um
- center_wavelength_um
- reflector_wavelength_um
- io_idt_pairs
- center_idt_pairs
- reflector_electrodes
- aperture_um
- idt_gap_lambda
- reflector_gap_lambda
- max violation
- active constraint
- validation-grid identity

手入力禁止。

---

# 4. Aperture boundary probe

## 4.1 Purpose

current MLIT bestでは:

```text
aperture ≈ 148.4 um
upper bound = 150 um
```

であり、search-space upper boundへの圧力が疑われる。

このStageでは、
他のgeometryを完全固定し、
apertureだけを外向きへ変更する。

## 4.2 Probe values

各seedのbest geometryについて:

```text
A0 = original optimized aperture
A1 = 150 um
A2 = 165 um
A3 = 180 um
A4 = 200 um
```

を評価する。

必要に応じてphysical/layout hard constraintに抵触する値は、
「not physically admissible」として評価せず記録する。

200 µmが明確にlayout hard limitを超える場合は、
hard limit以下の最大値へ置換してよい。

## 4.3 Fixed conditions

- topology: current 3-IDT
- wiring: current production wiring
- Zin = 50 Ω
- Zout = 50 Ω
- provider = MLIT
- all geometry except aperture fixed
- same validation grid
- no local optimization
- no warm start
- no interpolation of material parameters

---

# 5. Metrics

各probeについて保存:

- aperture_um
- aperture / main wavelength
- max violation
- sum violation
- worst IL
- ripple
- input VSWR
- output VSWR
- each stopband attenuation
- active limiting constraint
- passivity
- reciprocity
- geometry/layout validity
- response finite / nonfinite
- delta vs A0
- delta vs 150 µm

---

# 6. Aperture-bound decision

## `APERTURE_BOUND_NOT_ACTIVE`

以下のような場合:

- 150→165→180→200で性能改善がほぼ無い
- あるいは165以降で悪化
- improvement < material screening上意味のある閾値

→ Stage 3.8では現行upper bound 150 µmを維持。

---

## `APERTURE_BOUND_ACTIVE_MODERATE`

以下のような場合:

- 150→165で明確に改善
- 165→180で改善量が減少
- 180以降でplateau

→ Stage 3.8 MLIT側だけaperture upper boundを
  180 µm程度へ拡張する。

M0は現行boundを維持してよい。

---

## `APERTURE_BOUND_ACTIVE_STRONG`

以下のような場合:

- 150→165→180→200で一貫して改善
- 200でもplateauしない
- active constraintがmatching系から連続的に改善

→ Stage 3.8前にaperture search-space設計を再検討する。

ただし本Stageでさらにboundを広げたりoptimizerを回さない。

---

# 7. Recommended quantitative interpretation

本Stageでは性能絶対値ではなく方向性を見る。

例えば以下を記録:

```text
relative_improvement =
(max_violation_A0 - max_violation_Ax) / max_violation_A0
```

目安として:

- < 2%: negligible
- 2–5%: weak
- 5–10%: material
- >10%: strong

ただし最終判定はactive constraintやresponse形状も含める。

---

# 8. Material metadata problem

Stage 3.7C result/reportでは、
`FilterDesign` object由来の

```text
metallization_ratio = 0.5
thickness_over_lambda = 0.04
```

が残っている一方で、
実際のMLIT providerはsource profileとして概ね

```text
duty ≈ 0.65
h_over_lambda ≈ 0.08
```

を使用している。

このままだと将来、

> MLITを0.04 / 0.5で計算した

と誤解される可能性がある。

---

# 9. Metadata schema cleanup

result/reportに、
少なくとも以下を明示する。

## 9.1 Design fields

geometry object由来のlegacy fields:

```text
design.metallization_ratio
design.thickness_over_lambda
```

これらは「geometry metadata」であり、
MLIT COM generationに使われていない場合は
そのことを明記する。

## 9.2 Effective material profile

新たに明示:

```text
material_profile.id
material_profile.source
material_profile.substrate
material_profile.electrode_material
material_profile.temperature_c
material_profile.effective_h_over_lambda
material_profile.effective_duty
material_profile.phase_policy
material_profile.com_parameter_source
material_profile.normalization_definition_source
```

推奨例:

```text
material_profile.id = LI2024_42YX_LT_METAL_UNSPECIFIED_T25
material_profile.substrate = 42YX-LiTaO3
material_profile.electrode_material = unspecified_metal
material_profile.effective_h_over_lambda = 0.08
material_profile.effective_duty = 0.65
material_profile.phase_policy = SIGNED_REAL_TABLE_ASSUMPTION
```

---

# 10. Report display rule

MLIT使用時はreportで、

```text
Effective material profile:
  h/lambda = ...
  duty = ...
```

を優先表示する。

legacy `FilterDesign` fieldsを表示する場合は:

```text
legacy design field; not used to generate MLIT COM parameters
```

と注記する。

M0では従来どおり表示してよい。

---

# 11. No hidden physics change

metadata cleanupでCOM計算結果を変えてはならない。

必須regression:

- before/after same geometry
- same provider
- same frequency grid
- same Y
- same S
- same metrics

strict numerical equalityまたはmachine tolerance内一致を確認する。

---

# 12. Required tests

最低限:

1. MLIT metadata is emitted correctly
2. M0 metadata remains backward compatible
3. MLIT effective h/lambda and duty override display semantics only
4. provider output unchanged
5. response unchanged after metadata patch
6. serialization / deserialization works
7. report renders both M0 and MLIT correctly
8. full regression

保存:

- exact command
- passed
- failed
- skipped
- runtime

---

# 13. Stage 3.8 search-space recommendation

aperture probe結果から、
Stage 3.8用のsearch-space recommendationを作る。

必須表:

| Profile | aperture lower | aperture upper | rationale |
|---|---:|---:|---|
| M0 | current | current | Stage 3.6 continuity |
| MLIT | current | recommended | probe result |

M0とMLITでupper boundを同じにする必要はない。

ただしtopology comparison時のfairnessについて、
profile-specific boundであることを明記する。

---

# 14. Required outputs

## Data

- `mlit_aperture_boundary_probe.csv`
- `mlit_aperture_probe_seed_comparison.csv`
- `stage3_8_aperture_bound_recommendation.csv`
- `metadata_regression_check.csv`

## Markdown

- `stage3_7d_aperture_boundary_probe_summary.md`
- `material_profile_metadata_schema.md`
- `test_summary.md`

## Plots

minimum:

1. max violation vs aperture
2. input/output VSWR vs aperture
3. IL/ripple vs aperture

2seedは同じplot上で比較してよい。

---

# 15. Questions to answer

最終summaryで必ず回答:

1. 150 µm upper boundはMLIT設計を人工的に制限しているか？
2. 165/180/200 µmへ広げるとどのmetricが改善するか？
3. 改善は両seedで再現するか？
4. Stage 3.8 MLIT aperture upper boundはいくつにするべきか？
5. M0 boundは維持してよいか？
6. metadataでeffective h/lambda / dutyが正しく表示されるか？
7. metadata patchがphysics結果を変えていないか？
8. Stage 3.8へ進んでよいか？

---

# 16. Final decision labels

以下のどれかを明示:

### `STAGE3_8_READY_APERTURE_150`

MLIT 150 µm boundを維持してStage 3.8へ進む。

### `STAGE3_8_READY_APERTURE_EXPANDED`

MLIT aperture upper boundを指定値へ拡張してStage 3.8へ進む。

例:

```text
MLIT aperture upper = 180 um
```

### `APERTURE_SPACE_REDESIGN_REQUIRED`

200 µmでも強い改善が続き、
simple upper-bound extensionでは不十分。

Stage 3.8前にsearch-space設計を再検討。

---

# 17. Repository hygiene

終了時に以下を分類:

- Stage 3.7D source changes
- metadata-only changes
- generated artifacts
- pre-existing unrelated dirty files

commit / pushはしない。

---

# 18. Hard stop

成功時:

```text
STAGE3_7D_APERTURE_AND_METADATA_GATE_COMPLETE_STOP
```

search-space redesignが必要:

```text
STAGE3_7D_APERTURE_SPACE_REDESIGN_REQUIRED_STOP
```

いずれの場合もStage 3.8を自動開始しない。

---

# 19. Philosophy

今回の目的はMLITの最適設計を完成させることではない。

Stage 3.8のtopology comparisonに入る前に、

> 「aperture upper boundが人工的にMLITだけを不利にしていないこと」

と、

> 「どのmaterial profileを実際に使ったかがreportから一意に分かること」

の2点を保証する。

数点のforward evaluationで判断できる問題に、
新たな長時間optimizationを使わないこと。
