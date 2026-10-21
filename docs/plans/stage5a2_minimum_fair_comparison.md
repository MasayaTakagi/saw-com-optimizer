# Stage 5A-2 — minimum controlled generic full-space optimizer comparison

**Status (2026-10-21):** Q0 is `CLOSED / ACCEPTED` by explicit user decision on 2026-10-21; see the [formal Q0 closeout](../history/stage5a2_q0_closeout_20261021.md). Q0-R1/R2/R3 review decisions remain in the historical packets. Under Issue #52, Q1-A is `LOCAL_EVIDENCE_READY / AWAITING INDEPENDENT REVIEW`; Q1-B/C/D/E are `NOT AUTHORIZED / NOT STARTED`. This plan does not authorize synthetic integration, COM/network calculations, a real optimizer study, Stage 4C mutation, or production launch.

**Prerequisite:** [Stage 5A-1 read-only closeout](../history/stage5a1_closeout_20261020.md).

**Q0 design record:** the accepted [Q0-R3 protocol packet](../../reports/escalation_packets/stage5a2_q0_protocol_revision_r3_20261021.md) incorporates prior decisions preserved in the [Q0-R2 packet](../../reports/escalation_packets/stage5a2_q0_protocol_revision_r2_20261021.md) and [Q0-R1 packet](../../reports/escalation_packets/stage5a2_q0_protocol_revision_20261021.md). Historical packet statuses are unchanged; the current closeout status is authoritative in the linked closeout record.

**Q1 gates:** [single authoritative Q1 qualification matrix](stage5a2_q1_qualification_matrix.md).

**Prior decision history:** [PR #47](https://github.com/MasayaTakagi/saw-com-optimizer/pull/47), [PR #48](https://github.com/MasayaTakagi/saw-com-optimizer/pull/48), and [first Sol review packet](../../reports/escalation_packets/stage5a2_de_protocol_sol_review_20261021.md).

**Decision owner:** the user; a Sol judgment and independent GitHub review do not substitute for user acceptance.

## Question

Under one frozen Stage 4C COM/network/specification/bounds problem, does an alternative generic 13-variable mixed continuous/integer full-space optimizer obtain better short-budget common-grid feasibility-first quality or faster time-to-quality than the audited L-SHADE package? The comparison is exploratory, and does not test whether 4,096 evaluations prove feasibility or whether either topology/method is universally best.

## Q0-approved comparison contract with explicit Q0-R3 initializer exception

| Dimension | Frozen Q0 condition |
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

Q0-R2 received `REQUEST_Q0_REVISIONS` for partial pair/cell genesis, RNG-call crash recovery/local-state reconstruction, exact initial evaluator-vector identity, and contradictory Q1 scope. Q0-R3 resolved these at the design level with the G0–G4 identity barrier, lossless typed RNG-call replay from complete L-SHADE pre-step state, exact 234-member pre-FE input certificates, and a future synthetic-only Q1 boundary. Sol returned `APPROVE_Q0_PROTOCOL`; independent GitHub review accepted the narrow Phase-I/Phase-II clarification and initializer-exception wording for documentary merge; the user then formally closed Q0 separately. Q1 has not started and still requires separate explicit user authorization. The initializer pushforward exception remains disclosed, and original logical first-evaluation/backend-cache semantics must be qualified. The watchdog remains a proposal-count limit, not a wall-time cutoff; incomplete trajectories remain `BUDGET_STALLED`.

## Review and implementation gates

1. Q0-R1 and Q0-R2 each received one read-only Sol `REQUEST_Q0_REVISIONS`; Q0-R3 received one read-only `APPROVE_Q0_PROTOCOL`. The independent PR #50 review's required documentary clarification was applied and accepted as `ACCEPT_FOR_DOCUMENTARY_MERGE`; PR #50 merged at `9427b404d302932b27f50d31919bb3fb95fcfcd4`. The user separately closed Q0 on 2026-10-21. The [closeout](../history/stage5a2_q0_closeout_20261021.md) records the distinct events and historical evidence.
2. The [Q1 execution plan](stage5a2_q1_execution_plan.md) splits future work into Q1-A…Q1-E while keeping the existing Q1-01…Q1-23 matrix as the sole formal gate list. Issue #52 authorizes Q1-A implementation and deterministic synthetic/unit tests only; Q1-B/C/D/E remain unauthorized. No official Q1 gate has passed.
3. Q1-A is authorized for local deterministic synthetic/unit work only. Q1-B/C/D/E still require separate authorization; no Q1 work may change Q0 semantics or invoke COM/provider/physics, perform a real SAW optimizer study, launch production orchestration, or mutate Stage 4C data. Q1-A authorization and any later Q1 acceptance do not authorize a real pilot.
4. Any future physical study still requires a frozen implementation/source SHA and preflight, external persistent storage, exact run contract, resource/abort policy, and separate explicit user authorization through the qualified workflow.

## Cost and scientific interpretation

The historical Stage 4C evaluator rate is a planning reference only; it is not a runtime prediction, quality guarantee, or authorization. Equal unique FE budgets do not equalize generations, COM attempts, L-SHADE fallback work, or elapsed time. Compare best-so-far search quality versus unique FE separately from quality versus active and end-to-end wall time. Three matched seeds provide weak uncertainty estimates. If any cell stalls, is invalid/incomparable, remains immature, or has incomplete validation, report unresolved status rather than extrapolating, extending budgets, or changing constraints automatically.

## Protected non-goals

No changed COM/physics/model, specification, objective, geometry limit, bound, topology, or evaluation budget; no L-SHADE behavior change; no weighted objective; no automatic seed replacement, budget extension, bound expansion, local-polish arm, or SAW-guided initialization; no Stage 4C data mutation; no Q1/run authorization from Sol or GitHub review alone. The Stage 4C scientific result remains `STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`.
