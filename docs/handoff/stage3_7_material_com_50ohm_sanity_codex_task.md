# Codex 作業指示書
## Stage 3.7 — Literature-Grounded COM / 50 Ω Sanity Screen

## 0. Mission

Stage 3.6までの3-IDT DMS最適化結果について、現在のhypothetical COM parameter setへの依存性を軽量に確認する。

本Stageの目的は、材料スタックやCOM係数の最終確定ではない。

目的は以下である。

1. 現在の50 Ω・3-IDT最適設計方向が、文献ベースの42°YX-LiTaO3 / Al条件でも維持されるか確認する。
2. 現在観測されている
   - wavelength ≈ 5 µm
   - IDT gap ≈ 0.5 λ
   - `io_idt_pairs=8` hard-bound pressure
   - relatively small reflector count
   - aperture ≈ 20 λ
   - `stop_1` dominance
   が、hypothetical COM固有かどうかを判定する。
3. Stage 3.8のDMS topology screeningで使用するmaterial/COM baselineを最低1つ選定可能な状態にする。
4. 文献COM値を現在のCOM conventionへ安全に変換できない場合は、推測値を使用せず明示的に停止する。

本Stageでは高精度な最適値を求めない。

---

# 1. Current baseline audit

最初に現在repositoryを確認し、以下を記録する。

- git branch
- git HEAD
- git status
- current DMS model implementation
- current search-space definition
- current 50 Ω baseline config
- current COM config path
- current provider implementation
- current `FilterDesign` defaults
- metallization ratio
- thickness_over_lambda
- current COM parameter values
- current impedance = 50 / 50 Ω
- current wiring
- current validation grid/hash if available

Stage 3.6成果物を改変しない。

---

# 2. Current 50 Ω reference design

Stage 3.6で得られた現行50/50 Ωの代表best designを固定referenceとして選ぶ。

原則:

- Gate 2B-Bの50/50 Ω・32k結果
- validated max constraint violationが最小のseed
- current production `G1_G2`
- current 3-IDT topology

を使用する。

以下を保存する。

- wavelength_um
- center wavelength / reflector wavelength if independently represented
- io_idt_pairs
- center_idt_pairs
- reflector_electrodes
- idt_gap_lambda
- reflector_gap_lambda
- aperture_um
- aperture / lambda
- metallization_ratio
- thickness_over_lambda
- metrics
- active limiting constraint
- source file / run / seed

reference designの値を手で書き換えない。

---

# 3. Literature COM profile audit

## 3.1 Target material family

今回対象とするのは、

- substrate: 42°YX-LiTaO3
- electrode: Al または文献で明示されたAl系電極
- frequency / wavelength range: approximately 700–850 MHz equivalent
- DMS / LCR / SAW filter用途

とする。

## 3.2 Candidate profiles

最低限以下の分類を試みる。

### M0 — Current baseline
現行hypothetical COM parameter set。

### M1 — Thin-electrode literature profile
目安:

- h/lambda ≈ 0.04
- metallization ratio ≈ 0.6
- 700–800 MHz class DMS literature

### M2 — Medium-thickness COM-extraction profile
目安:

- h/lambda ≈ 0.08
- metallization ratio ≈ 0.65
- 42°YX-LiTaO3
- same-source velocity / kappa / alpha / capacitance set

### M3 — Thick-electrode / B28 reference
目安:

- h/lambda ≈ 0.10–0.11
- duty ≈ 0.70
- B28 or near-B28 literature

M3は完全COM setが得られない場合、reference-onlyでよい。

## 3.3 Mandatory fields

production simulationに使用するprofileには最低限以下を要求する。

- substrate / cut
- electrode material
- h/lambda
- metallization ratio / duty ratio
- wavelength or frequency context
- velocity
- kappa
- alpha
- capacitance
- loss / attenuation or explicit documented omission
- temperature if relevant
- parameter definitions / normalization convention
- source citation
- source publication metadata

## 3.4 Prohibited behavior

以下は禁止。

- kappaを論文A、alphaを論文B、Cを論文Cから混成
- normalizationが不明なまま数値を使用
- dimensionless / dimensional conventionを推測で変換
- missing alpha / C / lossを適当な値で補う
- literature profileを「calibrated」と呼ぶ
- measured device fitとFEM extractionを区別せず混在させる

同一material stack / same sourceで整合的に得られるCOM setのみproduction candidateとする。

---

# 4. COM convention mapping

現在solver conventionを明示的に確認する。

現在の基本式:

```text
dR/dx = -jδ R + jκ S + jα V
dS/dx = -jκ* R + jδ S - jα* V
dI/dx = -2jα* R - 2jα S + jω C V
```

current units:

- kappa: 1/m
- alpha: sqrt(S)/m
- C: F/m
- velocity: m/s
- loss: 1/m internally
- current config may store normalized `kappa_lambda`

各literature profileについて、

