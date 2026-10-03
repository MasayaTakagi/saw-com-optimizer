# Stage 4B prelaunch evidence — 2026-10-03

## Source and baseline

- Baseline: `origin/main` at `13d62dbde48ecbe5333e5b47fab6f68cba528544`.
- Stage 4B branch: `codex/stage4b-hybrid-production-20261003`.
- Initial implementation and shakedown source: `e1875ef9de0a096472fadb73df5ba113af4919a0`; the launch-gate fix and prelaunch regression are carried on this branch.
- Normal checkout is in use; no new worktree was created for Stage 4B.
- The prior `codex/production-queue-continuation` branch and its saved WIP commit remain available separately.

## Frozen production protocol

- Revision: `stage4b_hybrid_topology_production_v1`.
- Model: MLIT, `T1_SYMMETRIC_5IDT`, 50 Ω source and 50 Ω load; existing Stage 4A hybrid/resonator model, objective, geometry constraints, specification and network convention.
- Topologies: exactly `D`, `P_D`, `D_P`, `P_D_P`.
- Seeds: exactly `20261002`, `20261003`, `20261004`, `20261005`, `20261006`, paired across topologies.
- Matrix: 20 cold independent cells, no warm start or population transfer.
- Budget: 24,000 unique decoded evaluations per cell; terminal schedule budget 24,000; checkpoints 4,000 / 8,000 / 16,000 / 24,000. Total planned unique evaluations: 480,000.
- Initial population: `18 * dimension`: D=180 (10 DOF), P_D=234 (13), D_P=234 (13), P_D_P=288 (16).
- Search grid: 1,001 points; common validation grid: 9,113 points, identity `2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f`, SHA-256 `54c1daf67dd2bb9242f95e638d7bd801db536acc2c7d6f00c1f62a788bead554`.
- Computation fingerprint before callback-only correction: `f37b836eebdfdf1a9ad82abff378e9e6874d4dbde6a630a20978b1a60a5e04d2`.
- Requalified final schema-v2 computation fingerprint: `c63910623cb9a5d2a05ecb51f3685becf448f8ac91f169752f1b9703beef8464`. The change is caused solely by `src/sawopt/orchestration/codex_callback.py`, which the Stage 4B schema-v2 dependency list intentionally includes. `git diff a4c5b7c88530f22a9630e5b0b7af83cdceb4cf94..9bec56b1ea08e3ec174001c2f204021ed5e0a04f -- src/sawopt configs` reports only that orchestration source change; Stage 4A/4B numerical implementation and scientific config are unchanged. The Stage 4B context reload confirms schema 2, the same common-grid identity, and 1,001/9,113 points. The corrected fingerprint is the value to bind into the production manifest.
- Reporting fingerprint from the corrected shakedown: `b57c4b5365c96a22d65d2c82e0dd904f1484a4fd1139b062fc5e24c7fc1a65eb`.
- Production authorization is a one-shot CLI flag bound to the current exact protocol and source. The scientific config does not grant persistent production authorization.

## Validation and shakedown

- Historical pre-callback-correction focused Stage 4B / Stage 4A / orchestration regression tests: PASS, 56 passed and 9 subtests passed.
- Historical pre-callback-correction full suite: PASS, 249 passed.
- Initial Stage 4B shakedown: `runs/stage4b-shakedown-20261003`; four topologies, dedicated seed `20261001`, 512 unique evaluations per topology, cold starts, all checks PASS, and resume reused all four completed cells. Its manifest uses the earlier fingerprint `28e7babd…`; it is retained as history but does not qualify the corrected launch source.
- Corrected-source shakedown: `runs/stage4b-shakedown-launchfix-20261003`; four topologies × dedicated seed `20261001`, 512 unique evaluations per cell, dimension-scaled populations, cold starts, checkpoints 400/512. All ten checks PASS, including the matching source/fingerprint/grid, aggregation and outputs. A same-directory resume reused 4/4 completed cells. Source SHA `a4c5b7c88530f22a9630e5b0b7af83cdceb4cf94`; computation fingerprint `f37b836e…`.
- Lightweight evidence: `reports/stage4b_shakedown_launchfix_summary_20261003.json`. The full cell data remains under ignored `runs/`.
- Both shakedown directories are ranking-ineligible; no shakedown performance values are evidence for production topology ranking.
- One initial launch command stopped before callback preflight, authorization claim, run directory creation, or worker dispatch because the CLI lacked its `subprocess` import. The import was added and a positive authorized-launch manifest/claim regression test passed. This did not change the scientific protocol or start a production worker.
- Subsequent launch attempts stopped before authorization claim, run directory creation and worker dispatch. The standard sandbox denied the old callback-preflight temporary directory, and a managed attempt against the active implementation session produced no `session_id`/`thread_id` event. No callback PASS was recorded; no production worker is running.

## Callback preflight correction

GitHub-side callback-only corrections were applied after the blocked launch:

