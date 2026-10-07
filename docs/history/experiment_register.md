# Experiment Register

This register keeps the results and decisions needed to interpret later SAW
work. Historical source code is not a re-execution contract. Raw run data is
left in place and is referenced where it exists.

Historical source documents, stage code, and experiment configs removed from
the active tree are preserved at the annotated tag
`archive/pre-historical-deletion-2026-09-25`. Their old paths below identify
provenance; retrieve a file with `git show archive/pre-historical-deletion-2026-09-25:<path>`.

## Evidence limits

`runs/` and most of `artifacts/` are Git-ignored. Repository history can
prove the historical code/config/document state and expected artifact paths,
but it cannot prove that a referenced local run or review bundle still exists
after local cleanup. Artifact references below therefore describe historical
canonical or expected locations; current local availability is **UNVERIFIED**
unless it is checked separately.

For Stages whose raw data are unavailable, this register preserves only claims
supported by the pre-deletion Git snapshot, retained decision records, or a
2026-09-25 retrospective recovery from the project's prior ChatGPT
conversations and uploaded review material. Retrospectively recovered values
are labeled as such and are not used to invent missing run commits or raw
artifacts.

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

## Stage 2 — impedance-aware topology/wiring pilot

**Evidence level:** Git-recoverable implementation guide and Stage 2 task
definition at the pre-deletion tag; the pilot run directory is not required for
the decision record below.

- **Question:** Can the study compare separately re-optimized filters across
  impedance while avoiding topology/wiring pruning bias and coarse-grid
  acceptance bias?
- **Implementation decisions:** Stage 2 made source/load impedance explicit,
  closed the adaptive-frequency loop, canonicalized integer-containing designs
  before cache identity, scaled population with dimension, and required joint
  topology × wiring low-budget screening rather than keeping only the wiring
  that was best for D-only.
- **Pilot conditions:** Small 20/50/100 Ω pilot; candidate families
  `D`, `P_D`, and `P_D_P`; three DMS wirings; three seeds.
- **Pilot result:** At 20 Ω the selected result was
  `P_D_P / center_outer_same`, worst IL 9.3670 dB and maximum violation
  2.1223. At 50 Ω it was `P_D / center_outer_same`, worst IL 8.4666 dB and
  maximum violation 1.8222. At 100 Ω it was
  `P_D_P / center_outer_same`, worst IL 9.5004 dB and maximum violation
  2.6397. The corresponding 50 Ω-shape loading-only IL values were
  10.8352, 8.4666, and 10.3333 dB.
- **Decision:** All pilot points failed the target. The low-budget screen does
  not establish that 50 Ω is the optimum and does not support a real-device
  impedance recommendation. Continue with calibrated/common-budget
  convergence work before a production impedance sweep.
- **References:** Pre-deletion
  `docs/guides/stage2_implementation.md`,
  `CODEX_STAGE2_TASK.md` from the project attachment archive, and the Stage 2
  source/config snapshot at the annotated deletion tag.

## Stage 3.1–3.4b convergence and continuation

**Evidence level:** Git-recoverable configs/experiment guides plus
retrospectively recovered project-chat reviews. Raw Stage 3.1–3.5 run
availability is not established by Git.

- **Question:** How much unique-design search budget is needed for the 50 Ω
  `center_outer_same` DMS study, and how should stagnation and active search
  boundaries be treated?
- **Stage 3.1:** The exact legacy Stage 3.1 config fragment is missing and must
  not be reconstructed from Stage 3.2 settings. In the later corrected
  4,000-unique-design review, `center_outer_same` had best/median maximum
  violation 1.780/1.827, seed IQR 0.00524, paired 2k→4k median improvement
  0.00384, and no best-candidate polish improvement. This looked locally
  plateaued, but input/output IDT pairs were pressed against the active lower
  bound, so it was not accepted as a structure/model limit. `outer_ports`
  retained much larger seed dispersion (IQR about 0.163) and remained
  underoptimized.
