# SAW Optimizer Architecture Refactoring Plan

**Target repository:** `saw-com-optimizer`  
**Execution target:** Codex / GPT-5.6 Luna / ExHigh  
**Primary goal:** separate reusable optimizer/search infrastructure from experiment-specific orchestration without changing numerical behavior or invalidating past experiment semantics.  
**Plan revision:** 2026-09-11, updated against `saw-com-optimizer_new.zip` after completion of the latest Stage 3.2 production/escalation experiment.  
**Behavioral baseline for the refactor:** the NEW repository snapshot, not the older snapshot used for the first version of this plan.

---

## Revision delta — 2026-09-11

The repository changed after the first version of this plan. Codex must treat the following as **current production behavior/configuration to preserve**, not as refactor opportunities to undo.

### Source change

`src/sawopt/optimization/stage32_study.py` now contains a stagnation-recovery path for the legacy SciPy differential-evolution continuation trajectory.

New behavior:

- `ContinuationTrajectory._run_de()` may make up to **4 DE attempts** when a segment produces no new canonical/unique design.
- After each of the first 3 zero-progress attempts, `_diversify_after_stagnation()` rebuilds the DE initializer.
- The refreshed population is generated with the existing trajectory RNG (`self.rng`), current active bounds, and `_build_population()`.
- The refresh is centered on the current best decoded design when available, otherwise the default `FilterDesign`.
- Population size is preserved, with a minimum of 5.
- The first `max(1, len(population)//4)` members of the prior population are retained in the refreshed population.
- Each DE attempt still uses `seed=self.seed + self.segment_index`; `segment_index` increments after every attempt, including zero-progress attempts.
- If any attempt increases `actual_unique_design_evaluations`, `_run_de()` clears `stop_reason` and returns success.
- `stop_reason = "no_new_unique_designs"` is set only after all 4 attempts fail to add a new unique design.

This logic was introduced to handle integer/canonical decoding collapse near convergence. **Do not simplify it back to the previous single-attempt stop behavior during the refactor.**

Architectural ownership decision for this plan:

> The retry/diversification decision is a continuation-study/search policy, not a generic property of SciPy DE. Keep it with the continuation protocol (`studies/continuation.py`) unless a later, separately justified design change proves it is reusable. Only lower-level population construction primitives may move to `optimization/population.py`.

### Configuration changes

The new snapshot also adds/changes the following:

- `configs/stage3_2_production_process5_fragment.yaml`
  - enables seed-level production parallelism,
  - sets `production_workers: 5`,
  - sets `blas_threads_per_worker: 1`.
- `configs/stage3_2_center16000_fragment.yaml`
  - keeps budgets `[500, 1000, 2000, 4000, 8000]`,
  - adds `optional_max_budget: 16000`,
  - enables `auto_escalate: true`.
- `configs/studies/next_50ohm_dms_production.yaml` now loads `stage3_2_production_process5_fragment.yaml` **after** `stage3_2_convergence_fragment.yaml`, so the production worker setting is not overwritten by the historical single-worker default.
- `configs/studies/next_50ohm_center_outer_same_16000.yaml` is a new concrete experiment instance for 50 ohm / `center_outer_same`, 5 cold seeds, optional escalation to 16,000 unique designs, and production worker count 5.

The order of config fragment application is therefore observable behavior. Preserve merge order and last-fragment-wins semantics while extracting config infrastructure.

Generated `__pycache__` changes in the ZIP are not source changes and must never be committed as part of the refactor.

---

## 0. Executive summary

The repository has reached the point where experimental history is leaking into the software architecture.

`src/sawopt/core/` is already a useful physical-model boundary, but `src/sawopt/optimization/` currently contains all of the following in one package:

- reusable optimizer algorithms,
- optimizer backend interfaces,
- feasibility-first selection logic,
- SAW-specific evaluation logic,
- adaptive frequency-grid logic,
- budget/counter/cache infrastructure,
- runtime/parallel helpers,
- run/config/provenance utilities,
- generic study orchestration,
- Stage 2 / 3.1 / 3.2 / 3.3 / 3.3.1 experiment orchestration,
- some report/bundle generation.

The main refactoring objective is therefore **not** to make files smaller for its own sake. It is to establish stable dependency boundaries so that:

1. adding a new experiment usually adds **YAML/README only**;
2. adding a new optimizer adds one implementation under `sawopt/optimizers/`;
3. optimizer implementations do not know about Stage numbers, Band 28, wiring names, or SAW physics;
4. reusable studies are named by what they do, not by chronological Stage numbers;
5. historical commands and result files remain readable/reproducible during migration;
6. refactoring never silently changes search behavior.

The refactor must be performed incrementally and validated after every phase.

---

# 1. Current repository findings

At the time this plan was written, `src/sawopt/optimization/` contains approximately **7,209 lines**:

| File | Approx. LOC | Current role |
|---|---:|---|
| `backends.py` | 137 | optimizer backend abstraction + legacy SciPy DE backend |
| `lshade.py` | 848 | stateful L-SHADE implementation |
| `selection.py` | 136 | feasibility-first comparison and time-to-target |
| `polish.py` | 80 | Powell continuous polish |
| `optimizer_utils.py` | 494 | counters, cache, frequency adaptation, budget/convergence helpers |
| `study.py` | 738 | evaluation, dense validation, initialization, population, polish, optimization and impedance sweep |
| `hybrid_study.py` | 436 | hybrid/topology-specific study |
| `stage2_study.py` | 283 | Stage 2 orchestration |
| `convergence_study.py` | 835 | Stage 3.1 convergence/certificate orchestration |
| `stage32_study.py` | 1,113 | Stage 3.2 continuation/bound expansion orchestration + stagnation recovery |
| `stage33_study.py` | 1,166 | Stage 3.3 optimizer A/B orchestration + validation/report/bundle logic |
| `stage331_preprod.py` | 932 | Stage 3.3.1 preproduction/invariant/bundle workflow |

The main architectural smell is not merely file size. There are cross-study imports of private implementation details, including:

- `convergence_study.py -> study._mixed_variable_polish`
- `hybrid_study.py -> study._HistoryBuffer`, `study._adaptive_settings`
- `stage2_study.py -> hybrid_study._dense_hybrid`
- `stage32_study.py -> convergence_study._cold_seeds`, `_load_config`, `_primary`, `_status`, `_thresholds`
- `stage33_study.py -> convergence_study._cold_seeds`, `_load_config`
- `stage331_preprod.py -> convergence_study._load_config`
- `stage331_preprod.py -> stage33_study._evaluate_promotion_gate`, `_evaluator_factory`, `_lshade_exchange_at_checkpoint`

This makes Stage modules function as hidden shared libraries.

`study.py` and `optimizer_utils.py` also have a boundary problem: candidate selection in `optimizer_utils.py` depends on ranking in `study.py`, while `study.py` imports utilities from `optimizer_utils.py`. Local imports are being used to avoid a hard circular import. The shared abstraction belongs elsewhere.