- symbol definition
- phasor convention
- sign convention
- acoustic normalization
- electrical normalization
- kappa units
- alpha units
- C normalization

を確認する。

### Mapping confidence

各profileを以下に分類する。

- `DIRECT_COMPATIBLE`
- `CONVERTIBLE_WITH_DERIVATION`
- `REFERENCE_ONLY`
- `UNUSABLE`

`CONVERTIBLE_WITH_DERIVATION`の場合は変換式・単位検証・簡単なsanity testを文書化する。

---

# 5. Provider implementation

## 5.1 Existing provider preservation

現行`FixedProvider`を破壊しない。

M0は従来挙動を完全に維持する。

## 5.2 New provider

必要であれば、

- `LiteratureProfileProvider`
または
- `TabulatedCOMProvider`

のような明示的providerを追加する。

ただし今回のStageでは、

- continuous thickness interpolation
- continuous metallization interpolation
- temperature interpolation

は実装しない。

各profileを不可分なmaterial stackとして扱う。

例:

```text
M2:
substrate = 42YX_LT
electrode = Al
h_over_lambda = 0.08
duty = 0.65
COM = {v, kappa, alpha, C, loss}
```

## 5.3 No fake dependency

`thickness_over_lambda`を変更しただけで、同じCOM setを使い続ける実装は禁止。

material profile変更時にはCOM parameter set自体が切り替わること。

---

# 6. Provider verification tests

production前に最低限以下を確認する。

1. M0 parity
   - new code pathでM0が旧FixedProviderと一致する

2. profile switching
   - M0/M1/M2でvelocity/kappa/alpha/Cが実際に切り替わる

3. unit sanity
   - finite values
   - positive velocity
   - non-negative physical capacitance magnitude as appropriate
   - no invalid NaN/Inf

4. passivity / reciprocity
   - existing solver checksを通る

5. synchronous frequency sanity
   - expected center frequency orderがB28 vicinityに入るか

6. same geometry / different profile
   - responseが完全同一になっていないこと

source code変更を行った場合は関連unit tests + full regressionを実行する。

---

# 7. Phase C — Fixed-design profile sensitivity

optimizerを回す前に、Stage 3.6の50 Ω reference designを各usable profileでそのまま評価する。

## Conditions

- topology: current 3-IDT
- wiring: current production wiring
- Zin = 50 Ω
- Zout = 50 Ω
- same geometry
- same validation grid
- no geometry re-optimization

## Required metrics

- passband worst IL
- ripple
- input VSWR
- output VSWR
- max violation
- sum violation
- each stopband violation
- active limiting constraint
- resonance / antiresonance feature locations if extractable
- common-grid response

## Required interpretation

目的は性能順位ではない。

以下を評価する。

- passband frequency shift
- bandwidth change
- stopband movement
- resonance structure change
- matching change
- whether current geometry is catastrophically incompatible with literature profile

---

# 8. Phase D — Fast 50 Ω re-optimization

fixed-design evaluation後、usable profileについて軽量re-optimizationを実行する。

## 8.1 Conditions

- topology: current 3-IDT DMS
- Zin = 50 Ω
- Zout = 50 Ω
- search space: current `G1_G2`
- optimizer: current production L-SHADE
- cold start
- warm start prohibited
- budget: 8,000 unique evaluations / run
- seeds:
  - 20260917
  - 20260918
- common validation grid
- no bound expansion
- no DOF expansion

## 8.2 Profiles

最大:

- M0
- M1
- M2

の3profile。

M1/M2のどちらかが`REFERENCE_ONLY`ならproductionから除外する。

production usable profile数が1つしかない場合:

- M0 + one literature profile

で実行する。

literature production profileが0の場合はPhase Dを開始しない。

## 8.3 Maximum nominal compute

3 profiles × 2 seeds × 8k = 48k evaluations

これを超えて自動追加しない。

---

# 9. Checkpoints

Fast screeningなので最低限以下を保存する。

- 2k
- 4k
- 6k
- 8k

各runについて:

- best-so-far primary metric
- best geometry
- active limiting constraint
- last meaningful improvement
- feasible flag
- runtime

convergence certificateは要求しない。

---

# 10. Geometry comparison

各profileのbest designについて以下を比較する。

## Absolute

- wavelength_um
- center wavelength if applicable
- reflector wavelength if applicable
- io_idt_pairs
- center_idt_pairs
- reflector_electrodes
- aperture_um
- idt_gap_lambda
- reflector_gap_lambda

## Normalized

- aperture / lambda
- io_idt_pairs / center_idt_pairs
- reflector electrodes per side
- center wavelength / main wavelength
- reflector wavelength / main wavelength
- IDT gap / lambda
- reflector gap / lambda

## Important flags

- `io_idt_pairs == hard lower bound`
- reflector lower/upper boundary hit
- aperture boundary hit
- any geometry shift > 20% relative to M0
- active constraint change

---

# 11. Comparison against literature geometry

