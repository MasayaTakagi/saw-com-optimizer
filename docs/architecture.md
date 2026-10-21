# Architecture: current implementation and target ownership

**Status:** Responsibility map, not an implemented target package tree. R0
counted 94 Python modules at main `a4b3807d399cc78b10c280d41ee8cea476ade329`;
R2–R7 migration has not begun. Do not import, document, or rely on target APIs
as if they already exist.

## Target dependency direction

```text
cli / plotting / io
          ↓
optimization → evaluation → design + physics
```

- **`physics/`** — COM sections/elements, acoustic and electrical network,
  S-parameters, and physical metrics. Must not depend on optimizer, study,
  CLI, reporting, GitHub, or run lifecycle.
- **`design/`** — topology, bounds, variable representation, canonicalization,
  and geometry. Must not invoke COM evaluation or optimization.
- **`evaluation.py`** — the single bridge from design plus physics to response
  metrics, modeled constraints, feasibility, and the declared candidate-rank
  contract. Optimizers consume an evaluator interface, not COM internals.
- **`optimization/`** — L-SHADE/DE strategies and a bounded shared runner for
  search, unique-FE budget, cache, counters, and required checkpoint state.
  Algorithm-specific proposal rules remain within their strategies.
- **`io/`** — user configuration, results, frozen provenance, external raw
  storage, and only the checkpoint lifecycle required by the approved current
  design; no agent-session continuation.
- **`cli.py` / `plotting.py`** — user entry points and scientific visualization;
  lower-level packages do not import them.

These ownership statements describe the agreed destination. They are not
permission to create empty modules, move code en masse, preserve obsolete APIs,
or alter scientific behavior. No compatibility wrappers or old-checkpoint
readers are part of the target design.

## Current → target responsibility map

| Current code (exists) | Current role / observed coupling | Target owner (future) |
|---|---|---|
| `src/sawopt/core/com.py`, `models.py`, `network.py` | COM sections, providers/design/result records, acoustic solve, real-port network evaluator. | Split physics math/providers and network into `physics/`; domain input records into `design/` or `evaluation.py` according to ownership. |
| `src/sawopt/core/hybrid.py`, `topology.py` | Hybrid electrical composition/layout and DMS/topology behavior. | Reusable physical composition in `physics/`; topology definitions in `design/`. |
| `src/sawopt/core/metrics.py` | Frequency grids, metrics, geometry calculation, scalar search surrogate. | Grid/spec and constraint evaluation to `evaluation.py`; physical response metrics to `physics/` only where genuinely physical. |
| `src/sawopt/problem/design_space.py`, `dms_topologies.py`, `released_dms.py`, `hybrid.py`, `validation.py` | Design spaces, topology records, geometry and candidate evaluation; several depend upward on optimization services or core. | `design/` and one `evaluation.py`; remove upward dependency. |
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

These are software dependencies, not proof that a module is dead. In
particular, `problem.evaluator` uses optimization cache/adaptive-frequency
services, the optimizer packages overlap, and studies/reporting/orchestration
have runtime cycles. The architecture refactor must move ownership and invert
dependencies intentionally; renaming directories alone will not meet the target.

R2 extracts physics; R3 separates design and evaluation; R4 consolidates
optimization and reconciles the closed Q1-A implementation; R5 establishes
future raw/review storage contracts; R6 builds a minimal user-facing vertical
slice and retires replaced code; R7 audits risk-based CI and cutover. Each is a
separate review gate in the [migration plan](plans/repository_restructure_migration_plan_20261022.md).
No stage grants permission to change equations, ranking, bounds, Q0/Q1
semantics, or run conditions.

## Q1-A implementation and evidence boundary

Q1-A code currently lives under `studies/stage5a2/` and a shared
`design/canonicalization.py` leaf. Its work unit is closed as
`WORK_UNIT_READY`, but no formal Q1 gate passed. The target design removes
stage-specific runtime folders; it does **not** decide whether Q1-A source is
to be replaced, retired, or reused. The explicit contract disposition and
owner decision boundary are in
[Q1 contract disposition](plans/restructure_q1_contract_disposition_20261022.md).
Do not begin Q1-B/C/D/E or claim the existing foundation is generally
production-qualified.
