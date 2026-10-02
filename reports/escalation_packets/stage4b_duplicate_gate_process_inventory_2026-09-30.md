# Escalation Packet — Stage 4B Duplicate Gate Process Inventory

## Decision requested

Provide bounded judgment on whether the currently available non-elevated
process evidence is sufficient to pass the Stage 4B no-duplicate production
gate, or whether this launch must stop as `BLOCKED_DUPLICATE_CHECK`. If another
read-only Windows process query is the simplest compliant proof, identify that
query. Do not propose elevation, ACL changes, broader writable roots, source
changes, or a production launch.

## Context

The Stage 4B production task requires proof of all three conditions before
launch: no production manifest, no `stage4b_launched=true` metadata, and no
active Stage 4B worker or optimizer. The target run directory is
`runs/stage4b-hybrid-topology-screening`. Launch is conditional on a new C2C
PLAN, a complete pre-launch packet, and a distinct final C2C authorization.
The requested production launch must happen exactly once, in queue mode; Stage
4C is prohibited.

## Current evidence

- Branch: `codex/production-queue-continuation`.
- HEAD and upstream HEAD: `e00e47a23076793cdd093edaf5f7c060365edcf9`.
- Working tree was clean at the start of this task.
- Target run directory is absent.
- A read-only scan found 21 `run_manifest.json` files and 20
  `run_source_metadata.json` files. Its only Stage 4B-related manifest is
  `runs/stage4b_prelaunch_qualification/orchestration-smoke-run/run_manifest.json`,
  schema v2, `experiment_name=orchestration_smoke`, with its run directory
  under the qualification folder. No Stage 4B production manifest was found.
- No `stage4b_launched: true` value was found in scanned run-source metadata.
- `Get-CimInstance Win32_Process` failed with Access Denied while attempting
  to inspect process command lines.
- A subsequent `Get-Process -Name python,pythonw` query returned zero
  processes. This enumerates process names and executable paths but provides
  no command lines; therefore it did not establish whether the zero count alone
  is sufficient under the project gate.
- `USERPROFILE` and the Windows `UserProfile` special folder both resolve to
  `C:\Users\sub`; the current effective user is
  `DESKTOP-9IPACE7\CodexSandboxOffline`.

## Failed attempts / guardrails

Two attempts were made to complete the duplicate check. The first scan command
did not execute because its embedded Python source retained literal newline
escapes. The corrected PowerShell scan completed the manifest and metadata
checks but its WMI process query was denied. No elevated or approval-retry
command was used. The project instruction requires Sol judgment after two
failed repair attempts for the same issue; do not make another process query
until this judgment is received.

No optimizer process, queue send, production launch, source/config/docs edit,
or commit has been made. Other preflight checks found the expected config hash
and schema-v2 computation fingerprint, the target study contract resolved as
expected, and the qualified Codex CLI path/version/`queue --help` options
matched the accepted baseline.

## Requested scope

Judge only the duplicate-gate evidence and safest next step. Do not implement
anything, authorize Stage 4B, evaluate optimizer science, or broaden the task.

## Judgment and follow-up evidence

The requested Sol judgment was received: the duplicate gate passes if the
read-only Python process enumeration completes without suppressed errors and
returns zero rows. Codex then ran the stricter query with `-ErrorAction Stop`;
it completed with zero `python` / `pythonw` processes. This resolves the
duplicate-process uncertainty, and the judgment does not authorize a launch.

The separate exact orchestration queue preflight did not pass. Its
`SHGetFolderPathW(CSIDL_PROFILE)` lookup returned HRESULT `0x80070002`
(`Windows UserProfile special folder is unavailable`), so no final C2C launch
authorization was requested and no production run was started.

## Stage 4B final pre-launch packet

This is the current evidence packet for C2C task `c2c_2e3f`, PLAN iteration
`0`. It is evidence for review, not launch authorization.

### Baseline and freshness

- Expected branch: `codex/production-queue-continuation`.
- HEAD and upstream HEAD at task start: `e00e47a23076793cdd093edaf5f7c060365edcf9`.
- The working tree was clean at task start; `git diff --check` passes after
  the required Sol escalation record. Current worktree changes are only
  `reports/escalation_log.md` and this escalation packet. No source/config/
  `docs/` file was edited and no commit was made.
- The accepted current computation fingerprint is unchanged:
  `1e2459ef95915898e3774580522f983ecd0525a85db652f6ac4aa2f28f1a0daa`
  (schema v2). Reporting fingerprint:
  `cc7eed86e2f42fdc4dd7b87bc447c0edbddc70f0619d692fd32455826c6579b5`.

### Configuration and resolved scientific contract

