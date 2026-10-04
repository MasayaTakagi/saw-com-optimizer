# Post-run review and evidence contract

This document defines the required completion handoff for new long-running
production experiments in `saw-com-optimizer`.

It is intentionally separate from any one Stage. Historical runs retain their
original evidence paths and schemas.

## Purpose

The post-run workflow must make a completed numerical experiment independently
reviewable through GitHub without requiring raw checkpoints or ad-hoc file
selection after the fact.

The contract separates four concerns:

1. numerical execution;
2. continuation delivery back to the exact original Codex thread;
3. lightweight evidence publication;
4. external ChatGPT scientific review.

## Required completion flow

For a new production run:

```text
COMPLETED / FAILED optimizer state
→ durable one-shot continuation claim
→ exact original thread ID
→ queue delivery
→ same-thread continuation
→ evidence export
→ commit + push on experiment branch
→ REVIEW_WAITING
→ external ChatGPT review
```

No post-run continuation may automatically launch another production run.

## Continuation identity

The launch manifest must capture the exact original Codex thread ID before the
worker detaches.

For queue-native runs:

- `original_thread_id` is required;
- a session ID is not a substitute for a thread ID;
- delivery is one-shot and durable;
- an ambiguous attempt must fail closed rather than resend blindly;
- sender acceptance alone is not receiver confirmation;
- receiver confirmation, when available, must refer to the exact expected
  thread and delivery identity.

Legacy `codex exec resume` metadata may remain supported for reading/recovery of
historical manifests, but new production launch paths must not select it as the
normal continuation mode.

## Codex post-run responsibility

The resumed Codex task is a publisher/packager. It may:

- verify run completion/integrity;
- inspect the completed run read-only;
- export the required lightweight review artifacts;
- calculate hashes and package metadata;
- commit/push the review package to the existing experiment branch;
- report the branch, commit SHA, review directory, and high-level completion
  status.

It must not, without a later explicit instruction:

- declare the final scientific acceptance on ChatGPT's behalf;
- promote a topology/design as the project baseline;
- rewrite `current_baseline.md` or the long-term roadmap before external
  review;
- launch an extension, extra seed, impedance sweep, or next Stage;
- merge the experiment PR;
- delete the raw run or checkpoints.

## Canonical GitHub review path

New runs use:

```text
reports/experiment_reviews/<stage>/<run_id>/
```

Example:

```text
reports/experiment_reviews/stage4c/202610xx_xxxxxx_xxxxxx/
```

The directory is committed to the same experiment branch that contains the
implementation/configuration used for the run.

Historical evidence paths are not migrated solely for consistency.

## Required package structure

The exporter should produce the following logical structure when the underlying
study provides the corresponding artifacts:

```text
README.md
review_manifest.json
artifact_manifest.csv
run_manifest.json
status.json

metadata/
  run_completion.json
  config_snapshot.yaml
  protocol_snapshot.json
  integrity_check.json

summary/
  primary_summary.csv
  paired_comparisons.csv
  convergence.csv
  bound_pressure_summary.csv
  runtime_accounting_summary.csv
  scientific_limitations.md

cells/
  <arm-or-topology>/
    <seed>_result.json
    <seed>_status.json
```

Study-specific compact summaries may be added when necessary. The generic
contract should not force a topology-specific filename when a study has a
different comparison dimension.

If a requested logical artifact does not exist for that study, the manifest
must state that explicitly rather than silently omitting a required evidence
class.

## `review_manifest.json`

At minimum record:

- review schema version;
- run ID;
- Stage/study identifier;
- production execution source SHA;
- computation/protocol fingerprint where applicable;
- source branch;
- review branch;
- canonical review directory;
- optimizer completion state and exit code;
- number of expected/completed cells or arms;
- seed set;
- comparison-arm/topology set;
- evaluation budget and terminal horizon;
- search/common-validation grid identity where applicable;
- review package creation timestamp;
- exporter implementation/version identity;
- package completeness result;
- package total bytes;
- redaction result.

Do not store authentication credentials or temporary public connector URLs.

## `artifact_manifest.csv`

For every copied evidence artifact record:

```text
category
source_path_sanitized
source_size_bytes
source_mtime_utc
source_sha256
destination_path
destination_size_bytes
destination_sha256
included
reason
```

For byte-for-byte copies, source and destination SHA256 must match.

