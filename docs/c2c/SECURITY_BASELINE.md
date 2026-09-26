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

## Browser and bootstrap boundary

For ChatGPT interaction, use the currently bundled
`control-in-app-browser` Skill and the `browser-client.mjs` import path it gives
for the active Codex Desktop build. Do not assume `setupBrowserRuntime` is a
global function or pin a plugin version or installation path. The supported
bootstrap is:

```js
const { setupBrowserRuntime } = await import("<path from bundled Browser Skill>");
const agent = await setupBrowserRuntime();
const iab = await agent.browsers.get("iab");
```

Reuse the bound agent and IAB within the session. The in-app browser is the
standard ChatGPT control surface; do not fall back to Computer Use, Chrome, or
another external browser.

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
