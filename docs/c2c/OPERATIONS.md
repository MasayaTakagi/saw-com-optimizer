# C2C operations reference

> Issue #108 also retires legacy Codex queue/callback behavior. This record
> does not authorize C2C or provide a replacement agent transport; do not
> execute any runner/handoff instruction here.
>
> **FROZEN / HISTORICAL REFERENCE — effective 2026-10-02.** This procedure is
> retained for evidence and possible future requalification. It is not an
> active workflow for SAW project tasks. Do not invoke C2C while frozen. See
> [FROZEN.md](FROZEN.md) for current status and reactivation conditions.

This guide covers the C2C development control plane for `saw-com-optimizer`.
The C2C checkout remains a sibling repository outside the SAW repository. Use
the installed `codex-with-chatgpt` Skill for its task protocol and recovery
details; this document records the project-specific gates, approved local
runtime inputs, and ChatGPT UI route. For this workspace, the IAB-only route
below is the project-specific exception to generic UI-control restrictions in
the installed Skill; its task protocol and recovery rules still apply.

In managed sessions where `c2c` is not on `PATH`, invoke the installed checkout
directly (and prefer this form in project-specific procedures):

```powershell
node "C:\Users\sub\Documents\ChatGPT\codex-with-chatgpt\bin\c2c.js" <command>
```

Do not create a global link or change `PATH` as a qualification prerequisite.

## Normal startup

Follow this sequence for a C2C-controlled task:

```text
Codex task start
→ read the installed C2C Skill and computer-use Skill
→ provide the approved cloudflared path to the needed process
→ C2C doctor gate
→ follow the current mcp__cua_repl instructions
→ operate ChatGPT in the built-in IAB only
→ saved ChatGPT C2C conversation
→ workspace_info verification
→ INIT
```

Before the C2C-using task starts, run the installed CLI's
`sandbox-allow --json` subcommand as the normal user, using the explicit Node
invocation above. Follow the installed Skill. Never update on detection.
Confirm the C2C-related persistent Codex writable-root declaration is exactly
`%LOCALAPPDATA%\codex-with-chatgpt`; preserve unrelated pre-existing roots.
For this Windows workspace, use this canonical TOML representation:

```toml
[sandbox_workspace_write]
writable_roots = ["C:/Users/sub/AppData/Local/codex-with-chatgpt"]
```

C2C 0.1.3 `sandbox-allow` did not recognize an observed single-quoted Windows
path using backslashes as the same path, although it is valid TOML.
Use the forward-slash representation above for compatibility with that parser;
this is a bounded observation about C2C 0.1.3, not a general TOML rule.

`alreadyAllowed=true` confirms only persistent configuration, not access in
the current execution boundary. If the root was added or changed, start a
fresh managed Codex sandbox so the changed configuration can be materialized.
That fresh task is tied to an actual configuration change; do not use repeated
fresh tasks as a remedy for a reproducible ordinary-boundary denial.

At task start, run the installed CLI's `update-check --json` subcommand using
the explicit Node invocation above, for detection only. The result
`checked=false`, `updateAvailable=false`, `exit=0` can mean an offline/skipped
check and does not by itself fail state-access qualification. Treat
`updateAvailable=true` as a separate update workflow. Then use the SessionStart
state-access hook as an early warning and, immediately before any C2C
`doctor`, `session`, or `record` command, run the direct probe through the same
execution boundary that will run C2C:

```powershell
.codex\hooks\c2c_state_access_preflight.cmd --json
```

The hook only creates one exclusive, empty, uniquely named canary directly
inside the existing canonical state directory, flushes and closes it, then
removes that exact file. It does not create directories, alter C2C files, grant
permissions, read credentials, or relocate C2C state. A SessionStart result is
informational because hooks and the later command may have different effective
access. Keep the probe JSON status, probe/child exit code, and wrapper exit code
distinct where available; wrapper exit 0 alone is not proof that the child
operation succeeded.

Use this access decision:

1. Ordinary direct preflight `PASS`: continue in the ordinary execution
   boundary; do not use `require_escalated`.
2. Ordinary direct preflight `ACTIVE_SANDBOX_DENIED`: do not infer
   `ACTIVE_SANDBOX_STALE` or create a fresh task from this result alone. If the
   current operation explicitly authorizes the qualified, bounded C2C
   escalation path, use one targeted `require_escalated` command boundary.
   Verify `whoami` is `desktop-9ipace7\sub`, `USERPROFILE` is
   `C:\Users\sub`, and Windows `UserProfile` is `C:\Users\sub`; then run the
   direct preflight in that boundary. Continue with the C2C operation only
   if it returns `PASS`, in the same targeted boundary. Without explicit
   authorization, stop as `ACTIVE_SANDBOX_DENIED`.
