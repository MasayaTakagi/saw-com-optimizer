# Escalation Packet — Stage 3.8C-R1 Geometry Gate

## Requested reviewer

GPT-5.6 Sol, judgment only. Do not edit files, implement code, or run tests.

## Decision needed

Review the safest minimal ranking and counter design for Stage 3.8C-R1 so a
geometry-invalid candidate can never outrank a geometry-valid candidate, while
the validated T0/T1/T2 topology implementations and production L-SHADE algorithm
remain unchanged. Also resolve how to record the MLIT aperture bound discrepancy
described below.

## Evidence from the current repository

- `src/sawopt/studies/stage3_8_dual_material_dms_topology_fast_screen.py`,
  `evaluate_topology_design`: calls `core.metrics.geometry`; for any positive
  manufacturing violation it returns `_invalid_record` before calling
  `simulate_topology`, network conversion, or filter metrics.
- `_invalid_record` places geometry and numerical failure into the same
  `violations` mapping, sets `max_violation` from those values, fabricates
  `worst_il_db` and `ripple_db` as infinity, and sets scalar `objective` to
  infinity. It has no explicit `evaluation_status`.
- `src/sawopt/optimizers/selection.py`, `FeasibilityFirstComparator.rank_key`:
  all infeasible records rank by `(1, max_violation, sum_violation, worst_il,
  ...)`. Therefore a geometry-invalid candidate with a tiny geometry violation
  can beat a geometry-valid candidate with a larger filter violation.
- Stage 3.8 passes `DEFAULT_COMPARATOR` into `LShadeBackend`. The comparator is
  used for population ordering, trial replacement, incumbent updates, and
  best-so-far traces. The Stage 3.8 reporting selector also uses common rank
  semantics.
- `LShadeBackend.initialize` creates a uniform population by default and calls
  the evaluator for each member. Stage 3.8's known fixed designs are used in
  fixed-design sanity only; they are not inserted into optimization starts.
- Stage 3.8 `lshade_record` does not measure the requested geometry/physics
  counters; study reporting uses `record.get(..., 0)` for missing counters.
- Prior Stage 3.8 review bundle reports 96,000 nominal unique evaluations,
  `valid_physics_evaluations=0` and `solved_frequency_points=0` in all 12 cells;
  the final geometry-only ordering was explicitly deemed invalid for topology
  comparison.
- Existing geometry constraints in `configs/base/b28_dms_baseline.yaml` are
  max length 750 um, max width 250 um, minimum electrode width/gap 0.8 um,
  and maximum 500 electrodes. Search bounds live separately in the Stage 3.8
  topology config.

## Conflicting aperture provenance

The active R1 user-provided handoff says to restore MLIT aperture bounds to
30–180 um, stating this is the Stage 3.7D recommendation. However, the saved
Stage 3.7D CSV and summary in
`runs/stage3_7d_mlit_aperture_boundary_and_metadata_final/` explicitly record
MLIT 30–150 um and `STAGE3_8_READY_APERTURE_150`. The prior Stage 3.8 Sol
decision in `reports/escalation_log.md` also says to use 30–150 um for both
materials. The current user has explicitly asked to start the newer R1 handoff,
which calls for 180 um. Recommend how to preserve traceability and comparison
validity; do not silently change the bound.

## Proposed direction for review

1. Use an explicit geometry status / hard-feasibility rank prefix separate
   from filter-feasibility metrics, with geometry violation used only to order
   geometry-invalid candidates. Physics failure should also be explicit and
   must not use fabricated filter metrics.
2. Ensure the same rank policy drives L-SHADE parent replacement, incumbent,
   checkpoint selection, and final common-grid selection.
3. Start each cell with its known geometry-valid fixed-design seed and fill the
   rest of the initial population by bounded rejection sampling. Record sampling
   attempts separately from objective-budget evaluations, and make counter
   semantics explicit so the requested accounting identities remain valid.
4. Wrap only the Stage 3.8C-R1 study if possible, avoiding global changes to
   L-SHADE or prior comparator behavior.

Please identify any flaw in this direction, especially whether the existing
comparator API can support the R1 rank policy without changing protected
optimizer behavior, and whether the proposed counter split is auditable.
