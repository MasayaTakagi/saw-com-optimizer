# R3 ownership and caller disposition — 2026-10-22

**Scope:** Issue #65 R3 only. This is an implementation inventory and
handoff record, not authorization for R4, Q1, a new COM/optimizer study, or
changes to scientific contracts. R2 physics and its deterministic parity
identity are fixed dependencies. Historical reports, raw data, checkpoints,
configs, Q1-A fixtures, and saved Stage 4B/4C evidence remain immutable.

## Owner selections and exact limits

| Item | R3 disposition | Required limit / follow-up |
|---|---|---|
| `core.hybrid.response` seven-variable-root legacy path | **Retain as evidence and operational legacy route.** Keep implementation, behavior, live `studies.hybrid` and test callers, and source/evidence references. | Do not call it dead, delete, break, or repurpose as the canonical evaluator. Its eventual product-path disposition is an R6 review after replacement and evidence review. The path imports the canonical design record/decoder from `design.space`; no `core.models` proxy is retained. The current R2 parity recipe imports the new owner directly; its historical fallback only applies when run against the pre-extraction checkout. |
| `ReleasedFilterDesign` / `simulate_released_filter` | **Parity evidence only.** Keep the released implementation and the in-memory T0 parity gate in `studies.dms_topology_common.implementation_validation`. | Do not use it as the ordinary T0 optimizer/design record, migrate it, delete it, or designate it a supported product route. T0 search inputs are represented by `design.topology.ThreeIdtDesign`; the parity gate compares that generalized route with a separate released-type instance. Retirement needs replacement parity evidence and separate review. |
| `optimizers.selection` candidate ordering | **R4-owned; unchanged.** It remains the sole comparator/selection implementation. | `evaluation.py` may report metrics, violations, feasibility, and the existing scalar search surrogate, but must not reimplement comparator ordering, stable ordinal/tie semantics, or import optimizer state. |
| Adaptive sampling, cache, counters, `problem.evaluator.dense` | **R4-owned; unchanged.** Preserve the existing dense orchestration and its exact behavior. | R3 may redirect its pure grid/metric/evaluation dependencies downward to `evaluation.py`; do not move adaptive/cache/counter policy or alter FE accounting, grids, or validation semantics. |

## Current-to-R3 ownership and caller inventory

