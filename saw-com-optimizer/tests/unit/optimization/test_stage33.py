import json
import unittest

import numpy as np

from sawopt.optimization.lshade import LShadeBackend
from sawopt.optimization.selection import FeasibilityFirstComparator
from sawopt.optimization.stage32_study import _bound_state, detect_elite_boundary_probe


def sphere(x):
    value = float(np.sum((np.asarray(x) - .35) ** 2))
    return {
        "feasible": True, "max_violation": 0.0, "violations": {},
        "metrics": {"worst_il_db": value, "ripple_db": value},
    }


class Stage33Acceptance(unittest.TestCase):
    def test_comparator_is_penalty_invariant_and_feasibility_first(self):
        comparator = FeasibilityFirstComparator()
        feasible = {"feasible": True, "max_violation": 0.0, "violations": {},
                    "metrics": {"worst_il_db": 50.0}}
        infeasible = {"feasible": False, "max_violation": .01, "violations": {"il": .01},
                      "metrics": {"worst_il_db": .1}}
        self.assertTrue(comparator.better(feasible, infeasible))
        lower_max = {"feasible": False, "max_violation": .1, "violations": {"a": .1},
                     "metrics": {"worst_il_db": 1.0}}
        lower_sum = {"feasible": False, "max_violation": .1, "violations": {"a": .1, "b": .01},
                     "metrics": {"worst_il_db": .1}}
        self.assertTrue(comparator.better(lower_max, lower_sum))

    def test_checkpoint_resume_matches_uninterrupted_run(self):
        config = {"initial_population": 8, "min_population": 4, "history_size": 4,
                  "pbest_max_fraction": .3, "max_duplicate_retries": 3, "total_budget": 80}
        full = LShadeBackend([(0, 1)] * 3, seed=17, config=config, integer_indices=())
        full.initialize(sphere)
        full.advance_to_unique_budget(80)

        split = LShadeBackend([(0, 1)] * 3, seed=17, config=config, integer_indices=())
        split.initialize(sphere)
        split.advance_to_unique_budget(40)
        state = json.loads(json.dumps(split.state_dict(), allow_nan=False))
        resumed = LShadeBackend([(0, 1)] * 3, seed=17, config=config, integer_indices=())
        resumed.load_state_dict(state)
        resumed.set_evaluator(sphere)
        resumed.advance_to_unique_budget(80)
        np.testing.assert_array_equal(full.population(), resumed.population())
        self.assertEqual(full.incumbent(), resumed.incumbent())

    def test_canonical_duplicate_is_not_charged_twice(self):
        def canonicalizer(vector):
            value = np.rint(vector)
            return value, tuple(value.tolist())

        config = {"initial_population": 4, "min_population": 4, "total_budget": 12,
                  "max_duplicate_retries": 2}
        backend = LShadeBackend([(0, 2)] * 2, seed=3, config=config,
                                integer_indices=(0, 1), canonicalizer=canonicalizer)
        backend.initialize(lambda x: {"feasible": True, "max_violation": 0.0,
                                      "violations": {}, "metrics": {"worst_il_db": float(np.sum(x))}})
        initial = backend.unique_evaluations
        backend.advance_to_unique_budget(initial + 4)
        self.assertGreaterEqual(backend.duplicate_count, 0)
        self.assertLessEqual(backend.unique_evaluations, initial + 4)

    def test_elite_boundary_requests_probe_without_direct_expansion(self):
        cfg = {"stage3_3": {"bounds": {
            "integer_boundary_zone_steps": 1,
            "elite_probe_enabled": True,
            "elite_material_advantage_fraction": .05,
        }}}
        state = _bound_state(cfg)
        state["io_idt_pairs"]["expandable"] = True
        state["io_idt_pairs"]["active"] = [20, 40]
        state["io_idt_pairs"]["hard"] = [10, 50]
        records = [
            {"seed": 1, "design": {"io_idt_pairs": 20}, "feasible": False,
             "max_violation": .1, "violations": {"x": .1}, "metrics": {"worst_il_db": 1}},
            {"seed": 2, "design": {"io_idt_pairs": 35}, "feasible": False,
             "max_violation": 1.0, "violations": {"x": 1.0}, "metrics": {"worst_il_db": 1}},
        ]
        result = detect_elite_boundary_probe(records, state, cfg)
        self.assertEqual(len(result["probes"]), 1)
        self.assertFalse(result["probes"][0]["expansion_allowed"])


if __name__ == "__main__":
    unittest.main()
