# Git / worktree sandbox qualification report

Date: 2026-09-29

## Capability matrix

| Capability | Result | Evidence |
|---|---|---|
| Execution identity | `DESKTOP-9IPACE7\CodexSandboxOffline` (SID ending `-1004`) | `whoami /user` |
| Normal-user boundary | `UNVERIFIED` | The repository owner reported in the earlier Git ownership error was `DESKTOP-9IPACE7\sub` (SID ending `-1002`). This session did not run commands as that user. |
| Repository trust | `PASS` for the canonical repository | `git status`, `rev-parse`, and worktree inspection succeeded in this boundary. The C2C checkout required exact-path safe-directory entries before its Git read-only inspection succeeded. |
| safe.directory | Exact paths visible; no broad `*` entry | Exact entries were added for the C2C checkout and four existing managed worktree paths. The canonical root was also supplied by command-line safe-directory values. No wildcard `*` was added. |
| Git metadata read | `PASS` | `status`, `rev-parse`, branch, common Git directory, and worktree listing succeeded. |
| Git metadata write | `FAIL` | `git fetch origin` was denied opening `.git/FETCH_HEAD`. The new preflight's exclusive temporary-file probe was also denied at the canonical `.git` directory and left no file. |
| `git fetch` | `FAIL` in this boundary | Stopped with `.git/FETCH_HEAD: Permission denied`; no successful fetch was observed. |
| Remote access | `FAIL` for the read-only probe | `git ls-remote --heads origin main` could not connect to `github.com:443`. |
| Remote freshness | `UNVERIFIED` | No successful remote comparison completed. The locally stored `main` and `origin/main` initially matched, but that does not establish current remote freshness. |
| Existing worktree read | `PASS` after exact safe-directory entries | Worktree listing and status were readable. Two pre-existing managed worktrees were dirty and left untouched. |
| New worktree creation | `NOT ATTEMPTED — prerequisite failed` | The linked worktree would share the canonical common `.git`; metadata write capability failed. No create attempt or retry was made. |
| Branch creation / commit | `NOT ATTEMPTED — metadata write blocked` | Both require writes to common Git metadata. No branch, commit, or ref update was attempted. |
| Push | `UNVERIFIED` | No push was attempted; remote access failed independently. |

## Boundary evidence and limits

The canonical `.git` and `FETCH_HEAD` ACL inspection showed inherited permissions and unresolved deny ACE SIDs. Python's `os.access(..., W_OK)` reported `True` for both paths, while the actual Git fetch and the exclusive write probe were denied. Therefore the effective result must come from a direct, carefully scoped probe in the active execution boundary; ACL output and `os.access` alone did not explain or predict it here. No ACL, owner, security setting, or sandbox writable root was changed.

The C2C checkout was inspected as a Git repository only. No C2C doctor/session/record command, checkpoint operation, C2C conversation action, or tunnel operation was performed. No Stage 4A run, artifact, checkpoint, process, or file was intentionally changed.

At the start of inspection the canonical checkout reported `main`, HEAD `fb7bcbd8bddce6f9841798ce38557977a4345341`, and a clean tree. Later, the new preflight reported branch `codex/stage4a-hybrid-protocol`, the same HEAD, and a dirty tree. This indicates that the active Stage 4A task was using or changing the canonical checkout. No further Git inspection of that checkout was done after detecting this change, and no diff was read.

## Implementation and validation

The implementation, hook registration, documentation, and tests are preserved in `parallel_git_worktree_preflight.patch`. Targeted tests were run with the project's `.venv` interpreter: **14 passed**. Tests use temporary repositories, including a linked worktree, and simulate ownership, metadata-write, and remote-access failures.

Status: `IMPLEMENTATION_COMPLETE_OR_PARTIAL` / `GIT_METADATA_WRITE_BLOCKED` / `USER_ACTION_REQUIRED`. The patch was not applied to the canonical or Stage 4A checkout, and no branch/worktree/commit/push was created. It is ready for a user-controlled clean worktree once the active Stage 4A checkout and the required Git write boundary are resolved.
