# Issue #96 N1 — synthetic same-run transaction/recovery contract

**Date:** 2026-10-24 JST
**Status:** `OWNER_AUTHORIZED / TEST_OWNED_SYNTHETIC_ONLY / IMPLEMENTATION_IN_PROGRESS`
**Base:** `63f837b14ba12be6fe4299b1e1759d423f655da2` (verified GitHub `main`, PR #95 merge).
**Authority:** Issue [#96](https://github.com/MasayaTakagi/saw-com-optimizer/issues/96), owner work order [comment](https://github.com/MasayaTakagi/saw-com-optimizer/issues/96#issuecomment-6380953524).

This contract scopes N1 software verification only. Its maximum result is
`SYNTHETIC_TRANSACTION_RECOVERY_PASS`; it does not qualify a COM/FE evaluator,
scientific optimizer restart, Q1 gate, Pi session, or legacy cutover.

## 1. Test-owned scope and immutable identity

The additive seam is test-owned and opt-in under `tests/`; it is not a new
product CLI, worker, scheduler, or default path. It composes a deterministic
injected Python evaluator, an isolated SQLite transaction journal, the current
L-SHADE `state_dict`/`load_state_dict` and `CheckpointStore` interfaces, and
R5 `ExperimentRun` plus `export_review_package`. All roots are freshly created
private temporary roots in a test. It must reject symlinked roots, worktree/raw
root aliases, and unexpected entries before writing. It never opens any
external/current run or historical evidence.

Each journal record freezes these exact identities as data:

- the R5 `experiment_id` and its unchanged R5 `run_id` (the same `run_id` is
  used by the journal; each recovery process gets a distinct `attempt_id`);
- owner authorization reference `#96` / comment `6380953524`, with an explicit
  `authorization_test_only=true` marker;
- test execution-source SHA (`63f837b14ba12be6fe4299b1e1759d423f655da2` for
  the base under test; this is test provenance, not a new production source
  identity), canonical effective-config SHA, model SHA, search-grid SHA, and
  validation-grid SHA;
- exact expected-cell roster/hash, topology/design identity and bounds,
  optimizer/backend/runtime identity, seed and RNG identity, requested/hard
  search budget and validation horizon.

For this smoke fixture the requested unique budget and hard maximum are
intentionally equal to `search_fe_limit`; both are recorded separately in the
frozen N1 identity and checkpoint receipt. The raw/review identity and schema
remain owned by R5. No authorization or transaction fields are injected into,
or added to, R5 schema v1. The N1 ACK is
only a local test-journal record of the exact exported package; it is not a
GitHub push or a review acceptance. The journal
binds to the R5 `run_id`; the R5 manifest independently binds source/config/
model/grid/roster/budget and artifacts. A test assertion correlates their
identities before accepting evidence.

## 2. State owners and durable order

| State | Sole owner | Contract |
|---|---|---|
| Request/run identity, test authorization reference, `attempt_id` fencing, evaluator keys/results, checkpoint receipts, local R5 export intent/ack | Fresh test-owned journal | Separate minimal fixture-only WAL schema, never an existing task ledger. Its attempt is a test-harness fence; fault subprocesses are synchronously waited, not detached production workers. A committed result must identify the exact claimed candidate; duplicate claims/results fail closed and cannot start another evaluator call. |
| L-SHADE RNG, population/archive/memory, cache, unique FE and proposal counters | Existing optimizer state/checkpoint APIs | Save/load unchanged state format through `CheckpointStore`; the fixture receipt is optional `extra_state` via the existing checkpoint-session interface. |
| Frozen raw run, expected roster, cell counts, raw artifacts and checkpoint hashes | Existing R5 `ExperimentRun` | New fixture run only. No schema or lifecycle changes. |
| Deterministic compact review package and hashes | Existing R5 `export_review_package` | `READY_FOR_REVIEW` is not a GitHub publication, scientific acceptance, or owner acceptance. Never overwrite. |
| Detached countdown status/attempts | Existing #80/#82 `synthetic_task_ledger` and `synthetic_task_recovery` | Unmodified and not repurposed to execute an evaluator. Existing v1/v2 contracts remain unchanged and their regression tests are retained. N1 does not claim to replace their persisted PID/boot/argv fencing or qualify an integrated detached evaluator worker. |

The happy-path test runs the initial optimizer/checkpoint attempt in a child
process, waits for that exact child to exit, then opens the same run/journal and
validates/restores the persisted checkpoint in the parent before creating one
successor attempt. Crash-boundary tests also use only synchronously waited
children under fresh fixture roots. This is a controlled test seam, not an OS
process supervisor or a change to the #80/#82 worker lifecycle.

The intended transaction ordering is:

`freeze R5 run + journal identity → claim(run_id, attempt_id, FE key) → injected evaluator → durable result-journal commit → optimizer state advances → atomic checkpoint commit carrying journal receipt → journal checkpoint receipt → R5 cell/artifact/checkpoint records → R5 close → durable local-export intent → R5 review export → exact package hash ACK in the test journal`.

No cross-store atomic commit is assumed. Only a journal result with a matching,
validated checkpoint receipt and exact optimizer counters/cache can be resumed.
The fixture journal does not own or open R5 package files; the test harness
verifies the existing destination through R5's deterministic no-overwrite
export path, checks run/experiment/source/provenance IDs, hashes every package
file, and only then passes that verified identity to the journal ACK method.
A result committed without a checkpoint that can be proven to include it is
`RECOVERY_AMBIGUOUS`, even when the deterministic fixture could recompute the
same answer. The harness does not repair optimizer state or silently replay an
FE. An evaluator key already committed but absent from the checkpoint cache is
also ambiguous, not a cache miss.

| Crash/failure boundary | Recovery classification |
|---|---|
| Before task/FE claim transaction | No evaluator ran; no automatic successor unless a fresh explicit claim is authorized by this test contract. |
| Claim committed, before evaluator invocation | `RECOVERY_AMBIGUOUS` unless a test-owned durable no-call witness proves invocation did not begin; no automatic retry. |
| During evaluator or after return but before result commit | `RECOVERY_AMBIGUOUS`; invocation may have happened; no second call. |
| Result commit succeeded, before optimizer checkpoint | `RECOVERY_AMBIGUOUS`; journal result cannot be applied to stale optimizer RNG/population/counters. |
| Atomic checkpoint temp write fails before replace | Previous valid checkpoint remains authoritative; if a result was already committed after it, `RECOVERY_AMBIGUOUS`. No temp-file promotion/repair. |
| Checkpoint replace succeeded, journal receipt ACK not committed | Reconcile only when checkpoint `run_id`, attempt, generation, canonical state hash, result-key digest, identity, FE/cache counts all exactly match the durable claim/result journal. Otherwise ambiguous. |
| Checkpoint receipt committed, before/after resumed attempt claim | Reopen only the same run from the exact matched checkpoint and create one fenced successor. Duplicate/stale attempt claim is rejected. |
| Local review export before durable ACK | Reconcile an existing package only by exact R5 IDs and byte/hash identity. A mismatch, absent proof, or uncertain acknowledgment is `RECOVERY_AMBIGUOUS`; no blind second export or overwrite. No GitHub push is performed. |
| After exact package ACK | Repeated export request returns the recorded identity without exporting again. Local export receipt, `READY_FOR_REVIEW`, and scientific/owner acceptance stay distinct. |

## 3. Pass and fail-closed criteria

The normal synthetic route must create one immutable R5 run, run a deterministic
injected evaluator, commit each stable idempotency key once, save/load an
existing optimizer state, and explicitly resume only from the same `run_id`,
exact validated checkpoint receipt, frozen identity, counters, budget and
roster. Its recovered RNG state, FE/proposal/duplicate/cache counters, optimizer
state and result keys must equal the uninterrupted synthetic fixture. It emits
one correlated R5 review package, and the journal records no duplicate
local export. No GitHub review package push or publication is attempted.

Fault tests cover duplicate attempt/FE claims and the claimed-before-evaluator
gap; evaluator interruption during and after return; result-journal commit
rollback and crash gaps; atomic
checkpoint temp-write failure and post-replace/lost-receipt reconciliation;
local export subprocess exits before export, after package creation and after
ACK; concurrent FE-key claims, result commits, resume and export, plus sequential
duplicate attempt claims;
mismatched experiment/source/config/model/grids/roster/topology/seed/requested
and hard budgets/runtime/authorization; stale attempts; missing/corrupt
checkpoints; missing, orphaned, uncommitted and duplicate-commit result records;
accepted-checkpoint counter/cache/result-key equality and R5 no-overwrite
behavior. Each injected fault path is classified as recoverable only with exact
evidence or as `RECOVERY_AMBIGUOUS`; untested or unknown states never mean
retry. This is not
an exhaustive qualification of every possible filesystem/process failure.

Use test-created roots only. Keep existing synthetic-task v1/v2 roots and
implementation unchanged; existing tests establish their compatibility. Do
not run COM/FE, real optimizer studies, production searches, Pi/Node/Bun,
providers/prompts/sessions, or historical/active raw/checkpoint operations.
No new dependencies, `uv sync`, schema migration, algorithm/RNG/budget/cache
change, production default change, old queue/callback change, or legacy
retirement is in scope.

## 4. Evidence ceiling and rollback

Tests establish a deterministic test harness composition only. They do not
observe physical evaluations and cannot pass Q1-01…Q1-23, prove real FE exactly
once, certify checkpoint restart for a scientific run, or authorize follow-up
work. Revert only this additive docs/index/test contribution to roll back;
accepted #80/#82, optimizer, checkpoint, and R5 contracts remain byte/behavior
unchanged. Submit
one Draft PR referencing `#96 #94 #75 #53`, then stop for independent review.
