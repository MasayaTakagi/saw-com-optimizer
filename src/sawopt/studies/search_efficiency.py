"""Stage 3.5 search-space/optimizer efficiency study orchestration.

This runner keeps the four-arm comparison explicit and cold-started.  Legacy
DE reuses the existing continuation study, while L-SHADE reuses the existing
stateful backend and receives coordinated soft-bound expansions between
checkpoints.  Phase C only selects a candidate; Phase D is a separate config
and will refuse to run when Phase C is inconclusive.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np

from ..core.metrics import validation_grid
from ..core.models import BOUNDS, FilterDesign, NAMES
from ..io.config import load_experiment_config
from ..io.serialization import save
from ..optimization.convergence_policy import convergence_status, thresholds
from ..optimizers.selection import rank
from ..problem.evaluator import dense
from ..reporting.review_bundle import _source_hash
from .convergence import normalize_convergence_config
from .continuation import (
    ContinuationTrajectory,
    active_bounds,
    active_state_version,
    bound_state,
    boundary_probe,
    copy_bound_state,
    detect_boundary_pressure,
    next_expansion,
    run_stage32,
)
from .optimizer_ab import lshade_worker, run_workers
from .convergence_evidence import apply_checkpoint_evidence


ROOT = Path(__file__).resolve().parents[3]
ARM_NAMES = {
    ("S0", "scipy_de_legacy"): "A_S0_LEGACY",
    ("S1", "scipy_de_legacy"): "B_S1_LEGACY",
    ("S0", "lshade"): "C_S0_LSHADE",
    ("S1", "lshade"): "D_S1_LSHADE",
}


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(set().union(*(row.keys() for row in rows))) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def _clean(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return [_clean(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _clean(value.item())
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _load_s1(cfg: Mapping[str, Any]) -> tuple[dict[str, Any], Path]:
    stage = cfg.get("stage3_5", {})
    raw = Path(stage.get("s1_path", "artifacts/stage3_5/phase_a/search_space_s1.yaml"))
    path = raw if raw.is_absolute() else ROOT / raw
    if not path.is_file():
        raise FileNotFoundError(f"frozen S1 config is missing: {path}")
    import yaml
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not document.get("freeze") or not document.get("hard_bounds_unchanged"):
        raise ValueError("S1 config is not marked frozen with unchanged hard bounds")
    return document, path


def _bounds_for_strategy(cfg: Mapping[str, Any], strategy: str, s1: Mapping[str, Any]):
    state = bound_state(cfg)
    if strategy == "S1":
        supplied = s1.get("bounds", {})
        for name in NAMES:
            if name not in supplied:
                raise ValueError(f"S1 is missing bounds for {name}")
            item = supplied[name]
            hard = [float(value) for value in item["hard"]]
            baseline_hard = state[name]["hard"]
            if not np.allclose(hard, baseline_hard, rtol=0.0, atol=0.0):
                raise ValueError(f"S1 hard bounds changed for {name}")
            initial = [float(value) for value in item["initial"]]
            if initial[0] >= initial[1] or initial[0] < hard[0] or initial[1] > hard[1]:
                raise ValueError(f"invalid S1 bounds for {name}")
            state[name]["initial"] = list(initial)
            state[name]["active"] = list(initial)
            state[name]["lower_steps"] = [float(value) for value in item.get("lower_steps", [])]
            state[name]["upper_steps"] = [float(value) for value in item.get("upper_steps", [])]
            state[name]["expandable"] = bool(item.get("expandable", state[name]["expandable"]))
    for name in NAMES:
        if state[name]["active"][0] >= state[name]["active"][1]:
            raise ValueError(f"strategy {strategy} accidentally freezes {name}")
    return state


def _arm_config(base: Mapping[str, Any], *, phase: str, strategy: str, optimizer: str,
                state: Mapping[str, Any], seeds: list[int], budgets: list[int], workers: int):
    cfg = copy.deepcopy(base)
    cfg["experiment_name"] = f"stage3_5_{phase}_{strategy}_{optimizer}"
    cfg["seeds"] = list(seeds)
    cfg["wirings"] = ["center_outer_same"]
    cfg.setdefault("convergence", {})["seeds"] = list(seeds)
    cfg["convergence"]["min_cold_seeds"] = len(seeds)
    section = cfg.setdefault("optimizer_validation", {})
    section["budgets"] = list(budgets)
    section["optional_max_budget"] = None
    section["auto_escalate"] = False
    if phase == "screening":
        section["minimum_convergence_budget"] = max(budgets)
        cfg["convergence"]["stage3_4b"] = False
    else:
        section["minimum_convergence_budget"] = 32_000
        cfg["convergence"]["stage3_4b"] = True
        cfg["convergence"]["min_grid_converged_seed_fraction"] = .875
    section.setdefault("parallel", {})["production_workers"] = max(1, min(int(workers), len(seeds)))
    # Keep the canonical continuation section aligned with the arm-specific
    # design space.  Legacy reads these bounds directly, while L-SHADE uses
    # the same section for its parent-side boundary state.
    section["bounds"] = {
        name: {
            "initial": list(values["initial"]),
            "hard": list(values["hard"]),
            "expandable": bool(values.get("expandable", False)),
            "lower_steps": list(values.get("lower_steps", [])),
            "upper_steps": list(values.get("upper_steps", [])),
        }
        for name, values in ((name, state[name]) for name in NAMES)
    }
    active = active_bounds(state)
    hard = [tuple(values["hard"]) for values in (state[name] for name in NAMES)]
    cfg["stage3_5_active_bounds"] = [list(item) for item in active]
    cfg["stage3_5_hard_bounds"] = [list(item) for item in hard]
    cfg["stage3_5_design_space_version"] = 1
    cfg["stage3_5_boundary_events"] = []
    cfg["stage3_5_arm"] = {
        "phase": phase, "strategy": strategy, "optimizer": optimizer,
        "cold_start": True, "source_population_injected": False,
    }
    # The L-SHADE backend reads its checkpoints from this compact section.
    cfg["stage3_3"] = copy.deepcopy(cfg.get("stage3_3", {}))
    cfg["stage3_3"]["ab_pilot"] = {
        "wirings": ["center_outer_same"], "seeds": list(seeds), "budgets": list(budgets),
        "population_schedule_terminal_budget": max(budgets),
    }
    cfg["stage3_3"]["production_parallel"] = {
        "production_workers": max(1, min(int(workers), len(seeds))),
        "blas_threads_per_worker": 1,
    }
    cfg["stage3_3"]["lshade"] = copy.deepcopy(cfg["stage3_3"].get("lshade", {}))
    cfg["stage3_3"]["lshade"]["hard_max_budget"] = max(budgets)
    cfg["stage3_3"]["lshade"]["population_schedule_terminal_budget"] = max(budgets)
    return cfg


def _record_budget(record: Mapping[str, Any]) -> int:
    return int(record.get("requested_unique_design_budget", record.get("actual_unique_design_evaluations", 0)))


def _record_rank(record: Mapping[str, Any]) -> tuple[float, ...]:
    """Return the search/checkpoint rank kept for provenance."""
    value = record.get("validated_rank_tuple")
    return tuple(float(item) for item in value) if value is not None else tuple(float(item) for item in rank(record))


def _record_validation(record: Mapping[str, Any]) -> Mapping[str, Any]:
    value = record.get("validation_record")
    return value if isinstance(value, Mapping) else record


def _record_validation_rank(record: Mapping[str, Any]) -> tuple[float, ...]:
    return tuple(float(item) for item in rank(_record_validation(record)))


def _record_design(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return _record_validation(record).get("design", record.get("design", {}))


def _lshade_arm(out: Path, cfg: dict[str, Any], seeds: list[int], budgets: list[int], workers: int,
                *, resume: bool = False):
    """Run L-SHADE checkpoint-by-checkpoint with parent-coordinated expansion."""
    state = bound_state(cfg)
    version = 1
    boundary_events: list[dict[str, Any]] = []
    design_versions = [{
        "wiring": "center_outer_same", "design_space_version": version,
        "active_bounds": active_state_version(state), "reason": "initial",
    }]
    pressure_history: dict[tuple[str, str], int] = {}
    all_records: list[dict[str, Any]] = []
    required_persistence = int(cfg.get("optimizer_validation", {}).get(
        "boundary_detection", {}).get("required_persistent_checkpoints", 2))
    for budget_index, budget in enumerate(sorted(set(int(value) for value in budgets))):
        cfg["stage3_5_active_bounds"] = [list(item) for item in active_bounds(state)]
        cfg["stage3_5_hard_bounds"] = [list(values["hard"]) for values in state.values()]
        cfg["stage3_5_design_space_version"] = version
        cfg["stage3_5_boundary_events"] = copy.deepcopy(boundary_events)
        # Every checkpoint after the first must load the same cold trajectory
        # checkpoint.  ``resume`` only controls whether an already completed
        # first checkpoint may be reused.
        checkpoint_resume = bool(resume or budget_index > 0)
        tasks = [(str(out), cfg, "center_outer_same", seed, budget, checkpoint_resume) for seed in seeds]
        records = run_workers(
            tasks, lshade_worker,
            max(1, min(int(workers), len(seeds))),
            int(cfg.get("optimizer_validation", {}).get("parallel", {}).get("blas_threads_per_worker", 1)),
        )
        records = [dict(record) for record in records]
        for record in records:
            record["stage3_5_strategy"] = cfg["stage3_5_arm"]["strategy"]
            record["stage3_5_optimizer"] = "lshade"
            record["stage3_5_phase"] = cfg["stage3_5_arm"]["phase"]
        all_records.extend(records)
        pressure = detect_boundary_pressure(records, state, cfg)
        for key in list(pressure_history):
            if not any((item["variable"], item["direction"]) == key for item in pressure.get("pressures", [])):
                pressure_history[key] = 0
        for item in pressure.get("pressures", []):
            key = (item["variable"], item["direction"])
            pressure_history[key] = pressure_history.get(key, 0) + 1
            event = dict(item, budget=budget, wiring="center_outer_same",
                         design_space_version=version,
                         persistence_count=pressure_history[key])
            if pressure_history[key] < required_persistence:
                event["event"] = "boundary_pressure"
                boundary_events.append(event)
                continue
            probe = boundary_probe(records, cfg, cfg["convergence"]["impedance_ohm"],
                                   "center_outer_same", state, item)
            event["probe"] = probe
            event["probe_positive"] = bool(probe.get("positive"))
            target = next_expansion(state, item) if probe.get("positive") else None
            if target is None:
                event["event"] = "hard_bound_limited" if probe.get("hard_bound_reached") else "boundary_probe_no_improvement"
                boundary_events.append(event)
                continue
            old_state = copy_bound_state(state)
            state[item["variable"]]["active"][0 if item["direction"] == "lower" else 1] = target
            version += 1
            event.update({"event": "bound_expansion", "new_bound": float(target),
                          "new_design_space_version": version})
            boundary_events.append(event)
            design_versions.append({
                "wiring": "center_outer_same", "design_space_version": version,
                "active_bounds": active_state_version(state), "reason": "positive_boundary_probe",
                "trigger": event,
            })
            pressure_history = {}
            break
    return {
        "records": all_records,
        "boundary_events": boundary_events,
        "design_space_versions": design_versions,
        "stagnation_events": [],
        "final_state": state,
    }


def _arm_records(arm_dir: Path, optimizer: str) -> list[dict[str, Any]]:
    if optimizer == "scipy_de_legacy":
        paths = sorted(arm_dir.glob("trials/center_outer_same__B*__seed*.json"))
    else:
        paths = sorted(arm_dir.glob("trials/lshade/center_outer_same/seed*/B*.json"))
    records = []
    for path in paths:
        if path.name == "optimizer_checkpoint.json":
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        record["_arm_path"] = str(path.relative_to(arm_dir))
        records.append(record)
    return records


def _common_grid(cfg: Mapping[str, Any], records: list[Mapping[str, Any]],
                 baseline_records: Iterable[Mapping[str, Any]] = ()) -> np.ndarray:
    grid = np.unique(np.asarray(validation_grid(cfg["spec"], cfg), dtype=float))
    z0 = float(cfg.get("convergence", {}).get("impedance_ohm", 50.0))
    # The grid is frozen from the Stage 3.4b final eight designs plus every
    # current-arm checkpoint design.  It is deliberately independent of the
    # optimizer's private search grid.
    for record in [*baseline_records, *records]:
        try:
            design = FilterDesign(**dict(_record_design(record)))
            refined, _payload = dense(design, cfg, z0, z0, wiring="center_outer_same", validation=True)
            grid = np.unique(np.r_[grid, refined])
        except (KeyError, TypeError, ValueError, np.linalg.LinAlgError, FloatingPointError):
            continue
    return grid


def _grid_id(grid: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(grid, dtype="<f8").tobytes()).hexdigest()


def _baseline_common_rows(cfg: Mapping[str, Any], records: Sequence[Mapping[str, Any]], grid: np.ndarray,
                          grid_id: str) -> list[dict[str, Any]]:
    rows = []
    z0 = float(cfg.get("convergence", {}).get("impedance_ohm", 50.0))
    for record in records:
        design = FilterDesign(**dict(_record_design(record)))
        _f, (validated, _net, _sim) = dense(
            design, cfg, z0, z0, wiring="center_outer_same", base_grid=grid, passes=0, validation=True,
        )
        validated = dict(validated)
        rows.append({
            "source": "stage3_4b_final",
            "arm": "BASELINE_STAGE34B",
            "seed": int(record["seed"]),
            "budget": _record_budget(record),
            "common_validation_grid_id": grid_id,
            "common_validation_frequency_count": int(len(grid)),
            "design": json.dumps(_clean(dict(_record_design(record))), sort_keys=True),
            "historical_search_rank": json.dumps(list(_record_rank(record))),
            "historical_validation_rank": json.dumps(list(_record_validation_rank(record))),
            "feasible": bool(validated.get("feasible", False)),
            "max_violation": float(validated.get("max_violation", np.inf)),
            "sum_violation": float(sum(validated.get("violations", {}).values())),
            "worst_il_db": float(validated.get("metrics", {}).get("worst_il_db", np.inf)),
            "ripple_db": float(validated.get("metrics", {}).get("ripple_db", np.inf)),
            "validated_rank_tuple": list(float(value) for value in rank(validated)),
            "validation_error": "",
        })
    return rows


def _common_targets(baseline_rows: Sequence[Mapping[str, Any]], grid_id: str, grid: np.ndarray) -> dict[str, Any]:
    ordered = sorted(tuple(float(value) for value in row["validated_rank_tuple"]) for row in baseline_rows)
    if len(ordered) != 8:
        raise ValueError(f"common-grid baseline requires 8 rows, got {len(ordered)}")
    return {
        "grid_id": grid_id,
        "frequency_count": int(len(grid)),
        "source": "Stage3.4b final eight designs re-evaluated on the common grid",
        "T_best_common": list(ordered[0]),
        "T_median_common": list(ordered[(len(ordered) - 1) // 2]),
        "T_worst_common": list(ordered[-1]),
        "seed_count": len(ordered),
    }


def _validated_rows(cfg: Mapping[str, Any], arm_records: Mapping[str, list[dict[str, Any]]],
                    baseline_records: Sequence[Mapping[str, Any]] = ()):
    all_records = [record for records in arm_records.values() for record in records]
    grid = _common_grid(cfg, all_records, baseline_records)
    grid_id = _grid_id(grid)
    baseline_rows = _baseline_common_rows(cfg, baseline_records, grid, grid_id)
    rows = []
    z0 = float(cfg.get("convergence", {}).get("impedance_ohm", 50.0))
    for arm, records in arm_records.items():
        for record in records:
            evidence_record = apply_checkpoint_evidence(
                record,
                current_budget=_record_budget(record),
                terminal_budget=record.get(
                    "terminal_budget",
                    record.get("population_schedule_terminal_budget"),
                ),
            )
            row = {
                "arm": arm,
                "source": "stage3_5_current_arm",
                "common_validation_grid_id": grid_id,
                "common_validation_frequency_count": int(len(grid)),
                "phase": record.get("stage3_5_phase", cfg.get("stage3_5", {}).get("phase")),
                "strategy": record.get("stage3_5_strategy", "S0"),
                "optimizer": record.get("stage3_5_optimizer", record.get("backend", "unknown")),
                "seed": int(record["seed"]),
                "budget": _record_budget(record),
                "unique_decoded_evaluations": int(record.get("unique_decoded_evaluations", record.get("actual_unique_design_evaluations", 0))),
                "objective_calls": int(record.get("objective_calls", 0)),
                "cache_hits": int(record.get("cache_hits", 0)),
                "cache_hit_rate": record.get("cache_hit_rate"),
                "duplicate_decoded_attempts": record.get("duplicate_decoded_attempts"),
                "duplicate_rate": record.get("duplicate_decoded_rate"),
                "elapsed_s": record.get("elapsed_s"),
                "optimizer_wall_time_s": record.get("optimizer_wall_time_s"),
                "validation_wall_time_s": record.get("validation_wall_time_s"),
                "total_trial_wall_time_s": record.get("total_trial_wall_time_s"),
                "terminal_budget": record.get(
                    "terminal_budget", record.get("population_schedule_terminal_budget")
                ),
                "current_budget": record.get("current_budget", _record_budget(record)),
                "initial_population": record.get("initial_population"),
                "current_population": record.get("current_population", record.get("population_size")),
                "population_schedule_identifier": record.get("population_schedule_identifier"),
                "population_schedule_version": record.get("population_schedule_version"),
                "design_space_version": int(record.get("design_space_version", 1)),
                # Certificate evidence is fail-closed.  Missing evidence must
                # never be converted into a PASS by an optimistic default.
                "grid_converged": evidence_record.get("grid_converged"),
                "recovery_fired_at_current_checkpoint": bool(record.get("recovery_fired_at_current_checkpoint", False)),
                "recovery_pending_confirmation": evidence_record.get("recovery_pending_confirmation"),
                "boundary_pressure_first_seen_at_current_checkpoint": bool(record.get("boundary_pressure_first_seen_at_current_checkpoint", False)),
                "boundary_pending_confirmation": evidence_record.get("boundary_pending_confirmation"),
                "hard_bound_reached_by_variable": record.get("hard_bound_reached_by_variable", {}),
                "hard_bound_unresolved": evidence_record.get("hard_bound_unresolved"),
                "micro_polish_improvement": evidence_record.get("micro_polish_improvement"),
                "fraction_of_budget_at_last_significant_improvement": evidence_record.get(
                    "fraction_of_budget_at_last_significant_improvement"
                ),
                "convergence_evidence_complete": bool(evidence_record.get("complete")),
                "convergence_evidence_missing_fields": list(evidence_record.get("missing_fields", [])),
                "boundary_events": int(sum(1 for event in record.get("boundary_events", []) if event.get("event") in {"bound_expansion", "hard_bound_limited"})),
            }
            try:
                design = FilterDesign(**dict(_record_design(record)))
                _f, (validated, _net, _sim) = dense(
                    design, cfg, z0, z0, wiring="center_outer_same", base_grid=grid, passes=0, validation=True,
                )
                validated = dict(validated)
                rank_key = tuple(float(value) for value in rank(validated))
                row.update({
                    "feasible": bool(validated.get("feasible", False)),
                    "max_violation": float(validated.get("max_violation", np.inf)),
                    "sum_violation": float(sum(validated.get("violations", {}).values())),
                    "worst_il_db": float(validated.get("metrics", {}).get("worst_il_db", np.inf)),
                    "ripple_db": float(validated.get("metrics", {}).get("ripple_db", np.inf)),
                    "validated_rank_tuple": list(rank_key),
                    "validation_gap_primary": float(rank_key[1] - _record_rank(record)[1]) if _record_rank(record) else 0.0,
                    "validation_error": "",
                })
            except (KeyError, TypeError, ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                row.update({
                    "feasible": False, "max_violation": np.inf, "sum_violation": np.inf,
                    "worst_il_db": np.inf, "ripple_db": np.inf,
                    "validated_rank_tuple": [1.0, np.inf, np.inf, np.inf, np.inf],
                    "validation_gap_primary": np.inf, "validation_error": str(exc),
                })
            rows.append(row)
    return rows, grid, grid_id, baseline_rows, _common_targets(baseline_rows, grid_id, grid)


CERTIFICATE_REQUIRED_FIELDS = (
    "grid_converged",
    "recovery_pending_confirmation",
    "boundary_pending_confirmation",
    "hard_bound_unresolved",
    "micro_polish_improvement",
    "fraction_of_budget_at_last_significant_improvement",
    "validation_gap_primary",
)


def _missing_certificate_evidence(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Return certificate fields that are absent/unknown in any checkpoint row."""
    missing: set[str] = set()
    for row in rows:
        for field in CERTIFICATE_REQUIRED_FIELDS:
            if field not in row or row.get(field) is None:
                missing.add(field)
    return sorted(missing)


