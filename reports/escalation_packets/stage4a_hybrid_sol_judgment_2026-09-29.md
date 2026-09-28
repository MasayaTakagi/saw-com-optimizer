# Stage 4A hybrid protocol — pre-implementation Sol judgment

**Date:** 2026-09-29
**C2C task:** `c2c_0b52`, PLAN iteration 0
**Requested model:** `gpt-6-sol`
**Observed backend identity:** not exposed by the runtime

## Decision requested

Judge only the high-risk Stage 4A contracts before implementation: material
provider reuse for ladder resonators, design-space/topology boundaries, a
matched qualification-only L-SHADE smoke protocol, parity and comparison
conditions, and successful checkpoint disposition. This packet does not seek
authorization for Stage 4B, production optimization, or an impedance sweep.

## Scope and fixed conditions

- Material/provider: current MLIT profile
  `LI2024_42YX_LT_METAL_UNSPECIFIED_T25`.
- DMS: current `T1_SYMMETRIC_5IDT`; source/load: 50/50 Ω.
- Hybrid candidates: exactly `D`, `P_D`, `D_P`, `P_D_P`.
- Preserve current T1 bounds, the existing `RESONATOR_BOUNDS`, metrics,
  objective, specification, grids, geometry constraints, and optimizer.
- Reuse current L-SHADE, unique decoded evaluations, common validation,
  schema-v2 provenance, shared checkpoint lifecycle, and review-bundle APIs.
- Make D-only numerical parity a hard gate before any resonator smoke.
- No Stage 4B, T2 promotion, M0-vs-MLIT comparison, impedance sweep,
  production-budget run, calibration, FEM fitting, or relaxed constraint.

## Relevant implementation facts

- `core.hybrid.resonator_y` already evaluates a one-port resonator through
  `acoustic_admittance` and `validate_admittance` using its supplied provider.
- The legacy `core.hybrid.response` instead decodes the historical seven-DOF
  DMS and constructs `FixedProvider`; it cannot be the current MLIT/T1 path.
- `LiteratureProfileProvider` rejects incomplete profiles and has no fallback.
  The current DMS study builds MLIT through this provider and evaluates T1
  through `simulate_topology`.
- The current T1 vector has 10 DOFs. `P_D_P` therefore has 16 DOFs. L-SHADE's
  default 18 candidates per dimension would initialize 288 candidates, so a
  256-evaluation smoke requires a common fixed initial population smaller than
  the budget.
- Existing resonator defaults include 40 reflector electrodes, zero gap in
  the resonator section sequence, metallization ratio 0.5, and thickness over
  wavelength 0.04; these assumptions must be explicit in Stage 4A evidence.

## Bounded Sol judgment received

**Decision: approve Stage 4A qualification with the gates below.**

1. Use the identical complete MLIT provider for current T1 and
   `resonator_y`. Treat the added resonators as electrically shunted but
   acoustically separate tracks. Explicitly record reflector count 40, gap
   0, metallization ratio 0.5, and thickness over wavelength 0.04. If the
   provider or these existing assumptions fail validation, stop; do not borrow
   M0 parameters or add empirical corrections.
2. Keep the exact four shunt families and unchanged current T1 plus existing
   resonator bounds. Do not add series branches or widen bounds.
3. Use 256 unique decoded evaluations per topology, a fixed initial
   population of 32 for all four topologies, and checkpoints at 128 and 256.
   Require telemetry showing mutation/update and checkpoint continuation; if
   256 fails that qualification check because of duplicate/rejection behavior,
   increase only under a predeclared common budget no larger than 512. Do not
   interpret the smoke as a topology ranking.
4. Use cold independent initialization, no warm/parent transfer, identical
   ports/grids/specification/objective/comparator/counters, geometry-first
   ranking, and fail-closed D-only parity before resonator smoke.
5. Keep successful execution in `REVIEW_WAITING` pending C2C acceptance.

No files were changed and no optimization run was launched during this
judgment.
