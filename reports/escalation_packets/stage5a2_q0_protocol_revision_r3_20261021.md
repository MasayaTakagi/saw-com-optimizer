# Stage 5A-2 Q0-R3 — identity genesis, RNG replay, initialization identity, and Q1 boundary

**Sol re-review:** completed once; `SOL_DECISION: APPROVE_Q0_PROTOCOL`. The judgment closes the four design findings for this review path, but Q0 remains OPEN and is not accepted/closed. Q1 remains NOT STARTED / BLOCKED pending independent GitHub review and explicit user disposition. No implementation or execution is authorized.

**Revision:** Q0-R3, 2026-10-21
**Base:** merged PR #49 / main `25147a6b4912d4a00aa6eb023060d9507dd018f5`
**Prior packet:** [Q0-R2](stage5a2_q0_protocol_revision_r2_20261021.md), preserved unchanged; its single Sol decision was `REQUEST_Q0_REVISIONS`.
**Purpose:** close only R2-SOL-01 through R2-SOL-04. The previously accepted Q0-R2 comparison, budget, algorithm, censoring, reporting, and Stage 4C protection rules remain as specified.
**Review source:** PR #49 independent review comment [#6312601955](https://github.com/MasayaTakagi/saw-com-optimizer/pull/49#issuecomment-6312601955).
**Decision owner:** user. Neither Sol nor GitHub review alone closes Q0, permits Q1, or authorizes a study.

## 1. Scope and retained Q0-R2 decisions

The Q0-R2 comparison contract is retained without changing its scientific conditions: independent `P_D` and `D_P` cells; existing L-SHADE versus a dedicated controlled DE/rand/1/bin complete-package comparison; roots `20261012`, `20261013`, `20261014`; 234 common ordered initialization candidates; 4,096 unique search FEs per arm including initialization; 12 planned cells; existing COM/specification/constraints/bounds/grids/comparator; top-16 history finalists; serial execution; exact censored-pair reporting; and no claim of convergence, impossibility, global optimum, or general algorithm superiority. Preserve the cold 4,096 L-SHADE schedule, all existing L-SHADE search arithmetic/control flow, and Stage 4C records/source behavior. No optimizer, physics, budget, topology, objective, constraint, or experiment condition is changed here.

The four findings are Q0 design decisions, not implementation questions for Q1:

| Finding | R2 cause | Q0-R3 resolution | Status before Sol |
|---|---|---|---|
| R2-SOL-01 | Pair and cell identity writes are in separate SQLite databases; partial genesis was not recoverable and no sampler barrier was defined. | Pair journal coordinates ordered, idempotent pair→L-SHADE cell→DE cell identity commits, deterministic reconciliation of G0–G4, and a durable all-identities-ready barrier. No cross-database atomicity is assumed. | `RESOLVED_WITH_SPEC` |
| R2-SOL-02 | RNG start/commit events lacked full call binding, recovery of an uncommitted output, and a way to reconstruct local L-SHADE variables/cursors. | Versioned exact call identity + lossless typed request/output + PCG64 pre/post state; restart from a durable pre-step optimizer state and replay the unchanged control flow from committed RNG tape and committed evaluator results. | `RESOLVED_WITH_SPEC` |
| R2-SOL-03 | The sealed physical vector can differ bitwise after L-SHADE normalization→physical reconstruction→canonicalization. Hash equality alone did not establish actual evaluation identity. | Seal each candidate as the exact post-L-SHADE-transform canonical physical evaluator input; retain the input genotype and transformation evidence; Controlled DE consumes that exact sealed physical vector for its initialization FE. Run pure pre-FE qualification for all 234 in both arms and fail closed on any vector/key/order mismatch. | `RESOLVED_WITH_JUSTIFIED_ALTERNATIVE` |
| R2-SOL-04 | Q0-R2 §14 prohibited optimizer execution although Q1-16…Q1-21 require synthetic optimizer transitions/replay. | Explicitly prohibit all implementation/execution during Q0; after Q0 acceptance and separate user permission, permit only deterministic synthetic-only software qualification in Q1. Q1 permission never authorizes COM/production physics or a study. | `RESOLVED_WITH_SPEC` |

The design below elaborates these resolutions. R2's other contracts remain authoritative and are incorporated by reference; where there is any conflict, Q0-R3 supersedes only the four items above and the corresponding Q1 scope language.

## 2. Genesis coordinator and cross-journal identity protocol

### 2.1 Ownership, identity, and idempotency

The pair SQLite journal is the **genesis coordinator**, not a distributed transaction manager. It is the first durable owner of a pair identity and an immutable expected-arm roster. Each cell remains a separate SQLite journal. No claim is made that commits across the three databases are atomic.

Use new strict schemas `stage5a2_pair_identity_v2`, `stage5a2_genesis_roster_v1`, and `stage5a2_cell_identity_v2`, plus the existing hash-linked journal envelope versioned for this protocol. An identity is canonical typed bytes under its declared schema, including exact binary64 tokens and the schema version; its identity is `SHA256(domain_tag || canonical_identity_bytes)`. It is immutable. It binds the exact source/config/evaluator/grid/environment/algorithm identities already required by Q0-R2; every field is mandatory and missing/defaulted values are fatal. The pair identity includes both expected cell roles and their arm-configuration hashes, but not their later journal heads or population attachment. A cell identity binds its role/config hash to the pair identity ID and pair-journal UUID. No identity hash depends on mutable cursors, timestamps, or journal sequence.

Deterministic idempotency keys are:

- pair: `(pair_journal_uuid, "PAIR_IDENTITY_COMMITTED", pair_identity_id)`;
- roster: `(pair_identity_id, "GENESIS_ROSTER_COMMITTED", roster_hash)`;
- cell: `(cell_journal_uuid, "CELL_IDENTITY_COMMITTED", cell_identity_id)`;
- readiness: `(pair_identity_id, "ALL_IDENTITIES_READY", roster_hash)`.

The pair journal's roster stores both expected cell identities, their role, cell-journal UUID, pair ID, schema/config/environment hashes, and an operational locator for each DB. A cell identity stores the reciprocal pair identity ID/hash, pair-journal UUID, its own identity ID/hash, role and exact arm config hash. Thus references are checked in both directions without circular identity hashes. The roster and cell IDs are derived from the committed pair ID and the declared arm configs. Identical idempotency key plus identical bytes is a no-op/reuse; same key with any changed content is integrity failure.

