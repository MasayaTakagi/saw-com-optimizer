from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from sawopt.core.metrics import search_grid
from sawopt.io.config import load_experiment_config
from sawopt.optimizers.lshade import LShadeBackend
from sawopt.optimizers.selection import DEFAULT_COMPARATOR
from sawopt.studies import stage3_8c_r1_geometry_gate as r1


def _invalid(geometry_violation: float):
    return {
        "evaluation_status": "GEOMETRY_REJECTED",
        "geometry_valid": False,
        "geometry_violations": {"max_total_length": geometry_violation},
        "metrics": {},
        "violations": {},
        "filter_metrics_available": False,
        "feasible": False,
        "max_violation": None,
        "sum_violation": None,
        "objective": None,
    }


def _valid(max_violation: float, *, feasible: bool = False, worst_il: float = 9.0):
    return {
        "evaluation_status": "PHYSICS_EVALUATED",
        "geometry_valid": True,
        "geometry_violations": {"max_total_length": 0.0},
        "metrics": {
            "worst_il_db": worst_il,
            "ripple_db": 2.0,
            "input_vswr": 1.4,
            "output_vswr": 1.5,
            "source_return_loss_db_min": 16.0,
            "load_return_loss_db_min": 15.0,
            "stop_attenuation_db": [30.0, 30.0, 31.0, 32.0],
        },
        "violations": {"filter": max_violation},
        "filter_metrics_available": True,
        "feasible": feasible,
        "max_violation": max_violation,
        "sum_violation": max_violation,
        "objective": max_violation + worst_il,
    }


def test_tiny_geometry_violation_never_beats_valid_filter_candidate():
    invalid = _invalid(1e-10)
    valid = _valid(10.0)
    assert r1.R1_COMPARATOR.rank_key(valid) < r1.R1_COMPARATOR.rank_key(invalid)


def test_invalid_candidates_order_by_geometry_violation_only():
    small = _invalid(1e-10)
    large = _invalid(0.25)
    assert r1.R1_COMPARATOR.rank_key(small) < r1.R1_COMPARATOR.rank_key(large)
    assert small["metrics"] == {} and large["metrics"] == {}


def test_successful_geometry_valid_pairs_preserve_default_filter_order():
    left = _valid(0.15, worst_il=8.0)
    right = _valid(0.30, worst_il=7.0)
    assert r1.R1_COMPARATOR.rank_key(left)[2:] == DEFAULT_COMPARATOR.rank_key(left)
    assert r1.R1_COMPARATOR.rank_key(right)[2:] == DEFAULT_COMPARATOR.rank_key(right)
    assert r1.R1_COMPARATOR.better(left, right) == DEFAULT_COMPARATOR.better(left, right)


def test_incumbent_pbest_replacement_shrink_and_trace_keep_geometry_priority():
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
        comparator=r1.R1_COMPARATOR,
    )
    initial = np.asarray([[0.05], [0.35], [0.50], [0.62], [0.72], [0.82], [0.90], [0.98]])
    backend.initialize(evaluator, population=initial)
    assert backend.incumbent()["geometry_valid"] is True
    assert backend._ordered_indices()[0] != 0
    assert backend.best_so_far_trace[-1]["rank_key"][0] == 0.0

    backend._sample_parameters = lambda _memory: (1.0, 1.0)
    backend._sample_indices = lambda *_args: (1, 2, np.asarray([0.20]))
    backend._repair_boundary = lambda mutant, _parent: mutant
    backend._generation(9)
    assert backend._population[0].result["geometry_valid"] is True
    backend._resize_population(6)
    assert all(member.result["geometry_valid"] for member in backend._population)
    backend._record_trace()
    assert backend.incumbent()["geometry_valid"] is True
    assert backend.best_so_far_trace[-1]["rank_key"][0] == 0.0


def test_final_common_grid_selector_uses_geometry_priority():
    chosen = r1.select_common_grid_candidate([_invalid(1e-10), _valid(10.0)])
    assert chosen is not None
    assert chosen["geometry_valid"] is True


