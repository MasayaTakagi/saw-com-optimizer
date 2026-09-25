from dataclasses import asdict
from pathlib import Path
import yaml

import numpy as np

from sawopt.core.models import FilterDesign
from sawopt.optimization.adaptive_frequency import (
    common_validation_grid,
    critical_frequencies,
    new_frequency_points,
)
from sawopt.optimization.budget import PlateauStopper, adaptive_budget_limits
from sawopt.optimization.cache import IncrementalFrequencyCache
from sawopt.optimization.polish import mixed_variable_polish
from sawopt.problem.evaluator import dense, evaluate_design


def _record(violation, il=5.0):
    return {
        "feasible": violation == 0,
        "max_violation": violation,
        "violations": {"x": violation},
        "metrics": {"worst_il_db": il},
    }


def test_critical_frequencies_include_passband_and_stopband_controllers():
    frequencies = np.array([700, 758, 770, 780, 803, 840, 900], float) * 1e6
    il = np.array([40, 1.0, 3.0, 1.5, 2.0, 35, 45.0])
    vswr = np.column_stack(([1, 1.2, 2.4, 1.1, 1.3, 1, 1], [1, 1.1, 1.2, 2.6, 1.2, 1, 1]))
    spec = {"passband": [758, 803], "stopbands": [[690, 710, 20], [830, 850, 30]]}
    points = critical_frequencies(frequencies, {"il": il, "vswr": vswr}, spec, slope_threshold_db=100)
    assert 770e6 in points
    assert 780e6 in points
    assert 700e6 in points
    assert 840e6 in points


def test_new_frequency_points_respects_tolerance():
    existing = np.array([1e6, 2e6, 3e6])
    candidates = np.array([1e6 + 500, 1.5e6, 3e6 + 2000])
    np.testing.assert_allclose(new_frequency_points(existing, candidates, 1000), [1.5e6, 3e6 + 2000])


def test_common_validation_grid_unions_candidate_controls():
    result = common_validation_grid(np.array([1.0, 3.0]), [[2.0], [4.0]], tolerance_hz=0)
    np.testing.assert_array_equal(result, np.array([1.0, 2.0, 3.0, 4.0]))


def test_incremental_cache_evaluates_only_unseen_frequencies():
    calls = []

    def evaluate(frequencies):
        calls.append(frequencies.copy())
        return {"value": frequencies ** 2, "metadata": 7}

    cache = IncrementalFrequencyCache(evaluate)
    first = cache.evaluate(np.array([1.0, 3.0]))
    second = cache.evaluate(np.array([1.0, 2.0, 3.0]))
    assert [len(call) for call in calls] == [2, 1]
    np.testing.assert_array_equal(second["value"], np.array([1.0, 4.0, 9.0]))
    np.testing.assert_array_equal(first["value"], np.array([1.0, 9.0]))


def test_incremental_diagnostics_keep_conservative_extrema_and_flags():
    def evaluate(frequencies):
        if frequencies[0] == 1:
            diagnostics = {
                "min_conductance_eigenvalue": -1.0,
                "worst_conductance_frequency_hz": 1.0,
                "reciprocity_error": .3,
                "worst_reciprocity_frequency_hz": 3.0,
                "max_acoustic_solve_residual": .1,
                "worst_acoustic_residual_frequency_hz": 3.0,
                "nonfinite_failure": False,
            }
        else:
            diagnostics = {
                "min_conductance_eigenvalue": -2.0,
                "worst_conductance_frequency_hz": 2.0,
                "reciprocity_error": .2,
                "worst_reciprocity_frequency_hz": 2.0,
                "max_acoustic_solve_residual": .2,
                "worst_acoustic_residual_frequency_hz": 2.0,
                "nonfinite_failure": True,
            }
        return {"value": frequencies ** 2, "_diagnostics": diagnostics}

    cache = IncrementalFrequencyCache(evaluate)
    cache.evaluate(np.array([1.0, 3.0]))
    diagnostics = cache.evaluate(np.array([1.0, 2.0, 3.0]))["_diagnostics"]
    assert diagnostics["min_conductance_eigenvalue"] == -2.0
    assert diagnostics["worst_conductance_frequency_hz"] == 2.0
    assert diagnostics["reciprocity_error"] == .3
    assert diagnostics["worst_reciprocity_frequency_hz"] == 3.0
    assert diagnostics["max_acoustic_solve_residual"] == .2
    assert diagnostics["nonfinite_failure"]


