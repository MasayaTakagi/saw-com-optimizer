# Escalation Packet — Task 1R Windows State Lock

Date: 2026-10-06 (Asia/Tokyo)
Requested review target: `gpt-6-sol` (backend identity not independently exposed by the runtime)
Scope: bounded high-risk judgment only; no implementation requested.

## Context

The Task 1R qualification evaluates the unchanged menaje Codex MCP Bridge v0.4.1 at upstream commit `8bb81b1b27745532b7bc2113bb00e66c43df3bbb`. The qualification branch baseline is `codex/menaje-qualification` at `c430746b08334af2b1bbe8a74e9d8f671e92f283`. No upstream Bridge source, SAW source, or dependency was changed.

Seven selected Windows tests fail with `State migration lock is unreadable`. Source inspection found `readPrivateJson` rejects `(stat.mode & 0o077) !== 0`, while lock creation requests mode `0600`; Windows reports the created lock as `0666`. The release function catches read errors and leaves the lock in place.

## Reproduction and ACL evidence

A clean temporary directory was used with the pinned upstream `prepareStateDatabaseOpen()` path. First open plus `complete()` succeeded; the migration lock remained and reported mode `0666`; second open failed with `State migration lock is unreadable`. The temporary directory was removed after inspection.

The reproduced lock’s inherited ACL included `DESKTOP-9IPACE7\CodexSandboxUsers: Modify, Synchronize`, along with the user, SYSTEM, and Administrators. A failed-test SQLite database in the same Temp hierarchy had the same group ACE. The lock JSON field names were `acquiredAt`, `databaseFile`, `processId`, and `token`; values were not copied. Membership/effective access for another principal, access or disclosure, and ACLs on the actual per-user Bridge state path were not established.

## Judgment requested

1. Classify the failure as Windows test portability or runtime/product behavior.
2. Assess whether the inherited shared-sandbox group ACE changes the security characterization, separating established facts from plausible concerns.
3. State whether Task 1 may be positively qualified or Task 2 may proceed before a supported mitigation/fix and live tests.
4. Identify the minimum remaining evidence needed; do not recommend implementation or infer unobserved group membership or breach.

## Bounded judgment received

- The clean reproduction establishes an A-class Windows runtime defect: first open leaves a lock and the next open fails. Task 1 remains blocked regardless of any one-shot live success.
- A principal whose effective token includes `CodexSandboxUsers` could generally read, change, or delete a file covered by the observed `Modify` ACE. This creates a plausible confidentiality and integrity concern for the lock and a tampering/availability concern. It does not establish group membership, another user’s access, disclosure, or the sensitivity of the file contents. The Temp ACL does not prove the ACL on the database or other files under the intended state path.
- Before positive qualification, require a supported mitigation/fix that passes clean first-open, release, restart/second-open, and recovery checks; inspect effective ACLs on the lock, DB, and secret-bearing files; establish group trust boundary/membership from a separate principal; and assess lock contents. No implementation or dependency change was authorized.

## Qualification decision

Classify the seven lock-read failures as A and retain `TASK1_SECURITY_BLOCKED`. Keep the mode-only assertion classified B as a Windows test-portability failure, while treating actual Windows ACL privacy as unqualified pending the checks above. No upstream or SAW source changes were made.
