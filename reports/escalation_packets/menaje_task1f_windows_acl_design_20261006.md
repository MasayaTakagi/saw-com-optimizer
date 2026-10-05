# Escalation Packet — Task 1F Windows Private-State Design

Date: 2026-10-06 (Asia/Tokyo)
Requested review target: `gpt-6-sol` (backend identity not independently exposed by the runtime)
Scope: bounded high-risk architecture/security judgment before implementation; no implementation requested.

## Fixed context

- Candidate: menaje Codex MCP Bridge v0.4.1, exact commit `8bb81b1b27745532b7bc2113bb00e66c43df3bbb`.
- Qualification branch: `codex/menaje-qualification`, baseline `2087f717a4e7323c423bcf170a2843218592086c`.
- `git ls-remote` reports upstream `HEAD`, `refs/heads/main`, and `refs/tags/v0.4.1` all at the pinned commit; no upstream equivalent fix is available on the observed default branch.
- Existing reproducible defect: first state open and `complete()` succeed; Windows lock mode reports `0666`; release leaves the lock; second open fails `State migration lock is unreadable`.
- The test Temp hierarchy grants inherited `CodexSandboxUsers: Modify, Synchronize` on the lock and SQLite database. This is a plausible security exposure, not evidence of access or breach.
- The default per-user `.codex-mcp-bridge` state path does not exist, so production-file ACLs have not been observed. The profile root ACL is protected and allows the user, SYSTEM, and Administrators full control with inheritance; a non-inheritable AppContainer ACE grants traverse only. `%LOCALAPPDATA%` is a different root and is not being treated as equivalent.
- Scope excludes Secure MCP Tunnel live tests, Task 2, dependency changes, SAW source, C2C, and upstream push.

## Candidate designs

1. **A — per-file Windows ACL validation.** Preserve POSIX `mode`/`uid` checks on POSIX. On Windows, inspect owner and allow ACEs by SID for the actual private metadata object; reject unknown allow ACEs, non-regular files, and reparse points. A path-based external ACL query may have TOCTOU risk unless the state root is independently trusted or validation is bound to the opened object.
2. **B — protected Windows state root.** Establish a DACL for current-user SID, SYSTEM, and Administrators when creating a qualification state root, verify existing roots and path components, and ensure metadata files inherit that boundary. Reject broad inherited or explicit file ACEs and reparse substitution. This relies on establishing parent-path protection and secure creation.
3. **C — separate Windows lock implementation.** Hold OS-level ownership to improve crash/restart lock semantics. This alone does not make SQLite or metadata private and may alter existing stale-owner and recovery behavior.

Provisional proposal in the qualification document: preserve POSIX behavior; combine A with the protected-root property of B; do not accept Windows mode `0666` as proof of privacy and do not skip private-state validation. Prefer an in-box Windows API/.NET route with stable SID/ACE data and no parsing of localized `icacls` output. Keep current token, live-owner, malformed/oversized, alias, and reparse invariants.

## Judgment requested

1. Is a local, maintainable A+B implementation feasible without a new npm dependency or broad lifecycle refactor?
2. Is using a built-in PowerShell/.NET ACL helper acceptable for the security boundary, or is its process/path TOCTOU and platform availability too weak? If not, what API/binding level is minimally required?
3. What minimum checks are needed to make ACL validation race-resistant, especially for a file replacement or reparse point between ACL lookup and `openSync`?
4. Should C be rejected as unnecessary for this failure, or does the stale-lock lifecycle require it?
5. Is a bounded upstream patch feasible enough to keep menaje as a candidate, given the conditions for an acceptable fix?

## Decision boundaries

No Windows security check may be skipped. POSIX checks must remain unchanged. Do not infer production ACLs from Temp. Do not add dependencies or change upstream source until this judgment and a failing TDD regression are recorded. No upstream push is authorized.
