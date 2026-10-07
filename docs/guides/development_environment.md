# Official development environment

Use WSL2 Ubuntu 24.04, VS Code Remote WSL, Codex CLI running inside Ubuntu,
and uv. The verified versions on 2026-10-07 are Ubuntu system Python 3.12.3
(`/usr/bin/python3.12`) and uv 0.12.23. Use Ubuntu's Python 3.12 series;
uv-managed Python is not part of this migration.

## Setup for every worktree

Install Ubuntu's `python3.12` package if missing.
Install uv independently (the standalone binary requires no Node). Use the
existing Linux Codex CLI installation. For a host missing the prerequisites:

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends python3.12 curl ca-certificates
curl -LsSf https://astral.sh/uv/0.12.23/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
/usr/bin/python3.12 --version
```

Open the Linux checkout with VS Code
Remote WSL and run project commands in its Ubuntu terminal.

Place clones and worktrees on the Linux filesystem under `/home/...`, never
under `/mnt/c/...`. Keep Linux `~/.codex` independent from Windows
`%USERPROFILE%\.codex`; do not copy, symlink, or share them. Windows Codex
Desktop's WSL Agent is not an official development entry point. Do not
install Node for this setup.

From the new worktree root:

```bash
uv sync --locked --extra test
uv run --locked pytest
uv run --locked python -m sawopt --help
```

No activation, manual `venv` creation, or editable pip installation is needed.
uv creates a separate ignored `.venv` in each worktree and installs the
project and test extra using the tracked lockfile. `.python-version` selects
3.12; `uv.toml` restricts interpreter discovery to system Python and disables
Python downloads. Missing system Python blocks setup rather than triggering
a managed-Python download. `pyproject.toml` remains the dependency declaration;
`uv.lock` records resolved dependencies. Update the lockfile deliberately when
dependencies change, and review that change separately. Do not share `.venv`
between Windows, Linux, or worktrees.

uv creates environments itself ([uv environment documentation](https://docs.astral.sh/uv/pip/environments/))
and does not invoke stdlib `venv`/`ensurepip`;
`python3.12-venv` is not required. Python support is `>=3.12,<3.13`.
`uv.toml` requires exactly uv 0.12.23; project sync/run/lock commands reject
other versions in local, bootstrap, and CI workflows.

Root `.venv/` is disposable only after the worktree safety inventory confirms
a real uv environment and no other blockers. Internal POSIX symlinks are
unlinked without following their targets; external symlinks/reparse points block. See
[worktree safety](worktree_safety.md) before cleanup.

## Validation boundary

The initial migration parity check used
`uv sync --locked --no-python-downloads --extra test`, matched the previous
environment's main dependency versions, and passed 366 tests with one skip.
That historical count records the initial parity run; it is not the current
test-suite count and does not establish final WSL qualification.
`tools/wsl/qualify-core.sh` intentionally blocks when multiple worktrees
exist: do not run it while this migration worktree exists. Final qualification
requires a later clean single-worktree checkout and separate execution.
Linux production orchestration/storage qualification remains a separate gate;
this environment change does not authorize production runs.

PowerShell launchers under `scripts/` are retained for historical Windows
saved-run workflows only. Older commands under `docs/history/`, `docs/handoff/`,
and frozen `docs/c2c/` record historical procedures, not current setup.

CI also uses Ubuntu 24.04's system Python and the same locked sync/test
commands, with uv 0.12.23. The interpreter policy follows the
[uv settings reference](https://docs.astral.sh/uv/reference/settings/), and
CI setup follows [uv's GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/).
