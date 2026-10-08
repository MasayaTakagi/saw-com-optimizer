# Current SAW Design Baseline

This is the current scientific and software decision state after Stage 4C
(baseline date 2026-10-08). The project goal was revised on 2026-10-08 to
general constrained design optimization using supplied COM inputs, Smith
heatmaps of independently re-optimized impedance conditions, and practical
runtime. Physical COM calibration is no longer a roadmap requirement; correct
units/numerics and explicit design constraints remain required. See
`../project_roadmap.md` for the new plan and `experiment_register.md` for
historical evidence and limitations.

## Physical model

- Use SI internally where applicable and retain the repository COM convention:
  `exp(+jωt)`, propagation left-to-right, power-normalized acoustic waves, and
  dimensional COM quantities in the solver.
- `M0` is a hypothetical `FixedProvider`; it is not a calibrated material
  model.
- `MLIT` is the normalized literature profile
  `LI2024_42YX_LT_METAL_UNSPECIFIED_T25`. It is evaluation-only. Missing
  source-device geometry, terminal/phase registry, and loss details prevent a
  production-qualified or native-device claim. The profile must not borrow
  missing values from M0.
- FEM or measurement extraction would be needed to make claims about real
  device-specific parameters or loss, but it is **not a prerequisite** for the
  revised given-COM optimization tool. A 2026-09-25 retrospective recovery of
  the Stage 3.7D closeout corrected the aperture lineage: the 150 µm MLIT upper
  bound was judged moderately active, a no-rerun probe at 150/165/180/200 µm
  supported adopting 30–180 µm for the next topology screen, and 200 µm was
  not adopted. M0 remained 30–150 µm. Treat cross-material comparisons as
  confounded until bounds and material provenance are aligned.

## DMS representation

- T0: current three-IDT DMS reference.
- T1: mirrored `R-A-B-C-B-A-R` five-IDT chain with signed electrical mapping
  `[+,-,+,-,+]`.
- T2: two parallel three-IDT tracks; add their unterminated two-port Y
  matrices, then apply a single source/load termination. Split total aperture
  evenly between tracks.
- Topology validation covers T0 parity, T1 finite/passive/reciprocal behavior,
  and the T2 parallel identity. The reusable topology implementation is in
  `src/sawopt/problem/dms_topologies.py`; the released T0 design record and
  simulator are in `src/sawopt/problem/released_dms.py`.
- The 50 Ω `center_outer_same` DMS and the Stage 3.6 G1+G2 (`center` and
  reflector pitch) release form the historical reference. The exact numerical
  Gate 1 closeout is unrecovered and should not be reconstructed from later
  evidence. Gate 2A promoted center pitch and reflector pitch, while center
  aperture did not pass the individual promotion rule.

## Optimization and comparison

- The current DMS topology study uses L-SHADE with unique decoded designs as
  the search budget. Preserve deterministic seeds, checkpoint schedule, and
  geometry accounting when interpreting or continuing a run.
- The current DMS study uses a geometry-first comparator: any geometry-valid candidate
  precedes a geometry-rejected candidate; successful physics precedes physics
  failure; valid physics records retain the established metric comparator.
- Its initializer uses independent uniform proposals followed by geometry
  rejection and resampling. It does not repair invalid designs.
  Rejection fraction is diagnostic for R1.2, not a pilot gate.
- Do not infer optimizer superiority from the old Legacy-DE/L-SHADE A/B. The
  first Stage 3.3 comparison was invalid because L-SHADE did not consume the
  requested unique-design budget; the corrected 4k A/B favored Legacy-DE
  modestly under that short protocol, while the later Stage 3.5 parity audit
  found an adaptive-frequency timing mismatch between historical and current
  L-SHADE trajectories. The historical S1 box is experiment-specific and is
  not a default for other impedances.

## 50 Ω and port-impedance findings

- Keep 50/50 Ω as the comparison reference. Separate `Zin` and `Zout` controls
  remain necessary because the DMS can be asymmetric.
- The Stage 3.6 asymmetric fast screen had no feasible candidates and too few
  seeds/checkpoints to select an optimum port pair. Its 62.5/62.5 Ω mechanical
  ranking is not an impedance recommendation.
