# Stage 5A-2 Q0 — L-SHADE vs controlled DE design review packet

**Status:** Sol reviewed; `REQUEST_Q0_REVISIONS`. Q0 remains open, not frozen, and not authorization to implement or execute. A consolidated revision must receive a separate Sol re-review before Q1; this task is limited to recording the decision and required follow-up.
**Review target:** `openai/gpt-6.1-sol`, Pi `thinking="medium"`; one read-only reviewer.
**Base source:** main `a1cbd9eab3999fb18ca3e0683ddfbabe21ea0559` (PR #46 merged).
**Stage 5A-1 prerequisite:** `ACCEPT_STAGE5A1_READ_ONLY_AUDIT`, scope-limited; this does not approve a new experiment.
**Decision owner after Sol and GitHub review:** user.

## Decision requested

Review the proposed Stage 5A-2 minimum-fair two-optimizer comparison, identify any blocking or required design changes, and return the exact headings and decision values requested at the end of this packet. In particular, decide whether the provisional 4,096-unique-FE pilot can support Q1 implementation/qualification (not a COM run), and whether the proposed controlled DE update/checkpoint contract is sufficiently specified.

This is a bounded design-judgment request. Do not implement, run tests, call COM, optimize, use Git/GitHub, or modify files. Do not authorize COM evaluation or a production/pilot experiment. Sol approval, if granted, is not Q0 closeout, independent GitHub review, user acceptance, or execution authorization.

## Authoritative context and source reconciliation

The following documents were read at the stated base SHA `a1cbd9eab3999fb18ca3e0683ddfbabe21ea0559`:

- `AGENTS.md`
- `docs/project_roadmap.md`
- `docs/history/stage5a1_closeout_20261020.md`
- `docs/plans/stage5a2_minimum_fair_comparison.md`
- `docs/guides/pi_sol_review_routing.md`
- `reports/escalation_log.md`

The Stage 5A-1 closeout accepts a scoped read-only audit and retains the historical Stage 4C result as `STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`. It expressly does not establish convergence or an optimizer winner, and does not approve new optimization. The Stage 5A-2 plan is a proposal only. Stage 5A-2 requires a generic full-space comparison under the frozen COM/spec/geometry contract, matched unique evaluation budgets, independent seeds, common dense validation, and evaluation- and wall-clock-quality curves. The qualified Sol route is separate from the design decision.

The previous local packet's statement that the cited closeout/plan/routing guide were missing was based on an outdated checkout and is superseded. All three are present at the confirmed main SHA above. Current local branch is `codex/stage5a2-q0-sol-review`; no Stage 4C data or source is changed by this packet.

## Read-only implementation audit relevant to the comparison

1. `src/sawopt/optimizers/scipy_de.py::ScipyDELegacyBackend` is **not an eligible comparison arm as-is**. Its `initialize()` discards the supplied population; SciPy controls initialization and generation semantics; `ceil(target/population)` generations do not enforce the exact unique budget; calls after the budget return artificial `1e100`; the comparator rank tuple is folded into a base-1000 scalar; and saved state has only counters/incumbent rather than population, full RNG/cache/proposal trace, and exact resume state. The scalar is not order-preserving for unrestricted lexicographic components. Do not wrap, relabel, or silently repair this legacy adapter and then call it the same implementation.
2. `src/sawopt/optimizers/lshade.py::FixedDEReferenceBackend` is **not standard DE/rand/1/bin**. It subclasses L-SHADE and merely sets `pbest_max_fraction=1.0` around the inherited offspring operation. It retains adaptive F/CR, archive/population-schedule/state machinery and uses a current-to-pbest-style mutation, not `x[r1] + F * (x[r2] - x[r3])`. A name change or parameter override cannot make it the proposed DE baseline.
3. `LShadeBackend` already supports an injected population, canonicalizer, comparator, unique-design accounting, a budget-terminal population schedule, 16-member historical finalist retention, and state including population/cache/RNG/traces. Its existing design is the L-SHADE reference, not a reason to share optimizer-specific results or caches.
4. `HybridDesignSpace.canonicalize` clips physical values to frozen bounds, rounds declared integer coordinates using `floor(x + 0.5)`, clips again, and returns the canonical tuple key. The hybrid evaluator applies geometry checks before COM/network evaluation. `GeometryFirstComparator` ranks physics-evaluated records before physics failures and geometry rejections; evaluated records use the existing feasibility-first comparator. Its status helper defaults a missing status to `PHYSICS_FAILED` and treats other/unrecognized statuses as geometry rejects, so the proposed path must validate candidate schemas before calling the comparator. Serialized `_jsonable` maps non-finite floats to `null`, which is ambiguous for replay unless a versioned infinity encoding is specified. Call its tuple rank directly for all candidate ordering; do not convert it into a weighted scalar.
5. The Stage 4C source/config audit shows the L-SHADE comparison arm is a **complete algorithm package**, not an otherwise-shared mutation operator: with the historical configuration it starts at `18 × D = 234`, uses minimum population 4 and a linearly shrinking `round()` schedule tied to its terminal horizon; current defaults include history size 6, initial `M_F = M_CR = 0.5`, p-best fraction 0.20, archive rate 1.0, max duplicate retries 5, and memory-update batch size set to the initial population size. Its per-offspring F is sampled from a positive Cauchy perturbation around the selected `M_F` and clipped to `(0,1]`; CR is sampled from a normal perturbation around `M_CR` and clipped to `[0,1]`; successful settings update the memories by weighted Lehmer/arithmetic means. It generates one offspring at a time, target index `generation_count % current_population_size`, and immediately considers replacement. It stores pre-canonical normalized genotypes; its boundary rule is parent-midpoint repair. After six normal mutation proposals (default retry setting 5), it tries `_unseen_proposal()`; for this mixed continuous/integer design space that attempts up to 256 uniform normalized draws to find an uncached canonical design. There is no default duplicate-streak exhaustion threshold (`None`), so an unsuccessful fallback can leave the budget loop without FE progress. The historical Stage 4C config has no explicit `lshade` overrides; the pilot still must snapshot/freeze its actual resolved configuration and disclose these existing behaviors.
6. The Stage 4C/Stage 4B initializer is named `independent_uniform_rejection_v1`: uniform draws in physical bounds, canonicalization, duplicate-key rejection, then geometry rejection; the checked config uses a 10,000-draw cap and SHA-256 seed derivation. This is a **candidate** for the matched pilot, not yet approved: the Stage 5A-2 namespace/root seed, exact stream/coordinate conventions, complete-population serialization, evaluation order, partial failure recovery, and no-seed-substitution contract still require an explicit decision.

These are source findings, not a claim that the proposed protocol is approved.

## Provisional comparison envelope — all values are Q0 review subjects

| Item | Provisional value |
|---|---|
| Topologies | `P_D`, `D_P`, optimized independently |
| Optimizers | L-SHADE and a new controlled DE/rand/1/bin implementation; no Legacy-DE or `FixedDEReferenceBackend` substitution |
| Matched seeds | 3 fresh independent seeds per topology, same seed labels and same initial population across both optimizer arms; actual integer seeds are frozen before any later execution |
| Search budget | 4,096 unique canonical search-design evaluations **per cell, inclusive of initialization** |
| Matrix | 2 topologies × 2 optimizers × 3 matched seeds = 12 cells; 49,152 unique search FEs maximum |
| Dimensions | 13 DOF per topology |
| Initial population | `18 × D = 234` unique, geometry-valid designs per topology/seed, same physical canonical vectors and order for both methods; each arm independently evaluates and charges all 234, leaving 3,862 unique search FEs |
| Search / validation grids | Fixed historical 1,001-point search grid; common 9,113-point dense validation grid |
| Terminal candidates | Historical top 16 unique search candidates per cell, retained from the full search history and validated independently on the 9,113-point grid |

These are **provisional Q0 design values**, not frozen/approved values, an execution authorization, or evidence that 4,096 FEs is sufficient for convergence or feasibility. The 3-seed comparison is exploratory only. No optimizer arm may be declared universally superior from this small pilot.

### Initial-population fairness and accounting

- Generate each topology/seed's 234-member physical population once from an algorithm-independent sampler stream derived from a frozen root seed/protocol identity; do not derive it from optimizer-specific random state. Freeze and report the canonical population sequence and hash. Both arms receive exactly the same vector order.
- Each arm has a separate cache and independently evaluates every initial design on the same search grid. Do not transfer fitness, result records, or evaluation cache entries across algorithms or seeds. The initial 234 designs count toward each arm's own 4,096 unique-FE cap.
- Initialization sampling draws rejected before becoming members (duplicate canonical design or failed geometry screen) are reported separately as sampler draws/rejection reasons; they are not search objective evaluations. Every accepted unique, geometry-valid initial member is one charged search FE, even if its physics evaluation fails.
- Candidate initializer to resolve at Q0: reuse `independent_uniform_rejection_v1` from the existing hybrid study (independent uniform draws over physical bounds; canonicalize; reject duplicate canonical keys and geometry-invalid candidates; maximum 10,000 sampler draws), with a Stage 5A-2-specific stable SHA-256 seed namespace. Materialize and hash the entire ordered population before either arm evaluates it; pass identical canonical members in the normalized representation expected by L-SHADE. This specific distribution/namespace/cap is **not approved yet** and must be accepted or replaced before Q1.
- If the sampler cannot produce 234 unique geometry-valid candidates within its frozen cap, mark the cell `INITIALIZATION_FAILED`, retain all draw/rejection counts, do not substitute a seed or resample after seeing fitness, and do not treat the cell as a completed comparison. Specify whether full population construction precedes evaluation (preferred) and how interrupted partial evaluation resumes; any members already evaluated remain charged once.

### Candidate controlled DE contract for review

A dedicated backend is the candidate design; preserve historical backend behavior. Sol endorsed the following as defensible **design choices** (not as a frozen protocol or execution authorization): fixed population 234; no shrink/adaptation/archive/polish/alternate fallback; `F=0.5`, `CR=0.9`; deterministic componentwise reflection; canonical phenotype remapping; synchronous parent snapshots; and exact-budget final partial generation. The remaining details below still require resolution/freeze:

1. Work in normalized coordinates `[0,1]^13`, with each proposal decoded to the frozen physical bounds and then passed through the same canonicalizer as L-SHADE. After integer canonicalization, use the canonical physical design mapped back to normalized coordinates as the DE population genotype, so two proposals with the same canonical key cannot persist as different effective states.
2. Use classical DE/rand/1/bin mutation with a fixed population of 234: choose three donor indices uniformly and in a deterministic recorded draw order, without replacement from the population excluding target `i`, and form `v = x[r1] + F * (x[r2] - x[r3])`. No p-best, current-to-pbest, population shrinking, archive, adaptive SHADE parameters, polishing, or alternate proposal fallback.
3. **Sol-endorsed candidate fixed parameters:** `F = 0.5`, `CR = 0.9` for every topology and seed. Binomial crossover uses a forced coordinate, ensuring at least one mutant coordinate. No per-cell tuning or parameter adaptation. Sol judged these defensible untuned baseline settings, not established best settings; exact crossover RNG convention/draw order remains to be frozen.
4. **Sol-endorsed candidate boundary rule:** after crossover, componentwise deterministic reflection into `[0,1]`, e.g. `r(u) = 1 - abs((u mod 2) - 1)`, followed by physical decoding and the shared clip/half-up integer canonicalizer. Record per-coordinate boundary proposals/repairs. This intentionally differs from L-SHADE parent-midpoint repair and is part of the complete-package comparison, not an isolated mutation comparison.
5. **Provisional update rule:** canonical, synchronous generations. Freeze the parent population at generation start; generate one trial per target against that same parent snapshot, evaluate trial records, then replace a parent iff `GeometryFirstComparator.better(trial, parent)` is true. Exact rank-key ties keep the parent. No scalar fitness is used for survivor selection, incumbent, final selection, or trace.
6. The 3,862 post-initialization unique-FE remainder is not divisible by population size 234: complete full generations as possible, then stop exactly at 4,096 in a deterministic final partial generation (118 new unique evaluations if no earlier duplicates/stalls). Freeze the ordered target traversal, donor sampling/crossover draw order, and when survivor decisions are committed. Only targets whose unique trial has been completed participate in final partial-generation replacement; untouched parents remain unchanged. The full evaluated history, not just the final population, supplies the top-16. Store the pending generation snapshot, ordered targets/cursor, accumulated trial records, and any partially completed retry state so a checkpoint/resume in the middle of a generation reproduces uninterrupted proposal/evaluation order exactly.
7. Duplicate canonical proposals are raw proposals/cache hits, not unique FEs. The same target must regenerate its full DE proposal (donors, forced coordinate, crossover mask and resulting trial) against the same frozen parent generation after a duplicate; duplicate attempts never trigger an evaluator call or artificial sentinel. Freeze numeric per-target and no-progress retry/stall limits for both arms. On reaching a limit, report `BUDGET_STALLED`/incomplete (or formally certified exhaustion) rather than claiming 4,096 FEs or silently injecting an unrelated random fallback. The limits and exact accounting remain unresolved.

The synchronous partial-generation rule and checkpoint state above are explicit candidate choices for review, not frozen decisions. A serial asynchronous update might simplify exact checkpointing but would change standard generational DE semantics; it should not be substituted without stating and reviewing that algorithmic distinction.

### Evaluation identity, budget, comparator, and trace contract

- A cell-local cache is keyed by the complete immutable search-evaluation identity (study/config/source fingerprint, topology, optimizer, seed, search-grid identity, canonicalizer/comparator versions) plus the canonical physical design key. Never share search results across optimizer, seed, grid, topology, or config identities. Dense-validation results are a separately identified validation phase and are not cache hits against the search grid.
- Count separately: raw initialization sampler draws/rejection reasons; accepted initialization candidates; raw optimizer proposal attempts; duplicate/cached proposals; unique search FEs; geometry rejections; physics attempts/failures; COM calls if any later authorized execution; validation evaluations; proposal retry/stall counters; elapsed time. Define the counter identities before implementation and assert their reconciliation.
- A unique search FE is charged exactly once on the first evaluation of a canonical design in that cell, whether the geometry gate rejects it, physics evaluation fails, or it produces an ordinary record. Geometry-rejected search proposals and physics failures therefore consume the 4,096 unique-FE budget; initializer screening rejections are separately counted and not search FEs. A repeated canonical key consumes zero new FEs.
- Stop before any new search evaluator call when the per-cell counter equals 4,096. Never overrun a target, call an evaluator for a sentinel value, or count repeats as new FEs. If unique space/search is exhausted or duplicate stall occurs before the cap, mark the cell incomplete with exact counters; do not misreport it as a 4,096-FE completed comparison.
- Use `GeometryFirstComparator.rank_key` unchanged for parent/trial survivor choice, incumbent and best-so-far trace, historical search ranking, and final validated selection. Preserve stable evaluation-order tie-breaking for equal rank keys. Do not scalarize or change the lexicographic rank order. Synthetic fixtures must include violation magnitudes above 1,000 to catch base-1000 ordering errors.
- Retain the best 16 distinct canonical designs from the **entire unique search history** using search-grid comparator rank and stable evaluation order, not merely the terminal population. Independently validate all 16 on the common 9,113-point grid under identical physical/evaluation semantics. Select/report the final best-found validated candidate using the same comparator on validation records; also report all 16, their search and validation ranks, all named metrics/violations, and the search-selected incumbent separately. Validation calls and wall time are reported separately from the 4,096 search-FE budget.
- Trace every unique search FE (including initialization and trials awaiting synchronous generation commit) with canonical key/reference, rank key, **search-grid** best-so-far rank, immutable first-evaluation ordinal, unique-FE index, raw proposal/counter state, and search time-to-quality data. Search traces must not imply that dense-validation best-so-far is known during optimization; the 9,113-point validation is terminal/separate. Best-so-far search rank on the fixed 1,001-point grid must be nonincreasing. Freeze the exact tie policy for incumbent identity, top-16 and validation ranking; retain parent on equal trial rank and use immutable first-evaluation ordinal for history ties. Use a lossless/versioned canonical-key encoding and an explicit non-finite rank-key encoding (not ambiguous JSON `null`). Validate strict candidate record schemas before ranking, and freeze the search grid for the whole cell (no grid exchange/refresh or bound expansion).
- Freeze the counter identities, sampler/proposal/duplicate/fallback/geometry/physics/validation counts and timing boundaries. Report initialization sampling, initialization evaluation, search evaluation, optimizer/proposal, checkpoint I/O, and terminal dense-validation time separately. Freeze single-cell execution resources and deterministic cell order before any later run; report active computation time separately from end-to-end wall time including downtime. The two methods are compared as complete specified algorithm packages; their update mode, boundary repair, genotype representation, L-SHADE fallback, and population schedule intentionally differ and must not be described as isolating mutation/adaptation alone.

### RNG, seed, checkpoint, and L-SHADE horizon

- Use fresh, explicitly frozen seed integers for the three matched pairs. Derive separate deterministic streams for common population sampling and each optimizer's evolution from stable, documented identifiers (not Python's randomized `hash()`). Initial population stream is independent of optimizer. Record RNG algorithm/library versions, seeds/derivation, state, and the exact initial-population hash.
- For both arms checkpoint at a predeclared unique-FE lattice (candidate: initialization at 234, each 512-FE boundary, and terminal 4,096), plus failure-safe checkpoints. Serialize all state needed for exact same-environment deterministic continuation. For controlled synchronous DE this includes the frozen parent generation, ordered targets/cursor, completed but uncommitted trials, retry state, all candidate/cache/history indices, counters, RNG state, rank/trace state, and elapsed active-time accumulator. L-SHADE must persist population, archive, adaptive memories, fallback counters, cache/history, comparator/config identity, horizon, traces/counters, and RNG state. Current L-SHADE state support does not yet prove this full contract: it needs fail-closed validation of every required identity field (including missing values), lossless infinity/key serialization, and trajectory-neutral per-FE traces.
- Resume must fail closed on any source/config/protocol/topology/optimizer/seed/budget/grid/canonicalizer/comparator/initial-population/environment identity mismatch. Checkpoint/restart must not change the proposal sequence, accepted population, rank history, unique-FE trace, or final top-16 on the same pinned environment. Record downtime separately from active optimizer time; elapsed wall time including downtime is not a deterministic trajectory quantity.
- Construct L-SHADE cold with `population_schedule_terminal_budget = 4,096` from the start. Its schedule must use this immutable terminal horizon for every checkpoint. A 4,096-FE checkpoint cut from a 96,000-FE-horizon trajectory is not a valid independent pilot arm. The L-SHADE arm also receives/evaluates the same 234-member initial population and has the same exact 4,096 unique-FE cap.

