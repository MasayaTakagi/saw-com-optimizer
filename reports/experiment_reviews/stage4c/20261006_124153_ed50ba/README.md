# Experiment review evidence: 20261006_124153_ed50ba

- Stage: **stage4c**
- Study: **hybrid_stage4c_confirmatory**
- Optimizer state: **COMPLETED**
- Orchestration state: **REVIEW_WAITING**
- Recorded process exit code: **null / unknown; not inferred**
- Cells: 10/10, each at 96,000 unique evaluations
- Integrity: **PASS**; all final checkpoints finalized
- This directory is a deterministic compact export from the saved run.
- Checkpoint bodies, populations, caches, and process logs are excluded.

## Post-run orchestration recovery

The optimizer produced durable completion evidence for all 10 cells at 96,000 unique evaluations per cell. Integrity passed and all 10 final checkpoints were finalized. At the first post-run inspection, orchestration still showed RUNNING; the recorded worker and optimizer PIDs were no longer alive, the root stderr.log was empty, and the orchestration optimizer-completion and continuation-delivery records were missing.

The exact termination trigger is unknown: no exit code or traceback was recorded. The best-supported explanation is detached worker loss or termination after optimizer durable completion and before orchestration finalization. This diagnosis is not asserted as a proven cause. The recorded exit code remains null / unknown; it is not inferred.

The run was reconciled from existing durable evidence only. No optimizer or cell was rerun, and no checkpoint or raw scientific result was changed. The recovery audit remains in the external persistent run root as postrun_orchestration_recovery.json; its SHA-256 is recorded in review_manifest.json.

## Scientific result and interpretation

The scientific classification remains STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED.

### Completion and feasibility

- 10/10 cells completed 96,000 unique evaluations each.
- Integrity status is PASS; all final checkpoints were finalized.
- Feasible cells: P_D 0/5; D_P 0/5.

### Matched-seed terminal comparison

Terminal lexicographic wins were P_D 3, D_P 2, TIE 0, and INDETERMINATE 0. A clear winner requires at least 4/5 matched-seed wins, so neither topology met that rule.

### Convergence maturity

All 10/10 terminal cells are IMMATURE_OR_INCOMPLETE. Each of the 10 cells also shows significant improvement from 80,000 to 96,000 evaluations. The search therefore had not met the terminal maturity condition at the 96k horizon.

### Terminal boundary caveats

Unresolved hard-bound hits at the 96k terminal checkpoint are present in:

- P_D / seed 20261007
- D_P / seed 20261007
- D_P / seed 20261009

Each is an upper terminal hit on resonator_0_pairs. Earlier-checkpoint-only bound hits are not counted as terminal unresolved hits.

### Fail-closed interpretation

STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED is retained because no feasible solution was obtained, terminal matched-seed preference did not reach 4/5, all 10 terminal cells remain immature, significant improvement continued from 80k to 96k in all 10 cells, and terminal hard-bound caveats remain in three cells. No scientific final acceptance or selection of P_D versus D_P is made.

The 0.02 maximum normalized violation is an internal computational interpretation threshold. It is not a manufacturing tolerance or a measurement tolerance, and these results do not establish manufacturability, measured equivalence, or practical equivalence.

## Exact-thread continuation and review state

The one-shot queue continuation remains RECEIVER_CONFIRMED: attempt count 1, sender accepted, and the exact receiver thread confirmed. This package correction did not resend the queue message. The production result is completed, the scientific disposition remains unresolved, and the review workflow is waiting for independent review. Publication of this package does not constitute scientific acceptance or authorize another production run.
