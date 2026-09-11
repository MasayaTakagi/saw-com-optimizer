import json
import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from sawopt.optimization.lshade import LShadeBackend, parent_midpoint_repair, shade_success_memory
from sawopt.optimization.selection import DEFAULT_COMPARATOR, time_to_target
from sawopt.optimization.stage331_preprod import (
    SOURCE_HASH_CHECKPOINT_NAMES,
    evaluate_source_hash_gate,
    run_optimizer_invariants,
)
from sawopt.optimization.stage33_study import (
    _attach_time_to_target,
    _evaluate_promotion_gate,
    validate_ab_candidates,
)
from sawopt.optimization import study as study_module
from sawopt.studies import preproduction


def _objective(x):
    value = float(np.sum((np.asarray(x) - 0.3) ** 2))
    return {
        "feasible": True, "max_violation": 0.0, "sum_violation": 0.0,
        "violations": {}, "metrics": {"worst_il_db": value, "ripple_db": value},
    }


def _fixed_population():
    return np.asarray([
        [0.05, 0.15, 0.25], [0.15, 0.25, 0.35],
        [0.25, 0.35, 0.45], [0.35, 0.45, 0.55],
        [0.45, 0.55, 0.65], [0.55, 0.65, 0.75],
        [0.65, 0.75, 0.85], [0.75, 0.85, 0.95],
    ])