## Sol design decision — 2026-10-21

**Observed route:** requested `openai/gpt-6.1-sol`; saved session records provider `openai`, model `gpt-6.1-sol`, and `thinkingLevel=medium`; child completed normally and its session was saved locally (session ID `01a159d5-d230-71ea-818e-f9b077168d83`). Recorded effort is a runtime setting, not proof of internal reasoning effort. The raw session log and local filesystem path are not part of the review package.

### `SOL_DECISION`

`REQUEST_Q0_REVISIONS`. The comparison is defensible as an exploratory matched-budget comparison of two specified algorithm packages, but the protocol is not sufficiently frozen for Q1. Q1 implementation may begin only after the requested revisions are resolved, the bounded design disposition is recorded, and Q0 has independent GitHub review and user acceptance/implementation permission. This is not Q0 closeout and authorizes no implementation now, COM evaluation, pilot, validation experiment, or production run.

### `CRITICAL_FINDINGS`

1. A new controlled DE backend is justified; neither `ScipyDELegacyBackend` nor `FixedDEReferenceBackend` is eligible as-is.
2. L-SHADE differs from the proposed DE in update timing, latent/pre-canonical genotype storage, parent-midpoint boundary repair, and duplicate fallback. Comparing them is legitimate but evaluates **complete algorithm packages**, not isolated mutation/adaptation. These differences and the L-SHADE fallback must be disclosed and counted.
3. L-SHADE has no default duplicate-streak termination certificate. A mixed-space retry/fallback can fail to add a unique FE while the budget loop continues; both arms need an explicit bounded no-progress/incomplete-status contract.
4. Existing L-SHADE state support does not establish the proposed exact replay contract: initialization and retry loops, improvement-only trace, incomplete identity validation, and non-finite JSON conversion require qualification/extension.
5. 4,096 FEs × 3 seeds is suitable only for exploratory short-budget evidence. Fixed-population DE gets 16 complete post-initialization generations plus a partial generation (without duplicates), while L-SHADE follows its own shrinking short-horizon schedule. No convergence or broad superiority claim is justified.

