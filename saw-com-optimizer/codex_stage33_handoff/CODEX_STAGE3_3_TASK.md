# Codex Task — Stage 3.3 Search Engine Validation and Production Parallelism

## 0. Goal

Upgrade the SAW structural optimizer so that we can answer two questions with evidence:

1. Does a proper L-SHADE-style engine reach good SAW design basins more reliably than the current SciPy-DE continuation at the same unique-design budget?
2. Can the chosen optimizer run as an exactly resumable trajectory while preserving the Stage 3.2 adaptive-frequency, automatic-bound and convergence logic?

Production execution must use seed-level process parallelism.

The current Stage 3.2 repository state is the source of truth. Do not reapply old Stage 1/2/3 patches mechanically.

Read `ALGORITHM_REVIEW.md` before coding.

---

## 1. Non-negotiable semantic rule

`center_outer_same` is a **wiring identifier**, not a geometry-sharing flag.

Do not add or reinterpret `center_outer_same=True/False` as a reduced/full geometry switch.

Stage 3.3 keeps the current physical design parameterization unchanged. A future geometry hierarchy must use an explicit independent interface and is out of scope here.

---

## 2. Introduce an optimizer backend API

Create an explicit engine abstraction, for example:

```python
class OptimizerBackend(Protocol):
    def initialize(...): ...
    def advance_to_unique_budget(self, target_unique_evals: int, evaluator, ...): ...
    def state_dict(self) -> dict: ...
    def load_state_dict(self, state: dict): ...
    def population(self) -> np.ndarray: ...
    def incumbent(self): ...
```

Backends:

- `scipy_de_legacy`: preserve current Stage 3.2 behavior for regression only.
- `lshade`: new production candidate.

Optional but recommended for algorithm isolation:

- `fixed_de_reference`: a simple in-house DE backend using the same backend/evaluator/comparator infrastructure as L-SHADE. This helps distinguish “new engine plumbing” from “L-SHADE strategy” effects.

All engines must share the exact same evaluator, canonical decode/cache, constraints, bounds, frequency grids, boundary logic and final validation.

---

## 3. True feasibility-first comparator

Implement one central comparator/rank-key used by:

- evolutionary parent/trial selection;
- p-best ordering;
- archive-success calculation;
- incumbent tracking;
- final reports.

Required semantics:

```text
feasible > infeasible

infeasible vs infeasible:
  min max_violation
  then min sum_violation
  then min worst_il_db

feasible vs feasible:
  min worst_il_db
  then configured secondary passband metric(s)
```

Do not use a penalty coefficient to choose between individuals in the new optimizer.

Keep a scalar `objective` only for compatibility/logging if needed.

Unit tests must include candidate pairs whose ordering would change under plausible penalty weights and prove comparator invariance.

---

## 4. L-SHADE implementation

Implement canonical L-SHADE behavior closely enough that it can be checked against published pseudocode/reference implementations.

### 4.1 Search space

Operate internally in normalized `[0,1]^D` coordinates.

Evaluation path:

```text
normalized vector
  -> physical bounds map
  -> canonical decode/round integers
  -> manufacturing/layout validity
  -> COM/network evaluation
```

Cache key must be based on the canonical decoded physical design, not raw floating vectors.

### 4.2 Mutation/crossover

Use `current-to-pbest/1/bin` with the external archive:

```text
v_i = x_i + F_i*(x_pbest-x_i) + F_i*(x_r1-x_r2)
```

where `r2` may come from population union archive.

Use a p-best fraction consistent with SHADE/L-SHADE. Make the relevant constants config-driven and record them in manifests.

### 4.3 Success-history parameter adaptation

Maintain `M_F`, `M_CR` arrays initialized to 0.5.

For each target:

- choose a memory index;
- sample `F` from Cauchy(memory, 0.1), resampling `F<=0`, clip `F>1`;
- sample `CR` from Normal(memory, 0.1), clip to `[0,1]`;
- store successful `F/CR` and their improvement magnitudes;
- update memories with the standard success-history weighted means.

Tests must cover:

- reproducibility for a fixed RNG state;
- valid sampled ranges;
- memory updates after successful replacements;
- no update when there are no successes.

### 4.4 Linear population-size reduction

Let initial and minimum population sizes be config-driven.

Reduce population size as a deterministic function of consumed global unique-design budget, not generations, because canonical integer duplicates can make generation counts misleading.

When reducing, delete the worst ranked individuals and resize the external archive consistently.

Record population size in the best-so-far trace.

### 4.5 Mixed integer duplicate handling

Because different real vectors can decode to the same integer design:

- canonical cache remains authoritative;
- record raw offspring count, unique decoded count and duplicate count;
- when a trial decodes to the same canonical design as its parent or another already-produced trial, retry mutation/repair up to a bounded number of times;
- after retries, accept without charging a new unique-design evaluation if already cached;
- never fabricate a new result to force the counter forward.

Add duplicate-rate diagnostics by variable group.

---

## 5. Exact continuation and checkpoint/resume

The new `lshade` backend must support real state continuation across budget checkpoints and process restarts.

Checkpoint state must include at least:

- physical/normalized population;
- current rank/metrics for population on active grid;
- external archive;
- `M_F`, `M_CR`, history index;
- current population size;
- exact NumPy RNG bit-generator state;
- consumed unique-design evaluations;
- raw offspring and cache statistics;
- incumbent and best-so-far trace;
- active soft/hard bounds;
- `design_space_version`;
- active frequency grid and `frequency_grid_version`;
- convergence state;
- source/config fingerprint.