3. Any other preflight result: stop and preserve its exact fail-closed
   classification. Targeted escalation does not bypass path, root, identity,
   or cleanup failures.

The qualified path is a bounded Codex sandbox escalation, not Windows
Administrator/UAC or SYSTEM elevation. It is limited to the explicitly
authorized C2C state preflight, C2C Doctor, documented workspace/session/
state/record operations, the C2C/orchestration launcher, or bounded
qualification commands named by the task. It does not authorize arbitrary
shell work, unrelated AppData access, broader writable roots, ACL changes, or
broad permanent allow rules. On the currently qualified host, these targeted
commands are automatically approved; this does not grant unrestricted standing
permission or imply that other hosts have the same approval behavior. The
`with_additional_permissions` mode is unavailable in this environment and is
not a fallback path.

The normal order is: verify the persistent exact-root declaration → check for
an actual configuration change requiring a fresh task → read the SessionStart
diagnostic → run the ordinary direct probe → continue in the ordinary boundary
on `PASS`, or use the explicitly authorized targeted path on
`ACTIVE_SANDBOX_DENIED` → doctor → workspace identity → saved
conversation/session/INIT. Never broaden permissions for convenience.

### Approved cloudflared

Approved binary:

```text
C:\Users\sub\AppData\Local\codex-with-chatgpt\bin\cloudflared.exe
```

Approved version: `2026.9.3`

Approved SHA-256:
`f096265ec2fcbe9bb6e2d64268db167ced3fcbb83d894bdb9e2fcdb26f2ea7e2`

Before C2C doctor or tunnel commands, confirm the file exists, its reported
version is `2026.9.3`, and its SHA-256 matches the value above. Set
`C2C_CLOUDFLARED_PATH` only in the process running the relevant C2C command.
Do not modify the permanent User/Machine environment, Windows PATH, or system
installation. If the binary is absent or mismatched, stop as BLOCKED. Do not
download, replace, or install it; winget is not approved for this baseline.

### Doctor gate

Run the installed CLI's normal `doctor -w <saw-com-optimizer workspace> --json`
subcommand with the approved process-local cloudflared path; `--no-fix` is not
required for operational qualification. A stopped tunnel at fresh-session
startup is recoverable state, not by itself a state-access failure. Allow
Doctor's documented bridge/tunnel recovery, then judge the final gates.
Recovery must not require ACL or persistent-config changes or writable-root
expansion. A task-authorized targeted C2C `require_escalated` boundary may be
used after an ordinary `ACTIVE_SANDBOX_DENIED` and the identity/preflight gates
above. Do not use Windows Administrator/UAC or SYSTEM elevation. Before
opening the saved C2C conversation or sending INIT, confirm:

- bridge, MCP, OAuth, and tunnel checks are healthy;
- sandbox/state-directory checks are healthy;
- `namedRepair.needed` is `false`;
- `chatgptRepair.needed` is `false`.

If any required check is not green, follow the installed Skill's existing
recovery procedure and rerun doctor. Do not send INIT until the gate is green.

## IAB control and saved conversation

Before operating ChatGPT, read the installed `computer-use` Skill and the
current `mcp__cua_repl` tool instructions. The Skill supplies the applicable
computer-use safety rules; the tool instructions define the current IAB API,
initialization, and tab-selection procedure. For this project, operate ChatGPT
only through the browser API exposed for the built-in IAB. Do not use the
Skill's native Windows-app controls, `@oai/sky`, or another computer-control
surface for C2C.

Follow the tool's first-call and reset instructions exactly. Inspect the
returned browser/tab state, select only a tab identified as the IAB, and bind
an existing ChatGPT tab using its returned tab reference or observed URL. Do
not guess tab IDs or switch to Chrome, Edge, or another external browser. If
the IAB is unavailable, stop and report the blocker rather than falling back
to a different browser or native UI. After each UI action, inspect the latest
page state before deciding the next action.

Do not automate password, one-time-code, multi-factor, pairing-code, or other
credential entry. Hand authentication, pairing-code entry, and consent or
permission prompts to the user in the IAB; resume after the user completes
them. Never read or manipulate tokens, cookies, or session storage. Do not
treat the IAB-only rule as blanket approval to grant access or bypass a
security barrier.

Use the saved ChatGPT conversation according to `c2c session --json` and the
installed C2C Skill's conversation-mode rules. Use the IAB for every ChatGPT
step. Keep the workspace connector read-only and use it only for workspace
data; UI control does not replace the doctor gate or workspace identity check.

