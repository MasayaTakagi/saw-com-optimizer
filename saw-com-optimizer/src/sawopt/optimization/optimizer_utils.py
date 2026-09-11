"""Compatibility exports for the pre-refactor optimization helpers.

New code should import services from their focused modules in this package.
The re-exports preserve historical imports and result behavior during the
migration window.
"""

from .adaptive_frequency import (
    adaptive_exchange,
    adaptive_settings,
    common_validation_grid,
    critical_frequencies,
    new_frequency_points,
)
from .budget import PlateauStopper, adaptive_budget_limits
from .cache import IncrementalFrequencyCache, aggregate_diagnostics
from .convergence_metrics import (
    last_significant_improvement,
    paired_improvements,
    primary_metric,
    validated_candidate_selection,
)
from .counters import EvaluationCounters
from .population import scaled_population

_adaptive_budget_limits = adaptive_budget_limits

__all__ = [
    "EvaluationCounters", "IncrementalFrequencyCache", "PlateauStopper",
    "adaptive_exchange", "adaptive_settings", "adaptive_budget_limits",
    "aggregate_diagnostics", "common_validation_grid", "critical_frequencies",
    "last_significant_improvement", "new_frequency_points", "paired_improvements",
    "primary_metric", "scaled_population", "validated_candidate_selection",
]
