from types import SimpleNamespace

import numpy as np
import pytest

from sawopt.physics.literature_com import (
    NormalizedLiteratureCOMProfile,
    profile_from_mapping,
)


PROFILE = NormalizedLiteratureCOMProfile(
    profile_id="test",
    substrate="42YX-LiTaO3",
    electrode_material=None,
    temperature_c=25.0,
    wavelength_um=2.16,
    h_over_lambda=0.08,
    metallization_ratio=0.65,
    velocity_m_s=4045.0,
    kappa_p_percent=-18.96,
    alpha_n_value=92.566,
    capacitance_n_value=52.80,
    gamma_p=0.002684,
    kappa_phase_rad=0.0,
    alpha_phase_rad=0.0,
    phase_policy="SIGNED_REAL_TABLE_ASSUMPTION",
    loss_policy="AMPLITUDE_ATTENUATION_ASSUMPTION",
)
GEOMETRY = SimpleNamespace(wavelength_um=2.16, aperture_um=43.2)


def test_native_conversion_round_trips_normalized_values():
    values = PROFILE.normalized_identities(GEOMETRY)
    assert np.isclose(values["kappa_p"], -0.1896, rtol=0, atol=1e-15)
    assert np.isclose(values["alpha_n"], 92.566e-5, rtol=0, atol=1e-15)
    assert np.isclose(values["capacitance_n"], 52.80e-5 * 1e-6, rtol=0, atol=1e-21)
    assert np.isclose(values["gamma_p"], 0.002684, rtol=0, atol=1e-15)


def test_region_mapping_preserves_sign_and_zeroes_non_idt_terms():
    reflector = PROFILE.parameters("reflector", GEOMETRY)
    gap = PROFILE.parameters("gap", GEOMETRY)
    assert reflector["kappa"].real < 0
    assert reflector["alpha"] == 0j
    assert reflector["capacitance"] == 0.0
    assert gap["kappa"] == 0j
    assert gap["alpha"] == 0j
    assert gap["capacitance"] == 0.0


def test_profile_is_immutable_and_temperature_locked():
    with pytest.raises((AttributeError, TypeError)):
        PROFILE.velocity_m_s = 1.0
    with pytest.raises(ValueError, match="locked"):
        PROFILE.parameters("idt", GEOMETRY, temperature_c=100.0)


def test_missing_source_phase_is_not_silently_replaced():
    blocked = NormalizedLiteratureCOMProfile(
        profile_id="blocked",
        substrate="42YX-LiTaO3",
        electrode_material=None,
        temperature_c=25.0,
        wavelength_um=2.16,
        h_over_lambda=0.08,
        metallization_ratio=0.65,
        velocity_m_s=4045.0,
        kappa_p_percent=-18.96,
        alpha_n_value=92.566,
        capacitance_n_value=52.80,
        gamma_p=0.002684,
    )
    with pytest.raises(ValueError, match="phase/reference"):
        blocked.parameters("idt", GEOMETRY)


def test_signed_real_phase_policy_is_explicit_and_loss_policy_is_required():
    diagnostic = NormalizedLiteratureCOMProfile(
        profile_id="diagnostic",
        substrate="42YX-LiTaO3",
        electrode_material="unspecified_metal",
        temperature_c=25.0,
        wavelength_um=2.16,
        h_over_lambda=0.08,
        metallization_ratio=0.65,
        velocity_m_s=4045.0,
        kappa_p_percent=-18.96,
        alpha_n_value=92.566,
        capacitance_n_value=52.80,
        gamma_p=0.002684,
        phase_policy="SIGNED_REAL_TABLE_ASSUMPTION",
        loss_policy="AMPLITUDE_ATTENUATION_ASSUMPTION",
    )
    values = diagnostic.parameters("idt", GEOMETRY)
    assert values["kappa"].real < 0
    assert values["alpha"].real > 0
    assert values["kappa"].imag == 0.0
    assert values["alpha"].imag == 0.0


def test_mapping_constructor_has_no_fallback_for_critical_values():
    with pytest.raises(ValueError, match="missing fields"):
        profile_from_mapping({"profile_id": "incomplete"})