def test_pilot_gate_keeps_legacy_threshold_and_applies_r11_threshold():
    row = {
        "material": "M0",
        "topology": r1.T0,
        "optimizer_incumbent_geometry_valid": True,
        "r1_counters": {
            "geometry_valid_candidates": 1,
            "valid_physics_evaluations": 1,
            "solved_frequency_points": 1,
        },
        "finite_search_metrics": True,
        "finite_common_metrics": True,
        "population_initialization_passed": True,
        "geometry_rejection_fraction": 0.0,
        "initial_population_sampling": {
            "initial_sampling_draws": 100,
            "initial_sampling_geometry_rejections": 80,
            "initializer_method": "independent_uniform_rejection_v1",
        },
    }
    legacy_rows = [row.copy() for _ in range(6)]
    assert r1._pilot_gate_status(legacy_rows) == (True, [])

    conditional_rows = [
        {**row, "initial_population_sampling": {
            **row["initial_population_sampling"],
            "initializer_method": "conditional_integer_feasible_set_v1",
        }}
        for _ in range(6)
    ]
    passed, failures = r1._pilot_gate_status(conditional_rows)
    assert not passed
    assert len(failures) == 6
    assert all("not below 50%" in failure for failure in failures)

    for conditional_row in conditional_rows:
        conditional_row["initial_population_sampling"]["initial_sampling_geometry_rejections"] = 49
    assert r1._pilot_gate_status(conditional_rows) == (True, [])

    r12_rows = []
    for _ in range(6):
        r12_row = row.copy()
        r12_row["initial_population_sampling"] = {
            "study_revision": "R1.2",
            "initializer_method": "independent_uniform_rejection_v1",
            "initial_sampling_draws": 100,
            "initial_sampling_geometry_rejections": 95,
            "requested_population_size": 10,
            "valid_accepted_candidates": 10,
            "geometry_valid_members": 10,
            "max_attempts_exceeded": False,
            "unique_population_count": 10,
            "initializer_diversity_gate_passed": True,
            "distribution_regression_passed": True,
            "population_generation_time_s": 1.0,
        }
        r12_row["initializer_runtime_limit_s"] = 60.0
        r12_rows.append(r12_row)
    assert r1._pilot_gate_status(r12_rows) == (True, [])


def test_nonfinite_filter_metrics_are_reclassified_as_physics_failure(monkeypatch):
    cfg = load_experiment_config("configs/studies/stage3_8c_r1_pilot.yaml")
    design = r1.initial_design("M0", r1.T0, cfg)
    monkeypatch.setattr(
        r1,
        "simulate_topology",
        lambda *_args, **_kwargs: SimpleNamespace(y_parameters=np.zeros((2, 2, 2)), diagnostics={}),
    )
    monkeypatch.setattr(
        r1,
        "evaluate",
        lambda *_args, **_kwargs: {"gt": np.zeros(2), "s": np.zeros((2, 2, 2))},
    )

    def nonfinite_measure(*_args, **_kwargs):
        return {
            "metrics": {
                "worst_il_db": float("nan"),
                "ripple_db": 1.0,
                "input_vswr": 1.0,
                "output_vswr": 1.0,
                "source_return_loss_db_min": 20.0,
                "load_return_loss_db_min": 20.0,
                "stop_attenuation_db": [30.0, 30.0, 30.0, 30.0],
            },
            "violations": {"filter": 0.1, "geometry": 0.0},
            "feasible": False,
            "max_violation": 0.1,
            "sum_violation": 0.1,
            "objective": 1.0,
        }

    monkeypatch.setattr(r1, "measure", nonfinite_measure)
    record = r1.evaluate_r1_design(
        design, object(), cfg, np.asarray([750e6, 760e6]), r1.T0,
    )
    assert record["evaluation_status"] == "PHYSICS_FAILED"
    assert record["metrics"] == {}
    assert record["violations"] == {}
    assert record["geometry_valid"] is True


def test_comparator_improvement_is_finite_and_positive_for_gate_transition():
    invalid = _invalid(float("inf"))
    valid = _valid(10.0)
    improvement = r1.R1_COMPARATOR.improvement(invalid, valid)
    assert np.isfinite(improvement)
    assert improvement > 0.0