The current test suite collects **92 tests**. Several are especially valuable as refactoring acceptance tests:

- fixed-seed reproducibility,
- resume behavior,
- feasibility-first comparator behavior,
- unique-design budget accounting,
- canonical duplicate handling,
- checkpoint resume parity,
- L-SHADE state/resume contract,
- frequency-grid exchange behavior,
- continuation boundary policies,
- common dense validation,
- source-hash/preproduction gates.

These tests should be preserved and moved with the code rather than rewritten to match changed behavior.

### Pre-existing configuration issue

`configs/studies/stage3_convergence_50ohm.yaml` references:

```text
../../stage3_1_convergence_fragment.yaml
```

but that fragment was not present in the repository snapshot used for this review.

**Do not invent or silently reconstruct this file as part of the refactor.** Treat it as a pre-existing repository issue. If it exists in the real Git history/worktree, use the real version; otherwise record the missing dependency separately.

---

# 2. Non-negotiable invariants

This section has higher priority than the desired folder layout.

During the structural refactor, Codex must **not intentionally change** any of the following unless a separate bug-fix commit is explicitly created after the refactor is green:

- COM equations or network physics;
- parameter bounds;
- default optimizer hyperparameters;
- seed derivation or seed lists;
- random-number-generator type or initialization;
- order of stochastic draws;
- population initialization semantics;
- integer/canonical decoding behavior;
- candidate deduplication behavior;
- feasibility-first ranking semantics;
- violation aggregation semantics;
- boundary repair semantics;
- unique-design budget accounting;
- raw offspring accounting;
- adaptive-frequency checkpoint timing;
- critical-frequency selection thresholds;
- validation-grid construction;
- polish promotion rules;
- convergence/plateau thresholds;
- Stage 3.2 bound-expansion policy;
- Stage 3.2 zero-progress DE retry/diversification semantics (4 total attempts, up to 3 initializer refreshes, retained population quarter, segment-index/seed progression, and final `no_new_unique_designs` behavior);
- config fragment merge order and override precedence, including the Stage 3.2 production-worker override and optional 16,000-budget escalation fragment;
- Stage 3.3 promotion gates;
- checkpoint state schema unless compatibility is preserved;
- existing result JSON/CSV field names;
- existing run artifact filenames;
- existing CLI behavior during the compatibility window.

Do not combine architecture refactoring with optimizer-strategy improvements.

If a real behavioral bug is discovered during the work:

1. first preserve current behavior in the refactor;
2. document the bug;
3. complete the structural refactor and get tests green;
4. fix the bug later in a separate commit with a dedicated regression test.

---

# 3. Desired final architecture

The intended dependency direction is:

```text
experiments/configs
        |
        v
     studies
        |
        v
  optimization engine
     /       \
    v         v
 problem   optimizers
    |
    v
   core

io/runtime/reporting are supporting services and must not become reverse
entry points into studies.
```

Recommended package layout:

```text
saw-com-optimizer/
|
+-- src/sawopt/
|   |
|   +-- core/                         # SAW/COM physics only
|   |   +-- com.py
|   |   +-- hybrid.py
|   |   +-- metrics.py
|   |   +-- models.py
|   |   +-- network.py
|   |
|   +-- problem/                      # SAW optimization problem definition
|   |   +-- __init__.py
|   |   +-- design_space.py
|   |   +-- evaluator.py
|   |   +-- frequency.py
|   |   +-- validation.py
|   |
|   +-- optimizers/                   # reusable optimizer core
|   |   +-- __init__.py
|   |   +-- base.py
|   |   +-- scipy_de.py
|   |   +-- lshade.py
|   |   +-- selection.py
|   |   +-- polish.py
|   |
|   +-- optimization/                 # reusable search engine/services
|   |   +-- __init__.py
|   |   +-- runner.py
|   |   +-- population.py
|   |   +-- budget.py
|   |   +-- counters.py
|   |   +-- cache.py
|   |   +-- adaptive_frequency.py
|   |   +-- history.py
|   |   +-- checkpoint.py
|   |
|   +-- studies/                      # reusable experiment protocols
|   |   +-- __init__.py
|   |   +-- registry.py
|   |   +-- impedance_sweep.py
|   |   +-- hybrid.py
|   |   +-- topology_screening.py
|   |   +-- convergence.py
|   |   +-- continuation.py
|   |   +-- optimizer_ab.py
|   |   +-- preproduction.py
|   |
|   +-- io/                           # config/result/provenance concerns
|   |   +-- __init__.py
|   |   +-- config.py
|   |   +-- serialization.py
|   |   +-- run_store.py
|   |   +-- provenance.py
|   |
|   +-- runtime/                      # process/thread environment helpers
|   |   +-- __init__.py
|   |   +-- parallel.py
|   |
|   +-- reporting/
|   |   +-- ... existing reporting ...
|   |   +-- optimizer_ab.py           # only if extraction is useful
|   |   +-- bundles.py                # only if extraction is useful
|   |
|   +-- __main__.py
|
+-- experiments/                      # experiment instances, no Python logic
|   +-- stage2_topology_screening/
|   |   +-- experiment.yaml
|   |   +-- README.md
|   +-- stage3_1_convergence/
|   |   +-- experiment.yaml
|   |   +-- README.md
|   +-- stage3_2_continuation/
|   |   +-- experiment.yaml
|   |   +-- README.md
|   +-- stage3_3_optimizer_ab/
|   |   +-- experiment.yaml
|   |   +-- README.md
|   +-- stage3_3_1_preproduction/
|       +-- experiment.yaml
|       +-- README.md
|
+-- configs/
|   +-- base/
|   +-- models/
|   +-- fragments/                    # reusable policy/config fragments
|
+-- tests/
|   +-- unit/core/
|   +-- unit/problem/
|   +-- unit/optimizers/
|   +-- unit/optimization/
|   +-- unit/studies/
|   +-- unit/io/
|   +-- integration/
|
+-- scripts/
+-- docs/
+-- runs/
```

This is the **target architecture**, not a mandate to create empty modules. Only create a module when real current code belongs there.

Avoid “architecture theater”: do not create dozens of 5-line forwarding modules merely to match this tree.

---

# 4. Dependency rules

These rules should be treated as architectural tests.

## 4.1 `core/`

May depend on:

- Python standard library,
- NumPy/SciPy as required,
- other `sawopt.core` modules.

Must not import:

- `sawopt.optimizers`,
- `sawopt.optimization`,
- `sawopt.studies`,
- experiment configuration,
- reporting orchestration.

`core` answers: **“Given physical parameters/design/topology and termination, what is the response?”**

## 4.2 `problem/`

May depend on:

- `core`.

Owns SAW-search-specific concepts such as:

- design-vector canonicalization,
- mapping vector <-> `FilterDesign`,
- manufacturing geometry validation,
- evaluation records,
- search/validation frequency handling.

It must not know about Stage numbers or a particular optimizer algorithm.