### `REQUIRED_CHANGES`

Before Q1, consolidate and freeze:

1. The full L-SHADE reference configuration/estimand, including min population, adaptation memories/batch, archive/p-best, schedule rounding, target traversal, latent-genotype and boundary behavior, duplicate retry/fallback and its counters. Preserve the audited algorithm unless a separately reviewed change is required. Explicitly call the study a comparison of complete algorithm packages.
2. Controlled DE's fixed 234 population; donor sampling/ordering; crossover and RNG draw order; retry behavior; when pending survivors are committed; and no adaptation, archive, shrink, polish or alternate fallback.
3. The complete shared initializer distribution/seed namespace/order/canonical representation/hash/attempt cap, pre-evaluation snapshot, partial initialization failure/resume and no seed substitution. The existing `independent_uniform_rejection_v1` is a candidate, not yet accepted.
4. Numeric per-target retry and no-progress limits for both arms; distinct statuses for initialization failure, `BUDGET_STALLED`, infrastructure/runtime interruption, modeled physics failure and formally certified search exhaustion. Modeled failures are charged/cached; infrastructure exceptions must not be silently rewritten as scientific failures and require transactional recovery semantics.
5. Strict record-schema validation; stable first-evaluation ordinal tie semantics for incumbent, history, shortlist and validation; parent-on-equal; lossless canonical key and infinity encoding; fail-closed validation of missing as well as mismatched checkpoint identity. Freeze the search grid for each cell.
6. Trace one search-grid best-so-far event per unique FE, including initial and pending synchronous trials; distinguish this from terminal dense validation. Freeze timing boundaries, initialization/checkpoint overhead treatment, serial resources, deterministic cell order and counter equations.