The exporter must not silently rewrite line endings or normalize JSON/YAML/CSV
content that is claimed to be a byte-for-byte copy.

## Default inclusion classes

Include compact artifacts needed for independent scientific review, normally:

- immutable orchestration/run manifest;
- final status/completion metadata;
- frozen config/protocol snapshot;
- integrity/accounting summary;
- terminal per-seed/per-cell result and status;
- aggregate comparison tables;
- paired comparisons when the protocol is paired;
- checkpoint-derived convergence summary rather than all checkpoint bodies;
- active-bound/geometry/failure accounting;
- runtime summary;
- scientific limitations.

## Default exclusions

Do not commit by default:

- optimizer checkpoint bodies;
- `B*.json` checkpoint dumps;
- population/archive dumps;
- raw dense arrays or large NPZ/NPY files;
- full caches;
- complete stdout/stderr logs;
- callback/queue/Codex rollout logs;
- duplicate raw intermediate outputs;
- large binary dumps.

If an excluded artifact is essential to review, add a compact derived summary
or stop for an explicit exception rather than automatically committing the
large file.

## Size gate

Target package size:

```text
< 2 MiB
```

Hard default gate:

```text
< 10 MiB
```

If the package would exceed the hard gate, stop and report which evidence class
causes the excess. Do not use Git LFS automatically and do not silently remove
scientifically necessary evidence to fit the limit.

A study may declare a different approved size gate before production if its
review contract requires it.

## Redaction gate

Before commit, scan the package for at least:

- bearer/access/refresh tokens;
- OAuth authorization URLs or codes;
- client secrets;
- pairing codes;
- cookies;
- raw Quick Tunnel/public MCP endpoints;
- other reusable credentials.

Thread IDs, run IDs, Git SHAs, hashes, seed values, and process IDs may remain
when they are needed for provenance and are not authentication credentials.

Normalize local user-profile paths where practical when path identity is not
scientifically relevant.

## Completeness gate

Before push, verify at least:

- run ID consistency;
- source SHA consistency;
- fingerprint/config consistency;
- expected vs completed arm/cell counts;
- expected seed/arm sets;
- per-cell terminal result/status coverage;
- artifact hash agreement;
- no forbidden large artifacts staged;
- no unexpected source/config mutation caused by the exporter.

A failed completeness gate must prevent the package from being labeled ready
for external review.

## Review state semantics

Numerical completion and review are separate.

Recommended high-level states are:

```text
COMPLETED / FAILED
CONTINUATION_PENDING
CONTINUATION_SENT
REVIEW_WAITING
```

`REVIEW_WAITING` means that the run and lightweight evidence have been
published and are waiting for independent review. It does not mean the
scientific result has been accepted.

New schema-v4 manifests freeze the review stage, canonical output path, spec
identifier and hash, exporter contract version, and queue handoff identity.
Queue is the default for a new launch; the only other new-launch mode is an
explicitly disabled continuation. `legacy_resume` remains a historical
read/recovery mode and cannot be selected by a new launch. Schema-v4 queue
manifests do not require C2C task or plan-iteration metadata.

The worker records optimizer completion and makes at most one durable queue
attempt. Queue exit code zero records sender acceptance only. The resumed exact
thread confirms receipt using its runtime `CODEX_THREAD_ID` plus run ID,
delivery ID, and sentinel. Neither sender acceptance nor receiver confirmation
changes the orchestration state to `REVIEWED`.

The supported publication finalizer is
`python -m sawopt.orchestration.cli mark-review-published`. It requires a
terminal run, a complete/redacted canonical package, a commit containing that
package, a clean package path, and the matching pushed upstream branch. Only
then does the run enter `REVIEW_WAITING` and record publication metadata.

The project closeout/experiment register records the later external decision.

## Generic exporter target

The preferred implementation is a reusable command such as:

```text
python -m sawopt export-review --run <run-dir>
```

or an equivalent subcommand under the existing CLI.

The generic exporter should own:

- allowlist resolution;
- copy/hash verification;
- size accounting;
- redaction checks;
- completeness checks;
- review manifest generation;
- canonical destination-path generation.

Each study should only need to declare its compact study-specific artifact
specification rather than hand-coding a new GitHub export workflow.

This generic exporter is a required implementation target before the next
long-running Stage 4C production run.
