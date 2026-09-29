import json
from pathlib import Path

import numpy as np
import yaml
import sawopt.studies.hybrid as historical_hybrid

from sawopt.optimizers.checkpoint_session import LShadeCheckpointSession
from sawopt.optimizers.lshade import LShadeBackend
from sawopt.optimizers.selection import GeometryFirstComparator
from sawopt.studies.hybrid_comparison import (
    PRODUCTION_SEEDS,
    PRODUCTION_TOPOLOGIES,
    _resolved_context,
    _sample_initial_population,
    run_hybrid_topology_screening,
    validate_hybrid_topology_screening,
)


ROOT = Path(__file__).resolve().parents[3]


def _smoke_config(
    tmp_path: Path, *, topology: str = "D", evaluations_per_dimension: int = 1,
    normalized_targets: dict[str, int] | None = None,
) -> Path:
    source = ROOT / "configs/studies/hybrid_stage4b_comparison.yaml"
    cfg = yaml.safe_load(source.read_text(encoding="utf-8"))
    cfg["base_config"] = str((ROOT / "configs/studies/dms_topology_screening.yaml").resolve())
    cfg["study"]["mode"] = "orchestration_smoke"
    cfg["dms_topology"].update({
        "budget": 16, "initial_population": 4,
        "initial_population_per_dimension": 18,
        "population_schedule_terminal_budget": 16,
        "checkpoints": [8, 16], "seeds": [303],
    })
    cfg["hybrid"]["common_grid_finalists"] = 2
    cfg["hybrid"]["initializer"]["max_attempts"] = 2000
    cfg["hybrid_comparison"].update({
        "topologies": [topology], "primary_budget": 16,
        "evaluations_per_dimension": evaluations_per_dimension,
        "population_schedule_terminal_budget": 16,
        "checkpoint_budgets": [8, 16],
        "common_grid_finalists": 2,
        "normalized_targets": normalized_targets or {"D": 16},
        "production_launch_authorized": False,
    })
    cfg["hybrid"]["production_launch_authorized"] = False
    path = tmp_path / "hybrid_smoke.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path


def test_prelaunch_config_has_fixed_fairness_and_dimension_contract():
    context = _resolved_context("configs/studies/hybrid_stage4b_comparison.yaml")
    assert context["topologies"] == PRODUCTION_TOPOLOGIES
    assert context["seeds"] == PRODUCTION_SEEDS
    assert context["dimensions"] == {"D": 10, "P_D": 13, "D_P": 13, "P_D_P": 16}
    assert context["initial_populations"] == {"D": 180, "P_D": 234, "D_P": 234, "P_D_P": 288}
    assert context["targets"] == {"D": 4000, "P_D": 5200, "D_P": 5200, "P_D_P": 6400}
    assert context["contract"]["baseline_dimension"] == 10
    assert context["contract"]["normalized_targets"] == context["targets"]
    assert context["contract"]["production_launch_authorized"] is False
    assert context["contract"]["decision_policy"] == {
        "study_role": "screening_only",
        "authoritative_primary_stratum": "equal_budget_B4000",
        "normalized_sensitivity_may_replace_primary": False,
        "automatic_topology_promotion": False,
        "automatic_topology_elimination": False,
        "post_stage4b_candidate_topologies": ["D", "P_D", "D_P", "P_D_P"],
        "narrowing_gate": "separately_predeclared_selection_gate",
    }
    assert context["checkpoints"] == {
        "D": (1000, 2000, 3000, 4000),
        "P_D": (1300, 2000, 2600, 3900, 4000, 5200),
        "D_P": (1300, 2000, 2600, 3900, 4000, 5200),
        "P_D_P": (1600, 2000, 3200, 4000, 4800, 6400),
    }
    dimensions = context["contract"]["dimensions"]
    assert dimensions["D"]["primary_evaluations_per_dimension"] == 400
    assert dimensions["P_D"]["primary_evaluations_per_dimension"] == 4000 / 13
    assert dimensions["P_D_P"]["primary_evaluations_per_dimension"] == 250
    assert all(row["population_schedule_terminal_budget"] == 4000 for row in dimensions.values())
    assert all(row["hard_max_budget_from_cold_start"] == row["normalized_target"]
               for row in dimensions.values())
    assert context["contract"]["diagnostic_lattice_evaluations_per_dimension"] == [
        100, 200, 300, 400,
    ]


