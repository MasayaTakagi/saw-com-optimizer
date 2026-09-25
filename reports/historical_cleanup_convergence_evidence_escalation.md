# Escalation Packet: Convergence Evidence Ownership

Date: 2026-09-25

## Decision requested

Review the proposed ownership move of checkpoint/convergence evidence derivation
from `sawopt.studies.convergence_evidence` to
`sawopt.optimization.convergence_evidence`. Determine whether this is the
smallest safe canonical location, whether current callers should all migrate
now, and what minimal parity checks should gate the move. Judgment only; do not
implement.

## Repository state

- Branch: `codex-historical-cleanup`
- Starting HEAD: `baed01c365a5a7d0f87ae03344475037d9e476b8`
- Cleanup freeze tag target: `444d3a430797d32d688f74bb76ffda615cddfba0`
- The supplied pre-deletion correction instructions explicitly prohibit
  historical bulk deletion and numerical changes in this pass.

## Current ownership and callers

`src/sawopt/studies/convergence_evidence.py` derives optimizer-independent
evidence from checkpoint telemetry and exports `EVIDENCE_FIELDS`,
`derive_checkpoint_evidence`, and `apply_checkpoint_evidence`.
`src/sawopt/studies/lshade_records.py` imports `apply_checkpoint_evidence`,
leaving a current reusable serialization module dependent on a Stage-oriented
study package. Other direct callers are historical study modules, including
`optimizer_ab.py`, `search_efficiency.py`, and Phase C / Stage 3.6 studies.

The proposed change moves the implementation unchanged to
`src/sawopt/optimization/convergence_evidence.py`, updates current reusable
callers, and may retain the old studies path as a temporary re-export until the
historical deletion phase.

## Constraints

- No change to output fields, missing-value semantics, thresholds, event
  matching, or serialized records.
- No optimizer or production run.
- Preserve historical modules for this pass.
- Prefer a bounded migration and tests over broad refactoring.

## Requested judgment

1. Is `optimization/convergence_evidence.py` an appropriate canonical owner?
2. Should historical callers be updated now or use a clearly temporary re-export?
3. Are representative fixture parity tests plus L-SHADE record serialization
   parity sufficient to gate the move?
