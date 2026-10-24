# Git worktree safety

Git worktrees are disposable source checkouts. `git status --short` only reports
Git-visible changes; it does not prove that ignored raw runs, test state, logs,
or other local files are absent.

This guide documents retained worktree and data-safety mechanisms, not a
supported production launcher. PR #109 retired the old orchestration launch,
Codex continuation, and Stage 4B/4C production routes. R5 raw/review storage is
future-only and tested synthetically; it is not wired to a production runner.
Follow [`../experiments.md`](../experiments.md) for current storage contracts
and authorization. For the overview, see
[`data_storage_logging_review_policy.md`](data_storage_logging_review_policy.md).

## Durable run storage

The retained safety implementation validates persistent paths for legacy
control records and protects worktree removal. This does not make retired
launch commands supported or authorize a new run. Any future R5 store use must
follow the external `SAWOPT_DATA_ROOT`, containment, identity, exclusivity, and
fail-closed rules in `experiments.md`; it must not fall back to repository
`runs/`.

Historical orchestration manifests may contain old `external_persistent_v1`
fields and review paths. They remain records, not a current R5 schema or a
production-run procedure. Do not rewrite, migrate, or resume them under this
guide.

## Active-run registry and worktree protection

The active-run registry, PID/process checks, path validation, locks, and
worktree-removal protections remain independent safety owners. PR #109 did not
remove them, and C2A must not weaken them. Old launch/review commands and
publication finalizers described by historical run records are not active
operations. Registry presence is not proof that all external or unregistered
runs are known; never infer global absence from a repository-only check.

The following registry initialization operation is retained for the existing
safety utility, but it is not an experiment authorization and does not scan
arbitrary external disks. Only perform it under its own explicitly approved
operational scope:

```bash
uv run --locked python scripts/worktree_safety.py initialize-registry \
  --confirm-no-unregistered-active-runs
```

Initialization does not scan arbitrary external disks. The confirmation is an
explicit operator assertion that prior runs have been reconciled. Missing,
unreadable, or malformed registry data blocks any caller attempting active-run
registration and blocks worktree removal. Do not delete stale records based
only on optimizer state; investigate referenced control metadata under an
explicitly authorized scope. Registry operations and the remover's final audits
plus `git worktree remove` share one lock in the Git common directory, so a
registered run cannot race the final removal check.

## Audit before removal

Use the repository utility before considering a worktree removable:

```bash
uv run --locked python scripts/worktree_safety.py audit <absolute-worktree-path>
uv run --locked python scripts/worktree_safety.py remove <absolute-worktree-path>
```

The removal command repeats its full audit and worktree-identity check
immediately before calling plain `git worktree remove`. Tracked modifications,
untracked files, ignored files (including caches), protected raw-data paths,
reparse points, inaccessible paths, incomplete inventories, primary checkouts,
and unregistered residual directories block removal. If Git removal errors or
leaves a deregistered directory, the utility does not perform filesystem
cleanup. Preserve the residual and investigate separately. Do not use
`git clean` as a cleanup shortcut.

## Disposable uv environment

Only the worktree root `.venv/` is disposable. It must be a real directory with
an ordinary `pyvenv.cfg` containing the pinned uv marker (`uv = 0.12.23`).
Unrecognized environments remain nontracked-data blockers. Audit never deletes.
The full inventory still blocks inaccessible entries, mount points, protected
runs/checkpoints/logs, tracked changes, active runs, and every other ignored or
untracked path (including nested `.venv` directories).

Inside this verified subtree, POSIX symlinks are leaf entries: inventory never
follows them, and fd-safe `shutil.rmtree` unlinks them without deleting their
file or directory targets. No per-link allowlist is needed. The `.venv` root
itself and every link/reparse point outside it still block; Windows reparse
points remain blocked. Platforms without symlink-safe removal fail closed.
After two successful audits and identity checks under the shared launch lock,
remove deletes only `.venv`, then re-audits before plain Git worktree removal.
A cleanup failure preserves the worktree and prevents Git removal.
