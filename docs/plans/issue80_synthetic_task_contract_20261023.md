# Issue #80 — isolated synthetic detached-task contract (PR-A)

**Tracking:** [Issue #80](https://github.com/MasayaTakagi/saw-com-optimizer/issues/80), design parent [#77](https://github.com/MasayaTakagi/saw-com-optimizer/issues/77), mandatory cutover [#75](https://github.com/MasayaTakagi/saw-com-optimizer/issues/75).

**Scope/status:** `R6-C_PR_A_SOFTWARE_SYNTHETIC_ONLY`. This contract covers one opt-in, user-launched deterministic countdown worker and its local task ledger. It does not implement a scientific evaluator, optimizer resume, Pi/Codex session, service/scheduler, reboot recovery, old-queue cutover, or real-run feature. The existing `sawopt run/validate` and `python -m sawopt` interfaces remain unchanged.

## Command and boundary

The sole console entry point gains `sawopt synthetic-task launch|status|attach|stop`. Every operation requires an explicit `--root` naming an already-existing, absolute, private, empty controlled test directory (or one previously initialized by this feature). No environment/default root is consulted. Reject `..`, symlinked path components, repository-contained roots, the canonical resolved `SAWOPT_DATA_ROOT` and all descendants (or fail closed if the configured raw root cannot be resolved), non-directory/unowned or group/world-accessible roots, unexpected files, symlink/non-regular ledger artifacts, and malformed IDs before opening the ledger. First launch creates only `synthetic-tasks.sqlite3`, SQLite's WAL/SHM sidecars, and a bounded `synthetic-tasks.log` inside this root. It never selects or migrates `./runs`, `SAWOPT_DATA_ROOT`, old raw/checkpoint/session trees, or any historical data. No repository/physical/optimizer module is imported by the worker.

The internal worker is invoked only as a fixed `sys.executable -m sawopt.synthetic_worker` argv with validated run/attempt tokens; no shell, user-selected code/interpreter, callback, plugin or generic command runner. It uses `Popen(start_new_session=True, stdin=DEVNULL)` on supported Linux/WSL2 only. CLI import/help and status/attach never spawn or resume a worker. `attach` is a read-only status view, not an execution operation.

## Ledger and immutable request

SQLite is the only mutable lifecycle authority, stored directly under the explicit root and initialized in WAL mode with `synchronous=FULL`, foreign keys, bounded busy timeout, private permissions, fixed schema/version validation (including table constraints), bounded file/SQLite lock waits, and transactional state updates. Unknown schema, corruption, unsafe paths, or lock failure is an error, never a reset/migration. One task row carries its UUID `run_id`, canonical JSON request and SHA-256, unique bounded idempotency key, `authorization_test_only=1`, bounded UUID `attempt_id`, state, process owner `(PID, Linux /proc start-time ticks, boot ID)`, timestamps, durable countdown progress, and typed bounded error. `task_id` is intentionally omitted because this PR has one synthetic task kind and one run/attempt. The capped log is best-effort diagnostic only: a held log lock or log I/O failure is skipped and cannot block, fail, or change task lifecycle; it is never an independent status source.

The immutable request is limited to `synthetic-countdown-v1`, bounded step count and delay. Repeating an idempotency key with the identical request returns the original run ID and never creates a second attempt/worker; changing its request returns `IDEMPOTENCY_CONFLICT`. There is no task API for arbitrary commands, COM/FE, L-SHADE, optimizer work, or scientific claims.

## States and transitions

Normal lifecycle: `CREATED → STARTING → RUNNING → {STOP_REQUESTED → STOPPED, COMPLETED}`; bounded launch/worker errors may end in `FAILED`. Exceptional fail-closed classifications are `LAUNCH_AMBIGUOUS`, `PROCESS_IDENTITY_UNKNOWN`, and `RECOVERY_REQUIRED`. Each run has one bounded attempt; PR-A has no automatic retry or `resume` command.

- Commit `CREATED` and then `STARTING` intent before `Popen`. A crash in either window is observable but never causes status/attach or a repeated idempotency call to spawn a replacement.
- The worker must atomically claim the exact run/attempt and record its own verified Linux PID, `/proc` start time and boot ID before changing progress. A second process cannot claim the attempt. A crash around spawn/claim remains ambiguous unless that worker itself proves its identity in the ledger.
- Progress is committed durably after each bounded countdown step. Only the claimed owner can record progress or terminal completion. A lost process with a nonterminal ledger row is reported `RECOVERY_REQUIRED`, never `COMPLETED` based on a missing PID.
- `status` compares PID, start time, boot ID and the fixed worker argv/run/attempt identity, and fails closed on mismatch/unknown identity. `stop` requires the exact run and current attempt, validates that process identity, then commits `STOP_REQUESTED`; the worker observes it cooperatively at a step boundary. It never sends a signal to a stored PID. Missing, reused or foreign processes are not adopted or signalled.
- `status`/`attach` never change a task to successful, launch, or restart it. No automatic reboot/WSL restart recovery exists; interrupted state remains ambiguous/recovery-required for a later, separately authorized stage.

## Supported platform, durability and validation limits

Initial support is Linux/Ubuntu/WSL2 only. `boot_id` and `/proc` process start time are required; inability to read/verify them blocks claim/status/stop. WAL plus `synchronous=FULL` improves local transactional durability, but does not guarantee survival of faulty storage, filesystem/hardware lies, abrupt host/power failure, copied roots, or non-cooperating same-user mutation. No cross-host/shared-filesystem guarantee is made. WSL/host reboot does not restart a task. Manual recovery, same-run scientific replay, exactly-once evaluation/publication, native Windows, and agent-session continuity are explicitly out of scope.

Tests use only unique temporary roots and test-owned synthetic children. The detached integration proves progress advances after the launch CLI exits and a fresh CLI can observe it; concurrent/idempotent launch, failure/corruption/version/lock states, identity mismatch, aliased raw-root rejection, and safe cooperative stop under held diagnostic-log contention are tested without opening real raw/checkpoint/session paths. No COM/FE, study, optimizer qualification, historical-data access, or R5 schema change is performed.
