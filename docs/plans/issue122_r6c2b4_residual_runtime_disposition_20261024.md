# Issue #122 — R6-C2B4 residual runtime disposition

**Scope:** software-only retirement of proven-unused legacy execution code; preserve current reporting, reusable science contracts, numerical behavior, safety owners, and historical evidence. This record does not authorize COM/FE, optimizer, Stage 4B/4C, WSL, or production execution, Q1 qualification, or an R7 transition.

## Worktree and starting state

Recorded before source edits or destructive/staging commands:

```text
pwd:                  /home/user/src/saw-com-optimizer-issue122
git rev-parse root:   /home/user/src/saw-com-optimizer-issue122
branch:               issue122-r6c2b4-prune
expected starting HEAD: 06c71c29a3648f5e60015b3fbc06a375e2f2936d
git status --short:   clean
```

The entry baseline is merged PR #121 at `06c71c29a3648f5e60015b3fbc06a375e2f2936d`; merged-main CI run #40104807026 completed successfully (Haswell, 721/721 tests). Work is confined to the dedicated #122 worktree above, not the #71 or #119 worktrees.

Before removing the confirmed orphan source/config files, the dedicated worktree was re-asserted: `pwd` and `git rev-parse --show-toplevel` both returned `/home/user/src/saw-com-optimizer-issue122`; branch was `issue122-r6c2b4-prune`; HEAD remained the expected base SHA; status contained only the five scoped source/test modifications and this new disposition record.

Before staging the complete change, the worktree was re-asserted again: the same `pwd`, repository root, branch, and unchanged expected starting HEAD were verified. `git status --short` listed only the two intended deleted postrun files, this disposition record, the README correction, the two scoped Stage 4B/4C modules, and their three scoped test files.

Before staging the final CI evidence update for the amend, `pwd` and repository root were again `/home/user/src/saw-com-optimizer-issue122`, branch was `issue122-r6c2b4-prune`, HEAD was `c0dccb07e2388dc520924f5eb68e38b07f0773a1`, and status contained only this disposition record.

## Static caller/evidence disposition

The review used current-source/test/tool text searches and direct source inspection only. No old CLI, COM/FE, optimizer, Stage 4B/4C, WSL qualification, production, active-run/PID registry, or external run data was accessed.

| Candidate | Current caller / evidence | Disposition |
|---|---|---|
| `studies.postrun_workflow_qualification.run_qualification_fixture` | The former `__main__._run_study` route was removed before #122. No current source/test/tool imports or calls the helper. | Remove the orphan helper and its now-unreferenced `configs/studies/postrun_workflow_qualification.yaml`. No scientific or R5/synthetic worker consumer was found. |
| Postrun review export | `reporting.github_review.export_review` still resolves the legacy postrun review spec for historical manifests without an embedded spec; `tests/unit/reporting/test_github_review_export.py` exercises the generic exporter with that schema/spec; the committed qualification review package is historical evidence. | Keep `configs/review_specs/postrun_workflow_qualification.yaml`, the generic export path, its tests, and the committed report unchanged. These are current report-export behavior/evidence, not callers of the retired study helper. Keep the existing dated retirement notice and historical docs. |
| Stage 4B context/auth/launch wrappers | `load_stage4b_context`, `verify_production_manifest`, `run_stage4b_shakedown`, and `run_stage4b_production` are unconditional retirement stubs. Their current call sites are only obsolete rejection tests; there is no remaining CLI/worker route. | Remove the stubs and their stale error-compatibility tests; test symbol absence instead. Remove Stage 4B-only authorization builders/claim ID and launch-only `_initialize_batch_run` after static searches found no current callers. |
| Stage 4B shakedown/source-state glue | `SHAKEDOWN_*`, `_git_value`, `_source_state`/`read_source_state` and the old shakedown matrix are not imported by current code. | Remove this old-only glue/export. |
| Stage 4B reports/contracts | `reporting.hybrid_stage4b` imports `STUDY_TYPE`, protocol constants, `_cell_paths`, and `_expected_matrix`; Stage 4C report generation imports `matched_cell_paths`; Stage 4C manifest writing imports `write_atomic_json`. | Keep the report/contract constants and those reusable helpers/aliases. Keep `reporting.hybrid_stage4b` and all historical report/evidence tests. |
| Stage 4B cell algorithm and failure evidence | `_sample_stage4b_population`, `_run_cell`, `_cell_failure_payload`, and their checkpoint/evaluation/error paths are a scientific/runtime algorithm and unique failure/checkpoint evidence. The completed-cell fixture test returns before optimizer/evaluator construction; the production-mode guard also rejects before filesystem access. | **Retain unchanged**; do not exercise COM+optimizer execution. Keep the pure failure-payload and completed-cell short-circuit regressions. Remove the unused `run_matched_cell` alias after searches found no current source/test/tool caller; the underlying algorithm remains untouched as a scoped STOP/retained fragment. |
| Stage 4C execution entrypoint | `run_stage4c_production` is an unconditional retired stub; its only direct consumer is an old rejection test. No active CLI/worker caller remains. | Remove the stub/export and replace error-compatibility coverage with an absence assertion. |
| Stage 4C authorization workflow | Stage 5A-1, reporting, and review export do not import the old queue/one-shot-claim authorization helpers. The verifier/builders/path helpers are used only by their isolated test; execution is already retired. | Remove only this dead Stage 4C execution-authorization scaffold and its obsolete verifier test. Keep frozen config validation, protocol/run-manifest builders and validators, expected matrix, all report/export helpers, and their regressions. Do not modify frozen config or evidence. |
| Historical records | Dated plans, archived reports, the qualification review package, raw/checkpoint records, stored source SHA identities, and reports are immutable under this task. | Preserve byte-for-byte; no migration, regeneration, rewrite, or deletion. |
| `docs/README.md` #119 note | The index incorrectly says independent review is still pending. | Update only this current index sentence to PR #121 merged SHA and verified CI disposition; leave dated plans and history untouched. |

