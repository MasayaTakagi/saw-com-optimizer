# Stage 5A-2 — minimum controlled generic full-space optimizer comparison

**Status:** Q0-R1 and Q0-R2 Sol dispositions are both `REQUEST_Q0_REVISIONS`. Q0 remains OPEN; the R2 review identified remaining blockers in identity genesis, RNG-call replay, initialization representation, and Q1 qualification scope. Q1 implementation is blocked. No Q1 implementation, tests, synthetic evaluations, COM/network calculations, optimizer study, or production launch is authorized.

**Prerequisite:** [Stage 5A-1 read-only closeout](../history/stage5a1_closeout_20261020.md).

**Current Q0 proposal (not accepted):** [Q0-R2 transaction/identity/serialization/censored-reporting packet](../../reports/escalation_packets/stage5a2_q0_protocol_revision_r2_20261021.md). The [Q0-R1 packet](../../reports/escalation_packets/stage5a2_q0_protocol_revision_20261021.md) and its `REQUEST_Q0_REVISIONS` record are preserved as history.

**Q1 gates:** [single authoritative Q1 qualification matrix](stage5a2_q1_qualification_matrix.md).

**Prior decision history:** [PR #47](https://github.com/MasayaTakagi/saw-com-optimizer/pull/47), [PR #48](https://github.com/MasayaTakagi/saw-com-optimizer/pull/48), and [first Sol review packet](../../reports/escalation_packets/stage5a2_de_protocol_sol_review_20261021.md).

**Decision owner:** the user; a Sol judgment and independent GitHub review do not substitute for user acceptance.

## Question

Under one frozen Stage 4C COM/network/specification/bounds problem, does an alternative generic 13-variable mixed continuous/integer full-space optimizer obtain better short-budget common-grid feasibility-first quality or faster time-to-quality than the audited L-SHADE package? The comparison is exploratory, and does not test whether 4,096 evaluations prove feasibility or whether either topology/method is universally best.

## Q0-R1 comparison envelope retained by the current Q0-R2 proposal

| Dimension | Q0-R1 value retained by the Q0-R2 proposal (not yet accepted) |
|---|---|
| Model/spec/ports | Stage 4C MLIT/T1 at real 50/50 Ω; protected COM inputs, objective, specs, geometry constraints, bounds and conventions unchanged |
| Topologies | `P_D`, `D_P`, optimized independently; 13 DOF each |
| Methods | Existing L-SHADE complete package versus a new dedicated controlled `DE/rand/1/bin`; do not use/relabel `ScipyDELegacyBackend` or `FixedDEReferenceBackend` |
| L-SHADE | Retained cold 4,096 terminal horizon; initial 234, min 4; preserve existing F/CR adaptation, p-best, archive, latent genotypes, parent-midpoint repair, immediate replacement, shrink schedule and duplicate fallback; Q0-R2 §6 specifies transactional replay without search-rule changes |
| Controlled DE | Fixed population 234; `F=.5`, `CR=.9`; reflection; canonical phenotype remapping; synchronous generations; no adaptation/archive/shrink/polish/fallback; fully fixed RNG/donor/crossover/update/retry semantics in packet |
| Matched roots | `20261012`, `20261013`, `20261014` for each topology; same ordered initialization across methods; role-separated hash-derived PCG64 streams |
| Search budget | 4,096 unique canonical search FEs/cell inclusive of 234 initial FEs; 3,862 remain; geometry rejects and modeled physics failures charge one FE; duplicate/cache hit and sampler rejection do not |
| Matrix | 2 methods × 2 topologies × 3 matched roots = 12 cells; maximum 49,152 unique search FEs |
| Initializer | Retained `independent_uniform_rejection_v1`; physical-bounds uniform draw, unchanged canonicalizer, duplicate then geometry rejection, maximum 10,000 draws, complete ordered population before evaluation; Q0-R2 §§7–8 specify pair/cell identity lifecycle and lossless RNG state |
| Search/validation | Fixed 1,001-point search grid and unchanged 9,113-point common validation grid. Validate stable top 16 distinct search-history candidates; separate search incumbent and validation ranks |
| Ranking | Existing `GeometryFirstComparator.rank_key` unchanged; exact lexicographic tuples; no scalarization; parent-on-tie; stable first-evaluation ordinal for history, incumbent, finalist and validation ordering |
| Retry/failure | Retained DE ≤4,096 proposal attempts per target/generation and shared 65,536 no-progress proposal watchdog; Q0-R2 §§3–6 and 10–11 specify durable transitions, and censored-pair rules |
| Resources/order | One serial worker/process and one BLAS/OpenMP thread; fixed 12-cell alternating method order appears in packet; no parallel cells |
| Validation/interpretation | Report paired seed outcomes, FE- and wall-time curves, feasibility/violations, metrics, status, uncertainty and convergence limits. No finite-run global-optimum, infeasibility, or general superiority claim |

Q0-R1's Sol review and PR #48 comments identified four blockers. Q0-R2 received its requested Sol review, which accepted the censored-pair contract, lossless codec direction, zero-FE transition design, corrected fallback flow, and sole Q1-ID matrix, but returned `REQUEST_Q0_REVISIONS`. Remaining Q0 blockers are partial pair/arm identity genesis; RNG-call crash/idempotency and replay-state reconstruction; exact identity between sealed physical initial members and L-SHADE's normalized/reconstructed evaluated vectors; and the contradiction between Q1 synthetic optimizer-state qualification and wording that prohibits optimizer execution. These remain Q0 decisions, not Q1 options. The watchdog remains a proposal-count limit, not a wall-time cutoff; incomplete trajectories remain `BUDGET_STALLED`.

## Review and implementation gates

1. Q0-R1 and Q0-R2 each received one read-only Sol review; both returned `REQUEST_Q0_REVISIONS`. The R2 result and observed child routing are recorded in the R2 packet and escalation log. No additional Sol review will be started automatically.
2. These documents are published in [Draft PR #49](https://github.com/MasayaTakagi/saw-com-optimizer/pull/49) from branch `codex/stage5a2-q0-r2-transaction-design`. Await independent GitHub review and explicit user disposition; do not merge or close Q0 automatically.
3. Q1 implementation remains blocked until the four R2 open items are resolved in Q0, independent GitHub review is complete, and explicit user implementation permission is recorded. Q1 must distinguish COM-free synthetic algorithm qualification from prohibited COM/production studies and must not choose unresolved Q0 semantics.
4. Q1 pass does not authorize any pilot. A future launch still requires a frozen implementation/source SHA and preflight, external persistent storage, exact run contract, resource/abort policy, and separate explicit user authorization through the qualified workflow.

## Cost and scientific interpretation

The historical Stage 4C evaluator rate is a planning reference only; it is not a runtime prediction, quality guarantee, or authorization. Equal unique FE budgets do not equalize generations, COM attempts, L-SHADE fallback work, or elapsed time. Compare best-so-far search quality versus unique FE separately from quality versus active and end-to-end wall time. Three matched seeds provide weak uncertainty estimates. If any cell stalls, is invalid/incomparable, remains immature, or has incomplete validation, report unresolved status rather than extrapolating, extending budgets, or changing constraints automatically.

## Protected non-goals

No changed COM/physics/model, specification, objective, geometry limit, bound, topology, or evaluation budget; no L-SHADE behavior change; no weighted objective; no automatic seed replacement, budget extension, bound expansion, local-polish arm, or SAW-guided initialization; no Stage 4C data mutation; no Q1/run authorization from Sol or GitHub review alone. The Stage 4C scientific result remains `STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`.
