# SAW COM Filter Optimizer — Project Goal and Long-Term Roadmap

**Status:** Active product/development roadmap
**Revision:** 2026-10-08 — goals reset after Stage 4C
**Evidence baseline:** Stage 4C complete; topology selection unresolved

---

## 1. Revised project goals

Develop a reusable SAW filter design flow for **user-provided COM parameters, frequency-domain specifications, geometry/area limits, and source/load impedances**.

1. **Constrained optimization:** Find and report the best design discovered under the specified model, constraints, topology/design variables, and computing budget.
2. **Re-optimized impedance sensitivity:** Re-optimize the filter at **each** sampled source/load impedance condition and visualize achieved performance as a **Smith-chart heatmap**. A fixed-design termination sweep is **not** a user-facing goal.
3. **Practical computation:** Reduce both the number of evaluations required and the work per evaluation so single designs and impedance maps complete within realistic time/resources.

The tool must work with given, even hypothetical, COM values. **Measurement/FEM calibration, material attribution, device correlation, manufacturability certification and physical validation are no longer mandatory project gates.** Numerical correctness, COM conventions, input units, consistency of modeled constraints, and reproducibility remain mandatory. A calibrated model may be supplied, but cannot be required.

B28 Rx at 50/50 ohm is a **regression and diagnostic case** rather than the universal product deliverable. DMS and DMS-plus-ladder hybrid are supported design candidates, not assumed final winners. Never claim that a finite-budget best-found design is mathematically globally optimal.

---

## 2. Completion criteria

| Goal | Required deliverable |
|---|---|
| Parametric design | Explicit COM input, filter specifications, topology, variables/bounds, dimension/area constraints, Zs/Zl and optimizer budget; best-found geometry, metrics, feasibility and constraint violations |
| Impedance sensitivity | At each selected Zs/Zl, an **independently re-optimized** candidate and validated performance; Smith heatmaps over named impedance-space slices; 50/50-ohm baseline |
| Computational efficiency | Measured time-to-target, evaluation breakdown, CPU/memory, seed variation, map scaling; faster methods shown to preserve validated solution quality |
| Reproducibility | Frozen inputs, source/computation identity, seeds, search horizon, dense-grid results and compact review evidence |

An infeasible result under a given COM/area/spec combination is **a legitimate tool output**: include the best-found design, active limits, major violated bands/metrics and confidence/unfinished-convergence warnings. Do not force an apparent feasible design by silently relaxing constraints. When useful, report non-dominated alternatives for conflicting performance metrics.

---

## 3. Baseline and the immediate problem at 50 ohm

Prior studies remain immutable historical evidence; see [current baseline](history/current_baseline.md) and [experiment register](history/experiment_register.md).

- Stage 4A qualified hybrid computation/protocol behavior.
- Stage 4B completed 20/20 cells with four topologies; none achieved feasibility.
- Stage 4C completed **10/10 cells × 96,000 evaluations** at fixed 50/50 ohm with integrity PASS. P_D and D_P both had feasible 0/5; matched wins were 3–2; all 10 terminal cells were immature and still improving; three cells had unresolved resonator_0_pairs upper-bound hits. Scientific disposition: **STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED**. Execution completion does not imply convergence or topology selection. The persisted orchestration review state is **REVIEW_WAITING**.
- The 2026-10-08 [fixed-design resonator-pairs probe](history/stage4c_resonator_pair_coordinate_probe.md) reproduced all five baseline cases. All 15 points over 60 pairs improved stop_2, but only 1/15 improved maximum violation (by 0.00486), so classification was **MIXED_BOUND_SIGNAL**. The probe is diagnostic only; it did not authorize expanding bounds or rerunning production.
- The previous advice in that historical probe to prioritize COM/model calibration reflected the **old project objective**. Calibration is not a gate under this revised roadmap.

**We do not yet know why 50/50-ohm optimization remains below specification.** Plausible and possibly interacting causes are optimizer implementation/parameterization, insufficient search, imposed geometry/area and variable bounds, available topology/design degrees of freedom, and performance trade-offs under the supplied COM input. Failure to find a feasible solution does **not** prove mathematical infeasibility.

---

## 4. Development phases and gates

