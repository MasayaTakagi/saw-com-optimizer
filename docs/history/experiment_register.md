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

**Evidence level:** implementation validation, D-only parity, four bounded
protocol smoke cells, full regression output, and C2C acceptance are recorded
under the current Stage 4A run and review bundle.

- **Question:** Can the current MLIT/T1 DMS path compose with the existing
  one-port COM resonator model under the current L-SHADE, unique-evaluation,
  validation, provenance, checkpoint, and review-bundle contracts?
- **Conditions:** MLIT/T1, 50/50 Ω, cold independent initialization, seed
  `20260929`, 256 unique evaluations for each of `D`, `P_D`, `D_P`, and
  `P_D_P`; 1,001-point search grid and shared 9,113-point validation grid.
- **Qualification result:** D-only parity was exact (maximum absolute
  difference 0.0). Each smoke cell reached its 256-unique budget, completed
  common-grid validation, and recorded zero physics failures. Focused
  regressions passed 36/36; the full suite passed 238 tests and 20 subtests.
  C2C accepted Stage 4A at iteration 2; the accepted closeout then transitioned
  the run to `COMPLETED`, finalized all four checkpoint streams, and refreshed
  the lifecycle evidence in the review bundle. Schema-v2 computation fingerprint:
  `2120b2046bb424ec0445919ce1d4f6ca8c4de08e8b2d0b16a00d1e77d16cc3c2`.
- **Decision:** C2C task `c2c_0b52`, iteration 2, accepted Stage 4A with no
  mandatory remaining findings. The protocol is qualified for the requested
  implementation/smoke scope only. These smoke metrics are explicitly
  non-scientific and do not rank topology families or establish a preferred
  design.
- **Stage 4B boundary:** Do not launch Stage 4B from this qualification. The
  measured estimate for four topologies × two seeds × 4,000 unique evaluations
  is 0.56 hours centrally (0.42–0.84 hours), which invokes the managed
  long-running production path. A separate task must resolve comparison
  fairness for 10/13/13/16-dimensional families, add and validate supported
  orchestration dispatch, obtain Sol's budget judgment, and pass C2C
  pre-launch review.
- **References:** Run
  `runs/stage4a-hybrid-protocol-qualification-final-c2c-iteration2`;
  review bundle
  `artifacts/review_bundles/stage4a-hybrid-protocol-qualification-final-c2c-iteration2_review.zip`.
  Neither smoke response values nor this protocol qualification constitute a
  scientific topology comparison.

## Cleanup rule

At each future study closeout, add the result and decision here, update
`current_baseline.md` only when a result changes an adopted assumption, and
then decide whether experiment-specific implementation, config, and tests can
leave the active tree. Keep raw runs and review bundles at their recorded
locations. The pre-deletion tag is the canonical source for removed historical
files; it does not replace the scientific summaries in this register.
