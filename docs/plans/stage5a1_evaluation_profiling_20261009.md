# Stage 5A-1 hybrid evaluation profiling plan

## Purpose and boundary

This profiling task measures the cost of one fixed Stage 4C hybrid-filter
evaluation. It will separate COM/network/metric work from candidate decoding
and geometry checks so later work can compare reducing time per evaluation
with reducing the number of optimizer evaluations. It does not change or
benchmark an optimizer algorithm, and it does not launch optimization,
production, or checkpoint-resume work.

The source baseline is `2dc1d9421a1578548bd6cc18e4fbe6e733d0d6b8`, the
current remote `main` head when this work began. The tracked Stage 4C review
evidence is read-only input:
`reports/experiment_reviews/stage4c/20261006_124153_ed50ba/`.

## Candidates and evaluation conditions

Use only `common_grid_selected_finalist.candidate_vector` from the tracked
96k result for each of these six cells:

| Topology | Seeds |
| --- | --- |
| P_D | 20261007, 20261009, 20261011 |
| D_P | 20261007, 20261009, 20261011 |

The utility must fail with the missing cell path if any candidate is absent or
cannot be decoded consistently with its saved DMS/resonator design. It must
not substitute another finalist. Use the Stage 4C MLIT COM profile, T1 DMS,
saved resonator designs, specification and geometry constraints, with real
50 ohm source and load terminations.

Load frequency arrays from the Stage 4A context used by Stage 4C, and verify
both count and recorded identity before measuring:

| Grid | Points | Identity |
| --- | ---: | --- |
| Search | 1,001 | SHA256 `212dd2b0b71ddeffb7a8865937d132ee596870f25c989ac7d90c5dab6fd7faa0` |
| Common validation | 9,113 | ID `2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f`; SHA256 `54c1daf67dd2bb9242f95e638d7bd801db536acc2c7d6f00c1f62a788bead554` |

Use the loaded arrays themselves; matching only their point counts is not
sufficient. Read/configuration time is recorded separately from evaluation
time.

## Timed stages

Use `time.perf_counter()` and measure each decomposed evaluation as one ordered
pipeline. Stage A includes candidate decode and the Stage 4A hybrid geometry
gate. The remaining stages are:

| Stage | Timed work |
| --- | --- |
| A | Candidate decode and geometry validation |
| B | T1 DMS COM simulation |
| C | All topology resonator COM simulations |
| D | DMS/resonator admittance composition and internal-node elimination |
| E | 50/50 ohm network evaluation, including S parameters and transducer gain |
| F | Filter metrics, constraint violations, and objective calculation |
| G | Candidate decode plus the ordinary `_stage4a_evaluate()` call |

G is timed independently. Record its `_stage4a_evaluate()` call span as a
submeasurement because Stage 4C's `search_evaluation_wall_time_s` starts after
candidate decode and times that call. Report `sum(A..F)`, G, and their
difference; the component sum is a diagnostic decomposition, not a substitute
for the measured end-to-end time. Provider and frequency arrays are prepared
before the timed loops. Any provider or BLAS warm-up effect is documented.

For each of six candidates and both grids, do at least two untimed warm-ups,
then at least seven timed repetitions. Shuffle candidate/grid order within
each repetition using a recorded fixed measurement-order seed. This seed only
controls benchmark ordering. Store every sample and summarize with median,
minimum, maximum, and median absolute deviation.

## Numerical verification

Before collecting repeated timings, compare the decomposed pipeline against
the ordinary `_stage4a_evaluate()` path for all six candidates on both exact
grids. Capture the normal path's input Y and output network arrays during this
verification call, without adding instrumentation to production evaluation
code. Compare:

- Y parameters;
- complex S parameters, transducer gain, insertion loss, VSWR, and return loss;
- worst and average insertion loss, ripple, input/output VSWR, and stopband
  attenuation;
- maximum and summed normalized violation, feasibility, and scalar objective.

Use the existing Stage 4A parity tolerance `rtol=1e-10`, `atol=1e-12` from
`configs/studies/hybrid_stage4a_qualification.yaml`. Do not introduce a looser
tolerance. A mismatch or grid identity failure blocks timing publication.

## Outputs and analysis

Write compact, reproducible results under
`reports/benchmarks/stage5a1_evaluation_profile/`:

- `measurements.csv`: one row per candidate, grid, and repetition, with each
  timed stage in its own column, plus the decomposed sum and end-to-end sample;
- `profile_summary.json`: candidate/grid summaries, numerical parity maxima,
  setup/read time, CPU and OS, Python/NumPy/SciPy versions, BLAS identity and
  threadpool details when available, relevant thread environment variables,
  benchmark command, and source SHA.

The report will compare 1,001-point and 9,113-point per-evaluation costs,
P_D versus D_P, variation within each topology, and the sum of component times
against G. It will compare representative measurements with Stage 4C's
tracked `runtime_accounting_summary.csv`, which reports 96,000 search
evaluations per cell and separate common-validation time. Optimizer,
checkpoint, initialization, finalist-validation, and history costs remain
outside a single search evaluation and must be called out in that comparison.

