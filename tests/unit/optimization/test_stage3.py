import numpy as np
import unittest
from dataclasses import asdict
from unittest.mock import patch
from pathlib import Path
import yaml

from sawopt.optimization.optimizer_utils import (
    IncrementalFrequencyCache, PlateauStopper, critical_frequencies,
    aggregate_diagnostics, common_validation_grid, validated_candidate_selection,
)
from sawopt.optimization.stage2_study import aggregate_pair_rank
from sawopt.optimization.convergence_study import (
    DEFAULT_THRESHOLDS, _status, parity_check,
)
from sawopt.optimization.study import (
    _adaptive_budget_limits, _mixed_variable_polish, dense, evaluate_design,
)
from sawopt.core.models import FilterDesign


def _record(violation, il=5.0):
    return {
        'feasible': violation == 0,
        'max_violation': violation,
        'violations': {'x': violation},
        'metrics': {'worst_il_db': il},
    }


def test_vswr_peak_adds_local_refinement_points():
    f = np.array([758, 770, 780, 790, 803], dtype=float) * 1e6
    net = {
        'il': np.ones(len(f)),
        'vswr': np.column_stack(([1, 1, 3, 1, 1], [1, 1, 1, 1, 1])),
    }
    points = critical_frequencies(f, net, {'passband': [758, 803], 'stopbands': []},
                                  slope_threshold_db=100, max_points=64)
    assert 775e6 in points or 785e6 in points


def test_incremental_cache_evaluates_only_new_points():
    calls = []

    def evaluate(frequencies):
        calls.append(frequencies.copy())
        return {'value': frequencies ** 2, 'metadata': 7}

    cache = IncrementalFrequencyCache(evaluate)
    first = cache.evaluate(np.array([1.0, 3.0]))
    second = cache.evaluate(np.array([1.0, 2.0, 3.0]))
    assert [len(call) for call in calls] == [2, 1]
    np.testing.assert_array_equal(second['value'], np.array([1.0, 4.0, 9.0]))
    np.testing.assert_array_equal(first['value'], np.array([1.0, 9.0]))


def test_incremental_diagnostics_use_global_extrema_and_or_flags():
    batches = []

    def evaluate(frequencies):
        batches.append(frequencies.copy())
        if frequencies[0] == 1:
            diagnostics = {
                'min_conductance_eigenvalue': -1.0,
                'worst_conductance_frequency_hz': 1.0,
                'reciprocity_error': .3,
                'worst_reciprocity_frequency_hz': 3.0,
                'max_acoustic_solve_residual': .1,
                'worst_acoustic_residual_frequency_hz': 3.0,
                'nonfinite_failure': False,
            }
        else:
            diagnostics = {
                'min_conductance_eigenvalue': -2.0,
                'worst_conductance_frequency_hz': 2.0,
                'reciprocity_error': .2,
                'worst_reciprocity_frequency_hz': 2.0,
                'max_acoustic_solve_residual': .2,
                'worst_acoustic_residual_frequency_hz': 2.0,
                'nonfinite_failure': True,
            }
        return {'value': frequencies ** 2, '_diagnostics': diagnostics}

    cache = IncrementalFrequencyCache(evaluate)
    cache.evaluate(np.array([1.0, 3.0]))
    result = cache.evaluate(np.array([1.0, 2.0, 3.0]))
    diagnostics = result['_diagnostics']
    assert diagnostics['min_conductance_eigenvalue'] == -2.0
    assert diagnostics['worst_conductance_frequency_hz'] == 2.0
    assert diagnostics['reciprocity_error'] == .3
    assert diagnostics['worst_reciprocity_frequency_hz'] == 3.0
    assert diagnostics['max_acoustic_solve_residual'] == .2
    assert diagnostics['nonfinite_failure']


def test_adaptive_round_limits_share_one_total_budget():
    assert _adaptive_budget_limits(10, 2, [.7, .2, .1]) == [7, 9, 10]


def test_adaptive_round_limits_are_exact_and_monotonic():
    cases = [
        (10, [.7, .2, .1], [7, 9, 10]),
        (10, [7, 2, 1], [7, 9, 10]),
        (10, [1, 1, 1], [4, 7, 10]),
        (11, [.7, .2, .1], [8, 10, 11]),
    ]
    for total_budget, fractions, expected in cases:
        limits = _adaptive_budget_limits(total_budget, 2, fractions)
        assert limits == expected
        assert limits == sorted(limits)
        assert all(1 <= limit <= total_budget for limit in limits)
        assert limits[-1] == total_budget


