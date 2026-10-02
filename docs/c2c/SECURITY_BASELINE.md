# C2C security baseline reference

> **FROZEN / HISTORICAL REFERENCE — effective 2026-10-02.** These security
> records are preserved for a future explicit requalification. They do not
> authorize or require C2C use in the current project workflow. See
> [FROZEN.md](FROZEN.md).

## Approved dependency

| Property | Approved value |
| --- | --- |
| Repository | `XiaoDuoYa/codex-with-chatgpt` |
| Reviewed SHA | `9663b88753e35c76796c5bce000293e0bd22cd9e` |
| Package version | `0.1.3` |
| Status | `APPROVED WITH LIMITATIONS` |
| Automatic update | Prohibited |
| Dependency update | Prohibited without review |
| Required before upgrade | ChatGPT Security Review and explicit user approval |

The C2C checkout stays outside this repository. The installed Codex Skill is a
separate user-level operational copy; do not treat it as C2C source or replace
it from upstream without review. Keep the reviewed SHA fixed until a candidate
completes the review and approval process in [UPGRADE_POLICY.md](UPGRADE_POLICY.md).
An approved upgrade must use frozen-lockfile dependency installation.

## Workspace and MCP boundary

The connector is bound to `saw-com-optimizer` and provides a read-only view of
that workspace. Its approved tools are exactly:

`workspace_info`, `list_directory`, `read_file`, `search_workspace`,
`git_status`, `git_diff`, `test_status`, `execution_summary`, and
`execution_output`.

The connector must not expose workspace writes, deletes, shell execution, Git
commit, or package installation. Confirm workspace confinement and the
connector's read-only surface before use. Keep `.c2cignore` as a required
security control. Its existing exclusions protect `.git`, environment files,
virtual environments, generated/raw optimizer data, checkpoints, temporary
and cache files, archives, private or credential material, and licensed
references. The ignore rules must not be weakened to enable C2C.

## Local C2C state write boundary

The only project-approved persistent writable root for C2C control-plane
state is the exact canonical `%LOCALAPPDATA%\codex-with-chatgpt` directory.
Do not grant `%LOCALAPPDATA%`, the user profile, `.codex`, the workspace, or
the external C2C checkout for this purpose. Preserve other pre-existing
Codex roots, but do not add broader roots to solve C2C access failures.

Persistent Codex `writable_roots` configuration is distinct from the access
boundary of an already-materialized managed sandbox. Therefore
`sandbox-allow --json` returning `alreadyAllowed=true` is not evidence that the
current task can write to the state root. The project SessionStart hook is a
non-authoritative canary and cannot grant access or prove the permissions of a
later shell. Run a direct canary in the same execution boundary immediately
before C2C use. On ordinary `PASS`, continue in that ordinary boundary. An
ordinary `ACTIVE_SANDBOX_DENIED` does not by itself mean the task is stale and
does not authorize broadening the persistent root. If and only if the current
operation explicitly authorizes the qualified targeted C2C `require_escalated`
path, verify `whoami` is `desktop-9ipace7\sub`, `USERPROFILE` is
`C:\Users\sub`, and Windows `UserProfile` is `C:\Users\sub`; rerun the direct
canary in that bounded boundary and continue there only on `PASS`. Without
explicit authorization, stop as `ACTIVE_SANDBOX_DENIED`.

`require_escalated` here means a bounded Codex sandbox escalation under the
same normal Windows user. It is not Administrator/UAC or SYSTEM elevation and
does not grant broad or permanent access. The currently qualified host
automatically approves these targeted commands; that approval behavior does
not authorize arbitrary commands or generalize to other hosts. Do not use
Windows Administrator/UAC or SYSTEM, add broad allow rules, expand writable
roots, or change ACLs. Start a fresh managed sandbox only after a persistent
sandbox-configuration change that needs to materialize or other direct
evidence that the current task has a stale boundary; an ordinary denial alone
is not a fresh-task trigger. Reserve `ACTIVE_SANDBOX_STALE` for direct evidence
of stale task materialization, not for the known ordinary-boundary denial by
itself.

The canary may create one exclusive empty file directly inside the existing
exact root and remove only that same file. It must not create directories,
touch endpoint/session/record/auth/config files, inspect credentials, change
permissions, or relocate the state store. Preserve all existing path identity,
cleanup, and fail-closed checks below; targeted escalation does not bypass
them.

The approved state root is the lexical
`%LOCALAPPDATA%\codex-with-chatgpt` path. Inspect that directory with `lstat`
and reject symlinks, junctions, or other reparse points. If Windows resolves
the default lexical path to different text, accept the textual alias only
when both paths are existing directories and `samefile` proves they identify
the same filesystem object. All canary I/O stays on the lexical path, and a
noncanonical `C2C_STATE_DIR` override remains rejected. This identity proof
does not add the resolved alias as a writable root.

Access to this state root is solely for C2C control-plane metadata. It does
not expand MCP workspace permissions, authorize credential/session-store
reads, or make the C2C source checkout writable. A passing root canary is
necessary but not sufficient for each nested C2C operation; any later EPERM
must be treated as a separate exact-path failure without broadening access.

## ChatGPT UI control boundary

Read the installed `computer-use` Skill and the current `mcp__cua_repl` tool
instructions before ChatGPT UI control. Use the Skill for its safety rules and
the tool documentation for the current IAB API and initialization procedure.
The approved surface for C2C ChatGPT operations is the built-in IAB browser API
exposed by `mcp__cua_repl`; do not use native Windows-app control, `@oai/sky`,
Chrome, Edge, or another external browser for this workflow. Select an IAB tab
only from observed tool state and stop if IAB control is unavailable.

Do not automate password, one-time-code, multi-factor, pairing-code, or other
credential entry. Hand authentication, pairing-code entry, and consent or
permission prompts to the user in the IAB. Never read or manipulate tokens,
cookies, or session storage, and do not bypass browser or security warnings.
This is a narrow project-specific exception to generic UI-route restrictions,
not blanket authorization to use other computer-control surfaces or change
account access.

This UI-control boundary does not expand the connector's permissions. Keep
workspace access confined to the approved workspace and the read-only MCP
allowlist above; use the doctor gate and exact workspace identity check before
INIT.

## Approved tunnel binary

The approved `cloudflared` binary is version `2026.9.3`, SHA-256
`f096265ec2fcbe9bb6e2d64268db167ced3fcbb83d894bdb9e2fcdb26f2ea7e2`.
Supply it through `C2C_CLOUDFLARED_PATH` only in the process that needs it.
The machine-specific approved path and preflight steps are in
[OPERATIONS.md](OPERATIONS.md); do not add it to a permanent environment or
system PATH.

## Known limitations

The Closeout approved normal development use with limitations. The
`updateAvailable=true` notification-only case has not yet been exercised
against an actual candidate. The ordinary Windows file-symlink escape case
was not exercised because the required symlink could not be created under the
available permissions. Neither limitation changes the current approved SHA
or authorizes relaxing the security boundary.

See the [Pilot Closeout report](../../reports/c2c_secure_pilot_validation_20260925.md)
for the validation evidence and limits.
