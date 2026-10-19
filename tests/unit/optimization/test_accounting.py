import pytest

from sawopt.optimization.accounting import validate_checkpoint_lattice


def test_checkpoint_lattice_rejects_negative_evaluation_counter():
    row = {
        "material": "M0",
        "topology": "T0",
        "seed": 1,
        "checkpoint_budget": 8,
        "counter_identity_pass": True,
        "physics_partition_pass": True,
        "valid_physics_within_geometry_valid": True,
        "physics_attempt_identity_pass": True,
        "unique_decoded_evaluations": 8,
        "geometry_rejections": -1,
        "geometry_valid_candidates": 9,
        "valid_physics_evaluations": 9,
        "physics_failures": 0,
        "physics_attempted_evaluations": 9,
    }

    result = validate_checkpoint_lattice(
        [row], materials=["M0"], topologies=["T0"], seeds=[1], checkpoints=[8],
    )

    assert result["passed"] is False
    assert result["invalid_rows"][0]["failures"] == [
        "geometry_rejections must be non-negative",
    ]


@pytest.mark.parametrize("invalid_counter", [1.5, True])
def test_checkpoint_lattice_rejects_non_integer_counters(invalid_counter):
    row = {
        "material": "M0",
        "topology": "T0",
        "seed": 1,
        "checkpoint_budget": 8,
        "counter_identity_pass": True,
        "physics_partition_pass": True,
        "valid_physics_within_geometry_valid": True,
        "physics_attempt_identity_pass": True,
        "unique_decoded_evaluations": 8,
        "geometry_rejections": invalid_counter,
        "geometry_valid_candidates": 7,
        "valid_physics_evaluations": 7,
        "physics_failures": 0,
        "physics_attempted_evaluations": 7,
    }

    result = validate_checkpoint_lattice(
        [row], materials=["M0"], topologies=["T0"], seeds=[1], checkpoints=[8],
    )

    assert result["passed"] is False
    assert result["invalid_rows"][0]["failures"] == [
        "missing or invalid numeric counter value",
    ]
