# menaje Codex MCP Bridge — Task 1 Qualification

Date: 2026-10-05 (Asia/Tokyo)
Scope: Preflight, pinned upstream review, isolated fixture, read-only smoke, and security qualification only.

## Final decision

TASK1_SECURITY_BLOCKED

The mandatory live security gates were not run. The Windows environment has no tunnel-client, Secure MCP Tunnel runtime key, Tunnel ID, or ChatGPT Tunnel connection. A temporary, integrity-verified npm 10.9.3 runtime was used outside the repository to run the pinned upstream unit tests and audit. The audit reported four moderate advisories, and the selected upstream tests had Windows-specific failures. Do not treat source inspection or partial unit-test results as runtime qualification. Do not use another transport or API billing mode to bypass the missing Tunnel prerequisites.

A separate source-review concern also remains: upstream explicitly says project roots constrain the starting directory and are not OS-level isolation. Root-escape and prompt-injection tests therefore need a dedicated Windows user, VM, or equivalent disposable isolation before any later SAW access.

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
- Source checkout status: clean detached HEAD at the pinned commit; no upstream files were modified.
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
| Qualification branch and base | codex/menaje-qualification at c52ba5873f4625d6426c79347793d08dfb9afa0a, origin/main |
| Windows environment | Native Windows PowerShell |
| Node.js | v24.19.0, resolved from the Codex bundled runtime path; no separate Node installation found in checked common locations |
| npm | Not available on PATH or at the checked common Node installation paths; npm 10.9.3 was fetched by exact registry integrity and used from a temporary directory outside all worktrees |
| Upstream Node requirement | package.json engines: Node.js >=22; release-manifest toolchain baseline: Node 22 and npm 10.9.3 |
| Codex CLI | codex-cli 0.160.0 |
| Upstream Codex relation | release-manifest test baseline is codex-cli 0.153.3; source compatibility checks probe the selected App Server protocol rather than enforcing a runtime version allowlist |
| Codex App Server | codex app-server --help succeeds; App Server startup/handshake and a task through the Bridge were not tested |
| Codex login | codex login status reports ChatGPT login; Bridge compatibility remains untested |
| tunnel-client | Not found as a command; no matching tunnel-client process observed |
| Tunnel runtime key and Tunnel ID | Neither is set in the inspected process environment; no secret values were read |
| Bridge runtime config | Expected path C:/Users/sub/.config/codex-mcp-bridge/.env does not exist |
| Bridge state | Stable, candidate, and development default state files and models.json were absent at preflight |
| Bridge process | No matching menaje Bridge process observed |
| C2C conflict check | No matching process name was observed in the narrow process-name query. C2C runtime, configuration, and tools were not invoked or inspected because the project policy freezes C2C. |
| Secure MCP Tunnel access | Not established; runtime key, Tunnel ID, organization/workspace association, and ChatGPT developer-mode connection are prerequisites |
| Windows upstream support | The pinned README describes a generic Node.js server for Windows/Linux; the pinned setup guide has Windows PowerShell instructions |
| Tunnel requirements | OpenAI docs require Tunnel ID, runtime API key, an MCP server reachable by stdio or HTTP, outbound HTTPS to api.openai.com:443 or mtls.api.openai.com:443, plus ChatGPT Developer Mode and appropriate Tunnel access |
| Public tunnel-client release | v0.0.15 observed on the OpenAI tunnel-client releases page; no client installed |
| Review artifact policy | This is not a production experiment; no raw run data or production artifact was created |

The qualification worktree is based on origin/main, not the stale main checkout. The original checkout and Stage 4C worktrees were not modified.

## Private state and credentials

The pinned setup guide places the Tunnel configuration at:

- C:/Users/sub/.config/codex-mcp-bridge/.env

The pinned source uses a per-user SQLite authority under .codex-mcp-bridge. Stable uses state.sqlite; candidate and development use profiles/candidate/state.sqlite and profiles/development/state.sqlite. The default model catalog path is .codex-mcp-bridge/models.json.

