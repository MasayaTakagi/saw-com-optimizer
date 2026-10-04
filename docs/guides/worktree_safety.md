# Git worktree safety

Git worktrees are disposable source checkouts. `git status --short` only reports
Git-visible changes; it does not prove that ignored raw runs, test state, logs,
or other local files are absent.

For the canonical storage/logging/review split, see
[`data_storage_logging_review_policy.md`](data_storage_logging_review_policy.md).

## Durable run storage

New user-authorized or ranking-eligible production runs must use an absolute
persistent output location outside every registered Git worktree. Pass an
existing external root with `--run-root`; orchestration creates a unique
`<run_id>` child. An absolute `--run-dir` is also accepted. The launch gate
checks all registered worktrees, `.git`, canonical review publication output,
path reparse points, destination uniqueness, and parent writability before run
creation. Git discovery and path checks fail closed. An invalid production
path never falls back to repository `runs/`.

The raw orchestration and optimizer output, checkpoints, populations, raw logs,
and recovery-critical artifacts belong in persistent storage. A lightweight
review package remains under
`reports/experiment_reviews/<stage>/<run_id>/` in the source repository. New
production manifests record `run_storage_policy: external_persistent_v1`, the
persistent root, repository root, and source worktree. Historical manifests
without these optional fields remain readable.

## Active production worktree protection

New production launches also require the shared active-run registry in Git's
common directory. Before reserving a run directory, claiming Stage 4B
authorization, or starting the worker, launch records the run ID, external run
directory, source worktree, branch, and source commit. The record remains a
removal blocker even after optimizer completion. It is removed only after
`mark-review-published` has durably moved the run to `REVIEW_WAITING` with
`review_evidence_state: PUBLISHED`; repeating that publication command can
clear a marker left behind by an interrupted finalization.

For an existing repository, initialize the registry only after reconciling
every known external production-run root and confirming there are no active
unregistered runs:

```powershell
python scripts/worktree_safety.py initialize-registry `
  --confirm-no-unregistered-active-runs
```

Initialization does not scan arbitrary external disks. The confirmation is an
explicit operator assertion that prior runs have been reconciled. Missing,
unreadable, or malformed registry data blocks both production launch and
worktree removal. Do not delete stale records based only on optimizer state;
investigate the referenced run and publication state first. Launch registration
and the remover's final audits plus `git worktree remove` share one lock in the
Git common directory, preventing a new production run from racing the final
removal check.

## Audit before removal

Use the repository utility before considering a worktree removable:

```powershell
python scripts/worktree_safety.py audit <absolute-worktree-path>
python scripts/worktree_safety.py remove <absolute-worktree-path>
```

The removal command repeats its full audit and worktree-identity check
immediately before calling plain `git worktree remove`. Tracked modifications,
untracked files, ignored files (including caches), protected raw-data paths,
reparse points, inaccessible paths, incomplete inventories, primary checkouts,
and unregistered residual directories block removal. If Git removal errors or
leaves a deregistered directory, the utility does not perform filesystem
cleanup. Preserve the residual and investigate separately. Do not use
`git clean` as a cleanup shortcut.
