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
from ..optimizers.selection import DEFAULT_COMPARATOR
from .candidate_integrity import validated_hybrid_rank_key
from ..studies.hybrid_stage4c import (
    BUDGET, CHECKPOINTS, COMMON_GRID_ID, COMMON_GRID_SHA256, PROTOCOL_REVISION,
    SEARCH_GRID_SHA256, SEEDS, SHAKEDOWN_BUDGET, SHAKEDOWN_CHECKPOINTS,
    SHAKEDOWN_SEED, STUDY_TYPE, TOPOLOGIES, PRODUCTION_RUN_ROOT,
    expected_matrix, expected_shakedown_matrix,
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
SIGNIFICANT_ABSOLUTE_IMPROVEMENT = 0.02
SIGNIFICANT_RELATIVE_IMPROVEMENT = 0.01
MODEL_LEVEL_MATERIALITY_THRESHOLD = 0.02


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
    """Use the optimizer's canonical candidate key for comparable finalists.

    Full hybrid candidate records require internally coherent physics, filter,
    and geometry evidence. Sparse checkpoint projections retain their limited
    compatibility path. Neither path uses a scalar optimization objective.
    """
    if not isinstance(selected, Mapping):
        return None
    # Rich hybrid records have a stronger schema and must fail closed. Sparse
    # checkpoint projections omit physics/geometry fields by construction.
    if any(field in selected for field in
           ("evaluation_status", "geometry_violations", "geometry_max_violation",
            "candidate_vector")):
        return validated_hybrid_rank_key(selected)
    if not isinstance(selected.get("feasible"), bool):
        return None
    if not isinstance(selected.get("metrics"), Mapping):
        return None
    if any(_metric(selected, key) is None for key in
           ("max_violation", "sum_violation", "worst_il_db", "ripple_db")):
        return None
    return DEFAULT_COMPARATOR.rank_key(selected)


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
                               "lexicographic_winner": _winner(left, right),
                               "P_D_feasible": None if left is None else left.get("feasible"),
                               "D_P_feasible": None if right is None else right.get("feasible")}
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
    *, checkpoints: Sequence[int] = CHECKPOINTS, terminal_budget: int = BUDGET,
) -> list[dict[str, Any]]:
    from ..studies.hybrid_stage4b import matched_cell_paths
    from ..studies.hybrid import stage4a_active_bound_diagnostics

    rows = []
    for cell in cells:
        topology, seed = str(cell["topology"]), int(cell["seed"])
        cell_dir, _manifest, _result = matched_cell_paths(run, topology, seed)
        by_budget = {}
        for checkpoint in checkpoints:
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
            terminal_hit = bool(hard_hit and int(checkpoint) == int(terminal_budget))
            raw_evidence.update({
                "grid_converged": True,
                "recovery_pending_confirmation": False,
                "boundary_pending_confirmation": terminal_hit,
                "hard_bound_unresolved": terminal_hit,
                "micro_polish_improvement": 0.0,
            })
            evidence = apply_checkpoint_evidence(
                raw_evidence, current_budget=checkpoint, terminal_budget=BUDGET,
                trace_comparator="GeometryFirstComparator",
            )
            row = {
                "topology": topology, "seed": seed, "checkpoint_budget": checkpoint,
                "selected_max_violation": _metric(selected, "max_violation"),
                "selected_sum_violation": _metric(selected, "sum_violation"),
                "selected_worst_il_db": _metric(selected, "worst_il_db"),
                "selected_ripple_db": _metric(selected, "ripple_db"),
                "selected_feasible": selected.get("feasible"),
                "historical_bound_hit": bool(hard_hit),
                "active_bound_diagnostics": json.dumps([
                    {"variable": item.get("variable"),
                     "side": "lower" if item.get("at_lower_bound") else "upper"}
                    for item in bound_diagnostics
                    if item.get("at_lower_bound") or item.get("at_upper_bound")
                ], sort_keys=True),
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
        final = by_budget.get(terminal_budget)
        if final is None:
            continue
        previous = by_budget.get(80000) if terminal_budget == BUDGET else None
        significant = _significant_improvement(
            None if previous is None else previous["selected_max_violation"],
            final["selected_max_violation"],
        )
        last_fraction = _finite(final.get("fraction_of_budget_at_last_significant_improvement"))
        mature = bool(
            final.get("convergence_evidence_complete") is True
            and final.get("grid_converged") is True
            and final.get("recovery_pending_confirmation") is False
            and final.get("hard_bound_unresolved") is False
            and final.get("boundary_pending_confirmation") is False
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
    terminal_counts: Counter[tuple[str, str]] = Counter()
    events: dict[tuple[str, int], list[dict[str, Any]]] = {}
    # Checkpoint evidence stores the decisions; detailed optimizer events stay in raw B records.
    for row in checkpoints:
        key = (str(row["topology"]), int(row["seed"]))
        diagnostics = json.loads(row.get("active_bound_diagnostics", "[]"))
        is_terminal = int(row.get("checkpoint_budget", -1)) == BUDGET
        for item in diagnostics:
            side_key = (str(item.get("variable")), str(item.get("side")))
            counts[side_key] += 1
            if is_terminal:
                terminal_counts[side_key] += 1
        events.setdefault(key, []).append({
            "checkpoint": int(row["checkpoint_budget"]),
            "historical_bound_hit": row.get("historical_bound_hit") is True,
            "boundary_pending_confirmation": row.get("boundary_pending_confirmation") is True,
            "hard_bound_unresolved": row.get("hard_bound_unresolved") is True,
            "active_bound_diagnostics": diagnostics,
        })
    rows = []
    variables = sorted({name for name, _side in counts} | {"resonator_0_pairs"})
    for variable in variables:
        rows.extend((
            {"scope": "variable", "variable": variable, "side": "lower",
             "historical_bound_hits": counts[(variable, "lower")],
             "terminal_bound_hits": terminal_counts[(variable, "lower")]},
            {"scope": "variable", "variable": variable, "side": "upper",
             "historical_bound_hits": counts[(variable, "upper")],
             "terminal_bound_hits": terminal_counts[(variable, "upper")]},
        ))
    for cell in cells:
        topology, seed = str(cell["topology"]), int(cell["seed"])
        cell_events = events.get((topology, seed), [])
        historical_keys = {
            (str(d.get("variable")), str(d.get("side")))
            for event in cell_events for d in event["active_bound_diagnostics"]
        }
        terminal_event = next((event for event in cell_events if event["checkpoint"] == BUDGET), {})
        terminal_keys = {
            (str(d.get("variable")), str(d.get("side")))
            for d in terminal_event.get("active_bound_diagnostics", [])
        }
        rows.append({
            "scope": "cell", "topology": topology, "seed": seed,
            "historical_bound_hit": any(event["historical_bound_hit"] for event in cell_events),
            "historical_active_bound_hits_by_variable": json.dumps(sorted(f"{var}:{side}" for var, side in historical_keys)),
            "terminal_active_bound_hits_by_variable": json.dumps(sorted(f"{var}:{side}" for var, side in terminal_keys)),
            "hard_bound_events": json.dumps(cell_events),
            "boundary_pending_confirmation": terminal_event.get("boundary_pending_confirmation", False),
            "hard_bound_unresolved": terminal_event.get("hard_bound_unresolved", False),
            "resonator_0_pairs_upper_hit": ("resonator_0_pairs", "upper") in historical_keys,
            "resonator_0_pairs_upper_terminal_hit": ("resonator_0_pairs", "upper") in terminal_keys,
        })
    return rows


def runtime_rows(cells: Sequence[Mapping[str, Any]], checkpoints: Sequence[Mapping[str, Any]], *, terminal_budget: int = BUDGET) -> list[dict[str, Any]]:
    final_evidence = {(r["topology"], int(r["seed"])): r for r in checkpoints if int(r["checkpoint_budget"]) == terminal_budget}
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
         "metrics": {"worst_il_db": by_key.get(("P_D", seed), {}).get("selected_worst_il_db"),
                     "ripple_db": by_key.get(("P_D", seed), {}).get("selected_ripple_db")}},
        {"feasible": by_key.get(("D_P", seed), {}).get("selected_feasible"),
         "max_violation": by_key.get(("D_P", seed), {}).get("selected_max_violation"),
         "sum_violation": by_key.get(("D_P", seed), {}).get("selected_sum_violation"),
         "metrics": {"worst_il_db": by_key.get(("D_P", seed), {}).get("selected_worst_il_db"),
                     "ripple_db": by_key.get(("D_P", seed), {}).get("selected_ripple_db")}},
    ) for seed in SEEDS}