def test_initialization_is_seeded_canonical_and_reports_topology_volume(tmp_path):
    context = _resolved_context("configs/studies/hybrid_stage4b_comparison.yaml")
    space = context["spaces"]["P_D_P"]
    first, first_stats = _sample_initial_population(
        space, context["cfg"], seed=PRODUCTION_SEEDS[0], topology="P_D_P",
        population_size=48, max_attempts=10000,
    )
    second, second_stats = _sample_initial_population(
        space, context["cfg"], seed=PRODUCTION_SEEDS[0], topology="P_D_P",
        population_size=48, max_attempts=10000,
    )
    np.testing.assert_array_equal(first, second)
    assert first_stats == second_stats
    physical = space.bounds[:, 0] + first * (space.bounds[:, 1] - space.bounds[:, 0])
    for index in space.integer_indices:
        assert np.equal(physical[:, index], np.floor(physical[:, index] + 0.5)).all()
    assert first_stats["candidate_draws"] == (
        first_stats["accepted_population_size"]
        + first_stats["geometry_rejections"]
        + first_stats["duplicate_rejections"]
    )
    assert first_stats["historical_designs_included"] is False
    assert len(first_stats["integer_variable_distribution"]) == len(space.integer_indices)
    assert len(first_stats["per_coordinate_coverage"]) == space.dimension


def _parity_backend(space, *, seed: int, primary: int, hard_max: int,
                    population: np.ndarray, fingerprint: str, evaluator):
    hard = space.bounds.copy()
    config = {
        "total_budget": primary, "requested_unique_budget": primary,
        "hard_max_budget": hard_max,
        "population_schedule_terminal_budget": primary,
        "initial_population": len(population), "min_population": 4,
        "hard_bounds": hard.tolist(),
    }
    backend = LShadeBackend(
        space.bounds, seed=seed, config=config,
        integer_indices=space.integer_indices, canonicalizer=space.canonicalize,
        comparator=GeometryFirstComparator(), source_config_fingerprint=fingerprint,
    )
    backend.set_frequency_grid([1.0, 2.0, 3.0], version=1)
    backend.initialize(evaluator, population=population)
    return backend


def _toy_physics(space):
    def evaluate(vector):
        normalized = (vector - space.bounds[:, 0]) / (space.bounds[:, 1] - space.bounds[:, 0])
        score = float(np.dot(normalized, normalized))
        return {
            "evaluation_status": "PHYSICS_EVALUATED", "geometry_valid": True,
            "geometry_violations": {}, "metrics": {"worst_il_db": score, "ripple_db": 0.0},
            "violations": {}, "feasible": True, "max_violation": 0.0,
            "sum_violation": 0.0, "objective": score,
        }
    return evaluate


def _state_json(backend):
    return json.dumps(backend.state_dict(), sort_keys=True, separators=(",", ":"))


