# Stage 4B prelaunch evidence — 2026-10-03

## Source and baseline

- Baseline: `origin/main` at `13d62dbde48ecbe5333e5b47fab6f68cba528544`.
- Stage 4B branch: `codex/stage4b-hybrid-production-20261003`.
- Implementation and shakedown source: `e1875ef9de0a096472fadb73df5ba113af4919a0`.
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
- Schema-v2 computation fingerprint: `28e7babd41b175c24f89fb4951f58b95bd1685b6ae445aec2fba51e6e54286db`.
- Reporting fingerprint: `b57c4b5365c96a22d65d2c82e0dd904f1484a4fd1139b062fc5e24c7fc1a65eb`.
- Production authorization is a one-shot CLI flag bound to the current exact protocol and source. The scientific config does not grant persistent production authorization.

## Validation and shakedown

- Focused Stage 4B / Stage 4A regression tests: PASS, 42 passed and 9 subtests passed.
- Full suite: PASS, 248 passed and 20 subtests passed.
- Stage 4B shakedown: `runs/stage4b-shakedown-20261003`; four topologies, dedicated seed `20261001`, 512 unique evaluations per topology, cold starts. Manifest and summary report `PASS`; checks cover dispatch/topology count, dimension-scaled populations, unique accounting, checkpoints, cold initialization, common-grid identity, resume metadata, production separation, aggregation and output paths.
- Shakedown resume reused all four completed cells without recomputing them. The lightweight source artifacts are under `runs/stage4b-shakedown-20261003/metadata/`; detailed run data remains local and ignored.
- Shakedown is marked `ranking_eligible=false`; none of its performance values are evidence for production topology ranking.
- `git diff --check`: PASS before this evidence note was added; it will be rerun before commit and launch.

## Runtime estimate and launch plan

- Rough estimate: approximately 31,187 seconds (8.7 hours), derived from the shakedown's measured search-evaluation, common-validation and per-cell overhead components scaled to 480,000 evaluations, 1,280 finalist validations and 20 cells. This is an estimate from a single short shakedown and is not a service-time guarantee.
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
