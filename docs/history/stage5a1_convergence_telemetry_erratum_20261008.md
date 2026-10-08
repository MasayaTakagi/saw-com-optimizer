# Stage 5A-1: Stage 4C convergence telemetry erratum

Date: 2026-10-08

Affected run: `20261006_124153_ed50ba`
Scope: post-run diagnostic correction only

## Protocol and cause

The frozen Stage 4C protocol in
[`stage4c_protocol_20261005.md`](../plans/stage4c_protocol_20261005.md) remains
the pre-execution record and is unchanged. This dated erratum records a defect
found after the run in how its convergence diagnostic read the saved
best-so-far trace.

`GeometryFirstComparator` prefixes a physics-evaluated feasibility-first key
with geometry and evaluation categories. Its `rank_key[1]` is therefore zero
for every physics-evaluated candidate. The previous trace fallback treated
that coordinate as the scalar primary metric. At the 96,000-evaluation
checkpoint, it consequently identified the initial population evaluation
(234) as the last significant improvement and reported `234 / 96,000 =
0.0024375` for every cell.

For this run, the incumbent remained infeasible, so the scalar trace metric is
`max_normalized_violation`. It is the underlying feasibility-first component
at geometry-first `rank_key[3]`, rather than the geometry/evaluation prefix.
New traces store this scalar explicitly. Legacy traces are interpreted only
when they carry a supported comparator identity or their study caller supplies
that identity and the key has the exact legacy layout. A legacy key without
comparator context remains unknown; geometry-rejected and physics-failed
geometry-first keys do not contain a filter primary metric and remain unknown.
The Stage 4C report path supplies `GeometryFirstComparator` from the study
definition when it reads the legacy checkpoint traces, so those records are
not decoded from tuple shape alone.

## Corrected terminal diagnostics

| Topology | Seed | Previously reported | Recomputed from saved trace |
| --- | ---: | ---: | ---: |
| P_D | 20261007 | 0.00243750 | 0.87157292 |
| P_D | 20261008 | 0.00243750 | 0.95889583 |
| P_D | 20261009 | 0.00243750 | 0.84663542 |
| P_D | 20261010 | 0.00243750 | 0.91519792 |
| P_D | 20261011 | 0.00243750 | 0.79984375 |
| D_P | 20261007 | 0.00243750 | 0.80944792 |
| D_P | 20261008 | 0.00243750 | 0.89879167 |
| D_P | 20261009 | 0.00243750 | 0.83953125 |
| D_P | 20261010 | 0.00243750 | 0.92666667 |
| D_P | 20261011 | 0.00243750 | 0.95780208 |

The corrected fractions were recomputed read-only from the existing checkpoint
`best_so_far_trace` fields for all 80 cell/checkpoint records. No Stage 4C raw
run, checkpoint, or existing review CSV was changed. The committed review CSV
continues to preserve the originally published values; this erratum records
the correction separately.

## Interpretation boundary

These fractions describe when significant changes occurred in the optimizer's
search best-so-far trace. That trace reflects search evaluations on the fixed
search grid. It does not measure improvements on the common validation grid,
and these corrected values do not establish that validation-grid performance
improved at the same evaluations.

This correction changes convergence telemetry only. Candidate selection,
ranking, saved designs, and common-grid validation results are unchanged. The
existing Stage 4C record shows significant improvement from 80k to 96k for all
10 cells, so the topology-selection conclusion remains unresolved and no cell
becomes mature because of this correction.
