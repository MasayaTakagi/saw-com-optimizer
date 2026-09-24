# Escalation Packet — Stage 3.8C-R1.2 Initializer

## Scope

Judgment only before implementation. Review a study-level initializer change
and its pilot gates. Do not implement code. The requested active review target
is GPT-6 Sol (`gpt-6-sol`), per the current project policy.

## Project state

- Baseline branch: `main`.
- Baseline HEAD: `f2babf340f7143e44db6af83f28e2324e724f6ed`.
- Pre-work `git status --short`, tracked diff stat, and cached diff stat are
  preserved in `reports/stage3_8c_r1_2_pre_work_git_state.json`.
- The worktree already contains many unrelated and R1.1/C2C changes. They must
  remain untouched; do not restore, stash, commit, or push them.

## Requested R1.2 behavior

R1.2 should replace R1.1's conditional integer feasible-set initializer on the
study's production/default path with independent proposals followed by
canonicalization and hard geometry rejection/resampling. Invalid designs must
not be clamped, projected, repaired, or conditionally resampled. Keep all
search bounds, aperture ranges, physical constraints, topology, L-SHADE update
rule, evaluation budget, impedance, profiles, comparator, evaluator, and
counter semantics unchanged.

Remove rejection-fraction pass/fail thresholds; retain rejection as a
diagnostic. Mandatory initializer conditions are exact requested population
size, 100% accepted geometry-valid members, no attempt-cap exhaustion,
sufficient uniqueness/diversity, and practical measured runtime. Record
attempts, accepts, rejects, fraction, attempts per accepted member, runtime,
variable quantiles/mean/std, and total electrode/length distributions. Add
distribution validation and, if practical, an initializer-only Monte Carlo
reference. Run only the six-cell pilot: M0/MLIT × T0/T1/T2, seed `20260917`,
256 optimizer evaluations/cell. Stop at review; never start 96k production.

## Current implementation facts to assess

- R1.1's `sample_geometry_valid_population` currently inserts one known fixed
  design, then samples continuous coordinates and conditionally samples integer
  counts from derived feasible ranges. This creates the changed distribution
  R1.2 is intended to remove from the default path.
- Existing `_canonical_physical` maps integer coordinates with
  `floor(x + 0.5)`. The R1.1 independent-uniform reference samples real-valued
  coordinates uniformly over each active interval, canonicalizes them, then
  rejects invalid geometry. Thus integer endpoint values can have different
  probability mass than interior integer values.
- The R1.2 instructions say both “integer/discrete variables uniform over the
  declared discrete domain” and “preserve the original independent-uniform
  proposal distribution” plus the existing canonicalization rule. These can
  imply different discrete probability laws; resolve this explicitly using
  the actual R1-era behavior as the reference unless the specification clearly
  says otherwise.
- R1.1 currently ensures uniqueness by rejecting duplicates and drawing
  another candidate. R1.2 also makes sufficient diversity mandatory, so explain
  the resulting sequential unique-sample law and diagnostics.
- R1/R1.1 reports indicate approximately 7% acceptance for the hardest T2
  cells. For a population near 180, that is about 2,600 raw proposals in
  expectation; the attempt cap must have a generous finite safety margin and
  fail explicitly as `INITIALIZER_EXHAUSTED` if reached.

## Questions for reviewer

1. What exact discrete proposal law best preserves R1 semantics given the
   instruction's wording on uniform integer domains and existing
   `floor(x + 0.5)` canonicalization? Should the fixed known design remain one
   explicit population member, with the remaining slots drawn by rejection?
2. Is direct independent proposal → existing canonicalization → geometry test
   → accept/reject the correct conditional distribution, without any
   topology-dependent sampling order or geometry repair?
3. How should uniqueness rejection be documented so the target proposal law
   and its finite-population effect remain clear?
4. Is a `max_attempts = max(fixed_minimum, multiplier * population_size)` style
   cap appropriate, and what conservative values are defensible at the
   observed ~7% hardest-cell acceptance? Preserve finite termination.
5. Are the stated population, geometry-validity, cap, diversity, and runtime
   gates sufficient without a rejection-fraction gate? Recommend a robust
   uniqueness threshold/diagnostic that does not change the search space.
6. What light-weight Monte Carlo distribution regression (including T0/T1/T2
   integer counts and total electrodes/length) would adequately catch the
   R1.1 order bias without running COM physics?

## Decision boundary

Do not modify COM physics, network, measurement, B28 specification, objective,
filter violations, geometry/manufacturing constraints, topology, L-SHADE,
budget, impedance, material profiles, common grid, comparator, evaluator, or
counters. Do not run production. Pilot performance is diagnostic-only,
`promotion_eligible=false`, `seed_consistency=N/A_single_seed`. Keep GPT-6 Sol as
the active routing target; do not silently fall back to GPT-5.6 Sol. Runtime
backend identity must not be claimed verified unless exposed by the runtime.