## 4.3 `optimizers/`

May depend on:

- standard numerical libraries,
- small generic typing/protocol definitions.

Should not import `sawopt.core` or `sawopt.studies`.

The optimizer receives an evaluator/callback and bounds; it must not know:

- what a SAW filter is,
- what Band 28 is,
- what `outer_ports` means,
- what Stage 3.3 is,
- what 50 ohm means.

## 4.4 `optimization/`

Owns reusable execution mechanics shared by studies:

- budgets,
- counters,
- caches,
- history,
- population utilities,
- adaptive-frequency search support,
- generic optimization runner glue.

It may compose `problem` and `optimizers`.

It must not import from `studies`.

## 4.5 `studies/`

Owns reusable experimental protocols, named by purpose rather than chronology.

Examples:

- convergence study,
- continuation/bound expansion,
- optimizer A/B comparison,
- topology screening,
- preproduction qualification.

**One study module must not import another study module’s private functions.**

If two studies require the same function, move that function down into `problem`, `optimization`, `io`, `runtime`, or a clearly named public shared module.

## 4.6 `experiments/`

Contains experiment instances and documentation only.

Default rule:

> A new seed set, impedance set, optimizer comparison, budget series, threshold choice, or production run must not require adding a Python source file.

A Python change is justified only when the experiment introduces a genuinely new reusable protocol or optimizer capability.

---

# 5. Stable conceptual interfaces

Do not over-generalize these interfaces immediately, but shape extracted code toward them.

## 5.1 Optimizer backend

The existing `OptimizerBackend` / `LShadeBackend` direction is good and should become the stable optimizer boundary.

Conceptually:

```python
class OptimizerBackend(Protocol):
    def initialize(self, ...): ...
    def advance_to_unique_budget(self, budget: int): ...
    def incumbent(self) -> dict | None: ...
    def population(self) -> ...: ...
    def state_dict(self) -> dict: ...
    def load_state_dict(self, state: dict) -> None: ...
    def summary(self) -> dict: ...
```

Do not change the actual L-SHADE behavior merely to force a pretty interface.

`ScipyDELegacyBackend` is a compatibility/reference algorithm and should stay available until Stage 3.3 historical comparisons no longer require it.

## 5.2 SAW optimization problem

Move toward one explicit problem object or equivalent cohesive functions:

```python
class SawOptimizationProblem:
    bounds: ...

    def canonicalize(self, vector): ...
    def decode(self, vector): ...
    def geometry_violations(self, design): ...
    def evaluate(self, vector, frequencies, rs, rl, wiring): ...
```

This need not be introduced as a large class in Phase 1. Prefer extracting behavior first; introduce a class only if it makes dependencies simpler.

## 5.3 Study runner

A study should eventually look conceptually like:

```python
cfg = load_experiment_config(path)
problem = build_problem(cfg)
study = build_study(cfg["study"]["type"], cfg, problem)
result = study.run(output_path)
```

Do not create a plugin framework. A simple explicit registry is enough:

```python
STUDIES = {
    "convergence": run_convergence,
    "continuation": run_continuation,
    "optimizer_ab": run_optimizer_ab,
    "preproduction": run_preproduction,
}
```

---

# 6. Migration strategy

Perform the refactor in phases. Each phase should be independently reviewable and should leave the repository in a working state.

Do not perform a giant one-commit rename/rewrite.

---

# Phase 0 — Baseline and characterization

## Objective

Establish a trustworthy before-state before moving code.

## Tasks

1. Read `AGENTS.md` and this plan completely before editing.
2. Run `git status --short`.
3. Preserve all unrelated user changes. Never reset or overwrite them.
4. Record the current commit hash if Git metadata is available.
5. Collect tests:

```bash
PYTHONPATH=src pytest --collect-only -q
```

Expected from the reviewed snapshot: approximately 92 tests.

6. Run fast/targeted architecture-relevant tests first:

```bash
PYTHONPATH=src pytest -q \
  tests/unit/optimization/test_optimizer_utils.py \
  tests/unit/optimization/test_stage32.py \
  tests/unit/optimization/test_stage33.py \
  tests/unit/optimization/test_stage331.py
```

7. Run the complete suite once before refactoring, using a sufficiently generous timeout in the Codex environment:

```bash
PYTHONPATH=src pytest -q
```

If the repository standard environment uses `unittest`, also run the documented command before final completion:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

8. Record any pre-existing failures. Do not “fix” unrelated failures inside structural commits.
9. Check these public entry points and record their current behavior/help:

```bash
PYTHONPATH=src python -m sawopt --help
PYTHONPATH=src python -m sawopt.optimization.hybrid_study --help
PYTHONPATH=src python -m sawopt.optimization.stage2_study --help
PYTHONPATH=src python -m sawopt.optimization.convergence_study --help
PYTHONPATH=src python -m sawopt.optimization.stage32_study --help
```

10. Before changing config loading, characterize resolved configuration equality for known valid Stage 3.2/3.3/preproduction configs.

11. Treat the newly added Stage 3.2 stagnation-recovery behavior as part of the baseline. Before moving `ContinuationTrajectory`, add/confirm a focused characterization test that demonstrates all of the following without running a long optimization:

```text
zero unique-design progress on DE attempt 1 -> diversify -> retry
zero unique-design progress on DE attempt 2 -> diversify -> retry
zero unique-design progress on DE attempt 3 -> diversify -> retry
zero unique-design progress on DE attempt 4 -> stop_reason=no_new_unique_designs
```

The test should also characterize:

- `segment_index` increments once per DE call;
- the DE seed sequence is `seed + prior_segment_index`;
- diversification is called only between failed attempts, at most 3 times;
- successful progress on any retry exits immediately and clears `stop_reason`;
- the retained old-population prefix size is exactly `max(1, n//4)`;
- the refresh uses the same trajectory RNG, active bounds, and current-best/default center.

Use monkeypatching/fakes around `differential_evolution` and/or `_build_population`; do not launch a production search just to characterize this behavior.

12. Snapshot the resolved values of the new/current Stage 3.2 configs before refactoring config loading. At minimum verify:

```text
configs/studies/next_50ohm_dms_production.yaml
  optimizer_validation.parallel.production_workers == 5
  optimizer_validation.parallel.blas_threads_per_worker == 1

configs/studies/next_50ohm_center_outer_same_16000.yaml
  impedance_grid_ohm == [50]
  wirings == [center_outer_same]
  seeds == [20260909, 20260910, 20260911, 20260912, 20260913]
  optimizer_validation.budgets == [500, 1000, 2000, 4000, 8000]
  optimizer_validation.optional_max_budget == 16000
  optimizer_validation.auto_escalate == true
  optimizer_validation.parallel.production_workers == 5
  optimizer_validation.parallel.blas_threads_per_worker == 1
```

Also record the actual resolved config object or a stable normalized JSON form so Phase 2/5 can compare exact config semantics after moving loaders/fragments.

