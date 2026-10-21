# Stage 5A-2 Q1 synthetic qualification — execution plan

**Status:** `PLANNED / IMPLEMENTATION NOT STARTED / AWAITING SEPARATE USER AUTHORIZATION`.

**Q0:** `CLOSED / ACCEPTED` under the user decision recorded in the [Q0 closeout](../history/stage5a2_q0_closeout_20261021.md).

**Authority:** [Q0-approved comparison contract](stage5a2_minimum_fair_comparison.md), the sole official [Q1-01…Q1-23 qualification matrix](stage5a2_q1_qualification_matrix.md), and the accepted [Q0-R3 protocol](../../reports/escalation_packets/stage5a2_q0_protocol_revision_r3_20261021.md), together with retained Q0-R2 terms and the [project roadmap](../project_roadmap.md).

**Scope:** plan only. No Q1 source implementation, unit/synthetic test, synthetic integration, COM/network/physics evaluation, optimizer study, Stage 4C mutation, or production run is performed or authorized by this plan.

Q1 is deterministic, COM-free software qualification. Its synthetic objective is a software fixture, not a SAW proxy or a scientific comparison. Q1 must not resolve or change Q0 decisions. Q1 passing does not authorize a real COM comparison, pilot, or production run; each remains a separate user-reviewed authorization.

## 1. Work-unit model and order

Q1-A…Q1-E are **implementation work units**, not qualification gates and not additional IDs. The only formal qualification IDs are Q1-01…Q1-23 in the existing matrix. An official gate has exactly one primary work-unit owner below; related work units may supply interfaces or fault cases but do not duplicate gate ownership.

```text
Q1-A: identity/journal/RNG/population foundation
             ├── Q1-B: controlled DE ──┐
             └── Q1-C: L-SHADE adapter ├── Q1-D: cross-cutting recovery/determinism
                                        └── Q1-E: synthetic integration/reporting
```

Q1-B and Q1-C depend on the stable Q1-A contracts and can be developed as separate reviewed work units. Q1-D requires the integrated A/B/C transitions. Q1-E consumes the qualified interfaces, statuses, traces and comparison rules from A–D. Every boundary change must preserve the Q0 data/identity/event semantics; if a Q0 design decision would need to change, stop and return to governance rather than deciding it in implementation.

## 2. Frozen Q0 contract carried through Q1

- **Common initialization:** exactly 234 ordered candidates from `independent_uniform_rejection_lshade_image_v2`; preserve raw draw, provisional canonical vector, L-SHADE input genotype, its reconstructed physical vector, sealed actual canonical physical evaluator vector/key, and DE's direct physical input/genotype separately. Seal all members before either arm's first FE. Both full 234-member pure evaluator-input preflights and durable certificates must match the seal bitwise, by key, and in order before either arm evaluates. Mismatch fails both arms before FEs. No fitness-driven selection, redraw-until-round-trip, tolerance, or seed substitution.
- **RNG/replay:** explicit PCG64; `stage5a2_rng_call_v1`; exact versioned owner/role/step/cursor/ordinal/method/typed arguments, full lossless pre/post state and typed result; durable `STARTED` then `COMMITTED`; a committed output is replayed without redrawing; a pending call is regenerated from its verified pre-state under the same logical ID. L-SHADE restarts its existing control flow from complete pre-step state; no partial-local-state guessing.
- **Evaluation/accounting:** 4,096 unique search FEs per arm/cell including 234 initial FEs. Duplicate/cache hit and sampler rejection add no FE. Search geometry reject, typed modeled failure and invalid returned record retain their specified separate classification and accounting. Validation is separate. No dispatch past 4,096; no comparator change.
- **Scientific boundary:** synthetic-only, deterministic, no COM/provider/network physics and no production orchestration. No Stage 4C data/source/checkpoint mutation. Do not change optimizer search rules, objective/ranking, seeds, bounds, topology, constraints, evaluation budget, failure taxonomy or Q0 censoring/reporting rules.
- **Interpretation:** Q1 proves bounded software behavior only. It does not establish COM determinism, physical correctness, search convergence, feasibility, a best method/topology or permission to perform the 12-cell SAW comparison.

