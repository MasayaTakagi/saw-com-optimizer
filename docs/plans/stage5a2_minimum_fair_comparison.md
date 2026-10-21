# Stage 5A-2 — minimum controlled generic full-space optimizer comparison

**Status:** Q0-R1 and Q0-R2 Sol dispositions were `REQUEST_Q0_REVISIONS`; Q0-R3 received one Sol `APPROVE_Q0_PROTOCOL` judgment. Q0 remains OPEN pending independent GitHub review and explicit user disposition; Sol approval is not Q0 closure or Q1 permission. Q1 remains NOT STARTED / BLOCKED. No Q1 implementation, tests, synthetic evaluations, COM/network calculations, optimizer study, Stage 4C mutation, or production launch is authorized.

**Prerequisite:** [Stage 5A-1 read-only closeout](../history/stage5a1_closeout_20261020.md).

**Current Q0 proposal (not accepted):** [Q0-R3 identity-genesis/RNG-replay/initialization/Q1-scope packet](../../reports/escalation_packets/stage5a2_q0_protocol_revision_r3_20261021.md). Q0-R2's accepted design principles and remaining findings are preserved in the [Q0-R2 packet](../../reports/escalation_packets/stage5a2_q0_protocol_revision_r2_20261021.md); the [Q0-R1 packet](../../reports/escalation_packets/stage5a2_q0_protocol_revision_20261021.md) is unchanged history.

**Q1 gates:** [single authoritative Q1 qualification matrix](stage5a2_q1_qualification_matrix.md).

