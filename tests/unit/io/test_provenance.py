import tempfile
import unittest
from pathlib import Path

from sawopt.io.provenance import (
    build_fingerprint_metadata,
    computation_gate_matches,
    read_fingerprint_metadata,
)


class FingerprintV2(unittest.TestCase):
    def _root(self, directory):
        root = Path(directory)
        (root / "src" / "sawopt").mkdir(parents=True)
        (root / "src" / "sawopt" / "numerics.py").write_text("result = 1\n", encoding="utf-8")
        (root / "src" / "sawopt" / "report.py").write_text("title = 'one'\n", encoding="utf-8")
        return root

    def _fingerprints(self, root, configuration=None):
        return build_fingerprint_metadata(
            root,
            configuration or {"bounds": [1, 4]},
            computation_paths=["src/sawopt/numerics.py"],
            reporting_paths=["src/sawopt/report.py"],
        )

    def test_reporting_edit_changes_only_reporting_fingerprint(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self._root(temp)
            before = self._fingerprints(root)
            (root / "src" / "sawopt" / "report.py").write_text("title = 'two'\n", encoding="utf-8")
            after = self._fingerprints(root)
            self.assertEqual(before["computation_fingerprint"], after["computation_fingerprint"])
            self.assertNotEqual(before["reporting_fingerprint"], after["reporting_fingerprint"])
            self.assertTrue(computation_gate_matches(before, after))

    def test_numerical_source_and_configuration_edits_change_computation_fingerprint(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self._root(temp)
            before = self._fingerprints(root)
            (root / "src" / "sawopt" / "numerics.py").write_text("result = 2\n", encoding="utf-8")
            source_changed = self._fingerprints(root)
            self.assertNotEqual(before["computation_fingerprint"], source_changed["computation_fingerprint"])
            config_changed = self._fingerprints(root, {"bounds": [1, 5]})
            self.assertNotEqual(source_changed["computation_fingerprint"], config_changed["computation_fingerprint"])

    def test_dependency_paths_are_explicit_and_validated(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self._root(temp)
            with self.assertRaises(FileNotFoundError):
                build_fingerprint_metadata(
                    root, {}, computation_paths=["missing.py"], reporting_paths=[]
                )
            with self.assertRaises(ValueError):
                build_fingerprint_metadata(
                    root, {}, computation_paths=["src/sawopt/numerics.py"] * 2,
                    reporting_paths=[],
                )

    def test_legacy_fingerprint_is_read_without_rewriting_its_value(self):
        legacy = {"fingerprint": "legacy-v1", "source_hash": "old-source"}
        normalized = read_fingerprint_metadata(legacy)
        self.assertEqual(normalized["fingerprint_schema_version"], 1)
        self.assertEqual(normalized["legacy_fingerprint"], "legacy-v1")
        self.assertEqual(legacy["fingerprint"], "legacy-v1")
        self.assertTrue(computation_gate_matches(legacy, {"fingerprint": "legacy-v1"}))
        self.assertFalse(computation_gate_matches(legacy, {
            "fingerprint_schema_version": 2,
            "computation_fingerprint": "legacy-v1",
            "reporting_fingerprint": "r",
            "dependency_manifest": {"computation": [], "reporting": []},
        }))


if __name__ == "__main__":
    unittest.main()