The complete normative contract, including the initializer pushforward effect, G0–G4, schemas, failure states, budgets and comparison rules, remains in the linked Q0 records. This summary does not supersede them.

## 3. Cross-phase interface contract (freeze before implementation)

The following conceptual interfaces are to be agreed at Q1-A review before Q1-B/C code is written. Concrete Python class/function names may be selected during implementation, but data ownership, schema meaning, lifecycle and failure semantics below may not change without reopening Q0.

### 3.1 Identity and attachment lifecycle

1. **Phase I:** pair identity + immutable expected-arm roster, then immutable L-SHADE and controlled-DE cell identities, reconciled by the pair coordinator through G0–G4. G4 is the durable all-identities-ready barrier. There are no sampled population hashes in Phase-I identity bytes. No sampler method may be invoked before G4.
2. **Phase II:** the pair-owned population seal stores the ordered 234 actual evaluator physical vectors/keys and sampler evidence. A distinct representation attachment stores each representation path and hash. Each arm's post-seal `POPULATION_ATTACHMENT_ATTACHED` record/execution envelope references both hashes and its unchanged Phase-I cell identity ID. Never rewrite Phase-I IDs to add sampled data.
3. **Phase III:** mutable journal sequence/head, checkpoints, RNG cursors, results/cache, FE ledger, traces and validation cursors are integrity/recovery state, not scientific identity. Snapshots may be used only against an exact verified journal prefix.

### 3.2 Population boundary

Q1-A supplies an immutable ordered population object with 234 member records, the two seals, and an explicit representation record for raw/provisional/L-SHADE/decode/sealed/DE forms. Q1-C consumes each L-SHADE genotype through the existing `_normalize`/`_physical`/canonicalization behavior; Q1-B receives the sealed physical vector directly on its initial evaluator path and separately records the normalized canonical phenotype genotype used after initialization. Both paths expose a **pure preflight** that computes actual evaluator inputs without calling an evaluator or physics. Their complete certificates are persisted before either initialization FE. The arms have separate caches and independently evaluate all 234 members.

### 3.3 RNG/journal/evaluation boundary

Q1-A provides one lossless typed RNG journal facade. Its call identity is checked before generator invocation; committed results are returned without an underlying draw. Pair-sampler stream and each optimizer-role stream have separate ownership/cursors. An arm adapter can distinguish: RNG event, proposal, duplicate/retry, evaluation intent, external evaluation attempt, durable result/FE/cache commit, backend state update, and optimizer-step commit.

The journal result store is **not** a restored optimizer backend cache. If a result committed after the optimizer's pre-step snapshot, replay supplies it as the original logical first evaluation so the backend reconstruction is correct, while not recommitting or recounting the already durable result/FE/cache row. An optimizer transition, including a zero-FE L-SHADE step, commits exactly once.

### 3.4 No-COM integration seam

All Q1 runners receive an evaluator implementation by dependency injection. The synthetic integration must not import or resolve a COM/provider/network-physics evaluator or production orchestrator. Tests must assert this isolation at import and call boundaries, not infer it merely from using synthetic numeric outputs.

## 4. Proposed module ownership and protected boundaries

The paths below are implementation targets, not files changed by this plan. Keep Stage 5A-2 additions in a study-scoped package (recommended `src/sawopt/studies/stage5a2/`) and a dedicated controlled optimizer backend; do not repurpose Stage 4C production state or broadly modify shared numerical behavior.

