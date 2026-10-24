# Documentation index

This is the sole index of current project documentation. For each topic, use
the canonical source below; old plans and detailed guides are retained only as
evidence unless linked here as supporting references.

## Current sources of truth

- [Roadmap](roadmap.md) — product goal, stage gates, current scientific status,
  and interpretation limits.
- [Architecture](architecture.md) — current package ownership, dependency
  direction, target layout, and staged module migration.
- [Physics and numerical conventions](physics.md) — implemented COM equations,
  units/signs, network/port conventions, metrics, grids, and analytic tests.
- [Development](development.md) — Docs-first workflow, risk-based tests, PR
  responsibilities, environment commands, and CI status.
- [Experiments and data](experiments.md) — authorization, frozen conditions,
  historical preservation, raw storage, and the review schema.

## Authoritative supporting records

These records are authoritative only for their stated subject and do not
supersede the five current sources above:

- [Stage 5A-2 Q1 qualification matrix](plans/stage5a2_q1_qualification_matrix.md)
  is the sole formal Q1-01…Q1-23 gate list.
- [Stage 5A-2 Q1 execution plan](plans/stage5a2_q1_execution_plan.md) defines
  work-unit dependencies; it does not pass gates or authorize Q1-B/C/D/E.
- [Q0 closeout](history/stage5a2_q0_closeout_20261021.md) records the accepted
  comparison protocol and distinct approval/closure events.
- [Current historical baseline](history/current_baseline.md),
  [experiment register](history/experiment_register.md), and stage closeouts
  retain reviewed historical findings and limitations; they are not a new
  implementation plan.
- [R0 preflight inventory](../reports/restructure/r0_preflight_inventory_20261022.md),
  [reconstruction design](plans/repository_restructure_decisions_20261022.md),
  [migration plan](plans/repository_restructure_migration_plan_20261022.md),
  [R3 ownership/caller disposition](plans/restructure_r3_ownership_20261022.md),
  [R4 optimizer ownership inventory](plans/restructure_r4_ownership_20261022.md),
  [R6 software/evidence inventory](plans/restructure_r6_ownership_20261023.md),
  [R7 architecture/CI audit proposal](plans/r7_architecture_ci_audit_20261023.md),
  [Issue #77 async/resume design](plans/issue77_async_resume_design_20261023.md),
  [Issue #80 synthetic task contract](plans/issue80_synthetic_task_contract_20261023.md),
  [Issue #82 synthetic-recovery contract](plans/issue82_synthetic_recovery_contract_20261023.md),
  [Issue #84 mock-only Pi-session contract](plans/issue84_pi_session_mock_contract.md),
  [Issue #94 R6-C migration/three-continuity design](plans/issue94_r6c_three_resume_migration_design_20261024.md),
  [Issue #96 N1 transaction/recovery contract](plans/issue96_n1_synthetic_transaction_recovery_20261024.md),
  and [Issue #75 Codex retirement policy (2026-10-24)](plans/issue75_legacy_codex_retirement_decision_20261024.md)
  record staged reconstruction work. The [Issue #106 C0 static caller/evidence inventory](plans/issue106_r6c0_codex_removal_inventory_20261024.md)
  records the preflight; its historical-fingerprint reconstruction stop gate is superseded by the owner-authorized
  [Issue #108 R6-C1 scope](plans/issue108_r6c1_codex_removal_20261024.md). The R3 and R4 records are scoped to
  Issues #65 and #67; R6 is scoped to Issue #71's software/synthetic-only
  authorization; R7 is an audit/CI evidence and owner-decision proposal under
  Issue #74; Issue #77 is a design proposal; Issue #80 authorizes only isolated
  synthetic PR-A implementation; Issue #82 authorizes only isolated synthetic
  countdown recovery and does not authorize scientific or Pi-session recovery;
  Issue #84 authorizes only an injected fake Pi-session adapter and does not
  authorize real Pi runtime/session use; Issue #94 records a docs-only/static
  design audit; Issue #96 authorizes only its bounded test-owned synthetic N1
  implementation and software verification. Neither issue authorizes legacy
  cutover, active-run inspection, real Pi runtime, or scientific work.
  The later owner decisions for Issues #75 and #108 authorize scoped removal of
  old Codex queue/callback behavior without Pi-session parity or historical
  Stage4B fingerprint reconstruction; implementation must stop at a Draft PR
  for independent review and retain frozen scientific evidence.
  Earlier R7/#77 replacement-prerequisite statements are historical where they
  conflict with that newer policy. No plan authorizes Q1 qualification, real
  experiments, or production runs.

## Legacy paths

[`project_roadmap.md`](project_roadmap.md) and
[`architecture_overview.md`](architecture_overview.md) are retained as
compatibility pointers to [roadmap.md](roadmap.md) and
[architecture.md](architecture.md), respectively. Older guides, handoffs,
agent procedures, and stage plans are historical or supporting material, not
independent current policy. Do not follow an old operational procedure unless
it is explicitly re-authorized and consistent with the current sources above.