- **Stage 3.2 continuation:** The first 8k→16k continuation improved best
  maximum violation only from about 1.099 to 1.087 while the median improved
  from about 1.597 to 1.316; seed IQR widened from about 0.242 to 0.497 and two
  seeds made late material improvements at roughly 87.3% and 95.6% of the
  budget. Status therefore remained `likely_underoptimized`. The active
  `io_idt_pairs` lower bound expanded 20→15; a post-run 15→10 probe improved
  4/5 seeds, revealing that production bound expansion had not been wired to
  the elite-boundary evidence.
- **Recovery semantics:** Stage 3.2 added a bounded zero-progress recovery
  sequence: up to four DE attempts, three between-attempt population
  refreshes, retention of the first `max(1,n//4)` prior members, and
  deterministic retry seeds using the trajectory segment index. A successful
  retry exits immediately; `no_new_unique_designs` is set only after all
  four attempts fail to add a new canonical design.
- **Stage 3.4 boundary recovery:** The corrected boundary-aware continuation
  opened `io_idt_pairs` 20→15→10. Five final designs were 10,10,10,10,11,
  leaving clear lower-bound pressure. A later 16k/32k continuation remained
  underoptimized: two of five seeds materially improved at 32k, including
  1.5967→0.7124 and 1.0994→0.8563. The coordinate boundary probe was treated
  as diagnostic rather than proof of a jointly re-optimized optimum.
- **Stage 3.4b finding:** The final extended study used eight cold seeds and
  opened `io_idt_pairs` to the hard lower bound of 8. At 256k it met the
  study's convergence evidence: 192k→256k produced no significant improvement
  in 8/8 seeds, grid convergence passed 8/8, no recovery/boundary condition
  remained pending, and the maximum recorded validation gap was about
  0.00119. Additional 384k/512k checkpoints or more seeds were judged
  unnecessary for this question.
- **Decision:** The poor 50 Ω `center_outer_same` result could no longer be
  attributed simply to insufficient Legacy-DE budget. Remaining work shifted
  to search-space design, correlated/redundant DOFs, mixed
  discrete/continuous parameterization, and optimizer efficiency. A finite
  convergence certificate still does not prove a global optimum.
- **References:** The former convergence guides, experiment descriptors, and
  `configs/studies/stage3_2*`–`stage3_4b*` files are recoverable from the
  annotated cleanup tag. The Stage 3.1/3.2/3.4 numeric review statements above
  were recovered from the project's prior ChatGPT review conversations on
  2026-09-09 through 2026-09-12.

## Stage 3.3–3.5 optimizer and search-space studies

**Evidence level:** Git-recoverable configs/experiment READMEs/frozen S1,
retained escalation history, and retrospectively recovered A/B review values.
Raw production-run availability is not established by Git.

- **Question:** Which optimizer backend and starting box give useful progress
  under a matched protocol?
- **Initial Stage 3.3 A/B was invalid:** L-SHADE did not consume the requested
  4,000 unique designs: the recovered review recorded median actual unique
  counts of about 1,162 for `center_outer_same` and 1,306 for
  `outer_ports`. A duplicate-handling path could terminate progress after a
  generation with no new unique design, and checkpoint budget had been coupled
  to the L-SHADE population-schedule terminal horizon. Treating B1000 as the
  terminal horizon shrank population from 126 to 4 with no later re-expansion.
  This result was rejected before any optimizer-quality conclusion.
- **Stage 3.3.1b corrected A/B:** With both backends matched at 4,000 unique
  evaluations, five `center_outer_same` seeds and one 8,555-point common
  validation grid, Legacy-DE recorded median/best maximum violation
  1.8313/1.7795 with seed IQR 0.0189 and one of five seeds at or below 1.8.
  L-SHADE recorded 1.8676/1.8341 with IQR 0.0245 and zero of five at or below
  1.8. Median per-seed global-search wall time was about 150 s for Legacy-DE
  and 193 s for L-SHADE; the five-process run was about 375 s. L-SHADE was not
  promoted from this short-budget gate.
- **Pre-production gate:** A/B performance evidence required at least 98%
  budget completion, frozen source hashes, common validation, parallel parity,
  and human review before production. Auto-bound was disabled during the
  optimizer-isolation A/B. Historical A/B output was not allowed to become a
  promotion result if those validity gates failed.
