# Experiment Register

This register keeps the results and decisions needed to interpret later SAW
work. Historical source code is not a re-execution contract. Raw run data is
left in place and is referenced where it exists.

Historical source documents, stage code, and experiment configs removed from
the active tree are preserved at the annotated tag
`archive/pre-historical-deletion-2026-09-25`. Their old paths below identify
provenance; retrieve a file with `git show archive/pre-historical-deletion-2026-09-25:<path>`.

## Evidence limits

The current checkout contains canonical run data for Stages 3.6–3.8C, but not
the documented prototype or 50 Ω hybrid run directories. Stage 3.1–3.5 run
directories are also absent. For those records, this register preserves only
claims supported by the pre-deletion source snapshot and retained escalation
history; it does not invent missing metrics or run commits. Several old records
therefore have no recoverable raw artifact or exact source commit in this
checkout.

## Prototype impedance sweep

**Evidence level:** retained result/review documents; canonical run directory,
configuration, and run commit are absent from this checkout.

- **Question:** How does a separately optimized discrete SAW filter vary with
  real source/load impedance under the initial COM model?
- **Conditions:** Hypothetical COM parameters; 14 impedance values across the
  initial coarse sweep plus the documented 35, 45, and 55 Ω refinements; three
  seeds; 14 individuals and 20 generations per final seed run. Rejected
  geometries and cache hits make COM evaluation counts vary.
- **Result:** 45 Ω was the best point within this finite search. Its worst
  passband insertion loss was 10.6614 dB, ripple 5.4704 dB, and input/output
  VSWR about 5.7403. All points missed the intended specification.
- **Decision:** Treat 45 Ω as a provisional ranking under this hypothetical
  model only. Matching alone may not solve the loss problem. Calibrate COM
  parameters against measurement or FEM and confirm the physical IDT wiring
  before interpreting an optimum impedance.
- **Limits:** No material calibration, no global-optimum claim, and no
  convergence claim from zero seed spread. Reusing neighboring-impedance
  candidates also means zero spread is not independent evidence.
- **References:** Pre-deletion source documents
  `docs/results/prototype_results_ja.md` and `docs/reviews/review_ja.md` are
  available through the annotated cleanup tag; documented canonical run
  `runs/refined-prototype` is not present in this checkout. Config, review
  bundle, and run commit are not recoverable from the retained files.

## 50 Ω hybrid screen

**Evidence level:** retained result document; canonical run directory,
configuration, review bundle, and run commit are absent from this checkout.

- **Question:** Does adding ladder resonators to the DMS improve the 50 Ω
  response?
- **Conditions:** Hypothetical COM model; 50 Ω source and load; 57 trials and
  33,189 candidate evaluations. 7,914 candidates were rejected by geometry
  checks before COM evaluation.
- **Result:** Worst insertion loss was 10.90 dB for the earlier DMS wiring,
  8.54 dB for the selected DMS wiring, 6.55 dB after adding an input-side
  parallel resonator, and 6.50 dB after adding resonators at both ports. The
  best recorded `P_D_P` design had 3.05 dB ripple, input/output VSWR 4.54/3.98,
  16.00 dB minimum attenuation at 832–862 MHz, and did not meet the target.
- **Decision:** A ladder addition improved the recorded search result, but
  the comparison mixes finite searches and does not isolate topology from
  search-budget effects. Keep hybrid as a future candidate; do not claim the
  loss or upper-stopband target is solved.
- **Limits:** The 50 Ω results use uncalibrated hypothetical COM parameters.
  At the 765.74 MHz worst-loss point, the reported power budget assigned
  25.6% to input reflection, 22.4% to delivered load power, and 52.0% to model
  dissipation/acoustic radiation. This is evidence that matching alone may be
  insufficient within the model.
- **References:** The pre-deletion result document
  `docs/results/hybrid_50ohm_results_ja.md` is available through the annotated
  cleanup tag; documented run
  `runs/hybrid-50ohm` is not present in this checkout. Config, review bundle,
  and run commit are not recoverable from the retained files.

## Stage 3.1–3.4b convergence and continuation

**Evidence level:** retained configs, experiment READMEs, and project decision
records; canonical run directories and exact run commits are absent.

- **Question:** How much unique-design search budget is needed for the 50 Ω
  `center_outer_same` DMS study, and how should stagnation be treated?
