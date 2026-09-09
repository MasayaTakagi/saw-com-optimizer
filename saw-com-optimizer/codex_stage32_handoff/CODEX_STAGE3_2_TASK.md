# Codex Implementation Task — Stage 3.2

## Goal

Implement a convergence-validating, continuation-based optimizer for the SAW COM project. The primary target is 50-ohm DMS-only validation before broader impedance/topology studies.

Do not change the verified COM equations or network conversion unless a failing regression test proves a defect.

## Source of truth

Use the current Stage 3.1 implementation as source of truth. Older handoff patches are references for intent only. Do not mechanically reapply them.

Read `EXPERIMENT_PLAN.md` completely before editing.

---

# Required implementation

## 1. Continuation budgets

Replace independent budget restarts with one continuing trajectory per cold seed.

Required checkpoints:

- 500
- 1000
- 2000
- 4000
- 8000 optional escalation

Requirements:

- preserve optimizer population/state as far as practical;
- preserve seed/RNG trajectory;
- checkpoint at budget thresholds;
- do not discard remaining design budget when the frequency grid stops changing;
- track requested and actual unique decoded design evaluations separately;
- track solved frequency points separately.

If the current SciPy DE API makes true stateful continuation impractical, implement a controlled continuation layer that carries forward the full current population, incumbent, seed state or deterministic derived seed, and cache. Document exactly what state is and is not preserved. Do not silently call a fresh cold start and label it continuation.

## 2. Auto escalation

When `auto_escalate=true`, if the 4000 checkpoint is not converged, continue to `optional_max_budget=8000`.

## 3. Separate frequency-grid convergence from design convergence

Maintain separate states:

- `grid_converged`
- `optimizer_converged`

A converged grid must not terminate the design search while design budget remains.

When the grid changes:

- evaluate only newly added frequencies when possible;
- re-evaluate current population/objectives on the expanded grid;
- do not increment unique-design count for same-geometry frequency extension;
- continue search from current population.

## 4. Improved convergence evidence

For each wiring and budget checkpoint compute paired same-seed deltas.

Record at least:

- best and median primary metric;
- seed IQR;
- paired median improvement;
- paired improvement IQR;
- number/fraction of seeds with significant improvement;
- last significant improvement evaluation;
- fraction of budget elapsed at last significant improvement;
- common-grid validation gap;
- best-candidate polish improvement;
- median-candidate polish improvement.

Require two consecutive plateau intervals within the same design-space version before returning `converged`.

## 5. Mixed-variable polish

Intermediate checkpoint polish is diagnostic only and must not mutate the running DE trajectory.

At final stop:

- polish the best candidate;
- common-grid revalidate;
- accept polished candidate only if rank improves.

Keep best- and median-candidate polish metrics separate. Convergence gate must use best-candidate polish only.

## 6. Automatic bound diagnostics and expansion

Implement soft and hard bounds.

Each expandable variable must support metadata similar to:

```yaml
initial: [20, 100]
hard: [8, 120]
expandable: true
lower_steps: [15, 10, 8]
```

Hard bounds are never automatically crossed.

Implement multi-seed boundary-pressure diagnostics. One seed hitting a boundary is insufficient.

At global checkpoints detect:

- best-candidate boundary hit rate;
- elite-candidate boundary concentration;
- persistence across checkpoints;
- optional directional/boundary-probe evidence.

Before expansion perform a low-cost boundary probe when possible.

On confirmed expansion:

- increment `design_space_version`;
- reset convergence plateau history;
- keep incumbent/population information;
- inject 10–25% samples into newly opened region;
- continue the same experiment;
- never automatically shrink bounds.

Return a distinct `hard_bound_limited` status when strong outward pressure persists at a hard physical bound.

## 7. Seed-level parallelization

Implement outer-level parallel execution across cold seeds.

Benchmark 1, 2, 4, 5 workers.

For worker processes/threads set or document single-thread BLAS behavior to avoid oversubscription.

Serial and parallel results for a fixed seed must agree within declared numerical tolerances.

Prefer process-level isolation if thread/BLAS interaction makes timing or determinism poor.

## 8. Incremental diagnostics correctness

Aggregate diagnostics across all incremental frequency batches:

- minimum conductance eigenvalue: global min;
- reciprocity error: global max;
- solve residual: global max;
- condition number if present: global max.

Add full-vs-incremental parity tests for metrics and diagnostics.

## 9. Review bundle

Implement/upgrade review bundle generation according to `EXPERIMENT_PLAN.md`.

Bundle must be self-contained and include files at the relative paths expected by tests, including configs and repository metadata required for test discovery.

Add a bundle self-test that extracts the ZIP to a clean temporary directory and reruns manifest/hash verification plus the test suite using only bundle contents.

---

# Priority order

1. Correct continuation/budget accounting
2. Frequency-grid vs optimizer convergence separation
3. Auto escalation to 8000
4. Convergence evidence fixes
5. Soft/hard bound framework + diagnostics/expansion
6. Mixed-variable polish correctness
7. Incremental diagnostics aggregation
8. Small tests/debug
9. Seed-level parallelization
10. Production 50-ohm experiment
11. Review bundle creation/self-test

Do not spend significant effort on Numba, GPU, COM solver rewrites, or other low-level performance work in Stage 3.2.

---

# Production experiment

After all small tests pass, run:

- Z0 = 50 ohm
- DMS only
- wirings: `outer_ports`, `center_outer_same`
- minimum 5 cold seeds each
- checkpoints: 500,1000,2000,4000
- auto escalate to 8000 if not converged
- bound diagnostics active

Do not launch broad 20–200 ohm hybrid production sweeps before this experiment is reviewed.

---

# Deliverables

1. Updated source
2. Updated tests
3. Test logs
4. Small smoke-run artifacts
5. Production run artifacts
6. Convergence/boundary reports
7. Worker benchmark
8. Self-contained review ZIP
9. Short implementation note listing deviations from this spec and reasons
