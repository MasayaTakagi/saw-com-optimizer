import json
import unittest

import numpy as np

from sawopt.optimizers.lshade import LShadeBackend
from sawopt.optimizers.selection import FeasibilityFirstComparator


def _sphere(vector):
    value = float(np.sum((np.asarray(vector) - .35) ** 2))
    return {
        "feasible": True,
        "max_violation": 0.0,
        "violations": {},
        "metrics": {"worst_il_db": value, "ripple_db": value},
    }


class LShadeSearch(unittest.TestCase):
    def test_comparator_is_feasibility_first_and_penalty_invariant(self):
        comparator = FeasibilityFirstComparator()
        feasible = {
            "feasible": True, "max_violation": 0.0, "violations": {},
            "metrics": {"worst_il_db": 50.0},
        }
        infeasible = {
            "feasible": False, "max_violation": .01, "violations": {"il": .01},
            "metrics": {"worst_il_db": .1},
        }
        self.assertTrue(comparator.better(feasible, infeasible))
        lower_max = {
            "feasible": False, "max_violation": .1, "violations": {"a": .1},
            "metrics": {"worst_il_db": 1.0},
        }
        lower_sum = {
            "feasible": False, "max_violation": .1, "violations": {"a": .1, "b": .01},
            "metrics": {"worst_il_db": .1},
        }
        self.assertTrue(comparator.better(lower_max, lower_sum))

    def test_checkpoint_resume_matches_uninterrupted_search(self):
        config = {
            "initial_population": 8, "min_population": 4, "history_size": 4,
            "pbest_max_fraction": .3, "max_duplicate_retries": 3, "total_budget": 80,
        }
        full = LShadeBackend([(0, 1)] * 3, seed=17, config=config, integer_indices=())
        full.initialize(_sphere)
        full.advance_to_unique_budget(80)

        split = LShadeBackend([(0, 1)] * 3, seed=17, config=config, integer_indices=())
        split.initialize(_sphere)
        split.advance_to_unique_budget(40)
        state = json.loads(json.dumps(split.state_dict(), allow_nan=False))
        resumed = LShadeBackend([(0, 1)] * 3, seed=17, config=config, integer_indices=())
        resumed.load_state_dict(state)
        resumed.set_evaluator(_sphere)
        resumed.advance_to_unique_budget(80)
        np.testing.assert_array_equal(full.population(), resumed.population())
        self.assertEqual(full.incumbent(), resumed.incumbent())

    def test_canonical_duplicates_do_not_exceed_unique_budget(self):
        def canonicalizer(vector):
            value = np.rint(vector)
            return value, tuple(value.tolist())

        config = {
            "initial_population": 4, "min_population": 4,
            "total_budget": 12, "max_duplicate_retries": 2,
        }
        backend = LShadeBackend(
            [(0, 2)] * 2, seed=3, config=config, integer_indices=(0, 1),
            canonicalizer=canonicalizer,
        )
        backend.initialize(lambda x: {
            "feasible": True, "max_violation": 0.0, "violations": {},
            "metrics": {"worst_il_db": float(np.sum(x))},
        })
        initial = backend.unique_evaluations
        backend.advance_to_unique_budget(initial + 4)
        self.assertGreaterEqual(backend.duplicate_count, 0)
        self.assertLessEqual(backend.unique_evaluations, initial + 4)


if __name__ == "__main__":
    unittest.main()
