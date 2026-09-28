import numpy as np

from sawopt.io.lifecycle import RunDisposition
from sawopt.optimization.counters import GeometryGateCounters
from sawopt.optimizers.checkpoint_session import LShadeCheckpointSession
from sawopt.optimizers.lshade import LShadeBackend
from sawopt.optimizers.selection import GeometryFirstComparator
from sawopt.studies.hybrid import (
    _stage4a_load_context,
    run_stage4a_implementation_validation,
)


def _toy_backend(seed, evaluator):
    return LShadeBackend(
        np.asarray([[0.0, 1.0], [0.0, 1.0]]), seed=seed,
        config={
            "total_budget": 16, "requested_unique_budget": 16,
            "hard_max_budget": 16, "population_schedule_terminal_budget": 16,
            "initial_population": 4, "min_population": 4,
        },
        integer_indices=(), comparator=GeometryFirstComparator(),
    )


def test_lshade_uses_unique_budget_and_reproduces_the_same_seed():
    def run(seed):
        counters = GeometryGateCounters()
        calls = []

        def evaluator(vector):
            score = float(np.sum(np.asarray(vector) ** 2))
            result = {
                "evaluation_status": "PHYSICS_EVALUATED", "geometry_valid": True,
                "metrics": {"worst_il_db": score}, "violations": {"il": 0.0},
                "feasible": True, "max_violation": 0.0, "sum_violation": 0.0,
                "objective": score,
            }
            calls.append(tuple(vector))
            counters.observe_search(result, frequency_count=5)
            return result

        backend = _toy_backend(seed, evaluator)
        population = np.random.default_rng(seed).uniform(size=(4, 2))
        backend.set_frequency_grid([1, 2, 3, 4, 5], version=1)
        backend.initialize(evaluator, population=np.vstack([population, population[0]]))
        assert backend.summary()["cache_hits"] == 1
        assert backend.summary()["population_size"] == 4
        backend.advance_to_unique_budget(16)
        assert backend.unique_evaluations == 16
        assert len(calls) == backend.unique_evaluations
        assert counters.geometry_rejections + counters.geometry_valid_candidates == 16
        assert counters.geometry_valid_candidates == counters.valid_physics_evaluations
        assert counters.search_frequency_points == counters.valid_physics_evaluations * 5
        assert backend.summary()["generations"] > 0
        return backend

    left, right = run(20260929), run(20260929)
    np.testing.assert_array_equal(left.population(), right.population())
    assert left.incumbent() == right.incumbent()
    assert left.summary()["unique_evaluations"] == 16


def test_shared_checkpoint_session_resumes_exact_optimizer_state(tmp_path):
    def evaluator(vector):
        score = float(np.sum(np.asarray(vector) ** 2))
        return {
            "evaluation_status": "PHYSICS_EVALUATED", "geometry_valid": True,
            "metrics": {"worst_il_db": score}, "violations": {"il": 0.0},
            "feasible": True, "max_violation": 0.0, "sum_violation": 0.0,
            "objective": score,
        }

    control = _toy_backend(71, evaluator)
    population = np.random.default_rng(71).uniform(size=(4, 2))
    control.set_frequency_grid([1, 2, 3], version=1)
    control.initialize(evaluator, population=population)
    control.advance_to_unique_budget(16)

    checkpoint_root = tmp_path / "checkpoints"
    session = LShadeCheckpointSession(
        checkpoint_root, run_directory=tmp_path,
        legacy_path=tmp_path / "old_checkpoint.json", resume=False,
    )
    partial = _toy_backend(71, evaluator)
    partial.set_frequency_grid([1, 2, 3], version=1)
    partial.initialize(evaluator, population=population)
    partial.advance_to_unique_budget(8)
    session.save(partial)

    resumed_session = LShadeCheckpointSession(
        checkpoint_root, run_directory=tmp_path,
        legacy_path=tmp_path / "old_checkpoint.json", resume=True,
    )
    resumed = _toy_backend(71, evaluator)
    resumed_session.load(resumed)
    resumed.set_evaluator(evaluator)
    resumed.advance_to_unique_budget(16)
    np.testing.assert_array_equal(resumed.population(), control.population())
    assert resumed.incumbent() == control.incumbent()
    assert resumed.summary()["unique_evaluations"] == 16
    assert resumed_session.reference_metadata["checkpoint_policy"] == "rolling_latest_previous"


def test_stage4a_contract_grid_fingerprint_and_d_only_parity(tmp_path):
    context = _stage4a_load_context("configs/studies/hybrid_stage4a_qualification.yaml")
    assert context["fingerprint"]["fingerprint_schema_version"] == 2
    assert "src/sawopt/reporting/hybrid_qualification.py" not in context["computation_paths"]
    assert "src/sawopt/reporting/hybrid_qualification.py" in context["reporting_paths"]
    assert "src/sawopt/reporting/hybrid_qualification.py" not in {
        item["path"] for item in context["fingerprint"]["dependency_manifest"]["computation"]
    }
    assert "src/sawopt/reporting/hybrid_qualification.py" in {
        item["path"] for item in context["fingerprint"]["dependency_manifest"]["reporting"]
    }
    assert len(context["common_frequencies"]) == 9113
    assert context["contract"]["topologies"] == ["D", "P_D", "D_P", "P_D_P"]
    assert context["contract"]["source_impedance_ohm"] == 50.0
    assert context["contract"]["load_impedance_ohm"] == 50.0
    assert [row[:2] for row in context["cfg"]["spec"]["stopbands"][1:3]] == [
        [703, 748], [832, 862],
    ]

    result = run_stage4a_implementation_validation(
        "configs/studies/hybrid_stage4a_qualification.yaml", tmp_path / "validation",
    )
    assert result["status"] == "PASS"
    assert result["d_only_parity"]["status"] == "PASS"
    assert result["d_only_parity"]["grids"]["search"]["frequency_count"] == 1001
    assert result["d_only_parity"]["grids"]["common"]["frequency_count"] == 9113
    assert result["d_only_parity"]["overall_maximum_absolute_difference"] == 0.0
    assert result["provenance_status"]["schema_version"] == 2
    assert result["checkpoint_lifecycle"]["disposition_after_success"] == RunDisposition.REVIEW_WAITING.value
    assert result["optimizer_selection"]["backend_class"] == "LShadeBackend"
    assert result["optimizer_selection"]["scipy_differential_evolution_used"] is False


def test_lshade_dimension_matches_each_hybrid_topology():
    context = _stage4a_load_context("configs/studies/hybrid_stage4a_qualification.yaml")
    expected = {"D": 10, "P_D": 13, "D_P": 13, "P_D_P": 16}
    for topology, dimension in expected.items():
        space = context["spaces"][topology]
        assert space.dimension == dimension
        assert space.bounds.shape == (dimension, 2)
        assert len(space.integer_indices) == 3 + {"D": 0, "P_D": 1, "D_P": 1, "P_D_P": 2}[topology]
        backend = LShadeBackend(
            space.bounds, seed=20260929,
            config={
                "total_budget": 256, "hard_max_budget": 256,
                "population_schedule_terminal_budget": 256,
                "initial_population": 32, "min_population": 4,
                "hard_bounds": space.bounds.tolist(),
            },
            integer_indices=space.integer_indices,
            canonicalizer=space.canonicalize,
            comparator=GeometryFirstComparator(),
        )
        assert backend.dimension == dimension
        assert backend.initial_population_size == 32