### 2.2 Creation order and recovery state machine

Creation order is fixed: before G0, inspect all three journal locations; G0 is valid only if the pair DB and both cell DBs are pristine/absent, with no orphan identity or event. An orphan/preexisting cell journal without its pair coordinator is not G0 and fails closed without creating or overwriting anything. Then (1) pair identity and expected roster commit atomically in the pair DB; (2) L-SHADE cell identity commits in its cell DB; (3) Controlled DE cell identity commits in its cell DB; (4) coordinator verifies all records and reciprocal references; (5) `ALL_IDENTITIES_READY` commits in the pair DB. Separate-database writes are individually atomic only. The barrier is a positive durable proof that all three immutable identity records were read back and matched; it is not a distributed atomic commit.

| State | Pair identity | L-SHADE identity | DE identity | Durable condition / allowed action |
|---|---|---|---|---|
| G0 | absent | absent | absent | No journal identity/genesis events exist. Create pair identity + roster. No sampler RNG may be consumed. |
| G1 | committed | absent | absent | Pair identity and exact roster are immutable. Validate them, then create only the missing expected L-SHADE cell identity. No sampler RNG. |
| G2 | committed | committed | absent | Reuse and validate exact L-SHADE identity; create only the missing expected DE identity. No sampler RNG. |
| G3 | committed | committed | committed | Verify all hashes, schemas, configs, environment, and reciprocal refs; then commit readiness barrier. No sampler RNG before barrier. |
| G4 | committed + ready barrier | committed | committed | Before any first sampler operation or any resume draw, revalidate all three exact identity records and refs. If valid, sampler may start/resume. If any are missing/mismatched, fail closed; do not recreate or sample. |

The `GENESIS_INCOMPLETE` audit status applies to G1–G3 (and to any G0 attempt with no complete identity); it is not an optimizer-cell result and carries zero sampler draws, zero FE, and no comparison support. A conflict or unrecoverable journal is `GENESIS_IDENTITY_MISMATCH` / `JOURNAL_CORRUPT`, with original bytes preserved.

### 2.3 Crash reconciliation and no-overwrite rules

On resume before G4, the pair journal is read first. The coordinator recomputes the expected roster and exact cell identity bytes from the immutable pair record. It reuses an existing cell record only if UUID, schema, full identity bytes/hash, pair reference, role, config, and environment all match. It may create a missing expected cell identity only when that destination DB is demonstrably pristine (valid expected schema/header, no identity row, no event/genesis history, and no incompatible journal UUID). It never replaces an identity, truncates a journal, alters a different identity, repairs a hash, or infers a missing value. If there is any unrelated event, wrong schema/UUID, conflicting identity, nonreciprocal reference, inaccessible DB, or unknown partial write, stop and preserve it.

Crash before an individual identity transaction commit leaves that row absent and allows the exact idempotent creation described above. Crash after it commits leaves the row reusable only after full comparison. A G3 crash immediately before the barrier leaves G3; verify and commit the barrier. A crash immediately after barrier commit leaves G4; revalidate the records before any RNG. If an identity that was present at G4 is absent or differs after restart, the durable barrier does **not** authorize sampling: stop, do not recreate it, and retain the failure for audit. Pair/cell identities and existing scientific/journal data are never overwritten.

The barrier transaction itself contains `ready=true`, the pair ID/hash, both exact cell IDs/hashes, reciprocal-reference verification digest, schema versions, all required common/arm configuration and environment hashes, and a genesis-roster hash. The first sampler RNG request must query this committed barrier and revalidate its complete referenced set. Constructing a PCG64 instance or reading/storing its state is not an RNG consumption; no sampler method (`uniform`, etc.) may be called before G4. All pair journals remain auditable even if initialization never begins.

## 3. RNG-call transaction, identity, and replay contract

### 3.1 Logical RNG call identity

Every sampler or optimizer RNG invocation is one versioned logical event under `stage5a2_rng_call_v1`. Its identity envelope contains all of:

- immutable owner identity ID and journal UUID;
- role: `common_sampler`, `lshade`, or `controlled_de`;
- optimizer-step ID (sampler calls instead bind pair draw ID); generation and target IDs where applicable;
- normal retry/attempt cursor, Cauchy retry index, fallback phase and fallback candidate index as applicable;
- monotonically increasing ordinal in that owner's RNG stream;
- exact method name and positional/keyword call boundary;
- typed, shape-preserving, value-preserving method arguments;
- full lossless PCG64 state immediately before the call and its hash;
- returned raw value's type, dtype, shape and exact bits;
- full lossless PCG64 post-call state and its hash;
- call ID/idempotency key and event schema/version.

`call_id = SHA256(domain_tag || owner_id || role || logical_step_or_draw_id || cursor_tuple || ordinal)`. Method/arguments/pre-state are additionally bound into the start request hash. If an existing call ID is presented with a different method, argument encoding, cursor, owner/role, ordinal, or pre-state/hash, fail closed **before** invoking PCG64. An ordinal cannot be skipped, repeated with a different request, or reassigned to a later call. One unresolved call blocks every later call in that stream.

The fixed allowed method set covers all calls in the audited L-SHADE source and the specified controlled DE/sampler: `integers`, `choice`, `random`, `normal`, `standard_cauchy`, `uniform`, and `permutation`. Calls retain their exact existing method/argument order; the journal facade does not normalize method behavior or add draws. Request/output serialization uses a tagged lossless codec: Python scalar type tags; exact integer/bool/string/null tags; binary64 bit tokens; recursive tuple/list distinction; mappings with canonical key order; and NumPy arrays with dtype (including byte order), shape, order, and exact contiguous bytes. Unsupported types or implicit coercions are rejected. The PCG64 codec is Q0-R2 §8.1's exact 128-bit state/increment plus cached uint32 fields; the full pre/post states, not just hashes, are persisted for recovery.

