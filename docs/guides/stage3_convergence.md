# Stage 3 convergence benchmark

The canonical Stage 3.1 experiment is currently not migrated. The legacy
config references the missing `configs/stage3_1_convergence_fragment.yaml`;
do not substitute the Stage 3.2 config. See
`experiments/stage3_1_convergence/README.md` for the migration status.

Once the exact fragment is restored from project history, run the cold-seed
DMS benchmark from the repository root:

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