## Additional characterization tests to add only if needed

Prefer existing tests. Add tests only where they protect a migration boundary currently uncovered:

- resolved config merge result stays identical;
- old import paths still resolve during compatibility window;
- result field schema remains unchanged;
- existing CLI aliases route to the same implementation.

Do not add large golden files containing timing, platform metadata, or source hashes that are naturally unstable.

## Exit gate

- Baseline status documented.
- No source behavior changed.
- Pre-existing failures distinguished from new failures.

---

# Phase 1 — Extract the optimizer core

## Objective

Create a first-class `sawopt.optimizers` package without changing optimizer behavior.

This is the highest-priority structural change.

## Move implementation

Use `git mv` where practical.

### Current -> target

```text
src/sawopt/optimization/backends.py
    -> src/sawopt/optimizers/base.py
       src/sawopt/optimizers/scipy_de.py

src/sawopt/optimization/lshade.py
    -> src/sawopt/optimizers/lshade.py

src/sawopt/optimization/selection.py
    -> src/sawopt/optimizers/selection.py

src/sawopt/optimization/polish.py
    -> src/sawopt/optimizers/polish.py
```

### Details

- `OptimizerBackend` and `backend_name` -> `optimizers/base.py`.
- `ScipyDELegacyBackend` -> `optimizers/scipy_de.py`.
- `LShadeBackend`, `FixedDEReferenceBackend`, `parent_midpoint_repair`, `shade_success_memory` -> `optimizers/lshade.py`.
- `FeasibilityFirstComparator`, `DEFAULT_COMPARATOR`, `rank_key`, `compare`, `time_to_target` -> `optimizers/selection.py`.
- Powell/local optimizer implementation -> `optimizers/polish.py`.

## Important constraint

**Do not rewrite L-SHADE while moving it.**

No cleanup of mutation equations, archive logic, SHADE memories, RNG ordering, duplicate handling, boundary repair, state serialization, or budget accounting in this phase.

The new Stage 3.2 `_diversify_after_stagnation()` behavior is **not** part of the optimizer-core extraction. Do not move it into `optimizers/scipy_de.py` merely because it calls SciPy DE. The generic optimizer backend should remain free of continuation-specific unique-budget recovery policy.

## Compatibility layer

Historical imports and tests currently refer to paths such as:

```python
sawopt.optimization.lshade
sawopt.optimization.selection
sawopt.optimization.backends
sawopt.optimization.polish
```

Keep thin compatibility modules at those old locations for now, e.g.:

```python
# sawopt/optimization/lshade.py
"""Compatibility import. New code should use sawopt.optimizers.lshade."""
from ..optimizers.lshade import *
```

Prefer explicit re-exports with `__all__` if wildcard export could expose internals differently.

Do **not** leave duplicate implementations in both packages.

## Update new internal imports

All newly edited production code should import optimizer classes from `sawopt.optimizers`, not from compatibility shims.

## Tests

Move optimizer unit tests toward:

```text
tests/unit/optimizers/
```

but preserve compatibility-path tests for the old imports until the compatibility window is intentionally closed.

Run at minimum:

```bash
PYTHONPATH=src pytest -q \
  tests/unit/optimization/test_stage33.py \
  tests/unit/optimization/test_stage331.py
```

plus any moved optimizer tests.

Critical acceptance properties:

- fixed-seed deterministic behavior unchanged;
- canonical duplicates not charged twice;
- checkpoint resume equals uninterrupted run;
- success-memory behavior unchanged;
- boundary fixtures unchanged;
- comparator remains feasibility-first and penalty-invariant;
- state contains the same resume contract.

## Suggested commit

```text
refactor: extract reusable optimizer core
```

## Exit gate

- `sawopt.optimizers` is the canonical implementation location.
- old optimizer imports still work.
- no algorithm behavior changed.
- relevant tests pass.

---

# Phase 2 — Extract shared config, runtime, and serialization infrastructure

## Objective

Remove infrastructure that currently lives inside Stage modules and is imported privately by other Stage modules.

This phase should eliminate the most obvious cross-study private imports without yet renaming all studies.

## 2A. Configuration loading

Move reusable logic from `convergence_study.py`:

```text
_deep_update
_load_config
```

into:

```text
src/sawopt/io/config.py
```

Use public names such as:

```python
deep_update(...)
load_study_config(...)
```

Preserve exact current semantics, including:

- relative `base_config` resolution;
- ordered `config_fragments` merge;
- COM-file resolution relative to base config;
- exact input text capture used by review bundles;
- current deep-merge behavior.

Study-specific defaults such as `study_type`, Stage 3.1 convergence thresholds, or impedance defaults should **not** be hidden inside the generic loader. However, do not change behavior immediately. First separate generic loading from study-specific normalization with wrappers that reproduce current output exactly.

Target shape:

```python
cfg = load_study_config(path)
cfg = normalize_convergence_config(cfg)
```

`normalize_convergence_config` belongs to the convergence study until a more reusable policy is proven.

## 2B. Serialization/run-store helpers

Extract duplicated generic helpers such as:

- JSON-safe conversion,
- generic JSON save,
- generic CSV write,
- hashing utilities where semantics are identical.

Possible targets:

```text
src/sawopt/io/serialization.py
src/sawopt/io/run_store.py
src/sawopt/io/provenance.py
```

Do not force semantically different hashing methods into one function merely because they both use SHA-256.

Preserve source-fingerprint semantics required by Stage 3.3/3.3.1.

## 2C. Runtime/parallel helpers

There are repeated BLAS/process helpers in convergence, Stage 3.2, Stage 3.3 and preproduction code.

Move truly identical environment logic into:

```text
src/sawopt/runtime/parallel.py
```

Examples:

- single-BLAS-thread environment context,
- safe spawn-context selection if shared,
- worker-count normalization if shared.

Do not create one generic worker dispatcher if the studies have meaningfully different task/resume semantics.

## Tests

Add/retain tests ensuring:

- config resolution is byte/structure equivalent before and after extraction;
- review-bundle input text remains reproducible;
- source hash gate behavior remains unchanged;
- parallel invariant tests still pass.

## Suggested commit

```text
refactor: extract shared study infrastructure
```

## Exit gate

- Stage 3.2/3.3/3.3.1 no longer import config loaders from `convergence_study.py`.
- fragment composition preserves ordered, last-fragment-wins overrides; specifically the new `stage3_2_production_process5_fragment.yaml` must continue to override the historical worker setting from earlier fragments.
- the 16,000 escalation values from `stage3_2_center16000_fragment.yaml` resolve identically before and after extraction.
- generic serialization/runtime helpers are not duplicated across Stage files.
- no numerical behavior changed.

---

# Phase 3 — Separate the SAW optimization problem from search mechanics

## Objective

Break up `study.py` and `optimizer_utils.py` by responsibility and remove their circular dependency smell.

This is the most conceptually important phase after optimizer extraction.

## 3A. Candidate selection/ranking

