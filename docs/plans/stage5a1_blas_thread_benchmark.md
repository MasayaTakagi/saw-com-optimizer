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
Default BLAS. If the single-process results show no material latency change,
the parallel matrix may be narrowed to Single and Default to keep total
measurement time within the 15-minute cap; both settings remain mandatory.
Record the reason and the omitted settings. These processes evaluate only the
six saved finalists; they do not invoke optimizer code. Use 96 jobs per batch,
assigned round-robin over those six candidates, two untimed warm-up calls per
worker, and two batches per worker-count/BLAS combination. Shuffle the
condition order with a recorded seed. Every worker is a fresh Python process
with its BLAS environment set before import.

Measure process launch/context preparation separately from the synchronized
evaluation window. Report total batch wall time, evaluation-window wall time,
jobs/second, throughput relative to one worker at the same BLAS setting, CPU
time used, observed CPU utilization, process thread counts, and sampled peak
aggregate worker RSS. Distinguish total worker RSS from cell-hours or a
production optimizer's total runtime. The parent samples Linux `/proc` while
workers run; worker CPU time is measured with `time.process_time()`.

First run a short worst-case pilot (four workers, default BLAS, 24 jobs) in a
fresh process set. Do not begin the full matrix if its projected total runtime
exceeds 15 minutes. Enforce a 15-minute overall limit and stop further
conditions at the limit, retaining only completed results as PARTIAL.

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

Results and conclusions will be appended after measurement. They will state
the fastest single-evaluation setting, best observed multi-worker throughput,
uncertainty, whether DMS COM remains dominant, practical per-worker BLAS
recommendations, and follow-up work. Measured latency improvements will not
be presented as guaranteed production speedups.