def _material_terminal_win(
    topology: str, pair: Mapping[str, Any],
    final_by: Mapping[tuple[Any, int], Mapping[str, Any] | None],
) -> bool:
    if pair.get("lexicographic_winner") != topology:
        return False
    seed = int(pair["seed"])
    left, right = final_by.get(("P_D", seed)), final_by.get(("D_P", seed))
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    left_feasible, right_feasible = left.get("feasible"), right.get("feasible")
    winner = left if topology == "P_D" else right
    loser = right if topology == "P_D" else left
    if winner.get("feasible") is True and loser.get("feasible") is False:
        return True
    if left_feasible is False and right_feasible is False:
        left_max, right_max = _metric(left, "max_violation"), _metric(right, "max_violation")
        return left_max is not None and right_max is not None and abs(left_max - right_max) >= MODEL_LEVEL_MATERIALITY_THRESHOLD
    return False


def _terminal_equivalence_conditions(pairs: Sequence[Mapping[str, Any]]) -> bool:
    if len(pairs) != len(SEEDS):
        return False
    for pair in pairs:
        left, right = pair.get("P_D_feasible"), pair.get("D_P_feasible")
        delta = _finite(pair.get("delta_max_violation_P_D_minus_D_P"))
        if not isinstance(left, bool) or not isinstance(right, bool) or left != right:
            return False
        if delta is None or abs(delta) >= MODEL_LEVEL_MATERIALITY_THRESHOLD:
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
    # Rehydrate terminal values to apply the frozen model-level materiality rule.
    final_by = {(cell.get("topology"), int(cell.get("seed", -1))): _selected(cell) for cell in cells}
    component_pairs = []
    for row in pairs:
        seed = int(row["seed"])
        left, right = final_by.get(("P_D", seed)), final_by.get(("D_P", seed))
        component_pairs.append({
            **row,
            "P_D_feasible": None if left is None else left.get("feasible"),
            "D_P_feasible": None if right is None else right.get("feasible"),
            **{f"P_D_{metric}": _metric(left, metric) for metric in ("max_violation", "sum_violation", "worst_il_db", "ripple_db")},
            **{f"D_P_{metric}": _metric(right, metric) for metric in ("max_violation", "sum_violation", "worst_il_db", "ripple_db")},
        })
    late_improvement = any(
        row.get("significant_improvement_80k_to_96k") is True for row in checkpoints
        if int(row.get("checkpoint_budget", -1)) == BUDGET
    )
    material_terminal_wins = 0 if stable_winner is None else sum(
        _material_terminal_win(stable_winner, row, final_by) for row in component_pairs
    )
    terminal_wins = 0 if stable_winner is None else final_wins[stable_winner]
    equivalent = _terminal_equivalence_conditions(component_pairs)
    if (all_mature and stable_winner and final_wins[stable_winner] >= 4
            and terminal_wins >= 4 and not late_improvement and material_terminal_wins >= 4):
        classification = "STAGE4C_CLEAR_CONFIRMATORY_WINNER"
    elif all_mature and stable_winner is None and not late_improvement and equivalent:
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
        "model_level_materiality_threshold_max_normalized_violation": MODEL_LEVEL_MATERIALITY_THRESHOLD,
        "material_terminal_winning_pairs": material_terminal_wins,
        "terminal_equivalence_conditions_met": equivalent,
        "materiality_interpretation": (
            "0.02 is an internal computational interpretation threshold inherited from the existing "
            "significant-improvement convention. It is not a calibrated manufacturing or measurement equivalence tolerance."
        ),
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
        f"- Model-level materiality threshold: 0.02 maximum normalized violation; {classification['materiality_interpretation']}",
        "- Stopband labels: stop_1 = 703–748 MHz; stop_2 = 832–862 MHz.",
        "- This report is a post-run interpretation and does not authorize follow-up production.",
    ]
    (summary_dir / "final_execution_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    report["primary_summary"] = primary
    report["paired_comparisons"] = pairs
    report["stopband_diagnostics"] = stopbands
    return report


def write_stage4c_shakedown_reports(
    run_directory: str | Path, context: Mapping[str, Any],
    cells: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Write qualification diagnostics without topology ranking or scientific closeout."""
    from ..studies.hybrid_stage4b import matched_cell_paths

    run = Path(run_directory)
    expected_root = str(context["contract"]["storage_contract"]["qualification_root"])
    checks = {
        "shakedown_mode": manifest.get("mode") == "shakedown",
        "external_qualification_policy": manifest.get("run_storage_policy") == "external_qualification_v1",
        "external_qualification_root": manifest.get("required_storage_root") == expected_root,
        "frozen_shakedown_matrix": manifest.get("matrix") == expected_shakedown_matrix(),
        "seed_budget_checkpoints": (
            manifest.get("seeds") == [SHAKEDOWN_SEED]
            and manifest.get("budget_per_cell") == SHAKEDOWN_BUDGET
            and manifest.get("population_schedule_terminal_budget") == SHAKEDOWN_BUDGET
            and manifest.get("checkpoints") == list(SHAKEDOWN_CHECKPOINTS)
        ),
        "production_not_ranking_eligible": manifest.get("ranking_eligible") is False,
        "production_not_scientific_evidence": manifest.get("scientific_evidence") is False,
        "two_expected_cells": len(cells) == len(TOPOLOGIES),
        "topologies_exact": {row.get("topology") for row in cells} == set(TOPOLOGIES),
        "fresh_shakedown_seed": all(int(row.get("seed", -1)) == SHAKEDOWN_SEED for row in cells),
        "budget_and_terminal_schedule": all(
            int(row.get("budget", -1)) == SHAKEDOWN_BUDGET
            and int(row.get("population_schedule_terminal_budget", -1)) == SHAKEDOWN_BUDGET
            and int(row.get("unique_evaluations", -1)) == SHAKEDOWN_BUDGET
            for row in cells
        ),
        "checkpoints_exact": all(row.get("checkpoint_records") == list(SHAKEDOWN_CHECKPOINTS) for row in cells),
        "independent_cold_starts": all(
            row.get("cold_start") is True and row.get("warm_start") is False
            and row.get("parent_transfer") is False and row.get("topology_transfer") is False
            and row.get("historical_population_injection") is False
            for row in cells
        ),
        "cell_mode_is_shakedown": all(row.get("mode") == "shakedown" for row in cells),
        "common_grid_identity": all(row.get("common_validation_grid_id") == COMMON_GRID_ID for row in cells),
    }
    checkpoint_paths = []
    for row in cells:
        cell_dir, _cell_manifest, result_path = matched_cell_paths(
            run, str(row["topology"]), int(row["seed"]),
        )
        checkpoint_paths.append(
            result_path.is_file()
            and all((cell_dir / f"B{point}.json").is_file() for point in SHAKEDOWN_CHECKPOINTS)
        )
    checks["cell_results_and_checkpoints_persisted"] = all(checkpoint_paths)
    passed = all(checks.values())
    integrity = {
        "status": "PASS" if passed else "FAIL",
        "complete": passed,
        "cells_expected": len(TOPOLOGIES),
        "cells_present": len(cells),
        "cells_completed": sum(row.get("status") == "COMPLETED" for row in cells),
        "topologies_present": [row.get("topology") for row in cells],
        "seed": SHAKEDOWN_SEED,
        "budget_per_cell": SHAKEDOWN_BUDGET,
        "population_schedule_terminal_budget": SHAKEDOWN_BUDGET,
        "checkpoints": list(SHAKEDOWN_CHECKPOINTS),
        "common_validation_grid_id": COMMON_GRID_ID,
    }
    status = {
        "status": "PASS" if passed else "FAIL",
        "classification": "NON_SCIENTIFIC_STAGE4C_SHAKEDOWN_PASS" if passed else "NON_SCIENTIFIC_STAGE4C_SHAKEDOWN_FAIL",
        "checks": checks,
        "integrity": integrity,
        "ranking_eligible": False,
        "scientific_evidence": "NO",
        "production_authorized": False,
    }
    summary_rows = []
    for cell in cells:
        summary_rows.append({
            "topology": cell.get("topology"), "seed": cell.get("seed"),
            "status": cell.get("status"), "unique_evaluations": cell.get("unique_evaluations"),
            "budget_per_cell": cell.get("budget"),
            "population_schedule_terminal_budget": cell.get("population_schedule_terminal_budget"),
            "initial_population": cell.get("initial_population"),
            "checkpoint_records": json.dumps(cell.get("checkpoint_records", [])),
            "checkpoint_summaries": json.dumps(cell.get("checkpoint_summaries", []), allow_nan=False),
            "common_validation_grid_id": cell.get("common_validation_grid_id"),
            "physics_failures": cell.get("physics_failures"),
            "runtime": json.dumps(cell.get("runtime", {}), allow_nan=False),
        })
    _write_json(run / "metadata" / "integrity_check.json", integrity)
    _write_json(run / "metadata" / "shakedown_status.json", status)
    _write_json(run / "metadata" / "run_completion.json", {
        "status": "COMPLETED" if passed else "INCOMPLETE",
        "study_type": STUDY_TYPE, "protocol_revision": PROTOCOL_REVISION,
        "mode": "shakedown", "scientific_evidence": False,
        "cells_completed": integrity["cells_completed"], "cells_expected": integrity["cells_expected"],
    })
    _write_csv(run / "summary" / "shakedown_cells.csv", summary_rows)
    (run / "summary" / "shakedown_report.md").write_text(
        "# Stage 4C non-scientific shakedown\n\n"
        f"- Classification: `{status['classification']}`.\n"
        "- This 512-evaluation qualification run is not topology evidence and is not ranking eligible.\n"
        "- Production was not authorized or launched by this shakedown.\n"
        f"- Persisted outside the worktree under `{expected_root}`.\n",
        encoding="utf-8", newline="\n",
    )
    return status


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
    "MODEL_LEVEL_MATERIALITY_THRESHOLD", "STAGE4C_REQUIRED_ARTIFACTS", "classify_stage4c",
    "convergence_rows", "export_stage4c_review", "paired_comparisons",
    "primary_summary", "runtime_rows", "stopband_rows",
    "validate_stage4c_review_contract", "write_stage4c_reports",
    "write_stage4c_shakedown_reports",
]
