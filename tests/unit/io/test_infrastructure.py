import json
import os
import unittest
from pathlib import Path

from sawopt.io.config import deep_update, load_experiment_config
from sawopt.io.serialization import save
from sawopt.optimization import runner
from sawopt.runtime.parallel import single_blas_thread_environment


ROOT = Path(__file__).resolve().parents[3]


class ConfigurationInfrastructure(unittest.TestCase):
    def test_current_study_config_resolves_its_base_and_declares_role(self):
        cfg = load_experiment_config(ROOT / "configs" / "studies" / "dms_topology_screening.yaml")
        self.assertEqual(cfg["study"]["type"], "dms_topology_screening")
        self.assertIn("dms_topology", cfg)
        self.assertEqual(cfg["dms_topology"]["checkpoints"], [2000, 4000, 6000, 8000])


    def test_deep_update_preserves_recursive_merge_and_replacement(self):
        target = {"nested": {"keep": 1, "replace": {"old": True}}, "scalar": 1}
        result = deep_update(target, {"nested": {"replace": 2}, "scalar": {"new": True}})
        self.assertIs(result, target)
        self.assertEqual(target, {"nested": {"keep": 1, "replace": 2}, "scalar": {"new": True}})


class RunInfrastructure(unittest.TestCase):
    def test_current_runner_uses_canonical_run_helpers(self):
        self.assertTrue(callable(runner.initialize))
        self.assertTrue(callable(runner.optimize_one))

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