For 5x5, 10x10, and 41x41 maps, estimate cell-hours using the measured
search-grid evaluation cost and explicitly state the per-cell evaluation
budget, seed count, and topology count. Show ideal wall-clock at stated worker
counts separately from total cell-hours; ideal linear scaling is a lower-bound
scenario, not a throughput claim.

## Verification criteria

PASS requires all six source candidates and both grid identities to be
validated, all decomposed outputs to match the normal path within the existing
Stage 4A tolerance, at least seven timed samples per candidate/grid/stage,
portable CSV/JSON evidence with environment metadata, and a quantitative
comparison that identifies dominant per-evaluation costs and separates them
from evaluation-count costs. Focused tests and `git diff --check` must pass.

This task may write only its new source/docs/tests and compact benchmark
reports. It must leave tracked Stage 4C evidence, external raw runs,
checkpoints, COM parameters, optimizer behavior, constraints, and bounds
unchanged.

## Results (2026-10-09)

**Status: PASS.** All six requested finalists were loaded from the tracked
96k results, all twelve candidate/grid combinations passed numerical parity,
and each combination has seven timed samples after two warm-ups. The pilot
measured the common-grid call at about 0.405 s; the complete run finished in
about one minute. Input setup and evidence reading were outside timed calls:
context load was 0.079 s and all six result files took 0.0024 s to read and
parse.

The compact result package contains 84 timed rows in
[`measurements.csv`](../../reports/benchmarks/stage5a1_evaluation_profile/measurements.csv)
and environment, identity, parity, sample, and summary data in
[`profile_summary.json`](../../reports/benchmarks/stage5a1_evaluation_profile/profile_summary.json).
The benchmark tool SHA256 at measurement time was
`f579f7d55000024e8740e7d1d78a0c50effa79482f59c9f7af2675a9c7b89e94`; source
HEAD was the requested base `2dc1d9421a1578548bd6cc18e4fbe6e733d0d6b8`.
The SHA256 binds the measured tool version while its implementation was still
being prepared for commit. After measurement, CSV line endings were normalized
to LF for clean diffs; numeric sample values were not changed. The writer now
emits LF directly.

### Per-evaluation timing

The table gives medians of the six per-candidate seven-sample medians. Ranges
show the minimum and maximum of those six candidate medians. Times are
seconds; G is the independently timed candidate-decode plus normal evaluator
path. `G call` excludes candidate decoding, matching the Stage 4C timer span.

| Stage | Search, 1,001 points | Common, 9,113 points |
| --- | ---: | ---: |
| A — decode and geometry | 0.000170 | 0.000180 |
| B — DMS COM | 0.037004 | 0.350476 |
| C — resonator COM | 0.006698 | 0.058884 |
| D — admittance composition | 0.000703 | 0.005441 |
| E — network termination/evaluation | 0.000780 | 0.005902 |
| F — metrics and violations | 0.000280 | 0.000681 |
| Sum A–F | 0.046349 | 0.430556 |
| G — normal end-to-end evaluation | 0.046558 | 0.429438 |
| G `_stage4a_evaluate` call | 0.046496 | 0.429372 |
| Range of G call across candidates | 0.044146–0.050456 | 0.409298–0.451453 |

The common/search ratio of per-candidate G-call medians has median 9.22
(range 8.56–10.23), close to the point-count ratio 9.10. The median component
sum differs from G by less than 0.5% on either grid; individual paired samples
vary more, so both measured paths remain in the report.

DMS COM (B) occupies about 79.6% of search-grid and 81.6% of common-grid
evaluator time. Resonator COM (C) occupies about 14.4% and 13.7%. Network
composition and termination together occupy about 3.2% on search and 2.6% on
common. Metrics are below 1%; decode/geometry is below 0.4%. By these
measurements, COM kernels dominate per-evaluation cost.

Across the three selected designs per topology, median G-call times were:

| Topology | Search, 1,001 points | Common, 9,113 points |
| --- | ---: | ---: |
| P_D | 0.045115 s (0.044146–0.045162) | 0.424073 s (0.421575–0.451453) |
| D_P | 0.047829 s (0.047829–0.050456) | 0.434672 s (0.409298–0.436806) |

This sample has D_P 6.0% slower on search and 2.5% slower on common validation
than P_D by topology medians. This is descriptive of these six saved finalists;
it does not establish a general topology cost difference.

### Numerical parity and Stage 4C comparison

Decomposed and ordinary `_stage4a_evaluate()` arrays and records had maximum
absolute difference 0 across all twelve combinations. The checks included Y,
complex S, transducer gain, insertion loss, VSWR, every reported filter metric
and violation, maximum/summed violation, objective, and feasibility. On the
common grid, the ordinary evaluation also matched each saved finalist within
the existing Stage 4A tolerance (`rtol=1e-10`, `atol=1e-12`); the largest
absolute difference was `9.54e-7` in the large scalar objective, with relative
difference inside that tolerance. The grid arrays were loaded from the
Stage 4A context used by Stage 4C and checked against the recorded count,
array/grid identity, and metadata SHA.

