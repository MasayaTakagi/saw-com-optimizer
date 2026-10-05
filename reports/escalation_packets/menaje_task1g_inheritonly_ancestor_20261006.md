# Escalation Packet — Task 1G Existing-Path InheritOnly ACE Handling
Date: 2026-10-06
Requester role: Luna root implementation agent
Requested reviewer: GPT-6 Sol
Review type: bounded high-risk Windows ACL policy judgment; no implementation requested

## Context and exact candidate

Task 1G independently rejected the initial menaje v0.4.1 Windows candidate. The remediation candidate remains:
- Upstream base: `8bb81b1b27745532b7bc2113bb00e66c43df3bbb`
- Exact patch artifact: `reports/qualifications/menaje_task1g_v0.4.1_windows_acl_candidate_v2.patch`
- Patch SHA-256: `C570EA0E6329DA87017D4F773F04BF6BF40CA38A7ABCB669AB7F3CD432B9FBF3`

Sol's prior bounded judgment allowed a non-inheritable, CreateDirectories-only ACE on a non-private ancestor only when its next path component exists and is fully checked. It required rejection at the private root, before a missing child, for inheritable/CreateDirectories ACEs, and for any other mutation right.

## Additional native ACL evidence

After adding `0x4` to the mutation mask, the Windows lifecycle/migration suite stopped on a second standard `C:\` ACE:

- SID `S-1-5-11` (Authenticated Users)
- `FileSystemRights` numeric mask `0xE0010000`
- propagation `InheritOnly`
- inheritance `ContainerInherit, ObjectInherit`

This ACE does not grant access to the current `C:\` object. It is inheritable to children. The next component `C:\Users` already exists and is separately checked by the helper; the profile path and private root are subsequently checked component by component. The current helper stops at the volume root before reaching those checks, causing 30 failures and 2 passes in the focused Windows run. TypeScript checking passed. No POSIX/live/Tunnel/Task 2 test was run.

The same principle applies to other existing path ancestors: an `InheritOnly` ACE does not apply to the current ancestor. Its effects on an existing next component can be checked directly on that component. If the next component is missing, a future child could inherit the ACE, so the path must fail closed before creation. At the private root, any untrusted inheritable ACE remains a rejection.

## Judgment requested

Is it sound to handle an untrusted `InheritOnly` allow ACE on a non-private ancestor as follows?

- Permit traversal only if the immediate next path component already exists.
- Complete the same helper walk and require that next component (and every later component/target) pass full owner, DACL, object-type, and reparse checks before returning success.
- If any next component is missing, fail before creating it.
- Continue to reject all untrusted inheritable allow ACEs at the private root.
- Continue to reject any untrusted allow ACE that applies to the current ancestor and grants mutation rights.
- Preserve the previous stricter CreateDirectories rule: `CreateDirectories` itself gets the special allowance only when it is non-inheritable, is the only mutation right, and its next component exists and is fully verified.

Please assess whether this closes the standard volume-root path without weakening the protection against path replacement, and whether an InheritOnly ACE with generic write/delete bits can be safely ignored at an ancestor when the next existing child is independently validated. Specify counterexample tests or direct the candidate to remain blocked. Do not implement.

## Constraints

- Do not run C2C, Task 2, the Bridge, a Tunnel, or any live security gate.
- Do not alter global Windows ACLs.
- Do not change POSIX checks.
- This judgment does not settle stale-lock recovery; that user choice remains pending.
- Candidate v2 remains rejected until a later corrected candidate is independently reviewed.
