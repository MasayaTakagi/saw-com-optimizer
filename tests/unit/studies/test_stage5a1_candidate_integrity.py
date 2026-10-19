"""Full Stage 4C candidate ranking must fail closed on corrupt records."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sawopt.reporting.candidate_integrity import validated_hybrid_rank_key
from sawopt.reporting.hybrid_stage4c import _score, _winner
from sawopt.studies.hybrid_stage4c import SEEDS, TOPOLOGIES


DATA = (Path(__file__).resolve().parents[3] /
        "reports/experiment_reviews/stage4c/20261006_124153_ed50ba/cells")


def _saved_candidate(topology="P_D", seed=20261007, field="common_grid_selected_finalist"):
    path = DATA / topology / f"{seed}_result.json"
    return json.loads(path.read_text(encoding="utf-8"))[field]


@pytest.mark.parametrize("field", ("search_incumbent", "common_grid_selected_finalist"))
def test_all_frozen_stage4c_candidates_are_strictly_rankable(field):
    for topology in TOPOLOGIES:
        for seed in SEEDS:
            saved = _saved_candidate(topology, seed, field)
            assert validated_hybrid_rank_key(saved) == _score(saved)


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_status", "physics_failed", "string_false", "contradictory_feasible",
        "missing_violation", "nonfinite_violation", "negative_violation",
        "inconsistent_max", "inconsistent_sum", "nonfinite_il",
        "missing_geometry", "contradictory_geometry", "nonfinite_geometry",
        "failure_stage",
    ),
)
def test_corrupt_saved_candidate_cannot_enter_report_ranking(mutation):
    candidate = copy.deepcopy(_saved_candidate())
    if mutation == "missing_status":
        candidate.pop("evaluation_status")
    elif mutation == "physics_failed":
        candidate["evaluation_status"] = "PHYSICS_FAILED"
    elif mutation == "string_false":
        candidate["feasible"] = "false"
    elif mutation == "contradictory_feasible":
        candidate["feasible"] = True
    elif mutation == "missing_violation":
        candidate["violations"].pop("stop_1")
    elif mutation == "nonfinite_violation":
        candidate["violations"]["stop_1"] = float("nan")
    elif mutation == "negative_violation":
        candidate["violations"]["stop_1"] = -1.0
    elif mutation == "inconsistent_max":
        candidate["max_violation"] *= 0.5
    elif mutation == "inconsistent_sum":
        candidate["sum_violation"] += 1.0
    elif mutation == "nonfinite_il":
        candidate["metrics"]["worst_il_db"] = float("inf")
    elif mutation == "missing_geometry":
        candidate.pop("geometry_violations")
    elif mutation == "contradictory_geometry":
        candidate["geometry_max_violation"] = 0.1
        candidate["geometry_violations"]["combined_die_length"] = 0.1
    elif mutation == "nonfinite_geometry":
        candidate["geometry_violations"]["combined_die_length"] = float("nan")
    elif mutation == "failure_stage":
        candidate["failure_stage"] = "fake_error"
    assert validated_hybrid_rank_key(candidate) is None
    assert _score(candidate) is None
    assert _winner(candidate, _saved_candidate("D_P")) == "INDETERMINATE"


def test_invalid_pair_blocks_scientific_equivalence_classification():
    from sawopt.reporting.hybrid_stage4c import classify_stage4c, paired_comparisons

    cells = []
    checkpoints = []
    for seed in SEEDS:
        for topology in TOPOLOGIES:
            finalist = _saved_candidate(topology, seed)
            # Make finite, mutually equivalent sparse rank projections.
            finalist = dict(finalist)
            finalist["max_violation"] = 0.1
            finalist["sum_violation"] = 1.0
            finalist["violations"] = {
                "il": 0.1, "ripple": 0.1, "input_vswr": 0.1,
                "output_vswr": 0.1, "stop_0": 0.1, "stop_1": 0.1,
                "stop_2": 0.1, "stop_3": 0.3,
            }
            # This is deliberately inconsistent: one reported 0.3 > max 0.1.
            cells.append({
                "topology": topology, "seed": seed, "status": "COMPLETED",
                "common_grid_selected_finalist": finalist,
            })
            for checkpoint in (64000, 80000, 96000):
                checkpoints.append({
                    "topology": topology, "seed": seed, "checkpoint_budget": checkpoint,
                    "selected_feasible": False,
                    "selected_max_violation": 0.1,
                    "selected_sum_violation": 1.0,
                    "selected_worst_il_db": 4.0,
                    "selected_ripple_db": 1.0,
                    "significant_improvement_80k_to_96k": False,
                    "maturity_classification": (
                        "MATURE" if checkpoint == 96000 else "NOT_TERMINAL"
                    ),
                })
    pairs = paired_comparisons(cells)
    assert all(pair["lexicographic_winner"] == "INDETERMINATE" for pair in pairs)
    result = classify_stage4c(cells, checkpoints, pairs)
    assert result["terminal_ranking_complete"] is False
    assert result["classification"] == "STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED"