Session command options differ by subcommand. Follow the installed Skill or
that subcommand's CLI help; do not add `--json` mechanically. For example,
`session get --json` supports JSON output, while `session set` does not.

Before INIT, use the workspace-bound connector to verify:

```text
workspaceName = saw-com-optimizer
rootAlias = workspace:/
```

Stop without INIT if either value differs. Do not replace the connector or
Project merely to resume an existing task.

## C2C control loop

The standard loop is:

```text
INIT → PLAN → Codex execution → EXECUTED → independent ChatGPT review → DONE
```

ChatGPT plans and reviews; Codex executes. Make no changes before receiving
the PLAN. Record execution metadata with C2C when required by the Skill, then
send EXECUTED without pasting diffs or logs. ChatGPT must review the current
workspace/Git state through the approved read-only connector; an EXECUTED
message alone is not proof of correctness. Continue a requested review/fix
cycle until DONE, or stop and report BLOCKED. Keep long-running optimizer
processes independent from the lifetime of a C2C or ChatGPT session.

### Async continuation to the original Desktop thread

For newly designed C2C-managed asynchronous work, use the qualified one-shot
official `codex queue` route to return completion to the **exact original
Desktop thread**:

```text
accepted PLAN and durable continuation checkpoint
→ start detached job and end the initiating turn
→ job writes its durable terminal result
→ one codex queue --thread <exact-original-thread-id> --message <small-reference>
→ same-thread queued turn validates the result
→ continue at NEXT_EXPECTED_STEP
→ EXECUTED and independent review
```

Keep three durable layers connected:

- The original Desktop thread retains the PLAN and conversation context. Capture
  its exact thread ID before detaching; do not discover a target later, use
  `--last`, or create a continuation thread.
- The C2C checkpoint or HANDOFF retains `TASK_ID`, PLAN iteration, `RUN_ID`,
  and `NEXT_EXPECTED_STEP`. The original PLAN remains authoritative; do not
  replay it in the completion message.
- The detached job's existing run directory/status/checkpoint/result is the
  evidence of execution completion. Do not use a queued message as proof that
  the job completed or create a second production state store.

Only queue after the job has reached its durable completion gate. Use exactly
one `codex queue --thread <exact-thread-id> --message <message>` attempt per
completion event, protected by a durable one-shot claim. The completion message
should carry only routing and verification data, such as `TASK_ID`, `RUN_ID`,
the exact result/run reference, `NEXT_EXPECTED_STEP`, the claim-generated
`DELIVERY_ID`, and a unique delivery sentinel. The receiver must verify that
`DELIVERY_ID` matches the durable one-shot claim, along with the task, run,
sentinel, and exact thread, before confirming receipt. It asks the existing
thread to validate the referenced state and continue the existing task at that
next step. `codex queue` is a delivery and serialization primitive; it does not
resume optimizer state or create/acquire a second thread writer.

On Windows, run the helper in the qualified normal-user profile context and
fail closed unless the effective user, `USERPROFILE` versus the Windows
`UserProfile` special folder, Codex executable/version, and installed
`codex queue --help` syntax are valid. In particular, confirm explicit
`--thread` and `--message` support before relying on the route. Do not move the
queue call to a detached/background identity that has not passed this
preflight.

When the queued turn arrives, verify the exact original thread, durable job
completion and result reference, delivery/run markers, absence of duplicate or
overlapping turns, and the relevant Git baseline before continuing. Resume at
`NEXT_EXPECTED_STEP` from the existing PLAN/HANDOFF; do not replay the full
PLAN or rerun completed work. A completion continuation never authorizes a
subsequent production run.

If the queue call fails or its acknowledgement is ambiguous, leave the
completed job and its results intact. Do not retry automatically, create a new
thread, or relaunch the job. Recover explicitly in C2C using the same
`TASK_ID` and durable state, and determine whether a delivery was already
accepted before any further action.

The queue-native route is qualified for new managed C2C continuations. Use it
with the exact original Desktop thread and the durable one-shot delivery and
receiver-validation gates above. Existing manifests and runs using
`legacy_resume` retain their captured-session `codex exec resume` behavior;
do not reinterpret or rewrite those historical runs as queue mode. Queue
receipt confirms delivery to the intended thread, not optimizer recovery,
scientific acceptance, topology promotion, or authorization for another
production run. See
[`../guides/async_orchestration.md`](../guides/async_orchestration.md) for the
mode-specific launch and manifest contracts.

### Review routing and timing

