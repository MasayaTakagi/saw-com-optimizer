# GitHub review workflow

This guide defines the active repository review path for `saw-com-optimizer`.
ChatGPT reviews the pushed GitHub state; Codex implements changes and reports
local validation. C2C is frozen and is not part of this workflow.

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

The GitHub branch, commit, and PR are the review surface. Do not rely on a
local-only diff as evidence that ChatGPT can inspect. Codex's own validation
and explanation do not count as independent review. Keep the PR focused on the
reviewed work unit, and do not merge it until review and user acceptance.

## Experiment implementation review

Before a production run, commit and push the implementation and the exact
configuration needed to understand the run. Make these items available for
review when applicable:

- implementation and configuration;
- preflight result and production authorization gate;
- evaluation budget, seeds, and comparison conditions;
- checkpoint and continuation policy;
- output path and expected evidence;
- relevant validation summary and source provenance.

ChatGPT can review the GitHub state before launch. This review does not replace
the user's separate authorization to run an experiment, and a completion
notification does not authorize another production run. Long runs continue to
use the orchestration and manifest requirements in
[`async_orchestration.md`](async_orchestration.md).

## Experiment result review

After a run, commit a lightweight closeout record containing the summary,
manifest metadata, result tables needed for the decision, validation status,
decision evidence, and provenance. Keep raw checkpoints and very large run
artifacts out of GitHub when they are unsuitable for version control. Follow
the existing data-management policy and provide a review bundle or other large
evidence through a user-mediated channel when necessary.

Preserve the distinction between implementation acceptance and scientific
conclusions. A passing smoke or parity check does not by itself establish a
topology ranking, feasible design, or production optimum.

## Git handling

The Windows-native Codex workflow remains the project default. Perform normal
work in the standard sandbox. When Git metadata writes require permission
escalation, use only the smallest on-request operation needed for the user
requested branch, commit, or push. Do not use standing Full Access, change
`.git` ACLs, force-push, or discard existing work.
