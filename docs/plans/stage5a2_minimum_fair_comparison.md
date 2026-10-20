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
| Methods | `L-SHADE` and a **qualified** controlled `Legacy-DE` or comparable DE baseline, both using identical geometry gate, canonical cache policy and comparator | Two-arm generic-method feasibility pilot; no SAW-guided starts yet |
| Problem dimensions | 13 DOF per topology; all variables and bounds unchanged | Must remain a full-space comparison |
| Seeds | **Three new independent seeds**, matched between methods within topology; freeze actual integers before execution | Paired variance control; this small n is exploratory |
| Initialization | Same topology/seed initial physical candidate population if both methods can consume it without algorithm-specific manipulation. Record and account for any initialization policy mismatch; fail comparison gate if unequal initial information cannot be justified | Isolate search algorithm effect |
| Unique decoded budget | **4,096 per method/topology/seed**, from a 4,096 **terminal horizon at initialization** | 2 methods × 2 topologies × 3 seeds = 12 cells / **49,152 unique evaluations** |
| Dense validation | Common-grid validation of each cell's 16 best historical search candidates at terminal budget; report comparator-selected candidate and all violation metrics | Avoid search-grid-only ranking |
| Quality | Feasibility, maximum/summed normalized violations, worst IL, ripple, matching, named stopbands; per-seed paired ranks and differences | Same lexicographic feasibility-first rule as Stage 4C |
| Compute | Unique evaluations; raw proposal/cache-hit/geometry/physics counters; CPU time, wall time, RSS peak, worker/BLAS setting, best-so-far quality versus unique eval **and** elapsed time | Quality/time rather than budget-only comparison |
| Storage | New external persistent run, immutable frozen input/source/config/fingerprint, separate compact review export | Must never resume or modify Stage 4C raw data |

**Cost feasibility only:** 49,152 evaluations × historical 0.05856 s/search evaluation ≈ **0.80 aggregate search-evaluator hours** (plus optimizer/init/validation/I/O overhead). This is **not** a predicted wall-clock duration or authorization to execute. The 4k terminal L-SHADE schedule must be constructed afresh; taking a 4k checkpoint from a 96k terminal-horizon run is invalid as an independent 4k comparator.

## Pre-execution engineering qualification

**Stage 5A-2 Q0 reviewer routing:** use the [Pi Sol review procedure](../guides/pi_sol_review_routing.md).
The pinned design-judgment request is `openai/gpt-6.1-sol` with
`thinking=medium`, using Pi's current `openai` provider (which supports
ChatGPT OAuth). Earlier child runs established an effective `openai` /
`gpt-6.1-sol` / recorded `medium` execution route, but they had incorrectly
requested the legacy `openai-codex` provider; perform a short exact-request
recheck and keep effective credential provenance separate from stored
`openai: oauth` metadata. Connectivity does **not** constitute Q0 design
approval. Do not freeze Q0 or start Q1 on its basis alone. Log a separate
bounded Sol judgment and respect normal user authorization gates.

Before any empirical optimizer run, perform docs-first review and synthetic/unit qualification that both arms: (a) charge only new canonical designs to the unique budget, (b) use the identical feasibility/geometry comparator and fail-closed candidate schema, (c) respect exact integer canonicalization, DMS/resonator bounds and dense-grid identities, (d) use auditable initialization and final 16 candidate history, (e) stop at exact 4,096 unique designs or report justified exhaustion, and (f) record time/evaluation traces and checkpoint state without altering existing Stage 4C evidence.

Where the Legacy-DE implementation cannot satisfy a condition without substantial new code, **stop and report the limitation** rather than quietly changing the problem or replacing it with a different comparison. Unit tests/synthetic objective checks are permitted without initiating COM search or production work.

## Gating and interpretation

A launch request must show the exact frozen seeds, config diff, two-arm implementation/source SHA, expected I/O locations, an upper budget and resource cap, dense-grid parity tests, and an abort protocol. Only after explicit user approval should any optimizer be executed.

**Pass of a pilot** means complete/validated and comparable evidence for 12 cells, not superiority or scientific convergence. With three seeds, report estimates, spread and uncertainty; do not promote a method from a single winning run or overinterpret short-budget statistics. If both methods are immature at 4k, retain `UNRESOLVED` and use the results to choose the *next* informative budget/algorithm/local-polish comparison for separate approval. A controlled local-polish arm and SAW-guided starts belong to later Stage 5A-2/4/5 qualification, not to this first two-arm pilot.

## Explicit non-goals

No bound widening, no changed COM constants, no topology/geometry pruning, no automatic 96k/192k/256k budget extension, no forced-feasible objective or scalar penalty substitution, no user-facing fixed-design Smith map, and no modification of the historical Stage 4C `STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED` disposition.
