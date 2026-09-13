# Luna → Sol Pilot Review

Status: stopped at mandatory review gate

## Chat Sol review summary

| Metric | Result |
|---|---:|
| Sol calls | 1 |
| Automatic escalations | 1 |
| Manual escalations | 0 |
| Unnecessary escalations | 0 |
| Missed escalations | 0 |
| Sol decisions adopted | 1 |
| Sol decisions rejected | 0 |
| Spawn failures | 0 |
| Rework caused by Luna error | 0 |
| Re-experiments caused by implementation error | 0 |

Overall pilot assessment: one bounded Sol review was used at the first
high-risk parity decision. It prevented an unjustified optimizer/source
change and an additional expensive rerun, while routine implementation and
verification remained with Luna. Historical provenance is incomplete, so the
pilot must continue after review of the matched-protocol plan.

## 1. Task Summary

Introduced the Luna-root / on-demand Sol escalation policy and began the
current Stage 3.5 L-SHADE parity investigation.

## 2. Luna Work Summary

- Reviewed the supplied pilot instruction separately from the user request.
- Confirmed the existing `.codex` configuration and did not enable
  `multi_agent_v2`.
- Added the policy to `AGENTS.md`.
- Initialized escalation and missed-escalation tracking.
- Ran targeted and full tests.
- Audited historical/current parity provenance and checkpoint protocol.

## 3. Sol Escalations

Sol was asked for one bounded decision: provenance reconstruction versus
first-divergence tracing, and whether source changes were justified. The
recommendation was B: provenance/config/protocol reconstruction first, with
RC6 as the leading hypothesis. The requested model was `gpt-5.6-sol` with
`high` reasoning; backend identity and actual internal reasoning were not
independently verified.

## 4. Escalation Statistics

See the summary table above and `reports/escalation_log.md`.

## 5. Important Decisions

No optimizer, objective, COM, search-space, tolerance, or budget semantics
were changed. The current parity failure is held at the review gate because
current exchanges occur at 4k/8k/16k while historical records show 16k/32k/64k.

## 6. Implementation Results

Policy and tracking artifacts are present. Evidence-only parity artifacts are
under `runs/stage3_5_lshade_parity_root_cause/results/`.

## 7. Test Results

- Targeted Stage 3.5/orchestration tests: 35 passed.
- Full regression: 174 passed.
- Warning: pytest could not write `.pytest_cache` because of filesystem
  permissions; this did not affect test results.

## 8. Experiment Results

The existing parity result is `PARITY_FAILED_NEEDS_REVIEW`. Before the
current-only 4k exchange, population and archive traces match for 3,875
entries. No new production experiment was launched during this pilot turn.

## 9. Failures / Rework

No Luna-caused rework or re-experiment occurred. The historical provenance
record lacks a complete runtime/per-arm manifest and the parity comparison is
protocol-confounded.

## 10. Efficiency Assessment

The single escalation was necessary and bounded. It avoided source changes and
long reruns while evidence was insufficient.

## 11. Quality Assessment

The stop decision is conservative and consistent with the handoff: current
better/different metrics are not treated as parity. Quality remains pending a
matched-protocol 16k verification.

## 12. Problems with Escalation Mechanism

The available runtime exposed requested model/reasoning settings but not an
independent backend identity or internal reasoning measurement. Historical
experiment records also do not contain enough provenance to prove exact
lineage.

## 13. Recommendation

`C. CONTINUE PILOT`

After ChatGPT Sol review, reconstruct the historical protocol and perform at
most the bounded matched-protocol 16k parity check. Do not start Phase D or
resume production optimization automatically.
