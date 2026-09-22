import numpy as np

from sawopt.core.com import simulate_filter
from sawopt.core.models import FilterDesign, FixedProvider
from sawopt.core.network import evaluate
from sawopt.core.topology import parallel_two_port_admittance, simulate_section_chain
from sawopt.studies.stage3_6_gate2a import ReleasedFilterDesign, simulate_released_filter
from sawopt.studies.stage3_8_dual_material_dms_topology_fast_screen import (
    T0,
    T0_PORT_MATRIX,
    T1,
    T1_PORT_MATRIX,
    T2,
    FiveIdtDesign,
    ParallelThreeIdtDesign,
    implementation_validation,
    simulate_topology,
)
from sawopt.io.config import load_experiment_config


ROOT = __import__("pathlib").Path(__file__).parents[3]


def _cfg():
    return load_experiment_config(ROOT / "configs/studies/stage3_8_dual_material_dms_topology_fast_screen.yaml")


def test_generic_t0_matches_legacy_and_released_paths():
    cfg = _cfg()
    provider = FixedProvider(cfg["com"])
    frequencies = np.linspace(758e6, 803e6, 13)
    legacy = simulate_filter(FilterDesign(), provider, frequencies, cfg["center"], wiring="center_outer_same")
    released = simulate_released_filter(ReleasedFilterDesign(), provider, frequencies, cfg["center"], wiring="center_outer_same")
    generic = simulate_topology(ReleasedFilterDesign(), provider, frequencies, T0)
    np.testing.assert_allclose(generic.y_parameters, legacy.y_parameters, rtol=1e-10, atol=1e-12)
    np.testing.assert_allclose(generic.y_parameters, released.y_parameters, rtol=1e-10, atol=1e-12)
    assert generic.diagnostics["reciprocity_error"] <= 1e-7
    assert evaluate(generic.y_parameters, 50, 50)["gt"].max() <= 1 + 1e-7


def test_t1_is_finite_passive_reciprocal_and_deterministic():
    cfg = _cfg()
    provider = FixedProvider(cfg["com"])
    frequencies = np.linspace(758e6, 803e6, 13)
    design = FiveIdtDesign()
    first = simulate_topology(design, provider, frequencies, T1)
    second = simulate_topology(design, provider, frequencies, T1)
    np.testing.assert_array_equal(first.y_parameters, second.y_parameters)
    assert first.diagnostics["port_matrix"] == [list(row) for row in T1_PORT_MATRIX]
    assert first.diagnostics["reciprocity_error"] <= 1e-7
    assert evaluate(first.y_parameters, 50, 50)["gt"].max() <= 1 + 1e-7


def test_t2_parallel_sums_unterminated_track_y_and_splits_aperture():
    cfg = _cfg()
    provider = FixedProvider(cfg["com"])
    frequencies = np.linspace(758e6, 803e6, 13)
    design = ParallelThreeIdtDesign(
        track_A_main_wavelength_um=5.0,
        track_B_main_wavelength_um=5.0,
        total_aperture_um=80.0,
    )
    track = simulate_section_chain(
        design.track_sections(5.0), provider, frequencies, T0_PORT_MATRIX, topology_id="track",
    )
    combined = simulate_topology(design, provider, frequencies, T2)
    np.testing.assert_allclose(combined.y_parameters, 2 * track.y_parameters, rtol=1e-10, atol=1e-12)
    assert design.track_aperture_um() == 40.0
    assert combined.diagnostics["parallel_composition"] == "sum_unterminated_two_port_Y"
    assert evaluate(combined.y_parameters, 50, 50)["gt"].max() <= 1 + 1e-7


def test_stage3_8_implementation_gate_passes():
    result = implementation_validation(_cfg())
    assert result["status"] == "PASS"
