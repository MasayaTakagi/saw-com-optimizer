# Stage 3.5 search-space and optimizer efficiency

This experiment compares the frozen Stage 3.4b production initial box (S0)
with the data-informed, boundary-expandable initial box (S1), crossed with the
existing Legacy SciPy DE and L-SHADE backends.

Phase A diagnostics and the frozen S1 config are written under
`artifacts/stage3_5/phase_a_revised/`. Phase C uses the four development seeds
20260917–20260920: all four arms reach 16k/32k, A always reaches 64k, and only
the 32k survivors reach 64k. The final comparison uses one common validation
grid containing the Stage 3.4b final eight designs and current-arm checkpoint
designs. Phase D is intentionally separate and never starts automatically.

All runs are cold-started. Stage 3.4b vectors and populations are not copied
into any arm. Hard bounds, COM/network equations, validation semantics, and
convergence thresholds remain unchanged. The 50 ohm S1 box is evidence for
this study only and must not be copied to other impedance points.

Run Phase C through the asynchronous production launcher:

```text
.venv\\Scripts\\python.exe -m sawopt.orchestration.cli launch --config configs/studies/stage3_5_search_efficiency_screening.yaml --run-dir runs/stage3_5_phase_c_revised --workers 4
```

After Phase C completes, the canonical review bundle is
`artifacts/review_bundles/stage3_5_phase_c_review.zip` and the run stops at
`PHASE_C_COMPLETE_WAITING_FOR_REVIEW`. No Phase D, 192k/256k extension,
impedance sweep, or productionization is started by this experiment.