def test_population_sampling_is_deterministic_and_geometry_valid():
    cfg = load_experiment_config("configs/studies/stage3_8c_r1_1_pilot.yaml")
    for material in r1.MATERIALS:
        for topology in r1.TOPOLOGIES:
            active, hard, integer_indices = r1.material_bounds(cfg, material, topology)
            size = 32
            first, first_stats = r1.sample_geometry_valid_population(
                cfg, material, topology, seed=20260917,
                population_size=size, max_attempts=10000,
            )
            second, second_stats = r1.sample_geometry_valid_population(
                cfg, material, topology, seed=20260917,
                population_size=size, max_attempts=10000,
            )
            np.testing.assert_array_equal(first, second)
            for key in first_stats:
                if key != "population_generation_time_s":
                    assert first_stats[key] == second_stats[key]
            assert first.shape == (size, len(active))
            assert first_stats["requested_population_size"] == size
            assert first_stats["valid_accepted_candidates"] == size
            assert first_stats["unique_population_count"] == size
            assert first_stats["initial_sampling_draws"] == (
                first_stats["initial_sampling_geometry_rejections"]
                + first_stats["initial_sampling_duplicate_rejections"]
                + first_stats["random_initial_accepts"]
            )
            assert first_stats["geometry_rejection_fraction"] < 0.50

            physical = active[:, 0] + first * (active[:, 1] - active[:, 0])
            np.testing.assert_allclose(
                physical,
                np.asarray([
                    r1._canonical_physical(row, active, integer_indices)
                    for row in physical
                ]),
                rtol=0.0,
                atol=1e-10,
            )
            assert np.all(physical >= active[:, 0])
            assert np.all(physical <= active[:, 1])
            assert len({tuple(row) for row in physical}) == size
            for vector in physical:
                design = r1.decode_design(vector, topology, cfg)
                dims, violations = r1.geometry(design, cfg["constraints"])
                assert np.isfinite(list(dims.values())).all()
                assert max(violations, default=0.0) == 0.0

            names = {
                r1.T0: ("wavelength_um", "io_idt_pairs", "center_idt_pairs", "reflector_electrodes",
                        "idt_gap_lambda", "reflector_gap_lambda", "aperture_um", "center_wavelength_um",
                        "reflector_wavelength_um"),
                r1.T1: ("wavelength_A_um", "wavelength_B_um", "wavelength_C_um",
                        "reflector_wavelength_um", "pairs_A", "pairs_B", "pairs_C",
                        "common_idt_gap_lambda", "reflector_gap_lambda", "aperture_um"),
                r1.T2: ("track_A_main_wavelength_um", "track_B_main_wavelength_um", "io_idt_pairs",
                        "center_idt_pairs", "reflector_electrodes", "idt_gap_lambda",
                        "reflector_gap_lambda", "center_wavelength_ratio", "reflector_wavelength_ratio",
                        "total_aperture_um"),
            }[topology]
            for vector in physical:
                model = r1._geometry_sampling_model(cfg, topology, vector)
                counts = {index: int(round(vector[index])) for index in integer_indices}
                modeled_electrodes = model["base_electrodes"] + sum(
                    model["electrode_coefficients"][index] * count
                    for index, count in counts.items()
                )
                modeled_lengths = [
                    base + sum(
                        model["length_coefficients_um"][index][track] * count
                        for index, count in counts.items()
                    )
                    for track, base in enumerate(model["base_lengths_um"])
                ]
                dims, _ = r1.geometry(r1.decode_design(vector, topology, cfg), cfg["constraints"])
                assert np.isclose(dims["electrodes"], modeled_electrodes)
                assert np.isclose(dims["length_um"], max(modeled_lengths))
            assert set(first_stats["variable_distributions"]) == set(names)


def test_r1_2_rejection_sampler_replays_and_matches_monte_carlo_reference():
    cfg = load_experiment_config("configs/studies/stage3_8c_r1_2_pilot.yaml")
    for material in r1.MATERIALS:
        for topology in r1.TOPOLOGIES:
            active, hard, integer_indices = r1.material_bounds(cfg, material, topology)
            size = r1._population_size(cfg, topology, 256, hard)
            arguments = {
                "seed": 20260917,
                "population_size": size,
                "max_attempts": max(10000, 60 * size),
                "reference_proposals": 10000,
                "bootstrap_replicates": 128,
            }
            first, stats = r1.sample_independent_uniform_population(
                cfg, material, topology, **arguments,
            )
            second, second_stats = r1.sample_independent_uniform_population(
                cfg, material, topology, **arguments,
            )
            np.testing.assert_array_equal(first, second)
            assert first.shape == (size, len(active))
            assert stats["requested_population_size"] == size
            assert stats["valid_accepted_candidates"] == size
            assert stats["geometry_valid_members"] == size
            assert stats["unique_population_count"] == size
            assert stats["initializer_method"] == "independent_uniform_rejection_v1"
            assert stats["study_revision"] == "R1.2"
            assert stats["initial_sampling_draws"] == (
                stats["initial_sampling_geometry_rejections"]
                + stats["initial_sampling_duplicate_rejections"]
                + stats["random_initial_accepts"]
            )
            assert stats["distribution_regression_passed"] is True
            assert stats["initializer_diversity_gate_passed"] is True
            assert stats["population_generation_time_s"] >= 0.0
            assert stats["independent_uniform_reference"]["candidate_draws"] == 10000
            assert set(stats["variable_distributions"]) == set(r1._r1_variable_names(topology))
            for key in (
                "total_candidate_draws", "initial_sampling_geometry_rejections",
                "initial_sampling_duplicate_rejections", "variable_distributions",
                "geometry_metric_distributions", "distribution_validation",
                "initializer_diversity_gate_passed", "distribution_regression_passed",
            ):
                assert stats[key] == second_stats[key]

            physical = active[:, 0] + first * (active[:, 1] - active[:, 0])
            assert np.all(physical >= active[:, 0])
            assert np.all(physical <= active[:, 1])
            assert len({tuple(value) for value in physical}) == size
            for vector in physical:
                design = r1.decode_design(vector, topology, cfg)
                _dims, violations = r1.geometry(design, cfg["constraints"])
                assert max(violations, default=0.0) == 0.0


