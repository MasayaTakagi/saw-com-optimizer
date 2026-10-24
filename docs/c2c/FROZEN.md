# C2C freeze record

**Status:** RETIRED — historical archive only; no project-local C2C hook runtime

**Initial freeze date:** 2026-10-02

**Superseding retirement:** Issues #109/#111, 2026-10-24

**Project dependency:** Removed

## Decision

C2C is frozen because runtime, endpoint tracking, and state-access behavior
remain operationally unqualified for dependable project use. This is an
operational decision, not a SAW optimization or scientific conclusion.

C2C is not required for progression of the SAW optimization roadmap. The
project uses GitHub branches, commits, and pull requests for independent
review; Pi Code implements scoped software changes and stops at a Draft PR as
documented in the [current review workflow](../guides/github_review_workflow.md).

The former project-local `.codex` hook configuration, C2C state-access
preflight wrapper, and `.c2cignore` were removed under Issue #111. The old
Codex queue/callback transport and legacy Stage 4B/4C production entrypoints
were retired under Issue #109. Do not invoke C2C, Codex hooks, preflight
wrappers, queue/callback commands, or former orchestration procedures. No
user-level hook, external C2C checkout, or outside process was inspected or
changed; their state remains outside this repository disposition.

There is no active Codex/C2C production continuation contract. Historical
session, thread, callback, queue, and status values remain evidence only. The
current R5 raw/review APIs and R6 synthetic CLI/Worker have strictly scoped
software behavior; they are not production-runner or agent-session
replacements. This record changes no experiment authorization or scientific
status.

## Last recorded baseline and diagnosis

The retained approved C2C source baseline is version `0.1.3` at reviewed
commit `9663b88753e35c76796c5bce000293e0bd22cd9e`, as recorded in
[`baseline.json`](baseline.json). This metadata remains unchanged; it records
the last approved baseline and is not a claim that the service is currently
qualified.

The 2026-10-01 controlled diagnosis recorded
`C2C_ENDPOINT_TRACKING_INCONSISTENT`. A diagnostic Quick Tunnel fingerprint
changed, while Doctor reported `chatgptRepair.needed=false`. The controlled
`workspace_info` request was therefore not sent. No connector recreation was
attempted and no ChatGPT-to-workspace data-plane conclusion was made.

The recorded canonical baseline tunnel fingerprint was
`8901362d54872159`; the diagnostic deployment reported
`af506f34757d5935`; after restoring the canonical runtime, the final
fingerprint was `1b294fd1968a82ab`. The changed diagnostic endpoint was the
stop condition; these observations do not establish which endpoint ChatGPT
could reach.

The canonical runtime was restored from the reviewed source afterward. Its
final Doctor reported node, sandbox, workspace, bridge, MCP, OAuth, and tunnel
checks passing, with `chatgptRepair.needed=false`. The actual ChatGPT
connector endpoint was not independently inspected, and ChatGPT reachability
to the workspace was not established. A green Doctor result is limited to the
checks recorded in the diagnosis; it does not qualify end-to-end access.

The ordinary state-access probe returned `ACTIVE_SANDBOX_DENIED`; a targeted
probe under `desktop-9ipace7\sub` returned `PASS` with `USERPROFILE` and
Windows `UserProfile` both `C:\Users\sub`. This records different execution
boundary outcomes, not a general state-access guarantee.

The complete evidence and stop conditions are in
[`c2c_mcp_one_shot_live_diagnosis_2026-10-01.md`](../../reports/c2c_mcp_one_shot_live_diagnosis_2026-10-01.md).
Earlier C2C reviews and ACCEPT results, including the Stage 4A acceptance,
remain historical provenance and are not revoked or rewritten.

## Retained limitations

The following qualification was not completed in the last diagnosis:

- repeated Quick Tunnel endpoint stability cycles;
- a controlled `workspace_info` request and verified response;
- C2C state/session/record round-trip qualification;
- detached-child and queue end-to-end qualification;
- connector endpoint identity inspection.

The diagnosis did not identify the cause of the endpoint tracking behavior or
determine whether ChatGPT could reach the workspace. Do not infer either result
from Doctor's status.

## Archived reactivation criteria — not current authorization

The following criteria were recorded when C2C was frozen. They are not a
current project plan or approval to restore C2C, its hook/probe, or the retired
Codex transport. Any new proposal requires a separate owner decision and
independent review. The former local integration files were removed in Issues
#109/#111. The historical criteria were:

1. The canonical C2C version and reviewed source SHA, plus a current security
   review.
2. Runtime stability across repeated start/stop cycles.
3. Exact endpoint identity and a controlled request/response round trip to
   the intended workspace.
4. Read and write state-access behavior in the execution boundary that will
   run C2C, with the approved state root and fail-closed path checks.
5. Queue/request/response end-to-end behavior, including duplicate and
   ambiguous-delivery handling.
6. A small project-independent pilot and independent review of its evidence.

Do not use a SAW production experiment to qualify C2C. This archive does not
plan or authorize C2C reactivation; any future proposal requires a separate
owner decision and independent review.

## Repository dependency audit

- The active `AGENTS.md` review and experiment gates now use GitHub and user
  acceptance; they do not require C2C PLAN, ACCEPT, Doctor, workspace access,
  session state, or queue operations.
- `docs/c2c/README.md`, `OPERATIONS.md`, `SECURITY_BASELINE.md`, and
  `UPGRADE_POLICY.md` are marked frozen historical references.
- `baseline.json`, historical reports, prior experiment-review provenance,
  and handoff records remain unchanged. The project-local probe, hook
  container, `.c2cignore`, and dedicated test were removed under Issue #111.
  The [Issue #111 disposition](../plans/issue111_r6c2a_legacy_surface_disposition_20261024.md)
  records exact callers and the remaining out-of-scope safety owners.
- The async orchestration guide is a retirement notice, not a queue-native
  workflow. Historical captured-session and C2C continuation evidence remains
  preserved in old run records and the engineering decision register.
