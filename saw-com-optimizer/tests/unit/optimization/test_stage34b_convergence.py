import pickle

from sawopt.optimization.convergence_policy import convergence_status, thresholds
from sawopt.studies.continuation import ContinuationTrajectory, _convergence_stop_allowed


def _cfg():
    return {
        "convergence": {
            "stage3_4b": True,
            "min_grid_converged_seed_fraction": 0.875,
            "infeasible": {
                "paired_median_primary_relative_improvement": 0.02,
                "paired_median_primary_absolute_improvement": 0.02,
                "final_seed_primary_iqr": 0.10,
                "final_seed_primary_worst_minus_median": 0.10,
                "validation_primary_gap": 0.02,
                "best_polish_primary_improvement": 0.02,
                "late_improvement_final_budget_fraction": 0.25,
                "max_fraction_seeds_materially_improving": 0.25,
            },
        }
    }


def _rows(*, improving=2, grid_count=8, recovery=False,
          recovery_pending=False, boundary_first=False,
          boundary_pending=False, worst_spread=False):
    rows = []
    for budget in (100, 200, 400):
        for seed in range(1, 9):
            value = 1.0
            if seed <= improving and budget >= 200:
                value -= 0.03 * (budget // 200)
            if worst_spread and budget == 400 and seed == 8:
                value = 1.15
            rows.append({
                "budget": budget,
                "seed": seed,
                "feasible": False,
                "max_violation": value,
                "worst_il_db": 5.0,
                "validation_gap_primary": 0.0,
                "micro_polish_improvement": 0.0,
                "fraction_of_budget_at_last_significant_improvement": 0.5,
                "grid_converged": seed <= grid_count,
                "recovery_fired_at_current_checkpoint": recovery,
                "recovery_pending_confirmation": recovery_pending,
                "boundary_pressure_first_seen_at_current_checkpoint": boundary_first,
                "boundary_pending_confirmation": boundary_pending,
                "hard_bound_reached_by_variable": {},
                "hard_bound_unresolved": False,
            })
    return rows


def _status(**kwargs):
    cfg = _cfg()
    return convergence_status(_rows(**kwargs), thresholds(cfg))


def test_two_of_eight_materially_improving_passes():
    status, evidence = _status(improving=2)
    assert status == "converged"
    assert evidence["stage34b_gates"]["materially_improving_seed_fraction_pass"]


def test_three_of_eight_materially_improving_fails():
    status, evidence = _status(improving=3)
    assert status != "converged"
    assert not evidence["stage34b_gates"]["materially_improving_seed_fraction_pass"]


def test_iqr_pass_but_worst_minus_median_fails():
    status, evidence = _status(improving=0, worst_spread=True)
    assert status != "converged"
    assert evidence["final_seed_primary_iqr"] < 0.10
    assert evidence["final_seed_primary_worst_minus_median"] > 0.10


def test_grid_six_of_eight_fails():
    status, evidence = _status(improving=0, grid_count=6)
    assert status != "converged"
    assert not evidence["stage34b_gates"]["grid_converged_fraction_pass"]


def test_grid_seven_of_eight_passes():
    status, evidence = _status(improving=0, grid_count=7)
    assert status == "converged"
    assert evidence["stage34b_gates"]["grid_converged_fraction_pass"]


def test_current_checkpoint_recovery_cannot_converge():
    status, evidence = _status(improving=0, recovery=True)
    assert status != "converged"
    assert not evidence["stage34b_gates"]["recovery_confirmed"]


def test_next_checkpoint_after_recovery_can_converge():
    status, evidence = _status(improving=0, recovery=False, recovery_pending=False)
    assert status == "converged"
    assert evidence["stage34b_gates"]["recovery_confirmed"]


def test_first_boundary_pressure_checkpoint_cannot_converge():
    status, evidence = _status(improving=0, boundary_first=True, boundary_pending=True)
    assert status != "converged"
    assert not evidence["stage34b_gates"]["boundary_confirmed"]


def test_persistent_boundary_confirmed_is_a_pass_candidate():
    status, evidence = _status(improving=0)
    assert status == "converged"
    assert evidence["stage34b_gates"]["boundary_confirmed"]


def test_hard_ceiling_status_cannot_stop_as_converged():
    assert not _convergence_stop_allowed("inconclusive_at_hard_ceiling", 512000, 32000)


def test_missing_stage34b_evidence_fails_closed():
    cfg = _cfg()
    rows = _rows(improving=0)
    for row in rows:
        row.pop("grid_converged")
    status, evidence = convergence_status(rows, thresholds(cfg))
    assert status != "converged"
    assert not evidence["stage34b_gates"]["pass"]
    assert "grid_converged" in evidence["stage34b_gates"]["missing_evidence"]


def test_trajectory_pickle_does_not_copy_unbounded_search_cache():
    trajectory = object.__new__(ContinuationTrajectory)
    trajectory.cache = {"large": {"record": "discardable IPC cache"}}
    trajectory.seen = {(1.0,)}
    restored = pickle.loads(pickle.dumps(trajectory))
    assert restored.cache == {}
    assert restored.seen == {(1.0,)}
