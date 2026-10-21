# R1 Q1 contract disposition — proposal for owner review

**Scope:** Documentary inventory requested by Issue #59. This is a proposal,
not an amendment to Q0, Q1, a gate, or experiment conditions. The sole formal
gate list remains
[`stage5a2_q1_qualification_matrix.md`](stage5a2_q1_qualification_matrix.md).

**Current status (2026-10-22):** Q0 `CLOSED / ACCEPTED`; Q1-A
`WORK_UNIT_READY / CLOSED`; Q1-B/C/D/E `NOT AUTHORIZED / NOT STARTED`. None of
Q1-01…Q1-23 is `FULL_PASS`. Partial Q1-A component evidence is not a gate
pass. No Q1 integration, COM/physics evaluation, real comparison, or production
run is authorized here.

## 1. Classification and open owner decision

The categories below mean:

- **`PRESERVE_SCIENTIFIC_INVARIANT`** — preserve the scientific comparison
  condition or the software invariant needed to reproduce it. It may not be
  changed by migration/refactor.
- **`PRESERVE_HISTORICAL_EVIDENCE`** — retain the cited source identity,
  tests/fixtures, review decisions, and unpassed/pending disposition as
  evidence; do not relabel evidence or recompute it under a new source as if
  historical.
- **`REPLACE_IMPLEMENTATION`** — if later authorized, responsibility may move
  to target modules and be implemented without obsolete stage-specific
  compatibility paths. New code must meet the unchanged contract and be
  requalified under its actual pinned fingerprint.
- **`REQUIRES_OWNER_DECISION`** — do not act until the user decides. This
  proposal does not decide whether the Q1 comparison is still wanted after
  reconstruction, whether to requalify Q1-A under the target architecture, or
  whether its stage-scoped implementation may be retired.

**Proposed invariant:** preserve every Q0/Q1 scientific and comparison term,
all 23 gate definitions and gate IDs, and their unpassed status. Preserve Q1-A
source/evidence. For future architecture work, prefer replacing the
stage-specific implementation with behaviorally equivalent responsibility in
the target architecture, not retaining a shadow package solely for runtime
compatibility. **Owner decision required before R4 or any Q1-B/C/D/E work:**
confirm whether to continue Q1 as defined, and if yes, define an authorized
requalification plan for affected Q1-A contracts under the new architecture.
Until then, retain the current implementation and evidence; do not start Q1-B.

There is no proposal to change 234-member initialization, the 4,096 unique-FE
ceiling, three matched roots, PCG64 identity/replay, `GeometryFirstComparator`,
validation rules, failure taxonomy, or Q1-01…23 acceptance. Gate merging,
deleting, renumbering, or scientific-semantic alteration requires a separate
owner-approved amendment before implementation.

## 2. Authoritative frozen records and SHA-256/source identities