The tracked Stage 4C totals are:

| Category | Total |
| --- | ---: |
| Cell wall-clock | 18.057 cell-hours |
| Search evaluator | 15.616 cell-hours |
| Common validation | 0.180 cell-hours |
| Other cell work | 2.261 cell-hours |

The mean Stage 4C evaluator time was 0.05856 s per 96k-budget evaluation;
this profile measured 0.04650 s per 1,001-point search evaluation. The current
measurement is 20.6% lower. Common validation measured 0.42937 s per call
versus 0.50537 s per Stage 4C validation call, 15.0% lower. They agree in
scale and grid scaling, but not exact elapsed time. The Stage 4C run did not
record CPU, BLAS, or thread configuration. Its execution source is available;
the only difference in the evaluation function is an optional geometry-bound
diagnostic override, whose default path preserves the original behavior.
Consequently the time offset cannot be assigned to a code-path change from the
available evidence and should be treated as environment/run variation.

The profiling host was WSL2 Linux on an AMD Ryzen 7 PRO 4750G, 16 logical CPUs
in process affinity, Python 3.12.3, NumPy 2.5.3, and SciPy 1.18.1. NumPy
reports SciPy OpenBLAS 0.3.34 with `MAX_THREADS=64`; thread environment
variables were unset. The process had 31 OS threads after measurement.
`threadpoolctl` was unavailable, so the exact active BLAS pool size is not
reported. Conditions were shuffled with a recorded seed, both timed methods
were warmed twice per condition, and the same provider was reused. No optimizer
cache or candidate-result cache was used.

### Impedance-map scaling estimates

For each impedance pair, assume the Stage 4C budget of 96,000 unique
evaluations, five seeds, and both topologies: ten cell runs per map point and
960,000 evaluations per point. The evaluation-only estimate uses the measured
0.04650 s search evaluator median, about 1.240 cell-hours per cell. The
overhead-inclusive estimate scales the observed Stage 4C mean cell wall time
of 1.8057 hours per cell. Parallel wall time divides the latter by idealized
worker counts; it assumes linear scaling and is a lower bound, not measured
throughput. Both estimates assume per-cell time stays at the 50/50-ohm Stage
4C level across future impedance pairs; impedance-dependent cost variation has
not been measured.

| Map | Impedance pairs | Cell runs | Evaluations | Evaluation-only cell-hours | Stage 4C-scaled cell-hours | Ideal wall hours at 8 / 32 / 128 workers |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5×5 | 25 | 250 | 24,000,000 | 310.0 | 451.4 | 56.4 / 14.1 / 3.5 |
| 10×10 | 100 | 1,000 | 96,000,000 | 1,239.9 | 1,805.7 | 225.7 / 56.4 / 14.1 |
| 41×41 | 1,681 | 16,810 | 1,613,760,000 | 20,842.5 | 30,353.5 | 3,794.2 / 948.5 / 237.1 |

The 31 observed process threads on a 16-CPU affinity mask make linear scaling
particularly optimistic if each worker starts its own default BLAS pool.
Cell-hours count total work; the wall-hour columns assume ideal independent
workers and do not include contention or scheduling overhead.

### Prioritized future work

| Priority | Candidate | Evidence and likely effect | Difficulty / numerical risk | Validation and applicability |
| --- | --- | --- | --- | --- |
| 1 | Measure controlled BLAS thread counts before parallelizing | 31 process threads were present for 16 available CPUs; thread-pool-specific count was unavailable. Runtime effect is unmeasured. | Low-to-medium / low numerical risk | Repeat the same finalist benchmark at 1, 2, 4, and default threads, check the same parity contract. Applies across COM and network solves. |
| 2 | Reduce DMS COM kernel cost | DMS COM accounted for about 80–82% of evaluator time, the largest supported target. No speedup is assumed. | Medium-to-high / medium-to-high numerical risk | Profile section/block internals, then compare Y/S and metrics at the current tolerances across both topologies and providers. The generic COM path can benefit if the kernel is shared. |
| 3 | Reduce required evaluations through initialization or search strategy | Each Stage 4C cell uses 96k evaluations; map cost scales directly with points × seeds × topologies × budget. This profile does not measure savings from an algorithm change. | High / high comparison-validity risk | Requires matched-budget/seed validation and a separate approved study. Algorithmic changes apply broadly; classical SAW initialization is model/topology-specific. |
| 4 | Reduce resonator COM cost | Resonator COM accounted for about 14% of evaluator time. No speedup is assumed. | Medium / medium numerical risk | Profile and parity-check the one-port COM path on both resonator topologies; applicable to other filters using this resonator model. |
| 5 | Optimize network composition or metrics | D/E together were 3.2% on search and 2.6% on common; F was below 1%. Any total benefit is bounded by these measured shares. | Low-to-medium / low-to-medium risk | Keep strict Y/S and metric parity; network path is generic while metrics remain specification-dependent. |

Recommended next task: run the controlled 1/2/4/default BLAS thread-count
comparison on these same finalists before changing the COM kernel or planning
parallel impedance-map throughput.
