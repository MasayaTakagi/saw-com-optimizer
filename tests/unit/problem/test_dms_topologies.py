import unittest
from dataclasses import asdict

import numpy as np

from sawopt.core.metrics import geometry, measure, search_grid
from sawopt.core.network import evaluate
from sawopt.io.config import load_experiment_config
from sawopt.problem import dms_topologies as canonical
from sawopt.studies.stage3_6_gate2a import decode_release
from sawopt.studies import stage3_8_dual_material_dms_topology_fast_screen as legacy


def _load_config_with_initial_design_fixtures(path):
    cfg = load_experiment_config(path)
    cfg["stage3_8"]["initial_designs"] = {
        "M0": "tests/fixtures/stage3_8/m0_initial_design.json",
        "MLIT": "tests/fixtures/stage3_8/mlit_initial_design.json",
    }
    return cfg


class DmsTopologyParity(unittest.TestCase):
    def test_stage38_t0_decoder_matches_g1_g2_release_contract(self):
        cfg = load_experiment_config("configs/studies/stage3_8_dual_material_dms_topology_fast_screen.yaml")
        vector = [5.0, 24.0, 16.0, 40.0, .5, .5, 80.0, 5.2, 4.9]
        self.assertEqual(
            asdict(legacy.decode_design(vector, canonical.T0, cfg)),
            asdict(decode_release(vector, "G1_G2")),
        )

    def test_stage38_exports_are_compatibility_reexports(self):
        self.assertIs(legacy.FiveIdtDesign, canonical.FiveIdtDesign)
        self.assertIs(legacy.ParallelThreeIdtDesign, canonical.ParallelThreeIdtDesign)
        self.assertIs(legacy.simulate_topology, canonical.simulate_topology)
        self.assertIs(legacy.decode_t1, canonical.decode_t1)
        self.assertIs(legacy.decode_t2, canonical.decode_t2)

    def test_saved_fixed_design_metrics_match_pre_move_reference(self):
        cfg = _load_config_with_initial_design_fixtures("configs/studies/stage3_8c_r1_2_pilot.yaml")
        frequencies = search_grid(cfg["spec"], cfg)
        provider, _metadata = legacy._provider("MLIT", cfg)
        reference = {
            canonical.T0: {
                "worst_il_db": 5.54717729290152,
                "ripple_db": 3.5907944846189386,
                "geometry": (392.5298944619181, 148.41366049691598, 162.0),
            },
            canonical.T1: {
                "worst_il_db": 10.066838837687019,
                "ripple_db": 4.242504728282849,
                "geometry": (344.3654494280638, 148.41366049691598, 140.0),
            },
            canonical.T2: {
                "worst_il_db": 23.770954726443527,
                "ripple_db": 20.392420217822114,
                "geometry": (396.45519340653726, 148.41366049691598, 324.0),
            },
        }
        for topology, expected in reference.items():
            design = legacy.initial_design("MLIT", topology, cfg)
            canonical_result = canonical.simulate_topology(design, provider, frequencies, topology)
            compatibility_result = legacy.simulate_topology(design, provider, frequencies, topology)
            np.testing.assert_array_equal(canonical_result.y_parameters, compatibility_result.y_parameters)
            canonical_network = evaluate(canonical_result.y_parameters, 50.0, 50.0)
            compatibility_network = evaluate(compatibility_result.y_parameters, 50.0, 50.0)
            np.testing.assert_array_equal(canonical_network["s"], compatibility_network["s"])
            record = measure(frequencies, canonical_network, design, cfg)
            self.assertAlmostEqual(record["metrics"]["worst_il_db"], expected["worst_il_db"], places=8)
            self.assertAlmostEqual(record["metrics"]["ripple_db"], expected["ripple_db"], places=8)
            dimensions, violations = geometry(design, cfg["constraints"])
            self.assertEqual(max(violations, default=0.0), 0.0)
            for name, target in zip(("length_um", "width_um", "electrodes"), expected["geometry"]):
                self.assertAlmostEqual(dimensions[name], target, places=11)


if __name__ == "__main__":
    unittest.main()
