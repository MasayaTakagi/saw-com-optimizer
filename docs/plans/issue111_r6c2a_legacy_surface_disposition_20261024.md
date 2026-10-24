# Issue #111 — R6-C2A legacy surface disposition

**Tracking:** [Issue #111](https://github.com/miyabimm/saw-com-optimizer/issues/111), under #75/#71/#53.

**Disposition:** `C2A_IMPLEMENTED_IN_DRAFT / SOFTWARE_ONLY / C2B_NOT_STARTED`.

**Base:** `604091d550c8fad302ed179e3e177d3a1ee3c7c1` (merged PR #109).

**Scope:** repository-controlled hooks, tests, documentation, and static callers.
No user-level hook, external C2C checkout, active process, raw run, checkpoint,
credential, or provider/session state was inspected or changed.

## Owner authorization and boundary

The Issue #111 body and owner work-order comment authorize this bounded C2A
software cleanup after PR #109's merged-main Haswell CI succeeded. The verified
main CI was Actions `40087895187`, SUCCESS, 767/767. C1 retired active
Codex queue/callback execution, its old Stage 4B/4C production paths, and
session-capture hook. C2A removes only the remaining positively isolated
project-local C2C/Codex hook/probe surface and stale current-facing guidance.

This is not authorization to inspect or operate user-global hooks, external
C2C state, workers, raw/checkpoint trees, real Pi/Codex/Node/provider sessions,
COM/FE, optimizer or production studies. It changes no physics, numerical
contracts, optimizer/search/budget semantics, Q0/Q1 status, historical evidence,
raw data, or safety behavior. The existing worktree/storage/process safeguards,
R5 store/export, R6 synthetic CLI/Worker, historical records, and Q1-A/R2–R4
test contracts remain outside this retirement.

## Caller and safety-owner dispositions

| Path / symbol | Before | Disposition and evidence |
|---|---|---|
| `.codex/hooks/c2c_state_access_preflight.py` | Standalone tool probes the external C2C state path by creating, flushing, and deleting a canary. The only repository wrapper caller was the adjacent `.cmd`; tests imported it from disk and `docs/c2c/OPERATIONS.md` documented direct execution. No product source, active worktree/storage/process-safety owner, R5 API, or R6 CLI caller was found. | **DELETE.** It was a legacy C2C state-access probe, not `worktree_safety`, active-run protection, R5 path validation, or a new filter-design safety owner. Its canary behavior/test is retired; no external C2C state was touched. |
| `.codex/hooks/c2c_state_access_preflight.cmd` | Windows wrapper selected a Python executable and invoked the adjacent Python probe. No other checked-in caller beyond historical operations prose was found. | **DELETE** with the isolated probe. |
| `.codex/hooks.json` and `.codex/` container | Tracked JSON had an empty hooks object. `test_hook_policy.py` asserted the empty object and that the local probe remained. The empty file did not prove absence of user-level/external hooks. | **DELETE** the project-local configuration/container. Replace the old positive-presence policy test with a negative regression guard that fails if `.codex` or `.c2cignore` is reintroduced. No claim is made about external hook absence. |
| `.codex/runtime/` | No tracked or present directory/runtime was found in the reviewed base. | **NO FILE TO DELETE.** It is recorded as absent, not treated as a hidden consumer. |
| `.c2cignore` | C2C-only ignore rules. Repository search found no product parser/runtime caller. References were in archival C2C handoffs, historical reports/baseline, and old planning/inventory records. It is not Git's `.gitignore` and was not the owner of current worktree/storage safety. | **DELETE** as obsolete local C2C configuration. Keep dated historical references unchanged. Do not claim it provided Git or raw-data protection. |
| `tests/unit/test_c2c_state_access_preflight.py` | Dedicated unit suite exercised the removed temporary C2C-state canary/probe, including an informational SessionStart output path. No independent current safety consumer exists. | **DELETE** with the feature. Its synthetic C2C canary coverage has no current product meaning. |
| `tests/unit/orchestration/test_hook_policy.py` | One test asserted the empty local hook map and retained probe; a second pinned historical guide wording to Issue #108. | **REPLACE** local-hook presence with a repository-level negative absence/nonactivation test for `.codex` and `.c2cignore`, plus source/wrapper absence checks. Remove the stale-text assertion because current docs use the #109/#111 dispositions; link/status verification is recorded separately. No test examined global settings or claimed there are no outside callers. |
| `.codex/hooks.json` / local hooks vs user/global hook configuration | Only the repository-local empty file was observable through source control. | **KEEP_EXTERNAL_UNKNOWN.** Do not inspect, remove, or change user-level settings or external scripts. |
| `orchestration.worktree_safety`, `active_runs`, PID/process/path checks, locks, external-root validation, checkpoints, R5 store/review, R6 synthetic CLI/Worker | C1 disposition and current source show independent non-agent owners and current tests. | **KEEP_ACTIVE_SAFETY / KEEP_ACTIVE_SOFTWARE.** No path/function in these owners was changed or weakened. |
| C2C reports, `docs/c2c/baseline.json`, historical handoff/report files, Stage 4B/4C/Q1-A evidence and prior plans | Dated factual records and explicit evidence links; no active product caller. Several predate C1/C2A and describe earlier commands. | **KEEP_HISTORICAL_FACT.** Preserve raw/report bytes and old plan conclusions as dated evidence; current links now point to the superseding decision/disposition. No bulk deletion or history rewrite. |
| `tools/wsl/*` | Mixed host-preflight, environment/bootstrap, diagnostics, report collection, and old Codex/Stage4B/4C qualification behavior. `bootstrap-wsl.sh` installs old Codex CLI; `qualify-core.sh` invokes it and legacy study APIs. Other files own host/worktree diagnostics or qualification/reporting responsibilities. | **DEFER / DO NOT RUN OR DELETE IN C2A.** The WSL page is now explicitly archival/non-operational. No tool was run or modified; a separate per-file safety/qualification disposition is needed before changing these mixed scripts. |
| `docs/handoff/*`, root `handoff/*`, `reports/c2c_*` | Historical pilot instructions and reports, already dated/archival or linked as evidence. They are not runtime callers. | **KEEP_HISTORICAL_FACT.** Preserve; do not copy their former procedures into current policy. |
| `docs/plans/issue106_*`, `issue108_*`, old R6/R7 inventories and earlier async designs | Dated pre-cutover audits/plans, some with historically correct-at-the-time claims that hooks/probe/runtime were retained or C1 was pending. | **KEEP_HISTORICAL_FACT.** Do not rewrite their contemporaneous findings. This C2A disposition supersedes their present-tense local-hook claims. |

The repo scan found no additional source/test/CI/config dispatcher for the
C2C preflight wrapper. Historical prose/data keys remain intentionally
searchable as records. This is a repository-controlled inventory only; external
callers remain unknown.

## Documentation cutover

The requested current-facing and linked path groups were dispositioned
individually:

| Path | Disposition / caller evidence |
|---|---|
| `docs/README.md` | **KEEP_ACTIVE_INDEX / UPDATE.** Remains the only active docs index; now points to this disposition and distinguishes merged C1 from the C2A Draft PR. |
| `docs/architecture.md` | **KEEP_ACTIVE / UPDATE.** Records C1 retirement, C2A pending review, unsupported Stage 4B/4C production paths, and the separate C2B boundary. |
| `docs/guides/github_review_workflow.md` | **KEEP_ACTIVE / UPDATE.** Replaces stale Codex steps with Pi Code + GitHub Draft PR roles; links experiments authorization and says legacy production/transport unsupported. |
| `docs/guides/async_orchestration.md` | **KEEP_HISTORICAL_NOTICE / UPDATE.** No active launch, continuation, or queue procedure; links C1 and C2A dispositions. |
| `docs/guides/postrun_review_contract.md` | **ARCHIVE/TOMBSTONE.** Former exact-thread Codex/old exporter workflow is replaced by a short retirement notice linking the future-only R5 contract. Prior text remains in Git history. |
| `docs/guides/data_storage_logging_review_policy.md` | **KEEP_ACTIVE_SUMMARY / UPDATE.** Now defers to `docs/experiments.md`; describes R5 as future-only and preserves data/worktree boundaries without old queue or legacy exporter workflow. |
| `docs/guides/development_environment.md` | **KEEP_ACTIVE / UPDATE.** Names Ubuntu/uv/Pi Code/GitHub; no Codex install or user-level `.codex` steps. Warns that mixed WSL qualification scripts are historical and not authorized. |
| `docs/guides/worktree_safety.md` | **KEEP_ACTIVE_SAFETY / UPDATE.** Retains registry, path, process, lock, and removal protections; no longer presents the old orchestration launch/publication as current. |
| `docs/guides/checkpoint_lifecycle.md` | **KEEP_TECHNICAL / UPDATE.** Preserves checkpoint-owner details; adds non-authorization boundary and removes the old exporter command as current production guidance. No checkpoint code or numerical claim changed. |
| `docs/guides/new_experiments.md` | **KEEP_FORWARD_DESIGN / UPDATE.** Clearly non-operational; old R5 paths/exporter are marked not-current, while historical fingerprint design details remain. |
| `docs/guides/review_bundles.md` | **KEEP_AD-HOC_TOOL / UPDATE.** Retains already-authorized saved-run bundling notes; removes old `export-review`/`reports/experiment_reviews` as a production path and disclaims authorization to read raw runs. |
| `docs/guides/administrative_failure_closeout.md` | **KEEP_ACTIVE_SAFETY / UPDATE.** Retained only for separately authorized legacy-run closeout; clarifies R5 incompatibility and no resume/relaunch authority. |
| `docs/c2c/OPERATIONS.md` | **ARCHIVE/TOMBSTONE.** Removed the Node/C2C/preflight/queue command instructions from the current tree; preserves a short notice and Git-history pointer. |
| `docs/c2c/README.md`, `FROZEN.md`, `SECURITY_BASELINE.md`, `UPGRADE_POLICY.md` | **KEEP_HISTORICAL_FACT / UPDATE LABELS.** Index/status now states retired; security/upgrade bodies remain historical only and are not active protection or execution policy. |
| `docs/c2c/baseline.json`, `reports/c2c_*`, `handoff/c2c_pilot_validation.md` | **KEEP_HISTORICAL_FACT.** Retained unchanged as provenance; baseline references such as `.c2cignore` do not imply a current file or product caller. |
| `docs/handoff/C2C Secure Pilot Closeout・本運用移行 作業指示書.md`, `docs/handoff/C2C セキュア導入・固定運用 Pilot 作業指示書.md`, other `docs/handoff/*`, root `handoff/*` | **KEEP_HISTORICAL_FACT.** Existing dated historical banners and saved handoff/report links remain. No bulk deletion or editing of historical instructions. |
| `docs/plans/issue106_*`, `issue108_*`, earlier R6/R7/async plans | **KEEP_HISTORICAL_FACT.** Findings are retained as dated records, including superseded pre-cutover present-tense statements. This C2A disposition and current index now point to the latest decision; prior plans were not silently rewritten. |
| `tools/wsl/bootstrap-wsl.sh` | **DEFER / DO NOT RUN.** It installs the retired Codex CLI, modifies shell PATH/profile, and creates a WSL checkout; only the archived WSL qualification page documents its invocation. Not changed because it is mixed environment setup, not an isolated local hook wrapper. |
| `tools/wsl/qualify-core.sh`, `qualification_smoke.py` | **DEFER / DO NOT RUN.** The shell script launches Codex and runs numerical/checkpoint qualification; the Python smoke imports retired Stage 4B/4C study APIs. Both are outside C2A and have no current authorization. |
| `tools/wsl/preflight.ps1`, `install-wsl.ps1`, `diagnostic-helpers.ps1`, `test-diagnostics.ps1` | **DEFER / KEEP SAFETY SCOPE.** These contain generic Windows/WSL inventory, gated installation, diagnostic classification, and tests in addition to any Codex metadata; no broad deletion or execution was authorized. |
| `tools/wsl/collect-report.sh` | **DEFER / KEEP ARCHIVAL REPORTER.** It aggregates prior qualification artifacts including Codex status; no independent product caller or current report use was established. Not run or edited. |

Current operational links point to the GitHub/Pi Code workflow, R5/R6 synthetic
boundaries, and retained worktree/storage safety. Historical handoffs, source
identities, C2C reports, and scientific evidence remain preserved; none is a
current authorization or runtime-support claim.

## C2B follow-up proposal — not started or authorized here

C2B should create a separate per-symbol owner/caller matrix before any further
source retirement. Proposed review units (no code changed in C2A):

1. `studies.hybrid_stage4b` unreachable body behind the unconditional retired
   runtime guard: identify which functions are genuinely dead versus separately
   reusable numerical helpers, preserve current regression evidence, and
   remove only individually proven dead symbols.
2. `sawopt.__main__` legacy dispatcher: enumerate `simulate`, `optimize`,
   `sweep`, `report`, `run-study`, `stage4b-shakedown`, and `export-review`
   callers/configs; specify unsupported Stage 4B/4C behavior and retain
   unrelated or historical-report behavior where it still has a caller.
3. `orchestration` remaining run-manager/worker/CLI functions: distinguish
   dead lifecycle/agent-era code from active worktree, process, PID, path,
   status, checkpoint, administrative-closeout, and historical read-only
   owners. Keep all active safety until a reviewed replacement or explicit
   per-symbol disposition exists.
4. Mixed `studies`, `reporting`, `runtime`, `core`, and `problem` modules:
   trace dynamic dispatch and test/evidence callers before proposing deletion;
   preserve COM/design/evaluation/optimization behavior, R5, synthetic R6, and
   Q1-A evidence. Do not use package names or grep counts as dead-code proof.
5. `tools/wsl` functions: separately classify host preflight, installation,
   provider bootstrap, qualification-smoke, and reporting functions; keep
   safety diagnostics distinct from the retired Codex/Stage4 paths.

C2A itself does not create or start C2B, R7, or another runtime feature. Each
requires its own authorized scope and independent review.

## Validation and rollback

### Validation evidence

- Exact reviewed implementation commit `60bc630a331d2db382b40152f32e4bcfdb89170d`
  passed full GitHub CI run [40090087980](https://github.com/miyabimm/saw-com-optimizer/actions/runs/40090087980): `OPENBLAS_CORETYPE=Haswell`, fixed-evaluation numerical reproducibility diagnostic PASS, **751 collected / 751 passed**. The full unfiltered suite includes the Q1-A public/leaf golden verification and import guards.
- The test delta is accounted for: the dedicated C2C preflight module had **15 collected cases** (14 test functions, one two-value parametrization), all removed with that isolated feature. The former hook-policy file had two tests; one guide-wording assertion was retired and the hook-presence check was replaced with one negative absence guard. Net suite collection changed from the verified PR #109 baseline 767 to 751 (**−16**), consistent with those removals/replacement.
- `python3.12 -m compileall -q src tests` — PASS.
- Focused hook-absence guard — PASS by direct stdlib invocation. Local pytest could not be run: the fresh worktree has no `.venv` and system Python has no pytest. No dependency synchronization or installation was performed; exact-head GitHub CI is the full-suite evidence.
- `git diff --check` and staged diff check — PASS. Relative Markdown link check — PASS across all changed/new Markdown files. Static `src/` and `scripts/` scan found no reference to the removed hook path.

The implementation commit above passed CI before the documentation-only validation-record update in this plan. The Draft PR's current exact head and its final CI status are recorded on GitHub; this PR remains stopped for independent review. CI success is not external acceptance.

No active worker or external hook absence is inferred. No process/root audit was
repeated; Issue #110's accepted bounded PASS_SCOPED disposition is not expanded
here. Roll back a merged C2A change only with `git revert <whole_C2A_merge_sha>`;
never alter old run roots, user-level hooks, checkpoints, historical data, or
scientific files during rollback.
