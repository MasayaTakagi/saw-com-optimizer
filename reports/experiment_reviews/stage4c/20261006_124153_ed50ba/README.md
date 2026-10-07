# Experiment review evidence: 20261006_124153_ed50ba

- Stage: `stage4c`
- Study: `hybrid_stage4c_confirmatory`
- Optimizer state: `COMPLETED` (exit None)
- Cells: 10/10
- This directory is a deterministic compact export from the saved run.
- Checkpoint bodies, populations, caches, and process logs are excluded.

## Post-run orchestration recovery

The Stage 4C optimizer produced durable completion evidence: all 10 cells completed 96,000 unique evaluations each, the integrity check passed, and final checkpoints were finalized. At post-run inspection, the orchestration status still showed RUNNING; its worker and optimizer PIDs were no longer alive, the orchestration stderr.log was empty, and neither optimizer_completion.json nor continuation_delivery.json existed.

The exact process stop trigger cannot be established because no exit code or traceback was recorded. The best-supported diagnosis is that the detached orchestration worker was lost or terminated after the optimizer wrote its completion artifacts but before orchestration terminal state and continuation records were persisted. There is no evidence of a cell computation failure.

The run was reconciled from the durable Stage 4C completion, integrity, cell, and checkpoint evidence. Orchestration and optimizer disposition are COMPLETED; process exit code remains unknown (
ull). No optimizer cell was rerun and no checkpoint or scientific result was modified. The recovery audit and evidence hashes are in orchestration/postrun_orchestration_recovery.json.

## Exact-thread continuation

The single queue handoff was accepted and receiver-confirmed in the frozen original thread. continuation_state is RECEIVER_CONFIRMED;
eview_evidence_state was EXPORTED at this status snapshot. The handoff resumes evidence publication only; it is not scientific acceptance or authorization for another production run.
