# Stage 5A-2 Q0-R2 — proposed transaction, identity, serialization, and censored-comparison protocol

**Current status:** the requested Sol review returned `REQUEST_Q0_REVISIONS`; Q0 remains open and Q1 blocked. The review's open findings are recorded in §17. **Pre-review drafting status:** `READY_FOR_SOL_REREVIEW`; the four then-known Q0-R1 blockers were mapped to proposed specifications. This document remains a proposal, not Q0 approval, Q1 permission, or experiment authorization.

**Revision:** Q0-R2, 2026-10-21
**Base:** `main` / PR #48 merge `1db92ebc581b1e4e419f5122a652cf1e94219de5`
**Prior design:** [Q0-R1 packet](stage5a2_q0_protocol_revision_20261021.md)
**Prior judgment:** Q0-R1 Sol `REQUEST_Q0_REVISIONS` in Q0-R1 §14.
**Source scope:** read-only audit of the files in §13. No source, Stage 4C data, or experiment configuration is changed by Q0-R2.

## 1. Scope, authority, and retained comparison contract

This revision resolves only the design/replay/reporting blockers in Sol's Q0-R1 decision and PR #48 review. It retains Q0-R1's frozen-as-proposal comparison values and algorithm definitions: two topologies (`P_D`, `D_P`), two complete packages (existing L-SHADE and new controlled DE/rand/1/bin), three matched roots (`20261012`, `20261013`, `20261014`), 234 common initialization members, 4,096 unique search FEs per cell, the unchanged Stage 4C model/specification/bounds/grids/comparator, 16 history finalists, and serial execution. The 12 planned cells remain in the manifest and final report whether completed, stalled, interrupted, invalid, or failed to initialize.

The estimand is descriptive short-budget performance of the **complete algorithm packages**. Do not infer convergence, global optimality, mathematical infeasibility, or general algorithm superiority. No changed physics, objective, bounds, constraints, topology, budget, or L-SHADE search rule is proposed. The 65,536 limit is a proposal-count watchdog, never a wall-time cutoff.

The journal/state-machine and censoring choices below are Q0 decisions, not Q1 implementation options. Q1 may choose only equivalent data structures that satisfy every listed atomicity, ordering, and recovery invariant. Pi/GitHub review and later user acceptance are separate; Sol approval alone will not close Q0 or authorize Q1.

## 2. Finding disposition before Sol review

At pre-review drafting, every Q0-R1/PR #47 finding was mapped to an explicit specification and no blocker was intentionally deferred to Q1. `RESOLVED_WITH_SPEC` means a design contract was proposed, not that code or Q1 evidence exists; `RESOLVED_WITH_JUSTIFIED_ALTERNATIVE` identifies a specified, trajectory-preserving alternative to editing historical algorithm behavior. The Sol Q0-R2 re-review identified additional unresolved requirements; those are marked `BLOCKED_WITH_REASON` in the updated disposition table. Official Q1 IDs continue to live only in `docs/plans/stage5a2_q1_qualification_matrix.md`.

| Finding ID | Sol/PR finding (concise original issue) | Q0-R2 resolution | Location | Read-only source evidence | Resume/count/report effect | Official Q1 gate | State |
|---|---|---|---|---|---|---|---|
| R1-SOL-01 | Preserve and fully specify the existing L-SHADE package and the actual fallback control flow. | Retain exact resolved L-SHADE defaults, one-offspring behavior and first-`None` break; define separate fallback invocation/draw/proposal/evaluation counters and a non-algorithmic watchdog. | §§4, 5 | `lshade.py::_generation`, `_unseen_proposal`, `_sample_parameters`, `_flush_success_memory`, `_resize_population` | No operator change; each reachable draw/proposal counted once; cutoff only before a subsequent draw. | Q1-01, Q1-11 | `RESOLVED_WITH_SPEC` |
| R1-SOL-02 | Define durable proposal/intent/result/optimizer transitions, duplicate cursor idempotency, and no-FE L-SHADE updates. | Core event table and zero-FE commit are specified; Sol R2 still found incomplete identity genesis and RNG-call crash/retry transitions that prevent a complete replay contract. | §§3–6; §17 | `lshade.py::_generation`, `_evaluate`, `advance_to_unique_budget`; `checkpoint_session.py` | No-FE transitions are specified, but partial identity and RNG-call recovery remain blocked; no Q1 discretion. | Q1-03, Q1-06, Q1-16–Q1-19 | `BLOCKED_WITH_REASON` |
| R1-SOL-03 | Separate pre-sampling identity, population attachment and mutable journal/checkpoint identity; define sampler resume. | Pair/cell phases and immutable seal are specified; Sol R2 found no recovery rule for partial pair/arm identity creation and an unclosed exact evaluated-vector/attachment relationship. | §§7, 10; §17 | `hybrid_stage4b.py::_sample_stage4b_population`; L-SHADE normalized initialization; R2 Sol assessment | Population cannot enter Q1 until partial-genesis and exact evaluated vector/key identity are decided. | Q1-04, Q1-05, Q1-15–Q1-18 | `BLOCKED_WITH_REASON` |
| R1-SOL-04 | Specify complete PCG64 state and bypass the historical null-coercing state serializer. | Lossless PCG64 and Stage 5A-2-only raw-field L-SHADE codec; strict non-finite and nullable rules. | §8 | `lshade.py::_jsonable`, `state_dict`, `load_state_dict`; NumPy PCG64 state fields | Resume produces the same next draws; legacy null payloads cannot be misread as infinity. | Q1-14–Q1-18 | `RESOLVED_WITH_SPEC` |
| R1-SOL-05 | Define scientific trajectory equality separately from operational recovery; limit guarantees if evaluation is nondeterministic. | Equality fields and deterministic-evaluator boundary are specified; Sol R2 found RNG-call crash transitions and reconstruction/retry semantics still incomplete. | §§3.3, 5–6, 9; §17 | Evaluation callback and PCG64 source; R2 Sol assessment | At-least-once external/exactly-once durable FE boundary is clear, but deterministic replay remains blocked until draw-event recovery is fixed. | Q1-03, Q1-16–Q1-19 | `BLOCKED_WITH_REASON` |
| R1-SOL-06 | Compare censored cells only on valid common observed support, retain all pairs, do not forward-fill or use survivor-only rankings. | Exact FE support, status eligibility, endpoint, coverage and paired tuple rules; seven paper-only examples. | §§10–12 | `selection.py::GeometryFirstComparator`; R1 65,536 watchdog and 4,096 budgets | N_common uses valid committed trace prefixes, not requested FE or wall time; all 6 pairs remain visible. | Q1-19, Q1-20, Q1-23 | `RESOLVED_WITH_SPEC` |
| PR48-01 | Correct fallback control-flow description and account one fallback draw/candidate only once. | §4 separates invocation, every internal RNG candidate, canonical proposal, dispatch and committed FE with disjoint counter equations. | §4 | `lshade.py::_generation` lines around `attempts`, `_unseen_proposal`, `_evaluate` | Fallback candidate canonicalized internally is not counted again at `_evaluate`. | Q1-11, Q1-16 | `RESOLVED_WITH_SPEC` |
| PR48-02 | Make the standalone 23-gate Q1 matrix the only official ID assignment. | The Q1 matrix remains the only mapping; this packet references IDs but does not define another ID table. | §14 and matrix | Main `docs/plans/stage5a2_q1_qualification_matrix.md` has Q1-01…Q1-23 | Gate requirements updated in place only. | All affected existing IDs | `RESOLVED_WITH_SPEC` |
| PR48-03 | Preserve a truthful proposed/not-approved status and correct PR ancestry in the documentary record. | Q0-R2 is explicitly only a proposal awaiting review; the prior merged Q0-R1 packet and escalation log retain the corrected direction `a1cbd9e…` → `daa646b…` → `1db92eb…` without erasing history. | Header; preserved Q0-R1 packet and escalation log | Main PR #48 review follow-up; commits `25018b4…`, `05b1456…` in PR #48 history | No trajectory/accounting effect; prevents an inaccurate governance/provenance claim. | N/A — documentation/provenance only; not a Q1 behavior gate | `RESOLVED_WITH_SPEC` |
| PR47-01 | Freeze controlled DE, shared initialization, strict schema/ties, cutoff and resources. | DE semantics remain specified; initialization attachment/actual evaluation representation and transaction replay remain open per Sol R2. | §§1, 3–10, 13, 17 | R1 contract and the read-only source paths; R2 Sol assessment | No algorithm change, but no Q1 start until the newly identified representation/genesis/replay blockers are closed. | Q1-02–Q1-23 | `BLOCKED_WITH_REASON` |
| R2-SOL-01 | Define recovery after partial cross-journal Phase-I identity creation. | Unspecified whether and how pair/cell identities are reconciled if termination occurs between their separate commits; sampler must remain prohibited until all exact identities are verified. | §§3.1, 5, 7; §17 | Pair and arm identities are stored in separate journals; R2 Sol assessment | Resume must idempotently complete only matching missing identities or fail closed, before sampler/RNG starts. | Q1-15, Q1-16 | `BLOCKED_WITH_REASON` |
| R2-SOL-02 | Fully define RNG-call start/commit idempotency and reconcile retry with replay. | `RNG_DRAW_STARTED`/`RNG_DRAW_COMMITTED` lack full method/argument binding and crash recovery detail; reconcile retry cursor semantics with replaying pre-step draws and restoring local optimizer control state. | §§3.3–6; §17 | PCG64 facade, L-SHADE source RNG method calls; R2 Sol assessment | No logical draw may be duplicated or skipped; event payload and recovery state contract remains to be specified before Q1. | Q1-03, Q1-16–Q1-18 | `BLOCKED_WITH_REASON` |
| R2-SOL-03 | Bind exact sealed physical initialization to each optimizer's actual evaluated vectors/keys. | Attachment seals physical binary64 members, while L-SHADE receives normalized genotypes and reconstructs physical inputs; bitwise reversibility/evaluated-key equality is not specified. | §§7–8; §17 | `LShadeBackend.initialize`, `_physical`, `_canonical`; `HybridDesignSpace.canonicalize`; R2 Sol assessment | Define and validate actual evaluated canonical physical vectors/keys against the shared attachment before either arm's FE; no silently different start population. | Q1-04, Q1-05, Q1-07, Q1-15, Q1-17–Q1-18 | `BLOCKED_WITH_REASON` |
| R2-SOL-04 | Reconcile Q1 synthetic optimizer-state qualification with the statement prohibiting optimizer execution. | §14's “without optimizer execution” conflicts with required source-vs-hooked trajectory and synthetic optimizer transition/replay checks; distinguish COM/production studies from COM-free synthetic algorithm qualification. | §§14, 16–17 | Q1 matrix Q1-16–Q1-21 and R2 §14; R2 Sol assessment | Qualification scope is contradictory until explicitly clarified; Q1 cannot define its own authority. | Q1-16–Q1-21 | `BLOCKED_WITH_REASON` |

