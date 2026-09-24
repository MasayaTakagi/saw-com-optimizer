# Stage 3.8C-R1 pilot summary

- **Gate result: `STAGE3_8C_R1_PILOT_FAIL_STOP`.** The 96,000-evaluation production rerun was not started.
- Run: `runs/stage3_8c_r1_pilot_20260923_retry1`
- Matrix: M0/MLIT × T0/T1/T2; seed `20260917`; 256 unique optimizer evaluations per cell.
- Source fingerprint: `9f10e4d7771715b010fe13f38df5ce6ff1b08b4796857f464cb4162aeed954f4`
- Common validation grid: `2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f`

All six cells passed the evaluator-level pilot checks: each had a geometry-valid incumbent, finite search and common-grid metrics, positive successful physics evaluations, and positive solved-frequency counts. All six known seed designs also passed search-grid and common-grid preflight. Stage 3.8 topology implementation validation and the six fixed-design sanity cases passed.

| Material | Topology | Initial random geometry rejects | Optimizer geometry rejects | Valid physics / 256 | Solved frequency points | Search/common metrics |
|---|---|---:|---:|---:|---:|---|
| M0 | T0 | 1176 / 1337 (87.96%) | 3 / 256 (1.17%) | 253 | 399,061 | finite / finite |
| M0 | T1 | 8 / 187 (4.28%) | 0 / 256 (0.00%) | 256 | 402,064 | finite / finite |
| M0 | T2 | 2483 / 2662 (93.27%) | 5 / 256 (1.95%) | 251 | 397,059 | finite / finite |
| MLIT | T0 | 997 / 1158 (86.10%) | 5 / 256 (1.95%) | 251 | 397,059 | finite / finite |
| MLIT | T1 | 14 / 193 (7.25%) | 0 / 256 (0.00%) | 256 | 402,064 | finite / finite |
| MLIT | T2 | 2056 / 2235 (91.99%) | 3 / 256 (1.17%) | 253 | 399,061 | finite / finite |

## Stop condition

Both T2 cells exceeded the specified 90% geometry-rejection threshold during geometry-valid initial-population sampling. Although rejection sampling eventually constructed valid populations and the optimizer then evaluated valid physics, the high sampling rejection meets the handoff's pilot stop condition. T2's broad pair-count and reflector-count ranges cause frequent violations of both maximum total acoustic length and maximum total electrode count (these categories overlap). This identifies a search-space/initialization efficiency issue; no bounds, manufacturing constraints, objective, or optimizer behavior were changed in response.

Deterministic replay of the recorded initial-sampler seeds counted the violated hard limits on rejected T2 proposals: M0 had 2,382 maximum-acoustic-length hits and 2,483 total-electrode-count hits in 2,662 draws; MLIT had 1,976 and 2,056 such hits in 2,235 draws. Constraint hit counts overlap because a proposal can violate both limits.

The study-local fail marker is present in the run directory. A search-space redesign review is required before any production rerun. The existing production configuration remains gated by this failed pilot, and Stage 3.9, hybrid optimization, and impedance sweeps were not started.
