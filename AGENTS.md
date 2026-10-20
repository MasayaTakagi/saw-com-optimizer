# SAW COM Filter Optimization Project

## Project objective

Follow [`docs/project_roadmap.md`](docs/project_roadmap.md), revision
2026-10-08, as the authoritative product roadmap. Build a reusable SAW filter
design flow for user-provided COM parameters, frequency-domain specifications,
topology/design variables, geometry or area limits, source/load impedances,
and computing budgets. Report the best-found constrained design and its
feasibility, violations, and convergence limitations; never imply a finite
search proves a global optimum.

The long-term impedance deliverable is a Smith-chart heatmap of validated
performance from **independent filter re-optimization at each sampled source/
load impedance condition**. A fixed-design termination sweep is not a
user-facing substitute. B28 Rx at 50/50 ohm is a regression/diagnostic case.
Physical COM calibration is optional, not a project gate; numerical correctness,
units, COM conventions, modeled-constraint consistency, and reproducibility
remain mandatory. Preserve the roadmap's staged gates and do not infer that
infeasibility proves mathematical impossibility.

---

# Working principles

Work autonomously and complete the requested task without unnecessary
clarification.

When information is unspecified, choose a reasonable engineering
assumption, clearly document it, and continue.

Prefer producing a working numerical implementation over extended
discussion.

Make the smallest coherent change that fully solves the current task.

Do not refactor unrelated code.

Do not add speculative features unless they are necessary for the
requested objective.

## Execution and review-artifact conventions

The official development environment is WSL2 Ubuntu 24.04, VS Code Remote
WSL, Codex CLI inside Linux, and uv. Keep repositories/worktrees under
`/home/...` on the Linux filesystem and keep Windows and WSL `.codex` state
separate. Windows Codex Desktop WSL Agent is not part of this environment.
Use Ubuntu system Python 3.12 (`/usr/bin/python3.12`), not uv-managed Python.
From each new worktree root run `uv sync --locked --extra test`; use
`uv run --locked` for project commands and `uv run --locked pytest` for tests.
Track `.python-version` and `uv.lock`; never track `.venv`. Do not install Node.
See [`docs/guides/development_environment.md`](docs/guides/development_environment.md).

For new production studies, canonical lightweight GitHub review evidence lives
under `reports/experiment_reviews/<stage>/<run_id>/`. Large raw runs,
checkpoints, populations, dense arrays, and full logs belong in an external
persistent run root outside every Git worktree. The authoritative overview is
[`docs/guides/data_storage_logging_review_policy.md`](docs/guides/data_storage_logging_review_policy.md).

`artifacts/review_bundles/` and `sawopt.reporting.review_bundle` are retained for
historical/ad-hoc saved-run packaging only; they are not the canonical new
production review path.

## C2C status — frozen historical reference

C2C is frozen and is not a project, experiment, or review dependency. Do not
invoke its runtime, Doctor, queue, workspace tools, session/record/checkpoint
operations, or connector for ordinary SAW work. No C2C PLAN or ACCEPT gate is
required for roadmap progress. Keep its source external and preserve its
reviewed baseline, security records, and historical review provenance. The
qualification and explicit reactivation conditions are recorded in
[`docs/c2c/FROZEN.md`](docs/c2c/FROZEN.md); the other files under `docs/c2c/`
are historical references and are not operating instructions while frozen.

Reactivation requires a separate explicit user decision and a fresh
qualification. Do not use a SAW production experiment to qualify C2C.

## Review governance

Use one owner for each review responsibility:

- **PLAN — ChatGPT / user:** set the task or experiment plan and decide when its scope is ready.
- **IMPLEMENT / self-validation — Codex:** make the requested changes and run relevant local validation.
- **EXTERNAL REVIEW — ChatGPT through GitHub:** review the pushed branch, commit, PR diff, and committed evidence; request focused corrections when needed.
- **ACCEPT / MERGE — ChatGPT / user:** decide whether reviewed work is accepted and may be merged or used for the next stage.
- **JUDGMENT — Sol:** provide bounded high-risk judgment only when the escalation criteria below apply; this does not replace external review or user acceptance.