| Module/location | Intended responsibility in Q1 | Protected boundary |
|---|---|---|
| New `src/sawopt/studies/stage5a2/identity.py` | Strict typed identity schemas, pair coordinator G0–G4, Phase-II seal/attachment references and resume identity validation. | Phase-I bytes stay immutable; no cross-database atomicity claim. |
| New `.../journal.py` | SQLite transaction/event envelope, hash chain, idempotency, durable counters/result store and checkpoint-to-journal prefix checks. | Preserve Q0 event grouping and exactly-once durable result/FE semantics. |
| New `.../rng.py` | PCG64 codec, `stage5a2_rng_call_v1`, typed call tape, call facade, START/COMMITTED and replay. | No hidden draws, coercions, changed source draw order, or committed-call redraw. |
| New `.../initialization.py` | Representation-aware physical sampler, 234-member seal, lossless representation rows, both pure arm preflights and certificates. | No fitness information or COM call; exact Q0 sampler law and fail-closed equality. |
| New `src/sawopt/optimizers/controlled_de.py` | Dedicated fixed `DE/rand/1/bin` backend and complete generation/target state interface. | No legacy-backend relabeling; no adaptation/archive/shrink/polish/fallback or changed operator semantics. |
| New `src/sawopt/studies/stage5a2/lshade_adapter.py` | Transaction-aware evaluator/RNG seams and full live-state codec/restore adapter around existing L-SHADE. | Retain existing search path and Stage 4C state version; do not use null-coercing payload as lossless source. |
| New `.../recovery.py` / `runner.py` | Synthetic-only coordination of private arm journals, phase transitions, restart, status and fault injection. | No COM/provider import, no production orchestration, no Stage 4C reader/writer. |
| New `.../reporting.py` | Qualified synthetic integration records, resource/time ledger and exact Q0 censored-comparison reporting. | No imputation, survivor-only aggregation or newly invented ranking/reporting rule. |
| Existing `src/sawopt/optimizers/lshade.py` | Minimal observation hooks only where unavoidable to preserve RNG/evaluation/step boundaries. | No arithmetic, branch, method/argument order, retry, fallback, adaptation, cache or survivor behavior change. |
| Existing `src/sawopt/optimizers/selection.py`; `src/sawopt/problem/hybrid.py` | Read-only reuse of `GeometryFirstComparator` and the existing design-space canonicalization contract. | Do not change rank tuples, tie semantics, canonicalizer or rounding. |
| Existing `src/sawopt/studies/hybrid_stage4b.py`; `src/sawopt/optimizers/checkpoint_session.py` | Read-only evidence/reference for existing sampler and checkpoint ownership. | No Stage 4B/4C protocol, saved state, or historical data mutation. New Stage 5A-2 persistence is separate. |
| New focused test files under `tests/optimizers/` and `tests/studies/` | Synthetic, deterministic unit/fault/replay/integration fixtures per official gates. | Test fixtures cannot import/call COM or launch production orchestration. |

If implementation discovery shows a proposed seam cannot meet exact replay without changing an accepted Q0 rule, do not silently refactor or approximate: stop with the concrete evidence and request a governance decision.

## 5. Work-unit execution cards

### Q1-A — Common Identity / RNG / Population Infrastructure

**Purpose.** Build the pair/cell identity coordinator, append-only SQLite journal primitives, lossless typed PCG64 call service, one shared 234-member representation-aware population and pure pre-FE arm identity checks. This unit establishes stable interfaces before either optimizer integration.

**Q0 contract linkage.** Q0-R3 §§2–5; Q0-R2 identity/journal/codec requirements; all initial-population, PCG64, Phase-I/II/III and exact-input requirements in §2 above. The explicit initialization pushforward and immutable Phase-I/Phase-II separation are retained without alternative selection.

**Modules/responsibilities.** New `identity.py`, `journal.py`, `rng.py`, `initialization.py`; read-only use of `HybridDesignSpace.canonicalize` in `src/sawopt/problem/hybrid.py`; no change to COM, evaluator or Stage 4B runner. Provide typed pair/cell identities, G0–G4 coordinator, `PopulationMember`/seal/representation records, pair and arm journal APIs, typed PCG64 state/call DTOs, and preflight certificates.

**Inputs, outputs, state, persistence.** Inputs are frozen source/config/design-space/environment identities, 13 active physical bounds and integer-coordinate metadata, fixed pair/root-seed/role, and injected pure geometry predicate. Outputs: exact pair/cell identities; lossless sampler journal and counters; one ordered seal with 234 actual evaluator vectors/keys plus representation hash; each cell's Phase-II attachment reference; two complete preflight certificates. Pair-owned sampler state and per-cell attachment records persist in their SQLite stores. No fitness/result field participates in sampling.