## 3. Durable journal and atomicity model

### 3.1 Storage and event rules

The Stage 5A-2 pair-sampler journal and each arm's execution journal use a new, versioned, append-only SQLite database schema (`stage5a2_txn_journal_v1`) with WAL mode and `synchronous=FULL`. The pair journal owns shared sampler draws and the population seal; each method-cell journal owns its independent evaluations, optimizer state and validation. SQLite is selected because one transaction can atomically commit an event group, idempotency key, counter projection, cursor and snapshot reference without adding a database dependency (Python's standard library interface suffices). Separate JSONL events plus checkpoint files are rejected: they cannot atomically commit duplicate classification/cursor/counters or result/cache/FE/history together without a second recovery protocol. Identity rows, event rows, idempotency keys, materialized counters/indexes, and checkpoint blobs are committed in SQLite transactions. A committed event has monotonically increasing `journal_sequence`, previous-event hash, canonical event bytes, and `event_hash = SHA256(domain_tag || previous_hash || canonical_event_bytes)`. Use one writer per journal. In a later separately authorized run, all pair/cell journals, snapshots, populations and full logs reside under the external persistent run root outside every Git worktree; this Q0 review stores no run data. Do not write scientific state to an independent JSON file and then infer that the journal also committed.

All event values use the codecs in §8; wall-clock timestamps, process IDs, and timings are operational fields and are excluded from event identity hashes that bind scientific state. A transaction ID is deterministic from `(owner_identity_id, phase, logical_operation_id, event_kind)`, where the owner is the pair identity for sampler/seal events and the cell identity for arm-specific execution events. Database uniqueness constraints make repeated commit attempts idempotent: an identical key and identical payload returns the already committed row; same key with different payload is a fatal integrity error. Counters are projections of committed events, not separate increments.

Every event has a defined atomic commit boundary. If the SQLite transaction does not commit, none of its rows, counters, RNG state, or cursor changes exist durably. If it commits, recovery observes all of them. No process may issue a subsequent sampler draw, optimizer proposal, or evaluator dispatch while a required prior transition is unresolved.

### 3.2 Counter ownership

- Sampler draw and rejection counters change only in a committed `SAMPLER_DRAW` transaction.
- Optimizer raw canonical-proposal count and no-progress watchdog count change only when a `PROPOSAL_ATTEMPT` is committed. An RNG call by itself is not a proposal.
- Duplicate count, retry count, and target/retry cursor change together with the matching `DUPLICATE_DETECTED` in one SQLite transaction.
- A unique FE counter, canonical result/cache, first-evaluation ordinal, rank-history index and exactly one search FE trace row change only in `EVALUATION_RESULT_COMMITTED`.
- A validation cursor and validation result change only in `VALIDATION_RESULT_COMMITTED`; validation never changes search FEs.
- Optimizer population/archive/memory/generation/success-batch/optimizer trace state changes only in `OPTIMIZER_STEP_COMMITTED` (or the initialization-specific commits in §5). An optimizer-only commit can have FE delta zero.
- Checkpoint sequence changes only in `CHECKPOINT_SNAPSHOT`; it is mutable recovery metadata and never part of scientific cell identity.

### 3.3 RNG transaction adapter and minimal Q1 instrumentation boundary

Q1 must place a deterministic journal-aware facade around the existing `Generator(PCG64)` calls used by each algorithm and sampler. On a normal call it delegates once to the same underlying generator method with identical arguments, records exact output plus pre/post PCG64 state, then returns the unchanged output. On replay it returns the recorded output and sets the in-memory generator to the recorded post-state **without invoking the underlying draw**. No journal, trace, checkpoint, comparator, or timer code may draw randomness.

The existing L-SHADE source does not expose all these boundaries. Q1 may add instrumentation-only callbacks at (a) random-method calls, (b) normal proposal canonicalization, (c) each `_unseen_proposal` internal candidate after canonicalization, (d) evaluation/cache decision, and (e) entry/exit of `_generation`. They must not change any existing arithmetic, branch, RNG method/arguments/order, proposal, cache semantics, or survivor/adaptation behavior. This is a necessary observability/transaction seam, not permission to reimplement or alter L-SHADE. Q1's uninterrupted baseline comparison must establish identical algorithm state and proposal sequence with hooks enabled.

## 4. Event names, counters, and L-SHADE fallback/watchdog

### 4.1 Event inventory and proposal accounting

In addition to the event names required by the user, the journal uses `PAIR_IDENTITY_COMMITTED`, `CELL_IDENTITY_COMMITTED`, `POPULATION_ATTACHMENT_SEALED`, `POPULATION_ATTACHMENT_ATTACHED`, `RNG_DRAW_STARTED`, `RNG_DRAW_COMMITTED`, `FALLBACK_INVOKED`, `FALLBACK_CANDIDATE_DRAW`, `DUPLICATE_DETECTED`, `EVALUATOR_ATTEMPT_STARTED`, `GEOMETRY_GATE_RESULT`, `INITIALIZATION_MEMBER_COMMITTED`, `GENERATION_SNAPSHOT_COMMITTED`, and `CELL_TERMINAL_STATUS_COMMITTED` where needed. Event names do not imply separate counter increments; the rules below do.

Definitions are disjoint:

1. **Normal mutation proposal:** one complete L-SHADE or DE trial produced by the already-frozen algorithm, then canonicalized. It creates one `PROPOSAL_ATTEMPT`.
2. **Fallback function invocation:** one entry into `_unseen_proposal()`, counted once by `FALLBACK_INVOKED`; this is not a proposal count by itself.
3. **Fallback internal RNG candidate draw:** one uniform normalized candidate produced and canonicalized inside `_unseen_proposal()`. Each such candidate creates one `FALLBACK_CANDIDATE_DRAW` and one linked `PROPOSAL_ATTEMPT`, including candidates found to be already seen and the eventual unseen candidate. The same returned candidate is not counted again when `_evaluate` sees it.
4. **Canonicalized proposal:** a single candidate/key reaching the proposal observer. Normal mutation is one; each fallback internal candidate is one. This is the unit of `raw_canonical_proposal_count` and the watchdog.
5. **Evaluator dispatch:** one `EVALUATOR_ATTEMPT_STARTED` entry into the evaluator for a new intent, including the geometry gate. It is not a proposal count and may occur more than once for one logical intent after interruption.
6. **Physics dispatch:** one `PHYSICS_ATTEMPT_STARTED` after geometry accepts the candidate and immediately before network/COM work. Geometry-rejected candidates have no physics dispatch. It is neither a proposal count nor a unique FE count.
7. **Unique FE commit:** one durable terminal result for a new canonical key in the cell. It increments unique FE exactly once; it is not an evaluator invocation count.

For a given offspring step, source inspection confirms exactly six normal proposals at the default retry setting (`max_duplicate_retries=5`). `_attempt > max_duplicate_retries` first reaches the fallback branch once. In mixed continuous/integer space, `_unseen_proposal()` draws at most 256 normalized candidate vectors. If it returns `None`, `_generation()` immediately breaks; if it returns an unseen candidate, the loop ends after that candidate is evaluated. Therefore at most one fallback invocation is reachable per offspring step. This preserves the historical source; do not infer 64 fallback invocations from the syntactic loop bound.