- **Stage 3.5 conditions:** Stage 3.5 crossed both backends with the frozen
  Stage 3.4b S0 box and a data-informed, boundary-expandable S1 initial box.
  Phase C used cold starts and development seeds 20260917–20260920. All four
  arms reached 16k and 32k; arm A always reached 64k, while only the 32k
  survivors continued to 64k. The L-SHADE schedule horizon was 64,000.
- **Interpretation:** The later apparent change in backend preference was not
  interpreted as intrinsic superiority. Historical and current L-SHADE traces
  were identical through 4,000 unique evaluations, then the current protocol
  exchanged adaptive frequencies at 4k while the historical trajectory used
  16k/32k/64k exchanges. This is a protocol/provenance mismatch. Later work
  uses L-SHADE because the later production protocol adopts it, not because the
  early 4k A/B proved universal superiority.
- **S1 meaning:** The frozen
  `artifacts/stage3_5/phase_a_revised/search_space_s1.yaml` is a 50 Ω
  experiment-specific starting box inside unchanged hard bounds. It is not a
  material-independent or all-impedance default. Recorded SHA-256:
  `26feb9ebe09b7f37d71cc96b74e83544065fc2c0d62e5e830b601cb3b3dc731f`.
- **Decision:** Phase C was the bounded matched development comparison.
  Phase D, the 192k/256k extension, impedance sweep, and productionization were
  deliberately not started automatically.
- **References:** Pre-deletion Stage 3.3/3.5 configs and descriptors are
  recoverable from the annotated tag; Stage 3.5 provenance decisions are in
  `reports/escalation_log.md`. The invalid/corrected Stage 3.3 numeric review
  statements were recovered from project conversations dated 2026-09-10.

## Stage 3.6 — 50 Ω DOF release and asymmetric ports

**Evidence level:** historical canonical run/review-bundle paths and source
commits are recorded. Because runs/artifacts are Git-ignored, their present
local availability must be verified separately.

- **Question:** Which geometry DOFs should be released at the 50 Ω reference,
  and do separately optimized source/load impedances change the result?
- **Conditions:** The reference is a 50/50 Ω DMS with the existing topology,
  evaluator, constraints, objective, validation grid, and L-SHADE backend.
- **Gate 1:** A dedicated Gate 1 numerical closeout could not be recovered
  from the current Git history, the pre-deletion tracked files, or the indexed
  project attachments searched on 2026-09-25. Do not reconstruct its exact
  metrics from later Gate 2A evidence. What is recoverable is the carry-forward:
  Gate 2A started from the reduced 50 Ω reference and evaluated section-class
  DOF releases without changing COM equations, objective, constraints, or
  validation semantics. Exact Gate 1 numeric claims remain **UNRECOVERED**.
- **Gate 2A:** Center pitch (`G1`), reflector pitch (`G2`), and center
  aperture (`G3`) were screened against the reduced baseline. G1 and G2 were
  promoted; G3 did not meet the promotion rule. Final confirmation used three
  paired seeds at 50/50 Ω: G2 median maximum violation was about 0.498331 and
  G1+G2 about 0.495384, with all runs still infeasible. G1+G2 became the
  production reference search space; G3, added left/right geometry
  asymmetry, material/COM releases, and topology alternatives remained
  deferred.
- **Gate 2B-B:** Used nine symmetric/asymmetric port pairs, three seeds, 32k
  unique evaluations per run, and a 9,113-point common grid.
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

**Evidence level:** the material profile and historical configs are
Git-recoverable; Stage 3.7B decisions remain in escalation history. Stage 3.7C
and 3.7D numerical conclusions below were recovered from the project's prior
review conversation and checked against the pre-deletion configs. Current
local run availability is unverified.

- **Question:** Can a source-grounded 42°YX-LiTaO3/Al COM model replace the
  hypothetical provider and support a B28 comparison?
- **Model:** The normalized literature profile is
  `LI2024_42YX_LT_METAL_UNSPECIFIED_T25`. Raw values are retained, and a
  no-fallback adapter prevents missing literature values from being silently
  supplied by M0. The paper does not establish enough source-device detail to
  certify native reconstruction; the 80 µm validation aperture is an explicit
  evaluation assumption, not reported source geometry.