**Dependencies.** None within Q1; Q0 closure is complete. Q1 source work still waits for separate user authorization. Q1-B/C cannot begin their integration against moving data/journal/RNG interfaces.

**Required tests / abnormal cases.** Golden seed derivation and PCG64 state/call codec; every allowed method, scalar/array dtype/shape and exact bytes; request/cursor/ordinal/pre-state mismatch; START before draw; pending-call regeneration and committed-call no-redraw; crash after each G0–G4 journal boundary; orphan/conflicting/corrupt DB; pre-barrier draw attempt; post-G4 identity loss; 10,000-draw initialization shortfall; sampler resume; duplicate-before-geometry; ULP/representation mismatch; either-arm preflight mismatch, order/key/vector/copy mismatch; ensure zero evaluator calls before both certificates.

**Acceptance.** Recovered pair/cell identity is byte-exact or fails closed; no sampler RNG before G4; sealed ordered population and representation hashes validate; every actual L-SHADE and DE input equals the seal bitwise/key/order in both full preflights; committed RNG calls replay without redraw and pending calls reproduce under the same call ID; all counter equations reconcile; both arm stores are private; no COM/provider imports/calls occur. Q1-05's final arm-initialization recovery evidence is completed with the B/C initialization adapters and D's crash matrix before the gate is marked passed; A owns the gate-level record and contract.

**Evidence.** Deterministic golden vectors, schemas/hashes, journal event excerpts, fault-point recovery table, both 234-member preflight certificates, counter reconciliation, import-boundary report, pinned source/config/environment fingerprint, and reviewer-ready focused test results. No large raw population dump in Git; publish compact certificate summaries/hashes only.

**PR artifact.** One focused Q1-A implementation PR: new infrastructure modules, limited tests and compact synthetic evidence, explicit touched-file/import report, source/config/environment identity, and an interface compatibility table for B/C. No Stage 4C data. Do not merge without independent review/user acceptance.

**Exit to Q1-B/C.** Q1-A PR reviewed/accepted; schemas and interfaces are stable; Q1-03/04/14/15 pass and Q1-05's identity/genesis/seal/preflight portion passes; no unresolved Q0 contract ambiguity. Q1-05 is not marked fully passed until both B/C initialization paths and D's recovery evidence are integrated. Q1-16's foundational transaction primitives may be supplied here, but its full cross-optimizer crash/recovery gate is owned and closed by Q1-D.

### Q1-B — Controlled DE implementation

**Purpose.** Implement the dedicated controlled DE arm exactly as frozen and connect it to Q1-A interfaces without weakening accounting or replay identity.

**Q0 contract linkage.** Q0-R1/R2 controlled-DE proposal/donor/crossover/reflection/survivor/retry rules; Q0-R2 transaction and evaluation accounting; Q0-R3 RNG call tape, shared initialization and pre-FE identity contract.

**Modules/responsibilities.** New `src/sawopt/optimizers/controlled_de.py`; Q1-A journal/RNG/identity APIs; minimal integration in `runner.py`; new DE-focused synthetic tests. Do not use/relabel `ScipyDELegacyBackend` or `FixedDEReferenceBackend`. Do not edit comparator/canonicalizer.

**Inputs, outputs, state, persistence.** Inputs are a ready pair/cell identity, validated attached population, exact DE initial physical vectors, injected deterministic synthetic evaluator, PCG64 facade and 4,096 terminal budget. Persist generation-start parent snapshot, target order/cursor, ordered pending trials/results, retry cursor, proposal and evaluation events, private canonical cache, counters, trace and generation checkpoint. Outputs include exact search status and a complete backend/journal state suitable for replay.

**Dependencies.** Q1-A stable interfaces; Q1-C may proceed in parallel once A is accepted. Q1-D consumes this generation state and journal behavior.

