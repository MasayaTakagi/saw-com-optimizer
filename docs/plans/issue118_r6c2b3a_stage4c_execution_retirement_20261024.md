# Issue #118 — R6-C2B3A Stage 4C execution retirement

**Status:** `OWNER_APPROVED_SOFTWARE_RETIREMENT / DRAFT_PR_STOP`

**Scope/base:** Issue [#118](https://github.com/miyabimm/saw-com-optimizer/issues/118),
updated owner instruction in its latest comment, based on verified `main`
`93f5f0b42d862d306b18e5a4a7b495f6cfd82133` (merged PR #116). Merged-main
Actions [#40096296836](https://github.com/miyabimm/saw-com-optimizer/actions/runs/40096296836)
completed successfully at that exact SHA: Haswell, 752/752 passed.

This is a software-only retirement of obsolete Stage 4C shakedown execution,
one-off WSL/Codex qualification executables, and a closed historical audit
executable. No retired route was run. This change does not authorize COM/FE,
optimizer qualification, a Stage 4C study, live-process operations, or access
to external run/checkpoint data.

## Source and caller disposition

| Removed source / symbol | Static checked-in callers and tests | Disposition |
|---|---|---|
| `studies.hybrid_stage4c.run_stage4c_shakedown`, its `__all__` export, and the Stage 4C-only shakedown matrix/constants and `build_stage4c_run_manifest` shakedown branch | Direct test import and two-cell shakedown fixture/report test in `test_hybrid_stage4c.py`; former WSL qualification tool called Stage 4A/Stage 4B evaluation and optimizer/checkpoint routes. | Removed completely, with no compatibility stub. The manifest builder is now production-only; its frozen production identity and validator remain. A focused negative test pins that the callable and export are absent. No `__main__` dispatch existed for this callable. |
| `reporting.hybrid_stage4c.write_stage4c_shakedown_reports` and its export | Only the removed shakedown runner and its dedicated temporary-fixture test called it. | Removed as orphaned Stage 4C execution/reporting glue. Production reporting, contract validation, `export_stage4c_review`, and shared historical report readers remain. |
| `tools/wsl/qualify-core.sh`, `tools/wsl/qualification_smoke.py` | The shell qualification flow called the smoke utility; the smoke utility imported Stage 4A/4B/4C and optimizer/checkpoint APIs. No independent current host-diagnostics consumer was found. | Removed as the coupled retired Codex/numerical/checkpoint qualification workflow; neither was executed. |
| `tools/wsl/bootstrap-wsl.sh` | Only documented as a manual setup step for the same WSL qualification; `qualify-core.sh` expected its generated environment report. It installed Codex and created/configured a qualification checkout/environment. | Removed with its sole qualification purpose. No general WSL setup contract is claimed. |
| `tools/wsl/collect-report.sh` and `tests/unit/test_wsl_qualification_report.py` | The shell qualification flow called the report collector; the test was its only dedicated consumer. | Removed with the retired qualification report schema. Existing dated report/evidence files are unchanged. |
| `studies.audits.stage4c_resonator_pair_probe` and `test_stage4c_resonator_pair_probe.py` | Only the dedicated one-off audit test imported the module. Static search found no Q1-A, Stage5A2, or current regression API dependency. | Removed under the owner's updated approval for unused Stage 4C scripts. The audit's historical protocol/output are not regenerated, edited, or deleted. Shared Stage 4A evaluator/geometry code was left unchanged rather than changing scientific behavior as part of this retirement. |

## Retained boundaries

- Retain `run_stage4c_production`'s existing fail-closed guard and its
  no-side-effect regression, all Stage 4C frozen inputs, production matrix,
  authorization and manifest validators, production reporting, and
  `reporting.github_review`/`export-review` consumers.
- Retain Stage 4B `run_matched_cell`, Stage 4A evaluation, COM/physics and
  optimizer implementations, reusable Stage 4C report/audit-read helpers,
  Q1-A public/leaf goldens and import guards, R5, R6 synthetic code, and
  worktree/storage/checkpoint safety.
- Retain independent WSL host tools: `preflight.ps1`, `install-wsl.ps1`,
  `diagnostic-helpers.ps1`, and `test-diagnostics.ps1`. None was executed or
  modified. No blanket `tools/wsl/` deletion was performed.
- Keep historical raw runs, checkpoints, configs, reports, evidence bytes,
  source identities, and prior dated inventories/closeouts unchanged. Issue
  #58's off-device redundancy and missing legacy payload remain unresolved.

## Tests, docs, and validation

- Removed only tests dedicated to obsolete Stage 4C shakedown reporting, the
  Stage 4C coordinate-probe audit, and the retired WSL report collector.
- Added `test_stage4c_shakedown_execution_entrypoint_is_absent`; retained
  Stage 4C production rejection, frozen protocol/manifest/report tests, and all
  unrelated scientific/safety regressions.
- Updated the current development-environment guide and archival WSL page so
  they no longer direct users to deleted commands; added this record to the
  active documentation index. Historical inventories remain dated evidence
  and were not rewritten.
- Correct worktree-specific `.venv` was absent, so no local project tests were
  run; no dependency sync/install or borrowed editable environment was used.
  Static source/caller searches, `compileall`, `git diff --check`, changed-doc
  link checks, focused GitHub Actions, and the exact PR-head locked Haswell
  full CI are required before handoff. Record exact commands, counts and the
  final Actions URL/SHA in the Issue #118 work-order handoff; a previous/base
  CI result is not a substitute for final PR-head CI.

## Rollback and stop

Rollback is by reverting the complete reviewed PR. Do not restore a retired
execution route or modify historical artifacts to support rollback. Submit one
Draft PR and stop for independent GitHub review. Do not mark Ready/merge, begin
Issue #119, start R7, inspect or stop a live process, inspect/mutate external
raw/checkpoint state, or run COM/FE/optimizer/WSL qualification.
