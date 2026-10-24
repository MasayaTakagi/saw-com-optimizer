# Official development environment

Use Ubuntu/WSL2 with Python 3.12 and the project-locked `uv` environment. The
current project implementation/review workflow is Pi Code plus GitHub Draft
PRs; a local Codex CLI, C2C checkout, project-local hook, provider startup, or
agent-session continuation is not required or supported by this guide. Keep
worktrees under `/home/...`, not `/mnt/c/...`. The currently verified host
versions are recorded in the project history; this guide does not claim a
separate WSL qualification.

## Setup for a new worktree

Use the project-prescribed Ubuntu system Python and uv 0.12.23. Follow the
project lockfile and do not install Node or a Python-managed interpreter. From
a fresh worktree root, the standard environment setup is:

```bash
uv sync --locked --extra test
```

For normal project commands, use the locked environment:

```bash
uv run --locked pytest
uv run --locked python -m sawopt --help
```

This general setup instruction does not authorize execution of a scientific
study. In an already configured environment where dependency synchronization
is not approved, do not run `uv sync`; report the missing dependency as a
validation blocker instead.

Do not manually create or share virtual environments. Keep `.python-version`
and `uv.lock` tracked and never commit `.venv/`. `uv.toml` restricts interpreter
discovery to system Python and disables Python downloads; missing prerequisites
block setup rather than triggering an unreviewed managed-Python download.

## Retained safety and archived qualification tooling

Before removing a worktree, follow the
[worktree safety guide](worktree_safety.md). Its active-run registry, path,
process, lock, and data protections are separate safety responsibilities; do
not weaken them as part of environment cleanup.

`tools/wsl/` and [`../qualifications/wsl2_core_qualification.md`](../qualifications/wsl2_core_qualification.md)
are historical qualification artifacts, not the current setup path. Some
scripts install or invoke the retired Codex CLI and exercise legacy Stage 4B/4C
code. Do not run those scripts without a separately reviewed, explicit owner
authorization and a new compatibility disposition. They were not modified or
executed as part of Issue #111.

For current project policy, use [`../README.md`](../README.md),
[`../development.md`](../development.md), and
[`../experiments.md`](../experiments.md).
