# Experiment lifecycle

Experiment-specific configuration and orchestration live with the active
study. Reusable topology definitions belong in `problem/`, reusable search
and accounting services in `optimization/`, and result packaging in
`reporting/`.

Run the current DMS topology study through
`configs/studies/dms_topology_screening.yaml` and the `dms_topology_screening`
study adapter. The hybrid workflow uses
`configs/studies/hybrid_50ohm.yaml` and `sawopt.studies.hybrid`.

When a study closes, record its conditions, results, decision, limits, and raw
artifact locations in `docs/history/experiment_register.md`. Update
`docs/history/current_baseline.md` only when the result changes an adopted
assumption. Then remove study-only code, configuration, and tests when they no
longer serve an active workflow.
