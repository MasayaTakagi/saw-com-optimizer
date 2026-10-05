# Escalation Packet — Task 1G rejected patch remediation decision

Date: 2026-10-06 (Asia/Tokyo)
Requested review target: `gpt-6-sol` (backend identity is not independently exposed)
Request: bounded high-risk design judgment on whether the frozen candidate can be corrected safely and narrowly, or should remain rejected. Review only; do not implement.

## Exact rejected candidate

- menaje v0.4.1 base SHA: `8bb81b1b27745532b7bc2113bb00e66c43df3bbb`.
- Candidate patch: `reports/qualifications/menaje_task1g_v0.4.1_windows_acl_candidate.patch`.
- Stable patch ID: `214150f06169d3ba1aa70771fa72383e80e09e53`.
- Patch SHA-256: `5a3b9ed31ceb9d53c72d5a58c12f5d33e4ac9b182f6db483e060711e6c07ee35`.
- Independent patch-review disposition: `REJECT`; reviewer did not edit files or run tests.
- Candidate replay checkout: `C:\Users\sub\AppData\Local\Temp\menaje-task1g-candidate-5a3b9ed3`.

## Independent review findings

1. **Critical — inherited allow ACE can reach newly created private children.** The helper skips `InheritOnly` ACEs on a directory. Newly created files are then trusted from the cache without inspecting their ACL. Required: account for inheritable ACEs and validate the child ACL before writing/caching; reject parent inheritance that can expose private descendants.
2. **Major — environment-poisonable helper paths.** The PowerShell path uses `SystemRoot`, while its module search path uses `ProgramFiles`. Required: resolve and validate the OS executable/module independently of inherited environment values.
3. **Major — stale-lock reclamation race.** Two processes can both inspect one dead-owner lock; one may delete the other's newly created lock and both believe they own a lease. This race exists in the base implementation but is a required property for safe simultaneous restart. Required: make reclamation conditional on inspected file identity and demonstrate concurrent restart contention.
4. **Moderate — ancestor mask omits CreateDirectories.** The mutation mask omits `0x4`. Required: include the right and add a negative ACL regression.

The reviewer found POSIX permission branches preserved and the `O_RDWR` change Windows-only, but advised no live qualification until the ACL findings are corrected and reviewed.

## Judgment requested

- Is a safe bounded correction feasible without a broad state-lifecycle rewrite or new third-party dependency?
- What minimum Windows primitive is needed for race-safe stale-lock reclamation (for example, an OS-held mutex/lock, identity-bound delete, or another specific protocol)? Is preserving automatic stale-owner recovery required, or is explicit fail-closed manual recovery acceptable for this candidate?
- What exact trusted-source strategy is reasonable for locating the PowerShell executable and ACL module without trusting `SystemRoot`/`ProgramFiles` supplied by the process environment?
- What ACL rules must be rejected at the root to prevent inherited child ACEs, while still allowing the observed benign profile ancestors?
- If the answer requires replacing the Windows lock layer or adding a native dependency, is the fork maintenance cost unacceptable, or can menaje remain a conditional candidate?
- Recommend whether to remediate and submit a new candidate for review or stop with `REJECT` and keep Task 1 blocked.

Return bounded judgment and mandatory acceptance gates only. Do not modify candidate source. No POSIX runtime was available locally (WSL has no installed distribution); no CI or live gate has run. The `.env` path configured in the earlier handoff is absent. Tunnel, Bridge, App Server, Task 1 live security, and Task 2 have not been started.
