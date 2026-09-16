import json
from pathlib import Path

import numpy as np

from sawopt.core.com import simulate_filter
from sawopt.core.metrics import geometry
from sawopt.core.models import FilterDesign, FixedProvider, NAMES
from sawopt.io.config import load_experiment_config
from sawopt.studies.convergence import normalize_convergence_config
from sawopt.studies.stage3_6_gate2a import (
    BASELINE_GROUP,
    ReleasedFilterDesign,
    decode_release,
    release_bounds,
    release_schema,
    simulate_released_filter,
)


ROOT = Path(__file__).resolve().parents[3]


def _s1():
    import yaml
    return yaml.safe_load((ROOT / "artifacts/stage3_5/phase_a_revised/search_space_s1.yaml").read_text())


def _cfg():
    return normalize_convergence_config(load_experiment_config(
        ROOT / "configs/studies/stage3_6_phase_c1_c2_gate2a.yaml"
    ))


def test_release_schema_keeps_legacy_dimension_contract():
    s1 = _s1()
    active, hard, integer_indices = release_bounds("G1_CENTER_PITCH", s1)
    assert active.shape == (8, 2)
    assert hard.shape == (8, 2)
    assert integer_indices == (1, 2, 3)
    assert release_schema(BASELINE_GROUP, s1)["dimension"] == len(NAMES)
    assert release_schema("G1_CENTER_PITCH", s1)["extra_variables"][0]["name"] == "center_wavelength_um"


def test_shared_manifold_reproduces_legacy_com_and_geometry():
    cfg = _cfg()
    design = FilterDesign()
    released = ReleasedFilterDesign()
    frequencies = np.linspace(758e6, 803e6, 13)
    provider = FixedProvider(cfg["com"])
    legacy = simulate_filter(design, provider, frequencies, cfg["center"], wiring="center_outer_same")
    candidate = simulate_released_filter(released, provider, frequencies, cfg["center"], wiring="center_outer_same")
    np.testing.assert_allclose(candidate.y_parameters, legacy.y_parameters, rtol=0, atol=1e-12)
    assert candidate.diagnostics["max_acoustic_solve_residual"] == legacy.diagnostics["max_acoustic_solve_residual"]
    assert geometry(released, cfg["constraints"]) == geometry(design, cfg["constraints"])


def test_release_is_mirrored_and_center_perturbation_is_observable():
    cfg = _cfg()
    provider = FixedProvider(cfg["com"])
    frequencies = np.linspace(758e6, 803e6, 13)
    base = ReleasedFilterDesign()
    perturbed = ReleasedFilterDesign(center_wavelength_um=5.2)
    profile = perturbed.section_geometry()
    assert profile[0] == profile[-1]
    assert {key: profile[2][key] for key in profile[2] if key != "port"} == {
        key: profile[6][key] for key in profile[6] if key != "port"
    }
    symmetric = simulate_released_filter(perturbed, provider, frequencies, cfg["center"], wiring="center_outer_same")
    np.testing.assert_allclose(symmetric.y_parameters[:, 0, 1], symmetric.y_parameters[:, 1, 0], rtol=1e-10, atol=1e-12)
    changed = simulate_released_filter(base, provider, frequencies, cfg["center"], wiring="center_outer_same")
    assert not np.allclose(symmetric.y_parameters, changed.y_parameters, rtol=1e-10, atol=1e-12)


def test_release_decode_serializes_only_experiment_owned_extra_fields():
    design = decode_release([5.0, 24.0, 16.0, 40.0, .5, .5, 80.0, 5.2], "G1_CENTER_PITCH")
    payload = json.loads(json.dumps(design.__dict__))
    assert payload["center_wavelength_um"] == 5.2
    assert payload["reflector_wavelength_um"] is None
    assert design.io_idt_pairs == 24
