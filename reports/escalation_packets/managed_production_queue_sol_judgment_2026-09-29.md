# Managed production queue continuation — pre-implementation Sol judgment

**Date:** 2026-09-29
**C2C task:** `c2c_6d91`, PLAN iteration 0
**Requested model:** `gpt-6-sol`
**Scope:** bounded orchestration architecture judgment; no implementation or Stage 4B launch

## Decision requested

Judge the control-plane design that replaces the nested
`codex exec resume <session-id>` callback for new managed runs with the
qualified exact-original-thread, one-shot `codex queue --thread ... --message`
continuation. Optimizer state/results/checkpoints must remain independent of
delivery, and existing legacy manifests/runs must retain their old semantics.

## Proposed design

- Add a queue-specific adapter; keep `codex_callback.py` and historical
  `exec resume` behavior for legacy runs. Queue invocation always names the
  immutable pre-detach Desktop thread ID and message explicitly; never use
  `--last`, thread discovery, SDK fallback, or automatic retry.
- Capture the exact target thread, C2C task/iteration, `NEXT_EXPECTED_STEP`,
  run/result reference, and unique delivery sentinel in a queue-native
  immutable manifest before run creation/detach. Preserve schema-v1/v2 readers
  and legacy callback fields.
- After durable optimizer completion, atomically persist a per-run one-attempt
  claim before starting the queue process. A crash, timeout, nonzero result, or
  lost acknowledgement after claim is ambiguous and cannot reopen the claim.
  Queue delivery status must never alter `COMPLETED`, `FAILED`, or
  `REVIEW_WAITING`, optimizer result files, or checkpoint lifecycle.
- Run queue preflight before creating the run: resolve CLI, validate normal
  Windows user/profile identity, capture CLI version, confirm explicit
  `--thread` and `--message` in `codex queue --help`, and validate C2C/HANDOFF
  metadata. No `exec resume` preflight is required in queue mode.
- The receiving original thread validates trusted current-thread identity,
  task/run/attempt/sentinel, exactly one claim, durable terminal optimizer
  state, and result existence before idempotently recording receipt. Receipt
  may resolve sender ambiguity; it never reruns the optimizer or sends again.
- Test with injected fake queue and detached harmless work. After all tests, the
  C2C PLAN authorizes one real harmless same-thread queue qualification; no
  SAW/Stage 4B optimization is allowed.

## Judgment questions

1. Is a durable atomic claim before process creation sufficient for at-most-one
   locally initiated attempt, and what crash/ack states must fail closed?
2. What synchronization and receiver confirmation conditions are mandatory to
   avoid duplicate sends or lost status updates?
3. Should queue-native manifests use a new schema version, or are additive
   nullable fields safe while preserving legacy interpretation?
4. Identify any bounded correction required before implementation.

## Constraints

No ACL changes, permission widening, Full Access, state DB relocation/deletion,
callback elevation, or SDK fallback. Do not change Stage 4B scientific
conditions or launch Stage 4B.

## Judgment received — 2026-09-29

**Decision: APPROVE_WITH_CONDITIONS.** A durable pre-spawn claim can provide at
most one locally initiated attempt only if it is a cross-process atomic create
or CAS on a per-run key, durably flushed before process creation, and honored by
every worker, recovery, and manual sender path. It cannot establish delivery.
Crash after claim but before spawn, timeout, nonzero exit, or lost
acknowledgement remains ambiguous and must not permit resend.

Mandatory conditions:

- Keep optimizer disposition and delivery status orthogonal. Distinguish at
  least unclaimed, claimed/unknown, sender-accepted, receiver-confirmed, and
  ambiguous states. None reopens a claimed event.
- Include attempt UUID, immutable exact thread target, sentinel, and timestamp
  in the durable claim. Use one lock/CAS discipline and atomic durable writes
  for claim, status, and receiver confirmation to prevent races.
- Receiver confirmation must use trusted current-thread identity and match
  task/run/attempt/sentinel, the single persisted claim, and durable terminal
  optimizer evidence. It must be idempotent and cannot rerun or replay work.
- Use an immutable transport discriminator for new queue runs. Prefer a new
  manifest schema version, while strictly preserving v1/v2 legacy loading and
  callback interpretation. A version bump is only avoidable if the existing
  schema already supports explicit transport discrimination and every reader
  is updated.
- The one harmless live qualification must allow delivery after the initiating
  turn yields and verify same-thread receipt. No Stage 4B or science change.

Requested target was `gpt-6-sol`; runtime-visible backend identity and actual
reasoning effort were not independently verified. No files were edited by Sol.
