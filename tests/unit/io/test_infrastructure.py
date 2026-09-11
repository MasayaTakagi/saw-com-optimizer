import hashlib
import json
import os
import unittest
from pathlib import Path

from sawopt.io.config import deep_update, load_experiment_config, load_study_config
from sawopt.io.run_store import initialize
from sawopt.io.serialization import save
from sawopt.optimization import study
from sawopt.optimization import runner
from sawopt.optimization.convergence_study import normalize_convergence_config
from sawopt.runtime.parallel import single_blas_thread_environment


ROOT = Path(__file__).resolve().parents[3]


class ConfigurationInfrastructure(unittest.TestCase):
    def test_ordered_fragment_resolution_matches_phase0_fingerprints(self):
        expected = {
            "next_50ohm_dms_production.yaml": "9019f1e7ec1e29db13e5a4db3f126e3f63f5567cdd7c172df4fcb2e3a527114d",
            "next_50ohm_center_outer_same_16000.yaml": "e3a86a1feba308029c34be392bddf689b70a57616f85f7a6cb31d312e6e2d023",
        }
        for filename, fingerprint in expected.items():
            path = ROOT / "configs" / "studies" / filename
            cfg = normalize_convergence_config(load_study_config(path))
            payload = json.dumps(cfg, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), fingerprint)

        cfg = normalize_convergence_config(load_study_config(
            ROOT / "configs" / "studies" / "next_50ohm_center_outer_same_16000.yaml"
        ))
        self.assertEqual(cfg["optimizer_validation"]["budgets"], [500, 1000, 2000, 4000, 8000])
        self.assertEqual(cfg["optimizer_validation"]["optional_max_budget"], 16000)
        self.assertEqual(cfg["optimizer_validation"]["parallel"]["production_workers"], 5)
        self.assertEqual(cfg["optimizer_validation"]["parallel"]["blas_threads_per_worker"], 1)
        self.assertEqual(
            cfg["inputs"]["stage3_2_production_process5_fragment.yaml"],
            (ROOT / "configs" / "stage3_2_production_process5_fragment.yaml").read_text(encoding="utf-8"),
        )

    def test_deep_update_preserves_recursive_merge_and_replacement(self):
        target = {"nested": {"keep": 1, "replace": {"old": True}}, "scalar": 1}
        result = deep_update(target, {"nested": {"replace": 2}, "scalar": {"new": True}})
        self.assertIs(result, target)
        self.assertEqual(target, {"nested": {"keep": 1, "replace": 2}, "scalar": {"new": True}})

    def test_experiment_protocol_and_center_16000_resolution(self):
        experiments = sorted((ROOT / "experiments").glob("*/experiment.yaml"))
        protocols = {
            load_experiment_config(path)["study"]["type"] for path in experiments
        }
        self.assertEqual(
            protocols,
            {"topology_screening", "continuation", "optimizer_ab", "preproduction"},
        )
        self.assertFalse(
            (ROOT / "experiments" / "stage3_1_convergence" / "experiment.yaml").exists()
        )
        legacy = load_study_config(ROOT / "configs" / "studies" / "next_50ohm_center_outer_same_16000.yaml")
        migrated = load_experiment_config(
            ROOT / "experiments" / "stage3_2_center_outer_same_16000" / "experiment.yaml"
        )
        self.assertEqual(migrated.pop("study"), {"type": "continuation"})
        experiment_key = "experiments/stage3_2_center_outer_same_16000/experiment.yaml"
        self.assertIn(experiment_key, migrated["inputs"])
        self.assertEqual(
            migrated["inputs"][experiment_key],
            (ROOT / experiment_key).read_text(encoding="utf-8"),
        )
        migrated["inputs"].pop(experiment_key)
        self.assertEqual(migrated, legacy)

        stage33 = load_experiment_config(
            ROOT / "experiments" / "stage3_3_optimizer_ab" / "experiment.yaml"
        )
        self.assertIn(
            "experiments/stage3_3_optimizer_ab/experiment.yaml",
            stage33["inputs"],
        )
        self.assertIn("stage3_3_convergence_50ohm.yaml", stage33["inputs"])


class RunInfrastructure(unittest.TestCase):
    def test_legacy_study_exports_are_canonical_helpers(self):
        self.assertIs(study.initialize, initialize)
        self.assertIs(study.save, save)
        self.assertIs(study.optimize_one, runner.optimize_one)

    def test_json_save_is_atomic_and_blas_context_restores_environment(self):
        with self.subTest("save"):
            path = ROOT / "tests" / "unit" / "io" / "_temporary_infrastructure.json"
            try:
                save(path, {"value": 3})
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"value": 3})
                self.assertFalse(path.with_suffix(path.suffix + ".tmp").exists())
            finally:
                path.unlink(missing_ok=True)

        names = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
        original = {name: os.environ.get(name) for name in names}
        try:
            for name in names:
                os.environ[name] = "17"
            before_context = {name: os.environ.get(name) for name in names}
            with single_blas_thread_environment(3):
                self.assertEqual({name: os.environ[name] for name in names}, {name: "3" for name in names})
            self.assertEqual({name: os.environ.get(name) for name in names}, before_context)
        finally:
            for name, value in original.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
