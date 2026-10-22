"""Reference regression tests for the settled COM/network conventions.

Run from the parent directory with:
    pytest -q codex_handoff/test_reference.py

When integrating into the real project, move/adapt these tests to the project's
normal test package rather than keeping this handoff package.
"""
import numpy as np
import unittest

from sawopt.physics.com import FixedProvider, block, simulate_filter
from sawopt.physics.network import evaluate
from sawopt.core.models import FilterDesign


def test_synchronous_kappa_zero_analytic_limit():
    lam = 5e-6
    velocity = 4000.0
    f = np.array([velocity/lam])
    length = 10*lam
    alpha = 200.0
    capacitance = 1e-8
    p = dict(
        velocity=velocity,
        kappa=0.0j,
        alpha=alpha,
        capacitance=capacitance,
        loss=0.0,
    )
    P = block(f, length, lam, p)[0]
    expected_p13 = 1j*alpha*length
    expected_p33 = 2*alpha**2*length**2 + 1j*2*np.pi*f[0]*capacitance*length
    assert np.allclose(P[0, 2], expected_p13, rtol=1e-13, atol=1e-15)
    assert np.allclose(P[1, 2], expected_p13, rtol=1e-13, atol=1e-15)
    assert np.allclose(P[2, 2], expected_p33, rtol=1e-13, atol=1e-15)


def test_synchronous_lossless_reflector_limit():
    lam = 5e-6
    velocity = 4000.0
    f = np.array([velocity/lam])
    length = 20*lam
    kappa = 1.7e4
    p = dict(velocity=velocity, kappa=kappa, alpha=0.0, capacitance=0.0, loss=0.0)
    P = block(f, length, lam, p)[0]
    assert np.allclose(P[0, 0], 1j*np.tanh(kappa*length), rtol=1e-12, atol=1e-14)
    assert np.allclose(P[0, 1], 1/np.cosh(kappa*length), rtol=1e-12, atol=1e-14)


def test_gap_forces_zero_coupling_and_free_propagation():
    lam = 5e-6
    velocity = 4000.0
    f = np.array([800e6])
    length = 3.7*lam
    loss = 150.0
    # Deliberately malformed nonzero gap coupling values. block(gap=True)
    # must ignore them by convention.
    p = dict(
        velocity=velocity,
        kappa=3e4 + 2e4j,
        alpha=900 + 300j,
        capacitance=1e-6,
        loss=loss,
    )
    P = block(f, length, lam, p, gap=True)[0]
    expected = np.exp(-1j*(2*np.pi*f[0]/velocity - 1j*loss)*length)
    assert np.allclose(P[0, 1], expected, rtol=1e-12, atol=1e-14)
    assert np.allclose(P[1, 0], expected, rtol=1e-12, atol=1e-14)
    assert np.allclose(P[0, 0], 0.0, atol=1e-14)
    assert np.allclose(P[1, 1], 0.0, atol=1e-14)
    assert np.allclose(P[:, 2], 0.0, atol=1e-14)
    assert np.allclose(P[2, :], 0.0, atol=1e-14)


def test_frequency_dependent_parameter_arrays_are_supported():
    lam = 5e-6
    f = np.linspace(700e6, 900e6, 17)
    n = len(f)
    p = dict(
        velocity=np.linspace(3900.0, 4100.0, n),
        kappa=np.linspace(1e4, 2e4, n)*(1 + 0.2j),
        alpha=np.linspace(100.0, 200.0, n)*(1 - 0.1j),
        capacitance=np.linspace(1e-9, 2e-9, n),
        loss=np.linspace(0.0, 100.0, n),
    )
    P = block(f, 20*lam, lam, p)
    assert P.shape == (n, 3, 3)
    assert np.isfinite(P).all()


def test_network_gt_matches_s21_power_for_real_references():
    rng = np.random.default_rng(12345)
    for _ in range(100):
        a = rng.normal(size=(2, 2))
        conductance = a.T @ a * 1e-3
        b = rng.normal(size=(2, 2))
        susceptance = (b + b.T) * 1e-3
        y = (conductance + 1j*susceptance)[None, :, :]
        rs = float(rng.uniform(20, 200))
        rl = float(rng.uniform(20, 200))
        net = evaluate(y, rs, rl)
        assert np.allclose(net['gt'][0], abs(net['s'][0, 1, 0])**2, rtol=1e-12, atol=1e-14)


