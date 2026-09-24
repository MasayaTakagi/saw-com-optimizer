# Architecture overview

## Dependency direction

New numerical work follows the dependency direction below:

```text
studies → optimization → problem → core
studies → reporting
studies → io
```

`core` owns COM and network calculations. `problem` owns reusable design and
topology definitions. `optimization` owns search primitives such as counters,
population sampling, and accounting. `optimizers` owns algorithm backends and
candidate selection. Study modules compose those pieces and own experiment
configuration. Reporting consumes saved runs and result metadata.

`src/sawopt/problem/dms_topologies.py` is the canonical T0/T1/T2 DMS topology
module. The former Stage 3.8 module re-exports the design classes, decoders,
section builders, topology constants, and simulator for old imports. Its
Stage-specific config, material selection, initializer setup, and reports stay
in the study adapter.

## Provenance

`sawopt.io.run_store.initialize` and Stage 3.8's source/config gates implement
the historical fingerprint contract. They remain schema v1 and are not
rewritten. New studies may use `sawopt.io.provenance.build_fingerprint_metadata`
to save schema v2 with two hashes:

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
and optional files. Stage-specific reporting code owns the content of
`REVIEW_ME.md` and derived study summaries. Bundle generation uses saved run
files and does not import or run an optimizer.

New experiment guidance is in [new_experiments.md](guides/new_experiments.md);
standalone bundle instructions are in
[review_bundles.md](guides/review_bundles.md).
