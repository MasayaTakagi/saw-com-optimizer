# Stage 3.8C-R1 topology fast-screen status

## Final classification

**`SEARCH_SPACE_INVALID` — production screen not run.** The mandated pilot completed but returned `STAGE3_8C_R1_PILOT_FAIL_STOP`; therefore its one-seed, 256-evaluation-per-cell results are diagnostic only and are not promoted as the T0/T1/T2 ranking. No 8k × 2-seed optimization was launched.

## Geometry-gate correction and pilot

The geometry-first ranking correction behaved as intended. All six material/topology cells had geometry-valid incumbents, finite filter metrics on search and common validation grids, and positive physics and solved-frequency counts. Stage 3.8 implementation validation, six fixed-design sanity cases, all six known-design preflights, and geometry-valid initial populations passed.

The stop was caused by geometry rejection during random initial-population sampling:

| Material/topology | Rejected proposals | Geometry rejection rate | Optimizer physics evaluations |
|---|---:|---:|---:|
| M0/T0 | 1176/1337 | 87.96% | 253/256 |
| M0/T1 | 8/187 | 4.28% | 256/256 |
| M0/T2 | 2483/2662 | 93.27% | 251/256 |
| MLIT/T0 | 997/1158 | 86.10% | 251/256 |
| MLIT/T1 | 14/193 | 7.25% | 256/256 |
| MLIT/T2 | 2056/2235 | 91.99% | 253/256 |

Both T2 cases exceed the 90% pilot stop threshold. Seeded replay attributes most rejected T2 proposals to the hard maximum total acoustic length and maximum total electrode count; categories overlap. This makes T2's broad search space inefficient under the unchanged geometry limits. No geometry limits, search bounds, objective, optimizer, or topology physics were altered in response.

## Interpretation limits and next decision

- The invalid Stage 3.8 ranking remains `INVALIDATED_BY_GEOMETRY_RANKING_BUG`.
- The pilot is not sufficient evidence to rank or promote a topology; there is no Stage 3.9 shortlist from this run.
- MLIT used the newer handoff's user-directed 30–180 um aperture range; the archived Stage 3.7D recommendation remains 30–150 um. Cross-material comparisons would therefore be confounded even if production had run.
- T2 needs a bounded search-space/initializer redesign review before another pilot. Such a change requires the project's Sol escalation because optimizer search-space/initialization behavior is affected.
- No third seed, FEM extraction, Stage 3.9 work, hybrid run, or impedance sweep was started. FEM-derived parameters remain necessary before production-qualified device claims.

See [pilot summary](stage3_8c_r1_pilot_summary.md), [geometry gate root cause](stage3_8c_r1_geometry_gate_root_cause.md), and [review bundle](../artifacts/review_bundles/stage3_8c_r1_pilot_review.zip) for run details and machine-readable outputs.