- Config: `configs/studies/hybrid_stage4b_comparison.yaml`.
- Current config SHA-256:
  `fd868c0194c37c502e85f5c5efd1fe0732a80a24e70d672ce5e0bea952e3a314`.
- Resolved contract: MLIT / `T1_SYMMETRIC_5IDT`, source/load `50/50 ohm`,
  topologies `D`, `P_D`, `D_P`, `P_D_P`, seeds `20260917` and `20260918`.
- Primary budget: 4,000 unique evaluations per topology/seed, 32,000 total.
  Dimension-normalized endpoints: D 4,000; P_D 5,200; D_P 5,200; P_D_P
  6,400; 41,600 total across both seeds. Dimensions: 10/13/13/16; initial
  populations: 180/234/234/288; L-SHADE schedule horizon 4,000.
- Study role is `screening_only`; no automatic topology promotion or
  elimination. Config's `production_launch_authorized: true` does not replace
  a fresh C2C final authorization.
- Accepted parity evidence: D-only maximum difference 0.0 on both the
  1,001-point search grid and 9,113-point common grid. Focused validation:
  116 passed and 11 subtests passed. Accepted queue qualification: one attempt,
  sender acknowledged, `RECEIVER_CONFIRMED`, no duplicate. Persistence-only
  hook evidence: capture-session 3 passed; CLI 16 passed; queue 16 passed plus
  2 subtests; orchestration 74 passed plus 11 subtests. These accepted results
  are historical qualification evidence and were not repeated.

### Thread, duplicate, and executable gates

- App-issued current Desktop thread ID and trusted runtime `CODEX_THREAD_ID`
  both equal `01a0f1e2-0312-7f00-a3a6-fcaa75ad4efc`. The runtime variable was
  checked independently; `current_session.json.session_id` was not used as
  queue identity.
- Proposed target run directory
  `runs/stage4b-hybrid-topology-screening` is absent. The scan found 21 run
  manifests and 20 source-metadata files; the only Stage 4B-related manifest
  is the schema-v2 orchestration-smoke run under
  `runs/stage4b_prelaunch_qualification/`. No `stage4b_launched=true` metadata
  was found. The Sol-reviewed, unelevated process enumeration completed with
  zero `python` / `pythonw` processes.
- Qualified CLI path exists:
  `C:\Users\sub\AppData\Local\OpenAI\Codex\bin\faa963e871dd422c\codex.exe`.
  Version is `codex-cli 0.158.0-alpha.2.1`; `codex queue --help` exits 0 and
  exposes explicit `--thread` and `--message`.
- The exact `run_codex_queue_preflight` function did not return PASS. Its
  `SHGetFolderPathW(CSIDL_PROFILE)` call returned HRESULT `0x80070002`, even
  though PowerShell's `USERPROFILE` and
  `Environment.SpecialFolder.UserProfile` both show `C:\Users\sub`. The
  effective account is `DESKTOP-9IPACE7\CodexSandboxOffline`, which also does
  not match the profile-directory basename `sub` required by the preflight.
  Therefore the queue sender identity gate is
  `BLOCKED_QUEUE_PREFLIGHT_IDENTITY`.

### Proposed command (not executed)

```powershell
.venv\Scripts\python.exe -m sawopt.orchestration.cli launch `
  --config configs/studies/hybrid_stage4b_comparison.yaml `
  --run-dir runs/stage4b-hybrid-topology-screening `
  --continuation-mode queue `
  --thread-id 01a0f1e2-0312-7f00-a3a6-fcaa75ad4efc `
  --c2c-task-id c2c_2e3f `
  --plan-iteration 0 `
  --next-expected-step "Verify Stage 4B durable results and exact-thread queue receipt; do not launch Stage 4C." `
  --codex-executable C:\Users\sub\AppData\Local\OpenAI\Codex\bin\faa963e871dd422c\codex.exe
```

This proposed command has no session-ID/session-file/callback flags. It was
not run because queue sender identity did not pass. No final
`AUTHORIZE_STAGE4B_PRODUCTION_QUEUE` was requested or received; no production
launch occurred and Stage 4C was not started.

### Independent C2C review disposition

C2C independently reviewed the workspace, Git state, packet, and queue-gate
evidence and returned `BLOCKED_QUEUE_PREFLIGHT_IDENTITY`. It explicitly
withheld `AUTHORIZE_STAGE4B_PRODUCTION_QUEUE`, confirmed that no launch
occurred, and required a fresh passing queue preflight plus a newly reviewed
prelaunch packet before any future authorization request. The local C2C
checkpoint is recorded as `BLOCKED`, waiting for the user to re-establish an
execution identity/environment that passes the unmodified queue preflight.
