# Stage 3.3 optimizer validation

Stage 3.3 compares the existing `scipy_de_legacy` path with the resumable
`lshade` backend. `center_outer_same` remains a wiring identifier; it does not
change the geometry parameterization.

Run the controlled pilot with:

```text
PYTHONPATH=src python -m sawopt run-study \
  --config experiments/stage3_3_optimizer_ab/experiment.yaml \
  --run runs/stage3_3_50ohm --workers 5
```

Use `--resume` to continue L-SHADE seed checkpoints and
`--run-parallelism-benchmark` to measure spawn workers `[1, 2, 4, 5]`.
Each seed writes below its own trial directory; aggregation is parent-only.

The A/B decision is recorded in `algorithm_ab_summary.json`. L-SHADE is not
promoted automatically: the predefined median-quality, basin-hit,
evaluation-efficiency, dense-validation, numerical-failure, and checkpoint
gates must all be reviewed first.