- **Stage 3.7B/R1:** Algebraic normalization passed, but native
  resonator/source reconstruction remained inconclusive: the recovered review
  reports about 3.13% feature-scale error without a numeric digitized source
  feature. Phase sensitivity was not robust within 2% of resonance, so the
  fixed-design B28 sensitivity gate did not run at that point.
- **Stage 3.7C fast screen:** Applying the MLIT profile to the fixed M0
  geometry degraded maximum violation from about 0.504 to 82.08, worst IL from
  about 4.50 to 23.69 dB, and input/output VSWR from about 3.61/3.76 to
  207.7/91.6. Cold MLIT re-optimization recovered maximum violation to about
  1.0764 and 1.1293 for the two recorded seeds, but trajectories were still
  improving at the 8k checkpoint and therefore were not treated as converged.
  The optimized geometry moved strongly in a different direction, including
  gap ratio roughly 0.49→0.31 λ and aperture/λ roughly 20.6→29.9. The result
  established material-direction sensitivity, not a calibrated-material or
  production-performance claim.
- **Stage 3.7D aperture probe:** The pre-deletion config confirms a read-only
  two-seed probe at 150, 165, 180, and 200 µm with no optimizer rerun. The
  recovered review records seed 1 maximum violation
  1.0454→0.9019→0.8320→0.8837 and seed 2
  1.1170→1.0891→1.1201→1.1790. The 150 µm upper bound was therefore judged
  **active at a moderate level**, not inactive. 200 µm worsened both seeds;
  no third seed/further probe was considered necessary for this bound decision.
  The adopted MLIT aperture range for the next topology screen was 30–180 µm,
  while M0 remained 30–150 µm.
- **Decision:** Stage 3.7C/D supported using MLIT as a preliminary,
  evaluation-only comparison profile and proceeding to topology screening,
  while keeping FEM/measurement qualification on hold. Because M0 and MLIT use
  unequal aperture ranges and different model provenance, cross-material
  differences cannot be interpreted as pure material superiority.
- **Historical inconsistency corrected:** Later Stage 3.8-era decision text
  incorrectly described Stage 3.7D as recommending 30–150 µm and labeled
  30–180 µm as a later user override. The earlier Stage 3.7D review recovered
  on 2026-09-25 instead records `APERTURE_BOUND_ACTIVE_MODERATE` and adoption
  of MLIT 30–180 µm. This register uses that recovered closeout decision.
- **Unresolved:** Native electrode material, aperture, terminal/phase
  registry, and attenuation convention remain incomplete. No parameter
  mixing, B28 calibration, or FEM result resolves these gaps.
- **References:** Current material input
  `configs/models/stage3_7b_r1_normalized_literature_profile.yaml`;
  pre-deletion configs
  `configs/studies/stage3_7b_r2_stage3_7c_literature_com_b28_fast_screen.yaml`
  and
  `configs/studies/stage3_7d_mlit_aperture_boundary_and_metadata.yaml`.
  Historical expected run paths are
  `runs/stage3_7b_r2_stage3_7c_literature_com_b28_fast_screen_final_retry3`
  and
  `runs/stage3_7d_mlit_aperture_boundary_and_metadata_final`; their present
  local existence is not asserted here.

## Stage 3.8 / 3.8C — DMS topology screen

**Evidence level:** the canonical production run/review-bundle paths,
fingerprints, and closeout decisions are recorded. Their current local
availability is not established by Git and must be verified separately.

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
  cleanup tag. Historical canonical locations are
  `runs/stage3_8c_production_20260924`,
  `artifacts/review_bundles/stage3_8c_production_review.zip` and corrected
  closeout bundle `stage3_8c_production_closeout_corrected_review.zip`; their
  current local existence must be checked separately. The
  closeout report is preserved in the annotated cleanup tag. Frozen candidate
  fingerprint: `4465b7177b15ab44c10576a7c3d3bf0363c79a7dafa46ef8452a45626407824d`;
  recorded candidate commit: `f2babf340f7143e44db6af83f28e2324e724f6ed`.

## Stage 3.9 — selected 50 Ω DMS reference closeout

**Evidence level:** accepted 8k control, Stage 3.9A diagnosis, and C2C-accepted
16k extension with corrected persistence and prefix-parity verification.

