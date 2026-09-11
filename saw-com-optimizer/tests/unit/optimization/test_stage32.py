import unittest
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import sawopt.studies.continuation as stage32
from sawopt.core.models import FilterDesign
from sawopt.studies.continuation import (
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


class Stage32StagnationRecovery(unittest.TestCase):
    @staticmethod
    def _trajectory(*, best=None, seed=41):
        trajectory = object.__new__(stage32.ContinuationTrajectory)
        trajectory.cfg = {"optimizer": {"maxiter": 2, "maxiter_ceiling": 20, "population": 8}}
        trajectory.state = {
            name: {"active": list(bounds)}
            for name, bounds in zip(stage32.NAMES, stage32.BOUNDS)
        }
        trajectory.seed = seed
        trajectory.rng = np.random.default_rng(seed)
        trajectory.population = np.arange(8 * len(stage32.NAMES), dtype=float).reshape(8, -1)
        trajectory.seen = set()
        trajectory.best = best
        trajectory.segment_index = 0
        trajectory.stop_reason = "previous_reason"
        return trajectory

    def test_four_attempt_stagnation_contract_and_population_retention(self):
        best = {"design": asdict(FilterDesign(io_idt_pairs=33, center_idt_pairs=17))}
        trajectory = self._trajectory(best=best)
        original_population = trajectory.population.copy()
        de_calls = []
        build_calls = []

        def fake_de(_objective, bounds, *, init, seed, **kwargs):
            de_calls.append({
                "bounds": bounds,
                "init": np.asarray(init, dtype=float).copy(),
                "seed": seed,
                "kwargs": kwargs,
            })
            return SimpleNamespace(population=np.asarray(init, dtype=float).copy())

        def fake_build(cfg, rng, center, bounds, *, population=None):
            build_calls.append({
                "cfg": cfg,
                "rng": rng,
                "center": np.asarray(center, dtype=float).copy(),
                "bounds": bounds,
                "population": population,
            })
            return np.full((population, len(stage32.NAMES)), 100.0 + len(build_calls))

        with patch.object(stage32, "differential_evolution", side_effect=fake_de), \
                patch.object(stage32, "_build_population", side_effect=fake_build):
            self.assertFalse(trajectory._run_de(target=1))

        self.assertEqual([call["seed"] for call in de_calls], [41, 42, 43, 44])
        self.assertEqual(trajectory.segment_index, 4)
        self.assertEqual(len(build_calls), 3)
        self.assertEqual(trajectory.stop_reason, "no_new_unique_designs")
        self.assertEqual(build_calls[0]["rng"], trajectory.rng)
        self.assertEqual(build_calls[0]["bounds"], stage32.active_bounds(trajectory.state))
        np.testing.assert_allclose(
            build_calls[0]["center"],
            [best["design"][name] for name in stage32.NAMES],
        )
        self.assertEqual([call["population"] for call in build_calls], [8, 8, 8])
        for call in de_calls[1:]:
            np.testing.assert_array_equal(call["init"][:2], original_population[:2])

    def test_progress_on_retry_clears_stop_reason_and_uses_default_center(self):
        trajectory = self._trajectory(best=None, seed=99)
        de_calls = []
        build_calls = []

        def fake_de(_objective, bounds, *, init, seed, **kwargs):
            de_calls.append({"bounds": bounds, "init": np.asarray(init, dtype=float).copy(), "seed": seed})
            if len(de_calls) == 2:
                trajectory.seen.add(("new", 2))
            return SimpleNamespace(population=np.asarray(init, dtype=float).copy())

        def fake_build(cfg, rng, center, bounds, *, population=None):
            build_calls.append({
                "rng": rng,
                "center": np.asarray(center, dtype=float).copy(),
                "bounds": bounds,
                "population": population,
            })
            return np.full((population, len(stage32.NAMES)), 200.0)

        with patch.object(stage32, "differential_evolution", side_effect=fake_de), \
                patch.object(stage32, "_build_population", side_effect=fake_build):
            self.assertTrue(trajectory._run_de(target=1))

        self.assertEqual([call["seed"] for call in de_calls], [99, 100])
        self.assertEqual(trajectory.segment_index, 2)
        self.assertEqual(len(build_calls), 1)
        self.assertIsNone(trajectory.stop_reason)
        default = FilterDesign()
        np.testing.assert_allclose(
            build_calls[0]["center"],
            [getattr(default, name) for name in stage32.NAMES],
        )
        np.testing.assert_array_equal(de_calls[1]["init"][:2], trajectory.population[:2])


if __name__ == "__main__":
    unittest.main()
