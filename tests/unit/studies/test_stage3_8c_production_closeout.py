from __future__ import annotations

from sawopt.optimization.accounting import validate_checkpoint_lattice
from sawopt.studies.stage3_8c_r1_geometry_gate import _audit_counter_accounting_rows


MATERIALS = ("M0", "MLIT")
TOPOLOGIES = ("T0", "T1", "T2")
SEEDS = (20260917, 20260918)
CHECKPOINTS = (2000, 4000, 6000, 8000)


def _valid_counter_rows():
    rows = []
    for material in MATERIALS:
        for topology in TOPOLOGIES:
            for seed in SEEDS:
                for checkpoint in CHECKPOINTS:
                    rows.append({
                        "material": material,
                        "topology": topology,
                        "seed": seed,
                        "checkpoint_budget": checkpoint,
                        "unique_decoded_evaluations": checkpoint,
                        "geometry_rejections": 2,
                        "geometry_valid_candidates": checkpoint - 2,
                        "valid_physics_evaluations": checkpoint - 2,
                        "physics_failures": 0,
                        "physics_attempted_evaluations": checkpoint - 2,
                        "counter_identity_pass": True,
                        "physics_partition_pass": True,
                        "valid_physics_within_geometry_valid": True,
                        "physics_attempt_identity_pass": True,
                    })
    return rows


def _audit(rows):
    return _audit_counter_accounting_rows(
        rows, materials=MATERIALS, topologies=TOPOLOGIES,
        seeds=SEEDS, checkpoints=CHECKPOINTS,
    )


def test_complete_48_checkpoint_rows_pass_and_expected_count_is_derived():
    result = _audit(_valid_counter_rows())

    assert result["passed"] is True
    assert result["expected_rows"] == 48
    assert result["actual_rows"] == 48
    assert result["expected_seed_runs"] == 12
    assert result["seed_runs_with_complete_checkpoints"] == 12
    assert result["final_checkpoint_rows"] == 12


def test_historical_checkpoint_audit_is_a_compatibility_wrapper():
    rows = _valid_counter_rows()
    shared = validate_checkpoint_lattice(
        rows, materials=MATERIALS, topologies=TOPOLOGIES,
        seeds=SEEDS, checkpoints=CHECKPOINTS,
    )
    assert _audit(rows) == shared


def test_legacy_12_run_count_cannot_pass_as_checkpoint_row_count():
    result = _audit(_valid_counter_rows())

    assert result["expected_rows"] != result["expected_seed_runs"]
    assert result["expected_rows"] == result["actual_rows"] == 48
    assert result["passed"] is True


def test_missing_checkpoint_fails_even_when_all_remaining_rows_pass_invariants():
    rows = _valid_counter_rows()
    rows.pop(0)

    result = _audit(rows)

    assert result["passed"] is False
    assert result["actual_rows"] == 47
    assert result["missing_keys"]
    assert result["seed_runs_with_complete_checkpoints"] == 11


def test_duplicate_checkpoint_fails_even_when_total_rows_exceeds_expected():
    rows = _valid_counter_rows()
    rows.append(dict(rows[0]))

    result = _audit(rows)

    assert result["passed"] is False
    assert result["actual_rows"] == 49
    assert result["duplicate_keys"]


def test_any_counter_invariant_failure_fails_the_gate():
    rows = _valid_counter_rows()
    rows[9]["physics_attempt_identity_pass"] = False

    result = _audit(rows)

    assert result["passed"] is False
    assert result["invalid_rows"]
    assert "physics_attempt_identity_pass" in result["invalid_rows"][0]["failures"]


def test_numeric_counter_invariant_is_rechecked_instead_of_trusting_flag():
    rows = _valid_counter_rows()
    rows[0]["physics_attempted_evaluations"] += 1

    result = _audit(rows)

    assert result["passed"] is False
    assert "physics attempt identity values disagree" in result["invalid_rows"][0]["failures"]


def test_final_checkpoint_row_is_mandatory_for_every_seed_run():
    rows = [row for row in _valid_counter_rows() if int(row["checkpoint_budget"]) != 8000]

    result = _audit(rows)

    assert result["passed"] is False
    assert result["final_checkpoint_rows"] == 0
    assert result["seed_runs_with_complete_checkpoints"] == 0