### `APPROVED_DESIGN_CONSTRAINTS`

Sol explicitly endorsed the following **as design choices within a revised proposal only**, not as a frozen experiment or execution authorization:

- Independent `P_D`/`D_P` searches over unchanged 13-variable modeled bounds/constraints.
- 4,096 unique canonical search FEs per cell inclusive of 234 initialization FEs; three fresh matched seed pairs per topology; 12 cells / 49,152 maximum unique search FEs.
- Same ordered initial population, independently evaluated and charged by each arm, with separate caches.
- New controlled DE/rand/1/bin with fixed population 234, `F=0.5`, `CR=0.9`, componentwise reflection, canonical phenotype remapping, synchronous parent snapshots; no shrinking, adaptation, archive, polish or alternate proposal fallback.
- Exact-budget terminal partial generation (118 trials after 16 full post-initialization generations absent duplicates/stalls).
- Geometry rejects and modeled physics failures count as unique search FEs; duplicate proposals do not.
- Unmodified comparator tuple ordering, strict replacement, historical top-16 and independent common-grid terminal validation.
- Cold L-SHADE start with immutable 4,096 terminal schedule horizon.
- Checkpoint lattice at initialization, each 512-FE boundary and terminal, plus safe bounded-retry/failure checkpoints.

Actual seed values, sampler and attempt cap, retry/stall limits, L-SHADE resolved settings and complete resource/protocol identities remain unresolved. The above are not accepted as a complete Q0 freeze.

