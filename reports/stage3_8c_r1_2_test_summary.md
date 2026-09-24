# R1.2 Final Confirmation Source Test Run (2026-09-24)

These results apply to the frozen Final Confirmation / Production candidate source and configs. The earlier R1.2 pilot history below describes the previous pilot; it is not the Final Confirmation run.

- Source/config fingerprint: `4465b7177b15ab44c10576a7c3d3bf0363c79a7dafa46ef8452a45626407824d`
- Targeted command: `.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\unit\studies\test_stage3_8c_r1_geometry_gate.py tests\unit\test_sol_review_routing_policy.py -q`
- Targeted result: **22 passed** in 27.54 seconds.
- Full suite command: `.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q`
- Full suite result: **235 passed, 14 subtests passed** in 99.64 seconds.
- GPT-6 Sol routing policy regression: **PASS** (included in targeted command).

# Stage 3.8C-R1.2 Test and Pilot Summary

## Targeted tests

- Command: `.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\unit\studies\test_stage3_8c_r1_geometry_gate.py tests\unit\test_sol_review_routing_policy.py -q`
- Result: **19 passed** in 27.21 seconds (final rerun after review-table update).
- Coverage includes deterministic replay, all six material/topology cells,
  canonical bounds, 100% accepted geometry validity, independent-uniform
  endpoint mass, Monte Carlo distribution comparison, R1.1 distribution-bias
  detection, no-repair rejection, attempt-cap exhaustion, and the diagnostic-
  only initializer rejection fraction gate.

## Full repository suite

- Command: `.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q`
- Result: **232 passed, 14 subtests passed** in 98.07 seconds (final rerun after review-table update).
- No test failures.

## Numerical preflight

- R1.2 implementation and topology validation: **PASS**.
- Fixed-design sanity: **6/6 PASS**.
- Known-seed search/common-grid preflight: **6/6 PASS** with finite metrics.
- Initializer-only Monte Carlo reference: 10,000 proposals per cell; all six
  initializer distribution and diversity regression gates passed.
- Historical R1 seeded initializer replay: **6/6 exact** for recorded attempts,
  rejections, and accepted random members.
- Common validation grid: 9,113 points,
  `2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f`.

## R1.2 pilot

- Result: **`STAGE3_8C_R1_2_PILOT_PASS_AWAITING_REVIEW`**, 6/6 cells.
- Each cell used seed `20260917` and 256 unique optimizer evaluations.
- Accepted populations were exact size and 100% geometry-valid; all uniqueness,
  diversity, Monte Carlo distribution, runtime, and finite-attempt-cap checks
  passed. Geometry rejection is reported as a diagnostic, not a gate.
- Population generation time was 0.021–0.183 seconds. Initial geometry
  rejection ranged from 1.65% to 92.99% across cells.
- All six cells completed physics evaluations and produced finite search and
  common-grid metrics; fixed-design sanity remained 6/6 PASS.
- Performance interpretation: diagnostic only (`promotion_eligible=false`,
  `seed_consistency=N/A_single_seed`). R1.1 and R1.2 use different initializer
  distributions, so performance deltas are not optimizer regressions. M0 and
  MLIT aperture ranges differ and confound cross-material comparisons.
- Production: **NOT STARTED**.

## Sol routing

- Requested target: `gpt-6-sol`; the review request was accepted and judgment
  received. The runtime does not expose resolved backend identity, so it is
  **NOT VERIFIED**. Routing policy regression test passed.
