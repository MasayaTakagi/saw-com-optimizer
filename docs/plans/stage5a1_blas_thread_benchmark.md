# Stage 5A-1 BLAS thread and evaluation throughput benchmark

## Purpose and boundary

This study compares OpenBLAS thread limits for the existing Stage 4C hybrid
filter evaluation. It separates single-process evaluation latency from
throughput across independent evaluation processes. It does not modify COM,
network, optimizer, or application-wide BLAS behavior, and does not run an
optimizer or resume a production job.

The prerequisite Stage 5A-1 evaluation profiler was merged by PR #33. The
benchmark branch starts from the then-current `origin/main`; the profiler and
its Stage 4C evidence are inputs and must remain unchanged.

## Fixed input and grids

Reuse the Stage 4C MLIT/T1 context and the saved 96k
`common_grid_selected_finalist` candidate vectors for:

| Topology | Seeds |
| --- | --- |
| P_D | 20261007, 20261009, 20261011 |
| D_P | 20261007, 20261009, 20261011 |

Source and load are 50 ohm. Use the exact 1,001-point search and 9,113-point
common-validation arrays checked by the existing profiler. The runner must
fail on a missing candidate, a decoded-design mismatch, or a grid identity
mismatch; it must not substitute data.

## Thread configurations and process isolation

Run each single-process setting in a fresh Python process. Apply the setting
to the child environment before importing NumPy/SciPy or the profiler:

| Setting | Child `OPENBLAS_NUM_THREADS` |
| --- | --- |
| Single | `1` |
| Dual | `2` |
| Quad | `4` |
| Default | unset |

Keep and record other relevant thread variables (`OMP_NUM_THREADS`,
`MKL_NUM_THREADS`, `BLIS_NUM_THREADS`, `VECLIB_MAXIMUM_THREADS`, and
`NUMEXPR_NUM_THREADS`). Record any inherited non-empty values as possible
confounders. Use the benchmark-only `threadpoolctl` optional dependency to
record each loaded BLAS library and its effective thread count. An explicit
setting is valid only if every loaded BLAS pool reports that count. Default
is valid only when `OPENBLAS_NUM_THREADS` is absent and every loaded BLAS pool
reports its effective count. Invalid/missing runtime evidence blocks the
corresponding comparison.

## Single-process evaluation protocol

Invoke the existing Stage 5A-1 staged profiler in a fresh process for each
setting. Retain its decomposition, numerical parity checks, exact-grid checks,
candidate checks, warm-up and timing implementation. Use two warm-ups and
seven timed repetitions per candidate/grid/stage, fixed-seed shuffled
condition order, and wall-clock `perf_counter` timing. Record setting order,
process thread count, CPU affinity, memory, platform, Python, NumPy, SciPy,
thread environment and all active BLAS pools. Save median, minimum, maximum,
and MAD for DMS COM, resonator COM, Y composition, network evaluation,
metrics, and end-to-end evaluation. Compare setting results against the
same-host Default condition; the earlier Stage 5A-1 profile is historical
context only.

## Independent-process throughput protocol

Measure the fixed search-grid end-to-end Stage 4A evaluation with worker
counts 1, 2, and 4. The default comparison includes Single, Dual, Quad, and
Default BLAS. After reviewing single-process results, the parallel matrix may
be narrowed to Single and Default if other settings show no material latency
change. Retain any setting with a material single-process advantage for a
parallel comparison; omit settings that are slower or otherwise unpromising.
Single and Default remain mandatory. Record the reason and omitted settings.
These processes evaluate only the six saved finalists; they do not invoke
optimizer code. Use 96 jobs per batch, assigned round-robin over those six
candidates, two untimed warm-up calls per worker, and two batches per
worker-count/BLAS combination. Shuffle the condition order with a recorded
seed. Every worker is a fresh Python process with its BLAS environment set
before import.

Measure process launch/context preparation separately from the synchronized
evaluation window. Report total batch wall time, evaluation-window wall time,
jobs/second, throughput relative to one worker at the same BLAS setting, CPU
time used, observed CPU utilization, process thread counts, and sampled peak
aggregate worker RSS. Distinguish total worker RSS from cell-hours or a
production optimizer's total runtime. The parent samples Linux `/proc` while
workers run; worker CPU time is measured with `time.process_time()`.

First run a short worst-case pilot (four workers, default BLAS, 24 jobs) in a
fresh process set. Project each full batch as its measured process/context
setup time plus the pilot evaluation-window time scaled by the job-count
ratio, then multiply by condition count and a 1.25 safety factor. Do not begin
the full matrix if its projected total runtime exceeds the remaining
15-minute allowance. Enforce that overall limit and stop further conditions
at the limit, retaining only completed results as PARTIAL.

