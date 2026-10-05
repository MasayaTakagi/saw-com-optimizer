# menaje Codex MCP Bridge — Task 1 Qualification

Date: 2026-10-06 (Asia/Tokyo)
Scope: Task 1 preflight and pinned upstream review, Task 1R Windows failure classification, Task 1F local Windows fix feasibility, dependency reachability, and live qualification readiness.

## Final decision

TASK1_SECURITY_BLOCKED

Task 1R re-ran the selected Windows suite against the unchanged pinned v0.4.1 checkout: 50 passed and 15 failed. All 15 failures are individually classified below. A clean isolated Windows reproduction confirmed an A-class state-lock runtime defect. Task 1F applied a local-only Windows state-boundary patch in the exact pinned clone; focused state/migration tests pass, the seven original A-class settings failures now pass, and the one remaining settings-file failure is the already-classified B-class POSIX mode assertion. The proposed fix remains conditional and is not part of an upstream release or an independently accepted patch. The observed test-temp lock and database inherited `CodexSandboxUsers: Modify`; that is a plausible confidentiality/integrity concern, not evidence of access or breach. ACLs were separately inspected on qualification-only profile-backed state files; see Task 1F evidence below.

The official OpenAI tunnel-client v0.0.15 binary was integrity-verified and its version/help commands succeeded. The Task 1 baseline had no private Tunnel configuration or Bridge runtime. Task 1F did not inspect credential values or run a Tunnel/live Bridge test. No live security gate passed. Dependency advisories were assessed by path and reachability; their moderate severity alone is not treated as a blocker. Task 2 remains unauthorized because the pinned release still has the state-lock defect and the required live gates are incomplete. Do not use another transport or API billing mode to bypass Tunnel prerequisites.

Upstream Bridge branch/tag modifications: 0; no upstream push. Local pinned-clone Task 1F patch: 7 files (6 tracked plus a new helper). SAW source-code modifications: 0. Dependency changes: 0.

A separate source-review concern remains: upstream explicitly says project roots constrain the starting directory and are not OS-level isolation. Filesystem escape and prompt-injection tests therefore need a dedicated Windows user, VM, or equivalent disposable isolation before any later SAW access.

## Purpose and scope

Evaluate menaje/codex-mcp-bridge-for-chatgpt as a future candidate to replace C2C in the SAW filter impedance optimization project. This is an evaluation, not an adoption decision.

Expected benefits to evaluate:

- Remove Cloudflare Quick Tunnel dependency.
- Remove codex queue dependency.
- Simplify routine restart and recovery.
- Improve suitability for long-running work, subject to Task 2 stability tests.
- Keep ChatGPT planning and review separate from Codex execution.

This task does not run fault injection, long jobs, workspace-write development, a production-like SAW run, source changes to the upstream Bridge, C2C migration/removal, adoption, or Bridge commit/push workflow qualification.

## Candidate identity

- Upstream: https://github.com/menaje/codex-mcp-bridge-for-chatgpt
- Latest stable release observed on 2026-10-05: v0.4.1
- Exact tag commit: 8bb81b1b27745532b7bc2113bb00e66c43df3bbb
- Pin method: read-only git ls-remote for refs/tags/v0.4.1, then clone and verify the exact commit. No moving latest reference was used.
- Source checkout: C:/Users/sub/AppData/Local/Temp/menaje-task1-upstream-v0.4.1
- Source checkout baseline: detached HEAD at the pinned commit. Task 1F later added a local-only, uncommitted feasibility patch in this clone; the public upstream tag/branch was not changed.
- Release page: https://github.com/menaje/codex-mcp-bridge-for-chatgpt/releases/tag/v0.4.1
- Upstream modifications: 0.

The candidate identity must remain unchanged during Task 1. Any upstream update requires a new qualification record.

## Architecture

ChatGPT
→ OpenAI Secure MCP Tunnel
→ Codex MCP Bridge
→ Codex App Server
→ explicitly registered qualification fixture

The upstream secure launcher is intended to use a loopback server and an OpenAI-managed outbound Tunnel connection. No Quick Tunnel, Named Tunnel, custom domain, direct public endpoint, or codex queue fallback is allowed.

## Trust boundaries

Treat each as a distinct boundary:

1. ChatGPT conversation and model-visible tool responses.
2. OpenAI Secure MCP Tunnel control plane and Tunnel access grants.
3. Bridge process, operator policy, MCP parser, and logs.
4. Codex App Server process and its authenticated ChatGPT account.
5. Codex sandbox and approval policy.
6. The one registered qualification fixture root.
7. Windows user account and all other filesystem paths.
8. Tunnel runtime key and private Bridge configuration.
9. Bridge SQLite database, model catalog/cache, and other private state.

The Bridge policy is not an operating-system boundary. The upstream security model explicitly recommends a separate OS user, container, or VM for sensitive code.

## Required qualification policy

