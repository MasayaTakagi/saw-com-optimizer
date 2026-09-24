# GPT-6 Sol Migration Report

## Active target

- Active project review policy: `gpt-6-sol` in `AGENTS.md`.
- Previous active policy: GPT-5.6 Sol, replaced for future review requests.
- Active Python/runtime invocation call sites: none found in `src/`, `tests/`,
  `configs/`, or current reusable documentation. The repository's review
  dispatch is performed through the Codex task API.
- Historical `gpt-5.6-sol` records in `reports/luna_sol_pilot_review.md` and
  earlier `reports/escalation_log.md` entries remain unchanged.

## Routing request and fallback

- Requested model: `gpt-6-sol` (the Codex task API model key corresponding to
  the requested GPT-6 Sol target).
- Request submission: accepted; a bounded review task completed.
- Resolved model: **NOT VERIFIED**. The runtime did not expose the backend
  model identity or internal reasoning effort.
- Repository fallback behavior: no runtime caller or fallback path exists in
  this repository. The request specified only `gpt-6-sol`; external resolution
  or fallback cannot be independently observed here.
- Routing smoke status: **NOT VERIFIED** for resolved backend identity.

## Regression coverage

`tests/unit/test_sol_review_routing_policy.py` checks that the active
escalation policy requests `gpt-6-sol` and contains no `gpt-5.6-sol` fallback
in that active policy section. The task API accepted the explicit model
parameter. Neither result proves the hidden backend identity.
