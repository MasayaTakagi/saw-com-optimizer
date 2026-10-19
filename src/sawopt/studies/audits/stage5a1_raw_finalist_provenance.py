"""Read-only replay of Stage 4C saved *selection*, not COM physics.

Input is the external optimizer directory containing optimization/<topology>/
seed<seed>/B<budget>.json. Outputs go only to stdout. Raw artifacts, caches,
checkpoints and the compact review package are never written.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from ...reporting.candidate_integrity import validated_hybrid_rank_key
from ..hybrid_stage4c import (
    BUDGET, CHECKPOINTS, COMMON_GRID_ID, COMMON_GRID_SHA256, FINALIST_COUNT,
    SEARCH_GRID_SHA256, SEEDS, TOPOLOGIES,
)

_ALLOWED_STATUSES = {"PHYSICS_EVALUATED", "PHYSICS_FAILED", "GEOMETRY_REJECTED"}
_PROJECTION_OMIT = {"search_source_rank", "search_source_rank_key"}


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _vector(record: Mapping[str, Any]) -> tuple[float, ...] | None:
    value = record.get("candidate_vector")
    if not isinstance(value, list) or len(value) != 13:
        return None
    if any(isinstance(x, bool) or not isinstance(x, (int, float))
           or not math.isfinite(float(x)) for x in value):
        return None
    return tuple(float(x) for x in value)


def _projection(record: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k not in _PROJECTION_OMIT}


def audit_checkpoint(
    row: Mapping[str, Any], *, topology: str, seed: int, budget: int,
    index: int, fingerprint: str, compact: Mapping[str, Any],
) -> list[str]:
    """Replay the min-ranking decision across all 16 persisted common-grid rows.

    Equality uses the identical rank key and stable Python min tie policy as
    the Stage 4B engine. Schema validation is stricter to detect corruption.
    """
    errors: list[str] = []

    def check(name: str, condition: bool) -> None:
        if not condition:
            errors.append(name)

    try:
        check("identity", row["topology"] == topology and row["seed"] == seed
              and row["checkpoint_budget"] == budget
              and row["computation_fingerprint"] == fingerprint
              and row["common_validation_grid_id"] == COMMON_GRID_ID)
        candidates = row["validated_finalists"]
        if not isinstance(candidates, list) or len(candidates) != FINALIST_COUNT:
            return [*errors, "finalists.count"]
        ranks: list[int] = []
        vectors: list[tuple[float, ...]] = []
        valid: list[Mapping[str, Any]] = []
        failures = 0
        for position, candidate in enumerate(candidates, 1):
            if not isinstance(candidate, Mapping):
                errors.append(f"finalist.{position}.record")
                continue
            rank = candidate.get("search_source_rank")
            if type(rank) is not int or rank != position:
                errors.append(f"finalist.{position}.source_rank")
            else:
                ranks.append(rank)
            vector = _vector(candidate)
            if vector is None:
                errors.append(f"finalist.{position}.vector")
            else:
                vectors.append(vector)
            status = candidate.get("evaluation_status")
            if status not in _ALLOWED_STATUSES:
                errors.append(f"finalist.{position}.status")
            elif status == "PHYSICS_EVALUATED":
                if validated_hybrid_rank_key(candidate) is None:
                    errors.append(f"finalist.{position}.physics_integrity")
                else:
                    valid.append(candidate)
            elif status == "PHYSICS_FAILED":
                failures += 1
                if (candidate.get("max_violation") is not None
                        or candidate.get("sum_violation") is not None
                        or candidate.get("geometry_max_violation") != 0.0):
                    errors.append(f"finalist.{position}.failed_physics_integrity")
            else:
                # A historically shortlisted geometry rejection is unexpected
                # in the large production pools, and must not be silently
                # treated as a physics-evaluated finalist.
                failures += 1
                if (candidate.get("max_violation") is not None
                        or candidate.get("sum_violation") is not None
                        or not isinstance(candidate.get("geometry_max_violation"), (int, float))
                        or candidate["geometry_max_violation"] <= 0):
                    errors.append(f"finalist.{position}.geometry_integrity")
        check("finalists.rank_lattice", ranks == list(range(1, FINALIST_COUNT + 1)))
        check("finalists.unique_vectors", len(vectors) == FINALIST_COUNT
              and len(set(vectors)) == FINALIST_COUNT)

        selected = row.get("common_grid_selected_finalist")
        if not valid:
            check("selected.absent_if_no_success", selected is None)
        elif selected is None:
            errors.append("selected.missing")
        else:
            # For PHYSICS_EVALUATED the GeometryFirstComparator adds only
            # constant (0, 0) prefixes to the validated feasibility key.
            expected = min(valid, key=validated_hybrid_rank_key)
            check("selected.canonical_min", _projection(expected) == selected)
            check("selected.valid", validated_hybrid_rank_key(selected) is not None)
        counters = row["counters"]
        check("counter.search_budget", counters["unique_decoded_evaluations"] == budget)
        check("counter.validation_count",
              counters["validation_evaluations"] == (index + 1) * FINALIST_COUNT)
        check("counter.validation_failures",
              counters["validation_physics_failures"] >= failures)
        check("counter.validation_points",
              counters["validation_frequency_points"] ==
              (counters["validation_evaluations"] -
               counters["validation_physics_failures"]) * 9113)

        summary = compact["checkpoint_summaries"][index]
        check("checkpoint.summary_budget",
              summary["checkpoint_budget"] == budget
              and summary["unique_evaluations"] == budget)
        check("checkpoint.generations",
              summary["generations"] == row["lshade_summary"]["generations"])
        if selected is not None:
            for name, actual in (
                ("max_violation", selected["max_violation"]),
                ("sum_violation", selected["sum_violation"]),
                ("worst_il_db", selected["metrics"]["worst_il_db"]),
                ("ripple_db", selected["metrics"]["ripple_db"]),
            ):
                check(f"checkpoint.selected_{name}",
                      summary[f"selected_{name}"] == actual)
        if budget == BUDGET:
            check("terminal.selected", selected == compact["common_grid_selected_finalist"])
            check("terminal.search_incumbent",
                  row["search_incumbent"] == compact["search_incumbent"])
            check("terminal.counters", counters == compact["counters"])
    except (KeyError, ValueError, TypeError, IndexError, OverflowError) as exc:
        errors.append(f"checkpoint.malformed:{type(exc).__name__}:{exc}")
    return errors


def audit_raw_run(optimizer_run: str | Path, review_package: str | Path) -> dict[str, Any]:
    """Read all 80 B*.json records with exact frozen run identity."""
    optimizer = Path(optimizer_run)
    review = Path(review_package)
    report: dict[str, Any] = {
        "scope": "external_raw_stage4c_finalist_replay",
        "status": "INCOMPLETE",
        "checks": [],
        "checkpoints_expected": len(CHECKPOINTS) * len(SEEDS) * len(TOPOLOGIES),
        "checkpoints_checked": 0,
        "errors": [],
        "limitations": [
            "Only saved 16-finalist selection decisions are replayed; COM physics is not rerun",
            "Source rank keys are not projected into validated_finalists, so historical search rank cannot be independently recomputed from B*.json",
            "Full canonical-key cache/proposal histories are not reconstructed from B*.json",
        ],
    }
    try:
        manifest = _json_object(review / "metadata/stage4c_run_manifest.json")
        protocol = _json_object(review / "metadata/protocol_snapshot.json")
    except (OSError, ValueError, TypeError) as exc:
        report["errors"].append(f"review.missing_or_invalid:{type(exc).__name__}:{exc}")
        return report
    expected_metadata = {
        "search_grid_sha256": SEARCH_GRID_SHA256,
        "common_validation_grid_id": COMMON_GRID_ID,
        "common_validation_grid_sha256": COMMON_GRID_SHA256,
    }
    for name, expected in expected_metadata.items():
        if manifest.get(name) != expected:
            report["errors"].append(f"manifest.{name}")
    for name, expected in (
        ("search_frequency_sha256", SEARCH_GRID_SHA256),
        ("common_validation_grid_id", COMMON_GRID_ID),
        ("common_validation_grid_sha256", COMMON_GRID_SHA256),
        ("finalist_count_per_checkpoint", FINALIST_COUNT),
    ):
        if protocol.get(name) != expected:
            report["errors"].append(f"protocol.{name}")
    report["run_id"] = manifest.get("run_id")
    fingerprint = manifest.get("computation_fingerprint")
    source_sha = manifest.get("source_commit_sha")
    for topology in TOPOLOGIES:
        for seed in SEEDS:
            saved = review / "cells" / topology / f"{seed}_result.json"
            cell_dir = optimizer / "optimization" / topology / f"seed{seed}"
            try:
                compact = _json_object(saved)
            except (OSError, ValueError, TypeError) as exc:
                report["errors"].append(f"compact.{topology}.{seed}:{type(exc).__name__}")
                continue
            if (compact.get("computation_fingerprint") != fingerprint
                    or compact.get("source_commit_sha") != source_sha
                    or compact.get("common_validation_grid_id") != COMMON_GRID_ID):
                report["errors"].append(f"compact.{topology}.{seed}.identity")
            for index, budget in enumerate(CHECKPOINTS):
                path = cell_dir / f"B{budget}.json"
                check = {"topology": topology, "seed": seed, "budget": budget}
                try:
                    row = _json_object(path)
                    faults = audit_checkpoint(
                        row, topology=topology, seed=seed,
                        budget=budget, index=index,
                        fingerprint=fingerprint, compact=compact,
                    )
                    report["checkpoints_checked"] += 1
                except (OSError, ValueError, TypeError) as exc:
                    faults = [f"checkpoint.missing_or_invalid:{type(exc).__name__}:{exc}"]
                check["status"] = "FAIL" if faults else "PASS"
                check["errors"] = faults
                report["checks"].append(check)
    if (report["checkpoints_checked"] == report["checkpoints_expected"]
            and not report["errors"]
            and all(item["status"] == "PASS" for item in report["checks"])):
        report["status"] = "PASS"
    elif report["checkpoints_checked"] == report["checkpoints_expected"]:
        report["status"] = "FAIL"
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--optimizer-run", type=Path, required=True,
                        help="Directory containing optimization/<topology>/seed<seed>/B*.json")
    parser.add_argument("--review-package", type=Path, required=True,
                        help="Tracked compact review package directory")
    args = parser.parse_args(argv)
    result = audit_raw_run(args.optimizer_run, args.review_package)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