| Setting | Required value |
| --- | --- |
| Transport | OpenAI Secure MCP Tunnel only |
| Registered projects | One qualification fixture only |
| Sandbox | read-only |
| Access strategy | read-only |
| Approval policy | on-request |
| Approval reviewer | user |
| Workspace write | disabled |
| danger-full-access | disabled and never enabled |
| Max concurrent jobs | 1 |
| Upstream pool size | 1 |
| Secret scan | enabled |
| Project choice | explicit; no default or fuzzy fallback |
| Billing | authenticated ChatGPT plan; no automatic API-key fallback |

The pinned .env.example differs from this required policy: it defaults the access strategy to adaptive and the operator job ceiling to 100. If execution becomes possible, explicitly override these with read-only and 1. Keep both write-enabling variables unset:

- CODEX_MCP_BRIDGE_ALLOW_WRITE
- CODEX_MCP_BRIDGE_ALLOW_DANGER_FULL_ACCESS

The Bridge must not be configured to run against the SAW repository, a parent directory containing multiple repositories, production data, or a Stage 4C artifact.

## Explicit prohibitions

- danger-full-access.
- Cloudflare Quick Tunnel or Named Tunnel.
- Custom domain or public inbound listener.
- codex queue.
- Credentials in the SAW repository, fixture repository, Git-tracked directories, or run artifacts.
- Secret values in stdout, stderr, logs, SQLite model-visible fields, MCP responses, Git, or test snapshots.
- Automatic API billing fallback.
- Arbitrary cwd, project fallback, fuzzy project matching, or a parent directory as the registered root.
- Enabling workspace-write for this Task.
- Changing, disabling, or migrating C2C.
- Concurrent C2C and menaje runtime activity in one workspace.

## Phase 0 — Environment preflight

| Item | Observation |
| --- | --- |
| Original repository root | C:/Users/sub/Documents/ChatGPT/saw-com-optimizer |
| Original branch and HEAD | main, a28cfa5194f68cfd4b2222b85c8a6d2ea5e5928d |
| Original branch relation | origin/main was 13 commits ahead when checked |
| Original working tree | No changes reported; Git warned that several ignored temporary test directories were inaccessible, so ignored-path inventory was incomplete |
| Managed worktrees before qualification | stage4c-confirmatory-protocol at 4201f1bc0a14d46af4f63b15c54507215ec26f58; stage4c-production-20261005 at c52ba5873f4625d6426c79347793d08dfb9afa0a |
| Qualification managed worktree | C:/Users/sub/.codex/worktrees/menaje-qualification/saw-com-optimizer |
| Qualification branch and Task 1R base | codex/menaje-qualification at c430746b08334af2b1bbe8a74e9d8f671e92f283 |
| Windows environment | Native Windows PowerShell |
| Node.js | v24.19.0, resolved from the Codex bundled runtime path; no separate Node installation found in checked common locations |
| npm | Not available on PATH or at the checked common Node installation paths; npm 10.9.3 was fetched by exact registry integrity and used from a temporary directory outside all worktrees |
| Upstream Node requirement | package.json engines: Node.js >=22; release-manifest toolchain baseline: Node 22 and npm 10.9.3 |
| Codex CLI | codex-cli 0.160.0 |
| Upstream Codex relation | release-manifest test baseline is codex-cli 0.153.3; source compatibility checks probe the selected App Server protocol rather than enforcing a runtime version allowlist |
| Codex App Server | codex app-server --help succeeds; App Server startup/handshake and a task through the Bridge were not tested |
| Codex login | codex login status reports ChatGPT login; Bridge compatibility remains untested |
| tunnel-client | OpenAI official v0.0.15 Windows amd64 release verified: archive SHA-256 `3b53133a1e24d43f63088d843860cb1701a4c3ed6390de2e19f69089e43bddc1`; only `tunnel-client.exe` extracted to `C:/Users/sub/AppData/Local/Temp/menaje-task1-openai-tunnel-client-v0.0.15/`; binary SHA-256 `1946de55a038313a9b9b2458d05fe1719fa9cf1f20a94dd5f38fc26a98bfdd42`. `--version` and `help run` succeeded. `cloudflared.exe` was not extracted or run; no tunnel connection was initiated. |
| Tunnel runtime key and Tunnel ID | Not present in the inspected process environment; no secret values were read. User said they would configure these privately. |
| Bridge runtime config | Expected path C:/Users/sub/.config/codex-mcp-bridge/.env remains absent as of 2026-10-06. |
| Bridge state | Stable, candidate, and development default state files and models.json were absent at preflight |
| Bridge process | No matching menaje Bridge process observed |
| C2C conflict check | No matching process name was observed in the narrow process-name query. C2C runtime, configuration, and tools were not invoked or inspected because the project policy freezes C2C. |
| Secure MCP Tunnel access | Not established; runtime key, Tunnel ID, organization/workspace association, and ChatGPT developer-mode connection are prerequisites |
| Windows upstream support | The pinned README describes a generic Node.js server for Windows/Linux; the pinned setup guide has Windows PowerShell instructions |
| Tunnel requirements | OpenAI docs require Tunnel ID, runtime API key, an MCP server reachable by stdio or HTTP, outbound HTTPS to api.openai.com:443 or mtls.api.openai.com:443, plus ChatGPT Developer Mode and appropriate Tunnel access |
| Public tunnel-client release | OpenAI v0.0.15 Windows amd64 binary verified as above; no credential/profile was created and no network tunnel was started |
| Review artifact policy | This is not a production experiment; no raw run data or production artifact was created |

