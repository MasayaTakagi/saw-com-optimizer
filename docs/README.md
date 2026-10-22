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
  historical preservation, raw storage, and future review schema.

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
  and [R3 ownership/caller disposition](plans/restructure_r3_ownership_20261022.md)
  are records for the staged reconstruction. The R3 record is scoped to Issue
  #65's explicit authorization; it does not authorize R4, Q1 work, scientific
  changes, or new experiments.

## Legacy paths

[`project_roadmap.md`](project_roadmap.md) and
[`architecture_overview.md`](architecture_overview.md) are retained as
compatibility pointers to [roadmap.md](roadmap.md) and
[architecture.md](architecture.md), respectively. Older guides, handoffs,
agent procedures, and stage plans are historical or supporting material, not
independent current policy. Do not follow an old operational procedure unless
it is explicitly re-authorized and consistent with the current sources above.
