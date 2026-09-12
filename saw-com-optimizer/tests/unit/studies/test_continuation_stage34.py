import unittest
from dataclasses import asdict
from unittest.mock import patch

import numpy as np

import sawopt.studies.continuation as continuation
from sawopt.core.models import FilterDesign
from sawopt.io.config import load_study_config
from sawopt.studies.convergence import normalize_convergence_config


def _cfg():
    return {
        "constraints": {
            "max_length_um": 750, "max_width_um": 250,
            "min_electrode_width_um": .8, "min_electrode_gap_um": .8,
            "max_electrodes": 500,
        },
        "optimizer": {"population": 8, "maxiter": 2, "maxiter_ceiling": 20},
        "optimizer_validation": {
            "boundary_detection": {
                "enabled": True,
                "min_seed_fraction_at_boundary": .8,
                "elite_boundary_fraction": .5,
                "probe_improvement_threshold": .02,
                "integer_boundary_zone_steps": 1,
                "elite_probe_enabled": True,
                "elite_material_advantage_fraction": .05,
                "elite_probe_min_positive_seeds": 2,
                "elite_probe_min_positive_fraction": .5,
                "elite_probe_median_improvement_threshold": .02,
            },
            "bounds": {
                "io_idt_pairs": {
                    "initial": [20, 100], "hard": [8, 120],
                    "expandable": True, "lower_steps": [15, 10, 8],
                },
            },
        },
    }


def _record(seed, io_pairs, violation):
    return {
        "seed": seed,
        "design": asdict(FilterDesign(io_idt_pairs=io_pairs)),
        "feasible": False,
        "max_violation": float(violation),
        "violations": {"x": float(violation)},
        "metrics": {"worst_il_db": 5.0},
    }


class Stage34BoundaryPolicy(unittest.TestCase):
    def test_elite_seed_requests_probe_without_expanding(self):
        cfg = _cfg()
        state = continuation._bound_state(cfg)
        records = [_record(1, 20, .10), _record(2, 35, 1.0)]
        result = continuation.detect_elite_boundary_probe(records, state, cfg)
        self.assertEqual(len(result["probes"]), 1)
        self.assertFalse(result["probes"][0]["expansion_allowed"])
        self.assertEqual(state["io_idt_pairs"]["active"], [20, 100])

    def test_elite_probe_diagnostics_capture_each_seed_and_aggregate(self):
        cfg = _cfg()
        cfg["spec"] = {"passband": [758.0, 803.0], "stopbands": []}
        state = continuation._bound_state(cfg)
        records = [_record(1, 20, 1.0), _record(2, 20, .8)]

        def fake_evaluate(candidate, *_args, **_kwargs):
            return _record(candidate.io_idt_pairs, candidate.io_idt_pairs, .2), None, None

        with patch.object(continuation, "search_grid", return_value=np.array([1.0])), \
                patch.object(continuation, "_valid_geometry", return_value=True), \
                patch.object(continuation, "evaluate_design", side_effect=fake_evaluate):
            probe = continuation.boundary_probe(
                records, cfg, 50.0, "center_outer_same", state,
                {"variable": "io_idt_pairs", "direction": "lower"},
            )

        self.assertEqual(probe["evaluations"], 2)
        self.assertEqual(probe["positive_count"], 2)
        self.assertEqual(probe["positive_fraction"], 1.0)
        self.assertGreater(probe["median_improvement"], .02)
        self.assertEqual(
            set(probe["tested"][0]),
            {"seed", "design", "before_primary", "after_primary", "improvement",
             "before_rank", "after_rank", "rank", "before_validated_rank",
             "after_validated_rank", "search_rank"},
        )

    def test_elite_consensus_requires_count_fraction_and_median(self):
        cfg = _cfg()
        self.assertTrue(continuation.elite_probe_consensus(
            {"positive_count": 2, "positive_fraction": .5, "median_improvement": .021}, cfg
        ))
        self.assertFalse(continuation.elite_probe_consensus(
            {"positive_count": 1, "positive_fraction": .5, "median_improvement": .10}, cfg
        ))
        self.assertFalse(continuation.elite_probe_consensus(
            {"positive_count": 2, "positive_fraction": .49, "median_improvement": .10}, cfg
        ))
        self.assertFalse(continuation.elite_probe_consensus(
            {"positive_count": 2, "positive_fraction": .5, "median_improvement": .02}, cfg
        ))

    def test_one_positive_seed_cannot_expand(self):
        cfg = _cfg()
        state = continuation._bound_state(cfg)
        probe = {"positive_count": 1, "positive_fraction": 1 / 5, "median_improvement": .2}
        self.assertFalse(continuation.elite_probe_consensus(probe, cfg))
        self.assertEqual(
            continuation._next_expansion(state, {"variable": "io_idt_pairs", "direction": "lower"}),
            15,
        )

    def test_integer_boundary_zone_includes_lower_plus_one(self):
        cfg = _cfg()
        state = continuation._bound_state(cfg)
        values = state["io_idt_pairs"]
        self.assertEqual(continuation._boundary_hit({"io_idt_pairs": 21}, "io_idt_pairs", values), "lower")
        self.assertEqual(continuation._boundary_hit({"io_idt_pairs": 22}, "io_idt_pairs", values), None)

    def test_normal_multi_seed_pressure_and_hard_bound(self):
        cfg = _cfg()
        state = continuation._bound_state(cfg)
        records = [_record(seed, 20, 1.0 + seed / 1000) for seed in range(1, 6)]
        pressure = continuation.detect_boundary_pressure(records, state, cfg)
        self.assertEqual(pressure["pressures"][0]["seed_count"], 5)
        self.assertEqual(continuation._next_expansion(
            state, {"variable": "io_idt_pairs", "direction": "lower"}), 15)
        state["io_idt_pairs"]["active"][0] = 8
        self.assertIsNone(continuation._next_expansion(
            state, {"variable": "io_idt_pairs", "direction": "lower"}))

    def test_bound_expansion_injects_new_region(self):
        cfg = _cfg()
        old = continuation._bound_state(cfg)
        new = continuation._bound_state(cfg)
        new["io_idt_pairs"]["active"][0] = 15
        old_vectors = np.tile(np.asarray([5, 20, 16, 40, .5, .5, 80.]), (10, 1))
        injected = continuation._inject_new_region(
            old_vectors,
            continuation.active_bounds(old), continuation.active_bounds(new),
            np.random.default_rng(7), cfg, fraction=.2,
        )
        self.assertTrue(np.any(injected[:, 1] < 20))
        self.assertEqual(len(injected), len(old_vectors))


