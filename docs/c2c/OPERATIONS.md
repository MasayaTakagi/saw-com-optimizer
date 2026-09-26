# C2C operations

This guide covers the C2C development control plane for `saw-com-optimizer`.
The C2C checkout remains a sibling repository outside the SAW repository. Use
the installed `codex-with-chatgpt` Skill for its task protocol and recovery
details; this document records the project-specific gates and approved local
runtime inputs.

## Normal startup

Follow this sequence for a C2C-controlled task:

```text
Codex task start
→ read the installed C2C Skill
→ provide the approved cloudflared path to the needed process
→ C2C doctor gate
→ bundled Browser Skill bootstrap
→ IAB
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

## Browser bootstrap and saved conversation

Read the currently bundled `control-in-app-browser` Skill before browser
control. It is the source of truth for the current Codex Desktop build and
specifies the absolute `browser-client.mjs` path. Do not pin that path or the
plugin version in project documentation, and do not assume
`setupBrowserRuntime` is a global function.

Use the documented bootstrap:

```js
const { setupBrowserRuntime } = await import("<path from bundled Browser Skill>");
const agent = await setupBrowserRuntime();
const iab = await agent.browsers.get("iab");
```

Initialize once per Codex session and reuse the agent and IAB. Use the saved
ChatGPT conversation according to `c2c session --json` and the installed C2C
Skill's conversation-mode rules. Use the IAB for all ChatGPT steps. Computer
Use and external-browser/Chrome fallback are not part of the approved path.

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

## EPERM recovery

When a C2C state write returns EPERM, identify the exact C2C state path named
by the error and confirm the existing `sandbox-allow` setting. Grant only the
permission needed for that state path and retry the failed operation once.
Never broaden the workspace, home-directory, or sandbox-wide write boundary.
Do not casually use administrator privileges, change permanent system
permissions, or patch C2C. If the narrow permission is unavailable or the one
retry still fails, stop and report the blocker; do not try wider workarounds.
