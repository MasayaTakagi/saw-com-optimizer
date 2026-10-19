# Stage 5A-1 — Candidate record consistency audit

**Date:** 2026-10-20
**Audit mode:** Read-only; no optimization or physics evaluations were run.
**Disposition:** Stage 4C saved candidate values are internally consistent. Two latent comparator-integrity risks and one grid-provenance risk were identified; none changes the current Stage 4C candidate ordering or its unresolved scientific disposition.

## Source and evidence identity

- **Inspected source commit:** `3e099176481e3cd455260fac895b14c8f0a7fa1e` (`origin/main` when this audit branch was created).
- **Stage 4C run:** `20261006_124153_ed50ba`.
- **Stage 4C recorded source commit:** `65e1815db1cc18d74ff0dcee20ffd5e9098709df` (same across all 10 cell records).
- **Review evidence:** `reports/experiment_reviews/stage4c/20261006_124153_ed50ba/`.
- **Grid identities in the frozen protocol/run metadata:** search grid 1,001 points, SHA-256 `212dd2b0b71ddeffb7a8865937d132ee596870f25c989ac7d90c5dab6fd7faa0`; common validation grid 9,113 points, ID `2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f`, SHA-256 `54c1daf67dd2bb9242f95e638d7bd801db536acc2c7d6f00c1f62a788bead554`.

## Scope and method

Audited all **10 cells**: `P_D` and `D_P` × seeds `20261007`–`20261011`. Each cell contributes its saved `search_incumbent` and `common_grid_selected_finalist`, for **20 candidate records** total. The package integrity record reports 10/10 completed cells and `PASS`.

The audit read the roadmap, selection/L-SHADE implementation, Stage 4A hybrid evaluation and geometry code, Stage 4C report comparison code, the frozen Stage 4C protocol/config snapshots, the erratum, and the saved candidate/result records. It independently recomputed constraint summaries, feasibility, the per-constraint violation formulas, scalar objective values, and comparator keys. Malformed-record behavior was probed using in-memory synthetic records only. No saved result, checkpoint, CSV, or other experiment artifact was written or modified.

## Findings

### 1. Persisted record arithmetic and flags: no inconsistencies found

All 20 audited records have the expected candidate fields, finite numeric leaves, an eight-entry filter `violations` mapping, and an 18-entry `geometry_violations` mapping. All are 13-dimensional. All report `evaluation_status = PHYSICS_EVALUATED`, `geometry_max_violation = 0`, and 18 zero geometry violations. No status/geometry contradiction was found in these persisted finalist records. The compact candidate projection does not carry a separate `geometry_valid` flag; geometry status is represented by `evaluation_status` and its geometry-violation fields.

For every record:

- `max_violation` equals the maximum of the eight stored filter violations (checked at `rel_tol=1e-12`, `abs_tol=1e-12`).
- `sum_violation` equals their sum at the same tolerance.
- `feasible` is the Boolean result of the source's `max(violations) <= 1e-10` condition. All 20 are correctly `False`; their `max_violation` values range from about **0.306628 to 0.363328**.
- Each individual violation matches the saved metric and Stage 4C limits: IL/3 dB, ripple/2 dB, input/output VSWR/2.5, and normalized shortfall from stopband targets `[20, 32, 30, 30]` dB. All 160 per-constraint comparisons matched within `1e-11`.
- Reconstructing the infeasible scalar objective from the current `core.metrics.feasibility_objective` formula matched both `objective` and `search_scalar_objective` in all 20 records (0 mismatches). The L-SHADE candidate ordering uses the comparator, not this scalar.

The exact feasibility threshold is taken from `src/sawopt/core/metrics.py` and `src/sawopt/studies/hybrid.py`: **`1e-10`**. The geometry gate is separate and rejects when geometry maximum violation is strictly **greater than `0.0`**. These are implementation conditions, not audit-defined tolerances.

