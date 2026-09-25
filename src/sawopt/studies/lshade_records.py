"""Serialization for reusable L-SHADE study checkpoint records."""
from __future__ import annotations

import copy
import time
from collections.abc import Mapping

import numpy as np

from ..optimization.convergence_evidence import apply_checkpoint_evidence


def clean_record(record):
    def clean(value):
        if isinstance(value, np.ndarray):
            return [clean(item) for item in value.tolist()]
        if isinstance(value, np.generic):
            return clean(value.item())
        if isinstance(value, float) and not np.isfinite(value):
            return None
        if isinstance(value, dict):
            return {str(key): clean(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(item) for item in value]
        return value
    return clean(record)

def serialize_lshade_record(backend, wiring, seed, budget, checkpoint_path,
                            frequency_events, started_wall, started_cpu,
                            *, disk_resume_used=False, trajectory_index=0,
                            optimizer_wall_time_s=None, validation_wall_time_s=None,
                            total_trial_wall_time_s=None):
    """Serialize one checkpoint observation from a live trajectory."""
    summary = backend.summary()
    requested = int(budget)
    actual = int(summary["unique_evaluations"])
    if actual >= requested:
        stop_reason = "requested_budget_reached"
    elif summary.get("search_space_exhausted"):
        stop_reason = "search_space_exhausted"
    else:
        stop_reason = "numerical_failure"
    record = dict(backend.incumbent() or {})
    objective_calls = int(summary.get("proposals_total", 0))
    cache_hits = int(summary.get("cache_hits", 0))
    duplicate_attempts = max(objective_calls - actual, 0)
    terminal_budget = int(summary.get("terminal_budget", summary.get(
        "population_schedule_terminal_budget", requested)))
    record.update({
        "backend": "lshade", "wiring": wiring, "seed": int(seed),
        "requested_unique_design_budget": requested,
        "unique_decoded_evaluations": actual,
        "actual_unique_design_evaluations": actual,
        "actual_unique_budget": actual,
        "budget_completion_fraction": float(actual / max(requested, 1)),
        "budget_completion_passed": bool(actual >= .98 * requested),
         "objective_calls": objective_calls,
         "raw_offspring_count": int(summary.get("raw_offspring_count", 0)),
         "duplicate_decoded_count": int(summary.get("duplicate_count", 0)),
         "duplicate_decoded_attempts": duplicate_attempts,
         "duplicate_decoded_rate": float(duplicate_attempts / max(objective_calls, 1)),
         "cache_hits": cache_hits,
         "cache_hit_rate": float(cache_hits / max(objective_calls, 1)),
        "population_size": int(summary.get("population_size", 0)),
        "proposals_total": int(summary.get("proposals_total", 0)),
        "duplicate_rate": float(summary.get("duplicate_rate", 0.0)),
        "m_f": summary.get("m_f", []), "m_cr": summary.get("m_cr", []),
        "archive_size": int(summary.get("archive_size", 0)),
        "archive_trace": summary.get("archive_trace", []),
        "boundary_repair_counts": summary.get("boundary_repair_counts", {}),
         "population_schedule_terminal_budget": terminal_budget,
         "terminal_budget": terminal_budget,
         "current_budget": actual,
         "initial_population": int(summary.get("initial_population", 0)),
         "current_population": int(summary.get("current_population", summary.get("population_size", 0))),
         "population_schedule_identifier": summary.get(
             "population_schedule_identifier", "lshade_linear_population_v1"),
         "population_schedule_version": int(summary.get("population_schedule_version", 1)),
        "hard_max_budget": int(summary.get("hard_max_budget", requested)),
        "search_space_exhausted": bool(summary.get("search_space_exhausted", False)),
        "stop_reason": stop_reason,
        "best_so_far_trace": summary.get("best_so_far_trace", []),
        "population_trace": summary.get("population_trace", []),
        "checkpoint_budget": requested,
        "checkpoint_trajectory_index": int(trajectory_index),
        "trajectory_semantics": "one_seed_one_trajectory",
        "disk_resume_used": bool(disk_resume_used),
         "frequency_grid_version": int(backend.frequency_grid_version),
         "frequency_grid_events": copy.deepcopy(frequency_events),
         "boundary_events": [],
         "recovery_events": [],
         "hard_bound_reached_by_variable": {},
        "checkpoint_state_summary": {
            "unique_evaluations": actual,
            "population_size": int(summary.get("population_size", 0)),
            "archive_size": int(summary.get("archive_size", 0)),
            "frequency_grid_version": int(backend.frequency_grid_version),
            "m_f": summary.get("m_f", []), "m_cr": summary.get("m_cr", []),
        },
         "elapsed_s": (
             float(total_trial_wall_time_s)
             if total_trial_wall_time_s is not None
             else time.monotonic() - started_wall
         ),
         "cpu_time_s": time.process_time() - started_cpu,
         "optimizer_wall_time_s": optimizer_wall_time_s,
         "validation_wall_time_s": validation_wall_time_s,
         "total_trial_wall_time_s": (
             float(total_trial_wall_time_s)
             if total_trial_wall_time_s is not None
             else time.monotonic() - started_wall
         ),
         "design_space_version": int(backend.design_space_version),
    })
    record = apply_checkpoint_evidence(
        record, current_budget=requested, terminal_budget=terminal_budget
    )
    if isinstance(checkpoint_path, Mapping):
        record.update(checkpoint_path)
    elif checkpoint_path is not None:
        # Compatibility for historical direct-file checkpoint records.
        record["checkpoint"] = str(checkpoint_path)
    return clean_record(record)


def lshade_record(backend, wiring, seed, budget, checkpoint_path,
                  frequency_events, started_wall, started_cpu,
                  *, disk_resume_used, trajectory_index,
                  optimizer_wall_time_s, validation_wall_time_s,
                  total_trial_wall_time_s=None):
    """Public record adapter for study-specific trajectory implementations.

    The implementation remains centralized in the canonical serializer; this
    public name keeps cross-study imports within the architecture contract.
    """
    return serialize_lshade_record(
        backend, wiring, seed, budget, checkpoint_path, frequency_events,
        started_wall, started_cpu, disk_resume_used=disk_resume_used,
        trajectory_index=trajectory_index,
        optimizer_wall_time_s=optimizer_wall_time_s,
        validation_wall_time_s=validation_wall_time_s,
        total_trial_wall_time_s=total_trial_wall_time_s,
    )


__all__ = [
    "clean_record",
    "lshade_record",
    "serialize_lshade_record",
]