def test_two_consecutive_budget_plateaus_are_required():
    rows = []
    for budget in (100, 200, 400):
        for seed in (1, 2, 3):
            rows.append({
                'budget': budget, 'seed': seed, 'feasible': False,
                'max_violation': .5, 'worst_il_db': 4.0,
                'validation_gap_primary': 0.0,
                'micro_polish_improvement': 0.0,
                'fraction_of_budget_at_last_significant_improvement': .5,
            })
    status, evidence = _status(rows, DEFAULT_THRESHOLDS)
    assert status == 'converged'
    assert len(evidence['paired_budget_deltas']) == 2

    status, _ = _status(
        [dict(row, max_violation=row['max_violation'] - (row['budget'] / 1000))
         for row in rows], DEFAULT_THRESHOLDS)
    assert status == 'likely_underoptimized'


def test_incremental_dense_matches_full_metrics_rank_and_diagnostics():
    root = Path(__file__).parents[3] / 'configs'
    cfg = yaml.safe_load((root / 'base/b28_dms_baseline.yaml').read_text())
    cfg['com'] = yaml.safe_load((root / 'models/com_params_hypothetical.yaml').read_text())
    cfg['validation'] = {
        'dense_refinement_passes': 1, 'adaptive_frequency_tolerance_hz': 1000,
        'adaptive_max_points_per_round': 16, 'broad_points': 11,
        'band_points': 4, 'max_step_mhz': 50,
    }
    d = FilterDesign()
    frequencies, (incremental, net, sim) = dense(d, cfg, 50, 50)
    full, full_net, full_sim = evaluate_design(d, cfg, frequencies, 50, 50)
    np.testing.assert_array_equal(frequencies, full_sim.frequencies_hz)
    np.testing.assert_allclose(net['il'], full_net['il'], rtol=1e-11, atol=1e-11)
    np.testing.assert_allclose(net['vswr'], full_net['vswr'], rtol=1e-11, atol=1e-11)
    assert (incremental['feasible'], incremental['max_violation'], incremental['metrics']['worst_il_db']) == \
        (full['feasible'], full['max_violation'], full['metrics']['worst_il_db'])
    for key in incremental['diagnostics']:
        if isinstance(incremental['diagnostics'][key], (int, float)):
            assert np.isclose(incremental['diagnostics'][key], full['diagnostics'][key], rtol=1e-10, atol=1e-10)


def test_mixed_polish_honors_integer_step_and_only_promotes_better_rank():
    design = asdict(FilterDesign(io_idt_pairs=30))
    record = {
        'design': design, 'feasible': False, 'max_violation': .5,
        'violations': {'x': .5}, 'metrics': {'worst_il_db': 5.0},
    }
    cfg = {
        'constraints': {'max_length_um': 750, 'max_width_um': 250,
                        'min_electrode_width_um': .8, 'min_electrode_gap_um': .8,
                        'max_electrodes': 500},
        'micro_polish': {'enabled': True, 'max_passes': 1,
                         'continuous_steps_fraction_of_bound_span': [.01],
                         'integer_steps': [-1, 1]},
    }

    def fake_evaluate(candidate, *_args, **_kwargs):
        improved = candidate.io_idt_pairs == 29
        value = .4 if improved else .5
        return ({'feasible': False, 'max_violation': value,
                 'violations': {'x': value}, 'metrics': {'worst_il_db': 5.0}}, None, None)

    with patch('sawopt.optimization.study.evaluate_design', side_effect=fake_evaluate):
        polished, diagnostic = _mixed_variable_polish(
            record, cfg, 50, 50, 'outer_ports', np.array([1.0]))
    assert polished['design']['io_idt_pairs'] == 29
    assert diagnostic['promoted']
    assert diagnostic['evaluations'] > 0