For meaningful work units, commit and push a review branch, then report its
branch, commit SHA, and PR or commit URL. Codex self-validation is not an
independent review. For production experiments, make the implementation,
configuration, preflight, budget, seed, checkpoint policy, external output path,
and review spec available through GitHub before launch. Production execution
still requires separate user authorization. Keep routine, fully specified
documentation, tests, formatting, and simple refactoring within Codex without
Sol escalation.

For long-running production runs, immediately verify the immutable
`run_manifest.json` against the authorized continuation/storage/review contract
after launch. After completion, publish the canonical lightweight evidence and
stop at `REVIEW_WAITING` for independent GitHub review. A completion
continuation must not start another production run; user authorization is
required. See
[`docs/guides/github_review_workflow.md`](docs/guides/github_review_workflow.md).

## Long-running production run policy

- Treat any program expected to run for 30 minutes or longer as a long-running
  production run. If duration is uncertain, use this policy conservatively.
- Do not run a long production optimization synchronously from the Codex shell.
- Use `python -m sawopt.orchestration.cli launch` through the qualified Codex
  orchestration workflow for production runs; do not make routine user-side
  PowerShell launch the operating standard.
- New production continuation uses queue-native exact-thread routing. Capture
  the exact `CODEX_THREAD_ID` before detach and freeze it as
  `original_thread_id` in the manifest. Session IDs are not queue targets.
- New production must not select legacy `codex exec resume` / `legacy_resume`
  routing. Legacy metadata remains readable only for historical recovery.
- New user-authorized or ranking-eligible production must use an absolute
  external persistent `--run-root` or `--run-dir` outside every Git worktree and
  record `run_storage_policy: external_persistent_v1`.
- A missing/malformed/unreconciled active-run registry or invalid external run
  path blocks production before run creation; never fall back to repository
  `runs/`.
- After launch, verify the immutable manifest records the exact production
  source SHA, config/protocol identity, external output path, queue continuation
  identity, and frozen review destination/spec.
- Once the launcher reports a detached worker, do not poll `stdout.log` or wait
  for optimizer completion in the foreground.
- Optimizer checkpoint recovery and post-run thread continuation are distinct;
  do not substitute a new production run when an existing run can be recovered.
- The post-run publisher may export/hash/commit/push evidence but must not
  declare scientific acceptance, merge the PR, promote the baseline, or launch
  follow-up production without later explicit authorization.
- Short unit tests, smoke tests, and small validation runs may remain synchronous.

## Persistent run storage and worktree safety

- The canonical storage/logging/review split is defined in
  [`docs/guides/data_storage_logging_review_policy.md`](docs/guides/data_storage_logging_review_policy.md).
- Tracked source worktrees are disposable source checkouts, not durable raw-run
  storage.
- Production raw runs, checkpoints, optimizer populations, run-local
  continuation ledgers, recovery logs, full process logs, and scientific raw
  artifacts must be durably owned by the external persistent run root.
- Lightweight GitHub review packages remain under
  `reports/experiment_reviews/<stage>/<run_id>/` and are governed by
  [`docs/guides/postrun_review_contract.md`](docs/guides/postrun_review_contract.md).
- Before removing any worktree, run `python scripts/worktree_safety.py audit
  <absolute-worktree-path>` and use its `remove` mode for the re-audited
  operation. Direct `git worktree remove` is not the standard cleanup path.
  Git status cleanliness does not prove removability; ignored and untracked
  files block deletion by default. Do not use `git clean` as a cleanup
  shortcut. Incomplete or inaccessible inventories fail closed.
- Do not delete production raw data merely because the optimizer completed or a
  PR merged. Keep it through publication, external review, and closeout; later
  archive/deletion requires a separate explicit lifecycle decision.

## Sol Escalation Policy

You are the Luna root implementation agent.

Perform routine implementation, tests, experiment execution, logging,
reporting, and clearly specified changes yourself.

