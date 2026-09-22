import json

import numpy as np

from sawopt.io.config import load_experiment_config
from sawopt.studies.convergence import normalize_convergence_config
from sawopt.studies.stage3_6_gate2b_b import (
    CHECKPOINTS,
    CONDITIONS,
    SEEDS,
    _interaction_analysis,
    _stage_section,
    _transpose_analysis,
)


def _cfg():
    return normalize_convergence_config(load_experiment_config(
        "configs/studies/stage3_6_gate2b_b_asymmetric_impedance.yaml"
    ))


def _row(cid, seed, value):
    return {
        "condition_id": cid,
        "seed": seed,
        "zin_ohm": 50.0,
        "zout_ohm": 75.0,
        "max_violation": value,
        "sum_violation": value,
        "objective": value,
        "worst_il_db": value,
        "ripple_db": value,
        "input_vswr": value,
        "output_vswr": value,
        "stopband_violation": value,
    }


def test_stage_section_freezes_matrix_seeds_budget_and_checkpoints():
    section = _stage_section(_cfg())
    assert [item["id"] for item in section["conditions"]] == [
        item[0] for item in CONDITIONS
    ]
    assert tuple(section["seeds"]) == SEEDS
    assert section["budget"] == 32000
    assert tuple(section["checkpoints"]) == CHECKPOINTS


def test_transpose_analysis_reports_signed_seedwise_deltas():
    rows = []
    for cid, value in (("B6", 1.0), ("B7", 2.0), ("B8", 3.0), ("B9", 4.0)):
        rows.extend(_row(cid, seed, value + seed / 1e9) for seed in SEEDS)
    output = _transpose_analysis(rows)
    detail = [row for row in output if isinstance(row["seed"], int)]
    assert len(detail) == 6
    assert all(row["delta_transpose_max_violation"] < 0 for row in detail[:3])


def test_interaction_analysis_uses_75_ohm_center_and_signed_cross_differences():
    aggregates = []
    for cid, zin, zout in CONDITIONS:
        primary = zin / 100.0 + zout / 1000.0
        row = {"condition_id": cid, "zin_ohm": zin, "zout_ohm": zout}
        for metric in (
            "max_violation",
            "sum_violation",
            "objective",
            "worst_il_db",
            "ripple_db",
            "input_vswr",
            "output_vswr",
            "stopband_violation",
        ):
            row[f"median_{metric}"] = primary
        aggregates.append(row)
    rows, assessment = _interaction_analysis(aggregates)
    assert [row["condition_id"] for row in rows] == ["B6", "B7", "B3", "B8", "B9"]
    assert assessment["center"] == "B3 (75/75)"
    assert np.isfinite(assessment["residuals"]["50_block"]["max_violation"])
    assert json.dumps(rows)
