# Stage 3.1 convergence — not migrated

The legacy Stage 3.1 experiment is intentionally not a canonical
config-driven target. Its original config,
`configs/studies/stage3_convergence_50ohm.yaml`, references the missing
`configs/stage3_1_convergence_fragment.yaml`.

No replacement fragment is inferred or reconstructed, and this experiment
must not fall back to the Stage 3.2 configuration. Restore the exact fragment
from project history before reintroducing an executable Stage 3.1 experiment.