def _connect_identical_voltage(P1, P2):
    result = np.zeros_like(P1)
    for n in range(len(P1)):
        for column in range(3):
            drive = np.eye(3)[column]
            R0, S2, V = drive
            matrix = np.array([[1, -P1[n, 1, 1]], [-P2[n, 0, 0], 1]], complex)
            rhs = np.array([
                P1[n, 1, 0]*R0 + P1[n, 1, 2]*V,
                P2[n, 0, 1]*S2 + P2[n, 0, 2]*V,
            ])
            R1, S1 = np.linalg.solve(matrix, rhs)
            left = P1[n] @ np.array([R0, S1, V])
            right = P2[n] @ np.array([R1, S2, V])
            result[n, :, column] = [left[0], right[1], left[2] + right[2]]
    return result


def test_split_com_sections_equal_full_section():
    lam = 5e-6
    f = np.linspace(760e6, 820e6, 9)
    p = dict(velocity=3900., kappa=3500+700j, alpha=900-100j, capacitance=1e-8, loss=120.)
    full = block(f, 24*lam, lam, p)
    half = block(f, 12*lam, lam, p)
    assert np.allclose(_connect_identical_voltage(half, half), full, rtol=2e-11, atol=2e-12)


def test_pmatrix_reciprocity_current_identities():
    f = np.linspace(750e6, 810e6, 11)
    p = dict(velocity=3900., kappa=3000+500j, alpha=800-200j, capacitance=1e-8, loss=80.)
    P = block(f, 60e-6, 5e-6, p)
    assert np.allclose(P[:, 2, 0], -2*P[:, 0, 2], rtol=1e-11, atol=1e-12)
    assert np.allclose(P[:, 2, 1], -2*P[:, 1, 2], rtol=1e-11, atol=1e-12)


def test_fixed_provider_region_overrides_and_gap_zeroing():
    values = {
        'reference_aperture_um': 80, 'velocity_m_s': 3900, 'loss_db_per_lambda': .01,
        'idt': {'velocity_m_s': 4000, 'loss_db_per_lambda': .02, 'kappa_lambda': .02, 'alpha_sqrtS_per_m': 1000, 'capacitance_F_per_m': 1e-8},
        'reflector': {'kappa_lambda': .02, 'alpha_sqrtS_per_m': 0, 'capacitance_F_per_m': 0},
        'gap': {'kappa_lambda': 99, 'alpha_sqrtS_per_m': 99, 'capacitance_F_per_m': 99},
    }
    provider = FixedProvider(values)
    d = FilterDesign()
    assert provider.parameters('idt', d, np.array([1.]))['velocity'] == 4000
    gap = provider.parameters('gap', d, np.array([1.]))
    assert gap['kappa'] == gap['alpha'] == gap['capacitance'] == 0


def test_passive_network_scattering_singular_values():
    rng = np.random.default_rng(8)
    for _ in range(30):
        a = rng.normal(size=(2, 2)); g = a.T @ a * 1e-3
        b = rng.normal(size=(2, 2)); y = (g + 1j*(b+b.T)*1e-3)[None]
        s = evaluate(y, 37, 91)['s'][0]
        assert np.linalg.svd(s, compute_uv=False)[0] <= 1 + 1e-12


def test_condition_number_is_debug_only():
    values = {
        'reference_aperture_um': 80, 'velocity_m_s': 3900,
        'loss_db_per_lambda': .01,
        'idt': {'kappa_lambda': .02, 'alpha_sqrtS_per_m': 1000,
                'capacitance_F_per_m': 1e-8},
        'reflector': {'kappa_lambda': .02, 'alpha_sqrtS_per_m': 0,
                      'capacitance_F_per_m': 0},
        'gap': {'kappa_lambda': 0, 'alpha_sqrtS_per_m': 0,
                'capacitance_F_per_m': 0},
    }
    f = np.linspace(780e6, 800e6, 5)
    ordinary = simulate_filter(FilterDesign(), FixedProvider(values), f)
    debug = simulate_filter(
        FilterDesign(), FixedProvider(values), f, debug_diagnostics=True
    )
    assert 'max_acoustic_condition_number' not in ordinary.diagnostics
    assert np.isfinite(debug.diagnostics['max_acoustic_condition_number'])
    assert 'worst_acoustic_condition_frequency_hz' in debug.diagnostics


class ReferenceAcceptance(unittest.TestCase):
    def test_reference_cases(self):
        for case in (
            test_synchronous_kappa_zero_analytic_limit,
            test_synchronous_lossless_reflector_limit,
            test_gap_forces_zero_coupling_and_free_propagation,
            test_frequency_dependent_parameter_arrays_are_supported,
            test_network_gt_matches_s21_power_for_real_references,
            test_split_com_sections_equal_full_section,
            test_pmatrix_reciprocity_current_identities,
            test_fixed_provider_region_overrides_and_gap_zeroing,
            test_passive_network_scattering_singular_values,
            test_condition_number_is_debug_only,
        ):
            with self.subTest(case=case.__name__):
                case()
