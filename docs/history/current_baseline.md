# Current SAW Design Baseline

This is the current decision state after the registered experiments. Read
`experiment_register.md` for the evidence and limitations behind each item.

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
  parameters and device-specific loss. The recorded Stage 3.7D MLIT aperture
  recommendation is 30–150 µm; Stage 3.8's 30–180 µm range was a later
  user-directed override. Treat cross-material comparisons as confounded
  until bounds and material provenance are aligned.

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
  reflector pitch) release form the historical reference. Gate 2A did not
  promote center aperture by itself.

## Optimization and comparison

- Later topology studies use L-SHADE with unique decoded designs as the search
  budget. Preserve deterministic seeds, checkpoint schedule, and geometry
  accounting when interpreting or continuing a run.
- Stage 3.8C uses a geometry-first comparator: any geometry-valid candidate
  precedes a geometry-rejected candidate; successful physics precedes physics
  failure; valid physics records retain the established metric comparator.
- Stage 3.8C's current initializer is independent uniform proposals followed
  by geometry rejection and resampling. It does not repair invalid designs.
  Rejection fraction is diagnostic for R1.2, not a pilot gate.
- Do not infer optimizer superiority from the old Legacy-DE/L-SHADE A/B where
  adaptive-frequency exchange timing was not matched. The historical S1 box is
  experiment-specific and is not a default for other impedances.

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

## Current unresolved work

1. Obtain calibrated COM parameters from measurement or FEM and resolve the
   MLIT source-data gaps.
2. Align material search bounds before comparing M0 and MLIT.
3. Improve feasible search coverage without changing geometry constraints or
   distributions without review; no filter-feasible Stage 3.8C design exists.
4. Keep DMS-plus-ladder hybrid work as a candidate because it improved the
   recorded 50 Ω hypothetical-model result, while recognizing the target still
   failed.
5. A future impedance sweep must use independent inner optimizations per
   impedance and retain asymmetric source/load interfaces. The historical
   coarse screens are not a substitute.

## Active software boundaries

- `core/`: COM, network, metrics, and physical material calculations.
- `problem/`: reusable geometry and topology definitions.
- `studies/dms_topology_common.py`: current DMS study adapter helpers. It does
  not import a Stage 3.6 or Stage 3.8 runner.
- `studies/lshade_records.py`: shared L-SHADE checkpoint record serialization.
- `optimizers/`: L-SHADE, SciPy DE, and candidate ranking primitives.
- `optimization/`: budget, accounting, population, cache, and search mechanics.
- `studies/`: experimental protocols and their configuration adapters.
- `io/`, `reporting/`, and `orchestration/`: persistence, review artifacts,
  and detached execution lifecycle.

The historical cleanup is removing Stage-number-only workflows while
preserving these current responsibilities and the evidence in
`experiment_register.md`.
