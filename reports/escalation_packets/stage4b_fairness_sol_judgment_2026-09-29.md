# Stage 4B fairness and budget — pre-implementation Sol judgment

**Date:** 2026-09-29
**C2C task:** `c2c_a4f9`, PLAN iteration 0/1
**Requested model:** `gpt-6-sol`
**Scope:** bounded scientific fairness and lifecycle judgment; no implementation

## Decision requested

Judge whether the proposed Stage 4B primary and dimension-normalized comparison
tiers are scientifically defensible and implementable with the current L-SHADE
checkpoint contract. This packet does not seek authorization to launch any
Stage 4B production optimization.

## Fixed scientific conditions

- Material/provider: MLIT, current profile and provider.
- DMS: `T1_SYMMETRIC_5IDT`, with current Stage 3.9 bounds and semantics.
- Ports: `Zs = Zl = 50 Ω`; current specification, objective, search grid,
  common 9,113-point validation grid, geometry-first comparator, and metrics.
- Topologies: exactly `D`, `P_D`, `D_P`, `P_D_P`; dimensions 10/13/13/16.
- Seeds: `20260917` and `20260918`; all cells cold-start and independent.
- Initializer: independent uniform rejection and deterministic integer
  canonicalization, common policy across topologies. Record attempts,
  geometry/duplicate rejections, accepted population, feasible-volume
  diagnostics, integer distributions, and per-coordinate coverage. Do not
  force equal raw acceptance rates.
- Each Stage 4B `D` control is newly run under this same contract; do not
  substitute Stage 3.9 persisted candidates or trajectories.

## Budget interpretations

### Option A — equal-resource primary screen (preferred)

Run exactly 4,000 unique decoded evaluations per topology/seed:

```text
4 topologies × 2 seeds × 4,000 = 32,000 unique evaluations
```

Use the Stage 3.8/3.9 dimension-scaled initializer policy of 18 initial
members per degree of freedom, producing populations 180/234/234/288.
Persist the common primary endpoints at B2000 and B4000. This gives every
topology/seed the same primary unique-evaluation budget while documenting that
the initial populations and feasible design-space volumes differ.

### Option B — dimension-normalized screen

Use 400 unique evaluations per degree of freedom:

```text
D       10D → 4,000
P_D     13D → 5,200
D_P     13D → 5,200
P_D_P   16D → 6,400
```

Across two seeds this is 41,600 unique evaluations. It normalizes the
evaluation count by dimension but does not provide an equal-resource endpoint.

### Proposed two-tier contract for judgment

Keep Option A as the primary matched-budget comparison. Keep the B4000 result
for every cell as a first-class artifact. Treat later B5200/B6400 results as a
separate dimension-normalized sensitivity stratum, never as direct replacements
for a topology's B4000 primary result.

The C2C PLAN proposes a structural, deterministic extension rule:

```text
dimension_normalized_target(d) = max(4000, 400 × d)
extend whenever d > 10, for both seeds of that topology
```

This intentionally gives every 13D and 16D family the normalized continuation,
regardless of its B4000 performance. It avoids choosing rescue recipients
after observing objective, feasibility, seed agreement, comparator position,
convergence, or active-bound results. It increases the two-tier total from
32,000 to 41,600 evaluations. The user's original proposed rescue wording was
conditional on competitiveness or evidence of continued improvement; judge
whether the unconditional structural tier is the safer interpretation or
whether a different **predeclared and reproducible** conditional rule is
defensible without post-result selection bias.

The proposed L-SHADE rule keeps
`population_schedule_terminal_budget = 4000` for every cell while setting its
hard maximum to the topology's normalized target. Higher-dimensional cells
would save the exact B4000 state and, when extended, continue that same stream
to B5200/B6400. The primary B4000 trajectory must not be reconfigured after it
is observed. Please assess whether the existing backend supports this exact
continuation with its schedule horizon fixed at B4000; if not, recommend
BLOCKED or a revised plan before any implementation rather than silently
changing the optimizer schedule.

## Judgment questions

1. Is 4,000 unique evaluations per topology/seed the correct primary matched
   screen, with 41,600 as a separately reported dimension-normalized tier?
2. Is unconditional structural continuation of every 13D/16D family the right
   fairness policy, or should rescue be conditional? If conditional, give an
   exact criterion that uses only predeclared reproducible evidence and does
   not trigger because a candidate performs poorly. State the resulting total
   budget formula.
3. Is 18 × dimension an appropriate initial population policy for 10/13/13/16D
   under the equal-budget primary tier, given the differing initialization
   evaluation fraction and feasible-volume rejection rates?
4. Can a B4000 L-SHADE trajectory with a fixed schedule horizon of 4,000 be
   resumed exactly to B5200/B6400 under the existing checkpoint/state
   compatibility rules? What focused evidence is required?
5. Are B4000 and the dimension-normalized endpoints sufficiently separated to
   prevent unequal-budget results being presented as equal-resource rankings?
   With two seeds, should conclusions be limited to screening rather than a
   definitive topology ranking?
6. Does the proposed explicit lifecycle contract correctly retain runtime
   recovery state as `REVIEW_WAITING` until later review/closeout, including
   through detached orchestration callbacks?

## Constraints

- Do not change current T1/MLIT physics, bounds, constraints, objective, or
  validation semantics to improve outcomes.
- No T2, M0 comparison, impedance sweep, model calibration, production callback
  redesign, or unrelated optimizer change.
- No Stage 4B execution in this task, even if the protocol is approved.
- Stage 4A was accepted and locally committed at
  `eeda835f4341b664ac43564358a327000d455dd0`; its computation fingerprint is
  unchanged. Work proceeds on a separate Stage 4B qualification branch.

## Expected response

Return one of `APPROVE_AS_STATED`, `CHANGE_AND_RETURN_TO_C2C`, or `BLOCKED`,
followed by the exact primary budget, rescue formula/trigger, L-SHADE schedule
and checkpoint rule, population policy, interpretation limits, and any
implementation blockers. This is judgment only; do not implement.

## Judgment received — 2026-09-29

**Decision: APPROVE_AS_STATED**, subject to a pre-launch lifecycle fix and
checkpoint parity evidence.

- Primary: 4,000 unique decoded evaluations per topology and seed (32,000).
- Deterministic continuation for every dimension greater than 10, regardless
  of observed outcomes, to `max(4,000, 400 × d)`: 4,000 / 5,200 / 5,200 / 6,400
  for D / P_D / D_P / P_D_P. Report this separately as the normalized
  sensitivity stratum (41,600 total across two seeds).
- Initialize with `18 × d` members and retain initializer/feasible-volume
  diagnostics; do not force equal raw acceptance rates.
- Set each cell's final hard maximum before its cold start. Keep the
  L-SHADE schedule horizon at 4,000, persist the exact B4000 artifact, and
  continue the same backend/RNG stream. A checkpoint created with a 4,000 hard
  cap must not be loaded under a changed cap/configuration.
- Demonstrate split-versus-uninterrupted parity at B4000 and at each final
  target, including exact evaluation counts. Continuation uses minimum
  population four; two seeds support screening, not definitive ranking.
- Before any launch, correct and test the detached worker/direct CLI lifecycle
  so explicit `REVIEW_WAITING` is preserved and recovery checkpoints are not
  finalized while review remains pending.

Sol approved the unconditional structural continuation rule as the
predeclared fairness policy; it supersedes the outcome-conditional rescue
wording considered in this packet. Judgment only; it does not authorize a
Stage 4B production run. Backend model identity and actual reasoning effort
were not independently exposed.
