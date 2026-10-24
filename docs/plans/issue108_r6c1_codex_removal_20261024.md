# Issue #108 — R6-C1 legacy Codex retirement scope

**Tracking:** [Issue #108](https://github.com/miyabimm/saw-com-optimizer/issues/108), under #106/#75/#73/#71/#53.  
**Status:** `C1_IMPLEMENTED / DRAFT_PR_OPEN / HASWELL_CI_PASS / HISTORICAL_REPLAY_NOT_REQUIRED / ACTIVE_RUN_GATE_OPEN`.
**Base:** verified GitHub `main` / `origin/main` `639d2c033bb540e4b8343f9d4f385f694e2ba427` (PR #107).  
**Worktree:** `/home/user/src/saw-com-optimizer-issue108`, branch `issue108-r6c1-codex-removal`.  
**Authorization:** the Issue #108 owner instruction authorizes only scoped source removal and deterministic software tests. No real Pi/Codex/COM/FE/optimizer work, historical-run operation, data migration, or active-process manipulation is authorized.

## Binding scope reduction from #106

This addendum records the owner decision in Issue #108 and supersedes the historical-fingerprint reconstruction `STOP_FOR_OWNER` in [Issue #106 §4](issue106_r6c0_codex_removal_inventory_20261024.md). The former live Codex-dependent Stage4B production/shakedown/requalification path may be retired; reproducing the old schema-v2 computation fingerprint is **not** a requirement. The historical fingerprint `c63910623cb9a5d2a05ecb51f3685becf448f8ac91f169752f1b9703beef8464`, execution-source commit `c44798266067fa4b8b7d3b2873a798b7a1600ae8`, reports and prior Git objects remain historical facts; do not edit them, recalculate them as a new contract, or build an emulator.

## Intended software disposition

1. Remove the active `orchestration/codex_queue.py` and `codex_callback.py` modules and every callable import/dispatch, queue default, ACK/callback execution, session lookup, and automatic handoff. No dormant bridge, Pi/C2C/manual callback replacement, or silent `queue` → `disabled` fallback.
2. Make legacy orchestration execution fail closed before process creation, state mutation, authorization claim or provider/model access: launch/resume, recovery or worker routes capable of dispatching an old manifest, callback review, queue confirmation, and old Stage4B/4C production launch. Retain only individually justified observational or non-Codex safety/reporting behavior; old recorded states are not newly validated successes. Keep `python -m sawopt.cli` and `sawopt synthetic-task ...` separate and functional.
3. Retire only the obsolete Stage4B/Stage4C runtime/authorization entrypoints that depend on the unsupported transport or the live Stage4B fingerprint dependency. Preserve reusable COM, design, evaluation and optimizer implementation, and retain or relocate scientific regressions that independently protect those owners. Do not alter Stage4C's unresolved status, Q1-A/Q0 contracts, or any scientific behavior.
4. Remove or disposition strictly queue/callback-only tests and project-local hooks/configuration. Replace relevant mixed tests with negative no-spawn/no-state/no-auth/no-transport assertions. Keep worktree/process/path/storage/checkpoint safety, R5, synthetic Worker/CLI, historical report inputs and unrelated report functionality unless a concrete caller requires a separately justified change.
5. Audit source, dynamic entrypoints, scripts and project-local hooks for callable transport references. Preserve historical prose/data labels as evidence where useful; classify them as records, not executable features. Do not perform blanket cleanup of C2C/handoff/history directories.

## Mandatory software checks and interpretation limits

- Old transport modules and import routes are absent from active source; old command paths reject explicitly and before observable side effects.
- Historical queue/ACK/callback fields, where display is retained, remain recorded values only. This work does not migrate or rewrite v1–v4 manifests, status, delivery ledgers, raw data, checkpoints or reports.
- Preserve current Q1-A public/leaf 92-case goldens and import guards, R2–R4 numerical fixtures, current COM/optimizer/constraint tests, synthetic CLI/Worker, R5 I/O/review and independent process/worktree safety tests.
- Run relevant focused tests, the prescribed full locked Haswell-pinned pytest, Q1-A golden/import guards, compileall and `git diff --check`; report skipped checks and exact counts. No dependency installation/sync or scientific run.
- Before merge, the unknown active-old-worker risk needs either an explicitly authorized bounded, read-only metadata safety preflight or a recorded owner disposition. Do not inspect arbitrary roots/process environments or mutate/stop processes. If this remains open, record the blocker in the Draft PR and stop for owner decision; Draft PR is not merge authorization.

## Implementation disposition and validation record

- Removed `codex_queue.py`, `codex_callback.py`, the session-capture hook and their dedicated execution tests. The C2C state-access preflight remains; `.codex/hooks.json` is empty, with no active capture hook.
- Removed CLI queue launch, callback review and queue confirmation dispatch; new legacy-orchestration launches require explicit `--continuation-mode disabled`. Transport-linked historical manifests remain parseable, but resume, recovery, worker execution, new run creation, publication finalization, and status mutation for review export fail closed. Status rendering remains observational. Report export remains available and skips mutation of retired run lifecycle state.
- Stage 4B/4C orchestration launch and `run-study` dispatch reject before run creation or optimizer launch. Stage 4B context/fingerprint regeneration, production, shakedown, and direct `mode=production` cell execution reject before side effects. Stage 4C production rejects before reading/creating run artifacts. Stage 4C protocol/report contracts and the independently used non-production `run_matched_cell` modes remain intact.
- Retained COM/design/optimizer source, historical reports/manifests, scientific regression contracts, R5, synthetic CLI/Worker, administrative closeout, and process/worktree/storage/checkpoint safety owners. No historical source/data/evidence was rewritten.
- Focused tests passed before the final per-cell guard and report-export preservation adjustment: **81 passed**. A subsequent focused rerun could not start because the locked `--no-sync` environment no longer resolved pytest; direct import checks also found `numpy` unavailable. No dependencies were installed or synchronized.
- Full local `uv run --locked --no-sync pytest -q` was attempted: **686 passed, 79 failed, 15 subtests passed**. Failures included missing `numpy` distribution metadata and missing `yaml` in subprocess imports. No local dependencies were installed or synchronized; this local result is environment-blocked.
- GitHub Actions CI run [40085467489](https://github.com/miyabimm/saw-com-optimizer/actions/runs/40085467489) passed for commit `98cffa24545d1eb6c842aca92ca225d9717ad9cc`: **767 passed in 106.57s**. The project CI used `OPENBLAS_CORETYPE=Haswell`, ran `uv sync --locked --extra test --extra benchmark` in its ephemeral runner, then `uv run --locked pytest`; the 92-case Q1-A public/leaf goldens and import guards were included in this full-suite pass. Local dependency state was not changed.
- Passed on the current tip: `compileall` for `src/sawopt` and modified orchestration/study tests; `git diff --check`; AST import scan found no imports of the deleted Codex transport modules; `find_spec` returned `None` for both removed modules. No real Pi/Codex, COM/FE/optimizer, or scientific study was run.
- Active legacy-worker status remains **unknown**. No processes or arbitrary run roots were inspected or manipulated. This remains a pre-merge owner gate; the Draft PR is for independent review only.

### Caller and safety-owner dispositions

| Area / callers | Disposition | Preserved owner / evidence |
|---|---|---|
| `orchestration/codex_queue.py`, `codex_callback.py`, automatic worker handoff, callback review, queue confirmation/ACK and session capture hook | Deleted; no replacement transport | Historical manifest/status parsing and observational status rendering remain; C2C state-access preflight remains independent. |
| `orchestration.cli.launch`, resume/recover, `worker.execute_run`, `run_manager.create_run` and lifecycle finalizers | Explicit rejection for retired transport-linked runs and Stage 4B/4C study types before spawn or writes | Non-agent synthetic CLI/Worker, process/worktree/storage/checkpoint guards, R5, and independent administrative closeout remain. |
| Stage 4B context/fingerprint, production, shakedown, direct production cell mode; Stage 4C production and `run-study` dispatch | Explicit unsupported-path rejection; no fingerprint reconstruction | Stage4B/4C protocol validation, scientific report contracts, reusable COM/design/optimizer implementation, and Stage4C's unresolved disposition remain. Stage4C's distinct shakedown/qualification helper is not a production replacement. |
| `reporting.github_review.export_review` for historical queue/Stage 4B/4C records | Keep report package generation; skip retired run-status mutation | Historical inputs and package bytes remain observable/exportable without rewriting old run status. |
| `.codex/hooks.json`, capture-session hook, guides and current documentation index | Remove capture hook; replace active instructions with retirement notice and link this plan | Historical inventory/decision plans retain old behavior as records. |
| Queue/callback-only tests vs mixed orchestration/study/report tests | Delete transport-only suites; add pre-side-effect rejection and read-only historical assertions; retain scientific/report regressions | Q1-A goldens/import guards and R2–R4/COM/optimizer fixtures remain in the prescribed validation set. |

**Unsupported entrypoints/options:** `sawopt.orchestration.cli review`; `confirm-queue`; `launch --continuation-mode queue`; `--thread-id`, `--queue-timeout-seconds`, `--codex-executable`, `--session-id`, `--session-file`, `--no-callback`, `--authorize-stage4b-production`, and `--authorize-stage4c-production`; `recover` and `launch --resume` for transport-linked/Stage 4B/4C runs; worker dispatch for such manifests; and direct `run-study` Stage 4B/4C plus Stage 4B context/fingerprint/production/shakedown and Stage 4C production callables. Rejections occur before process creation, state writes, or authorization-claim creation. Pure historical report export and status display are not execution routes.

## Delivery and stop

Draft PR [#109](https://github.com/miyabimm/saw-com-optimizer/pull/109) is open from `issue108-r6c1-codex-removal`; implementation commit `98cffa24545d1eb6c842aca92ca225d9717ad9cc` is the reviewed change set. Roll back that implementation with `git revert 98cffa24545d1eb6c842aca92ca225d9717ad9cc` if required. Per-file caller/safety dispositions, unsupported entrypoints, validation evidence, and active-run uncertainty are recorded above. Stop at Draft PR for independent review. No Ready/merge, C2, historical-data action or experiment follows automatically. The active legacy-worker owner gate remains open.
