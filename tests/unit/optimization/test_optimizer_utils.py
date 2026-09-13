import numpy as np
import unittest

from sawopt.optimization.optimizer_utils import scaled_population, critical_frequencies, new_frequency_points


def test_population_scales_with_dimension():
    assert scaled_population(56, 7) == 56
    assert scaled_population(56, 10) == 80
    assert scaled_population(56, 13) == 104


def test_critical_frequencies_include_spec_controllers():
    f = np.array([700, 758, 770, 780, 803, 840, 900], float) * 1e6
    il = np.array([40, 1.0, 3.0, 1.5, 2.0, 35, 45.0])
    vswr = np.column_stack([
        [1, 1.2, 2.4, 1.1, 1.3, 1, 1],
        [1, 1.1, 1.2, 2.6, 1.2, 1, 1],
    ])
    spec = {'passband': [758, 803], 'stopbands': [[690, 710, 20], [830, 850, 30]]}
    pts = critical_frequencies(f, {'il': il, 'vswr': vswr}, spec, slope_threshold_db=100)
    assert 770e6 in pts  # worst passband IL and input VSWR
    assert 780e6 in pts  # worst output VSWR
    assert 700e6 in pts  # stopband minimum attenuation in first stopband
    assert 840e6 in pts  # stopband minimum attenuation in second stopband


def test_new_frequency_points_respects_tolerance():
    existing = np.array([1e6, 2e6, 3e6])
    cand = np.array([1e6 + 500, 1.5e6, 3e6 + 2000])
    out = new_frequency_points(existing, cand, tolerance_hz=1000)
    assert np.allclose(out, [1.5e6, 3e6 + 2000])


class OptimizerUtilsAcceptance(unittest.TestCase):
    def test_reference_cases(self):
        for case in (
            test_population_scales_with_dimension,
            test_critical_frequencies_include_spec_controllers,
            test_new_frequency_points_respects_tolerance,
        ):
            with self.subTest(case=case.__name__):
                case()
