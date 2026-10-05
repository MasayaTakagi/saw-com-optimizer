# Escalation Packet — Task 1H Lock Policy and Release Semantics

Date: 2026-10-06
Requester role: Luna root implementation agent
Requested reviewer: GPT-6 Sol
Review type: bounded high-risk lock design judgment; no implementation requested

## Context

Candidate v3 for menaje Codex MCP Bridge v0.4.1 was independently rejected at exact patch SHA-256 `2CCFEBAEA2CE6744E959A65A34BE779D5D1070C1F05470DCFBE7B22DA6B5765C`, against upstream base `8bb81b1b27745532b7bc2113bb00e66c43df3bbb`. The review identified a stale-lock read/decide/path-unlink race and a post-create ACL failure that can leave an empty lock. The user has now fixed the policy: the runtime must never automatically reclaim an existing lock. No native Windows coordination or identity-deletion mechanism is allowed in this task.

The intended `EEXIST` behavior is: safely inspect the existing lock when possible; reject a live owner as already owned; reject dead-PID/stale, malformed, oversized, ACL-invalid, wrong-type, reparse, unreadable, or uncertain locks with a recovery-required/security error. Do not unlink or replace. If `openSync("wx")` created a lock and post-create ACL verification then fails, close and fail; leave the lock and require offline manual recovery. No empty marker or malformed content gains automatic reclaim rights.

The current source also has two normal-release paths (`prepareStateDatabaseOpen` and `acquireStateMaintenanceLease`) which read the lock token, compare it, then call `rmSync(lockFile)`. The path unlink may delete a replacement inserted after the token check. The task requires us to preserve existing normal-release token semantics, not add a native mechanism, and report a release race if it exists.

## Judgment requested

1. Is replacing stale-owner reclaim with unconditional fail-closed behavior for every existing non-live-owner lock a sound minimal implementation of the user's policy? Identify any important distinction among valid-dead, malformed, ACL-invalid, wrong-type, reparse, and oversized locks.
2. Does the normal release sequence (`readPrivateJson` token check, followed by path-based `rmSync`) contain the same replacement race in a way that must block candidate v4? Is there any KISS mitigation within existing Node path APIs that preserves token semantics without identity-bound deletion, or should the race be reported unresolved?
3. Review the proposed regression matrix: dead PID unchanged/no ownership; deterministic replacement race; concurrent stale contenders; malformed/oversized/ACL-invalid/wrong-type/reparse; live owner; injected post-create ACL failure; normal release replacement; no runtime unlink of an existing lock; POSIX path unchanged. State minimum test assertions and whether deterministic hooks are needed.

This is judgment only. Do not implement, run tests, or claim that the candidate is accepted. Do not expand into POSIX or live qualification. Candidate v3 remains immutable and rejected.

## Constraints

- Preserve Windows private-state checks and POSIX checks.
- No stale lock is automatically reclaimed for any reason.
- Do not add native code, dependencies, daemons, heartbeat, or automatic recovery.
- Do not alter C2C, Task 2, Tunnel setup, production data, SAW numerical code, or Stage 4C.
- Candidate v4 must be a new exact patch identity and receive independent review after implementation.

## Judgment outcome

Sol judged unconditional fail-closed on every existing lock path to be the minimal sound implementation. A safely readable live PID remains an already-owned conflict; a valid dead PID is recovery-required; malformed, oversized, ACL-invalid, wrong-type, reparse, unreadable, and uncertain cases fail closed without deletion or replacement. If post-create ACL validation fails, close the descriptor, leave the lock, and require offline recovery.

Sol confirmed both normal-release paths have a real replacement race: after a token is validated, a different object can replace the lock path before `rmSync`, which can then delete the replacement. Existing Node path APIs provide no atomic compare-token-and-unlink; extra reads or rename do not close this race. Under the user's constraints, this remains an unresolved candidate-v4 blocker and must be reported, not concealed or addressed with native code.

Minimum deterministic regression points are before the old reclaim decision, after successful `wx` before ACL verification, and after token validation before release unlink in both release paths. Verify lock object/content unchanged, no stale contender gets ownership, created lock survives post-create ACL failure and blocks subsequent startup, and the release replacement is not silently deleted. Include malformed/oversized/ACL-invalid/wrong-type/reparse/uncertain and live owner cases; preserve POSIX behavior. Sol did not implement or test; backend identity was not independently verified.