`rank()` currently belongs in `study.py`, but selection logic belongs with the feasibility comparator.

Move or define the canonical rank implementation under:

```text
src/sawopt/optimizers/selection.py
```

or a very small shared selection API that delegates to `DEFAULT_COMPARATOR`.

Then update candidate-selection helpers to depend directly on that public selection API.

Goal:

```text
optimizer_utils -> study.rank
```

must disappear.

Do not change rank tuple contents or tie-breaking.

Keep a compatibility `study.rank` re-export during migration.

## 3B. SAW evaluator

Extract from `study.py` and Stage 3.3 the reusable problem behavior currently represented by:

- `evaluate_design`,
- dense evaluation,
- invalid manufacturing/numerical record construction,
- design decoding/canonicalization where common,
- geometry validation where common.

Target:

```text
src/sawopt/problem/evaluator.py
src/sawopt/problem/design_space.py
src/sawopt/problem/validation.py
```

Important: there are currently multiple canonicalization/build-population functions because some studies have active/dynamic bounds or topology-specific variables. Do **not** falsely unify them.

Extract only the common primitive behavior. Keep policy-specific wrappers in the relevant study/optimization module.

A good boundary is:

```python
canonicalize(vector, bounds, integer_indices_or_metadata)
evaluate_filter_design(design, cfg, frequencies, rs, rl, wiring)
geometry_violations(design, constraints)
```

while Stage 3.2 remains responsible for deciding **which active bounds are currently valid**.

## 3C. Frequency adaptation

Move from `optimizer_utils.py`:

- `critical_frequencies`,
- `new_frequency_points`,
- `common_validation_grid`,
- frequency-control helper primitives,

into:

```text
src/sawopt/optimization/adaptive_frequency.py
```

or `problem/frequency.py` if the implementation is intrinsically tied to RF/SAW response semantics.

Use this rule:

- “where should frequencies be sampled for this RF problem?” -> `problem/frequency.py`;
- “when should an optimizer exchange/re-evaluate a grid?” -> `optimization/adaptive_frequency.py`.

Keep those two concerns separate if doing so does not require behavioral rewrite.

## 3D. Counters/cache/history/budget

Extract:

```text
EvaluationCounters       -> optimization/counters.py
IncrementalFrequencyCache -> optimization/cache.py
_HistoryBuffer           -> optimization/history.py
PlateauStopper            -> optimization/budget.py or convergence policy module
_adaptive_budget_limits   -> optimization/budget.py
scaled_population         -> optimization/population.py
```

`paired_improvements` and `last_significant_improvement` may remain with convergence analysis if they are only used for that protocol; do not force them into a generic utility module without multiple consumers.

## 3E. Mixed-variable polish

There are two polish concepts:

- generic optimizer implementation (`Powell`),
- SAW/mixed-variable promotion policy around it.

Keep the generic numerical optimizer in:

```text
optimizers/polish.py
```

Move the SAW-specific mixed-variable orchestration out of `study.py` into an optimization/problem-level module, e.g.:

```text
optimization/polish.py
```

or a more descriptive name if needed.

This removes the private import:

```text
convergence_study -> study._mixed_variable_polish
```

## 3F. Base run initialization and generic run store

`initialize()` and `save()` are not optimization algorithms.

Move generic run-directory/manifest persistence into `io/run_store.py` while retaining compatibility re-exports from `study.py` until callers have migrated.

## Tests

Run all optimization-related unit tests after this phase:

```bash
PYTHONPATH=src pytest -q tests/unit/optimization tests/unit/optimizers tests/unit/problem
```

(adjust directories to those that actually exist after the move).

Also run:

```bash
PYTHONPATH=src pytest -q tests/integration/test_study.py
```

Critical assertions:

- `rank()` exact behavior unchanged;
- adaptive budget sums unchanged;
- incremental cache evaluates only new points;
- dense/incremental metric parity unchanged;
- common validation grid unchanged;
- polish only promotes strictly better rank according to existing comparator;
- fixed seeds remain reproducible.

## Suggested commit

```text
refactor: separate SAW problem from optimization services
```

## Exit gate

- no circular dependency between old `study` and optimizer utility concepts;
- `optimizer_utils.py` is either gone or a thin compatibility module;
- `study.py` is significantly reduced or is a compatibility facade;
- optimizer algorithms remain independent of SAW physics.

---

# Phase 4 — Convert Stage modules into reusable studies

## Objective

Remove chronological Stage numbering from the canonical source architecture.

Stage numbers should remain experiment/history labels, not reusable implementation names.

## Canonical moves

### Current -> target concept

```text
optimization/hybrid_study.py
    -> studies/hybrid.py

optimization/stage2_study.py
    -> studies/topology_screening.py

optimization/convergence_study.py
    -> studies/convergence.py

optimization/stage32_study.py
    -> studies/continuation.py

optimization/stage33_study.py
    -> studies/optimizer_ab.py

optimization/stage331_preprod.py
    -> studies/preproduction.py

optimization/study.py::run
    -> studies/impedance_sweep.py   (if it is specifically the basic impedance sweep)
```

Use names based on behavior. If inspection shows a better descriptive name, use it and document the mapping.

## Required extraction of shared functionality

Before/while moving, remove all cross-study private imports.

### Specifically resolve

```text
stage2_study -> hybrid_study._dense_hybrid
```

Move dense hybrid evaluation to `problem` or expose a deliberately public hybrid evaluator.

```text
stage32_study -> convergence_study._cold_seeds
```

Seed normalization is shared infrastructure; move to a public config/study utility only if the semantics are genuinely shared.

```text
stage32_study -> convergence_study._primary/_status/_thresholds
```

Determine whether these are:

- a shared convergence policy -> extract a named public convergence policy module, or
- truly Stage 3.1 behavior -> duplicate policy is not acceptable; instead have Stage 3.2 depend on a lower-level public `ConvergencePolicy` concept, not on a study module.

```text
stage331_preprod -> stage33_study._evaluator_factory
```

Move common SAW evaluator construction to `problem/evaluator.py`.

```text
stage331_preprod -> stage33_study._lshade_exchange_at_checkpoint
```

Move checkpoint frequency-exchange orchestration to a reusable optimization service only if preproduction is validating the exact same mechanism. Give it a public name.

```text
stage331_preprod -> stage33_study._evaluate_promotion_gate
```

Move the gate to a named public policy object/function, e.g. `studies/policies.py` only if it is genuinely a reusable study policy. Prefer a narrower module such as `studies/optimizer_ab_policy.py` if appropriate.

The important rule is: **preproduction validates a public production contract; it does not reach into another study’s private implementation.**

### Preserve the new Stage 3.2 stagnation-recovery policy

When `stage32_study.py` becomes `studies/continuation.py`, move `ContinuationTrajectory._diversify_after_stagnation()` and its `_run_de()` retry loop together as one behavioral unit.

Do not:

- replace the 4-attempt loop with a generic optimizer retry wrapper;
- change the number of retry attempts;
- change when `segment_index` increments;
- derive retry seeds differently;
- reseed `self.rng`;
- change the quarter-population retention rule;
- change the center used to refresh the initializer;
- charge duplicate/cached designs differently;
- change when `stop_reason` is cleared or set.

If `_build_population()` is extracted to `optimization/population.py`, retain a characterization/parity test proving the continuation trajectory produces the same refreshed initializer for the same RNG state, center, bounds and population size.

## Keep compatibility entry points

During the migration window, old commands must continue to work.

Keep thin wrappers such as:

```text
sawopt.optimization.stage32_study
sawopt.optimization.stage33_study
sawopt.optimization.stage331_preprod
```

that forward to canonical implementations in `sawopt.studies`.

The wrappers should contain no optimization logic.

Add a short deprecation comment/documentation, but do not print noisy runtime deprecation warnings into experiment logs unless explicitly desired.

## Reporting extraction

`stage33_study.py` currently also performs reporting/bundle operations.

Once study behavior is stable, consider moving:

- report rebuild,
- HTML/CSV formatting,
- review-bundle creation,

into `reporting/`.

Do this only where the extraction is clean. Do not block the main architecture refactor on perfect report factoring.

## Tests

Move tests according to canonical ownership:

```text
test_stage32.py  -> tests/unit/studies/test_continuation.py
test_stage33.py  -> tests/unit/studies/test_optimizer_ab.py
test_stage331.py -> tests/unit/studies/test_preproduction.py
```

Test names should describe behavior, not only Stage numbering.

Keep a small compatibility-entry-point test if old module paths are retained.

Run all unit and integration tests after this phase.

## Architectural acceptance test

Add a lightweight test or static script that rejects these dependency directions:

- `core -> optimizers/optimization/studies`
- `optimizers -> core/studies`
- `problem -> studies`
- `optimization -> studies`
- any canonical `studies/*.py` importing `_private_name` from another `studies/*.py`.

Do not add a heavy external dependency solely for architecture checking; an AST-based test is sufficient.

## Suggested commit

```text
refactor: move experiment protocols into studies package
```

## Exit gate

- canonical source files are named by reusable behavior, not Stage number;
- no study-to-study private imports remain;
- old Stage import/CLI paths still work through thin wrappers;
- full test suite passes or matches documented pre-existing baseline.

---

# Phase 5 — Make experiment instances configuration-driven

## Objective

Stop adding Python modules for ordinary new experiments.

This phase changes repository organization and CLI/config routing, but must still preserve experiment semantics.

## 5A. Create `experiments/`

Create experiment directories for historically important/current workflows, for example:

```text
experiments/
  stage2_topology_screening/
    experiment.yaml
    README.md
  stage3_1_convergence/
    experiment.yaml
    README.md
  stage3_2_continuation/
    experiment.yaml
    README.md
  stage3_3_optimizer_ab/
    experiment.yaml
    README.md
  stage3_3_1_preproduction/
    experiment.yaml
    README.md
  stage3_2_center_outer_same_16000/
    experiment.yaml
    README.md
```

The current `configs/studies/next_50ohm_center_outer_same_16000.yaml` is a particularly good migration fixture because it is a concrete experiment instance rather than reusable source logic. Its fragment stack and resolved values must remain identical after migration.

Do not move all historical configs blindly. First distinguish:

- reusable base/model config,
- reusable fragment/policy,
- concrete experiment instance.

Recommended final responsibilities:

```text
configs/models/       physical/COM parameter sets
configs/base/         reusable baseline filter/spec constraints
configs/fragments/    reusable optimizer/study policy fragments
                      (e.g. production-process-5-worker policy, optional-16000 escalation policy)
experiments/*/        concrete run definitions
                      (e.g. 50-ohm center_outer_same 16k escalation run)
```

## 5B. Explicit study type

Each experiment config should eventually declare the reusable protocol explicitly, e.g.:

```yaml
study:
  type: optimizer_ab
```

or, if preserving existing top-level keys first:

```yaml
study_type: optimizer_ab
```

Choose one format and document it.

Do not mechanically rename every existing YAML key in the same commit. Preserve compatibility with the currently deployed configs while introducing the new field.

## 5C. Generic study entry point

Add a canonical command such as:

```bash
PYTHONPATH=src python -m sawopt run-study \
  --config experiments/stage3_3_optimizer_ab/experiment.yaml \
  --run runs/stage3_3_50ohm
```

A shorter alternative is acceptable if it integrates naturally with the current CLI.

Internally use an explicit registry, not dynamic `eval`, arbitrary import paths, or a plugin framework.

## 5D. Preserve old CLI aliases

Existing commands currently include at least:

```text
python -m sawopt simulate
python -m sawopt optimize
python -m sawopt sweep
python -m sawopt report
python -m sawopt stage3_3
python -m sawopt stage3_3_1_preprod
```

and direct module invocations documented for older studies.

Keep these working during the migration window by routing them to the canonical study functions.

Update documentation to prefer the new generic command while marking old commands as compatibility aliases.

## 5E. No Python for ordinary next experiments

Validate the design by expressing at least one existing experiment variant entirely as config.

For example, a Stage 3.3 budget/seed/impedance variation should require only:

- new or modified experiment YAML,
- optional experiment README,

with **no new `src/sawopt/*.py` file**.

## Suggested commit

```text
refactor: make study instances configuration driven
```

## Exit gate

- an ordinary new experiment can be added without source-code duplication;
- canonical reusable studies are selected by config;
- legacy experiment commands remain usable;
- docs and launchers point to canonical paths where practical.

---

# Phase 6 — Cleanup and documentation

## Objective

Remove migration leftovers that are no longer useful while retaining deliberate compatibility where needed.

## Tasks

1. Update `src/README.md` to describe:
   - `core`,
   - `problem`,
   - `optimizers`,
   - `optimization`,
   - `studies`,
   - `io`,
   - `runtime`,
   - `reporting`.

2. Update `configs/README.md` and add `experiments/README.md`.
3. Update root `README.md` commands.
4. Update PowerShell launchers and analysis scripts to canonical imports.
5. Search for obsolete imports:

```bash
grep -RIn "sawopt.optimization.stage" src tests scripts docs configs
```

Old references should remain only where intentionally documenting/validating compatibility.

6. Search for cross-study private imports using AST or grep.
7. Ensure no implementation remains duplicated between compatibility modules and canonical modules.
8. Remove stale `__pycache__` from the worktree if present locally; do not commit generated cache files.
9. Do not alter existing `runs/`.
10. Do not regenerate old experimental results merely because source paths changed.

## Compatibility-shim removal

Do **not** remove old import shims in the same refactor unless all of the following are true:

- all scripts/docs/tests use canonical imports;
- no stored workflow depends on old module execution paths;
- the user explicitly accepts breaking old imports.

It is acceptable for the final repository to retain tiny compatibility files under `optimization/` while all real implementation lives elsewhere.

