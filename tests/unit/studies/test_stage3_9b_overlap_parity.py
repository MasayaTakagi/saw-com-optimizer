from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sawopt.io.config import load_experiment_config
from sawopt.studies.audits import stage3_9b_overlap_parity as parity
from sawopt.studies.audits.stage3_9b_overlap_parity import (
    CHECKPOINTS,
    COUNTER_FIELDS,
    SEEDS,
    TOPOLOGY,
    _compare_common_grid,
    _initializer_projection,
    _normalized_counters,
    _normalized_run_metadata,
    _read_frequency_grid,
    _array_sha256,
    _canonical_protocol_evidence,
    _config_protocol,
    _validate_grid_provenance_hashes,
    compare_values,
    validate_checkpoint_lattice,
)


ROOT = Path(__file__).resolve().parents[3]


def test_overlap_config_inherits_accepted_protocol_and_limits_only_budget_lattice():
    base = load_experiment_config(
        ROOT / "configs/studies/stage3_9b_mlit_t1_50ohm_budget_extension.yaml"
    )
    overlap = load_experiment_config(
        ROOT / "configs/studies/stage3_9b_mlit_t1_50ohm_overlap_parity.yaml"
    )
    b = base["dms_topology"]
    o = overlap["dms_topology"]
    assert overlap["study"]["revision"] == "stage3_9b_mlit_t1_50ohm_overlap_parity"
    assert o["selection"] == b["selection"] == {
        "materials": ["MLIT"], "topologies": ["T1_SYMMETRIC_5IDT"]
    }
    assert {k: v for k, v in o.items() if k not in {"budget", "checkpoints"}} == {
        k: v for k, v in b.items() if k not in {"budget", "checkpoints"}
    }
    assert o["budget"] == 8000
    assert o["checkpoints"] == list(CHECKPOINTS)
    assert b["budget"] == 16000
    assert b["checkpoints"] == list(range(2000, 16001, 2000))
    assert o["initial_population_seed_contract"] == b["initial_population_seed_contract"]
    assert o["initial_population_seed_contract"] == (
        "stage3_8c_r1_2_independent_rejection"
    )
    assert overlap["spec"] == base["spec"]
    assert overlap["constraints"] == base["constraints"]


def test_resolved_parity_protocol_pins_seed_contract_and_seed_values():
    cfg = load_experiment_config(
        ROOT / "configs/studies/stage3_9b_mlit_t1_50ohm_overlap_parity.yaml"
    )
    protocol = _config_protocol(cfg)
    assert protocol["initial_population_seed_contract"] == {
        "identifier": "stage3_8c_r1_2_independent_rejection",
        "namespace": "stage3_8c_r1_geometry_first_v1",
        "derivation_suffix": "r1_2_independent_rejection",
    }
    assert protocol["initial_sampling_seeds"] == {
        "MLIT/T1_SYMMETRIC_5IDT/20260917": 3938065196,
        "MLIT/T1_SYMMETRIC_5IDT/20260918": 1982837181,
    }


def test_historical_config_presence_does_not_change_snapshot_protocol_path(tmp_path, monkeypatch):
    canonical = tmp_path / "canonical"
    metadata = canonical / "metadata"
    metadata.mkdir(parents=True)
    legacy_config = tmp_path / "stage3_8c_r1_2_production.yaml"
    (metadata / "run_source_metadata.json").write_text(json.dumps({
        "source_config_path": str(legacy_config),
    }))
    calls = []

    def persisted_snapshot_check(run_dir, protocol):
        calls.append((run_dir, protocol))
        return ["persisted-snapshot-check"]

    monkeypatch.setattr(parity, "_compare_persisted_protocol", persisted_snapshot_check)
    absent = _canonical_protocol_evidence(canonical, {"budget": 8000})
    legacy_config.write_text(
        "study:\n  type: stage3_8c_r1_geometry_gate\nstage3_8c_r1:\n  budget: 8000\n",
        encoding="utf-8",
    )
    present = _canonical_protocol_evidence(canonical, {"budget": 8000})

    assert absent["differences"] == present["differences"] == ["persisted-snapshot-check"]
    assert absent["source_config_status"] == "absent"
    assert present["source_config_status"] == "present_optional_corroboration"
    assert len(calls) == 2
    assert all(call[0] == canonical for call in calls)


