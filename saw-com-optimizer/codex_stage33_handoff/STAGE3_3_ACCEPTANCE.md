# Stage 3.3 Acceptance Criteria

Stage 3.3 is complete only when all applicable items pass.

## A. Semantics and regression

- [ ] `center_outer_same` remains a wiring mode; no geometry-sharing semantic overload introduced.
- [ ] Existing COM/network physics tests still pass.
- [ ] Current Stage 3.2 baseline can still be run through `scipy_de_legacy`.
- [ ] Adaptive frequency and common-dense validation regression tests pass.

## B. Feasibility-first

- [ ] One central comparator is used by new optimizer selection and p-best ordering.
- [ ] Feasible always beats infeasible.
- [ ] Infeasible ordering uses max violation, then sum violation.
- [ ] Selection does not depend on a penalty-weight hyperparameter.
- [ ] Comparator unit tests cover conflicting performance/violation cases.

## C. L-SHADE correctness

- [ ] current-to-pbest/1/bin implemented.
- [ ] external archive implemented and bounded.
- [ ] M_F/M_CR success history implemented.
- [ ] F/CR sampling constraints tested.
- [ ] linear population reduction tied to unique evaluation budget.
- [ ] fixed-seed deterministic run test passes.
- [ ] normalized-coordinate search implemented.
- [ ] mixed-integer duplicate statistics and canonical cache implemented.

## D. Exact continuation

- [ ] Checkpoint stores population, archive, memories, RNG, counters, bounds and grid versions.
- [ ] New process can load checkpoint and continue.
- [ ] uninterrupted vs save/reload continuation parity test passes.
- [ ] extending 4000 -> 8000 does not restart the optimizer.
- [ ] optional resume CLI is documented and tested.

## E. Bounds

- [ ] integer boundary zone includes one decoded step by default.
- [ ] multi-seed pressure still works.
- [ ] elite alone triggers probe only, not expansion.
- [ ] repeated improving elite probes can justify expansion.
- [ ] hard bounds never change.
- [ ] no auto-shrink exists.
- [ ] expansion increments design_space_version and resets convergence evidence.
- [ ] population is preserved/re-normalized and new-region samples are injected.

## F. Polish

- [ ] integer neighborhood refinement regression passes.
- [ ] Powell continuous-only polish implemented behind config flag.
- [ ] dense validation can reject a bad polish.
- [ ] Powell vs existing polish comparison report generated.

## G. Parallel production

- [ ] ProcessPool seed runner implemented using spawn-safe tasks.
- [ ] shared output files are not concurrently mutated.
- [ ] worker BLAS/OpenMP threads limited to 1.
- [ ] serial vs parallel per-seed parity passes.
- [ ] 1/2/4/5 worker benchmark generated.
- [ ] production config enables the selected worker count.

## H. A/B experiment

- [ ] Current DE and L-SHADE use identical seeds, fixed design space, evaluator and budgets.
- [ ] 5-seed center_outer_same pilot completed.
- [ ] median/best/IQR/basin-hit/late-improvement/duplicate/wall-time metrics reported.
- [ ] promotion decision is explicit and supported by the predefined gate.
- [ ] algorithms are not benchmarked concurrently against each other.

## I. Production 50-ohm run

- [ ] Selected optimizer run for center_outer_same and outer_ports with >=5 cold seeds.
- [ ] budget continuation reaches 8000 when required without reset.
- [ ] 16000 used only under documented escalation condition.
- [ ] bound events and design-space versions reported.
- [ ] convergence classification emitted for each wiring.

## J. Review bundle

- [ ] self-contained source/config/test layout.
- [ ] exact COM inputs included.
- [ ] source/config/environment fingerprint included.
- [ ] algorithm A/B report included.
- [ ] production convergence report included.
- [ ] parallel benchmark included.
- [ ] bound and duplicate diagnostics included.
- [ ] checkpoint-resume parity result included.
- [ ] all bundle files hashed with SHA-256.
- [ ] empty-directory bundle self-test passes and log is included.

## K. Token-efficient execution

- [ ] long experiment is one self-contained command.
- [ ] internal checkpoints/progress require no conversational polling.
- [ ] final review bundle is generated automatically.
