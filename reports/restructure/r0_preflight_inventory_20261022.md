# R0 preflight inventory — 2026-10-22

**Scope:** Issue [#56](https://github.com/MasayaTakagi/saw-com-optimizer/issues/56), read-only repository/data inventory and the owner-authorized, external historical-data preservation copy. This is not an R1 implementation plan acceptance, Q1 gate pass, scientific acceptance, or experiment authorization.

**R0 disposition:** `READY_FOR_INDEPENDENT_REVIEW`; preservation copy `COPY_VERIFIED`; physical/off-device redundancy `UNVERIFIED`. No R1 source deletion or scientific work is authorized by this report. Historical raw, manifest, checkpoint, protocol, configuration, and evidence files were not edited, moved, or deleted. The only external writes were the previously authorized new preservation destination; this report is the only tracked-file change in the repository worktree.

## 1. Baseline and safety snapshot

- GitHub `main` at inventory time: `4621946a4aae3e88d7a182fa6b061c5cbdcf7dd5`, the PR #55 merge commit. The inventory worktree was created from this ref after the authorized preservation copy; its starting tree was clean. The R0 branch is `docs/r0-restructure-inventory-20261022`.
- PR #54 is merged at `03d673052c7570d86b78b43849f649758bb7d3f4`; its reviewed source head was `ba0d13f69a34422669fee9dd88819dfbab45d392`. PR #55 is merged. There were no open PRs at the check; Issues #53 and #56 remain open, and Issue #52 is closed.
- Stage 5A-2: Q0 is `CLOSED / ACCEPTED`; Q1-A is `WORK_UNIT_READY / CLOSED`, not an official Q1 gate pass. Q1-B/C/D/E are `NOT AUTHORIZED / NOT STARTED`; none of Q1-01…Q1-23 is `FULL_PASS`.
- The previously unidentified PID was owner-confirmed as an unrelated Pi process and terminated. A read-only active-run check found an initialized registry with zero registered entries, a prior unregistered-run acknowledgement, and no Python/uv `sawopt` worker. No process was stopped, restarted, attached to, or signalled.
- Before the preservation copy, the owner reported no existing backup. `SAWOPT_DATA_ROOT` was unset; this alone was not treated as evidence that historical raw was absent. The actual historical root was established from frozen manifests and bounded known candidates. The source remained read-only.
- The GitHub `main` CI latest run observed was [run 39634119913](https://github.com/MasayaTakagi/saw-com-optimizer/actions/runs/39634119913), on the baseline SHA above; it failed in its `test` job. Details are classified in §7.

At the baseline SHA the repository has **427 tracked files**, including 94 Python modules under `src/sawopt/`, 21 tracked config files, 17 scripts, and 59 `test_*.py` modules (56 unit, 3 integration). The target layout and deletion candidates below are inventory only; nothing was removed.

## 2. Current code responsibility and module inventory

The package responsibilities documented in [`docs/architecture_overview.md`](../../docs/architecture_overview.md) broadly match current code, but boundaries are not acyclic. Module counts include `__init__.py` files.

| Current package | Count | Observed responsibility | Proposed target responsibility |
| --- | ---: | --- | --- |
| `sawopt` | 2 | Package metadata and legacy/top-level CLI | One `sawopt/cli.py` entry point |
| `core` | 8 | COM, filter models, network, metrics, topology and hybrid composition | `physics/` (COM, elements/network, metrics); separate topology belongs in `design/` |
| `design` | 2 | Canonicalization extraction | `design/space.py` / representation contract |
| `problem` | 7 | Design spaces/topologies, evaluator, hybrid and validation | `design/` plus shared `evaluation.py` |
| `optimization` | 11 | FE accounting, budgets, cache, convergence, history, population, runner and SAW polish | Unified `optimization/` |
| `optimizers` | 7 | Backend contract, L-SHADE, SciPy DE, selection, checkpoint and optimizer polish | Unified `optimization/` strategies and runner |
| `io` | 8 | Config, run stores, serialization, provenance, checkpoint and lifecycle handling | `io/` config/results/checkpoints; no agent continuation |
| `studies` | 24 | Live study adapters, audits, stage-specific adapters and Q1-A foundation | Config-driven experiment definitions plus thin reusable adapters; retire stage folders after disposition |
| `reporting` | 10 | Result/report generation, integrity and historical/ad-hoc review bundles | `plotting.py` and compact review export responsibilities in the new I/O/review contract |
| `orchestration` | 13 | Detached launcher/worker, active runs, storage, review publishing, Codex queue/callback | Small user CLI plus process supervision; no agent-session/queue dependency |
| `runtime` | 2 | Parallel execution environment | Remove unless a concrete current user responsibility remains |

Module names (94 total):

- `sawopt/`: `__init__`, `__main__`.
- `core/`: `__init__`, `com`, `hybrid`, `literature_com`, `metrics`, `models`, `network`, `topology`.
- `design/`: `__init__`, `canonicalization`.
- `problem/`: `__init__`, `design_space`, `dms_topologies`, `evaluator`, `hybrid`, `released_dms`, `validation`.
- `optimization/`: `__init__`, `accounting`, `adaptive_frequency`, `budget`, `cache`, `convergence_evidence`, `counters`, `history`, `polish`, `population`, `runner`.
- `optimizers/`: `__init__`, `base`, `checkpoint_session`, `lshade`, `polish`, `scipy_de`, `selection`.
- `io/`: `__init__`, `checkpoints`, `config`, `legacy_lifecycle`, `lifecycle`, `provenance`, `run_store`, `serialization`.
- `studies/`: `__init__`, `dms_topology_common`, `dms_topology_screening`, `hybrid`, `hybrid_stage4b`, `hybrid_stage4c`, `lshade_records`, `postrun_workflow_qualification`; `audits/{__init__,stage3_9b_budget_extension,stage3_9b_overlap_parity,stage4c_resonator_pair_probe,stage5a1_blas_thread_benchmark,stage5a1_cache_trajectory,stage5a1_evaluation_profile,stage5a1_integrity,stage5a1_raw_finalist_provenance}`; `stage5a2/{__init__,codec,identity,initialization,journal,production_identity,rng}`.
- `reporting/`: `__init__`, `candidate_integrity`, `github_review`, `hybrid_qualification`, `hybrid_report`, `hybrid_stage4b`, `hybrid_stage4c`, `material_metadata`, `report`, `review_bundle`.
- `orchestration/`: `__init__`, `active_runs`, `administrative_closeout`, `cli`, `codex_callback`, `codex_queue`, `models`, `persistent_storage`, `pid_utils`, `process_runner`, `run_manager`, `worker`, `worktree_safety`.
- `runtime/`: `__init__`, `parallel`.

### Static imports and layer boundaries

A read-only AST scan of Python imports (package-local cross-package edges only; it does not resolve dynamic imports) found:

```text
__main__       -> core, io, optimization, reporting, studies
problem        -> core, design, optimization
optimization   -> core, io, optimizers, problem
optimizers     -> io
studies        -> core, design, io, optimization, optimizers,
                  orchestration, problem, reporting
reporting      -> core, optimization, optimizers, orchestration, studies
orchestration  -> io, reporting, studies
```

The notable concerns are observed edges, not dead-code findings:

- `problem.evaluator` imports shared adaptive-frequency/cache services from `optimization`; this is an upward dependency for the target `evaluation.py` boundary.
- `optimization` and `optimizers` overlap: e.g. SAW-specific and optimizer-generic polish are split between them, and the runner imports optimizer backends/selection.
- `studies`, `reporting`, and `orchestration` are mutually coupled at submodule level (for example the Stage 4B/4C adapters and reporters, the launch CLI and study adapters, and GitHub review export and run management). These cycles need explicit R1/R6 responsibility placement; a package rename alone will not break them.
- `sawopt.__main__` is not a thin wrapper: it imports physics/search/reporting/study duties. README examples expose `simulate`, `optimize`, `sweep`, `report`, and `run-study`; the separate `python -m sawopt.orchestration.cli` exposes production lifecycle operations such as `launch`, review/recovery/queue state and an internal `worker`. No `project.scripts` console entry point was found. Consolidating these surfaces requires preserving the current authorized production-launch contract, not keeping obsolete command wrappers by default.

### Configs, scripts, tests and fixtures

- `configs/` has `base/b28_dms_baseline.yaml`; model profiles `models/com_params_hypothetical.yaml` and `models/stage3_7b_r1_normalized_literature_profile.yaml`; DMS reference grids/design origins under `reference/dms_topology_screening/`; study configs for DMS screening, hybrid 4A/4B/4C, post-run workflow qualification and Stage 3.9B; and review specs for hybrid production, Stage 4C and post-run qualification. The 21-file count also includes README and the reference design/grid files. There is no current `configs/experiments/` tree.
- 17 tracked scripts: `analysis/{power_budget,resonator_plot}.py`; `build_stage3_9a_search_viability_diagnosis.py`; `build_stage3_9b_source_compatibility.py`; `capture_stage5a2_legacy_canonicalization.py`; `check_stage5a2_foundation_imports.py`; `check_stage5a2_pure_leaf_import.py`; `common/invoke-sawopt.ps1`; `launchers/{base-study,hybrid-50ohm}.ps1`; `preflight_stage3_9b_budget_extension.py`; `preflight_stage3_9b_budget_extension_config.py`; `verify_stage3_9b_budget_extension.py`; `verify_stage3_9b_overlap_parity.py`; `verify_stage5a2_canonicalization_golden.py`; `worktree_safety.py`. Stage-specific and PowerShell scripts are candidates for review, not proven dead. `scripts/worktree_safety.py` is an active safety responsibility and must not be dropped without an accepted replacement.
- Test modules are grouped under `tests/unit/{core,io,optimization,optimizers,orchestration,problem,reporting,studies}` plus four root-level unit tests; `tests/integration/` has three study/protocol tests. Storage/provenance/checkpoint and production orchestration have dedicated tests; historical C2C/Sol-routing tests are also in the active CI suite.
- Numerical/reference tests: `tests/unit/core/{test_physics.py,test_literature_com.py,test_reference.py,test_scalar_regression.py,test_topology.py,test_hybrid.py,test_stage4a_hybrid_composition.py}`. The reference suite contains analytic COM propagation/sign and real-reference network/S-parameter, split-section equivalence and passivity checks; most expected values are inline, not a separate COM fixture file.
- Design/ranking/validation/accounting: `tests/unit/problem/{test_dms_topologies.py,test_stage4a_hybrid_design_space.py}`, `tests/unit/optimizers/test_selection.py`, `tests/unit/studies/{test_hybrid_stage4b.py,test_hybrid_stage4c.py,test_stage5a1_candidate_integrity.py,test_stage5a1_reporter_parity.py}`, `tests/unit/optimization/test_accounting.py`, and `tests/unit/studies/audits/{test_stage5a1_accounting_provenance.py,test_stage5a1_cache_trajectory.py,test_stage5a1_raw_finalist_provenance.py}`.
- Optimizer/checkpoint evidence: `tests/unit/optimizers/test_lshade.py`, `test_lshade_compact_bounds_policy.py`, `test_lshade_compact_history.py`, `test_selection.py`; `tests/unit/optimization/test_lshade_record_serialization.py`; and `tests/unit/io/test_checkpoints.py`. These cover selected optimizer mechanics, saved-state structure and component serialization; they do **not** supply the missing full proposal-by-proposal Stage 4C replay.
- Q1-A fixtures are `tests/fixtures/stage5a2/{canonicalization_legacy_golden.json,q0_design_space_contract.json,seed_derivation_golden.json}`. The 92-case canonicalization corpus and seed/identity evidence are described in `reports/stage5a2_q1a_common_foundation_20261021.md`. Common DMS validation-grid inputs are under `configs/reference/dms_topology_screening/`. These are evidence with pinned scope, not general production qualification.

## 3. Retirement candidates and preservation boundary

The design record [`repository_restructure_decisions_20261022.md`](../../docs/plans/repository_restructure_decisions_20261022.md) calls for a responsibility-oriented tree, no backward-compatibility wrappers or old-checkpoint readers, and removal of agent-specific and historical implementation paths. The following are **R1+ candidates only**; none are deleted or approved for deletion by this R0 inventory:

| Candidate | R0 evidence / dependency | Required R1 disposition |
| --- | --- | --- |
| `.c2cignore`, `.codex/`, `docs/c2c/`, `docs/handoff/`, `handoff/` | Tracked historical/frozen agent operations, hook and handoff material; not a SAW runtime dependency per current project policy | Remove obsolete operating instructions as designed, while resolving how the current requirement to preserve C2C baseline/security/review provenance is met (e.g. concise historical pointer, not copied runtime instructions). Do not invoke C2C. |
| `orchestration/codex_callback.py`, `codex_queue.py`, root capture/hook tests and Sol model-routing instructions/tests | Direct agent-session/queue integration; target product must not depend on agent state. Current pinned Sol policy is an agent-review process rule, not a SAW product feature. | Remove product coupling and stale policy assertions in the intended docs/CI cutover; preserve reviewer governance outside the product CLI. |
| `io/legacy_lifecycle.py` and lifecycle compatibility paths | `orchestration.worker` still imports legacy and current lifecycle modules | Resolve exact remaining worker/recovery use before retiring; no assumption of dead code. |
| `reporting/review_bundle.py` and bundle tests | Current docs explicitly retain it only for historical/ad-hoc saved-run packaging; canonical new production review is a separate exporter under `sawopt.reporting.github_review` | Decide whether historical packaging has a real current user; preserve existing committed bundles/provenance even if transport code is removed. |
| Stage-specific studies, audits, config adapters and `scripts/` | Several modules implement Stage 3.9B, Stage 4B/4C, Stage 5A-1 audits or Stage 5A-2 Q1-A; some remain evidence-generating tools/tests | Retain only general behavior in shared engine; freeze or retire audit-only paths with their committed evidence pointers. Confirm callers/tests before deletion. |
| Current `README.md`, `AGENTS.md`, historical plans/handoffs | Multiple active instructions coexist; `AGENTS.md` is much longer than the target 50–80-line entry point and README still shows prototype `runs/` command examples | R1 should establish the six canonical docs and reconcile paths/commands, science contracts and history pointers before any file removal. |

The existing R0 repository source, GitHub review packages and committed audit reports are preservation evidence, not substitutes for external raw/checkpoints. No raw data is to be made backward-compatible by writing it into a new schema.

## 4. Scientific baselines, evidence and validation contracts

### Historical stages

| Stage / logical evidence | Execution source SHA and review references | Scientific / software interpretation |
| --- | --- | --- |
| Stage 4A hybrid qualification | Four bounded qualification records are in the new external manifest. Legacy manifests do not record their execution source SHA. Config: `configs/studies/hybrid_stage4a_qualification.yaml`; tests: `tests/integration/test_stage4a_hybrid_protocol.py`, `tests/unit/core/test_stage4a_hybrid_composition.py`. | Preserve complete success/failure/retry qualification evidence. Do not attribute a source SHA from later code to these records. Q1-A later characterized the shared canonicalizer at pre-extraction SHA `f32b8f8dac928f21c567b34593b1ed227a4c9c9e` and file SHA `b892be9360174d6701f3db0dc8ba49c82d1b75d8b3c1886dbbba998bd3242462`; these are not proven Stage 4A run SHAs. |
| Stage 4B production | Run `20261003_014817_ea08db`, source `c44798266067fa4b8b7d3b2873a798b7a1600ae8`; closeout [`docs/history/stage4b_closeout_20261004.md`](../../docs/history/stage4b_closeout_20261004.md); review package `reports/stage4b_production_review/20261003_20261003_014817_ea08db/`. | 20 cells completed/accepted as a matched comparison; 0/5 feasible in each of four topologies, no unique topology winner. Fixed 50/50 Ω, provisional MLIT/T1, 24k unique FE/cell, 9,113-point common grid. Does not prove infeasibility or convergence. Four launch/qualification/preflight records are separately retained; some lack source-SHA metadata. |
| Stage 4C qualification / failed attempt / completed production | Smoke run source `39fe0c8a251e52183e87c63bff9e7aac393fb501`; incomplete 80k MemoryError attempt `c52ba5873f4625d6426c79347793d08dfb9afa0a`; completed run `20261006_124153_ed50ba` source `65e1815db1cc18d74ff0dcee20ffd5e9098709df`. Review package `reports/experiment_reviews/stage4c/20261006_124153_ed50ba/`; closeout/current limits in `docs/history/current_baseline.md` and `docs/history/stage5a1_closeout_20261020.md`. | Completed evidence is 10 cells (P_D and D_P × five seeds) to 96k; integrity passed, but 0/10 filter-feasible, terminal cells immature/incomplete, and topology selection unresolved. The failed attempt is administratively closed and must never be resumed. No optimum or mathematical infeasibility conclusion. |
| Stage 5A-1 read-only audit | Same Stage 4C raw run and source SHA above. Audit implementation source recorded as `c0ab7cc5ad93569c1828f812cf90655e89c5cc8f` in `reports/experiment_reviews/stage5a1/20261006_124153_ed50ba/raw_finalist_provenance_audit.md`; closeout `docs/history/stage5a1_closeout_20261020.md`. | Saved finalist replay: 80/80 checkpoints and 1,280/1,280 validation candidate records passed; cache/trajectory audit found 10 terminal states, 960k canonical index entries and 80 search-grid top-16 reconstructions. These are replay/integrity checks on saved state, not COM recalculation or reconstruction of all 1,003,677 proposals. Full L-SHADE proposal/cache/RNG event replay remains unavailable from the retained final-state evidence. Stage 4C scientific disposition remains unresolved. |

The R0 external preservation set has 12 run trees across Stage 4A/4B/4C plus five associated source/reconciliation manifests. Stage 5A-1 uses the Stage 4C completed run and is not a thirteenth raw run. To avoid publishing raw directory names, the following report-local aliases identify every copied logical run. The aliases map in order to the 12 entries in the external inventory manifest's `scope.runs` array; original directory names remain only in that external manifest.

| Alias | Stage / role | Terminal state from existing evidence | Execution source SHA |
| --- | --- | --- | --- |
| `S4A-Q01` | Initial hybrid protocol qualification | `FAILED` | Not recorded in legacy metadata |
| `S4A-Q02` | Final qualification smoke | `REVIEW_WAITING / STAGE4A_SMOKE_COMPLETE` | Not recorded |
| `S4A-Q03` | Accepted final qualification | `COMPLETED / STAGE4A_CLOSEOUT_ACCEPTED` | Not recorded |
| `S4A-Q04` | Qualification retry | `REVIEW_WAITING / STAGE4A_SMOKE_COMPLETE` | Not recorded |
| `S4B-Q01` | Full four-topology production | `COMPLETED / REVIEWED` | `c44798266067fa4b8b7d3b2873a798b7a1600ae8` |
| `S4B-Q02` | Initial launch shakedown | `COMPLETED / ranking-ineligible` | `e1875ef9de0a096472fadb73df5ba113af4919a0` |
| `S4B-Q03` | Corrected launch shakedown | `COMPLETED / ranking-ineligible` | `a4c5b7c88530f22a9630e5b0b7af83cdceb4cf94` |
| `S4B-Q04` | Prelaunch qualification | `REVIEW_WAITING / STAGE4B_PRELAUNCH_QUALIFICATION_COMPLETE` | Not recorded in legacy metadata |
| `S4B-Q05` | Production launch preflight | `prelaunch-only` | Not recorded |
| `S4C-Q01` | Stage 4C launch qualification | `COMPLETED / shakedown PASS` | `39fe0c8a251e52183e87c63bff9e7aac393fb501` |
| `S4C-Q02` | Incomplete 80k MemoryError attempt | `FAILED / administrative closeout` — never resume | `c52ba5873f4625d6426c79347793d08dfb9afa0a` |
| `S4C-Q03` | Completed 10-cell 96k baseline; Stage 5A-1 audit input | `COMPLETED / REVIEW_WAITING; integrity PASS` | `65e1815db1cc18d74ff0dcee20ffd5e9098709df` |

The five additional preserved manifests are historical run index/re-run index, Stage 4B raw-archive index, and two historical reconciliation records. The manifest records their names and hashes. Stage 5A-1 is not a separate raw run.

### Q0 / Q1-A scope that must remain frozen

- Q0 documentary protocol was merged in PR #50 at `9427b404d302932b27f50d31919bb3fb95fcfcd4`; the separate formal closeout is `docs/history/stage5a2_q0_closeout_20261021.md`. Its fixed comparator, 234-member shared initializer, 4,096 unique FE/arm ceiling, RNG/replay and censoring rules remain unchanged.
- Q1-A was reviewed at source head `ba0d13f69a34422669fee9dd88819dfbab45d392`, merged by PR #54 at `03d673052c7570d86b78b43849f649758bb7d3f4`. Its reported post-patch local validation used source `03b9a5495111a1f933f542682f76b5ec9bad4e53`: 65 focused tests, 92/92 public and 92/92 leaf canonicalization parity, and no-COM import checks. This does not pass an official Q1 gate; the evidence report explicitly says preflight certificates are synthetic/non-authoritative and evaluator dispatch rejects.
- Q1-A asset classification: **carry forward as invariants** exact legacy canonicalization semantics where still needed to interpret historical comparisons; frozen Q0 comparison rules and IDs; exact numeric/rank/RNG serialization and seed semantics only if later approved qualification reuses them. **Preserve as historical evidence** the Q1-A source SHA, report, corpus and three fixtures. **Potentially retire/reimplement after R1 decision** the `studies/stage5a2` journal, identity, codec, RNG and production-identity implementation; the design target explicitly removes stage folders, but any replacement must not be called Q1-qualified based on this foundation. **Await separate authority** for Q1-B/C/D/E, integration or any synthetic/physical run.
- Current qualification matrix records Q1-03/04/05/14/15/16 as `PENDING_DEPENDENCY`; all other Q1 gates are likewise unpassed. Keep the Q0 234-member and 4,096-unique-FE contract intact; R0 does not amend it.

## 5. External raw preservation and copy verification

**Status:** `SOURCE_RAW_STATUS=FOUND_READ_ONLY`; `COPY_STATUS=COPY_VERIFIED`; `PHYSICAL_REDUNDANCY=OFF_DEVICE_REDUNDANCY_UNVERIFIED`.

- Logical destination: external persistent archive `archive/restructure-r0-20261022/`; inventory `archive/restructure-r0-20261022/inventory-manifest.json`. The absolute path is intentionally omitted from this public report. Source data remain at the original location and were not moved, changed, repaired or overwritten.
- Scope copied: 12 logical run trees and five source/reconciliation manifests, **798 regular files / 9,996,102,874 bytes**. The selection preserves the bounded Stage 4A/4B/4C evidence closure, including full Stage 4B production checkpoints/history/accounting/authorization provenance, the failed Stage 4C attempt, and the completed Stage 4C 10-cell 96k run required as the Stage 5A-1 audit input. Unrelated pre-Stage-4 runs, orphan logs/caches and repository source/review files were excluded; an unresolved missing legacy payload was not fabricated or substituted.
- External inventory manifest SHA-256: `d0bfc7189d0c8f35aa46875b4f7de4d64727ef6b570e2a157b8da900898d9c7d` (669,341 bytes). The manifest records per-file relative name, size and SHA-256 outside Git; the full file-hash list and raw data are not committed.
- Post-publication audit re-read and matched all **798/798** destination files and aggregate size (`POST_PUBLISH_DESTINATION_AUDIT=PASS`). Stage 4A/4B qualification files matched existing historical per-file verification records. Stage 4B production matched 242 old file-hash records and the raw-archive manifest; one 449-byte authorization-claim provenance item absent from those prior lists is explicitly included in the new inventory. Stage 4C had no complete prior file-hash manifest; every copied source stream hash matched a destination re-read hash.
- The first transfer attempt halted on an internal relative-path-set assertion after the first Stage 4A run; it was not a hash mismatch. That staged run was read-only reconciled against source and prior hashes, then the same new staging destination was completed without overwrite. No source file change or hash discrepancy was observed.
- The new destination is external to all registered worktrees, but the source/destination physical-device and failure-domain relationship is not established. A verified external preservation copy is **not** proof of off-device disaster recovery. The manifest correctly records `OFF_DEVICE_REDUNDANCY_UNVERIFIED`; keep this risk open and do not claim independent-media backup.

## 6. R1+ priority handoff and blockers

Recommended order, subject to independent review and owner acceptance:

1. **R1 docs/Q1 disposition:** establish canonical docs and a compact old-to-new responsibility/evidence map. Freeze Stage 4A/4B/4C source/config/protocol/ranking/geometry/FE/RNG contracts and scientific limits. Explicitly resolve the Q1-A code disposition and retain all historic pointers before removing active docs or stage paths.
2. **Resolve preservation risk:** owner/storage administrator may confirm whether the verified copy is on independent media or authorize a second independent copy. Until then, say only `COPY_VERIFIED`; do not claim off-device redundancy. Keep external raw/checkpoints untouched in every case.
3. **R2 physics:** move COM/network/model behavior without equation/sign/unit changes; gate with existing analytic/reference/passivity tests. Do not invoke optimizer or COM calculations as part of this R0 review.
4. **R3 design/evaluation:** separate topology, geometry, canonicalization, evaluation and one feasibility-first rank contract; preserve search-versus-dense-validation distinctions and exact legacy canonicalization evidence where needed.
5. **R4 optimization:** consolidate accounting/cache/budget/optimizer layers only after a Q1 disposition. No live Q1-B/C/D/E or 12-cell qualification is authorized by this inventory.
6. **R5–R7 storage, CLI, reporting and cutover:** migrate only compact review responsibility, not historical raw. Validate the documented external-root/fail-closed and per-run provenance contracts in synthetic tests before any later user-authorized run.

R0 uncovered no basis for declaring modules dead solely by age or stage name. In particular, `worktree_safety.py`, current detached production supervision, canonicalization, comparator, budget/accounting, evidence exporters and checkpoint/provenance contracts require explicit new-owner placement before retirement. The candidate list is a review queue, not permission to delete.

## 7. CI and validation performed

- Current [`ci.yml`](../../.github/workflows/ci.yml) has one `test` job: locked `uv sync --locked --extra test`, then `uv run --locked pytest` on every push/PR. It is not currently risk-tiered.
- The baseline GitHub run failed at `Run tests` (job annotations only report exit code 1; `gh run view --log-failed` returned no test traceback). Issue #56 explicitly identifies the known `tests/unit/test_sol_review_routing_policy.py` failure. Inspection of that test shows it hard-codes `gpt-6-sol` and `gpt-5.6-sol`; current `AGENTS.md` instead pins `openai/gpt-6.1-sol` with `medium` thinking. This is a stale policy assertion, classified `KNOWN_BASELINE_FAILURE`, not evidence of a numerical or physics regression. The test was not run or edited in R0. CI also reports a Node 20 deprecation warning for `actions/checkout@v4`; it is not the failure cause established here.
- The agreed design's CI policy is risk-based: focused RED/GREEN + relevant integration for behavior changes; analytic/numerical gates and full suite at material scientific releases; do not run full suite for every trivial docs change, but intentionally maintain CI. It does not authorize skipping checks or changing CI in R0. R1 should retire/replace stale agent-policy assertions together with the docs cutover, then review the full-suite requirement as specified.
- Read-only inventory commands, GitHub metadata, source/config/test searches and bounded manifest metadata/hash reads were used. The authorized copy streamed the selected source files read-only and verified destination hashes; no raw payload is included in this report. `uv sync --locked --extra test` had already completed in the isolated worktree. **No pytest suite, COM/FE calculation, optimizer, experiment, seed sampling, Stage 4C resume or checkpoint write was run.** The only tracked-file change is this report; no source raw was modified, moved, deleted or repaired.

## 8. Gate report

- `PROCESS_STATUS=USER_CONFIRMED_UNRELATED_PI_TERMINATED`; the separate active-run check was clear at inspection time.
- `RAW_ROOT_STATUS=FOUND_READ_ONLY`; bounded historical runs are accounted for in the external manifest.
- `BACKUP_STATUS=VERIFIED_READABLE_COPY`; 798/798 files/hash reads and aggregate size verified. `OFF_DEVICE_REDUNDANCY_UNVERIFIED` remains explicit.
- `EXECUTION_SAFETY=PASS`: no process control, numerical calculation, optimization, experiment, checkpoint mutation or source-raw write/move/delete.
- `R0_GATE=READY_FOR_INDEPENDENT_REVIEW`, **not accepted**. The Draft PR contains inventory documentation only and should be the next review checkpoint. R1 implementation, source deletion, Q1 work and any production execution remain outside this authorization.
