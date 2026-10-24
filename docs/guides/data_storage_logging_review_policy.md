# Data storage, logging, and review policy

This page is a navigation summary, not a run authorization or a separate
storage contract. The authoritative rules for scientific experiments,
historical preservation, the future-only R5 store/review schema, and all
required approvals are in [`../experiments.md`](../experiments.md).

## Current status

R5 raw storage (`sawopt.io.experiment_store`) and compact review export
(`sawopt.reporting.experiment_review`) are implemented and verified with
synthetic fixtures. They are not wired to a scientific optimizer or production
runner. R6's `sawopt` / `python -m sawopt.cli` path accepts strict synthetic
configuration and injected fixtures only; the separate legacy `python -m
sawopt` dispatcher is not a production interface. The retired Codex queue and
callback provide no active continuation or publishing path.

An issue, passing test, software work unit, or package-ready status does not
authorize COM/FE, optimizer qualification, a real SAW study, production work,
resume, or a changed scientific condition. Obtain the separate explicit owner
authorization required by `experiments.md` before any such operation.

## Storage and evidence boundaries

- Keep historical raw runs, checkpoints, manifests, frozen configurations,
  reports, and source identities immutable. Do not move, repair, migrate,
  delete, or resume them as routine restructuring.
- Any future R5 run requires the explicitly configured external
  `SAWOPT_DATA_ROOT`; rejected paths fail closed. Worktree/repository
  containment and active-run safety remain independent protections.
- Keep raw numerical data and recovery-heavy artifacts outside Git. Compact
  future review packages belong under the R5 path and schema documented in
  `experiments.md`; they do not replace raw preservation or independent review.
- Never infer completion, feasibility, acceptance, or successful publication
  from a missing artifact, historical status label, or package-integrity check.
  Report explicit statuses, violations, failures, and limits.
- Do not include secrets, private credentials, user-specific absolute paths, or
  full raw checkpoints/populations/caches in a review package.

For repository checkout and retained safety-tool details, use the
[worktree safety guide](worktree_safety.md). That guide's registry, path, PID,
lock, and worktree-removal protections remain safety owners; their existence
does not authorize or enable the retired legacy production launcher.

The former queue/callback lifecycle, Codex handoff, and old
`reports/experiment_reviews/...` procedure are historical only. See the
[retired post-run contract](postrun_review_contract.md) and the
[Issue #111 C2A disposition](../plans/issue111_r6c2a_legacy_surface_disposition_20261024.md).