For L-SHADE this binds each separate invocation in the observed order, including `integers` memory/indices/forced-coordinate/archive calls; each individual `standard_cauchy` attempt; `normal`; each `choice`; each `random`; and each internal `uniform` fallback candidate. Controlled DE binds `permutation(eligible)`, `integers`, and `random`; the common physical sampler binds its `uniform(low, high)` call. Shape, arrays, scalars, argument values, cursor, and method are all identity fields. These names describe audited/proposed call sites, not a replacement algorithm.

### 3.2 Two-event atomicity and call lifecycle

Before invoking the method, commit `RNG_DRAW_STARTED` with the complete call ID, request hash, callsite cursor, exact method/typed args, full pre-state/hash, and stream predecessor. No underlying generator call is allowed before this transaction commits. Then invoke exactly the named method once in the current uninterrupted attempt. On successful return, commit `RNG_DRAW_COMMITTED` with the exact typed raw return, output hash, full post-state/hash, and matching start ID/request hash. The returned value becomes available to the caller only after the committed record is durable. Start and result are separate SQLite transactions because the process may crash between them; no cross-transaction atomicity is assumed.

| Durable state / crash point | Recovery behavior |
|---|---|
| Before `RNG_DRAW_STARTED` commit | No call has been permitted. Restore last committed stream state, reconstruct the next request by replaying the pre-step source control flow, verify the next ordinal/cursor, commit `STARTED`, then invoke it. |
| Immediately after `RNG_DRAW_STARTED` commit, before method call | The start is a pending logical call. Verify the same exact request and pre-state, restore that pre-state, invoke the same method/arguments, and commit the result. |
| PCG64 call returned but `RNG_DRAW_COMMITTED` not committed | The process may have executed the pure call but its output is not durable. Recreate PCG64 from the committed pre-state and repeat the exact call/method/arguments under the same call ID; validate deterministic environment and request hash, then commit output/post-state. It is the same logical draw, not a new call ordinal. The underlying library function may physically have been invoked again. |
| `RNG_DRAW_COMMITTED` committed, caller/proposal not yet advanced | Return the stored typed value and install the stored post-state without invoking the underlying method. Re-executed control flow must match the call identity exactly. |
| Proposal/evaluation processing after committed draws | Restart from the durable pre-step state and replay the source method sequence through stored RNG outputs. Reuse committed proposal/duplicate/result/cache events by their idempotency keys. No PCG64 call or evaluator call is repeated if its scientific result is already committed. |

If the runtime cannot restore a verified pre-state, the library/environment hash differs, the recomputed result is structurally or bitwise inconsistent with the declared pinned generator contract, or the source requests a different call at the same ID/cursor, stop as `RNG_REPLAY_MISMATCH`. No later draw is allowed. A started-but-uncommitted call cannot preserve an inaccessible transient return; deterministic regeneration from exact pre-state is the specified recovery. Pure PCG64 calls can be invoked more than once physically across a crash, while one `call_id` and one committed `RNG_DRAW_COMMITTED` define the sole scientific logical draw.

### 3.3 Retry, event replay, and RNG state guarantees

Every committed draw's returned value and post-state are immutable. During replay, the facade checks owner, role, step/cursor, ordinal, method, exact arguments and pre-state against the next tape entry, returns the stored output, and moves the local generator to the recorded post-state. It must never call the underlying method for an already committed draw. The stream event chain and call ID unique constraint prohibit gaps, duplicate commits, forked ordinals, or a cursor advance without its draw. If a pre-call state has advanced past a pending/uncommitted call, restore the stored pre-state; do not attempt to continue from an arbitrary later state.

`DUPLICATE_DETECTED`, raw proposal classification, duplicate/retry counts, no-progress watchdog count, and retry/fallback cursor transition remain one atomic event group as in Q0-R2. On replay a duplicate group is verified/no-op, not counted twice. If a draw committed but proposal creation did not, reconstruct the same proposal. If a proposal committed but evaluation intent did not, create the same intent without RNG. If result committed before optimizer update, replay the source step with the committed evaluation result and no evaluator call. These operations do not create additional logical draws or unique FEs.

## 4. L-SHADE pre-step state and local-state reconstruction

### 4.1 Restart unit

The restart unit is one complete call to the unchanged `LShadeBackend._generation(target_budget)`. Before entering it, persist `OPTIMIZER_STEP_STARTED` with the exact pre-step backend snapshot/hash, optimizer identity, step sequence, generation/target cursor, FE/cache/journal prefix, complete PCG64 pre-state, and first expected RNG-call ordinal. Keep the state codec in Q0-R2 §8.2, built from live backend fields; never wrap the null-coercing historical `state_dict()` payload. No partial `_generation` Python locals are inferred or persisted as a substitute for replay.

On restart before `OPTIMIZER_STEP_COMMITTED`, hydrate the exact pre-step state, then execute the same existing `_generation` source path using the journal RNG facade and transaction-aware evaluator/cache adapter. Already committed RNG outputs are replayed; a pending RNG start is regenerated by §3; committed proposal/duplicate/evaluation records are reused idempotently; committed evaluator results are returned from the journal. The same source branches, comparisons, floating arithmetic and loop exit are rerun. At the end compare the entire resulting scientific state and call/proposal/event sequence to the durable replay digest before committing one `OPTIMIZER_STEP_COMMITTED`. If any call, argument, cursor, proposal key/vector, result identity, or post-state differs, stop. Do not guess or patch local state.

The optimizer-only step commit atomically persists the complete resulting state and step idempotency key, whether FE delta is positive or zero. A crash before it replays the step; a crash after it loads the committed post-state and never replays it. A no-FE path such as `_unseen_proposal() is None` still commits its source-produced memory-batch count, memory update/index, generation count, archive/trim, schedule shrink, counters and backend traces exactly once. No FE trace is invented. Success memory updates that were only local before the optimizer commit are rebuilt from the same committed trial/result sequence.

### 4.2 Rebuilt local variables; fail-closed callsite/cursor verification

The following are intentionally recomputed by replaying the unchanged source from the complete pre-step snapshot and recorded event tape; they are not recovered by partial-value inference:

- memory index, each `F` Cauchy rejection attempt and final `F`, and `CR` normal draw;
- target and p-best pool/selection; `r1`/`r2` donor indices and vectors;
- mutation vector, parent-midpoint boundary repair and repair counters;
- forced coordinate, crossover random vector and mask;
- canonical trial/key and proposal source;
- duplicate retry attempt/count, fallback phase, each internal fallback draw, and first-`None` exit;
- generation/target/call/proposal cursor and pending trial/result;
- successful `(F, CR, weight)` samples and success-memory flush/index transition;
- archive insertion/removal, population shrink and trace/history transition.

Every RNG callsite has a stable cursor path (including Cauchy-loop index, normal-retry index, fallback candidate index and target/generation). Each proposal event stores the exact latent proposal bits, reconstructed/canonical physical vector/key, source, cursor, and ordered references to its RNG call IDs. Replay compares these against the immutable journal before classification. Local trial state remains transient until the source step ends; the durable pre-step state and append-only transaction records make it reproducible without a “partial F/CR” checkpoint.

The same pre-step/replay/commit pattern applies to controlled DE's complete proposal attempt or synchronous generation unit, with its frozen parent snapshot and exact target/retry cursor. It does not alter the R2 algorithm contract. Sampler draws are separately one-call transactions owned by the pair identity and protected by the G4 barrier.

### 4.3 Crash boundaries and exactly-once scientific state

The crash boundaries are fully specified: before call-start → no call made; after call-start → repeat that same pending logical call from pre-state; after PCG64 return before result commit → deterministic regeneration of the same logical draw; after draw commit → replay stored value/post-state and never redraw; after proposal before intent → create that intent from its event, no draw; after evaluator starts but before result commit → at-least-once external call, deterministic result required, exactly one durable result/FE; after duplicate commit → retry cursor is already advanced atomically; before L-SHADE step commit including zero-FE `None` → replay source step and commit once; after step commit → load it and do not flush/shrink/trace twice.

These rules guarantee no missing or duplicate **logical** RNG events, exact method/argument/cursor matching, deterministic retry and proposal sequence, at-most-once durable cache/result/FE/history/trace commits, and once-only FE-free L-SHADE state transitions, conditional on the pinned deterministic generator/evaluator and source identity. Physical evaluator invocation remains at-least-once across an uncertain crash as Q0-R2 states. A non-deterministic or identity-varying physical evaluator prevents a trajectory-equivalence claim; Q1 uses deterministic synthetic evaluators only. Q1 proves the software contract; it does not qualify COM physics.

## 5. Exact common initial population and pre-FE identity contract

### 5.1 Read-only implementation finding and representations

The audited existing path is:

- `LShadeBackend.initialize(population=...)` treats supplied rows as normalized `x` and stores `_make_member(np.clip(row,0,1))`;
- `_make_member` → `_make_member_result` → `_evaluate` → `_canonical` reconstructs `physical = low + clip(x)*(high-low)`, invokes the canonicalizer and passes a copy of the resulting vector to the evaluator;
- `_normalize(physical) = clip((physical-low)/(high-low),0,1)` and `_physical(x) = low + clip(x)*(high-low)` are separate binary64 operations, so `physical → normalized → physical → canonicalized` is not guaranteed bitwise identity;
- `HybridDesignSpace.canonicalize` clips to active bounds, applies `floor(value+0.5)` to integer coordinates and clips again; its key is the resulting Python-float tuple;
- the existing Stage 4B sampler draws physical `uniform(low, high)`, canonicalizes, rejects duplicate keys before geometry screening, and returns normalized vectors to the L-SHADE runner. This R2-R3 work remains read-only; no source path is altered.

Five representations are named and never conflated: (1) raw physical sampler draw/candidate; (2) exact backend input genotype; (3) reconstructed physical vector; (4) actual canonical physical vector/key; (5) exact evaluator input vector/key. A population attachment hash alone is insufficient.

### 5.2 Representation-aware sealed candidate construction

Use the versioned sampler `independent_uniform_rejection_lshade_image_v2`: the same declared physical-bounds uniform source draws and no-fitness-reselection law, but seal each member **after** applying the existing L-SHADE initialization transform:

1. Draw `raw_physical` with the frozen pair sampler stream, exact `uniform(low, high)` call and physical-coordinate order. Apply unchanged `HybridDesignSpace.canonicalize` to produce a provisional canonical source candidate `x0`.
2. Compute the exact L-SHADE backend input genotype `gL = LShadeBackend._normalize(x0)` using the existing bounds and source arithmetic; do not edit or replace this operation.
3. Reconstruct using the exact existing L-SHADE arithmetic `rL = LShadeBackend._physical(gL)`, then call the same existing canonicalizer used by `_canonical`, producing the actual L-SHADE canonical vector `pL` and exact canonical key `kL`.
4. Define the sealed physical member to be `pL`/`kL`—the actual canonical evaluator input L-SHADE will receive—not the provisional `x0`. Preserve `raw_physical`, `x0`, `gL`, `rL`, `pL`, and `kL` as separate lossless fields in a representation record. Geometry screening and duplicate detection for acceptance operate on the final sealed `pL`/`kL`, duplicate before geometry, without consulting fitness. The first occurrence is retained; no objective/fitness-based replacement or seed substitution occurs.
5. Controlled DE's initialization contract is deliberately direct and explicit: its initial evaluation accepts the sealed physical vector `pL` as a physical candidate, applies the same unchanged canonicalizer once, and sends that exact canonical result to its evaluator. It stores the corresponding canonical-phenotype normalized genotype `gDE = LShadeBackend._normalize(pL)` for subsequent DE state. It must not decode a second independently rounded approximation before the initial evaluator call. This is a new controlled-DE initialization interface, not a change to an existing backend.
6. Construct and seal all 234 ordered members before either arm makes any FE. Seal hash covers the ordered exact `pL` IEEE-754 binary64 arrays and exact keys; a second representation hash covers the per-member L-SHADE input genotype/reconstruction and DE input/genotype encodings. Every arm identity references both hashes. Each arm has private cache and independently evaluates all 234 members.

