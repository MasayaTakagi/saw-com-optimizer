# Architecture overview

## Package responsibilities

- `core/` implements COM sections, acoustic and electrical networks, S-parameter
  conversion, metrics, and physical material calculations.
- `problem/` defines reusable design spaces and evaluation boundaries,
  including the canonical DMS topologies in `dms_topologies.py` and the released
  DMS representation in `released_dms.py`.
- `optimizers/` contains backend contracts, L-SHADE, the SciPy differential
  evolution backend, candidate comparators, and optimizer-generic polish.
- `optimization/` contains SAW search orchestration and shared services such as
  accounting, adaptive frequency handling, budgets, caching, convergence
  evidence, counters, history, population management, the runner, and
  SAW-specific mixed-variable polish.
- `studies/` contains the current live, role-named study adapters:
  `dms_topology_common.py`, `dms_topology_screening.py`, `hybrid.py`, and
  `lshade_records.py`. Its `audits/` subpackage contains read-only historical
  and saved-result validation tools; these are not launch-dispatchable study
  adapters.
- `io/` owns configuration resolution, persistence, checkpoint lifecycle, and
  provenance. `reporting/` builds artifacts from saved runs. `orchestration/`
  manages detached execution and callbacks. `runtime/` configures execution
  environment boundaries.

Study adapters compose problem definitions, optimizer backends, and
optimization services. The `run-study` CLI dispatches the configured DMS
topology study; the 50 Ω Hybrid workflow has its own CLI at
`sawopt.studies.hybrid`.

## Provenance

`sawopt.io.run_store.initialize` supports the historical schema-v1 fingerprint
contract. New studies may use
`sawopt.io.provenance.build_fingerprint_metadata` to save schema v2 with two
hashes:

- `computation_fingerprint`: canonical configuration plus an explicit list of
  source dependencies that can affect numerical results.
- `reporting_fingerprint`: an explicit list of report, plotting, and bundle
  dependencies.

Both lists are recorded with file hashes in `dependency_manifest`. A source
file must be listed in exactly one set. Production computation gates compare
the computation fingerprint; a reporting-only change leaves that gate valid
and can trigger report regeneration. A v1 fingerprint remains readable but is
never interpreted as a v2 computation fingerprint.

## Review bundles

`sawopt.reporting.review_bundle` owns artifact validation, file collection,
source snapshots, Git/environment metadata, SHA-256 manifests, ZIP creation,
and post-ZIP validation. `ReviewBundleSpec` describes a saved run's required
and optional files. Bundle generation uses saved run files and does not import
or run an optimizer.

New experiment guidance is in [new_experiments.md](guides/new_experiments.md);
standalone bundle instructions are in
[review_bundles.md](guides/review_bundles.md).