class Stage331Acceptance(unittest.TestCase):
    def test_full_regression_gate_uses_pytest_and_propagates_nonzero(self):
        with TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            out = Path(temp) / "run"
            repo.mkdir()
            completed = SimpleNamespace(returncode=1, stdout="pytest failure", stderr="")
            with mock.patch.object(preproduction.subprocess, "run", return_value=completed) as run:
                summary = preproduction.run_full_test_suite(repo, out)
            command = run.call_args.args[0]
            self.assertEqual(command[:3], [sys.executable, "-m", "pytest"])
            self.assertEqual(command[3:], ["-q"])
            self.assertFalse(summary["passed"])
            self.assertEqual(summary["exit_code"], 1)

    @unittest.skipUnless(importlib.util.find_spec("pytest"), "pytest is not installed")
    def test_pytest_only_failure_blocks_full_regression_gate(self):
        with TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            out = Path(temp) / "run"
            repo.mkdir()
            (repo / "test_pytest_only_failure.py").write_text(
                "def test_failure():\n    assert False\n", encoding="utf-8"
            )
            summary = preproduction.run_full_test_suite(repo, out)
            self.assertFalse(summary["passed"])
            self.assertNotEqual(summary["exit_code"], 0)

    def test_required_synthetic_invariants(self):
        result = run_optimizer_invariants()
        self.assertTrue(result["passed"], result["failed"])

    def test_terminal_horizon_is_not_observation_budget(self):
        backend = LShadeBackend(
            [(0, 1)] * 3, seed=12,
            config={"initial_population": 8, "min_population": 4,
                    "total_budget": 1000, "hard_max_budget": 4000,
                    "population_schedule_terminal_budget": 4000},
            integer_indices=(),
        )
        backend.initialize(_objective)
        backend.advance_to_unique_budget(1000)
        self.assertGreater(backend.population_size_for_budget(1000), 4)
        self.assertEqual(backend.population_schedule_terminal_budget, 4000)

    def test_state_contains_resume_contract(self):
        backend = LShadeBackend(
            [(0, 1)] * 3, seed=13,
            config={"initial_population": 8, "min_population": 4,
                    "total_budget": 50, "hard_max_budget": 100,
                    "population_schedule_terminal_budget": 100},
            integer_indices=(),
        )
        backend.initialize(_objective)
        backend.advance_to_unique_budget(20)
        state = backend.state_dict()
        for key in ("rng_state", "archive", "m_f", "m_cr", "history_index",
                    "requested_unique_budget", "actual_unique_budget",
                    "proposals_total", "population_schedule_terminal_budget",
                    "hard_max_budget", "best_so_far_trace", "population_trace",
                    "boundary_repair_counts"):
            self.assertIn(key, state)
        json.dumps(state, allow_nan=False)

    def test_memory_and_boundary_fixtures(self):
        new_f, new_cr = shade_success_memory([0.2, 0.8], [0.1, 0.8], [1, 2])
        self.assertAlmostEqual(new_f, 0.7333333333333333)
        self.assertAlmostEqual(new_cr, 0.5666666666666667)
        repaired, events = parent_midpoint_repair([-0.4, 1.4], [0.2, 0.6])
        np.testing.assert_allclose(repaired, [0.1, 0.8])
        self.assertEqual(events, {"lower": [0], "upper": [1]})

    def test_time_to_target_trace_metric(self):
        target = {"feasible": True, "max_violation": 0.0,
                  "violations": {}, "metrics": {"worst_il_db": 1.0}}
        key = list(DEFAULT_COMPARATOR.rank_key(target))
        reached = time_to_target([{"unique_evaluation": 3, "rank_key": [0, 2, 0, 0, 0]},
                                  {"unique_evaluation": 8, "rank_key": key}], target,
                                 requested_unique_budget=20)
        self.assertEqual(reached["status"], "reached")
        self.assertEqual(reached["evals_to_target"], 8)
        not_reached = time_to_target([{"unique_evaluation": 20, "rank_key": [0, 2, 0, 0, 0]}],
                                     target, requested_unique_budget=20)
        self.assertEqual(not_reached["status"], "not_reached")

    def test_legacy_budget_is_consumed_when_frequency_grid_stops_growing(self):
        """A fixed validation grid must not terminate the design search."""
        cfg = {
            "spec": {
                "passband": [758, 803], "il": 3.0, "ripple": 2.0,
                "vswr": 2.5, "stopbands": [[10, 700, 20]],
            },
            "constraints": {"max_length_um": 750, "max_width_um": 250},
            "center": "grounded", "com": {}, "seeds": [3],
            "optimizer": {
                "maxiter": 2, "population": 5,
                "max_unique_decoded_evaluations": 12,
            },
            "max_unique_decoded_evaluations": 12,
            "adaptive_frequency_rounds": 2,
            "budget_allocation": {"adaptive_round_fractions": [0.5, 0.25, 0.25]},
            "micro_polish": {"enabled": False},
        }

        def fake_record(design):
            value = float(sum(design.__dict__.values()))
            return {
                "feasible": True, "max_violation": 0.0,
                "sum_violation": 0.0, "violations": {},
                "metrics": {"worst_il_db": value, "ripple_db": value},
                "objective": value,
            }

        def fake_dense(design, cfg, rs, rl, *, wiring, counters,
                       base_grid=None, passes=0, validation=False):
            del cfg, rs, rl, wiring, counters, passes, validation
            frequencies = np.asarray(base_grid if base_grid is not None else [1.0])
            return frequencies, (fake_record(design), {}, SimpleNamespace(y_parameters=np.zeros((1, 2, 2))))

        def fake_evaluate(design, cfg, frequencies, rs, rl, *, wiring):
            del cfg, frequencies, rs, rl, wiring
            return fake_record(design), {}, SimpleNamespace(y_parameters=np.zeros((1, 2, 2)))

        with TemporaryDirectory() as temp, mock.patch.object(
            study_module, "geometry", return_value=(None, [0.0])
        ), mock.patch.object(study_module, "evaluate_design", side_effect=fake_evaluate), \
                mock.patch.object(study_module, "dense", side_effect=fake_dense), \
                mock.patch.object(study_module, "critical_frequencies", return_value=np.asarray([])), \
                mock.patch.object(study_module, "new_frequency_points", return_value=np.asarray([])), \
                mock.patch.object(study_module, "_mixed_variable_polish", return_value=(
                    fake_record(study_module.FilterDesign()), {"enabled": False, "promoted": False}
                )):
            result = study_module.optimize_one(
                Path(temp), cfg, 50.0, 50.0, 3,
                wiring="center_outer_same", mode="benchmark", warm_resume=False,
            )
        self.assertEqual(result["actual_unique_design_evaluations"], 12)
        self.assertEqual(result["stop_reason"], "requested_budget_reached")
        self.assertTrue(result["budget_completion_passed"])

    def test_ab_gate_rejects_budget_shortfall(self):
        def row(passed):
            return {
                "seed_count": 2, "best_primary": 1.0,
                "median_primary": 1.0, "seed_iqr": 0.0,
                "basin_hit_rates": {"1.8": 2},
                "target_reached_seed_count": 2,
                "median_evals_to_target": 10.0,
                "median_eval_fraction_to_target": .2,
                "budget_completion_passed": passed,
                "minimum_budget_completion_fraction": 1.0 if passed else 0.9,
                "search_space_exhausted_seed_count": 0,
            }
        summary = {
            "wirings": ["center_outer_same"], "budgets": [4000],
            "budget_summary": {
                "scipy_de_legacy": {"center_outer_same": {"4000": row(False)}},
                "lshade": {"center_outer_same": {"4000": row(True)}},
            },
            "common_dense_validation": {"completed": True, "failures": []},
            "checkpoint_resume_parity": {"status": "passed"},
            "promotion_gate": {},
        }
        self.assertEqual(
            _evaluate_promotion_gate(summary)["decision"],
            "invalid_ab_due_to_budget_shortfall",
        )


    def test_common_dense_validation_uses_one_grid_for_both_algorithms(self):
        from dataclasses import asdict
        from sawopt.core.models import FilterDesign
        from sawopt.optimization import stage33_study as stage33_module

        cfg = {
            "spec": {"passband": [1.0, 2.0], "il": 3.0, "ripple": 2.0,
                     "vswr": 2.5, "stopbands": []},
            "convergence": {"impedance_ohm": 50.0},
            "validation": {"dense_refinement_passes": 0},
        }

        def fake_dense(design, cfg, rs, rl, *, wiring, counters,
                       base_grid=None, passes=None, validation=False):
            del cfg, rs, rl, wiring, counters, passes, validation
            if base_grid is None:
                extra = 10.0 if design.io_idt_pairs == 24 else 20.0
                frequencies = np.asarray([1.0, 2.0, extra])
            else:
                frequencies = np.asarray(base_grid, dtype=float)
            value = float(design.io_idt_pairs) / 100.0
            record = {
                "feasible": False, "max_violation": value,
                "sum_violation": value, "violations": {"x": value},
                "metrics": {"worst_il_db": 5.0 + value, "ripple_db": 1.0},
            }
            return frequencies, (record, {}, SimpleNamespace(y_parameters=np.zeros((len(frequencies), 2, 2))))

        with TemporaryDirectory() as temp, \
                mock.patch.object(stage33_module, "validation_grid", return_value=np.asarray([1.0, 2.0])), \
                mock.patch.object(stage33_module, "dense", side_effect=fake_dense):
            run = Path(temp)
            legacy_dir = run / "trials" / "scipy_de_legacy"
            lshade_dir = run / "trials" / "lshade" / "center_outer_same" / "seed1"
            legacy_dir.mkdir(parents=True)
            lshade_dir.mkdir(parents=True)
            legacy = {
                "seed": 1, "wiring": "center_outer_same",
                "requested_unique_design_budget": 200,
                "design": asdict(FilterDesign(io_idt_pairs=24)),
            }
            low = {
                "seed": 1, "wiring": "center_outer_same",
                "requested_unique_design_budget": 100,
                "design": asdict(FilterDesign(io_idt_pairs=30)),
            }
            terminal = {
                "seed": 1, "wiring": "center_outer_same",
                "requested_unique_design_budget": 200,
                "design": asdict(FilterDesign(io_idt_pairs=30)),
            }
            (legacy_dir / "legacy.json").write_text(json.dumps(legacy), encoding="utf-8")
            (lshade_dir / "B100.json").write_text(json.dumps(low), encoding="utf-8")
            (lshade_dir / "B200.json").write_text(json.dumps(terminal), encoding="utf-8")

            result = validate_ab_candidates(run, cfg)
            self.assertTrue(result["completed"], result["failures"])
            self.assertTrue(result["shared_grid_across_algorithms"])
            self.assertEqual(result["validated_by_algorithm"]["scipy_de_legacy"], 1)
            self.assertEqual(result["validated_by_algorithm"]["lshade"], 2)
            records = [
                json.loads((legacy_dir / "legacy.json").read_text(encoding="utf-8")),
                json.loads((lshade_dir / "B100.json").read_text(encoding="utf-8")),
                json.loads((lshade_dir / "B200.json").read_text(encoding="utf-8")),
            ]
            ids = {record["common_validation_grid_id"] for record in records}
            self.assertEqual(len(ids), 1)
            self.assertEqual({record["common_validation_frequency_count"] for record in records}, {4})

    def test_time_to_target_uses_common_validated_checkpoint_trace(self):
        def row(algorithm, budget, max_violation, seed=1):
            return {
                "algorithm": algorithm, "wiring": "center_outer_same",
                "budget": budget, "seed": seed, "feasible": False,
                "max_violation": max_violation, "sum_violation": max_violation,
                "worst_il_db": 8.0, "ripple_db": 2.0,
                "actual_unique_design_evaluations": budget,
                "common_validation_grid_id": "shared-grid",
                # Deliberately impossible raw-search trace: the helper must ignore it.
                "best_so_far_trace": [{"unique_evaluation": 1, "rank_key": [0, 0, 0, 0, 0]}],
            }

        rows = [
            row("scipy_de_legacy", 4000, 1.5, seed=10),
            row("scipy_de_legacy", 4000, 1.6, seed=11),
            row("lshade", 1000, 2.0),
            row("lshade", 2000, 1.4),
            row("lshade", 4000, 1.3),
        ]
        _attach_time_to_target(rows)
        terminal = next(item for item in rows if item["algorithm"] == "lshade" and item["budget"] == 4000)
        self.assertEqual(terminal["time_to_target_status"], "reached")
        self.assertEqual(terminal["evals_to_target"], 2000)
        self.assertAlmostEqual(terminal["eval_fraction_to_target"], .5)
        self.assertEqual(terminal["time_to_target_source"], "common_validated_checkpoints")
        self.assertEqual([item["checkpoint_budget"] for item in terminal["validated_checkpoint_trace"]], [1000, 2000, 4000])

    def test_ab_gate_treats_search_space_exhaustion_as_inconclusive(self):
        def aggregate(exhausted):
            return {
                "seed_count": 2, "best_primary": 1.0, "median_primary": 1.0,
                "seed_iqr": 0.0, "basin_hit_rates": {"1.8": 2},
                "target_reached_seed_count": 2, "median_evals_to_target": 100.0,
                "median_eval_fraction_to_target": .25,
                "budget_completion_passed": not exhausted,
                "minimum_budget_completion_fraction": 1.0 if not exhausted else 0.5,
                "search_space_exhausted_seed_count": 1 if exhausted else 0,
            }
        summary = {
            "wirings": ["center_outer_same"], "budgets": [4000],
            "budget_summary": {
                "scipy_de_legacy": {"center_outer_same": {"4000": aggregate(False)}},
                "lshade": {"center_outer_same": {"4000": aggregate(True)}},
            },
            "common_dense_validation": {
                "completed": True, "failures": [],
                "shared_grid_across_algorithms": True,
                "validated_by_algorithm": {"scipy_de_legacy": 2, "lshade": 2},
            },
            "checkpoint_resume_parity": {"status": "passed"},
            "promotion_gate": {},
        }
        self.assertEqual(
            _evaluate_promotion_gate(summary)["decision"],
            "inconclusive_due_to_search_space_exhaustion",
        )

    def test_grid_exchange_rebuilds_incumbent_on_new_grid(self):
        state = {"new": False}
        population = np.asarray([[0.0], [0.5]])

        def evaluate(x):
            value = float(2.0 if state["new"] and x[0] == 0.0 else
                          1.0 if state["new"] else
                          0.0 if x[0] == 0.0 else 0.5)
            return {"feasible": True, "max_violation": 0.0,
                    "sum_violation": 0.0, "violations": {},
                    "metrics": {"worst_il_db": value}}

        backend = LShadeBackend(
            [(0, 1)], seed=5,
            config={"initial_population": 4, "min_population": 4,
                    "total_budget": 4, "canonical_space_size": 100},
            integer_indices=(),
        )
        population = np.asarray([[0.0], [0.5], [0.2], [0.8]])
        backend.initialize(evaluate, population=population)
        self.assertEqual(backend.incumbent()["metrics"]["worst_il_db"], 0.0)
        state["new"] = True
        backend.exchange_frequency_grid([2.0], evaluate, version=2)
        self.assertEqual(backend.incumbent()["metrics"]["worst_il_db"], 1.0)
        self.assertEqual(backend.best_so_far_trace[-1]["frequency_grid_version"], 2)
        self.assertEqual(backend.unique_evaluations, 4)

    def test_checkpoint_progression_matches_direct_terminal_run(self):
        direct = LShadeBackend([(0, 1)] * 3, seed=21,
                               config={"initial_population": 8, "min_population": 4,
                                       "total_budget": 40, "hard_max_budget": 40},
                               integer_indices=())
        split = LShadeBackend([(0, 1)] * 3, seed=21,
                              config={"initial_population": 8, "min_population": 4,
                                      "total_budget": 40, "hard_max_budget": 40},
                              integer_indices=())
        direct.initialize(_objective, population=_fixed_population())
        split.initialize(_objective, population=_fixed_population())
        direct.advance_to_unique_budget(40)
        for budget in (20, 30, 40):
            split.advance_to_unique_budget(budget)
        self.assertEqual(
            json.dumps(direct.state_dict(), sort_keys=True),
            json.dumps(split.state_dict(), sort_keys=True),
        )

    def test_checkpoint_progression_uses_new_frequency_grid(self):
        backend = LShadeBackend([(0, 1)] * 3, seed=22,
                                config={"initial_population": 8, "min_population": 4,
                                        "total_budget": 20, "hard_max_budget": 20},
                                integer_indices=())
        backend.initialize(_objective, population=_fixed_population())
        backend.set_frequency_grid([1.0], version=1)
        backend.advance_to_unique_budget(10)
        backend.exchange_frequency_grid([1.0, 2.0], _objective, version=2)
        backend.advance_to_unique_budget(20)
        self.assertEqual(backend.frequency_grid_version, 2)
        self.assertEqual(backend.population_trace[-1]["frequency_grid_version"], 2)
        self.assertTrue(any(
            row["frequency_grid_version"] == 2
            for row in backend.population_trace if row["unique_evaluation"] > 10
        ))

    def test_time_to_target_uses_actual_trace_target(self):
        target = {"feasible": True, "max_violation": 0.0,
                  "violations": {}, "metrics": {"worst_il_db": 1.0}}
        key = list(DEFAULT_COMPARATOR.rank_key(target))
        result = time_to_target(
            [{"unique_evaluation": 6, "rank_key": key}],
            target, requested_unique_budget=100,
        )
        self.assertEqual(result["evals_to_target"], 6)
        self.assertAlmostEqual(result["eval_fraction_to_target"], .06)

    def test_source_hash_change_invalidates_preprod(self):
        checkpoints = {name: "same" for name in SOURCE_HASH_CHECKPOINT_NAMES}
        checkpoints["source_hash_after_smoke"] = "changed"
        result = evaluate_source_hash_gate(checkpoints)
        self.assertFalse(result["passed"])
        self.assertFalse(result["production_allowed"])
        self.assertIn("SOURCE CHANGED", result["message"])

    def test_lshade_success_memory_changes_on_successful_synthetic_run(self):
        backend = LShadeBackend(
            [(0, 1)] * 3, seed=23,
            config={"initial_population": 8, "min_population": 4,
                    "total_budget": 80, "hard_max_budget": 80,
                    "memory_update_batch_size": 4},
            integer_indices=(),
        )
        backend.initialize(_objective, population=_fixed_population())
        backend.advance_to_unique_budget(80)
        self.assertTrue(
            any(not np.isclose(value, .5) for value in backend.m_f)
            or any(not np.isclose(value, .5) for value in backend.m_cr)
        )


if __name__ == "__main__":
    unittest.main()
