# Escalation Packet: Historical Cleanup Architecture Boundaries

Date: 2026-09-25

## Requested review

Provide a bounded architecture judgment for the first cleanup extraction.
Recommend the smallest ownership map that removes current Stage 3.8/3.8C
runtime dependencies on historical Stage modules while preserving current
numerical behavior and serialized result semantics. Do not implement changes.

## Repository state

- Work branch: `codex-historical-cleanup`
- Freeze commit: `444d3a430797d32d688f74bb76ffda615cddfba0`
- Annotated freeze tag: `archive/pre-historical-cleanup-2026-09-25`
- Baseline: `.venv\Scripts\python.exe -m pytest` — 288 passed; one harmless
  pytest cache write warning.
- The supplied historical cleanup plan asks to extract shared Stage 3.8
  dependencies before deleting historical Stage code.
- An earlier architecture cleanup already created
  `src/sawopt/problem/dms_topologies.py`; avoid duplicating that work.

## Observed code boundaries

1. `problem/dms_topologies.py` owns reusable DMS section and topology
   structures, including the T0/T1/T2 simulation path.
2. `studies/stage3_8_dual_material_dms_topology_fast_screen.py` imports that
   canonical topology code, but also imports the following from
   `studies/stage3_6_gate2a.py`:
   - `ReleasedFilterDesign`
   - `release_schema`, `release_bounds`, and `decode_release`
   - `simulate_released_filter`
3. Stage 3.6 and Stage 3.7 studies also use these APIs, but the cleanup plan
   intends to remove those experiment-specific implementations after their
   knowledge is recorded. The release group/schema/bounds logic is tied to
   Stage 3.6 experiment protocol; the design representation and filter
   simulation may be reusable problem-layer behavior.
4. Stage 3.8 and Stage 3.8C import `lshade_record` from
   `studies/optimizer_ab.py`. The adapter serializes optimizer summary,
   timing, checkpoint, and frequency-grid fields, then calls
   `studies/convergence_evidence.apply_checkpoint_evidence`. Checkpoint tests
   currently import this helper through `optimizer_ab.py`.
5. Stage 3.8C imports topology, material, initializer, and simulation helpers
   from the Stage 3.8 fast-screen module. Its source also references a
   historical handoff and report for provenance/review output.

## Judgment requested

- Should `ReleasedFilterDesign`, section geometry, and
  `simulate_released_filter` move into the existing
  `problem/dms_topologies.py`, or should any of these remain in a study layer?
- Should release schema/bounds/vector decoding remain with the historical
  Stage 3.6 adapter rather than become a canonical problem API?
- Where should `lshade_record` live given its dependency on study-level
  checkpoint evidence? Identify any field groups whose semantics must stay
  unchanged during the move.
- What minimum characterization checks should gate removal of the old
  imports, without rerunning any production or historical optimization?
- Which current historical file/hash/report references are runtime
  dependencies that should be removed, and which are provenance contracts
  that must remain in saved artifacts?

## Constraints

- Structural changes only; no edits to COM/network equations, design bounds,
  geometry constraints, objectives, ranking, optimizer behavior, RNG order,
  budgets, checkpoint semantics, or saved `runs/`.
- Do not rerun production optimization or regenerate historical artifacts.
- Preserve old Stage modules until current callers and tests have moved and
  targeted parity checks pass.
- Review judgment only; Luna retains implementation and verification.