literature design geometryをreference tableにまとめる。

最低限:

- wavelength
- IDT pair counts
- reflector finger count
- aperture/lambda
- IDT gap/lambda
- metallization ratio
- h/lambda
- DMS order / number of IDTs
- frequency band

現行bestおよびM1/M2 reoptimized bestと比較する。

目的はexact matchではなく、

`same order / same direction / materially different`

の判定。

---

# 12. Decision logic

## `ROBUST_3IDT_DIRECTION`

以下のような場合:

- wavelength stays in expected B28-scale range
- IDT gap remains around the same normalized region
- center/outer electrode-count relationship remains broadly similar
- aperture/lambda remains same order
- active bottleneck remains similar
- current 3-IDT geometry does not collapse under literature profile

→ current design direction is considered robust enough for topology screening.

Stage 3.8へ進む候補baselineを選ぶ。

---

## `MATERIAL_SENSITIVE`

以下のような場合:

- io_idt_pairs hard-bound pressure disappears
- reflector count moves strongly toward literature-like larger values
- aperture/lambda changes substantially
- dominant constraint changes
- impedance/matching behavior changes qualitatively
- M0 geometry performs very poorly while reoptimized literature profile recovers strongly

→ Stage 3.6 geometry trends were materially dependent on hypothetical COM assumptions.

Stage 3.8ではliterature-grounded profileをbaselineとして使用する。

---

## `COM_MAPPING_BLOCKED`

- no reliable kappa/alpha/C convention mapping
- literature data are incomplete
- provider cannot reproduce basic sanity/passivity
- normalization ambiguity remains

→ do not fabricate profile.

次タスクを
`COM parameter acquisition / FEM extraction`
とする。

---

# 13. Material baseline selection

Stage 3.8用baselineは以下で選ぶ。

優先順:

1. complete / internally consistent COM set
2. 42°YX-LiTaO3 + Al
3. frequency / wavelength close to B28
4. documented DMS/SAW validation
5. physically reasonable response
6. reproducible mapping to current solver convention

optimization metricだけでmaterial baselineを選ばない。

---

# 14. Required outputs

## Data

- `literature_com_profile_audit.csv`
- `com_convention_mapping.csv`
- `fixed_design_profile_sensitivity.csv`
- `all_seed_results.csv`
- `profile_summary.csv`
- `geometry_comparison.csv`
- `literature_geometry_comparison.csv`
- `convergence_lite.csv`

## Config / metadata

- exact M0 snapshot
- exact usable literature profile snapshots
- source citations / DOI / publication metadata
- mapping derivation note
- run config
- git head / branch / status
- test command/results
- validation grid identity/hash

## Markdown

- `stage3_7_material_com_sanity_summary.md`
- `com_profile_mapping_notes.md`
- `test_summary.md`

## Plots

最低限:

1. fixed-design response by profile
2. reoptimized max violation by profile/seed
3. normalized geometry comparison
4. literature vs optimized geometry comparison

不要にplotを増やさない。

---

# 15. Final summary requirements

`stage3_7_material_com_sanity_summary.md`には以下を必ず含める。

1. current M0 COM assumptions
2. literature sources reviewed
3. profile candidates
4. usable vs reference-only profile classification
5. convention mapping confidence
6. fixed-design sensitivity
7. 8k reoptimization results
8. geometry shifts
9. comparison with representative literature geometry
10. `io_idt_pairs` boundary behavior
11. reflector count behavior
12. aperture/lambda behavior
13. dominant constraint changes
14. whether 3-IDT direction appears robust
15. recommended material baseline for Stage 3.8
16. unresolved COM uncertainties
17. recommended next action

以下の表現は禁止:

- calibrated material model
- experimentally validated
- globally optimal material stack
- final physical design

literature-grounded / literature-derived / preliminary profileなどの表現を使用する。

---

# 16. Hard stop

以下を開始してはならない。

- 5-IDT implementation
- parallel DMS implementation
- hybrid DMS + ladder optimization
- impedance sweep
- 32k / 64k escalation
- 5-seed confirmation
- continuous h/lambda optimization
- continuous duty optimization
- arbitrary COM interpolation
- FEM extraction unless separately instructed

全成果物作成後、

`STAGE3_7_MATERIAL_COM_SANITY_COMPLETE_STOP`

と出力して停止する。

usable literature COM profileが得られずPhase Dを実施しなかった場合は、

`STAGE3_7_COM_MAPPING_BLOCKED_STOP`

と出力して停止する。

---

# 17. Philosophy

今回の成功条件は、実材料を完全に再現することではない。

成功とは、

> 「現在の3-IDT最適化方向が、文献に基づくより現実的なCOM条件でも概ね維持されるのか、それとも材料モデル依存性が大きいのか」

を少ない計算量で明確にすることである。

曖昧なCOM値を推測して計算量を浪費するより、mapping不能なら止めることを優先する。