def test_adaptive_budget_limits_are_exact_and_monotonic():
    cases = [
        (10, [.7, .2, .1], [7, 9, 10]),
        (10, [7, 2, 1], [7, 9, 10]),
        (10, [1, 1, 1], [4, 7, 10]),
        (11, [.7, .2, .1], [8, 10, 11]),
    ]
    for total_budget, fractions, expected in cases:
        limits = adaptive_budget_limits(total_budget, 2, fractions)
        assert limits == expected
        assert limits == sorted(limits)
        assert all(1 <= limit <= total_budget for limit in limits)


def test_plateau_stopper_waits_for_minimum_and_patience():
    stopper = PlateauStopper(min_generations=3, patience_generations=2,
                             improvement_abs=.1, improvement_rel=.1)
    assert stopper.update(1.0) is False
    assert stopper.update(1.0) is False
    assert stopper.update(1.0) is True


def test_incremental_dense_evaluation_matches_full_metrics():
    root = Path(__file__).parents[3] / "configs"
    cfg = yaml.safe_load((root / "base/b28_dms_baseline.yaml").read_text(encoding="utf-8"))
    cfg["com"] = yaml.safe_load((root / "models/com_params_hypothetical.yaml").read_text(encoding="utf-8"))
    cfg["validation"] = {
        "dense_refinement_passes": 1, "adaptive_frequency_tolerance_hz": 1000,
        "adaptive_max_points_per_round": 16, "broad_points": 11,
        "band_points": 4, "max_step_mhz": 50,
    }
    design = FilterDesign()
    frequencies, (incremental, network, _simulation) = dense(design, cfg, 50, 50)
    full, full_network, full_simulation = evaluate_design(design, cfg, frequencies, 50, 50)
    np.testing.assert_array_equal(frequencies, full_simulation.frequencies_hz)
    np.testing.assert_allclose(network["il"], full_network["il"], rtol=1e-11, atol=1e-11)
    np.testing.assert_allclose(network["vswr"], full_network["vswr"], rtol=1e-11, atol=1e-11)
    assert (incremental["feasible"], incremental["max_violation"], incremental["metrics"]["worst_il_db"]) == (
        full["feasible"], full["max_violation"], full["metrics"]["worst_il_db"]
    )


def test_mixed_polish_honors_integer_steps_and_only_promotes_better_rank():
    design = asdict(FilterDesign(io_idt_pairs=30))
    record = {"design": design, "feasible": False, "max_violation": .5,
              "violations": {"x": .5}, "metrics": {"worst_il_db": 5.0}}
    cfg = {
        "constraints": {"max_length_um": 750, "max_width_um": 250,
                        "min_electrode_width_um": .8, "min_electrode_gap_um": .8,
                        "max_electrodes": 500},
        "micro_polish": {"enabled": True, "max_passes": 1,
                         "continuous_steps_fraction_of_bound_span": [.01],
                         "integer_steps": [-1, 1]},
    }

    def evaluate(candidate, *_args, **_kwargs):
        improved = candidate.io_idt_pairs == 29
        value = .4 if improved else .5
        return ({"feasible": False, "max_violation": value,
                 "violations": {"x": value}, "metrics": {"worst_il_db": 5.0}}, None, None)

    polished, diagnostic = mixed_variable_polish(
        record, cfg, 50, 50, "outer_ports", np.array([1.0]), evaluate_fn=evaluate
    )
    assert polished["design"]["io_idt_pairs"] == 29
    assert diagnostic["promoted"]
    assert diagnostic["evaluations"] > 0


def test_mixed_polish_shrinks_continuous_step_after_no_improvement():
    design = asdict(FilterDesign())
    record = {"design": design, "feasible": False, "max_violation": .5,
              "violations": {"x": .5}, "metrics": {"worst_il_db": 5.0}}
    cfg = {
        "constraints": {"max_length_um": 750, "max_width_um": 250,
                        "min_electrode_width_um": .8, "min_electrode_gap_um": .8,
                        "max_electrodes": 500},
        "micro_polish": {"enabled": True, "max_passes": 4,
                         "continuous_steps_fraction_of_bound_span": [.01],
                         "minimum_step_fraction": .0025, "shrink_factor": .5,
                         "integer_steps": [-1, 1]},
    }

    def evaluate(candidate, *_args, **_kwargs):
        return (dict(record, design=asdict(candidate)), None, None)

    polished, diagnostic = mixed_variable_polish(
        record, cfg, 50, 50, "outer_ports", np.array([1.0]), evaluate_fn=evaluate
    )
    assert polished is record
    np.testing.assert_allclose(diagnostic["step_fraction_history"], [.01, .005, .0025])
    assert not diagnostic["promoted"]
