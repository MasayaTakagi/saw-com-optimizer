from dataclasses import asdict
import unittest

import numpy as np

from sawopt.core.hybrid import resonator_admittance
from sawopt.problem.dms_topologies import T1
from sawopt.problem.hybrid import HybridDesignSpace, hybrid_geometry
from sawopt.studies.dms_topology_common import decode_design
from sawopt.studies.hybrid import _stage4a_load_context


class Stage4AHybridDesignSpaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = _stage4a_load_context("configs/studies/hybrid_stage4a_qualification.yaml")

    def test_t1_decode_matches_current_dms_decoder(self):
        cfg = self.context["cfg"]
        space = self.context["spaces"]["D"]
        vector = np.mean(space.bounds, axis=1)
        candidate = space.decode(vector, reflector_electrodes=cfg["dms_topology"]["t1_reflector_electrodes"])
        current = decode_design(vector, T1, cfg)
        self.assertEqual(asdict(candidate.dms_design), asdict(current))

    def test_resonator_pair_rounding_and_canonical_identity(self):
        space = self.context["spaces"]["P_D"]
        low = np.mean(space.bounds, axis=1)
        first, _ = space.canonicalize(np.r_[low[:11], 21.1, low[12]])
        second, first_key = space.canonicalize(np.r_[low[:11], 21.49, low[12]])
        self.assertEqual(first[11], 21)
        self.assertEqual(second[11], 21)
        self.assertEqual(tuple(first), first_key)
        rounded, _ = space.canonicalize(np.r_[low[:11], 21.5, low[12]])
        self.assertEqual(rounded[11], 22)
        self.assertEqual(space.decode(first).resonator_designs[0].pairs, 21)

    def test_bounds_validate_against_current_t1_hard_contract(self):
        space = self.context["spaces"]["D"]
        active = space.bounds.copy()
        hard = active.copy()
        active[0, 0] -= 0.1
        with self.assertRaises(ValueError):
            HybridDesignSpace.from_contract("D", active, hard)
        with self.assertRaises(ValueError):
            HybridDesignSpace.from_contract("S_D", space.bounds, space.bounds)

    def test_combined_layout_rejects_electrode_overflow_separately(self):
        space = self.context["spaces"]["P_D_P"]
        vector = np.mean(space.bounds, axis=1)
        vector[11] = 60
        vector[14] = 60
        candidate = space.decode(vector)
        result = hybrid_geometry(candidate, self.context["cfg"])
        self.assertEqual(result["dms"]["max_violation"], 0.0)
        self.assertEqual(result["resonators"][0]["max_violation"], 0.0)
        self.assertGreater(result["combined"]["violations"]["max_total_electrodes"], 0.0)
        self.assertGreater(result["max_violation"], 0.0)

    def test_resonator_output_is_deterministic_finite_and_passive(self):
        design = self.context["spaces"]["P_D"].decode(
            np.r_[np.mean(self.context["spaces"]["P_D"].bounds[:10], axis=1), 5.0, 20.0, 90.0]
        ).resonator_designs[0]
        frequencies = np.asarray([758e6, 780e6, 803e6])
        first = resonator_admittance(design, self.context["provider"], frequencies)
        second = resonator_admittance(design, self.context["provider"], frequencies)
        np.testing.assert_array_equal(first, second)
        self.assertTrue(np.isfinite(first).all())
        self.assertGreaterEqual(float(np.min(np.real(first))), -1e-8)


if __name__ == "__main__":
    unittest.main()
