# C2C security baseline

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
