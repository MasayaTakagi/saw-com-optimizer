# Codex Git and worktree preflight

The `SessionStart` hook runs `.codex/hooks/git_workspace_preflight.py` and adds a short diagnostic to startup context. On Windows, the command wrapper requires the project `.venv`; it does not silently switch to a system Python. The check is informational and never changes the branch, refs, index, `FETCH_HEAD`, or working tree.

Run a structured local check from the repository root with the project interpreter:

```powershell
.venv\Scripts\python.exe .codex\hooks\git_workspace_preflight.py --json
```

To compare the current upstream tracking ref with the remote without updating local refs, request an explicit read-only check:

```powershell
.venv\Scripts\python.exe .codex\hooks\git_workspace_preflight.py --json --verify-remote
```

The optional remote check uses `git ls-remote`; it does not run `fetch`. Without `--verify-remote`, remote access and freshness are reported as `UNVERIFIED` and no network request is made.

## Separate the failure classes

- `REPO_TRUST=BLOCKED` means Git rejected the repository because of ownership, usually with `fatal: detected dubious ownership`. This is a `safe.directory` trust issue. If the owner mismatch is expected, add only the exact repository path under the user's approved policy. Never use `safe.directory=*` or change filesystem ownership.
- `GIT_METADATA_WRITE=FAIL` means the active process could not create, flush, close, and remove the temporary probe in a Git metadata directory. This is a filesystem or managed-sandbox write boundary. Adding `safe.directory` does not grant write access.
- `REMOTE_ACCESS=FAIL` means the optional `ls-remote` could not reach or authenticate to the remote. It is separate from local trust and metadata access.
- `REMOTE_FRESHNESS=UNVERIFIED` means no read-only comparison succeeded. Do not infer that `origin/*` is either current or stale.

The metadata probe uses a random name and exclusive creation. It writes and flushes a short temporary file in each distinct Git metadata directory, closes it, and removes it. It does not touch Git-owned files. A cleanup failure is reported with the remaining probe path and requires user attention. A successful directory probe proves only that the tested directory accepted a temporary write; it does not guarantee every Git operation or every individual metadata file is writable.

## Worktree interpretation

The preflight reports the current worktree identity (`PRIMARY` or `LINKED`), its Git directory, common Git directory, registration and lock state. Linked worktrees share the common Git metadata directory. A separate worktree path therefore does not bypass a write denial in the common `.git` directory. Worktree creation also needs a writable destination parent, which this current-worktree check does not create or modify.

Before parallel work, confirm all of the following in the same managed execution boundary:

1. `REPO_TRUST=PASS` and the intended repository, branch, and HEAD are visible.
2. `GIT_METADATA_WRITE=PASS`; otherwise do not attempt branch, commit, fetch, or worktree creation.
3. The destination parent is writable under the already-approved sandbox boundary.
4. If remote freshness matters, `--verify-remote` reports `REMOTE_ACCESS=PASS` and an explicit freshness result.
5. Existing worktrees are clean or their owners and dirty changes are understood. Never repurpose an active worktree.

Do not resolve metadata denials by changing ACLs, ownership, administrator elevation, broad Codex writable roots, or Windows security settings. If a required Git operation is available only under the normal user and not `CodexSandboxOffline`, report `USER_ACTION_REQUIRED` with a narrow command proposal. Do not launch a normal-user shell or request broader sandbox access from the preflight.

Results are specific to the current execution boundary. Re-run preflight for each new managed task; do not carry a previous task's result forward.