Use the roles defined in [`AGENTS.md`](../../AGENTS.md): C2C/ChatGPT owns PLAN
and ACCEPT, Sol provides bounded JUDGMENT only when escalation criteria apply,
and Codex root owns implementation and self-validation. At PLAN, classify
whether Sol escalation is required. If it is, obtain Sol's judgment before
changing the implementation; Codex root then resumes execution. Treat Sol's
judgment as input to the plan, not acceptance of the integrated result, and
avoid asking both reviewers the same question by default.

At meaningful work-unit completion, Codex root sends EXECUTED with current
workspace, Git, and validation evidence. C2C independently reviews that state
and decides ACCEPT/DONE or requests a focused revision. Get that acceptance
before dependent work, promotion to the next study stage, or commit/push/merge
when the unit is intended for integration.

Before launching a long-running or high-cost production run, obtain C2C
acceptance of the implementation and pre-launch configuration/preflight,
including readiness to capture and preflight the continuation identity
required by the selected continuation mode. Queue mode requires the exact
original Desktop thread ID, accepts neither `--session-id` nor
`--session-file`, and records `codex_session_id=null`; `legacy_resume`
requires its captured Codex session identity; disabled continuation requires
no continuation identity. Launch only after that acceptance and successful
mode-specific preflight. Immediately after launch, verify
`run_manifest.json` against the requirements in `AGENTS.md`; do not consider
the launch valid until those checks pass. After completion, C2C reviews the
recorded run result; involve Sol only if a defined high-risk escalation
condition applies. A completion callback reviews the finished run and must
never automatically launch another production run.

## EPERM recovery

Treat the probe's results as follows:

| Result | Action |
| --- | --- |
| `PASS` | Continue to the next C2C gate in the ordinary execution boundary. Do not use `require_escalated`. A later EPERM is a distinct child-path or operation defect; inspect only the exact failing path and stop before retrying. |
| `ACTIVE_SANDBOX_DENIED` | Do not infer `ACTIVE_SANDBOX_STALE` from this result alone. If the current operation explicitly authorizes targeted C2C escalation, verify the normal Windows user/profile, run the direct probe in one bounded `require_escalated` boundary, and continue only on `PASS` in that same targeted boundary. Otherwise stop as `ACTIVE_SANDBOX_DENIED`. |
| Targeted identity mismatch | Stop as `C2C_TARGETED_ESCALATION_IDENTITY_INVALID`; do not run the state operation. |
| Targeted preflight not `PASS` | Stop as `C2C_TARGETED_ESCALATION_FAILED` for an access denial, or preserve the exact non-access result classification. Do not run the state operation. |
| `STATE_PATH_MISMATCH` | Stop. Reject conflicting `C2C_STATE_DIR` redirects, a symlink/junction/reparse point on the state directory, or an unproven path identity. Do not relocate C2C state. |
| `STATE_ROOT_MISSING` / `OTHER_IO_FAILURE` | Stop and report the exact classification. Do not create the state directory or attempt C2C operations. |
| `PROBE_CLEANUP_FAILED` | Stop; report the exact canary filename for manual cleanup after checking it is the probe's own file. Do not continue or retry automatically. |

The only approved operation path is the lexical
`%LOCALAPPDATA%\codex-with-chatgpt` path. Inspect the state directory with
`lstat` and fail closed if it is a symlink, junction, or other reparse point.
If the OS resolves this default path to different text, accept it only when
both names identify existing directories and `samefile` proves they are the
same filesystem object. Keep canary creation and deletion on the lexical path.
This identity check does not authorize the resolved alias as another writable
root; a noncanonical `C2C_STATE_DIR` remains rejected even if it would resolve
to the same object.

If `sandbox-allow` reports that the persistent exact root is absent, add only
that root through the approved normal-user setup. Because this changes
persistent sandbox configuration, start one fresh managed sandbox so the
change can materialize before retrying the ordinary preflight. If it says
`alreadyAllowed=true` but the ordinary probe is denied, do not repeat
`sandbox-allow` or create more fresh tasks as the repair. Use the targeted path
only when the current operation explicitly authorizes it. Never broaden the
workspace, home-directory, or sandbox-wide write boundary, change ACLs, or
modify the external C2C checkout.

`ACTIVE_SANDBOX_STALE` is reserved for direct evidence that sandbox
configuration changed after task creation or that the task has a materially
stale boundary. Persistent exact-root configuration plus ordinary denial is
not sufficient evidence. The two-fresh-normal-session requirement in the
2026-09-28 escalation-log entry records that historical qualification and is
not a current recovery prerequisite. Historical outcomes remain valid for
their recorded environment and time; evaluate current operations using the
decision path above.
