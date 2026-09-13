import json

import numpy as np

from sawopt.optimizers.lshade import LShadeBackend
from sawopt.orchestration.run_manager import transition
from sawopt.studies.convergence_evidence import apply_checkpoint_evidence
from sawopt.studies.phase_c_supplement import select_stage35_decisions


def _objective(x):
    value = float(np.sum((np.asarray(x) - .25) ** 2))
    return {
        "feasible": False,
        "max_violation": value,
        "sum_violation": value,
        "violations": {"x": value},
        "metrics": {"worst_il_db": value, "ripple_db": value},
    }


def test_lshade_evidence_is_derived_from_trace_and_events():
    record = apply_checkpoint_evidence(
        {
            "requested_unique_design_budget": 100,
            "best_so_far_trace": [
                {"unique_evaluation": 4, "rank_key": [1, 2.0, 0, 0, 0]},
                {"unique_evaluation": 80, "rank_key": [1, 1.0, 0, 0, 0]},
            ],
            "frequency_grid_events": [{"checkpoint_budget": 100, "grid_fixed": True}],
            "recovery_events": [],
            "boundary_events": [],
            "hard_bound_reached_by_variable": {},
            "micro_polish_improvement": 0.01,
        },
        current_budget=100,
        terminal_budget=100,
    )
    assert record["grid_converged"] is True
    assert record["recovery_pending_confirmation"] is False
    assert record["boundary_pending_confirmation"] is False
    assert record["hard_bound_unresolved"] is False
    assert record["fraction_of_budget_at_last_significant_improvement"] == .8
    assert record["convergence_evidence_complete"] is True


def test_missing_evidence_is_not_filled_with_false_or_zero():
    record = apply_checkpoint_evidence(
        {"requested_unique_design_budget": 100}, current_budget=100, terminal_budget=100
    )
    assert record["grid_converged"] is None
    assert record["micro_polish_improvement"] is None
    assert "micro_polish_improvement" in record["convergence_evidence_missing_fields"]


def test_terminal_horizon_changes_population_trajectory_and_is_metadata():
    common = {"initial_population": 8, "min_population": 4, "total_budget": 32, "hard_max_budget": 64}
    low = LShadeBackend([(0, 1)] * 3, seed=7, config={**common, "population_schedule_terminal_budget": 32}, integer_indices=())
    high = LShadeBackend([(0, 1)] * 3, seed=7, config={**common, "population_schedule_terminal_budget": 64}, integer_indices=())
    population = np.asarray([[.05, .15, .25], [.15, .25, .35], [.25, .35, .45], [.35, .45, .55],
                             [.45, .55, .65], [.55, .65, .75], [.65, .75, .85], [.75, .85, .95]])
    low.initialize(_objective, population=population)
    high.initialize(_objective, population=population)
    low.advance_to_unique_budget(32)
    high.advance_to_unique_budget(32)
    assert low.population_size_for_budget(32) != high.population_size_for_budget(32)
    assert low.summary()["terminal_budget"] == 32
    assert high.summary()["terminal_budget"] == 64
    assert json.loads(json.dumps(high.state_dict()))["population_schedule_terminal_budget"] == 64


def test_terminal_horizon_mismatch_requires_cold_start():
    source = LShadeBackend(
        [(0, 1)] * 2, seed=9,
        config={"initial_population": 6, "min_population": 4, "total_budget": 20,
                "hard_max_budget": 32, "population_schedule_terminal_budget": 32},
        integer_indices=(),
    )
    source.initialize(_objective)
    state = source.state_dict()
    target = LShadeBackend(
        [(0, 1)] * 2, seed=9,
        config={"initial_population": 6, "min_population": 4, "total_budget": 20,
                "hard_max_budget": 64, "population_schedule_terminal_budget": 64},
        integer_indices=(),
    )
    try:
        target.load_state_dict(state)
    except ValueError as exc:
        assert "terminal horizon mismatch" in str(exc)
    else:
        raise AssertionError("a 32k trajectory must not resume as a 64k trajectory")


def test_selector_keeps_optimizer_and_search_space_decisions_separate():
    result = select_stage35_decisions(
        {"evidence_complete": True, "median_by_budget": {"64000": {"Legacy-DE": .70, "L-SHADE": .60}}},
        {
            "C64_S0_LSHADE": {"seed_count": 4, "median_primary": .60, "convergence_evidence_missing_fields": []},
            "D64_S1_LSHADE": {"seed_count": 4, "median_primary": .70, "convergence_evidence_missing_fields": []},
            "paired": [],
        },
    )
    assert result == {
        "optimizer_decision": "PROMOTE_LSHADE",
        "search_space_decision": "PROMOTE_S0",
        "evidence_status": "COMPLETE",
        "equivalence_tolerance_fraction": .02,
    }


def test_review_waiting_state_is_persistable(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "status.json").write_text(json.dumps({"state": "COMPLETED", "updated_at": "now"}), encoding="utf-8")
    # Use the real state-machine path through a minimal valid status fixture.
    status = {
        "state": "COMPLETED", "updated_at": "now", "callback_attempts": 0,
        "callback_completed": False, "callback_enabled": False,
    }
    (run / "status.json").write_text(json.dumps(status), encoding="utf-8")
    updated = transition(run, "REVIEW_WAITING")
    assert updated["state"] == "REVIEW_WAITING"
    assert updated["optimizer_state"] == "REVIEW_WAITING"