### `Q1_QUALIFICATION_REQUIREMENTS` — Sol additions

In addition to the tests below, qualification must include golden tests for the frozen DE proposal/retry/update order; bounded L-SHADE fallback/no-progress; exact initialization representation and interrupted initialization recovery; a checkpoint with synchronous trials evaluated but not committed; first-evaluation tie cases; infinity-preserving rank/cache/trace round trips and malformed-record rejection; missing and mismatched identity rejection; deterministic replay at initialization, duplicate retries, final partial generation and failure boundaries excluding nondeterministic timestamps; proof that tracing/checkpoint observation does not alter either RNG trajectory; and synthetic-only complete/incomplete cell integration with no COM invocation.

### `RESIDUAL_RISKS`

The 3 matched seeds provide weak uncertainty estimates; equal unique-FE budgets do not equalize physics calls, generations, fallback exposure or compute cost; geometry-valid initialization conditions the starting distribution; boundary/genotype differences may matter materially; terminal top-16 validation cannot prove full-history dense-grid optimality; the 4,096-horizon L-SHADE run is not a continuation of historical 96k; and all failed, immature or inconsistent results must remain unresolved without automatic extension or constraint/topology change.

### Q0 revision and re-review condition

This task uses its single authorized Sol reviewer. No second Sol review is being started here. Q0 remains **OPEN / REVISIONS REQUIRED**. A future Q0 revision must resolve the list above in both this packet and the plan draft, then receive a separate bounded Sol re-review, independent GitHub review, and user acceptance before Q1 implementation permission can be considered. Q1 remains **NOT STARTED**; no experiment/run authorization follows from any of those design judgments alone.

