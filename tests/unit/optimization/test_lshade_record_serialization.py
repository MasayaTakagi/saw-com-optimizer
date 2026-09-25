from sawopt.studies import lshade_records
from sawopt.studies import optimizer_ab


class _FixedBackend:
    frequency_grid_version = 3
    design_space_version = 2

    @staticmethod
    def summary():
        return {
            "unique_evaluations": 8,
            "proposals_total": 11,
            "cache_hits": 2,
            "raw_offspring_count": 9,
            "duplicate_count": 1,
            "population_size": 4,
            "duplicate_rate": 3 / 11,
            "m_f": [0.5, 0.6],
            "m_cr": [0.8, 0.9],
            "archive_size": 2,
            "archive_trace": [{"generation": 2, "size": 2}],
            "boundary_repair_counts": {"reflector_pitch": 1},
            "terminal_budget": 16,
            "initial_population": 4,
            "current_population": 4,
            "population_schedule_identifier": "fixture_schedule_v1",
            "population_schedule_version": 1,
            "hard_max_budget": 16,
            "search_space_exhausted": False,
            "best_so_far_trace": [
                {"unique_evaluation": 4, "primary_metric": 10.0},
                {"unique_evaluation": 8, "primary_metric": 9.97},
            ],
            "population_trace": [{"unique_evaluation": 8, "size": 4}],
        }

    @staticmethod
    def incumbent():
        return {
            "design": {"main_pitch_um": 5.1},
            "metrics": {"worst_il_db": 9.97},
            "feasible": False,
            "max_violation": 0.2,
            "violations": {"return_loss": 0.2},
        }


def test_lshade_record_legacy_and_canonical_paths_match_fixed_semantics(monkeypatch):
    monkeypatch.setattr(lshade_records.time, "process_time", lambda: 50.0)
    monkeypatch.setattr(lshade_records.time, "monotonic", lambda: 100.0)
    backend = _FixedBackend()
    args = (
        backend, "G1_G2", 17, 8,
        {"checkpoint_stream": "checkpoints", "checkpoint_state": "runtime_recovery"},
        [{"checkpoint_budget": 8, "grid_fixed": True, "added_count": 0}],
        99.0, 49.0,
    )
    kwargs = {
        "disk_resume_used": False,
        "trajectory_index": 1,
        "optimizer_wall_time_s": 2.0,
        "validation_wall_time_s": 0.5,
        "total_trial_wall_time_s": 3.0,
    }

    canonical = lshade_records.lshade_record(*args, **kwargs)
    legacy = optimizer_ab.lshade_record(*args, **kwargs)

    assert legacy == canonical
    assert {
        key: canonical[key]
        for key in (
            "unique_decoded_evaluations", "objective_calls", "raw_offspring_count",
            "duplicate_decoded_count", "duplicate_decoded_attempts", "cache_hits",
            "population_size", "initial_population", "current_population",
            "terminal_budget", "current_budget", "checkpoint_budget",
            "checkpoint_trajectory_index", "population_schedule_identifier",
            "population_schedule_version", "frequency_grid_version",
            "design_space_version", "frequency_grid_events", "checkpoint_stream",
            "checkpoint_state", "grid_converged", "recovery_pending_confirmation",
            "boundary_pending_confirmation", "hard_bound_unresolved",
            "micro_polish_improvement", "fraction_of_budget_at_last_significant_improvement",
            "convergence_evidence_complete", "convergence_evidence_missing_fields",
            "elapsed_s", "cpu_time_s", "optimizer_wall_time_s",
            "validation_wall_time_s", "total_trial_wall_time_s",
        )
    } == {
        "unique_decoded_evaluations": 8,
        "objective_calls": 11,
        "raw_offspring_count": 9,
        "duplicate_decoded_count": 1,
        "duplicate_decoded_attempts": 3,
        "cache_hits": 2,
        "population_size": 4,
        "initial_population": 4,
        "current_population": 4,
        "terminal_budget": 16,
        "current_budget": 8,
        "checkpoint_budget": 8,
        "checkpoint_trajectory_index": 1,
        "population_schedule_identifier": "fixture_schedule_v1",
        "population_schedule_version": 1,
        "frequency_grid_version": 3,
        "design_space_version": 2,
        "frequency_grid_events": [{"checkpoint_budget": 8, "grid_fixed": True, "added_count": 0}],
        "checkpoint_stream": "checkpoints",
        "checkpoint_state": "runtime_recovery",
        "grid_converged": True,
        "recovery_pending_confirmation": False,
        "boundary_pending_confirmation": False,
        "hard_bound_unresolved": False,
        "micro_polish_improvement": None,
        "fraction_of_budget_at_last_significant_improvement": 1.0,
        "convergence_evidence_complete": False,
        "convergence_evidence_missing_fields": ["micro_polish_improvement"],
        "elapsed_s": 3.0,
        "cpu_time_s": 1.0,
        "optimizer_wall_time_s": 2.0,
        "validation_wall_time_s": 0.5,
        "total_trial_wall_time_s": 3.0,
    }