- **Question:** Can the selected 50/50 Ω DMS reference recover a stable,
  feasible or credibly near-feasible design under the current model and
  search protocol?
- **Conditions:** MLIT/T1 symmetric five-IDT DMS; 50 Ω source and load; cold
  starts; seeds 20260917 and 20260918; 16,000 unique evaluations per seed;
  retained 8,000-evaluation population-schedule horizon; checkpoints every
  2,000 evaluations; common 9,113-point validation grid. The 0–8k prefixes
  match the accepted controls exactly.
- **Result:** At 16k, search max normalized violations were 0.428364 and
  0.430129. Common-grid maxima were 0.428503 and 0.430129. Both final designs
  passed geometry but failed filter feasibility. The two trajectories
  approached a similar empirical late plateau, with only 0.000002 and
  0.000301 improvement from 14k to 16k. Formal convergence fields remain
  incomplete (`grid_converged` and `micro_polish_improvement` are null).
  Stopband constraints at 703–748 MHz and 832–862 MHz dominate; no unresolved
  active search-bound or hard-geometry limitation was reported.
- **Decision:** Close Stage 3.9 under roadmap branch (b) for the selected
  MLIT/T1 50/50 Ω DMS reference path. Do not run another T1 budget extension.
  MLIT/T2 remains unresolved and unpromoted; it does not block this scoped
  closeout. Stage 4 may qualify fixed-50/50 Ω hybrid candidates.
- **Limits:** This is an engineering closeout of the tested reference path,
  not a proof of global physical or topological impossibility. It makes no
  material-superiority claim and does not establish that T2 or other future
  models/design spaces are infeasible. The model remains uncalibrated for
  production or real-device impedance claims. Formal convergence evidence is
  incomplete, so describe a late empirical plateau rather than verified
  convergence.
- **Review:** C2C closeout PLAN `c2c_stage39_close` iteration 1 and bounded Sol
  judgment are preserved in `reports/escalation_log.md`. Integrated C2C
  review iteration 2 accepted the scientific evidence and identified one
  roadmap baseline inconsistency; that correction is recorded in
  `reports/escalation_log.md`. C2C iteration 3 accepted the corrected
  closeout and confirmed Stage 3.9 closed under branch (b) for the selected
  MLIT/T1 path; no additional optimizer experiment is required.
- **References:** Closeout bundle
  `artifacts/review_bundles/stage3_9_closeout_20260927/`; Stage 3.9A bundle
  `artifacts/review_bundles/stage3_9a_search_viability_diagnosis/`; accepted
  Stage 3.9B bundle
  `artifacts/review_bundles/stage3_9b_budget_extension_review_corrected/`;
  run `runs/stage3_9b_mlit_t1_50ohm_budget_extension_20260927`, ID
  `20260927_053504_a62960`.

## Stage 4A — hybrid protocol qualification

**Status:** COMPLETED / finalized. **Evidence level:** implementation and
protocol qualification only; no scientific topology comparison.

- **Question:** Can the current MLIT/T1 DMS implementation compose with the
  existing one-port COM resonator representation under the established
  L-SHADE, unique-evaluation accounting, validation, provenance, checkpoint,
  and review-bundle contracts?
- **Scope and conditions:** MLIT/T1, 50/50 Ω, cold independent initialization,
  seed `20260929`, and 256 unique evaluations for each of `D`, `P_D`, `D_P`,
  and `P_D_P`. Search used 1,001 frequencies and common validation used 9,113
  frequencies. The combined row placement is a hypothetical separate-row
  approximation.
- **Topology / representation:** `D` is the T1 DMS control. `P_D`, `D_P`, and
  `P_D_P` compose one-port COM resonator shunts at their defined terminal
  nodes. The resonator remains the existing placeholder COM model; this result
  does not qualify its physical parameters.
- **Implementation introduced:** reusable hybrid composition and design-space
  support, the Stage 4A study/configuration, and qualification reporting and
  bundle support. Source files include `src/sawopt/core/hybrid.py`,
  `src/sawopt/problem/hybrid.py`, `src/sawopt/studies/hybrid.py`,
  `src/sawopt/reporting/hybrid_qualification.py`, and
  `configs/studies/hybrid_stage4a_qualification.yaml`.