## Q1 synthetic/unit qualification requirements (design only; do not execute now)

Before any later Q1 implementation is used for a COM run, design and pass a focused, deterministic, COM-free qualification covering at least:

1. **DE operator:** verify exact rand/1 donor distinctness/exclusion, mutation equation, binomial crossover and forced coordinate, fixed F/CR, boundary reflection, physical mapping, canonical phenotype remapping, integer half-up behavior, and same-seed determinism.
2. **Comparator:** fixtures for geometry-valid evaluated feasible/infeasible, physics failures, and geometry rejects; prove exact geometry-first/feasibility-first lexicographic ordering, stable tie rule, and violation values above 1,000. No scalarization path may influence ordering.
3. **Initialization parity:** exact same per-topology/seed ordered 234 canonical members and hash for both arms; unique and geometry-valid; independent initialization seed derivation; sampler draw/duplicate/geometry rejection accounting; arm-local evaluation/cache isolation.
4. **Accounting:** initial 234 charged per arm; initialization-screen rejects excluded but separately counted; unique geometry rejects and physics failures charged; repeated canonical proposals/cache hits uncharged; proposal/cache/counter identities reconcile; no evaluator call after 4,096; exact full and partial final-generation behavior; duplicate-stall/exhaustion reports incomplete without a false pass.
5. **L-SHADE horizon:** explicitly instantiated 4,096 terminal schedule; assert the population schedule and fail-closed rejection of 96,000-horizon state/config as a pilot continuation.
6. **History and dense validation:** stable historical top-16 over all unique search evaluations; distinct canonical keys; validate exactly those 16 on the 9,113-point grid; preserve search-vs-validation rank distinction and select from validated results using the same comparator.
7. **Checkpoint/replay:** uninterrupted versus checkpoint/resume at initialization, ordinary checkpoint lattice points, a mid-generation DE state, duplicate retries, the final partial generation, and terminal budget. Assert exact proposal vectors/order, RNG/population/cache/rank/counter state, trace and top-16 on the pinned environment; reject identity mismatch.
8. **Trace/resource accounting:** nonincreasing fixed-grid best-so-far rank, unique-FE-indexed quality and time curves, raw proposal/cache/duplicate/geometry/physics counters, active time vs resume downtime, and separate validation time/calls.
9. **Protocol matrix:** synthetic-only 12-cell contract with exactly two topologies × two optimizers × three matched seeds, 234 shared initial members per matched pair, exact per-cell 4,096 FE or explicit incomplete status, and complete metadata. Prove the synthetic execution path imports/uses no COM physics/provider or optimizer-production orchestration.
10. **Test-data design:** include known-feasible and infeasible continuous/mixed-integer constrained synthetic landscapes to check broad correctness, not to claim one optimizer is superior or infer physical filter quality.
11. **Sol-specific gates:** deterministic DE proposal/retry/update golden fixtures; L-SHADE fallback/no-progress behavior; partial initialization and recovery; pending synchronous-trial checkpoint; first-evaluation ties; strict record-schema and non-finite/key roundtrip checks; missing/mismatched checkpoint identity rejection; replay at initialization/retry/final partial/failure boundaries; verify trace/checkpoint observation does not perturb RNG trajectories; and synthetic complete/incomplete-cell integration with no COM imports or calls.

