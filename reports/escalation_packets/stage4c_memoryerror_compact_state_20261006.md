# Escalation packet: Stage 4C L-SHADE MemoryError repair

Date: 2026-10-06  
Run: `20261005_132015_3b263c`  
Production source: `c52ba5873f4625d6426c79347793d08dfb9afa0a`

## Decision requested

Review the bounded cache/checkpoint design and failure-state lifecycle for a
root fix. Do not implement, resume, delete, or mutate the existing production
run. Do not authorize or start another production run.

## Evidence and suspected cause

The sole attempted cell (`P_D/seed20261007`) is `INCOMPLETE` at 80,000 unique
evaluations with `MemoryError: `; `str(MemoryError())` is empty. The 80k summary
is absent. The latest durable checkpoint is roughly 774 MiB and corresponds to
the prior 64k durable point. `stderr.log` contains only `{"error":""}`, so the
specific failed allocation is not recoverable from the current raw evidence.

At source SHA `c52ba58`, `LShadeBackend._cache` retains a deep-copied evaluator
mapping for every canonical design. State version 3 serializes every mapping.
Checkpoint validation parses the whole JSON and loads a probe backend; writes
validate the temporary and existing latest generations. The Stage 4B/4C cell
runner also reconstructs counters from all cache results and copies/ranks all
cache values at each checkpoint. This creates large persistent state and
multiple simultaneous materialized copies. The implementation cannot prove
which individual allocation raised MemoryError; the evidence supports cache /
checkpoint amplification as the root cause class.

## Proposed invariants

- Cache identity is canonical design key plus last frequency-grid version; a
  separate compact comparator-rank/vector/order index supplies exact historical
  finalist ranking without evaluator payloads.
- Full results stay only for active population/incumbent and bounded finalist
  records (16 for Stage 4C), including rejected proposals. This preserves
  historical finalist selection.
- A same-grid historical hit does not call the evaluator and cannot enter the
  population; a stale-grid hit refreshes without charging unique evaluations.
- RNG, proposal/duplicate/cache-hit counters, population, archive, incumbent,
  bounds, schedule, grid version, and traces remain trajectory-identical.
- Study counters are checkpointed atomically with optimizer state rather than
  reconstructed from discarded evaluator payloads.
- Bump the state version and reject v3 before parsing the full checkpoint; do
  not migrate or resume the failed run.
- Persist exception type/message/repr/traceback and last durable cell/budget.
  Worker-observed child nonzero exit must produce durable terminal failure
  state. If the worker itself disappeared, recovery must not leave RUNNING or
  overwrite completion evidence; it records an orphan disposition until a
  deliberate closeout is defined. Never mark a run failed or release its
  active-run registry while a child is alive.
- Preserve the repository rule that the active-run registry remains until the
  failure evidence is published and `REVIEW_WAITING` is durable.

## Required proof

Duplicate-heavy deterministic trajectory parity; checkpoint/resume parity;
frequency-grid exchange parity; bounds-update parity; exact stable top-16
finalist parity; persistence of counters; compact checkpoint sizing with large
synthetic evaluator payloads; and a 96k synthetic smoke. Orchestration tests
must cover nonzero optimizer exit, worker/child liveness, durable failure
diagnostics, and registry lifecycle. The frozen scientific contract is
unchanged. Any production continuation or new production run requires separate
user authorization.

## Sol judgment — approved with safeguards

Sol approved the compact canonical key/grid-version index plus bounded retained
result records. It specifically required all historical candidates (including
rejected proposals) in the exact cumulative top-16 shortlist, stable insertion
order for equal rank, direct persistence of `GeometryGateCounters`, stale-grid
unique-count parity, v3 rejection before whole-file parsing, full traceback
diagnostics, and no finalization/release while a child is alive. Sol confirmed
that the scientific study conditions must remain unchanged and no production
run is authorized.

## Implementation validation

- TDD regression coverage verifies duplicate-heavy trajectory parity,
  checkpoint/resume parity, frequency-grid exchange, expanded-bounds behavior,
  stable finalist ties, counter state persistence, non-finite rank serialization,
  large-payload compaction, and pre-parse v3 rejection.
- The relevant optimizer, study, and orchestration suites pass: 44 tests.
- The full repository suite passes: 350 tests and 20 subtests.
- A synthetic 96,000-entry history-storage smoke completed in 17.248 seconds.
  It serialized and reloaded 96,000 rank/index rows while retaining 16 full
  finalist records plus 234 active-population records. The resulting compact
  checkpoint JSON was 56,098,481 bytes. An 8 KiB payload retained for every
  design would contribute at least 786,432,000 payload bytes before JSON and
  Python-object overhead. This smoke validates history storage/round-trip, not
  an optimizer trajectory or a production run.
- `git diff --check` passes. No Stage 4C production or shakedown was launched.

The original run was rechecked read-only after the repair work. Its orchestration
status still says `RUNNING`, but neither recorded PID (`21068` worker,
`36644` optimizer) exists. The sole cell remains `INCOMPLETE` at 80,000 unique
evaluations with the original blank `MemoryError` message; no B80000 summary is
present, and the latest checkpoint remains 811,213,260 bytes. No recovery,
closeout, or evidence rewrite was run. The exact failing allocation remains
unknown because the original child emitted no traceback.

The existing data-storage policy keeps a failed run registered until failure
evidence is published and `REVIEW_WAITING` is durable; implementation follows
that stricter lifecycle rather than clearing the marker at optimizer failure.