- **Parity and smoke result:** D-only parity was exact, with maximum absolute
  difference `0.0` on both grids (`rtol=1e-10`, `atol=1e-12`). Each of the four
  smoke cells reached 256 unique evaluations, passed common-grid validation,
  and recorded zero physics failures. All four checkpoint streams were
  finalized.
- **Tests:** 36 focused regressions passed; the full suite passed 238 tests and
  20 subtests, with zero failures.
- **Decision:** the implementation and requested smoke protocol were accepted
  for this qualification scope. The historical C2C record is task
  `c2c_0b52`, iteration 2, `ACCEPT_STAGE4A`, with no mandatory findings. This
  preserves provenance only; C2C is now frozen and this acceptance is not a
  future project gate. Smoke metrics are non-scientific: they do not rank
  topologies, establish a feasible B28 filter, or select a preferred design.
- **Limitations:** one seed and 256 evaluations per cell are protocol smoke,
  not production comparison evidence. The COM profile is uncalibrated and the
  combined placement is hypothetical. No Stage 4B production comparison,
  ranking, or production optimum was established.
- **Carry-forward:** keep 50/50 Ω while Stage 4 hybrid qualification is
  planned; retain independent `Zs` and `Zl` controls and independently
  re-optimize each impedance pair in any later impedance study. Final
  asymmetric impedance conclusions remain premature until topology and the
  physical COM model are qualified. The next Stage 4 experiment plan is to be
  set separately after this documentation closeout.
- **Source provenance:** branch `codex/stage4a-hybrid-protocol`, closeout
  commit `eeda835f4341b664ac43564358a327000d455dd0`; closeout metadata records
  a clean tree and disposition `COMPLETED`. At documentation-closeout start,
  `origin/main` was `fb7bcbd8bddce6f9841798ce38557977a4345341` and did not
  contain this commit. The recorded experiment completion is distinct from
  integration into `main`.
- **Evidence location:** run
  `runs/stage4a-hybrid-protocol-qualification-final-c2c-iteration2`, including
  `metadata/run_completion.json`, `metadata/test_summary.json`,
  `metadata/d_only_parity.json`, and `metadata/c2c_review_status.json`; review
  bundle
  `artifacts/review_bundles/stage4a-hybrid-protocol-qualification-final-c2c-iteration2_review.zip`.
  Computation fingerprint (schema v2):
  `2120b2046bb424ec0445919ce1d4f6ca8c4de08e8b2d0b16a00d1e77d16cc3c2`.

## Stage 4B — hybrid topology production comparison

**Status:** COMPLETED / external review accepted. The execution disposition is
`STAGE4B_EXECUTION_ACCEPTED:TOPOLOGY_SELECTION_UNRESOLVED`. **Evidence level:**
matched-budget production comparison under the current provisional model; the
practical shortlist is `P_D` and `D_P`, with no unique topology selected.

- **Question:** Which fixed-50/50 Ω DMS + ladder hybrid topology should be
  carried forward under the current provisional MLIT/T1 model?
- **Production identity:** Run `20261003_014817_ea08db`; production execution
  source `c44798266067fa4b8b7d3b2873a798b7a1600ae8`; schema-v2 computation
  fingerprint
  `c63910623cb9a5d2a05ecb51f3685becf448f8ac91f169752f1b9703beef8464`.
  Later review and documentation commits do not replace this production source
  identity.
- **Conditions:** MLIT, `T1_SYMMETRIC_5IDT`, fixed 50/50 Ω, and exactly `D`,
  `P_D`, `D_P`, and `P_D_P`. The matched seeds were 20261002–20261006, giving
  20 independent cold-start cells at 24,000 unique decoded evaluations each
  (480,000 total). Checkpoints were 4k/8k/16k/24k under a terminal L-SHADE
  budget fixed at 24k from launch. Initial population followed one
  dimension-scaled rule, 18 × dimension (180/234/234/288 for `D`/`P_D`/`D_P`/
  `P_D_P`). Search used 1,001 points and common validation used 9,113 points.
  There was no warm start, historical population injection, parent transfer,
  or topology transfer.
- **Integrity and execution:** All 20/20 cells completed at 24,000 unique
  evaluations; the optimizer exited 0, the integrity check passed with no
  issues, and all cells share the same computation fingerprint and common-grid
  identity. Physics failures and common-validation physics failures were both
  zero. The production execution is accepted; no rerun is required.