## Numerical comparison

For every single-process BLAS setting, use the existing Stage 4A parity
tolerance (`rtol=1e-10`, `atol=1e-12`) against the ordinary evaluator and the
saved finalist on the common grid. Do not loosen tolerance. The compared
outputs include Y, S, transducer gain, filter metrics, violations, objective,
and feasibility. Any mismatch invalidates that setting's timing results.
Parallel workers must also check representative decomposed-versus-normal
evaluation parity under their active BLAS setting before the timed window.

## Reproducibility and output

Commit the protocol, runner, and tests before measuring. The measured runner
must record its commit SHA, source SHA256, configuration, environment, grid
and candidate identities. If an earlier committed run produced complete,
parity-passing single-process profiles but its parallel phase failed, reuse
those serial CSV/JSON files only after validating their source identity,
candidate/grid identity, repetition counts, and effective BLAS settings; the
parallel phase still runs from the current committed runner and its provenance
is recorded separately. Write raw per-run CSV/JSON under a temporary
directory outside the repository; never overwrite an existing output. After
checking completeness and parity, copy only compact CSV/JSON evidence into
`reports/benchmarks/stage5a1_blas_threads/` and commit it separately from the
measurement code.

Focused tests cover environment construction, active-pool validation,
condition selection, numeric result validation, throughput aggregation,
incomplete results, and overwrite refusal. Acceptance also requires the
existing profiler tests, architecture tests, `git diff --check`, and no diff
to evaluation/optimizer/COM modules or Stage 4C evidence.

## Results

### Status, provenance, and conditions

**PASS.** The final selected matrix completed: all four BLAS settings for
single-process profiles and Single, Dual, and Default for independent workers
1, 2, and 4, with two 96-job batches per parallel condition. Quad was omitted
from parallel work because it was slower than Dual on both single-process
grids and slower than Default on the search grid. The measured Dual advantage
was retained for parallel comparison. Single and Default are included as
required.

A preliminary Single/Default parallel matrix was completed before the final
setting selection. Its output remains in temporary storage and was not
overwritten. After the exact serial summary showed a material Dual advantage,
the final 18-batch matrix below was run. The final review package contains that
matrix only. The cumulative benchmark timer, including earlier discarded
attempts, is 769.43 seconds of the 900-second limit.

The final runner used clean source commit `19a13a5558874a5160259cc73367ea7545a496ff`
with SHA-256
`14f66ef9a167d6b727b50ab7a2351a9d258095fd3a072a4a1dcf636099552afd`.
It is based on the current main commit `c176f7f9c24b6644902825f32e9f20aa824c77fe`.
The valid single-process profiles were produced by earlier committed runner
`6421d1e61ce055b3d7f5fe3b262d7a435ab7a9a0` (runner SHA-256
`6e057d7b27c3431e8775f70f1d587ec79c7ce2d331740af65f0706857ad6b267`). That
source run was marked PARTIAL only because its parallel pilot rejected the
same BLAS libraries in different enumeration orders. The serial measurements
passed validation and were rechecked for complete candidates, exact grids,
seven repetitions, numerical parity, and active thread counts by the final
runner. Its parallel phase was repeated from the final runner.

The fixed candidates, 50/50 ohm terminations, and exact grid identities match
the Stage 4C evidence. The search grid identity is
`212dd2b0b71ddeffb7a8865937d132ee596870f25c989ac7d90c5dab6fd7faa0`; the
common grid identity is
`2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f`.
The final summary records all six candidate evidence hashes and both grid
identities.

Environment: WSL2 Ubuntu 24.04, Linux kernel `6.18.40.1-microsoft-standard-WSL2`,
AMD Ryzen 7 PRO 4750G, 16 logical CPUs and 16 CPUs in affinity, Python 3.12.3,
NumPy 2.5.3, SciPy 1.18.1. Parent `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`,
`MKL_NUM_THREADS`, `BLIS_NUM_THREADS`, `VECLIB_MAXIMUM_THREADS`, and
`NUMEXPR_NUM_THREADS` were unset. `threadpoolctl` found two OpenBLAS libraries:
SciPy `0.3.31.dev` and NumPy `0.3.34.106.0`, both Haswell/pthreads. Both
libraries reported effective counts 1, 2, and 4 for Single, Dual, and Quad;
both reported 16 for Default. The effective values were checked after
evaluation imports and again after worker preflight.

Serial condition order was `quad, single, default, dual`; each setting used
two warm-ups and seven timed repetitions per candidate/grid. The parallel
condition order used fixed seed `20261010`; each worker used two warm-up calls.
The default four-worker/24-job pilot passed before the full matrix. Candidate
and COM results were recomputed for each timed call; the recorded profiler
states that neither optimizer cache nor candidate-result cache was used.
Repeated calls share the loaded process context/provider, so this protocol
does not measure cold process startup as part of the evaluation window.

