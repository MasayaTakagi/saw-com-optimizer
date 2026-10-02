# Stage 4B prelaunch evidence — 2026-10-03

## Source and baseline

- Baseline: `origin/main` at `13d62dbde48ecbe5333e5b47fab6f68cba528544`.
- Stage 4B branch: `codex/stage4b-hybrid-production-20261003`.
- Initial implementation and shakedown source: `e1875ef9de0a096472fadb73df5ba113af4919a0`; the launch-gate fix and prelaunch regression are included in the current clean launch source commit and recorded on the PR/manifest.
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
- Schema-v2 computation fingerprint for the corrected launch source: `f37b836eebdfdf1a9ad82abff378e9e6874d4dbde6a630a20978b1a60a5e04d2`.
- Reporting fingerprint: `b57c4b5365c96a22d65d2c82e0dd904f1484a4fd1139b062fc5e24c7fc1a65eb`.
- Production authorization is a one-shot CLI flag bound to the current exact protocol and source. The scientific config does not grant persistent production authorization.

## Validation and shakedown

- Focused Stage 4B / Stage 4A / orchestration regression tests after the launch-gate fix: PASS, 56 passed and 9 subtests passed.
- Full suite after the launch-gate fix: PASS, 249 passed.
- Initial Stage 4B shakedown: `runs/stage4b-shakedown-20261003`; four topologies, dedicated seed `20261001`, 512 unique evaluations per topology, cold starts, all checks PASS, and resume reused all four completed cells. Its manifest uses the earlier fingerprint `28e7babd…`; it is retained as history but does not qualify the corrected launch source.
- Corrected-source shakedown: `runs/stage4b-shakedown-launchfix-20261003`; four topologies × dedicated seed `20261001`, 512 unique evaluations per cell, dimension-scaled populations, cold starts, checkpoints 400/512. All ten checks PASS, including the matching source/fingerprint/grid, aggregation and outputs. A same-directory resume reused 4/4 completed cells. Source SHA `a4c5b7c88530f22a9630e5b0b7af83cdceb4cf94`; computation fingerprint `f37b836e…`.
- Lightweight evidence: `reports/stage4b_shakedown_launchfix_summary_20261003.json`. The full cell data remains under ignored `runs/`.
- Both shakedown directories are ranking-ineligible; no shakedown performance values are evidence for production topology ranking.
- One initial launch command stopped before callback preflight, authorization claim, run directory creation, or worker dispatch because the CLI lacked its `subprocess` import. The import was added and a positive authorized-launch manifest/claim regression test now passes. This did not change the scientific protocol or start a production worker.
- Subsequent exact launch attempts stopped before authorization claim, run directory creation and worker dispatch. The standard sandbox denied callback-preflight temporary-directory creation under both the repository and configured task scratch. A bounded managed execution then reached the callback CLI, but preflight returned `CodexCallbackTargetUnavailableError: Codex emitted no session_id/thread_id JSON event`. No callback PASS was recorded, so the production launch gate remains BLOCKED. The run directory and the one-shot authorization claim are absent; no production worker is running. Do not retry or replace this run until the exact callback identity can be verified.
- `git diff --check`: rerun after this blocked-launch evidence update and before committing it.

## Runtime estimate and launch plan

- Rough estimate: approximately 31,558 seconds (8.8 hours), derived from measured search-evaluation, common-validation and per-cell overhead components scaled to 480,000 evaluations, 1,280 finalist validations and 20 cells. This is an estimate from one small shakedown and is not a service-time guarantee.
- Output directory: `runs/stage4b-hybrid-topology-production-20261003` (must be new at launch).
- Launch command:

```powershell
.venv\Scripts\python.exe -m sawopt.orchestration.cli launch --config configs/studies/hybrid_stage4b_topology_comparison.yaml --run-dir runs/stage4b-hybrid-topology-production-20261003 --session-id 01a0fcca-3d9f-7a23-8622-1afe71e79c02 --authorize-stage4b-production
```

- Continuation mode is the existing explicit-session callback. Immediately after launch, validate the immutable `run_manifest.json` for the exact session ID, `callback_enabled=true`, `review_after_completion=true`, source SHA, fingerprint, authorization scope and 20-cell protocol. A manifest mismatch invalidates the launch.
- Each topology/seed cell owns its checkpoint stream. Resume must reuse the same run, seed, checkpoint and fingerprint; completed cells are skipped. Fingerprint mismatch fails closed. Do not replace the run.
- The production launch is authorized once for this exact protocol. A protocol change invalidates that authorization. No follow-up optimization is authorized by this run.

## Scope and limitations

The comparison can support relative topology, convergence and robustness observations under the current provisional model, and a shortlist proposal. It cannot establish real Band 28 device feasibility, a calibrated physical prediction, a real-device optimum, or a final impedance/topology recommendation. C2C remains frozen and was not invoked; GitHub is the external review surface. The PR must remain unmerged pending external review.
