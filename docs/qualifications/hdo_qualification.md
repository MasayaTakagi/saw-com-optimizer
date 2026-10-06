# HDO qualification record

**Interim status:** `HDO_REJECTED` at Gate B; downstream gates are not run.
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
Gate B resume. Gate B then failed a focused Windows command-line boundary test;
later gates will not start after this Windows runtime finding.

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
when rerun alone. This is a Windows command-process boundary used by HDO's
`.cmd` shim handling, so it is classified **A — real Windows runtime blocker**
for this host, not an environment/network failure or an unrelated test.

**Gate B status: FAIL.** Stop qualification here; do not patch HDO to force a
pass. The read-only `help`/`config`/`doctor` preflight was not completed after
the Windows process-boundary failure. A preliminary `--help` invocation exited
2 because this CLI exposes `help` as a subcommand, not an option; it is not
counted as the CLI preflight. Gates C–M remain NOT_RUN. Codex runtime modified:
NO. System PATH permanently modified: NO. HDO source patches: NONE.

| Gate | Status | Notes |
|---|---|---|
| A — upstream pin / supply chain | PASS | Static review plus successful lockfile install and native dependency load closed the Gate A conditions. |
| B — Windows host preflight | FAIL | Classification A: the real `cmd.exe` 8191-character boundary test fails reproducibly on the current Windows host. |
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

## Qualification decision

**Final status:** `HDO_REJECTED` at Gate B.
**SAW Pilot authorized:** NO.
**Pinned HDO commit:** `f9b4b0923929223d218e8f69e8353a07155ce726` (`0.14.0`).
**HDO source patches:** NONE.

Local qualification: FAIL. GitHub Actions automatic handoff: NOT_RUN.
Self-hosted runner scope: sandbox-only runner not registered. Main blocker:
the pinned HDO process runner cannot execute a command at the documented
Windows `cmd.exe` 8191-character limit on this host. Gate C executed: NO.
Current Codex CLI: `0.160.1`. Isolated Node/npm: `v24.21.0` / `11.19.0`.
`npm ci`: PASS. Typecheck: PASS. Focused tests: FAIL (241/242). HDO CLI
preflight: NOT_RUN after the STOP condition. HDO source patches: NONE.
