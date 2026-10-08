"""Fixed-design resonator pair coordinate probe for tracked Stage 4C evidence.

This module evaluates selected finalists directly. It does not invoke an
optimizer, orchestration, or production lifecycle.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..hybrid import stage4a_evaluate
from ..hybrid_stage4c import load_stage4c_context


STAGE4C_RUN_ID = "20261006_124153_ed50ba"
CELL_KEYS = (
    ("P_D", 20261007),
    ("D_P", 20261007),
    ("D_P", 20261009),
    ("P_D", 20261011),
    ("D_P", 20261011),
)
PAIR_PROBES = (60, 65, 70, 75)
MAX_PROBE_PAIRS = 75
BASELINE_FIELDS = ("worst_il_db", "ripple_db", "input_vswr", "output_vswr")


def probe_values(original_pairs: int) -> tuple[int, ...]:
    """Return the original coordinate and distinct frozen probe points."""
    original = int(original_pairs)
    if original < 1 or original > MAX_PROBE_PAIRS:
        raise ValueError("selected resonator pair count must be between 1 and 75")
    return tuple(dict.fromkeys((original, *PAIR_PROBES)))


def candidate_at_pairs(space, selected: Mapping[str, Any], pairs: int, reflector_electrodes: int):
    """Keep a selected finalist fixed except for its resonator pair coordinate."""
    vector = np.asarray(selected["candidate_vector"], dtype=float)
    base = space.decode(vector, reflector_electrodes=reflector_electrodes)
    pair_index = 11  # T1's ten coordinates, then resonator wavelength/pairs/aperture.
    original = int(np.floor(vector[pair_index] + 0.5))
    if len(base.resonator_designs) != 1 or original != int(selected["resonator_designs"][0]["pairs"]):
        raise ValueError("selected finalist resonator coordinate does not match its decoded design")
    if int(pairs) not in probe_values(original):
        raise ValueError("requested pair count is outside this cell's frozen probe points")
    changed = vector.copy()
    changed[pair_index] = int(pairs)
    candidate = replace(
        base,
        vector=tuple(float(value) for value in changed),
        key=tuple(float(value) for value in changed),
        resonator_designs=(replace(base.resonator_designs[0], pairs=int(pairs)),),
    )
    if any(index != pair_index and changed[index] != vector[index]
           for index in range(len(vector))):
        raise AssertionError("coordinate probe changed a non-pair design value")
    return candidate


def _assert_baseline_reproduced(selected: Mapping[str, Any], evaluated: Mapping[str, Any]) -> None:
    if evaluated.get("geometry_valid") is not True or evaluated.get("evaluation_status") != "PHYSICS_EVALUATED":
        raise RuntimeError("selected-value baseline did not complete valid physics evaluation")
    for name in ("max_violation", "sum_violation"):
        if not np.isclose(float(evaluated[name]), float(selected[name]), rtol=1e-10, atol=1e-10):
            raise AssertionError(f"selected-value baseline does not reproduce tracked {name}")
    if bool(evaluated["feasible"]) != bool(selected["feasible"]):
        raise AssertionError("selected-value baseline does not reproduce tracked feasibility")
    for name in BASELINE_FIELDS:
        if not np.isclose(float(evaluated["metrics"][name]), float(selected["metrics"][name]),
                          rtol=1e-10, atol=1e-10):
            raise AssertionError(f"selected-value baseline does not reproduce tracked metric {name}")
    for name, value in selected["violations"].items():
        if not np.isclose(float(evaluated["violations"][name]), float(value),
                          rtol=1e-10, atol=1e-10):
            raise AssertionError(f"selected-value baseline does not reproduce tracked violation {name}")


def _record(topology: str, seed: int, original: int, pairs: int,
            evaluated: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    geometry_valid = evaluated.get("geometry_valid") is True
    if not geometry_valid:
        return {
            "topology": topology, "seed": int(seed), "original_pairs": int(original),
            "probe_pairs": int(pairs), "geometry_valid": False,
            "status": "INVALID_GEOMETRY", "max_violation": None,
            "sum_violation": None, "worst_il_db": None, "ripple_db": None,
            "input_vswr": None, "output_vswr": None,
            "stop_1_violation": None, "stop_2_violation": None,
            "feasible": False, "delta_max_violation": None,
            "delta_stop_2_violation": None, "delta_sum_violation": None,
        }
    if evaluated.get("evaluation_status") != "PHYSICS_EVALUATED":
        raise RuntimeError(
            f"physics evaluation failed for {topology}/{seed} at resonator_0_pairs={pairs}: "
            f"{evaluated.get('failure', evaluated.get('evaluation_status'))}"
        )
    metrics = evaluated["metrics"]
    violations = evaluated["violations"]
    return {
        "topology": topology, "seed": int(seed), "original_pairs": int(original),
        "probe_pairs": int(pairs), "geometry_valid": True,
        "status": "PHYSICS_EVALUATED",
        "max_violation": float(evaluated["max_violation"]),
        "sum_violation": float(evaluated["sum_violation"]),
        "worst_il_db": float(metrics["worst_il_db"]),
        "ripple_db": float(metrics["ripple_db"]),
        "input_vswr": float(metrics["input_vswr"]),
        "output_vswr": float(metrics["output_vswr"]),
        "stop_1_violation": float(violations["stop_1"]),
        "stop_2_violation": float(violations["stop_2"]),
        "feasible": bool(evaluated["feasible"]),
        "delta_max_violation": float(evaluated["max_violation"] - baseline["max_violation"]),
        "delta_stop_2_violation": float(violations["stop_2"] - baseline["violations"]["stop_2"]),
        "delta_sum_violation": float(evaluated["sum_violation"] - baseline["sum_violation"]),
    }


def classify_signal(rows: Sequence[Mapping[str, Any]]) -> str:
    """Apply the frozen 0.02 max-normalized-violation cell-count rule."""
    improved_cells: set[tuple[str, int]] = set()
    any_improvement = False
    for row in rows:
        if row.get("geometry_valid") is not True or int(row["probe_pairs"]) <= 60:
            continue
        delta = float(row["delta_max_violation"])
        any_improvement |= delta < -1e-12
        if delta <= -0.02:
            improved_cells.add((str(row["topology"]), int(row["seed"])))
    if len(improved_cells) >= 3:
        return "STRONG_BOUND_SIGNAL"
    if any_improvement:
        return "MIXED_BOUND_SIGNAL"
    return "NO_BOUND_SIGNAL"


def run_probe(
    evidence_root: str | Path,
    *,
    config_path: str | Path = "configs/studies/hybrid_stage4c_confirmatory.yaml",
) -> dict[str, Any]:
    """Evaluate the five tracked 96k selected finalists on the common grid."""
    evidence_root = Path(evidence_root)
    if evidence_root.name != STAGE4C_RUN_ID:
        raise ValueError(f"evidence root must identify Stage 4C run {STAGE4C_RUN_ID}")
    context = load_stage4c_context(config_path)
    if len(context["common_frequencies"]) != 9113:
        raise ValueError("Stage 4C common validation grid must contain 9,113 points")
    cfg = context["cfg"]
    # This is an evaluation-only geometry allowance; the loaded config and search space stay frozen.
    probe_bounds = np.asarray(cfg["hybrid"]["resonator_bounds"], dtype=float).copy()
    probe_bounds[1, 1] = MAX_PROBE_PAIRS
    rows: list[dict[str, Any]] = []
    baseline_reproduction: list[dict[str, Any]] = []

    for topology, expected_seed in CELL_KEYS:
        path = evidence_root / "cells" / topology / f"{expected_seed}_result.json"
        cell = json.loads(path.read_text(encoding="utf-8"))
        selected = cell.get("common_grid_selected_finalist")
        if (cell.get("topology") != topology or int(cell.get("seed", -1)) != expected_seed
                or not isinstance(selected, Mapping)
                or selected.get("evaluation_status") != "PHYSICS_EVALUATED"):
            raise ValueError(f"tracked selected-finalist identity/status mismatch: {path}")
        original = int(selected["resonator_designs"][0]["pairs"])
        space = context["spaces"][topology]
        reflector_count = int(cfg["dms_topology"]["t1_reflector_electrodes"])
        baseline_candidate = candidate_at_pairs(space, selected, original, reflector_count)
        baseline_eval = stage4a_evaluate(
            baseline_candidate, context["provider"], cfg, context["common_frequencies"],
            context["source_impedance_ohm"], context["load_impedance_ohm"],
        )
        _assert_baseline_reproduced(selected, baseline_eval)
        baseline_reproduction.append({
            "topology": topology, "seed": expected_seed, "original_pairs": original,
            "max_violation": float(baseline_eval["max_violation"]),
            "sum_violation": float(baseline_eval["sum_violation"]),
            "tracked_max_violation": float(selected["max_violation"]),
            "tracked_sum_violation": float(selected["sum_violation"]),
            "metrics_match": True, "violations_match": True,
        })
        for pairs in probe_values(original):
            candidate = candidate_at_pairs(space, selected, pairs, reflector_count)
            if pairs == original:
                evaluated = baseline_eval
            else:
                evaluation_options = ({"geometry_resonator_bounds": probe_bounds}
                                      if pairs > 60 else {})
                evaluated = stage4a_evaluate(
                    candidate, context["provider"], cfg, context["common_frequencies"],
                    context["source_impedance_ohm"], context["load_impedance_ohm"],
                    **evaluation_options,
                )
            rows.append(_record(topology, expected_seed, original, pairs, evaluated, baseline_eval))

    return {
        "run_id": STAGE4C_RUN_ID,
        "common_validation_frequency_count": int(len(context["common_frequencies"])),
        "probe_upper_value": MAX_PROBE_PAIRS,
        "baseline_reproduction": baseline_reproduction,
        "rows": rows,
        "signal": classify_signal(rows),
        "production_authorization": "NO",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-root",
        default=f"reports/experiment_reviews/stage4c/{STAGE4C_RUN_ID}",
        help="tracked compact Stage 4C review evidence directory",
    )
    parser.add_argument(
        "--config", default="configs/studies/hybrid_stage4c_confirmatory.yaml",
        help="unchanged Stage 4C configuration used to load fixed model inputs",
    )
    args = parser.parse_args(argv)
    result = run_probe(args.evidence_root, config_path=args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
