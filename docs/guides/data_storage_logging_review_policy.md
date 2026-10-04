# Data storage, logging, and GitHub review policy

This document is the canonical overview for production data storage, execution logging, and GitHub-mediated review in `saw-com-optimizer`.

Detailed mechanics live in:

- [`async_orchestration.md`](async_orchestration.md) for launch, continuation, and recovery;
- [`postrun_review_contract.md`](postrun_review_contract.md) for review-package contents and gates;
- [`github_review_workflow.md`](github_review_workflow.md) for review roles and branch/PR workflow;
- [`worktree_safety.md`](worktree_safety.md) for persistent storage and worktree removal safety;
- [`checkpoint_lifecycle.md`](checkpoint_lifecycle.md) for checkpoint retention and recovery semantics.

Historical runs keep their original schemas and paths. The rules below apply to new user-authorized or ranking-eligible production work unless a frozen study protocol explicitly says otherwise.

## 1. Three storage classes

The repository separates three kinds of data.

| Class | Canonical location | Git tracked | Purpose |
| --- | --- | --- | --- |
| Source / protocol / tests | repository worktree | yes | code, configs, tests, documentation, decision history |
| Raw production data | external persistent run root | no | checkpoints, populations, raw numerical outputs, recovery state, full logs |
| Review evidence | `reports/experiment_reviews/<stage>/<run_id>/` | yes | compact, deterministic evidence sufficient for independent review |

Tracked source worktrees are disposable checkouts. They are not durable owners of production raw data.

## 2. Raw production data

New production launches must use an absolute persistent run root or run directory outside every registered Git worktree. The active storage contract is:

```text
run_storage_policy = external_persistent_v1
```

On the current Windows workstation the operational root is typically adjacent to the repository, for example:

```text
saw-com-optimizer-runs/
  production/
  archive/
  manifests/
  cleanup-backups/
```

Tracked code must not hard-code a user-profile-specific absolute path. Orchestration receives the path explicitly through `--run-root` or `--run-dir` and records the resolved location in the immutable run manifest.

Production storage normally contains:

- optimizer checkpoints and resumable state;
- population/archive dumps;
- dense numerical arrays and large intermediate results;
- run-local continuation/delivery state;
- full stdout/stderr and recovery logs;
- terminal raw result artifacts;
- other data needed for forensic analysis or numerical recovery.

The launch gate rejects relative paths, paths inside any worktree, `.git`, review-publication directories, conflicting destinations, unsafe reparse-point layouts, and paths whose worktree identity cannot be established. It fails closed and never falls back to repository `runs/` for a new production launch.

## 3. Raw-data retention

Raw production data must be retained at least until all of the following are complete:

1. optimizer terminal state is durable;
2. continuation handling is complete or explicitly closed out;
3. canonical review evidence is exported and published;
4. independent scientific review is complete;
5. any required closeout / baseline / experiment-register update is complete.

There is currently no automatic age- or size-based deletion policy. After scientific closeout, raw data may be moved from `production/` to `archive/`, or deleted only through a separate explicit cleanup task with provenance and backup checks appropriate to the run's value. Do not infer permission to delete raw data merely because the optimizer completed or a PR merged.

Important or expensive runs should keep a durable archive or a verified manifest-backed backup. Recovery-critical state is never owned solely by a disposable worktree.

## 4. Active-run registry

Production launch and worktree removal share the repository active-run registry stored in Git common state.

A production record is created before the worker starts and remains a worktree-removal blocker through numerical completion. It is cleared only after review publication has been durably finalized into `REVIEW_WAITING` with matching evidence publication metadata.

A missing, malformed, or unreconciled registry fails closed. Existing repositories must reconcile known external run roots before initializing or repairing the registry.

## 5. Logging policy

Logs are split by purpose rather than copied wholesale into Git.

### Full execution logs

Full stdout/stderr, optimizer logs, callback/queue transport logs, and other verbose process output stay with the external raw run. They are not committed by default.

### Durable diagnostic excerpts

When a detached sender or orchestration step fails, preserve enough bounded, redacted diagnostic evidence to explain the failure after the process exits. At minimum, where applicable, record:

- exit code;
- start and finish timestamps;
- stdout/stderr SHA256;
- bounded UTF-8 excerpts or bounded run-local text files;
- truncation flags;
- executable/version identity.

