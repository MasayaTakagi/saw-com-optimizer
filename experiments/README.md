# Config-driven experiments

Each experiment declares a reusable protocol in `experiment.yaml` and may
reference an existing resolved study configuration. Run one with:

```powershell
$env:PYTHONPATH = "./src"
python -m sawopt run-study --config experiments/stage3_2_continuation/experiment.yaml --run runs/stage3_2-continuation
```

The selected protocol is an explicit `study.type` value. Existing configs and
the historical Stage commands remain supported as compatibility aliases.

`stage3_1_convergence/` is a documented, intentionally non-executable
migration placeholder because its exact legacy fragment is missing.