- **Conditions and decisions:** Stage 3.1's exact legacy config fragment is
  missing; the retained experiment is intentionally non-executable and must
  not be reconstructed from Stage 3.2 settings. Stage 3.2 added a bounded
  zero-progress recovery sequence: four DE attempts, three between-attempt
  population refreshes, quarter-population retention, and deterministic seed
  progression. Later convergence accounting uses unique decoded designs so
  duplicate proposals do not inflate the comparison budget.
- **Stage 3.4b finding:** The cleanup plan records an extension through
  256,000 unique evaluations. The 64,000 checkpoint alone was not enough to
  assert convergence. Eight cold seeds, the 50 Ω wiring, and the hard lower
  bound of eight input/output IDT pairs define the extended study. Do not
  present a finite checkpoint or the study's 512,000 absolute ceiling as proof
  of a global optimum.
- **Carry-forward:** Treat convergence status as evidence about remaining
  budget, not global optimality. Retain unique-evaluation accounting,
  deterministic recovery, and the 50 Ω `center_outer_same` result as a
  comparison reference.
- **Limits and references:** The former convergence guides, experiment
  descriptors, and `configs/studies/stage3_2*`–`stage3_4b*` files are available
  from the annotated cleanup tag. Canonical run data and exact run commits are
  absent from the current `runs/` tree.

## Stage 3.3–3.5 optimizer and search-space studies

**Evidence level:** retained configs, experiment READMEs, frozen S1 artifact,
and escalation history; canonical production run and review bundle are absent.

- **Question:** Which search backend and starting box give useful progress
  under a matched protocol?
- **Conditions:** Stage 3.3 compared Legacy SciPy DE and L-SHADE; Stage 3.5
  crossed both backends with the frozen Stage 3.4b S0 box and a data-informed,
  boundary-expandable S1 initial box. Phase C used cold starts and development
  seeds 20260917–20260920. All four arms reached 16k and 32k; arm A always
  reached 64k, while only the 32k survivors continued to 64k. The L-SHADE
  schedule horizon was 64,000 with checkpointed progression. Hard bounds,
  COM/network behavior, validation, and convergence thresholds were held
  fixed.
- **Interpretation:** Early apparent Legacy-DE advantage was not sufficient to
  establish backend superiority. A parity audit found identical historical
  and current traces through 4,000 unique evaluations, then a current-only
  adaptive-frequency exchange at 4,000 versus historical exchanges at
  16,000/32,000/64,000. This is a protocol/provenance mismatch, not evidence
  that one optimizer is intrinsically better. Use L-SHADE as the later study
  backend because the later protocol adopts it; do not treat the historical
  A/B as a universal algorithm ranking.
- **S1 meaning:** The frozen
  `artifacts/stage3_5/phase_a_revised/search_space_s1.yaml` is a 50 Ω
  experiment-specific starting box inside unchanged hard bounds. It narrows
  the wavelength and reflector ranges and provides expandable ranges for
  selected IDT pair counts. It is not a material-independent or all-impedance
  default. The recorded source artifact SHA-256 is
  `26feb9ebe09b7f37d71cc96b74e83544065fc2c0d62e5e830b601cb3b3dc731f`.
- **Decision:** Phase C was added as a bounded matched development comparison.
  Phase D, 192k/256k extension, impedance sweep, and productionization were
  deliberately not started automatically. Preserve the source/config and
  protocol provenance before drawing further backend conclusions.
- **References:** The former Stage 3.3/3.5 experiment descriptors, configs,
  and frozen S1 artifact are available from the annotated cleanup tag. The
  Stage 3.5 decisions remain in `reports/escalation_log.md`. The production
  run and review bundle referenced by the old handoff are not present here.

## Stage 3.6 — 50 Ω DOF release and asymmetric ports

**Evidence level:** canonical runs and review bundles are retained, with
recorded source commits for Gate 2A, Gate 2B-B, and Gate 2C.

- **Question:** Which geometry DOFs should be released at the 50 Ω reference,
  and do separately optimized source/load impedances change the result?
- **Conditions:** The reference is a 50/50 Ω DMS with the existing topology,
  evaluator, constraints, objective, validation grid, and L-SHADE backend.
  Gate 2A screened center pitch (`G1`), reflector pitch (`G2`), and center
  aperture (`G3`) against the reduced baseline. Its 16k three-seed screen
  promoted G1 and G2; G3 did not meet the promotion rule. The promoted
  interaction is G1+G2. Gate 2B-B used nine symmetric/asymmetric port pairs,
  three seeds, 32k unique evaluations per run, and a 9,113-point common grid.