class Stage34StagnationAndConvergence(unittest.TestCase):
    def _trajectory(self):
        cfg = _cfg()
        cfg["optimizer_validation"]["stagnation_recovery"] = {
            "enabled": True, "duplicate_fraction_threshold": .8,
            "minimum_interval_objective_calls": 500,
            "unique_evaluations_since_improvement": 2000,
            "max_recoveries_per_design_space_version": 1,
        }
        trajectory = object.__new__(continuation.ContinuationTrajectory)
        trajectory.cfg = cfg
        trajectory.design_space_version = 1
        trajectory.objective_calls = 1000
        trajectory.cache_hits = 900
        trajectory.seen = {tuple([float(i)]) for i in range(2500)}
        trajectory.last_significant = 0
        trajectory.seed = 7
        trajectory._diagnostic_objective_calls = 0
        trajectory._diagnostic_cache_hits = 0
        trajectory._stagnation_recoveries_by_version = {}
        trajectory.stagnation_events = []
        trajectory.grid_extension_events = []
        trajectory._diversify_after_stagnation = lambda: None
        return trajectory

    def test_duplicate_recovery_uses_interval_counters_and_is_capped(self):
        trajectory = self._trajectory()
        first = trajectory.maybe_diversify_for_duplicate_stagnation()
        self.assertIsNotNone(first)
        self.assertAlmostEqual(first["interval_duplicate_fraction"], .9)
        trajectory.objective_calls += 1000
        trajectory.cache_hits += 900
        self.assertIsNone(trajectory.maybe_diversify_for_duplicate_stagnation())
        self.assertEqual(len(trajectory.stagnation_events), 1)

    def test_bound_expansion_resets_interval_diagnostics(self):
        trajectory = self._trajectory()
        trajectory.state = continuation._bound_state(trajectory.cfg)
        trajectory.rng = np.random.default_rng(7)
        trajectory.population = None
        trajectory.cache = {"old": 1}
        old_state = continuation._bound_state(trajectory.cfg)
        new_state = continuation._bound_state(trajectory.cfg)
        new_state["io_idt_pairs"]["active"][0] = 15
        trajectory.expand(old_state, new_state, 2, .2)
        self.assertEqual(trajectory._diagnostic_objective_calls, trajectory.objective_calls)
        self.assertEqual(trajectory._diagnostic_cache_hits, trajectory.cache_hits)
        self.assertEqual(trajectory.cache, {})

    def test_minimum_convergence_budget_blocks_early_stop(self):
        self.assertFalse(continuation._convergence_stop_allowed("converged", 8000, 16000))
        self.assertTrue(continuation._convergence_stop_allowed("converged", 16000, 16000))
        self.assertFalse(continuation._convergence_stop_allowed("likely_underoptimized", 16000, 16000))

    def test_stage34_config_resolves_production_settings(self):
        root = __import__("pathlib").Path(__file__).resolve().parents[3]
        cfg = normalize_convergence_config(load_study_config(
            root / "configs" / "studies" / "next_50ohm_center_outer_same_stage34.yaml"
        ))
        self.assertEqual(cfg["optimizer_validation"]["budgets"],
                         [500, 1000, 2000, 3000, 4000, 6000, 8000, 10000, 12000, 14000, 16000])
        self.assertEqual(cfg["optimizer_validation"]["optional_max_budget"], 32000)
        self.assertEqual(cfg["optimizer_validation"]["parallel"]["production_workers"], 5)
        self.assertEqual(cfg["optimizer_validation"]["minimum_convergence_budget"], 16000)


if __name__ == "__main__":
    unittest.main()
