# Stage 5A-2 — minimum controlled generic full-space optimizer comparison (proposal only)

**Status:** DESIGN / NOT AUTHORIZED TO EXECUTE  
**Date:** 2026-10-20  
**Prerequisite:** [Stage 5A-1 read-only closeout](../history/stage5a1_closeout_20261020.md).  
**Decision owner:** user approval required for any optimization, COM/validation experiment, or new production-like run.

## Question

Under one frozen COM/network/spec/bounds problem, does an alternative generic **13-variable mixed continuous/integer full-space optimizer** obtain better common-grid feasibility-first quality or faster time-to-quality than the currently audited L-SHADE reference? The question is not whether 4k evaluations suffice to solve the B28 Rx specification or whether either topology is universally best.

## Protocol proposal (to be frozen before authorization)

| Dimension | Proposed choice | Rationale |
|---|---|---|
| Model/spec/ports | Historical Stage 4C MLIT/T1 at real 50/50 Ω; exactly the unchanged search and 9,113-point common validation grids, geometry bounds and network conventions | Avoid introducing physical/constraint confounders |
| Topologies | `P_D`, `D_P`, independently optimized | No premature topology exclusion |
| Methods | `L-SHADE` and a purpose-built controlled `DE/rand/1/bin` implementation using common evaluation, geometry, canonicalization, cache and comparator semantics. `ScipyDELegacyBackend` and `FixedDEReferenceBackend` are not eligible as-is and must not be relabelled as standard DE. Compare the **complete specified algorithm packages**, explicitly reporting L-SHADE's one-offspring immediate updates, latent normalized genotypes, parent-midpoint repair, shrinking population and duplicate fallback versus the controlled DE contract. | Two-arm generic-method feasibility pilot; no SAW-guided starts yet |
| Problem dimensions | 13 DOF per topology; all variables and bounds unchanged | Must remain a full-space comparison |
| Seeds | **Three new independent seeds**, matched between methods within topology; freeze actual integers before execution | Paired variance control; this small n is exploratory |
| Initialization | Same ordered 234-member canonical, geometry-valid population (`18 × 13`) for each topology/matched seed; algorithm-independent sampler stream; each arm independently evaluates and charges all 234, with no cross-arm result/cache sharing. Candidate sampler is `independent_uniform_rejection_v1` (uniform physical-bounds draws, canonicalization, duplicate and geometry rejection; existing config cap 10,000) with a Stage 5A-2 seed namespace. Sampler distribution, exact seed derivation, representation/hash, attempt cap and partial-failure recovery remain Q0 revision items, not frozen. | Isolate starting information; do not resample or substitute a seed after observing fitness |
| Unique decoded budget | **4,096 per method/topology/seed, inclusive of the 234 initialization FEs**, from a cold 4,096 terminal L-SHADE horizon; 3,862 FEs remain after initialization. Duplicate proposals are not FEs; new canonical geometry rejections and modeled physics failures are FEs. | 2 methods × 2 topologies × 3 seeds = 12 cells / **49,152 unique search FEs maximum** |
| Dense validation | Retain the stable-rank top 16 distinct canonical candidates from each cell's entire unique search history on the 1,001-point search grid; validate all 16 independently on the common 9,113-point grid; report search incumbent separately and select the best validated candidate by the same comparator. Validation evaluations/time are outside the search-FE budget. | Avoid terminal-population-only and search-grid-only ranking |
| Quality | Feasibility, maximum/summed normalized violations, worst IL, ripple, matching, named stopbands; per-seed paired ranks and differences | Same lexicographic feasibility-first rule as Stage 4C |
| Compute | Unique FEs plus raw proposal/cache/duplicate/fallback/sampler/geometry/physics/validation counters; search best-so-far trace per unique FE; CPU, active and end-to-end wall time, initialization/search/checkpoint/validation timing, RSS, serial resources and frozen cell order | Quality/time rather than budget-only comparison; trace search-grid quality separately from terminal dense validation |
| Storage | New external persistent run, immutable frozen input/source/config/fingerprint, separate compact review export | Must never resume or modify Stage 4C raw data |

**Cost feasibility only:** 49,152 evaluations × historical 0.05856 s/search evaluation ≈ **0.80 aggregate search-evaluator hours** (plus optimizer/init/validation/I/O overhead). This is **not** a predicted wall-clock duration or authorization to execute. The 4k terminal L-SHADE schedule must be constructed afresh; taking a 4k checkpoint from a 96k terminal-horizon run is invalid as an independent 4k comparator.

## Q0 Sol design-review disposition — 2026-10-21

**Decision:** `REQUEST_Q0_REVISIONS`. Sol judged the proposed two-arm comparison defensible as an exploratory matched-budget comparison of complete algorithm packages, but not sufficiently frozen for Q1. Q0 remains open; this is not design freeze, user acceptance, Q1 permission, or experiment authorization. See the complete decision and evidence in [`reports/escalation_packets/stage5a2_de_protocol_sol_review_20261021.md`](../../reports/escalation_packets/stage5a2_de_protocol_sol_review_20261021.md).