def _target_from_artifact(cfg: Mapping[str, Any]) -> dict[str, Any]:
    from ..reporting.search_space_diagnostics import final_seed_records, load_stage34b_artifact
    raw = Path(cfg["stage3_5"]["baseline_artifact"])
    artifact = load_stage34b_artifact(raw if raw.is_absolute() else ROOT / raw)
    finals = final_seed_records(artifact["trials"])
    ordered = sorted((tuple(_record_validation_rank(record)) for record in finals))
    if not ordered:
        raise ValueError("Stage 3.4b artifact has no final seed targets")
    return {
        "kind": "historical_validation_provenance_only",
        "T_best": list(ordered[0]),
        "T_median": list(ordered[(len(ordered) - 1) // 2]),
        "T_worst": list(ordered[-1]),
        "seed_count": len(ordered),
    }


def _attach_targets(rows: list[dict[str, Any]], targets: Mapping[str, Any]) -> None:
    target_values = targets.get("T_median_common", targets.get("T_median"))
    if target_values is None:
        raise ValueError("common validation target is missing T_median_common")
    target = tuple(float(value) for value in target_values)
    by_key: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        by_key.setdefault((row["arm"], row["seed"]), []).append(row)
    for entries in by_key.values():
        reached = None
        for row in sorted(entries, key=lambda value: value["budget"]):
            if reached is None and tuple(row["validated_rank_tuple"]) <= target:
                reached = int(row["unique_decoded_evaluations"])
            row["reached_target"] = reached is not None
            row["first_reach_unique_evals"] = reached


def _final_rows(rows: list[Mapping[str, Any]], arm: str) -> list[Mapping[str, Any]]:
    entries = [row for row in rows if row["arm"] == arm]
    by_seed: dict[int, Mapping[str, Any]] = {}
    for row in entries:
        previous = by_seed.get(int(row["seed"]))
        if previous is None or int(row["budget"]) > int(previous["budget"]):
            by_seed[int(row["seed"])] = row
    return [by_seed[key] for key in sorted(by_seed)]


def _arm_summaries(rows: list[dict[str, Any]], targets: Mapping[str, Any]) -> dict[str, Any]:
    result = {}
    for arm in sorted({row["arm"] for row in rows}):
        final = _final_rows(rows, arm)
        evals = [row["first_reach_unique_evals"] for row in final if row.get("first_reach_unique_evals") is not None]
        primary = [float(row["validated_rank_tuple"][1]) for row in final]
        result[arm] = {
            "seed_count": len(final),
            "terminal_budget": max((int(row["budget"]) for row in final), default=0),
            "validated_median_primary": float(np.median(primary)) if primary else None,
            "validated_worst_primary": float(max(primary)) if primary else None,
            "validated_iqr_primary": float(np.percentile(primary, 75) - np.percentile(primary, 25)) if primary else None,
            "target_reach_count": len(evals),
            "median_evals_to_target": float(np.median(evals)) if evals else None,
            "median_duplicate_rate": (
                float(np.median([row["duplicate_rate"] for row in final if row.get("duplicate_rate") is not None]))
                if any(row.get("duplicate_rate") is not None for row in final) else None
            ),
            "boundary_event_count": int(sum(int(row["boundary_events"]) for row in final)),
            "recovery_event_count": int(sum(bool(row["recovery_fired_at_current_checkpoint"]) for row in final)),
            "final_rows": [dict(row) for row in final],
        }
    return result


def _phase_c1_candidates(rows: list[dict[str, Any]], cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the 32k futility gate and return arms eligible for 64k."""
    threshold = float(cfg.get("stage3_5", {}).get("material_degradation_fraction", .02))
    short_rows = [row for row in rows if int(row["budget"]) <= 32_000]
    summaries = _arm_summaries(short_rows, {})
    baseline = summaries.get("A_S0_LEGACY")
    if not baseline:
        return {"candidate_arms": [], "decision": "INCONCLUSIVE", "reason": "missing A baseline at 32k", "summaries": summaries}
    baseline_final = {int(row["seed"]): row for row in _final_rows(short_rows, "A_S0_LEGACY")}
    candidate_arms: list[str] = []
    reasons: dict[str, str] = {}

    b_final = _final_rows(short_rows, "B_S1_LEGACY")
    if b_final:
        paired = [row for row in b_final if int(row["seed"]) in baseline_final]
        non_worse = sum(
            float(row["validated_rank_tuple"][1])
            <= float(baseline_final[int(row["seed"])] ["validated_rank_tuple"][1]) * (1.0 + threshold)
            for row in paired
        )
        median_ok = summaries["B_S1_LEGACY"]["validated_median_primary"] <= baseline["validated_median_primary"] * (1.0 + threshold)
        if median_ok and non_worse >= max(3, int(np.ceil(len(paired) * .75))):
            candidate_arms.append("B_S1_LEGACY")
            reasons["B_S1_LEGACY"] = "S1 quality preserved at 32k"

    for legacy_arm, lshade_arm in (("A_S0_LEGACY", "C_S0_LSHADE"), ("B_S1_LEGACY", "D_S1_LSHADE")):
        if legacy_arm not in summaries or lshade_arm not in summaries:
            continue
        legacy = summaries[legacy_arm]
        candidate = summaries[lshade_arm]
        reduction = None
        if legacy.get("median_evals_to_target") and candidate.get("median_evals_to_target"):
            reduction = 1.0 - candidate["median_evals_to_target"] / legacy["median_evals_to_target"]
        quality_better = (
            candidate.get("validated_median_primary") is not None
            and candidate["validated_median_primary"] <= legacy["validated_median_primary"] * (1.0 - threshold)
        )
        if (reduction is not None and reduction >= .20) or quality_better:
            candidate_arms.append(lshade_arm)
            reasons[lshade_arm] = "L-SHADE passed 32k paired efficiency/quality gate"

    # The Phase C-1 gate can admit at most the three non-baseline arms; all
    # four arms were still run through 32k before this decision.
    candidate_arms = sorted(set(candidate_arms))[:3]
    return {
        "candidate_arms": candidate_arms,
        "baseline_arm": "A_S0_LEGACY",
        "decision": "CONTINUE_TO_64K" if candidate_arms else "INCONCLUSIVE",
        "reasons": reasons,
        "summaries": summaries,
    }


def _select_phase_c(rows: list[dict[str, Any]], summaries: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any]:
    threshold = float(cfg.get("stage3_5", {}).get("material_degradation_fraction", .02))
    baseline = summaries.get("A_S0_LEGACY")
    if not baseline:
        return {"decision": "INCONCLUSIVE", "reason": "missing A baseline"}
    baseline_final = {int(row["seed"]): row for row in _final_rows(rows, "A_S0_LEGACY")}
    candidates = []
    # B: safe narrowing must preserve quality and at least three paired seeds.
    b_final = _final_rows(rows, "B_S1_LEGACY")
    if b_final:
        paired = [row for row in b_final if int(row["seed"]) in baseline_final]
        non_worse = sum(
            float(row["validated_rank_tuple"][1])
            <= float(baseline_final[int(row["seed"])] ["validated_rank_tuple"][1]) * (1.0 + threshold)
            for row in paired
        )
        median_ok = summaries["B_S1_LEGACY"]["validated_median_primary"] <= baseline["validated_median_primary"] * (1.0 + threshold)
        if median_ok and non_worse >= max(3, int(np.ceil(len(paired) * .75))):
            candidates.append(("PROMOTE_S1_LEGACY", summaries["B_S1_LEGACY"]["median_evals_to_target"] or np.inf))
    # C/D: compare each optimizer with its matching Legacy arm and require
    # either a 20% target-evaluation reduction or materially better quality.
    for legacy_arm, lshade_arm, decision in (
        ("A_S0_LEGACY", "C_S0_LSHADE", "PROMOTE_S0_LSHADE"),
        ("B_S1_LEGACY", "D_S1_LSHADE", "PROMOTE_S1_LSHADE"),
    ):
        if legacy_arm not in summaries or lshade_arm not in summaries:
            continue
        legacy = summaries[legacy_arm]
        candidate = summaries[lshade_arm]
        reduction = None
        if legacy.get("median_evals_to_target") and candidate.get("median_evals_to_target"):
            reduction = 1.0 - candidate["median_evals_to_target"] / legacy["median_evals_to_target"]
        quality_better = candidate.get("validated_median_primary") is not None and candidate["validated_median_primary"] <= legacy["validated_median_primary"] * (1.0 - threshold)
        if (reduction is not None and reduction >= .20) or quality_better:
            candidates.append((decision, candidate.get("median_evals_to_target") or np.inf))
    if not candidates:
        return {"decision": "INCONCLUSIVE", "reason": "no Phase C promotion rule passed", "candidates": []}
    selected = min(candidates, key=lambda item: item[1])
    return {"decision": selected[0], "candidates": [
        {"decision": decision, "median_evals_to_target": None if not np.isfinite(value) else value}
        for decision, value in candidates
    ], "selected": selected[0]}


def _write_review_bundle(run: Path, *, phase: str, summary: Mapping[str, Any]) -> Path:
    filename = "stage3_5_phase_c_review.zip" if phase == "screening" else "stage3_5_phase_d_review.zip"
    out = ROOT / "artifacts" / "review_bundles" / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = run / "_review_bundle"
    if staging.exists():
        import shutil
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    (staging / "results").mkdir()
    (staging / "environment").mkdir()
    for path in run.rglob("*"):
        if not path.is_file() or "_review_bundle" in path.parts:
            continue
        relative = path.relative_to(run)
        destination = staging / "results" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())
    (staging / "environment" / "git_head.txt").write_text(
        subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout,
        encoding="utf-8",
    )
    (staging / "environment" / "git_status.txt").write_text(
        subprocess.run(["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True, check=True).stdout,
        encoding="utf-8",
    )
    (staging / "environment" / "git_diff.patch").write_bytes(
        subprocess.run(["git", "diff", "--binary"], cwd=ROOT, capture_output=True, check=True).stdout,
    )
    decision = summary.get("decision", summary.get("phase_c_selection", {}).get("decision", "pending"))
    manifest_path = run / "stage3_5_manifest.json"
    run_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    parity_path = run / "phase_a_evidence" / "cross_version_parity.csv"
    parity_rows = list(csv.DictReader(parity_path.read_text(encoding="utf-8-sig").splitlines())) if parity_path.is_file() else []
    parity_passes = sum(str(row.get("validation_parity_pass", "")).lower() == "true" for row in parity_rows)
    parity_max = max((float(row["max_abs_validation_rank_diff"]) for row in parity_rows if row.get("max_abs_validation_rank_diff")), default=None)
    targets = summary.get("target", {})
    review_text = (
        f"# Stage 3.5 {phase} review bundle\n\n"
        "This bundle contains cold-start search-space/optimizer evidence. "
        "It does not claim a global optimum and does not start an impedance sweep.\n\n"
        f"Decision: `{decision}`\n\n"
        "## A. Parity\n\n"
        f"- Result: `{parity_passes}/{len(parity_rows)} PASS`\n"
        f"- Maximum absolute validation-rank difference: `{parity_max}`\n"
        f"- Stage 3.4b artifact SHA-256: `{run_manifest.get('baseline_artifact_sha256', 'see manifest')}`\n"
        "- Detailed report: `results/phase_a_evidence/cross_version_parity.csv`\n\n"
        "## B. S1\n\n"
        f"- Frozen S1: `{run_manifest.get('s1_path', '')}`\n"
        f"- S1 SHA-256: `{run_manifest.get('s1_sha256', '')}`\n"
        "- Hard bounds unchanged, no variables fixed, and `io_idt_pairs` lower bound remains 8; expansion schedules are retained in the S1 YAML.\n\n"
        "## Common-grid baseline\n\n"
        f"- grid_id: `{targets.get('grid_id')}`\n"
        f"- T_best_common: `{targets.get('T_best_common')}`\n"
        f"- T_median_common: `{targets.get('T_median_common')}`\n"
        f"- T_worst_common: `{targets.get('T_worst_common')}`\n\n"
        "## C. Phase C-1 / D. Phase C-2\n\n"
        "Checkpoint-level tables are in `results/phase_c1_checkpoint_data.csv`, `results/checkpoint_data.csv`, and `results/phase_c_arm_summaries.json`.\n\n"
        f"- Phase C-1 futility gate: `{json.dumps(summary.get('phase_c1_gate', {}), ensure_ascii=False)}`\n"
        f"- L-SHADE certificate readiness: `{json.dumps(summary.get('lshade_certificate_readiness', {}), ensure_ascii=False)}`\n"
    )
    if phase == "screening":
        review_text += (
            "\nRequired stop: no Phase D, 192k/256k extension, impedance sweep, or productionization "
            "is authorized by this run.\n\nPHASE_C_COMPLETE_WAITING_FOR_REVIEW\n"
        )
        (staging / "PHASE_C_COMPLETE_WAITING_FOR_REVIEW.txt").write_text(
            "PHASE_C_COMPLETE_WAITING_FOR_REVIEW\n", encoding="utf-8"
        )
    (staging / "REVIEW_ME.md").write_text(review_text, encoding="utf-8")
    files = []
    for path in sorted(staging.rglob("*")):
        if path.is_file():
            files.append({"path": path.relative_to(staging).as_posix(), "sha256": _sha256(path), "bytes": path.stat().st_size})
    (staging / "bundle_manifest.json").write_text(json.dumps({
        "bundle_format_version": 1, "study_type": "stage3_5_search_space_optimizer_efficiency",
        "phase": phase, "source_hash": _source_hash(ROOT / "src" / "sawopt"), "files": files,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with ZipFile(out, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(staging).as_posix())
    with ZipFile(out) as archive:
        for item in files:
            if _sha256_bytes(archive.read(item["path"])) != item["sha256"]:
                raise RuntimeError(f"Stage 3.5 review bundle hash failure: {item['path']}")
    return out


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _run_arm(run: Path, base: Mapping[str, Any], *, phase: str, strategy: str, optimizer: str,
             s1: Mapping[str, Any], seeds: list[int], budgets: list[int], workers: int, resume: bool,
             segment: str = "phase_c1"):
    state = _bounds_for_strategy(base, strategy, s1)
    cfg = _arm_config(base, phase=phase, strategy=strategy, optimizer=optimizer,
                      state=state, seeds=seeds, budgets=budgets, workers=workers)
    arm = ARM_NAMES[(strategy, optimizer)] if phase == "screening" else (
        "A_S0_LEGACY" if strategy == "S0" and optimizer == "scipy_de_legacy" else "V_" + strategy + "_" + optimizer.upper()
    )
    arm_dir = run / "arms" / arm / segment
    arm_dir.mkdir(parents=True, exist_ok=True)
    if optimizer == "scipy_de_legacy":
        result = run_stage32(arm_dir, cfg, run_parallelism=False)
        records = _arm_records(arm_dir, optimizer)
        for record in records:
            record["stage3_5_arm"] = arm
            record["stage3_5_strategy"] = strategy
            record["stage3_5_optimizer"] = optimizer
            record["stage3_5_phase"] = phase
        return arm, cfg, {"summary": result, "records": records, "boundary_events": result.get("boundary_events", []), "design_space_versions": result.get("design_space_versions", [])}
    result = _lshade_arm(arm_dir, cfg, seeds, budgets, workers, resume=resume)
    records = _arm_records(arm_dir, optimizer)
    for record in records:
        record["stage3_5_arm"] = arm
        record["stage3_5_strategy"] = strategy
        record["stage3_5_optimizer"] = optimizer
        record["stage3_5_phase"] = phase
    return arm, cfg, {**result, "records": records}


def run_stage35(config_path: str | Path, run: str | Path, *, resume: bool = False) -> dict[str, Any]:
    """Run Phase C or Phase D from a frozen config."""
    config_path = Path(config_path).resolve()
    # Stage 3.5 must inherit the same historical/default normalization used by
    # the canonical continuation and optimizer A/B entry points.  Without this
    # step fields such as ``layout`` can be absent even though the inherited
    # study is otherwise valid.
    base = normalize_convergence_config(load_experiment_config(config_path))
    stage = base.get("stage3_5", {})
    phase = str(stage.get("phase", "screening"))
    if phase not in {"screening", "confirmation"}:
        raise ValueError("stage3_5.phase must be screening or confirmation")
    s1, s1_path = _load_s1(base)
    seeds = [int(value) for value in stage.get("seeds", base.get("seeds", []))]
    budgets = [int(value) for value in stage.get("budgets", [])]
    if not seeds or not budgets:
        raise ValueError("Stage 3.5 config needs explicit seeds and budgets")
    if phase == "screening" and budgets != [16_000, 32_000, 64_000]:
        raise ValueError("Phase C budgets must be exactly [16000, 32000, 64000]")
    if phase == "screening" and seeds != [20260917, 20260918, 20260919, 20260920]:
        raise ValueError("Phase C seed set is not the frozen development set")
    if phase == "confirmation" and set(seeds) & {20260917, 20260918, 20260919, 20260920}:
        raise ValueError("Phase D seeds overlap Phase C")
    workers = int(stage.get("workers", 4))
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=True)
    from ..reporting.search_space_diagnostics import final_seed_records, load_stage34b_artifact
    baseline_artifact_path = Path(stage["baseline_artifact"])
    baseline_artifact = load_stage34b_artifact(
        baseline_artifact_path if baseline_artifact_path.is_absolute() else ROOT / baseline_artifact_path
    )
    baseline_records = final_seed_records(baseline_artifact["trials"])
    if len(baseline_records) != 8:
        raise ValueError("Stage 3.4b baseline must provide exactly eight final seed records")
    historical_target = _target_from_artifact(base)
    manifest = {
        "study_type": "stage3_5_search_space_optimizer_efficiency",
        "phase": phase, "config_path": str(config_path), "config_sha256": _sha256(config_path),
        "s1_path": str(s1_path), "s1_sha256": _sha256(s1_path),
        "source_hash": _source_hash(ROOT / "src" / "sawopt"),
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
        "seeds": seeds, "budgets": budgets, "workers": workers, "cold_start": True,
        "source_population_injected": False,
        "baseline_artifact_sha256": baseline_artifact["sha256"],
        "historical_validation_target": historical_target,
        "target": {"status": "derived_after_common_validation_grid"},
    }
    save(run / "stage3_5_manifest.json", manifest)
    phase_a_copy = run / "phase_a_evidence"
    phase_a_copy.mkdir(parents=True, exist_ok=True)
    for name in (
        "search_space_diagnostics.json", "search_space_diagnostics.md",
        "search_space_elites.csv", "local_sensitivity.csv",
        "pairwise_diagnostics.csv", "cross_version_parity.csv",
        "search_space_s1.yaml", "search_space_s1_rationale.md",
    ):
        source = s1_path.parent / name
        if source.is_file():
            phase_a_copy.joinpath(name).write_bytes(source.read_bytes())
    save(phase_a_copy / "phase_a_manifest.json", {
        "source_directory": str(s1_path.parent),
        "s1_sha256": _sha256(s1_path),
        "baseline_artifact_sha256": baseline_artifact["sha256"],
    })
    if phase == "confirmation":
        selection_path = Path(stage.get("phase_c_selection", "runs/stage3_5_phase_c/phase_c_selection.json"))
        selection_path = selection_path if selection_path.is_absolute() else ROOT / selection_path
        if not selection_path.is_file():
            raise FileNotFoundError(f"Phase C selection is missing: {selection_path}")
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        decision = selection.get("decision")
        if decision not in {"PROMOTE_S1_LEGACY", "PROMOTE_S0_LSHADE", "PROMOTE_S1_LSHADE"}:
            summary = {"phase": phase, "decision": "INCONCLUSIVE", "phase_c_selection": selection,
                       "reason": "Phase C did not select exactly one promotion candidate"}
            save(run / "stage3_5_summary.json", summary)
            _write_review_bundle(run, phase=phase, summary=summary)
            return summary
        variant = {
            "PROMOTE_S1_LEGACY": ("S1", "scipy_de_legacy"),
            "PROMOTE_S0_LSHADE": ("S0", "lshade"),
            "PROMOTE_S1_LSHADE": ("S1", "lshade"),
        }[decision]
        arms = [("S0", "scipy_de_legacy"), variant]
    else:
        arms = [("S0", "scipy_de_legacy"), ("S1", "scipy_de_legacy"),
                ("S0", "lshade"), ("S1", "lshade")]
    arm_payloads = {}
    arm_cfgs = {}
    phase_c1_gate = None
    if phase == "screening":
        # Phase C-1: every arm gets the same 16k/32k cold-start screen.  The
        # A baseline is also carried through 64k; only arms admitted by the
        # 32k futility gate receive the optional 64k candidate run.
        for strategy, optimizer in arms:
            initial_budgets = budgets if (strategy, optimizer) == ("S0", "scipy_de_legacy") else budgets[:2]
            arm, arm_cfg, payload = _run_arm(
                run, base, phase=phase, strategy=strategy, optimizer=optimizer,
                s1=s1, seeds=seeds, budgets=initial_budgets, workers=workers,
                resume=resume, segment="phase_c1",
            )
            arm_cfgs[arm] = arm_cfg
            arm_payloads[arm] = payload
        c1_record_map = {arm: payload["records"] for arm, payload in arm_payloads.items()}
        c1_rows, c1_grid, c1_grid_id, _c1_baseline_rows, c1_targets = _validated_rows(
            base, c1_record_map, baseline_records
        )
        _attach_targets(c1_rows, c1_targets)
        phase_c1_gate = _phase_c1_candidates(c1_rows, base)
        save(run / "phase_c1_arm_summaries.json", phase_c1_gate["summaries"])
        _write_csv(run / "phase_c1_checkpoint_data.csv", c1_rows)
        save(run / "phase_c1_gate.json", {
            "common_validation_grid_id": c1_grid_id,
            "common_validation_frequency_count": int(len(c1_grid)),
            **phase_c1_gate,
        })
        selected = set(phase_c1_gate.get("candidate_arms", []))
        for strategy, optimizer in arms:
            arm_name = ARM_NAMES[(strategy, optimizer)]
            if arm_name not in selected:
                continue
            arm, arm_cfg, payload = _run_arm(
                run, base, phase=phase, strategy=strategy, optimizer=optimizer,
                s1=s1, seeds=seeds, budgets=budgets, workers=workers,
                resume=False, segment="phase_c2",
            )
            arm_cfgs[arm] = arm_cfg
            arm_payloads[arm] = payload
    else:
        for strategy, optimizer in arms:
            arm, arm_cfg, payload = _run_arm(
                run, base, phase=phase, strategy=strategy, optimizer=optimizer,
                s1=s1, seeds=seeds, budgets=budgets, workers=workers, resume=resume,
                segment="phase_d",
            )
            arm_cfgs[arm] = arm_cfg
            arm_payloads[arm] = payload
    record_map = {arm: payload["records"] for arm, payload in arm_payloads.items()}
    rows, grid, grid_id, baseline_rows, target = _validated_rows(base, record_map, baseline_records)
    for row in rows:
        payload = arm_payloads[row["arm"]]
        row["boundary_events"] = int(sum(1 for event in payload.get("boundary_events", []) if event.get("budget") == row["budget"]))
    _attach_targets(rows, target)
    summaries = _arm_summaries(rows, target)
    lshade_readiness = {}
    for arm in sorted(arm for arm in summaries if "LSHADE" in arm):
        arm_rows = [row for row in rows if row["arm"] == arm]
        missing = _missing_certificate_evidence(arm_rows)
        lshade_readiness[arm] = {
            "ready_for_certificate_follow_on": not missing,
            "missing_fields": missing,
        }
    output = {
        "phase": phase, "decision": "pending", "target": target,
        "common_validation_grid_id": grid_id, "common_validation_frequency_count": int(len(grid)),
        "arms": summaries, "rows": len(rows),
        "lshade_certificate_readiness": lshade_readiness,
        "baseline_common_grid_rows": len(baseline_rows),
        "historical_validation_target": historical_target,
        "phase_c1_gate": phase_c1_gate,
        "boundary_events": {arm: payload.get("boundary_events", []) for arm, payload in arm_payloads.items()},
        "design_space_versions": {arm: payload.get("design_space_versions", []) for arm, payload in arm_payloads.items()},
        "source_population_injected": False, "cold_start": True,
    }
    _write_csv(run / "checkpoint_data.csv", rows)
    _write_csv(run / "baseline_common_grid_rows.csv", baseline_rows)
    # Keep a descriptive alias for older local tooling while the review-gate
    # filename above remains the canonical handoff contract.
    _write_csv(run / "baseline_common_validation.csv", baseline_rows)
    _write_csv(run / "common_validation_grid_hz.csv", [{"frequency_hz": float(value)} for value in grid])
    save(run / "baseline_common_grid_targets.json", target)
    save(run / "common_validation_targets.json", target)
    save(run / "phase_c_arm_summaries.json", summaries)
    if phase == "screening":
        if phase_c1_gate and not phase_c1_gate.get("candidate_arms"):
            selection = {
                "decision": "INCONCLUSIVE",
                "reason": "32k futility gate admitted no candidate arm",
                "phase_c1_gate": phase_c1_gate,
            }
        else:
            selection = _select_phase_c(rows, summaries, base)
            selection["phase_c1_gate"] = phase_c1_gate
            selected = selection.get("decision", "")
            selected_arm = {
                "PROMOTE_S0_LSHADE": "C_S0_LSHADE",
                "PROMOTE_S1_LSHADE": "D_S1_LSHADE",
            }.get(selected)
            if selected_arm and not lshade_readiness.get(selected_arm, {}).get("ready_for_certificate_follow_on", False):
                selection = {
                    "decision": "INCONCLUSIVE",
                    "reason": "L-SHADE candidate lacks certificate evidence capability",
                    "candidate": selected,
                    "lshade_certificate_readiness": lshade_readiness.get(selected_arm, {}),
                    "phase_c1_gate": phase_c1_gate,
                }
        output["decision"] = selection["decision"]
        output["phase_c_selection"] = selection
        save(run / "phase_c_selection.json", selection)
    else:
        baseline_arm = "A_S0_LEGACY"
        variant_arm = next(arm for arm in summaries if arm != baseline_arm)
        baseline_by_seed = {int(row["seed"]): row for row in _final_rows(rows, baseline_arm)}
        variant_by_seed = {int(row["seed"]): row for row in _final_rows(rows, variant_arm)}
        output["decision"] = "confirmation_complete"
        output["paired_comparison"] = [
            {
                "seed": seed,
                "baseline_first_target_eval": baseline_by_seed[seed].get("first_reach_unique_evals"),
                "variant_first_target_eval": variant_by_seed[seed].get("first_reach_unique_evals"),
                "baseline_final_rank": baseline_by_seed[seed]["validated_rank_tuple"],
                "variant_final_rank": variant_by_seed[seed]["validated_rank_tuple"],
                "baseline_convergence_checkpoint": None,
                "variant_convergence_checkpoint": None,
            }
            for seed in sorted(set(baseline_by_seed) & set(variant_by_seed))
        ]
        output["certificates"] = {}
        certificate_thresholds = thresholds(base)
        for arm, arm_rows in ((arm, [row for row in rows if row["arm"] == arm]) for arm in summaries):
            missing = _missing_certificate_evidence(arm_rows)
            if missing:
                output["certificates"][arm] = {
                    "status": "inconclusive_missing_evidence",
                    "evidence": {"missing_fields": missing},
                }
                continue
            status, evidence = convergence_status(arm_rows, certificate_thresholds)
            output["certificates"][arm] = {"status": status, "evidence": evidence}
    save(run / "stage3_5_summary.json", output)
    (run / "final_report.md").write_text(_final_report(output), encoding="utf-8")
    _write_review_bundle(run, phase=phase, summary=output)
    return output


def _final_report(output: Mapping[str, Any]) -> str:
    lines = [f"# Stage 3.5 {output['phase']} report", "", f"Decision: `{output.get('decision')}`", ""]
    if output.get("phase_c_selection"):
        lines += ["## Phase C selection", "", "```json", json.dumps(output["phase_c_selection"], ensure_ascii=False, indent=2), "```", ""]
    lines += ["## Arm summaries", "", "| arm | seeds | terminal budget | median primary | target reach | median evals to target |", "|---|---:|---:|---:|---:|---:|"]
    for arm, summary in output.get("arms", {}).items():
        lines.append(f"| {arm} | {summary['seed_count']} | {summary['terminal_budget']} | {summary['validated_median_primary']} | {summary['target_reach_count']} | {summary['median_evals_to_target']} |")
    if output.get("paired_comparison"):
        lines += ["", "## Paired comparison", "", "| seed | baseline first target eval | variant first target eval | baseline final rank | variant final rank |", "|---:|---:|---:|---|---|"]
        for row in output["paired_comparison"]:
            lines.append(f"| {row['seed']} | {row['baseline_first_target_eval']} | {row['variant_first_target_eval']} | {row['baseline_final_rank']} | {row['variant_final_rank']} |")
    return "\n".join(lines) + "\n"


sha256 = _sha256
arm_config = _arm_config
bounds_for_strategy = _bounds_for_strategy
clean = _clean


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 3.5 efficiency study")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_stage35(args.config, args.run, resume=args.resume), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
