# SAW COM Stage 3.2 Codex Handoff

Read in this order:

1. `EXPERIMENT_PLAN.md`
2. `CODEX_STAGE3_2_TASK.md`
3. `STAGE3_2_ACCEPTANCE.md`
4. `config/stage3_2_fragment.yaml`

This package consolidates the current optimizer ideas:

- continuing budgets instead of cold restarts;
- exact unique-design budget accounting;
- automatic 8000 escalation;
- separation of frequency-grid and design convergence;
- multi-seed automatic soft-bound expansion with hard physical limits;
- boundary probes;
- convergence-history reset on design-space changes;
- seed-level parallelization;
- self-contained review-bundle generation.

The first production target remains 50 Ω DMS-only. Broad impedance/topology sweeps should wait for review of the Stage 3.2 production bundle.