Sol endorsed as candidate design choices (not as a frozen protocol): controlled DE fixed population 234, fixed `F=0.5` / `CR=0.9`, reflection repair, canonical phenotype remapping, synchronous parent snapshots, no shrink/adaptation/archive/polish/alternate fallback, and exact-budget partial final generation; plus the 4,096-FE / 234-initialization / three-matched-seed envelope and cold L-SHADE 4,096 horizon.

Before Q1, Q0 must still freeze: (1) the exact L-SHADE reference package/config and explicitly count its existing fallback behavior; (2) DE donor order, RNG draw order, target traversal, retry and survivor-commit semantics; (3) exact common initializer stream/distribution/hash/attempt cap and partial failure recovery; (4) bounded duplicate/no-progress limits and distinct modeled-vs-infrastructure-failure handling for both arms; (5) strict record schema, stable first-evaluation tie ordering, lossless canonical/rank encoding and fail-closed identity checks; and (6) search-only per-FE trace semantics, time/accounting boundaries, serial resources and deterministic cell order. The packet records these unresolved items and the additional Q1 qualification conditions.

Current Stage 4C L-SHADE settings to be frozen/reconciled for the pilot are not merely a mutation name: source defaults include min population 4, history size 6, initial `M_F=M_CR=0.5`, p-best fraction 0.20, archive rate 1.0, duplicate retry setting 5, and memory batch size initialized to 234; it uses one-offspring immediate updates, parent-midpoint repair, latent normalized genotypes and a uniform unseen-proposal fallback after repeated duplicates. The protocol must preserve or separately review any change to this audited reference. A comparison is not an isolated test of mutation/adaptation alone.

Q1 implementation remains blocked pending a consolidated Q0 revision and separate Sol re-review, GitHub independent review, and user acceptance/implementation permission. Synthetic qualification and all COM/optimization execution remain unstarted and unauthorized.

## Pre-execution engineering qualification

**Stage 5A-2 Q0 reviewer routing:** use the [Pi Sol review procedure](../guides/pi_sol_review_routing.md).
The pinned design-judgment request is `openai/gpt-6.1-sol` with
`thinking=medium`, using Pi's current `openai` provider (which supports
ChatGPT OAuth). The 2026-10-20 exact-request read-only subagent qualification is **PASS**
for recorded `openai` / `gpt-6.1-sol` / `medium`, a successful child response
and a persisted session. Stored `openai: oauth` and no detected API-key
override are consistent with ChatGPT sign-in; the effective token/billing
path is not independently proven. The prior legacy-`openai-codex` request
mismatch is historical, not a remaining route gate. Connectivity does
**not** constitute Q0 design approval. Do not freeze Q0 or start Q1 on its
basis alone. Log the separate bounded Sol judgment and respect normal user
authorization gates.

Before any empirical optimizer run, perform docs-first review and synthetic/unit qualification that both arms: (a) charge only new canonical designs to the unique budget, (b) use the identical feasibility/geometry comparator and fail-closed candidate schema, (c) respect exact integer canonicalization, DMS/resonator bounds and dense-grid identities, (d) use auditable initialization and final 16 candidate history, (e) stop at exact 4,096 unique designs or report justified exhaustion, and (f) record time/evaluation traces and checkpoint state without altering existing Stage 4C evidence.

Do not use or relabel `ScipyDELegacyBackend` or `FixedDEReferenceBackend` as the controlled DE arm; Q0 calls for a new, dedicated DE/rand/1/bin implementation. If that implementation cannot satisfy the frozen comparator, cache, exact-budget, retry/stall, trace, and checkpoint contracts without changing the problem or L-SHADE reference, **stop and report the limitation** rather than quietly substituting another algorithm or comparison. Unit tests/synthetic objective checks are permitted without initiating COM search or production work.

## Gating and interpretation

A launch request must show the exact frozen seeds, config diff, two-arm implementation/source SHA, expected I/O locations, an upper budget and resource cap, dense-grid parity tests, and an abort protocol. Only after explicit user approval should any optimizer be executed.

**Pass of a pilot** means complete/validated and comparable evidence for 12 cells, not superiority or scientific convergence. With three seeds, report estimates, spread and uncertainty; do not promote a method from a single winning run or overinterpret short-budget statistics. If both methods are immature at 4k, retain `UNRESOLVED` and use the results to choose the *next* informative budget/algorithm/local-polish comparison for separate approval. A controlled local-polish arm and SAW-guided starts belong to later Stage 5A-2/4/5 qualification, not to this first two-arm pilot.

## Explicit non-goals

No bound widening, no changed COM constants, no topology/geometry pruning, no automatic 96k/192k/256k budget extension, no forced-feasible objective or scalar penalty substitution, no user-facing fixed-design Smith map, and no modification of the historical Stage 4C `STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED` disposition.
