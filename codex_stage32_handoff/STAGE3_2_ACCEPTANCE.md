# Stage 3.2 Acceptance Checklist

## Optimizer correctness

- [ ] Same seed uses continuation across 500→1000→2000→4000.
- [ ] 4000 non-converged auto-escalates to 8000 when enabled.
- [ ] Requested unique budget is actually consumed unless convergence/explicit stop occurs.
- [ ] Grid convergence does not terminate remaining design budget.
- [ ] Grid extension does not increment unique-design evaluation count.
- [ ] Population/objectives are updated after grid extension.

## Convergence

- [ ] Same-seed paired budget deltas are reported.
- [ ] Two consecutive plateau intervals required for converged.
- [ ] Best-candidate polish metric separated from median-candidate polish metric.
- [ ] Late significant improvement metric implemented.
- [ ] Convergence history resets after design-space expansion.

## Bounds

- [ ] Initial/soft and hard bounds are distinct.
- [ ] Hard bounds cannot be auto-crossed.
- [ ] Single-seed boundary hit cannot trigger expansion.
- [ ] Persistent multi-seed boundary pressure can trigger probe.
- [ ] Positive probe can trigger expansion.
- [ ] No automatic bound shrink.
- [ ] Design-space version is logged.
- [ ] New-region exploration injection occurs after expansion.
- [ ] `hard_bound_limited` status is distinguishable from `converged`.

## Numerical correctness

- [ ] Incremental frequency results equal full recompute within tolerance.
- [ ] Incremental diagnostics aggregate to full-range diagnostics.
- [ ] Serial/parallel result parity passes.
- [ ] Existing COM/network regression tests pass.

## Small-scale testing

- [ ] Synthetic bound-expansion tests pass.
- [ ] 100→200→400 SAW smoke run passes.
- [ ] Checkpoint/resume/continuation smoke test passes.
- [ ] Budget accounting error is zero.

## Performance

- [ ] 1/2/4/5-worker benchmark completed.
- [ ] Wall times and efficiency recorded.
- [ ] BLAS threading behavior recorded.
- [ ] No low-level performance rewrite introduced without need.

## Production run

- [ ] 50 Ω outer_ports run completed.
- [ ] 50 Ω center_outer_same run completed.
- [ ] ≥5 cold seeds each.
- [ ] 500/1000/2000/4000 checkpoints present.
- [ ] 8000 present when auto escalation required.
- [ ] Boundary events and design-space versions recorded.
- [ ] Final status for each wiring is one of converged / hard_bound_limited / likely_underoptimized / inconclusive.

## Review bundle

- [ ] Bundle manifest contains SHA-256 and size for all files.
- [ ] Exact config and COM input included.
- [ ] Source snapshot included.
- [ ] Configs exist at test-expected relative paths.
- [ ] Repository metadata required by tests included.
- [ ] Test logs included.
- [ ] Production trial summaries included.
- [ ] Boundary event log included.
- [ ] Parallel benchmark included.
- [ ] ZIP extracts in a clean temporary directory and bundle-only test rerun passes.
