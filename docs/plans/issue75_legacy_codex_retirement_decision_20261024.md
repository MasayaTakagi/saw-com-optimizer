# Issue #75 — superseding Codex queue/callback retirement decision

**Decision date:** 2026-10-24 JST  
**Status:** `OWNER_POLICY_APPROVED / CODE_REMOVAL_NOT_YET_EXECUTED / RECONSTRUCTION_FIRST`  
**Owner authority:** [Issue #75 current binding decision](https://github.com/miyabimm/saw-com-optimizer/issues/75), with [parent #53](https://github.com/miyabimm/saw-com-optimizer/issues/53) and [R6-B #73](https://github.com/miyabimm/saw-com-optimizer/issues/73).

## 1. Changed requirement and precedence

The owner explicitly stated that legacy Codex queue/callback will **not be used in the future** and must be **fully removed as part of repository reconstruction, without waiting for a replacement session-resume feature**. This **supersedes only the prior retirement dependency** in R7 policy C, #73, #75, #77 and the #94 design requiring exact Pi/agent-session parity, real Pi qualification, or detached Worker/scientific same-run recovery **before removal of the old Codex code**. Those designs and proven synthetic/mock increments remain historically valid as bounded software evidence, but their future implementation is **not on the R6 retirement critical path**.

Unchanged constraints: no unapproved scientific COM/FE study or Q1 qualification; unchanged optimizer/COM equations, RNG, ranking, budgets and checkpoints; no rewriting old run manifests, raw data, historical execution fingerprints or scientific reports; no implicit execution on status/help/import; preserve the R7 A/B/D decisions on unsupported external Codex hooks, readable historical v1–v4 evidence and scientific provenance.

**Product acceptance choice:** the new architecture does **not** promise to continue a legacy Codex thread, hand off to Codex after a finished run, or reopen an old Codex callback session. Removing this obsolete *feature* is permitted without supplying feature parity. An optional future Pi exact-session adapter or result-driven workflow may be implemented later under its own owner approval, not as an R6 dependency.

## 2. Removal targets and mandatory dependency audit

| Target | Active callers and evidence constraints | Required final disposition |
|---|---|---|
| `src/sawopt/orchestration/codex_queue.py` | `orchestration/cli.py` queue default/preflight, `worker.py` post-run dispatch, `models.py` thread validation, `run_manager.py` claim/ACK/continuation records and dedicated tests. | **REMOVE active source and imports**, CLI choices/implicit queue default, exact-thread preflight and send/ACK handlers. Do not leave a dormant callable bridge or auto-prompt fallback. |
| `src/sawopt/orchestration/codex_callback.py` | CLI/worker imports and pre-v4 callback paths; Stage4B frozen computation fingerprint enumerates this source path. | **REMOVE active source and imports** after migrating remaining *historical provenance verification* to a pinned historic Git source/commit reference. Never rebaseline Stage4B execution source SHA. |
| Legacy `orchestration/`, `runtime/`, `__main__.py`, `studies/`, `reporting/`, scripts/config/tests/docs/hook policy | Process lifecycle, run safety, worktree protection, dynamic `study.type`, old publication and read-only status all share modules with Codex paths. External user-level hooks cannot be ruled out from repository search. | **PER-SYMBOL DISPOSITION**, not package-wide delete by name. Remove Codex-only glue; retain or move independently required safety/legacy-status/physical/qualification evidence by reviewed owner assignment. Unsupported old launch/resume must fail closed. |
| Old manifest v1–v4, queue delivery ledgers, review traces, Stage4B and Q1-A evidence | Historic run identity, source SHA, published reports and source-linked goldens need interpretation. | **READ-ONLY EVIDENCE**, no active Codex callback, no migration/rewrite/backfill, no fabricated success. Preserve exact previous source versions in immutable Git history and verified evidence refs. |

Do not infer that no active old run exists simply because the owner will not use the old mechanism again. Before deleting old dispatch paths, a separate owner-approved **bounded metadata-only active-run inventory** must check for current dependants. Never access live roots, credentials, private Pi sessions, raw/checkpoint payloads or mutate run state under this policy/document-only change. Any unknown active dependency is `STOP / OWNER_DISPOSITION_REQUIRED`, not a prerequisite to rebuild Pi continuity.

## 3. Staged reconstruction execution plan (NOT yet implementation authorization)

1. **R6-C0 — fixed caller/evidence matrix:** at current exact main HEAD, enumerate all static, dynamic/config/subprocess, CLI, hook, documentation and test references, and pin the historical Stage4B callback path/source/commit verification method. Classify each active or evidence-only symbol as `DELETE`, `MOVE/REPLACE`, `RETAIN_READ_ONLY`, or `STOP`. Audit current live-run assumptions without opening any live root until separately authorized. Note #58 off-device/missing historical payload uncertainties without claiming their resolution.
2. **R6-C1 — remove queue/callback dispatch:** separately reviewed smallest coherent non-scientific PR(s) remove the two old active modules, default queue setting, imports, runtime handoff/ACK delivery paths, agent-only config/tests/docs, and make old unsupported dispatch commands **explicitly rejected**. Preserve immutable historic records/source and retained manifest read-only parser/status behavior. No automatic Pi substitute is introduced.
3. **R6-C2 — complete remaining old-to-new module ownership:** disposition old dispatcher and old `core/problem/studies/reporting/orchestration/runtime` code by their actual callers. Keep the new synthetic CLI, Worker/SQLite synthetic contracts, R5, physics/design/evaluation/optimization owners and Q1-A public/leaf golden verifiers intact. Removing a dead source must not silently alter a supported scientific algorithm or numerical evaluation path.
4. **R7 final gate — verify and close:** no reachable Codex queue/callback in the supported active source tree, CLI/help/status/import cannot dispatch it, old manifest audit is read-only, frozen Stage4B/Q1-A scientific references remain resolvable, tests/import guards/goldens and full Haswell-pinned CI pass on exact final HEAD and merged main; independent review and traceable rollback. Only then close R6-C #75, R6 #71 and reconstruction #53 as appropriate.

Every source change needs its own scoped work order and reviewable Draft PR, with failed negative tests, exact touched paths, dependency disposition and rollback. This decision document authorizes **policy and planning only**, not Pi Code code changes, experiments, real Pi/Node/Bun launch, old-run inspection, live migration or irreversible data cleanup.

## 4. Independent future features — no longer retirement prerequisites

- Detached Worker ↔ optimizer/checkpoint/R5 integration: [#104](https://github.com/miyabimm/saw-com-optimizer/issues/104), plan only.
- Real Pi exact agent session and diagnostics: [#86](https://github.com/miyabimm/saw-com-optimizer/issues/86) / [#91](https://github.com/miyabimm/saw-com-optimizer/issues/91), unqualified/blocked.
- Result publication, fault diagnosis, Pi orchestration and next-run proposals: [#97–#102](https://github.com/miyabimm/saw-com-optimizer/issues/97), separately owner-scheduled, plan only.

**Closeout principle:** deleting old Codex session behavior is not the same as qualifying a successor. Mark only what was actually retired and verified; keep data/science authorizations distinct.