The exact proposal distribution is therefore a deterministic representation-aware pushforward of the existing physical uniform draw through `canonicalize → _normalize → _physical → canonicalize`, with duplicate/geometry acceptance applied to the final evaluator-space vector. The sampler ID/version and transform code fingerprint are part of the pair identity and population attachment. This preserves the physical-uniform source draw, coordinate order, no warm start, no fitness selection, and no adaptive sampler. It can shift a coordinate by one or more ULPs and can change canonical duplicate/geometry classifications at binary64 boundaries relative to sealing the provisional `x0`; that is an explicit, narrow change to the exact realized sampler law required to make the sealed object equal the actual evaluated design. The physical draw distribution and support remain the declared bounds; Q0-R2's proposed population hash is replaced by a hash of the **actual** ordered common evaluator vectors plus the separate representation hash. No Stage 4C data or behavior changes.

### 5.3 Pre-FE pure transformation qualification

Before the first initialization evaluator/geometry/physics call in **either** arm, run the entire 234-member pure transformation preflight for both arms. It performs no COM/network/physics call and no fitness evaluation. At minimum it:

1. loads the sealed members and all hashes/schema versions;
2. reconstructs the L-SHADE genotype from its sealed exact input bits and uses the unchanged `_physical`, `_canonical`, and `HybridDesignSpace.canonicalize` arithmetic to identify the real evaluator call argument;
3. reconstructs the Controlled DE physical initialization input from the sealed representation and uses its declared direct physical initial-evaluation path plus the unchanged canonicalizer to identify its actual evaluator argument;
4. for every member, compares both actual canonical vectors coordinate-by-coordinate as exact IEEE-754 binary64 bytes against the sealed physical vector, and compares the full versioned canonical key bytes against the sealed key;
5. checks all 234 entries in exact order, dimension, bounds, finite values, duplicate/geometry preconditions, both attachment IDs/hashes, and exact evaluator input copy semantics; and
6. emits a pass certificate bound to both cell identities and the immutable population/representation hashes. Only after both complete certificates are durable can either initialization FE begin.

Any mismatch in any coordinate, bit pattern, key, order, schema, hash, or evaluated-input boundary fails both arms before the first FE with `INITIALIZATION_REPRESENTATION_MISMATCH`. No tolerance comparison, implicit evaluator substitution, change to historical L-SHADE arithmetic, or fitness-driven resampling is allowed. The preflight stops; the mismatch and data remain auditable. The check is explicit even though the construction is intended to make it an identity, so implementation drift cannot silently break fairness.

### 5.4 Alternatives considered

- **Keep original physical seal and tolerate ULP differences:** rejected; it cannot prove the actual evaluator inputs match.
- **Change `_normalize`/`_physical`, canonicalization, or Stage 4C behavior:** prohibited; changes historical optimizer/semantics and requires a separate high-risk decision.
- **Pass a sealed physical vector around L-SHADE's normal initialization evaluator path:** rejected; would bypass the audited existing behavior or require an optimizer modification, instead of qualifying its actual input.
- **Redraw members until they happen to round-trip or until any fitness outcome looks acceptable:** rejected; can condition/change the sampler law; fitness-based selection is expressly forbidden. The specified transform is deterministic for every source draw and rejection is only the frozen duplicate/geometry screening on the final actual vector.
- **Redefine the common population from L-SHADE's actual evaluator image and give Controlled DE that exact physical vector:** adopted; preserves the legacy L-SHADE transform and makes common FE identity exact. Cost: the final sealed physical values/key are the transformed values, not provisional pre-transform source candidates; the deterministic ULP/pushforward effect and versioned sampler identity are recorded and hashed.

If any implementation cannot honor the exact direct DE initial evaluator path or any preflight comparison fails, do not let Q1 choose a tolerance or alternative. Stop `BLOCKED_WITH_REASON` and return to Q0 review.

## 6. Q1 synthetic-only software qualification scope

### 6.1 Q0 prohibitions (apply now)

During this Q0-R3 work, prohibited are optimizer/source implementation, unit or synthetic-test execution, synthetic optimizer runs, any COM/network/physics calculation, optimization research experiment, Stage 4C data/config mutation, production orchestration, and production/pilot launch. This packet and Sol review are documentation/design judgment only. No Q1 work is authorized by drafting this protocol or by a Sol response.

### 6.2 Conditional Q1 permissions (future, only after all gates)

Only after Q0 is explicitly accepted/closed by the user, this protocol receives independent GitHub review, and the user grants a separate explicit Q1 implementation/qualification permission, Q1 may implement and run **deterministic synthetic-only software qualification** with no COM/provider, no SAW physics, and no production orchestration. That bounded Q1 scope includes the existing Q1-01…Q1-23 matrix: synthetic optimizer state transitions; COM-free L-SHADE trajectory parity; Controlled DE golden operator fixtures; RNG replay and crash injection; journal/checkpoint replay; no-FE L-SHADE transition; synthetic 12-cell integration; and censored-pair reporting fixtures. The synthetic objective is a software fixture, not a SAW proxy or scientific experiment. Q1-01…Q1-23 are retained unchanged as the sole authoritative IDs; their acceptance remains all mandatory gates passing under a pinned environment.

Q1 permission is not implicit in Q0 acceptance: it requires the separate explicit user gate. Q1 test/run authorization may name only synthetic evaluators and the listed COM-free execution paths. It does not authorize opening/importing/calling a COM or network physics evaluator.

### 6.3 Never authorized by Q1 alone

Even after Q1 implementation permission, Q1 pass or Q1-only approval never authorizes COM/network physics, actual SAW filter optimization, a production benchmark/pilot, any evaluation-budget extension, topology/model/specification/constraint/bounds change, Stage 4C historical raw-data mutation, or production orchestration/run launch. Every such action remains separately gated by explicit experiment design/review and user production authorization. The future 12-cell real comparison is not part of Q1.

## 7. R2 self-audit before Sol review

