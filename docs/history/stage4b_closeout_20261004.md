# Stage 4B Closeout — Hybrid Topology Production Comparison

**Closeout date:** 2026-10-04  
**Disposition:** `STAGE4B_EXECUTION_ACCEPTED:TOPOLOGY_SELECTION_UNRESOLVED`

## Authoritative evidence

- Production run: `20261003_014817_ea08db`
- Production source: `c44798266067fa4b8b7d3b2873a798b7a1600ae8`
- Computation fingerprint: `c63910623cb9a5d2a05ecb51f3685becf448f8ac91f169752f1b9703beef8464`
- Review bundle: `reports/stage4b_production_review/20261003_20261003_014817_ea08db/`
- Protocol: MLIT / `T1_SYMMETRIC_5IDT`, fixed 50/50 Ω, topologies `D`, `P_D`, `D_P`, `P_D_P`, five matched cold seeds, 24,000 unique evaluations per cell, 9,113-point common validation grid.

## Integrity and result

All 20 production cells completed and passed the Stage 4B integrity checks. The run is accepted as a valid matched-budget topology comparison and does not need to be repeated.

No topology was filter-feasible: all four finished at 0/5 feasible seeds. Final topology-level medians were:

| Topology | Median max violation | IQR | Median sum violation | Median worst IL (dB) | Median ripple (dB) |
|---|---:|---:|---:|---:|---:|
| D | 0.406567 | 0.005213 | 1.993734 | 3.231093 | 2.071686 |
| P_D | 0.380730 | 0.038509 | 1.852516 | 3.486393 | 2.290020 |
| D_P | 0.387728 | 0.011668 | 1.762396 | 3.460690 | 2.049092 |
| P_D_P | 0.406617 | 0.026917 | 1.839262 | 3.614099 | 2.110611 |

The formal production report returned `STAGE4B_SHORTLIST_IDENTIFIED`, but its conservative IQR fallback retained all four topologies. It therefore did not identify a unique scientific winner.

## External review decision

The practical shortlist for subsequent work is:

- `P_D`
- `D_P`

`D` and `P_D_P` are de-prioritized for the next experiment but are not globally rejected.

Matched-seed lexicographic wins across all pairwise comparisons were `D_P=12`, `P_D=11`, `P_D_P=4`, `D=3`. `P_D` beat `D` 5–0 and `P_D_P` 4–1; `D_P` beat `D` 5–0 and `P_D_P` 4–1. `P_D` versus `D_P` remained unresolved at 2–3.

## What Stage 4B established

- The present hybrid model can improve relative topology performance, but no tested topology meets the B28 specification under the provisional MLIT/T1 model.
- The dominant terminal violation is usually `stop_2`, the 832–862 MHz upper stopband.
- Broad active-bound saturation is not the evident limiter; only one terminal upper-bound hit on `resonator_0_pairs` was reported across the selected designs.
- `P_D_P` is not prioritized because it did not improve the matched-seed ranking enough to justify its extra complexity and had 4,332 geometry rejections versus 95/103/113 for `D`/`P_D`/`D_P`.
- The 50/50 Ω direction sanity check does not show a stable input-side versus output-side resonator preference. The matched worst-IL differences change sign, with median `P_D - D_P` about +0.0257 dB.
- Stage 4B is not a convergence certificate. Median maximum violation still improved materially between 16k and 24k for every topology, so the 24k endpoint must not be treated as a converged optimum.

## Scientific limits

These findings are relative to the provisional MLIT COM profile, `T1_SYMMETRIC_5IDT`, the existing resonator/layout model, and fixed 50/50 Ω ports. They do not establish a calibrated real-device prediction, a globally optimal topology, physical Band 28 feasibility, or a final impedance recommendation.

## Next gate — Stage 4C

Stage 4C is a fixed-50/50 Ω convergence/budget qualification for `P_D` and `D_P` only. It is planning-only at this closeout; no Stage 4C optimization has been launched.

The Stage 4C protocol must predeclare a longer L-SHADE terminal horizon before cold start, retain matched seeds and independent cold starts, preserve the 9,113-point validation grid, and include checkpoints that can determine whether the late Stage 4B improvement persists or plateaus. Because the L-SHADE population schedule depends on the declared terminal horizon, the Stage 4B 24k trajectories must not simply be reinterpreted as trajectories generated under a longer horizon.

Possible Stage 4C outcomes are: promote one topology with robust matched-seed/convergence evidence; retain both if they remain unresolved; or reconsider the design/model space if neither approaches a credible near-feasible region.

The final asymmetric `Zs × Zl` study remains gated on a sufficiently stable topology/design-space direction and a physically qualified COM/material model. If Stage 4C leaves `P_D` and `D_P` unresolved, both remain eligible for later `Zs != Zl` work.