- `src/sawopt/orchestration/codex_callback.py` now creates callback-preflight temporary files under the project-local ignored scratch root `runs/.callback_preflight`, rather than relying on the global OS temp directory.
- Explicit callback resume now uses `codex exec --json -c 'sandbox_mode="workspace-write"' resume <THREAD_ID> <PROMPT>` semantics and continues to prohibit `--last`.
- Exact target validation remains fail-closed. Missing, foreign, or mixed session/thread IDs are rejected.
- Preflight now requires exactly one completed agent acknowledgement equal to `CALLBACK_PREFLIGHT_OK`.
- Unit tests were updated to cover the new argv, project-local scratch path, absence of `--sandbox`/`--last`, and extra-agent-message rejection.
- These changes are orchestration/callback-only; no Stage 4B scientific config, optimizer, topology, seed, budget, grid, objective, bounds, or metric was changed.

### Callback requalification completed

- Codex CLI diagnosis: `codex-cli 0.159.0-alpha.12.1`. `codex exec --help` and `codex exec resume --help` were captured; they confirm structured `--json`, config override `-c`, and explicit `resume [SESSION_ID] [PROMPT]` syntax. Callback environment inputs were `USERPROFILE=C:\Users\sub`, `HOME` unset (helper supplies `C:\Users\sub`), `CODEX_HOME` unset (helper supplies `C:\Users\sub\.codex`), and repository cwd `C:\Users\sub\Documents\ChatGPT\saw-com-optimizer`.
- A fresh, dedicated `codex exec --json -c 'sandbox_mode="workspace-write"'` callback channel completed with exit code 0, one authoritative `thread.started.thread_id`, and exactly `CALLBACK_CHANNEL_READY`: `01a0ff60-991d-7dc3-bde4-cc3640853a0d`. The active implementation session `01a0fcca-3d9f-7a23-8622-1afe71e79c02` was not used.
- The repository's actual `run_codex_callback_preflight()` helper resumed the dedicated ID explicitly using `codex exec --json -c 'sandbox_mode="workspace-write"' resume <THREAD_ID> <PROMPT>`. Result: exit code 0; requested ID and observed JSONL identity both `01a0ff60-991d-7dc3-bde4-cc3640853a0d`; exactly one completed agent acknowledgement `CALLBACK_PREFLIGHT_OK`. No `--last` was used. Result: PASS.
- Project-local scratch: `runs/.callback_preflight`. Raw channel creation and exact-resume JSONL captures are retained there; no production run directory was created during preflight.
- Focused callback + Stage 4B/orchestration + Stage 4A regression: PASS, 57 passed. Full local suite: PASS, 250 passed. Tests used repository-local pytest temp storage because the standard sandbox denied `%TEMP%`/`.pytest_cache` access; no test failures remained on the bounded project-local rerun.
- GitHub Actions CI run #50: `SUCCESS` at source SHA `9bec56b1ea08e3ec174001c2f204021ed5e0a04f` (PR #16).
- Callback-requalified executable source SHA: `9bec56b1ea08e3ec174001c2f204021ed5e0a04f`. This report-only evidence update will be committed before launch; the exact launch source SHA will be captured in the immutable production manifest and PR body.
- Scientific protocol changed: NO. Production remains blocked until the evidence commit is pushed and the remaining launch gates are rechecked against its exact source SHA.

## Runtime estimate and launch plan

- Rough estimate: approximately 31,558 seconds (8.8 hours), derived from measured search-evaluation, common-validation and per-cell overhead components scaled to 480,000 evaluations, 1,280 finalist validations and 20 cells. This is an estimate from one small shakedown and is not a service-time guarantee.
- Output directory: `runs/stage4b-hybrid-topology-production-20261003` (must be new at launch).
- Launch with the qualified dedicated callback thread ID:

```powershell
.venv\Scripts\python.exe -m sawopt.orchestration.cli launch --config configs/studies/hybrid_stage4b_topology_comparison.yaml --run-dir runs/stage4b-hybrid-topology-production-20261003 --session-id <DEDICATED_CALLBACK_THREAD_ID> --authorize-stage4b-production
```

- The production launch source must be the clean, pushed evidence-commit HEAD. Immediately after launch, validate immutable `run_manifest.json`: its `codex_session_id` must equal the dedicated validated callback thread ID, `callback_enabled=true`, `review_after_completion=true`, and source SHA/fingerprint/authorization scope/20-cell protocol must match that launch source.
- Each topology/seed cell owns its checkpoint stream. Resume must reuse the same run, seed, checkpoint and fingerprint; completed cells are skipped. Fingerprint mismatch fails closed. Do not replace the run.
- The production launch is authorized once for this exact protocol. A protocol change invalidates that authorization. No follow-up optimization is authorized by this run.

## Scope and limitations

The comparison can support relative topology, convergence and robustness observations under the current provisional model, and a shortlist proposal. It cannot establish real Band 28 device feasibility, a calibrated physical prediction, a real-device optimum, or a final impedance/topology recommendation. C2C remains frozen and was not invoked; GitHub is the external review surface. The PR must remain unmerged pending external review.
