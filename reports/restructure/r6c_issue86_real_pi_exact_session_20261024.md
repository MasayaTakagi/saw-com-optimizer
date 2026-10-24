# Issue #86 — Real Pi offline exact-session preflight and bounded trial

**Date:** 2026-10-24 JST

**Project baseline:** `4d1711799a64fb4078cf2b9f24312af5e1b27f5a` (merged PR #85)

**Result:** `REAL_PI_OFFLINE_TEST_BLOCKED` — isolation preflight passed, but the one permitted real Pi startup exited unsuccessfully before a session identity could be qualified. No retry or reopen was attempted.

## Scope and authorization

This was limited to the owner-authorized Issue #86 trial: one newly created, temporary test-owned real Pi session, only if offline isolation could first be objectively demonstrated. No existing Pi session, home configuration, provider credentials, project worker, agent task, Codex queue/callback, optimizer, COM/FE calculation, scientific run, or raw/checkpoint data was accessed. No prompt was sent.

## Read-only Pi capability check

The installed `pi` reported version **1.4.0**. Only the allowed non-session `pi --version` and `pi --help` introspections were used before the runtime trial. Help documented `--mode rpc`, `--session <path|id>`, `--session-dir`, `--no-tools`, `--no-extensions`, `--no-mcp`, `--no-skills`, `--no-prompt-templates`, `--no-themes`, `--no-context-files`, `--no-approve`, and `--offline`. The installed CLI and session/RPC/security documentation confirms that `--session` accepts a session path, while `--session-id` creates a session when absent; the latter, `--continue`, and `--resume` were not used.

Runtime identity, recorded by content digests rather than machine paths:

| Component | Version / identity |
|---|---|
| Pi CLI | 1.4.0; launcher SHA-256 `da0c6a49fe94aadc9765cc7afc6ba6b17e553eed0247d0385c160bc188f5cfbb` |
| Bundled Pi CLI entry | SHA-256 `e79626f2dd6f94aa45d30f3fa63cd84319a6eefcd150b353cfaf274366926774` |
| Existing Node runtime | 22.23.4; SHA-256 `94efd062ed066c1a0b332e18249859c905e920eeada5df55d24c99b919629a90` |

No software or package was installed or updated.

## Safety preflight — PASS before the Pi startup

- A rootless Linux user, mount, network, and PID namespace was created with the available unprivileged namespace mechanism; no elevated privilege was used.
- In that network namespace, the only interface was loopback in the **DOWN** state and the route table was empty. This was checked in the same namespace used for the sandbox. `PI_OFFLINE=1` and `--offline` were also configured, but were not treated as the network boundary.
- Pi ran under `chroot` into a newly created, mode-0700 test fixture. Only the exact installed Pi 1.4.0 release, the exact existing Node executable, and required OS runtime libraries were bind-mounted read-only. No host home tree, session/config directories, worktree, `/run`, device tree, provider configuration, browser/GitHub socket, or historical data path was mounted; `/proc` was not exposed inside the chroot. The fixture's project directory was empty.
- `HOME`, all XDG config/data/cache/state paths, Pi config/session roots, temporary directory, and working directory were directed to fresh test-owned fixture locations. The profile and its writable directories were mode 0700. The launch used an explicit `env -i` environment; provider credentials, `SSH_AUTH_SOCK`, personal Pi configuration, and other inherited environment variables were not passed.
- Startup explicitly disabled tools, extensions (including discovered and built-in extensions), MCP, skills, prompt templates, themes, context files, and project trust. The initial invocation used RPC mode and an explicit test-only session directory; it did not use a prompt or a model/provider selection.
- Per-process limits were set before launch: 15-second wall-clock deadline, 12 CPU seconds, 3 GiB address-space limit, 8 MiB maximum file size, 64 open files, 64 processes, and no core dump. The process ran in its own process group and PID namespace for bounded cleanup.

These checks established the isolation prerequisite for the single bounded startup attempt. They do **not** qualify Pi behavior outside this fixture.

## Bounded real Pi startup — FAILED; stopped

One actual Pi 1.4.0 RPC process was started with the documented session-directory and disable/offline flags above. The only input records were read-only `get_state` and `get_entries` requests; **no `prompt`, `steer`, `follow_up`, tool, extension, MCP, or provider request was issued**.

The process exited with status **1** before the harness accepted a successful correlated state/entries response. Standard error was nonempty. Its contents were deliberately not retained or published, so the failure cause is **unclassified**; this report does not guess at it. The process was not retried, and no second Pi process or reopen was attempted.

Post-exit inspection was confined to the test-owned fixture: the session directory contained **zero** session JSONL files; the test profile, workspace, and temporary directory contained no files; the fixture contained only six zero-length runtime bind-mount placeholders. The process group was empty after exit, with no orphan. No Pi session identity, exact path, inode, branch, or cursor was therefore available to verify.

## Classification and unverified claims

- **`REAL_PI_OFFLINE_TEST_BLOCKED`** — one bounded real-Pi startup failed before identity evidence was accepted. The safe isolation preflight itself passed.
- **`REAL_PI_EXACT_SESSION_IDENTITY_PASS` — NOT CLAIMED.** No persisted test session was created/verified, and no exact-session reopen occurred.
- **`REAL_PI_BRANCH_CONTEXT_PASS` — NOT CLAIMED.** No branch entries or active cursor were established. Branch/content continuation remains unverified.
- **`PI_RPC_WIRE_INTEGRATION_UNVERIFIED`** — no successful RPC state/entries exchange was qualified.
- **`INFLIGHT_AGENT_PROMPT_REPLAY_UNVERIFIED`** — no prompt was sent; no exactly-once or recovery behavior was tested. Preserve `DISPATCH_AMBIGUOUS` as a manual/no-auto-resend state for any future uncertain dispatch.
- **`SCIENTIFIC_FE_RESTART_UNVERIFIED`** — outside this work unit and not tested.
- Issue #84 remains `MOCK_PROTOCOL_PASS` only; this failed runtime attempt does not upgrade the mock adapter's qualification.

## Stop and next gate

No additional real Pi startup, session creation, diagnostic prompt, or retry is authorized by this evidence. A future attempt requires an owner disposition for the failed startup and a separately bounded scope; do not infer that `--offline` alone is sufficient, or that the exact-session/replay gates passed. The private test fixture was removed after capturing the sanitized evidence. No session file, transcript, machine path, credential, or raw runtime output is part of this report.
