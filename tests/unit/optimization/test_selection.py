import numpy as np

from sawopt.optimization.lshade import LShadeBackend
from sawopt.optimization.selection import DEFAULT_COMPARATOR, GeometryFirstComparator


def _invalid(geometry_violation):
    return {
        "evaluation_status": "GEOMETRY_REJECTED",
        "geometry_valid": False,
        "geometry_violations": {"max_total_length": geometry_violation},
        "metrics": {},
        "violations": {},
        "feasible": False,
    }


def _valid(max_violation, *, worst_il=9.0):
    return {
        "evaluation_status": "PHYSICS_EVALUATED",
        "geometry_valid": True,
        "geometry_violations": {"max_total_length": 0.0},
        "metrics": {"worst_il_db": worst_il, "ripple_db": 2.0},
        "violations": {"filter": max_violation},
        "feasible": False,
        "max_violation": max_violation,
        "sum_violation": max_violation,
        "objective": max_violation + worst_il,
    }


def test_geometry_valid_candidate_precedes_any_invalid_geometry_candidate():
    comparator = GeometryFirstComparator()
    assert comparator.rank_key(_valid(10.0)) < comparator.rank_key(_invalid(1e-10))


def test_invalid_geometry_candidates_rank_by_geometry_violation():
    comparator = GeometryFirstComparator()
    assert comparator.rank_key(_invalid(1e-10)) < comparator.rank_key(_invalid(0.25))


def test_physics_evaluated_candidates_keep_standard_filter_order():
    comparator = GeometryFirstComparator()
    left, right = _valid(0.15, worst_il=8.0), _valid(0.30, worst_il=7.0)
    assert comparator.rank_key(left)[2:] == DEFAULT_COMPARATOR.rank_key(left)
    assert comparator.better(left, right) == DEFAULT_COMPARATOR.better(left, right)


def test_lshade_selection_and_trace_preserve_geometry_priority():
    comparator = GeometryFirstComparator()

    def evaluator(vector):
        value = float(vector[0])
        if value < 0.30:
            return _invalid(1e-10)
        return _valid(10.0 - value, worst_il=9.0 - value)

    bounds = np.asarray([[0.0, 1.0]])
    backend = LShadeBackend(
        bounds,
        seed=123,
        config={
            "total_budget": 10,
            "hard_max_budget": 10,
            "population_schedule_terminal_budget": 10,
            "initial_population": 8,
            "min_population": 4,
            "hard_bounds": bounds.tolist(),
        },
        integer_indices=(),
        comparator=comparator,
    )
    initial = np.asarray([[0.05], [0.35], [0.50], [0.62], [0.72], [0.82], [0.90], [0.98]])
    backend.initialize(evaluator, population=initial)

    assert backend.incumbent()["geometry_valid"] is True
    assert backend._ordered_indices()[0] != 0
    assert backend.best_so_far_trace[-1]["rank_key"][0] == 0.0
    assert backend.best_so_far_trace[-1]["rank_key"][1] == 0.0
    assert backend.best_so_far_trace[-1]["comparator"] == "GeometryFirstComparator"
    assert tuple(backend.best_so_far_trace[-1]["rank_key"]) == comparator.rank_key(
        backend.incumbent()
    )
    assert backend.best_so_far_trace[-1]["primary_metric"] == comparator.primary_metric(
        backend.incumbent()
    )
    assert backend.best_so_far_trace[-1]["primary_metric_feasible"] is False
