"""SAW-specific mixed-variable polish plus the legacy Powell re-export."""
from __future__ import annotations

import time
from dataclasses import asdict

import numpy as np

from ..design.geometry import geometry
from ..design.space import BOUNDS, NAMES, decode
from ..optimizers.polish import powell_continuous_polish
from ..optimizers.selection import rank
from ..evaluation import evaluate_design


def mixed_variable_polish(record, cfg, rs, rl, wiring, frequencies, counters=None,
                          promote=True, *, evaluate_fn=None):
    """Deterministic mixed integer/continuous coordinate polish."""
    evaluate = evaluate_fn or evaluate_design
    settings = cfg.get("micro_polish", {})
    if not settings.get("enabled", True):
        return record, {
            "enabled": False, "promoted": False, "evaluations": 0,
            "solved_frequency_points": 0, "improvement": 0.0,
        }
    frequencies = np.unique(np.asarray(frequencies, dtype=float))
    current = np.asarray([record["design"][name] for name in NAMES], dtype=float)
    best, _, _ = evaluate(decode(current), cfg, frequencies, rs, rl, wiring=wiring)
    best["design"] = asdict(decode(current))
    before = best
    evaluations = 0
    solved_points = 0
    step_history = []
    improved_any = False
    integer_indices = {1, 2, 3}
    integer_steps = [float(value) for value in settings.get("integer_steps", [-1, 1])]
    second_integer_steps = [float(value) for value in settings.get(
        "optional_second_integer_steps", [])]
    fractions = [float(value) for value in settings.get(
        "continuous_steps_fraction_of_bound_span", [0.01, 0.005])]
    fractions = [value for value in fractions if value > 0]
    if not fractions:
        fractions = [0.005]
    shrink = float(settings.get("shrink_factor", 0.5))
    if not 0 < shrink < 1:
        raise ValueError("micro_polish.shrink_factor must be between 0 and 1")
    min_fraction = float(settings.get("minimum_step_fraction", min(fractions)))
    max_passes = max(0, int(settings.get("max_passes", 4)))
    bounds = np.asarray(BOUNDS, dtype=float)
    best_primary_before = (
        float(record["metrics"]["worst_il_db"])
        if record.get("feasible", False) else float(record.get("max_violation", np.inf))
    )
    polish_started = time.time()
    step_fraction = max(fractions)
    for polish_pass in range(max_passes):
        fraction = max(min_fraction, step_fraction)
        step_history.append(float(fraction))
        improved = False
        for index in range(len(BOUNDS)):
            if index in integer_indices:
                steps = integer_steps + (second_integer_steps if polish_pass >= 1 else [])
            else:
                span = bounds[index, 1] - bounds[index, 0]
                steps = [-fraction * span, fraction * span]
            for step in steps:
                trial = current.copy()
                trial[index] = np.clip(trial[index] + float(step), *BOUNDS[index])
                candidate = decode(trial)
                _dims, geometry_violation = geometry(candidate, cfg["constraints"])
                if max(geometry_violation) > 0:
                    if counters is not None:
                        counters.geometry_rejections += 1
                    continue
                started = time.time()
                candidate_result, _, _ = evaluate(
                    candidate, cfg, frequencies, rs, rl, wiring=wiring)
                elapsed = time.time() - started
                evaluations += 1
                solved_points += len(frequencies)
                if counters is not None:
                    counters.add_solved(len(frequencies), polish=True)
                    counters.add_polish(1, elapsed)
                candidate_result["design"] = asdict(candidate)
                if rank(candidate_result) < rank(best):
                    best = candidate_result
                    current = np.asarray([getattr(candidate, name) for name in NAMES], dtype=float)
                    improved = True
                    improved_any = True
        if not improved:
            if fraction <= min_fraction:
                break
            step_fraction = max(min_fraction, fraction * shrink)
    polished_primary = (
        float(best["metrics"]["worst_il_db"])
        if best.get("feasible", False) else float(best.get("max_violation", np.inf))
    )
    promoted = bool(promote and rank(best) < rank(record))
    if not promoted:
        best = record
    elapsed = time.time() - polish_started
    stop_reason = "accepted_improvement" if promoted else (
        "no_valid_moves" if evaluations == 0 else "no_improvement"
    )
    return best, {
        "enabled": True,
        "promoted": promoted,
        "evaluations": evaluations,
        "solved_frequency_points": solved_points,
        "polish_wall_time_s": elapsed,
        "passes": len(step_history),
        "step_fraction_history": step_history,
        "before_rank": list(rank(record)),
        "after_rank": list(rank(best)),
        "improvement": float(best_primary_before - polished_primary),
        "best_feasible": bool(best.get("feasible", False)),
        "accepted": promoted,
        "stop_reason": stop_reason,
        "improved_any": improved_any,
    }


_mixed_variable_polish = mixed_variable_polish

__all__ = ["mixed_variable_polish", "powell_continuous_polish"]
