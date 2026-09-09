# Stage 3 convergence benchmark

Run the cold-seed DMS benchmark from the repository root:

```text
PYTHONPATH=src python -m sawopt.optimization.convergence_study \
  --config configs/studies/stage3_convergence_50ohm.yaml \
  --run runs/convergence-50ohm-dms
```

The benchmark evaluates every configured DMS wiring at 1x/2x/4x budget with
cold seeds. It writes `convergence_report.html`, `convergence_summary.json`,
and `convergence_trials.csv`. A status is evidence about remaining optimizer
budget only: `converged`, `likely_underoptimized`, or `inconclusive`. It never
claims a global optimum.

For reproducible outer parallel jobs, keep each seed/wiring/run tag unique and
set the following environment variables before launching workers:

```text
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
```

This prevents BLAS threads from multiplying the process-level seed/wiring
parallelism. Benchmark mode disables warm starts and early stopping. Warm
resume, when explicitly enabled for production, is a warm restart from the
checkpoint best candidate and is not exact Differential Evolution population
continuation.
