# Stage 3.3 Experiment Plan

## Objective

Select the next production optimizer for the SAW project using controlled evidence, while completing safe production seed parallelism and exact resume support.

Primary hypothesis:

> An L-SHADE-style engine will reach the low-violation basin at 50 ohm `center_outer_same` more reliably and/or with fewer unique decoded design evaluations than the current SciPy-DE continuation.

Secondary hypotheses:

- improved integer/elite bound diagnostics will prevent false convergence at soft boundaries;
- Powell may improve final continuous coordinates after integer refinement;
- process-level 5-seed parallelism will reduce wall time without changing per-seed results.

---

# Phase 0 — Freeze and reproduce Stage 3.2 baseline

1. Create a clean branch/tag.
2. Save current source/config/COM hashes.
3. Run the existing fast test suite.
4. Reproduce one small Stage 3.2 seed result.
5. Confirm current review-bundle generator works before changing optimizer code.

Gate: no optimizer work until baseline regression is green.

---

# Phase 1 — Implementation

Implement in this order:

1. central feasibility-first comparator;
2. optimizer backend interface;
3. L-SHADE state machine;
4. exact checkpoint serialization/load;
5. normalized mixed-variable evaluation and duplicate diagnostics;
6. adaptive-frequency state integration;
7. improved integer boundary zone;
8. elite-boundary probe;
9. ProcessPool seed runner;
10. optional Powell polish;
11. algorithm-comparison reporting;
12. self-contained review bundle updates.

No long production run in Phase 1.

---

# Phase 2 — Unit and synthetic tests

## 2.1 L-SHADE algorithm unit tests

Use cheap analytic functions, not COM.

Required:

- sphere/ellipsoid: convergence sanity;
- multimodal test such as Rastrigin: diversity/seed behavior smoke;
- fixed-seed deterministic reproduction;
- F/CR memory update tests;
- p-best selection validity;
- archive insert/trim behavior;
- linear population schedule reaches configured minimum;
- checkpoint save/load exact continuation parity;
- mixed integer canonical duplicate cache test;
- comparator/feasibility ordering tests.

Do not use these functions to tune L-SHADE exhaustively; they are correctness tests.

## 2.2 Bound tests

Synthetic objective whose optimum lies just outside an initial soft bound but inside hard bound.

Verify:

- integer boundary zone recognizes lower and lower+1;
- one elite triggers only a probe;
- failed probe does not expand;
- multiple improving probes expand;
- hard bound is never crossed;
- `design_space_version` increments;
- convergence evidence resets;
- new-region population injection occurs.

## 2.3 Parallel tests

Run 2 or 3 cheap seeds serial and with ProcessPool.

Verify identical per-seed results and no shared-file corruption.

Gate: all unit/synthetic tests pass.

---

# Phase 3 — Small SAW smoke/debug tests

Use 50 ohm DMS only.

Wiring priority:

1. `center_outer_same` — primary because Stage 3.2 showed low basin-hit rate;
2. `outer_ports` — regression/control.

Use 2 cold seeds and very small unique budgets, for example:

```text
250 -> 500 -> 1000
```

Run both algorithms:

- A = current SciPy-DE continuation;
- B = L-SHADE.

Auto-bound may be enabled for integration smoke, but also run one fixed-design-space smoke so optimizer engine behavior is separable from bound expansion.

Debug checks:

- unique budget is consumed exactly;
- budget continuation does not restart seed trajectory;
- frequency reevaluation does not increase unique design count;
- L-SHADE checkpoint reload reproduces uninterrupted path;
- no nonfinite COM result leaks into population;
- duplicate decoded rate is reported;
- adaptive-grid events and bound events are versioned;
- reports clearly identify algorithm backend.

Gate: no production run if any budget/accounting/state issue remains.

---

# Phase 4 — Controlled optimizer A/B pilot

## 4.1 Isolate optimizer effect

Primary dataset:

```text
50 ohm
wiring = center_outer_same
5 identical cold seeds
fixed common design-space bounds
no auto-bound expansion during this subtest
budgets = 1000, 2000, 4000 unique decoded designs
same frequency machinery
same evaluator/cache/comparator
```

Use the current Stage 3.2 final design-space version as the fixed space, unless the run manifest shows it is invalid; record exact bounds.

Run Algorithm A and Algorithm B separately. Use production ProcessPool within each algorithm, but do not run A and B at the same time.

Metrics:

- final median max_violation;
- final best max_violation;
- seed IQR;
- basin hit rate;
- median unique eval at first reaching thresholds;
- late-improvement fraction;
- duplicate decoded rate;
- COM frequency points solved;
- wall time and CPU time.

### Basin-hit thresholds

Use data-driven thresholds anchored to the Stage 3.2 center result. At minimum report hit rates for:

```text
max_violation <= 1.8
max_violation <= 1.6
max_violation <= 1.5
```

Do not make the entire decision depend on one threshold.

## 4.2 Promotion criterion

Promote L-SHADE if it shows a meaningful advantage on at least one major efficiency/reliability dimension without a material regression on the others. Suggested evidence threshold:

- median max_violation improved by >= 5%, OR
- basin-hit rate improves by >= 2 of 5 seeds, OR
- reaches the same median quality with <= 70% of unique evaluations,

and

- common-dense validation remains equivalent;
- no deterioration in numerical failure rate;
- checkpoint parity passes.

If differences are small/inconsistent, retain current DE as production default and keep L-SHADE experimental.

---

# Phase 5 — Integrated bound-aware pilot

Using the provisional winner from Phase 4:

```text
50 ohm
center_outer_same
5 cold seeds
auto-bound enabled
1000 -> 2000 -> 4000 -> 8000
```

Apply:

- integer boundary zone = 1 step;
- multi-seed pressure;
- elite-boundary probes;
- hard bounds;
- exact continuation;
- adaptive frequency exchange.

Also run `outer_ports` at reduced pilot budget if needed to confirm bound logic does not regress.

Review:

- whether `io_idt_pairs` expands 15 -> 10 when justified;
- whether center elite-boundary probe finds evidence below 15;
- design-space version history;
- convergence within each version;
- whether the good center basin becomes more reproducible.

---

# Phase 6 — Continuous-polish experiment

Take the top candidates from Phase 5.

Compare:

A. existing integer/mixed local refinement;
B. integer refinement + Powell continuous-only polish.

Use the same final active grid and common dense validation.

Measure:

- rank improvement;
- extra function evaluations;
- wall time;
- rejection rate after dense validation.

Promote Powell only if it improves at least 3/5 representative final candidates or materially improves the best candidate with acceptable extra cost and no dense-validation regression.

---

# Phase 7 — Production parallel benchmark and enablement

Production implementation must use ProcessPool seed-level parallelism.

Benchmark the selected optimizer with 5 identical seeds at a moderate budget using:

```text
workers = 1, 2, 4, 5
```

Run each setting multiple times if individual runs are short; report median wall time.

Before benchmark launch set each worker's BLAS/OpenMP threads to 1.

Required outputs:

- per-worker-count wall time;
- speedup;
- parallel efficiency;
- per-seed result parity;
- CPU utilization if available.

Select production worker count as the fastest setting that preserves deterministic per-seed results and does not cause memory pressure.

Then set this value in the production Stage 3.3 config.

---

# Phase 8 — 50 ohm production convergence run

Only after Phase 4–7 gates pass.

Run the selected optimizer at 50 ohm for:

- `center_outer_same`;
- `outer_ports`.

Cold seeds: >=5.

Continuation checkpoints:

```text
500 -> 1000 -> 2000 -> 4000 -> 8000
```

Allow 16000 only if:

- current design-space version remains unconverged;
- a trajectory is still improving late;
- or seed dispersion remains large;
- and no unresolved implementation/debug issue exists.

Do not reset optimizer state when extending the budget.

Production uses the selected ProcessPool worker count.

Status vocabulary:

- `converged`
- `hard_bound_limited`
- `likely_underoptimized`
- `inconclusive`

Do not proceed to the full 20–200 ohm/topology sweep unless at least one 50-ohm wiring has a defensible convergence classification and all bound-pressure questions relevant to the winner are resolved.

---

# Phase 9 — Review bundle generation

At the end of the production command, automatically create a self-contained review ZIP.

It must include:

```text
REVIEW_ME.md
bundle_manifest.json

source/
  all runtime source
  tests/
  configs/ at the paths tests expect
  pyproject.toml / package metadata needed for test execution

inputs/
  exact run configs
  exact COM parameter files

environment/
  git commit/status/diff
  Python + package versions
  source hash

results/
  algorithm_ab_summary.json/csv/html
  convergence_summary.json/csv/html
  basin_hit_rates.csv
  duplicate_statistics.csv
  bound_events.json/csv
  design_space_versions.json
  best_candidates.json
  best_so_far_traces.csv
  performance_parallel.json/csv
  checkpoint_resume_parity.json
  polish_comparison.json/csv

trials/
  per-seed final/result JSON
  checkpoint metadata (large raw state may be optional)

tests/
  unit_test_log.txt
  test_summary.json
  bundle_self_test.txt
```

The bundle must be executable/reviewable without files from the original worktree.

Self-test procedure:

1. copy ZIP to an empty temporary directory;
2. extract;
3. run the documented fast test command using only bundle contents;
4. verify every manifest SHA-256;
5. save result in `bundle_self_test.txt`.

Large NPZ/history/checkpoint binary state may be optional flags, but enough metadata must remain to reproduce claims.

---

# Phase 10 — Codex long-run behavior

The experiment runner must be self-contained. Codex should not repeatedly poll the process during long optimization.

Preferred operation:

```text
Codex starts one production command
  -> Python handles checkpoints, progress, seeds, parallel workers, reports
  -> command finishes and review bundle is generated
  -> Codex reads final summary once
```

If the execution environment requires detaching/reconnecting, use saved checkpoints and coarse-grained process status only. Do not consume chat/model tokens by repeatedly tailing progress logs.