**Required tests / abnormal cases.** Fixed-RNG golden donor exclusion/order, exact `rand/1`, forced coordinate/mask draw sequence, F/CR, reflection and canonical remap; duplicate retry against immutable generation snapshot; exact tie keeps parent; geometry reject ends target; max 4,096 proposal boundary with no extra draw; shared 65,536 watchdog; no evaluator beyond 4,096 FE; exact 16×234 + 118 partial-generation arithmetic; crashes at pending generation, target cursor, duplicate, RNG/evaluator intent/result, result-before-survivor and terminal FE.

**Acceptance.** Fixed N=234, F=.5, CR=.9 and synchronous frozen-parent semantics match the Q0 proposal exactly; per-target proposal cap and global watchdog stop at exact boundaries; 4,096 cap and all counter partitions reconcile; canonical duplicate/cache never incurs an evaluator call/FE; restart/replay eventually matches uninterrupted DE scientific state and trace; no comparator change, COM/provider call or production route.

**Evidence.** Golden input/output fixtures, proposal and call-identity trace, FE/counter ledger, final partial-generation proof, duplicate/failure boundary cases, checkpoint/replay digest, source/config/environment fingerprint and focused-test summary.

**PR artifact.** One focused Q1-B implementation PR with dedicated backend, adapter use, gate-linked synthetic tests and compact replay evidence. No COM evaluation or real study outputs.

**Exit to Q1-D/E.** Q1-B PR independently reviewed/accepted; primary gates Q1-02/06/07/08/09/10/13/17 pass; DE state/trace/replay interface is stable for Q1-D and integration.

### Q1-C — L-SHADE integration

**Purpose.** Attach transaction, RNG-tape and restart instrumentation to the existing L-SHADE package while preserving its actual search behavior and complete pre-step state.

**Q0 contract linkage.** Frozen Q0 L-SHADE resolved settings, source operator/update/fallback behavior, 4,096 cold horizon, versioned lossless state/RNG contracts, Q0-R3 full pre-step replay and Q1 result-store/backend-cache separation.

**Modules/responsibilities.** New `lshade_adapter.py` and stage-specific codec/state boundary; minimal, reviewed observation hooks in `src/sawopt/optimizers/lshade.py` only if required. Continue use of the existing `GeometryFirstComparator` unchanged. Do not alter Stage 4C `state_version=4`, `checkpoint_session.py`, historical readers or saved checkpoints.

**Inputs, outputs, state, persistence.** Inputs are the immutable cell identity, Phase-II-attached common population and L-SHADE genotype, lossless RNG facade, private journal/result adapter and deterministic synthetic evaluator. Persist complete live pre-step state, event-tape cursor, proposal/evaluation events, result/cache/FE state, fallback and memory batch state, and exactly one post-step commit (including FE delta zero). On restore, replay existing `_generation` control flow from the pre-step; rebuild locals from recorded RNG/results, never partial values.

**Dependencies.** Q1-A interfaces; can proceed in parallel with Q1-B. Q1-D verifies cross-cutting crashes and complete scientific trajectory equivalence.

**Required tests / abnormal cases.** Assert all resolved settings and reject 96,000 horizon; no-crash hooked/unhooked proposal/state parity; F/CR Cauchy retries, donor and crossover order, repair, duplicate retries; first-`None` fallback exit and fallback candidate accounting; interrupted evaluator and result-before-update; memory flush, archive trim, population shrink; zero-FE unsuccessful offspring; backend historical cache/FE restoration distinct from journal result store; crash before/after optimizer-step commit; direct-live-field lossless codec and reject nullified v4 payload as source.

**Acceptance.** Existing L-SHADE decisions, arithmetic, branches, RNG calls/order, proposal sequence and comparator semantics are unchanged; cold horizon/settings match Q0; journal replay reconstructs all local values from source/tape; each no-FE transition commits once; durable result is replayed as original logical first evaluation where appropriate and never recommitted/recounted; no Stage 4C source/state/data change.

**Evidence.** Uninstrumented-versus-hooked parity artifact; complete pre/post state and per-step replay digest; fallback and no-FE trace; codec round-trip/negative cases; separate backend and journal counter ledger; pinned source/config/environment identity and focused tests.

**PR artifact.** One Q1-C integration PR with minimal hook diff, adapter/state codec, isolated synthetic tests and explicit historical-protection diff; no COM runs and no migration of Stage 4C states.