| ID | Cause | Adopted design / alternatives rejected | Transaction, evaluation-count, reproducibility effect | Q1 gates (existing IDs only) | Residual risk | Status |
|---|---|---|---|---|---|---|
| R2-SOL-01 | Independent pair/cell SQLite commits allowed G1/G2 partial genesis; R2 assumed records existed. | Pair DB is coordinator; exact ordered pair→L-SHADE→DE commits with hashed immutable roster, idempotent cell identities and G0–G4 recovery. Repair only absent expected rows in a pristine DB before barrier; never overwrite. Cross-DB atomicity is not claimed. Mismatch after G4 is terminal. | Each DB transaction is independently atomic. Partial genesis is not a cell/FE/draw; coordinator barriers before sampler. Recovery can only append missing expected identity records and preserves old data. Readiness is durable and verified before every sampler draw; G4 data loss after barrier fails closed. | Q1-05, Q1-15, Q1-16 | SQLite/storage failure can leave an unrecoverable but auditable partial pair; explicit re-run/new identity would require separate user authority. | `RESOLVED_WITH_SPEC` |
| R2-SOL-02 | RNG events were not bound to full method/args/pre-state; source-local L-SHADE variables/cursors were not recoverable from a partial call. | Exact versioned call identity/tape, lossless args/results/states, START-before-call and COMMITTED-after-return. Pending call regenerates from pre-state under same ID; committed draw is returned without calling RNG. Full unchanged `_generation` replays from a durable pre-step state, rebuilding F/CR, donors, masks, repairs, retry/fallback and success batches. Tolerance or inferred partial state rejected. | One committed call ID/ordinal per logical draw; underlying pure function can be repeated only when its result had not committed. Proposal/duplicate/cursor and result/cache/FE events remain idempotent; L-SHADE zero-FE step commits once. Same pinned PCG64 and deterministic evaluator yield same proposal trajectory. | Q1-03, Q1-06, Q1-11, Q1-16, Q1-17, Q1-18 | Native/library nondeterminism, evaluator nondeterminism, code-path bypass or unobservable method calls invalidate replay; identity pinning and synthetic fault injection are mandatory. External physics call remains at-least-once. | `RESOLVED_WITH_SPEC` |
| R2-SOL-03 | Physical seal vs actual L-SHADE evaluation could differ through floating round-trip; population hash alone does not prove actual inputs. | Seal the exact post-L-SHADE-transform canonical vector/key, keep raw/provisional/genotype/reconstruction distinct, and pass that sealed physical vector directly to new DE initialization. Compare all actual evaluator vectors and keys bitwise in order via both pure preflights before either arm starts. No tolerance, L-SHADE arithmetic edit, hidden substitution, or fitness reselection. Rejected keeping pre-transform seal and optimizer modifications. | Common vector/key/hash refer to actual charged initialization candidates; each arm still commits its own 234 FEs/private cache. Deterministic pushforward may change ULP-level realized sampler values/duplicate/geometry screening versus sealing provisional draws, and is hashed/versioned; no fitness information enters. | Q1-04, Q1-05, Q1-07, Q1-14, Q1-15, Q1-17, Q1-18 | Exact equality depends on pinned source and DE direct-initialization contract; any mismatch blocks before all FEs. The tiny representation-aware sampling-law change must remain disclosed and independently reviewed. | `RESOLVED_WITH_JUSTIFIED_ALTERNATIVE` |
| R2-SOL-04 | Q0-R2 prohibited optimizer execution while official Q1 gates require synthetic transitions, replay and integration. | Distinguish Q0's absolute no-execution boundary from future, explicitly authorized, deterministic synthetic-only Q1 software execution. Keep one Q1-01…Q1-23 matrix. Q1 cannot import/call COM or production orchestration. | No current evaluations/tests. Future Q1 synthetic calls do not count as SAW FEs and cannot be reported as production comparison results. Q0 acceptance and separate Q1 user permission precede them; production requires another gate. | Q1-01…Q1-23 (all, no new/duplicate IDs) | Synthetic qualification cannot prove physical determinism or scientific validity; those remain outside Q1. | `RESOLVED_WITH_SPEC` |

### Self-audit decision

All four findings have a specific pre-Q1 protocol decision; none is left to implementation discretion. The only bounded, explicit comparison effect is the representation-aware deterministic initialization pushforward in R2-SOL-03. It is not an optimizer or physics change and must be reviewed as part of this Q0 packet. If the reviewer identifies a missing invariant, classify it `BLOCKED_WITH_REASON`, preserve the finding, and do not issue an approval request as if complete. No prior Sol-closed R2 item is being reopened except where needed to state these four transitions consistently.

## 8. Required qualification mapping (no new gate IDs)

The official Q1 matrix remains the only gate-ID authority. Its synthetic evidence must include:

- pair/cell identity genesis crashes at G0–G4, exact-idempotent creation, conflicting/preexisting/corrupt journal rejection, barrier-before-any-sampler-call and missing identity after G4 (Q1-05, Q1-15, Q1-16);
- all PCG64 method signatures and typed argument/output/state round-trips; start-before-call and every crash edge including call-return-before-commit; proof committed tape results never invoke the generator; exact cursor/method/argument mismatch rejection and proposal/call sequence parity (Q1-03, Q1-14, Q1-16–Q1-18);
- L-SHADE replay from pre-step across F/CR partial calls, donor/crossover, retries, fallback/first-`None`, result-before-update, memory flush, archive, shrink, trace and FE-free optimizer commit; no partial-local guessing (Q1-11, Q1-16, Q1-18);
- representation preflight over exactly 234 sealed members, both paths' actual evaluator input, bitwise binary64/key/order comparison, zero evaluator invocation before both certificates, and fail-closed mismatch (Q1-04, Q1-05, Q1-07, Q1-15, Q1-17, Q1-18);
- a synthetic 12-cell integration proving no COM/provider import/call and no production orchestration (Q1-21);
- keep the journal's committed result store separate from the backend state restored from the pre-step snapshot. When replaying a result that committed after that snapshot, provide it to the backend as the original logical first-evaluation return—not as a pre-populated backend cache hit—so the backend state transition reconstructs once while the durable journal FE/cache/result transaction is not recommitted or recounted (Q1-06, Q1-16, Q1-18).

Q1-01 through Q1-23 continue to cover all previously specified gates; none is deleted, renumbered, duplicated, or treated as passed by this design document.

## 9. Sol Q0-R3 independent review request

**Routing requested:** one `agent_spawn`, `model="openai/gpt-6.1-sol"`, `thinking="medium"`, `tools=["read"]`, `persistent=false`, label `stage5a2-q0-r3-sol-review`. No parallel Sol review. The child has judgment-only read access and is not authorized to implement, modify files, run Git commands, test, execute synthetic evaluations, call COM, or optimize.