## Suggested commit

```text
refactor: update architecture docs and compatibility entry points
```

---

# 7. Concrete ownership map for existing symbols

This is a guide, not a blind mechanical mapping. Keep semantics first.

## From `optimization/backends.py`

| Symbol | Target |
|---|---|
| `OptimizerBackend` | `optimizers/base.py` |
| `backend_name` | `optimizers/base.py` |
| `ScipyDELegacyBackend` | `optimizers/scipy_de.py` |

## From `optimization/lshade.py`

| Symbol | Target |
|---|---|
| `LShadeBackend` | `optimizers/lshade.py` |
| `FixedDEReferenceBackend` | `optimizers/lshade.py` or `optimizers/de_reference.py` only if separation is real |
| `parent_midpoint_repair` | `optimizers/lshade.py` |
| `shade_success_memory` | `optimizers/lshade.py` |
| state JSON helpers | keep private beside L-SHADE unless reused independently |

## From `optimization/selection.py`

All canonical comparator/ranking/time-to-target behavior belongs under `optimizers/selection.py`, unless time-to-target proves purely study-analysis-specific. Preserve behavior first.

## From `optimization/optimizer_utils.py`

| Symbol | Likely target |
|---|---|
| `aggregate_diagnostics` | `problem/validation.py` or reporting/analysis if only diagnostic |
| `scaled_population` | `optimization/population.py` |
| `EvaluationCounters` | `optimization/counters.py` |
| `IncrementalFrequencyCache` | `optimization/cache.py` |
| `paired_improvements` | `studies/convergence.py` or convergence policy module |
| `last_significant_improvement` | `studies/convergence.py` or convergence policy module |
| `critical_frequencies` | `problem/frequency.py` |
| `new_frequency_points` | `problem/frequency.py` |
| `common_validation_grid` | `problem/frequency.py` |
| `primary_metric` | selection/convergence policy according to actual consumers |
| `validated_candidate_selection` | `problem/validation.py` or `optimization/runner.py` |
| `PlateauStopper` | `optimization/budget.py` |
| `adaptive_exchange` | `optimization/adaptive_frequency.py` |

## From `optimization/study.py`

| Symbol | Likely target |
|---|---|
| `save` | `io/run_store.py` / `io/serialization.py` |
| `initialize` | `io/run_store.py` |
| `evaluate_design` | `problem/evaluator.py` |
| `dense` | `problem/evaluator.py` or `problem/validation.py` |
| `_canonical_design` | `problem/design_space.py` |
| `_adaptive_budget_limits` | `optimization/budget.py` |
| `_record_primary` | shared selection/policy if actually shared |
| `_mixed_variable_polish` | `optimization/polish.py` |
| `_build_population` | `optimization/population.py` if generic; otherwise study policy |
| `_HistoryBuffer` | `optimization/history.py` |
| `_adaptive_settings` | config normalization or optimization policy module |
| `optimize_one` | `optimization/runner.py` |
| `run` | `studies/impedance_sweep.py` |
| `rank` | canonical public selection API |

## Stage modules

| Current module | Canonical target |
|---|---|
| `hybrid_study.py` | `studies/hybrid.py` |
| `stage2_study.py` | `studies/topology_screening.py` |
| `convergence_study.py` | `studies/convergence.py` |
| `stage32_study.py` | `studies/continuation.py` |
| `stage33_study.py` | `studies/optimizer_ab.py` |
| `stage331_preprod.py` | `studies/preproduction.py` |

---

# 8. Result and checkpoint compatibility contract

Refactoring a research optimizer is only successful if old and new experimental evidence remains interpretable.

## Preserve result schemas

Do not rename/remove existing fields in JSON/CSV records during this refactor.

Examples that must remain semantically stable include fields related to:

- design,
- metrics,
- violations,
- feasibility,
- objective/search objective,
- seed,
- wiring,
- requested/actual budget,
- unique decoded evaluations,
- objective calls/raw offspring,
- duplicate counts/rates,
- cache hits,
- solved frequency points,
- validation fields,
- polish fields,
- timing fields,
- optimizer memory/archive state where serialized.

Adding an explicit schema version is allowed only if it does not break old readers. Do not opportunistically redesign the schema here.

## Preserve checkpoints

Existing L-SHADE checkpoint/resume tests are high-value acceptance criteria.

New code must be able to:

- serialize the same logical state,
- resume deterministically,
- preserve terminal-horizon vs observation-budget semantics,
- preserve frequency-grid version behavior.

If module-qualified pickle objects are used anywhere, moving classes could break deserialization. Search for `pickle`, `joblib`, module-qualified serialization, and NumPy object serialization before moving classes. If present, implement compatibility carefully.

JSON state dictionaries are safer, but do not assume all historical artifacts are JSON without checking.

## Provenance/source fingerprints

Moving files will naturally change source hashes.

Do not modify old run manifests to pretend the code hash stayed the same.

Rules:

- old run provenance remains immutable;
- new runs record the new source hash;
- source-hash gate behavior itself must remain correct;
- refactor validation should compare numerical behavior independently of hash equality.

---

# 9. Numerical parity strategy

Do not demand byte-identical output for fields that are expected to vary because of the refactor environment, such as:

- wall-clock timing,
- CPU timing,
- absolute paths,
- source hashes,
- Git metadata if commit changed.

For deterministic numerical/search fields, prefer exact comparison where current behavior is exact:

- canonical design vectors,
- seed lists,
- unique evaluation counts,
- duplicate counts,
- checkpoint progression,
- rank tuples,
- fixed-grid frequency arrays where generated deterministically.

For floating physics results, use the same tolerances already encoded by current regression tests. Do not loosen tolerances merely to make the refactor pass.

For stochastic optimizers, preserve RNG call order. A mathematically equivalent code rewrite can still alter the trajectory if it changes when random numbers are drawn; avoid such rewrites in structural phases.

---

# 10. Testing matrix by phase

## Every phase

Run targeted tests for changed ownership first.

## After Phase 1

Focus on optimizer invariants and Stage 3.3/3.3.1 synthetic tests.

## After Phase 2

Add config/provenance/parallel tests.

## After Phase 3

Run all problem + optimization tests and `integration/test_study.py`.

## After Phase 4

Run all unit + integration tests.

## Final

Run both supported discovery paths where practical:

```bash
PYTHONPATH=src pytest -q
PYTHONPATH=src python -m unittest discover -s tests -v
```

Then run CLI smoke tests for canonical and compatibility commands.

Do not launch long production optimization runs simply as refactor tests. Use existing synthetic/smoke configurations and small budgets.

---

# 11. Required architecture acceptance criteria

The refactor is complete only when all applicable conditions below are met.

### Optimizer core

- [ ] `sawopt.optimizers` exists and is the canonical home of optimizer algorithms.
- [ ] L-SHADE implementation is not duplicated.
- [ ] optimizer modules do not import SAW physics/studies.
- [ ] legacy SciPy DE remains available for historical A/B comparison.