**Exit to Q1-D/E.** Q1-C PR independently reviewed/accepted; primary gates Q1-01/11/18 pass; Q1-D can fault-inject complete L-SHADE paths and Q1-E can invoke the stable backend interface.

### Q1-D — Crash Recovery / Determinism Qualification

**Purpose.** Cross the integration boundary and establish fail-closed, exactly-once durable accounting and scientific trajectory equivalence under synthetic fault injection.

**Q0 contract linkage.** Entire Q0-R2 transition/failure/censor contract and Q0-R3 genesis/RNG/pre-step replay requirements. This unit validates implementation against the fixed rules; it does not invent recovery states or redefine evaluator determinism.

**Modules/responsibilities.** New/reused `recovery.py` test harness and shared fault-injection fixtures; exercise Q1-A journal, Q1-B DE and Q1-C L-SHADE. Keep operational-attempt history separate from scientific trajectory fields.

**Inputs, outputs, state, persistence.** Inputs are versioned pair/cell identities, persisted SQLite journals/checkpoints, deterministic synthetic evaluator and explicit fault-point schedule. Outputs are per-fault recovery verdicts, exact event-chain and state digests, durable FE/result ledgers, trajectory comparisons and terminal failure status where appropriate.

**Dependencies.** Q1-A, Q1-B and Q1-C reviewed interfaces/implementations. Q1-D is not a substitute for a failing unit gate in A/B/C; fix at owner, then rerun only the bounded affected qualification and D matrix.

**Required tests / abnormal cases.** Inject crash before/after every genesis, RNG START/COMMITTED, PCG64 return, proposal, intent, evaluator start/return, result, duplicate/cursor, fallback `None`, zero-FE step, memory/archive/shrink/trace, DE generation, checkpoint and validation boundary. Test corrupt/truncated journals/checkpoints, hash/sequence mismatch, wrong identity/environment/config, post-G4 loss, pending evaluation, repeated physical attempt, committed result, and stale/missing snapshots. Verify exact result/FE/cache/trace once, logical RNG calls no skip/double, and unchanged science state after restart.

**Acceptance.** All mandatory Q1-12/Q1-16/Q1-19 cases pass. Restarted scientific proposal/RNG/population/cache/rank/trace/top-16 fields equal the uninterrupted reference exactly for both algorithms. Operational retries, journal recovery and downtime are separately recorded. Committed draws/results are not redrawn/recounted; pending calls/transactions follow only their Q0 recovery rule. Any corrupted or identity-mismatched state fails before hydration/evaluator call.

**Evidence.** Fault-injection matrix (boundary × expected state × observed state), event hash-chain and prefix reconciliation, uninterrupted/recovered bitwise digests, FE/result/cache/trace uniqueness report, invalid-state rejection records, environment fingerprint and test summary.

**PR artifact.** One focused Q1-D recovery/qualification PR with fault fixtures, reproducible compact synthetic evidence, per-gate pass table and no production or COM evidence.

**Exit to Q1-E.** Q1-D PR independently reviewed/accepted; primary Q1-12/16/19 pass with no unresolved integrity mismatch; all A/B/C primary gates remain passing at the same pinned fingerprint.

### Q1-E — Synthetic Integration / Comparison Reporting

**Purpose.** Exercise the full fixed matrix only as a synthetic software integration and generate reproducible, censored comparison records using Q0 rules.

**Q0 contract linkage.** Fixed 2 topologies × 2 algorithms × 3 matched roots, private arm caches, exact shared 234-member starts, 4,096 unique search FE/cell, top-16 validation, serial order, exact timing/resource ledger, and Q0-R2 seven paper-only censored cases. The integration objective is synthetic and makes no physical or SAW claim.

**Modules/responsibilities.** New `runner.py` orchestration restricted to injected synthetic evaluator; `reporting.py` consumes gate-qualified journal traces and emits deterministic JSON/CSV/report. Tests enforce no COM/provider/physics import or call and no production orchestration. Never call a COM evaluator, the real Stage 4C evaluator or launch APIs.

