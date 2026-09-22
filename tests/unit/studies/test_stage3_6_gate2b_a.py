import json
from pathlib import Path

import numpy as np

from sawopt.studies.convergence import normalize_convergence_config
from sawopt.studies.stage3_6_gate2b_a import (
    CONDITIONS,
    RELEASE_GROUP,
    SEEDS,
    _aggregate,
    _interaction,
    _stage_section,
    _transpose,
    run_termination_preflight,
)
from sawopt.io.config import load_experiment_config


ROOT = Path(__file__).resolve().parents[3]


def _cfg():
    return normalize_convergence_config(load_experiment_config(
        ROOT / "configs/studies/stage3_6_gate2b_a_asymmetric_impedance.yaml"
    ))


def _rows():
    rows = []
    for cid, zin, zout in CONDITIONS:
        for seed_index, seed in enumerate(SEEDS):
            primary = zin / 1000.0 + zout / 10000.0 + seed_index / 100000.0
            rows.append({
                "condition_id": cid, "zin_ohm": zin, "zout_ohm": zout,
                "seed": seed, "budget": 16000, "actual_unique_evaluations": 16000,
                "budget_complete": True, "feasible": False,
                "max_violation": primary, "sum_violation": 2 * primary,
                "objective": 1000 * primary, "worst_il_db": primary,
                "ripple_db": primary, "input_vswr": primary,
                "output_vswr": primary, "stopband_violation": primary,
                "fraction_of_budget_at_last_significant_improvement": .8,
                "elapsed_s": 1.0, "stop_reason": "requested_budget_reached",
                "grid_converged": False, "convergence_evidence_complete": False,
            })
    return rows


def test_stage_section_freezes_canonical_factorial_and_budget():
    section = _stage_section(_cfg())
    assert section["release_group"] == RELEASE_GROUP
    assert tuple(section["seeds"]) == SEEDS
    assert section["budget"] == 16000
    assert [item["id"] for item in section["conditions"]] == [item[0] for item in CONDITIONS]


def test_preflight_reaches_network_with_ordered_asymmetric_terminations():
    result = run_termination_preflight(_cfg())
    assert result["passed"]
    observations = result["conditions"]
    assert [(row["network_source_impedance_ohm"], row["network_load_impedance_ohm"]) for row in observations] == [(25.0, 50.0), (50.0, 25.0)]


def test_transpose_and_interaction_analysis_use_signed_deltas():
    rows = _rows()
    aggregates = _aggregate(rows)
    detail, summary = _transpose(rows)
    assert len(detail) == 9
    assert len(summary) == 3
    assert summary[0]["median_delta_asym_max_violation"] < 0
    interaction_rows, assessment = _interaction(aggregates)
    assert len(interaction_rows) == 9
    assert np.isfinite(assessment["max_absolute_residual"]["max_violation"])
    assert json.dumps(interaction_rows)
