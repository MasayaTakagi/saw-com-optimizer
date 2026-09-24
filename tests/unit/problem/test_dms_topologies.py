import hashlib
import unittest

import numpy as np

from sawopt.core.metrics import geometry, measure, search_grid
from sawopt.core.network import evaluate
from sawopt.io.config import load_experiment_config
from sawopt.problem import dms_topologies as canonical
from sawopt.studies import stage3_8_dual_material_dms_topology_fast_screen as legacy


class DmsTopologyParity(unittest.TestCase):
    def test_stage38_exports_are_compatibility_reexports(self):
        self.assertIs(legacy.FiveIdtDesign, canonical.FiveIdtDesign)
        self.assertIs(legacy.ParallelThreeIdtDesign, canonical.ParallelThreeIdtDesign)
        self.assertIs(legacy.simulate_topology, canonical.simulate_topology)
        self.assertIs(legacy.decode_t1, canonical.decode_t1)
        self.assertIs(legacy.decode_t2, canonical.decode_t2)

    def test_saved_fixed_design_response_matches_pre_move_reference(self):
        cfg = load_experiment_config("configs/studies/stage3_8c_r1_2_pilot.yaml")
        frequencies = search_grid(cfg["spec"], cfg)
        provider, _metadata = legacy._provider("MLIT", cfg)
        reference = {
            canonical.T0: {
                "y": "0507654ffe4e44d33603f670e38e88f6a8c7fbdcabba9cfa3b5e5e78a7d209c1",
                "s": "bd6bbf3cc77bfe7e9dcecb9a581736d99309330e38384961773f50b2fdb2226e",
                "worst_il_db": 5.54717729290152,
                "ripple_db": 3.5907944846189386,
                "geometry": (392.5298944619181, 148.41366049691598, 162.0),
            },
            canonical.T1: {
                "y": "3ab3453554c6d0df4dc90a481a808b3bfdef056acabac30197cf98f067b09b81",
                "s": "41e4dba77b9e6383da3d3b0dea90f1b2858cc1f047684eac1db8f5de43fb1d4b",
                "worst_il_db": 10.066838837687019,
                "ripple_db": 4.242504728282849,
                "geometry": (344.3654494280638, 148.41366049691598, 140.0),
            },
            canonical.T2: {
                "y": "3e5dccd3f327f88690d5c291d0319da9a6d2d70f9f52c2d4af9a8642aa10d89d",
                "s": "ac5c21ffba8a41dc46a0d0e5b454f1d2f85a476cb3ece521ff4314b763d43381",
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
            self.assertEqual(
                hashlib.sha256(np.asarray(canonical_result.y_parameters, dtype="<c16").tobytes()).hexdigest(),
                expected["y"],
            )
            self.assertEqual(
                hashlib.sha256(np.asarray(canonical_network["s"], dtype="<c16").tobytes()).hexdigest(),
                expected["s"],
            )
            record = measure(frequencies, canonical_network, design, cfg)
            self.assertAlmostEqual(record["metrics"]["worst_il_db"], expected["worst_il_db"], places=11)
            self.assertAlmostEqual(record["metrics"]["ripple_db"], expected["ripple_db"], places=11)
            dimensions, violations = geometry(design, cfg["constraints"])
            self.assertEqual(max(violations, default=0.0), 0.0)
            for name, target in zip(("length_um", "width_um", "electrodes"), expected["geometry"]):
                self.assertAlmostEqual(dimensions[name], target, places=11)


if __name__ == "__main__":
    unittest.main()