Read the following complete files/current source at this branch base: this packet (absolute path `/home/user/src/saw-com-optimizer/reports/escalation_packets/stage5a2_q0_protocol_revision_r3_20261021.md`); Q0-R2 packet and its Sol decision; `docs/plans/stage5a2_q1_qualification_matrix.md`; `docs/plans/stage5a2_minimum_fair_comparison.md`; PR #49 independent review comment above; and read-only sources `src/sawopt/optimizers/lshade.py`, `src/sawopt/optimizers/selection.py`, `src/sawopt/problem/hybrid.py`, `src/sawopt/studies/hybrid_stage4b.py`, and `src/sawopt/optimizers/checkpoint_session.py`. The earlier Q0-R1 and DE review decisions are preserved in the referenced Q0-R2/Q0-R1 packets; do not reopen already accepted non-blockers without a concrete contradiction.

**Prior Q0-R2 Sol judgment:** `REQUEST_Q0_REVISIONS`, Q1 blocked. Closed: pair-scoped sampler/separate arm journals in principle, Q0-R2 censoring, codec direction, no-FE transition design, fallback correction and the sole Q1-ID matrix. Open exactly four findings: (1) partial pair/cell identity genesis; (2) incomplete RNG-call identity/recovery and L-SHADE local-state replay; (3) actual common initialized evaluator vectors/keys not proven bitwise identical; (4) Q1 synthetic optimizer qualification contradicted by an optimizer-execution ban.

**Review request:** independently determine whether these four R2 blockers are resolved without disturbing accepted Q0-R2 terms. Assess (1) whether G0–G4 genesis recovery and the all-identities-ready barrier safely handle separate SQLite commits; (2) whether every logical RNG call and crash edge is bound and replayed without missing/duplicating a logical draw; (3) whether pre-step L-SHADE plus the RNG tape reconstructs local F/CR, retries, fallback, and FE-free transitions exactly; (4) whether the actual 234 canonical evaluator vectors/keys in both arms are bitwise identical before any FE and whether the representation-aware sampling-law adjustment is justified; (5) whether synthetic-only Q1 permissions are distinct from Q0 prohibitions and COM/production study authorization; and (6) whether any Q1 implementation choice remains unresolved.

Return exactly these headings and decisions:

- `SOL_DECISION`: `APPROVE_Q0_PROTOCOL` / `REQUEST_Q0_REVISIONS` / `BLOCK_Q0`
- `CLOSED_FINDINGS`
- `OPEN_FINDINGS`
- `NEW_CRITICAL_FINDINGS`
- `IDENTITY_GENESIS_ASSESSMENT`
- `RNG_REPLAY_ASSESSMENT`
- `INITIAL_POPULATION_IDENTITY_ASSESSMENT`
- `Q1_SCOPE_ASSESSMENT`
- `Q1_QUALIFICATION_REQUIREMENTS`
- `RESIDUAL_RISKS`

This request grants no implementation, file-change, Git/GitHub, test, COM, synthetic-run, optimizer-study, Q0-close, Q1, or production permission. Sol approval is necessary for this requested path but is not Q0 formal acceptance, user acceptance, or implementation authorization.

## 10. Sol outcome and routing record

**One independent read-only review completed:** `SOL_DECISION: APPROVE_Q0_PROTOCOL`; no open or new critical findings. This is design approval only. Q0 is not formally closed, Q1 is not permitted, and no implementation, test, synthetic evaluation, COM calculation, optimization study, or production run is authorized.

**Routing and child-session verification (read-only):** requested `openai/gpt-6.1-sol`, Pi `thinking=medium`, `tools=["read"]`, `persistent=false`, label `stage5a2-q0-r3-sol-review`. The saved session `/home/user/.pi/agent/subagent-sessions/2026-10-21T09-45-11-037Z_01a15dd9-b47c-7349-be7e-e8faa6150e02.jsonl` (session ID `01a15dd9-b47c-7349-be7e-e8faa6150e02`) records actual provider `openai`, API `openai-responses`, model `gpt-6.1-sol`, and `thinkingLevel=medium`. It contains the requested review response and ends with `stopReason="stop"`, `rawStopReason="completed"`; judgment was obtained. The actual child record was inspected locally. Recorded `medium` is a runtime setting, not proof of internal reasoning effort or backend internals. Raw session is local and is not committed.

The root agent also retrieved PR #49 issue comment #6312601955 read-only before review. The child had no GitHub tool and notes that it assessed the supplied review record through the packets; its limitation does not invalidate the independent design judgment.

### Sol response (verbatim)

## SOL_DECISION

`APPROVE_Q0_PROTOCOL`

Approval is for the proposed design, including its explicitly disclosed initialization pushforward—not an assertion that every realized sampling detail remains unchanged from R2. It does not close Q0, grant Q1 permission, or authorize execution.

## CLOSED_FINDINGS

- **R2-SOL-01:** Ordered, pair-coordinated genesis, immutable expected identities, reciprocal verification and the durable readiness barrier resolve partial cross-database identity creation without assuming distributed atomicity.
- **R2-SOL-02:** The complete RNG request/result contract and source replay from a durable pre-step state resolve the previously unspecified logical-draw recovery and L-SHADE local-state reconstruction.
- **R2-SOL-03:** Sealing L-SHADE’s actual canonical evaluator image, using direct physical DE initialization, and requiring both complete pre-FE certificates establish an explicit exact-input contract.
- **R2-SOL-04:** Current Q0 prohibitions are now distinct from future, separately authorized synthetic-only Q1 execution.

Previously accepted censoring, budgets, ranking, fallback semantics, separate arm caches and journals, lossless-codec direction, and official Q1 IDs remain intact.

## OPEN_FINDINGS

None requiring another Q0 design decision within the bounded scope.

The R3 blanket statements that no experiment condition changes must be read subject to §5’s explicit exception: the final initializer distribution and boundary classifications can change. The packet discloses and fixes that exception sufficiently; it must not disappear from subsequent review evidence.

## NEW_CRITICAL_FINDINGS

None identified.

No approval of implementation correctness, physical determinism, or production readiness follows from this design judgment.

