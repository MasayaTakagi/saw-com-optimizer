# HDO qualification record

**Interim status:** `READY_TO_CONTINUE_GATE_C` after Gate B2; Gate C and later gates are not run.
**Last updated:** 2026-10-06 (JST)

## Scope and intended role

- **Candidate:** `kkb-hub/hybrid-dev-orchestrator`
- **Qualification sandbox:** [`MasayaTakagi/hdo-qualification-sandbox`](https://github.com/MasayaTakagi/hdo-qualification-sandbox)
- **Intended role:** GitHub Issue → isolated worktree → Codex execution → validation/state/result packaging
- **HDO is not:** the planner, final reviewer, or SAW acceptance authority.
- **Decision authority:** ChatGPT Sol makes the final accept/reject decision from the GitHub review evidence.
- **Production status:** This qualification does not authorize installation or production use in `saw-com-optimizer`.

## Phase 0 — qualification sandbox

| Item | Recorded value |
|---|---|
| Repository | `MasayaTakagi/hdo-qualification-sandbox` |
| URL | <https://github.com/MasayaTakagi/hdo-qualification-sandbox> |
| Visibility | Private |
| Default branch | `main` |
| Initial commit SHA (repository creation) | `15cfc8ab366b45337e97cf3737c8e0ee9dad0cdc` |
| Phase 0 baseline commit SHA | `849da6bb17dd78b5712d97143cb28ce428d63cf9` |
| Created | `2026-10-06T12:19:49Z` (2026-10-06 JST) |
| Phase 0 baseline tree | `README.md`, `src/example.txt` (`before`), `tests/README.md` |
| Workflow / runner | No workflow files or runner registration at initial setup |

The sandbox contains no SAW source, COM model, experiment data, or credentials.
HDO execution, qualification issues, labels, branches, pull requests, runner,
and workflow work are reserved for this repository.

## Host snapshot before Gate B

These are initial observations, not a completed Gate B result.

| Component | Observation |
|---|---|
| Windows | Windows 10 Pro 25H2, build 26200.9550 (host information supplied for this qualification) |
| Node | `v24.19.0`; the current shell resolves the Codex-bundled Node runtime |
| npm | Not found on PATH; no npm executable was found beside the resolved Node binary or at the checked standard Node.js install paths |
| Git | `git version 2.55.0.windows.5` |
| GitHub CLI | `gh version 2.101.0 (2026-09-15)` |
| Codex CLI before Gate B resume | `codex-cli 0.160.0` |

### Authentication environment finding

`gh auth refresh` completed successfully in the app terminal. The same user,
`gh.exe`, and standard profile paths were used by the sandboxed subprocess, but
`gh auth status` there reported the keyring token as invalid. Outside the
workspace sandbox, that read-only check reported `MasayaTakagi` logged in via
the Windows keyring, and GitHub API reads/writes succeeded. Ordinary sandboxed
GitHub API calls also failed because the configured proxy at `127.0.0.1:9` was
unreachable. The cause is the execution boundary's restricted access to the
host keyring/network, not a failed user authentication. Do not record or print
token values. GitHub CLI operations requiring host credentials or network must
use the approved out-of-sandbox path when necessary. A host-side
`gh auth status` confirmed the `MasayaTakagi` account is authenticated; the
user did not need to repeat authentication.

## Gate tracker

Phase 0 and Phase 1 are complete. Gate A's conditions were cleared during the
Gate B resume. Gate B initially failed a focused Windows command-line boundary
test. Gate B2 assessed whether that edge failure affects the intended native
Codex path. The first smoke in the restricted Codex execution context was
inconclusive; the approved host-side read-only smoke later passed. Gate C and
later gates remain NOT_RUN.

## Gate A — upstream pin and supply chain

| Item | Finding |
|---|---|
| Upstream repository | `https://github.com/kkb-hub/hybrid-dev-orchestrator` (public) |
| Exact source pin | `f9b4b0923929223d218e8f69e8353a07155ce726` |
| Retrieval date | 2026-10-06 |
| Version at pin | `0.14.0` |
| Release / tag | No GitHub release or tag was present; pin is the signed `main` commit. |
| License | MIT |
| Node requirement | `>=24`; README names Windows 11 and Node.js 24 LTS. |
| Lockfile | `package-lock.json`, lockfileVersion 3; 28 locked package entries. |
| Runtime dependencies | `ajv`, `ajv-formats`, `koffi`; dev dependencies are TypeScript and Node types. |
| Root lifecycle scripts | None declared in `package.json`. |

The package lock's root version is `0.1.0` while `package.json` says `0.14.0`.
This metadata inconsistency is retained as a Gate B `npm ci` check; the lockfile
still pins the root dependencies. The project declares no `build` script and
`tsconfig.json` has `noEmit: true`, so a separate build step is not defined.

The only locked dependency marked with an install lifecycle is `koffi@3.2.1`,
the Windows Job Object FFI dependency. Its npm tarball SHA-512 matched the exact
lockfile integrity value. Its install script runs the package's bundled CNoke
prebuild check; it loads the platform binary if available and otherwise invokes
CMake to compile from the included source. Static inspection found no network
download in that lifecycle script. The Windows x64 optional binary is separately
version- and integrity-pinned. No lifecycle script was executed during Gate A.

Source review findings:

- The built-in Codex adapter invokes `codex exec --ephemeral`, reads its prompt
  from stdin, requests JSON/schema output, and writes `--output-last-message`.
  No `codex queue` invocation or queue dependency was found.
- Built-in sandbox values are limited to `read-only` and `workspace-write`;
  plan/review require read-only and implement/fix require workspace-write.
  Adapter-controlled CLI flags cannot be overridden with `extraArgs`. The
  built-in path does not select `danger-full-access` or a dangerous approval
  bypass.
- Runner child environments are built with a denylist before spawning Codex.
  `GH_TOKEN` and `GITHUB_TOKEN` are blocked explicitly; names ending in
  `_TOKEN`, `_SECRET`, `_PASSWORD`, or `_KEY` are blocked by default. The
  repository `.hdo/config.json` schema does not let an Issue author configure
  `passEnvironment`; repository-supplied GitHub control-plane credentials are
  rejected by config validation.
- GitHub operations use the `gh` CLI. Executables are spawned as argv arrays;
  `.cmd` handling uses a dedicated quoting layer instead of `shell: true`.
  Issue bodies are parsed as task fields and known validation gate IDs; the
  trusted `.hdo/project.json` is the only source of executable validation
  commands.
- Worktrees are created under the configured worktree root and integrity checks
  pin their root and base commit. Run artifacts include `run.json` and event
  records under the configured artifact root. Cleanup checks the configured
  root and refuses dirty worktrees unless `-Force` is explicit.
- Claiming uses managed GitHub issue comments with a lease and a best-effort
  winner check. Duplicate exclusion and stale-claim behavior remain unproven
  until Gate H.

**Gate A status: PASS.** The Gate B resume confirmed that `npm ci` accepts the
lockfile metadata and the pinned native dependency loads on this host. **HDO
source patches: NONE.**

## Gate B — Windows host preflight

The host registry reports Windows 10 Pro 25H2, build 26200.9550. The earlier
snapshot found that the Codex-bundled Node `v24.19.0` has no npm. Codex's runtime
was left untouched. For this resume, the official Node.js `v24.21.0` Windows
x64 ZIP was downloaded over HTTPS from
`https://nodejs.org/dist/v24.21.0/node-v24.21.0-win-x64.zip`; its SHA-256
matched the official `SHASUMS256.txt` entry:
`158f7685b44de51f6c0df1d153526cbcd3e1bc739a8dfc607721cef75de9e541`.
The portable archive, which includes npm, was extracted to
`C:\Users\sub\AppData\Local\hdo-qualification\node-v24.21.0-win-x64`.
System PATH was not changed; each validation process prepended this directory
only to its own PATH. Node resolved to `v24.21.0`, npm to `11.19.0`, while
Codex continued to resolve to its installed executable and reported
`codex-cli 0.160.1`. The original bundled Node still reports `v24.19.0`.

The pinned HDO checkout remained clean at
`f9b4b0923929223d218e8f69e8353a07155ce726`. Its package scripts are `typecheck`,
`test`, and `cli`; no separate build script exists. The first `npm ci` installed
the lockfile dependencies but npm 11 withheld the unreviewed `koffi@3.2.1`
install script. After Gate A's static review, a temporary external npm config
allowed only `koffi@3.2.1`; the second lockfile-based `npm ci` exited 0. That
temporary config was removed. `require('koffi')` loaded successfully and
`npm run typecheck` passed. No package/lockfile edits, HDO source patches, or
global installs were made.

Focused Windows/config/process/Codex-adapter/worktree tests were run from 15
selected test files: **241 passed, 1 failed**. The reproducible failure is
`src/process/runner.test.ts`, “an argument landing the REAL command line at
exactly 8191 characters runs to completion”. It expects exit 0 but the actual
`cmd.exe` process exits 255 with mojibake Japanese stderr; the test source
documents this failure mode as `command line too long`. The same test failed
when rerun alone. At the time, this `.cmd` shim boundary failure was classified
**A — real Windows runtime blocker**, and Gate B was rejected at commit
`401fad702d4722f429410b9b5e29f1697957ae73`.

Gate B2 confirmed that this exact test's behavior depends on the shim body near
the limit and measured the intended Codex adapter route well below the
boundary. The first doctor attempt from the restricted Codex execution context
was inconclusive because child-process creation returned `EPERM`; the host-side
finalization below resolved that limitation. No credential or Codex
implementation run was attempted.

**Gate B2 final status: B2_NON_MATERIAL_EDGE_FAILURE.** The original Gate B
failure remains recorded, with the operational condition that future Codex
configuration resolves to native `codex.exe` and does not rely on near-limit
`.cmd`/`.bat` invocations. No HDO source patch was made. Gates C–M remain
NOT_RUN. Codex runtime modified: NO. System PATH permanently modified: NO.
HDO source patches: NONE.

| Gate | Status | Notes |
|---|---|---|
| A — upstream pin / supply chain | PASS | Static review plus successful lockfile install and native dependency load closed the Gate A conditions. |
| B — Windows host preflight | PASS_WITH_CONDITIONS | Host-side doctor and child-process probes passed. Retain the reproduced near-limit `.cmd` edge condition; use native Codex and validation executables. |
| C — sandbox fixture setup | NOT_RUN | Only the Phase 0 minimal tree exists. |
| D — current Codex CLI compatibility | NOT_RUN | |
| E — local HDO Issue flow | NOT_RUN | |
| F — SAW workflow fit | NOT_RUN | |
| G — long-running / state semantics | NOT_RUN | |
| H — claim / duplicate control | NOT_RUN | |
| I — security boundary | NOT_RUN | |
| J — sandbox-only Windows runner | NOT_RUN | |
| K — GitHub Actions workflow | NOT_RUN | |
| L — automatic handoff | NOT_RUN | |
| M — runner fault tests | NOT_RUN | |

## Gate B2 — `cmd.exe` boundary materiality

**History:** Gate B initially rejected HDO under the original stop policy.
Gate B2 was added after independent review to determine whether the single
exact-boundary failure was material to the actual Codex execution path. The
original rejection at `401fad702d4722f429410b9b5e29f1697957ae73` is preserved.

### Resolved executable and adapter route

With the isolated Node directory prepended to this process's PATH only,
`where.exe codex` and `Get-Command codex -All` each found one candidate:
`C:\Users\sub\AppData\Local\OpenAI\Codex\bin\5ea220ae823df3d7\codex.exe`.
HDO's own Windows `resolveExecutable("codex")` resolved to that same native
`.exe` (type A); `codex --version` reported `codex-cli 0.160.1`. HDO routes
only `.cmd` and `.bat` executables through `cmd.exe`; this Codex executable
does not use that shim route.

The HDO default profile is `claude-only`. For measuring its shipped Codex
adapter, the pinned `config/examples/cloud-only.json` profile's
`codex-cloud-implementer` was used (`codex`, model `gpt-5.6-terra`, reasoning
`medium`, `workspace-write`). This is a measurement profile, not an enabled
qualification workflow.

The adapter data flow is:

- Prompt text → stdin; argv ends with `-`.
- JSON schema → `output.schema.json` → `--output-schema <path>`.
- Final message → `final.json` → `--output-last-message <path>`.
- Model and reasoning effort → argv (`--model`, `--config`).
- Dedicated worktree → argv (`--cd <worktree path>`).
- Invocation uses `codex exec --ephemeral --json --sandbox workspace-write`;
  no `codex queue` dependency was found.

An actual `runAgentStep` call with a fake process runner measured 1,000-,
10,000-, and 50,000-character prompts. Each prompt was supplied through the
stdin field; the 20 argv entries and their lengths stayed identical for all
three sizes. No Codex process or API call was made by this prompt-size check.

### Command-line measurements

Lengths below were generated by the pinned HDO `getCodexArguments()` and
`quoteMsvcrtArgument()` functions using the shipped implementer configuration.
They estimate the CreateProcess command line for the resolved native `.exe`;
the `cmd.exe` 8191-character limit does not apply to this primary route.

| Measurement | Baseline HDO paths | Conservative SAW paths |
|---|---:|---:|
| Executable path length | 70 | 70 |
| Argument count | 20 | 20 |
| Quoted command-line length | 633 | 800 |
| Margin to 8191 | 7558 | 7391 |

The conservative simulation used a long `.codex\worktrees\hdo-qualification-saw-filter-impedance-optimization...` worktree and matching long HDO artifact root, including both schema and final-message paths. Ordered argv character lengths were:
`4, 11, 20, 14, 6, 7, 5, 9, 15, 4, 133, 7, 13, 8, 31, 15, 195, 21, 187, 1`.
The worktree, schema, and final-message path entries account for the longer
lengths; prompt size does not.

HDO's executable resolver found native `.exe` paths for Codex, Git, and gh.
It found a `.cmd` for the isolated npm (`npm.cmd`, a representative 132-character
HDO command line exited 0 and returned npm `11.19.0`); `pytest` was unresolved
on the measured PATH. A SAW validation contract can select a native Python
executable and pass `-m pytest`, avoiding a pytest shim by configuration. Keep
future Codex runner configuration on the native `codex.exe` resolution and do
not rely on near-limit `.cmd` invocations.

### Boundary characterization

The small temporary `.cmd` wrapper succeeded at outer command-line lengths
8180, 8185, 8190, and 8191; HDO rejected 8192 before spawn. Repeating those
five lengths with the exact wrapper body from the upstream failing test gave
exit 255 at 8180, 8185, 8190, and 8191, while 8192 was rejected before spawn.
The wrapper body therefore affects the nested command passed to Node near the
limit; this is a reproducible upstream edge failure, not a safe general `.cmd`
boundary contract. No large loop or fuzzing was run.

### Initial restricted-context smoke (historical)

Correct HDO syntax was taken from `node src/cli/main.ts help`. `help` and
`config -RepositoryPath . -Config config/examples/cloud-only.json -Json` both
exited 0. `doctor -RepositoryPath . -Config config/examples/cloud-only.json
-DryRun -Json` exited 2 with `Failed to start command: node. EPERM: spawn EPERM`.
The error occurred at the optional `node --version` preflight check, before
GitHub authentication or validation-gate checks. A minimal child-process probe
from this same Codex execution context also got `EPERM` for Node, Git, gh,
Codex, and `cmd.exe`, indicating an execution-boundary limitation but not
identifying its source. That restricted-context doctor attempt was **FAIL /
incomplete**, not a host-side HDO result. It was superseded by the approved
host-side finalization below.

| Required record | Result |
|---|---|
| Current Codex command / type | `C:\Users\sub\AppData\Local\OpenAI\Codex\bin\5ea220ae823df3d7\codex.exe` / native `.exe` |
| Prompt / schema / output transport | stdin / file path / file path |
| Current / conservative command line | 633 / 800 characters |
| Conservative margin to 8191 | 7391 characters |
| Long prompt effect on argv | NONE |
| `.cmd` relevance to Codex | SECONDARY; native `.exe` is the primary route |
| Boundary samples | minimal wrapper: 8180–8191 pass, 8192 pre-spawn reject; upstream wrapper: 8180–8191 fail, 8192 pre-spawn reject |
| CLI smoke | FAIL / incomplete (`help` and `config` PASS; `doctor` blocked by `EPERM`) |
| Source patches | NONE |
| Materiality at this point | INCONCLUSIVE — restricted-context smoke could not distinguish host behavior from execution-boundary restrictions |

At this point the Gate B2 result was `B2_INCONCLUSIVE`; the later host-side
smoke finalized the result as recorded below. Gate C was not run.

## Gate B2 host-side finalization

The finalization used the approved host-side execution context with the
qualification Node directory prepended to this process's PATH only. No system
PATH change was made. Effective host tool paths and versions were:

| Tool | Effective path / version |
|---|---|
| Node | `C:\Users\sub\AppData\Local\hdo-qualification\node-v24.21.0-win-x64\node.exe` — `v24.21.0` |
| npm | `11.19.0` |
| Git | `C:\Program Files\Git\cmd\git.exe` — `2.55.0.windows.5` |
| gh | `C:\Users\sub\AppData\Local\Programs\GitHub CLI\bin\gh.exe` — `2.101.0` |
| Codex | `C:\Users\sub\AppData\Local\OpenAI\Codex\bin\5ea220ae823df3d7\codex.exe` — `0.160.1` |

The Node child-process probe passed for `node --version`, `git --version`,
`gh --version`, `codex --version`, and `cmd.exe /d /c exit 0`. `where.exe`
also found the Codex-bundled Node as a secondary candidate and three alternate
Git executables; the effective first Git resolution was the path above. No
credential values were read or displayed. GitHub authentication was not
repeated.

The pinned HDO checkout remained at
`f9b4b0923929223d218e8f69e8353a07155ce726` with a clean working tree before
and after the smoke. Using that checkout as the read-only `RepositoryPath`,
the CLI results were:

| Check | Result |
|---|---|
| HDO `help` | PASS, exit 0 |
| HDO `config -RepositoryPath <pinned checkout> -Config config/examples/cloud-only.json -Json` | PASS, exit 0; profile `cloud-only`, no warnings, repository config not loaded |
| HDO `doctor -RepositoryPath <pinned checkout> -Config config/examples/cloud-only.json -DryRun -Json` | PASS, exit 0; `ok=true`, `readOnly=true` |

Doctor checks passed for Node version, Git, gh, GitHub authentication, Git
repository, project contract, both validation-gate command resolutions, and
all four Codex runner command resolutions. Ollama and writable-path checks
were skipped as expected for this cloud-only read-only preflight. No Codex
implementation ran, no Issue was claimed, and no worktree was created.

**Failure class: NONE for the host-side smoke. Gate B2 final:
`B2_NON_MATERIAL_EDGE_FAILURE`.** The reproducible upstream `.cmd` near-limit
edge remains a condition, but the intended native Codex route measured 800
characters under the conservative SAW path simulation (7391 characters of
margin to 8191), with prompts sent on stdin. Keep Codex on native `codex.exe`,
avoid near-limit `.cmd`/`.bat` calls, and prefer native executables for SAW
validation commands. **Gate B: `PASS_WITH_CONDITIONS`. Gate C: NOT_RUN.**

## Qualification decision

**Final status:** `READY_TO_CONTINUE_GATE_C`.
**SAW Pilot authorized:** NO.
**Pinned HDO commit:** `f9b4b0923929223d218e8f69e8353a07155ce726` (`0.14.0`).
**HDO source patches:** NONE.

Local qualification through Gate B: PASS_WITH_CONDITIONS. GitHub Actions
automatic handoff: NOT_RUN. Self-hosted runner scope: sandbox-only runner not
registered. Residual condition: the pinned HDO `.cmd` shim has a reproduced
near-limit edge failure; the measured SAW Codex route uses native `codex.exe`
and remains far below that boundary. Gate C executed: NO. Current Codex CLI:
`0.160.1`. Isolated Node/npm: `v24.21.0` / `11.19.0`. `npm ci`: PASS.
Typecheck: PASS. Focused tests: FAIL (241/242; boundary edge). Host-side HDO
CLI smoke: PASS. HDO source patches: NONE. SAW Pilot authorized: NO.
