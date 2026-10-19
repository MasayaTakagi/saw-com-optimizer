# Stage 5A-1 raw finalist provenance audit

## Result

**PASS — 80/80 checkpoints; 1,280/1,280 finalist records checked; 0 reported inconsistencies.**

This is a read-only replay of saved finalist selection. It does not rerun the optimizer or COM simulation, and it does not change the Stage 4C result or scientific classification.

## Scope and provenance

- Run: `20261006_124153_ed50ba` (Stage 4C confirmatory)
- Frozen source commit recorded by the run: `65e1815db1cc18d74ff0dcee20ffd5e9098709df`
- Auditor implementation reviewed: `c0ab7cc5ad93569c1828f812cf90655e89c5cc8f`
- Expected cells: 2 topologies × 5 seeds; expected checkpoints: 8 per cell.
- External raw optimizer data was read in place. No raw checkpoint, candidate, cache, or review-package data is included in this report or committed with it.

The run manifest, all ten compact cell records, and all 80 raw checkpoint records carry the requested original execution SHA. The audit verified compact-record fingerprints and validation-grid identity against the checkpoint records. The original Stage 4B checkpoint-writing/selection implementation is unchanged between the recorded source SHA and the auditor commit. The only intervening change in `GeometryFirstComparator` adds telemetry methods; its ranking key is unchanged. In the original implementation, selection is `min(eligible, key=GeometryFirstComparator.rank_key)`. For a physics-evaluated candidate, that key adds a constant `(0, 0)` prefix to the standard feasibility-first rank key. The audit validates the full record before applying that same underlying key and Python's stable first-on-tie `min` behavior.

## Checks and results

| Check | Result |
|---|---:|
| Required raw checkpoint files present and nonempty | 80/80 |
| Checkpoint source SHA | 80/80 match the recorded execution SHA |
| Checkpoint audits | 80 PASS, 0 FAIL |
| Saved finalist records | 1,280 (16 per checkpoint) |
| Evaluation status | 1,280 `PHYSICS_EVALUATED`; no failed/geometry-rejected finalist records |
| Source-rank positions | 80/80 pools contain ranks 1–16 in saved order |
| Duplicate finalist vectors within a checkpoint pool | 0 pools with duplicates |
| Full record / feasibility / violation integrity | 1,280 passed the strict rankability checks |
| Formal-comparator selected finalist replay | 80/80 matched the saved selection |
| Per-checkpoint cumulative validation counter and frequency-point accounting | 80/80 passed |
| Terminal compact selection, search incumbent, and counters | 10/10 cells matched the terminal raw checkpoint |
| Aggregate validation evaluations at terminal state | 1,280 (128 per cell); 0 validation physics failures |
| Aggregate validation frequency points | 11,664,640 |

The audit command exited `0` with status `PASS` and no manifest, protocol, checkpoint, or candidate errors. Checkpoint validation counters were checked against 16 additional validations per checkpoint, cumulatively through 128 per cell at the terminal checkpoint; frequency-point accounting used the recorded 9,113-point common validation grid.

## Validation performed

- `uv sync --locked --extra test` — passed in the dedicated audit worktree.
- `uv run --locked pytest tests/unit/studies/audits/test_stage5a1_raw_finalist_provenance.py` — **9 passed**.
- `uv run --locked pytest` — **475 passed, 1 skipped**.
- Read-only raw finalist replay — **80/80 PASS**, exit code `0`.

## Limits / not established

This result establishes saved finalist-selection replay only. It does **not** reproduce COM physics, prove optimizer convergence or a global optimum, or reconstruct the optimizer trajectory. Although the saved `search_source_rank` sequence was checked, `search_source_rank_key` was omitted from the persisted finalist projection, so the historical search-grid ordering of those finalists cannot be independently recomputed. Full canonical-key cache/proposal-history uniqueness is likewise not established. These are not failures of the 80 checkpoint selection replay; they remain outside the evidence available in the saved `B*.json` records.

The Stage 4C scientific classification remains **`STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`**. This audit makes no topology selection or scientific acceptance decision.
