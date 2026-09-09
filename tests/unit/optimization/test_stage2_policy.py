import unittest
import numpy as np

from sawopt.core.metrics import feasibility_objective
from sawopt.core.models import CalibratedProvider
from sawopt.optimization.optimizer_utils import scaled_population, adaptive_exchange
from sawopt.optimization.hybrid_study import _canonical_candidate


class Stage2Policy(unittest.TestCase):
    def test_max_violation_dominates_sum_of_squares(self):
        metrics = {'worst_il_db': 5.0}
        a = {'a': 0.50, 'b': 0.0, 'c': 0.0}
        b = {'a': 0.40, 'b': 0.40, 'c': 0.40}
        score_a, _ = feasibility_objective(metrics, a)
        score_b, _ = feasibility_objective(metrics, b)
        self.assertLess(score_b, score_a)

    def test_search_surrogate_does_not_reverse_intended_lexicographic_order(self):
        metrics = {'worst_il_db': 5.0}
        lower_max = {'a': 0.4000, 'b': 0.10, 'c': 0.10}
        higher_max = {'a': 0.4001, 'b': 0.0, 'c': 0.0}
        lower_score, _ = feasibility_objective(metrics, lower_max)
        higher_score, _ = feasibility_objective(metrics, higher_max)
        self.assertLess(lower_score, higher_score)

    def test_feasible_always_beats_infeasible(self):
        feasible, _ = feasibility_objective({'worst_il_db': 100.0}, {'a': 0.0})
        infeasible, _ = feasibility_objective({'worst_il_db': 0.0}, {'a': 1e-6})
        self.assertLess(feasible, infeasible)

    def test_population_examples(self):
        self.assertEqual([scaled_population(56, n) for n in (7, 10, 13)], [56, 80, 104])

    def test_calibrated_provider_never_invents_data(self):
        metadata = {key: 'documented' for key in CalibratedProvider.REQUIRED_METADATA}
        provider = CalibratedProvider(metadata)
        with self.assertRaises(NotImplementedError):
            provider.parameters('idt', object(), np.array([1.0]))

    def test_hybrid_integer_cache_identity_is_canonical(self):
        a = np.array([5, 24.1, 16.1, 40.1, .5, .5, 80, 5.1, 15.1, 60])
        b = np.array([5, 24.4, 16.4, 40.4, .5, .5, 80, 5.1, 15.4, 60])
        self.assertEqual(_canonical_candidate(a)[3], _canonical_candidate(b)[3])

    def test_adaptive_exchange_closes_synthetic_narrow_feature(self):
        initial = np.array([758, 780, 803], float) * 1e6
        dense = np.array([758, 780, 790, 790.125, 790.25, 803], float) * 1e6
        seen = []
        def optimize(f):
            seen.append(f.copy())
            return {'grid': f.copy()}
        def evaluate(_candidate):
            il = np.array([1, 1, 1, 8, 1, 1], float)
            return dense, {'il': il, 'vswr': np.ones((len(dense), 2))}
        _candidate, final, rounds = adaptive_exchange(
            initial, optimize, evaluate,
            {'passband': [758, 803], 'stopbands': []}, rounds=2,
            tolerance_hz=1000, slope_threshold_db=.5,
        )
        self.assertIn(790.125e6, final)
        self.assertGreaterEqual(len(seen), 2)

    def test_adaptive_exchange_stops_on_represented_smooth_response(self):
        initial = np.array([758, 780, 803], float) * 1e6
        def optimize(f): return f
        def evaluate(_):
            return initial, {'il': np.array([1., 2., 1.]), 'vswr': np.ones((3, 2))}
        _, final, rounds = adaptive_exchange(
            initial, optimize, evaluate,
            {'passband': [758, 803], 'stopbands': []}, rounds=2,
            slope_threshold_db=10,
        )
        np.testing.assert_array_equal(final, initial)
        self.assertEqual(rounds, 0)