def test_split_resume_matches_uninterrupted_b4000_and_final_for_control_and_extended(tmp_path):
    context = _resolved_context("configs/studies/hybrid_stage4b_comparison.yaml")
    # Scale B4000 to 24 evaluations for a deterministic non-production parity test.
    primary = 24
    for topology, final_target in (("D", 24), ("P_D", 32)):
        space = context["spaces"][topology]
        population, _stats = _sample_initial_population(
            space, context["cfg"], seed=717, topology=topology,
            population_size=4, max_attempts=10000,
        )
        fingerprint = f"scaled-resume-parity-{topology}"
        evaluator = _toy_physics(space)
        uninterrupted = _parity_backend(
            space, seed=717, primary=primary, hard_max=final_target,
            population=population, fingerprint=fingerprint, evaluator=evaluator,
        )
        uninterrupted.advance_to_unique_budget(primary)
        primary_state = _state_json(uninterrupted)
        uninterrupted.advance_to_unique_budget(final_target)

        checkpoint_root = tmp_path / topology / "checkpoints"
        checkpoint_run = tmp_path / topology
        writer = LShadeCheckpointSession(
            checkpoint_root, run_directory=checkpoint_run,
            legacy_path=checkpoint_run / "old.json", resume=False,
        )
        split = _parity_backend(
            space, seed=717, primary=primary, hard_max=final_target,
            population=population, fingerprint=fingerprint, evaluator=evaluator,
        )
        split.advance_to_unique_budget(primary)
        assert _state_json(split) == primary_state
        writer.save(split)
        resumed_session = LShadeCheckpointSession(
            checkpoint_root, run_directory=checkpoint_run,
            legacy_path=checkpoint_run / "old.json", resume=True,
        )
        resumed = _parity_backend(
            space, seed=717, primary=primary, hard_max=final_target,
            population=population, fingerprint=fingerprint, evaluator=evaluator,
        )
        resumed_session.load(resumed)
        resumed.set_evaluator(evaluator)
        assert _state_json(resumed) == primary_state
        resumed.advance_to_unique_budget(final_target)
        assert _state_json(resumed) == _state_json(uninterrupted)
        assert resumed.unique_evaluations == final_target
        assert resumed.population_schedule_terminal_budget == primary
        assert resumed.hard_max_budget == final_target


def test_implementation_validation_runs_parity_and_initializer_gates(tmp_path):
    result = validate_hybrid_topology_screening(
        "configs/studies/hybrid_stage4b_comparison.yaml", tmp_path / "validation",
    )
    assert result["status"] == "PASS"
    assert result["stage4b_launched"] is False
    assert result["d_only_parity"]["status"] == "PASS"
    assert result["d_only_parity"]["overall_maximum_absolute_difference"] == 0.0
    assert result["hybrid_structure"]["status"] == "PASS"
    assert result["optimizer_and_accounting"]["P_D_P"]["initial_population"] == 288
    assert result["optimizer_and_accounting"]["P_D_P"]["hard_max_budget"] == 6400
    assert result["optimizer_and_accounting"]["P_D_P"]["population_schedule_terminal_budget"] == 4000
    assert result["provenance_status"]["schema_version"] == 2
    computation = {row["path"] for row in result["provenance_status"]["computation_dependencies"]}
    reporting = {row["path"] for row in result["provenance_status"]["reporting_dependencies"]}
    assert "src/sawopt/studies/hybrid_comparison.py" in computation
    assert "src/sawopt/optimizers/lshade.py" in computation
    assert "src/sawopt/core/hybrid.py" in computation
    assert "src/sawopt/reporting/hybrid_topology_report.py" in reporting
    assert not (computation & reporting)
    assert json.loads((tmp_path / "validation" / "metadata" / "implementation_validation.json").read_text())["status"] == "PASS"


def test_bounded_smoke_runner_produces_nonproduction_result_and_review_bundle(
    tmp_path, monkeypatch,
):
    context = _resolved_context("configs/studies/hybrid_stage4b_comparison.yaml")
    assert context["mode"] == "production"
    config = _smoke_config(tmp_path)
    monkeypatch.setattr(
        historical_hybrid, "differential_evolution",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("historical SciPy DE path invoked by Stage 4B")
        ),
    )
    result = run_hybrid_topology_screening(config, tmp_path / "tiny-run")
    assert result["status"] == "HYBRID_TOPOLOGY_SCREENING_COMPLETE"
    assert result["stage4b_launched"] is False
    assert result["scientific_conclusion"] is False
    assert result["topologies"][0]["absolute_unique_evaluations"] == 16
    assert result["normalized_sensitivity"][0]["absolute_unique_evaluations"] == 16
    assert result["fairness_contract"]["decision_policy"]["authoritative_primary_stratum"] == "equal_budget_B4000"
    assert result["fairness_contract"]["decision_policy"]["normalized_sensitivity_may_replace_primary"] is False
    assert result["fairness_contract"]["decision_policy"]["automatic_topology_promotion"] is False
    assert result["fairness_contract"]["decision_policy"]["automatic_topology_elimination"] is False
    assert "selected_topology" not in result and "promoted_topologies" not in result
    assert result["run_disposition"] == "REVIEW_WAITING"
    assert result["review_bundle_path"].endswith("_review.zip")
    trajectory = tmp_path / "tiny-run" / "metadata" / "trajectory.csv"
    assert trajectory.is_file()
    contents = trajectory.read_text(encoding="utf-8-sig")
    assert "absolute_unique_evaluations" in contents
    assert "evaluations_per_dimension" in contents


