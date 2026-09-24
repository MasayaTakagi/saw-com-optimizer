# Historical Cleanup Freeze

Recorded: 2026-09-25

## Git state

- Branch: `codex/historical-cleanup`
- HEAD: `444d3a430797d32d688f74bb76ffda615cddfba0`
- Freeze tag: `archive/pre-historical-cleanup-2026-09-25`
- Tracked worktree changes before this report: none
- Existing untracked user file: `docs/handoff/SAW Optimizer Historical Cleanup Plan.md`
- `git diff --stat` before this report: empty

The freeze tag points to the cleanup-start commit. The supplied plan file is
untracked and remains in the working tree; it is not included in that commit.

## Test baseline

Command: `.venv\Scripts\python.exe -m pytest`

Result: **288 passed** in 108.02 seconds. Pytest emitted one cache warning
because it could not write `.pytest_cache`; this did not affect test results.

## Tracked file inventory

The repository has 303 tracked files at the freeze point:

| Area | Files |
| --- | ---: |
| `src/` | 96 (95 Python, 1 README) |
| `tests/` | 58 (54 Python, 2 JSON, 2 Markdown) |
| `configs/` | 47 |
| `experiments/` | 17 |
| `docs/` | 27 |
| `reports/` | 27 |
| Other paths | 31 |

## Current dependency observations

- DMS topology structures and simulation already have a canonical home in
  `src/sawopt/problem/dms_topologies.py`.
- `src/sawopt/studies/stage3_8_dual_material_dms_topology_fast_screen.py`
  imports the canonical topology implementation, but still imports
  `ReleasedFilterDesign`, its release decoder/schema/bounds, and
  `simulate_released_filter` from `stage3_6_gate2a.py`.
- The Stage 3.8 and Stage 3.8C study modules import `lshade_record` from
  `optimizer_ab.py`. That record adapter calls
  `studies.convergence_evidence.apply_checkpoint_evidence`, so its ownership
  needs review before moving it into `optimization/` or `optimizers/`.
- Stage 3.8C imports topology/material/initializer helpers from the Stage 3.8
  study module. Its source also hashes a handoff document and copies a
  historical report into review output; these are candidates for removal from
  future runtime dependencies after their knowledge is preserved.
- `tests/unit/core/test_topology.py`,
  `tests/unit/problem/test_dms_topologies.py`, and checkpoint tests still
  contain imports through historical study modules.

These are static observations only; they do not imply that the full historical
modules are still required by current workflows.
