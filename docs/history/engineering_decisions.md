# Engineering Decision Register

This document records non-scientific project decisions that affect how future
SAW optimization work is executed or maintained. Scientific experiment
conclusions belong in `experiment_register.md`.

## Autonomous Codex session resume — frozen / deferred

**Decision state:** `FROZEN / DEFERRED`

The local optimizer lifecycle does not depend on autonomous Codex session
resume.

Recovered Stage 3.6 freeze-closeout evidence:

- local checkpoint: PASS;
- controlled stop: PASS, with known status-lock recovery;
- local resume: PASS;
- same `run_id` after local resume: PASS;
- evaluation continuity: PASS, 240 → 480 → 960;
- result bundle generation: PASS;
- Task Scheduler for Codex resume: DISABLED;
- Resume Agent: STOPPED;
- frozen implementation preserved: YES;
- project can continue without autonomous Codex resume: YES;
- Stage 3.6 automation work was closed as frozen and work returned to the SAW
  optimizer core.

This was a deferred-scope closeout, not evidence that local checkpoint/resume
was unusable.

### Why it was frozen

Earlier validation established that explicit-session callback and
medium-duration detached execution could work, but autonomous/background wake
and session ownership remained a separate systems problem.

The later W7/R4 investigation established several useful mechanisms, including
persistent app-server operation, single-writer protection, crash/reconciliation
logic and duplicate prevention. However, the project did not obtain sufficient
production evidence for the full automatic path:

`future condition → wake an idle/cold Codex agent/thread → acquire safe
writer ownership → execute exactly once → recover after failure → safely hand
off with Desktop → continue`.

A W7.3 path also reached agent-owned thread creation and fail-closed behavior,
but production-identity thread start/reconnect and complete scheduler E2E were
not established. This feature was not on the SAW scientific critical path.

### Current interpretation

Keep detached optimizer execution, explicit status, checkpoint lifecycle and
manual/local resume capability as useful infrastructure.

Do not make SAW experiment progress depend on autonomous Codex session wake or
automatic thread continuation.

### Reopen condition

Reconsider the frozen feature only in a separate infrastructure task that can
demonstrate the missing autonomous wake/session-ownership path and a complete
unattended E2E proof without blocking the SAW optimizer roadmap.

## Long-running orchestration evidence retained

Earlier controlled validation did establish:

- explicit session binding to the intended Codex session;
- callback target-ID verification;
- manual retry after callback timeout without rerunning the optimizer;
- multi-session A/B callback targeting;
- bounded medium-duration optimizer completion;
- no automatic launch of a subsequent production optimization.

These are historical infrastructure capabilities, not authorization to restore
autonomous session-resume as a project requirement.