| Phase | Purpose | Required work | Exit gate |
|---|---|---|---|
| **Stage 5A — Diagnose and simplify the 50-ohm optimization** (**NEXT**) | Determine whether generic high-dimensional optimization is feasible in realistic compute time and what blocks current performance | Audit objective/network and optimizer; quantify quality/time scaling; diagnose constraints; investigate classical SAW synthesis for guided starts/reparameterization; fair bounded comparisons | Evidence-based cause matrix, baseline cost envelope, recommended algorithm/design-space strategy |
| **Stage 5B — General-purpose design optimization** | Reliable best-found constrained designs for arbitrary supplied inputs | Unify COM/spec/area/topology/port/budget configuration; mixed-integer optimizer and ranking; diagnostics; optional validated SAW-informed search | End-to-end user-configurable optimization with consistent constraints and reproducible outputs |
| **Stage 5C — Complex Zs/Zl numerical support** | Valid impedance-space evaluation | Positive-real reference parity; complex passive source/load power-transfer and reflection conventions; analytic network tests | Numerically verified complex-port evaluation without changing the meaning of old real-port results |
| **Stage 5D — Impedance-wise re-optimization** | Compute best-found performance for sampled port pairs | Outer impedance sampling, independent inner design search, coarse-to-fine/adaptive refinement, comparison controls | Per-point candidate, validated metrics, seed/budget/time metadata |
| **Stage 5E — Smith-chart re-optimized heatmaps** | Inspect impedance-dependent achievable filter quality | Gamma coordinates, fixed-other-port slices, selectable metrics, feasibility and missing-point annotation | Reproducible heatmap of **re-optimized designs**, not fixed geometry |
| **Stage 5F — Runtime/memory scaling** | Make map computation practical | COM/Y and frequency reuse where valid, profiling, evaluation acceleration, worker parallelism, adaptive budgets and search efficiency | Demonstrated wall-clock/memory gains at comparable dense-validated quality |
| **Stage 5G — Integrated design tool** | Ship a usable workflow | CLI/config, progress/time estimates, bounded resume, plots, export and benchmark documentation | Reproducible model→constrained design→impedance map→Smith plot within agreed resources |

**Performance measurement starts at 5A and runs through all stages.** Stage 5F is the final integrated performance gate, not permission to postpone obvious optimizations.

### Stage 5A-1 — Read-only numerical/optimizer and cost audit (**CLOSED 2026-10-20; evidence-limited**)

**Closeout:** [Stage 5A-1 audit decision](history/stage5a1_closeout_20261020.md) accepts saved-candidate/comparator integrity, all 10 L-SHADE compact states, 80 historical top-16 search pools, 80 dense-validation selection pools, evaluation accounting and the measured baseline cost envelope. It does **not** establish convergence, an algorithm winner, per-proposal replay or independently recomputed COM results for all historical candidates. Stage 4C scientific disposition remains unchanged. [Stage 5A-2 fair-pilot design](plans/stage5a2_minimum_fair_comparison.md) is planning-only and does not authorize new optimization.

Start with existing Stage 4C evidence and current source. Verify feasibility-first comparator/objective behavior, search versus dense-validation ranking, mixed-integer canonicalization, geometry gates, initializer, cache identity, population behavior, late convergence, and run accounting. Distinguish implementation bugs from legitimate infeasible designs. Profile or reconstruct COM/network, metric, optimizer, validation and storage time. Estimate scaling by evaluations × seeds × topologies × impedance points and memory.

Historical Stage 4C consumed about **18.1 cell-hours for 10 cells** at 96k each (roughly **1.8 cell-hours/cell**). This is a reference measurement, **not** a runtime guarantee. Dense maps that repeat the full 96k horizon at every point are likely impractical. Also, L-SHADE's terminal budget affects its population schedule: a checkpoint at 24k in a 96k run is not a valid independent 24k benchmark.

**Deliverable:** quantitative generic-method quality/time envelope, identified correctness risks and minimum next experiment; no new production runs.

### Stage 5A-2 — Generic high-dimensional optimization viability

Before narrowing the search, treat the current 13-variable mixed continuous/integer P_D/D_P optimization as a generic constrained black-box problem. Check whether full-space L-SHADE, controlled differential evolution, and targeted local polish can achieve useful quality within a practical resource envelope. Keep the COM/spec/geometry contract fixed; use independent seeds, matching **unique-evaluation budgets** and **wall-clock quality curves**, followed by the same dense-grid validation. Start small; escalate only when evidence justifies the information gained. A method winning one short run is not evidence of universal superiority.

