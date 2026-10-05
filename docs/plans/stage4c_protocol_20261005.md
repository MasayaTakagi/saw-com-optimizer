# Stage 4C confirmatory protocol — 2026-10-05

## Purpose and question

Stage 4C is a fixed-50/50 Ω confirmatory comparison of `P_D` and `D_P`. It
asks: “Under the unchanged provisional MLIT / T1_SYMMETRIC_5IDT / fixed-50/50-ohm
model and design bounds, does a substantially longer L-SHADE horizon produce a
robust matched-seed preference between P_D and D_P, or are the two topologies
practically unresolved?”

Stage 4C is not an impedance, COM calibration, design-space expansion, material
comparison, or production-feasibility study. It changes neither source/load
impedance nor any model, specification, or design bound.

## Stage 4B rationale and read-only trajectory audit

Stage 4B run `20261003_014817_ea08db` completed on source
`c44798266067fa4b8b7d3b2873a798b7a1600ae8` with 24,000 unique decoded
evaluations per cell. Its disposition was
`STAGE4B_EXECUTION_ACCEPTED:TOPOLOGY_SELECTION_UNRESOLVED`. The practical
shortlist is `P_D` / `D_P`; the matched-seed ordering was unresolved. Stage 4B
was not a convergence certificate.

The following audit reads only the committed review package at
`reports/stage4b_production_review/20261003_20261003_014817_ea08db/`. Max
violation values are shown at the four saved checkpoints; values are rounded to
three decimals.

| Topology | Seed | 4k | 8k | 16k | 24k |
| --- | ---: | ---: | ---: | ---: | ---: |
| P_D | 20261002 | 1.674 | 0.736 | 0.464 | 0.361 |
| P_D | 20261003 | 0.889 | 0.777 | 0.486 | 0.406 |
| P_D | 20261004 | 0.975 | 0.696 | 0.550 | 0.381 |
| P_D | 20261005 | 1.540 | 1.000 | 0.495 | 0.365 |
| P_D | 20261006 | 1.790 | 0.826 | 0.492 | 0.403 |
| D_P | 20261002 | 1.008 | 0.715 | 0.463 | 0.388 |
| D_P | 20261003 | 1.383 | 0.696 | 0.438 | 0.393 |
| D_P | 20261004 | 2.070 | 0.926 | 0.571 | 0.399 |
| D_P | 20261005 | 1.395 | 0.654 | 0.483 | 0.364 |
| D_P | 20261006 | 0.746 | 0.636 | 0.539 | 0.381 |

| Topology | Median max violation 4k | 8k | 16k | 24k | Median sum violation 16k | 24k |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| P_D | 1.540 | 0.777 | 0.492 | 0.381 | 2.338 | 1.853 |
| D_P | 1.383 | 0.696 | 0.483 | 0.388 | 2.217 | 1.762 |

All five matched cells for each topology had a material max-violation
improvement from 16k to 24k. The required Stage 4C budgets remain 96k; this
supporting audit does not change the frozen budget.

Per-cell tracked sum-violation and operational diagnostics are below. Runtime
geometry rejection rate is rejected candidates divided by rejected plus
geometry-valid candidates; initializer rate is rejected draws divided by all
initializer draws. Throughput is unique decoded evaluations divided by cell
wall time. `cache/duplicate` shows the recorded cache hits and duplicate
proposals.