def test_mixed_polish_shrinks_continuous_step_after_no_improvement():
    design = asdict(FilterDesign())
    record = {
        'design': design, 'feasible': False, 'max_violation': .5,
        'violations': {'x': .5}, 'metrics': {'worst_il_db': 5.0},
    }
    cfg = {
        'constraints': {'max_length_um': 750, 'max_width_um': 250,
                        'min_electrode_width_um': .8, 'min_electrode_gap_um': .8,
                        'max_electrodes': 500},
        'micro_polish': {'enabled': True, 'max_passes': 4,
                         'continuous_steps_fraction_of_bound_span': [.01],
                         'minimum_step_fraction': .0025, 'shrink_factor': .5,
                         'integer_steps': [-1, 1]},
    }

    def fake_evaluate(candidate, *_args, **_kwargs):
        return (dict(record, design=asdict(candidate)), None, None)

    with patch('sawopt.optimization.study.evaluate_design', side_effect=fake_evaluate):
        polished, diagnostic = _mixed_variable_polish(
            record, cfg, 50, 50, 'outer_ports', np.array([1.0]))
    assert polished is record
    np.testing.assert_allclose(diagnostic['step_fraction_history'], [.01, .005, .0025])
    assert not diagnostic['promoted']


def test_common_grid_is_union_of_all_candidate_controls():
    base = np.array([1.0, 3.0])
    out = common_validation_grid(base, [[2.0], [4.0]], tolerance_hz=0)
    np.testing.assert_array_equal(out, np.array([1.0, 2.0, 3.0, 4.0]))


def test_aggregate_rank_rejects_lucky_infeasible_outlier():
    lucky = [_record(.01), _record(.8), _record(.8)]
    stable = [_record(.3), _record(.3), _record(.3)]
    assert aggregate_pair_rank(stable) < aggregate_pair_rank(lucky)


def test_plateau_waits_for_minimum_and_patience():
    stopper = PlateauStopper(min_generations=3, patience_generations=2,
                             improvement_abs=.1, improvement_rel=.1)
    assert stopper.update(1.0) is False
    assert stopper.update(1.0) is False
    assert stopper.update(1.0) is True


def test_common_validation_can_select_an_earlier_round():
    candidates = [
        {'name': 'early'},
        {'name': 'last'},
    ]

    def evaluate(candidate, _grid):
        il = 1.0 if candidate['name'] == 'early' else 2.0
        return _record(0.0, il=il)

    selected, validated, common = validated_candidate_selection(
        candidates, np.array([1e6, 3e6]), [[2e6], [4e6]], evaluate,
        tolerance_hz=0,
    )
    assert selected['metrics']['worst_il_db'] == 1.0
    assert len(validated) == 2
    np.testing.assert_array_equal(common, np.array([1e6, 2e6, 3e6, 4e6]))


def test_legacy_and_hybrid_outer_port_parity():
    root = Path(__file__).parents[3] / 'configs'
    cfg = yaml.safe_load((root / 'base/b28_dms_baseline.yaml').read_text())
    cfg['com'] = yaml.safe_load((root / 'models/com_params_hypothetical.yaml').read_text())
    cfg['layout'] = {'die_um': [900, 700], 'length_margin_um': 60,
                     'width_margin_um': 60, 'max_total_electrodes': 500}
    result = parity_check(cfg, 50)
    assert result['passed']


class Stage3Acceptance(unittest.TestCase):
    def test_vswr_peak(self):
        test_vswr_peak_adds_local_refinement_points()

    def test_incremental_cache(self):
        test_incremental_cache_evaluates_only_new_points()

    def test_incremental_diagnostics(self):
        test_incremental_diagnostics_use_global_extrema_and_or_flags()

    def test_total_budget(self):
        test_adaptive_round_limits_share_one_total_budget()

    def test_two_plateaus(self):
        test_two_consecutive_budget_plateaus_are_required()

    def test_incremental_dense_parity(self):
        test_incremental_dense_matches_full_metrics_rank_and_diagnostics()

    def test_mixed_polish(self):
        test_mixed_polish_honors_integer_step_and_only_promotes_better_rank()

    def test_polish_shrink(self):
        test_mixed_polish_shrinks_continuous_step_after_no_improvement()

    def test_common_grid(self):
        test_common_grid_is_union_of_all_candidate_controls()

    def test_aggregate_rank(self):
        test_aggregate_rank_rejects_lucky_infeasible_outlier()

    def test_plateau(self):
        test_plateau_waits_for_minimum_and_patience()

    def test_earlier_adaptive_round_can_win(self):
        test_common_validation_can_select_an_earlier_round()

    def test_outer_port_parity(self):
        test_legacy_and_hybrid_outer_port_parity()