| Topology / seed | Search incumbent `max / sum` | Common-grid finalist `max / sum` |
|---|---:|---:|
| P_D / 20261007 | 0.341806 / 2.071834 | 0.342266 / 2.047807 |
| P_D / 20261008 | 0.316759 / 1.687720 | 0.316759 / 1.687618 |
| P_D / 20261009 | 0.318975 / 1.786699 | 0.319074 / 1.814052 |
| P_D / 20261010 | 0.363328 / 1.813721 | 0.363328 / 1.813763 |
| P_D / 20261011 | 0.330295 / 1.498524 | 0.330295 / 1.498981 |
| D_P / 20261007 | 0.306628 / 1.566575 | 0.306628 / 1.639299 |
| D_P / 20261008 | 0.322457 / 1.802775 | 0.323618 / 1.801206 |
| D_P / 20261009 | 0.359026 / 1.774618 | 0.359074 / 1.775171 |
| D_P / 20261010 | 0.312638 / 1.606126 | 0.312638 / 1.607143 |
| D_P / 20261011 | 0.341674 / 1.864621 | 0.341689 / 1.875833 |

The two columns are intentionally labeled by their respective evaluation grids. They are **not** same-grid paired values or a validation “delta”; candidate identities can differ between the columns.

### 2. Geometry and physics-status semantics

In `src/sawopt/studies/hybrid.py` (`_stage4a_evaluate`), a positive geometry violation returns `GEOMETRY_REJECTED` before COM/network evaluation; filter metrics and filter violations are unavailable and the filter `max_violation`/`sum_violation` are `None`. Once the geometry gate passes, the routine attempts physics and metrics. Success returns `PHYSICS_EVALUATED`; numerical/model errors caught by the evaluator return `PHYSICS_FAILED` with geometry still valid but filter metrics unavailable. Thus geometry feasibility is a hard gate, distinct from filter feasibility.

`GeometryFirstComparator` orders physics-evaluated records using the feasibility-first filter key, places physics failures after successful physics evaluations, and orders geometry-rejected proposals by geometry violation. Every saved terminal candidate audited here is physics-evaluated and has zero geometry violations; no geometry-rejected or physics-failed candidate is among the 20 terminal records. This does not assert that no such evaluations occurred during the 96,000-evaluation searches.

### 3. Comparator rankings on like-for-like grids

All saved candidates were passed through the current `GeometryFirstComparator`. Because the audited records are all `PHYSICS_EVALUATED`, their ordering reduces to the underlying feasibility-first key. Matched-seed P_D-versus-D_P outcomes were:

- **Search incumbents, compared only to other search-grid incumbents:** P_D wins seeds 20261008, 20261009, 20261011; D_P wins 20261007, 20261010; 3–2, no ties.
- **Common-grid selected finalists, compared only to other common-grid finalists:** the same 3–2 outcomes and seed assignments.

These are finite-budget candidate rankings, not proof of convergence, global optimality, or topology selection. The result remains `STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`, consistent with the Stage 4C review and roadmap.

### 4. Grid distinction and provenance risk

The run manifest/protocol snapshots distinguish a 1,001-point search grid from a 9,113-point common validation grid. The search incumbent is evaluated on the former; the selected finalist is re-evaluated on the latter. This audit did not rank a search-grid metric against a common-grid metric as if they shared conditions.

**Provenance limitation:** the projected candidate objects themselves contain no per-record grid ID/hash. Their containing field names (`search_incumbent` versus `common_grid_selected_finalist`) and run-level protocol metadata supply the distinction, but detached/copied candidate objects are not self-describing. No incorrect cross-grid comparison was observed in the saved paired report; its pairwise summary reads `common_grid_selected_finalist` records. The summary projection in `src/sawopt/studies/hybrid_stage4b.py` is where the per-record scope is omitted.

The saved package contains only the selected common-grid finalist, not the full 16-member validation pool. Therefore this audit could not independently prove that the saved common-grid selected finalist was the minimum-ranked member of all 16 re-evaluated candidates. Current source selects the best physics-evaluated row from that pool, but the compact evidence does not expose the whole pool for replay.

### 5. Latent implementation integrity risks (not triggered by these records)

**A. Reporter and optimizer differ for feasible candidates.** `GeometryFirstComparator` delegates physics-evaluated records to `FeasibilityFirstComparator`: once feasible, its key is worst IL, then configured secondary ripple, then violations. In contrast, `src/sawopt/reporting/hybrid_stage4c.py::_score` ranks all records by `(feasible, max_violation, sum_violation, worst_il)`. An in-tolerance synthetic pair demonstrates reversal: both candidates satisfy the source threshold (`max_violation` 0 and `5e-11`), with worst IL 3 and 2 dB respectively. The optimizer prefers the 2 dB candidate; the report helper prefers the zero-violation/3 dB candidate. This is a latent comparator-parity inconsistency, **not an observed Stage 4C data inconsistency**: all 20 saved candidates are infeasible, so this branch did not affect their ordering or the recorded 3–2 result. The discrepancy should be resolved against the authoritative ranking contract before relying on that helper for a future feasible study.

