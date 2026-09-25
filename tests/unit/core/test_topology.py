import numpy as np

from sawopt.core.com import simulate_filter
from sawopt.core.models import FilterDesign, FixedProvider
from sawopt.core.network import evaluate
from sawopt.core.topology import simulate_section_chain
from sawopt.io.config import load_experiment_config
from sawopt.problem.dms_topologies import (
    FiveIdtDesign,
    ParallelThreeIdtDesign,
    T0,
    T0_PORT_MATRIX,
    T1,
    T1_PORT_MATRIX,
    T2,
    simulate_topology,
)


def _cfg():
    return load_experiment_config("configs/studies/dms_topology_screening.yaml")


def test_t0_matches_the_canonical_filter_path():
    cfg = _cfg()
    provider = FixedProvider(cfg["com"])
    frequencies = np.linspace(758e6, 803e6, 13)
    generic = simulate_topology(FilterDesign(), provider, frequencies, T0)
    direct = simulate_filter(
        FilterDesign(), provider, frequencies, cfg["center"], wiring="center_outer_same",
    )
    np.testing.assert_allclose(generic.y_parameters, direct.y_parameters, rtol=1e-10, atol=1e-12)
    assert generic.diagnostics["reciprocity_error"] <= 1e-7
    assert evaluate(generic.y_parameters, 50, 50)["gt"].max() <= 1 + 1e-7


def test_t1_is_finite_passive_reciprocal_and_deterministic():
    cfg = _cfg()
    provider = FixedProvider(cfg["com"])
    frequencies = np.linspace(758e6, 803e6, 13)
    first = simulate_topology(FiveIdtDesign(), provider, frequencies, T1)
    second = simulate_topology(FiveIdtDesign(), provider, frequencies, T1)
    np.testing.assert_array_equal(first.y_parameters, second.y_parameters)
    assert first.diagnostics["port_matrix"] == [list(row) for row in T1_PORT_MATRIX]
    assert first.diagnostics["reciprocity_error"] <= 1e-7
    assert evaluate(first.y_parameters, 50, 50)["gt"].max() <= 1 + 1e-7


def test_t2_parallel_sums_unterminated_track_admittances():
    cfg = _cfg()
    provider = FixedProvider(cfg["com"])
    frequencies = np.linspace(758e6, 803e6, 13)
    design = ParallelThreeIdtDesign(
        track_A_main_wavelength_um=5.0,
        track_B_main_wavelength_um=5.0,
        total_aperture_um=80.0,
    )
    track = simulate_section_chain(
        design.track_sections(5.0), provider, frequencies, T0_PORT_MATRIX,
        topology_id="track",
    )
    combined = simulate_topology(design, provider, frequencies, T2)
    np.testing.assert_allclose(combined.y_parameters, 2 * track.y_parameters, rtol=1e-10, atol=1e-12)
    assert design.track_aperture_um() == 40.0
    assert combined.diagnostics["parallel_composition"] == "sum_unterminated_two_port_Y"
    assert evaluate(combined.y_parameters, 50, 50)["gt"].max() <= 1 + 1e-7
