"""Optional continuous-only Powell polish for Stage 3.3."""
from __future__ import annotations

from typing import Any, Callable, Mapping

import numpy as np
from scipy.optimize import minimize

from .selection import DEFAULT_COMPARATOR, FeasibilityFirstComparator


def _rank_scalar(record: Mapping[str, Any], comparator: FeasibilityFirstComparator) -> float:
    key = comparator.rank_key(record)
    # This scalar is only Powell's direction-finding merit.  Final promotion
    # always uses the exact lexicographic comparator below.
    if key[0] == 0:
        return float(key[1]) + 1e-6 * sum(float(x) for x in key[2:] if np.isfinite(x))
    return 1e6 + 1e3 * float(key[1]) + float(key[2]) + 1e-6 * float(key[3])


def powell_continuous_polish(
    physical_vector,
    evaluator: Callable[[np.ndarray], Mapping[str, Any]],
    bounds,
    *,
    integer_indices=(1, 2, 3),
    comparator: FeasibilityFirstComparator | None = None,
    maxfev: int = 250,
):
    """Polish only continuous coordinates and reject comparator regressions.

    ``evaluator`` must perform canonical decode and common-grid evaluation. The
    integer coordinates are fixed exactly; Powell's internal vectors are
    clipped to their physical bounds before each call.
    """
    comparator = comparator or DEFAULT_COMPARATOR
    x0 = np.asarray(physical_vector, dtype=float).copy()
    bounds = np.asarray(bounds, dtype=float)
    integer_indices = set(int(i) for i in integer_indices)
    continuous = [index for index in range(len(x0)) if index not in integer_indices]
    baseline = dict(evaluator(x0))
    calls = 1
    if not continuous or int(maxfev) <= 0:
        return baseline, {"enabled": False, "promoted": False, "evaluations": calls,
                          "before_rank": list(comparator.rank_key(baseline)),
                          "after_rank": list(comparator.rank_key(baseline)), "rejected": False}

    cache = {}

    def objective(reduced):
        nonlocal calls
        trial = x0.copy()
        trial[continuous] = np.clip(np.asarray(reduced, dtype=float), bounds[continuous, 0], bounds[continuous, 1])
        key = tuple(float(value) for value in trial)
        if key not in cache:
            cache[key] = dict(evaluator(trial))
            calls += 1
        return _rank_scalar(cache[key], comparator)

    result = minimize(
        objective, x0[continuous], method="Powell",
        bounds=[tuple(row) for row in bounds[continuous]],
        options={"maxfev": int(maxfev), "xtol": 1e-5, "ftol": 1e-5, "disp": False},
    )
    candidate = x0.copy()
    candidate[continuous] = np.clip(np.asarray(result.x, dtype=float), bounds[continuous, 0], bounds[continuous, 1])
    polished = dict(evaluator(candidate))
    calls += 1
    promoted = comparator.better(polished, baseline)
    selected = polished if promoted else baseline
    return selected, {
        "enabled": True, "promoted": bool(promoted), "rejected": not promoted,
        "evaluations": int(calls), "maxfev": int(maxfev),
        "before_rank": list(comparator.rank_key(baseline)),
        "candidate_rank": list(comparator.rank_key(polished)),
        "after_rank": list(comparator.rank_key(selected)),
        "scipy_success": bool(getattr(result, "success", False)),
        "scipy_message": str(getattr(result, "message", "")),
    }