**Inputs, outputs, state, persistence.** Inputs are pinned source/config/environment fingerprints, fixture topologies/design spaces, exact matched roots, one synthetic objective, 12 isolated cell journals and fixed resource policy. Outputs: 12 visible cell records including incomplete/invalid cells; immutable input/identity hashes; validated synthetic top-16 records; phase-separated timing/resource counters; complete synthetic comparison summary and censored-case fixtures. Any raw synthetic journals remain outside Git if bulky; committed PR evidence is compact and deterministic.

**Dependencies.** A–D acceptance and stable public APIs; no Q1 run before separate authorization. The integration itself remains Q1 synthetic-only.

**Required tests / abnormal cases.** Exactly 12 planned cells and fixed order; shared initialization hash per pair and independent arm evaluation/caches; all complete/incomplete statuses; stable top-16 distinct search-history candidates and validation isolation; time/resource counter disjointness; all seven paper-only censored examples including initialization-only/asymmetric failure; valid contiguous common prefixes, exact tuple paired outcomes, six pairs always visible, no forward-fill/survivor-only summary; missing/invalid trace support; import/call guard proving no COM/provider/network and no production orchestration.

**Acceptance.** Q1-20…23 all pass. Every cell and pair is visible; all aggregation obeys the frozen comparator/support/endpoint/status rules; synthetic search FE never exceeds 4,096 per arm; validation is excluded; report hashes reproduce; no physical evaluator or production path is imported or invoked. Results are labeled synthetic qualification only, not SAW outcomes.

**Evidence.** Matrix manifest and 12 cell-status ledger, population/preflight hashes, top-16 and validation digest, comparison/censor report, FE/time/resource reconciliation, import/call-boundary evidence, pinned source/config/environment fingerprint, deterministic report checksum and focused-test summary.

**PR artifact.** One focused Q1-E integration/reporting PR with compact synthetic evidence, Q1-20…23 dispositions, exact report reproduction and explicit no-COM/no-production boundary proof.

**Exit / overall Q1 close.** Q1-E PR independently reviewed and accepted; all 23 official gates pass in one pinned implementation/config/environment provenance set and reproducible evidence is published. Stop at review. A Q1 pass does not authorize a real optimizer comparison, COM evaluation, Stage 4C change or production launch.

## 6. Sole official Q1 gate ownership and coverage

This is a **one-to-one primary ownership map** to the existing matrix only. The work-unit gate associations requested in the project plan may overlap as dependencies (in particular Q1-16); that does not duplicate or redefine an official gate. Full pass conditions remain solely in the [Q1 matrix](stage5a2_q1_qualification_matrix.md).

| Official gate | Primary owner | Cross-unit dependency / note |
|---|---|---|
| Q1-01 | Q1-C | Uses A RNG/state codec. |
| Q1-02 | Q1-B | Uses A RNG and canonicalization. |
| Q1-03 | Q1-A | Shared facade supports B/C/D. |
| Q1-04 | Q1-A | B/C supply actual-input paths; both certificates before any FE. |
| Q1-05 | Q1-A | D fault-injects coordinator; A owns initial population/genesis qualification. |
| Q1-06 | Q1-B | C participates in private L-SHADE cache behavior. |
| Q1-07 | Q1-B | D independently fault-tests reconciliation. |
| Q1-08 | Q1-B | Synchronous DE semantics. |
| Q1-09 | Q1-B | Exact final partial generation. |
| Q1-10 | Q1-B | Proposal/stall boundaries. |
| Q1-11 | Q1-C | Existing L-SHADE fallback behavior. |
| Q1-12 | Q1-D | Cross-component failure taxonomy. |
| Q1-13 | Q1-B | DE and shared schema validation; C must preserve existing comparator behavior. |
| Q1-14 | Q1-A | Lossless shared codecs; C supplies live state payload. |
| Q1-15 | Q1-A | Identity/attachment lifecycle; D tests corruption/recovery. |
| Q1-16 | Q1-D | One integrated transaction-transition/recovery matrix; A/B/C supply transitions. |
| Q1-17 | Q1-B | DE restart; D supplies crash harness. |
| Q1-18 | Q1-C | L-SHADE restart; D supplies crash harness. |
| Q1-19 | Q1-D | Cross-algorithm scientific trace integrity. |
| Q1-20 | Q1-E | Dense finalist validation. |
| Q1-21 | Q1-E | Synthetic-only 12-cell integration. |
| Q1-22 | Q1-E | Timing/resources/storage reporting. |
| Q1-23 | Q1-E | Frozen censored comparison report and seven paper-only examples. |