### Search/problem separation

- [ ] SAW evaluation/canonicalization/geometry behavior has a clear problem-layer owner.
- [ ] counters/cache/budget/history/frequency-exchange execution have clear shared owners.
- [ ] `study.py <-> optimizer_utils.py` circular dependency smell is gone.
- [ ] `rank` has one canonical implementation.

### Study architecture

- [ ] canonical study modules are named by purpose rather than Stage number.
- [ ] no canonical study imports another canonical study’s private symbols.
- [ ] preproduction validates public contracts rather than Stage 3.3 private functions.
- [ ] Stage-number modules, if retained, are only compatibility wrappers.

### Experiments

- [ ] at least one existing experiment is expressed via reusable study + config with no Stage-specific Python implementation.
- [ ] changing seeds/budgets/impedance/optimizer choice does not require a new source module.
- [ ] `experiments/` and reusable `configs/` responsibilities are documented.

### Compatibility

- [ ] existing important CLI commands still work during migration.
- [ ] old result files remain readable by current reporting tools.
- [ ] checkpoint resume invariants pass.
- [ ] Stage 3.2 stagnation recovery preserves 4-attempt/3-refresh behavior, segment-index seed progression, population retention, unique-budget semantics, and final stop reason.
- [ ] new Stage 3.2 production/16k configs resolve identically, including `production_workers: 5` and ordered fragment overrides.
- [ ] source provenance remains honest; old run hashes are not rewritten.

### Quality

- [ ] relevant tests pass or match explicitly recorded pre-existing failures.
- [ ] full suite passes before final handoff if it passed at baseline.
- [ ] no unrelated formatting/refactor noise.
- [ ] no generated `__pycache__` or run artifacts committed.

---

# 12. Things Codex must NOT do

Do not:

- redesign COM physics;
- tune optimizer parameters;
- remove or generalize away the newly added Stage 3.2 zero-progress diversification/retry policy;
- change Stage 3.2 retry count, retained-population fraction, retry seed progression, or 16,000 escalation/5-worker config semantics;
- replace SciPy DE/L-SHADE algorithms;
- “simplify” RNG behavior;
- normalize/round design variables differently;
- change feasibility tolerances;
- alter comparison ordering;
- merge Stage 3.2 and Stage 3.3 logic into one giant framework;
- introduce Hydra, Pydantic, Ray, Optuna, Nevergrad, DEAP, or other new frameworks merely for architecture;
- add a dependency-injection framework;
- implement dynamic plugins/import strings for study registration;
- convert all dictionaries to dataclasses in one pass;
- rename all config keys at once;
- rewrite all reporting code unless needed to break a dependency;
- delete old CLI/import paths before compatibility is verified;
- modify or regenerate historical `runs/`;
- repair unrelated scientific assumptions while moving files;
- create speculative optimizer interfaces for algorithms not implemented yet;
- add empty placeholder packages/files only to make the tree look complete;
- use broad automatic formatting that obscures semantic diffs.

Prefer the smallest coherent refactor that establishes each boundary.

---

# 13. Codex execution protocol

This section is written specifically for the Codex agent performing the work.

## Before editing

1. Read `AGENTS.md`.
2. Read this `REFACTOR_PLAN.md`.
3. Inspect only the source/tests/configs relevant to the current phase.
4. Check Git status and preserve user changes.
5. Establish baseline tests.

## During editing

- Work phase by phase.
- Use `git mv` for moves where helpful to preserve history.
- Keep compatibility shims when changing import paths.
- Update imports in small batches.
- Run targeted tests after each batch.
- If a phase introduces a regression, fix it before starting the next phase.
- Do not spend time polishing names/formatting while behavior is still unstable.
- Prefer public shared abstractions over importing another study’s `_private` symbol.
- Do not extract code merely because two snippets look similar; verify the semantics are actually the same.

## Commits

If the repository is clean enough to create commits, use one coherent commit per phase. Suggested sequence:

```text
1. test: characterize refactor compatibility boundaries       # only if new characterization tests are needed
2. refactor: extract reusable optimizer core
3. refactor: extract shared study infrastructure
4. refactor: separate SAW problem from optimization services
5. refactor: move experiment protocols into studies package
6. refactor: make study instances configuration driven
7. refactor: update architecture docs and compatibility entry points
```

If unrelated user modifications are present, do not commit them. If safe phase commits cannot be made without including unrelated changes, leave the work uncommitted and report the reason.

## On failure

When a test fails after a structural change:

1. assume the refactor caused it until proven otherwise;
2. compare against baseline;
3. inspect import ownership/state serialization/RNG ordering first;
4. revert or correct the structural change rather than weakening the test;
5. do not change numerical tolerances unless the prior tolerance was demonstrably incorrect and that bug fix is separated.

## Final report

At completion, report:

- final package tree;
- old -> new module map;
- compatibility shims retained;
- tests run and results;
- any pre-existing failures;
- any intentionally deferred cleanup;
- any discovered behavioral bugs not fixed because they were outside the structural scope;
- whether a normal new experiment now requires only config/docs.

---

# 14. Recommended immediate stopping point

The entire target architecture does not have to be implemented in one session.

All phases in this revision must use the post-experiment NEW snapshot as the before-state. Do not compare numerical parity against the earlier ZIP for Stage 3.2, because the new stagnation-recovery behavior is an intentional production change that occurred before refactoring begins.

The highest-value safe stopping point is after **Phase 4**:

```text
core/          physical solver
problem/       SAW optimization problem
optimizers/    optimizer algorithms
optimization/  reusable search mechanics
studies/       reusable experiment protocols
reporting/     reporting
```

with compatibility wrappers under old paths.

At that point the architecture problem is largely solved even if configuration files still reside under `configs/studies/`.

Phase 5 (`experiments/`) can then be performed as a second, lower-risk migration once the canonical source boundaries are stable.

This separation is recommended because moving Python architecture and redesigning config/CLI conventions simultaneously would make regressions harder to localize.

---

# 15. Definition of success for this project

The refactor should make the following future workflow natural:

## Add another L-SHADE experiment

Create/edit YAML only.

## Compare L-SHADE with CMA-ES later

Implement:

```text
src/sawopt/optimizers/cmaes.py
```

against the same optimizer contract, then select it in an existing reusable optimizer-comparison study.

Do **not** create `stage34_study.py` merely because it is the next experiment.

## Change impedance sweep from 20–200 ohm to a refined region

Change experiment configuration only.

## Change convergence budgets/seeds

Change experiment configuration only.

## Add a genuinely new experimental protocol

Add one reusable module under `studies/` named after the method/protocol, then instantiate it from config.

The key design rule is:

> **Chronology belongs in experiment metadata. Reusable behavior belongs in source code.**

And for the optimizer itself:

> **The optimizer searches vectors. The SAW problem gives those vectors physical meaning. The study decides how experiments are conducted.**

That separation should remain the architectural standard for subsequent development.
