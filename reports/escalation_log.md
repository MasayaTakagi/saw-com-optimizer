# Luna → Sol Escalation Log

Pilot: Stage 1
Status: stopped at mandatory review gate

Each escalation must be recorded as a self-contained packet followed by the
decision, Luna's action, verification, and outcome. Requested model and
reasoning effort must be kept separate from independently observed backend
identity and behavior.

## 2026-09-13 — Stage 3.5 L-SHADE parity root-cause review

### Packet

- Scope: evidence-only review of the current-versus-historical L-SHADE
  trajectory divergence before any source change or production experiment.
- Decision requested: choose provenance reconstruction, first-divergence
  tracing, or another bounded audit; classify RC1–RC8.
- Constraints: no source edits, optimizer changes, Phase D, production reruns,
  tuning, tolerance changes, or `multi_agent_v2` configuration.
- Requested reviewer: GPT-5.6 Sol, high reasoning, one reviewer.

### Decision

- Recommendation: **B — reconstruct historical provenance and checkpoint/grid
  protocol first**.
- Confidence: high for B; medium-high for **RC6 historical provenance mismatch**.
- Evidence: historical and current best/population/archive traces are exactly
  equal through 4,000 unique evaluations. The first observable divergence is
  the current-only 4k adaptive-frequency exchange. Historical checkpoints use
  16k/32k/64k exchanges, while current diagnostic checkpoints use 4k/8k/16k.
- Population bounds, initial/minimum population, 64k schedule horizon, and 16k
  population size agree. Missing historical schedule telemetry is not evidence
  of RC3.
- No optimizer or diagnostic source change is justified from current evidence.

### Luna action, verification, and outcome

- Accepted the review decision. No experiment was launched and no optimizer,
  objective, search-space, COM, tolerance, or budget behavior was changed.
- Required next validation is a provenance/source/config/protocol diff, followed
  only after protocol equivalence by one bounded 16k parity verification with a
  64k population horizon and no objective-changing 4k/8k exchange.
- Stop for review if exact historical provenance cannot be reconstructed, the
  matched-protocol parity check fails, or a repair would change optimizer
  behavior or require repeating a long production run.
- Backend model identity and actual internal reasoning effort were not
  independently verified by the runtime; GPT-5.6 Sol and high reasoning were
  requested through the task API.

## 2026-09-13 — Stage 3.5 matched-protocol configuration gate

### Packet

- Scope: decide whether the existing L-SHADE trajectory worker can express the
  matched-protocol run with a 64,000 population-schedule horizon, a 16,000
  diagnostic stop, and one adaptive-grid exchange at 16,000.
- Evidence: the historical D/S1/seed20260917 B16000 snapshot records traces at
  grid version 1 through evaluation 16,000 and serializes the version-2
  exchange after that observation. The current trajectory worker derives its
  L-SHADE total budget and schedule horizon from `max(budgets)`, so a
  `[16000]` request would incorrectly use a 16,000 horizon.
- Constraints: no optimizer/objective/physics/search-space/canonicalization/
  tolerance/seed/budget-semantic changes; one diagnostic run only.
- Requested reviewer: GPT-5.6 Sol, high reasoning, one reviewer.

### Decision

- Recommendation: proceed only after a minimal orchestration/configuration
  change that decouples the 64,000 schedule horizon from the 16,000 execution
  stop.
- Required assertions: seed 20260917, S1, Zport 50 ohm, L-SHADE total and
  population horizon 64,000, actual stop 16,000, no 4,000/8,000 exchanges,
  exactly one exchange at 16,000, pre-exchange trace at grid version 1, and
  protected numerical semantics unchanged.
- Historical B16000 semantics are sufficiently supported as PRE_EXCHANGE,
  while broader historical protocol semantics remain UNKNOWN. Do not claim
  FULL_PARITY_PASS from this inference alone.
- Any required change to L-SHADE behavior or protected numerical semantics
  requires a new escalation. No additional user clarification is needed.

### Luna action

Implement only an explicit matched-protocol orchestration/configuration path,
with the existing behavior preserved when the opt-in setting is absent. Add
preflight and post-run guardrails before launching the one diagnostic run.
