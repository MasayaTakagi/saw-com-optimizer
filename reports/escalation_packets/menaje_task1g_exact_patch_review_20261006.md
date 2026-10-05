# Escalation Packet — Task 1G exact Windows patch review

Date: 2026-10-06 (Asia/Tokyo)
Requested review target: `gpt-6-sol` (runtime does not independently expose backend identity)
Request: independent security/code review of the exact frozen candidate patch. Review only; do not implement or modify files.

## Frozen candidate identity

- Upstream: menaje Codex MCP Bridge v0.4.1, base SHA `8bb81b1b27745532b7bc2113bb00e66c43df3bbb`.
- Qualification artifact: `reports/qualifications/menaje_task1g_v0.4.1_windows_acl_candidate.patch`.
- Stable patch ID: `214150f06169d3ba1aa70771fa72383e80e09e53`.
- Git blob SHA-1 of patch artifact: `dc35b30344ab2851cd8a203c6d6e3e2521913a44`.
- Patch SHA-256: `5a3b9ed31ceb9d53c72d5a58c12f5d33e4ac9b182f6db483e060711e6c07ee35`.
- Diffstat: 7 files changed, 564 insertions(+), 45 deletions(-); 41,702-byte patch.
- Changed files: `package.json`, `scripts/verify-private-state-acl.ps1`, `src/stateBackup.ts`, `src/stateDatabaseLifecycle.ts`, `test/stateDatabaseLifecycle.test.ts`, `test/stateSchemaMigration.test.ts`, `test/userSettings.test.ts`.
- The patch applies to the exact base above. The menaje public repository was not modified or pushed. No complete menaje source tree is included in the SAW repository.

## Context and scope

The patch addresses the Task 1R Windows runtime defect: first state open/complete leaves a migration lock because Node reports Windows mode bits as `0666`; a later open rejects it as unreadable. A Task 1F implementation also exposed and addressed a separate Windows backup-flush failure (`fsyncSync()` on `O_RDONLY` returns `EPERM`). The patch is local-only and not yet approved for use. Task 1G requires this review and POSIX regression before any live Tunnel/security test.

Implementation summary:

- POSIX mode/owner checks remain in their original branch; Windows validation uses an in-box PowerShell/.NET helper, SID/ACE checks, owner validation, path-component/reparse/object-type checks, and fails closed on missing or unknown state.
- Newly created sidecars inherit a profile-backed private root; verified paths are cached in-process. No separate Windows lock implementation or npm dependency is added.
- Windows backup snapshot flush opens `O_RDWR`; POSIX continues using `O_RDONLY`. Snapshot validation, no-follow flags where supported, bytes, and operation ordering remain unchanged.
- Test-only path helpers place private test state under the user profile on Windows so test state does not inherit the broad Temp `CodexSandboxUsers: Modify` ACE. The POSIX mode-bit assertion itself remains unchanged.

## Review questions

Independently inspect the exact patch and assess:

1. Whether the POSIX code path and security checks are unchanged.
2. Whether the Windows ACL branch fails closed; SID/owner/allow-ACE handling; inherited, deny, `InheritOnly`, Administrators, SYSTEM, and TrustedInstaller semantics.
3. Whether every path/reparse/object-type check and the verified-root argument sufficiently close ACL-probe/open TOCTOU and replacement races.
4. Whether cache invalidation assumptions are sound against the intended lower-trust threat model.
5. PowerShell invocation, command/argument injection, environment poisoning, module-path sanitization, helper packaging/runtime resolution, and fail-closed behavior.
6. Lock token mismatch, live/stale owner, restart, recovery, and competing-process behavior.
7. Whether the `O_RDWR` change is restricted to Windows and preserves backup bytes, validation, and error handling.
8. Any critical or major defect that must block live qualification.

Return exactly one disposition: `ACCEPT`, `ACCEPT_WITH_CONDITIONS`, or `REJECT`. List findings with severity, file/line, rationale, and mandatory conditions. Do not implement fixes. A clean local test run is not independent review and does not itself authorize the live tests.

## Existing local evidence (not a substitute for review)

- Native Windows focused lifecycle and schema migration suites: 29/29 pass, including reopen/restart, competing process, lock invariants, ACL-negative, reparse, migration/recovery, and backup byte-preservation checks.
- Native Windows `userSettings.test.ts`: 20/21 pass; all seven original A-class lock failures pass. The sole remaining failure is the known B-class POSIX `0600` mode-bit assertion.
- TypeScript check and patch whitespace checks pass. POSIX-host regression and live Tunnel qualification have not run.