Required test:

```text
one uninterrupted run to N evaluations
vs
run to N/2 -> save -> new process/load -> continue to N
```

For the same seed and deterministic evaluator, final optimizer state and result must match within exact/declared deterministic tolerance.

---

## 6. Interaction with adaptive frequency grid

Keep Stage 3.2 adaptive frequency logic.

When critical frequencies are added:

1. evaluate only newly required frequencies for existing candidates;
2. recompute population rank on the new active grid;
3. do not count this as new unique designs;
4. continue the same L-SHADE state;
5. increment `frequency_grid_version`;
6. record the event.

Frequency-grid convergence must never terminate the design optimizer while unique-design budget remains and design convergence is not satisfied.

---

## 7. Bound logic improvements

Preserve Stage 3.2 soft/hard bound logic with these changes.

### 7.1 Integer boundary zone

For integer variables default to one decoded step inside the boundary:

```text
lower pressure zone: x <= lower + 1
upper pressure zone: x >= upper - 1
```

Make step count configurable.

### 7.2 Elite-boundary probe

Add a second diagnostic path in addition to multi-seed boundary pressure.

Trigger an **elite probe**, not direct expansion, when all are true:

- current global best is in the boundary zone;
- the elite is materially better than the seed median or next-best cluster according to configurable threshold;
- hard bound permits expansion.

Probe several points beyond the soft bound around the elite while preserving other variables. One elite seed alone cannot expand the bound.

Expansion requires reproducible improvement from multiple probe evaluations (or configured consensus rule).

### 7.3 On expansion

- never exceed hard bounds;
- never auto-shrink;
- increment `design_space_version`;
- reset convergence plateau evidence;
- preserve incumbent/population physical solutions;
- re-normalize them under new bounds;
- inject a configurable fraction of new samples in the newly opened region;
- clear or explicitly version the external archive so stale old-domain diversity cannot silently dominate the new region;
- document whether `M_F/M_CR` are preserved or reset and test the chosen policy.

Default policy for Stage 3.3: preserve `M_F/M_CR`, clear external archive, inject 20% new-region samples.

---

## 8. Integer refinement and continuous polish

### 8.1 Integer neighborhood

Keep the existing mixed-variable micro-polish/refinement, but expose it as a deterministic post-global step.

- one integer variable at a time, ±1 and ±2 when within hard bounds;
- accept only comparator improvement after common-grid evaluation;
- optional two-variable refinement only after single-variable moves plateau;
- track extra evaluation budget separately from global unique-design budget.

### 8.2 Continuous polish A/B

Implement Powell as an optional continuous-only polish backend.

- integers fixed;
- optimize continuous variables only;
- final active grid for calls;
- strict max function-evaluation budget;
- common-dense validation afterward;
- reject if final comparator rank worsens.

Compare:

- existing local polish;
- Powell polish.

Do not enable Powell as production default until the experiment plan promotion gate is met.

---

## 9. Production process parallelism

Production must use **seed-level process parallelism**, not thread-level DE-internal parallelism.

Use one process per cold seed up to the configured worker count.

Recommended implementation:

```python
ProcessPoolExecutor(
    max_workers=min(config_workers, number_of_seeds),
    mp_context=multiprocessing.get_context('spawn'),
)
```

Requirements:

- parent creates the run manifest and immutable inputs once;
- each seed writes only seed-specific files/subdirectory;
- aggregation/reporting happens only in the parent after workers finish;
- no concurrent writes to one JSONL/JSON file;
- all worker exceptions propagate and are recorded;
- per-worker BLAS/OpenMP thread count is 1;
- serial and parallel runs with the same seeds must produce identical per-seed results (subject to declared deterministic tolerance);
- production report records worker count, wall time, CPU time where available, and per-seed elapsed time.

Do not run algorithms A and B concurrently when benchmarking wall time. Run each algorithm separately with the same process-worker policy so timing comparisons are interpretable.

---

## 10. Codex execution/token-efficiency policy

Long optimization loops must remain entirely inside Python.

Codex should:

1. implement;
2. run the prescribed command once;
3. avoid repeated polling/tailing while the script is running;
4. rely on internal checkpoints/progress files for recovery;
5. after completion, read the final summary/review bundle once.

The production CLI should be able to run implementation validation + experiment + review-bundle generation without conversational supervision.

Add `--resume` support so a failed/terminated production job restarts from saved optimizer checkpoints rather than from zero.

---

## 11. Do not implement in Stage 3.3

- independent center/outer geometry degrees of freedom not currently represented by the physics model;
- the attached MD's `center_outer_same=True/False` geometry switch;
- CMA-ES replacement;
- Bayesian optimization;
- surrogate models;
- GPU/Numba rewrite;
- automatic bound shrinking;
- 20–200 ohm full production sweep before the Stage 3.3 optimizer winner is selected.

---

## 12. Deliverables

Code:

- optimizer backend interface;
- L-SHADE backend;
- comparator/constraint selection module;
- checkpoint/resume state serialization;
- improved bound diagnostics;
- production ProcessPool seed runner;
- optional Powell polish;
- tests.

Reports:

- algorithm A/B CSV/JSON/HTML;
- basin-hit statistics;
- convergence curves;
- duplicate/canonicalization statistics;
- bound events;
- checkpoint-resume parity;
- serial/parallel parity and speedup;
- final review bundle.

Finish only when `STAGE3_3_ACCEPTANCE.md` is satisfied.
