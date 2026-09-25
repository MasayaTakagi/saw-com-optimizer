# SAW COM Filter Optimizer

Python implementation of a Coupling-of-Modes (COM) filter solver and
optimization workflows. The checked-in COM inputs are evaluation assumptions;
they are not calibrated production parameters. See
[`docs/history/current_baseline.md`](docs/history/current_baseline.md) for the
adopted model, current limits, and next engineering questions, and
[`docs/history/experiment_register.md`](docs/history/experiment_register.md)
for historical results and decisions.

## Current workflows

- DMS topology screening: `configs/studies/dms_topology_screening.yaml`
- 50 Ω hybrid exploration: `configs/studies/hybrid_50ohm.yaml`
- Prototype simulation, optimization, impedance sweep, and saved-run reports
  through `python -m sawopt`

Use the project virtual environment on Windows:

```powershell
.\.venv\Scripts\Activate.ps1
python -m sawopt simulate --run runs/baseline
python -m sawopt optimize --rs 50 --rl 50 --run runs/50ohm
python -m sawopt sweep --run runs/prototype --refine-step 5
python -m sawopt report --run runs/prototype
```

Run a configured study with:

```powershell
python -m sawopt run-study --config configs/studies/dms_topology_screening.yaml --run runs/dms-topology-screening
```

Run the separate 50 Ω Hybrid workflow with its standalone CLI:

```powershell
python -m sawopt.studies.hybrid --config configs/studies/hybrid_50ohm.yaml --run runs/hybrid-study
```

Use `python -m sawopt.orchestration.cli launch` for production runs expected to
take 30 minutes or longer. Follow
[`docs/guides/async_orchestration.md`](docs/guides/async_orchestration.md)
for session capture, detached launch, and recovery.

Review bundles belong under `artifacts/review_bundles/`. Build one from a saved
run with `ReviewBundleSpec` and `sawopt.reporting.review_bundle`; see
[`docs/guides/review_bundles.md`](docs/guides/review_bundles.md).

## Development

Create and install the project environment from this directory:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
```

Tests live under `tests/`. COM sign conventions are in
[`docs/conventions/com_convention.md`](docs/conventions/com_convention.md),
and network conventions are in
[`docs/conventions/network_convention.md`](docs/conventions/network_convention.md).
