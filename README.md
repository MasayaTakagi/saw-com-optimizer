# SAW COM Filter Optimizer

Python prototype for modeling and optimizing SAW filters with Coupling-of-Modes
(COM) inputs. The checked-in COM parameters are engineering/evaluation
assumptions, not calibrated production values.

The product target is a user-configurable constrained design flow and, later,
a Smith-chart heatmap built from an **independent filter re-optimization at
each sampled source/load impedance pair**. B28 Rx at 50/50 ohm is a regression
and diagnostic case. A finite-budget result is best-found, not a proof of a
global optimum. Physical COM calibration is optional; numerical correctness,
units/conventions, modeled-constraint consistency, and reproducibility remain
required.

## Current status

Stage 4C remains `STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`. Q0 is
`CLOSED / ACCEPTED`; Q1-A is `WORK_UNIT_READY / CLOSED`; no formal Q1 gate
Q1-01…Q1-23 has passed, and Q1-B/C/D/E are `NOT AUTHORIZED / NOT STARTED`.
The target `physics/design/evaluation/optimization/io` architecture and future
experiment-storage schema are plans, not implemented package APIs.

## Documentation

Start with the [current documentation index](docs/README.md), which identifies
the authoritative [roadmap](docs/roadmap.md), [architecture](docs/architecture.md),
[physics conventions](docs/physics.md), [development workflow](docs/development.md),
and [experiment/data policy](docs/experiments.md). The [historical baseline](docs/history/current_baseline.md)
and [experiment register](docs/history/experiment_register.md) preserve prior
evidence and limitations.

## Existing prototype

The current source remains under `src/sawopt/`; its CLI and study adapters are
legacy implementation paths pending the staged reconstruction. Existing
entrypoint help is available with:

```bash
uv run --locked python -m sawopt --help
```

This command is informational; it does not authorize a numerical or production
run. Use the locked Ubuntu/uv environment documented in
[`docs/development.md`](docs/development.md).
