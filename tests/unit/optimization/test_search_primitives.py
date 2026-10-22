import unittest

import numpy as np

from sawopt.core.metrics import feasibility_objective
from sawopt.physics.com import CalibratedProvider
from sawopt.optimization.adaptive_frequency import adaptive_exchange
from sawopt.optimization.population import scaled_population
from sawopt.studies.hybrid import _canonical_candidate


class SearchPrimitives(unittest.TestCase):
    def test_max_violation_dominates_sum_of_squares(self):
        metrics = {"worst_il_db": 5.0}
        score_a, _ = feasibility_objective(metrics, {"a": 0.50, "b": 0.0, "c": 0.0})
        score_b, _ = feasibility_objective(metrics, {"a": 0.40, "b": 0.40, "c": 0.40})
        self.assertLess(score_b, score_a)

    def test_search_surrogate_preserves_max_violation_order(self):
        metrics = {"worst_il_db": 5.0}
        lower, _ = feasibility_objective(metrics, {"a": 0.4000, "b": 0.10, "c": 0.10})
        higher, _ = feasibility_objective(metrics, {"a": 0.4001, "b": 0.0, "c": 0.0})
        self.assertLess(lower, higher)

    def test_feasible_always_beats_infeasible(self):
        feasible, _ = feasibility_objective({"worst_il_db": 100.0}, {"a": 0.0})
        infeasible, _ = feasibility_objective({"worst_il_db": 0.0}, {"a": 1e-6})
        self.assertLess(feasible, infeasible)

    def test_population_scales_with_dimension(self):
        self.assertEqual([scaled_population(56, n) for n in (7, 10, 13)], [56, 80, 104])

    def test_calibrated_provider_does_not_invent_data(self):
        metadata = {key: "documented" for key in CalibratedProvider.REQUIRED_METADATA}
        provider = CalibratedProvider(metadata)
        with self.assertRaises(NotImplementedError):
            provider.parameters("idt", object(), np.array([1.0]))

    def test_hybrid_integer_cache_identity_is_canonical(self):
        first = np.array([5, 24.1, 16.1, 40.1, .5, .5, 80, 5.1, 15.1, 60])
        second = np.array([5, 24.4, 16.4, 40.4, .5, .5, 80, 5.1, 15.4, 60])
        self.assertEqual(_canonical_candidate(first)[3], _canonical_candidate(second)[3])

    def test_adaptive_exchange_adds_a_narrow_feature(self):
        initial = np.array([758, 780, 803], float) * 1e6
        dense = np.array([758, 780, 790, 790.125, 790.25, 803], float) * 1e6
        seen = []

        def optimize(frequencies):
            seen.append(frequencies.copy())
            return {"grid": frequencies.copy()}

        def evaluate(_candidate):
            return dense, {
                "il": np.array([1, 1, 1, 8, 1, 1], float),
                "vswr": np.ones((len(dense), 2)),
            }

        _candidate, final, _rounds = adaptive_exchange(
            initial, optimize, evaluate,
            {"passband": [758, 803], "stopbands": []}, rounds=2,
            tolerance_hz=1000, slope_threshold_db=.5,
        )
        self.assertIn(790.125e6, final)
        self.assertGreaterEqual(len(seen), 2)

    def test_adaptive_exchange_stops_when_response_is_already_represented(self):
        initial = np.array([758, 780, 803], float) * 1e6

        def evaluate(_candidate):
            return initial, {"il": np.array([1., 2., 1.]), "vswr": np.ones((3, 2))}

        _candidate, final, rounds = adaptive_exchange(
            initial, lambda frequencies: frequencies, evaluate,
            {"passband": [758, 803], "stopbands": []}, rounds=2,
            slope_threshold_db=10,
        )
        np.testing.assert_array_equal(final, initial)
        self.assertEqual(rounds, 0)
