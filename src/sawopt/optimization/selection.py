"""Compatibility imports; use :mod:`sawopt.optimizers.selection` for new code."""

from ..optimizers.selection import (
    DEFAULT_COMPARATOR,
    FeasibilityFirstComparator,
    compare,
    rank,
    rank_key,
    time_to_target,
    trace_time_to_target,
)

__all__ = [
    "DEFAULT_COMPARATOR", "FeasibilityFirstComparator", "rank", "rank_key", "compare",
    "time_to_target", "trace_time_to_target",
]