- **Topology medians:**

  | Topology | Median max violation | Median sum violation | Median worst IL (dB) | Feasible seeds |
  | --- | ---: | ---: | ---: | ---: |
  | `D` | 0.406567 | 1.993734 | 3.231093 | 0/5 |
  | `P_D` | 0.380730 | 1.852516 | 3.486393 | 0/5 |
  | `D_P` | 0.387728 | 1.762396 | 3.460690 | 0/5 |
  | `P_D_P` | 0.406617 | 1.839262 | 3.614099 | 0/5 |

- **Matched-seed results:** `P_D` beat `D` 5–0; `D_P` beat `D` 5–0;
  `D_P` beat `P_D` 3–2; `P_D` beat `P_D_P` 4–1; `D_P` beat `P_D_P` 4–1;
  and `D` beat `P_D_P` 3–2. Total pairwise seed wins were `D_P` 12,
  `P_D` 11, `P_D_P` 4, and `D` 3. These paired results support `P_D` and
  `D_P` as a practical next-step shortlist, not a unique winner.
- **Formal versus external disposition:** The generated formal report was
  `STAGE4B_SHORTLIST_IDENTIFIED`, but its conservative IQR fallback retained
  all four topologies, so the formal shortlist did not reduce the candidate
  set. External review accepted the execution while leaving selection
  unresolved: `STAGE4B_EXECUTION_ACCEPTED:TOPOLOGY_SELECTION_UNRESOLVED`.
  `D` and `P_D_P` are de-prioritized for the next study, not globally rejected.
- **Convergence:** Stage 4B is matched-budget evidence, not a convergence
  certificate. Median maximum violation improved by approximately 15% (`D`),
  23% (`P_D`), 20% (`D_P`), and 20% (`P_D_P`) from 16k to 24k. Any longer
  study must predeclare a new L-SHADE terminal horizon and start cold; the 24k
  trajectories must not be reinterpreted under a changed horizon.
- **Constraint and bounds:** The dominant final constraint was `stop_2` in the
  832–862 MHz upper stopband, which requires 30 dB attenuation. Broad bound
  saturation was not observed; the terminal bound-pressure evidence contains
  one upper-bound hit on `resonator_0_pairs`. This does not establish global
  bound optimality.
- **Direction sanity:** The `P_D`/`D_P` direction check passed. The worst-IL
  difference changed sign across seeds, with median `P_D - D_P` about
  +0.0257 dB. There is no stable directional preference at 50/50 Ω, so both
  remain relevant to future `Zs != Zl` work; Stage 4C also left their selection
  unresolved.
- **`P_D_P` disposition:** It had 4,332 geometry rejections, versus 95 for
  `D`, 103 for `P_D`, and 113 for `D_P`. It showed no median max-violation
  advantage over `P_D`/`D_P` and lost 4–1 to each shortlisted topology. It is
  de-prioritized under this protocol, not globally inferior.
- **Limits:** Findings are conditional on the provisional MLIT profile,
  `T1_SYMMETRIC_5IDT`, current resonator/hybrid representation, current
  geometry model, and fixed 50/50 Ω ports. They do not establish calibrated
  real-device prediction, physical B28 feasibility, a final topology optimum,
  or a final impedance optimum.
- **Carry-forward at Stage 4B closeout:** Stage 4C was planned as a matched
  convergence/budget qualification for `P_D` and `D_P`; its execution and
  disposition are recorded below. The final `Zs × Zl` sweep remains gated.
- **Evidence:** The compact Git-tracked review bundle is at
  `reports/stage4b_production_review/20261003_20261003_014817_ea08db/`; the
  closeout is `docs/history/stage4b_closeout_20261004.md`, with current
  decisions in `docs/history/current_baseline.md` and forward gates in
  `docs/project_roadmap.md`. The large raw run and checkpoints remain local at
  `runs/stage4b-hybrid-topology-production-20261003`.

## Stage 4C — shortlisted hybrid convergence / budget qualification

