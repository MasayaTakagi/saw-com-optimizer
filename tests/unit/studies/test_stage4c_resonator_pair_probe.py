from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pytest

from sawopt.studies.audits.stage4c_resonator_pair_probe import (
    candidate_at_pairs,
    classify_signal,
    probe_values,
)


@dataclass(frozen=True)
class DummyResonator:
    wavelength_um: float
    pairs: int
    aperture_um: float


@dataclass(frozen=True)
class DummyCandidate:
    topology: str
    vector: tuple[float, ...]
    key: tuple[float, ...]
    dms_design: tuple[float, ...]
    resonator_designs: tuple[DummyResonator, ...]


def test_probe_values_include_selected_coordinate_and_unique_fixed_points():
    assert probe_values(60) == (60, 65, 70, 75)
    assert probe_values(59) == (59, 60, 65, 70, 75)
    with pytest.raises(ValueError):
        probe_values(76)


@pytest.mark.parametrize("original", [58, 59, 60])
def test_candidate_at_pairs_changes_only_resonator_pair_coordinate(original):
    vector = [5.0] * 13
    vector[10:13] = [5.2, float(original), 100.0]
    base = DummyCandidate(
        topology="P_D", vector=tuple(vector), key=tuple(vector),
        dms_design=tuple(vector[:10]),
        resonator_designs=(DummyResonator(5.2, original, 100.0),),
    )
    space = SimpleNamespace(decode=lambda *_args, **_kwargs: base)
    selected = {
        "candidate_vector": vector,
        "resonator_designs": [{"pairs": original}],
    }

    result = candidate_at_pairs(space, selected, 70, reflector_electrodes=40)

    assert result.vector[11] == 70
    assert result.resonator_designs[0].pairs == 70
    assert [i for i, (before, after) in enumerate(zip(base.vector, result.vector))
            if before != after] == [11]
    assert result.dms_design == base.dms_design
    assert result.resonator_designs[0].wavelength_um == 5.2
    assert result.resonator_designs[0].aperture_um == 100.0
    with pytest.raises(ValueError):
        candidate_at_pairs(space, selected, 66, reflector_electrodes=40)


def test_signal_requires_three_distinct_cells_to_cross_materiality_threshold():
    rows = [
        {"topology": "P_D", "seed": 20261007, "probe_pairs": 65,
         "geometry_valid": True, "delta_max_violation": -0.025},
        {"topology": "D_P", "seed": 20261007, "probe_pairs": 65,
         "geometry_valid": True, "delta_max_violation": -0.021},
        {"topology": "D_P", "seed": 20261009, "probe_pairs": 70,
         "geometry_valid": True, "delta_max_violation": -0.020},
    ]
    assert classify_signal(rows) == "STRONG_BOUND_SIGNAL"
    assert classify_signal(rows[:2]) == "MIXED_BOUND_SIGNAL"
    assert classify_signal([
        {"topology": "P_D", "seed": 20261007, "probe_pairs": 65,
         "geometry_valid": False, "delta_max_violation": None},
    ]) == "NO_BOUND_SIGNAL"


def test_stage4a_evaluator_accepts_probe_geometry_bounds_without_mutating_them(monkeypatch):
    from sawopt.core import metrics
    from sawopt.physics import network
    from sawopt.problem import hybrid as problem_hybrid
    from sawopt.studies import hybrid as study_hybrid

    seen = {}

    def fake_geometry(candidate, cfg, *, resonator_bounds=None):
        del candidate, cfg
        seen["bounds"] = None if resonator_bounds is None else np.asarray(resonator_bounds).copy()
        return {
            "dms": {"violations": {}}, "resonator_violations": {},
            "combined": {"violations": {}}, "max_violation": 0.0,
        }

    monkeypatch.setattr(problem_hybrid, "hybrid_geometry", fake_geometry)
    monkeypatch.setattr(study_hybrid, "_stage4a_y", lambda *_args: (None, {}))
    monkeypatch.setattr(network, "evaluate", lambda *_args: {
        "gt": np.asarray([0.9]), "s": np.zeros((1, 2, 2), dtype=complex),
    })
    monkeypatch.setattr(metrics, "measure", lambda *_args: {
        "metrics": {"worst_il_db": 1.0, "ripple_db": 0.5},
        "violations": {"stop_1": 0.0, "stop_2": 0.1}, "objective": 1.0,
    })
    @dataclass
    class Design:
        pairs: int

    candidate = SimpleNamespace(
        topology="P_D", vector=(0.0,), key=(0.0,), dms_design=Design(1),
        resonator_designs=(Design(60),),
    )
    probe_bounds = np.asarray([[4.5, 5.6], [10, 75], [30, 150]], dtype=float)
    frozen_copy = probe_bounds.copy()

    default_result = study_hybrid.stage4a_evaluate(
        candidate, object(), {}, np.asarray([1.0]), 50.0, 50.0,
    )
    assert default_result["geometry_valid"] is True
    assert seen["bounds"] is None

    probe_result = study_hybrid.stage4a_evaluate(
        candidate, object(), {}, np.asarray([1.0]), 50.0, 50.0,
        geometry_resonator_bounds=probe_bounds,
    )

    assert probe_result["geometry_valid"] is True
    np.testing.assert_array_equal(seen["bounds"], frozen_copy)
    np.testing.assert_array_equal(probe_bounds, frozen_copy)
    assert probe_result["max_violation"] == default_result["max_violation"]


def test_normal_evaluation_rejects_pair_65_but_probe_geometry_allows_diagnosis():
    import json
    from pathlib import Path

    from sawopt.problem.hybrid import hybrid_geometry
    from sawopt.studies.audits.stage4c_resonator_pair_probe import candidate_at_pairs
    from sawopt.studies.hybrid import stage4a_evaluate
    from sawopt.studies.hybrid_stage4c import load_stage4c_context

    root = Path(__file__).resolve().parents[3]
    evidence = root / "reports/experiment_reviews/stage4c/20261006_124153_ed50ba"
    context = load_stage4c_context("configs/studies/hybrid_stage4c_confirmatory.yaml")
    cell = json.loads((evidence / "cells/P_D/20261007_result.json").read_text(encoding="utf-8"))
    selected = cell["common_grid_selected_finalist"]
    cfg = context["cfg"]
    candidate = candidate_at_pairs(
        context["spaces"]["P_D"], selected, 65,
        reflector_electrodes=int(cfg["dms_topology"]["t1_reflector_electrodes"]),
    )

    normal = stage4a_evaluate(
        candidate, context["provider"], cfg, context["common_frequencies"], 50.0, 50.0,
    )
    assert normal["evaluation_status"] == "GEOMETRY_REJECTED"
    assert normal["geometry_valid"] is False
    assert normal["geometry_violations"]["resonator_0_pairs_upper"] == pytest.approx(65 / 60 - 1)

    probe_bounds = np.asarray(cfg["hybrid"]["resonator_bounds"], dtype=float).copy()
    probe_bounds[1, 1] = 75
    probe_geometry = hybrid_geometry(candidate, cfg, resonator_bounds=probe_bounds)
    assert probe_geometry["max_violation"] == 0.0