**Current Stage 5A-2 gate status (2026-10-22):** Q0 is `CLOSED / ACCEPTED` (see [Q0 closeout](history/stage5a2_q0_closeout_20261021.md)). Q1-A is `WORK_UNIT_READY / CLOSED`: [PR #54](https://github.com/MasayaTakagi/saw-com-optimizer/pull/54) merged at `03d673052c7570d86b78b43849f649758bb7d3f4`; [Issue #52](https://github.com/MasayaTakagi/saw-com-optimizer/issues/52) is completed. Pi Code reported 65 focused tests and 92/92 public + 92/92 leaf canonicalization parity, plus no-COM import passes. The [Q1 execution plan](plans/stage5a2_q1_execution_plan.md) and [qualification matrix](plans/stage5a2_q1_qualification_matrix.md) remain authoritative. Q1-B/C/D/E are `NOT AUTHORIZED / NOT STARTED`; no official Q1-01…Q1-23 gate has passed. Real COM/physics evaluation and the 12-cell experiment remain prohibited without separate authorization.

### Stage 5A-3 — Constraint and design-space cause isolation

Assess resonator pair bounds, DMS IDT variables, aperture, acoustic dimensions, hypothetical die footprint and electrode count. Begin with read-only boundary/correlation analysis; when warranted, authorize minimal **re-optimization** with one bound/constraint changed at a time, keeping independent baseline controls. Fixed-coordinate probes alone cannot settle a constrained multi-variable question. Only broaden topology, dimensionality or interacting constraints if simpler diagnostics fail or reveal strong coupling. Do not use a single optimizer failure to prove a mathematical impossibility.

### Stage 5A-4 — Classical SAW-design guidance

Review methods for center-frequency/wavelength and pitch initialization, DMS modal coupling and pole/zero placement, ladder resonator resonance/antiresonance or equivalent-circuit seeds, aperture/capacitance/matching, and hierarchical DMS/resonator adjustment. For each, document applicable COM assumptions and topology, which variables it guides, and when it is invalid.

**First use the knowledge as a diversified initializer or reparameterization, without deleting parts of the full search space.** Only freeze variables or narrow bounds after a controlled demonstration that doing so does not materially degrade solution quality or robustness. Always retain a generic full-space fallback for other COM inputs/impedances.

### Stage 5A-5 — Small controlled comparison and method selection

Compare:
- Generic full-space optimizer baseline;
- Algorithmic improvements with the same design space;
- SAW-guided initialization, hierarchical search or justified reduced-variable methods.

Measure feasible fraction, common-grid best/median violations, stopband, IL, ripple, matching, seed variation, time-to-target, evaluation counts and memory. Use identical computational inputs, validated comparison rules and independent seeds. Select the simplest approach with demonstrated quality/runtime benefit. Obtain separate approval before any large run or permanent constraint change.

---

## 5. Re-optimized impedance map definition

Let x denote geometry/topology design variables and F the declared feasibility-first objective. At every sampled port pair, the software must independently search for the best discovered x under that pair:

    best_found(Zs,Zl) ≈ min_x F(x; Zs,Zl)

It maps the validated **best-found** performance after optimization, not the response of one fixed filter at different terminations. Warm-start sharing across map points is an optional acceleration and must be clearly labeled and checked against independent cold-start controls.

For Smith display use **Gamma = (Z − Z0)/(Z + Z0)** with documented real positive reference Z0 (normally 50 ohm). Two independently complex port impedances are four real dimensions; provide first (a) a Zs Smith slice at fixed Zl and (b) a Zl Smith slice at fixed Zs. Mark the slice condition. Distinguish evaluated, interpolated, uncomputed, infeasible and insufficiently converged points.

The current **core/network.evaluate** supports positive real scalar terminations only. Complex source/load calculations require explicit available-source-power, delivered-load-power, reflection and power-wave/reference conventions. Verify against 50/50-ohm legacy results, analytic passive circuits and finite/passive power accounting before use. Return loss and VSWR require a stated impedance reference, not an implicit real-only assumption.

Allow plotting worst IL, ripple, source/load matching, stopband attenuation, maximum violation, feasibility and computational effort. Fixed-network impedance sweeps may serve **internal tests and optimizations**, but are not a separate end-user heatmap feature.

---

## 6. Efficiency, development and evidence rules

Total effort depends on **distinct design evaluations × work per evaluation + validation/orchestration overhead**. Improvements may reduce required evaluations (SAW-guided initialization, structured parameterization, local refinement) or cost per evaluation (COM/Y reuse, cache, vectorization and careful frequency resolution). Reuse of a fixed geometry's Y-response across *different termination conditions* is valid only if it preserves the correct network semantics; it does not replace inner design re-optimization. Parallelize independent seeds/impedance points while measuring memory and I/O pressure.

Do not weaken the authoritative dense-grid validation or silently relax geometry/specification limits for speed. Set actual runtime targets with the user after baseline profiling rather than inventing an SLA now. L-SHADE remains the historical reference, **not** the presumed final optimizer.

Development cycle: **docs first → necessary focused tests → minimal implementation → review contradictions/dead code**. Keep the implementation KISS; avoid redundant legacy compatibility when not required by explicitly frozen historical evidence. Preserve historical experiment source identities and prior interpretation in [experiment register](history/experiment_register.md). New large production, resume, extra budget or changed bounds require a separate review and explicit user authorization.

The official development environment and storage/review contracts remain as documented; this goal reset does not authorize any run. Use the active [GitHub review workflow](guides/github_review_workflow.md), not frozen C2C.

---

## 7. Final deliverable and next task

A user can supply **COM parameters, performance spec, topology/variables, area/geometry limits, independent (potentially complex) Zs/Zl conditions and runtime budget**, then obtain the best-found constrained design with explanations if infeasible, a Smith heatmap of independently re-optimized designs, verified metrics and reproducible run evidence, all at measured practical computation cost.

The tool need not prove actual-device accuracy, find a universally feasible design or demonstrate that non-50-ohm ports always win.

**NEXT:** Prepare separate Q1-B (controlled DE) and Q1-C (existing L-SHADE instrumentation) Issues based on the accepted Q1-A foundation. Obtain user authorization before either begins. Actual two-arm 234-member evaluator-input preflight remains unqualified and Q1-A's certificates cannot authorize FE. Q1-03/04/05/14/15/16 remain `PENDING_DEPENDENCY`; no official gate is passed by Q1-A closure. The full Q1 qualification and all real COM/production experiments require independent subsequent decisions. Stage 5A-1 remains an evidence-limited read-only audit; no automatic 192k/256k extension or COM calibration track.
