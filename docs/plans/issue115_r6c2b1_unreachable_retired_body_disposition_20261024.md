# Issue #115 — R6-C2B1 retired-body disposition

**Status:** `FIVE_GUARDED_BODIES_REMOVED / DRAFT_PR_AND_EXACT_HEAD_CI_PENDING`

**Scope/base:** Issue [#115](https://github.com/miyabimm/saw-com-optimizer/issues/115), C2B0 inventory [#113](issue113_r6c2b0_legacy_owner_caller_inventory_20261024.md), base `ec2c28350ce51edcaaba3b4943c5e5ee0c1ab23e` (merged PR #114). This is a software-only removal of unreachable source text after existing unconditional retirement guards.

## Exact source disposition

Only the post-`raise RuntimeError(...)` bodies in the five Issue #115 functions were removed:

| Module / public function | Removed unreachable lines | Retained guard |
|---|---:|---|
| `studies.hybrid_stage4b.load_stage4b_context` | 148 | `legacy Stage 4B context and fingerprint regeneration are retired` |
| `studies.hybrid_stage4b.verify_production_manifest` | 96 | `legacy Stage 4B production authorization is retired` |
| `studies.hybrid_stage4b.run_stage4b_shakedown` | 80 | `legacy Stage 4B shakedown execution is retired` |
| `studies.hybrid_stage4b.run_stage4b_production` | 22 | `legacy Stage 4B production execution is retired` |
| `studies.hybrid_stage4c.run_stage4c_production` | 49 | `legacy Stage 4C production execution is retired` |
| **Total** | **395** | |

Each signature, docstring, exception type/message, module import identity, and `__all__` export remains unchanged. Static AST comparison against the base confirms that only these five bodies differ; the other top-level nodes in both modules are unchanged. Public aliases/helpers including `run_matched_cell`, `_run_cell`, `_cell_failure_payload`, the sampling/source/path helpers, and Stage 4C contract/report helpers remain present. `run_stage4c_shakedown` is unchanged and remains **STOP_FOR_OWNER**: it was not invoked, edited, disabled, or tested through execution.

## Regression and evidence

- Kept existing negative retirement tests. Added one focused mock test for `verify_production_manifest`: `_read_json` and `_source_state` are patched to fail if called; the public function still raises its exact retired error before either helper or output-path effects. Together the existing and new cases directly cover all five public retired entrypoints.
- Focused Stage 4B/4C and Issue #108 retirement suites: **54 passed**.
- Focused physics/core/design/optimization, Q1-A foundation, checkpoint, R5 store/review, and orchestration safety suites: **326 passed, 14 subtests passed**.
- Q1-A canonicalization verifiers: public **92/92** and leaf **92/92**, fixture SHA-256 `3763c5746f4bf800a54f310aeeb94f493520fc0962505b1eed85d3c32b589aa2`. Both fresh-process import guards passed with no forbidden imports.
- `compileall` and `git diff --check`: passed.
- A full local no-sync test attempt used an existing environment from another worktree because this worktree had no test-enabled `.venv` and its existing environment lacked pytest. It reported **738 passed, 14 failed, 15 subtests passed**. All 14 failures were detached synthetic-task subprocess cases ending in `LAUNCH_AMBIGUOUS` / no worker claim (12 in `test_synthetic_task_worker.py`, one real test-owned zombie case in `test_synthetic_task_resume.py`, and one synthetic task case in `test_pi_session.py`). The reused environment's editable install points at another worktree; this is a plausible source-path mismatch, not a proven cause. No tests were deleted or weakened. The exact clean-checkout PR-head GitHub Actions result is required to resolve this local discrepancy.
- **Exact PR-head Haswell CI:** pending; report the final PR-head SHA and Actions result in the Draft PR handoff. No earlier/base CI is substituted for this check.

## Explicit non-scope / rollback / next gates

No physics, design, evaluation, optimization, budget, seed, checkpoint, R5, synthetic R6, process/worktree/storage safety, historical report/source identity, or raw/checkpoint data was changed. No COM/FE study, optimizer qualification, production run, historical replay, raw/checkpoint access, active PID/process inspection, or external data operation was performed. Stage 4C shakedown remains untouched and gated.

Rollback is by reverting the complete reviewed PR merge commit; do not restore a retired execution route or alter historical evidence. C2B2 command-alias policy is deferred. C2B3 Stage 4C shakedown remains `STOP_FOR_OWNER`. Submit one Draft PR and stop for independent review; do not mark Ready, merge, or start follow-on work.
