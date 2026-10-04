# SAW COM Filter Optimizer — Project Goal and Long-Term Roadmap

**Status:** Active project roadmap
**Baseline date:** 2026-10-04

**Current baseline:** after Stage 4B
**Repository:** `saw-com-optimizer`

---

## 1. Purpose

This document defines the long-term engineering objective of the SAW COM filter optimization project and the sequence of work required to reach it.

It is a **living forward-looking document**. Historical experiment results and evidence belong in:

- `docs/history/current_baseline.md`
- `docs/history/experiment_register.md`

Software structure and ownership belong in:

- `docs/architecture_overview.md`

This roadmap should be updated when a major gate changes the adopted technical direction. It should not become a detailed log of every experiment.

---

## 2. Final project goal

The final goal is to determine, with reproducible numerical evidence and a physically qualified model, the **best robustly achievable B28 Rx SAW filter design** when the following are allowed to vary jointly:

- SAW filter topology;
- DMS geometry and relevant discrete/continuous design degrees of freedom;
- ladder-resonator structure and geometry;
- source impedance `Zs`;
- load impedance `Zl`.

The project must not assume that the optimum occurs at `Zs = Zl = 50 Ω`, and it must not assume that the optimum source and load impedances are equal.

For every impedance pair under consideration, the filter itself must be **independently re-optimized**. Comparing one fixed filter under different terminations is not sufficient for the final impedance conclusion.

The final result should answer:

> Under a calibrated COM / network model and realistic manufacturing constraints, what topology, geometry, source impedance, and load impedance give the best achievable B28 Rx performance, and how much improvement is obtained relative to an independently optimized 50/50 Ω reference?

The intended final architecture is expected to be a **DMS + ladder hybrid**, but this is a working hypothesis rather than a predetermined conclusion. The project must retain the ability to reject that hypothesis if the validated evidence favors another topology.

---

## 3. Definition of a successful final result

A final design recommendation is not complete unless it contains all of the following:

| Item | Required final evidence |
|---|---|
| Physical model | COM parameters traceable to measurement and/or FEM, with documented loss, phase, terminal, material, and geometry assumptions |
| Topology | Selected DMS / hybrid topology with alternatives explicitly compared |
| Geometry | Fully specified optimized geometry within manufacturing constraints |
| Port condition | Independently optimized `Zs` and `Zl`, with 50/50 Ω retained as the reference |
| Electrical performance | Common dense-grid evaluation of passband loss/ripple, return loss or VSWR, and stopband attenuation |
| Optimization evidence | Multiple independent seeds, sufficient budget, convergence evidence, and boundary diagnostics |
| Robustness | Sensitivity to manufacturing variation, model uncertainty, and relevant parasitics |
| Reproducibility | Frozen config, source fingerprint, result summary, and review bundle |
| Decision statement | Quantified difference between the selected design and the independently optimized 50/50 Ω reference |

The project should report a Pareto set when meaningful trade-offs remain rather than forcing a single scalar “winner” prematurely.

---

## 4. Current baseline — after Stage 4B

The project has a reusable software architecture with separate `core`, `problem`, `optimizers`, `optimization`, `studies`, `io`, `reporting`, and orchestration layers. Stage 4A qualified the hybrid representation and protocol mechanics. Stage 4B then executed the first matched production comparison of the four hybrid topologies at fixed 50/50 Ω under the provisional MLIT/T1 model. See [`history/current_baseline.md`](history/current_baseline.md) and [`history/experiment_register.md`](history/experiment_register.md).

The historical cleanup is complete, and closed experiment knowledge is retained in the history documents and the annotated Git recovery tag.

Scientifically, the current state is:

- 50/50 Ω remains the comparison reference.
- Source and load impedance must remain independently controllable.
- The Stage 3.6 G1+G2 release is the historical 50 Ω DMS reference.
- T0, T1, and T2 DMS representations are available and validated at the structural/network level.
- Stage 3.8C produced no filter-feasible design.
- The selected MLIT/T1 50/50 Ω DMS reference path closed Stage 3.9 under branch (b); two accepted 16k trajectories plateaued empirically near maximum normalized violation 0.43 while remaining materially infeasible.
- Stage 4B run `20261003_014817_ea08db` completed 20/20 cells (4 topologies × 5 matched seeds × 24,000 unique evaluations) with integrity PASS, but all four topologies remained 0/5 feasible.
- The formal Stage 4B IQR shortlist retained all four topologies, so it did not identify a unique production winner. External review carries `P_D` and `D_P` forward as the practical shortlist and de-prioritizes `D` and `P_D_P` without globally rejecting them.
- `P_D` and `D_P` remained close: the matched-seed lexicographic comparison split 2–3 between them, and the 50/50 Ω direction sanity check found no stable input-side versus output-side worst-IL preference.
- Stage 4B did not establish convergence. Median maximum violation continued to improve materially between 16k and 24k for every topology; the next hybrid gate must predeclare a longer L-SHADE terminal horizon rather than reinterpret the 24k trajectories as a longer-horizon continuation.
- The dominant remaining violation is usually the 832–862 MHz upper stopband (`stop_2`). Broad active-bound saturation was not observed.
- Formal convergence is still not established for the hybrid shortlist; MLIT/T2 also remains unresolved and unpromoted.
- M0 and MLIT cannot yet support a clean material-superiority claim because their provenance and aperture bounds differ.
- MLIT is still an evaluation-only literature profile, not a production-qualified material model.
- The final impedance optimum is unknown. Earlier 45 Ω and 62.5 Ω observations are screening results only and are not final recommendations.

