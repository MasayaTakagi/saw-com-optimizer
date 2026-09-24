# Stage 3.8C-R1 Geometry Gate Root Cause

## Finding

The Stage 3.8C ranking mixed a hard manufacturing gate with filter constraint
violations in one `max_violation` scalar. That allowed a design outside a hard
geometry limit to beat a manufacturable design whose filter metrics were poor.
The geometry-invalid design was returned before COM/network evaluation, so the
winner did not have filter metrics at all.

## Code path

1. `src/sawopt/studies/stage3_8_dual_material_dms_topology_fast_screen.py`,
   `evaluate_topology_design`, evaluates `core.metrics.geometry` and returns
   `_invalid_record` as soon as any hard geometry violation is positive. It
   does not call `simulate_topology`, network conversion, or `measure` on that
   path.
2. `_invalid_record` inserts the geometry violation into the ordinary
   `violations` mapping, derives `max_violation` and `sum_violation` from it,
   sets absent filter metrics (`worst_il_db` and `ripple_db`) to infinity, and
   has no `evaluation_status` that distinguishes geometry rejection from a
   physics evaluation.
3. `src/sawopt/optimizers/selection.py`,
   `FeasibilityFirstComparator.rank_key`, ranks all infeasible records first by
   `(max_violation, sum_violation)`. Consequently, for example, a geometry
   violation of `1e-8` beats a geometry-valid filter violation of `0.8`.
4. Stage 3.8 passes `DEFAULT_COMPARATOR` to `LShadeBackend`; that comparator
   drives population order, trial replacement, incumbent updates, and stored
   best-so-far rank keys. The R1 final selector must use the same geometry-first
   policy as these optimizer paths.
5. `LShadeBackend.initialize` builds a uniform population and evaluates every
   member without a geometry-validity filter. The known fixed designs used by
   Stage 3.8 fixed-design sanity are not supplied to optimizer initialization.
6. Stage 3.8 result/report adapters default missing physics counters to zero,
   so those zeros were not measurements.

## Confirmation from the invalidated Stage 3.8 run

The existing review bundle records 96,000 nominal unique evaluations over 12
material/topology/seed cells. Every final cell has
`valid_physics_evaluations=0` and `solved_frequency_points=0`; the output
summary has no usable filter metrics. The previous T0/T1/T2 proxy orderings
are therefore invalid for topology promotion and must not be reused.

The Stage 3.8 fixed-design sanity records remain separate evidence that the
validated topology physics can reach the COM/network evaluator. The R1 rerun
must retain those topology definitions and correct the geometry/objective
integration only.

## Related bound provenance discrepancy

The current R1 handoff requests MLIT aperture search bounds of 30–180 um. The
saved Stage 3.7D recommendation CSV and summary record 30–150 um and label it
`STAGE3_8_READY_APERTURE_150`; the prior Stage 3.8 escalation log also records
30–150 um. The current R1 request is newer and explicitly asks for 180 um, but
that difference must be called out in the R1 metadata and review. It must not
be described as the recorded Stage 3.7D recommendation unless that source is
corrected by an auditable new decision.

## Required correction boundary

Geometry validity must be a first-level rank condition that always precedes
filter feasibility/performance. A geometry rejection must carry an explicit
status and hard-constraint diagnostics, with no fabricated filter metrics.
Geometry-valid evaluations must be counted separately from successful physics
evaluations, physics failures, cache hits, and solved frequency points. The
counter accounting identity must be tested before any pilot is accepted.

This report captures the pre-fix diagnosis; the reviewer decision and R1
validation results are recorded separately.
