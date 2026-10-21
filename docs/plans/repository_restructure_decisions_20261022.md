# Repository reconstruction — agreed design and implementation checklist

**Decision record:** 2026-10-21–22 (JST), consolidated from the user-approved project design discussion.  
**Tracking issue:** [#53](https://github.com/MasayaTakagi/saw-com-optimizer/issues/53).  
**Status:** target architecture and development/storage principles agreed; **implementation not yet performed**. This document authorizes neither production experiments nor modification/deletion of scientific raw data.  
**Purpose:** Preserve decisions until the reconstruction is implemented, reviewed, and reflected in the new canonical docs. Do not silently revert to today's layout for compatibility.

## 1. Non-negotiable principles

1. This is an **internal, still-developing service**: prefer the ideal simple current design, even when it requires breaking existing APIs or rewriting code. **No backward-compatibility wrappers, old-checkpoint readers, or data migration** merely to preserve old software behavior.
2. **Docs-first → TDD → minimum implementation → remove unused code and reconcile documents** for code changes. Tests are chosen for observable behavior and risks, not maximized for count.
3. KISS/YAGNI: no speculative abstraction or stage-specific copies. Keep an explicit and simple dependency direction. Reuse existing verified COM mathematics where appropriate; a breaking structural change does not require gratuitous numerical rewrites.
4. Preserve **scientific correctness, reproducibility, units and sign conventions, and fairness of comparisons**. Do not silently change equations, objectives, ranking, bounds, seeds, search-budget accounting, validation grids or scientific protocols under the label of refactoring.
5. **Discard current C2C/Codex-specific implementation and operating instructions** from the new repository: they are not product requirements. Pi Code remains an external implementation agent; ChatGPT independently reviews GitHub evidence. The product must not depend on an agent session or queue.
6. Old scientific raw data/checkpoints and the historical source commit identity must remain recoverable and unmodified; this is **data preservation**, not runtime backward compatibility. Git commits retain historical source; the new live repository should not carry obsolete compatibility paths.
7. Changes to material scientific conditions and new COM/production experiments require separate user decisions. A design memo or successful software test alone is not experiment authorization.

## 2. Final target tree (responsibility-oriented, not stage-oriented)

```text
saw-com-optimizer/
├── AGENTS.md
├── README.md
├── .gitignore
├── .python-version
├── pyproject.toml
├── uv.lock
├── docs/
│   ├── README.md
│   ├── roadmap.md
│   ├── architecture.md
│   ├── physics.md
│   ├── development.md
│   └── experiments.md
├── src/
│   └── sawopt/
│       ├── __init__.py
│       ├── cli.py
│       ├── physics/
│       │   ├── com.py
│       │   ├── elements.py
│       │   └── network.py
│       ├── design/
│       │   ├── topology.py
│       │   └── space.py
│       ├── evaluation.py
│       ├── optimization/
│       │   ├── lshade.py
│       │   ├── de.py
│       │   └── runner.py
│       ├── io/
│       │   ├── config.py
│       │   ├── results.py
│       │   └── checkpoints.py
│       └── plotting.py
├── tests/
│   ├── unit/
│   └── integration/
├── configs/
│   ├── examples/
│   └── experiments/
├── reports/
│   └── experiments/
└── .github/
    └── workflows/
        └── ci.yml
```

This is a **responsibility map**, not a demand to create empty modules. Add a module only when actual behavior warrants it. Keep documentation or scientific derivations in additional files only if the initial six active docs genuinely become unwieldy. Do **not** introduce duplicate `agent_docs/` trees or nested `AGENTS.md` without a demonstrated need.

### Code boundaries

- `physics/`: COM sections, devices, acoustic/electrical network and S-parameter computations; no optimizer, study or GitHub dependency.
- `design/`: topology, bounds, variable representation and canonicalization; no COM evaluation or runner dependency.
- `evaluation.py`: connect design, physics, RF metrics, constraints and the single declared candidate ranking contract. The same evaluator is shared by all optimizer algorithms.
- `optimization/`: solver strategies (L-SHADE, controlled DE) and search runner. Optimizer backends consume evaluator callbacks; no direct dependency on COM internals. Runner owns FE limits, caching and search execution without becoming an unbounded monolith.
- `io/`: configuration, result persistence, resumable optimizer checkpoints as required; no agent-oriented continuation.
- `plotting.py`: scientific figures / Smith outputs when implemented; `cli.py` is the user entry point. Long-running execution can use external process supervision; resuming a **run** is independent of resuming an **AI session**.
- Tests follow functional behavior (unit/integration), not historical stage folders. Config-driven experiments use the shared engine, **not** new `stage5*.py` implementations.
- Current `core/` and `problem/` are reorganized as `physics/`, `design/` and `evaluation.py`; current `optimizers/` and `optimization/` are unified. Retire `studies/`, agent-coupled `orchestration/`, separate `reporting/` and `runtime/` packages after moving only still-needed behavior.

### Removal scope

Remove obsolete tracked files and their **current** references/tests, including `.c2cignore`, `.codex/`, `docs/c2c/`, `docs/handoff/`, root `handoff/`, Codex/Sol routing instructions, old Codex callbacks/queue, obsolete lifecycle adapters, historical stage-specific scripts/config adapters, review-bundle transport code and legacy wrappers **unless a genuinely current product responsibility remains**. Do not copy their content into the new `AGENTS.md`. Removal is not permission to delete external experiment runs. Inspect references and remove or replace imports/tests in the same coherent change.

## 3. Documentation and agent instruction policy

- `AGENTS.md` is a small entry point (target **50–80 lines**, not a rigid limit): project goal, canonical document map, four-step development cycle, high-consequence scientific restrictions, basic uv commands, GitHub handoff. No old agent/model/provider/callback instructions, COM derivations or lengthy histories.
- `docs/README.md` is the document index and identifies one source of truth per topic.
- `docs/roadmap.md` owns product objectives, stages and current status (best-found, finite-budget ≠ proven global optimum; given COM inputs; independent optimization for every impedance map sample; B28/50-ohm is diagnostic).
- `docs/architecture.md` owns module/dependency contracts.
- `docs/physics.md` owns COM conventions, units, physical assumptions and numerical invariants. Keep traceable equations/analytic references as needed.
- `docs/development.md` owns Docs-first, RED→GREEN→REFACTOR, KISS/YAGNI, risk-based testing, PR review and agent role boundaries. Pi Code implements/pushes PR; ChatGPT independently reviews; user approves material scientific changes, experiments and transitions.
- `docs/experiments.md` owns experiment data location, schema, protocol freeze, fairness, review requirements, archival criteria and explicit execution approvals.
- Historical stage plans and agent procedures must not remain active instructions. Retain only compact, traceable scientific baseline and evidence pointers; remove irrelevant historical operating paperwork from the new working tree. Historic Git commits remain available for past code references.

### Test/CI principles

- TDD on changes in behavior; one focused test for each important contract, not repeated test fixtures for every redundant implementation detail.
- Low risk (docs/simple cleanup): links/static consistency. Normal code: focused RED/GREEN test + relevant smoke/integration. Scientific/compute core (COM equations, units, candidate ranking, RNG/replay, budgets, checkpoint integrity): relevant numerical regression, analytical limiting cases and integration checks, with full-suite runs at material release/experiment gates.
- Do not require old API bit-parity solely to keep historical software interfaces alive. **Keep numerical parity or controlled-change evidence where needed to interpret a scientific comparison**. Measure CI duration, flakiness and rework before claiming a faster process.
- No broad, repetitive full-suite requirement for every trivial documentation edit. CI and the policies are updated intentionally, not simply disabled.

## 4. Experiment data: permanent raw vs. versioned GitHub review evidence

**Two locations, common IDs and identical frozen scientific inputs**:

| Class | Path | In Git? | Purpose |
| --- | --- | --- | --- |
| Experiment templates | `configs/experiments/<experiment_id>.yaml` | Yes | Planned scientific conditions |
| Raw run | `$SAWOPT_DATA_ROOT/runs/<experiment_id>/<run_id>/` | **No** | All numerical data, checkpoints, intermediate arrays, full logs, replay/reanalysis |
| Review package | `reports/experiments/<experiment_id>/<run_id>/` | **Yes** | Independent GitHub review of completed, failed and incomplete work |
| Rules | `docs/experiments.md` | Yes | Normative storage/review contract |

- `SAWOPT_DATA_ROOT` is a configured **absolute persistent location outside every Git checkout/worktree**; WSL example: `/home/user/sawopt-data`. Do not hardcode user-specific paths in source. An unset/invalid path, destination within a worktree, conflicting run ID, unsafe path or inadequate destination must stop launch; no fallback to repo `runs/`.
- `experiment_id` is a stable lowercase slug (e.g. `stage5a2-comparison`). `run_id` uses UTC date/time plus random uniqueness (e.g. `20261022T010203Z-a1b2c3d4`). Same IDs for raw and review. A paired comparison's cells belong to one run.
- Raw example: `manifest.json`, `config.yaml`, `cells/<topology>/<method>/<seed>/`, `checkpoints/` and `logs/`. Store all high-volume traces, populations, optimizer and cache state only here. Optimize internal raw formats for fidelity and read-only investigation, not for Git diff.
- Put defensive ignore rules in `.gitignore` (e.g. repo-root `/runs/`, `/data/`); **do not ignore** `reports/experiments/`. Git ignore is not data durability. Back up important runs outside the worktree.
- No automatic raw deletion upon PR merge or review acceptance. Retain through independent scientific review and closeout. Archival/deletion requires a deliberate, separately reviewed decision. Old raw schemas do not have to be migrated or readable by the new runtime.
- Do not relocate Stage 4C/5A historic raw runs or silently rewrite their stored evidence as part of restructuring.

### GitHub review package (proposed `review schema v1`)

```text
reports/experiments/<experiment_id>/<run_id>/
├── README.md
├── manifest.json
├── config.yaml
├── cells.json
├── convergence.csv
├── checks.json
├── comparison.csv         # required for paired/method comparisons
├── validation.csv         # required when interpreting RF response needs it
└── plots/                 # optional
```

| File | Required data |
| --- | --- |
| `README.md` | Hypothesis/purpose, scope, main findings, limitations, reviewer instructions and scientific disposition **as a claim to be reviewed**, not automatic acceptance. |
| `manifest.json` | Review schema, IDs, immutable execution source SHA, creation/finish time and states, software environment, exact method/topology/seed/FE budget, expected cell roster, config/COM input/search-grid/validation-grid hashes, important raw artifact hashes, review artifact sizes/hashes (exclude self-hash), completeness and redaction status. Git branch HEAD may move after execution: **execution SHA never changes**. |
| `config.yaml` | Frozen *effective* scientific configuration used in the execution, stripped of credentials/private absolute user paths. |
| `cells.json` | **Every expected cell**, including failed/incomplete, with status/reason, topology/method/seed, unique search FEs, proposal/duplicate/failure accounting, time, best-found vector and geometry, search metrics, **separate dense/common-grid validation** metrics, feasibility and individual constraint violations; missing fields explicitly noted. |
| `convergence.csv` | Predeclared common FE checkpoints, observed search best-so-far quality, elapsed time and cell identity. Never forward-fill missing measurements as if observed. |
| `checks.json` | Completeness, expected-vs-present cells, config/source/hash consistency, FE accounting, exported-artifact hashes, redaction and tests executed/not executed. |
| `comparison.csv` (comparisons) | Pair identity, methods, result differences, exact pairing/aggregation rules, ties, incomplete/censored or non-comparable cases, missing reasons and seed coverage. |
| `validation.csv` (when needed) | Selected candidates' common-grid frequency response (e.g. frequency in Hz, S-parameter real/imag or explicitly defined magnitude/phase), enough to independently recompute the cited RF metrics; clear units. |
| `plots/` | Optional compact visualizations, not evidence in lieu of machine-readable numbers. |

- Prefer UTF-8 JSON for structured records, CSV with named/unit-bearing columns for tables/traces, YAML for effective configuration, Markdown for reviewer narrative and PNG for figures. Specify `status`/`null` for missing/nonfinite numerical results; no ambiguous silent omission.
- Target review package **≤2 MiB per run**; default hard cap **10 MiB**, with an explicit preapproved exception if scientific evidence needs more. Never delete indispensable evidence only to satisfy size targets. No automatic Git LFS.
- Never commit full checkpoints, populations/archives, caches, giant NumPy arrays, all-proposal logs, full stdout/stderr, credentials or personal path details. Include a sanitized logical raw identifier + SHA-256 instead of treating a user-specific path as a portable reference.
- Export/check complete package before marking **READY_FOR_REVIEW**. Packaging and independent ChatGPT scientific acceptance are different states. Summary review cannot claim bitwise verification of raw candidates not actually read.
- If GitHub evidence is insufficient, a separate **read-only** local raw audit can publish an additional compact GitHub artifact; no silent rerun or recomputation with changed assumptions.

## 5. Operation/review contract

1. For a new experiment, document the hypothesis/conditions, frozen input, budget, seed pairing, validation grid, source SHA, raw location and **required review evidence** before launch.
2. User authorizes real COM/optimization/production execution separately. The repository restructuring and this plan do not authorize it.
3. Experiment writes only into the configured external raw run. Persist enough information for recovery and provenance; never automatically dispatch further work from an agent callback.
4. Generate the compact GitHub review package on the experiment branch and PR; correlate exact run ID and hashes with raw. Keep incomplete/failed cells visible.
5. ChatGPT reads the code diff, exact execution source, frozen settings, all-cell evidence, convergence and failure accounting. Request bounded additional raw-derived evidence if needed. Independently record acceptance/rejection with limitations. A numerical PASS is not scientific acceptance.
6. Do not run more production or promote new scientific conclusions without the relevant user decision.

## 6. Reconstruction execution checklist (future implementation PR(s))

- [ ] **Preflight**: record current main SHA, identify active Q1-A/PRs and in-flight external runs, verify available backups of historic raw results. No mutation or cleanup of raw scientific data.
- [ ] **Documentation first**: create/finalize six active docs and minimal `AGENTS.md`, replacing the old reference paths; resolve contradiction between issue #52/Q0/Q1 and this new architecture before issuing new Pi Code work.
- [ ] **Risk-based TDD**: define tests against new public behavior and retained scientific invariants. Do not blanket-require legacy API parity.
- [ ] **Implement smallest new working vertical slice** (physical response → design → evaluate → optimize → save → review export/CLI) using the target dependency boundaries. Only implement features currently required by the roadmap.
- [ ] **Migrate/retire current code intentionally**: eliminate old `core/problem/optimizers/studies/orchestration/reporting/runtime` boundaries, legacy flags/adapters, agent-specific integration and stale references. Rewire imports, tests, configs and docs; no compatibility shims.
- [ ] **Raw/review contract**: check external run root validation, reproducible IDs/hashes, fail-closed collisions, size/redaction/completeness, all-cell evidence and read-only audit support. Avoid unapproved real COM or production testing.
- [ ] **Final KISS pass**: remove dead files and redundant tests, audit source/test/doc links and entry points, review numerical invariants, and reconcile plans/gates/issue outcomes.
- [ ] **Independent PR review**: inspect actual diff and tests before merging. Record preserved scientific baseline and any comparisons made invalid by structural changes.
- [ ] **Closeout**: mark this temporary planning file superseded only when `AGENTS.md`, `docs/{roadmap,architecture,physics,development,experiments}.md` and the actual repository layout reflect its clauses; update/close Issue #53.

### Specific Q1-A conflict rule

[Issue #52](https://github.com/MasayaTakagi/saw-com-optimizer/issues/52) authorized a narrow Q1-A work unit under older Stage 5A-2 contracts, including bit-exact legacy canonicalization and compatibility conditions. **This new plan is not a retroactive cancellation or silent approval to change optimizer/comparator/physics science**. Before starting restructuring or instructing Pi Code to rewrite Q1, reconcile live PR state, update the authoritative docs/Issue #52 explicitly, and obtain any necessary user approval for altered scientific conditions. Preserve pending/failed qualification evidence honestly; do not report unrun gates as PASS.

## 7. Review acceptance checklist for the reconstruction itself

This decision record is fulfilled only when a reviewer can find:

- A small, accurate, **non-C2C/non-Codex-specific** `AGENTS.md` and one current source of truth per topic.
- New `physics/design/evaluation/optimization/io` package responsibilities and no hidden imports from retired legacy modules.
- Config-driven experiments; no mandatory stage-specific runtime, AI queue or GitHub PR exporter dependency in numerical computation.
- External `SAWOPT_DATA_ROOT` raw storage (not under any worktree) and compact committed `reports/experiments/<experiment_id>/<run_id>/` review evidence with source/config/seed/FE/validation identity.
- Test selection proportional to risk and meaningful COM numerical/comparator/accounting safety checks.
- Historical scientific data and commit provenance preserved, without new backward-compatibility/data-migration code.
- Explicit Q1/production authorization states and independent GitHub review.

**Current action boundary:** This record can be created/reviewed without changing the implementation, performing COM calculations, deleting datasets or starting experiments.
