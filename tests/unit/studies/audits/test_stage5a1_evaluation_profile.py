import csv
import json
from pathlib import Path

import numpy as np
import pytest

from sawopt.studies.audits.stage5a1_evaluation_profile import (
    assert_profile_equivalence,
    assert_saved_finalist_equivalence,
    capture_stage4a_reference,
    profile_decomposed_evaluation,
    summarize_seconds,
    summarize_samples,
    _validate_grids,
    write_profile_outputs,
)
from sawopt.studies.hybrid_stage4c import load_stage4c_context


ROOT = Path(__file__).resolve().parents[4]
STAGE4C_REVIEW = ROOT / "reports/experiment_reviews/stage4c/20261006_124153_ed50ba"
TIMING_FIELDS = (
    "A_s", "B_s", "C_s", "D_s", "E_s", "F_s", "sum_A_to_F_s",
    "G_s", "G_stage4a_call_s", "G_decode_s",
)


def test_timing_summary_uses_median_range_and_median_absolute_deviation():
    summary = summarize_seconds([1.0, 2.0, 3.0, 4.0, 100.0])

    assert summary == {
        "n": 5,
        "median_s": 3.0,
        "min_s": 1.0,
        "max_s": 100.0,
        "mad_s": 1.0,
    }
    with pytest.raises(ValueError, match="non-empty"):
        summarize_seconds([])
    with pytest.raises(ValueError, match="finite non-negative"):
        summarize_seconds([0.1, float("nan")])


def test_sample_summaries_and_json_csv_outputs_are_reproducible(tmp_path):
    samples = []
    for repetition, elapsed in enumerate((1.0, 3.0, 2.0), start=1):
        row = {"topology": "P_D", "seed": 20261007, "grid": "search",
               "repetition": repetition}
        row.update({field: elapsed for field in TIMING_FIELDS})
        samples.append(row)

    summaries = summarize_samples(samples)
    stage_a = next(row for row in summaries if row["stage"] == "A_s")
    assert stage_a == {
        "topology": "P_D", "seed": 20261007, "grid": "search",
        "stage": "A_s", **summarize_seconds([1.0, 3.0, 2.0]),
    }

    metadata = {"source_sha": "abc123", "environment": {"python": "3.12"}}
    parity = [{"topology": "P_D", "seed": 20261007, "grid": "search",
               "status": "PASS", "maximum_absolute_difference": 0.0}]
    csv_path, json_path = write_profile_outputs(
        tmp_path / "profile", metadata, samples, parity,
    )

    assert b"\r" not in csv_path.read_bytes()
    with csv_path.open(newline="", encoding="utf-8") as stream:
        saved_samples = list(csv.DictReader(stream))
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(saved_samples) == 3
    assert saved_samples[0]["G_s"] == "1.0"
    assert saved["sample_count"] == 3
    assert saved["source_sha"] == "abc123"
    assert saved["parity_results"] == parity
    assert saved["summaries"] == summaries


def test_saved_finalist_comparison_checks_feasibility_and_filter_metrics():
    record = {
        "evaluation_status": "PHYSICS_EVALUATED", "feasible": False,
        "metrics": {"worst_il_db": 3.0, "stop_attenuation_db": [20.0, 30.0]},
        "violations": {"il": 0.1, "stop_0": 0.2},
        "max_violation": 0.2, "sum_violation": 0.3, "objective": 1.2,
    }
    assert all(value == 0.0 for value in assert_saved_finalist_equivalence(
        record, record, rtol=1e-10, atol=1e-12,
    ).values())

    changed = {**record, "metrics": {**record["metrics"], "worst_il_db": 3.1}}
    with pytest.raises(AssertionError, match="saved finalist metrics.worst_il_db"):
        assert_saved_finalist_equivalence(changed, record, rtol=1e-10, atol=1e-12)


def test_reference_grid_validation_checks_array_identity_and_metadata_sha_separately():
    context = load_stage4c_context("configs/studies/hybrid_stage4c_confirmatory.yaml")

    identities = _validate_grids(context)

    assert identities["search"]["frequency_count"] == 1001
    assert identities["search"]["sha256"] == "212dd2b0b71ddeffb7a8865937d132ee596870f25c989ac7d90c5dab6fd7faa0"
    assert identities["common"]["frequency_count"] == 9113
    assert identities["common"]["grid_id"] == "2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f"
    assert identities["common"]["array_sha256"] == identities["common"]["grid_id"]
    assert identities["common"]["sha256"] == "54c1daf67dd2bb9242f95e638d7bd801db536acc2c7d6f00c1f62a788bead554"

    mismatched = {**context, "common_grid_id": "wrong-grid"}
    with pytest.raises(ValueError, match="common-validation-grid identity"):
        _validate_grids(mismatched)


@pytest.mark.parametrize("topology,seed", [("P_D", 20261007), ("D_P", 20261007)])
def test_decomposed_profile_matches_normal_stage4a_evaluation(topology, seed):
    context = load_stage4c_context("configs/studies/hybrid_stage4c_confirmatory.yaml")
    record_path = STAGE4C_REVIEW / "cells" / topology / f"{seed}_result.json"
    saved = json.loads(record_path.read_text(encoding="utf-8"))
    finalist = saved["common_grid_selected_finalist"]
    vector = finalist["candidate_vector"]
    frequencies = context["search_frequencies"][
        np.linspace(0, len(context["search_frequencies"]) - 1, 9).astype(int)
    ]

    decomposed = profile_decomposed_evaluation(vector, topology, context, frequencies)
    reference = capture_stage4a_reference(vector, topology, context, frequencies)
    parity = context["cfg"]["hybrid"]["parity"]
    differences = assert_profile_equivalence(
        decomposed, reference, rtol=parity["rtol"], atol=parity["atol"],
    )

    assert decomposed["record"]["evaluation_status"] == "PHYSICS_EVALUATED"
    assert reference["record"]["evaluation_status"] == "PHYSICS_EVALUATED"
    assert decomposed["record"]["feasible"] is reference["record"]["feasible"]
    assert all(value == 0.0 for value in differences.values())
    assert all(decomposed["stage_seconds"][f"{stage}_s"] >= 0 for stage in "ABCDEF")