Active Pi Sol review target (pinned 2026-10-20):
`openai/gpt-6.1-sol` with Pi thinking level `medium`.
In current Pi, the `openai` provider supports ChatGPT OAuth;
`openai-codex` is the legacy provider. Specify **both** model and
thinking in each Pi `agent_spawn` request; inspect the actual child
session record and fail closed on provider/model/thinking mismatch.
Do not assume the extension's model lookup enforces exact provider identity.
The earlier `openai-codex/gpt-6.1-sol` configuration was superseded.
See [Pi Sol review routing](docs/guides/pi_sol_review_routing.md) for evidence
and remaining credential-verification limits.

Use GPT-6.1 Sol only for bounded high-risk judgment tasks.

You MUST escalate before changing:

- optimizer algorithms
- objective functions
- penalties or constraints
- search-space definitions
- convergence or early-stopping logic
- evaluation budgets when comparison fairness may change
- COM/physics calculations
- experiment conditions affecting comparison validity
- architectural interfaces
- behavior that could invalidate previous experiment results

You MUST also escalate when:

- current results materially contradict previous results
- there are multiple reasonable interpretations of the specification
- root cause is unclear and a design change is being considered
- two repair attempts for the same issue have failed
- a long-running experiment would need to be repeated because of a proposed change

Do NOT escalate routine implementation, tests, logging, plotting, documentation,
formatting, simple refactoring, or changes whose behavior is fully specified.

When escalating:

1. Create a self-contained Escalation Packet.
2. In a Pi session, use the qualified `agent_spawn` extension with explicit
   `model="openai/gpt-6.1-sol"` and `thinking="medium"`. For
   Codex-specific escalation, prefer `fork_context=false` only if supported;
   it is **not** a Pi `agent_spawn` parameter.
3. Restrict child tools to the least privilege the review requires and permit
   no fallback. Do not pass unsupported `run_in_background` to `agent_spawn`.
4. Use one Sol agent at a time.
5. Ask Sol for judgment/review, not full implementation.
6. Inspect the child session record and distinguish requested routing from
   observed provider/model/thinking metadata; a successful textual response
   is insufficient to assert all three were verified.
7. Resume implementation only after a recorded review decision and applicable
   project gates; log routing, evidence, judgment, and outcome in
   `reports/escalation_log.md`.

Never claim that the backend model identity or actual internal reasoning effort
was verified unless the runtime explicitly exposes that information.

---

# Token and context efficiency

Keep repository investigation focused on files directly relevant to the
current task.

Prefer targeted file searches over broad repository scans.

Do not recursively inspect the entire repository unless necessary.

Do not repeatedly read files that have already been inspected unless:

- the file changed,
- a specific unresolved issue requires rereading,
- or exact implementation details must be verified.

Batch related searches and file reads when possible.

Reuse information already established in:

- this AGENTS.md,
- existing documentation,
- source code already inspected,
- previous conversation context.

Do not repeat extensive explanations already established.

Avoid generating long progress reports.

During implementation, communicate only significant findings,
decisions, failures, or changes in direction.

---

# Reasoning policy

Assume the default reasoning level is LOW.

LOW reasoning should be sufficient for:

- creating files,
- implementing known equations,
- routine numerical code,
- plotting,
- parameter handling,
- ordinary unit tests,
- fixing straightforward bugs,
- small refactors.

Use deeper reasoning only when necessary for:

- deriving or validating COM equations,
- deciding model architecture,
- diagnosing unexplained numerical behavior,
- optimization strategy design,
- convergence failures,
- physically inconsistent results,
- difficult multi-module bugs.

Do not spend extended reasoning on formatting, naming, boilerplate, or
simple implementation work.

---

# Physical model

Use a modular COM-theory-based model.

Initially use representative placeholder COM parameters rather than
material-specific production parameters.

The architecture must make it easy to replace placeholder values with
measured, FEM-derived, or literature-derived COM parameters later.

Typical COM quantities may include:

- propagation constant
- acoustic attenuation
- reflection coefficient
- electromechanical transduction coefficient
- static capacitance
- acoustic velocity
- electrode pitch
- aperture
- number of electrode pairs
- reflector parameters

Keep physical quantities and units explicit.

