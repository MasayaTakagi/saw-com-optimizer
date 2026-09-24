# Checkpoint lifecycle

## Storage classes

Full optimizer state is a runtime recovery artifact by default. Each managed
optimizer stream lives under its own `checkpoints/` directory and keeps:

```text
latest.json
previous.json
final.json          # only after successful completion
pinned/<label>.json # only when explicitly requested
retention.json
```

Analysis history stays in ordinary CSV/JSONL outputs. Do not write full
population dumps to history as a substitute for resumable state. Existing
convergence traces, counter summaries, and milestone accounting remain the
canonical analysis records.

## Writes and recovery

Use `sawopt.io.checkpoints.CheckpointStore` for filesystem lifecycle. A store
accepts the existing serializer as a writer callback, writes to a temporary
file in the same directory, parses and validates it, rotates the previous
latest to `previous.json`, then atomically promotes the temporary file to
`latest.json`. It does not change checkpoint state fields or serialization.

Resume validates `latest.json` first, then `previous.json`. Optimizer-specific
validation must use a fresh backend instance so a failed load cannot leave the
live optimizer partially mutated. The L-SHADE study adapter
`LShadeCheckpointSession` provides this behavior and preserves the legacy
single-file `save_checkpoint`/`load_checkpoint` API. When an old run is resumed
from its legacy file, that run continues using the legacy path; no migration is
performed. A legacy run whose `manifest.json` uses the historical v1
`run_store.initialize` fingerprint still requires its matching source checkout:
that contract hashes every Python file and rejects a changed source tree. The
checkpoint adapter does not bypass that manifest check or migrate old runs.
Legacy checkpoint format loading remains supported independently. This does
not promise that a legacy run can resume under a changed source tree.

Failed or incomplete runs keep their runtime generations. Historical run
directories are read-only unless a user explicitly asks for a separate,
reviewable cleanup operation; no repository-wide cleanup is provided.
When a previously finalized run is resumed, its older `final.json` remains
available until the next successful finalization replaces it.

Managed result artifacts refer to the logical stream directory and policy,
not to a future `final.json` file. The stream reference remains valid while
the run is active and while review or recovery is pending. A final checkpoint
path is added to completion metadata only after finalization succeeds. Legacy
direct-file mode continues to record its actual checkpoint file path.

## Completion and retention

Checkpoint finalization is controlled by an explicit `RunDisposition`, not by
the absence of an error status or by a study's scientific gate result. The
generic lifecycle API supports `COMPLETED`, `REVIEW_WAITING`, `FAILED`, and
`UNKNOWN`. Missing or unknown disposition retains runtime recovery state.

`COMPLETED` allows a direct CLI run to finalize immediately. An orchestrated
run finalizes only after its durable optimizer status records successful
completion and exit code zero. `REVIEW_WAITING`, `FAILED`, and `UNKNOWN` keep
`latest` and `previous`. Finalization validates and promotes the newest valid
state to `final.json` before removing runtime and temporary files. Pinned
states survive finalization.

The compatibility adapter in `sawopt.io.legacy_lifecycle` maps the historical
Stage review markers to `REVIEW_WAITING` at legacy entrypoint boundaries. The
generic checkpoint store does not inspect Stage marker names. New studies
should supply an explicit disposition and must not add Stage-specific markers
to the generic checkpoint core. A later closeout after human review requires
a dedicated reviewed-closeout action that records `COMPLETED` and
updates the durable optimizer disposition. The callback or `REVIEWED` state
alone is not completion evidence and does not release recovery checkpoints.

Direct Python calls to a study function do not imply successful completion.
Call the shared completion/finalization API only after the study has written
its successful closeout artifacts.

`metadata/recovery_policy.json` records the retention policy, final checkpoint
presence, explicit pin count, and history artifact paths. This neutral filename
is intentionally outside the review builder's checkpoint-payload filter.
`metadata/run_completion.json` records the explicit disposition and, after a
successful finalization, the existing final checkpoint path or paths.

## Review bundles

Use the generic `ReviewBundleSpec` and `build_review_bundle` APIs for saved-run
packaging. Include `metadata/recovery_policy.json` as a required or optional
artifact when checkpoint provenance is relevant. Full checkpoints remain
excluded by default; include a final payload only as an explicit optional
artifact. The generic builder hashes and validates bundle contents and never
rotates or deletes checkpoints.

The filter excludes files in dedicated `checkpoints/` directories and
checkpoint-named JSON/binary payloads. It retains checkpoint lifecycle
documentation, source code, and CSV accounting.