| Existing responsibility | Observed callers/contracts | R3 owner / action |
|---|---|---|
| `core.models.FilterDesign`, `NAMES`, `BOUNDS`, `decode`; `problem.design_space` canonical design | Provider-visible complete 9-field record is exercised by physics tests, optimizer/study code and the R2 parity check. Legacy seven-variable decoding and integer half-up behavior feed historical optimization. | Move the sole implementation to `design.space`, update current callers, and remove `core.models` rather than retain a proxy module. `core.hybrid.response` imports the new owner directly; the current R2 parity recipe does likewise. The historical R2 fallback branch only applies when run against the pre-extraction checkout. Move canonicalization alongside the design decoder. Do not change fields, defaults, names, bounds, rounding, clipping, or key ordering. |
| `problem.dms_topologies` T0/T1/T2 records, section geometry, decoders, and simulation | Active screening/common helpers, Stage 4A/B/C, topology tests, the Stage 3.9B source-compatibility recipe, and T0 parity validation. `AcousticSection`/`simulate_section_chain` are physical composition APIs from R2. | Put pure topology records, exact ordered section geometry and decoders in `design.topology`; put COM-to-two-port topology simulation in `evaluation.py`. Update callers and remove `problem.dms_topologies` rather than keep a proxy. Ordinary T0 designs use `design.topology.ThreeIdtDesign`; the released design/simulator are referenced only by the explicit parity check. Convert the physics-free design section record at the evaluation boundary. |
| `problem.hybrid.HybridDesignSpace`, candidate decoding, hybrid layout/assumptions | Stage 4A/B/C and audit consumers; Q1-A's 92-case “public” golden verifier and capture script import `problem.hybrid.HybridDesignSpace`. | Move the space/candidate to `design.space` and pure layout/assumptions to `design.geometry`; use those owners from active study/tests. Keep only the narrow `problem.hybrid` imports required for Q1-A public-path characterization; do not duplicate canonicalization or geometry. Preserve `design.canonicalization.py` numerical statements and the fixture byte-for-byte. |
| `core.metrics.geometry` and `problem.validation` | Legacy response/layout, active search/studies/tests, DMS geometry checks; generic duck-typed topology/section geometry. | Put pure geometry and constraint-dimension calculation once in `design.geometry`; update callers and remove both old modules rather than retain proxy surfaces. Do not change formulas, constraint order/names, error behavior, or geometry-before-physics gates. |
| `core.metrics` grids, `measure`, feasibility record, scalar search objective | Search/evaluation, adaptive validation, reports, topology studies, optimizer and regression tests. `optimizers.selection.rank` is distinct and authoritative for candidate ordering. | Put one implementation in `evaluation.py`, update callers, and remove `core.metrics` rather than retain a proxy. Keep the scalar as the existing search surrogate, not a rank/comparator. Preserve all grid construction and metric/violation semantics exactly. |
| `problem.evaluator.evaluate_design` | Search runner, mixed-variable polish, adaptive-search tests; takes one decoded design and explicit frequency/port inputs. | Move to `evaluation.py` as the one-design response/metrics bridge and update live callers. `problem.evaluator.dense` remains the explicit R4 orchestration boundary; it consumes the new pure response bridge without absorbing cache/adaptive/counter policy. |
| T0 `ReleasedFilterDesign` / `simulate_released_filter` | Existing in-memory T0 parity gate comparing the released algorithm with the generalized T0 path. | Leave `problem.released_dms` implementation unchanged and keep it only in the explicit parity call. Ordinary T0 decode/initial-design returns `design.topology.ThreeIdtDesign`; parity compares the generalized result to `ReleasedFilterDesign` / `simulate_released_filter`. |
| `optimizers.selection`, `optimization.adaptive_frequency`, `optimization.cache`, counters and runner | Active optimizer and parity/trajectory tests; ownership is explicitly deferred. | No R3 policy edits. Import only the downward `design` / `evaluation.py` interfaces needed by the existing runner; keep comparator and optimizer state in their current owners. |
| Stage 4A/B/C and Q1-A support | `studies.hybrid`, Stage 4 audit/profile modules, canonicalization corpus/verifier, import guards. | Update imports only where ownership moved. Keep Stage 4 behavior/evidence and the Q1-A 92-case fixture unchanged. No Stage 4C resume, optimizer qualification, or Q1 integration. |

### Static import and provenance obligations

- `design/` must not import `core`, `problem`, `physics`, `evaluation`,
  `optimization`, `optimizers`, `studies`, `io`, `reporting`, `orchestration`,
  or `runtime`.
- `evaluation.py` may depend on `design/`, `physics/`, and numerical/standard
  libraries; it must not import optimizer state, study orchestration, or IO.
- Existing Q1-A fresh-process import guards and the public/leaf golden runner
  remain in place and are updated only to check the new ownership boundary.
- Update any source manifests/import allowlists that enumerate module paths;
  do not edit fixture contents, historical report hashes, run identities, or
  raw/checkpoint files. Do not retain proxy import modules. A historical
  script may contain an old-path fallback only when run against the older
  checkout it documents; current-checkout callers use new owners.
- The Q1-A corpus remains 92 cases and its exact SHA-256; the 234-member Q0
  seal, comparator semantics, source/load conditions, budgets, FE/RNG policy,
  search/validation grids, Stage 4C saved identities, and R2 parity evidence
  are not recalibrated or re-issued by R3.

## R3 acceptance and explicit handoff

Validate the moved contracts with the frozen canonicalization corpus, static
architecture/import checks, focused deterministic/analytic regressions, the
locked project suite and CLI/import guards on the actual PR head. No new COM,
optimizer FE, qualification, or production run is authorized. Record any
baseline failures distinctly from R3 regressions.

R3 exits with `optimizers.selection`, adaptive-frequency policy/cache/counter
ownership and `problem.evaluator.dense` still in place. R4 must receive a
separate owner authorization and review objective for their interface before
moving any of them. R6 owns the eventual disposition of the retained seven-
variable legacy path and any obsolete import surfaces. Issue #58's unresolved
preservation risks remain open and unchanged.