Use SI units internally whenever practical.

Document every placeholder physical parameter.

Do not silently introduce empirical correction factors.

---

# Filter structure

Start with a representative discrete SAW filter topology suitable for
demonstrating impedance-dependent optimization.

The software architecture must not hard-code the solver to only one
topology.

Separate:

1. COM element model
2. resonator / IDT representation
3. acoustic/electrical network composition
4. filter topology
5. port termination
6. optimization
7. specification evaluation

The model should eventually allow alternative SAW structures to be
implemented without rewriting the core solver.

---

# Port impedance study

Source and load impedances are user-specified inputs, not the sole or primary
independent variable of the design tool. Constrained optimization for a single
specified Zs/Zl pair is a first-class workflow.

The historical real-impedance prototype may sweep 20–200 ohm and, when explicitly
configured, use Zs = Zl = Zport. Neither this range nor equal terminations are
universal design requirements. Keep Zs and Zl independently configurable.

The roadmap's Smith-chart workflow will allow complex passive Zs/Zl only after
Stage 5C establishes the required numerical, power, and reference conventions;
the current real-port evaluator must not be represented as complex-capable.

For every sampled source/load impedance pair in an impedance-sensitivity map:
1. Independently optimize the filter design for that pair under the declared
   COM inputs, specification, topology, geometry constraints, and budget.
2. Validate the best-found design on the declared validation grid.
3. Record the geometry, feasibility, constraint violations, performance,
   evaluation budget, and convergence limitations.

A fixed-design termination sweep is valid for internal diagnostics, not as the
user-facing re-optimized impedance map. Do not call a finite-budget solution a
proven optimum.

---

# Initial RF target

For the B28 Rx regression/diagnostic case, use a representative LTE
Band 28 receive-band filter target.

Use approximately the following passband:

758 MHz to 803 MHz

Treat these initial values as engineering targets rather than a
production-qualified specification.

The specification model should be configurable rather than hard-coded.

Initial evaluation metrics should include:

- maximum passband insertion loss
- average passband insertion loss
- passband ripple
- minimum return loss
- lower stopband attenuation
- upper stopband attenuation
- transition behavior
- optional group-delay ripple

Use the explicitly declared feasibility-first objective and candidate ranking
for the active study, consistent with the project roadmap and study
configuration. Do not silently substitute a weighted penalty that changes the
feasibility or ranking semantics. Retain individual metrics for comparison and
later Pareto analysis.

---

# Design variables

Use plausible dimensions for a compact discrete SAW filter.

Initial variables may include:

- IDT electrode pair counts
- reflector electrode counts
- electrode pitch
- aperture
- section lengths
- resonator frequency offsets
- coupling-related COM parameters where appropriate
- static-capacitance scaling
- topology-specific coupling variables

Do not optimize physically meaningless combinations.

Use explicit lower and upper bounds.

Put all bounds in a configuration file or parameter structure.

Avoid embedding bounds directly inside optimization code.

---

# Optimization strategy

A single filter design is a constrained optimization problem with explicit
COM inputs, frequency-domain specifications, topology/design variables,
bounds and area/geometry constraints, independent source/load terminations,
and a finite computing budget. Respect the study's declared feasibility-first
ranking and report best-found performance, violations, and uncertainty.

When an impedance map is requested, add an outer sampling loop over declared
Zs/Zl pairs, with an independent inner design optimization at each pair.
Initial coarse sampling, adaptive refinement, and parallel workers may reduce
cost but must preserve the re-optimization and validation contract. For
Smith-chart slices, name the fixed and varied port and distinguish evaluated,
interpolated, infeasible, and incomplete points.

Do not treat a 20–200 ohm real-port sweep as the tool's required outer loop;
it is an optional historical diagnostic. Complex-port studies require the
separate numerical qualification in Stage 5C. Follow the stage gates and
obtain explicit approval before large production runs or changed budgets,
bounds, constraints, or optimizer behavior.

---

# Optimization algorithms

Design the optimizer interface so algorithms can be swapped.

A reasonable initial strategy is:

Stage 1:
global or multi-start search