The fallback returns `None` only after the internal candidate sequence fails to find an unseen key (or a finite-space enumerator finds none). Every actual internal random draw counts once even when no proposal is returned to `_evaluate`. A deterministic finite enumerator item is counted as a canonical proposal but not as an RNG draw. Q0 pilot uses the mixed-space path. The exact post-initialization proposal partition is `raw_canonical_proposal_count = lshade_normal_proposals + lshade_fallback_candidate_draws + controlled_de_trial_proposals`; these terms are mutually exclusive. `fallback_candidate_draws ≤ 256 × fallback_invocations`, and `fallback_invocations ≤ completed_or_attempted_lshade_offspring_steps`. `evaluator_dispatch_attempts` is the count of `EVALUATOR_ATTEMPT_STARTED`, `physics_dispatch_attempts` is the count of `PHYSICS_ATTEMPT_STARTED`, and neither is added to proposal count. The watchdog reads only `raw_canonical_proposal_count` since the last committed unique result.

### 4.2 Atomic normal/duplicate candidate handling

`PROPOSAL_ATTEMPT` stores proposal ID, source (`normal_lshade`, `lshade_fallback`, or `controlled_de`), raw genotype, canonical physical vector/key, generation/target/retry/fallback draw index, proposal RNG draw references and pre/post RNG-state hashes. It increments the proposal and watchdog counters once.

If the canonical key is already in this cell's committed cache or current algorithm population/history, the *same database transaction* inserts both `PROPOSAL_ATTEMPT` and `DUPLICATE_DETECTED`, increments duplicate/cache-hit and retry counters, updates the next retry cursor, and leaves FE/cache/history/target-generation advancement unchanged. The event transaction ID is the proposal ID. Thus there is no durable state in which a duplicate is recorded but its retry/watchdog/cursor update is absent or can be applied twice. If a process dies before this transaction commits, recovery replays recorded RNG draws, reclassifies the candidate and commits this group once. If it dies after commit, recovery starts at the next retry without another logical draw.

A new canonical key commits `PROPOSAL_ATTEMPT` as `UNIQUE_PENDING`; it does **not** create an FE or update result cache/history/trace. This is the proposal-before-intent state in case A. An `EVALUATOR_ATTEMPT_STARTED` is operational call telemetry; `PHYSICS_ATTEMPT_STARTED` is recorded only after the existing geometry gate accepts the key and immediately before physics/network work.

### 4.3 65,536 no-progress proposal watchdog

The counter is the number of committed, post-initialization canonical proposals since the last committed unique terminal result. It includes duplicates and each fallback internal candidate, each once. It excludes sampler draws, `FALLBACK_INVOKED` itself, evaluator dispatch/retries, result commits, generation/cursor bookkeeping, and validation. A result commit for a new canonical key (including geometry rejection, modeled physics failure, or an invalid returned record) resets the streak to zero; an interrupted dispatch or a new intent without result does not.

After proposal 65,536 is committed, the wrapper starts no additional canonical proposal or RNG draw. It lets already-entered deterministic control flow finish without another draw (for example, the current 256th fallback candidate returning `None` naturally ends the L-SHADE offspring), then durably commits any resulting completed optimizer-only state and records `BUDGET_STALLED`. If the existing retry loop requires another draw, the wrapper stops before it and records the pending, uncommitted optimizer step and `BUDGET_STALLED`. The wrapper is an external stop rule; it does not introduce fallback, random restart, or an algorithmic early-stop inside the allowed trajectory. It is not elapsed-time censoring or proof of search-space exhaustion.

## 5. Transition table and crash/recovery contract

`cursor` below means the applicable sampler draw cursor, initialization member cursor, optimizer proposal/retry/target cursor, generation cursor, or validation finalist cursor. All specified writes occur in a single SQLite transaction. Recovery starts at the last committed event and consumes committed records; it never guesses from an in-memory object.

| From → to | Trigger / atomic durable events | Atomic state/counter changes and RNG point | Cache/history/trace and cursor | Crash immediately before / after commit | Idempotency key; fatal invalid transition |
|---|---|---|---|---|---|
| No pair → pre-sampling | Validate common frozen inputs; commit `PAIR_IDENTITY_COMMITTED`, then both immutable `CELL_IDENTITY_COMMITTED` arm records before the first sampler draw. | Pair Phase-I identity owns topology/root seed/common sampler/model/design-space inputs; each cell identity binds the pair ID to one optimizer and its exact settings. No population hash or mutable journal head enters either identity. | Empty sampler, both optimizer/cache/history/trace cursors. | Before: no pair/cells exist and no draw/evaluation is allowed. After: resume only from the pair identity and both cell identities. | `pair_identity_id=SHA256(canonical pair identity)` and `cell_identity_id=SHA256(pair_identity_id || canonical arm identity)`; missing field or conflict stops before any draw. |
| Pre-sampling → sampler draw committed | One physical vector draw; `SAMPLER_DRAW` group includes RNG before/after and canonicalized result/classification. | Sampler RNG advances exactly once logically; draw ordinal and one mutually exclusive accepted/duplicate/geometry-reject count update. No optimizer RNG, FE or optimizer proposal count. | If accepted, ordered pending-population prefix/seen keys update in the same transaction; otherwise no population member. Cursor becomes next sampler draw. | Before: replay from saved pre-draw state and make that draw once. After: use recorded vector/classification and saved post-draw RNG; never redraw/recount it. | `sampler_draw_id=(pair_identity_id,draw_ordinal)`; wrong predecessor RNG hash, invalid classification or draw >10,000 stops. |
| Sampler incomplete → population sealed | Exactly 234 ordered unique geometry-valid canonical members exist; commit `POPULATION_ATTACHMENT_SEALED`. | Store ordered population/schema/hash, final sampler RNG state, draw/rejection counters and seal. No FE or optimizer state changes. | Set immutable Phase-II attachment ID and close sampler cursor. | Before: continue sampler from next durable draw. After: validate the seal and attach the same population; never resample or edit it. | `population_seal_id=SHA256(pair_identity_id || population_hash || counters_hash)`; count/hash/order mismatch stops. |
| Sampler cap → initialization failed | 10,000 draws committed with fewer than 234 accepted; commit terminal initialization status. | Persist exact count and unsealed accepted prefix; no evaluation/FE. | No optimizer cells may evaluate. All planned pair/cell records remain present. | Before: continue only if draws remain; after cap, terminal. | `init_status_id=(phaseI_id,10000)`; no seed substitution or partial population use. |
| Sealed population → arm initialization | Create per-arm state from ordered attachment, then evaluate member `i`. | `EVALUATION_INTENT` before any evaluator/geometry operation; provisional `evaluation_ordinal=FE_committed+1` is reserved but FE counter does not move. Initialization target cursor remains `i`. | No result cache/history/trace until result commit. | Before intent: create it from sealed member `i`, no sampler RNG. After intent: resume this same intent. | `evaluation_id=(cell_id,phase,canonical_key)`; key already terminal is a cache replay, not a new intent. |
| Intent → evaluator/physics attempt | Append `EVALUATOR_ATTEMPT_STARTED` before entering the evaluator. At its existing hard-geometry boundary, append `GEOMETRY_GATE_RESULT`; if geometry is valid, append `PHYSICS_ATTEMPT_STARTED` immediately before the physics/network calculation. A rejected design commits its result without a physics start. | Increment evaluator/physics attempt counts only for their respective durable start events. No unique FE or watchdog reset. External evaluator invocation may be at-least-once. | Intent remains pending; no result/cache/history/trace until terminal result commit. | Before evaluator start: invoke on recovery. After any start without result: mark the attempt uncertain and redrive same key only under §9 determinism; otherwise fail closed. | `attempt_id=(evaluation_id,attempt_index)` and `physics_attempt_id=(evaluation_id,attempt_index,physics_attempt_index)`; dispatch without its durable start event is prohibited. |
| Intent / started → result committed | Evaluator returns typed geometry/physics terminal record, or strict validator identifies returned `INVALID_RECORD`; append `EVALUATION_RESULT_COMMITTED`. | In one DB transaction store exact result/hash, increment unique FE once, assign first-evaluation ordinal, update FE counter and reset watchdog, record outcome partitions and any physics attempts. | Insert canonical cache entry once; update rank/history/top-16 index; append exactly one search trace row (rankable event or invalid status with unchanged best-known rank). For initialization, keep member cursor until member commit. | Before result transaction: intent remains pending; recovery redrives only if allowed, otherwise terminal replay-unknown. After commit: never reevaluate; use stored record. | `result_id=evaluation_id`; conflicting second result/hash for one ID stops. Invalid record is terminal/counted and stops cell; never comparator-rank it. |
| Result committed → initialized member committed | Result is available for initialization member `i`; append `INITIALIZATION_MEMBER_COMMITTED`. | Add exactly one evaluated member to backend initialization state; advance initialization member cursor `i→i+1`; no extra FE/RNG. | Result/cache/history/trace already durable; insert population member by `(arm_id,i)` exactly once. | Before: hydrate result and add member without evaluator; after: continue at next member. | `init_member_id=(arm_id,population_seal_id,i)`; duplicate member slot or key mismatch stops. |
| Duplicate proposal → next retry | Candidate canonical key is already known; atomic `PROPOSAL_ATTEMPT + DUPLICATE_DETECTED + RETRY_CURSOR_ADVANCED`. | Proposal post-draw RNG state was durably set by RNG draw records. Atomically increment raw proposal, duplicate and watchdog counts; increment retry cursor; do not change FE counter. | No evaluator intent, cache/history/trace or target/generation advance. | Before group: replay committed RNG outputs and commit group once. After: continue next retry with the committed RNG state; do not reapply counts. | `proposal_id`; conflicting proposal/cursor sequence or duplicate with a new-key intent is corruption. |
| Unique proposal → intent (case A) | A committed new `PROPOSAL_ATTEMPT` has no intent; append `EVALUATION_INTENT`. | No new RNG draw; no FE count. Reserve next FE ordinal without incrementing committed count. | Pending proposal/key is retained; no cache/history/trace. Cursor stays at the same target/member. | Before intent: on recovery synthesize this exact intent from proposal row, not a new proposal. After: resume same intent. | `evaluation_id` linked to `proposal_id`; duplicate intent or identity/key mismatch stops. |
| DE unique result → pending target | Result commits while DE generation snapshot is active. | FE/cache/history/trace are committed; append result into ordered pending-trial slot and advance target cursor only after unique terminal result. Duplicate retries do not advance it. | Generation snapshot remains immutable; no survivor replacement until full generation or the exact terminal partial-generation boundary. | Before target slot commit: result and slot/cursor are in the same DB transaction, so recovery either sees both or neither. After: continue next target. | `de_target_result_id=(generation_id,target_index,evaluation_id)`; missing/multiple target result or cursor gap stops. |
| Completed optimizer transition → step committed | Existing algorithm step ends, including FE=0 L-SHADE step, or DE full/partial generation reaches its defined commit boundary; append `OPTIMIZER_STEP_COMMITTED` with complete state. | Atomically store population/genotypes, archive, memories, success batch, history index, generation/target cursors, retry/fallback counters, optimizer RNG post-state, shrink state and full current trace state. FE delta may be zero. | Add population/archive/trace history exactly once; no new result/cache/FE. Clear pending step/generation only in this commit. | Before: restore step's pre-state and replay recorded RNG/proposals/results; no underlying random draw or evaluator call for already committed records. After: restore committed post-state and never apply step again. | `optimizer_step_id=(cell_id,optimizer_step_sequence,generation_before,target_or_boundary)`; duplicate with same post-state is no-op; conflicting payload or a next proposal before commit stops. |
| Any committed state → checkpoint snapshot | At FE lattice, safe interruption boundary, or declared snapshot point; append `CHECKPOINT_SNAPSHOT` and snapshot blob atomically in journal DB. | Snapshot references a committed state and current RNG; no FE, proposal, cursor or optimizer transition change. Increment checkpoint sequence only. | Snapshot includes journal sequence/head hash and state digest. | Before: latest prior snapshot plus journal replay. After: snapshot is usable only at its exact hash-linked sequence; journal remains source of truth. | `checkpoint_id=(cell_id,checkpoint_sequence)`; snapshot not anchored to a journal prefix, or impossible sequence, stops. |
| Validation intent → validation result | Each selected finalist has a validation intent; call validation evaluator; commit `VALIDATION_RESULT_COMMITTED`. | Validation-attempt counts/time update; never search FE or search RNG. | Commit validation cache/result/rank and advance finalist cursor atomically. | Before: retry same finalist under same validation identity. After: load committed record and continue; do not call again. | `validation_id=(cell_id,validation_grid_hash,source_search_ordinal)`; conflicting result/key stops. |
| Any active state → terminal status | Budget, watchdog, initialization failure, invalid record, interruption, or completed validation condition. | Commit exact status, cutoff reason, last event/cursor and pending IDs; do not synthesize missing FEs or state transitions. | Preserve all committed history and all 12 manifest rows; pending records remain explicitly pending. | Before: resume according to pending transition only if status is recoverable. After: terminal statuses do not auto-launch a new run. | `terminal_status_id=(cell_id,terminal_transition_sequence)`; second incompatible terminal status or resumption without explicit recovery policy stops. |

