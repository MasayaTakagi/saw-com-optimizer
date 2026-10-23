# Legacy and evidence scripts

This file is an inventory of retained scripts, not a current scientific-run
procedure. The authoritative current operating and authorization policy is in
[docs/README.md](../docs/README.md), especially
[development](../docs/development.md) and
[experiments/data](../docs/experiments.md). A script, config, old handoff, or
passing fixture does not authorize COM/FE, optimizer research, production, Q1
qualification, or historical-data access.

The `scripts/` tree mixes historical analysis/launch artifacts with evidence
verifiers. Preserve source-identity, parity, golden-fixture, and import-boundary
verifiers until their evidence disposition has been reviewed. Do not run
historical launchers or edit/migrate their raw inputs as part of R6.

The active **software-only** R6 CLI is `uv run --locked sawopt` or
`uv run --locked python -m sawopt.cli`; it currently supports only strict
synthetic configuration validation and an explicitly requested synthetic
fixture. It requires an external `SAWOPT_DATA_ROOT` for a run and does not
invoke COM/FE. The separate legacy `python -m sawopt` dispatcher is not this
new CLI and remains subject to the R6 caller/gate disposition.

`worktree_safety.py` delegates to the retained safety implementation in
`sawopt.orchestration.worktree_safety`; see
[the worktree safety guide](../docs/guides/worktree_safety.md). Preserve this
safety path until a reviewed replacement exists.