Accordingly, the project is **not ready for the final 2-D impedance sweep**.

---

## 5. Long-term roadmap

| Phase | Main question | Core work | Exit gate |
|---|---|---|---|
| **Stage 3.9 — Search viability and 50 Ω reference recovery (CLOSED 2026-09-27, branch b scoped to MLIT/T1)** | Can the current model/topology/search space produce a credible feasible or near-feasible 50 Ω design? | Decompose active violations by constraint/frequency; improve search coverage and parameterization without silently relaxing physical constraints; resolve obviously inefficient/redundant DOFs; keep common dense validation and reproducible L-SHADE accounting; align material bounds before direct M0-vs-MLIT comparisons or keep the material tracks separate. | Closed for the selected MLIT/T1 50/50 Ω DMS reference path after two accepted 16k trajectories remained materially infeasible near max normalized violation 0.43. MLIT/T2 remains unresolved and unpromoted. This is not a global impossibility result. |
| **Stage 4A — hybrid protocol qualification (COMPLETED)** | Can the hybrid representation use the current accounting, validation, provenance, and checkpoint contracts? | Completed implementation validation, D-only parity, and bounded smoke cells at 50/50 Ω. | Hybrid software baseline is available; no scientific topology ranking or feasible-filter claim follows from the smoke. |
| **Stage 4B — hybrid topology comparison (COMPLETED 2026-10-03)** | Which DMS + ladder architecture should be carried forward? | Compared `D`, `P_D`, `D_P`, and `P_D_P` at MLIT/T1, fixed 50/50 Ω, five matched cold seeds, 24k unique evaluations/cell, and common 9,113-point validation. | Execution/integrity accepted. No topology was feasible. Formal shortlist rule retained all four; external review carries `P_D` and `D_P` as the practical shortlist while keeping topology selection unresolved. |
| **Stage 4C — shortlisted hybrid convergence / budget qualification (NEXT; planning only)** | Do `P_D` and `D_P` retain their relative advantage with a sufficiently long predeclared search horizon, and does either approach a stable near-feasible region? | Fixed 50/50 Ω, MLIT/T1, matched `P_D`/`D_P` seeds, independent cold starts, L-SHADE with a longer terminal horizon fixed before launch, checkpoints that resolve late improvement, common 9,113-point validation, bound/geometry/physics accounting, and explicit 24k→later-checkpoint improvement tests. Do not reuse Stage 4B trajectories as if they had been generated under a longer population-schedule horizon. | One topology may be promoted only with robust matched-seed and convergence evidence. Otherwise retain both. If neither approaches a credible near-feasible region, reconsider the model/design space rather than forcing a winner. |
| **Model Qualification Track — run in parallel, become mandatory before final impedance optimization** | Is the physical model accurate enough for a real impedance conclusion? | Extract/fit COM parameters from FEM and/or measurement; resolve electrode/material assumptions, terminal/phase registry, attenuation/loss conventions, aperture dependence, and parasitics; validate against resonator/device S-parameters; version the calibrated provider. | A calibrated model with documented uncertainty and validation error. No final impedance recommendation is allowed before this gate. |
| **Stage 5 — Calibrated-model re-baseline and geometry release** | Does the selected topology remain valid after physical calibration, and which geometry DOFs are actually needed? | Re-run the 50 Ω reference and selected hybrid topology under the calibrated model; release left/right/asymmetric or additional geometry DOFs progressively; re-check active bounds and parameter correlations; reconsider topology if calibration materially changes the ranking. | A calibrated, converged 50/50 Ω production reference and a frozen design-space definition for impedance exploration. |
| **Stage 6 — Asymmetric impedance exploration** | Where in `(Zs, Zl)` space does the independently re-optimized filter perform best? | Use an outer impedance search and a full inner filter re-optimization for every impedance pair. Preserve separate `Zs` and `Zl`. Begin with a coarse 20–200 Ω real-impedance region or an adaptively selected representative subset, retain 50/50 Ω as a control, then refine promising regions. Warm starts may accelerate computation but must not replace independent global-search protection. If Stage 4C leaves `P_D` and `D_P` unresolved, both must remain eligible because a 50/50 Ω directional tie does not imply equivalence when `Zs != Zl`. | A reproducible impedance-performance map with a small set of candidate regions; no optimum claim based only on sparse screening. |
| **Stage 7 — Deep certification of candidate impedance regions** | Are the apparent impedance gains real and converged? | Increase seeds and budget for the best candidate pairs plus 50/50 Ω; perform late-improvement and boundary checks; compare cold-start and transferred populations where necessary; verify common-grid performance and repeatability. | Stable ranking of the candidate impedance regions with convergence evidence strong enough to support engineering comparison. |
| **Stage 8 — Robust optimization and implementation realism** | Does the advantage survive realistic uncertainty? | Include manufacturing tolerances, material/model uncertainty, electrode/process variation, and relevant package/interconnect parasitics. Evaluate robust or yield-oriented objectives and retain Pareto alternatives where appropriate. | The preferred non-50 Ω or 50 Ω solution remains competitive under uncertainty and does not depend on an unrealistically narrow nominal optimum. |
| **Stage 9 — Physical validation and final release** | Does hardware/FEM validation agree with the predicted design advantage? | Fabricate or otherwise validate the final candidate(s), compare measured/FEM and predicted S-parameters, update the calibrated model if needed, and perform one final optimization/verification loop if discrepancies are material. | Final released design and impedance recommendation with measured/FEM correlation, uncertainty statement, and complete reproducibility package. |