- **Reason for asymmetric ports:** A left/right asymmetric DMS can present
  different source-side and load-side sensitivities, so `Zin` and `Zout` were
  independently varied instead of assuming one shared optimum.
- **Gate 2B-B result:** No feasible runs (0/27). The best median maximum
  violation was 0.501944 at 62.5/62.5 Ω; the 50/50 baseline median was
  0.511222. The mechanical order is descriptive only; three seeds do not
  establish significance or a final port choice. Several late checkpoints
  still improved, so the runs do not establish convergence.
- **Gate 2B-A result:** The nine-cell 25/50/100 Ω factorial used three cold
  seeds and 16k evaluations per cell. Median maximum violation ranged from
  0.508612 at 50/50 Ω to 0.666007 at 25/100 Ω; the asymmetric cells show
  directional differences, but three seeds support no significance claim.
  Gate 2B-B narrowed and refined conditions without selecting a final pair.
- **Gate 2C result:** Added center aperture (`G3`) to the G1+G2 release and
  compared selected impedances. The strongest two-seed signal was the 50/75 Ω
  S1 comparison, but no run was feasible; the label was
  `DOF_BENEFIT_STRONG`, not a final impedance decision. At 100/100 Ω the added
  DOF was inconclusive. No bounds were expanded and no production follow-up
  started.
- **Carry-forward:** Keep the 50 Ω Gate 2A result as the reference; do not
  select an optimum impedance from the small asymmetric screen. Preserve
  independent source/load controls for future studies.
- **References:** Runs `runs/stage3_6_gate2a_dof_release_50ohm`,
  `runs/stage3_6_gate2b_a_asymmetric_impedance_retry_20260917`,
  `runs/stage3_6_gate2b_b_asymmetric_impedance`, and
  `runs/stage3_6_gate2c_joint_impedance_dof_fast_screening`; review bundles
  `artifacts/review_bundles/stage3_6_gate2a_dof_release_50ohm_review.zip`,
  `stage3_6_gate2b_a_asymmetric_impedance_review.zip`,
  `stage3_6_gate2b_b_asymmetric_impedance_refinement_review.zip`, and
  `stage3_6_gate2c_joint_impedance_dof_fast_screening_review.zip`. Recorded
  source commits: Gate 2A `c207bb6444dc1fa9c37dd91f5f677dc523bd1920`, Gate 2B-B
  `eb4b626486d8972ee1c860bf7a9695a4e59f27da`, and Gate 2C
  `db049bd9d0eb0e2c8730e9909ca0e5a422d09f70`.

## Stage 3.7 — literature COM and aperture study

**Evidence level:** canonical run data and model/study configs are retained;
the Stage 3.7C decision is also recorded in escalation history.

- **Question:** Can a source-grounded 42°YX-LiTaO3/Al COM model replace the
  hypothetical provider and support a B28 comparison?
- **Model:** The normalized literature profile is
  `LI2024_42YX_LT_METAL_UNSPECIFIED_T25`. Raw values are retained, and a
  no-fallback adapter prevents missing literature values from being silently
  supplied by M0. The paper does not establish enough source-device detail to
  certify native reconstruction; the 80 µm validation aperture is an explicit
  evaluation assumption, not reported source geometry.
- **Result and decision:** Algebraic normalization passed, but native
  resonator/source reconstruction remained inconclusive (reported feature
  scale error 3.13%, without a numeric digitized source feature). Phase
  sensitivity was not robust within 2% of resonance, so the fixed-design B28
  sensitivity was not run at that gate. The later Stage 3.7C fast screen used
  M0 and MLIT as dual baselines and reported material-direction sensitivity;
  neither is calibrated or production-qualified.
- **Aperture:** Stage 3.7D found the 150 µm upper bound was not active and
  recommended 30–150 µm for MLIT. Stage 3.8 later used 30–180 µm for MLIT as
  an explicit user-directed override. That unequal range versus M0's
  30–150 µm confounds cross-material comparisons and remains part of the
  baseline provenance.
