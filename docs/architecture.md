# Architecture: current implementation and target ownership

**Status:** Responsibility map; R2 physics extraction was merged before R3
(Issue #63). R3 ownership and caller disposition is recorded in
[the R3 inventory](plans/restructure_r3_ownership_20261022.md); this document
is updated for the authorized R3 implementation. The R0 inventory counted 94
Python modules at main `a4b3807d399cc78b10c280d41ee8cea476ade329` (pre-R2
baseline). R4–R7 remain unstarted. Target APIs not yet implemented must not be
treated as current.

## Target dependency direction

```text
cli / plotting / io
          ↓
optimization → evaluation → design + physics
```

- **`physics/`** — COM sections/elements, acoustic and electrical network,
  and S-parameter calculations. Must not depend on optimizer, study, CLI,
  reporting, GitHub, or run lifecycle.
- **`design/`** — topology, bounds, variable representation, canonicalization,
  and geometry. Must not invoke COM evaluation or optimization.
- **`evaluation.py`** — the single response/metrics/constraint bridge from
  design plus physics. It reports feasibility and the existing scalar search
  surrogate; the sole candidate comparator remains `optimizers.selection`
  until its R4 review. The existing `problem.evaluator.dense` adaptive/cache/
  counter orchestration is explicitly retained for R4, not represented as
  already migrated.
- **`optimization/`** — L-SHADE/DE strategies and a bounded shared runner for
  search, unique-FE budget, cache, counters, and required checkpoint state.
  Algorithm-specific proposal rules remain within their strategies.
- **`io/`** — user configuration, results, frozen provenance, external raw
  storage, and only the checkpoint lifecycle required by the approved current
  design; no agent-session continuation.
- **`cli.py` / `plotting.py`** — user entry points and scientific visualization;
  lower-level packages do not import them.

These ownership statements describe target ownership and the R3-authorized
subset; they do not imply that the entire repository has reached that target.
Avoid duplicate implementations and blanket compatibility layers. R3 retains
the operational seven-variable `core.hybrid.response` path and the narrow
`problem.hybrid` public import needed by Q1-A golden verification; moved
`core.models`, `core.metrics`, and mixed `problem/` implementations are
removed rather than retained as proxy modules. Current R2 parity and Stage
3.9B source recipes import the new owners directly. `problem.evaluator.dense`,
adaptive/cache/counter policy and `optimizers.selection` are deferred to R4;
no old-checkpoint reader is introduced.

## Current → target responsibility map

| Current code (exists) | Current role / observed coupling | Target owner (future) |
|---|---|---|
| `src/sawopt/physics/com.py`, `network.py`, `literature_com.py`; former `src/sawopt/core/models.py` | R2 owns COM P-matrix propagation/global acoustic solve, COM providers and result record, and the real-positive-port network evaluator. R3 moves the complete provider-visible `FilterDesign` record and decoder to `design.space`, updates current callers, and removes the duplicate `core.models` module. | Physics remains in `physics/`; design records/decoding in `design/`, response and RF metrics in `evaluation.py`. |
| `src/sawopt/physics/elements.py`; `src/sawopt/core/hybrid.py` | R2 owns reusable acoustic-section, IDT-port, one-port resonator, parallel-track, and electrical nodal composition in `physics/`. The seven-variable-root `core.hybrid.response` and its live `studies.hybrid`/test callers are expressly retained as operational legacy evidence; it is not the new canonical evaluator. | Reusable physical composition in `physics/`; new design ownership in `design/`. `core.hybrid.response` remains until an R6 disposition after replacement/evidence review. |
| Former `src/sawopt/core/metrics.py` | Legacy owner of frequency grids, response metrics, geometry and a scalar search surrogate; candidate comparison is separately owned by `optimizers.selection`. R3 moves callers and removes the duplicate module. | Pure geometry to `design.geometry`; grids/metrics/feasibility and the unchanged scalar surrogate to `evaluation.py`. |
| Former `src/sawopt/problem/design_space.py`, `dms_topologies.py`, `validation.py`; current `released_dms.py`, `hybrid.py`, `evaluator.py` | Mixed design/topology/geometry/evaluation responsibilities; `problem.evaluator.dense` owns adaptive/cache/counter orchestration. R3 moves design/geometry/evaluation owners and removes the duplicated mixed modules. `ReleasedFilterDesign` / `simulate_released_filter` remain exclusively as T0 parity evidence; ordinary T0 design/evaluation now uses `design.topology.ThreeIdtDesign` and the generalized evaluator. `problem.hybrid` remains only for the Q1-A public golden import path. | Pure records/spaces/canonicalization/geometry to `design/`; one-design response and metrics to `evaluation.py`. Preserve the `problem.evaluator.dense` adaptive/cache/counter orchestration and behavior for explicit R4 follow-up; the point-response dependency now delegates to evaluation. Released DMS code remains parity-only. |
| `src/sawopt/optimizers/` and `src/sawopt/optimization/` | Separate optimizer backends/policies and shared budget/cache/accounting/runner; responsibilities overlap. | One cohesive `optimization/` with algorithm strategies and common runner/services. |
| `src/sawopt/io/` | Config, serialization, run stores, provenance, checkpoints and lifecycle. | `io/` config/results/checkpoint, with the approved external data contract. |
| `src/sawopt/studies/` | Live adapters, historical audits, stage-specific studies, Q1-A foundation. | Config-driven experiment inputs and only thin reusable orchestration; retire stage-specific runtime after explicit disposition. |
| `src/sawopt/reporting/` | Historical/ad-hoc reports, bundles, GitHub review export and integrity. | Compact review export in the data/review responsibility; plots in `plotting.py`; retain no agent coupling. |
| `src/sawopt/orchestration/`, `runtime/` | Detached run lifecycle, process/storage safety, review publishing, agent-session queue/callback, execution environment. | User-run process supervision only where required; no AI session/queue. Preserve safety responsibilities until a reviewed replacement exists. |
| `src/sawopt/__main__.py` | Existing CLI composition for `simulate`, `optimize`, `sweep`, `report`, and `run-study`. | A thin `cli.py` entry point after vertical-slice replacement; not yet implemented. |

The concrete inventory, module list, configs/tests, and observed package edges
are recorded in the [R0 preflight inventory](../reports/restructure/r0_preflight_inventory_20261022.md).

## Current dependency risks and migration prerequisites

R0's static package import scan found these existing edges:

- `__main__ → core, io, optimization, reporting, studies`;
- `problem → core, design, optimization`;
- `optimization → core, io, optimizers, problem`;
- `optimizers → io`;
- `studies → core, design, io, optimization, optimizers, orchestration, problem, reporting`;
- `reporting → core, optimization, optimizers, orchestration, studies`;
- `orchestration → io, reporting, studies`.

These are the pre-R2 software dependencies, not proof that a module is dead.
The R2 extraction now has `physics.elements → physics.com`; the other physics
modules import only external numerical libraries or standard-library modules.
`problem.evaluator` still uses optimization cache/adaptive-frequency services,
the optimizer packages overlap, and studies/reporting/orchestration have
runtime cycles. The architecture refactor must move ownership and invert
dependencies intentionally; renaming directories alone will not meet the target.

R2 physics extraction is merged. R3 separates design and evaluation under
Issue #65's owner authorization; the current ownership choices, caller list,
and evidence-only dispositions are explicit in the
[R3 inventory](plans/restructure_r3_ownership_20261022.md).
R4 may later review optimization ownership and the retained dense boundary; R5
establishes future raw/review storage contracts; R6 builds a minimal
user-facing vertical slice and considers the deferred legacy path; R7 audits
risk-based CI and cutover. Each is a separate review gate in the
[migration plan](plans/repository_restructure_migration_plan_20261022.md). No
stage grants permission to change equations, ranking, bounds, Q0/Q1 semantics,
or run conditions.

## Q1-A implementation and evidence boundary

Q1-A code currently lives under `studies/stage5a2/` and a shared
`design/canonicalization.py` leaf. Its work unit is closed as
`WORK_UNIT_READY`, but no formal Q1 gate passed. The target design removes
stage-specific runtime folders; it does **not** decide whether Q1-A source is
to be replaced, retired, or reused. R3 preserves the 92-case Q1-A public/leaf
golden corpus and the canonicalizer's exact behavior; the legacy public import
surface remains only for its explicit verifier/capture callers. The explicit
contract disposition and owner decision boundary are in
[Q1 contract disposition](plans/restructure_q1_contract_disposition_20261022.md).
Do not begin Q1-B/C/D/E or claim the existing foundation is generally
production-qualified.