- The Stage 3.8C production screen optimized each material/topology cell for
  8,000 unique evaluations per seed, across two seeds. It produced no
  filter-feasible design. The lowest median maximum violation was 0.504066 for
  M0/T0; the lowest MLIT value was 0.492134 for MLIT/T1. Treat both only as
  screening clues under their own model and search bounds.
- No claim is made that 45 Ω, 50 Ω, or 62.5 Ω is the real-device optimum.
  Re-optimize the filter independently at every impedance in any future sweep.
- Stage 3.9 closed under roadmap branch (b) for the selected MLIT/T1 50/50 Ω
  DMS reference path. Two accepted 16k trajectories plateaued empirically near
  maximum normalized violation 0.43 and remained materially infeasible on the
  common grid. T2 remains unresolved and unpromoted; this is not a global
  impossibility result. See the Stage 3.9 closeout in the experiment register.

## Stage 4 hybrid baseline

- Stage 4A is completed and finalized. Its D-only parity, focused/full
  regression validation, and bounded smoke cells qualify the reusable hybrid
  implementation and protocol behavior; they are not scientific ranking
  evidence.
- Stage 4B production run `20261003_014817_ea08db` is complete and its
  execution/integrity are accepted. The exact production source was
  `c44798266067fa4b8b7d3b2873a798b7a1600ae8`, and all 20 cells
  (4 topologies × 5 matched seeds) completed 24,000 unique evaluations on the
  common 9,113-point validation grid with one computation fingerprint.
- No Stage 4B topology was filter-feasible: every topology finished at 0/5
  feasible seeds. The formal production report returned
  `STAGE4B_SHORTLIST_IDENTIFIED`, but its conservative IQR rule retained all
  four topologies and therefore did not produce a unique scientific winner.
- External review adopts the practical shortlist `P_D` and `D_P`.
  `D` and `P_D_P` are de-prioritized for the next experiment but are not
  globally rejected. Matched-seed lexicographic wins were 12 for `D_P`, 11 for
  `P_D`, 4 for `P_D_P`, and 3 for `D`; `P_D` versus `D_P` remained split 2–3.
- The dominant remaining violation is usually `stop_2`, corresponding to the
  832–862 MHz upper stopband. Broad active-bound saturation was not observed;
  the terminal bound-pressure summary contained only one upper-bound hit on
  `resonator_0_pairs`.
- Stage 4B is a matched-budget comparison, not a convergence certificate.
  Median maximum violation still improved materially from 16k to 24k for all
  four topologies, so 24k must not be treated as a converged terminal budget.
- The predeclared `P_D`/`D_P` direction sanity check passed. Worst-IL
  differences changed sign across matched seeds and the median difference was
  only about +0.0257 dB (`P_D - D_P`), much smaller than the within-topology
  five-seed spans. Do not infer a stable 50/50 Ω input-side versus output-side
  resonator preference.
- Stage 4C production run `20261006_124153_ed50ba` completed under source
  `65e1815db1cc18d74ff0dcee20ffd5e9098709df` and protocol
  `stage4c_confirmatory_v1` (computation fingerprint
  `fdff19b63739efe1022092aa21e2ba3651c82a3344d54721522e5e0fc5cef9dd`). It
  compared `P_D` and `D_P` at MLIT/T1 and fixed 50/50 Ω, using five matched
  cold-start seeds (20261007–20261011), 96,000 unique evaluations per cell,
  and common 9,113-point validation. The optimizer state is `COMPLETED`; the
  orchestration state is `REVIEW_WAITING`. All 10/10 cells completed, integrity
  is `PASS`, and all final checkpoints were finalized. The compact Git-tracked
  evidence is
  `reports/experiment_reviews/stage4c/20261006_124153_ed50ba/`.
- No Stage 4C cell was feasible (`P_D` 0/5, `D_P` 0/5). Terminal matched-seed
  lexicographic wins were `P_D` 3 and `D_P` 2; neither met the 4/5 clear-winner
  gate. The classification is
  `STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`; neither topology is selected.
