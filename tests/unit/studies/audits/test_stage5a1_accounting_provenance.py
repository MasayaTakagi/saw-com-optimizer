"""Stage 5A-1 saved-record accounting, corruption and provenance checks."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sawopt.studies.audits.stage5a1_integrity import audit_cell, audit_package


REVIEW = (Path(__file__).resolve().parents[4] /
          "reports/experiment_reviews/stage4c/20261006_124153_ed50ba")


def _saved():
    return json.loads((REVIEW / "cells/P_D/20261007_result.json").read_text(encoding="utf-8"))


def _check(record):
    return audit_cell(record, topology="P_D", seed=20261007,
                      source_commit_sha=record["source_commit_sha"],
                      fingerprint=record["computation_fingerprint"])


def test_frozen_review_package_all_ten_cells_read_only_pass():
    report = audit_package(REVIEW)
    assert report["status"] == "PASS"
    assert report["cells_checked"] == 10
    assert report["failed_checks"] == 0
    assert all(row["status"] == "PASS" for row in report["cells"])
    limitations = " ".join(report["limitations"])
    assert "16-member" in limitations and "cache keys" in limitations


@pytest.mark.parametrize(("section", "field", "delta", "error"), [
    ("initialization", "candidate_draws", 1, "initializer.partition"),
    ("initialization", "initial_sampling_seed", 1, "initializer.seed"),
    ("counters", "cache_hits", 1, "cache.proposals"),
    ("counters", "search_frequency_points", 1, "search.points"),
    ("counters", "validation_frequency_points", 1, "validation.points"),
    ("counters", "geometry_valid_candidates", 1, "search.partition"),
    ("counters", "raw_offspring_count", 1, "cache.offspring"),
    ("counters", "generations", 1, "optimizer.generations"),
    ("runtime", "cell_wall_time_s", -2000, "runtime.partition"),
])
def test_mutated_accounting_fails_closed(section, field, delta, error):
    record = copy.deepcopy(_saved())
    record[section][field] += delta
    result = _check(record)
    assert result["status"] == "FAIL"
    assert error in result["errors"]


def test_corrupted_final_checkpoint_detected():
    record = copy.deepcopy(_saved())
    record["checkpoint_summaries"][-1]["selected_max_violation"] += 0.01
    result = _check(record)
    assert "checkpoint.final.max_violation" in result["errors"]


def test_corrupted_common_grid_candidate_detected():
    record = copy.deepcopy(_saved())
    record["common_grid_selected_finalist"]["violations"]["stop_1"] = 7.0
    result = _check(record)
    assert "candidate.common" in result["errors"]


def test_missing_evidence_does_not_pass():
    record = copy.deepcopy(_saved())
    del record["counters"]["validation_evaluations"]
    assert _check(record)["status"] == "FAIL"