---

## 6. Required sequencing rules

The roadmap is intentionally gated.

**Do not perform the expensive final `Zs × Zl` optimization before both of these are true:**

1. the topology/design-space direction is sufficiently stable at 50/50 Ω; and
2. the COM/material model is physically qualified enough that an impedance optimum has engineering meaning.

Likewise, do not interpret a change in optimum impedance as a pure impedance effect if topology, material model, aperture bounds, objective definition, or optimization budget changed at the same time.

Every production impedance comparison must preserve the principle:

\[
x^*(Z_s,Z_l)=\arg\min_x F(x;Z_s,Z_l)
\]

and the outer comparison must be performed on the optimized value

\[
F^*(Z_s,Z_l)=F(x^*(Z_s,Z_l);Z_s,Z_l).
\]

The project is therefore a nested optimization problem, not a termination sweep of one fixed geometry.

The active repository review path is GitHub-mediated external review. C2C is
frozen as a historical reference and is not a roadmap gate; see
[`guides/github_review_workflow.md`](guides/github_review_workflow.md).

---

## 7. Optimization strategy policy

L-SHADE is the current production search backend because it is the adopted later-stage protocol, not because the historical short-budget A/B proved universal optimizer superiority.

Optimizer strategy may be revisited when the dimensionality or topology changes substantially. A new benchmark is justified especially when moving from DMS-only to a higher-dimensional hybrid/full-asymmetric design space.

Potential later improvements such as surrogate-assisted search, multi-fidelity search, or specialized mixed-variable methods should be introduced only after the baseline problem and validation contract are stable. They are acceleration tools, not substitutes for model qualification or convergence evidence.

---

## 8. Documentation and evidence policy

The repository should distinguish four document roles:

| Document | Role |
|---|---|
| `docs/project_roadmap.md` | Forward-looking goals, sequencing, and gates |
| `docs/history/current_baseline.md` | Current adopted scientific assumptions and unresolved questions |
| `docs/history/experiment_register.md` | Closed experiment results, decisions, evidence limits, and provenance |
| `docs/architecture_overview.md` | Current software architecture and ownership boundaries |

At each major study closeout:

1. record the experiment result in `experiment_register.md`;
2. update `current_baseline.md` only when the adopted state changes;
3. update this roadmap only when the future sequence, final goal, or a major gate changes;
4. remove obsolete experiment-specific implementation from the active tree once its necessary evidence is preserved.

The active repository should describe the **current system and future work**. Detailed superseded implementation plans should be retained through Git history/tags rather than left in the repository root as if they were active instructions.

---

## 9. Final deliverable

The project is complete when it can release a reproducible record containing:

**calibrated model version + selected topology + optimized geometry + `Zs*` + `Zl*` + validated B28 performance + robustness/yield evidence + comparison against an independently optimized 50/50 Ω reference + provenance/review bundle.**

The final conclusion may legitimately be that 50/50 Ω remains preferable. The purpose of the project is to determine the optimum from evidence, not to prove that a non-50 Ω interface is better.