## IDENTITY_GENESIS_ASSESSMENT

G0–G4 is safe as a **fail-closed recovery protocol**, not an availability guarantee:

- Pair identity and roster commit together before either cell identity.
- Missing expected cell records may be appended only before readiness and only into demonstrably pristine compatible destinations.
- Existing records require exact byte/hash/configuration/UUID/reference agreement.
- Orphans, incompatible contents and inaccessible or corrupt journals stop recovery without replacement.
- After G4, disappearance or mismatch is terminal rather than permission to recreate identities.

The roster supplies the expected cross-database identities without circular hashes. The barrier records their verified relationship; revalidation prevents a stale barrier from legitimizing later data loss.

No sampler method invocation is permitted before the barrier. Constructing or restoring PCG64 state is not a draw. Q1 must establish that every sampler entry path enforces this restriction.

## RNG_REPLAY_ASSESSMENT

The contract binds the required owner, role, step, cursor, ordinal, method, typed arguments, complete pre-state, exact return representation, post-state, schema and idempotency information. Changing a request under an existing call identity is an integrity failure.

Crash handling correctly distinguishes:

- no committed start: no permitted physical call;
- committed start without result: regenerate the pending call from its exact pre-state;
- committed result: replay stored output and post-state without invoking the generator;
- subsequent proposal/result processing: reuse committed records idempotently.

Repeated physical invocation after an uncertain crash is compatible with **one committed logical draw**. It is not exactly-once physical execution.

The actual L-SHADE source supports the proposed replay unit. Re-executing `_generation` from its full pre-state can reconstruct parameter rejection loops, donor selection, mutation, repair, crossover, duplicate retries, internal fallback candidates, success samples and terminal bookkeeping. Preserving the sampled F/CR association across fallback is particularly important.

This requires a strict separation between the **reconstructed backend’s historical cache/FE state** and the journal’s already committed result store. A previously committed first evaluation must replay as its original logical first evaluation, not become a backend cache hit merely because the durable journal now contains it. R2 §6 and R3’s unchanged-control-flow requirements specify that behavior.

Result/cache/FE transactions and optimizer-step transactions remain distinct but consistent. Zero-FE transitions still commit once; a committed step must never be replayed.

## INITIAL_POPULATION_IDENTITY_ASSESSMENT

The adopted construction resolves the floating-point round-trip problem without changing historical L-SHADE arithmetic:

- Retain L-SHADE’s exact input genotype.
- Seal its reconstructed, canonical physical evaluator argument and key.
- Give DE that physical vector directly for its initial evaluation.
- Store DE’s normalized phenotype representation separately for subsequent search.

Repeated canonicalization is consistent with the inspected clipping/half-up canonicalizer. Nonetheless, construction alone is not qualification evidence.

The guarantee is appropriately **fail-closed**: either all 234 actual evaluator arguments and keys match bitwise, in order, with both certificates durable before either initialization FE, or neither arm proceeds. It does not guarantee that arbitrary implementation drift will pass.

The sampler-law effect is real but justified and fully selected at Q0: deterministic representation pushforward, with duplicate/geometry acceptance on the final evaluator-space vectors. No tolerance, alternative remapping, redraw-until-round-trip strategy or fitness-based repair remains for Q1 to choose.

## Q1_SCOPE_ASSESSMENT

The scope contradiction is resolved.

Q0 currently permits design judgment only. Future Q1 requires accepted Q0, independent GitHub review and separate explicit user permission. Its optimizer execution is restricted to deterministic synthetic software fixtures.

COM/provider/network-physics imports or calls, actual SAW optimization, production orchestration, production studies and protected Stage 4C mutations remain prohibited. Synthetic qualification cannot authorize a later physical study.

## Q1_QUALIFICATION_REQUIREMENTS

Retain all mandatory **Q1-01…Q1-23**, especially:

- **Q1-05/15/16:** Every genesis crash edge, pristine-destination checks, conflicts, post-barrier data loss and zero pre-barrier sampler calls.
- **Q1-03/14/16–18:** Every allowed RNG signature, lossless scalar/array/state encoding, pending-call regeneration, committed-call no-redraw proof and mismatch rejection.
- **Q1-11/16/18:** Uninstrumented-versus-hooked parity; replay across parameter sampling, fallback, result-before-update, memory flush, archive removal, shrink and zero-FE transitions.
- **Q1-04/05/15/17/18:** Both complete 234-member actual-input preflights, exact keys/order/copy semantics and zero initialization evaluator calls before both certificates.
- **Q1-07/19/23:** Exactly-once durable accounting, original logical cache behavior, trace integrity and all retained censored-reporting cases.
- **Q1-21:** Synthetic integration with no prohibited physics imports/calls or production orchestration.

A failed invariant returns to review; Q1 may not select new scientific semantics.

## RESIDUAL_RISKS

- Storage loss can make a partial pair unrecoverable; preservation and fail-closed handling are appropriate.
- Exact replay remains conditional on pinned source, environment, numerical behavior and deterministic evaluators.
- Start telemetry proves durable dispatch intent, not that the underlying function entered.
- Synthetic qualification does not establish physical evaluator determinism.
- Equal unique FE budgets do not equalize proposals, physical attempts, generations or elapsed cost.
- Three roots and top-16 validation support only bounded descriptive conclusions.
- The linked GitHub comment was not independently retrieved under this file-only review; its recorded findings were assessed through the supplied packets.

## 11. Governance, non-execution record, and next gate

- Q0-R3 is design-only. No optimizer code, test/synthetic execution, COM/network/physics calculation, optimization research, production orchestration, or Stage 4C data change is part of this work.
- Q0 remains OPEN until explicit user disposition after Sol and independent GitHub review. Sol `APPROVE_Q0_PROTOCOL` alone does not close Q0.
- Q1 remains NOT STARTED. It requires accepted Q0, independent review, and separate explicit user Q1 implementation/qualification permission.
- Q1 success does not authorize real optimizer/COM experiments, a pilot/benchmark, budget or topology/model/spec changes, or production launch. Those need their own separate user-reviewed experiment authorization.
- Existing R2/R1 packets and review history remain immutable. Do not include raw child sessions, credentials, experiment outputs, or checkpoint data in Git.
