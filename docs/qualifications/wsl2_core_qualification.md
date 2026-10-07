# WSL2 core qualification

## Current development status

The official environment is now [WSL2 Ubuntu + uv](../guides/development_environment.md),
with VS Code Remote WSL and Linux Codex CLI, using Ubuntu system Python 3.12.
The setup below records the original Windows-to-WSL qualification preparation;
its Case A inventory is historical, not the current WSL installation status.
The bootstrap now uses `uv sync --locked --extra test`, with system-only Python
and no Python downloads. Do not run final `qualify-core.sh` while this migration
worktree exists: multiple worktrees intentionally trigger `WORKTREE_BASELINE`.
No final WSL qualification is claimed by the environment formalization.

## Historical scope and stop point

This procedure prepares a fresh Ubuntu 24.04 environment for the SAW
repository and checks whether Codex CLI can work reliably from the Linux
filesystem. The current Windows checkout, Windows virtual environment, and
Windows `%USERPROFILE%\.codex` remain the rollback baseline. The Linux
checkout is a separate clone under `~/src/saw-com-optimizer`; Linux Codex
state is independently created under `~/.codex` after first sign-in.

The present preparation stops before enabling Windows features or installing
WSL. The preflight found WSL absent (Case A). Read-only optional-feature
queries require elevation on this host, so firmware virtualization and the
Windows feature states remain unknown pending the user's administrator gate.
No administrator command, restart, Ubuntu first launch, Linux account setup,
or authentication was performed.

The inventory identified Windows 10 Pro, display version 25H2, build
26200.9550, x64, while Python's `platform.platform()` labels that build
`Windows-11-10.0.26200-SP0`. This is recorded as an OS naming discrepancy;
the registry product/build fields are the preflight's Windows identity.

## Prepared files

- `tools/wsl/preflight.ps1` records a read-only local inventory in ignored
  `artifacts/wsl-qualification/preflight.json`.
- `tools/wsl/install-wsl.ps1` classifies the host and contains the user-gated
  install path. Its default run refreshes preflight and stops if virtualization
  cannot be affirmatively verified or WSL cannot enumerate registered
  distributions. It never self-elevates, restarts Windows, or launches Ubuntu.
  `-PlanOnly` prints the proposed case without changing Windows features.
- `tools/wsl/bootstrap-wsl.sh` is run manually from the initialized Ubuntu
  account. It installs only missing base packages, makes a new clone of the
  qualification branch in Linux home, uses uv to create `.venv` from the tracked lockfile and install the project
  and test extra, and installs the official stable Codex CLI if absent. It
  does not copy Windows Codex state. Sign-in is a separate user action.
- `tools/wsl/qualify-core.sh` checks WSL2/Linux filesystem placement, Git
  fetch/write/diff behavior, temporary external worktrees and audited cleanup,
  Codex `workspace-write` behavior (including an outside-workspace denial),
  fixed-input numerical parity, checkpoint-v4 recovery, and then one full
  `pytest` regression run.
- `tools/wsl/collect-report.sh` produces local JSON and Markdown results. A
  successful report is `WSL2_CORE_QUALIFIED`; any missing or failed check is
  recorded as `WSL2_CORE_BLOCKED` with a `BLOCKER=` category.
- The report's **Source commit** is the repository `HEAD` read for that
  qualification run; it must not come from the earlier bootstrap environment
  snapshot. The snapshot's `git_head` is reported separately as
  **Bootstrap source commit**. Machine-readable reports expose both
  `source_commit_sha` and `bootstrap_source_commit_sha`, plus the qualification
  working-tree state. A dirty checkout remains blocked by the qualification
  preflight; its report still identifies the HEAD and records that the working
  tree was dirty, so that report is not mistaken for a clean-source run.
- The sanitized Windows parity fixture and its provenance are in
  `reports/experiment_reviews/qualification/wsl2-core-20261007-65e1815/`.

All detailed environment output, pytest logs, smoke raw data, and checkpoint
files are written under ignored `artifacts/wsl-qualification/`. They are not
the production review artifact path and are not committed.

## Numerical smoke boundary

The smoke uses the existing Stage 4C context and P_D evaluator with the
existing configuration and evaluator; it changes no COM equations, optimizer
algorithm, objective, constraints, or experiment protocol. It evaluates one
fixed design on the 1,001-point configured frequency grid and compares S11,
S21, metrics, objective, and constraints against the committed Windows
fixture. Frequency values must match exactly. S-parameter and metric arrays
use relative and absolute tolerances of `1e-12`; objective uses relative
tolerance `1e-12` and absolute tolerance `1e-6`. A difference is reported for
review and blocks qualification.

The optimizer smoke uses the existing P_D matched-cell path, seed `20261022`,
and 270 unique evaluations. It creates checkpoints at 250 and 270, simulates
two controlled stops, resumes, and compares the result with an uninterrupted
same-seed run. It checks active population, compact historical finalists,
frequency-grid version, cache accounting, finite metrics, and checkpoint
state version 4. This is a short API/recovery check, not a performance
comparison or production experiment. The Stage 4C module currently contains
a Windows-specific external qualification-root assumption; this smoke calls
the lower-level matched-cell API and does not validate the production
orchestration launcher or output-path integration on Linux.

## User-gated sequence

1. Review the branch and this procedure. Before any Windows mutation, rerun
   `tools/wsl/preflight.ps1` and inspect its local JSON report. Confirm
   virtualization and optional-feature status through the administrator
   preflight. If the result remains unknown, stop and resolve it before
   installing WSL.
2. For Case A, use an elevated PowerShell to run
   `tools/wsl/install-wsl.ps1`. It uses Microsoft's stable WSL install route
   with `Ubuntu-24.04` and `--no-launch`; it does not select a preview channel.
   Follow any manually requested Windows restart. The script stops before
   Ubuntu's first launch.
3. Launch Ubuntu yourself once, create the Linux username and password, then
   authenticate Codex inside Linux when prompted. Do not copy the Windows
   `.codex` directory.
4. From the Ubuntu shell, run the cloned branch's
   `tools/wsl/bootstrap-wsl.sh`, then `tools/wsl/qualify-core.sh`.
5. Review the generated report and logs. A failed parity check, failed
   sandbox/worktree check, or failed single full regression blocks
   qualification. This process runs no production optimization.

Microsoft documents the stable `wsl --install`, `--distribution`,
`--no-launch`, version, listing, and export commands in its [WSL installation
guide](https://learn.microsoft.com/en-us/windows/wsl/install) and [basic WSL
command reference](https://learn.microsoft.com/en-us/windows/wsl/basic-commands).
The Codex CLI bootstrap uses the official Linux installer documented in the
[Codex CLI guide](https://learn.chatgpt.com/docs/codex/cli).

## Rollback baseline

The current Windows checkout, branch, `.venv`, user `.codex`, and existing
worktrees were left in place. The WSL preparation is additive: local Windows
diagnostics are ignored; source changes are isolated on
`codex/wsl2-core-qualification`; the Linux setup creates a separate clone and
home directory. No Linux distribution backup or conversion is applicable to
the observed Case A. Do not remove the Windows checkout or its Codex data as
part of this qualification.