### 5.1 Four mandatory crash windows

**Case A — unique proposal durable, intent absent.** This is a legal state. Recovery selects the sole `UNIQUE_PENDING` proposal, creates its `EVALUATION_INTENT` with the original proposal/key/cursor and reserved next FE ordinal, and dispatches only after that commit. It does not call the proposal generator or consume RNG. A second pending unique proposal is invalid.

**Case B — duplicate visible, cursor not advanced.** This state is impossible in a valid v1 journal: proposal, duplicate event, retry count, watchdog count, RNG reference and retry-cursor advancement commit together under `proposal_id`. A crash before the SQLite commit leaves none of this group; a crash after it leaves all of it. A journal containing only part of the group is corrupt and fails closed; recovery must not heuristically increment counters.

**Case C — evaluator called, result not committed.** `PHYSICS_ATTEMPT_STARTED` may have happened and the physical COM/network function may have completed. This is an unresolved at-least-once external invocation, not an FE. Under the deterministic-evaluator precondition in §9, recovery invokes the same canonical input/evaluator identity again and commits one result/cache/history/trace/FE. Record every actual invocation attempt. Never claim external exactly-once. Durable unique FE accounting is exactly-once; result/cache commit is once per canonical key/phase identity.

**Case D — result committed, optimizer update absent.** The result, unique FE, cache/history/trace and pending trial/result are durable. Resume from the prior optimizer state, use the committed result as the exact logical response to the interrupted proposal, and complete the survivor/adaptation/cursor/state transition once. Do not call the evaluator. The RNG facade replays recorded random outputs and restores their post-state without consuming new draws. The optimizer-step idempotency key prevents duplicate generation increment, memory flush, archive trim, shrink, population/history trace, or survivor application.

## 6. L-SHADE optimizer-only transition and trajectory preservation

The journal's optimizer-step unit is one complete call to the existing `LShadeBackend._generation(target_budget)`. Its pre-state records every mutable field that can affect that call: population and latent genotypes, keys/results, archive, `m_f`, `m_cr`, memory `history_index`, pending successful F/CR/weights, `_memory_batch_proposals`, generation count, duplicate/fallback counters, duplicate streak/watchdog count, population schedule/horizon, boundary counters, cache/index state, incumbent/history/trace state and PCG64 state.

At `_generation` exit, persist the entire post-state in one `OPTIMIZER_STEP_COMMITTED`, regardless of whether unique FE changed. For `FE_delta=0`, the commit still includes, exactly as the source produced:

- generation and next target traversal;
- memory-batch proposal counter, any success-memory flush and history-ring advance;
- archive insert/trim and its random removal if invoked;
- schedule-based population shrink and survivor order;
- incumbent plus backend best/population/archive traces;
- fallback/duplicate/retry and watchdog state;
- exact post-step PCG64 state.

The external per-FE search trace is updated only by `EVALUATION_RESULT_COMMITTED`; the existing backend improvement-only trace is captured as algorithm state and is not substituted for the complete external FE trace. A no-FE optimizer step cannot append another FE trace row, but its backend population/archive trace changes are part of the optimizer commit.

On crash before the step commit, restore the exact pre-step snapshot and replay the existing RNG event tape. The facade returns stored random outputs and moves state to each recorded post-draw state without drawing again. Existing committed result records are replayed as logical first-evaluation responses; an old cache hit is replayed as a cache hit. Continue until the existing `_generation` control path reaches the same end state, verify its after-state digest, then commit once. On crash after the step commit, load its after-state and proceed to the next step. Do not run a second memory flush, generation increment, archive trim, population shrink, fallback, or trace append.

This preserves the existing L-SHADE trajectory because it changes only external event observation/replay: the same source methods, input vectors, branch outcomes, arithmetic, underlying RNG method/argument order and result records are supplied. No random calls are added; on replay, the saved RNG outputs are returned and exact bit-generator post-state is installed. Q1 must compare no-crash hooked execution against the uninstrumented frozen source for proposal sequence, final `state_dict` scientific fields, population/archive/memories and output ranks. If that parity cannot be established without changing `_generation` semantics, stop; do not substitute a new optimizer implementation.

Initialization is not treated as an offspring generation. Each initialization result commits first; `INITIALIZATION_MEMBER_COMMITTED` then inserts the member and advances the member cursor exactly once. Once all 234 members are committed, an initialization seal records the complete backend initial population/memory state and first population trace. A restart in between restores committed results/members, not a partial re-sampling or duplicate evaluation.

## 7. Three-phase checkpoint identity lifecycle

### Phase I — pre-sampling identities (immutable)