def test_r1_2_integer_canonicalization_preserves_half_mass_endpoint_law():
    low, high = 1.0, 5.0
    integer_values = np.arange(1, 6)
    probabilities = [
        max(0.0, min(high, value + 0.5) - max(low, value - 0.5)) / (high - low)
        for value in integer_values
    ]
    np.testing.assert_allclose(probabilities, [0.125, 0.25, 0.25, 0.25, 0.125])
    active = np.asarray([[low, high]])
    proposal_points = np.asarray([[1.1], [1.6], [2.1], [2.6], [3.1], [3.6], [4.1], [4.6]])
    canonical = np.asarray([
        r1._canonical_physical(point, active, (0,))[0]
        for point in proposal_points
    ])
    np.testing.assert_array_equal(canonical, [1, 2, 2, 3, 3, 4, 4, 5])


def test_r1_2_distribution_regression_detects_r1_1_conditional_order_bias():
    cfg = load_experiment_config("configs/studies/stage3_8c_r1_2_pilot.yaml")
    material, topology = "M0", r1.T2
    active, hard, integer_indices = r1.material_bounds(cfg, material, topology)
    size = r1._population_size(cfg, topology, 256, hard)
    conditional_cfg = load_experiment_config("configs/studies/stage3_8c_r1_1_pilot.yaml")
    conditional, _stats = r1.sample_geometry_valid_population(
        conditional_cfg, material, topology, seed=20260917,
        population_size=size, max_attempts=10000,
    )
    physical = active[:, 0] + conditional * (active[:, 1] - active[:, 0])
    random_members = physical[1:]
    sample_metrics = r1._geometry_population_metrics(random_members, cfg, topology)
    _reference_stats, reference, reference_metrics = r1._uniform_geometry_reference(
        cfg, material, topology, active=active, integer_indices=integer_indices,
        seed=91233, proposals=10000,
    )
    validation = r1._distribution_validation(
        random_members, reference, sample_metrics, reference_metrics,
        integer_indices, seed=77881, bootstrap_replicates=128,
    )
    assert validation["distribution_match_passed"] is False


def test_r1_2_rejects_invalid_proposal_without_repair(monkeypatch):
    cfg = load_experiment_config("configs/studies/stage3_8c_r1_2_pilot.yaml")
    active, _hard, integer_indices = r1.material_bounds(cfg, "M0", r1.T0)
    fixed = r1._design_vector(r1.initial_design("M0", r1.T0, cfg), r1.T0)
    invalid = np.asarray([5.0, 100, 24, 160, 1.0, 1.0, 100.0, 5.0, 5.0])
    valid = fixed.copy()
    valid[0] = 4.9
    proposals = iter((invalid, valid))
    seen = []

    def proposal(_rng, _low, _high, _integer_indices):
        value = next(proposals).copy()
        seen.append(value)
        return value

    monkeypatch.setattr(r1, "_independent_uniform_candidate", proposal)
    population, stats = r1.sample_independent_uniform_population(
        cfg, "M0", r1.T0, seed=20260917, population_size=2,
        max_attempts=2, reference_proposals=0, bootstrap_replicates=0,
    )
    physical = active[:, 0] + population * (active[:, 1] - active[:, 0])
    assert stats["initial_sampling_geometry_rejections"] == 1
    assert stats["random_initial_accepts"] == 1
    assert np.array_equal(seen[0], invalid)
    assert not np.any(np.all(physical == invalid, axis=1))
    assert np.all(physical[1] == valid)
    assert np.all(physical[1] == r1._canonical_physical(valid, active, integer_indices))


