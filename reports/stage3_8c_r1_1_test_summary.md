# Stage 3.8C-R1.1 Test Summary

## Targeted tests

- Command: `.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\unit\studies\test_stage3_8c_r1_geometry_gate.py tests\unit\test_sol_review_routing_policy.py -q`
- Result: **14 passed**.
- Coverage includes geometry-first ranking, deterministic conditional initialization for all six material/topology cells, geometry validity, active-bound compliance, uniqueness, no clipping/rounding of emitted population coordinates, conditional geometry formula agreement, active GPT-6 Sol review policy, and a regression for the distinct legacy R1 (90%) versus R1.1 (50%) initializer-rejection gate thresholds.
- Boundary cases hit 750 um acoustic length for T0/T1 and both the 750 um length and 500-electrode limits for T2.

## Full repository suite

- Command: `.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q`
- Result: **227 passed, 14 subtests passed** in 77.83 seconds (final rerun after the gate-threshold regression case).
- No test failures.

## Numerical preflight

- Topology implementation validation: **PASS**.
- Fixed-design sanity: **6/6 PASS**.
- Known-seed search/common-grid preflight: **6/6 PASS**.
- Geometry-valid initial populations: **6/6 PASS**.
- Search grid: 1,001 points; common validation grid ID:
  `2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f`.

## R1.1 Pilot

- Gate: **PASS_AWAITING_REVIEW**, 6/6 cells.
- Every cell used seed `20260917` and 256 unique optimizer evaluations.
- All six cells had valid physics evaluations, solved frequency points, and
  finite search/common-grid metrics.
- Conditional initializer geometry rejection: **0/6 cells**. The separately
  sampled independent-uniform reference estimated 87.17%, 4.32%, and 92.69%
  for M0/T0, M0/T1, and M0/T2; 88.16%, 3.72%, and 92.67% for MLIT/T0, MLIT/T1,
  and MLIT/T2. This is a diagnostic reference, not the R1.1 population.
- Production: **NOT STARTED**.
