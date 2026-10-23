# Python source layout (current status)

The current ownership map and dependency rules are maintained in
[`docs/architecture.md`](../docs/architecture.md). The package currently
contains the extracted `physics/`, `design/`, `evaluation.py`, and unified
`optimization/` owners, alongside legacy study, orchestration, IO, and report
paths whose individual disposition is tracked under R6.

The new `sawopt.cli` is synthetic/injected-only during R6. The older
`__main__.py`, stage-specific study callers, and safety/process helpers are not
implicitly retired by the new entry point; see
[`docs/plans/restructure_r6_ownership_20261023.md`](../docs/plans/restructure_r6_ownership_20261023.md)
for their caller and evidence disposition. Do not treat this file as an
independent architecture plan.
