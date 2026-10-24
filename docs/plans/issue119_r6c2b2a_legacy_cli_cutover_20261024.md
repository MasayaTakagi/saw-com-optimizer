# Issue #119 — legacy CLI and orchestration launch cutover

**Status:** `OWNER_APPROVED_BREAKING_CUTOVER / EXPORT_REVIEW_KEEP / DRAFT_PR_STOP`

**Base:** `d13917e13074620f85c19634d7eb776f4fb6d65f` (PR #120 merge; merged-main
CI #40100838324 passed 744/744 on Haswell). Implementation branch:
`issue119-r6c2b2a-cli-cutover`.

This is a software-only deletion of obsolete `python -m sawopt` scientific
commands and the coupled detached legacy-orchestration launch/worker. It does
not authorize COM/FE or optimizer work, a study, a historical run operation,
process inspection, or access to external raw/checkpoint data. Breaking old
CLI/script compatibility is explicitly accepted by the owner.

## Source/caller disposition

| Source / symbols | Checked-in caller and test disposition |
|---|---|
| `src/sawopt/__main__.py`: `simulate`, `optimize`, `sweep`, `report`, `run-study`, `stage4b-shakedown`, legacy parser defaults, `_run_study`, `_refinement_points` | Replaced with an `export-review`-only dispatcher. Removed old scientific/config/report imports, parser options, config loading, output initialization, COM/optimizer dispatch and old lifecycle completion. `python -m sawopt export-review --run PATH [--destination PATH]` delegates directly to `reporting.github_review.main`. Negative tests ensure every retired command is rejected before an output path is created. The independent synthetic `sawopt` / `python -m sawopt.cli` interface is unchanged. |
| `orchestration.cli`: `launch`, `launch --resume`, `recover`, `worker`, `_build_optimizer_command`, resume checkpoint and run-registration helpers | Parser now exposes only recorded `status` and guarded `mark-review-published`. The retired commands are rejected by argparse before config reads, run/registry writes, or subprocess creation. Removed the `python -m sawopt run-study` command construction and detached worker dispatch. Tests retain and pin both surviving CLI routes. |
| `orchestration.worker`, `orchestration.process_runner`, `run_manager.create_run` | Deleted: static source search found their only runtime callers were the removed old orchestration launch/resume/worker dispatch. Their worker execution, subprocess-launch tests, worker-only status/checkpoint finalization tests, and new legacy-run creation helper were retired with that runtime, not migrated to the synthetic worker. The independent `orchestration.pid_utils` implementation remains; `administrative_closeout` now imports it directly. PID liveness, worktree, registry, storage, closeout, and status/publication behavior remain under their existing owners. |
| `studies.audits.stage3_9b_budget_extension` preflight `launch_command` field | Removed the emitted command to the retired `orchestration.cli launch` route and its conditional-launch text. The read-only audit/projection/verifier code and stored reports remain unchanged; this PR does not execute the audit or inspect its run inputs. |
| Legacy run/report/checkpoint modules | Retained `reporting.github_review::{main,export_review,load_review_spec}`, `reporting.experiment_review` (R5, separate schema), `run_manager` status/locks/publication/completion, administrative closeout, `active_runs`, `worktree_safety`, `persistent_storage`, `pid_utils`, `io.checkpoints`, and historical `RunManifest` parsing. Direct current consumers include review export, closeout, worktree safety, `studies.hybrid`, and `optimization` checkpoint sessions. The launch-only `run_manager.create_run` helper was removed; tests seed their historical records directly. No stored reports, source identities, raw runs, checkpoints, or manifests were modified. The `io.checkpoints.complete_study_run` docstring now describes its retained direct-study and legacy-manifest behavior; runtime semantics are unchanged. |

## Tests and documentation

- Added focused negative coverage for the six removed `python -m sawopt`
  commands; `orchestration.cli` launch, launch-resume, recover, and worker
  rejection before config/file/registry/process side effects; and successful,
  invalid-fixture, and conflicting-destination `export-review` behavior.
- Kept tests for the synthetic CLI, Q1-A public/leaf goldens and import guards,
  current R2–R4 scientific regressions, R5, export redaction/hash/status and
  publication distinctions, administrative closeout, PID/worktree/storage
  safety, and Stage 4B/4C frozen/rejection contracts. Removed only tests whose
  subject was the deliberately deleted old CLI, legacy run creation/worker, or
  detached process launcher; administrative-closeout and run-state tests now
  seed their own historical records. The exact collected-test delta is
  reported from CI.
- Updated current CLI/environment/architecture/review documentation and the
  active command examples. Dated inventories, historical plans, reports and
  evidence are not rewritten. No old route is aliased to the synthetic CLI or
  R5 schema.

## Validation and delivery record

- Base merged-main Haswell CI: [Actions #40100838324](https://github.com/miyabimm/saw-com-optimizer/actions/runs/40100838324), exact base SHA above, **744/744 passed**.
- Local `git diff --check` and `/usr/bin/python3.12 -m compileall -q src tests` are
  required. The dedicated worktree has no `.venv`; local pytest will not be run
  using another worktree's editable environment, and no environment sync/install
  is performed without approval.
- Exact PR-head full locked Haswell CI and final collected/passed counts: to be
  recorded in the Draft PR / Issue #119 handoff after publication.
- Changed files: `AGENTS.md`, `README.md`, `scripts/README.md`,
  `docs/README.md`, `docs/architecture.md`, `docs/development.md`,
  `docs/guides/{development_environment,github_review_workflow,review_bundles}.md`,
  this plan, `src/sawopt/__main__.py`, `src/sawopt/io/checkpoints.py`,
  `src/sawopt/orchestration/{__init__,administrative_closeout,cli,run_manager}.py`, deleted
  `src/sawopt/orchestration/{process_runner,worker}.py`,
  `src/sawopt/studies/audits/stage3_9b_budget_extension.py`, and the focused
  CLI/export/orchestration/PID/Stage4C and administrative-closeout test
  updates and deletions. The administrative-closeout fixture now creates its
  historical manifest/status
  bytes directly rather than using the retired run-creation helper.

**Operational note:** an initial relative-path `git rm` ran in the Issue #71
worktree rather than this dedicated worktree. The four intended deletions were
immediately restored from that worktree's `HEAD`; its index and worktree status
were verified clean, with no commit or push. The subsequent deletion was run
from the verified Issue #119 root; all implementation edits are confined to
this worktree.

**Rollback:** revert the complete reviewed squash merge if necessary. Do not
restore a deleted worker by manipulating historic run state, or repair, migrate,
resume, overwrite, or delete historical/external data. No scientific execution,
Stage 4C run, live-worker inspection, COM/FE evaluation, or optimizer study was
performed or authorized by this change.

**Stop:** one dedicated Draft PR linked to #119, #117, #113, and #118; stop for
independent GitHub review. Do not mark Ready, merge, begin R7/Q1, or launch any
scientific work.
