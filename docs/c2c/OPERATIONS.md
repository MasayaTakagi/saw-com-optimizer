# C2C operations

This guide covers the C2C development control plane for `saw-com-optimizer`.
The C2C checkout remains a sibling repository outside the SAW repository. Use
the installed `codex-with-chatgpt` Skill for its task protocol and recovery
details; this document records the project-specific gates, approved local
runtime inputs, and ChatGPT UI route. For this workspace, the IAB-only route
below is the project-specific exception to generic UI-control restrictions in
the installed Skill; its task protocol and recovery rules still apply.

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

At the start of the workflow, run `c2c update-check --json` for detection only
and `c2c sandbox-allow --json` according to the installed Skill. Never update
on detection. `sandbox-allow` must be idempotent when the existing state path
is already allowed; do not broaden permissions for convenience.

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

Run `c2c doctor -w <saw-com-optimizer workspace> --json` with the approved
process-local cloudflared path. Before opening the saved C2C conversation or
sending INIT, confirm:

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
including readiness to capture a valid Codex session. Launch only after that
acceptance and successful preflight. Immediately after launch, verify
`run_manifest.json` against the requirements in `AGENTS.md`; do not consider
the launch valid until those checks pass. After completion, C2C reviews the
recorded run result; involve Sol only if a defined high-risk escalation
condition applies. A completion callback reviews the finished run and must
never automatically launch another production run.

## EPERM recovery

When a C2C state write returns EPERM, identify the exact C2C state path named
by the error and confirm the existing `sandbox-allow` setting. Grant only the
permission needed for that state path and retry the failed operation once.
Never broaden the workspace, home-directory, or sandbox-wide write boundary.
Do not casually use administrator privileges, change permanent system
permissions, or patch C2C. If the narrow permission is unavailable or the one
retry still fails, stop and report the blocker; do not try wider workarounds.
