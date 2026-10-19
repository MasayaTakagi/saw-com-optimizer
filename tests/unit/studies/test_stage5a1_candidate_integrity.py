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
