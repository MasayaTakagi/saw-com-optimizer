"""Evaluation accounting for search and validation services."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


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


def evaluation_status(record: Mapping[str, Any]) -> str:
    """Return the status tag used by geometry-gated evaluation records."""
    return str(record.get("evaluation_status", "PHYSICS_FAILED"))


@dataclass
class GeometryGateCounters:
    """R1 geometry/physics accounting with its historical field semantics."""

    geometry_rejections: int = 0
    geometry_valid_candidates: int = 0
    physics_attempted_evaluations: int = 0
    valid_physics_evaluations: int = 0
    physics_failures: int = 0
    search_frequency_points: int = 0
    validation_evaluations: int = 0
    validation_physics_failures: int = 0
    validation_solved_frequency_points: int = 0
    initial_sampling: dict[str, int] = field(default_factory=dict)

    @property
    def solved_frequency_points(self) -> int:
        return self.search_frequency_points + self.validation_solved_frequency_points

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)

    def restore_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        for name in self.snapshot():
            if name in snapshot:
                value = snapshot[name]
                setattr(self, name, dict(value) if name == "initial_sampling" else int(value))

    def observe_search(self, record: Mapping[str, Any], frequency_count: int) -> None:
        status = evaluation_status(record)
        if status == "GEOMETRY_REJECTED":
            self.geometry_rejections += 1
        else:
            self.geometry_valid_candidates += 1
            self.physics_attempted_evaluations += 1
            if status == "PHYSICS_EVALUATED":
                self.valid_physics_evaluations += 1
                self.search_frequency_points += int(frequency_count)
            else:
                self.physics_failures += 1

    def restore_from_cache(self, records: Sequence[Mapping[str, Any]], frequency_count: int) -> None:
        self.geometry_rejections = 0
        self.geometry_valid_candidates = 0
        self.physics_attempted_evaluations = 0
        self.valid_physics_evaluations = 0
        self.physics_failures = 0
        self.search_frequency_points = 0
        for record in records:
            self.observe_search(record, frequency_count)

    def restore_validation(self, snapshot: Mapping[str, Any]) -> None:
        self.validation_evaluations = int(snapshot.get("validation_evaluations", 0))
        self.validation_physics_failures = int(snapshot.get("validation_physics_failures", 0))
        self.validation_solved_frequency_points = int(snapshot.get("validation_frequency_points", 0))


__all__ = ["EvaluationCounters", "GeometryGateCounters", "evaluation_status"]
