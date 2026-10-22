"""Fail-closed ranking validation for full hybrid candidate projections.

Stage 4C saves complete physics-evaluated records; checkpoint comparisons may
also use deliberately sparse metric projections. Only full records are subject
to this validation; it does not change the optimizer's legacy comparator.
"""
from __future__ import annotations

import math
from numbers import Real
from typing import Any, Mapping

from ..optimization.selection import DEFAULT_COMPARATOR


STAGE4C_FILTER_CONSTRAINTS = frozenset({
    "il", "ripple", "input_vswr", "output_vswr",
    "stop_0", "stop_1", "stop_2", "stop_3",
})


def _nonnegative_finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0.0 else None


def validated_hybrid_rank_key(record: Mapping[str, Any]) -> tuple[float, ...] | None:
    """Return canonical key only for a coherent, full Stage 4C finalist.

    None means unrankable, including missing data, inconsistent feasibility,
    status/geometry contradictions, and non-finite or omitted violations.
    The physics evaluator and frozen metric specification remain authoritative.
    """
    if not isinstance(record, Mapping):
        return None
    if record.get("evaluation_status") != "PHYSICS_EVALUATED":
        return None
    if record.get("failure_stage") is not None:
        return None
    if "geometry_valid" in record and record["geometry_valid"] is not True:
        return None
    if not isinstance(record.get("feasible"), bool):
        return None
    if "filter_feasible" in record and record["filter_feasible"] is not record["feasible"]:
        return None

    metrics = record.get("metrics")
    if not isinstance(metrics, Mapping):
        return None
    for name in ("worst_il_db", "ripple_db"):
        value = metrics.get(name)
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
            return None

    violations = record.get("violations")
    if not isinstance(violations, Mapping) or set(violations) != STAGE4C_FILTER_CONSTRAINTS:
        return None
    values = [_nonnegative_finite(value) for value in violations.values()]
    if any(value is None for value in values):
        return None
    values = [float(value) for value in values]
    maximum = _nonnegative_finite(record.get("max_violation"))
    total = _nonnegative_finite(record.get("sum_violation"))
    if maximum is None or total is None:
        return None
    if not math.isclose(maximum, max(values), rel_tol=1e-12, abs_tol=1e-12):
        return None
    if not math.isclose(total, sum(values), rel_tol=1e-12, abs_tol=1e-12):
        return None
    feasible = maximum <= 1e-10
    if record["feasible"] is not feasible:
        return None

    geometry = record.get("geometry_violations")
    if not isinstance(geometry, Mapping) or not geometry:
        return None
    geometry_values = [_nonnegative_finite(value) for value in geometry.values()]
    if any(value is None for value in geometry_values):
        return None
    geometry_maximum = _nonnegative_finite(record.get("geometry_max_violation"))
    if geometry_maximum is None:
        return None
    if not math.isclose(geometry_maximum, max(geometry_values), rel_tol=1e-12, abs_tol=1e-12):
        return None
    if geometry_maximum != 0.0 or any(value != 0.0 for value in geometry_values):
        return None
    return DEFAULT_COMPARATOR.rank_key(record)