| Topology | Seed | Sum violation 16k | Sum violation 24k | Init geometry rejects / draws (rate) | Runtime geometry rejects (rate) | Physics failures | Cache / duplicate | Wall seconds / evals per second | Terminal bound hit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| P_D | 20261002 | 1.574 | 1.948 | 13/247 (5.3%) | 14 (0.058%) | 0 | 50/50 | 1,820 / 13.19 | none |
| P_D | 20261003 | 2.620 | 2.264 | 14/248 (5.6%) | 28 (0.117%) | 0 | 87/87 | 1,845 / 13.01 | none |
| P_D | 20261004 | 2.928 | 1.570 | 15/249 (6.0%) | 25 (0.104%) | 0 | 253/253 | 1,813 / 13.24 | none |
| P_D | 20261005 | 2.139 | 1.649 | 6/240 (2.5%) | 7 (0.029%) | 0 | 152/152 | 1,877 / 12.78 | none |
| P_D | 20261006 | 2.338 | 1.853 | 9/243 (3.7%) | 29 (0.121%) | 0 | 212/212 | 1,873 / 12.82 | none |
| D_P | 20261002 | 1.106 | 1.893 | 12/246 (4.9%) | 17 (0.071%) | 0 | 24/24 | 1,838 / 13.06 | none |
| D_P | 20261003 | 1.914 | 1.642 | 10/244 (4.1%) | 20 (0.083%) | 0 | 150/150 | 1,875 / 12.80 | none |
| D_P | 20261004 | 3.058 | 1.676 | 12/246 (4.9%) | 26 (0.108%) | 0 | 138/138 | 1,849 / 12.98 | none |
| D_P | 20261005 | 2.217 | 2.333 | 7/241 (2.9%) | 30 (0.125%) | 0 | 103/103 | 1,838 / 13.06 | none |
| D_P | 20261006 | 2.902 | 1.762 | 11/245 (4.5%) | 20 (0.083%) | 0 | 105/105 | 1,889 / 12.71 | `resonator_0_pairs` upper |

The committed checkpoint summary does not contain fine best-so-far traces or
`fraction_of_budget_at_last_significant_improvement`. The historical manifest
points to a repository-local raw path that is absent in this host; no raw data
was copied, repaired, or modified. This trajectory field remains unavailable
for Stage 4B.

This audit supports a longer horizon and the choice of `P_D` / `D_P`; it does
not establish either topology as a winner or as converged.

## Frozen protocol

| Item | Frozen value |
| --- | --- |
| Study type / revision | `hybrid_stage4c_confirmatory` / `stage4c_confirmatory_v1` |
| Material / DMS | MLIT / `T1_SYMMETRIC_5IDT` |
| Hybrid topologies | `P_D`, `D_P` only |
| Source / load | 50.0 / 50.0 Ω, independently represented and equal by this study |
| Optimizer | L-SHADE |
| Unique decoded budget per cell | 96,000 |
| Terminal population-schedule budget | 96,000 from initialization |
| Initial population | 18 × 13 = 234 per cell |
| Fresh matched seeds | 20261007, 20261008, 20261009, 20261010, 20261011 |
| Cells / planned production evaluations | 10 / 960,000 |
| Checkpoints | 8k, 16k, 24k, 32k, 48k, 64k, 80k, 96k |
| Start policy | Cold starts; no warm start, parent/topology transfer, or historical population injection |
| Production early stop | Disabled |
| Finalist validation | 16 per checkpoint on the same 9,113-point common grid |

Seeds `20261002` through `20261006` are rejected. The L-SHADE schedule is set
to 96k from the beginning; the run is not a resumed sequence of shorter
terminal horizons.

The protected contract snapshots the unchanged B28 specification; MLIT
profile; T1 active and hard bounds; resonator wavelength, pair-count and
aperture bounds; 40 reflector electrodes; 0.5 metallization ratio; 0.0 gap/λ;
0.04 thickness/λ; `hypothetical_separate_rows` layout; fixed 50/50 Ω
termination; Stage 4A network convention; and the qualified search/common-grid
identities. Search uses exactly 1,001 points with SHA-256
`212dd2b0b71ddeffb7a8865937d132ee596870f25c989ac7d90c5dab6fd7faa0`; common
validation uses exactly 9,113 points, grid ID
`2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f`, and
SHA-256 `54c1daf67dd2bb9242f95e638d7bd801db536acc2c7d6f00c1f62a788bead554`.
The implementation validates these values against Stage 4A’s qualified
configuration and fails closed on drift.

## Convergence and maturity interpretation

The shared `convergence_evidence` rule defines a significant improvement as
absolute improvement of at least 0.02 or relative improvement of at least 1%.
Stage 4C reports these items by cell and checkpoint: grid convergence,
recovery-pending state, boundary-pending state, unresolved hard-bound state,
micro-polish improvement, last-significant-improvement budget fraction, and
evidence completeness. The 64k→80k and 80k→96k comparisons are exposed
separately. The L-SHADE best-so-far trace supplies improvement timing. Fixed
grid identity and the absence of recovery/polish phases in this execution path
are recorded as explicit protocol facts. Late gain uses the existing
convergence helper's primary rank component (maximum normalized violation),
not a newly weighted score. An active hard-bound hit is treated conservatively
as unresolved for maturity.

