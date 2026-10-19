"""Read-only accounting/provenance audit for the frozen Stage 4C export.

The compact export omits raw checkpoints, canonical cache keys and the full
validation pools. Passing these checks never implies replay of those objects.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from ...reporting.candidate_integrity import validated_hybrid_rank_key
from ..hybrid_stage4c import (
    BUDGET, CHECKPOINTS, COMMON_GRID_ID, COMMON_GRID_SHA256, FINALIST_COUNT,
    SEARCH_GRID_SHA256, SEEDS, TOPOLOGIES,
)

SEARCH_POINTS = 1001
COMMON_POINTS = 9113
INITIAL_POPULATION = 234
LIMITATIONS = (
    "Full 16-member common-grid finalist pools and source ranks are not exported",
    "Canonical cache keys, full population, RNG state and raw checkpoints are not exported",
    "Candidate projections omit per-record grid identities; only parent field and protocol give scope",
    "COM/network spectra are not rerun from the compact records",
)


def _nonnegative_int(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("nonnegative integer required")
    return value


def _duration(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("numeric duration required")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError("finite nonnegative duration required")
    return result


def _sampling_seed(seed: int, topology: str) -> int:
    payload = f"stage4b-v1/{seed}/MLIT/{topology}/initial_population"
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big") % 2**32


def audit_cell(cell: Mapping[str, Any], *, topology: str, seed: int,
               source_commit_sha: str, fingerprint: str) -> dict[str, Any]:
    """Check one saved Stage 4C cell using only its persisted evidence."""
    errors: list[str] = []

    def check(label: str, condition: bool) -> None:
        if not condition:
            errors.append(label)

    try:
        check("identity", cell["topology"] == topology and cell["seed"] == seed
              and cell["source_commit_sha"] == source_commit_sha
              and cell["computation_fingerprint"] == fingerprint
              and cell["common_validation_grid_id"] == COMMON_GRID_ID
              and cell["status"] == "COMPLETED" and cell["mode"] == "production")
        check("protocol", cell["budget"] == BUDGET
              and cell["population_schedule_terminal_budget"] == BUDGET
              and cell["dimension"] == 13 and cell["initial_population"] == INITIAL_POPULATION
              and cell["cold_start"] is True and cell["warm_start"] is False
              and cell["parent_transfer"] is False and cell["topology_transfer"] is False
              and cell["historical_population_injection"] is False)
        init = cell["initialization"]
        draws = _nonnegative_int(init["candidate_draws"])
        accepted = _nonnegative_int(init["accepted_population_size"])
        rejects = _nonnegative_int(init["geometry_rejections"])
        duplicates = _nonnegative_int(init["duplicate_rejections"])
        check("initializer.partition", draws == accepted + rejects + duplicates)
        check("initializer.size", accepted == INITIAL_POPULATION
              and init["requested_population_size"] == INITIAL_POPULATION)
        check("initializer.seed", init["initial_sampling_seed"] == _sampling_seed(seed, topology)
              and init["topology"] == topology and init["seed"] == seed)
        check("initializer.policy", init["method"] == "independent_uniform_rejection_v1"
              and init["historical_seed_count"] == 0 and init["warm_start"] is False
              and init["parent_transfer"] is False and init["topology_transfer"] is False)

        c = cell["counters"]
        cache = cell["cache_statistics"]
        unique, geometry, valid = (_nonnegative_int(c[k]) for k in (
            "unique_decoded_evaluations", "geometry_rejections", "geometry_valid_candidates"))
        successful, failed, attempted = (_nonnegative_int(c[k]) for k in (
            "valid_physics_evaluations", "physics_failures", "physics_attempted_evaluations"))
        hits, proposals, duplicates = (_nonnegative_int(c[k]) for k in (
            "cache_hits", "objective_proposals", "duplicate_proposals"))
        validations = _nonnegative_int(c["validation_evaluations"])
        failed_validations = _nonnegative_int(c["validation_physics_failures"])
        check("search.budget", unique == BUDGET and cell["unique_evaluations"] == unique)
        check("search.partition", unique == geometry + valid
              and valid == successful + failed == attempted)
        check("search.points", c["search_frequency_points"] == successful * SEARCH_POINTS)
        check("cache.proposals", proposals == unique + hits)
        check("cache.duplicates", duplicates == hits
              and cache["duplicate_count"] == duplicates and cache["cache_hits"] == hits
              and cache["proposals_total"] == proposals)
        check("cache.offspring", c["raw_offspring_count"] + INITIAL_POPULATION == proposals
              and cache["raw_offspring_count"] == c["raw_offspring_count"])
        check("cache.rates", proposals > 0
              and math.isclose(cache["cache_hit_rate"], hits / proposals, abs_tol=1e-12)
              and math.isclose(cache["duplicate_rate"], duplicates / proposals, abs_tol=1e-12))
        check("optimizer.generations", c["generations"] + INITIAL_POPULATION == unique
              and c["initial_population"] == INITIAL_POPULATION
              and c["population_size"] == 4)
        check("optimizer.population_schedule",
              c["population_schedule_identifier"] == "lshade_linear_population_v1"
              and c["population_schedule_terminal_budget"] == BUDGET)
        check("validation.count", validations == len(CHECKPOINTS) * FINALIST_COUNT
              and failed_validations <= validations)
        check("validation.points",
              c["validation_frequency_points"] ==
              (validations - failed_validations) * COMMON_POINTS)
        check("counter.mirrors", cell["physics_failures"] == failed
              and cell["validation_physics_failures"] == failed_validations
              and cell["geometry_rejections"] == geometry)
        check("checkpoint.lattice",
              cell["checkpoints"] == list(CHECKPOINTS)
              and cell["checkpoint_records"] == list(CHECKPOINTS))
        checkpoint = cell["checkpoint_summaries"]
        check("checkpoint.count", len(checkpoint) == len(CHECKPOINTS))
        for value, row in zip(CHECKPOINTS, checkpoint):
            check(f"checkpoint.{value}", row["checkpoint_budget"] == value
                  and row["unique_evaluations"] == value
                  and row["generations"] == value - INITIAL_POPULATION)
        selected, search = cell["common_grid_selected_finalist"], cell["search_incumbent"]
        check("candidate.common", validated_hybrid_rank_key(selected) is not None)
        check("candidate.search", validated_hybrid_rank_key(search) is not None)
        last = checkpoint[-1]
        for name, target in (
            ("max_violation", selected["max_violation"]),
            ("sum_violation", selected["sum_violation"]),
            ("worst_il_db", selected["metrics"]["worst_il_db"]),
            ("ripple_db", selected["metrics"]["ripple_db"]),
        ):
            check(f"checkpoint.final.{name}",
                  math.isclose(float(last[f"selected_{name}"]), float(target),
                               rel_tol=1e-12, abs_tol=1e-12))
        runtime = cell["runtime"]
        check("runtime.partition",
              _duration(runtime["cell_wall_time_s"]) + 1e-9 >=
              _duration(runtime["search_evaluation_wall_time_s"]) +
              _duration(runtime["common_validation_wall_time_s"]))
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        errors.append(f"record.malformed:{type(exc).__name__}:{exc}")
    return {"topology": topology, "seed": seed, "status": "FAIL" if errors else "PASS",
            "errors": errors}


def audit_package(review_dir: str | Path) -> dict[str, Any]:
    """Read the checked-in export, never write or re-evaluate it."""
    root = Path(review_dir)
    manifest = json.loads((root / "metadata/stage4c_run_manifest.json").read_text(encoding="utf-8"))
    protocol = json.loads((root / "metadata/protocol_snapshot.json").read_text(encoding="utf-8"))
    issues = []
    for key, expected in (
        ("search_grid_sha256", SEARCH_GRID_SHA256),
        ("common_validation_grid_id", COMMON_GRID_ID),
        ("common_validation_grid_sha256", COMMON_GRID_SHA256),
        ("budget_per_cell", BUDGET),
        ("seeds", list(SEEDS)),
        ("topologies", list(TOPOLOGIES)),
    ):
        if manifest.get(key) != expected:
            issues.append(f"manifest.{key}")
    for key, expected in (
        ("search_frequency_sha256", SEARCH_GRID_SHA256),
        ("common_validation_grid_id", COMMON_GRID_ID),
        ("common_validation_grid_sha256", COMMON_GRID_SHA256),
        ("search_frequency_count", SEARCH_POINTS),
        ("common_validation_frequency_count", COMMON_POINTS),
        ("finalist_count_per_checkpoint", FINALIST_COUNT),
        ("budget_per_cell", BUDGET),
        ("seeds", list(SEEDS)),
    ):
        if protocol.get(key) != expected:
            issues.append(f"protocol.{key}")
    records = []
    for topology in TOPOLOGIES:
        for seed in SEEDS:
            path = root / "cells" / topology / f"{seed}_result.json"
            cell = json.loads(path.read_text(encoding="utf-8"))
            records.append(audit_cell(
                cell, topology=topology, seed=seed,
                source_commit_sha=manifest["source_commit_sha"],
                fingerprint=manifest["computation_fingerprint"],
            ))
    errors = len(issues) + sum(len(row["errors"]) for row in records)
    return {"status": "PASS" if errors == 0 else "FAIL",
            "scope": "frozen_stage4c_compact_export_only",
            "run_id": manifest.get("run_id"), "cells_checked": len(records),
            "failed_checks": errors, "package_errors": issues, "cells": records,
            "limitations": list(LIMITATIONS)}
