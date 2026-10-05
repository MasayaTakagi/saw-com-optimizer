# Escalation Packet — Task 1G Post-create ACL Failure Cleanup

Date: 2026-10-06
Requester role: Luna root implementation agent
Requested reviewer: GPT-6 Sol
Review type: bounded high-risk lock and Windows file-identity judgment; no implementation requested

## Context

Task 1G qualifies a Windows private-state patch for menaje Codex MCP Bridge v0.4.1. The candidate is an exact patch against upstream base `8bb81b1b27745532b7bc2113bb00e66c43df3bbb` (v0.4.1), with patch SHA-256 `2CCFEBAEA2CE6744E959A65A34BE779D5D1070C1F05470DCFBE7B22DA6B5765C`. Independent review rejected it and blocked live qualification.

The reviewer found a major failure path in `src/stateDatabaseLifecycle.ts`: migration-lock acquisition calls `openSync(file, "wx")`, then validates the new lock's Windows ACL. If ACL validation fails or times out, the catch closes the descriptor and rethrows, leaving the newly created empty lock. A later process encounters `EEXIST`, cannot parse that lock, and fails closed indefinitely unless it is manually removed.

The relevant operations are path based. A naive `rmSync(file)` in the catch could delete a replacement lock created after the descriptor is closed or after the path is swapped. The profile-backed parent should be protected from lower-trust principals, but the proposed fix must still establish why cleanup is bound to the exact file created by this attempt and cannot erase another owner's lock.

The independent reviewer separately identified a stale-lock reclamation race: concurrent processes can inspect one dead owner, one can replace the file, and another can then delete the replacement. This is an independent blocker and is not the judgment requested here. The user has already been asked to choose the stale-lock recovery policy; that choice remains pending. No lock semantics have been changed.

## Judgment requested

Assess the safest bounded handling for failure of the post-create Windows ACL check:

1. Is there a reliable Windows/Node mechanism available here to remove the just-created lock by open-handle/file identity, without path-based deletion of a replacement? If so, state the identity and race invariants and minimum counterexample tests.
2. If not, is leaving a deliberately identifiable empty lock and failing closed preferable to path cleanup? Specify a safe/manual recovery invariant and how the implementation can distinguish its own incomplete creation from another malformed or active lock without weakening ownership checks.
3. Would preflighting a path's inherited creation ACL before `openSync("wx")` solve the problem, or can it only reduce the failure probability because the post-create object DACL still must be verified?

Please make a bounded design judgment, not an implementation. Keep the stale-lock race separate and do not treat this candidate as accepted. Backend model identity or internal reasoning effort must not be claimed as independently verified unless the runtime exposes it.

## Constraints

- Do not use C2C, Task 2, a live Tunnel, the SAW source tree as a menaje runtime, or any production data.
- Do not weaken POSIX behavior or ACL checks.
- Do not change stale-lock semantics without the user's pending policy decision.
- Any implementation creates a new patch identity and requires independent review plus affected Windows tests before live qualification.

## Judgment outcome

Sol's bounded judgment: the current Node path APIs cannot safely identity-delete the file created by `openSync("wx")`; path-based unlink and stat/file-ID comparison followed by unlink retain a replacement race. The immediate safe behavior is to close and fail closed, leaving an identifiable diagnostic condition that does not grant the empty/malformed lock automatic reclaim rights. Manual recovery must verify there is no live owner or competing creator, inspect the private parent and exact lock object, and remove it only under controlled exclusive maintenance; preserve it if uncertain. ACL preflight can reduce the failure probability but cannot replace post-create object verification.

Before accepting a future remediation, test post-create ACL denial and timeout, replacement by a valid active lock, malformed/forged empty markers, preflight-pass plus post-create-fail, concurrent creation, and unchanged POSIX behavior. Native handle-based deletion would require a separate design and validation of original-file identity across rename/swap, sharing violations, and process termination. This judgment does not resolve the independent stale-lock reclamation race or the user's pending recovery-policy choice. The candidate remains rejected.