**Status:** Execution completed; topology selection unresolved. The
orchestration/review state is `REVIEW_WAITING`; this documentation closeout
does not record scientific acceptance or select a topology. **Evidence
level:** matched-seed production evidence under the provisional MLIT/T1 model
at fixed 50/50 Ω.

- **Question:** Do shortlisted `P_D` and `D_P` retain a relative advantage at a
  longer search horizon, and does either approach a stable near-feasible
  region?
- **Production identity and conditions:** Run `20261006_124153_ed50ba`, study
  `hybrid_stage4c_confirmatory`, protocol revision `stage4c_confirmatory_v1`,
  production source
  `65e1815db1cc18d74ff0dcee20ffd5e9098709df`, computation fingerprint
  `fdff19b63739efe1022092aa21e2ba3651c82a3344d54721522e5e0fc5cef9dd`. The
  study compared `P_D` and `D_P` with MLIT / `T1_SYMMETRIC_5IDT` and fixed
  50/50 Ω ports. Five matched cold-start seeds were used:
  20261007–20261011. Each of 10 cells received 96,000 unique evaluations
  (960,000 across the matrix), with checkpoints at 8k, 16k, 24k, 32k, 48k,
  64k, 80k, and 96k. Search used 1,001 frequencies and common validation used
  9,113 points. There was no early stop, warm start, parent/topology transfer,
  or historical population injection.
- **Execution and integrity:** The optimizer state is `COMPLETED` and the
  orchestration state is `REVIEW_WAITING`. All 10/10 cells completed at budget;
  integrity is `PASS`, and all final checkpoints were finalized. The recorded
  process exit code is null/unknown and is not inferred. The compact review
  package was reconciled from existing durable evidence; no cell was rerun and
  no raw result or checkpoint was changed.
- **Feasibility and comparison:** Feasible cells were `P_D` 0/5 and `D_P` 0/5.
  Terminal matched-seed lexicographic wins were `P_D` 3, `D_P` 2, with no ties
  or indeterminate comparisons. The predeclared clear-winner rule requires at
  least 4/5 wins, so neither topology passed. Median maximum normalized
  violation was 0.330295 for `P_D` and 0.323618 for `D_P`. The formal
  classification is `STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`.
- **Convergence and maturity:** All 10/10 terminal cells are
  `IMMATURE_OR_INCOMPLETE`; each improved significantly from 80k to 96k.
  Consequently this budget does not establish a converged terminal result.
- **Boundary diagnostics:** Terminal unresolved hard-bound hits were an upper
  hit on `resonator_0_pairs` for `P_D` / seed 20261007 and `D_P` / seeds
  20261007 and 20261009. Other historical or non-terminal hits are not counted
  as unresolved terminal hits.
- **Implementation provenance:** The production path used compact history
  retention (`compact_history_cache=True`) and 16 historical finalists.
  L-SHADE checkpoint state version 4 and its compact-checkpoint MemoryError
  fix are already in `main` (the fix is present at commit `1acd381`). These
  implementation facts were checked read-only; no source or test files were
  changed for closeout.
- **Decision and limits:** Do not promote `P_D` or `D_P`; retain both for later
  asymmetric `Zs != Zl` work. The 0.02 maximum normalized violation threshold
  is an internal computational interpretation threshold, not a manufacturing
  or measurement tolerance. The result is conditional on the provisional
  literature COM profile, topology/model implementation, fixed 50/50 Ω ports,
  and existing bounds. It does not establish physical B28 feasibility,
  manufacturability, model calibration, or an impedance optimum. No additional
  production authorization follows. Budget extension, bound changes, and
  model/design-space changes require a separate review and plan.
- **Evidence:** Canonical compact Git-tracked package:
  `reports/experiment_reviews/stage4c/20261006_124153_ed50ba/`. It includes
  `README.md`, run and review manifests, integrity and completion records,
  per-cell results, and summary reports. The external raw run and checkpoints
  remain outside the repository.

## Cleanup rule

At each future study closeout, add the result and decision here, update
`current_baseline.md` only when a result changes an adopted assumption, and
then decide whether experiment-specific implementation, config, and tests can
leave the active tree. Keep raw runs and review bundles at their recorded
locations. The pre-deletion tag is the canonical source for removed historical
files; it does not replace the scientific summaries in this register.