| Record/artifact | Identity | What it establishes / does not establish |
|---|---|---|
| Q0-R3 approved protocol | PR #50 merge/source commit `9427b404d302932b27f50d31919bb3fb95fcfcd4` | Design contract and Sol/documentary review record; not software correctness or experiment authorization. |
| Q0 formal closeout | [`docs/history/stage5a2_q0_closeout_20261021.md`](../history/stage5a2_q0_closeout_20261021.md) | User accepted Q0 on 2026-10-21; Q1 still required separate authorization. |
| Sole Q1 matrix | [`stage5a2_q1_qualification_matrix.md`](stage5a2_q1_qualification_matrix.md) | Formal gate requirements Q1-01…Q1-23; all unpassed. |
| Q1 execution plan | [`stage5a2_q1_execution_plan.md`](stage5a2_q1_execution_plan.md) | Work-unit ownership/dependencies and stop conditions; not an additional gate list. |
| Q1-A pre-extraction source | commit `f32b8f8dac928f21c567b34593b1ed227a4c9c9e`; `src/sawopt/problem/hybrid.py` SHA-256 `b892be9360174d6701f3db0dc8ba49c82d1b75d8b3c1886dbbba998bd3242462` | Legacy canonicalizer characterization source; not a Stage 4A/4B/4C execution SHA. |
| Q1-A characterization corpus | `tests/fixtures/stage5a2/canonicalization_legacy_golden.json`, SHA-256 `3763c5746f4bf800a54f310aeeb94f493520fc0962505b1eed85d3c32b589aa2` | 92 compatibility cases; local parity evidence only. |
| Q0 design-space fixture | `tests/fixtures/stage5a2/q0_design_space_contract.json`, SHA-256 `c7902e30f7becf2e2c0aa280d8f51c25f31f524cbf06c3516252bf47b2faddc9` | Frozen active dimensions/bounds/integer-coordinate/topology records for four design spaces. |
| Q1-A seed fixture | `tests/fixtures/stage5a2/seed_derivation_golden.json`, SHA-256 `1a824a07a6e7d652f47388e6604889e612c2809704b7681df713bb9ec8c7087a` | Golden seed derivation cases; not proof of full optimizer RNG replay. |
| Q1-A reviewed merge | PR #54 merge `03d673052c7570d86b78b43849f649758bb7d3f4`; reviewed source head `ba0d13f69a34422669fee9dd88819dfbab45d392`; post-reviewer-patch tests used `03b9a5495111a1f933f542682f76b5ec9bad4e53` | Q1-A work unit accepted as `WORK_UNIT_READY`; the official gates remain unpassed. |
| Q1-A report | [`reports/stage5a2_q1a_common_foundation_20261021.md`](../../reports/stage5a2_q1a_common_foundation_20261021.md) | 65 focused tests, 92/92 public and leaf characterization, imports checked; actual B/C evaluator paths absent and dispatch rejects. |
| Stage 4B frozen production | `c44798266067fa4b8b7d3b2873a798b7a1600ae8` | 20/20 completed; 0 feasible; no unique topology. |
| Stage 4C frozen production | `65e1815db1cc18d74ff0dcee20ffd5e9098709df` | 10/10 completed; 0 feasible; immature/still improving; topology unresolved. |
| Stage 5A-1 audit implementation | `c0ab7cc5ad93569c1828f812cf90655e89c5cc8f` | Read-only saved-evidence audit; not a replay of every historical proposal or a Q1 gate pass. |
| R0 preflight/preservation | Source main SHA `a4b3807d399cc78b10c280d41ee8cea476ade329`; report [`r0_preflight_inventory_20261022.md`](../../reports/restructure/r0_preflight_inventory_20261022.md); external inventory manifest SHA-256 `d0bfc7189d0c8f35aa46875b4f7de4d64727ef6b570e2a157b8da900898d9c7d` | 12 run trees / 5 related manifests copied and destination-verified. Physical off-device redundancy unverified; missing payload impact unclassified (#58). The manifest/raw files are external and are not in Git. |

The 2026-10-22 R0 inventory notes that legacy Stage 4A records do not
establish a common source SHA. Do not assign a later source commit to them.
Stage 4B/4C and Q1-A execution identities above are not interchangeable.

## 3. Frozen cross-cutting Q0 invariants

These terms remain unchanged, including the Q0-R3 initializer exception:

- Exact 234-member ordered common initialization using
  `independent_uniform_rejection_lshade_image_v2`. Preserve raw/provisional,
  L-SHADE genotype/reconstruction, sealed actual canonical physical vector/key,
  and DE direct physical input as separate representations. Seal actual
  post-L-SHADE-transform evaluator inputs; both complete 234-member pure
  preflights and certificates must match the seal bitwise, by key and order,
  before either arm's first FE. Duplicate before geometry; no fitness-based
  resampling.
- Exactly 4,096 unique search FEs per arm/cell, including 234 initial FEs;
  validation is separate. Sampler rejections and duplicate/cache hits are
  uncharged. Search geometry rejects, typed modeled failures, and invalid
  returned records retain distinct required status/accounting. No dispatch
  after the budget.
- Explicit PCG64, versioned `stage5a2_rng_call_v1`, complete typed request and
  output, full pre/post state, durable `STARTED`/`COMMITTED`, committed-result
  replay without redraw, and pending-call regeneration only from verified
  pre-state. L-SHADE replay begins from complete pre-step state; no partial
  local-state inference.
- Existing `GeometryFirstComparator`, exact tuple semantics, parent-on-tie,
  stable ordinal/tie behavior, separate private arm caches, top-16 common-grid
  validation, Q0 censored comparison rules, and all planned/incomplete cells
  remain as specified in Q0/Q1 sources.
- Synthetic-only Q1 means deterministic software fixtures with no COM/provider/
  network physics and no production orchestration. Q1 does not qualify physical
  determinism, optimizer convergence, feasibility, or production readiness.

## 4. Q1-01…Q1-23 disposition proposal

Every row is presently **UNPASSED**. “Q1-A component evidence” is not an
official gate pass. The specific pass clauses remain in the sole formal Q1
matrix; the summaries here do not replace it.

| Gate | Present status/evidence | Classification | Proposed future responsibility if Q1 is owner-authorized |
|---|---|---|---|
| Q1-01 L-SHADE resolved configuration | Unpassed; no Q1-C implementation. | `PRESERVE_SCIENTIFIC_INVARIANT`; `PRESERVE_HISTORICAL_EVIDENCE`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-C verifies the frozen configuration and cold 4,096 horizon under target `optimization/`; requalify on actual source/config/environment fingerprint. |
| Q1-02 Controlled DE golden operator | Unpassed; Q1-B not started. | `PRESERVE_SCIENTIFIC_INVARIANT`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-B implements the dedicated controlled `DE/rand/1/bin` and fixed-RNG golden tests; no legacy backend relabeling. |
| Q1-03 Seed derivation/RNG draws | Q1-A codec/seed components have local evidence; full proposal-stream parity unpassed and pending B/C/D. | `PRESERVE_SCIENTIFIC_INVARIANT`; `PRESERVE_HISTORICAL_EVIDENCE`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-A supplies identity/RNG primitives; B/C use them; D fault-injects; final gate closure only under a shared pinned fingerprint. |
| Q1-04 Shared initial population | Q1-A synthetic seal/preflight components exist; actual optimizer evaluator paths are absent; gate unpassed/pending B/C. | `PRESERVE_SCIENTIFIC_INVARIANT`; `PRESERVE_HISTORICAL_EVIDENCE`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-A/B/C prove both actual 234-member paths and evaluator-boundary identity before FEs. Do not use current synthetic certificates as authority. |
| Q1-05 Partial initialization/recovery | Q1-A genesis component evidence exists; arm initialization/recovery unpassed/pending B/C/D. | `PRESERVE_SCIENTIFIC_INVARIANT`; `PRESERVE_HISTORICAL_EVIDENCE`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-A/D validate G0–G4 and recovery against the real future Q1-A/B/C interfaces; no new gate. |
| Q1-06 Canonical duplicate/cache | Unpassed; optimizer arms and integrated accounting not started. | `PRESERVE_SCIENTIFIC_INVARIANT`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-B plus Q1-C/D establish private cache, duplicate accounting, atomic retry and replay. |
| Q1-07 Unique-FE ceiling/reconciliation | Unpassed; frozen 4,096 ceiling retained. | `PRESERVE_SCIENTIFIC_INVARIANT`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-B/C supply arm transitions; Q1-D reconciles every FE class and boundary. |
| Q1-08 DE synchronous survivor semantics | Unpassed; Q1-B not started. | `PRESERVE_SCIENTIFIC_INVARIANT`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-B implements frozen-parent generation, target order, strict replacement and tie behavior. |
| Q1-09 DE final partial generation | Unpassed; Q1-B not started. | `PRESERVE_SCIENTIFIC_INVARIANT`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-B proves 16 full post-initialization generations plus 118 final trials at 4,096 FEs. |
| Q1-10 DE retry/stall boundaries | Unpassed; Q1-B not started. | `PRESERVE_SCIENTIFIC_INVARIANT`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-B proves exact proposal/watchdog boundaries and no extra draw/evaluation. |
| Q1-11 L-SHADE fallback/watchdog | Unpassed; Q1-C not started. | `PRESERVE_SCIENTIFIC_INVARIANT`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-C instruments the existing search path without changing arithmetic/control flow; Q1-D qualifies restart. |
| Q1-12 Failure taxonomy | Unpassed; no integrated transition/recovery implementation. | `PRESERVE_SCIENTIFIC_INVARIANT`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-D checks distinct geometry, modeled, infrastructure, invalid, initialization, exhaustion, and corruption outcomes. |
| Q1-13 Candidate schema/comparator | Existing comparator is historical code; Q1 strict-schema gate unpassed. | `PRESERVE_SCIENTIFIC_INVARIANT`; `PRESERVE_HISTORICAL_EVIDENCE`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-B/D validate strict synthetic schema while reusing frozen comparator semantics unchanged. |
| Q1-14 Lossless serialization | Q1-A codecs have local evidence; live L-SHADE state component and full gate unpassed/pending C/final qualification. | `PRESERVE_SCIENTIFIC_INVARIANT`; `PRESERVE_HISTORICAL_EVIDENCE`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-A/C implement typed codecs and live L-SHADE state; Q1-D validates crash/replay. |
| Q1-15 Identity/checkpoint lifecycle | Q1-A identity components have local evidence; full hydration/recovery gate unpassed/pending B/C/D. | `PRESERVE_SCIENTIFIC_INVARIANT`; `PRESERVE_HISTORICAL_EVIDENCE`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-A/B/C/D validate unchanged identity lifecycle, attachments, exact source/config, and recovery. |
| Q1-16 Transaction transition/recovery | Q1-A primitives only; cross-optimizer matrix unpassed/pending D. | `PRESERVE_SCIENTIFIC_INVARIANT`; `PRESERVE_HISTORICAL_EVIDENCE`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-D integrates A/B/C transactions and fault matrix. Do not treat A primitives as a full pass. |
| Q1-17 DE checkpoint/replay | Unpassed; Q1-B/D not started. | `PRESERVE_SCIENTIFIC_INVARIANT`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-B owns DE restart semantics; Q1-D provides crash harness. |
| Q1-18 L-SHADE checkpoint/replay | Unpassed; Q1-C/D not started. | `PRESERVE_SCIENTIFIC_INVARIANT`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-C owns L-SHADE state replay; Q1-D provides crash harness. |
| Q1-19 Trace/replay comparison | Unpassed; Q1-D not started. | `PRESERVE_SCIENTIFIC_INVARIANT`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-D validates trace integrity and separates scientific trajectory from operational retry/time. |
| Q1-20 Dense finalist validation | Unpassed; Q1-E not started. | `PRESERVE_SCIENTIFIC_INVARIANT`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-E independently validates full-history top 16 on common grid, outside search FE budget. |
| Q1-21 Synthetic 12-cell integration | Unpassed; Q1-E unauthorized. | `PRESERVE_SCIENTIFIC_INVARIANT`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Only after separate Q1 permission, Q1-E runs the frozen synthetic-only 12-cell matrix and no-COM/no-production isolation proof. |
| Q1-22 Timing/resource/storage | Unpassed; no authorized integration. | `PRESERVE_SCIENTIFIC_INVARIANT`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-E records disjoint timing/resource fields and external raw placement for any later authorized synthetic integration. |
| Q1-23 Censored comparison reporting | Unpassed; Q1-E not started. | `PRESERVE_SCIENTIFIC_INVARIANT`; `REPLACE_IMPLEMENTATION`; `REQUIRES_OWNER_DECISION` | Q1-E reproduces exact Q0 censored-pair rules and seven paper-only examples; no invented aggregation or missing-cell omission. |

The repeated `REQUIRES_OWNER_DECISION` is intentional: none of these proposals
authorizes the dependent work unit. It marks the overall continuation and
requalification question as unresolved, not a new gate or an invitation to
change an individual contract.

## 5. R0 → R1 → R2 protection and stop conditions

- Keep Q0/Q1 evidence, Q1-A code, source identities, configs, fixtures, and
  historical reports unchanged through this documentation-only PR.
- R1-A does not modify `src/`, tests, CI, raw data, checkpoints, optimizer
  behavior, COM equations, comparison conditions, schemas, budgets, or gate
  definitions. The known baseline Sol-routing test failure remains separate
  R1-B work.
- R2/R3/R4 may replace code ownership only after R1 review and owner decision;
  equivalent scientific effects require the risk-based regression evidence in
  the roadmap/physics docs.
- If the target architecture cannot preserve a Q0/Q1 invariant as written, stop
  and present a bounded owner decision. Do not silently merge, drop, reinterpret,
  or mark a gate passed. Q1-B/C/D/E remain unauthorized regardless of R1
  acceptance.