- **Unresolved:** Native electrode material, aperture, terminal/phase
  registry, and attenuation convention are incomplete. No parameter mixing,
  B28 calibration, or FEM result resolves these gaps. Production claims require
  a complete same-source profile or FEM/measurement extraction.
- **References:** `configs/models/stage3_7b_r1_normalized_literature_profile.yaml`,
  runs under `runs/stage3_7*`, including
  `runs/stage3_7b_r2_stage3_7c_literature_com_b28_fast_screen_final_retry3`
  and `runs/stage3_7d_mlit_aperture_boundary_and_metadata_final`; decisions in
  `reports/escalation_log.md`. Stage 3.7C source commit:
  `db049bd9d0eb0e2c8730e9909ca0e5a422d09f70`.

## Stage 3.8 / 3.8C — DMS topology screen

**Evidence level:** canonical production run, review bundles, and closeout
evidence are retained.

- **Question:** How do three candidate DMS topologies compare under the
  retained COM model and manufacturing constraints?
- **Topology definitions:** T0 is the current 3-IDT structure. T1 is a
  mirrored five-IDT `R-A-B-C-B-A-R` chain with signed port mapping
  `[+,-,+,-,+]`. T2 is two parallel three-IDT tracks whose unterminated Y
  matrices are summed before applying one source/load termination; each track
  gets half of the total aperture.
- **R1 correction:** The first 96k ranking was invalid because geometry
  constraint violations could beat geometry-valid filters under the old
  comparator. All 12 recorded cells had zero valid physics evaluations and
  zero solved points. The R1 geometry-first rank path fixed the ordering and
  kept filter metrics out of geometry-rejected records.
- **Pilot lineage:** R1 stopped because T2 geometry rejection was 93.27% for
  M0 and 91.99% for MLIT, above the 90% pilot limit. R1.1's conditional
  initializer passed pilot gates but changed sampling distribution; it was
  diagnostic only. R1.2 restored independent uniform proposals plus geometry
  rejection, rejected rather than repaired invalid designs, and passed its
  six-cell pilot and final confirmation. The pilot was not treated as a
  topology ranking.
- **Canonical production:** Run
  `runs/stage3_8c_production_20260924`, R1.2, six material/topology cells,
  two seeds per cell, 8,000 unique evaluations per seed (96,000 total),
  checkpoints 2k/4k/6k/8k, and 9,113-point common validation grid
  `2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f`.
  All 12 seed runs and 48 checkpoint rows passed accounting; physics failures
  were zero. No candidate was filter-feasible.
- **Screen result:** M0/T0 had the lowest median maximum violation for M0
  (0.504066); MLIT/T1 ranked first within MLIT (0.492134). T2 remains
  unresolved because it was still improving at the 8k checkpoints. These are
  within-profile screening results, not promotion or proof of absolute
  superiority. Cross-material comparison is confounded by material provenance
  and unequal aperture bounds.
- **Closeout correction:** An initial closeout counter check expected 12
  seed-run rows, but the canonical result stores 48 checkpoint rows. The
  counter gate was corrected and the existing 96k result was read-only audited;
  no optimizer or physics rerun occurred.
- **Carry-forward:** No feasible filter exists in this screen. Preserve T0/T1/T2
  topology validation and the R1.2 independent-uniform initializer. Before
  Stage 3.9, address material calibration, geometry/search-space efficiency,
  and the aperture-bound mismatch. Do not infer a best real-device material or
  impedance.
- **References:** The former production config is available from the annotated
  cleanup tag. Retained raw data includes `runs/stage3_8c_production_20260924`,
  `artifacts/review_bundles/stage3_8c_production_review.zip` and corrected
  closeout bundle `stage3_8c_production_closeout_corrected_review.zip`. The
  closeout report is preserved in the annotated cleanup tag. Frozen candidate
  fingerprint: `4465b7177b15ab44c10576a7c3d3bf0363c79a7dafa46ef8452a45626407824d`;
  recorded candidate commit: `f2babf340f7143e44db6af83f28e2324e724f6ed`.

## Cleanup rule

At each future study closeout, add the result and decision here, update
`current_baseline.md` only when a result changes an adopted assumption, and
then decide whether experiment-specific implementation, config, and tests can
leave the active tree. Keep raw runs and review bundles at their recorded
locations. The pre-deletion tag is the canonical source for removed historical
files; it does not replace the scientific summaries in this register.
