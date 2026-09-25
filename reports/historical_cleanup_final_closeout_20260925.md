# Historical Cleanup Final Closeout

## Repository state

- Branch: `codex-historical-cleanup`
- Starting HEAD: `1282699b9c56a099b6fdb42b38ecba9009d91954`
- The closeout changes were committed on `codex-historical-cleanup`; Git history is the canonical source for the resulting commit SHA.
- Recovery tag: `archive/pre-historical-deletion-2026-09-25`
- Recovery tag target: `3f88bf0be2a0ac651e35f9de678df1ca5023f387`
- The recovery tags and Git history were not changed.

## Final inventory

- Tracked files: 150
- Python source files: 62
- Python test files: 40
- Configuration files: 12
- Current study modules: `dms_topology_common.py`, `dms_topology_screening.py`, `hybrid.py`, `lshade_records.py`

## Historical cleanup

Retired stage-numbered runners, configurations, tests, and tracked handoff/report artifacts have been pruned. Historical findings remain in `docs/history/current_baseline.md` and `docs/history/experiment_register.md`; the annotated recovery tag preserves the exact pre-deletion source state.

## Current workflows

- DMS topology screening through `python -m sawopt run-study`
- 50 Ω Hybrid through `python -m sawopt.studies.hybrid`
- Prototype simulation, optimization, impedance sweep, and saved-run reports through `python -m sawopt`

## Compatibility cleanup

Removed the unreferenced pure re-export modules `optimization/backends.py`, `optimization/lshade.py`, and `optimization/selection.py`. `optimization/__init__.py` remains as a minimal package marker. Kept `optimization/polish.py` because it implements SAW-specific mixed-variable polish, and kept `optimizers/polish.py` for optimizer-generic polish.

Current source, tests, scripts, and execution documentation contain no imports of the removed modules. Remaining Stage-named strings document implementation lineage, immutable reference-input provenance, or legacy checkpoint marker translation; current architecture and execution guides do not describe deleted study modules as active.

## Verification

- Focused regression: `59 passed in 63.27s`
- Full regression: `165 passed, 11 subtests passed in 63.63s`
- The CI workflow triggers on pushes to `main`/`master` and on pull requests; a direct push to this branch does not trigger it.

## Numerical impact

`NO PRODUCTION OPTIMIZATION RERUN`

`NO COM/NETWORK/OBJECTIVE/OPTIMIZER NUMERICAL SEMANTICS CHANGE`

`NO CANONICAL SAVED RUN MODIFICATION`

## Final status

`HISTORICAL_CLEANUP_COMPLETE`
