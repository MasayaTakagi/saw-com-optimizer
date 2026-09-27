# Sol judgment packet: Stage 3.9 close decision

Date: 2026-09-27

## Decision requested

Provide bounded judgment on whether Stage 3.9 may close under roadmap exit
branch (b), as an empirical engineering closeout of the current 50/50-ohm
DMS-only reference path, without another production experiment. Specifically:

1. Does the accepted MLIT/T1 two-seed 8k-to-16k evidence, late plateau,
   common-grid infeasibility, and lack of active search-bound pressure satisfy
   branch (b) for that current reference path?
2. May MLIT/T2 remain documented as unresolved and not promoted, without a
   further T2 run blocking Stage 3.9 closure?
3. Is another MLIT/T1 budget extension low-value given the 14k-to-16k gains?
4. Confirm the conclusion must not claim global physical/topological
   impossibility, material superiority, or a feasible/near-feasible reference.

Do not implement changes, authorize a production run, or review unrelated
orchestration/code changes.

## Applicable project rules

`AGENTS.md` requires Sol judgment where multiple reasonable interpretations
of a specification exist, and for any change to budgets that could affect
comparison fairness. The Stage 3.9 roadmap exit gate is either a stable
feasible/credible near-feasible 50/50-ohm reference with convergence/boundary
evidence, or a documented conclusion that the current model/topology cannot
reach feasibility. The phrase “current model/topology” could mean either the
selected reference path or every explored DMS variant, which is the specific
interpretation in question.

The user has explicitly authorized additional experiments if needed to
complete Stage 3.9. C2C's current PLAN recommends no additional T1 production
run and only a matched 16k T2 extension if Sol decides T2 must be resolved.

## Evidence reviewed

- Stage 3.8C used two seeds and 8k unique evaluations per model/topology cell;
  no candidate was feasible. T2 remained improving at 8k but materially
  trailed T1 at the same budget. The roadmap says T2 must not be promoted just
  because it is underexplored.
- Stage 3.9A: M0/T0 stayed at maximum normalized violation 0.504066 from 2k
  through 8k for both seeds. MLIT/T1 improved to 0.474658 and 0.509609 at 8k,
  without active final search-bound hits; MLIT/T1 was selected for the
  controlled extension. Cross-material rankings remain confounded by
  different aperture bounds.
- The Stage 3.9B accepted Gate D/E evidence establishes the controlled
  MLIT/T1 50/50-ohm 16k continuations, exact 0-8k prefix parity, and valid
  persisted results. The corrected verifier bundle has all 12 gates PASS and
  all 8 seed/checkpoint prefix cells have zero mismatches. C2C accepted this
  result; both final candidates remain infeasible.
- Max normalized violation checkpoints:

  | Seed | 8k | 10k | 12k | 14k | 16k |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | 20260917 | 0.474658 | 0.444978 | 0.432722 | 0.428366 | 0.428364 |
  | 20260918 | 0.509609 | 0.440541 | 0.432042 | 0.430431 | 0.430129 |

- Final common-grid max violation is approximately 0.428503 and 0.430129.
  Stop_1 and stop_2 remain materially violated (roughly 17-18 dB attenuation
  where 30-32 dB is required); VSWR and other constraints also remain active.
  The accepted final designs have no unresolved active search-bound or hard
  geometry violation.
- The formal `grid_converged` and `micro_polish_improvement` fields remain
  null, so formal convergence evidence is incomplete. Checkpoint trajectories
  show 14k-to-16k improvements of about 0.000002 and 0.000301, with two-seed
  agreement near a 0.43 floor.

## Requested judgment boundary

Assess whether these observations are sufficient to close only the selected
current MLIT/T1 50/50-ohm DMS reference path under branch (b), while recording
T2 as unresolved and declining to make a global impossibility claim. If you
judge T2 resolution mandatory, state only the smallest defensible matched
experiment and its fairness requirements; do not authorize it. Otherwise,
recommend closeout documentation and no further production run.
