import unittest

import numpy as np

from sawopt.optimization.lshade import LShadeBackend
from sawopt.optimization.selection import GeometryFirstComparator


def _record(vector):
    values = np.asarray(vector, dtype=float)
    score = float(np.sum((values - 0.37) ** 2))
    return {
        "evaluation_status": "PHYSICS_EVALUATED",
        "candidate_vector": values.tolist(),
        "feasible": True,
        "max_violation": 0.0,
        "sum_violation": 0.0,
        "violations": {},
        "metrics": {"worst_il_db": score, "ripple_db": score / 2},
    }


class _SequenceRng:
    def __init__(self, *values):
        self._values = [np.asarray(value, dtype=float) for value in values]
        self.calls = 0

    def uniform(self, low, high, size):
        if self.calls >= len(self._values):
            raise AssertionError("update_bounds requested an unexpected extra proposal")
        value = self._values[self.calls]
        self.calls += 1
        if value.shape != (int(size),):
            raise AssertionError("test RNG proposal shape mismatch")
        return value.copy()


class CompactBoundsPolicyTests(unittest.TestCase):
    def test_unretained_historical_collision_is_skipped_during_bounds_injection(self):
        config = {
            "initial_population": 6,
            "min_population": 4,
            "history_size": 4,
            "max_duplicate_retries": 3,
            "total_budget": 24,
            "hard_max_budget": 24,
            "population_schedule_terminal_budget": 24,
            "hard_bounds": [[-1.0, 2.0], [-1.0, 2.0]],
            "compact_history_cache": True,
            "historical_finalist_count": 1,
        }
        calls = []

        def canonicalizer(vector):
            # Keep the test focused on compact-history collision policy rather
            # than float round-trip noise introduced by changing active bounds.
            value = np.round(np.asarray(vector, dtype=float), 12)
            return value, tuple(float(item) for item in value)

        def evaluator(vector):
            calls.append(tuple(np.asarray(vector, dtype=float)))
            return _record(vector)

        backend = LShadeBackend(
            [(0.0, 1.0), (0.0, 1.0)],
            seed=41,
            config=config,
            integer_indices=(),
            canonicalizer=canonicalizer,
            comparator=GeometryFirstComparator(),
        )
        backend.initialize(evaluator)
        backend.advance_to_unique_budget(18)

        active_keys = {member.key for member in backend._population}
        retained_keys = set(backend._cache)
        historical_key = next(
            key for key in backend._cache_frequency_versions
            if key not in active_keys and key not in retained_keys
        )

        new_bounds = np.asarray([[-0.1, 1.1], [-0.1, 1.1]], dtype=float)
        historical_physical = np.asarray(historical_key, dtype=float)
        historical_proposal = (
            (historical_physical - new_bounds[:, 0])
            / (new_bounds[:, 1] - new_bounds[:, 0])
        )
        fresh_proposal = np.zeros(2, dtype=float)
        rng = _SequenceRng(historical_proposal, fresh_proposal)

        before_unique = backend.unique_evaluations
        before_calls = len(calls)
        backend.update_bounds(new_bounds, rng=rng)

        self.assertEqual(rng.calls, 2)
        self.assertEqual(len(calls), before_calls + 1)
        self.assertEqual(backend.unique_evaluations, before_unique + 1)
        self.assertNotIn(historical_key, {member.key for member in backend._population})
        self.assertIn(tuple(new_bounds[:, 0]), {member.key for member in backend._population})


if __name__ == "__main__":
    unittest.main()