def test_r1_2_attempt_cap_fails_explicitly_with_accounting():
    cfg = load_experiment_config("configs/studies/stage3_8c_r1_2_pilot.yaml")
    with np.testing.assert_raises(r1.InitializerExhausted) as caught:
        r1.sample_independent_uniform_population(
            cfg, "M0", r1.T0, seed=20260917, population_size=2,
            max_attempts=0, reference_proposals=10000,
        )
    assert "INITIALIZER_EXHAUSTED" in str(caught.exception)
    assert caught.exception.diagnostics["failure_code"] == "INITIALIZER_EXHAUSTED"
    assert caught.exception.diagnostics["total_candidate_draws"] == 0
    assert caught.exception.diagnostics["valid_accepted_candidates"] == 1


def test_r1_2_final_confirmation_and_production_candidate_fingerprints_match():
    final_path = Path("configs/studies/stage3_8c_r1_2_final_confirmation.yaml")
    production_path = Path("configs/studies/stage3_8c_r1_2_production.yaml")
    assert r1._source_fingerprint(final_path.read_text(encoding="utf-8")) == r1._source_fingerprint(
        production_path.read_text(encoding="utf-8")
    )


def test_r1_2_final_confirmation_skips_repeated_distribution_reference():
    cfg = load_experiment_config("configs/studies/stage3_8c_r1_2_final_confirmation.yaml")
    population, sampling, row = r1._population_preflight(
        cfg, "M0", r1.T2, 20260917, 256, 10000,
    )
    assert population.shape[0] == row["population_size"]
    assert row["initializer_gate_failures"] == []
    assert "independent_uniform_reference" not in sampling
    assert sampling["distribution_validation_status"] == "SKIPPED_FINAL_CONFIRMATION"
    assert sampling["initializer_diversity_validation_status"] == "SKIPPED_FINAL_CONFIRMATION"


def test_r1_2_production_gate_requires_matching_final_confirmation(tmp_path):
    config_path = Path("configs/studies/stage3_8c_r1_2_production.yaml")
    cfg = load_experiment_config(config_path)
    confirmation_dir = tmp_path / "confirmation"
    confirmation_dir.mkdir()
    cfg["stage3_8c_r1"]["pilot_run_dir"] = str(confirmation_dir)
    fingerprint = r1._source_fingerprint(config_path.read_text(encoding="utf-8"))
    gate = {
        "status": "PASS",
        "final_confirmation_fingerprint": fingerprint,
        "production_candidate_fingerprint": fingerprint,
        "common_validation_grid_id": "grid-id",
        "gates": {"fingerprint": True, "pilot": True},
    }
    (confirmation_dir / "stage3_8c_r1_2_final_confirmation_gate.json").write_text(
        json.dumps(gate), encoding="utf-8",
    )
    (confirmation_dir / "STAGE3_8C_R1_2_FINAL_CONFIRMATION_PASS.txt").write_text(
        "pass\n", encoding="utf-8",
    )
    r1._check_final_confirmation_gate(cfg, fingerprint, "grid-id")
    gate["production_candidate_fingerprint"] = "different"
    (confirmation_dir / "stage3_8c_r1_2_final_confirmation_gate.json").write_text(
        json.dumps(gate), encoding="utf-8",
    )
    with np.testing.assert_raises(RuntimeError):
        r1._check_final_confirmation_gate(cfg, fingerprint, "grid-id")