**Coverage check:** 23 distinct primary assignments; Q1-01 through Q1-23 each appear once; no new qualification ID is introduced. Work-unit gate associations (which can overlap) are: Q1-A touches Q1-03/04/05/14/15 and provides transaction primitives for Q1-16; Q1-B touches Q1-02/06–10/13/17 and supplies transitions for Q1-16; Q1-C touches Q1-01/11/16/18; Q1-D touches Q1-12/16–19 and provides the integrated crash/recovery qualification, while Q1-17 and Q1-18 remain primarily owned by Q1-B and Q1-C respectively; Q1-E owns Q1-20–23. Cross-unit mentions are dependencies, not additional gate instances.

## 7. Shared evidence, PR and governance requirements

Each implementation PR must include: changed-module/responsibility list; exact Q0 contracts/gate IDs; focused synthetic test commands/results; abnormal-case evidence; source/config/environment fingerprint; machine-readable compact evidence or hashes; and explicit statement that no COM/network/physics, real SAW optimization, Stage 4C mutation or production orchestration was run. Review the PR on GitHub; a passing test or Codex self-review is not external acceptance. Keep each PR scoped to its work unit and do not merge automatically.

Q1 qualification artifacts must be sufficient for an independent reader to reproduce the checks, while large journals/checkpoints/populations remain outside the repository under the project storage policy. Only compact deterministic summaries/hashes belong in the PR.

## 8. Start gate and stop conditions

### Start gate — currently unmet

Q0 closeout is recorded and independent Q0 review is complete. The missing condition is **separate explicit user authorization to start Q1 implementation and deterministic synthetic-only qualification**. Until that authorization is received, Q1 remains not started; this plan is not such permission.

### Stop/fail-closed conditions

Stop the affected work unit and do not choose a workaround if any of the following occurs:

- A Q0 identity, sampler, RNG, optimizer, evaluation, failure, comparator, budget, censoring or reporting rule cannot be implemented as written.
- Either actual initial population preflight differs by one bit, key, order or evaluator boundary before FE.
- Journal/checkpoint identity, sequence/hash, typed value, event, RNG cursor, result or FE ledger is missing/mismatched/corrupt.
- A committed RNG result would be redrawn, a committed result/FE/cache/trace would be duplicated, or a zero-FE optimizer step would be skipped/doubled.
- L-SHADE instrumentation changes its original uninterrupted scientific trajectory or uses a lossy/nullified historical state payload.
- An unexpected/infrastructure failure is being classified as modeled physics failure, or a censored/invalid cell is about to be ranked as complete.
- A COM/provider/physics import or call, production orchestration, Stage 4C write, actual SAW optimizer run, changed budget or other prohibited action is reached or proposed.

Record concrete evidence and impact, preserve journals/source, and request the appropriate independent review/user decision. Do not automatically escalate to Sol unless a Q0 design contradiction or high-risk change requires it under project policy. Do not spawn a successor implementation/run from a completion continuation.

## 9. Q1 acceptance and what remains out of scope

Q1 acceptance requires all Q1-01…Q1-23 mandatory gates passed in a pinned environment with reproducible evidence and a common source/config/environment fingerprint, independent GitHub review of the implementation/evidence, and user acceptance. Any mandatory failure leaves Q1 incomplete; no partial pass can be represented as authorization for a later stage.

Even after Q1 acceptance, **separate user-reviewed authorization** is still required before COM/network/physics evaluation, the 12-cell real comparison, an optimizer pilot/benchmark, production orchestration, any budget/bound/topology/specification/constraint change, or Stage 4C data changes. This plan authorizes none of them.
