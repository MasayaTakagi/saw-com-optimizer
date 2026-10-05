# Escalation Packet — Task 1G CreateDirectories Ancestor Policy
Date: 2026-10-06
Requester role: Luna root implementation agent
Requested reviewer: GPT-6 Sol
Review type: bounded high-risk ACL policy judgment; no implementation requested

## Context

Task 1G is qualifying a frozen Windows private-state patch for menaje Codex MCP Bridge v0.4.1. The first frozen candidate was independently rejected. Sol's remediation judgment required the corrected candidate to include `CreateDirectories` (access mask `0x4`) in the ancestor mutation mask and add a negative ACL test.

Upstream base: `8bb81b1b27745532b7bc2113bb00e66c43df3bbb`.
Current corrected candidate artifact: `reports/qualifications/menaje_task1g_v0.4.1_windows_acl_candidate_v2.patch`.
Candidate SHA-256: `C570EA0E6329DA87017D4F773F04BF6BF40CA38A7ABCB669AB7F3CD432B9FBF3`.
The patch artifact is a source diff against the upstream base. It has not been accepted and is not eligible for live qualification.

## New Windows evidence

The updated helper now includes `0x4` in its mutation mask. On this Windows host, the ACL on `C:\` grants SID `S-1-5-11` (Authenticated Users) `CreateDirectories` (mask 4). The qualification state roots are under the current user's profile, but all normal absolute paths traverse this drive root.

The focused run used:
`node node_modules/vitest/vitest.mjs run test/stateDatabaseLifecycle.test.ts test/stateSchemaMigration.test.ts --maxWorkers=4`

TypeScript `tsc -p tsconfig.json --noEmit --incremental false` passed. Vitest reported 30 failed and 2 passed across the two files. The failures all stop in the first ACL preflight at `C:\` with:
`Private state path has an allow ACE outside the trusted SID boundary: C:\; S-1-5-11; 4.`
Therefore the run did not exercise deeper ACL checks or the new trusted PowerShell/module provenance checks. No live Tunnel or Task 2 gate was run.

A separate read-only diagnostic observed the pinned PowerShell executable and Security module both have valid Microsoft Windows Authenticode signatures, TrustedInstaller owner, and read/execute (not write) access for Users on this host. The runtime helper's corresponding check remains unexercised due the earlier `C:\` failure.

## Judgment requested

Should the ancestor policy keep `CreateDirectories` in the mutation mask but permit it only under this narrow condition:

- ACE grants no mutation bit other than `CreateDirectories`;
- the ACE is non-inheritable and not `InheritOnly`;
- the path component is an existing, independently verified directory;
- its next path component already exists and is verified as a non-reparse object;
- it is never the private-state root or the nearest existing parent of a missing tail;
- all other write/delete/ACL/owner changes remain rejected?

Rationale: `CreateDirectories` cannot replace an already existing child by itself. Requiring the next component to exist avoids allowing an untrusted principal to race creation of a missing path element. The private root and every child still receive their own ACL/reparse validation. The proposed behavior keeps the bit in the mutation policy and fails closed on missing descendants; it only tolerates the observed standard volume-root ACE for an already existing verified path.

Please assess whether this condition preserves the intended Windows path integrity and the mandatory `CreateDirectories` finding, and state any required counterexample tests. If not acceptable, advise whether Task 1 should remain blocked on this host or whether a safer bounded alternative exists. Do not implement changes.

## Constraints

- Do not use C2C, Task 2, the SAW source tree as a menaje runtime, or any live Tunnel path.
- Do not weaken POSIX checks.
- Do not propose changing global drive ACLs on the user's machine.
- Keep this exact candidate rejected until a new candidate passes the independent review.
- Stale-lock recovery design is still awaiting the user's explicit choice.