- All 10 terminal cells are `IMMATURE_OR_INCOMPLETE`, and all 10 improved
  significantly from 80,000 to 96,000 evaluations. Terminal unresolved upper
  hits on `resonator_0_pairs` occurred for `P_D` / seed 20261007 and `D_P` /
  seeds 20261007 and 20261009. The results therefore do not establish
  convergence or a credible near-feasible region. The 0.02 maximum normalized
  violation threshold is an internal computational interpretation threshold,
  not a manufacturing or measurement tolerance.
- Read-only source review confirmed the Stage 4C production path used
  `compact_history_cache=True`, retained 16 historical finalists, and used
  L-SHADE checkpoint state version 4. The compact-checkpoint memory fix is
  already present in `main` (commit `1acd381`); it was not reimplemented for
  this closeout.
- Keep topology selection unresolved and retain both `P_D` and `D_P` as
  candidates for future asymmetric `Zs != Zl` re-optimization. The Smith
  map of re-optimized complex impedance conditions has not started. Its new
  prerequisites are diagnosis of optimizer/constraint limitations, reliable
  design optimization, consistent complex-port numerics, and measured resource
  feasibility, **not COM calibration**. The historical Stage 4C closeout
  authorized no budget extension, bounds change, or further production run.

## Revised objective and current unresolved work

- **Accepted probe evidence:** The Stage 4C resonator-pairs coordinate probe
  is now recorded in
  [stage4c_resonator_pair_coordinate_probe.md](stage4c_resonator_pair_coordinate_probe.md).
  Five selected baselines reproduced existing values; 22 points were
  geometry-valid under probe-only assumptions; all 15 points above 60
  improved stop_2, but only one improved max violation (by 0.00486).
  Disposition is MIXED_BOUND_SIGNAL, not permission to enlarge frozen bounds,
  launch production, or promote either topology. Its earlier call to prioritize
  physical COM qualification was conditional on the old goal and is superseded.

1. **Stage 5A priority:** Audit 50/50-ohm objective/numerics, mixed-variable
   optimizer, budget/seed behavior and late convergence. Distinguish optimizer,
   geometry/area, bounds and model/topology causes; none has been proven primary.
2. Characterize the practical quality/time envelope of generic full-space
   optimization **before** reducing degrees of freedom or running new long
   horizons. Historical Stage 4C checkpoints are not independent shorter runs.
3. Investigate classical SAW synthesis for physically guided initialization
   and hierarchical optimization; compare against full-space generic baselines
   and preserve a fallback for arbitrary user-supplied COM parameters.
4. Unify configurable COM/spec/area/geometry/port inputs and extend the
   real-positive-only network evaluation to passive complex source/load.
5. Build Smith heatmaps from a new design optimization at **each impedance
   condition**; a fixed-geometry termination map is not a final feature.
   Measure runtime/memory, dense-grid quality and seed dispersion as first-class
   outputs. Historical M0 versus MLIT bounds and MLIT/T2 limitations remain
   model-specific; no unwarranted material superiority claims.

## Active software boundaries

- `core/`: COM, network, metrics, and physical material calculations.
- `problem/`: reusable geometry and topology definitions.
- `problem/released_dms.py`: reusable released-design representation and T0
  simulation.
- `studies/dms_topology_common.py` and
  `studies/dms_topology_screening.py`: current DMS study helpers and adapter.
- `studies/lshade_records.py`: shared L-SHADE checkpoint record serialization.
- `optimization/convergence_evidence.py`: checkpoint evidence derivation used
  by study record serialization.
- `optimizers/`: L-SHADE, SciPy DE, and candidate ranking primitives.
- `optimization/`: budget, accounting, population, cache, and search mechanics.
- `studies/`: experimental protocols and their configuration adapters.
- `io/`, `reporting/`, and `orchestration/`: persistence, review artifacts,
  and detached execution lifecycle.

Historical study runners and their old configs/tests have been removed from
the active tree. The pre-cleanup annotated Git tag
`archive/pre-historical-deletion-2026-09-25` preserves their exact source for
inspection; the experiment register retains the findings and decisions needed
for current work.

## Workflow / review infrastructure

C2C is frozen and is no longer a project progression dependency. Meaningful
repository work uses the GitHub-mediated external review process documented in
[`../guides/github_review_workflow.md`](../guides/github_review_workflow.md).
This workflow decision does not change the scientific baseline above.
