# Stage 5A-2 Q0 formal closeout — 2026-10-21

**Current decision:** `CLOSED / ACCEPTED` by explicit user direction on 2026-10-21.

**Protocol evidence:** Q0-R3 design approval by Sol and independent GitHub acceptance for documentary merge.

**Q1 status:** `PLANNED / IMPLEMENTATION NOT STARTED / AWAITING SEPARATE USER AUTHORIZATION`.

**Scope of this record:** documentary closeout of Q0 and the boundary into Q1. It records no Q1 implementation or software qualification result.

## 1. Q0 purpose and boundary

Q0 froze the design contract for a bounded, exploratory, matched-budget comparison of two complete optimizer packages on the unchanged Stage 4C MLIT/T1 problem. It addressed comparison identity, initialization, optimizer semantics, evaluation accounting, deterministic replay and censoring/reporting. Q0 approved a protocol design; it did **not** implement or validate that protocol in software, conduct a synthetic qualification, prove physical evaluator determinism, authorize COM/network evaluation, or authorize the 12-cell SAW comparison.

The Q0 design record is carried by the [minimum-fair-comparison plan](../plans/stage5a2_minimum_fair_comparison.md), the [Q1 qualification matrix](../plans/stage5a2_q1_qualification_matrix.md), and the [Q0-R3 packet](../../reports/escalation_packets/stage5a2_q0_protocol_revision_r3_20261021.md), which incorporates earlier decisions from [Q0-R2](../../reports/escalation_packets/stage5a2_q0_protocol_revision_r2_20261021.md) and [Q0-R1](../../reports/escalation_packets/stage5a2_q0_protocol_revision_20261021.md). Prior packets and their recorded statuses remain historical evidence; this closeout does not rewrite them.

## 2. Q0-R1/R2/R3 decision history

| Revision | Design/review outcome | Closeout interpretation |
|---|---|---|
| Q0-R1 | Sol's bounded re-review returned `REQUEST_Q0_REVISIONS`; independent GitHub review accepted the fidelity of the finding record as `ACCEPT_REVIEW_RECORD_WITH_DOC_CORRECTIONS` / `Q0_NOT_APPROVED`. | Proposed the exploratory full-package comparison envelope, common 234-member initialization, 4,096 unique-FE budget, controlled-DE operator, unchanged comparator and top-16 validation. The reviews required further decisions on fallback/replay transitions, identity/serialization, exact initialization inputs and censored-cell reporting. This was not protocol approval. |
| Q0-R2 | Sol returned `REQUEST_Q0_REVISIONS` (one review; the later read-back was a confirmation, not a second review). Independent GitHub review returned `ACCEPT_REVIEW_RECORD / REQUEST_Q0_REVISIONS / Q1_BLOCKED`. | Added SQLite transaction/idempotency rules, L-SHADE zero-FE commits, lossless codec direction, corrected fallback accounting, failure taxonomy and censored-pair reporting. R2-SOL-01–04 below remained unresolved and were not delegated to Q1. |
| Q0-R3 | Sol returned `APPROVE_Q0_PROTOCOL`. Independent GitHub review of PR #50 first required a narrow Phase-I/Phase-II identity clarification; that clarification and the initializer-exception wording were applied and independently accepted as `ACCEPT_FOR_DOCUMENTARY_MERGE`. | Closed the four R2 blockers at the design level: G0–G4 identity readiness, exact RNG-call recovery and L-SHADE pre-step replay, representation-aware sealed evaluator inputs with bitwise pre-FE checks, and future synthetic-only Q1 scope. Design approval and review prerequisites were met after the specified documentary correction. PR merge and formal Q0 closure remained separate events. |

