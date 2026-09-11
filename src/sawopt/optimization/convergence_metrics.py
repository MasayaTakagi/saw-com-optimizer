"""Convergence-analysis helpers retained outside the search engine."""
from __future__ import annotations

import numpy as np

from ..optimizers.selection import rank
from .adaptive_frequency import common_validation_grid


def paired_improvements(records_by_budget, metric_fn):
    """Return paired same-seed deltas for consecutive numeric budgets."""
    budgets = sorted(int(budget) for budget in records_by_budget)
    out = []
    for lower, upper in zip(budgets, budgets[1:]):
        lower_by_seed = {int(record["seed"]): record for record in records_by_budget[lower]}
        upper_by_seed = {int(record["seed"]): record for record in records_by_budget[upper]}
        common = sorted(set(lower_by_seed) & set(upper_by_seed))
        deltas = [
            float(metric_fn(lower_by_seed[seed]) - metric_fn(upper_by_seed[seed]))
            for seed in common
        ]
        out.append({
            "lower_budget": lower,
            "upper_budget": upper,
            "seed_count": len(deltas),
            "seeds": common,
            "deltas": deltas,
            "median_improvement": float(np.median(deltas)) if deltas else None,
            "mean_improvement": float(np.mean(deltas)) if deltas else None,
            "iqr_improvement": float(np.percentile(deltas, 75) - np.percentile(deltas, 25)) if deltas else None,
        })
    return out


def last_significant_improvement(trace, budget, *, absolute=0.02, relative=0.01):
    """Find the last meaningful best-so-far update in a compact trace."""
    if not trace:
        return None, None
    significant = [trace[0]]
    for row in trace[1:]:
        old = float(significant[-1]["primary_metric"])
        new = float(row["primary_metric"])
        improvement = old - new
        scale = max(abs(old), np.finfo(float).tiny)
        if improvement >= float(absolute) or improvement / scale >= float(relative):
            significant.append(row)
    last = significant[-1]
    return int(last["unique_evaluation"]), float(last["unique_evaluation"]) / max(float(budget), 1.0)


def primary_metric(record):
    """Return the convergence metric used for a validated record."""
    if record.get("feasible", False):
        return float(record["metrics"]["worst_il_db"])
    return float(record.get("max_violation", np.inf))


def validated_candidate_selection(candidates, base_grid, critical_by_candidate,
                                  evaluate_candidate, tolerance_hz=1e3):
    """Re-evaluate candidates on one common grid and select by canonical rank."""
    if len(candidates) != len(critical_by_candidate) or not candidates:
        raise ValueError("Candidates and critical-frequency collections must match")
    common = common_validation_grid(base_grid, critical_by_candidate, tolerance_hz)
    validated = []
    for candidate in candidates:
        record = evaluate_candidate(candidate, common)
        record["common_validation_grid_count"] = len(common)
        record["validated_objective"] = record.get("objective")
        validated.append(record)
    return min(validated, key=rank), validated, common


__all__ = [
    "last_significant_improvement", "paired_improvements", "primary_metric",
    "validated_candidate_selection",
]
