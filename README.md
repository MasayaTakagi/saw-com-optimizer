# SAW COM Filter Optimizer

Python implementation of a Coupling-of-Modes (COM) filter solver and
optimization workflows. The checked-in COM inputs are evaluation assumptions;
they are not calibrated production parameters. See
[`docs/history/current_baseline.md`](docs/history/current_baseline.md) for the
adopted model, current limits, and next engineering questions, and
[`docs/history/experiment_register.md`](docs/history/experiment_register.md)
for historical results and decisions.
See [`docs/project_roadmap.md`](docs/project_roadmap.md) for the long-term goal,
sequencing, and phase exit gates.

The evidence baseline is after Stage 4C. Stage 4A qualified hybrid behavior,
Stage 4B compared four topologies, and Stage 4C completed 10/10 cells with
neither feasibility nor convergence/topology selection established. The
2026-10-08 resonator-pair diagnostic is recorded separately. See the
[experiment register](docs/history/experiment_register.md) for evidence.

**Revised project targets:** (1) optimize filter designs under user-provided
COM parameters, specification, area/geometry and impedance constraints,
(2) draw Smith-chart performance heatmaps based on **independent design
re-optimization at each sampled impedance**, and (3) make both workloads
practical in time and resources. Physical COM calibration is optional, not
a development gate. The next Stage 5A priority is to diagnose why existing
50/50-ohm optimization has not met specification, quantify the generic
high-dimensional optimizer's cost and quality, and evaluate classical
SAW-design-guided search simplifications.

## Current workflows

- DMS topology screening: `configs/studies/dms_topology_screening.yaml`
- 50 Ω hybrid exploration: `configs/studies/hybrid_50ohm.yaml`
- Existing prototype simulation, optimization, real-impedance sweep, and
  saved-run reports through `uv run --locked python -m sawopt` (not yet the
  planned re-optimized complex-impedance Smith heatmap workflow)

Run from the worktree root in the WSL Ubuntu shell:

```bash
uv run --locked python -m sawopt simulate --run runs/baseline
uv run --locked python -m sawopt optimize --rs 50 --rl 50 --run runs/50ohm
uv run --locked python -m sawopt sweep --run runs/prototype --refine-step 5
uv run --locked python -m sawopt report --run runs/prototype
```

Run a configured study with:

```bash
uv run --locked python -m sawopt run-study --config configs/studies/dms_topology_screening.yaml --run runs/dms-topology-screening
```

Run the separate 50 Ω Hybrid workflow with its standalone CLI:

```bash
uv run --locked python -m sawopt.studies.hybrid --config configs/studies/hybrid_50ohm.yaml --run runs/hybrid-study
```

Use `uv run --locked python -m sawopt.orchestration.cli launch` for production runs expected to
take 30 minutes or longer. Follow
[`docs/guides/async_orchestration.md`](docs/guides/async_orchestration.md)
for session capture, detached launch, and recovery.

Review bundles belong under `artifacts/review_bundles/`. Build one from a saved
run with `ReviewBundleSpec` and `sawopt.reporting.review_bundle`; see
[`docs/guides/review_bundles.md`](docs/guides/review_bundles.md).

## Repository review

The active external review path is GitHub branches, commits, and pull requests.
See [`docs/guides/github_review_workflow.md`](docs/guides/github_review_workflow.md).
C2C is frozen as a historical reference; its status and retained diagnosis
are in [`docs/c2c/FROZEN.md`](docs/c2c/FROZEN.md).

## Development

The official environment is WSL2 Ubuntu 24.04 + VS Code Remote WSL + Codex
CLI + uv, using Ubuntu system Python 3.12. Keep each checkout/worktree under
`/home/...` and Windows/WSL `.codex` state separate. Windows Codex Desktop's
WSL Agent is outside this environment; Node is not required or installed.
See [development setup](docs/guides/development_environment.md).

From each new worktree root:

```bash
uv sync --locked --extra test
uv run --locked pytest
```

`.python-version` and `uv.lock` are tracked; `.venv/` stays ignored.

Tests live under `tests/`. COM sign conventions are in
[`docs/conventions/com_convention.md`](docs/conventions/com_convention.md),
and network conventions are in
[`docs/conventions/network_convention.md`](docs/conventions/network_convention.md).
