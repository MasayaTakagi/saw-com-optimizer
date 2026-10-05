"""Stage 4C compact reports and fail-closed GitHub review export."""
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..optimization.convergence_evidence import apply_checkpoint_evidence
from ..studies.hybrid_stage4c import (
    BUDGET, CHECKPOINTS, COMMON_GRID_ID, COMMON_GRID_SHA256, PROTOCOL_REVISION,
    SEARCH_GRID_SHA256, SEEDS, SHAKEDOWN_BUDGET, SHAKEDOWN_CHECKPOINTS,
    SHAKEDOWN_SEED, STUDY_TYPE, TOPOLOGIES, PRODUCTION_RUN_ROOT, expected_matrix,
)


STAGE4C_REQUIRED_ARTIFACTS = (
    "run_manifest.json", "status.json", "metadata/run_completion.json",
    "metadata/config_snapshot.yaml", "metadata/protocol_snapshot.json",
    "metadata/integrity_check.json", "metadata/stage4c_run_manifest.json",
    "summary/primary_summary.csv", "summary/paired_comparisons.csv",
    "summary/convergence.csv", "summary/bound_pressure_summary.csv",
    "summary/runtime_accounting_summary.csv", "summary/stopband_diagnostics.csv",
    "summary/scientific_limitations.md", "summary/final_execution_report.md",
)
EQUIVALENCE_MARGINS = {
    "max_violation_absolute": 0.02,
    "max_violation_relative": 0.01,
    "sum_violation_absolute": 0.02,
    "sum_violation_relative": 0.01,
    "worst_il_db_absolute": 0.05,
    "ripple_db_absolute": 0.05,
}
SIGNIFICANT_ABSOLUTE_IMPROVEMENT = 0.02
SIGNIFICANT_RELATIVE_IMPROVEMENT = 0.01


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = sorted(set().union(*(row.keys() for row in rows))) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        if columns:
            writer.writeheader()
            writer.writerows(rows)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _selected(cell: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = cell.get("common_grid_selected_finalist")
    return value if isinstance(value, Mapping) else None


def _metric(selected: Mapping[str, Any] | None, key: str) -> float | None:
    if not isinstance(selected, Mapping):
        return None
    if key in {"worst_il_db", "ripple_db"}:
        return _finite(selected.get("metrics", {}).get(key))
    return _finite(selected.get(key))


def _violation(selected: Mapping[str, Any] | None, key: str) -> float | None:
    if not isinstance(selected, Mapping):
        return None
    return _finite(selected.get("violations", {}).get(key))


def _score(selected: Mapping[str, Any] | None) -> tuple[float, ...] | None:
    """Existing feasibility-first comparator, with no scalar score."""
    if not isinstance(selected, Mapping):
        return None
    values = tuple(_metric(selected, key) for key in ("max_violation", "sum_violation", "worst_il_db"))
    if any(value is None for value in values):
        return None
    return (0.0 if selected.get("feasible") is True else 1.0, *values)  # type: ignore[arg-type]


def _winner(left: Mapping[str, Any] | None, right: Mapping[str, Any] | None) -> str:
    a, b = _score(left), _score(right)
    if a is None or b is None:
        return "INDETERMINATE"
    if a == b:
        return "TIE"
    return "P_D" if a < b else "D_P"


def primary_summary(cells: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for topology in TOPOLOGIES:
        group = [cell for cell in cells if cell.get("topology") == topology]
        selected = [_selected(cell) for cell in group]
        valid = [row for row in selected if row is not None]
        max_values = [_metric(row, "max_violation") for row in valid]
        sum_values = [_metric(row, "sum_violation") for row in valid]
        il_values = [_metric(row, "worst_il_db") for row in valid]
        ripple_values = [_metric(row, "ripple_db") for row in valid]
        stop1 = [_violation(row, "stop_1") for row in valid]
        stop2 = [_violation(row, "stop_2") for row in valid]
        dominant = Counter()
        for row in valid:
            violations = row.get("violations", {})
            if isinstance(violations, Mapping) and violations:
                name, value = max(violations.items(), key=lambda item: float(item[1]))
                if float(value) > 0:
                    dominant[str(name)] += 1
        rows.append({
            "topology": topology,
            "completed_seeds": sum(cell.get("status") == "COMPLETED" for cell in group),
            "feasible_count": sum(row.get("feasible") is True for row in valid),
            "max_violation_median": statistics.median(v for v in max_values if v is not None) if any(v is not None for v in max_values) else None,
            "sum_violation_median": statistics.median(v for v in sum_values if v is not None) if any(v is not None for v in sum_values) else None,
            "worst_in_band_il_db_median": statistics.median(v for v in il_values if v is not None) if any(v is not None for v in il_values) else None,
            "ripple_db_median": statistics.median(v for v in ripple_values if v is not None) if any(v is not None for v in ripple_values) else None,
            "stop_1_703_748_violation_median": statistics.median(v for v in stop1 if v is not None) if any(v is not None for v in stop1) else None,
            "stop_2_832_862_violation_median": statistics.median(v for v in stop2 if v is not None) if any(v is not None for v in stop2) else None,
            "dominant_violated_constraint_counts": json.dumps(dominant.most_common()),
        })
    return rows


def paired_comparisons(cells: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_key = {(cell.get("topology"), int(cell.get("seed", -1))): cell for cell in cells}
    rows = []
    for seed in SEEDS:
        left = _selected(by_key.get(("P_D", seed), {}))
        right = _selected(by_key.get(("D_P", seed), {}))
        row: dict[str, Any] = {"topology_left": "P_D", "topology_right": "D_P", "seed": seed,
                               "lexicographic_winner": _winner(left, right)}
        for name in ("max_violation", "sum_violation", "worst_il_db", "ripple_db"):
            a, b = _metric(left, name), _metric(right, name)
            row[f"delta_{name}_P_D_minus_D_P"] = None if a is None or b is None else a - b
        for name in ("stop_1", "stop_2"):
            a, b = _violation(left, name), _violation(right, name)
            row[f"delta_{name}_violation_P_D_minus_D_P"] = None if a is None or b is None else a - b
        rows.append(row)
    return rows


def _significant_improvement(previous: Any, current: Any) -> bool | None:
    before, after = _finite(previous), _finite(current)
    if before is None or after is None:
        return None
    improvement = before - after
    relative = improvement / max(abs(before), np.finfo(float).tiny)
    return improvement >= SIGNIFICANT_ABSOLUTE_IMPROVEMENT or relative >= SIGNIFICANT_RELATIVE_IMPROVEMENT


def _checkpoint_rows(
    run: Path, cells: Sequence[Mapping[str, Any]], context: Mapping[str, Any],
) -> list[dict[str, Any]]:
    from ..studies.hybrid_stage4b import matched_cell_paths
    from ..studies.hybrid import stage4a_active_bound_diagnostics

    rows = []
    for cell in cells:
        topology, seed = str(cell["topology"]), int(cell["seed"])
        cell_dir, _manifest, _result = matched_cell_paths(run, topology, seed)
        by_budget = {}
        for checkpoint in CHECKPOINTS:
            record_path = cell_dir / f"B{checkpoint}.json"
            if not record_path.is_file():
                continue
            record = _read_json(record_path)
            raw_evidence = dict(record.get("lshade_summary", {}))
            selected = record.get("common_grid_selected_finalist") or {}
            bound_diagnostics = stage4a_active_bound_diagnostics(
                selected.get("candidate_vector", []), context["spaces"][topology].bounds,
            ) if selected.get("candidate_vector") is not None else []
            hard_hit = any(item.get("at_lower_bound") or item.get("at_upper_bound")
                           for item in bound_diagnostics)
            # Stage 4C uses fixed, fingerprinted grids and the base L-SHADE
            # backend has no recovery or micro-polish phase. Mark those facts
            # explicitly so the shared evidence routine can distinguish
            # unavailable telemetry from a protocol with no such event.
            raw_evidence.update({
                "grid_converged": True,
                "recovery_pending_confirmation": False,
                "boundary_pending_confirmation": bool(hard_hit),
                "hard_bound_unresolved": bool(hard_hit),
                "micro_polish_improvement": 0.0,
            })
            evidence = apply_checkpoint_evidence(
                raw_evidence, current_budget=checkpoint, terminal_budget=BUDGET,
            )
            row = {
                "topology": topology, "seed": seed, "checkpoint_budget": checkpoint,
                "selected_max_violation": _metric(selected, "max_violation"),
                "selected_sum_violation": _metric(selected, "sum_violation"),
                "selected_worst_il_db": _metric(selected, "worst_il_db"),
                "selected_ripple_db": _metric(selected, "ripple_db"),
                "selected_feasible": selected.get("feasible"),
                "active_bound_hits_by_variable": json.dumps([
                    item.get("variable") for item in bound_diagnostics
                    if item.get("at_lower_bound") or item.get("at_upper_bound")
                ]),
                "micro_polish_performed": False,
                "convergence_evidence_complete": evidence["convergence_evidence_complete"],
                "convergence_evidence_missing_fields": json.dumps(evidence["convergence_evidence_missing_fields"]),
                **{key: evidence.get(key) for key in (
                    "grid_converged", "recovery_pending_confirmation", "boundary_pending_confirmation",
                    "hard_bound_unresolved", "micro_polish_improvement",
                    "fraction_of_budget_at_last_significant_improvement",
                )},
            }
            by_budget[checkpoint] = row
            rows.append(row)
        final = by_budget.get(BUDGET)
        if final is None:
            continue
        previous = by_budget.get(80000)
        significant = _significant_improvement(
            None if previous is None else previous["selected_max_violation"],
            final["selected_max_violation"],
        )
        any_boundary = any(
            row.get("boundary_pending_confirmation") is True
            for row in by_budget.values()
        )
        last_fraction = _finite(final.get("fraction_of_budget_at_last_significant_improvement"))
        mature = bool(
            final.get("convergence_evidence_complete") is True
            and final.get("grid_converged") is True
            and final.get("recovery_pending_confirmation") is False
            and final.get("hard_bound_unresolved") is False
            and final.get("boundary_pending_confirmation") is False
            and not any_boundary
            and significant is False
            and last_fraction is not None and last_fraction <= 0.80
        )
        for row in by_budget.values():
            row["significant_improvement_80k_to_96k"] = significant
            row["maturity_classification"] = "MATURE" if mature else "IMMATURE_OR_INCOMPLETE"
    return rows


def convergence_rows(
    cells: Sequence[Mapping[str, Any]], run: str | Path | None = None,
    context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if run is None or context is None:
        return []
    return _checkpoint_rows(Path(run), cells, context)


def _boundary_rows(cells: Sequence[Mapping[str, Any]], checkpoints: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str]] = Counter()
    for cell in cells:
        for item in cell.get("active_bound_diagnostics", ()):
            if item.get("at_lower_bound"):
                counts[(str(item.get("variable")), "lower")] += 1
            if item.get("at_upper_bound"):
                counts[(str(item.get("variable")), "upper")] += 1
    events: dict[tuple[str, int], list[dict[str, Any]]] = {}
    # Checkpoint evidence stores the decisions; detailed optimizer events stay in raw B records.
    for row in checkpoints:
        key = (str(row["topology"]), int(row["seed"]))
        events.setdefault(key, []).append({
            "checkpoint": int(row["checkpoint_budget"]),
            "boundary_pending_confirmation": row.get("boundary_pending_confirmation"),
            "hard_bound_unresolved": row.get("hard_bound_unresolved"),
        })
    rows = []
    variables = sorted({name for name, _side in counts} | {"resonator_0_pairs"})
    for variable in variables:
        rows.extend((
            {"scope": "variable", "variable": variable, "side": "lower", "active_bound_hits": counts[(variable, "lower")]},
            {"scope": "variable", "variable": variable, "side": "upper", "active_bound_hits": counts[(variable, "upper")]},
        ))
    for cell in cells:
        topology, seed = str(cell["topology"]), int(cell["seed"])
        diag = cell.get("active_bound_diagnostics", ())
        cell_keys = {(str(d.get("variable")), side) for d in diag
                     for side, flag in (("lower", "at_lower_bound"), ("upper", "at_upper_bound")) if d.get(flag)}
        rows.append({
            "scope": "cell", "topology": topology, "seed": seed,
            "active_bound_hits_by_variable": json.dumps(sorted(f"{var}:{side}" for var, side in cell_keys)),
            "hard_bound_events": json.dumps(events.get((topology, seed), [])),
            "boundary_pending_confirmation": any(item.get("boundary_pending_confirmation") is True
                                                  for item in events.get((topology, seed), [])),
            "hard_bound_unresolved": any(item.get("hard_bound_unresolved") is True
                                          for item in events.get((topology, seed), [])),
            "resonator_0_pairs_upper_hit": any(var == "resonator_0_pairs" and side == "upper" for var, side in cell_keys),
        })
    return rows


def runtime_rows(cells: Sequence[Mapping[str, Any]], checkpoints: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    final_evidence = {(r["topology"], int(r["seed"])): r for r in checkpoints if int(r["checkpoint_budget"]) == BUDGET}
    rows = []
    for cell in cells:
        counters = cell.get("counters", {})
        initialization = cell.get("initialization", {})
        runtime = cell.get("runtime", {})
        total = int(cell.get("unique_evaluations", 0))
        elapsed = _finite(runtime.get("cell_wall_time_s"))
        rows.append({
            "topology": cell.get("topology"), "seed": cell.get("seed"),
            "unique_decoded_evaluations": total,
            "budget_per_cell": cell.get("budget"),
            "population_schedule_terminal_budget": cell.get("population_schedule_terminal_budget"),
            "initial_population": cell.get("initial_population"),
            "checkpoint_lattice": json.dumps(cell.get("checkpoint_records", [])),
            "initializer_geometry_rejections": initialization.get("geometry_rejections"),
            "initializer_geometry_rejection_rate": (
                initialization.get("geometry_rejections", 0) / max(1, initialization.get("candidate_draws", 0))
            ),
            "runtime_geometry_rejections": counters.get("geometry_rejections"),
            "runtime_geometry_rejection_rate": counters.get("geometry_rejections", 0) / max(1, counters.get("objective_proposals", 0)),
            "duplicate_proposals": counters.get("duplicate_proposals"),
            "duplicate_proposal_rate": counters.get("duplicate_proposals", 0) / max(1, counters.get("objective_proposals", 0)),
            "physics_failures": counters.get("physics_failures"),
            "physics_failure_rate": counters.get("physics_failures", 0) / max(1, counters.get("physics_attempted_evaluations", 0)),
            "duplicate_cache_hits": cell.get("cache_statistics", {}).get("cache_hits"),
            "search_frequency_points": counters.get("search_frequency_points"),
            "validation_evaluations": counters.get("validation_evaluations"),
            "validation_frequency_points": counters.get("validation_frequency_points"),
            "search_evaluation_wall_time_s": runtime.get("search_evaluation_wall_time_s"),
            "common_validation_wall_time_s": runtime.get("common_validation_wall_time_s"),
            "cell_wall_time_s": elapsed,
            "unique_evaluations_per_wall_second": None if not elapsed else total / elapsed,
            "fraction_of_budget_at_last_significant_improvement": final_evidence.get((cell.get("topology"), int(cell.get("seed", -1))), {}).get("fraction_of_budget_at_last_significant_improvement"),
        })
    return rows


def stopband_rows(cells: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    by_seed = {}
    for cell in cells:
        selected = _selected(cell)
        violations = selected.get("violations", {}) if selected else {}
        if not isinstance(violations, Mapping):
            violations = {}
        dominant = max(violations, key=lambda key: float(violations[key])) if violations else None
        row = {
            "scope": "cell", "topology": cell.get("topology"), "seed": cell.get("seed"),
            "stop_1_band_mhz": "703-748", "stop_1_violation": _finite(violations.get("stop_1")),
            "stop_2_band_mhz": "832-862", "stop_2_violation": _finite(violations.get("stop_2")),
            "dominant_constraint": dominant,
        }
        rows.append(row)
        by_seed[(cell.get("topology"), int(cell.get("seed", -1)))] = row
    stop2 = [row["stop_2_violation"] for row in rows if row["scope"] == "cell" and row["stop_2_violation"] is not None]
    paired = [by_seed[("P_D", seed)]["stop_2_violation"] - by_seed[("D_P", seed)]["stop_2_violation"]
              for seed in SEEDS if ("P_D", seed) in by_seed and ("D_P", seed) in by_seed
              and by_seed[("P_D", seed)]["stop_2_violation"] is not None
              and by_seed[("D_P", seed)]["stop_2_violation"] is not None]
    ordered = sorted(stop2)
    q1 = float(np.percentile(ordered, 25)) if ordered else None
    q3 = float(np.percentile(ordered, 75)) if ordered else None
    rows.append({
        "scope": "aggregate", "stop_2_dominance_count": sum(row["dominant_constraint"] == "stop_2" for row in rows),
        "stop_2_violation_median": statistics.median(ordered) if ordered else None,
        "stop_2_violation_iqr": None if q1 is None or q3 is None else q3 - q1,
        "paired_stop_2_difference_median_P_D_minus_D_P": statistics.median(paired) if paired else None,
        "paired_stop_2_difference_by_seed_P_D_minus_D_P": json.dumps({
            str(seed): by_seed[("P_D", seed)]["stop_2_violation"] - by_seed[("D_P", seed)]["stop_2_violation"]
            for seed in SEEDS if ("P_D", seed) in by_seed and ("D_P", seed) in by_seed
            and by_seed[("P_D", seed)]["stop_2_violation"] is not None
            and by_seed[("D_P", seed)]["stop_2_violation"] is not None
        }, sort_keys=True),
        "stop_2_band_mhz": "832-862",
    })
    return rows


def _paired_at_checkpoint(checkpoints: Sequence[Mapping[str, Any]], budget: int) -> dict[int, str]:
    by_key = {(row["topology"], int(row["seed"])): row for row in checkpoints
              if int(row.get("checkpoint_budget", -1)) == budget}
    return {seed: _winner(
        {"feasible": by_key.get(("P_D", seed), {}).get("selected_feasible"),
         "max_violation": by_key.get(("P_D", seed), {}).get("selected_max_violation"),
         "sum_violation": by_key.get(("P_D", seed), {}).get("selected_sum_violation"),
         "metrics": {"worst_il_db": by_key.get(("P_D", seed), {}).get("selected_worst_il_db")}},
        {"feasible": by_key.get(("D_P", seed), {}).get("selected_feasible"),
         "max_violation": by_key.get(("D_P", seed), {}).get("selected_max_violation"),
         "sum_violation": by_key.get(("D_P", seed), {}).get("selected_sum_violation"),
         "metrics": {"worst_il_db": by_key.get(("D_P", seed), {}).get("selected_worst_il_db")}},
    ) for seed in SEEDS}


def _inside_margin(delta: Any, left: Any, right: Any, *, absolute: float, relative: float | None = None) -> bool:
    d, a, b = _finite(delta), _finite(left), _finite(right)
    if d is None or a is None or b is None:
        return False
    if abs(d) > absolute:
        return False
    return relative is None or abs(d) / max(abs(a), abs(b), np.finfo(float).tiny) <= relative


def _equivalence_pairs(pairs: Sequence[Mapping[str, Any]]) -> bool:
    if len(pairs) != len(SEEDS):
        return False
    for row in pairs:
        for metric, abs_margin, rel_margin in (
            ("max_violation", EQUIVALENCE_MARGINS["max_violation_absolute"], EQUIVALENCE_MARGINS["max_violation_relative"]),
            ("sum_violation", EQUIVALENCE_MARGINS["sum_violation_absolute"], EQUIVALENCE_MARGINS["sum_violation_relative"]),
        ):
            delta = row.get(f"delta_{metric}_P_D_minus_D_P")
            left = row.get(f"P_D_{metric}")
            right = row.get(f"D_P_{metric}")
            if not _inside_margin(delta, left, right, absolute=abs_margin, relative=rel_margin):
                return False
        for metric, margin in (("worst_il_db", EQUIVALENCE_MARGINS["worst_il_db_absolute"]),
                               ("ripple_db", EQUIVALENCE_MARGINS["ripple_db_absolute"])):
            delta = row.get(f"delta_{metric}_P_D_minus_D_P")
            if _finite(delta) is None or abs(float(delta)) > margin:
                return False
    return True


def classify_stage4c(
    cells: Sequence[Mapping[str, Any]], checkpoints: Sequence[Mapping[str, Any]],
    pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply only the frozen Stage 4C post-run closeout classes."""
    final_wins = Counter(row.get("lexicographic_winner") for row in pairs)
    maturity = {}
    for topology in TOPOLOGIES:
        rows = [row for row in checkpoints if row.get("topology") == topology
                and int(row.get("checkpoint_budget", -1)) == BUDGET]
        maturity[topology] = len(rows) == len(SEEDS) and all(row.get("maturity_classification") == "MATURE" for row in rows)
    all_mature = all(maturity.values())
    late_directions = {budget: _paired_at_checkpoint(checkpoints, budget)
                       for budget in (64000, 80000, 96000)}
    stable_winner = None
    for topology in TOPOLOGIES:
        win_seed_sets = [{seed for seed, winner in directions.items() if winner == topology}
                         for directions in late_directions.values()]
        if (all(len(seeds) >= 4 for seeds in win_seed_sets)
                and len(set.intersection(*win_seed_sets)) >= 4):
            stable_winner = topology
    # Rehydrate terminal component values for the equivalence-envelope check.
    final_by = {(cell.get("topology"), int(cell.get("seed", -1))): _selected(cell) for cell in cells}
    component_pairs = []
    for row in pairs:
        seed = int(row["seed"])
        left, right = final_by.get(("P_D", seed)), final_by.get(("D_P", seed))
        component_pairs.append({
            **row,
            **{f"P_D_{metric}": _metric(left, metric) for metric in ("max_violation", "sum_violation", "worst_il_db", "ripple_db")},
            **{f"D_P_{metric}": _metric(right, metric) for metric in ("max_violation", "sum_violation", "worst_il_db", "ripple_db")},
        })
    late_improvement = any(
        row.get("significant_improvement_80k_to_96k") is True for row in checkpoints
        if int(row.get("checkpoint_budget", -1)) == BUDGET
    )
    outside_margin_wins = 0
    if stable_winner:
        for row in component_pairs:
            if row.get("lexicographic_winner") != stable_winner:
                continue
            if (not _inside_margin(row.get("delta_max_violation_P_D_minus_D_P"),
                                   row.get("P_D_max_violation"), row.get("D_P_max_violation"),
                                   absolute=EQUIVALENCE_MARGINS["max_violation_absolute"],
                                   relative=EQUIVALENCE_MARGINS["max_violation_relative"])
                    or not _inside_margin(row.get("delta_sum_violation_P_D_minus_D_P"),
                                          row.get("P_D_sum_violation"), row.get("D_P_sum_violation"),
                                          absolute=EQUIVALENCE_MARGINS["sum_violation_absolute"],
                                          relative=EQUIVALENCE_MARGINS["sum_violation_relative"])):
                outside_margin_wins += 1
            elif abs(float(row.get("delta_worst_il_db_P_D_minus_D_P") or 0.0)) > EQUIVALENCE_MARGINS["worst_il_db_absolute"]:
                outside_margin_wins += 1
            elif not _inside_margin(
                    row.get("delta_ripple_db_P_D_minus_D_P"),
                    row.get("P_D_ripple_db"), row.get("D_P_ripple_db"),
                    absolute=EQUIVALENCE_MARGINS["ripple_db_absolute"]):
                outside_margin_wins += 1
    if (all_mature and stable_winner and final_wins[stable_winner] >= 4
            and not late_improvement and outside_margin_wins >= 4):
        classification = "STAGE4C_CLEAR_CONFIRMATORY_WINNER"
    elif all_mature and not late_improvement and _equivalence_pairs(component_pairs):
        classification = "STAGE4C_PRACTICALLY_EQUIVALENT"
    else:
        classification = "STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED"
    return {
        "classification": classification,
        "all_cells_mature": all_mature,
        "mature_cells_by_topology": maturity,
        "terminal_matched_wins": {key: int(final_wins.get(key, 0)) for key in ("P_D", "D_P", "TIE", "INDETERMINATE")},
        "late_checkpoint_direction_by_seed": {str(k): {str(seed): winner for seed, winner in v.items()} for k, v in late_directions.items()},
        "stable_winner": stable_winner,
        "significant_80k_to_96k_improvement_present": late_improvement,
        "equivalence_margins": EQUIVALENCE_MARGINS,
        "primary_comparator": "feasibility_first_lexicographic; no weighted scalar score",
        "ranking_eligible": True,
    }


def write_stage4c_reports(
    run_directory: str | Path, context: Mapping[str, Any], cells: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    run = Path(run_directory)
    summary_dir = run / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_data = _checkpoint_rows(run, cells, context)
    pairs = paired_comparisons(cells)
    classification = classify_stage4c(cells, checkpoint_data, pairs)
    primary = primary_summary(cells)
    bounds = _boundary_rows(cells, checkpoint_data)
    runtime = runtime_rows(cells, checkpoint_data)
    stopbands = stopband_rows(cells)
    integrity = {
        "status": "PASS" if len(cells) == 10 and all(cell.get("status") == "COMPLETED" for cell in cells) else "FAIL",
        "complete": len(cells) == 10 and all(cell.get("status") == "COMPLETED" for cell in cells),
        "cells_expected": 10,
        "cells_present": len(cells),
        "cells_completed": sum(cell.get("status") == "COMPLETED" for cell in cells),
        "topologies_present": list(TOPOLOGIES),
        "seeds_present": list(SEEDS),
        "budget_per_cell": BUDGET,
        "population_schedule_terminal_budget": BUDGET,
        "common_validation_grid_id": COMMON_GRID_ID,
        "common_validation_grid_sha256": COMMON_GRID_SHA256,
    }
    _write_json(run / "metadata" / "integrity_check.json", integrity)
    _write_json(run / "metadata" / "run_completion.json", {
        "status": "COMPLETED" if integrity["complete"] else "INCOMPLETE",
        "study_type": STUDY_TYPE, "protocol_revision": PROTOCOL_REVISION,
        "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
        "cells_completed": integrity["cells_completed"], "cells_expected": 10,
    })
    _write_csv(summary_dir / "primary_summary.csv", primary)
    _write_csv(summary_dir / "paired_comparisons.csv", pairs)
    _write_csv(summary_dir / "convergence.csv", checkpoint_data)
    _write_csv(summary_dir / "bound_pressure_summary.csv", bounds)
    _write_csv(summary_dir / "runtime_accounting_summary.csv", runtime)
    _write_csv(summary_dir / "stopband_diagnostics.csv", stopbands)
    limitations = (
        "Stage 4C compares only P_D and D_P under the provisional MLIT / T1_SYMMETRIC_5IDT model and fixed 50/50-ohm ports.\n\n"
        "This is not COM calibration, a material comparison, a bound-expansion study, a production-feasibility claim, or an impedance study.\n"
    )
    (summary_dir / "scientific_limitations.md").write_text(limitations, encoding="utf-8", newline="\n")
    report = {
        **classification,
        "integrity": integrity,
        "budget_per_cell": BUDGET,
        "total_unique_evaluations": 960000,
        "checkpoint_lattice": list(CHECKPOINTS),
        "common_validation_grid_id": COMMON_GRID_ID,
        "common_validation_grid_sha256": COMMON_GRID_SHA256,
    }
    lines = [
        "# Stage 4C final execution report", "",
        f"- Integrity: `{integrity['status']}` ({integrity['cells_completed']}/10 cells).",
        f"- Classification: `{classification['classification']}`.",
        "- All final topology metrics use the same 9,113-point common validation grid.",
        "- Comparator: feasibility-first lexicographic; no weighted scalar score.",
        "- Stopband labels: stop_1 = 703–748 MHz; stop_2 = 832–862 MHz.",
        "- This report is a post-run interpretation and does not authorize follow-up production.",
    ]
    (summary_dir / "final_execution_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    report["primary_summary"] = primary
    report["paired_comparisons"] = pairs
    report["stopband_diagnostics"] = stopbands
    return report


def validate_stage4c_review_contract(run_directory: str | Path, repository_root: str | Path) -> dict[str, Any]:
    """Fail closed unless this is a complete Stage 4C production review input."""
    from .github_review import ReviewExportError, _canonical_json_sha256, load_review_spec

    run = Path(run_directory).resolve()
    raw = _read_json(run / "run_manifest.json")
    status = _read_json(run / "status.json")
    metadata = raw.get("experiment_metadata") or {}
    manifest = _read_json(run / "optimizer" / "metadata" / "stage4c_run_manifest.json")
    spec = raw.get("review_spec")
    if not isinstance(spec, Mapping) or _canonical_json_sha256(spec) != raw.get("review_spec_sha256"):
        raise ReviewExportError("Stage 4C frozen review spec missing or hash mismatch")
    declared_spec = load_review_spec("hybrid_stage4c", repository_root)
    if dict(spec) != declared_spec:
        raise ReviewExportError("Stage 4C run uses a different frozen review spec")
    if raw.get("review_stage") != "stage4c" or spec.get("stage") != "stage4c":
        raise ReviewExportError("Stage 4C review stage mismatch")
    expected_path = f"reports/experiment_reviews/stage4c/{raw.get('run_id', '')}"
    if raw.get("review_output_dir", "").replace("\\", "/").strip("/") != expected_path:
        raise ReviewExportError("Stage 4C review output path is not canonical")
    if raw.get("study_type") != STUDY_TYPE or metadata.get("study_type") != STUDY_TYPE:
        raise ReviewExportError("Stage 4C study type mismatch")
    if manifest.get("study_type") != STUDY_TYPE or manifest.get("protocol_revision") != PROTOCOL_REVISION:
        raise ReviewExportError("Stage 4C protocol manifest identity mismatch")
    if manifest.get("mode") != "production":
        raise ReviewExportError("Stage 4C review export requires production mode")
    checks = (
        ("topologies", list(TOPOLOGIES)), ("seeds", list(SEEDS)),
        ("budget_per_cell", BUDGET), ("population_schedule_terminal_budget", BUDGET),
        ("checkpoints", list(CHECKPOINTS)), ("search_grid_sha256", SEARCH_GRID_SHA256),
        ("common_validation_grid_id", COMMON_GRID_ID),
        ("common_validation_grid_sha256", COMMON_GRID_SHA256),
    )
    for key, expected in checks:
        if manifest.get(key) != expected or metadata.get(key) != expected:
            raise ReviewExportError(f"Stage 4C {key} mismatch")
    if manifest.get("run_id") != raw.get("run_id") or manifest.get("source_commit_sha") != raw.get("source_commit_sha"):
        raise ReviewExportError("Stage 4C source/run identity mismatch")
    if manifest.get("run_storage_policy") != "external_persistent_v1" or raw.get("run_storage_policy") != "external_persistent_v1":
        raise ReviewExportError("Stage 4C production storage policy mismatch")
    if manifest.get("required_storage_root") != PRODUCTION_RUN_ROOT:
        raise ReviewExportError("Stage 4C frozen production root mismatch")
    try:
        Path(raw.get("persistent_run_root", "")).resolve(strict=False).relative_to(
            Path(PRODUCTION_RUN_ROOT).resolve(strict=False)
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise ReviewExportError("Stage 4C orchestration run is outside the frozen external production root") from exc
    frozen_flags = {
        "initial_population_rule": "18 * topology_dimension",
        "initial_populations": {"P_D": 234, "D_P": 234},
        "production_early_stop": False,
        "cold_start": True,
        "warm_start": False,
        "parent_transfer": False,
        "topology_transfer": False,
        "historical_population_injection": False,
    }
    for key, expected in frozen_flags.items():
        if manifest.get(key) != expected or metadata.get(key) != expected:
            raise ReviewExportError(f"Stage 4C {key} mismatch")
    if "codex_session_id" in manifest or "callback_enabled" in manifest:
        raise ReviewExportError("Stage 4C manifest contains deprecated session/callback metadata")
    if metadata.get("source_impedance_ohm") != 50.0 or metadata.get("load_impedance_ohm") != 50.0:
        raise ReviewExportError("Stage 4C port termination mismatch")
    if status.get("optimizer_state", status.get("state")) != "COMPLETED":
        raise ReviewExportError("Stage 4C optimizer is not completed")
    matrix = expected_matrix()
    for cell in matrix:
        topology, seed = cell["topology"], cell["seed"]
        cell_dir = run / "optimizer" / "optimization" / topology / f"seed{seed}"
        for filename in ("cell_result.json", "cell_status.json"):
            item = _read_json(cell_dir / filename)
            if (item.get("topology") != topology or int(item.get("seed", -1)) != seed
                    or int(item.get("budget", -1)) != BUDGET
                    or int(item.get("population_schedule_terminal_budget", -1)) != BUDGET
                    or item.get("common_validation_grid_id") != COMMON_GRID_ID
                    or item.get("cold_start") is not True
                    or item.get("warm_start") is not False
                    or item.get("parent_transfer") is not False
                    or item.get("topology_transfer") is not False):
                raise ReviewExportError(f"Stage 4C cell protocol mismatch: {topology}/seed{seed}")
    return {"status": "PASS", "expected_cells": len(matrix), "grid_id": COMMON_GRID_ID,
            "review_stage": "stage4c", "canonical_path": expected_path}


def export_stage4c_review(
    run_directory: str | Path, *, repository_root: str | Path,
    destination: str | Path | None = None,
) -> dict[str, Any]:
    """Validate the exact Stage 4C matrix before calling the generic exporter."""
    validate_stage4c_review_contract(run_directory, repository_root)
    from .github_review import export_review
    return export_review(run_directory, destination=destination, repository_root=repository_root)


__all__ = [
    "EQUIVALENCE_MARGINS", "STAGE4C_REQUIRED_ARTIFACTS", "classify_stage4c",
    "convergence_rows", "export_stage4c_review", "paired_comparisons",
    "primary_summary", "runtime_rows", "stopband_rows",
    "validate_stage4c_review_contract", "write_stage4c_reports",
]
