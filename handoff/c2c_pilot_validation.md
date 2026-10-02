# C2C Pilot Validation

> **Historical evidence — not an active qualification or operating guide.**
> Retained pilot notes are superseded for current project workflow by
> [`docs/c2c/FROZEN.md`](../docs/c2c/FROZEN.md) and
> [`docs/c2c/README.md`](../docs/c2c/README.md).

## Environment

- OS: Windows (host details to be completed)
- Codex: Codex desktop (version not exposed to the CLI)
- Node: v24.19.0
- pnpm: v11.19.0 (corepack command not available on PATH)
- cloudflared: 2026.9.1 (C2C custom binary path; winget unavailable)
- C2C version: 0.1.3
- C2C commit: 9663b88753e35c76796c5bce000293e0bd22cd9e

## SAW Baseline

- Workspace: `C:\Users\sub\Documents\ChatGPT\saw-com-optimizer`
- Branch: `main`
- Commit: `f2babf340f7143e44db6af83f28e2324e724f6ed`
- Working tree: 23 pre-existing deleted files; preserved without modification
- Baseline note: the checkout was concurrently moved from the previously observed feature branch to `main` and fast-forwarded before this record was created; the values above are the final rechecked baseline.
- Date: 2026-09-23 (Asia/Tokyo)

## Gate Results

- Gate 1 Build: PASS — `pnpm install`, `pnpm build`, and 178/178 tests passed
- Gate 2 Local health: PENDING — setup choice required before local workspace setup
- Gate 3 ChatGPT MCP: PENDING
- Gate 4 C2C loop: PENDING

## MCP Tests

- workspace_info: PENDING
- list_directory: PENDING
- read_file: PENDING
- git_status: PENDING
- git_diff: PENDING
- execution_summary: PENDING
- execution_output: PENDING

## Problems

- First sandboxed `pnpm test` launch was blocked by esbuild/Vitest access to a parent directory; the unchanged test suite passed when rerun with the required permission.
- `corepack` and `winget` were not available on PATH. Existing `pnpm` was used; the Cloudflare official Windows binary was downloaded and will be supplied through `C2C_CLOUDFLARED_PATH`.
- Initial SAW branch/HEAD observation changed during the session due to an external checkout/fast-forward. The current baseline was re-read and recorded; no SAW files were restored, stashed, committed, or discarded.

## Workarounds Used

- Used `pnpm` 11.19.0 directly because `corepack` was unavailable.
- Used the C2C-supported `C2C_CLOUDFLARED_PATH` override because `winget` was unavailable.
- Installed the C2C Skill at `C:\Users\sub\.codex\skills\codex-with-chatgpt\SKILL.md` with the actual checkout path.

## SAW Repository Changes

- Added `.c2cignore`.
- Added this validation record under `handoff/`.
- No Python, COM, optimizer, experiment, or existing review-bundle files were changed.

## Final Classification

PENDING

## Recommendation

- Continue pilot after the required connection and ChatGPT setup choices.
