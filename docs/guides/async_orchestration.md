# 非同期オーケストレーション — historical record only

> **廃止済み:** Merged PR #109 (Issue #108) retired the legacy Codex
> queue/callback and Stage 4B/4C production execution routes. Issue #111 also
> removes the remaining project-local hook/probe utilities. This page is not
> an operational guide.
> Do not use its former launch, resume, recovery, review, queue-confirmation,
> publication, production, or shakedown commands. No replacement continuation
> transport is provided.
>
> The previous command contract remains documented as historical evidence in
> [the Issue #106 inventory](../plans/issue106_r6c0_codex_removal_inventory_20261024.md)
> and [the Issue #75 retirement decision](../plans/issue75_legacy_codex_retirement_decision_20261024.md).
> The binding Issue #108 scope and fail-closed dispositions are in
> [the Issue #108 plan](../plans/issue108_r6c1_codex_removal_20261024.md)
> and [the Issue #111 C2A disposition](../plans/issue111_r6c2a_legacy_surface_disposition_20261024.md).

This document is intentionally limited to explaining why older asynchronous
orchestration instructions are unsupported. It does not document a current
launch or continuation workflow. Historical run manifests, reports, status
fields, and numerical evidence remain records; their presence does not mean
that a legacy operation is supported or that a recorded result was accepted.

The synthetic CLI/Worker is separate from this retired Codex transport. Its
software tests and independent process/storage safety behavior remain covered
by the current test suite; that does not authorize COM/FE/optimizer work or a
scientific study. Follow [`../experiments.md`](../experiments.md) and the
roadmap gates for any future experiment authorization.

For current implementation and independent review responsibilities, see the
[GitHub review workflow](github_review_workflow.md). For current project
contracts, use the [documentation index](../README.md).
