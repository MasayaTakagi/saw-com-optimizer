# Issue #82 — synthetic-only same-run recovery contract

**Tracking:** [Issue #82](https://github.com/MasayaTakagi/saw-com-optimizer/issues/82), mandatory migration/cutover parent [#75](https://github.com/MasayaTakagi/saw-com-optimizer/issues/75), design record [#77](https://github.com/MasayaTakagi/saw-com-optimizer/issues/77), synthetic executor [#80](https://github.com/MasayaTakagi/saw-com-optimizer/issues/80).

**Authorization:** owner instruction `issue82を進めます`, recorded 2026-10-23 JST, authorizes implementation and verification only for an isolated synthetic countdown task. `R6-C_SYNTHETIC_RECOVERY_OWNER_AUTHORIZED / PI_CODE_READY / ALL_SCIENCE_PI_SESSION_AND_LEGACY_ACTIONS_GATED`.

**Starting source:** accepted PR #81 commit `58402bdff8ae13589a71decec5678a57e5147ce0`; PR #81 post-merge Actions #39983950665 reported success (638 passed / 1 skipped). Work is isolated in branch `issue82-r6c-synthetic-recovery` from this commit. The fetched `origin/main` ref was `90a99822777e646ceaf4e515acd67ada72bfad50` during setup, while the issue names the PR #81 merge as its baseline; the worktree therefore uses the explicitly authorized and verified PR #81 merge commit, which descends from that fetched ref.

## Scope and non-goals

Add one explicit `sawopt synthetic-task resume --root <absolute-private-synthetic-root> --run-id <id> --expected-attempt-id <id>` operation for the deterministic countdown only. Resume preserves one immutable request and `run_id`; it never invokes COM/FE, an optimizer, an experiment, a Pi session, or an external side effect. The only progress effect is a SQLite transaction that increments one integer. That transaction commit is the step's linearization point: an uncommitted step did not happen and can be discarded; a committed step remains authoritative. Do not generalize this recovery rule to evaluator calls, FE accounting, optimizer checkpoints, filesystem writes, or any side-effecting work. Unknown future task kinds must fail closed as `RECOVERY_AMBIGUOUS`.

No status/help/import/attach/normal idempotent launch, host boot, or Pi reconnect may resume or spawn a worker. Only an explicit `resume` can create a successor attempt. No production, scientific, optimizer, historical, raw/checkpoint/session, queue/callback, Pi, or legacy runtime work is in scope.

## Ledger versioning and compatibility

- Keep the sole ledger pathname `synthetic-tasks.sqlite3` and SQLite as the one mutable lifecycle authority. A new empty synthetic root initializes the strict schema **v2**; schema version is recorded in `PRAGMA user_version` and validated against exact table definitions and constraints.
- Existing v1 databases are never altered, migrated, renamed, repaired, or supplemented. The CLI routes v1 roots to their original launch/status/attach/stop implementation and behavior. `resume` on v1 returns typed `RECOVERY_UNSUPPORTED` without writing. Unsupported/unknown schema versions fail closed before any spawn or mutation.
- Do not add a second ledger, progress/checkpoint file, external evaluator, or competing status store. The v2 schema uses a task record for immutable request/current progress and attempt rows for durable process identity and full predecessor lineage. Both tables are updated in one SQLite transaction; every worker mutation is fenced by the current attempt ID and generation.
- A repeated idempotency key with the same request still returns the same run; a changed request is a conflict. Resume keeps the original `run_id`, canonical request SHA, idempotency key, `authorization_test_only=1`, task kind/version, and progress bounds. A new random `attempt_id` and monotonically increasing generation are created only by a successful explicit resume transaction.

## V2 identity and state contract

The v2 request and attempt records bind the task kind/version, original total and delay, immutable request SHA-256, run ID, idempotency key, test-only authorization marker, generation/predecessor chain, last committed progress, source-contract digest, Python executable content/runtime identity, and claimed `(PID, /proc start ticks, Linux boot ID)` plus expected worker argv identity. Source identity is computed from the fixed synthetic CLI, ledger, recovery implementation, and allowlisted worker source files; interpreter bytes and version are also fingerprinted. Inability to read or match those bytes/runtime is a typed failure, not permission to fall back. A worker verifies the frozen source/runtime identity before claiming; resume verifies it again before committing a successor attempt. No quiet cross-version migration is allowed.

Normal task states remain `CREATED → STARTING → RUNNING → {STOP_REQUESTED → STOPPED, COMPLETED, FAILED}`. `STARTING` is durable launch intent and is observationally reported as `LAUNCH_AMBIGUOUS` until the one worker claims that attempt. Resume is allowed only from an identity-matched, nonterminal `RUNNING` task whose current attempt was claimed and whose previous process is positively proven dead, with valid request/source/runtime/lineage/progress evidence. It commits the old-attempt disposition, new generation, predecessor link, unchanged progress, and new `STARTING` state atomically, then spawns the fixed worker. `COMPLETED`, `STOPPED`, `FAILED`, `STOP_REQUESTED`, `CREATED`, `STARTING`, and any ambiguous state are not resumable.

Process-death classification is Linux/WSL2-only:

- Require the persisted positive PID, process start ticks, boot ID, claimed attempt identity, and expected worker argv record. Never signal a stored PID.
- On the same boot, an absent `/proc/<pid>` established by `ENOENT` can prove death. A matching live `/proc` identity and argv means `WORKER_ACTIVE` and no spawn. A zombie is dead only when its start-time/boot identity matches the process identity previously claimed by the allowlisted worker.
- An unreadable proc record, unavailable boot ID, PID reuse, foreign argv, any present mismatching PID, incomplete owner identity, unclaimed launch, or uncertain state returns a typed fail-closed status and cannot spawn.
- After reboot, boot-ID change alone is insufficient. Resume requires the stored identity and all request/source/lineage/progress checks; if the old PID now exists (including as a foreign process), or its absence cannot be established, recovery is ambiguous and blocked. No host startup automation is installed.

The worker's initial claim is unique. An old attempt can neither claim nor write once a successor generation is current. A cancellation or terminal task cannot be superseded, and only stop with the exact current attempt ID may request cooperative stop. Status and attach are read-only and report, but do not repair, classify persistently, or launch.

## Crash / race matrix

| Boundary or state | Allowed result | Forbidden result |
|---|---|---|
| Before a progress transaction commits | Discard that not-yet-committed increment; continue from prior SQLite count only after safe explicit resume. | Count elapsed sleep or log text as progress. |
| After a progress commit | Resume from exactly that committed count. | Roll back or increment the same committed step twice. |
| Before resume's `BEGIN IMMEDIATE` transaction | No task/attempt mutation and no spawn. | Pre-create a successor or launch a fresh run. |
| During failed resume transaction | Roll back all lineage/state edits; no spawn. | Leave partial generation/attempt state. |
| After committed resume intent, before spawn | Leave `STARTING`/`LAUNCH_AMBIGUOUS`; no later resume from that ambiguous attempt. | Guess that no worker started and retry. |
| After spawn, before worker claim | Keep the unique attempt ambiguous until that one worker claims; no replacement attempt. | Spawn a second child or infer claim from elapsed time/logs. |
| During/after claim commit with lost CLI acknowledgement | Read-only status may observe the claimed owner; only the matching worker can write. If the ledger cannot establish the owner, remain ambiguous. | Create another attempt because acknowledgement was lost. |
| Two explicit resumes with the same expected attempt | SQLite transaction plus current-attempt compare allows at most one successor; the loser gets `ATTEMPT_MISMATCH`/`ALREADY_RESUMED`, no spawn. | Two active successors or silent idempotent second spawn. |
| Original worker races with resume or is stale | Progress/terminal writes require the current attempt ID, generation and owner identity; stale writes affect zero rows and fail. | Old worker can complete or change progress on the successor. |
| PID absent vs reused/foreign/unreadable | Only positive death evidence is resumable; any mismatch/uncertainty is typed and blocked. | Treat unknown process identity as death or signal it. |
| User stop/cancel, `STOP_REQUESTED`, `STOPPED`, `COMPLETED`, `FAILED` | Preserve terminal/cancellation state; reject resume. | Turn a user cancellation or terminal result into a retry. |
| Corruption, unknown schema, source/runtime mismatch, untrusted root, missing authorization marker, impossible lineage/progress | Return typed error/status; no write/spawn. | Reset, migrate, repair, or start a new task implicitly. |

The restart-intent/spawn/claim gap intentionally sacrifices availability for no-duplicate safety. If evidence cannot prove exactly which attempt is authoritative, the state remains blocked for separate owner disposition; this contract does not add manual force-recovery.

Root validation rejects unsafe paths, then pins the verified Linux directory with a no-follow directory descriptor. SQLite, WAL/SHM sidecars, and best-effort logs are opened relative to that pinned descriptor so a pathname swap after validation cannot redirect task operations into the configured raw root. Temporary roots remain private, explicit synthetic-only directories; this does not claim safety against a same-user actor that can directly mutate the database contents.

## Required synthetic verification

Use only newly-created private temporary roots and test-owned countdown children. Tests must establish: interrupted worker after committed progress resumes in the same run at exactly that count with one new attempt; a live worker blocks resume; stale/repeated/concurrent resume yields at most one spawn; stale workers cannot write; status/attach/help/import remain observational; old v1 roots retain launch/status/attach/exact-attempt stop semantics and reject resume without mutation; v2 launch/status/stop/resume works; and corrupt/unknown schema, bad source/runtime, process identity ambiguity, cancellation, terminal state, unsafe roots and crash boundaries fail closed. Use deterministic barriers/transaction fault injection where practical; poll only for explicit worker progress/state synchronization and always clean up only identity-verified test-owned children.

This qualifies only recovery of the SQLite-backed synthetic countdown. It does **not** solve uncertain COM FE or external writes, qualify optimizer/checkpoint resume, authorize Pi-session work, or make scientific recovery safe.
