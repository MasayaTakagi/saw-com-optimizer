# Escalation Packet — Stage 3.8C-R1.1 Initializer

## Scope

Select a study-level geometry-aware initial-population sampler for the R1.1
six-cell pilot. Review judgment only; leave implementation to the Luna root
agent. The requested review target was GPT-6 Sol (`gpt-6-sol`).

## Evidence and constraints

- The R1 sampler independently sampled continuous and integer coordinates,
  rounded integer coordinates, decoded the design, then rejected geometry
  violations.
- `LShadeBackend.initialize` already accepts a supplied population. The
  initializer can remain study-specific.
- T0 and T1 use summed serial section lengths and electrode counts. T2 checks
  both parallel track lengths and total device electrodes.
- The geometry limits, active search bounds, material profiles, topology
  definitions, objective, comparator, optimizer, budget, impedance, and common
  validation grid must remain unchanged.
- Do not clamp, project, or narrow bounds. Validate every emitted candidate
  with the existing decoder and geometry evaluator.

## Decision

Keep one `sample_geometry_valid_population(...)` interface and use
topology-specific conditional feasible discrete sets. Draw continuous
wavelength, gap, ratio, and aperture coordinates within their declared
bounds, then sample each integer count from its feasible values after
reserving the minima of counts still to be drawn. The reviewer derived the
electrode and length contributions directly from the current decoders and
recommended that every completed design still pass the existing geometry
evaluator. Fail loudly if those derived constraints disagree with it.

This retains support across feasible count combinations in the declared box,
but it changes the initial-population distribution. Report coordinate
quantiles, geometry margins, and a separate independent-uniform rejection
reference; label pilot performance diagnostic-only.

## Action and verification

The R1.1 initializer implements the recommendation without modifying the
generic L-SHADE backend. Targeted tests passed (14); the full suite passed
(227 tests and 14 subtests). Independent preflight passed topology validation,
fixed-design sanity 6/6, known-seed checks 6/6, and geometry-valid population
checks 6/6. The six-cell Pilot reached `PASS_AWAITING_REVIEW`; details are in
the R1.1 review bundle. The conditional initializer had zero geometry
rejections; the separate independent-uniform reference remained close to R1.
No 96k Production run was started.

A post-pilot gate-only correction preserves the legacy R1 90% initializer-rejection threshold while applying the R1.1 50% threshold; the regression test covers both. The saved Pilot outputs were not rerun or changed.

The request used the `gpt-6-sol` tool model parameter. Runtime-visible backend
identity and internal reasoning effort were not exposed, so those are not
claimed as independently verified.