The qualification worktree is the retained `codex/menaje-qualification` branch at the Task 1R baseline SHA above, not the stale main checkout. The original checkout and Stage 4C worktrees were not modified.

## Private state and credentials

The pinned setup guide places the Tunnel configuration at:

- C:/Users/sub/.config/codex-mcp-bridge/.env

The pinned source uses a per-user SQLite authority under .codex-mcp-bridge. Stable uses state.sqlite; candidate and development use profiles/candidate/state.sqlite and profiles/development/state.sqlite. The default model catalog path is .codex-mcp-bridge/models.json.

For an isolated run, use an explicit state database and model catalog path under a qualification-only private directory outside every Git worktree and run-artifact directory. Do not select existing stable state. The expected credential values are CONTROL_PLANE_API_KEY and CONTROL_PLANE_TUNNEL_ID. Store only a runtime-scoped key; never use an admin credential.

No persistent Bridge state, runtime configuration, Tunnel credential, or Tunnel connection was created. The upstream tests created temporary state under Temp; the separate state-lock reproduction created only a temporary lock and removed its directory after inspection.

## Upstream source and supply-chain review

Static review and package checks were limited to the exact v0.4.1 checkout. Locked dependencies were installed in the external temporary clone with `npm ci --ignore-scripts --no-audit --no-fund`; npm lifecycle scripts were not run. `npm audit --json` was then run against the pinned lockfile. Neither operation modified upstream tracked files.

- package.json has no package-level preinstall, install, or postinstall script.
- package-lock.json pins packages to registry.npmjs.org tarballs with integrity hashes.
- Direct production dependencies pinned in the lock: @modelcontextprotocol/sdk 1.29.0, better-sqlite3 13.0.3, tar 7.5.22, and zod 4.4.3.
- The release manifest identifies MIT licensing and a test toolchain baseline of Node 22, npm 10.9.3, and codex-cli 0.153.3.
- Lockfile lifecycle-script flags occur for esbuild 0.28.1 and optional fsevents 2.3.3; fsevents is not a Windows dependency. No package lifecycle executable was run.
- The v0.4.1 release page describes generic npm archives with SHA-256 metadata. No release archive was downloaded.
- The full lockfile `npm audit --json` returned four moderate affected package nodes, zero high, and zero critical across 220 packages. `npm audit --omit=dev` returned two moderate production-tree package nodes (`fast-uri` and `ip-address`). These are npm package-node counts; Vitest and `@vitest/mocker` report the same underlying advisory. Severity alone does not block under Task 1R.
- `fast-uri@3.1.7` path: `@modelcontextprotocol/sdk@1.29.0 -> ajv-formats@3.0.1 -> ajv@8.20.0 -> fast-uri@3.1.7`. It is in the production dependency tree and the validator/schema path is loaded by the Bridge. The reviewed Bridge code uses it through Ajv schema/URI parsing; no Bridge host allowlist, destination authorization, or URL-fetch decision using the vulnerable normalization was found. The GHSA requires a case-sensitive host decision involving a scheme-relative reference. No practical Tunnel-to-sink route was identified in the pinned Bridge. Candidate status: conditionally acceptable on this reviewed path, not an automatic blocker; fix is `fast-uri >=3.1.8` in a separately qualified dependency update.
- `ip-address@10.5.0` path: `@modelcontextprotocol/sdk@1.29.0 -> express-rate-limit@8.5.2 -> ip-address@10.5.0`. It is present in the production dependency tree, but the SDK references it through OAuth/auth handler modules that the Bridge entry path does not import. No Bridge MCP-input path to the vulnerable IP classification, subnet, or diagnostic parser was found. Four reported `ip-address` advisories affect versions through 10.7.0; use `>=10.7.1` to cover those findings in a separately reviewed update. Candidate status: not reachable in the reviewed runtime path; no advisory-only block.
- `vitest@4.1.9` and `@vitest/mocker@4.1.9` are development/test dependencies. They share `GHSA-82fw-gwwq-j7x9` for path traversal/arbitrary file read through redirect mocks. These modules are not part of Bridge runtime deployment. The reported fix is Vitest `>=4.1.11`; no runtime block.
- No dependency was changed or refreshed. Dependency updates remain outside this qualification task and require a separately reviewed qualification.

## Advisories — dependency reachability