Before the first sampler draw, commit one strict `stage5a2_pair_identity_v1` and two strict `stage5a2_cell_identity_v1` records. The pair identity contains common sampler/evaluation inputs; each cell identity binds the pair to one optimizer package. Neither contains a population hash or mutable journal head.

Pair identity fields include protocol ID/version, Stage 5A-2 role, topology and root seed; exact source commit SHA, clean-tree evidence, computation-source fingerprint, raw config SHA-256 and canonical effective config SHA-256; frozen COM/profile, specification, geometry constraints, bounds, design-space schema/version and identity; sampler algorithm/version, stream role/derivation namespace, PCG64 identifier/schema and initial sampler seed/state identity; evaluator/model and 1,001-point search-grid content hash; 9,113-point validation-grid ID/content hash; comparator/schema/canonicalizer/rounding identities; Python/NumPy/SciPy/platform/BLAS/thread environment and dependency-lock fingerprint; and candidate, journal, key/rank, state-codec and outer-envelope schema versions.

Each cell identity additionally requires optimizer ID/version, exact resolved complete settings, terminal 4,096-FE budget (L-SHADE horizon included), and the pair identity ID. Both cell records must exist before sampling starts. The sampler identity is pair-scoped, so the same stream and resulting ordered population is shared across the two optimizer arms. Every listed field is required and type/range-validated. `null`, empty, missing, or defaulted identity fields are rejected. Pair identity commits the intended sampler stream and generator type, not its future/current RNG state. Neither identity can include generated members, sampler final RNG state, journal sequence/head, active cursor or checkpoint sequence.

### Phase II — frozen population attachment (write once)

After all 234 ordered, unique, geometry-valid canonical physical members are complete, atomically commit the pair-scoped `POPULATION_ATTACHMENT_SEALED` containing:

- ordered population schema/version (`stage5a2_initial_population_v1`), exact 234×13 physical canonical vectors and ordered canonical keys;
- dimension, member count, design-space identity, lossless binary64 representation and SHA-256 population hash;
- sampler final PCG64 state in §8 codec, draw count, duplicate/geometry rejection partition and accepted count;
- complete-population seal and `population_attachment_id=SHA256(pair_identity_id || population_hash || sampler_counters_hash)`.

Both optimizer cell identities then attach this same immutable Phase-II ID/hash. Each cell journal records an idempotent `POPULATION_ATTACHMENT_ATTACHED` reference; attachment does not fork the population identity by optimizer. The pair sampler journal owns the single sampler stream and seal; per-cell execution journals own independent arm evaluations/caches/results. No optimizer evaluation starts before the seal. Once sealed, this attachment is immutable for both methods in the matched pair; a later update, changed order, replacement member or changed hash invalidates the run. If 10,000 draws end before 234 acceptances, persist the exact unsealed prefix and `INITIALIZATION_FAILED`; do not evaluate it, substitute a seed, or resample.

### Phase III — mutable execution state

Journal sequence/head, checkpoint sequence, active optimizer/RNG state, pending transaction, counters, caches/results, trace/history, validation cursor, recovery attempts and timing are mutable state. They are not scientific identity. Every mutable state snapshot binds the pair Phase-I ID, arm cell Phase-I ID and (after attachment) shared Phase-II attachment ID, state codec/version, `journal_sequence`, `journal_head_hash`, and state digest.

### Resume and corruption rules

- **Before population seal:** validate the pair and both cell Phase-I records, replay the pair sampler from the last committed `SAMPLER_DRAW`, restoring lossless post-draw RNG and accepted/seen prefix. No population hash is required before it exists. Resume the next draw without repeating a logical draw or changing the accepted sequence.
- **Immediately after seal:** verify population hash, order, schema, counters, final RNG and seal ID; both cells attach exactly that same population. Never call sampler again.
- **During either optimizer's 234-member initialization:** use the sealed population and that arm's ordered initialization cursor/results; resume at the first member not committed. Search starts only after all arm members and initialization state are sealed.
- **During search:** restore a snapshot anchored to a journal prefix and replay all later complete transactions per §§5–6.
- **Checkpoint versus journal:** journal is authoritative. An older snapshot is usable iff its `(sequence, head_hash)` exactly matches a verified journal prefix; replay the contiguous valid tail. If the snapshot sequence is greater than the journal, sequence hash differs, snapshot is not an ancestor/prefix, or state digest disagrees, stop with `CHECKPOINT_JOURNAL_MISMATCH`; do not choose one side or overwrite. If a snapshot is missing but the complete journal is valid from the committed identity/genesis and contains the needed state transitions, rebuild from it; otherwise fail closed.
- **Journal damage:** a gap, duplicate sequence, broken previous hash, malformed event, bad idempotency reuse or invalid state digest makes the cell `JOURNAL_CORRUPT`; no ranking/continuation from that cell. Keep the damaged journal and all 12 manifest records for audit. Do not repair or truncate it in place.
- **Identity mismatch:** any missing or unequal pair/cell Phase-I field, Phase-II seal/attachment, codec, terminal budget, L-SHADE horizon or environment field rejects resume before state hydration or evaluator call. Both optimizer cells must reference the same pair identity and population attachment. Do not fall back to defaults or the Stage 4C reader.
- **Stage 4C protection:** its existing `LShadeBackend` `state_version=4`, checkpoint session and all Stage 4C files remain untouched. Stage 5A-2 uses an outer versioned envelope and a separate journal/codec. No Stage 4C state is rewritten, migrated, or used as a Stage 5A-2 checkpoint.

## 8. Lossless PCG64 and L-SHADE state codecs

### 8.1 PCG64 state schema

Encode `Generator(PCG64).bit_generator.state` as `stage5a2_pcg64_state_v1` with exact keys:

```json
{
  "schema": "stage5a2_pcg64_state_v1",
  "bit_generator": "PCG64",
  "state_128_be_hex": "32 lowercase hex digits",
  "increment_128_be_hex": "32 lowercase hex digits",
  "has_uint32": 0,
  "cached_uint32_be_hex": "8 lowercase hex digits"
}
```

The state and increment are unsigned 128-bit values encoded as exactly 16 big-endian bytes rendered in network-order hex, with leading zeros retained. They are never JSON numbers, floats, decimal conversions through binary64, or shortened hex. `has_uint32` is an integer restricted to 0 or 1; `cached_uint32_be_hex` represents the entire cached-value field as unsigned 32-bit big-endian hex and is preserved even when the flag is zero. Validate exact key set, schema, lowercase hex length/charset, `0 ≤ state, increment < 2^128`, odd increment as required by PCG64, `0 ≤ cached < 2^32`, and exact bit-generator name. Reject overflow, sign, malformed lengths, extra keys, booleans masquerading as integers, unknown versions, `NaN` and JSON-number encodings.

To restore, instantiate the explicitly identified NumPy `PCG64` in the pinned environment and assign state/inc as Python arbitrary-precision integers plus `has_uint32` and `uinteger` as validated uint32 fields. Q1 verifies both encoded state equality and that subsequent `random`, `integers`, `uniform`, `choice`, and `permutation` outputs (where used) match a same-state uninterrupted generator bit-for-bit. Include exact NumPy version/build in identity; a different environment fails identity before replay.

### 8.2 Stage 5A-2 L-SHADE codec; do not wrap nullified data

The current `LShadeBackend.state_dict()` calls `_jsonable()` for cache/results, RNG, success samples, incumbent and traces; `_jsonable()` maps every non-finite Python/NumPy float to JSON `null`. `load_state_dict()` then interprets `None` in compact-history rank keys as `+Inf`. Consequently the current serialized inner payload cannot distinguish an original null from positive infinity and is **not** lossless enough to wrap.

Stage 5A-2 therefore uses `stage5a2_lshade_state_v1`, built directly from the live backend fields **before** `state_dict()` or `_jsonable()` is called. It stores all state that affects a future transition or report:

- every population member's latent genotype, physical canonical phenotype, exact key and unmodified result;
- archive vectors and order;
- full cache or compact retained results, cache-frequency-version map, compact rank/vector/first-order index, `_history_next_order`, historical finalist keys and finalist count;
- `M_F`, `M_CR`, history size/index, successful F/CR/weights, memory-batch proposal count and current configured batch size;
- retry/duplicate/fallback/watchdog state (including duplicate-by-group and exhaustion flag), generation/target/cursors, boundary counters, population sizes/schedule/shrink state;
- full PCG64 state using §8.1; incumbent/key, first-evaluation ordinals, population/archive/best traces, active frequency grid/version and convergence state;
- FE/proposal/duplicate/cache/dispatch counters, initial/current/minimum population sizes, exact optimizer config and resolved settings, requested/actual/hard budgets, terminal horizon, active/hard bounds, canonical space size, design-space version, source/config fingerprint, compact-cache mode and all required v4 scientific fields.

