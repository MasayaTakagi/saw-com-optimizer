# Stage 3.8C-R1 test summary

Date: 2026-09-23

## Full repository regression

Command: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`

Final result: **224 passed, 14 subtests passed** (76.93 s, after the pilot serializer correction).

The first regression attempt exposed private cross-study imports in the new R1 module. R1-local provider, validation-grid, and L-SHADE configuration adapters resolved the architecture-boundary failure. The full regression was rerun afterward and passed.

The regression includes topology/network/COM tests, material metadata, reporting, orchestration, and R1 geometry-ranking tests. The targeted R1 module suite separately passed **11 tests**.

The first pilot attempt exited during geometry-boundary CSV serialization because a NumPy boolean reached the standard JSON encoder. The serializer now normalizes NumPy scalar types; that partial attempt was not resumed. The clean retry completed the six-cell pilot and produced the gate result below.

The runtime Stage 3.8 topology validation, six fixed-design sanity cases, all six known-design grid preflights, and geometry-valid population construction passed. All six pilot cells reached physics and produced finite search/common-grid metrics. The pilot gate nevertheless failed because geometry rejection during initial sampling exceeded 90% for M0/T2 (93.27%) and MLIT/T2 (91.99%). The required `STAGE3_8C_R1_PILOT_FAIL_STOP` marker was written, and the 96,000-evaluation production rerun was not started.