**Prior decision history:** [PR #47](https://github.com/MasayaTakagi/saw-com-optimizer/pull/47), [PR #48](https://github.com/MasayaTakagi/saw-com-optimizer/pull/48), and [first Sol review packet](../../reports/escalation_packets/stage5a2_de_protocol_sol_review_20261021.md).

**Decision owner:** the user; a Sol judgment and independent GitHub review do not substitute for user acceptance.

## Question

Under one frozen Stage 4C COM/network/specification/bounds problem, does an alternative generic 13-variable mixed continuous/integer full-space optimizer obtain better short-budget common-grid feasibility-first quality or faster time-to-quality than the audited L-SHADE package? The comparison is exploratory, and does not test whether 4,096 evaluations prove feasibility or whether either topology/method is universally best.

## Retained Q0-R1 comparison envelope with explicit Q0-R3 initializer exception

| Dimension | Proposed Q0-R1/R2 terms and Q0-R3 initializer exception (not yet accepted) |
|---|---|
| Model/spec/ports | Stage 4C MLIT/T1 at real 50/50 Ω; protected COM inputs, objective, specs, geometry constraints, bounds and conventions unchanged |
| Topologies | `P_D`, `D_P`, optimized independently; 13 DOF each |
| Methods | Existing L-SHADE complete package versus a new dedicated controlled `DE/rand/1/bin`; do not use/relabel `ScipyDELegacyBackend` or `FixedDEReferenceBackend` |
| L-SHADE | Retained cold 4,096 terminal horizon; initial 234, min 4; preserve existing F/CR adaptation, p-best, archive, latent genotypes, parent-midpoint repair, immediate replacement, shrink schedule and duplicate fallback; Q0-R2 §6 and Q0-R3 §4 specify transaction replay without search-rule changes |
| Controlled DE | Fixed population 234; `F=.5`, `CR=.9`; reflection; canonical phenotype remapping; synchronous generations; no adaptation/archive/shrink/polish/fallback; fully fixed RNG/donor/crossover/update/retry semantics in packet |
| Matched roots | `20261012`, `20261013`, `20261014` for each topology; same ordered initialization across methods; role-separated hash-derived PCG64 streams |
| Search budget | 4,096 unique canonical search FEs/cell inclusive of 234 initial FEs; 3,862 remain; geometry rejects and modeled physics failures charge one FE; duplicate/cache hit and sampler rejection do not |
| Matrix | 2 methods × 2 topologies × 3 matched roots = 12 cells; maximum 49,152 unique search FEs |
| Initializer | Q0-R3 `independent_uniform_rejection_lshade_image_v2`: retain physical-bounds uniform source draws, then apply unchanged canonicalize → existing L-SHADE normalize → physical → canonicalize; seal the actual L-SHADE evaluator vector/key, reject duplicate before geometry on that final vector, cap 10,000 draws, complete/hash all 234 before either arm FE, and run both exact pre-FE evaluator-input checks. This is a deterministic binary64 representation pushforward, not fitness-based resampling; see Q0-R3 §5 for the explicit sampler-law impact. |
| Search/validation | Fixed 1,001-point search grid and unchanged 9,113-point common validation grid. Validate stable top 16 distinct search-history candidates; separate search incumbent and validation ranks |
| Ranking | Existing `GeometryFirstComparator.rank_key` unchanged; exact lexicographic tuples; no scalarization; parent-on-tie; stable first-evaluation ordinal for history, incumbent, finalist and validation ordering |
| Retry/failure | Retained DE ≤4,096 proposal attempts per target/generation and shared 65,536 no-progress proposal watchdog; Q0-R2 §§3–6 and 10–11 specify durable transitions/censoring, with Q0-R3 §§2–4 closing identity genesis and RNG replay |
| Resources/order | One serial worker/process and one BLAS/OpenMP thread; fixed 12-cell alternating method order appears in packet; no parallel cells |
| Validation/interpretation | Report paired seed outcomes, FE- and wall-time curves, feasibility/violations, metrics, status, uncertainty and convergence limits. No finite-run global-optimum, infeasibility, or general superiority claim |

Q0-R2 received `REQUEST_Q0_REVISIONS` for partial pair/cell genesis, RNG-call crash recovery/local-state reconstruction, exact initial evaluator-vector identity, and contradictory Q1 scope. Q0-R3 specifies an ordered pair-coordinated G0–G4 identity genesis with a durable all-identities-ready barrier; an exact typed RNG-call tape replayed from a complete pre-step L-SHADE state; a sealed population whose values are the exact actual evaluator vectors in both arms, with a pure 234-member pre-FE identity gate; and a conditional synthetic-only Q1 scope that is prohibited during Q0. Sol returned `APPROVE_Q0_PROTOCOL` for this design, with no open/new critical findings, while requiring the initialization pushforward exception to remain disclosed and original logical first-evaluation/cache semantics to be verified in Q1. The packet remains pending independent GitHub review and explicit user disposition. The watchdog remains a proposal-count limit, not a wall-time cutoff; incomplete trajectories remain `BUDGET_STALLED`.

## Review and implementation gates

1. Q0-R1 and Q0-R2 each received one read-only Sol review; both returned `REQUEST_Q0_REVISIONS`. Q0-R3 received one read-only `APPROVE_Q0_PROTOCOL` review. All records are preserved; no additional Sol review is planned.
2. Q0-R3 and the updated Q1 matrix are prepared in the current dedicated review branch. The prior Draft PR #49 records Q0-R2 history and is not rewritten. Q0-R3 publication requires its own Draft PR; do not merge or close Q0 automatically.
3. No Q1 work is authorized during Q0-R3. After accepted Q0, Q1 synthetic-only implementation/qualification still requires separate explicit user permission and must not choose unresolved Q0 semantics. No COM/provider/physics, real SAW optimizer study, production orchestration, or Stage 4C data change is within Q1.
4. Q1 pass does not authorize any pilot. A future launch still requires a frozen implementation/source SHA and preflight, external persistent storage, exact run contract, resource/abort policy, and separate explicit user authorization through the qualified workflow.

## Cost and scientific interpretation

The historical Stage 4C evaluator rate is a planning reference only; it is not a runtime prediction, quality guarantee, or authorization. Equal unique FE budgets do not equalize generations, COM attempts, L-SHADE fallback work, or elapsed time. Compare best-so-far search quality versus unique FE separately from quality versus active and end-to-end wall time. Three matched seeds provide weak uncertainty estimates. If any cell stalls, is invalid/incomparable, remains immature, or has incomplete validation, report unresolved status rather than extrapolating, extending budgets, or changing constraints automatically.

## Protected non-goals

No changed COM/physics/model, specification, objective, geometry limit, bound, topology, or evaluation budget; no L-SHADE behavior change; no weighted objective; no automatic seed replacement, budget extension, bound expansion, local-polish arm, or SAW-guided initialization; no Stage 4C data mutation; no Q1/run authorization from Sol or GitHub review alone. The Stage 4C scientific result remains `STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`.