| Package | Dependency path | Runtime/dev | Reachable | Decision |
| --- | --- | --- | --- | --- |
| `fast-uri@3.1.7` | `@modelcontextprotocol/sdk@1.29.0 -> ajv-formats@3.0.1 -> ajv@8.20.0 -> fast-uri@3.1.7` | Production runtime tree | Validator/schema URI parsing is loaded. No vulnerable host-policy or fetch sink was found in the Bridge; no practical Secure Tunnel input-to-sink route was identified. | Conditional candidate; not blocked by severity alone. Separately qualify `>=3.1.8`. |
| `ip-address@10.5.0` | `@modelcontextprotocol/sdk@1.29.0 -> express-rate-limit@8.5.2 -> ip-address@10.5.0` | Production runtime tree, but auth-handler branch | Not loaded from the reviewed Bridge entry path; SDK OAuth/auth handlers containing the dependency are not imported. | Not reachable in the reviewed deployment path; no advisory-only block. If updated, use `>=10.7.1` for the listed advisories. |
| `vitest@4.1.9` | Root development dependency; same Vitest redirect-mock advisory | Development/test only | Not in Bridge runtime deployment. | No runtime block; reported fix `>=4.1.11` belongs in a separately reviewed dependency update. |
| `@vitest/mocker@4.1.9` | `vitest@4.1.9 -> @vitest/mocker@4.1.9` | Development/test only | Not in Bridge runtime deployment. | Same `GHSA-82fw-gwwq-j7x9` as Vitest; no runtime block. |

Relevant reviewed advisories:

- https://github.com/advisories/GHSA-frvp-7c67-39w9
- https://github.com/advisories/GHSA-q3j6-qgpj-74h6
- https://github.com/advisories/GHSA-v39h-62p7-jpjc
- https://github.com/advisories/GHSA-v2v4-37r5-5v8g
- https://github.com/advisories/GHSA-hrr3-gc8f-f4qj
- https://github.com/advisories/GHSA-rpw4-54j3-4h4q
- https://github.com/advisories/GHSA-2vr4-cq9g-pvrc
- https://github.com/advisories/GHSA-j6r3-76f7-8jcv
- https://github.com/advisories/GHSA-h3mg-xc3c-68pw
- https://github.com/advisories/GHSA-82fw-gwwq-j7x9

## Windows failures — selected upstream unit tests

The upstream test files for project registration, configuration, user settings, and execution policy were run on native Windows against exact v0.4.1 with Node.js 24.19.0 and npm 10.9.3. Invocation: `npm test -- test/projectRegistry.test.ts test/config.test.ts test/userSettings.test.ts test/executionPolicy.test.ts`. Result: 50 passed and 15 failed (65 total); command exit 1. The table records every failing test. No upstream source/test file or dependency was edited to make tests pass.