### Single-process timings

The following values are milliseconds and are the median of six candidate
medians. `G call` is the ordinary `_stage4a_evaluate` call; `G total` includes
candidate decode plus that call. The auxiliary CSV derives A and `sum A–F`
from the preserved per-run samples using the same six-candidate aggregation.
The main summary CSV retains median, minimum, maximum, and MAD for each
reported stage.

| Grid | Setting | A decode/geometry | B DMS COM | C resonator COM | D Y composition | E network | F metrics | G call | G total | G call vs Default |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Search, 1,001 | Single | 0.177 | 37.198 | 6.882 | 0.698 | 0.772 | 0.303 | 46.599 | 46.682 | 1.019× |
| Search, 1,001 | Dual | 0.165 | 35.718 | 6.349 | 0.695 | 0.717 | 0.280 | 45.163 | 45.238 | 1.051× |
| Search, 1,001 | Quad | 0.177 | 39.443 | 6.829 | 0.779 | 0.760 | 0.296 | 50.966 | 51.037 | 0.932× |
| Search, 1,001 | Default | 0.187 | 38.231 | 6.713 | 0.726 | 0.796 | 0.286 | 47.482 | 47.565 | 1.000× |
| Common, 9,113 | Single | 0.190 | 365.371 | 60.058 | 5.111 | 5.369 | 0.687 | 439.153 | 439.261 | 1.033× |
| Common, 9,113 | Dual | 0.173 | 329.806 | 56.335 | 5.037 | 5.191 | 0.610 | 409.047 | 409.121 | 1.109× |
| Common, 9,113 | Quad | 0.187 | 374.179 | 61.183 | 5.358 | 5.409 | 0.635 | 435.562 | 435.625 | 1.041× |
| Common, 9,113 | Default | 0.182 | 363.878 | 62.936 | 5.487 | 5.876 | 0.731 | 453.562 | 453.662 | 1.000× |

Common/search `G total` ratios were 9.41× Single, 9.04× Dual, 8.54× Quad,
and 9.54× Default, near the point-count ratio of 9.10. DMS COM accounts for
about 80.4% of Default search evaluation and 80.2% of Default common-grid
evaluation; resonator COM accounts for about 14.1% and 13.9%. Geometry,
composition, network termination, and metric calculation are individually
small compared with COM.

`sum A–F` minus `G call` ranges from −1.58 to +0.74 ms on search and −17.45
to +13.71 ms on common. These are independently timed paths, not an exact
additive accounting identity. The differences are within 3.9% of the full call
time; candidate-level minimum/maximum/MAD data are retained in the CSVs.

Dual was the fastest setting in the median single-process measurement on both
grids: 5.1% faster than Default on search and 9.8% faster on common. Quad was
7.3% slower than Default on search and 4.1% faster on common, while remaining
slower than Dual on both grids. These are small fixed-host microbenchmark
comparisons, not evidence for a universal BLAS optimum.

For Default, candidate-median `G call` times were:

| Grid | P_D candidates (ms) | P_D median | D_P candidates (ms) | D_P median |
| --- | --- | ---: | --- | ---: |
| Search | 44.217, 46.225, 47.904 | 46.225 | 47.060, 53.633, 53.309 | 53.309 |
| Common | 408.007, 448.104, 433.122 | 433.122 | 459.021, 500.685, 465.279 | 465.279 |

These are descriptive differences among three saved finalists per topology;
they do not establish a general topology cost difference. Across the same
candidate set, the earlier Stage 5A-1 Default profile reported 46.496 ms
search and 429.372 ms common-grid `G call`. The current values are 2.1% and
5.6% higher respectively. That historical same-host result is context only;
the current shuffled, same-run BLAS comparison is the primary contrast.

### Independent-process throughput

Each cell below reports the median of two 96-job batches. Setup includes fresh
worker launch and context loading; the evaluation window is reported
separately. RSS is peak aggregate worker memory. CPU utilization is aggregate
worker CPU time divided by the evaluation window and the 16-CPU affinity.

