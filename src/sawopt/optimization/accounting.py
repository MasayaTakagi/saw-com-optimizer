"""Shared checkpoint-lattice and evaluation-counter validation."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def _record_flag_is_true(value: Any) -> bool:
    return value is True or str(value).strip().lower() == "true"


def validate_checkpoint_lattice(
    rows: Sequence[Mapping[str, Any]],
    *,
    materials: Sequence[str],
    topologies: Sequence[str],
    seeds: Sequence[int],
    checkpoints: Sequence[int],
) -> dict[str, Any]:
    """Validate the full material/topology/seed/checkpoint accounting grid.

    This is the canonical Stage 3.8-compatible validator. Its key coercions,
    counter identities, final-checkpoint rule, and return fields preserve the
    historical R1 audit contract for compatibility callers.
    """
    axes = (tuple(map(str, materials)), tuple(map(str, topologies)),
            tuple(map(int, seeds)), tuple(map(int, checkpoints)))
    axes_unique = all(len(axis) == len(set(axis)) for axis in axes)
    expected_keys = {
        (material, topology, seed, checkpoint)
        for material in axes[0]
        for topology in axes[1]
        for seed in axes[2]
        for checkpoint in axes[3]
    }
    observed: list[tuple[str, str, int, int] | None] = []
    invalid_rows: list[dict[str, Any]] = []
    key_counts: dict[tuple[str, str, int, int], int] = {}
    required_flags = (
        "counter_identity_pass",
        "physics_partition_pass",
        "valid_physics_within_geometry_valid",
        "physics_attempt_identity_pass",
    )
    for index, row in enumerate(rows):
        try:
            key = (
                str(row["material"]), str(row["topology"]),
                int(row["seed"]), int(row["checkpoint_budget"]),
            )
        except (KeyError, TypeError, ValueError):
            observed.append(None)
            invalid_rows.append({"row": index, "reason": "missing or invalid run/checkpoint key"})
            continue
        observed.append(key)
        key_counts[key] = key_counts.get(key, 0) + 1
        failures = [name for name in required_flags
                    if not _record_flag_is_true(row.get(name))]
        try:
            unique = int(row["unique_decoded_evaluations"])
            rejected = int(row["geometry_rejections"])
            geometry_valid = int(row["geometry_valid_candidates"])
            valid_physics = int(row["valid_physics_evaluations"])
            physics_failures = int(row["physics_failures"])
            physics_attempted = int(row["physics_attempted_evaluations"])
            if unique != rejected + geometry_valid:
                failures.append("counter identity values disagree")
            if geometry_valid != valid_physics + physics_failures:
                failures.append("physics partition values disagree")
            if valid_physics > geometry_valid:
                failures.append("valid physics exceeds geometry-valid candidates")
            if physics_attempted != valid_physics + physics_failures:
                failures.append("physics attempt identity values disagree")
            if unique != key[3]:
                failures.append("checkpoint budget differs from unique evaluation count")
        except (KeyError, TypeError, ValueError):
            failures.append("missing or invalid numeric counter value")
        if failures:
            invalid_rows.append({"row": index, "key": list(key), "failures": failures})

    duplicate_keys = sorted((list(key) for key, count in key_counts.items() if count > 1))
    unexpected_keys = sorted((list(key) for key in key_counts if key not in expected_keys))
    present_keys = set(key_counts)
    missing_keys = sorted((list(key) for key in expected_keys - present_keys))
    expected_rows = len(expected_keys)
    run_keys = {(material, topology, seed) for material, topology, seed, _ in expected_keys}
    observed_run_checkpoint_counts = {
        key: sum(1 for observed_key in observed
                 if observed_key is not None and observed_key[:3] == key)
        for key in run_keys
    }
    complete_runs = all(
        observed_run_checkpoint_counts[key] == len(axes[3])
        and all((key[0], key[1], key[2], checkpoint) in present_keys for checkpoint in axes[3])
        for key in run_keys
    )
    final_checkpoint = max(axes[3]) if axes[3] else None
    final_checkpoint_rows = sum(
        key[3] == final_checkpoint and key_counts.get(key, 0) == 1
        for key in expected_keys
    ) if final_checkpoint is not None else 0
    passed = (
        axes_unique
        and len(rows) == expected_rows
        and len(observed) == len(rows)
        and not missing_keys
        and not duplicate_keys
        and not unexpected_keys
        and not invalid_rows
        and complete_runs
        and final_checkpoint_rows == len(run_keys)
    )
    return {
        "passed": passed,
        "expected_rows": expected_rows,
        "actual_rows": len(rows),
        "unique_rows": len(key_counts),
        "expected_seed_runs": len(run_keys),
        "seed_runs_with_complete_checkpoints": sum(
            observed_run_checkpoint_counts[key] == len(axes[3])
            and all((key[0], key[1], key[2], checkpoint) in present_keys for checkpoint in axes[3])
            for key in run_keys
        ),
        "checkpoints_per_seed_run": len(axes[3]),
        "checkpoint_budgets": list(axes[3]),
        "final_checkpoint_budget": final_checkpoint,
        "final_checkpoint_rows": final_checkpoint_rows,
        "missing_keys": missing_keys,
        "duplicate_keys": duplicate_keys,
        "unexpected_keys": unexpected_keys,
        "invalid_rows": invalid_rows,
    }


__all__ = ["validate_checkpoint_lattice"]