def test_grid_hash_validation_uses_source_normalized_bytes(tmp_path):
    source = tmp_path / "source.csv"
    run_copy = tmp_path / "run-copy.csv"
    source.write_bytes(b"frequency_hz\r\n100.0\r\n200.0\r\n")
    run_copy.write_bytes(b"frequency_hz\n100.0\n200.0\n")
    normalized_file_hash = hashlib.sha256(
        b"frequency_hz\n100.0\n200.0\n"
    ).hexdigest()
    assert _read_frequency_grid(source).tolist() == _read_frequency_grid(run_copy).tolist()
    assert _validate_grid_provenance_hashes(
        source, run_copy,
        source_metadata_hash=normalized_file_hash,
        run_metadata_hash=normalized_file_hash,
    ) == []

    run_copy.write_bytes(b"frequency_hz\n100.0\n201.0\n")
    assert _validate_grid_provenance_hashes(
        source, run_copy,
        source_metadata_hash=normalized_file_hash,
        run_metadata_hash=normalized_file_hash,
    ) == ["run common-grid copy does not match normalized source bytes"]

    assert _validate_grid_provenance_hashes(
        source, source,
        source_metadata_hash="wrong-source-hash",
        run_metadata_hash=normalized_file_hash,
    ) == ["configured common-grid source hash does not match its normalized metadata hash"]


def test_checkpoint_lattice_requires_exact_two_seed_four_checkpoint_cells():
    expected = {(seed, budget): object() for seed in SEEDS for budget in CHECKPOINTS}
    assert validate_checkpoint_lattice(expected) == []
    missing = dict(expected)
    missing.pop((SEEDS[0], CHECKPOINTS[0]))
    errors = validate_checkpoint_lattice(missing)
    assert errors and "missing" in errors[0]
    extra = dict(expected)
    extra[(999, 2000)] = object()
    errors = validate_checkpoint_lattice(extra)
    assert errors and "extra" in errors[0]


def test_decoded_design_and_control_state_require_exact_equality():
    baseline = {"design": {"wavelength_A_um": 5.1}, "population_size": 180, "counter": 2000}
    assert compare_values(baseline, baseline) == []
    for key, value in (("design", {"wavelength_A_um": 5.100000000000001}), ("population_size", 179), ("counter", 2001)):
        changed = dict(baseline)
        changed[key] = value
        assert compare_values(baseline, changed)


def test_metric_and_composite_objective_tolerances_are_predeclared():
    assert compare_values({"metrics": {"worst_il_db": 1.0}}, {"metrics": {"worst_il_db": 1.0 + 1e-13}}) == []
    assert compare_values({"metrics": {"worst_il_db": 1.0}}, {"metrics": {"worst_il_db": 1.0 + 1e-8}})
    assert compare_values({"objective": 1e9}, {"objective": 1e9 + 5e-4}) == []


def test_initializer_accounting_is_exact_but_timing_is_separate():
    baseline = {
        "initializer_method": "independent_uniform_rejection_v1",
        "initial_sampling_seed": 10,
        "requested_population_size": 180,
        "max_attempts": 10000,
        "max_attempts_exceeded": False,
        "total_candidate_draws": 181,
        "valid_accepted_candidates": 180,
        "geometry_valid_members": 180,
        "rejected_candidates": 0,
        "initial_sampling_draws": 181,
        "initial_sampling_geometry_rejections": 0,
        "initial_sampling_duplicate_rejections": 0,
        "initial_sampling_rejection_reason_counts": {"length": 0},
        "fixed_seed_count": 1,
        "random_initial_accepts": 179,
        "unique_population_count": 180,
        "variable_distributions": {"x": {"mean": 1.0}},
        "geometry_metric_distributions": {"length": {"mean": 1.0}},
        "random_member_variable_distributions": {"x": {"mean": 1.0}},
        "random_member_geometry_metric_distributions": {"length": {"mean": 1.0}},
        "population_generation_time_s": 0.01,
        "study_revision": "old",
        "distribution_validation_status": "PASS",
        "distribution_regression_passed": True,
    }
    revised = {
        **baseline,
        "population_generation_time_s": 99.0,
        "study_revision": "new",
        "distribution_validation_status": "SKIPPED_FINAL_CONFIRMATION",
        "independent_uniform_reference": {"diagnostic": "new implementation"},
        "integer_diversity_diagnostic_passed": True,
        "distribution_reference_check_passed": True,
    }
    assert compare_values(_initializer_projection(baseline), _initializer_projection(revised)) == []
    revised["initial_sampling_seed"] = 11
    assert compare_values(_initializer_projection(baseline), _initializer_projection(revised))