**B. Comparator input handling is permissive, not schema-validating.** `FeasibilityFirstComparator.rank_key` trusts an explicit `feasible` value via Python truth conversion and does not reconcile it with violations. When the field is absent, missing `max_violation` plus empty violations defaults to zero and therefore feasible. Non-finite individual violation entries are converted to infinity and then omitted from the derived max/sum list. An explicit contradictory `feasible=True` can override a positive `max_violation`; a string such as `"false"` is truthy. `GeometryFirstComparator` likewise trusts `evaluation_status` and does not cross-check the geometry fields when status says `PHYSICS_EVALUATED`. These in-memory probes show malformed records can obtain deceptively favorable keys. None of these conditions appeared in the 20 persisted records (0 missing expected keys, 0 non-finite values, 0 contradictory flags), but candidate schema validation/fail-closed handling is a real future-input risk.

## Counted outcomes

| Category | Count | Result |
|---|---:|---|
| Persisted candidate records inspected | 20 | 10 cells × 2 record types |
| Persisted max/sum, feasibility, individual formula or geometry inconsistencies | 0 | All checks passed |
| Missing required candidate fields / non-finite values / contradictory flags | 0 / 0 / 0 | None in saved records |
| Scalar objective reconstruction mismatches | 0 | 20/20 matched |
| Cross-grid rank comparisons performed | 0 | Explicitly excluded |
| Latent implementation comparator-parity mismatch | 1 | Reporter ordering can disagree for feasible records; not triggered |
| Latent malformed-record validation weakness | 1 class | Permissive fallbacks/truth conversion; not triggered |
| Candidate-level grid identity omitted | 20 records | Context names and run-level metadata distinguish scope; provenance risk only |

## Implementation defect versus saved-data status

There is **no detected internal inconsistency in the persisted Stage 4C candidate metrics, violation totals, feasibility flags, geometry fields, or scalar objective values**. The two implementation risks above concern future feasible or malformed candidate inputs and did not change this run’s all-infeasible results. The grid identity omission is a provenance limitation, not evidence that the saved metrics were computed on the wrong grid. No optimizer, objective, comparator, report, checkpoint, or experiment data was modified.

## Unverified items

- The full finalist set and raw terminal checkpoint were not in the compact review package; the finalist selection over all 16 candidates cannot be independently replayed.
- No COM/network physics was rerun, by design. This audit verifies record arithmetic and saved-grid comparisons, not independently recomputed spectra or physics correctness.
- This task did not audit cache identity, canonicalization behavior, population evolution, initializer replay, complete evaluation accounting, or the full Stage 5A time/cost profile.
- Synthetic malformed-record probes characterize current source behavior but are not evidence that malformed records occurred in Stage 4C.

## Stage 5A-1 next priority

First have the authoritative feasible-candidate tie-break contract reviewed and align future reporting with the canonical comparator; add fail-closed candidate-record validation before such records can enter ranking. Then complete the remaining read-only Stage 5A-1 optimizer-integrity and cost audit: canonicalization/cache identity, finalist provenance/accounting, population and initialization behavior, and evaluation-time reconstruction. Keep the Stage 4C result immutable and do not launch a new optimization for this audit. Any later controlled comparison remains a separately authorized task under the roadmap.

## Validation

- `uv sync --locked --extra test` — completed in the dedicated audit worktree.
- `uv run --locked pytest tests/unit/optimizers/test_selection.py tests/unit/studies/test_hybrid_stage4c.py tests/unit/studies/test_hybrid_stage4b.py` — **46 passed**.
- `uv run --locked pytest tests/unit/optimization/test_search_primitives.py tests/unit/problem/test_stage4a_hybrid_design_space.py tests/unit/problem/test_dms_topologies.py tests/unit/core/test_stage4a_hybrid_composition.py` — **20 passed**.
- `git diff --check` — to be run before commit.
- No GitHub Actions workflow was requested or run.