For an isolated run, use an explicit state database and model catalog path under a qualification-only private directory outside every Git worktree and run-artifact directory. Do not select existing stable state. The expected credential values are CONTROL_PLANE_API_KEY and CONTROL_PLANE_TUNNEL_ID. Store only a runtime-scoped key; never use an admin credential.

No Bridge state, configuration, Tunnel credential, or Tunnel connection was created.

## Upstream source and supply-chain review

Static review and package checks were limited to the exact v0.4.1 checkout. Locked dependencies were installed in the external temporary clone with `npm ci --ignore-scripts --no-audit --no-fund`; npm lifecycle scripts were not run. `npm audit --json` was then run against the pinned lockfile. Neither operation modified upstream tracked files.

- package.json has no package-level preinstall, install, or postinstall script.
- package-lock.json pins packages to registry.npmjs.org tarballs with integrity hashes.
- Direct production dependencies pinned in the lock: @modelcontextprotocol/sdk 1.29.0, better-sqlite3 13.0.3, tar 7.5.22, and zod 4.4.3.
- The release manifest identifies MIT licensing and a test toolchain baseline of Node 22, npm 10.9.3, and codex-cli 0.153.3.
- Lockfile lifecycle-script flags occur for esbuild 0.28.1 and optional fsevents 2.3.3; fsevents is not a Windows dependency. No executable downloads were run.
- The v0.4.1 release page describes generic npm archives with SHA-256 metadata. No release archive was downloaded.
- The complete lockfile audit returned exit code 1: 4 moderate, 0 high, and 0 critical findings across 220 packages. Affected locked packages are `fast-uri` 3.1.7, `ip-address` 10.5.0, and `vitest`/`@vitest/mocker` 4.1.9. npm reports fixes available. Advisory fix thresholds vary: `fast-uri` is patched at 3.1.8, Vitest at 4.1.11, while `ip-address` advisories include affected ranges through 10.7.0, so 10.5.1 must not be assumed to cover every finding. The Vitest issue is in the test dependency tree; the others are also part of the resolved dependency graph. These are moderate findings, not proof of exploitability in this Bridge deployment, but they prevent a clean security qualification.
- No dependency was changed or refreshed; dependency updates are outside this preflight task and require a separately reviewed qualification.

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

## Selected upstream unit tests

The upstream test files for project registration, configuration, user settings, and execution policy were run on native Windows against the exact v0.4.1 checkout using Node.js 24.19.0 and npm 10.9.3. Invocation: `npm test -- test/projectRegistry.test.ts test/config.test.ts test/userSettings.test.ts test/executionPolicy.test.ts`. Result: 50 passed and 15 failed (65 total); the command exited nonzero. Failures include POSIX path-separator expectations, Windows symlink creation denied with `EPERM`, state-migration lock readability/database permission-mode assertions, and a test that tries to execute a fake `.mjs` Codex binary through a Windows process API. No upstream test or source file was edited to make the suite pass. These failures are a qualification blocker for Windows until resolved upstream or supported by a documented passing Windows test profile.

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

## Qualification results

An upstream source test being present does not count as a test result. No mandatory live Tunnel/Bridge runtime test below was executed.