def test_conditional_integer_feasible_sets_include_geometry_limit_edges():
    cfg = load_experiment_config("configs/studies/stage3_8c_r1_1_pilot.yaml")
    cases = (
        # T0: R + 2I + C = 150 at 5 um gives exactly 750 um total length.
        ("M0", r1.T0, np.asarray([5.0, 43, 24, 40, 0.0, 0.0, 80.0, 5.0, 5.0]),
         {1: 43, 2: 24}, 3, 40, 300.0),
        # T1: the C count at 14 reaches 750 um with fixed 40-electrode reflectors.
        ("M0", r1.T1, np.asarray([5.0, 5.0, 5.0, 5.0, 24, 24, 14, 0.0, 0.0, 80.0]),
         {4: 24, 5: 24}, 6, 14, 300.0),
        # T2: both the 500-electrode and 750-um device limits are active.
        ("MLIT", r1.T2, np.asarray([
            750.0 / (104 * 1.1 + 2 * 8 + 5 * 1.08 + 2 * (3 + 3)),
            750.0 / (104 * 1.1 + 2 * 8 + 5 * 1.08 + 2 * (3 + 3)),
            8, 5, 104, 3.0, 3.0, 1.08, 1.1, 80.0,
        ]), {2: 8, 3: 5}, 4, 104, 500.0),
    )
    for material, topology, vector, selected, current, expected_count, expected_electrodes in cases:
        active, _hard, integer_indices = r1.material_bounds(cfg, material, topology)
        support = r1._integer_search_support(active, integer_indices)
        model = r1._geometry_sampling_model(cfg, topology, vector)
        upper = r1._count_upper_bound(
            current, model=model, selected=selected, remaining=(), support=support,
            constraints=cfg["constraints"],
        )
        assert upper == expected_count
        design = r1.decode_design(vector, topology, cfg)
        dims, violations = r1.geometry(design, cfg["constraints"])
        assert max(violations, default=0.0) == 0.0
        assert np.isclose(dims["length_um"], 750.0, rtol=0.0, atol=1e-8)
        assert np.isclose(dims["electrodes"], expected_electrodes, rtol=0.0, atol=1e-10)


def test_counter_partition_and_search_frequency_accounting():
    counters = r1.EvaluationCounters()
    counters.observe_search(_invalid(0.1), 7)
    counters.observe_search(_valid(10.0), 7)
    counters.observe_search({"evaluation_status": "PHYSICS_FAILED"}, 7)
    r1._assert_counter_invariants(counters, unique=3, search_frequency_count=7)
    assert counters.geometry_rejections == 1
    assert counters.geometry_valid_candidates == 2
    assert counters.valid_physics_evaluations == 1
    assert counters.physics_failures == 1
    assert counters.search_frequency_points == 7


def test_counter_invariants_use_geometry_partition_and_validation_is_restorable():
    counters = r1.EvaluationCounters()
    counters.observe_search(_invalid(0.01), 5)
    counters.observe_search(_valid(10.0), 5)
    r1._assert_counter_invariants(counters, unique=2, search_frequency_count=5)
    counters.restore_validation({
        "validation_evaluations": 3,
        "validation_physics_failures": 1,
        "validation_frequency_points": 10,
    })
    snapshot = r1._counter_snapshot(
        SimpleNamespace(summary=lambda: {
            "unique_evaluations": 2, "proposals_total": 2, "cache_hits": 0,
        }),
        counters, search_frequency_count=5, elapsed_s=1.25,
    )
    assert snapshot["geometry_rejections"] + snapshot["geometry_valid_candidates"] == 2
    assert snapshot["valid_physics_evaluations"] <= snapshot["geometry_valid_candidates"]
    assert snapshot["validation_evaluations"] == 3
    assert snapshot["validation_frequency_points"] == 10
    assert snapshot["solved_frequency_points"] == 15


def test_aggregate_topology_ranking_applies_documented_priority_order():
    valid_fraction_wins = {
        "feasible_fraction": 1.0,
        "median_max_violation": 0.2,
        "p75_max_violation": 0.3,
        "median_sum_violation": 0.5,
        "median_worst_il_db": 5.0,
        "seed_consistent": True,
        "seed_max_violation_spread": 0.0,
        "best_seed_max_violation": 0.2,
        "best_seed_sum_violation": 0.5,
        "best_seed_worst_il_db": 5.0,
    }
    lower_violation_loses = dict(valid_fraction_wins, feasible_fraction=0.5,
                                 median_max_violation=0.0)
    assert (r1._topology_summary_rank_key(valid_fraction_wins)
            < r1._topology_summary_rank_key(lower_violation_loses))

    consistent = dict(valid_fraction_wins, seed_consistent=True, seed_max_violation_spread=0.1)
    inconsistent = dict(valid_fraction_wins, seed_consistent=False, seed_max_violation_spread=0.0)
    assert r1._topology_summary_rank_key(consistent) < r1._topology_summary_rank_key(inconsistent)

    better_single_seed = dict(consistent, best_seed_max_violation=0.1)
    assert r1._topology_summary_rank_key(better_single_seed) < r1._topology_summary_rank_key(consistent)