A cell is mature only when evidence is complete, the grid is stable, recovery
and boundary states are clear, no unresolved hard-bound condition remains,
there is no significant 80k→96k improvement, and the last significant gain is
at or before 80% of the terminal budget. Reaching 96k alone does not establish
maturity. Maturity is post-run interpretation only and never an early-stop
condition.

Stage 4B did not supply a numerical paired-equivalence margin. Before Stage 4C
production, this protocol therefore freezes the following planning judgment;
these margins are not estimated from Stage 4B outcomes: max and sum normalized
violation differences must each be within both 0.02 absolute and 1% relative;
worst in-band IL and ripple must each be within 0.05 dB. Practical equivalence
requires all five final matched pairs inside every margin and all cells mature.
Sol judgment advised that equivalence margins must be declared before results
are seen and that incomplete maturity cannot support equivalence. Sol did not
recommend numerical values. Requested model: `gpt-6-sol`; backend model
identity was not independently verified. The recorded judgment and decision
are in `reports/escalation_packets/stage4c_closeout_margin_sol_2026-10-05.md`.

## Topology ordering and closeout classes

The primary comparison remains feasibility-first and lexicographic over
feasibility, maximum normalized violation, sum normalized violation, and worst
in-band insertion loss. Ripple and stopband metrics remain reported separately;
no weighted scalar score is used. Paired comparisons match each fresh seed.

- `STAGE4C_CLEAR_CONFIRMATORY_WINNER`: one topology wins at least 4/5 matched
  seeds at each of 64k, 80k, and 96k; at least four of those same seeds retain
  that direction at every late checkpoint; the terminal result is mature and
  outside the frozen equivalence envelope for at least four winning pairs.
- `STAGE4C_PRACTICALLY_EQUIVALENT`: all cells are mature, all five final paired
  differences fit the frozen margins, and neither topology has a robust
  matched-seed advantage.
- `STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`: every other outcome, including a
  3–2 split, unstable late direction, material final improvement, incomplete
  convergence evidence, or unresolved boundary limitation.

The report includes feasibility counts, max/sum violation, worst in-band IL,
ripple, stop_1 and stop_2 violation, dominant constraint, active-bound events,
geometry and physics failure counts/rates, duplicate/cache counts, and runtime.
`stop_1` is 703–748 MHz; `stop_2` is 832–862 MHz. Aggregate stop_2 dominance,
median, IQR, and paired P_D−D_P difference are included. Final comparisons are
derived only from the common 9,113-point grid.

## Storage and orchestration

Any later authorized production must use an absolute external persistent
destination below
`C:\Users\sub\Documents\ChatGPT\saw-com-optimizer-runs\production` and
record `external_persistent_v1`. The optimizer never falls back to repository
`runs/`. A non-scientific shakedown, if separately chosen, uses the external
qualification destination `...\qualification\stage4c\`, seed `20261012`,
512 unique evaluations per cell, terminal schedule 512, and checkpoints 400 /
512. This preparation did not run that optional shakedown.

The qualified launch flow remains automated Codex launch, external raw
storage, active-run registry, optimizer terminal state, exact-thread queue
continuation, compact review export, commit/push, then `REVIEW_WAITING`. Queue
E2E was not requalified and no queue continuation was sent. Stage 4C uses its
own review spec and canonical package destination
`reports/experiment_reviews/stage4c/<run_id>/`, with a 2 MiB target and 10 MiB
hard limit. Checkpoints, arrays, populations, histories, and full logs are
excluded.

## Limitations and authorization

MLIT remains a provisional normalized literature profile; this comparison
cannot qualify material parameters or device feasibility. Five matched seeds
cannot establish a global optimum. The frozen bounds and hypothetical layout
can limit interpretation, and an unresolved resonator boundary event keeps
the result unresolved. Stage 4C does not expand bounds or change the
specification.

**Stage 4C production is NOT authorized by this document.** No production
optimization or queue continuation was launched for this protocol preparation.
