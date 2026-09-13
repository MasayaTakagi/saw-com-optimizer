"""Optimizer-independent convergence evidence derivation.

The search backends collect traces and event telemetry; this module turns that
telemetry into the small evidence contract consumed by convergence policy and
Stage 3.5 reports.  It deliberately preserves ``None`` when a required fact
cannot be established from the saved record.
"""
from __future__ import annotations

from typing import Any, Mapping

import numpy as np


EVIDENCE_FIELDS = (
    "grid_converged",
    "recovery_pending_confirmation",
    "boundary_pending_confirmation",
    "hard_bound_unresolved",
    "micro_polish_improvement",
    "fraction_of_budget_at_last_significant_improvement",
)


def _number(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _trace_primary(row: Mapping[str, Any]) -> float | None:
    if row.get("primary_metric") is not None:
        return _number(row.get("primary_metric"))
    rank_key = row.get("rank_key")
    if isinstance(rank_key, (list, tuple)) and len(rank_key) > 1:
        return _number(rank_key[1])
    return None


def _last_significant_fraction(trace: Any, budget: float) -> float | None:
    if not isinstance(trace, list) or not trace or budget <= 0:
        return None
    significant = []
    previous = None
    for row in trace:
        if not isinstance(row, Mapping):
            continue
        metric = _trace_primary(row)
        evaluation = _number(row.get("unique_evaluation"))
        if metric is None or evaluation is None:
            continue
        if previous is None:
            significant.append((evaluation, metric))
        else:
            improvement = previous - metric
            relative = improvement / max(abs(previous), np.finfo(float).tiny)
            if improvement >= 0.02 or relative >= 0.01:
                significant.append((evaluation, metric))
        previous = metric
    if not significant:
        return None
    return float(significant[-1][0] / budget)


def _event_at_checkpoint(record: Mapping[str, Any], current_budget: int | None) -> Mapping[str, Any] | None:
    events = record.get("frequency_grid_events")
    if not isinstance(events, list) or not events:
        return None
    if current_budget is None:
        return events[-1] if isinstance(events[-1], Mapping) else None
    matching = [
        event for event in events
        if isinstance(event, Mapping)
        and int(event.get("checkpoint_budget", event.get("budget", -1))) == int(current_budget)
    ]
    return matching[-1] if matching else (events[-1] if isinstance(events[-1], Mapping) else None)


def _event_bool(record: Mapping[str, Any], field: str) -> bool | None:
    value = record.get(field)
    if value is not None:
        return bool(value)
    return None


def derive_checkpoint_evidence(
    record: Mapping[str, Any],
    *,
    current_budget: int | None = None,
    terminal_budget: int | None = None,
) -> dict[str, Any]:
    """Derive evidence without inventing values for unavailable telemetry."""
    requested = current_budget or record.get("requested_unique_design_budget")
    budget = _number(requested) or 0.0
    terminal = terminal_budget or record.get("terminal_budget") or record.get(
        "population_schedule_terminal_budget"
    )
    terminal_value = _number(terminal)
    result: dict[str, Any] = {}

    grid = _event_bool(record, "grid_converged")
    if grid is None:
        event = _event_at_checkpoint(record, current_budget)
        if event is not None:
            if "grid_fixed" in event:
                grid = bool(event["grid_fixed"])
            elif "added_count" in event:
                grid = int(event.get("added_count", 0)) == 0
    result["grid_converged"] = grid

    recovery = _event_bool(record, "recovery_pending_confirmation")
    if recovery is None:
        events = record.get("recovery_events", record.get("stagnation_events"))
        if isinstance(events, list):
            recovery = any(
                isinstance(event, Mapping)
                and int(event.get("budget", event.get("checkpoint_budget", -1))) == int(current_budget or -1)
                for event in events
            )
    result["recovery_pending_confirmation"] = recovery

    boundary = _event_bool(record, "boundary_pending_confirmation")
    if boundary is None:
        events = record.get("boundary_events")
        if isinstance(events, list):
            boundary = any(
                isinstance(event, Mapping)
                and int(event.get("budget", event.get("checkpoint_budget", -1))) == int(current_budget or -1)
                and event.get("event") in {
                    "boundary_pressure", "bound_expansion", "elite_boundary_probe",
                }
                for event in events
            )
    result["boundary_pending_confirmation"] = boundary

    hard = _event_bool(record, "hard_bound_unresolved")
    if hard is None:
        reached = record.get("hard_bound_reached_by_variable")
        if isinstance(reached, Mapping):
            hard = bool(reached)
        else:
            events = record.get("boundary_events")
            if isinstance(events, list):
                hard = any(
                    isinstance(event, Mapping)
                    and event.get("event") == "hard_bound_limited"
                    for event in events
                )
    result["hard_bound_unresolved"] = hard

    micro = record.get("micro_polish_improvement")
    if micro is None:
        micro = record.get("best_candidate_polish_improvement")
    if micro is None:
        diagnostic = record.get("micro_polish") or record.get("best_candidate_polish")
        if isinstance(diagnostic, Mapping):
            micro = diagnostic.get("improvement")
    result["micro_polish_improvement"] = _number(micro)

    fraction = record.get("fraction_of_budget_at_last_significant_improvement")
    if fraction is None:
        fraction = _last_significant_fraction(record.get("best_so_far_trace"), budget)
    result["fraction_of_budget_at_last_significant_improvement"] = _number(fraction)
    result["current_budget"] = int(current_budget) if current_budget is not None else int(budget or 0)
    result["terminal_budget"] = int(terminal_value) if terminal_value is not None else None
    result["missing_fields"] = [field for field in EVIDENCE_FIELDS if result.get(field) is None]
    result["complete"] = not result["missing_fields"]
    return result


def apply_checkpoint_evidence(
    record: Mapping[str, Any],
    *,
    current_budget: int | None = None,
    terminal_budget: int | None = None,
) -> dict[str, Any]:
    """Return a record augmented with the derived evidence fields."""
    updated = dict(record)
    evidence = derive_checkpoint_evidence(
        updated, current_budget=current_budget, terminal_budget=terminal_budget
    )
    for field in EVIDENCE_FIELDS:
        updated[field] = evidence[field]
    updated["convergence_evidence_complete"] = bool(evidence["complete"])
    updated["convergence_evidence_missing_fields"] = list(evidence["missing_fields"])
    return updated


__all__ = [
    "EVIDENCE_FIELDS",
    "apply_checkpoint_evidence",
    "derive_checkpoint_evidence",
]
