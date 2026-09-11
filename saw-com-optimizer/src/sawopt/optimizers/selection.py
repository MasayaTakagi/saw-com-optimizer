"""Authoritative feasibility-first candidate ordering for Stage 3.3.

The optimizer is allowed to expose a scalar objective for compatibility, but
selection must use this module's lexicographic key.  Keeping the policy in a
small dependency-free module makes it usable by all backends and reports.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np


def _finite(value: Any, default: float = np.inf) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return float(default)
    return value if np.isfinite(value) else float(default)


def _metrics(record: Mapping[str, Any]) -> Mapping[str, Any]:
    value = record.get("metrics", record)
    return value if isinstance(value, Mapping) else {}


def _violations(record: Mapping[str, Any]) -> Mapping[str, Any]:
    value = record.get("violations", {})
    return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class FeasibilityFirstComparator:
    """Deterministic constrained ordering.

    ``feasible`` is explicit when present; otherwise non-positive finite
    violations are considered feasible.  Secondary metrics are names looked up
    in ``record['metrics']`` and are only used after the required primary
    ordering.  No penalty coefficient enters this key.
    """

    feasible_secondary: tuple[str, ...] = ("ripple_db",)

    def rank_key(self, record: Mapping[str, Any]) -> tuple[float, ...]:
        violations = _violations(record)
        values = [_finite(value, np.inf) for value in violations.values()]
        values = [max(0.0, value) for value in values if np.isfinite(value)]
        max_violation = _finite(record.get("max_violation", max(values, default=0.0)))
        max_violation = max(0.0, max_violation)
        sum_violation = _finite(record.get("sum_violation", sum(values)), np.inf)
        feasible = bool(record.get("feasible", max_violation <= 1e-10))
        metrics = _metrics(record)
        worst_il = _finite(metrics.get("worst_il_db", record.get("worst_il_db", np.inf)))
        # Missing optional metrics are neutral for compatibility with legacy
        # records; an explicitly present non-finite metric remains poor.
        secondary = tuple(_finite(metrics.get(name, record.get(name, 0.0)), 0.0)
                          for name in self.feasible_secondary)
        if feasible:
            return (0.0, worst_il, *secondary, max_violation, sum_violation)
        return (1.0, max_violation, sum_violation, worst_il, *secondary)

    def compare(self, left: Mapping[str, Any], right: Mapping[str, Any]) -> int:
        """Return ``-1`` when left wins, ``1`` when right wins, else ``0``."""
        left_key = self.rank_key(left)
        right_key = self.rank_key(right)
        return -1 if left_key < right_key else (1 if left_key > right_key else 0)

    def better(self, left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        return self.compare(left, right) < 0

    def quality(self, record: Mapping[str, Any]) -> float:
        """Continuous improvement proxy used only for SHADE weights."""
        key = self.rank_key(record)
        return float(key[1])

    def improvement(self, old: Mapping[str, Any], new: Mapping[str, Any]) -> float:
        if not self.better(new, old):
            return 0.0
        old_key = self.rank_key(old)
        new_key = self.rank_key(new)
        # The first differing coordinate is the active lexicographic metric.
        for old_value, new_value in zip(old_key, new_key):
            if old_value != new_value:
                return max(float(old_value) - float(new_value), np.finfo(float).eps)
        return np.finfo(float).eps


DEFAULT_COMPARATOR = FeasibilityFirstComparator()


def rank_key(record: Mapping[str, Any], *, comparator: FeasibilityFirstComparator = DEFAULT_COMPARATOR):
    return comparator.rank_key(record)


def rank(record: Mapping[str, Any], *, comparator: FeasibilityFirstComparator = DEFAULT_COMPARATOR):
    """Compatibility-friendly name for the canonical candidate rank key."""
    return comparator.rank_key(record)


def compare(left: Mapping[str, Any], right: Mapping[str, Any], *,
            comparator: FeasibilityFirstComparator = DEFAULT_COMPARATOR) -> int:
    return comparator.compare(left, right)


def time_to_target(trace: Sequence[Mapping[str, Any]], target: Mapping[str, Any] | Sequence[float],
                   *, requested_unique_budget: int | None = None,
                   comparator: FeasibilityFirstComparator = DEFAULT_COMPARATOR):
    """Measure the first unique FE that reaches a baseline comparator target.

    A best-so-far trace stores comparator rank keys rather than full records, so
    the comparison is performed directly on the lexicographic key.  This is a
    trace metric; it is deliberately not derived from two final FE counts.
    """
    if isinstance(target, Mapping):
        target_key = tuple(comparator.rank_key(target))
    else:
        target_key = tuple(float(value) for value in target)
    ordered = sorted(trace, key=lambda row: int(row.get("unique_evaluation", 0)))
    for row in ordered:
        row_key = row.get("rank_key")
        if row_key is None:
            continue
        if tuple(row_key) <= target_key:
            evaluations = int(row.get("unique_evaluation", 0))
            result = {
                "status": "reached",
                "target_rank_key": list(target_key),
                "evals_to_target": evaluations,
                "eval_fraction_to_target": (
                    float(evaluations) / float(requested_unique_budget)
                    if requested_unique_budget is not None and requested_unique_budget > 0
                    else None
                ),
            }
            return result
    return {"status": "not_reached", "target_rank_key": list(target_key)}


# Descriptive alias for callers/report code that prefer the metric's name.
trace_time_to_target = time_to_target