| BLAS | Workers | Evaluations/s (min–max) | Speedup vs one worker | Setup s | Eval window s | Total batch s | Peak RSS MiB | Peak threads | CPU use |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Single | 1 | 19.12 (18.62–19.61) | 1.000× | 1.280 | 5.025 | 6.306 | 118.5 | 1 | 6.0% |
| Single | 2 | 33.06 (32.54–33.58) | 1.729× | 1.471 | 2.905 | 4.375 | 233.7 | 2 | 12.0% |
| Single | 4 | 48.56 (46.50–50.63) | 2.541× | 1.858 | 1.980 | 3.838 | 454.4 | 4 | 22.7% |
| Dual | 1 | 19.34 (19.18–19.49) | 1.000× | 1.328 | 4.965 | 6.293 | 118.5 | 3 | 6.1% |
| Dual | 2 | 32.66 (32.51–32.81) | 1.689× | 1.473 | 2.939 | 4.412 | 233.4 | 6 | 11.9% |
| Dual | 4 | 47.24 (47.03–47.45) | 2.443× | 1.849 | 2.032 | 3.881 | 456.0 | 12 | 23.0% |
| Default | 1 | 20.03 (20.00–20.06) | 1.000× | 1.401 | 4.793 | 6.193 | 117.0 | 31 | 6.1% |
| Default | 2 | 31.17 (30.32–32.01) | 1.556× | 1.569 | 3.083 | 4.652 | 233.6 | 62 | 12.0% |
| Default | 4 | 46.57 (45.26–47.87) | 2.325× | 2.069 | 2.063 | 4.132 | 458.3 | 124 | 22.6% |

Single gave the highest four-worker median throughput (48.56 evaluations/s,
2.54× the single-worker result), with Dual close at 47.24/s and Default at
46.57/s. At four workers all three timing ranges overlap. Two repetitions per
condition and one randomized block are not enough to establish a small
throughput difference as statistically reliable. Default loaded two 16-thread
OpenBLAS pools per worker; at four workers it exposed 124 process threads on
16 affinity CPUs. Single exposed four total threads, Dual twelve. This is an
oversubscription warning for Default, not proof that every thread was active
at once. Peak aggregate memory was about 454–458 MiB at four workers.

### Numerical validation and Stage 4C comparison

All four serial settings passed 12/12 decomposed-versus-normal evaluations
with `rtol=1e-10`, `atol=1e-12`. Y parameters, network S and transducer gain,
insertion loss, VSWR, all metrics and violations, objective, and feasibility
had maximum absolute difference 0.0. Each common-grid result also passed
comparison with its saved finalist; maximum absolute difference was
`9.54e-7` (objective), within the existing relative/absolute tolerance. Every
parallel batch passed its active-BLAS preflight and repeat comparison; both
recorded maximum absolute differences were 0.0. No tolerance was loosened.

The Stage 4C evidence totals 15.616 cell-hours of search evaluation,
0.180 cell-hours of common validation, 2.261 cell-hours of other runtime, and
18.057 cell-hours of cell wall time across ten cells. Search evaluation time
per unique decoded evaluation has median 57.72 ms, mean 58.56 ms, and range
57.39–63.21 ms. This is about 21% above the current standalone Default
`G total` search median of 47.57 ms. Stage 4C includes work around optimizer
evaluation callbacks and its own runtime/accounting path, so the difference
is not a measured speedup or a direct prediction for a future run. The earlier
Stage 5A-1 Default profile and the current standalone result are closer in
scale, but still differ by 2.1–5.6% between measurement sessions.

### Recommendation and limitations

- For a single isolated evaluation, Dual was fastest in these seven-repeat
  medians. Treat the result as a candidate setting, especially for the
  9,113-point common grid.
- For independent search-grid jobs, start with Single per worker and test up
  to four workers on this 16-CPU host. It had the best observed four-worker
  median, avoided Default's 124-thread exposure, and used about 454 MiB peak
  aggregate RSS. Dual was close. Validate the exact setting with the actual
  optimizer/checkpoint workload before adopting it for production or a map.
- DMS COM remains the dominant per-evaluation cost. The next performance task
  should profile DMS COM kernels and allocations in isolation before selecting
  an implementation change; keep optimizer evaluation-count reduction as a
  separate workstream.

Only one machine was measured. Parallel cells have two batches each, candidate
order was fixed-seed shuffled, the worker job set contains six repeated
finalists, and the timer excludes fresh-process startup from the evaluation
window. The benchmark does not establish production optimizer or impedance-map
wall-clock speed, common-grid parallel throughput, or the best setting on
other CPUs/BLAS builds. No production optimizer, Stage 4C resume, COM model,
bounds, design variable, or historical Stage 4C evidence was changed.

The committed evidence is under
`reports/benchmarks/stage5a1_blas_threads/`: `benchmark_summary.json`,
`single_process_samples.csv`, `single_process_summary.csv`,
`single_process_auxiliary_summary.csv`, `parallel_batches.csv`, and
`parallel_summary.csv`. The summary records the measurement source commit,
tool hash, environment, grids, candidate hashes, order, and parity results.