def test_historical_and_current_counter_container_names_normalize_exactly():
    counters = {field: 0 for field in COUNTER_FIELDS}
    counters.update({
        "objective_calls": 12,
        "canonical_candidates_seen": 12,
        "unique_decoded_evaluations": 10,
        "geometry_rejections": 2,
        "geometry_valid_candidates": 8,
        "valid_physics_evaluations": 8,
        "physics_attempted_evaluations": 8,
        "physics_failures": 0,
        "search_frequency_count": 1001,
    })
    old = {"r1_counters": counters, "evaluation_counters": {}}
    current = {"r1_counters": {}, "evaluation_counters": {**counters, "elapsed_s": 123.0}}
    assert _normalized_counters(old) == _normalized_counters(current)
    changed = {**current, "evaluation_counters": {**counters, "geometry_rejections": 3}}
    assert _normalized_counters(old) != _normalized_counters(changed)
    with pytest.raises(ValueError, match="missing required counter fields"):
        _normalized_counters({"evaluation_counters": {"unique_decoded_evaluations": 10}})


def test_historical_and_current_run_metadata_names_normalize_array_identity():
    grid = [10_000_000.0, 10_198_000.0]
    array_hash = _array_sha256(grid)
    old = {
        "budget": 8000,
        "common_validation_grid_count": 2,
        "common_validation_grid_id": array_hash,
        "common_validation_grid_sha256": array_hash,
        "initialization_policy": "independent_uniform_rejection_v1",
        "initializer_method": "independent_uniform_rejection_v1",
        "input_output_impedance_ohm": [50.0, 50.0],
        "resolved_search_frequency_count": 1001,
        "resolved_search_frequency_sha256": "search-array-hash",
        "seeds": list(SEEDS),
    }
    current = {
        "budget": 8000,
        "common_validation_grid_count": 2,
        "common_validation_grid_id": array_hash,
        # The modern field is a CSV byte hash and is intentionally not treated
        # as the normalized array identity.
        "common_validation_grid_sha256": "different-csv-byte-hash",
        "initializer_method": "independent_uniform_rejection_v1",
        "source_impedance_ohm": 50.0,
        "load_impedance_ohm": 50.0,
        "search_frequency_count": 1001,
        "search_frequency_sha256": "search-array-hash",
        "seeds": list(SEEDS),
    }
    old_normalized = _normalized_run_metadata(
        old, common_grid_count=len(grid), common_grid_array_sha256=array_hash,
    )
    current_normalized = _normalized_run_metadata(
        current, common_grid_count=len(grid), common_grid_array_sha256=array_hash,
    )
    assert old_normalized == current_normalized
    changed = {**current, "load_impedance_ohm": 51.0}
    assert _normalized_run_metadata(
        changed, common_grid_count=len(grid), common_grid_array_sha256=array_hash,
    ) != old_normalized
    with pytest.raises(ValueError, match="common-grid ID"):
        _normalized_run_metadata(
            current, common_grid_count=len(grid), common_grid_array_sha256="wrong-array-hash",
        )


def test_historical_and_current_common_grid_artifact_names_compare_semantically(tmp_path):
    old_dir = tmp_path / "old" / "seed"
    current_dir = tmp_path / "current" / "seed"
    old_dir.mkdir(parents=True)
    current_dir.mkdir(parents=True)
    design = {"wavelength_A_um": 5.1, "pairs_A": 10}
    candidate = {
        "evaluation_status": "PHYSICS_EVALUATED",
        "failure_stage": None,
        "geometry_valid": True,
        "geometry_dimensions": {"length_um": 100.0},
        "geometry_violations": {},
        "geometry_max_violation": 0.0,
        "metrics": {"worst_il_db": 1.0},
        "violations": {"stop_1": 0.2},
        "filter_metrics_available": True,
        "filter_feasible": False,
        "feasible": False,
        "max_violation": 0.2,
        "sum_violation": 0.2,
        "objective": 1.0,
        "objective_parts": {"primary": 0.2, "secondary": 0.0},
        "design": design,
        "topology": TOPOLOGY,
        "source_impedance_ohm": 50.0,
        "load_impedance_ohm": 50.0,
        "search_source_rank_key": [0, 0.2, 0.0, 1.0],
    }
    grid_id = "common-grid-id"
    old_payload = {
        "common_validation_grid_id": grid_id,
        "search_unique_evaluations": 8000,
        "selected": candidate,
        "validated_finalists": [candidate],
    }
    current_payload = {
        "common_validation_grid_id": grid_id,
        "selected": candidate,
        "validated_finalists": [candidate],
    }
    (old_dir / "final_common_grid_selection.json").write_text(json.dumps(old_payload))
    (current_dir / "common_grid_selection.json").write_text(json.dumps(current_payload))
    assert _compare_common_grid(old_dir, current_dir, expected_grid_id=grid_id) == []
    mutated = {**candidate, "metrics": {"worst_il_db": 1.01}}
    (current_dir / "common_grid_selection.json").write_text(json.dumps({
        **current_payload, "selected": mutated, "validated_finalists": [mutated],
    }))
    assert _compare_common_grid(old_dir, current_dir, expected_grid_id=grid_id)
