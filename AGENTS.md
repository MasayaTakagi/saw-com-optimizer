```markdown
# SAW COM Filter Optimization Project

## Project objective

Build a computational tool based on Coupling-of-Modes (COM) theory for
SAW filter analysis and optimization.

The main objective is to investigate how the optimum achievable filter
performance changes as the real-valued input/output port impedance is
varied.

For each candidate impedance, the SAW filter itself must be re-optimized.

The initial impedance sweep range is:

20 ohm <= Zport <= 200 ohm

Do not simply renormalize one fixed filter design to different
impedances. Each impedance point represents a separate optimization
problem.

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

Use the project virtual environment by default. From the
`saw-com-optimizer` directory, the Windows interpreter is
`.venv\Scripts\python.exe`; do not silently fall back to a system or bundled
Python runtime. Create the environment with `py -3 -m venv .venv` when it is
missing, then install the project with `.venv\Scripts\python.exe -m pip
install -e .`.

Review bundles are external artifacts and must always be written to this
repository root's `artifacts/review_bundles/` directory. Do not place review
bundles under `runs/`.

## C2C development control plane

When C2C is available for a project task, use it as the standard planning and
review control plane: ChatGPT plans and reviews; Codex executes. Use only the
`Codex with ChatGPT · saw-com-optimizer` connector bound to the
`saw-com-optimizer` workspace, and verify the C2C doctor gate and workspace
identity before INIT. Keep C2C source in its external
sibling repository; do not vendor it or update it automatically. The reviewed
baseline and operating policy are documented under [`docs/c2c/`](docs/c2c/README.md).

## Long-running production run policy

- Treat any program expected to run for 30 minutes or longer as a long-running
  production run. If duration is uncertain, use this policy conservatively.
- Do not run a long production optimization synchronously from the Codex shell.
- Use `python -m sawopt.orchestration.cli launch` for production runs.
- Long-running launches must capture a Codex session for completion callback and
  reattachment. Do not pass `--no-callback` unless the user explicitly requests
  callback suppression for that specific run.
- Prefer an explicit valid `--session-id` or `--session-file` when launching.
  After launch, verify `run_manifest.json` before considering the launch valid:
  `codex_session_id` must be non-null, `callback_enabled` must be true, and
  `review_after_completion` must be true. If any check fails, stop and repair
  the launch configuration before relying on the run.
- If no valid Codex session can be captured, do not start the long-running
  program silently; report the blocker and request a session or explicit user
  instruction to run without automatic callback.
- Once the launcher reports a detached worker, do not poll `stdout.log` or wait for optimizer completion.
- The worker stores state and invokes the callback against the explicitly captured Codex session.
- Use the orchestration `--resume` path for reattachment or recovery. Do not
  substitute a new production run when an existing detached run can be resumed.
- Callback review must not automatically start another production run; user approval is required.
- Short unit tests, smoke tests, and small validation runs may remain synchronous.

## Sol Escalation Policy

You are the Luna root implementation agent.

Perform routine implementation, tests, experiment execution, logging,
reporting, and clearly specified changes yourself.

Active Sol review target: `gpt-6-sol`.

Use GPT-6 Sol only for bounded high-risk judgment tasks.

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
2. Prefer `fork_context=false`.
3. Explicitly request `gpt-6-sol`.
4. Use one Sol agent at a time.
5. Ask Sol for judgment/review, not full implementation.
6. Resume implementation yourself after receiving the decision.
7. Record the escalation and outcome in `reports/escalation_log.md`.

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

The primary independent variable is real port impedance.

Initial range:

Zport = 20 to 200 ohm

An explicitly configured initial one-dimensional study may use equal
source and load impedances:

Zs = Zl = Zport

Keep source and load impedances independently configurable. Do not assume
they are equal unless the study configuration says so; final impedance
comparisons must preserve independent control and re-optimize the filter
for each impedance pair.

For every impedance value:

1. Set the source and load impedance.
2. Optimize the SAW design variables for that impedance.
3. Calculate the resulting filter response.
4. Evaluate the specification metrics.
5. Store the optimum design and metrics.
6. Compare the optimum achievable result against other impedances.

Never compare port impedances using only a fixed geometry.

---

# Initial RF target

Use a representative LTE Band 28 receive-band filter target.

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

Where a single optimization objective is required, construct a weighted
penalty function from these metrics.

Prefer retaining the individual metrics as well so that results can be
compared using Pareto analysis later.

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

Separate the optimization into two levels.

Outer loop:

port impedance sweep

Inner loop:

SAW filter optimization for the selected impedance

Conceptually:

for Zport in impedance_grid:

    optimum_design = optimize_filter(
        port_impedance=Zport
    )

    evaluate optimum_design

    store results

The outer impedance sweep should be parallelizable.

Start with a coarse impedance grid and allow refinement near promising
regions.

Example initial grid:

20, 30, 40, ..., 200 ohm

Later allow interpolation/refinement such as 1-5 ohm spacing around the
best region.

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
```