Do not persist reusable credentials, cookies, OAuth codes, bearer/access/refresh tokens, pairing codes, client secrets, or temporary public endpoints. Redaction applies before diagnostic excerpts are committed or published.

### Engineering decision history

Human-readable decisions belong in Git, not raw process logs. Use the existing history, closeout, experiment-register, and escalation records to preserve why a result was accepted, rejected, blocked, or superseded and which run/commit/evidence supports that decision.

## 6. Canonical GitHub review evidence

The canonical review destination for new production runs is:

```text
reports/experiment_reviews/<stage>/<run_id>/
```

It is committed to the same experiment branch that contains the implementation/configuration used for the run unless a forensic recovery case requires a separate evidence branch.

The package should contain compact evidence such as:

- immutable run/orchestration manifest;
- final status/completion metadata;
- config and protocol snapshots;
- integrity/accounting summaries;
- terminal per-seed/per-cell result and status;
- aggregate comparison tables;
- paired comparisons when the protocol is paired;
- derived convergence evidence;
- bound-pressure / geometry / physical-failure accounting;
- runtime accounting;
- scientific limitations.

The package should exclude by default:

- checkpoint bodies and `B*.json` dumps;
- population/archive dumps;
- large NPZ/NPY or dense raw arrays;
- caches;
- full stdout/stderr;
- callback/queue/Codex rollout logs;
- duplicate raw intermediate outputs;
- other large binary dumps.

When an excluded artifact is scientifically important, derive a compact summary or request an explicit exception rather than silently committing the raw payload.

## 7. Review package gates

The normal package target is:

```text
< 2 MiB
```

The default hard gate is:

```text
< 10 MiB
```

A package that exceeds the hard gate must stop and identify the responsible evidence class. Do not automatically use Git LFS and do not silently remove scientifically necessary evidence.

Before publication, verify at least:

- run ID and source SHA consistency;
- protocol/config fingerprint consistency;
- expected vs completed seed/cell/arm coverage;
- artifact hashes;
- package completeness;
- redaction;
- absence of forbidden large raw artifacts;
- absence of unexpected source/config mutation caused by export.

## 8. Production completion and review flow

The active continuation contract for new production runs is queue-native and exact-thread:

```text
optimizer COMPLETED / FAILED
→ durable one-shot continuation claim
→ codex queue --thread <original_thread_id>
→ same original thread continuation
→ review evidence export
→ commit + push
→ publication finalizer
→ REVIEW_WAITING
→ independent ChatGPT review
```

`original_thread_id` is captured before detach. Session IDs are not queue routing identities. `legacy_resume` and `codex exec resume` remain historical read/recovery concepts and are not valid new-production routing modes.

Sender acceptance is not the same as receiver confirmation. Ambiguous one-shot delivery fails closed rather than being resent blindly.

## 9. Review state semantics

Numerical completion, evidence publication, and scientific acceptance are separate states.

`REVIEW_WAITING` means the terminal run and canonical lightweight evidence have been published and are waiting for independent review. It does not mean the result is scientifically accepted.

External scientific acceptance/rejection is recorded later through GitHub review history, closeout documents, the experiment register, and baseline/roadmap updates as appropriate.

A continuation/publisher must not automatically launch the next production run, promote a topology/design, merge the experiment PR, or rewrite the scientific baseline without later explicit authorization.

## 10. Review roles

- **Codex:** implement, validate, execute an explicitly authorized production run, package/publish evidence, then stop.
- **GitHub:** canonical source/config/provenance/review-evidence surface.
- **ChatGPT:** independent external review of the pushed state.
- **User:** production authorization and major stage/merge decisions.

C2C is frozen and is not part of the active storage, logging, continuation, or review path.

## 11. Legacy review bundles

`artifacts/review_bundles/` and `sawopt.reporting.review_bundle` remain useful for manual packaging of historical or ad-hoc saved runs. They are not the canonical review path for new production studies.

For new production runs, use the canonical `export-review` flow and `reports/experiment_reviews/<stage>/<run_id>/`.

## 12. Operational rule of thumb

Use this simple split:

```text
Git repository
  = code + protocol + compact evidence + decisions

external persistent run root
  = raw/recovery-heavy numerical data + full logs

GitHub review package
  = enough evidence to judge the run without uploading the raw data lake
```

When in doubt, preserve raw data externally and publish a small deterministic derivative to GitHub.