| Test | Result | Evidence | Notes |
| --- | --- | --- | --- |
| Secure Tunnel smoke | BLOCKED / not run | No tunnel-client, Tunnel ID, runtime key, or ChatGPT Tunnel connection | No fallback used |
| Read-only Codex task through ChatGPT | BLOCKED / not run | Depends on Secure Tunnel setup | |
| Bridge loopback bind | SOURCE ONLY | Pinned default is 127.0.0.1; no server was started | |
| Fixture-only registration | NOT RUN | Fixture prepared; no Bridge settings or registration | |
| Selected upstream Windows unit tests | FAIL (50/65 passed) | Four selected files: project registry, config, user settings, execution policy; command exit 1 | Path-separator assumptions, symlink privilege, SQLite state-lock/permission assertions, fake executable launch incompatibility |
| Absolute path escape | NOT RUN | Source rejects per-call cwd; no live task | |
| Parent traversal | NOT RUN | No live project/sandbox boundary test | |
| Symlink escape | NOT RUN | Registry root is canonicalized; nested target access untested | |
| Windows junction/reparse escape | NOT RUN | No Windows Bridge runtime test | |
| Unknown/stale/renamed/archive/malformed project | UNIT TESTS RAN; LIVE BRIDGE TEST NOT RUN | Project-registry unit-test file was included in the selected Windows run | Aggregate suite failed; no project was registered in the Bridge |
| Workspace-write escalation | SOURCE GUARD PRESENT; NOT RUN | Requires allow-write false at runtime and task probe | |
| danger-full-access escalation | SOURCE GUARD PRESENT; NOT RUN | Never enabled; no live task probe | |
| Approval/reviewer/arbitrary-cwd/operator-limit bypass | NOT RUN | No App Server task through ChatGPT | |
| Secret scan | LIVE SCAN NOT RUN | Fake filenames prepared; Bridge scanner could not be invoked without the Tunnel/runtime | Filename scan is not DLP |
| Prompt injection | NOT RUN | Harmless hostile text is present in fixture README; not submitted to a model | |
| Replay/idempotency | SOURCE TESTS PRESENT; NOT RUN | Unit test covers identical retry and changed-payload request-ID reuse | |
| Dependency/security advisory review | FAIL | `npm audit --json` on exact pinned lock: 4 moderate, 0 high, 0 critical; fix available | Affected: fast-uri 3.1.7, ip-address 10.5.0, vitest/@vitest/mocker 4.1.9; no dependency changes made |
| Credential leak check | NOT RUN | No credential exists in this setup; no logs or responses generated | |
| Quick Tunnel / Named Tunnel / custom domain / codex queue | NOT USED | No Bridge or alternate tunnel process was started | |

## Secret-scanning limitation

Secret scanning is a useful filename preflight, not complete DLP. It does not guarantee detection of credentials.json, tokens embedded in config.yaml, source-code secrets, Git history, or novel credential formats. A directory symlink is not followed by the source scanner. Do not infer filesystem isolation from a clean scan.

## Qualification gate and handoff

Task 1 is PASS only when the exact pinned release runs on Windows native, Secure MCP Tunnel reaches the Bridge, and every mandatory security test passes under the required read-only policy. An unexecuted or inconclusive test is not PASS.

- TASK1_SECURITY_QUALIFIED requires every mandatory item to pass with evidence.
- TASK1_SECURITY_QUALIFIED_WITH_CONDITIONS requires explicit conditions, risks, mitigations, and a justified decision that Task 2 may proceed.
- TASK1_SECURITY_BLOCKED applies when prerequisites are missing or a security boundary fails.

Current gate: BLOCKED. Reasons: live Tunnel prerequisites and runtime tests are absent; selected upstream Windows unit tests have 15 failures; the pinned dependency audit has four moderate findings; and OS-level filesystem isolation/root-escape behavior remains untested. Do not proceed to Task 2 from this result. Do not use the SAW repository or enable workspace-write.

If Task 1 is later completed and accepted, Task 2 separately covers Bridge/Tunnel restart, network interruption, long-running jobs, completion recovery, and lost/duplicate jobs. Workspace-write and SAW project qualification belong to Task 3 in the staged plan and remain unauthorized.

## References

- menaje release v0.4.1: https://github.com/menaje/codex-mcp-bridge-for-chatgpt/releases/tag/v0.4.1
- menaje security model at v0.4.1: https://github.com/menaje/codex-mcp-bridge-for-chatgpt/blob/v0.4.1/docs/security.md
- OpenAI Secure MCP Tunnel: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- OpenAI MCP servers and approval behavior: https://developers.openai.com/api/docs/guides/tools-connectors-mcp
