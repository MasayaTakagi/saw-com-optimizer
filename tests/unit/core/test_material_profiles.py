import copy
from pathlib import Path

import numpy as np
import pytest
import yaml

from sawopt.design.space import FilterDesign
from sawopt.physics.com import FixedProvider, LiteratureProfileProvider


def _metadata():
    return {
        "substrate": "42YX_LiTaO3",
        "electrode_material": "Al",
        "h_over_lambda": 0.04,
        "metallization_ratio": 0.6,
        "frequency_context": "758-803 MHz",
        "phasor_convention": "exp(+j omega t)",
        "x_direction": "left_to_right",
        "acoustic_normalization": "|R|^2 - |S|^2",
        "electrical_normalization": "peak V, current into transducer",
        "parameter_definitions": "repository COM convention",
        "normalization_convention": "dimensional alpha/C and kappa_lambda",
        "source_citation": "test fixture",
        "source_publication_metadata": "test fixture",
    }


def _profile(com, classification="DIRECT_COMPATIBLE"):
    return {
        "classification": classification,
        "metadata": _metadata(),
        "com": com,
    }


def test_literature_provider_m0_matches_fixed_provider():
    values = yaml.safe_load(
        (Path(__file__).parents[3] / "configs" / "models" / "com_params_hypothetical.yaml").read_text()
    )
    old = FixedProvider(values)
    new = LiteratureProfileProvider(
        {"M0": _profile(copy.deepcopy(values), "CURRENT_BASELINE")}, "M0"
    )
    design = FilterDesign()
    frequencies = np.linspace(758e6, 803e6, 7)
    for region in ("idt", "reflector", "gap"):
        expected = old.parameters(region, design, frequencies)
        actual = new.parameters(region, design, frequencies)
        for key in expected:
            np.testing.assert_allclose(actual[key], expected[key], rtol=0, atol=0)


def test_profile_switching_changes_com_parameters():
    base = {
        "reference_aperture_um": 80.0,
        "velocity_m_s": 3900.0,
        "loss_db_per_lambda": 0.015,
        "idt": {"kappa_lambda": 0.020, "alpha_sqrtS_per_m": 1200.0,
                "capacitance_F_per_m": 1e-8},
        "reflector": {"kappa_lambda": 0.020, "alpha_sqrtS_per_m": 0.0,
                       "capacitance_F_per_m": 0.0},
        "gap": {"kappa_lambda": 0.0, "alpha_sqrtS_per_m": 0.0,
                "capacitance_F_per_m": 0.0},
    }
    changed = copy.deepcopy(base)
    changed["velocity_m_s"] = 4100.0
    changed["idt"]["kappa_lambda"] = 0.025
    changed["idt"]["alpha_sqrtS_per_m"] = 900.0
    provider_0 = LiteratureProfileProvider({"M0": _profile(base)}, "M0")
    provider_1 = LiteratureProfileProvider({"M1": _profile(changed)}, "M1")
    geometry = FilterDesign()
    frequencies = np.array([780e6])
    first = provider_0.parameters("idt", geometry, frequencies)
    second = provider_1.parameters("idt", geometry, frequencies)
    assert first["velocity"] != second["velocity"]
    assert not np.allclose(first["kappa"], second["kappa"])
    assert not np.allclose(first["alpha"], second["alpha"])


def test_incomplete_profile_is_rejected_without_m0_fallback():
    values = {
        "reference_aperture_um": 80.0,
        "velocity_m_s": 3900.0,
        "loss_db_per_lambda": 0.015,
        "idt": {"kappa_lambda": 0.020, "capacitance_F_per_m": 1e-8},
        "reflector": {"kappa_lambda": 0.020, "alpha_sqrtS_per_m": 0.0,
                       "capacitance_F_per_m": 0.0},
        "gap": {"kappa_lambda": 0.0, "alpha_sqrtS_per_m": 0.0,
                "capacitance_F_per_m": 0.0},
    }
    with pytest.raises(ValueError, match="missing"):
        LiteratureProfileProvider({"M1": _profile(values)}, "M1")


def test_reference_only_profile_cannot_be_used_by_provider():
    values = {
        "reference_aperture_um": 80.0,
        "velocity_m_s": 3900.0,
        "loss_db_per_lambda": 0.015,
        "idt": {"kappa_lambda": 0.020, "alpha_sqrtS_per_m": 1200.0,
                "capacitance_F_per_m": 1e-8},
        "reflector": {"kappa_lambda": 0.020, "alpha_sqrtS_per_m": 0.0,
                       "capacitance_F_per_m": 0.0},
        "gap": {"kappa_lambda": 0.0, "alpha_sqrtS_per_m": 0.0,
                "capacitance_F_per_m": 0.0},
    }
    with pytest.raises(ValueError, match="not production-eligible"):
        LiteratureProfileProvider(
            {"M1": _profile(values, "REFERENCE_ONLY")}, "M1"
        )
