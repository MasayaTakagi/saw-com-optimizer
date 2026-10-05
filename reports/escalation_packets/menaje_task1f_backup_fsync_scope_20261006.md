# Escalation Packet — Task 1F Windows migration-backup fsync scope

Date: 2026-10-06 (Asia/Tokyo)
Requested review target: `gpt-6-sol` (backend identity is not independently exposed)
Request: bounded judgment on whether the newly exposed Windows migration-backup failure is within the authorized state-lock fix or must remain a separate blocker. No implementation requested.

## Fixed context

- Candidate: menaje Codex MCP Bridge v0.4.1 at `8bb81b1b27745532b7bc2113bb00e66c43df3bbb`.
- Task 1F scope: locally assess a minimal Windows private-state/lock-boundary fix; no upstream push, dependency changes, Task 2, Tunnel live test, SAW source, or C2C.
- The lock defect is independently reproduced: first `prepareStateDatabaseOpen()` and `complete()` leave a lock on Windows because Node reports a POSIX-like `0666`; the second open rejects it. The patch's Windows-only ACL helper has now allowed the simple first-open/release/reopen test and a two-process reopen test to pass in the profile-protected directory.
- TDD uses temporary qualification state under the user's profile because Task 1R observed a `CodexSandboxUsers: Modify` ACE on the Windows Temp hierarchy. No credential is used.

## Newly exposed independent failure

When state migration tests are run under the private profile path, several full migration/recovery cases stop in `src/stateBackup.ts` before reaching their intended checkpoint:

```ts
const descriptor = openSync(file, fsConstants.O_RDONLY | noFollow);
...
fsyncSync(descriptor);
```

Windows returns `EPERM: operation not permitted, fsync` at the read-only descriptor. This was masked in earlier runs because the original migration lock defect stopped the same tests before backup validation. The focused Task 1F patch has not modified `stateBackup.ts`.

## Candidate minimal change

If appropriate, use a writable read/write handle for the Windows backup flush while preserving POSIX flags and all snapshot validation/durability steps. This is a state-backup durability change, not a lock permission-check change; it expands the patch beyond the currently reviewed ACL/lock boundary.

## Judgment requested

1. Should the Windows read-only-handle `fsync` issue be fixed in this bounded Task 1F qualification, or held as a separate upstream defect and explicit blocker?
2. If included, is changing only the Windows snapshot descriptor from `O_RDONLY` to `O_RDWR` an acceptable minimal durability-preserving fix, with a targeted Windows regression, or is a different flush design required?
3. Can Task 1F conclude `MENAJE_WINDOWS_FIX_FEASIBLE_WITH_CONDITIONS` if the lock/ACL/reopen gates pass but full migration remains unverified due this separate failure?

No state-backup production code has been changed for this finding.
