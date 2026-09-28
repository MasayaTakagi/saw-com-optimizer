import unittest

import numpy as np

from sawopt.core.hybrid import compose_stage4a_y


class Stage4AHybridCompositionTests(unittest.TestCase):
    def setUp(self):
        base = np.asarray([
            [[1.2e-3 + 2e-4j, -2e-4 + 3e-5j], [-2e-4 + 3e-5j, 1.1e-3 + 1e-4j]],
            [[1.0e-3 + 1e-4j, -1e-4 + 2e-5j], [-1e-4 + 2e-5j, 1.3e-3 + 3e-4j]],
        ], dtype=complex)
        self.dms_y = base
        self.shunt_a = np.asarray([1.5e-4 + 1e-5j, 2e-4 + 2e-5j])
        self.shunt_b = np.asarray([2.5e-4 + 2e-5j, 1e-4 + 1e-5j])

    def test_d_topology_is_exact_zero_resonator_identity(self):
        result = compose_stage4a_y(self.dms_y, "D", ())
        np.testing.assert_array_equal(result, self.dms_y)

    def test_source_and_load_shunts_preserve_terminal_orientation(self):
        source = compose_stage4a_y(self.dms_y, "P_D", (self.shunt_a,))
        load = compose_stage4a_y(self.dms_y, "D_P", (self.shunt_a,))
        np.testing.assert_allclose(source[:, 0, 0], self.dms_y[:, 0, 0] + self.shunt_a)
        np.testing.assert_array_equal(source[:, 1, 1], self.dms_y[:, 1, 1])
        np.testing.assert_allclose(load[:, 1, 1], self.dms_y[:, 1, 1] + self.shunt_a)
        np.testing.assert_array_equal(load[:, 0, 0], self.dms_y[:, 0, 0])
        np.testing.assert_array_equal(source[:, 0, 1], self.dms_y[:, 0, 1])
        np.testing.assert_array_equal(load[:, 1, 0], self.dms_y[:, 1, 0])

    def test_dual_shunts_are_finite_passive_and_reciprocal(self):
        result = compose_stage4a_y(self.dms_y, "P_D_P", (self.shunt_a, self.shunt_b))
        expected = self.dms_y.copy()
        expected[:, 0, 0] += self.shunt_a
        expected[:, 1, 1] += self.shunt_b
        np.testing.assert_allclose(result, expected)
        self.assertTrue(np.isfinite(result).all())
        np.testing.assert_allclose(result, np.swapaxes(result, 1, 2), atol=1e-12)
        conductance = (result + np.swapaxes(result.conj(), 1, 2)) / 2
        self.assertGreaterEqual(float(np.linalg.eigvalsh(conductance).min()), -1e-12)

    def test_topology_rejects_wrong_resonator_count(self):
        with self.assertRaises(ValueError):
            compose_stage4a_y(self.dms_y, "D", (self.shunt_a,))
        with self.assertRaises(ValueError):
            compose_stage4a_y(self.dms_y, "P_D_P", (self.shunt_a,))


if __name__ == "__main__":
    unittest.main()