Each binary64 scalar/vector element is encoded as its exact 8-byte IEEE-754 big-endian word (16 lowercase hex digits); arrays additionally declare shape, dtype, order and schema. Integer counters/ordinals and any arbitrary-precision RNG integers use canonical base-10 or fixed-width hex strings as specified by their field schema, never a float. Mapping order is canonicalized; ordered populations, archive, finalist and trace lists retain their algorithmic order. Signed zero is preserved in internal genotype/state values. Canonical phenotype keys use the R1 `f64be_tuple_v1` policy (finite coordinates, signed zero normalized to +0) because Python tuple key equality treats both zeros equally.

Nullable fields are only the explicit schema-defined absence values (e.g. no incumbent before first evaluation, no optional metric in a typed failure). A numeric `None` is never an infinity. `+Inf` is encoded with a tagged binary64 token and accepted only where the unchanged comparator permits it, including the exact rank components for a typed `PHYSICS_FAILED` record. `NaN` and `-Inf` in records, population, adaptive values, genotype, cache, trace or comparator ranks are invalid and fail closed. The codec can parse their bit patterns for diagnostics but may not load them as scientific state. Finite values preserve all bits. Any historical v4 JSON payload with ambiguous nulls in numeric fields is rejected for Stage 5A-2; no guessed reconstruction.

The decoder validates the outer envelope, strict required-field set, dimensions, schema versions, shapes, status-specific non-finite allowances, and identity before rehydration. It reconstructs a complete clean v4-shaped state mapping only after lossless decoding and then may invoke the existing loader with no compatibility defaults exercised; alternatively an explicit Stage 5A-2 hydrator can assign validated fields. The implementation must not change the v4 schema or historical Stage 4C serializer. Q1 tests encode directly from backend attributes and prove round-trip of allowed infinities, arrays, cache, history, pending samples, rank trace and RNG; wrapping an already `null`-coerced `state_dict()` is an automatic failure.

## 9. Resume equivalence and determinism boundary

### Scientific trajectory equality

For identical Phase-I identity, sealed population attachment, software environment, optimizer state and deterministic evaluator, uninterrupted and resumed execution must match exactly in:

- ordered RNG draw outputs, canonicalized proposal vectors/keys and proposal order;
- unique evaluation result hashes/statuses and FE-indexed result history;
- survivor population/genotypes, DE pending generation or L-SHADE archive and adaptive memories;
- counters that affect stopping/algorithm state, target/retry/generation cursor and terminal cutoff;
- comparator rank tuples and first-evaluation ordinals;
- best-so-far search trace and historical top-16 keys/order;
- terminal validation candidates/results when validation is resumed.

Exact is byte-level for RNG state, keys, arrays and stored result payload under the pinned codec; ranking is exact tuple equality. Timestamps and performance measurements are outside trajectory equality.

### Operational recovery metadata

Actual external evaluator invocation attempts, retries after an uncertain dispatch, process/crash count, downtime, restart/restore/replay time, journal/checkpoint I/O, CPU time and end-to-end duration may differ. These fields are counted/reported but never feed proposals, ranking, watchdog proposal count, identity-derived seeds, cache keys or stopping other than a documented infrastructure interruption.

### Guarantee scope and fail-closed cases

External physics invocation is **at-least-once**, because a crash after computation but before durable result commit cannot reveal whether that external call finished. Unique FE accounting is **exactly-once durably** per cell/canonical-key/evaluation phase; result/cache commit is once per canonical key. This is not exactly-once external computation.

Trajectory equality across this uncertainty is guaranteed only if the evaluator is deterministic for the complete frozen identity/canonical candidate/grid in the pinned environment, including any floating-point/native-library behavior that affects returned record bits. The current task performs no COM measurement or evaluation and does not claim that assumption has been empirically proven here. Q1 qualifies the transaction/replay machinery with a deterministic synthetic evaluator. Before any later authorized COM pilot, the frozen COM/network evaluator must be explicitly classified deterministic under the pinned single-thread environment. If it is stochastic, environment-dependent, or otherwise cannot assure the same terminal record on retry, then a started-but-uncommitted call is `REPLAY_RESULT_UNVERIFIABLE`: preserve raw attempts, do not silently accept a changed result, mark that cell invalid/incomplete, exclude it from paired scientific ranking beyond its last verified prefix, and do not claim trajectory equivalence. A committed result is always replayed from journal without re-evaluation.

## 10. Censored matched-pair reporting contract

### 10.1 Units, status and valid support

There are six planned matched pairs `(topology, root_seed)` and 12 method cells. Every pair/cell remains in the manifest, matrix report and final summary. For cell `c`, define `N_valid(c)` as the largest contiguous FE prefix starting at FE 1 with a committed, integrity-verified, comparator-rankable terminal result and one trace row per FE, up to the earliest unrecovered interruption, invalid result, identity/journal failure, or other terminal cutoff. A committed result whose optimizer update is pending is still a valid evaluated candidate and can contribute its FE rank; it cannot generate another proposal until its optimizer transition commits. A pending intent with no committed result is not an FE and creates no trace point. Invalid/corrupt journal/identity cells have no reportable scientific prefix (`N_valid=0`); retain forensic rows but exclude them from paired ranks.

Population attachment must match exactly (same Phase-II ID/hash) for post-initialization method comparison. The 234 common initialization records are a shared-start baseline, not an optimizer win. They may be compared only when both arms have committed the same ordered initialization prefix; label this `INITIALIZATION_ONLY`. An asymmetric arm initialization failure yields no post-initialization coverage. A shared sampler failure before seal yields `INITIALIZATION_FAILED` for both cells and zero search FE coverage. No seed or population replacement is allowed.

