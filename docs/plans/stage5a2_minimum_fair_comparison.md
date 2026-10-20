# Stage 5A-2 — minimum controlled generic full-space optimizer comparison

**Status:** One independent Sol re-review was executed; decision `REQUEST_Q0_REVISIONS`. Q0 remains OPEN and Q1 implementation is blocked. No Q1 implementation, tests, synthetic evaluations, COM/network calculations, optimizer execution, or production launch is authorized.

**Prerequisite:** [Stage 5A-1 read-only closeout](../history/stage5a1_closeout_20261020.md).

**Q0 protocol proposal (not accepted):** [Q0-R1 packet and independent Sol findings](../../reports/escalation_packets/stage5a2_q0_protocol_revision_20261021.md).

**Q1 gates:** [Q1 qualification matrix](stage5a2_q1_qualification_matrix.md).

**Prior decision history:** [PR #47](https://github.com/MasayaTakagi/saw-com-optimizer/pull/47) and [first Sol review packet](../../reports/escalation_packets/stage5a2_de_protocol_sol_review_20261021.md).

**Decision owner:** the user; a Sol judgment and independent GitHub review do not substitute for user acceptance.

## Question

Under one frozen Stage 4C COM/network/specification/bounds problem, does an alternative generic 13-variable mixed continuous/integer full-space optimizer obtain better short-budget common-grid feasibility-first quality or faster time-to-quality than the audited L-SHADE package? The comparison is exploratory, and does not test whether 4,096 evaluations prove feasibility or whether either topology/method is universally best.

## Q0-R1 comparison envelope

| Dimension | Proposed Q0-R1 choice (not accepted; see open findings) |
|---|---|
| Model/spec/ports | Stage 4C MLIT/T1 at real 50/50 Ω; protected COM inputs, objective, specs, geometry constraints, bounds and conventions unchanged |
| Topologies | `P_D`, `D_P`, optimized independently; 13 DOF each |
| Methods | Existing L-SHADE complete package versus a new dedicated controlled `DE/rand/1/bin`; do not use/relabel `ScipyDELegacyBackend` or `FixedDEReferenceBackend` |
| L-SHADE | Proposed cold 4,096 terminal horizon; initial 234, min 4; retain existing F/CR adaptation, p-best, archive, latent genotypes, parent-midpoint repair, immediate replacement, shrink schedule and existing duplicate fallback; see packet for settings, but replay/transaction details remain open |
| Controlled DE | Fixed population 234; `F=.5`, `CR=.9`; reflection; canonical phenotype remapping; synchronous generations; no adaptation/archive/shrink/polish/fallback; fully fixed RNG/donor/crossover/update/retry semantics in packet |
| Matched roots | `20261012`, `20261013`, `20261014` for each topology; same ordered initialization across methods; role-separated hash-derived PCG64 streams |
| Search budget | 4,096 unique canonical search FEs/cell inclusive of 234 initial FEs; 3,862 remain; geometry rejects and modeled physics failures charge one FE; duplicate/cache hit and sampler rejection do not |
| Matrix | 2 methods × 2 topologies × 3 matched roots = 12 cells; maximum 49,152 unique search FEs |
| Initializer | Proposed `independent_uniform_rejection_v1`; physical-bounds uniform draw, unchanged canonicalizer, duplicate then geometry rejection, maximum 10,000 draws, complete ordered population before evaluation; sampler resume identity and lossless RNG serialization remain open |
| Search/validation | Fixed 1,001-point search grid and unchanged 9,113-point common validation grid. Validate stable top 16 distinct search-history candidates; separate search incumbent and validation ranks |
| Ranking | Existing `GeometryFirstComparator.rank_key` unchanged; exact lexicographic tuples; no scalarization; parent-on-tie; stable first-evaluation ordinal for history, incumbent, finalist and validation ordering |
| Retry/failure | Proposed DE ≤4,096 proposal attempts per target/generation and shared 65,536 no-progress proposal watchdog; exact transition/recovery journal and censored-pair reporting remain open |
| Resources/order | One serial worker/process and one BLAS/OpenMP thread; fixed 12-cell alternating method order appears in packet; no parallel cells |
| Validation/interpretation | Report paired seed outcomes, FE- and wall-time curves, feasibility/violations, metrics, status, uncertainty and convergence limits. No finite-run global-optimum, infeasibility, or general superiority claim |

The Q0 packet §13 matrix records each prior Sol/PR #47 finding as `RESOLVED_WITH_SPEC`, `RESOLVED_WITH_JUSTIFIED_ALTERNATIVE`, or `BLOCKED_WITH_REASON`. Sol's re-review found blockers in L-SHADE replay, transaction transitions, identity/RNG serialization, and censored-pair reporting; see §14. The factual first-`None` fallback control-flow description and the single authoritative Q1-ID mapping were corrected after review, but were not re-reviewed by Sol. Q1 may not decide remaining items. The watchdog is a proposal-count limit, not a wall-time cutoff; incomplete trajectories remain `BUDGET_STALLED`.

## Review and implementation gates

1. The one authorized read-only Sol review was completed using the pinned `openai/gpt-6.1-sol` route and returned `REQUEST_Q0_REVISIONS`; the recorded child route is documented in §14. No second Sol agent is launched by this task.
2. The revised packet, finding matrix, this plan, Q1 qualification matrix, escalation log and Sol result are published on branch `codex/stage5a2-q0-protocol-revision` in [Draft PR #48](https://github.com/MasayaTakagi/saw-com-optimizer/pull/48). Obtain independent GitHub review and explicit user acceptance. Do not merge or close Q0 without that acceptance.
3. Q1 implementation remains blocked until the Q0 blockers in §14 have been explicitly resolved in an accepted protocol, then independent GitHub review and explicit user implementation permission are recorded. Q1 must pass the synthetic/unit-only matrix with proof that no COM/provider or production orchestration path is called.
4. Q1 pass does not authorize any pilot. A future launch still requires a frozen implementation/source SHA and preflight, external persistent storage, exact run contract, resource/abort policy, and separate explicit user authorization through the qualified workflow.

## Cost and scientific interpretation

The historical Stage 4C evaluator rate is a planning reference only; it is not a runtime prediction, quality guarantee, or authorization. Equal unique FE budgets do not equalize generations, COM attempts, L-SHADE fallback work, or elapsed time. Compare best-so-far search quality versus unique FE separately from quality versus active and end-to-end wall time. Three matched seeds provide weak uncertainty estimates. If any cell stalls, is invalid/incomparable, remains immature, or has incomplete validation, report unresolved status rather than extrapolating, extending budgets, or changing constraints automatically.

## Protected non-goals

No changed COM/physics/model, specification, objective, geometry limit, bound, topology, or evaluation budget; no L-SHADE behavior change; no weighted objective; no automatic seed replacement, budget extension, bound expansion, local-polish arm, or SAW-guided initialization; no Stage 4C data mutation; no Q1/run authorization from Sol or GitHub review alone. The Stage 4C scientific result remains `STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`.