Review records: [PR #47](https://github.com/MasayaTakagi/saw-com-optimizer/pull/47#issuecomment-6294426203), [PR #48](https://github.com/MasayaTakagi/saw-com-optimizer/pull/48#issuecomment-6304039265), [PR #49](https://github.com/MasayaTakagi/saw-com-optimizer/pull/49#issuecomment-6312601955), [PR #50 initial independent review](https://github.com/MasayaTakagi/saw-com-optimizer/pull/50#issuecomment-6313318732), and [PR #50 follow-up acceptance](https://github.com/MasayaTakagi/saw-com-optimizer/pull/50#issuecomment-6313529105). The review trail distinguishes accepting a record, accepting a design for documentary merge, and accepting/closing the Q0 protocol.

## 3. R2-SOL-01…04 final disposition

| Finding | Final Q0 disposition | Required Q1 proof (not yet performed) |
|---|---|---|
| **R2-SOL-01 — partial pair/cell identity genesis** | `RESOLVED_WITH_SPEC`: the pair journal coordinates immutable pair/roster and ordered arm identities through G0–G4, with exact recovery rules and a durable all-identities-ready barrier. No cross-database atomicity is claimed; no sampler method may run before the barrier; post-barrier identity loss fails closed. | Fault-inject each genesis boundary; verify exact identity/reference checks, pristine-destination-only repair before G4, no sampler RNG before readiness, and fail-closed handling after G4. |
| **R2-SOL-02 — RNG-call transaction and L-SHADE state replay** | `RESOLVED_WITH_SPEC`: `stage5a2_rng_call_v1` binds owner/role/step/cursor/ordinal/method/typed arguments and complete PCG64 pre/post states and results. START/COMMITTED semantics distinguish pending-call regeneration from committed-output replay. Existing L-SHADE control flow is replayed from a complete pre-step state; partial local values are not guessed. | Prove each allowed RNG method/call identity and every crash edge, and demonstrate uninterrupted/restarted scientific trajectory equivalence under the pinned synthetic fixture. |
| **R2-SOL-03 — exact common initialization evaluator inputs** | `RESOLVED_WITH_JUSTIFIED_ALTERNATIVE`: `independent_uniform_rejection_lshade_image_v2` seals the actual post-L-SHADE-transform canonical physical input/key; DE receives that sealed physical vector directly. Both complete 234-member evaluator-input preflights must match the seal bitwise and in order before either arm's first FE. The deterministic representation pushforward and possible ULP/duplicate/geometry classification changes are explicit and retained. | Prove both actual 234-member paths, keys, order and evaluator-boundary copies match exactly before any synthetic initialization FE; any mismatch stops both arms. |
| **R2-SOL-04 — Q0/Q1 execution boundary** | `RESOLVED_WITH_SPEC`: Q0 itself allowed no implementation or execution. Future Q1 may run only deterministic COM-free synthetic software qualification after Q0 acceptance and separate user permission. | Establish synthetic-only import/call boundaries, no COM/provider/physics calls and no production orchestration in all Q1 integration paths. |

## 4. Sol and independent GitHub review; separate closure events

- **Sol:** Q0-R3 received one judgment-only `APPROVE_Q0_PROTOCOL`; the recorded review reports no open or new critical findings. This approved the protocol design, not software correctness or execution.
- **Independent GitHub review:** PR #50's review identified a real documentary ambiguity: Phase-I cell identities are immutable and precede population sampling, so sampled population/representation hashes must belong to each post-seal Phase-II attachment/execution record, not be back-written into Phase-I identity. The correction, and explicit labeling of the initializer-law exception, were accepted as `ACCEPT_FOR_DOCUMENTARY_MERGE`.
- **PR #50 merge event:** PR #50 was merged on 2026-10-21 at merge commit [`9427b404d302932b27f50d31919bb3fb95fcfcd4`](https://github.com/MasayaTakagi/saw-com-optimizer/commit/9427b404d302932b27f50d31919bb3fb95fcfcd4). This published the accepted design documentation. It was **not** the Q0 formal-close event.
- **Q0 formal-close event:** separately, the user explicitly directed formal Q0 closure on 2026-10-21 in the present work instruction. This closeout records that user decision as `CLOSED / ACCEPTED`. Neither Sol approval nor PR merge is represented as the user decision.

## 5. Q0-frozen comparison conditions

These are protocol conditions, not experimental outcomes or an authorization to run:

| Dimension | Frozen condition |
|---|---|
| Problem | Unchanged Stage 4C MLIT/T1 model/specification/geometry constraints/bounds/conventions, real 50/50 Ω ports, and 1,001-point search / 9,113-point common validation grids. No Stage 4C data or behavior change. |
| Topologies and design | `P_D` and `D_P`, independently optimized, 13 variables each. |
| Arms | Existing L-SHADE complete package, cold with a 4,096-FE terminal schedule horizon, versus a dedicated new controlled `DE/rand/1/bin`; do not relabel either legacy DE backend. L-SHADE search arithmetic/control flow is retained. |
| Controlled DE | Population 234, `F=0.5`, `CR=0.9`, reflection, synchronous generations and frozen proposal/update/retry semantics from Q0-R2/R3; no adaptation, archive, shrink, polish or fallback. |
| Matched roots and matrix | Roots `20261012`, `20261013`, `20261014`; 2 methods × 2 topologies × 3 matched roots = 12 planned cells, fixed alternating method order, serial execution, one worker/process and one BLAS/OpenMP thread. |
| Initialization | 234 shared ordered members generated with `independent_uniform_rejection_lshade_image_v2`. Seal actual L-SHADE evaluator vectors/keys after its existing normalize→physical→canonicalize path; give those exact physical values to DE initialization. Complete both arm pre-FE bitwise checks before any initial FE. No fitness-based resampling. |
| Budget/accounting | 4,096 unique search FEs per arm/cell including 234 initial evaluations (3,862 remaining; 49,152 maximum across 12 cells). New search geometry rejects, typed modeled failures, and returned invalid records charge one FE under their distinct statuses; duplicate/cache hits and sampler rejects do not. Validation is outside the search FE budget. No dispatch beyond 4,096. |
| Retry, ranking and validation | Shared 65,536 no-progress proposal watchdog and DE 4,096 proposals per target/generation; exact failure/censor rules; unchanged `GeometryFirstComparator.rank_key`, stable ordinals and parent-on-tie; stable top-16 full-history candidates independently validated. |
| RNG/replay | Explicit PCG64, versioned lossless typed call identity and START/COMMITTED journal, exact state serialization, identity barrier, and source-control-flow replay contracts as detailed in Q0-R3. |
| Interpretation | Exploratory complete-package comparison only. Report all planned cells, matched support, FE and wall-time curves, feasibility/violations, resources and limitations. No proof of convergence, infeasibility, global optimum or universal superiority. |

The Q0-R3 initializer is an expressly selected deterministic pushforward of the physical-bounds uniform draw through the existing L-SHADE representation path. It can alter final binary64 values and boundary duplicate/geometry outcomes relative to sealing the provisional candidate. That effect is not to be hidden or changed during Q1.

## 6. Q1 handoff interfaces and dependencies

Q1 is software qualification against deterministic synthetic evaluators only. Its cross-phase interfaces must preserve, rather than reinterpret, the Q0 contract:

1. **Pair identity/genesis (Phase I):** immutable pair identity and expected arm roster; immutable arm cell identities reference the pair. G0–G4 and the readiness barrier precede any sampler draw. Q1 must not insert population hashes into or rewrite these identities.
2. **Population attachment (Phase II):** one ordered 234-member population seal plus a separate representation attachment. Each arm's post-seal `POPULATION_ATTACHMENT_ATTACHED` record/execution envelope references both hashes and its unchanged Phase-I cell identity. Both pure arm preflight certificates precede either arm's initial FE.
3. **RNG facade:** Q1-A provides one journal-owned interface for typed PCG64 calls, with call request, START/COMMITTED lifecycle, exact results and pre/post states. Sampler and optimizer streams remain role-separated. The facade's replay API returns committed values without redraw and reproduces a pending call only from its verified pre-state.
4. **Evaluation boundary:** each arm has a private canonical-key cache and result/FE journal. The backend's restored pre-step cache/FE state is distinct from the journal result store. A result committed after the pre-step is supplied to the backend as its original logical first-evaluation response, while durable FE/cache/result state is not committed or counted twice.
5. **Optimizer-step boundary:** DE exposes frozen-generation/target state; L-SHADE replays its existing `_generation` from a complete pre-step snapshot through its unchanged control flow. The transaction journal records a complete optimizer-only commit even when FE delta is zero.
6. **Validation/reporting:** validation records are isolated from search FEs; comparison aggregation consumes only qualified committed traces and the fixed censored-pair rules. It cannot impute missing FEs or drop planned pairs.

**Dependency order:** Q1-A establishes identity, population, journal and RNG contracts first. Q1-B and Q1-C then consume those stable interfaces and may proceed independently of one another. Q1-D integrates/fault-injects the complete transaction and replay behavior across A/B/C; Q1-E depends on the qualified optimizer, recovery and trace interfaces from A–D. No dependency authorizes a future COM or production study.

## 7. Q1 carry-forward risks

- Q0 design review is not software verification. All 23 gates remain unpassed; exact behavior, atomicity, parity, and accounting must be established by Q1 evidence.
- Replay guarantees are conditional on pinned source/environment and deterministic evaluator behavior. Synthetic qualification cannot establish physical COM determinism. A real evaluator call may be physically repeated after uncertain interruption even though its durable result/FE is committed once.
- The initializer pushforward is a deliberate sampler-law change from the provisional R2 formulation and may affect ULP-level canonical values or duplicate/geometry classification; keep the exception disclosed and identity-bound.
- Equal unique FE counts do not equalize proposal counts, generations, physical evaluator attempts, fallback exposure, journal/recovery work or elapsed time. Three matched roots provide weak uncertainty evidence.
- A 4,096-FE finite search is not convergence/global-optimum proof. Stalls/incomplete cells remain censored and cannot establish mathematical infeasibility.
- Q1 must preserve Stage 4C source/data/checkpoints and must not route to COM/network models, production orchestration, or physical optimizer runs.

## 8. Matters not validated in Q0

No Q1 source code has been implemented; no unit or synthetic test, integration, RNG replay, crash injection, population preflight, SQLite fault case, optimizer run, COM/network/physics evaluation, Stage 4C mutation, or production launch was performed for this closeout. The Q0 approval is protocol/design acceptance only. The Q1 matrix is a future qualification contract, not evidence that any gate passed.

## 9. Conditions to begin Q1

Q0 is now formally closed, but Q1 may begin only after **separate explicit user authorization** for Q1 implementation and deterministic synthetic-only qualification. The work must proceed through reviewed Q1 implementation PRs under the official review workflow and remain within the existing 23 gate IDs. Before qualification runs, pin the implementation/source/config/environment identities and demonstrate the COM/provider/production-orchestration boundary. No Q1 pass, Q1 PR merge, or Q1 authorization permits actual COM/network calculations, the real 12-cell comparison, a pilot, budget/topology/model/spec changes, Stage 4C changes, or production orchestration; each remains subject to a later separate user-reviewed experiment authorization.

The one authoritative Q1 gate list is the [qualification matrix](../plans/stage5a2_q1_qualification_matrix.md); the implementation plan is [Q1 execution plan](../plans/stage5a2_q1_execution_plan.md). Q1 is awaiting authorization and has not started.