Stage 2:
local refinement

Possible algorithms include:

- differential evolution
- CMA-ES
- multistart local optimization
- scipy.optimize methods

Do not add multiple optimization libraries unless required.

Prefer scipy-based implementation initially if it is adequate.

Make stochastic optimizations reproducible using explicit random seeds.

---

# Numerical architecture

Prefer Python.

The current implementation lives under `src/sawopt/`. See
[`docs/architecture_overview.md`](docs/architecture_overview.md) for its
current layers and ownership boundaries.

Keep COM physics separate from optimization code.

The COM solver must be usable independently from the optimizer.

---

# Interfaces

Prefer structured dataclasses or equivalent typed configuration objects
for:

- COM parameters
- geometry
- frequency grid
- filter specification
- optimization settings
- port impedance
- simulation results

Avoid passing large unstructured dictionaries through the numerical
core unless there is a strong reason.

Use type hints.

---

# Output data

For every optimized impedance point, save at minimum:

- port impedance
- optimized geometry / parameters
- objective value
- passband insertion loss
- ripple
- return loss
- stopband metrics
- optimizer success/failure status
- number of objective evaluations
- random seed
- runtime metadata if useful

Use a machine-readable format such as CSV plus JSON.

Do not make plots the sole output.

---

# Plots

Provide plots useful for engineering comparison.

At minimum:

1. S21 versus frequency for selected optimized impedances
2. S11 versus frequency
3. best objective versus port impedance
4. passband insertion loss versus port impedance
5. passband ripple versus port impedance
6. return loss versus port impedance

Do not generate excessive plots during optimization.

Generate summary plots after the sweep.

---

# Testing

Run tests appropriate to the changed code.

Prioritize tests for:

- dimensions and matrix shapes
- network cascading
- impedance termination
- S-parameter conversion
- limiting cases
- numerical stability
- objective-function behavior

Use physically meaningful sanity checks where possible.

Examples:

- passive networks should not exhibit unexplained gain
- symmetric structures should produce expected symmetry
- zero coupling should reduce to the appropriate limiting behavior
- changing reference impedance should behave consistently
- repeated calculation with identical inputs should be deterministic

Do not create tests that simply reproduce implementation details.

For small localized changes, run targeted tests first.

Do not run the entire test suite repeatedly without reason.

Once the relevant tests pass, stop testing unless:

- shared numerical infrastructure changed,
- a failure occurred,
- or an unresolved concern remains.

---

# Numerical safety

Watch for:

- singular matrices
- exponential overflow
- extreme acoustic propagation factors
- ill-conditioned transfer matrices
- invalid logarithms
- divide-by-zero
- NaN propagation

Prefer numerically stable network formulations.

If conventional transfer matrices become unstable for long structures,
consider scattering or chain-scattering representations.

Do not hide numerical failures by clipping arbitrary values unless the
physical reason is documented.

---

# Validation

Before trusting optimization results, validate the implementation in
progressively harder stages:

1. simple analytical limiting cases
2. single COM section
3. simple resonator / IDT
4. small cascaded network
5. complete filter
6. optimization
7. impedance sweep

Do not begin interpreting the optimum impedance until the underlying
solver passes basic physical sanity checks.

---

# Performance

Avoid premature optimization.

Vectorize frequency calculations where practical.

Cache quantities that do not change during an optimization iteration.

Do not repeatedly reconstruct invariant objects inside the objective
function.

Parallelize primarily across independent impedance points or optimizer
starts rather than adding unnecessary complexity inside the COM solver.

Measure bottlenecks before introducing advanced acceleration.

---

# Documentation

For equations, document:

- definition
- units
- sign convention
- source/assumption
- relationship to the implemented matrix

Pay particular attention to COM sign conventions because literature
conventions differ.

Keep derivation notes separate from routine source-code comments when
they become lengthy.

---

# Final response style

Keep Codex final responses concise.

Report:

- what was implemented
- important assumptions
- files changed
- tests run and whether they passed
- important numerical or physical issues
- recommended next step

Do not restate the entire task.

Do not include long explanations unless explicitly requested.