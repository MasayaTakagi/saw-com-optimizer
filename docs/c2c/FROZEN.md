# C2C freeze record

**Status:** FROZEN — suspended from normal project operation

**Effective date:** 2026-10-02

**Project dependency:** Removed

## Decision

C2C is frozen because runtime, endpoint tracking, and state-access behavior
remain operationally unqualified for dependable project use. This is an
operational decision, not a SAW optimization or scientific conclusion.

C2C is not required for progression of the SAW optimization roadmap. No
additional C2C investigation is required before Stage 4 work continues. The
project will use GitHub branches, commits, and pull requests for independent
ChatGPT repository review, as described in
[`../guides/github_review_workflow.md`](../guides/github_review_workflow.md).

Do not start the C2C runtime, run Doctor, send a queue request, call
`workspace_info`, resume a session, qualify a checkpoint, rebuild the runtime,
recreate a connector, or upgrade C2C as part of ordinary project work.

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

## Reactivation conditions

Reactivation requires a separate explicit user decision and a fresh,
project-independent qualification. At minimum, it must establish:

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

Do not use a SAW production experiment to qualify C2C. Do not restore C2C as
an active gate until the user separately approves reactivation after those
checks.

## Repository dependency audit

- The active `AGENTS.md` review and experiment gates now use GitHub and user
  acceptance; they do not require C2C PLAN, ACCEPT, Doctor, workspace access,
  session state, or queue operations.
- `docs/c2c/README.md`, `OPERATIONS.md`, `SECURITY_BASELINE.md`, and
  `UPGRADE_POLICY.md` are marked frozen historical references.
- `baseline.json`, historical reports, previous experiment review provenance,
  handoff records, `.c2cignore`, and C2C runtime/tests are retained. Runtime
  code and tests are not removed as part of this dependency change.
- The async orchestration guide documents the supported captured-session
  callback flow independently of C2C. Historical C2C-specific continuation
  evidence remains in the engineering decision register.