## Test disposition

Retain `tests/unit/reporting/test_github_review_export.py` and Stage 4B/4C report, frozen-contract, manifest, integrity, boundary, and classification regressions. Retire only tests whose subject is the deleted Stage 4B/4C stub/error interface or deleted Stage 4C authorization verifier; add narrow source/symbol-absence assertions. The completed historical-cell short-circuit and pure failure-payload checks remain, while no COM+optimizer route is exercised. Do not remove or weaken scientific tests, safety tests, or the generic review exporter.

Baseline full CI was 721 tests. Expected collected count is 717: three Stage 4B stub-rejection tests become one Stage 4B symbol-absence test (-2), and two duplicate Stage 4B/4C stub-rejection tests in `test_issue108_legacy_codex_retirement.py` are removed (-2). The Stage 4C auth test is replaced in-place by manifest-contract/absence assertions (0 net); remaining parametrized and scientific/report tests stay. Confirm this against the exact PR-head GitHub run; no mass skip or test weakening is authorized.

## Final evidence

- Base SHA: `06c71c29a3648f5e60015b3fbc06a375e2f2936d`
- Branch: `issue122-r6c2b4-prune`
- Implementation commit tested by the initial Draft PR CI: `c0dccb07e2388dc520924f5eb68e38b07f0773a1`
- Draft PR: [#123](https://github.com/miyabimm/saw-com-optimizer/pull/123)
- Local checks: `/usr/bin/python3.12 -m compileall -q src tests` PASS; `git diff --check` and `git diff --cached --check` PASS; local Markdown links in `docs/README.md` and this plan PASS. Pytest was not run locally: the dedicated worktree has no `.venv` and system `pytest` is absent; Issue #122 prohibits package/environment sync here.
- Initial exact-PR-head Haswell GitHub CI: [run #40107162924](https://github.com/miyabimm/saw-com-optimizer/actions/runs/40107162924) SUCCESS; checked head `c0dccb07e2388dc520924f5eb68e38b07f0773a1`; full suite **717 passed in 104.16s**. This run confirms the expected -4 test delta from merged-main baseline 721.
- Removed/retained test delta: three Stage 4B stub rejection tests replaced by one absence test (-2); two duplicate Stage 4B/4C rejection tests removed from `test_issue108_legacy_codex_retirement.py` (-2); Stage 4C auth verifier test replaced in-place by manifest/absence assertions (0 net). Generic report/export, historical contract, matrix, checkpoint/failure, and scientific regressions remain.
- Unresolved symbols/scope stops: `_sample_stage4b_population` and `_run_cell` remain unchanged as a scoped STOP because they implement scientific cell initialization/evaluation/checkpoint behavior and retained failure/cached-cell regressions; no old execution route was run. The handoff-record update after this run requires a fresh CI check on the resulting final PR head.
- Status: `OWNER_AUTHORIZED_RESIDUAL_OLD_CODE_PRUNING / C2B4_NARROW_SOURCE_AND_TEST / PRESERVE_REUSABLE_SCIENCE_AND_SAFETY / DRAFT_PR_STOP`
