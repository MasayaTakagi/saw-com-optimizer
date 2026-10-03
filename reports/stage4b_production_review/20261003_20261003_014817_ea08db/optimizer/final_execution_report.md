# Stage 4B Hybrid Topology Production Comparison

**State: `STAGE4B_EXECUTED_REVIEW_PENDING`** — Codex analysis only; external GitHub review is pending.

- Run ID: `20261003_014817_ea08db`
- Production source SHA: `c44798266067fa4b8b7d3b2873a798b7a1600ae8`
- Computation fingerprint (schema v2): `c63910623cb9a5d2a05ecb51f3685becf448f8ac91f169752f1b9703beef8464`
- Integrity: `20/20` completed; `PASS`
- Protocol: 4 topologies × 5 matched seeds × 24,000 unique decoded evaluations = 480,000 total.
- Decision: `STAGE4B_SHORTLIST_IDENTIFIED`
- P_D / D_P sanity: `PASS`

## Topology summary

| Topology | Feasible seeds | Median max violation | IQR | Median sum violation | Median worst IL dB | Median ripple dB |
|---|---:|---:|---:|---:|---:|---:|
| D | 0/5 | 0.4065669972737998 | 0.0052128792144383596 | 1.9937341496597805 | 3.231093142627548 | 2.0716861474418544 |
| P_D | 0/5 | 0.3807299270539546 | 0.038508636839501176 | 1.8525157910901613 | 3.4863926167455617 | 2.29002004574612 |
| D_P | 0/5 | 0.38772820094128185 | 0.011668146102836618 | 1.7623963444862747 | 3.4606901123439093 | 2.049092249288802 |
| P_D_P | 0/5 | 0.4066174806192623 | 0.026917483872898662 | 1.8392619739232763 | 3.6140986355719553 | 2.1106112831754222 |

## Decision rationale

No primary/fallback pair met the strict paired gate; every topology within the maximum observed five-seed IQR of the leader on the first discriminating median metric is included.

## Scientific limitations

This is a relative topology comparison under the current provisional MLIT COM profile, T1_SYMMETRIC_5IDT model, existing resonator model, and fixed 50/50 ohm ports. It does not confirm real Band 28 device feasibility, calibrated physical prediction, a real-device optimum, a final topology optimum, or an impedance recommendation. Stage 4A smoke results are not used as scientific ranking evidence.

The review state remains `STAGE4B_EXECUTED_REVIEW_PENDING`; this report does not say `STAGE4B_ACCEPTED`.