| Test | Classification | Security impact | Runtime impact | Decision |
| --- | --- | --- | --- | --- |
| `project registry > requires stored paths to retain their canonical identity`<br>Failure: `EPERM: operation not permitted, symlink ...\workspace -> ...\alias` | C — local environment/privilege limitation | Canonical identity/symlink check was not exercised; no bypass demonstrated. | Windows symlink creation was denied before assertions ran. | Environment-limited, not a product pass. Repeat only in disposable Windows isolation with symlink privilege; nested symlink/reparse behavior remains unqualified. |
| `config policy > starts without a second allowed-root registry`<br>Failure: POSIX `/` path regex did not match Windows `\` path | B — Windows test portability defect | No wider-root or policy bypass indicated by the observed path. | Windows path is emitted with native separators; test assumes POSIX spelling. | Test portability issue; Windows config behavior still needs an equivalent runtime check before Task 2. |
| `config policy > ignores retired automatic-policy model and effort seeds`<br>Failure: expected `/tmp/codex-mcp-bridge-test-models.json`, received `\tmp\codex-mcp-bridge-test-models.json` | B — Windows test portability defect | No security impact shown. | POSIX temporary-path literal is compared to a Windows-normalized path. | Test portability issue; no upstream test was changed. |
| `config policy > selects the build-stage profile by default and keeps explicit profiles isolated`<br>Failure: POSIX profile-path regex did not match Windows `\` separators | B — Windows test portability defect | Profile isolation semantics were not disproven. | Assertion is separator-specific. | Test portability issue; profile-selection runtime check remains in live gates. |
| `config policy > blocks sensitive-looking symlink names before delegation`<br>Failure: `EPERM` creating symlink `...\target -> ...\.env` | C — local environment/privilege limitation | Sensitive-name symlink preflight was not exercised; no bypass demonstrated. | Test stopped at Windows symlink creation. | Environment-limited, not a product pass. A safe Windows-native substitute is still required. |
| `central execution policy > carries the same policy through typed start, resume, and fork`<br>Failure: fake `fake-codex-app-server.mjs` could not be verified with `--version` | B — Windows test portability defect | Policy assertion was not reached; no policy bypass demonstrated. | Windows process launch does not execute this fake `.mjs` as a native binary. | Test harness portability issue; the runtime policy still needs live verification. |
| `central execution policy > carries the same policy through compatibility start, resume, and fork`<br>Failure: fake `fake-codex-app-server.mjs` could not be verified with `--version` | B — Windows test portability defect | Policy assertion was not reached; no policy bypass demonstrated. | Same fake executable launch incompatibility as the typed path. | Test harness portability issue; the runtime policy still needs live verification. |
| `user settings and project registry > validates and persists history retention while migrating legacy settings to thirty days`<br>Failure: `State migration lock is unreadable` | A — runtime/product defect | Private lock read rejects Windows metadata; observed inherited group Modify ACE makes lock confidentiality/integrity a plausible concern, not a confirmed breach. | First open leaves the lock; a later open fails. | Hard Task 1 block. Clean first-open/release/reopen/recovery must pass after a supported fix or mitigation. |
| `user settings and project registry > defaults new installations to durable conversations while retaining explicit and legacy hidden settings`<br>Failure: `State migration lock is unreadable` | A — runtime/product defect | Same lock confidentiality/integrity concern; no access or disclosure was established. | Startup/reopen is blocked by the stale lock. | Hard Task 1 block; same root cause and required evidence as above. |
| `user settings and project registry > persists inactive Ultra selections through restart and restores them when enabled`<br>Failure: `State migration lock is unreadable` | A — runtime/product defect | Same lock confidentiality/integrity concern; no access or disclosure was established. | Restart/reopen persistence path fails. | Hard Task 1 block; same root cause and required evidence as above. |
| `user settings and project registry > migrates the v2 preferred selection by removing the retired fallback`<br>Failure: `State migration lock is unreadable` | A — runtime/product defect | Same lock confidentiality/integrity concern; no access or disclosure was established. | State migration/reopen path fails. | Hard Task 1 block; same root cause and required evidence as above. |
| `user settings and project registry > removes a migrated model-only preference while preserving automatic policy`<br>Failure: `State migration lock is unreadable` | A — runtime/product defect | Same lock confidentiality/integrity concern; no access or disclosure was established. | State migration/reopen path fails. | Hard Task 1 block; same root cause and required evidence as above. |
| `user settings and project registry > ignores retired environment model seeds for an automatic policy`<br>Failure: `State migration lock is unreadable` | A — runtime/product defect | Same lock confidentiality/integrity concern; no access or disclosure was established. | State reopen path fails. | Hard Task 1 block; same root cause and required evidence as above. |
| `user settings and project registry > safely clamps but does not erase a saved full-access preference`<br>Failure: `State migration lock is unreadable` | A — runtime/product defect | Same lock confidentiality/integrity concern; no access or disclosure was established. | State reopen path fails. | Hard Task 1 block; same root cause and required evidence as above. |
| `user settings and project registry > persists ordinary settings separately from the project registry in SQLite`<br>Failure: expected POSIX mode 384 (`0600`), received 438 (`0666`) | B — Windows test portability defect, with ACL qualification pending | The mode assertion is not a Windows ACL test. The failed-test temp DB/lock inherited `CodexSandboxUsers: Modify`; this does not establish ACLs on the intended private state path. | SQLite operation completed; Node/Windows mode reporting does not match the POSIX assertion. | Classify the assertion as portability, but do not infer private Windows state. Before positive qualification inspect effective ACLs on the qualification lock, DB, and secret-bearing files under a separate principal. |

### State-lock root cause and bounded Windows reproduction

`writePrivateJson`/`acquireMigrationLock` request mode `0600`; `readPrivateJson` rejects when `(stat.mode & 0o077) !== 0`. In this Windows runtime the created lock reports mode `0666`. The lock release path catches that read failure and leaves the file in place. A clean, disposable Temp reproduction against the pinned source recorded: first `prepareStateDatabaseOpen()` plus `complete()` succeeded; the lock remained with reported mode `0666`; second open failed with `State migration lock is unreadable`. The temporary repro directory was removed after inspection.

The observed temp lock contained only the fields `acquiredAt`, `databaseFile`, `processId`, and `token` (values were not copied into the report). Its inherited ACL included `CodexSandboxUsers: Modify, Synchronize`, plus the owner, SYSTEM, and Administrators. A failed-test SQLite database in the same temp hierarchy had the same inherited group ACE. A principal with that group in its effective access token could generally read, alter, or delete those files. No evidence establishes that another principal belongs to that group, accessed the files, or disclosed data. These Temp ACLs do not prove the ACL on the intended per-user Bridge state path; effective access for that location and other sensitive files remains unqualified.

Bounded high-risk judgment: classify the lock behavior as A and block Task 1 independently of Tunnel success. Treat the group ACE as a plausible lock/database confidentiality and integrity concern, not a confirmed breach. See the packet and outcome in `reports/escalation_packets/menaje_task1r_windows_state_lock_20261006.md` and `reports/escalation_log.md`. No upstream fix or dependency patch was made.

### Task 1F Phase 1 — Windows private-state fix criteria

- Windows does not provide a trustworthy POSIX `stat.mode` private-file authority through this Node runtime; the `0666`-equivalent result cannot prove that a file is or is not private.
- POSIX and Windows private-state verification must be separate. Existing POSIX mode/owner checks remain unchanged. Windows private-state authority is the NTFS security descriptor/DACL, interpreted by SID and access rules rather than locale-dependent `icacls` text.
- The previous `CodexSandboxUsers: Modify` observation applies to a disposable Temp hierarchy. It is not evidence of the production state-path ACL. The current default per-user `.codex-mcp-bridge` directory and state files are absent. The profile root has a protected DACL for the user, SYSTEM, and Administrators, plus a non-inheritable AppContainer traverse ACE; this makes profile-root inheritance a candidate to test, not a substitute for inspecting the actual qualification state root and its files.
- Rejected design: skip the private-state check on Windows. Also rejected: accept mode `0666` without independently proving Windows ACL privacy.

Candidate designs for the minimal fix:

| Design | Security/correctness | Windows and restart behavior | Race resistance | Dependency / size / maintenance |
| --- | --- | --- | --- | --- |
| A. Per-file Windows ACL validation | Strong if the opened lock/status file and its owner/allow ACEs are inspected without following a reparse point; fail closed on unknown ACEs. | Correctly handles Windows DACL authority and preserves existing lock semantics. | A pathname-only ACL probe may race file replacement; needs same-object or trusted-parent reasoning. | No npm dependency if implemented with a supported OS API; runtime/API bridge may add complexity. |
| B. Establish and validate a protected state root; private files inherit it | Strong if root creation is protected, all parent path components are trusted, and explicit/broadened child ACLs are rejected. | Keeps the existing lock and restart protocol; new sidecars inherit an owner/SYSTEM/Admin-only boundary. | Better against untrusted principals when parent/root cannot be renamed or replaced; reparse and child ACL checks remain necessary. | Potentially small if Windows ACL setup/inspection uses a supported built-in API; requires safe handling of existing roots. |
| C. Separate Windows lock mechanism | An OS-held lock can avoid stale ownership metadata after process exit, but does not establish privacy for the DB/status/model metadata. | Could change restart and crash recovery semantics substantially. | Kernel ownership can help with stale-owner races, but named-object ACLs and stale sidecars still need a design. | Larger behavior change; no external dependency is automatically justified. |

Chosen direction after bounded high-risk review: retain POSIX checks and lock semantics; on Windows fail closed using owner/SID/ACE ACL checks for the full path, protected-root inheritance, and reparse/object-type checks. Do not add a separate lock mechanism. The implementation is limited to the local pinned clone for feasibility evidence; it is neither an upstream patch nor approved for production use.

### Task 1F — implementation and requalification result

Root cause confirmed: `readPrivateJson()` treated Windows `stat.mode` bits as a POSIX authority. The initial red first-open regression reproduced the defect before the implementation: first open and `complete()` left the lock and second open failed as unreadable.

Local candidate patch:

- Added `scripts/verify-private-state-acl.ps1`, using built-in PowerShell/.NET security descriptors and SID/ACE data. It walks and validates each path component, rejects untrusted owners, untrusted allow ACEs, null/missing DACLs, wrong object types, and reparse points, and fails closed when evidence is missing. Runtime invocation uses `-EncodedCommand`, a sanitized Windows PowerShell module path, no execution-policy override, and no npm dependency.
- `src/stateDatabaseLifecycle.ts` now uses the Windows ACL boundary for state database/private JSON/lock access, verifies/creates the private root before writing, skips POSIX mode/uid checks only on Windows, and caches checks only after the protected path boundary is verified. Existing POSIX checks and lock token/live-owner/recovery semantics are retained.
- Full migration tests exposed a separate Windows backup durability defect: `fsyncSync()` on an `O_RDONLY` descriptor returns `EPERM`. A bounded second review approved switching only the Windows snapshot descriptor to `O_RDWR`; POSIX remains `O_RDONLY`, and no file bytes are changed. Microsoft documents that `FlushFileBuffers` requires `GENERIC_WRITE` access ([FlushFileBuffers](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers)).
- Test fixtures that exercise private state use a profile-backed root on Windows instead of inheriting the broad Temp ACL. The one B-class assertion expecting POSIX `0600` mode bits was deliberately not rewritten in the settings suite; it remains classified as test portability.
- Patch size in the pinned local clone: 7 files total (6 tracked files plus the 98-line PowerShell helper); `git diff --check` is clean. The local diff has 556 insertions and 45 deletions including the helper. No dependency, MCP contract, policy, sandbox, Tunnel, SAW, or C2C changes were made.

Windows evidence and tests:

- Focused `stateDatabaseLifecycle.test.ts` and `stateSchemaMigration.test.ts`: 29/29 pass. Coverage includes first open/complete/lock removal/second open; separate-process reopen; separate-process contention while a live owner holds the lock; token mismatch; live/stale owner; malformed and oversized lock; directory and junction/reparse rejection; failed migration and maintenance-lease recovery; migration checkpoints/backup restore paths; Windows ACL-negative rejection; and snapshot flush with byte-for-byte unchanged backup contents.
- `userSettings.test.ts`: 20/21 pass. All seven original A-class state-lock failures pass. The sole remaining failure is the unchanged B-class assertion that Windows `stat.mode` equals POSIX `0600`.
- `tsc --noEmit -p tsconfig.json`: pass. `git diff --check`: pass. Vitest used the thread pool because this sandbox blocks fork workers; the native Windows tests ran with the required profile-root access.
- ACL evidence was collected from a disposable qualification root directly under `C:\Users\sub`, then the root was removed. The root, SQLite database, backup snapshot, migration lock, migration status, and state metadata had current-user ownership. Their allow ACEs granted Full Control only to the current user, SYSTEM, and Administrators; no `CodexSandboxUsers` ACE or other principal allow ACE was present. The resolved `CodexSandboxUsers` SID was absent from the current process token. This verifies the disposable profile-backed qualification boundary, not the absent default `.codex-mcp-bridge` path or a different account's effective token; no separate-principal access attempt was made.
- The original Temp hierarchy remains broader (`CodexSandboxUsers: Modify, Synchronize`) and is rejected as a private-state location. No evidence shows access or disclosure.
- POSIX runtime tests were not rerun on a POSIX host. Their implementation branches remain unchanged by the patch; that is still a condition for accepting or releasing a fix.

Feasibility judgment: `MENAJE_WINDOWS_FIX_FEASIBLE_WITH_CONDITIONS`. Keep menaje as a conditional candidate for a reviewed upstream fix or separately accepted mitigation. Do not treat the local patch as Task 1 qualification: the exact release remains affected, Task 1 live Tunnel/security gates remain unrun, the default state path has not been populated/qualified, and POSIX-host validation plus external review are outstanding. Task 2 remains unauthorized.

## Pinned source security findings

- Bridge binds to loopback by default; this was read in source, not verified by a running listener.
- New work requires an explicit registered project selector. Source tests cover missing selection, unknown references, stale revisions, renamed selectors, and archived projects. There is no sole/default project fallback.
- Per-call cwd and permission fields are excluded from the strict task contract. Source enforcement rejects workspace-write unless CODEX_MCP_BRIDGE_ALLOW_WRITE is enabled, and rejects danger-full-access unless CODEX_MCP_BRIDGE_ALLOW_DANGER_FULL_ACCESS is enabled.
- Approval defaults in config are on-request and user. Source documentation says the Bridge cannot independently prove a particular host approval happened.
- Project registration canonicalizes the selected starting directory and can enforce a legacy allowed-root ceiling if explicitly configured. The security guide cautions that an allowed-root check constrains the starting directory, not every path Codex may attempt to access.
- The security guide describes filename-only detection for common credential files. Source scanning detects names such as .env, .env.local, .npmrc, id_ed25519 and extensions .pem, .key, .p12, .pfx. It does not inspect file contents and does not recurse through directory symlinks.
- Source tests exist for the project registry, sensitive-file preflight, policy ceilings, task selector behavior, and request deduplication. Source tests are not evidence that this exact Windows environment passes.
- The upstream security guide states that bridge controls do not replace filesystem permissions or OS isolation. This means the user-requested root-escape, symlink/junction, and prompt-injection guarantees remain unproven until tested under a disposable Windows user/VM boundary.

## Phase 2 — Isolated fixture prepared

Fixture root:

C:/Users/sub/.codex/worktrees/menaje-qualification/saw-com-optimizer/qualification/menaje-fixture

Created only in the qualification managed worktree:

- README.md with the harmless prompt-injection test text.
- Empty placeholder README files under src/, tests/, and fixtures/.
- Dummy files under fixtures/secrets/: .env, .env.local, .npmrc, dummy.pem, dummy.key, dummy.p12, and id_ed25519.
- Every dummy secret-like value uses the unmistakable `FAKE_QUALIFICATION_ONLY_NOT_A_CREDENTIAL` marker; config-shaped files contain no real credential material.
- No real credential, experiment data, or executable fixture code is present.

The Bridge is not installed or configured, so this fixture has not been registered. Intended registration is exactly this root, not its parent. For a later prompt-injection test, the dummy sensitive filenames must first be removed from the active fixture or the secret preflight should correctly reject the task before Codex starts.

## Live qualification

An upstream source test being present does not count as a test result. No mandatory live Tunnel/Bridge runtime test below was executed.

| Test | Result | Evidence |
| --- | --- | --- |
| Secure Tunnel smoke | BLOCKED / not run | Task 1 baseline lacked private config, Tunnel ID/key, and ChatGPT Tunnel connection. Task 1F did not inspect credentials or start any tunnel. |
| Read-only Codex task through ChatGPT | BLOCKED / not run | Depends on Secure Tunnel setup; no Bridge or App Server task was started. |
| Bridge loopback bind | SOURCE ONLY | Pinned default is 127.0.0.1; no server was started. |
| Fixture-only registration | NOT RUN | Fixture prepared; no Bridge settings or registration. |
| Selected upstream Windows unit tests | BASELINE FAIL (50/65 passed; 15 individually classified) | Exact v0.4.1, Node 24.19.0/npm 10.9.3; detailed table above. Task 1F local-clone reruns are recorded below; the pinned release remains unchanged. |
| Absolute path escape | NOT RUN | Source rejects per-call cwd; no live task or filesystem probe. |
| Parent traversal | NOT RUN | No live project/sandbox boundary test. |
| Symlink escape | NOT RUN | Registry root is canonicalized; nested target access untested. |
| Windows junction/reparse escape | NOT RUN | No Windows Bridge runtime test. |
| Unknown/stale/renamed/archive/malformed project | UNIT TESTS RAN; LIVE BRIDGE TEST NOT RUN | Project-registry unit-test file was included in the selected Windows run; no project was registered in the Bridge. |
| Workspace-write escalation | SOURCE GUARD PRESENT; NOT RUN | Requires allow-write false at runtime and task probe. |
| danger-full-access escalation | SOURCE GUARD PRESENT; NOT RUN | Never enabled; no live task probe. |
| Approval/reviewer/arbitrary-cwd/operator-limit bypass | NOT RUN | No App Server task through ChatGPT. |
| Secret scan | LIVE SCAN NOT RUN | Fake filenames prepared; Bridge scanner could not be invoked without the Tunnel/runtime. Filename scan is not DLP. |
| Prompt injection | NOT RUN | Harmless hostile text is present in fixture README; not submitted to a model. |
| Replay/idempotency | SOURCE TESTS PRESENT; NOT RUN | Unit test covers identical retry and changed-payload request-ID reuse; no live replay was attempted. |
| Dependency/security advisory review | REVIEWED; no severity-only block | Full audit: four affected package nodes at moderate; production-only audit: fast-uri/ip-address; dependency paths and runtime call paths assessed in the advisory table above. No dependencies changed. |
| Credential leak check | NOT RUN | No credential was present in inspected process environment/config; no Bridge runtime logs or responses were generated to scan. |
| Quick Tunnel / Named Tunnel / custom domain / codex queue | NOT USED | No Bridge or alternate tunnel process was started. |

## Secret-scanning limitation

Secret scanning is a useful filename preflight, not complete DLP. It does not guarantee detection of credentials.json, tokens embedded in config.yaml, source-code secrets, Git history, or novel credential formats. A directory symlink is not followed by the source scanner. Do not infer filesystem isolation from a clean scan.

## Qualification gate and handoff

Task 1 is PASS only when the exact pinned release runs on Windows native, Secure MCP Tunnel reaches the Bridge, and every mandatory security test passes under the required read-only policy. An unexecuted or inconclusive test is not PASS.

- TASK1_SECURITY_QUALIFIED requires every mandatory item to pass with evidence.
- TASK1_SECURITY_QUALIFIED_WITH_CONDITIONS requires explicit conditions, risks, mitigations, and a justified decision that Task 2 may proceed.
- TASK1_SECURITY_BLOCKED applies when prerequisites are missing or a security boundary fails.

Current gate: BLOCKED. The local Task 1F patch clears the tested state-lock and migration regressions, but the exact pinned release is unchanged and still contains the defect. Tunnel status was not rechecked in Task 1F, and all live runtime/security tests remain incomplete. Advisory severity counts alone are not a block based on reviewed reachability. The profile-backed ACL evidence qualifies only the disposable Task 1F root; it is not the default `.codex-mcp-bridge` runtime state. Do not proceed to Task 2 from this result. Do not use the SAW repository or enable workspace-write.

## Remaining conditions before Task 2

- Land or otherwise accept a reviewed fix through a supported upstream release or a separately approved mitigation; the local feasibility patch alone does not clear the pinned release. Re-run first-open, release, separate-process reopen/contention, migration, and recovery checks against that accepted artifact.
- Qualify the actual configured `.codex-mcp-bridge` state root and files when the Bridge runtime is authorized. Task 1F inspected a disposable profile-backed state root; Temp remains unsuitable. No breach was established.
- Verify the user-private Secure MCP Tunnel setup using only non-secret readiness indicators, then run the required Tunnel/Bridge gates only when separately authorized. Do not disclose credential values.
- With the required read-only policy and fixture-only registration, execute every required live gate: Tunnel and loopback path; read-only ChatGPT-to-App-Server task; selector fail-closed cases; permission escalation; secret preflight; prompt-injection boundary; isolated absolute/parent/symlink/junction tests; and replay/idempotency. Record evidence for each.
- Replace the C-class symlink tests with safe Windows-native tests under disposable isolation. Validate the B-class Windows path/profile/config and fake-executable cases with an equivalent Windows-native runtime harness; do not edit the pinned upstream source or tests in this qualification.
- Keep Task 2 unauthorized until all required live tests pass and unresolved security-relevant runtime defects equal zero.

Upstream Bridge branch/tag modifications: 0; no upstream push. Local pinned-clone Task 1F patch: 7 files. SAW source-code modifications: 0. Dependency changes: 0.

## References

- menaje release v0.4.1: https://github.com/menaje/codex-mcp-bridge-for-chatgpt/releases/tag/v0.4.1
- menaje security model at v0.4.1: https://github.com/menaje/codex-mcp-bridge-for-chatgpt/blob/v0.4.1/docs/security.md
- OpenAI Secure MCP Tunnel: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- OpenAI tunnel-client v0.0.15 release: https://github.com/openai/tunnel-client/releases/tag/v0.0.15
- OpenAI MCP servers and approval behavior: https://developers.openai.com/api/docs/guides/tools-connectors-mcp

Final classification: `TASK1_SECURITY_BLOCKED`
