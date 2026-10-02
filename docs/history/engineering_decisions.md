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

Do not make scientific SAW progress depend on cold/unattended Codex wake,
unqualified session ownership, or automatic recovery across an unknown
thread. A qualified one-shot queue to a known original Desktop thread may be
used as a control-plane convenience after durable job completion; it must fail
closed without risking or losing the recorded optimizer result.

### Bounded SDK-first pilot (2026-09-27)

A bounded infrastructure pilot demonstrated the public Python Codex SDK
process-boundary primitive, but did not change the frozen production decision:

- `openai-codex==0.157.1` created a dedicated thread in Process A; after A
  exited, Process B resumed the exact public thread ID and recovered context
  supplied only in the earlier turn.
- A public active-writer observation showed a second runtime's resume rejected
  while the first turn was in progress. The thread ended with one completed
  turn and no duplicate. This is observed behavior for this host and SDK
  version, not a broader concurrency guarantee.
- A detached synthetic job and one bounded hypothetical B28 `simulate` run
  completed through pilot-only SDK callbacks and reached `REVIEWED`. The SAW
  smoke is labeled `INFRASTRUCTURE_PILOT / NON-SCIENTIFIC`; its numerical
  results are not evidence for filter comparisons or design decisions.
- SDK execution succeeded under the normal Windows user identity
  `desktop-9ipace7\sub`. The restricted `CodexSandboxOffline` identity could
  not start a thread because the runtime could not resolve a home directory.
- The public turn-handle operation used by the pilot,
  `AsyncTurnHandle.run()`, has no timeout argument; later automation would need
  an external finite supervisor.
- No production orchestration or callback backend was changed. The production
  callback remains `codex exec resume`.

The SDK pilot qualifies those SDK and detached-execution primitives for further
bounded infrastructure work only. It does not establish long-duration
continuation, unattended wake, or production SDK callback support. The
subsequent exact-thread queue qualification below establishes a separate,
bounded message-delivery path; it does not resume the frozen autonomous
session-resume feature or change the production callback backend.

### Exact-thread asynchronous queue continuation (2026-09-27)

**Decision state:** `QUALIFIED / BOUNDED C2C CONTINUATION`

> **Historical decision:** this qualification remains evidence of the tested
> delivery path. Its use as an active project workflow was superseded by the
> 2026-10-02 C2C freeze decision below.

A one-shot official CLI queue was qualified for returning a completed detached
job to its known, original Desktop thread on the tested Windows host and
`codex-cli 0.158.0-alpha.2.1`:

- The pilot (`TASK_ID=c2c_49c9`,
  `RUN_ID=async_c2c49c9_0647bc562e3f4360a13f82e478b073e7`) targeted the existing
  Desktop thread `01a0ddf7-8185-7982-8940-72e62875e7ce`.
- A normal-user/profile-qualified detached helper completed one harmless
  asynchronous dummy job. Exactly one `codex queue --thread <exact-id>` attempt
  was accepted for that same thread after the durable completion record.
- The queued message arrived after the initiating turn completed, as the next
  sequential user turn in the same thread. The assistant recovered prior
  context and the job marker; exactly one continuation occurred, with no
  duplicate or overlapping turn.
- The helper, dummy, and queue processes exited. Git remained at its recorded
  baseline. No repository, SAW, or production run state was changed.

This qualifies a bounded delivery mechanism, not autonomous session resume.
Keep `FROZEN / DEFERRED` for cold/unattended wake, arbitrary thread discovery or
writer acquisition, Task Scheduler/Resume Agent operation, recovery across
unknown ownership, and SDK `thread_resume()` against a Desktop-owned thread.
At the time of this qualification, the project policy selected the
exact-thread one-shot queue for new C2C-managed detached work after durable
completion, continuing from the existing task's `NEXT_EXPECTED_STEP`. The
helper had to pass the qualified normal-user/profile and CLI preflight, use a
one-shot claim without automatic retry, and fail closed on ambiguous delivery
while preserving job results. The queue did not restore optimizer state or
automatically start follow-up production work. The 2026-10-02 freeze decision
below supersedes this historical workflow selection.

The managed production callback remains `codex exec resume` against its
captured session ID. The queue pilot does not migrate that backend; any such
change needs a separate implementation, test, and architecture review.

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

## 2026-10-02 — Freeze C2C and adopt GitHub-mediated external review

**Decision category:** engineering / workflow; not a scientific conclusion.

- C2C is frozen and is no longer a project progression dependency.
- C2C runtime use, diagnosis, session operations, and review gates are not part
  of ordinary project work. Reactivation requires a separate explicit user
  decision and fresh qualification.
- ChatGPT repository review uses GitHub branches, commits, pull requests, and
  committed evidence. Codex self-validation is not independent review.
- The Windows-native Codex workflow remains unchanged.
- Git metadata operations continue to use limited, on-request permission
  escalation only. No standing broad access or ACL change is introduced.
- Historical C2C security records, the reviewed baseline, and past experiment
  review provenance are retained.

See [`../c2c/FROZEN.md`](../c2c/FROZEN.md) for the preserved last diagnosis
and reactivation conditions, and [`../guides/github_review_workflow.md`](../guides/github_review_workflow.md)
for the active review process.