Cell search status is one of `COMPLETED` (4,096 committed FEs and no pending search transaction; dense validation status is reported separately), `BUDGET_STALLED` (65,536 shared watchdog or DE's 4,096 per-target proposal limit before 4,096 FEs), `INITIALIZATION_FAILED` (shared sampler cap or arm initialization cannot produce the required 234-member optimizer state), `INFRASTRUCTURE_INTERRUPTED` (unrecovered process/host/storage interruption), `INVALID_RECORD`, `CHECKPOINT_IDENTITY_MISMATCH`, `CHECKPOINT_JOURNAL_MISMATCH`, `JOURNAL_CORRUPT`, `REPLAY_RESULT_UNVERIFIABLE`, or `SEARCH_SPACE_EXHAUSTED` (only a formal cardinality and all-key terminal-result certificate). If an interrupted cell is later explicitly resumed and completes, final status is `COMPLETED` and its recovery history remains visible. No status is replaced by zero or silently omitted.

A valid but incomplete cell's endpoint is its last committed rankable FE `N_valid`, recorded as a **censored endpoint** with the exact stopping cause; it is never labeled as FE=4,096. If no rankable FE exists, endpoint is `NONE`. Dense-validation endpoint is separately eligible only when the stated finalist set has all corresponding committed validation records; a search-complete but validation-interrupted cell has a usable search endpoint and no validated endpoint.

### 10.2 FE-axis support and coverage

For each pair `p`, let `N_common(p)=min(N_valid(L,p),N_valid(DE,p))` only when both cells pass integrity, have the identical sealed population attachment, and have rank traces through the compared point. Otherwise that pair's eligible support is empty (or, for initialization-only, limited to its common committed initialization prefix as specified above). The observed FE support is every integer FE `1…N_common`; trace events are dense by construction. No value may be synthesized after either cell's last valid event.

At each FE `n`, publish:

- `pair_coverage(n) = number of planned pairs with both valid rankable records at n / 6`;
- exact eligible pair IDs and ineligible pair IDs with reason/status;
- paired wins/losses/ties from the existing `GeometryFirstComparator.compare` on the two best-so-far records at the same `n`;
- counts of each, and their denominator `eligible_pairs(n)`.

No scalar average of tuple components is allowed. At a given FE, comparison coverage can grow only through pairs whose both observed traces reach it; it must not silently change denominator. If a trace has a gap, malformed row, invalid record, uncommitted result or hash discontinuity, the usable prefix ends immediately before that point.

### 10.3 Pair endpoint and aggregate participation

A pair participates in a **4,096 search-FE paired endpoint** only if both method cells have exactly 4,096 durably committed unique search FEs, valid complete search traces, no pending search intent/step/generation, identical population attachment, and no identity/journal/record error. Search endpoint comparison uses their best-so-far search-grid records at FE 4,096. It is distinct from a validated endpoint, which additionally requires both independently completed dense-validation finalist sets.

Incomplete endpoints are always reported side-by-side at their actual `N_valid`; methods stopping at different FE counts are not an endpoint pair and cannot be compared as if budgets matched. They can contribute to FE-axis pairs only through `N_common`. Initialization-only pairs appear at FE 234 (only when both have all 234 initial commits) and never enter post-initialization algorithm comparison or a 4,096 endpoint.

A completed-pair-only table is permitted only with heading `COMPLETED_PAIRS_ONLY (k/6; conditional subset, not the planned-pair result)`, the six-pair denominator and a paired coverage table alongside it. It is not a substitute for the all-pair support summary or a winner claim. Report every stalled/interrupted/invalid/failed pair individually.

### 10.4 Paired outcomes and scientific interpretation

At every common FE and common observed time point, wins/losses/ties are calculated from exact comparator ordering. Additionally report without scalar aggregation:

- feasible/infeasible/unrankable status of each side and pair counts for both feasible, L-SHADE-only feasible, DE-only feasible, neither feasible;
- for rankable physics-evaluated designs, the paired `max_violation`, `sum_violation`, worst/average IL, ripple, return loss/matching and each named stopband metric side-by-side;
- geometry rejection, modeled physics failure, invalid, and retry/fallback status counts separately;
- per-pair endpoint result, support length, cutoff status and dense-validation status.

`UNRESOLVED` is mandatory when any required pair lacks valid support at the requested comparison endpoint, when endpoint records/statuses are malformed or incomparable, when no meaningful common support exists, or when the short-budget trajectories are explicitly immature. With three roots, even a complete matrix yields descriptive paired evidence only; it does not establish statistical general superiority or convergence. A full six-pair complete result may be called `COMPLETE_DESCRIPTIVE_PILOT`, not an optimizer winner. No significance test or rank-tuple average is authorized by this Q0.

A malformed/invalid cell remains visible with the original reason and exact valid-prefix length. Forensic valid-prefix points may be shown separately as diagnostics if journal integrity proves them, but they do not make that cell a completed endpoint. A checkpoint identity/journal/hash-chain failure invalidates the cell's scientific series rather than inviting a guessed prefix repair.

### 10.5 Time-axis and compute-cost contract

Never equate FEs, proposal counts, evaluator calls, active seconds, or wall seconds. Record, with mutually exclusive durations:

- active worker computation time (all active process time, including recovery/replay);
- evaluator time (including repeated external attempts);
- proposal/retry/fallback generation and selection time;
- journal and checkpoint I/O/serialization time;
- infrastructure recovery/restore/replay time as a separately reported subcomponent of active worker time;
- stopped downtime and end-to-end wall time (first sampler start through terminal search/validation stop, including downtime).

The active-time component buckets reconcile to active worker time; recovery time is not added a second time. End-to-end wall time equals observed active intervals plus measured downtime within timer resolution. Instrumentation/journal overhead is part of the evaluated implementation package, not hidden overhead. Count `FALLBACK_INVOKED` and internal draws but do not treat them as evaluator time; retries of a physical call contribute evaluator time and operational attempt count, not new FEs/proposals.

For time-axis paired curves, compare only at common observed time support where both cells have valid journaled observations and known status. A stepwise last-committed best-so-far value may be shown only between observed commits while the cell's timeline is actually observed; stop the paired curve at the earlier observation/censor boundary. Do not extrapolate after a cell's last observation, across unrecorded gaps, or use a stalled FE endpoint as if it reached 4,096. Publish active-time and end-to-end wall-time curves separately, with evaluator/proposal/journal/recovery breakdowns.

## 11. Paper-only examples (no computation)

These are arithmetic/specification examples, not synthetic evaluations or test execution. In each, the denominator is six planned topology/seed pairs; the individual example is one pair.

| Case | L-SHADE cell | Controlled DE cell | Pair support and coverage | Endpoint/aggregate consequence |
|---|---|---|---|---|
| 1. Both complete | `COMPLETED`, `N_valid=4096` | `COMPLETED`, `N_valid=4096` | `N_common=4096`; this pair contributes at every FE 1–4096; per-point coverage contribution `1/6`. | Eligible for paired search endpoint at 4096. Validated endpoint only if both validation sets complete. Still descriptive; not general superiority. |
| 2. L-SHADE stalls at 2000 | `BUDGET_STALLED`, `N_valid=2000` | `COMPLETED`, `N_valid=4096` | `N_common=2000`; pair contributes through 2000 only; none at 2001–4096. | Record both actual endpoints. No 4096 paired endpoint; never forward-fill L-SHADE's FE-2000 rank. |
| 3. DE stalls at 1500 | `COMPLETED`, `N_valid=4096` | `BUDGET_STALLED`, `N_valid=1500` | `N_common=1500`; pair contributes through 1500 only. | Record DE per-target/watchdog reason; no 4096 paired endpoint and no fill to 4096. |
| 4. One arm fails initialization | Shared population is sealed; L-SHADE deterministically fails before its first member/FE and is `INITIALIZATION_FAILED`, `N_valid=0`. DE completes. | `COMPLETED`, `N_valid=4096` | No optimizer paired support (`N_common=0`); if both have a valid identical committed initialization prefix, that prefix may appear only as `INITIALIZATION_ONLY`, not as algorithm comparison. | Pair remains in all manifests; no 4096 endpoint; report exact arm failure. A shared sampler cap failure would mark both cells initialization-failed with zero FEs. |
| 5. Infrastructure interruption | `INFRASTRUCTURE_INTERRUPTED` at FE 2,500; an intent after FE 2,500 has no committed result. | `COMPLETED`, `N_valid=4096` | `N_common=2500`; pair contributes only through 2500. If result had committed before interruption, that committed FE is included even if optimizer update remains pending. | Uncommitted result is not FE. Retain external-attempt count and interruption; no 4096 endpoint. |
| 6. Different incomplete endpoints | `BUDGET_STALLED`, `N_valid=2500` | `INFRASTRUCTURE_INTERRUPTED`, `N_valid=3200` | `N_common=2500`; pair contributes through 2500. | Report endpoints 2500 and 3200 independently with causes; they are not a same-budget endpoint pair. |
| 7. Initial 234 only | Both have sealed same population and exactly 234 committed initialization FEs; then both are stopped before any optimizer proposal. | Same. | Coverage exists at the shared initialization prefix through 234; no post-initialization support. | Show `INITIALIZATION_ONLY`; no method win/loss claim, no incomplete cell dropped, no 4096 endpoint. |

For any malformed result or broken journal, the affected cell is listed as invalid with reason and `N_valid`; it contributes no point at or after the first invalid boundary (and no scientific points at all if identity/hash-chain integrity is lost). The other five pairs remain listed. Coverage denominators never shrink by hiding that pair.

## 12. Preserved Q0-R1 algorithm/recovery details

The DE operator, fixed parameters, donor order, target traversal, reflection, canonical remapping, synchronous survivor rule, partial final generation, 4,096 per-target retry ceiling, 65,536 global watchdog, sampler law/seed derivation/population hash, record schema, comparator order, serial order and resource contract remain as Q0-R1. Q0-R2 adds no DE algorithm variant or budget extension.

L-SHADE remains exactly the Stage 4C source algorithm/configuration as resolved in Q0-R1: initial population 234, minimum population 4, history size 6, initial memories 0.5, p-best 0.20, effective archive cap equal to current population (source `archive_rate` field is not used by trimming), memory batch 234 offspring steps, 5 duplicate retries plus first normal attempt (six normal proposals), normalized latent genotype, parent-midpoint repair, per-offspring immediate update, existing `None` fallback exit and 4,096 cold terminal schedule. No change to `lshade.py` search behavior is proposed.

## 13. Read-only source evidence and constraints

Reviewed at Q0-R2 base `1db92ebc581b1e4e419f5122a652cf1e94219de5`:

- `src/sawopt/optimizers/lshade.py`: `_generation` calls `_sample_parameters`, evaluates one offspring, then regardless of acceptance increments `_memory_batch_proposals`, may flush success memories, increments `generations`, invokes `_resize_population` and `_record_trace` when any FE exists. When the attempt index first exceeds `max_duplicate_retries`, it calls `_unseen_proposal`; a `None` return immediately `break`s. `_unseen_proposal` makes up to 256 normalized uniform draws in mixed space. This establishes at most one reachable fallback invocation for an offspring and demonstrates no-FE state changes.
- `src/sawopt/optimizers/lshade.py`: `state_dict()` passes result/RNG/trace fields through `_jsonable`; both NumPy and Python nonfinite floats become `None`. `load_state_dict()` uses compatibility defaults for several identity fields and maps `None` compact rank components to `+Inf`. This motivates the independent lossless Stage 5A-2 codec; the historical codec is not modified.
- `src/sawopt/optimizers/selection.py`: `GeometryFirstComparator` delegates evaluated physics ordering to the existing feasibility-first rank tuple and uses positive infinity for failed-physics rank components. Exact tuple comparisons are retained.
- `src/sawopt/problem/hybrid.py`: canonicalization clips, applies `floor(x+0.5)` at integer coordinates, clips again, and returns the canonical key.
- `src/sawopt/studies/hybrid_stage4b.py::_sample_stage4b_population` and `hybrid_stage4c.py`: existing initializer, Stage 4C configuration, grid/model/serial study references; read only.
- `src/sawopt/optimizers/checkpoint_session.py`: historical Stage 4C checkpoint session and state schema remain untouched.
- `docs/plans/stage5a2_q1_qualification_matrix.md`: official Q1-01…Q1-23 gate list; updated by this review branch only where pass conditions depend on R2.
- PR #47 review: https://github.com/MasayaTakagi/saw-com-optimizer/pull/47#issuecomment-6294426203
- PR #48 review and follow-up: https://github.com/MasayaTakagi/saw-com-optimizer/pull/48#issuecomment-6304039265 and https://github.com/MasayaTakagi/saw-com-optimizer/pull/48#issuecomment-6304081334

## 14. Q1 gate ownership and required qualification evidence

`docs/plans/stage5a2_q1_qualification_matrix.md` is the sole official Q1 ID table. It retains exactly Q1-01 through Q1-23. This packet references those existing IDs only; it does not create or duplicate their assignment. The R2-specific required changes are: direct-field L-SHADE codec; exact PCG64 state schema; Phase-I/II/III lifecycle; journal crash recovery including proposal-before-intent and result-before-update; no-FE L-SHADE optimizer commit; replay event tape without redraw; and paired censoring examples/support/reporting. Q1 remains unstarted and none of these gates has been executed.

Q1 must additionally demonstrate the following, without COM imports/calls, production orchestration, or optimizer execution:

- exact PCG64 next-output parity and all invalid codec rejection cases;
- source-vs-hooked L-SHADE trajectory parity and exact `None` fallback control flow;
- proposal/intent/result/optimizer-commit crash injection at every row in §5, including duplicate atomicity, result replay and a no-FE memory flush/generation/shrink/trace transition;
- every resume phase, missing identity, stale valid snapshot, conflicting snapshot, journal gap/hash error and Stage 4C read-only fixture;
- checkpoint equivalence for ordered proposals, canonical keys, RNG, population/archive/memories, FE/history/ranks/traces/top-16;
- complete six-pair reporting for all seven §11 scenarios, status preservation, exact per-FE coverage and no fill/extrapolation;
- timer/counter reconciliation with instrumentation overhead and operational recovery kept separate from scientific state.

Q1 qualification can demonstrate software behavior, not physical correctness or production readiness. Later COM/optimizer use still requires Q0 acceptance, Q1 completion, independent review and separate explicit user authorization.

## 15. Sol Q0-R2 independent review request

Review only this R2 packet, the preserved Q0-R1 packet/decision, official 23-gate Q1 matrix, and the listed implementation sources. Do not implement, test, calculate COM/network response, optimize, or modify files. Please determine whether every prior `REQUEST_Q0_REVISIONS` blocker is now specifically resolved for Q1 design and whether the proposal is internally consistent.

Please return exactly:

- `SOL_DECISION`: `APPROVE_Q0_PROTOCOL` / `REQUEST_Q0_REVISIONS` / `BLOCK_Q0`
- `CLOSED_FINDINGS`
- `OPEN_FINDINGS`
- `NEW_CRITICAL_FINDINGS`
- `TRANSACTION_REPLAY_ASSESSMENT`
- `IDENTITY_SERIALIZATION_ASSESSMENT`
- `CENSORED_COMPARISON_ASSESSMENT`
- `Q1_QUALIFICATION_REQUIREMENTS`
- `RESIDUAL_RISKS`

Explicitly assess durable transaction transitions, L-SHADE optimizer-only no-FE commit, identity lifecycle, lossless RNG/state serialization, censored matched-pair reporting, and the previously corrected fallback control flow and Q1 gate-ID centralization. State whether Q1 implementation is design-eligible only after independent GitHub review/user acceptance/implementation permission; do not authorize any test or experiment. If revisions are requested, stop after recording that decision; do not start another Sol review.

## 16. Q0/Q1 and work-scope status

- Q0-R2 received one Sol review and a follow-up confirmation of the same `REQUEST_Q0_REVISIONS` decision after documentation refinements. The follow-up was not another independent review. Open findings are in §17; Q0 remains open and is not accepted or closed.
- Q1 is `NOT STARTED / BLOCKED`; no implementation or qualification is authorized by this packet or review.
- No tests, synthetic evaluation, COM/network calculation, optimization experiment, source-code edit, Stage 4C data change, production run, budget extension, merge, or Q0 close is part of this work. The documentation record of Sol's decision does not cure the open design findings and no additional Sol review is initiated.

## 17. Sol Q0-R2 review result and confirmation

**SOL_DECISION:** `REQUEST_Q0_REVISIONS`. Sol performed the requested review against this Q0-R2 packet, the preserved Q0-R1 record, official Q1 matrix and plan. After seeing documentation refinements, Sol re-read the current packet and confirmed the same decision, explicitly noting that this confirmation was not another independent review. Treat this as one Sol review, not two. No additional review will be started automatically.

**Routing verification (local child record, read-only):** requested `openai/gpt-6.1-sol`, `thinking=medium`, `tools=["read"]`, `persistent=false`, label `stage5a2-q0-r2-sol-review`. Saved session `01a15bc6-0387-74bf-b554-20a1aa81d6df` records provider `openai`, model `gpt-6.1-sol`, `thinkingLevel=medium`, API `openai-responses`, and normal completed review. Recorded `medium` is a runtime setting, not proof of internal reasoning effort. The raw session remains local and is not included in Git.

### CLOSED_FINDINGS

Sol accepted these as explicit design specifications (not implementation or Q1 evidence): pair-scoped sampler journal and shared Phase-II attachment; arm-local evaluation journals/caches; evaluator-start versus physics-start distinction and geometry-reject behavior; mutually exclusive proposal/fallback/evaluator/FE counters; external-persistent storage for any later authorized run; L-SHADE optimizer-only no-FE commit; lossless PCG64 and direct-live-field L-SHADE codec; censored matched-pair support/status/endpoint rules and all seven examples; corrected first-`None` fallback control flow; and the standalone Q1 matrix as the unique official Q1-ID assignment.

### OPEN_FINDINGS

1. **Partial identity genesis:** R2 does not define recovery or terminal handling if a crash occurs between committing the pair identity and its two arm identities across separate journals. Sampling must remain prohibited until all exact identities are verified.
2. **RNG-call crash transitions:** `RNG_DRAW_STARTED`/`RNG_DRAW_COMMITTED` lack complete method/argument binding, idempotency, and crash/retry semantics. Reconcile retry-cursor recovery with replaying the pre-step draw tape and reconstructing local F/CR/control state.
3. **Q1 scope contradiction:** §14 prohibits “optimizer execution” while Q1 requires source-versus-hooked L-SHADE trajectory parity and synthetic optimizer transition/replay. Define that COM-free synthetic algorithm qualification is allowed and distinct from prohibited COM/production optimizer studies.

These are unresolved Q0 design decisions; they may not be left to Q1 discretion.

### NEW_CRITICAL_FINDINGS

The initial population attachment seals exact physical binary64 vectors, while existing L-SHADE initialization receives normalized genotypes and reconstructs physical vectors. The design does not prove that the actual evaluated physical vectors/keys after this round trip are bit-identical to the sealed shared population. Specify an exact relation and fail-closed equality condition before either arm's initialization FEs; a shared attachment hash alone does not establish identical evaluated starts.

### TRANSACTION_REPLAY_ASSESSMENT

Proposal-before-intent, atomic duplicate/cursor updates, result-before-optimizer-update and zero-FE L-SHADE commits are substantially specified. However, partial identity genesis and RNG-call crash recovery prevent full replay-design approval. Start events also cannot prove the corresponding evaluator/physics function entered; retain the explicit at-least-once external invocation versus exactly-once durable FE/result distinction.

### IDENTITY_SERIALIZATION_ASSESSMENT

The pair-scoped owner and shared Phase-II ID are appropriate. Phase-I/II/III separation, complete PCG64 state and bypass of nullified historical L-SHADE payloads remain sound. The remaining issues are partial record creation and exact physical-versus-normalized initialization representation, not the stated integer widths.

### CENSORED_COMPARISON_ASSESSMENT

Accepted as specified: fixed six-pair visibility, common verified support, actual incomplete endpoints, initialization-only labeling, separate validated endpoints and no extrapolation/survivor-only conclusion. Sol noted that the disposition-table phrase “six paper-only examples” should say seven; the table has been corrected as a documentary change. §11 and Q1-23 contain the seven required examples.

### Q1_QUALIFICATION_REQUIREMENTS

Retain the single official Q1-01…Q1-23 matrix. Once Q0 is revised/accepted, qualification must cover partial identity creation; RNG-call crash boundaries; exact sealed versus actual evaluated initialization vectors/keys; unchanged hooked L-SHADE behavior and zero-FE transitions; lossless replay; all seven censored cases; and separate operational accounting. Qualification cannot substitute for the missing Q0 decisions.

Q1 implementation is design-eligible only after resolving these findings, independent GitHub review, explicit user acceptance, and explicit implementation permission. This Sol review authorizes no tests, synthetic evaluation, COM/network calculation, optimizer study or production run.

### RESIDUAL_RISKS

Three roots provide weak uncertainty; equal FE budgets do not equalize physics calls, generations, fallback exposure or compute work; journal/recovery overhead affects package cost; evaluator determinism remains an explicit replay precondition; initialization representation, boundary/update differences and top-16 validation limit attribution and global/dense-grid claims.

**Disposition:** Q0 `OPEN / REQUEST_Q0_REVISIONS`; Q1 `NOT STARTED / BLOCKED`. Stop after recording and publishing this review. Do not start an automatic follow-up Sol review.