def test_normalized_sensitivity_never_replaces_primary_decision_stratum(tmp_path):
    config = _smoke_config(
        tmp_path, topology="P_D", evaluations_per_dimension=2,
        normalized_targets={"P_D": 26},
    )
    run = tmp_path / "extended-sensitivity-smoke"
    result = run_hybrid_topology_screening(config, run)
    primary = json.loads(
        (run / "optimization/P_D/seed303/primary_result.json").read_text(encoding="utf-8")
    )
    sensitivity = json.loads(
        (run / "optimization/P_D/seed303/normalized_sensitivity_result.json").read_text(encoding="utf-8")
    )
    assert result["topologies"][0]["absolute_unique_evaluations"] == 16
    assert primary["absolute_unique_evaluations"] == 16
    assert sensitivity["absolute_unique_evaluations"] == 26
    assert sensitivity["stratum"] == "dimension_normalized_sensitivity"
    assert result["normalized_sensitivity"][0]["absolute_unique_evaluations"] == 26
    policy = result["fairness_contract"]["decision_policy"]
    assert policy["authoritative_primary_stratum"] == "equal_budget_B4000"
    assert policy["normalized_sensitivity_may_replace_primary"] is False
    assert policy["automatic_topology_promotion"] is False
    assert policy["automatic_topology_elimination"] is False
    assert "selected_topology" not in result and "promoted_topologies" not in result


def test_production_decision_policy_cannot_be_relaxed_after_predeclaration(tmp_path):
    source = ROOT / "configs/studies/hybrid_stage4b_comparison.yaml"
    cfg = yaml.safe_load(source.read_text(encoding="utf-8"))
    cfg["base_config"] = str((ROOT / "configs/studies/dms_topology_screening.yaml").resolve())
    cfg["hybrid_comparison"]["decision_policy"]["automatic_topology_elimination"] = True
    path = tmp_path / "relaxed_decision_policy.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    try:
        _resolved_context(path)
    except ValueError as exc:
        assert "decision_policy" in str(exc)
    else:
        raise AssertionError("relaxed Stage 4B decision policy was accepted")


def test_prelaunch_production_config_cannot_start_without_launch_authorization(tmp_path):
    config = ROOT / "configs/studies/hybrid_stage4b_comparison.yaml"
    run = tmp_path / "unauthorized-production"
    try:
        run_hybrid_topology_screening(config, run)
    except PermissionError as exc:
        assert "production config is pre-launch only" in str(exc)
    else:
        raise AssertionError("pre-launch config unexpectedly allowed a production run")
    assert not run.exists()


def test_production_normalized_targets_must_match_predeclared_formula(tmp_path):
    source = ROOT / "configs/studies/hybrid_stage4b_comparison.yaml"
    cfg = yaml.safe_load(source.read_text(encoding="utf-8"))
    cfg["base_config"] = str((ROOT / "configs/studies/dms_topology_screening.yaml").resolve())
    cfg["hybrid_comparison"]["normalized_targets"]["P_D_P"] = 6401
    path = tmp_path / "mismatched_targets.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    try:
        _resolved_context(path)
    except ValueError as exc:
        assert "normalized_targets" in str(exc)
    else:
        raise AssertionError("mismatched normalized target was accepted")
