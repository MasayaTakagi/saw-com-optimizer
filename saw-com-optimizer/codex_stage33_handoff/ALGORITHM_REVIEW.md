# Stage 3.3 Algorithm Proposal Review

## Decision

The attached `SAW_structure_optimization_algorithm.md` is directionally sound, but it must **not** be implemented literally. Stage 3.3 adopts the optimizer improvements that are compatible with the current model and explicitly defers the geometry-parameterization proposal that conflicts with current code semantics.

## Adopt now

1. L-SHADE / SHADE-family adaptive DE as an A/B candidate against the current DE engine.
2. Feasibility-first selection implemented as a comparator, not as a tunable penalty weight.
3. Integer-neighborhood refinement after global search.
4. Continuous-only local polish after integer refinement, with Powell tested against the existing local polish.
5. Existing adaptive/dense frequency validation retained and used identically across algorithms.
6. Exact optimizer-state checkpoint/resume for the new optimizer backend.
7. Production seed-level process parallelism.
8. Existing automatic soft-bound expansion retained and improved.

## Important correction: `center_outer_same`

In the current COM code, `center_outer_same` is a **DMS electrical wiring mode**, not a boolean that ties or unties center/outer geometry variables. Therefore the proposed two-phase sequence

```
center_outer_same=True  -> reduced DOF
center_outer_same=False -> full DOF
```

must not be implemented under those names or semantics.

The current `FilterDesign` also does not yet expose a full set of independent center/outer wavelength/aperture/gap variables. Creating such variables without a corresponding COM/provider/layout interpretation would expand the physical model, not merely the optimizer.

### Stage 3.3 rule

- Treat `wiring` and `geometry parameterization` as independent concepts.
- Keep the current physical design parameterization unchanged for the optimizer A/B study.
- Reserve a future explicit interface such as `geometry_mode=current_7d|reduced|full` for a later stage, only after the COM/provider/layout model supports the added degrees of freedom.

## Feasibility-first: refine the proposal

Do not use a weighted sum of violations as the primary constrained-selection rule. Use the existing normalized violations and a deterministic lexicographic comparison:

```
if one candidate is feasible:
    feasible candidate wins
elif both are infeasible:
    lower max_violation wins
    then lower sum_violation
    then lower worst_passband_il
else:  # both feasible
    lower worst_passband_il wins
    then lower ripple / secondary metrics as configured
```

This removes penalty-weight tuning from evolutionary selection. A scalar objective may still be emitted for logging/backward compatibility but must not determine L-SHADE selection or p-best ordering.

## L-SHADE implementation requirements

Implement the new engine from the published SHADE/L-SHADE algorithm, including:

- current-to-pbest/1/bin mutation;
- external archive;
- memories `M_F`, `M_CR` initialized to 0.5;
- success-history updates using improvement-weighted successful parameters;
- `F` sampled from a Cauchy distribution around memory, resampling non-positive values and clipping above 1;
- `CR` sampled normally around memory and clipped to [0,1];
- p-best selection from the best fraction of the population;
- linear population-size reduction as a function of consumed unique-design budget;
- exact RNG state in checkpoints.

Run in normalized coordinates so variables with very different physical scales do not distort mutation distances. Decode/repair to the canonical mixed integer/continuous design only at evaluation boundaries.

## Mixed integer handling

L-SHADE is fundamentally a real-valued optimizer. For this project:

- store search vectors in normalized continuous coordinates;
- canonicalize integer variables at evaluation;
- cache using canonical decoded designs;
- detect duplicate decoded offspring and allow bounded resampling/repair so evaluations are not wasted on plateaus;
- keep the existing integer-neighborhood final refinement;
- do not claim that standard L-SHADE alone solves the mixed-integer problem.

## Continuous polish

Powell is a candidate final polish, not a replacement for global search.

- Fix all integer variables first.
- Optimize only continuous variables.
- Use the final active frequency grid during local calls.
- Always common-dense validate the polished candidate.
- Reject the polish if the final rank is worse.
- A/B Powell versus the current local polish before making Powell the production default.

SLSQP is not a Stage 3.3 default because the merit function is non-smooth (max/min metrics and active constraint changes) and robust derivatives are unavailable.

## Frequency-grid proposal

The attached document's coarse -> medium -> dense idea is conceptually correct, but the current project already has a more advanced adaptive-frequency mechanism. Do not replace it with a simpler staged grid.

Keep:

- incremental frequency evaluation;
- critical-frequency exchange;
- common-dense validation;
- separate frequency-grid convergence and design-optimizer convergence;
- population reevaluation when the active grid changes without counting it as a new unique design.

## Bound logic improvements carried into Stage 3.3

From Stage 3.2 review:

1. For integer variables, define the boundary zone in integer steps. Default lower-zone rule: `x <= lower + 1` and upper-zone rule: `x >= upper - 1`.
2. Keep the existing multi-seed boundary-pressure route.
3. Add an elite-boundary-probe route: if the global best is on the boundary and materially better than the rest, probe beyond the soft bound even if the multi-seed pressure threshold is not met. One seed can trigger a probe, but cannot directly trigger expansion.
4. Expand only after multiple probe points demonstrate improvement and hard bounds allow it.
5. Auto-expand soft bounds only; never auto-shrink.
6. Increment `design_space_version` on expansion and reset convergence-plateau evidence.

## Why L-SHADE is worth testing now

Stage 3.2 showed a low basin-hit rate for `center_outer_same`: one seed reached a much better region while the median remained substantially worse, and one trajectory improved very late. This is exactly the situation where adaptive control parameters, p-best guidance, archive-based diversity and population-size scheduling may improve evaluation efficiency. It is not proof that L-SHADE will win, so Stage 3.3 is an A/B validation rather than an unconditional replacement.
