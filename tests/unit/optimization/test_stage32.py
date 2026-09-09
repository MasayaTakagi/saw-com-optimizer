import unittest
from dataclasses import asdict

import numpy as np

from sawopt.core.models import FilterDesign
from sawopt.optimization.stage32_study import (
    _bound_state,
    _inject_new_region,
    _next_expansion,
    detect_boundary_pressure,
)


def _cfg():
    return {
        "constraints": {
            "max_length_um": 750, "max_width_um": 250,
            "min_electrode_width_um": .8, "min_electrode_gap_um": .8,
            "max_electrodes": 500,
        },
        "optimizer_validation": {
            "boundary_detection": {
                "enabled": True,
                "min_seed_fraction_at_boundary": .8,
                "elite_boundary_fraction": .5,
            },
            "bounds": {
                "io_idt_pairs": {
                    "initial": [20, 100], "hard": [8, 120],
                    "expandable": True, "lower_steps": [15, 10, 8],
                },
            },
        }
    }


def _record(seed, io_pairs):
    return {
        "seed": seed,
        "design": asdict(FilterDesign(io_idt_pairs=io_pairs)),
        "feasible": False,
        "max_violation": 1.0 + seed / 1000,
        "violations": {"x": 1.0 + seed / 1000},
        "metrics": {"worst_il_db": 5.0},
    }


class Stage32Bounds(unittest.TestCase):
    def test_single_seed_does_not_trigger_boundary_pressure(self):
        state = _bound_state(_cfg())
        pressure = detect_boundary_pressure([_record(1, 20)], state, _cfg())
        self.assertEqual(pressure["pressures"], [])

    def test_persistent_candidate_pressure_is_detected_for_multiple_seeds(self):
        state = _bound_state(_cfg())
        records = [_record(seed, 20) for seed in range(1, 6)]
        pressure = detect_boundary_pressure(records, state, _cfg())
        self.assertEqual(len(pressure["pressures"]), 1)
        self.assertEqual(pressure["pressures"][0]["direction"], "lower")
        self.assertEqual(pressure["pressures"][0]["seed_count"], 5)

    def test_hard_bound_is_never_crossed_by_next_expansion(self):
        state = _bound_state(_cfg())
        pressure = {"variable": "io_idt_pairs", "direction": "lower"}
        self.assertEqual(_next_expansion(state, pressure), 15)
        state["io_idt_pairs"]["active"][0] = 8
        self.assertIsNone(_next_expansion(state, pressure))

    def test_expansion_injection_enters_new_region_without_shrink(self):
        cfg = _cfg()
        old = _bound_state(cfg)
        new = _bound_state(cfg)
        new["io_idt_pairs"]["active"][0] = 15
        old_vectors = np.tile(np.asarray([5, 20, 16, 40, .5, .5, 80.]), (10, 1))
        injected = _inject_new_region(
            old_vectors, [(4.6, 5.4), (20, 100), (10, 80), (40, 160), (0, 3), (0, 3), (30, 150)],
            [(4.6, 5.4), (15, 100), (10, 80), (40, 160), (0, 3), (0, 3), (30, 150)],
            np.random.default_rng(7), cfg, fraction=.2)
        self.assertTrue(np.any(injected[:, 1] < 20))
        self.assertEqual(len(injected), len(old_vectors))
        self.assertEqual(old["io_idt_pairs"]["active"], [20, 100])


if __name__ == "__main__":
    unittest.main()
