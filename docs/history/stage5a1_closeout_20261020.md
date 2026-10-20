# Stage 5A-1 closeout — read-only optimizer/numerical integrity and cost audit

**Date:** 2026-10-20  
**Decision:** **ACCEPT_STAGE5A1_READ_ONLY_AUDIT** (scope-limited).  
**Baseline source:** `main` at `ad492cde3ffdabbfbed9a0b73e481a8ab74a3de7` before this closeout.  
**Historical production source:** `65e1815db1cc18d74ff0dcee20ffd5e9098709df`.  
**Run:** `20261006_124153_ed50ba`, fixed MLIT/T1, P_D/D_P, 50/50 Ω, five matched seeds, 96,000 unique evaluations per cell.

This document closes **Stage 5A-1 only**, the frozen-evidence/cost audit defined in [the active roadmap](../project_roadmap.md). It does **not** close Stage 5A, select a topology, prove feasibility/convergence, validate arbitrary user-supplied COM models, approve a new experiment, or modify the Stage 4C scientific result. No optimization or COM evaluations were launched for this closeout.

## 1. Evidence and gate traceability

| Stage 5A-1 requirement | Retained evidence | Audit disposition |
|---|---|---|
| Feasibility-first objective and rank consistency | [20-record candidate audit](stage5a1_candidate_consistency_audit.md); [reporter canonical rank parity and candidate fail-closed tests](https://github.com/MasayaTakagi/saw-com-optimizer/pull/38); [full candidate integrity checks](https://github.com/MasayaTakagi/saw-com-optimizer/pull/39) | PASS for Stage 4C saved records; no general optimizer-input schema certification |
| Geometry/canonicalization, initializer and unique accounting | [ten-cell accounting audit](stage5a1_accounting_provenance_audit.md); [PR #40](https://github.com/MasayaTakagi/saw-com-optimizer/pull/40) | PASS for saved-record consistency |
| Full common-grid validation finalist selection | [80-checkpoint raw finalist audit](../../reports/experiment_reviews/stage5a1/20261006_124153_ed50ba/raw_finalist_provenance_audit.md); [PR #41–42](https://github.com/MasayaTakagi/saw-com-optimizer/pull/42) | PASS: 80 pools / 1,280 final candidate positions; no COM rerun |
| Full historical search-grid finalist order and state structure | [cache/trajectory audit](../../reports/experiment_reviews/stage5a1/20261006_124153_ed50ba/cache_trajectory_audit.md), [machine-readable evidence](../../reports/experiment_reviews/stage5a1/20261006_124153_ed50ba/cache_trajectory_audit.json), [PR #43](https://github.com/MasayaTakagi/saw-com-optimizer/pull/43) | PASS: ten terminal states, 960k canonical index entries, 80 reconstructed top-16 lists; rank keys were **read from saved state**, not independently physically evaluated |
| Late convergence and boundary pressure | [Stage 4C review](../../reports/experiment_reviews/stage4c/20261006_124153_ed50ba/summary/final_execution_report.md); [convergence telemetry erratum](stage5a1_convergence_telemetry_erratum_20261008.md); [current baseline](current_baseline.md) | Diagnostic complete; no convergence or robust topology winner |
| COM/network/metric numeric and latency decomposition | [Stage 5A-1 measured six-finalist profiler](../plans/stage5a1_evaluation_profiling_20261009.md) and [profile data](../../reports/benchmarks/stage5a1_evaluation_profile/profile_summary.json) | 12/12 candidate-grid combinations passed existing Y/S/metric parity; constrained to sampled frozen cases |
| BLAS/process throughput and memory | [BLAS benchmark](../plans/stage5a1_blas_thread_benchmark.md), [performance evidence](../../reports/benchmarks/stage5a1_blas_threads/benchmark_summary.json) | PASS for measured WSL2 host and six fixed designs; not a production throughput guarantee |

The stored source/fingerprint are common to the ten Stage 4C cells. The PR #43 raw read-only investigation found 10/10 `final.json` states with 96,000 unique canonical-key entries each, fixed grid/design-space version 1, and 16 retained full-result records. All 80 search-grid top-16 lists matched historical B-record source positions and vectors. PR #42 separately validated the 80 common-grid selection decisions. This is an integrity/replay-of-saved-evidence result, **not** reconstruction of all 1,003,677 actual objective proposals or an independent recalculation of all COM-based ranks.

## 2. Historical quality envelope

The Stage 4C 96k run remains **0/10 filter-feasible**, with P_D and D_P each 0/5. Common-grid terminal maximum normalized violations span **0.306628–0.363328** (pooled median **0.326957**). Matched-seed lexicographic wins are **P_D 3 / D_P 2**, the same assignment on search and common-validation grids. All ten cells improved their common-grid selected maximum violation between the saved 80k and 96k checkpoints; these are **within a single 96k-horizon trajectory**, not ten independently budgeted 80k experiments.

The revised saved-search-trace last-significant-improvement fractions range from approximately **0.7998 to 0.9589** after the [telemetry correction](stage5a1_convergence_telemetry_erratum_20261008.md); do **not** use the original uncorrected `0.0024375` fields in the frozen Stage 4C CSV. The review marked every terminal cell immature/incomplete and three with unresolved terminal upper-bound pressure on `resonator_0_pairs`. A failure to find feasibility at 96k is not a proof that the supplied model/design space is infeasible.

No valid multi-algorithm time-to-quality frontier has yet been established. This is a **one-algorithm historical reference envelope**, not a general-method viability conclusion.

## 3. Quantitative runtime and scaling baseline

The fixed Stage 4C run consumed:

| Component | 10-cell aggregate | Meaning |
|---|---:|---|
| Search evaluation | **15.616 cell-hours** | 960,000 unique decoded designs at historical runtime conditions |
| Dense common validation | **0.180 cell-hours** | 1,280 finalist validations |
| Other optimizer/checkpoint/runtime | **2.261 cell-hours** | Difference from total wall-accounting |
| Total cell wall time | **18.057 cell-hours** | Average **1.806 cell-hours per 96k cell** |

The six-finalist isolated profiler measured a **0.04650 s** median search-grid ordinary evaluator call and **0.42937 s** on the common validation grid. Its decomposed DMS COM share was ~**80%**, resonator COM ~**14%**; the other network and metric components were small. The historical Stage 4C average search evaluation time was ~**0.05856 s**. These values differ because benchmark and production contexts differ; neither is a universal latency estimate.

The BLAS benchmark measured a 47.482 ms Default search call, 45.163 ms with Dual BLAS on one sampled host. Four-worker Single BLAS completed a median **48.56 independent search-grid evaluations/s**, compared with **46.57/s** for Default; small ranges overlap, and only two batches were collected per parallel condition. Treat Single as a low-oversubscription option for future qualification, **not** a validated global production configuration. At four workers the observed peak aggregate RSS was ~454–458 MiB, not a measurement of 96k optimizer peak memory.

Assuming **exactly** 96k unique evaluations × five seeds × two topologies at every impedance pair, the measured Stage 4C cell-time extrapolation is about **451 cell-hours for a 5×5 map**, **1,806** for 10×10, and **30,354** for 41×41; these are budget-scaled total work estimates at fixed 50/50 conditions, not measured map throughput. The Stage 5A-2 pilot must prioritize reducing needed evaluations while keeping dense-grid validity.

## 4. Cause matrix and correctness/risk disposition

| Hypothesis / risk | Current evidence | Disposition / owner |
|---|---|---|
| Wrong finalist / report ranking | Historic report comparator diverged for feasible synthetic records; authoritative comparator parity has been corrected and tested. B finalist and full compact search-history selection independently replayed. | **Resolved for audited Stage 4C evidence and reporter path**; keep future production output fail-closed. |
| Malformed candidate records / missing local grid tags | Saved 20 terminal candidates and 1,280 validation records rankable; candidate objects do not embed own grid hash. Parent field/manifest carries grid identity. | **Known provenance/design risk**, Stage 5B configuration/export contract; not a Stage 4C numerical discrepancy. |
| Incorrect canonical cache/initialization/accounting | 960k final index entries plus exact order/identity, stable 80 shortlisted pools, consistent cache/proposal summaries. | **Saved-state integrity PASS**; actual per-proposal replay impossible from the retained final state alone. |
| Incorrect COM/network computation | Stage 4A parity and twelve profiler candidate/grid cases passed stringent Y/S/metrics validation. | **No discrepancy observed in checked cases**, not a general numerical proof or COM physical calibration. |
| Insufficient search / optimizer strategy | 10/10 cells still improving at 96k, all infeasible; no comparable DE/alternative method at the same independent full budget. | **OPEN — Stage 5A-2**. |
| Geometry limits, stopband trade-offs, active resonator pairs | stop_2 (832–862 MHz) commonly dominates; three terminal upper-bound hits; fixed-coordinate pairs probe showed mixed effect on overall violation. | **OPEN — Stage 5A-3**; do not infer the active bound causes failure or unilaterally enlarge bounds. |
| Search parameterization / SAW-informed initialization | No controlled quality/runtime comparison under frozen 13-variable COM model. | **OPEN — Stage 5A-4/5A-5**. |
| Per-evaluation runtime and worker oversubscription | DMS COM dominates observed evaluator costs; 16-thread Default BLAS pools oversubscribe at multiworker scale. | **Profiled but optimization not implemented**; Stage 5F/performance workstream. |

## 5. What remains outside this closeout

1. **Complete proposal-by-proposal L-SHADE replay**, including every cache hit, proposal sequence, and RNG transition. Final compact index plus status counters do not contain a sufficient raw proposal event log.
2. **Independent recomputation of all 960k search candidate rank keys from physics**, or any independently calibrated model/device proof. Full evaluation payloads are retained for the terminal top 16 only; the audit uses saved historical rank keys.
3. **Proof of optimizer convergence, globally optimal/feasible design, or topology preference**. Every Stage 4C cell is inconclusive for those goals.
4. **Multi-algorithm matched-budget quality/time evidence** and any changed-bound/constraint study. Those require prospective, separately authorized experiments.
5. **Production/general-user input validation and complex impedance accuracy**. These are later roadmap gates, not grounds to reinterpret Stage 4C.

## 6. Closeout decision and next gate

**ACCEPT_STAGE5A1_READ_ONLY_AUDIT.** The scoped audit has a traceable baseline cost envelope, tested numerical/comparator integrity within its frozen evidence, explicit unresolved correctness/provenance risks, and a bounded proposed next experiment. No further 192k/256k extension is implied, no feasibility inference is made, and historical experiment CSV/raw state remain immutable.

The next development task is **Stage 5A-2 experimental protocol and lightweight qualification**, using [the minimum fair comparison plan](../plans/stage5a2_minimum_fair_comparison.md). **This closeout authorizes documentation and synthetic tests only.** New Stage 5A-2 optimization runs (even tiny pilots) require separate explicit user approval for the frozen protocol, budgets, and storage destination. COM measurement/FEM calibration is not a prerequisite under the current product roadmap.

Scientific result retained: **`STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`**.
