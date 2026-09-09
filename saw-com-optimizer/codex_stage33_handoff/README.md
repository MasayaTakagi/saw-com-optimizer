# Stage 3.3 Handoff

Read in this order:

1. `ALGORITHM_REVIEW.md`
2. `CODEX_STAGE3_3_TASK.md`
3. `EXPERIMENT_PLAN.md`
4. `STAGE3_3_ACCEPTANCE.md`
5. `config/stage3_3_fragment.yaml`

Reference material:

- `references/SAW_structure_optimization_algorithm.md`

Key correction: the reference MD uses `center_outer_same` as if it were a geometry-DOF switch. In the current project it is a wiring mode. Stage 3.3 therefore validates L-SHADE and related optimizer improvements on the existing physical design parameterization and defers any new center/outer independent geometry model.

Production seed parallelism is part of Stage 3.3 and should use ProcessPool/spawn with one BLAS thread per worker.
