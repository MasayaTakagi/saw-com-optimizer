"""Evaluation accounting for search and validation services."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class EvaluationCounters:
    """Counters used to distinguish optimizer calls from actual work."""

    objective_calls: int = 0
    canonical_candidates_seen: int = 0
    unique_decoded_evaluations: int = 0
    valid_physics_evaluations: int = 0
    geometry_rejections: int = 0
    cache_hits: int = 0
    solved_frequency_points: int = 0
    validation_frequency_points: int = 0
    polish_evaluations: int = 0
    polish_solved_frequency_points: int = 0
    optimization_wall_time_s: float = 0.0
    global_search_wall_time_s: float = 0.0
    validation_wall_time_s: float = 0.0
    polish_wall_time_s: float = 0.0
    com_network_evaluation_wall_time_s: float = 0.0
    history_io_time_s: float = 0.0

    def add_solved(self, count, *, validation=False, polish=False):
        count = int(count)
        self.solved_frequency_points += count
        if validation:
            self.validation_frequency_points += count
        if polish:
            self.polish_solved_frequency_points += count

    def add_polish(self, count, elapsed):
        self.polish_evaluations += int(count)
        self.polish_wall_time_s += float(elapsed)

    def add_evaluation_time(self, elapsed, *, validation=False):
        elapsed = float(elapsed)
        self.com_network_evaluation_wall_time_s += elapsed
        if validation:
            self.validation_wall_time_s += elapsed
        else:
            self.optimization_wall_time_s += elapsed

    def as_dict(self):
        values = asdict(self)
        values["unique_evaluations"] = self.unique_decoded_evaluations
        values["validation_solved_frequency_points"] = self.validation_frequency_points
        values["global_search_evaluations"] = self.unique_decoded_evaluations
        return values


__all__ = ["EvaluationCounters"]