No Q1 implementation, synthetic qualification code, or tests have been run or are authorized in this task.

## Comparison interpretation and gates

The proposed 4,096 × 3-seed comparison is a bounded exploratory **search pilot**. It can characterize short-budget quality/time under this frozen 13-DOF problem; it cannot establish feasibility impossibility, convergence, global optimality, or general optimizer superiority. Report paired per-seed outcomes, spread/uncertainty, best/median violation metrics, named RF metrics, feasibility, time-to-target where observed, and whether each trajectory remains immature. If incomplete, incomparable, or still improving, label the outcome unresolved and return to the user with a next-step proposal rather than automatically extending budget.

No execution is authorized by the Stage 5A-1 closeout, this packet, Sol's judgment, or a later Q0 GitHub review alone. A later run requires Q0 GitHub independent review and user acceptance; Q1 implementation plus synthetic/unit qualification; frozen exact seeds/config/bounds/grid/budget/checkpoint/trace/resource cap; approved preflight; external persistent run storage outside Git worktrees; and separate explicit user production authorization through the qualified orchestration workflow. Stage 4C artifacts remain immutable. No COM calculations, optimizer run, Q1 implementation, tests, or DMS acceleration are in scope now.

## Sol response format required

Return exactly these top-level headings and include concise, specific rationale beneath each:

- `SOL_DECISION`: choose exactly one: `APPROVE_Q0_PROTOCOL`, `REQUEST_Q0_REVISIONS`, `BLOCK_Q0`
- `CRITICAL_FINDINGS`
- `REQUIRED_CHANGES`
- `APPROVED_DESIGN_CONSTRAINTS`
- `Q1_QUALIFICATION_REQUIREMENTS`
- `RESIDUAL_RISKS`

State explicitly whether Q1 implementation may begin after the listed Q0/user gates (implementation only; no COM or production authorization). If conditional, preserve the conditions; do not state unconditional approval. Distinguish Q0 design disposition from user acceptance and all experiment/run authorization.
