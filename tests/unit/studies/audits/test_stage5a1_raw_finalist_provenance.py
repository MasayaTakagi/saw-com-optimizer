"""Synthetic raw Stage 4C finalist replay; no physics evaluation."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from sawopt.optimization.selection import GeometryFirstComparator
from sawopt.reporting.candidate_integrity import validated_hybrid_rank_key
from sawopt.studies.audits.stage5a1_raw_finalist_provenance import (
    audit_checkpoint, audit_raw_run, main,
)


ROOT = (Path(__file__).resolve().parents[4] /
        "reports/experiment_reviews/stage4c/20261006_124153_ed50ba")


def _compact():
    return json.loads((ROOT / "cells/P_D/20261007_result.json").read_text(encoding="utf-8"))


def _fixture():
    compact = _compact()
    original = compact["common_grid_selected_finalist"]
    finalists = []
    # All other synthetic candidates have strictly worse comparator keys.
    for position in range(1, 17):
        candidate = copy.deepcopy(original)
        candidate["search_source_rank"] = position
        candidate["candidate_vector"][0] += position * 1e-6
        if position != 5:
            candidate["violations"]["stop_2"] += 0.1
            candidate["max_violation"] += 0.1
            candidate["sum_violation"] += 0.1
        else:
            candidate["candidate_vector"] = copy.deepcopy(original["candidate_vector"])
        finalists.append(candidate)
    chosen = copy.deepcopy(finalists[4])
    chosen.pop("search_source_rank")
    compact["common_grid_selected_finalist"] = chosen
    compact["checkpoint_summaries"][-1].update({
        "selected_max_violation": chosen["max_violation"],
        "selected_sum_violation": chosen["sum_violation"],
        "selected_worst_il_db": chosen["metrics"]["worst_il_db"],
        "selected_ripple_db": chosen["metrics"]["ripple_db"],
    })
    record = {
        "topology": "P_D", "seed": 20261007, "checkpoint_budget": 96000,
        "computation_fingerprint": compact["computation_fingerprint"],
        "common_validation_grid_id": compact["common_validation_grid_id"],
        "validated_finalists": finalists,
        "common_grid_selected_finalist": chosen,
        "search_incumbent": compact["search_incumbent"],
        "counters": compact["counters"],
        "lshade_summary": {"generations": compact["checkpoint_summaries"][-1]["generations"]},
    }
    return record, compact


def _audit(row, compact):
    return audit_checkpoint(row, topology="P_D", seed=20261007,
                            budget=96000, index=7,
                            fingerprint=compact["computation_fingerprint"], compact=compact)


def test_synthetic_16_member_terminal_pool_replays_exact_selected_candidate():
    row, compact = _fixture()
    assert _audit(row, compact) == []


def test_worse_candidate_selected_fails_canonical_min():
    row, compact = _fixture()
    row["common_grid_selected_finalist"] = copy.deepcopy(row["validated_finalists"][0])
    row["common_grid_selected_finalist"].pop("search_source_rank")
    assert "selected.canonical_min" in _audit(row, compact)


def test_corrupted_source_rank_lattice_is_rejected():
    row, compact = _fixture()
    row["validated_finalists"][3]["search_source_rank"] = 1
    issues = _audit(row, compact)
    assert "finalist.4.source_rank" in issues


def test_duplicate_canonical_vector_is_rejected():
    row, compact = _fixture()
    row["validated_finalists"][2]["candidate_vector"] = copy.deepcopy(
        row["validated_finalists"][0]["candidate_vector"]
    )
    assert "finalists.unique_vectors" in _audit(row, compact)


def test_full_pool_count_required():
    row, compact = _fixture()
    row["validated_finalists"].pop()
    assert "finalists.count" in _audit(row, compact)


def test_invalid_violation_fails_closed():
    row, compact = _fixture()
    row["validated_finalists"][2]["violations"]["stop_1"] = float("nan")
    assert "finalist.3.physics_integrity" in _audit(row, compact)


def test_terminal_compact_mismatch_fails():
    row, compact = _fixture()
    compact["search_incumbent"] = None
    assert "terminal.search_incumbent" in _audit(row, compact)


def test_missing_raw_run_never_claims_success(tmp_path):
    result = audit_raw_run(tmp_path / "missing-run", ROOT)
    assert result["status"] == "INCOMPLETE"
    assert result["checkpoints_expected"] == 80
    assert result["checkpoints_checked"] == 0
    assert main(["--optimizer-run", str(tmp_path / "missing-run"),
                 "--review-package", str(ROOT)]) == 1


def test_rank_key_agrees_with_geometry_comparator_after_constant_prefix():
    row, _compact = _fixture()
    comparator = GeometryFirstComparator()
    for candidate in row["validated_finalists"]:
        assert comparator.rank_key(candidate)[2:] == validated_hybrid_rank_key(candidate)
