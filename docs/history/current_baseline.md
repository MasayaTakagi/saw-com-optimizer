# Current SAW Design Baseline

This is the current decision state after Stage 4A (baseline date
2026-10-02). Read `experiment_register.md` for the evidence and limitations
behind each item.

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
- FEM or measurement extraction is still needed to establish material
  parameters and device-specific loss. A 2026-09-25 retrospective recovery of
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

## Stage 4A hybrid software baseline

- Stage 4A is completed and finalized. The reusable hybrid implementation and
  its 50/50 Ω qualification workflow are available as a software baseline.
- D-only parity and the focused/full regression validations passed; the four
  bounded smoke cells completed. These results qualify implementation and
  protocol behavior only. They do not establish a feasible B28 filter, rank
  the hybrid topologies, or identify a production optimum.
- A Stage 4B production comparison has not been run. The next Stage 4
  experiment plan is intentionally left open for separate planning.
- Continue hybrid qualification at fixed 50/50 Ω. Keep the final asymmetric
  impedance sweep premature until topology is stable and the COM/material
  model has been physically qualified. Preserve independent source/load
  control and independently re-optimize the filter for every impedance pair.

## Current unresolved work

1. Obtain calibrated COM parameters from measurement or FEM and resolve the
   MLIT source-data gaps.
2. Either align material search bounds before comparing M0 and MLIT, or keep
   cross-material conclusions explicitly conditional on the current M0
   30–150 µm versus MLIT 30–180 µm ranges.
3. Keep MLIT/T2 explicitly unresolved; do not promote it on underexplored
   status alone. Any future T2 study is a separate, matched-budget question.
4. Continue DMS-plus-ladder hybrid qualification at fixed 50/50 Ω under the
   hypothetical model, while keeping physical model qualification in view.
5. A future impedance sweep must use independent inner optimizations per
   impedance and retain asymmetric source/load interfaces. The historical
   coarse screens are not a substitute, and impedance conclusions require a
   calibrated COM model.

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
