# New experiment implementation guidance

New experiments should reuse study, reporting, and search infrastructure
instead of adding Stage-specific copies. Keep reusable topology definitions in
`problem`, reusable counter/population/accounting logic in `optimization`, and
experiment conditions in the study configuration and study adapter.

Use the shared checkpoint lifecycle in
[`checkpoint_lifecycle.md`](checkpoint_lifecycle.md) for full-state recovery,
rolling retention, and successful-run finalization. Keep analysis history in
CSV/JSONL outputs and do not add per-study checkpoint rotation code.

Every new study entry point must pass a `RunDisposition` explicitly to
`sawopt.io.checkpoints.complete_study_run`. Use `COMPLETED` only when the study
execution and its required closeout artifacts are complete; use
`REVIEW_WAITING` while human review remains, and `FAILED` when execution or
execution infrastructure validation failed. A scientific gate may finish
normally with either pass or fail; do not use its result as lifecycle state.
Missing or ambiguous evidence must remain `UNKNOWN`, which
preserves recovery checkpoints. Historical marker translation belongs in
`sawopt.io.legacy_lifecycle`; new studies should not add marker-name checks to
the checkpoint core.

Use `ReviewBundleSpec` and `build_review_bundle` for saved-run packaging. Keep
`REVIEW_ME.md` wording and derived study summaries in the study's reporting
module. Do not copy ZIP, hashing, Git snapshot, or environment-capture code
into a study runner.

Use fingerprint schema v2 for new studies. Enumerate the full numerical source
dependency set explicitly, including the study's numerical implementation,
COM/network dependencies, topology, optimizer selection, counters, initializer,
and the exact input configuration. Enumerate reporting code, plots, templates,
and bundle schema only in the reporting dependency set.

> Reporting-only changes do not invalidate computation fingerprints.

New computation gates should call
`sawopt.io.provenance.computation_gate_matches`; compare schema-v2 computation
fingerprints and ignore a reporting fingerprint mismatch for optimizer
execution. A reporting mismatch can require regenerating review artifacts.
Historical schema-v1 manifests and gates must remain readable and unchanged.

Prefer role-based module names such as `topology_screening`, `hybrid`, or
`impedance_sweep`; keep experiment chronology in configuration, run
directories, and result metadata.
