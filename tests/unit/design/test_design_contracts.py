from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pytest

from sawopt.design.geometry import geometry
from sawopt.design.space import BOUNDS, NAMES, FilterDesign, HybridDesignSpace, decode
from sawopt.design.topology import FiveIdtDesign, T1, decode_t1


def test_filter_design_provider_visible_record_and_scalar_decoder_are_frozen():
    design = FilterDesign()
    assert list(asdict(design)) == [
        "wavelength_um", "io_idt_pairs", "center_idt_pairs", "reflector_electrodes",
        "idt_gap_lambda", "reflector_gap_lambda", "aperture_um", "metallization_ratio",
        "thickness_over_lambda",
    ]
    assert (design.metallization_ratio, design.thickness_over_lambda) == (0.5, 0.04)
    assert NAMES == list(asdict(design))[:7]
    assert BOUNDS == [(4.6, 5.4), (20, 100), (10, 80), (40, 160), (0, 3), (0, 3), (30, 150)]

    decoded = decode([5.0, 20.5, 10.5, 40.5, 0.0, 0.0, 80.0])
    assert (decoded.io_idt_pairs, decoded.center_idt_pairs, decoded.reflector_electrodes) == (21, 11, 41)


def test_hybrid_space_clips_rounds_half_up_and_returns_ordered_owned_key():
    active = np.tile(np.asarray([0.0, 10.0]), (10, 1))
    space = HybridDesignSpace.from_contract("D", active, active.copy())
    proposal = np.full(10, 5.0)
    proposal[0] = -2.0
    proposal[4:7] = (4.5, 5.5, 6.5)
    original = proposal.copy()

    canonical, key = space.canonicalize(proposal)

    assert canonical.tolist() == [0.0, 5.0, 5.0, 5.0, 5.0, 6.0, 7.0, 5.0, 5.0, 5.0]
    assert key == tuple(float(value) for value in canonical)
    assert canonical.flags.owndata
    assert not np.shares_memory(canonical, proposal)
    np.testing.assert_array_equal(proposal, original)


def test_hybrid_space_rejects_invalid_bounds_and_nonfinite_proposals():
    active = np.tile(np.asarray([0.0, 10.0]), (10, 1))
    for invalid in (np.nan, np.inf, -np.inf):
        bad = active.copy()
        bad[0, 0] = invalid
        with pytest.raises(ValueError):
            HybridDesignSpace.from_contract("D", bad, active)

    space = HybridDesignSpace.from_contract("D", active, active.copy())
    proposal = np.full(10, 5.0)
    proposal[0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        space.canonicalize(proposal)


def test_geometry_constraints_preserve_exact_boundary_and_individual_violations():
    design = FilterDesign()
    constraints = {
        "max_length_um": 530.0,
        "max_width_um": 80.0,
        "min_electrode_width_um": 1.25,
        "min_electrode_gap_um": 1.25,
        "max_electrodes": 208.0,
    }
    dimensions, violations = geometry(design, constraints)
    assert dimensions == {"length_um": 530.0, "width_um": 80.0, "electrodes": 208}
    assert violations == [0.0, 0.0, 0.0, 0.0, 0.0]

    just_over = dict(constraints, max_length_um=529.0)
    _dimensions, violations = geometry(design, just_over)
    assert violations[0] == pytest.approx(530.0 / 529.0 - 1.0, rel=0.0, abs=1e-15)
    assert violations[1:] == [0.0, 0.0, 0.0, 0.0]


def test_t1_decoder_rounding_and_section_port_order_are_unchanged():
    design = decode_t1([5.0, 5.0, 5.0, 5.0, 4.5, 5.5, 6.5, 0.5, 0.5, 80.0])
    assert isinstance(design, FiveIdtDesign)
    assert (design.pairs_A, design.pairs_B, design.pairs_C) == (5, 6, 7)
    profile = design.section_geometry()
    assert len(profile) == 13
    assert [section["port"] for section in profile if section["port"] is not None] == [0, 1, 2, 3, 4]
    assert [section["label"] for section in profile] == [
        "reflector_left", "reflector_gap_left", "A_left", "gap_A_B", "B_left",
        "gap_B_C_left", "C_center", "gap_C_B_right", "B_right", "gap_B_A_right",
        "A_right", "reflector_gap_right", "reflector_right",
    ]
