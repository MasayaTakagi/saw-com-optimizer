# Stage 4C resonator pair coordinate probe protocol

This is a fixed-design, non-production sensitivity probe for the Stage 4C
`resonator_0_pairs` coordinate. It uses the 96,000-evaluation common-grid
selected finalist from each listed cell and evaluates it on the existing
9,113-point common validation grid. It does not run or resume an optimizer,
rank topologies, qualify the model, or authorize a bound change or production
study.

## Frozen inputs and probe points

Evidence source:
`reports/experiment_reviews/stage4c/20261006_124153_ed50ba/`

Cells: `P_D/20261007`, `D_P/20261007`, `D_P/20261009`, `P_D/20261011`, and
`D_P/20261011`. For each cell, vary only `resonator_0_pairs`; evaluate the
selected value and the distinct values among 60, 65, 70, and 75. Keep the DMS
geometry, resonator wavelength and aperture, 50/50-ohm ports, MLIT/T1 profile,
network convention, frequency grid, objective, and specification fixed.
Values above 75 are outside this probe.

The frozen Stage 4C bounds remain 10–60 pairs and are unchanged. Values above
60 are valid only under the probe-specific geometry assumption that the tested
pair upper limit is 75; this does not establish production geometry acceptance
or authorize a bound change. Under that probe-specific assumption, the existing
checks still cover acoustic length, aperture, electrode dimensions, total
electrodes, and hypothetical die footprint. A geometry-invalid point is
recorded as `INVALID_GEOMETRY` and has no performance comparison.

## Recorded comparison and interpretation

Record violations and filter metrics for each point, plus deltas from that
cell's selected-value baseline. The absolute 0.02 max-normalized-violation
threshold is an internal computational interpretation threshold only; it is
not a manufacturing or measurement tolerance.

Classify the result as `STRONG_BOUND_SIGNAL` only if geometry-valid points above
60 improve max violation by at least 0.02 for at least three of five cells,
with the result not dependent on one exceptional cell. Classify smaller,
cell-dependent, or materially traded-off improvement as `MIXED_BOUND_SIGNAL`.
Classify no consistent improvement or no geometry-valid expansion as
`NO_BOUND_SIGNAL`.

This probe cannot promote `P_D` or `D_P`, formally change the upper bound, or
authorize expanded-bound reoptimization, larger cell matrices, or longer
horizons. A strong signal makes a matched expanded-bound reoptimization plan
the next review task. Mixed or no signal makes COM/model qualification the
next priority. Either path requires a separate review and authorization.

## Execution record — 2026-10-08

The five selected-value baselines reproduced their tracked common-grid
max/sum violations, filter metrics, and constraint violations. All 22 evaluated
points passed the existing geometry/layout checks, including all 15 points
above 60 pairs. At points above 60, stop_2 violation decreased in every cell,
while max violation improved only at `P_D/20261007` with 65 pairs, by 0.00486;
the other 14 expanded points worsened max violation. No point was feasible.
The result is `MIXED_BOUND_SIGNAL`: the only max-violation improvement is below
the internal 0.02 threshold. Topology selection remains
`STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`; production authorization is `NO`. The
next task is COM/model qualification priority.
