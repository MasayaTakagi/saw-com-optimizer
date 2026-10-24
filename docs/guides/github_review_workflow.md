# GitHub review workflow

> **Historical operational details:** Issue #108 retires the legacy Codex
> queue/callback and Stage 4B/4C execution routes. Do not use Codex handoff,
> automatic callback, or old orchestration commands described below. The
> repository review boundary remains GitHub PRs; see the
> [current index](../README.md) and [Issue #108 scope](../plans/issue108_r6c1_codex_removal_20261024.md).

This guide defines the active repository review path for `saw-com-optimizer`.
ChatGPT independently reviews the pushed GitHub state; Pi Code implements
scoped software changes, validates them, and publishes a Draft PR for review.
Scientific execution and project-stage transitions remain separately gated by
the user and [`../experiments.md`](../experiments.md). C2C is frozen and is not
part of this workflow.

The GitHub branch, commit, and PR are the review surface. A local-only diff or a
Codex self-review is not independent external review.

For the canonical data-storage/logging split used by this workflow, see
[`data_storage_logging_review_policy.md`](data_storage_logging_review_policy.md).
The package-level evidence contract is
[`postrun_review_contract.md`](postrun_review_contract.md).

## Roles

Use the following separation of responsibility.

- **Pi Code:** implement and validate scoped changes, then publish a Draft PR
  and stop for independent review. It does not launch production or scientific
  runs without separate user authorization.
- **GitHub:** canonical review surface for source, configuration, provenance,
  lightweight experiment evidence, and closeout history.
- **ChatGPT:** independently review the pushed source/evidence and make the
  scientific/engineering disposition.
- **User:** authorize production execution and decide material scientific
  changes, project-stage transitions, and merge acceptance.

The retired Codex queue/callback is not an evidence-publishing or review
mechanism. A report's existence does not mean it was independently reviewed or
scientifically accepted. No topology promotion, baseline update, follow-up run,
or merge is implied by software validation.

## Code and documentation changes

Use this sequence for a meaningful work unit:

```text
ChatGPT / user plan
→ Codex implementation and relevant validation
→ commit on a review branch
→ push branch to GitHub
→ report branch, commit SHA, and PR or commit URL
→ ChatGPT reviews the GitHub diff, files, and committed validation evidence
→ Codex makes focused corrections and pushes them
→ ChatGPT reviews the update
→ user accepts and authorizes merge or the next project stage
```

Keep the PR focused on the reviewed work unit. Do not merge it until review and
user acceptance unless the user explicitly delegated that merge in the current task.

## Experiment branch model

For a normal production study, prefer one experiment branch/PR rather than a
separate result-review branch:

```text
experiment branch
├─ implementation/config/preflight commits
├─ production execution source SHA  ← frozen in run manifest
├─ post-run review-evidence commit
├─ externally requested corrections, if any
└─ closeout documentation commit
```

The branch HEAD may advance after the run. The immutable
`execution_source_sha` recorded in the run manifest remains the source that
actually produced the numerical result.

A separate evidence branch is an exception for recovery, forensic preservation,
or an unwritable/blocked production worktree. Do not make it the default path.

## Experiment implementation review

Before a production run, commit and push the implementation and exact
configuration needed to understand the run. Make these items available for
review when applicable:

- implementation and configuration;
- preflight result and production authorization gate;
- evaluation budget, seeds, and comparison conditions;
- checkpoint and continuation policy;
- external raw output path and expected review-evidence path;
- relevant validation summary and source provenance;
- exact production execution source SHA.

ChatGPT can review the GitHub state before launch. This does not replace the
user's separate authorization to start production.

## Retired Codex continuation

Issue #108 removes the active Codex queue/callback transport and disables the
legacy Stage 4B/4C production entrypoints. Do not launch, resume, recover,
confirm, or publish through the retired commands described in historical
materials. No replacement continuation transport is part of this change.

Historical manifests and review packages remain evidence. Their recorded
continuation or review state is not newly validated, and this workflow does not
rewrite them. See the [Issue #108 scope](../plans/issue108_r6c1_codex_removal_20261024.md)
and the [historical async-orchestration notice](async_orchestration.md).

## Experiment result review

After a run, Codex publishes a deterministic lightweight review directory in the
canonical location:

```text
reports/experiment_reviews/<stage>/<run_id>/
```

Existing historical review directories such as the Stage 4B
`reports/stage4b_production_review/...` path remain valid historical evidence;
do not move them merely to conform to the new convention.

The required review package and exclusion rules are defined in
[`postrun_review_contract.md`](postrun_review_contract.md). In summary, the
package must contain enough text/JSON/CSV evidence for an independent GitHub
review while excluding large checkpoints, population dumps, raw caches, and
full process logs.

A passing smoke/parity/integrity check does not by itself establish a topology
ranking, feasible design, production optimum, or convergence result.

## Review states

Keep numerical completion, orchestration delivery, publication, and external
scientific review separate.

The intended terminal handoff state for an externally reviewable run is:

```text
REVIEW_WAITING
```

`REVIEW_WAITING` means the canonical package is published and waiting for
independent review. It does not mean the result is scientifically accepted.
Scientific acceptance/rejection is recorded later by GitHub review/closeout
history, the experiment register, and baseline/roadmap changes when applicable.

## Large data and logs

Do not use the PR as a raw-data transport mechanism. Production checkpoints,
populations, dense arrays, full stdout/stderr, and other recovery-heavy data stay
in the external persistent run root. GitHub receives compact deterministic
summaries and hashes sufficient for independent review.

If review requires information absent from the compact package, derive a bounded
summary from the raw run or request an explicit exception. Do not silently upload
the raw data lake.

## Development environment and Git handling

The official development environment is WSL2 Ubuntu 24.04 with VS Code Remote
WSL, Pi Code running inside Ubuntu, Ubuntu system Python 3.12, and uv. Keep
checkouts/worktrees under `/home/...`; do not use Windows-native project
commands or place active worktrees under `/mnt/c/...`. Follow the
[development environment guide](development_environment.md) for setup and
locked project commands. This workflow documentation does not change the
official development environment during any tool pilot.

When Git metadata writes require permission escalation, use only the smallest
on-request operation needed for the requested branch, commit, worktree, fetch,
or push. Do not use standing Full Access, change `.git` ACLs, force-push, or
discard existing work.
