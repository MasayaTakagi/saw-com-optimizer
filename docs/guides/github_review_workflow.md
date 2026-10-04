# GitHub review workflow

This guide defines the active repository review path for `saw-com-optimizer`.
ChatGPT reviews the pushed GitHub state; Codex implements changes, validates them,
and publishes review evidence. C2C is frozen and is not part of this workflow.

The GitHub branch, commit, and PR are the review surface. A local-only diff or a
Codex self-review is not independent external review.

## Roles

Use the following separation of responsibility.

- **Codex:** implement, validate, execute an explicitly authorized production
  run, export the required lightweight review evidence, commit/push it, and stop.
- **GitHub:** canonical review surface for source, configuration, provenance,
  lightweight experiment evidence, and closeout history.
- **ChatGPT:** independently review the pushed source/evidence and make the
  scientific/engineering disposition.
- **User:** authorize production execution and accept major project transitions
  or merges.

A post-run Codex continuation is therefore an **evidence publisher**, not the
final scientific reviewer. It must not silently promote a topology, update the
current scientific baseline, launch a follow-up production run, or merge the
review PR before external review.

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
user acceptance.

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
- output path and expected review-evidence path;
- relevant validation summary and source provenance;
- exact production execution source SHA.

ChatGPT can review the GitHub state before launch. This does not replace the
user's separate authorization to start production.

## Post-run continuation contract

New production runs must not use a dedicated legacy `codex exec resume`
callback as the normal completion path. The required target contract is:

```text
optimizer completion
→ durable one-shot continuation claim
→ exact original Codex thread ID captured before detach
→ codex queue --thread <original-thread-id> --message <bounded handoff>
→ same original thread resumes
→ Codex exports/pushes review evidence
→ REVIEW_WAITING
→ STOP for external ChatGPT review
```

Session IDs and thread IDs are distinct identities. Queue delivery must use an
explicit thread ID. New manifests must not reinterpret a session ID as a queue
thread target.

Until the queue-native implementation is integrated and re-qualified on the
active orchestration branch, **new long-running production experiments are
blocked**. Historical legacy-resume support may remain readable for old run
manifests, but it is not an approved launch mode for a new production study.

See [`postrun_review_contract.md`](postrun_review_contract.md) for the review
artifact and completion contract.

## Experiment result review

After a run, Codex must publish a deterministic lightweight review directory in
this canonical location:

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

Keep orchestration delivery state separate from external review state.

The orchestrator may establish that a run is complete and that a continuation
message was sent/received. It must not label the scientific result `REVIEWED`
merely because a Codex callback/continuation process exited successfully.

The intended terminal handoff state for an externally reviewable run is:

```text
REVIEW_WAITING
```

Scientific acceptance/rejection is then recorded by GitHub review/closeout
history, not inferred from continuation process success.

## Git handling

The Windows-native Codex workflow remains the project default. Perform normal
work in the standard sandbox. When Git metadata writes require permission
escalation, use only the smallest on-request operation needed for the requested
branch, commit, worktree, fetch, or push.

Do not use standing Full Access, change `.git` ACLs, force-push, or discard
existing work.
