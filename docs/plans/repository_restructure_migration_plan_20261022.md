# Repository reconstruction — staged migration and acceptance plan

**Date:** 2026-10-22 (JST)  
**Tracking:** [Issue #53](https://github.com/MasayaTakagi/saw-com-optimizer/issues/53)  
**Design authority:** [repository_restructure_decisions_20261022.md](repository_restructure_decisions_20261022.md) (Draft PR #55)  
**Status:** PLAN / NOT IMPLEMENTED. This plan is not an authorization for COM runs, optimizer experiments, historical data mutation, or unapproved Q0/Q1 scientific contract changes.

## 1. Objective and explicit non-goals

Reconstruct the in-development SAW COM optimizer around scientific responsibilities, rather than moving the existing modules wholesale. New active code should be small, config-driven, and independent of C2C/Codex session control. Preserve trustworthy numerical behavior and the provenance of prior Stage 4A/4B/4C/5A evidence while deliberately not preserving old runtime/API/checkpoint-format compatibility.

Non-goals: a new optimizer algorithm, COM equation redesign, new production results, retuning specifications/bounds/budgets/seeds, rereading old checkpoints through the new implementation, moving historical raw runs, or establishing new scientific conclusions.

**Execution rule:** first merge reviewed documentation and migration contracts; only then create implementation Issues and instruct Pi Code. Each implementation unit follows docs-first → risk-based RED test → minimum GREEN → KISS/dead-code reconciliation → independent GitHub review. Do not start all units in one large implementation PR.

## 2. Baseline, dependencies and cutover constraints

As checked on 2026-10-22, the main branch SHA was `b9d6c5c46d1da54662bc6f0316b9570e4e5d4eb7` (recheck when executing preflight). It contained 425 tracked files and separate `core/`, `problem/`, `optimizers/`, `optimization/`, `io/`, `studies/`, `orchestration/`, `reporting/`, `runtime/` packages. CI ran `uv run --locked pytest` for every PR. PR #55 is an unmerged Draft design record.

Stage 5A-2 Q0 is closed/accepted; Q1-A is complete in merged PR #54 / closed Issue #52. Q1-B/C/D/E are not authorized or started, and none of Q1-01…Q1-23 is FULL_PASS. The proposed target deletes the `studies/stage5a2` home for Q1-A; therefore **do not launch Q1-B/C/D/E on the old paths during reconstruction**. First classify Q1-A outputs into (a) reusable current scientific invariants, (b) frozen historical qualification evidence, and (c) dispensable implementation compatibility. Carry only (a) into current packages after explicit contract reconciliation. Preserve evidence for (b) with exact source SHA. Never silently turn pending Q1 gates into passed gates or rewrite Q0 fairness conditions.

All external scientific raw/checkpoints remain read-only. Inventory their actual storage, integrity, backups, execution source SHA, protocol, and review references in the Pi Code environment before deleting any source or active document pointers. Git history is not a substitute for a verified external raw backup. Any pre-cutover Git tag/commit manifest should be immutable, and final historical evidence pointers must survive in the current docs.

## 3. Target ownership and import direction

The target layout is defined by the design authority, not by this document; it is a responsibility map rather than a requirement to create empty files.

- `sawopt.physics`: COM elements, network, S parameters and physical metrics; must not import optimizer, CLI, study, PR, or run-lifecycle modules.
- `sawopt.design`: topologies, variable bounds, mixed-integer transformations and canonicalization; no optimizer or COM evaluator import.
- `sawopt.evaluation`: sole bridge from design/physics to RF metrics, constraints, feasibility-first ranking and per-candidate evaluation.
- `sawopt.optimization`: algorithms and shared runner/counters/budget/cache, consuming only an evaluator interface; no direct internal COM imports.
- `sawopt.io`: active config, external raw-store, frozen provenance and only needed same-version run checkpoints.
- `sawopt.cli`/`sawopt.plotting`: user entry points and plots, importing from lower-level services, not vice versa.

Delete current `core/` and `problem/` *after* physics/design/evaluation replacement; unify `optimizers/` and `optimization/`; retire current `studies/`, Agent-bound `orchestration/`, old `reporting/`, `runtime/` and stale scripts when each needed product function has an assigned owner. No compatibility proxy packages, shadow imports or abandoned dual source-of-truth trees at final closeout.

## 4. Sequential migration units / proposed PR boundaries

Each unit is a separate reviewable PR unless a small, demonstrably safe merge is justified. PR numbers below are **not allocated**. An accepted PR is a dependency for its successors. Assign new implementation Issues after the preceding contract gate.

| Unit | Scope and acceptance evidence | Gate / dependency |
| --- | --- | --- |
| **R0: Preflight & preservation** | Reconfirm main and open PR/Issues; file/import/entry-point/test inventory; frozen numeric fixtures and environment baseline; map historical raw paths, source SHAs and reviewed backups; identify active detached runs and stop unsafe cutover. No deletion. | Owner verifies old evidence recoverable, baseline inventories linked to Issue #53. Before implementation. |
| **R1: Docs & Q1 contract cutover** | Merge reviewed design PR #55; replace active docs with `docs/{README,roadmap,architecture,physics,development,experiments}.md`; shrink `AGENTS.md`; mark legacy plans as historical or remove obsolete operating instructions after retaining pointers. Create explicit old-to-new responsibility map and Q1-A/Q0/Q1-01…23 disposition matrix. | Independent docs review; science contract adjustments explicitly approved; no new Q1-B work yet. |
| **R2: Physics extraction** | Move actively required `core/com.py`, network/elements/metrics functionality to `physics/` with single ownership; remove hidden upward imports; do not rewrite scientific equations for style. | Analytic/limit-case, unit/sign/reference, finite/passivity and trusted fixture checks appropriate to changed code; numerical deltas explained; no new experimental conclusion. |
| **R3: Design + evaluation** | Move topology, bounds, canonicalization, validation and evaluator duties from `problem/` and relevant shared modules into `design/` and `evaluation.py`; preserve the single candidate ranking rule. | Boundary/integer canonical identity, geometry constraints, search-vs-dense-grid separation, feasibility-first/tie ordering and invalid-case tests; documented exact-versus-tolerance expectations. |
| **R4: Optimization consolidation** | Merge `optimizers/` + `optimization/`; keep only needed L-SHADE/DE strategies, runner, budget/FE accounting, cache, deterministic RNG and active checkpoint semantics; absorb or retire Q1-A study foundation according to the approved matrix. | Unique-FE vs duplicate/reject ledger, seed reproducibility, hard budget/no-overrun, deterministic fail/recovery and same-evaluator integration tests; no Q0/Q1 contract mutation without approved amendment. |
| **R5: Data, result & review contract** | Implement `SAWOPT_DATA_ROOT` fail-closed absolute external path, unique experiment/run IDs, frozen config and execution source SHA, versioned same-run raw persistence, and `reports/experiments/<experiment_id>/<run_id>/` review schema v1. | Synthetic/fixture-only tests of root rejection (including worktree/symlink), collision, atomic initialization, hashes, nonfinite/null/status, expected-all-cell coverage, failures, redaction, 10 MiB policy and reproducible export; no real run launch. |
| **R6: CLI, minimal vertical slice & retirement** | Config → design → evaluate → optimize → external save → review export, initially with a synthetic/injected evaluator; CLI help/config validation/smoke. Retire old `studies/`, agent queue/callback/C2C/Codex integration, `orchestration/`, old `reporting/` and `runtime/`, scripts and dead tests *after* replacement is qualified. | User-visible CLI/smoke passes; no imports from retired packages, no mandatory agent session, and clean source/test/doc entry points. Only run numerical COM integration by separate authorization. |
| **R7: CI risk lanes, final audit & Q1 rebaseline** | Benchmark current and proposed CI duration/flake rate; add docs lint/static-only, focused normal-code, scientific-core regression and full-suite milestone/experiment gates without eroding numerical assurance. Finish docs/links/dead-code scan; update Q1 plan and new implementation Issues. | Reproducible clean `uv sync --locked --extra test`, agreed required tests, no stale references, scientific contract disposition, accepted independent review and Issue #53 checklist. |

**Recommended partition:** R2, R3, R4 and R5 are separate high-risk code PRs. Do not batch broad code deletion with a numerical-method change. For every PR, record base/head SHA, the before/after module ownership, tests executed/skipped, intentional scientific deltas, surviving risks and rollback action. A structural merge never by itself certifies Q1 or authorizes experimental FEs.

## 5. Protected scientific invariants and risk-based tests

| Risk level | Examples | Evidence policy |
| --- | --- | --- |
| **Critical scientific** | COM equations, admittance/S-parameter conversion, units, source/load reference, RF metric definition; objective/feasibility comparator; geometry constraints; search/validation-grid semantics; FE accounting, RNG identity/replay, checkpoint correctness | Representative analytical cases, reference fixtures, targeted regression and integration; full suite before high-risk merge or approved experiment gate. Numeric tolerance must be predeclared and justified; exact equality for canonical identity, hashes, counters and discrete ordering where mandated. |
| **Normal functional** | Config/CLI, output schema, formatting, review exporter, paths | TDD behavior and error cases, integration smoke, schema/hash completeness. |
| **Low risk** | Docs-only, link updates, unused non-scientific assets | Link/cross-reference/static checks; do not blindly trigger costly numerical tests once measured CI policy is approved. |

An implementation-only rename is not permission to change COM semantics or solver policy. Numerically changed behavior must have an explicit before/after explanation and an approved scientific interpretation. Old public API shape and obsolete checkpoint readers are not protected. Current scientific invariants, historical raw evidence, frozen executable SHA, and validated comparison fairness *are* protected.

The preserved reference cases should cover, as applicable: scalar COM/network limiting cases and complex S response, fixed-real-port baseline; canonical mixed-integer vectors/keys; feasible/infeasible and NaN/failure classification; tie ordering; duplicate/cache/unique FE counting; dense-grid recomputation; deterministic optimizer seeds and recovery. Characterize old behavior only where it supplies evidence for these current invariants, not blanket legacy bitwise parity.

## 6. Experiment raw/review contract (implementation of PR #55 design)

New runs use `$SAWOPT_DATA_ROOT/runs/<experiment_id>/<run_id>/`, outside all worktrees and outside Git, with frozen `manifest.json`, `config.yaml`, full cells, checkpoints and logs. Require an explicitly configured, resolved absolute path, exclusive collision-safe creation and space/permission/path validation before mutation; never fall back to `./runs`. Before any actual run, verify backup capacity and path handling in the user's environment. Do not move old runs.

Commit a compact review set in `reports/experiments/<experiment_id>/<run_id>/` using identical IDs. Schema v1 requires `README.md`, `manifest.json`, `config.yaml`, `cells.json`, `convergence.csv`, `checks.json`, plus `comparison.csv` for comparisons and `validation.csv` when physical response claims require it; `plots/` optional. Record source SHA, package versions, scientific input/grid SHA-256, seed/method/topology/FE budget, **every planned cell**, separate search versus common-grid validation metrics, per-cell violations/failures/incompleteness and raw↔review integrity. Never fabricate unobserved convergence points or omit failed cells. Target ≤2 MiB/run; normally enforce ≤10 MiB unless user approves an exception. Never commit raw checkpoints or sensitive personal paths.

The exporter may be qualified with synthetic fixture records before any experiment. READY_FOR_REVIEW means **package integrity**, not independent scientific acceptance. Historical data and review packages are not rewritten to the new schema and must retain accessible provenance links.

## 7. Pause points, review decisions and recovery

- **After R0:** if historic raw, baseline source SHA, backed-up checkpoints or active long-running tasks cannot be accounted for, stop source deletion; report blocker to owner.
- **After R1:** if Q1 frozen semantics and proposed architecture conflict, produce an explicit disposition and seek user approval. Do not silently change Q1-01…23 or redefine Q0 fairness, 234-member initialization, 4,096 unique FE, seed/replay, or common-grid comparison.
- **Before high-risk R2–R4 merge:** require independent GitHub review; a failing scientific invariant blocks merge regardless of overall test count.
- **Before R5/R6 real COM or production test:** explicit experiment authorization, with exact source/config/seed/budget and intended run location. Synthetic software tests do not authorize production.
- **After R7:** consider cutover complete only if the new package tree, docs, CLI, raw/review outputs, import guards, scientific regression evidence and historical pointers all meet PR #55 and Issue #53 acceptance criteria. Close Issue #53 then; close/rebaseline Q1 gates only by their own approved qualification process.

Rollback for a failed migration is the Git branch/PR revert or temporary halt at the last reviewed SHA, **not** mutating historical raw nor constructing a legacy reader. The immutable old source and evidence remain available independently from the live package.

## 8. Immediate next actions

1. Extend/review Draft PR #55 with this staged migration plan; merge documentation only after independent review.
2. Complete R0 evidence inventory (Pi Code can perform read-only local raw/backup checks only after the corresponding Issue/instruction is authorized).
3. Implement R1 canonical docs and Q1 contract disposition **before** any Q1-B/C/D/E or source package deletion.
4. Create separate, implementation-ready Issues for R2–R7, one at a time as dependency gates pass; do not bulk-authorize experiments.
5. Maintain one owner-facing migration checklist in Issue #53; close only after independently verified R7 acceptance.
