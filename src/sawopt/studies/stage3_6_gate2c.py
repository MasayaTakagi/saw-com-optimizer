"""Stage 3.6 Gate 2C joint-impedance and DOF fast screening.

Gate 2C compares the frozen ``G1_G2`` space (S0) with the already implemented
``G1_G2_G3`` space (S1).  It does not introduce a new physical parameter,
alter the objective, relax ``io_idt_pairs >= 8``, or change the DMS topology.
The runner performs a small sensitivity preflight before any production
trajectory and writes the prescribed descriptive review bundle at completion.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import multiprocessing as mp
import shutil
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Mapping
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np

from ..core.metrics import geometry, search_grid
from ..core.models import FixedProvider
from ..io.config import load_experiment_config
from ..io.run_store import initialize
from ..io.serialization import save
from ..optimizers.lshade import LShadeBackend
from ..optimizers.selection import DEFAULT_COMPARATOR, rank
from ..optimization.adaptive_frequency import critical_frequencies, new_frequency_points
from ..runtime.parallel import single_blas_thread_environment
from .convergence import normalize_convergence_config
from .optimizer_ab import lshade_record
from .stage3_6_gate2a import (
    WIRING,
    BASELINE_GROUP,
    ReleasedFilterDesign,
    decode_release,
    evaluate_released_design,
    release_bounds,
    release_dense,
    release_schema,
    release_extra_names,
    simulate_released_filter,
)


ROOT = Path(__file__).resolve().parents[3]
STUDY_TYPE = "stage3_6_gate2c_joint_impedance_dof_fast_screening"
S0_GROUP = "G1_G2"
S1_GROUP = "G1_G2_G3"
SEEDS = (20260917, 20260918)
OPTIONAL_THIRD_SEED = 20260919
BUDGET = 16000
CHECKPOINTS = (4000, 8000, 12000, 16000)
MAX_PROMOTED_CELLS = 4
CONDITIONS = (
    ("I0", 50.0, 50.0),
    ("I1", 62.5, 62.5),
    ("I2", 100.0, 100.0),
    ("I3", 50.0, 75.0),
)
METRICS = (
    "max_violation",
    "sum_violation",
    "objective",
    "worst_il_db",
    "ripple_db",
    "input_vswr",
    "output_vswr",
    "stopband_violation",
)
FINAL_BUNDLE_NAME = "stage3_6_gate2c_joint_impedance_dof_fast_screening_review.zip"
STOP_MARKER = "STAGE3_6_GATE2C_FAST_SCREEN_COMPLETE_STOP.txt"
AUDIT_STOP_MARKER = "STAGE3_6_GATE2C_DOF_AUDIT_STOP.txt"


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_text(path: str | Path, value: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _write_csv(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    rows = list(rows)
    path = Path(path)
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


def _git(args: list[str]) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"git {' '.join(args)} failed: {exc}"


def _load_s1(cfg: Mapping[str, Any]) -> tuple[dict[str, Any], Path]:
    section = cfg["stage3_6_gate2c"]
    raw = Path(section["s1_path"])
    path = raw if raw.is_absolute() else ROOT / raw
    if not path.is_file():
        raise FileNotFoundError(f"frozen S1 config is missing: {path}")
    import yaml

    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not document.get("freeze") or not document.get("hard_bounds_unchanged"):
        raise ValueError("S1 config is not marked frozen with unchanged hard bounds")
    return document, path


def _stage_section(cfg: Mapping[str, Any]) -> dict[str, Any]:
    section = dict(cfg.get("stage3_6_gate2c", {}))
    if tuple(int(value) for value in section.get("seeds", SEEDS)) != SEEDS:
        raise ValueError(f"Gate 2C base seeds must be {SEEDS}")
    if int(section.get("optional_third_seed", OPTIONAL_THIRD_SEED)) != OPTIONAL_THIRD_SEED:
        raise ValueError("Gate 2C optional third seed must be 20260919")
    if int(section.get("budget", BUDGET)) != BUDGET:
        raise ValueError("Gate 2C budget must be exactly 16000 unique evaluations")
    if tuple(int(value) for value in section.get("checkpoints", CHECKPOINTS)) != CHECKPOINTS:
        raise ValueError(f"Gate 2C checkpoints must be {CHECKPOINTS}")
    expected = [{"id": cid, "zin_ohm": zin, "zout_ohm": zout}
                for cid, zin, zout in CONDITIONS]
    if section.get("conditions") != expected:
        raise ValueError("Gate 2C conditions must be the fixed I0--I3 matrix")
    if str(section.get("s0_release_group", S0_GROUP)) != S0_GROUP:
        raise ValueError("Gate 2C S0 must remain G1_G2")
    if str(section.get("s1_release_group", S1_GROUP)) != S1_GROUP:
        raise ValueError("Gate 2C S1 must remain the existing G1_G2_G3 release")
    workers = max(1, min(int(section.get("workers", 2)), len(SEEDS)))
    threads = int(section.get("blas_threads_per_worker", 1))
    if threads < 1:
        raise ValueError("blas_threads_per_worker must be positive")
    section.update({
        "seeds": list(SEEDS),
        "optional_third_seed": OPTIONAL_THIRD_SEED,
        "budget": BUDGET,
        "checkpoints": list(CHECKPOINTS),
        "workers": workers,
        "blas_threads_per_worker": threads,
        "max_promoted_cells": min(
            MAX_PROMOTED_CELLS, max(0, int(section.get("max_promoted_cells", MAX_PROMOTED_CELLS)))
        ),
        "s0_release_group": S0_GROUP,
        "s1_release_group": S1_GROUP,
        "conditions": expected,
    })
    return section


def _b_reference(cfg: Mapping[str, Any], s1_path: Path) -> dict[str, Any]:
    raw = Path(cfg["stage3_6_gate2c"]["gate2b_b_run_dir"])
    run = raw if raw.is_absolute() else ROOT / raw
    manifest_path = run / "stage3_6_gate2b_b_manifest.json"
    summary_path = run / "stage3_6_gate2b_b_summary.json"
    grid_path = run / "results" / "common_validation_grid_hz.csv"
    grid_meta_path = run / "results" / "common_validation_grid.json"
    required = (manifest_path, summary_path, grid_path, grid_meta_path)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Gate 2B-B reference is incomplete: " + ", ".join(missing))
    manifest = _json(manifest_path)
    summary = _json(summary_path)
    if manifest.get("release_group") != S0_GROUP or manifest.get("release_dimension") != 9:
        raise ValueError("Gate 2B-B reference is not the required frozen G1_G2 S0 protocol")
    if manifest.get("s1_sha256") != _sha256(s1_path):
        raise ValueError("Gate 2B-B and Gate 2C frozen S1 hashes differ")
    if int(summary.get("completed_runs", 0)) != 27 or int(summary.get("failed_runs", 1)) != 0:
        raise ValueError("Gate 2B-B must be complete before Gate 2C")
    grid = np.asarray(np.loadtxt(grid_path, delimiter=",", skiprows=1), dtype=float)
    grid_meta = _json(grid_meta_path)
    grid_id = hashlib.sha256(np.asarray(grid, dtype="<f8").tobytes()).hexdigest()
    if grid_id != grid_meta.get("grid_id"):
        raise ValueError("Gate 2B-B common validation grid hash is inconsistent")
    if not bool(summary.get("preflight_passed")):
        raise ValueError("Gate 2B-B termination preflight was not passed")
    return {
        "run_dir": run,
        "manifest": manifest,
        "summary": summary,
        "grid": grid,
        "grid_id": grid_id,
        "grid_meta": grid_meta,
    }


def _space_snapshot(group: str, s1: Mapping[str, Any]) -> dict[str, Any]:
    active, hard, integer_indices = release_bounds(group, s1)
    schema = release_schema(group, s1)
    return {
        "group": group,
        "schema": schema,
        "active_bounds": active.tolist(),
        "hard_bounds": hard.tolist(),
        "integer_indices": list(integer_indices),
        "base_names": list(schema["base_variable_names"]),
        "extra_names": list(release_extra_names(group)),
        "io_idt_pairs_hard_lower": int(hard[1, 0]),
        "source_s1_sha256": _sha256(
            ROOT / "artifacts/stage3_5/phase_a_revised/search_space_s1.yaml"
        ),
    }


def _backend_config(cfg: Mapping[str, Any], terminal: int, hard_bounds: np.ndarray) -> dict[str, Any]:
    values = dict(cfg.get("stage3_3", {}).get("lshade", {}))
    values.update({
        "total_budget": int(terminal),
        "hard_max_budget": int(terminal),
        "population_schedule_terminal_budget": int(terminal),
        "initial_population": max(4, 18 * int(len(hard_bounds))),
        "hard_bounds": np.asarray(hard_bounds, dtype=float).tolist(),
    })
    return values


def _evaluator_factory(cfg: Mapping[str, Any], group: str, rs: float, rl: float, frequencies: np.ndarray):
    frequency_ref = [np.asarray(frequencies, dtype=float)]

    def evaluator(vector):
        design = decode_release(vector, group)
        geometry_violations: list[float] = []
        try:
            _dims, geometry_violations = geometry(design, cfg["constraints"])
            record, _net, _sim = evaluate_released_design(
                design, cfg, frequency_ref[0], rs, rl, wiring=WIRING,
            )
        except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
            record = {
                "metrics": {"worst_il_db": float("inf"), "ripple_db": float("inf"),
                            "input_vswr": float("inf"), "output_vswr": float("inf")},
                "violations": {"geometry": max(geometry_violations, default=0.0),
                                "numerical_failure": 1.0},
                "max_violation": 1.0,
                "sum_violation": 1.0 + sum(geometry_violations),
                "feasible": False,
                "failure": str(exc),
                "objective": float("inf"),
                "search_scalar_objective": float("inf"),
            }
        record = dict(record)
        record["design"] = asdict(design)
        record["source_impedance_ohm"] = float(rs)
        record["load_impedance_ohm"] = float(rl)
        record["termination"] = {
            "source_ohm": float(rs), "load_ohm": float(rl),
            "source_is_real": True, "load_is_real": True,
        }
        record.setdefault("violations", {})["geometry"] = max(geometry_violations, default=0.0)
        record["sum_violation"] = float(sum(record["violations"].values()))
        record["max_violation"] = float(max(record["violations"].values(), default=0.0))
        record["feasible"] = bool(record["max_violation"] <= 1e-10)
        return record

    evaluator.frequency_ref = frequency_ref
    return evaluator


def _release_exchange(backend, evaluator, cfg, group: str, rs: float, rl: float, checkpoint: int):
    event = {
        "event": "adaptive_frequency_check",
        "checkpoint_budget": int(checkpoint),
        "frequency_grid_version_before": int(backend.frequency_grid_version),
        "unique_designs_charged": 0,
        "added_count": 0,
        "grid_fixed": True,
        "frequencies_hz": [],
    }
    if not bool(cfg.get("stage3_3", {}).get("adaptive_frequency_exchange", True)):
        event["disabled"] = True
        event["frequency_grid_version_after"] = int(backend.frequency_grid_version)
        return event
    incumbent = backend.incumbent()
    if not incumbent:
        event["skipped"] = "no_incumbent"
        event["frequency_grid_version_after"] = int(backend.frequency_grid_version)
        return event
    design = ReleasedFilterDesign(**{
        key: incumbent["design"][key]
        for key in ReleasedFilterDesign.__dataclass_fields__
        if key in incumbent["design"]
    })
    dense_f, (_dense_result, dense_net, _dense_sim) = release_dense(
        design, cfg, rs, rl, wiring=WIRING, passes=0, validation=True,
    )
    critical = critical_frequencies(
        dense_f, dense_net, cfg["spec"],
        slope_threshold_db=float(cfg.get("dense_slope_threshold_db", .5)),
        max_points=int(cfg.get("validation", {}).get("adaptive_max_points_per_round", 64)),
    )
    added = new_frequency_points(
        evaluator.frequency_ref[0], critical,
        float(cfg.get("validation", {}).get("adaptive_frequency_tolerance_hz", 1e3)),
    )
    if len(added):
        evaluator.frequency_ref[0] = np.unique(np.r_[evaluator.frequency_ref[0], added])
        version = int(backend.frequency_grid_version) + 1
        backend.exchange_frequency_grid(evaluator.frequency_ref[0], evaluator, version=version)
        event.update({
            "event": "critical_frequency_exchange", "added_count": int(len(added)),
            "grid_fixed": False, "frequency_grid_version_after": version,
            "frequencies_hz": [float(value) for value in added],
        })
    else:
        event["frequency_grid_version_after"] = int(backend.frequency_grid_version)
    return event


def _worker(payload):
    out, cfg, group, condition, rs, rl, s1, seed, budgets, resume = payload
    out = Path(out)
    budgets = tuple(sorted(int(value) for value in budgets))
    schema = release_schema(group, s1)
    active, hard, integer_indices = release_bounds(group, s1)
    seed_dir = out / "conditions" / condition / "groups" / group / "trials" / "lshade" / WIRING / f"seed{int(seed)}"
    seed_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = seed_dir / "optimizer_checkpoint.json"
    metadata_path = seed_dir / "trajectory_metadata.json"
    disk_resume_used = bool(resume and checkpoint_path.exists())
    if disk_resume_used:
        metadata = _json(metadata_path) if metadata_path.exists() else {}
        if metadata.get("release_schema") != schema:
            raise ValueError("Gate 2C checkpoint schema mismatch")
        state = _json(checkpoint_path)
        saved = np.asarray(state.get("bounds", []), dtype=float)
        if saved.shape != active.shape or not np.array_equal(saved, active):
            raise ValueError("Gate 2C checkpoint bounds mismatch")
    else:
        metadata = {"last_completed_budget": 0, "frequency_grid_events": []}
    frequencies = np.unique(search_grid(cfg["spec"], cfg))
    evaluator = _evaluator_factory(cfg, group, rs, rl, frequencies)
    fingerprint = hashlib.sha256(json.dumps({
        "cfg": cfg, "group": group, "condition": condition,
        "zin": rs, "zout": rl, "schema": schema,
        "active": active.tolist(), "hard": hard.tolist(), "budgets": list(budgets),
    }, sort_keys=True, default=str).encode()).hexdigest()
    backend = LShadeBackend(
        active, seed=int(seed), config=_backend_config(cfg, BUDGET, hard),
        integer_indices=integer_indices, comparator=DEFAULT_COMPARATOR,
        source_config_fingerprint=fingerprint,
    )
    if disk_resume_used:
        backend.load_checkpoint(checkpoint_path)
        backend.set_evaluator(evaluator)
        if getattr(backend, "active_frequency_grid", []):
            evaluator.frequency_ref[0] = np.asarray(backend.active_frequency_grid, dtype=float)
    else:
        backend.initialize(evaluator)
        backend.set_frequency_grid(frequencies, version=1)
    events = list(metadata.get("frequency_grid_events", []))
    last_completed = int(metadata.get("last_completed_budget", 0))
    records = []
    started_wall = time.monotonic()
    started_cpu = time.process_time()
    for index, budget in enumerate(budgets):
        result_path = seed_dir / f"B{budget}.json"
        if disk_resume_used and last_completed >= budget and result_path.exists():
            records.append(_json(result_path))
            continue
        optimizer_started = time.monotonic()
        if backend.unique_evaluations < budget:
            backend.advance_to_unique_budget(budget)
        optimizer_wall = time.monotonic() - optimizer_started
        validation_started = time.monotonic()
        if budget == BUDGET:
            event = _release_exchange(backend, evaluator, cfg, group, rs, rl, budget)
        else:
            event = {
                "event": "convergence_checkpoint", "checkpoint_budget": int(budget),
                "frequency_grid_version": int(backend.frequency_grid_version),
                "grid_fixed": True, "unique_designs_charged": 0,
            }
        validation_wall = time.monotonic() - validation_started
        events.append(event)
        record = lshade_record(
            backend, WIRING, seed, budget, checkpoint_path, events,
            started_wall, started_cpu, disk_resume_used=disk_resume_used,
            trajectory_index=index, optimizer_wall_time_s=optimizer_wall,
            validation_wall_time_s=validation_wall,
            total_trial_wall_time_s=time.monotonic() - started_wall,
        )
        record.update({
            "stage3_6_group": group, "release_schema": schema,
            "release_dimension": int(schema["dimension"]),
            "condition_id": condition, "source_impedance_ohm": float(rs),
            "load_impedance_ohm": float(rl),
            "termination": {"source_ohm": float(rs), "load_ohm": float(rl),
                            "source_is_real": True, "load_is_real": True},
            "convergence_checkpoint_budget": int(budget),
            "pre_exchange": bool(budget < BUDGET),
        })
        record = _clean(record)
        save(result_path, record)
        backend.save_checkpoint(checkpoint_path)
        save(metadata_path, {
            "last_completed_budget": int(budget), "frequency_grid_events": events,
            "trajectory_semantics": "one_seed_one_release_trajectory",
            "condition_id": condition, "source_impedance_ohm": float(rs),
            "load_impedance_ohm": float(rl), "release_schema": schema,
            "active_bounds": active.tolist(), "hard_bounds": hard.tolist(),
            "checkpoints": list(budgets),
        })
        last_completed = budget
        records.append(record)
    return records


def _run_workers(tasks, workers: int, threads: int):
    with single_blas_thread_environment(threads):
        if int(workers) == 1:
            return [_worker(task) for task in tasks]
        context = mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=int(workers), mp_context=context) as pool:
            return list(pool.map(_worker, tasks))


def _mean_vector(group: str, s1: Mapping[str, Any]) -> np.ndarray:
    active, _hard, _integer = release_bounds(group, s1)
    return np.mean(active, axis=1)


def run_sensitivity_preflight(cfg: Mapping[str, Any], s1: Mapping[str, Any]) -> dict[str, Any]:
    """Verify that the existing G3 aperture release is safe to screen."""
    s0 = _mean_vector(S0_GROUP, s1)
    s0_design = decode_release(s0, S0_GROUP)
    s1_center = _mean_vector(S1_GROUP, s1)
    s0_names = release_extra_names(S0_GROUP)
    s1_names = release_extra_names(S1_GROUP)
    added = [name for name in s1_names if name not in s0_names]
    if added != ["center_aperture_um"]:
        raise ValueError(f"Gate 2C expected only center_aperture_um as added DOF, got {added}")
    active, hard, _integer = release_bounds(S1_GROUP, s1)
    # ``measure`` requires the configured stopband intervals as well as the
    # passband; use the same deterministic search grid as production.
    base_grid = np.unique(search_grid(cfg["spec"], cfg))
    observations = []
    for cid, rs, rl in (CONDITIONS[0], CONDITIONS[3]):
        for name in added:
            value_index = len(s0)
            values = {
                "lower": float(active[value_index, 0]),
                "center": float(np.mean(active[value_index])),
                "upper": float(active[value_index, 1]),
            }
            for location, value in values.items():
                vector = np.array(s1_center, dtype=float)
                vector[value_index] = value
                design = decode_release(vector, S1_GROUP)
                profile = design.section_geometry()
                dims, violations = geometry(design, cfg["constraints"])
                sim = simulate_released_filter(
                    design, FixedProvider(cfg["com"]),
                    base_grid, cfg["center"], wiring=WIRING,
                )
                base_sim = simulate_released_filter(
                    s0_design, FixedProvider(cfg["com"]), base_grid,
                    cfg["center"], wiring=WIRING,
                )
                validation_f, (validated, _net, _validation_sim) = release_dense(
                    design, cfg, rs, rl, wiring=WIRING, base_grid=base_grid,
                    passes=0, validation=True,
                )
                key_backend = LShadeBackend(
                    active, seed=7, config=_backend_config(cfg, 32, hard),
                    integer_indices=(1, 2, 3), comparator=DEFAULT_COMPARATOR,
                )
                lower_physical = np.array(s1_center, dtype=float)
                upper_physical = np.array(s1_center, dtype=float)
                lower_physical[value_index] = values["lower"]
                upper_physical[value_index] = values["upper"]
                _low_canonical, low_key = key_backend._canonical(key_backend._normalize(lower_physical))
                _high_canonical, high_key = key_backend._canonical(key_backend._normalize(upper_physical))
                observations.append({
                    "condition_id": cid, "zin_ohm": rs, "zout_ohm": rl,
                    "dof": name, "location": location, "value": value,
                    "decoded_value": float(getattr(design, name)),
                    "decoded_changes_from_s0": bool(getattr(design, name) != getattr(s0_design, name)),
                    "section_center_aperture_um": float(profile[4]["aperture_um"]),
                    "geometry_dimensions": _clean(dims),
                    "geometry_violations": _clean(violations),
                    "response_linf_from_s0": float(np.max(np.abs(
                        sim.y_parameters - base_sim.y_parameters
                    ))),
                    "validation_frequency_count": int(len(validation_f)),
                    "validation_propagated": bool(np.isfinite(float(validated["max_violation"]))),
                    "canonical_low_high_distinct": bool(low_key != high_key),
                })
    passed = all(
        row["decoded_changes_from_s0"] and row["section_center_aperture_um"] > 0
        and row["validation_propagated"] and row["canonical_low_high_distinct"]
        for row in observations
    ) and all(
        max(
            row["response_linf_from_s0"] for row in observations
            if row["condition_id"] == cid
        ) > 1e-14
        for cid, _rs, _rl in (CONDITIONS[0], CONDITIONS[3])
    )
    return {
        "passed": bool(passed),
        "scope": "existing G1_G2_G3 release; no new physics or bounds",
        "added_dofs": added,
        "conditions": ["I0", "I3"],
        "legal_value_locations": ["lower", "center", "upper"],
        "observations": observations,
        "io_idt_pairs_hard_lower": int(hard[1, 0]),
        "prohibited_dofs_released": [],
    }


def _record_path(run: Path, condition: str, group: str, seed: int, budget: int) -> Path:
    return (run / "conditions" / condition / "groups" / group / "trials"
            / "lshade" / WIRING / f"seed{int(seed)}" / f"B{int(budget)}.json")


def _final_records(run: Path, condition: str, group: str, seeds: Iterable[int]) -> list[dict[str, Any]]:
    records = []
    for seed in seeds:
        path = _record_path(run, condition, group, seed, BUDGET)
        if not path.is_file():
            raise RuntimeError(f"missing Gate 2C final record: {path}")
        record = dict(_json(path))
        record["_record_path"] = str(path.relative_to(run))
        records.append(record)
    return records


def _snapshot_records(run: Path, condition: str, group: str, seeds: Iterable[int]) -> list[dict[str, Any]]:
    records = []
    root = run / "conditions" / condition / "groups" / group / "trials" / "lshade" / WIRING
    for seed in seeds:
        for path in sorted((root / f"seed{int(seed)}").glob("B*.json")):
            record = dict(_json(path))
            record["_record_path"] = str(path.relative_to(run))
            records.append(record)
    return records


def _stopband_violation(violations: Mapping[str, Any]) -> float:
    return float(max(
        (float(value) for key, value in violations.items() if str(key).startswith("stop_")),
        default=0.0,
    ))


def _active_constraint(violations: Mapping[str, Any]) -> str:
    values = {str(key): float(value) for key, value in violations.items()}
    if not values:
        return "none"
    maximum = max(values.values())
    return ";".join(sorted(
        key for key, value in values.items() if abs(value - maximum) <= 1e-12
    ))


def _validate_record(cfg: Mapping[str, Any], record: Mapping[str, Any], grid: np.ndarray) -> dict[str, Any]:
    group = str(record["stage3_6_group"])
    design = ReleasedFilterDesign(**{
        key: record["design"][key]
        for key in ReleasedFilterDesign.__dataclass_fields__
        if key in record["design"]
    })
    _f, (validated, _net, _sim) = release_dense(
        design, cfg, float(record["source_impedance_ohm"]),
        float(record["load_impedance_ohm"]), wiring=WIRING,
        base_grid=grid, passes=0, validation=True,
    )
    validated = dict(validated)
    metrics = dict(validated.get("metrics", {}))
    violations = dict(validated.get("violations", {}))
    return {
        "condition_id": str(record["condition_id"]),
        "search_space": group,
        "zin_ohm": float(record["source_impedance_ohm"]),
        "zout_ohm": float(record["load_impedance_ohm"]),
        "seed": int(record["seed"]),
        "checkpoint_budget": int(record.get("convergence_checkpoint_budget", BUDGET)),
        "requested_unique_evaluations": int(record.get("requested_unique_design_budget", BUDGET)),
        "actual_unique_evaluations": int(record.get("unique_decoded_evaluations", 0)),
        "budget_complete": bool(record.get("unique_decoded_evaluations", 0) >= BUDGET),
        "feasible": bool(validated.get("feasible", False)),
        "max_violation": float(validated.get("max_violation", np.inf)),
        "sum_violation": float(sum(violations.values())),
        "objective": float(validated.get("objective", np.inf)),
        "worst_il_db": float(metrics.get("worst_il_db", np.inf)),
        "ripple_db": float(metrics.get("ripple_db", np.inf)),
        "input_vswr": float(metrics.get("input_vswr", np.inf)),
        "output_vswr": float(metrics.get("output_vswr", np.inf)),
        "stopband_violation": _stopband_violation(violations),
        "active_limiting_constraint": _active_constraint(violations),
        "individual_violations": json.dumps(_clean(violations), sort_keys=True),
        "all_metrics": json.dumps(_clean(metrics), sort_keys=True),
        "design": json.dumps(_clean(record["design"]), sort_keys=True),
        "boundary_repair_counts": json.dumps(
            _clean(record.get("boundary_repair_counts", {})), sort_keys=True
        ),
        "validated_rank_tuple": json.dumps([float(value) for value in rank(validated)]),
        "stop_reason": record.get("stop_reason"),
        "fraction_of_budget_at_last_significant_improvement": record.get(
            "fraction_of_budget_at_last_significant_improvement"
        ),
        "record_path": record.get("_record_path"),
    }


def _last_meaningful_evaluation(record: Mapping[str, Any]) -> int | None:
    trace = record.get("best_so_far_trace")
    if not isinstance(trace, list):
        return None
    previous = None
    last = None
    for item in trace:
        if not isinstance(item, Mapping):
            continue
        try:
            evaluation = int(item["unique_evaluation"])
            primary = float(item["rank_key"][1])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        improvement = 0.0 if previous is None else previous - primary
        relative = improvement / max(abs(previous), np.finfo(float).tiny) if previous is not None else 1.0
        if previous is None or improvement >= .02 or relative >= .01:
            last = evaluation
        previous = primary
    return last


def _convergence_lite(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for record in rows:
        by_budget = {int(record["convergence_checkpoint_budget"]): record}
        # This function is called with all checkpoint rows; the caller groups
        # them before invoking it so the placeholder is replaced below.
        del by_budget
    return output


def _build_convergence_lite(snapshot_rows: Iterable[Mapping[str, Any]], raw_final: Mapping[tuple[str, str, int], Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int], dict[int, Mapping[str, Any]]] = {}
    for row in snapshot_rows:
        key = (str(row["condition_id"]), str(row["search_space"]), int(row["seed"]))
        grouped.setdefault(key, {})[int(row["checkpoint_budget"])] = row
    output = []
    for key, final in sorted(raw_final.items()):
        snapshots = grouped.get(key, {})
        item = {
            "condition_id": key[0], "search_space": key[1], "seed": key[2],
            "zin_ohm": float(final["source_impedance_ohm"]),
            "zout_ohm": float(final["load_impedance_ohm"]),
        }
        for budget in CHECKPOINTS:
            if budget not in snapshots:
                raise RuntimeError(f"missing convergence checkpoint {key} B{budget}")
            item[f"max_violation_at_{budget}"] = float(snapshots[budget]["max_violation"])
            item[f"objective_at_{budget}"] = float(snapshots[budget]["objective"])
        last = _last_meaningful_evaluation(final)
        item["delta_4k_16k"] = item["max_violation_at_4000"] - item["max_violation_at_16000"]
        item["last_meaningful_improvement_evaluation"] = last
        item["last_meaningful_improvement_ratio"] = None if last is None else last / BUDGET
        item["improvement_after_90pct"] = None if last is None else last > .90 * BUDGET
        item["underoptimization_flag"] = bool(
            last is not None and last > .90 * BUDGET
        )
        item["stop_reason"] = final.get("stop_reason")
        output.append(item)
    return output


def _boundary_rows(rows: Iterable[Mapping[str, Any]], s1: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = list(rows)
    output = []
    for row in rows:
        group = str(row["search_space"])
        active, hard, _integer = release_bounds(group, s1)
        schema = release_schema(group, s1)
        names = list(schema["base_variable_names"]) + [item["name"] for item in schema["extra_variables"]]
        design = json.loads(row["design"])
        repairs = json.loads(row["boundary_repair_counts"])
        lower_repairs = repairs.get("lower", [0] * len(names))
        upper_repairs = repairs.get("upper", [0] * len(names))
        for index, name in enumerate(names):
            value = float(design[name])
            low, high = hard[index]
            distance = min((value - low) / (high - low), (high - value) / (high - low))
            output.append({
                "condition_id": row["condition_id"], "search_space": group,
                "seed": row["seed"], "variable": name, "value": value,
                "hard_lower": float(low), "hard_upper": float(high),
                "lower_bound_hit": bool(abs(value - low) <= 1e-10),
                "upper_bound_hit": bool(abs(value - high) <= 1e-10),
                "normalized_distance_to_nearest_hard_bound": float(distance),
                "lower_repair_count": int(lower_repairs[index]),
                "upper_repair_count": int(upper_repairs[index]),
                "active_bounds": json.dumps(active[index].tolist()),
            })
    return output


def _bottleneck_summary(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str, str], int] = {}
    rows = list(rows)
    for row in rows:
        for key in str(row["active_limiting_constraint"]).split(";"):
            counts[(row["condition_id"], row["search_space"], key)] = counts.get(
                (row["condition_id"], row["search_space"], key), 0
            ) + 1
    output = []
    for (condition, space, constraint), count in sorted(counts.items()):
        total = sum(value for (cid, grp, _key), value in counts.items()
                    if cid == condition and grp == space)
        output.append({
            "condition_id": condition, "search_space": space,
            "constraint": constraint, "count": count,
            "seed_count": total, "fraction": count / max(total, 1),
        })
    return output


def _space_comparison(rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    indexed = {(row["condition_id"], int(row["seed"]), row["search_space"]): row for row in rows}
    detail = []
    for cid, zin, zout in CONDITIONS:
        for seed in sorted({int(row["seed"]) for row in rows if row["condition_id"] == cid}):
            s0 = indexed[(cid, seed, S0_GROUP)]
            s1 = indexed[(cid, seed, S1_GROUP)]
            delta = float(s1["max_violation"] - s0["max_violation"])
            detail.append({
                "condition_id": cid, "zin_ohm": zin, "zout_ohm": zout, "seed": seed,
                "s0_max_violation": float(s0["max_violation"]),
                "s1_max_violation": float(s1["max_violation"]),
                "delta_space_max_violation": delta,
                "relative_improvement_percent": 100.0 * (-delta) / max(abs(float(s0["max_violation"])), np.finfo(float).tiny),
                "s1_better": bool(delta < 0),
                "s0_feasible": bool(s0["feasible"]), "s1_feasible": bool(s1["feasible"]),
                "s0_sum_violation": float(s0["sum_violation"]),
                "s1_sum_violation": float(s1["sum_violation"]),
            })
    aggregate = []
    for cid, zin, zout in CONDITIONS:
        selected = [row for row in detail if row["condition_id"] == cid]
        deltas = np.asarray([row["delta_space_max_violation"] for row in selected], dtype=float)
        improvements = -deltas
        if np.all(deltas < 0) and np.max(improvements) >= .01:
            label = "DOF_BENEFIT_STRONG"
        elif np.all(deltas <= .005) and np.any(improvements > 0):
            label = "DOF_BENEFIT_WEAK"
        elif np.max(deltas) - np.min(deltas) >= .01 and np.any(deltas < 0) and np.any(deltas > 0):
            label = "DOF_IMPEDANCE_INTERACTION"
        elif np.all(np.abs(deltas) < .005):
            label = "NO_MATERIAL_DOF_BENEFIT"
        else:
            label = "INCONCLUSIVE"
        aggregate.append({
            "condition_id": cid, "zin_ohm": zin, "zout_ohm": zout,
            "seed_count": len(selected),
            "mean_delta_space_max_violation": float(np.mean(deltas)),
            "median_delta_space_max_violation": float(np.median(deltas)),
            "min_delta_space_max_violation": float(np.min(deltas)),
            "max_delta_space_max_violation": float(np.max(deltas)),
            "sign_consistent_improvement": bool(np.all(deltas < 0) or np.all(deltas > 0)),
            "s1_better_seed_count": sum(row["s1_better"] for row in selected),
            "mean_relative_improvement_percent": float(np.mean([row["relative_improvement_percent"] for row in selected])),
            "decision_label": label,
        })
    return detail, aggregate


def _impedance_comparison(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for cid, zin, zout in CONDITIONS:
        for group in (S0_GROUP, S1_GROUP):
            selected = [row for row in rows if row["condition_id"] == cid and row["search_space"] == group]
            values = [float(row["max_violation"]) for row in selected]
            output.append({
                "condition_id": cid, "zin_ohm": zin, "zout_ohm": zout,
                "search_space": group, "seed_count": len(values),
                "mean_max_violation": float(np.mean(values)),
                "median_max_violation": float(np.median(values)),
                "min_max_violation": float(np.min(values)),
                "max_max_violation": float(np.max(values)),
                "feasible_seed_count": sum(bool(row["feasible"]) for row in selected),
            })
    for group in (S0_GROUP, S1_GROUP):
        selected = [row for row in output if row["search_space"] == group]
        for rank_index, row in enumerate(sorted(selected, key=lambda item: item["median_max_violation"]), start=1):
            row["mechanical_rank"] = rank_index
    return output


def _dof_utilization(rows: Iterable[Mapping[str, Any]], s1: Mapping[str, Any]) -> list[dict[str, Any]]:
    group = S1_GROUP
    active, hard, _integer = release_bounds(group, s1)
    schema = release_schema(group, s1)
    names = list(schema["base_variable_names"]) + [item["name"] for item in schema["extra_variables"]]
    output = []
    for row in rows:
        if row["search_space"] != group:
            continue
        design = json.loads(row["design"])
        for extra in schema["extra_variables"]:
            name = extra["name"]
            index = names.index(name)
            value = float(design[name])
            low, high = hard[index]
            output.append({
                "condition_id": row["condition_id"], "zin_ohm": row["zin_ohm"],
                "zout_ohm": row["zout_ohm"], "seed": row["seed"], "dof": name,
                "best_value": value, "bound_low": float(low), "bound_high": float(high),
                "normalized_position": float((value - low) / (high - low)),
                "nearest_bound_distance": float(min(value - low, high - value)),
                "normalized_distance_to_nearest_bound": float(min((value - low) / (high - low), (high - value) / (high - low))),
                "active_bounds": json.dumps(active[index].tolist()),
            })
    return output


def _boundary_probe(cfg: Mapping[str, Any], rows: Iterable[Mapping[str, Any]], s1: Mapping[str, Any], grid: np.ndarray) -> list[dict[str, Any]]:
    """Probe only legal inward moves; results are kept outside ranking."""
    rows = list(rows)
    output = []
    for cid, _zin, _zout in CONDITIONS:
        for group in (S0_GROUP, S1_GROUP):
            selected = [row for row in rows if row["condition_id"] == cid and row["search_space"] == group]
            if not selected:
                continue
            best = min(selected, key=lambda row: tuple(json.loads(row["validated_rank_tuple"])))
            design_values = json.loads(best["design"])
            schema = release_schema(group, s1)
            names = list(schema["base_variable_names"]) + [item["name"] for item in schema["extra_variables"]]
            active, hard, _integer = release_bounds(group, s1)
            repair = json.loads(best["boundary_repair_counts"])
            near = []
            for index, name in enumerate(names):
                value = float(design_values[name])
                low, high = hard[index]
                distance = min((value - low) / (high - low), (high - value) / (high - low))
                if distance <= .05:
                    near.append((index, name, value, low, high, distance))
            for index, name, value, low, high, distance in near:
                probe_values = []
                if name == "io_idt_pairs" and abs(value - 8) <= 1e-10:
                    probe_values = [9.0, 10.0]
                elif name == "reflector_electrodes" and abs(value - low) <= 1e-10:
                    probe_values = [value + 2.0, value + 4.0]
                if not probe_values:
                    output.append({
                        "condition_id": cid, "search_space": group, "seed": best["seed"],
                        "variable": name, "original_value": value,
                        "probe_value": None, "original_max_violation": float(best["max_violation"]),
                        "probe_max_violation": None, "classification": "near_bound_record_only",
                        "normalized_distance": float(distance),
                        "lower_repair_count": int(repair.get("lower", [0] * len(names))[index]),
                        "upper_repair_count": int(repair.get("upper", [0] * len(names))[index]),
                    })
                    continue
                base_vector = np.asarray([design_values[name_] for name_ in names], dtype=float)
                base_vector[index] = value
                original_design = decode_release(base_vector, group)
                _f, (original_result, _net, _sim) = release_dense(
                    original_design, cfg, float(best["zin_ohm"]), float(best["zout_ohm"]),
                    wiring=WIRING, base_grid=grid, passes=0, validation=True,
                )
                probe_results = []
                for probe_value in probe_values:
                    if probe_value < low or probe_value > high:
                        continue
                    vector = base_vector.copy()
                    vector[index] = probe_value
                    probe_design = decode_release(vector, group)
                    _f, (probe_result, _net, _sim) = release_dense(
                        probe_design, cfg, float(best["zin_ohm"]), float(best["zout_ohm"]),
                        wiring=WIRING, base_grid=grid, passes=0, validation=True,
                    )
                    probe_results.append({
                        "probe_value": float(probe_value),
                        "probe_max_violation": float(probe_result["max_violation"]),
                        "delta_max_violation": float(probe_result["max_violation"] - original_result["max_violation"]),
                    })
                deltas = [item["delta_max_violation"] for item in probe_results]
                if deltas and all(delta > 0 for delta in deltas):
                    classification = "persistent_hard_boundary_pressure"
                elif deltas and all(delta < 0 for delta in deltas):
                    classification = "optimizer_artifact_or_accidental_hit"
                elif deltas:
                    classification = "inconclusive"
                else:
                    classification = "inconclusive"
                for item in probe_results or [{"probe_value": None, "probe_max_violation": None, "delta_max_violation": None}]:
                    output.append({
                        "condition_id": cid, "search_space": group, "seed": best["seed"],
                        "variable": name, "original_value": value,
                        "probe_value": item["probe_value"],
                        "original_max_violation": float(original_result["max_violation"]),
                        "probe_max_violation": item["probe_max_violation"],
                        "delta_max_violation": item["delta_max_violation"],
                        "classification": classification,
                        "normalized_distance": float(distance),
                        "lower_repair_count": int(repair.get("lower", [0] * len(names))[index]),
                        "upper_repair_count": int(repair.get("upper", [0] * len(names))[index]),
                    })
    return output


def _promotion_decisions(rows: Iterable[Mapping[str, Any]], max_cells: int) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    rows = list(rows)
    by_key = {(row["condition_id"], int(row["seed"]), row["search_space"]): row for row in rows}
    medians = {}
    for cid, _zin, _zout in CONDITIONS:
        for group in (S0_GROUP, S1_GROUP):
            medians[(cid, group)] = float(np.median([
                by_key[(cid, seed, group)]["max_violation"] for seed in SEEDS
            ]))
    s0_order = [cid for cid, _zin, _zout in sorted(CONDITIONS, key=lambda item: medians[(item[0], S0_GROUP)])]
    s1_order = [cid for cid, _zin, _zout in sorted(CONDITIONS, key=lambda item: medians[(item[0], S1_GROUP)])]
    decisions = []
    for cid, zin, zout in CONDITIONS:
        deltas = [by_key[(cid, seed, S1_GROUP)]["max_violation"] - by_key[(cid, seed, S0_GROUP)]["max_violation"] for seed in SEEDS]
        rule_a = all(delta < 0 for delta in deltas)
        rule_b = (min(deltas) <= -.015 and max(deltas) <= .005)
        s1_is_absolute_best = medians[(cid, S1_GROUP)] <= min(medians.values())
        rule_c = bool(s1_is_absolute_best)
        rule_d = s0_order.index(cid) != s1_order.index(cid)
        eligible = bool(rule_a or rule_b or rule_c or rule_d)
        priority = (
            0 if rule_c else 1,
            0 if cid == "I1" else 1,
            -float(max(-delta for delta in deltas)),
            0 if cid == "I3" else (1 if cid == "I2" else 2),
            0 if cid == "I0" else 1,
        )
        decisions.append({
            "condition_id": cid, "zin_ohm": zin, "zout_ohm": zout,
            "delta_seed_20260917": deltas[0], "delta_seed_20260918": deltas[1],
            "rule_a_both_seeds_improve": rule_a,
            "rule_b_one_improves_015_other_regression_le_005": rule_b,
            "rule_c_absolute_best_candidate": rule_c,
            "rule_d_ranking_change": rule_d,
            "s0_median_rank": s0_order.index(cid) + 1,
            "s1_median_rank": s1_order.index(cid) + 1,
            "eligible": eligible, "priority": json.dumps(priority),
            "decision": "pending",
        })
    candidates = sorted(
        [row for row in decisions if row["eligible"]],
        key=lambda row: tuple(json.loads(row["priority"])),
    )[:max_cells]
    selected = {(row["condition_id"], S1_GROUP) for row in candidates}
    for row in decisions:
        row["decision"] = "PROMOTE_THIRD_SEED" if (row["condition_id"], S1_GROUP) in selected else "NOT_PROMOTED"
    return decisions, sorted(selected)


def _plot_outputs(
    space_aggregate: list[dict[str, Any]],
    impedance_rows: list[dict[str, Any]],
    dof_rows: list[dict[str, Any]],
    boundary_rows: list[dict[str, Any]],
    out: Path,
) -> list[Path]:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    labels = [row["condition_id"] for row in space_aggregate]
    values = [row["median_delta_space_max_violation"] for row in space_aggregate]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(labels, values, color=["tab:green" if value < 0 else "tab:red" for value in values])
    ax.axhline(0, color="black", linewidth=.8)
    ax.set_ylabel("Median S1 − S0 max violation")
    ax.set_title("Gate 2C search-space effect by impedance")
    fig.tight_layout()
    path = out / "s1_minus_s0_by_impedance.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for group, marker in ((S0_GROUP, "o"), (S1_GROUP, "s")):
        selected = [row for row in impedance_rows if row["search_space"] == group]
        ax.scatter(
            [f"{row['condition_id']}\n{row['zin_ohm']:g}/{row['zout_ohm']:g}" for row in selected],
            [row["median_max_violation"] for row in selected], marker=marker, label=group,
        )
    ax.set_ylabel("Median max violation")
    ax.set_title("Max violation by impedance and search space")
    ax.legend()
    ax.tick_params(axis="x", labelrotation=45)
    fig.tight_layout()
    path = out / "max_violation_by_impedance_search_space.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    selected = [row for row in dof_rows if row["dof"] == "center_aperture_um"]
    x = [f"{row['condition_id']}\nseed{row['seed']}" for row in selected]
    y = [row["normalized_position"] for row in selected]
    ax.scatter(x, y)
    ax.axhline(0, color="black", linewidth=.6)
    ax.axhline(1, color="black", linewidth=.6)
    ax.set_ylabel("Normalized position in hard bounds")
    ax.set_title("Added DOF utilization: center aperture")
    ax.tick_params(axis="x", labelrotation=60)
    fig.tight_layout()
    path = out / "added_dof_utilization.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    probes = [row for row in boundary_rows if row.get("probe_value") is not None]
    labels = [f"{row['condition_id']}\n{row['search_space']}\n{row['variable']}" for row in probes]
    values = [row["delta_max_violation"] for row in probes]
    ax.bar(labels, values, color=["tab:red" if value > 0 else "tab:green" for value in values])
    ax.axhline(0, color="black", linewidth=.8)
    ax.set_ylabel("Inward probe Δ max violation")
    ax.set_title("Boundary probe comparison (diagnostic only)")
    ax.tick_params(axis="x", labelrotation=70)
    fig.tight_layout()
    path = out / "boundary_probe_comparison.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)
    return paths


def _summary_markdown(summary: Mapping[str, Any], space_rows: list[dict[str, Any]], impedance_rows: list[dict[str, Any]], convergence: list[dict[str, Any]], boundary: list[dict[str, Any]], bottleneck: list[dict[str, Any]]) -> str:
    lines = [
        "# Stage 3.6 Gate 2C — Joint impedance / DOF fast screening",
        "",
        "## Scope and safety",
        "",
        f"- S0: `{S0_GROUP}` (dimension {summary['s0_dimension']}).",
        f"- S1: `{S1_GROUP}` (dimension {summary['s1_dimension']}); added DOF: `center_aperture_um`.",
        "- S1 uses the existing Gate 2A release decoder, mirrored geometry, evaluator, and geometry/manufacturing constraints.",
        "- `metallization_ratio` and `thickness_over_lambda` remained fixed; `io_idt_pairs` hard lower bound remained 8.",
        "- Objective, ranking, constraints, common validation grid, L-SHADE backend, DMS topology, and wiring were unchanged.",
        f"- Sensitivity preflight passed: `{summary['preflight_passed']}`.",
        "",
        "## Completion",
        "",
        f"- Base cells completed: {summary['base_completed_cells']} / 8; base runs: {summary['base_completed_runs']} / 16.",
        f"- Promoted third-seed cells: {summary['promoted_cells']} / 4 maximum; promoted runs: {summary['promoted_runs']}.",
        f"- Nominal evaluations: {summary['nominal_evaluations']} / 320000 upper limit.",
        "",
        "## S1 − S0 paired comparison",
        "",
        "| Condition | Zin/Zout | Median Δ max violation | Mean Δ | S1 better seeds | Label |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in space_rows:
        lines.append(
            f"| {row['condition_id']} | {row['zin_ohm']:g}/{row['zout_ohm']:g} | "
            f"{row['median_delta_space_max_violation']:.8g} | {row['mean_delta_space_max_violation']:.8g} | "
            f"{row['s1_better_seed_count']}/{row['seed_count']} | `{row['decision_label']}` |"
        )
    lines += [
        "",
        "## Impedance ranking",
        "",
        "S0 and S1 rankings are descriptive mechanical rankings only; no global optimum, final impedance, or statistical significance claim is made.",
        "",
        "| Condition | Space | Median max violation | Rank | Feasible seeds |",
        "|---|---|---:|---:|---:|",
    ]
    for row in impedance_rows:
        lines.append(
            f"| {row['condition_id']} | {row['search_space']} | {row['median_max_violation']:.8g} | "
            f"{row.get('mechanical_rank', 'n/a')} | {row['feasible_seed_count']}/{row['seed_count']} |"
        )
    lines += [
        "",
        "## Convergence-lite and underoptimization",
        "",
        f"- Runs with a meaningful improvement after 90% of the 16k budget: {sum(bool(row['improvement_after_90pct']) for row in convergence)} / {len(convergence)}.",
        "- Checkpoint values at 4k, 8k, 12k, and 16k are in `convergence_lite.csv`; this is not a convergence certificate.",
        "",
        "## Boundary pressure",
        "",
        "Boundary probes were evaluated only at legal inward values and were not mixed into ranking. `persistent_hard_boundary_pressure` means all legal inward probes worsened the primary metric; `optimizer_artifact_or_accidental_hit` means all improved; mixed results are `inconclusive`.",
        f"- Probe rows: {len(boundary)}; actual inward probes: {sum(row.get('probe_value') is not None for row in boundary)}.",
        "",
        "## Constraint bottlenecks",
        "",
        "| Condition | Space | Constraint | Count | Fraction |",
        "|---|---|---|---:|---:|",
    ]
    for row in bottleneck:
        lines.append(
            f"| {row['condition_id']} | {row['search_space']} | {row['constraint']} | {row['count']} | {row['fraction']:.4g} |"
        )
    lines += [
        "",
        "## Limitations and unresolved items",
        "",
        "- The COM provider remains a placeholder model; center-aperture effects omit transverse diffraction/mode mismatch.",
        "- Results are an operational fast screen, not certification or statistical significance.",
        "- Hybrid, ladder, material/COM-coefficient, metallization/thickness, and next-stage production work were not started.",
        "",
        "## Hard stop",
        "",
        "STAGE3_6_GATE2C_FAST_SCREEN_COMPLETE_STOP",
        "",
        "No 32k/64k confirmation, five-seed all-cell confirmation, bound relaxation, or automatic next stage was started.",
        "",
    ]
    return "\n".join(lines)


def _build_review_bundle(run: Path, summary: Mapping[str, Any], plot_paths: list[Path]) -> Path:
    bundle_root = ROOT / "artifacts" / "review_bundles"
    bundle_root.mkdir(parents=True, exist_ok=True)
    staging = run / "_gate2c_bundle"
    staging.mkdir(parents=True, exist_ok=True)
    for name in (
        "stage3_6_gate2c_fast_screen_summary.md", "test_summary.md",
        "experiment_manifest.json", "s0_search_space_snapshot.json",
        "s1_search_space_snapshot.json", "reproduction_metadata.json",
        "promotion_decisions.csv", "git_status.txt", "git_diff_summary.txt",
    ):
        source = run / name
        if source.is_file():
            shutil.copy2(source, staging / name)
    for name in (
        "all_seed_results.csv", "search_space_comparison.csv",
        "impedance_comparison.csv", "dof_utilization.csv",
        "boundary_probe_results.csv", "convergence_lite.csv",
        "constraint_bottleneck_summary.csv",
    ):
        source = run / "results" / name
        if source.is_file():
            shutil.copy2(source, staging / name)
    for path in plot_paths:
        if path.is_file():
            shutil.copy2(path, staging / path.name)
    output = bundle_root / FINAL_BUNDLE_NAME
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(staging).as_posix())
    return output


def _build_audit_bundle(run: Path) -> Path:
    bundle_root = ROOT / "artifacts" / "review_bundles"
    bundle_root.mkdir(parents=True, exist_ok=True)
    staging = run / "_gate2c_audit_bundle"
    staging.mkdir(parents=True, exist_ok=True)
    for source in sorted(run.glob("*")):
        if source.is_file() and source.name != "stdout.log":
            shutil.copy2(source, staging / source.name)
    output = bundle_root / "stage3_6_gate2c_dof_audit_review.zip"
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(staging).as_posix())
    return output


def _write_audit_summary(run: Path, reason: str, preflight: Mapping[str, Any] | None = None) -> None:
    lines = [
        "# Stage 3.6 Gate 2C — DOF audit stop",
        "",
        "Production optimization was not started because the Gate 2C safety audit did not pass.",
        "",
        f"Reason: {reason}",
        "",
        "The audit checked the existing release registry, decoder, mirrored geometry/evaluator path, manufacturing geometry constraints, prohibited DOFs, and the frozen Gate 2B-B prerequisite.",
        "",
        "Recommended next action: resolve the listed release/physics validation blocker and obtain explicit review before constructing a new S1.",
        "",
        "STAGE3_6_GATE2C_DOF_AUDIT_STOP",
        "",
    ]
    if preflight is not None:
        lines += ["## Preflight payload", "", "```json", json.dumps(_clean(preflight), ensure_ascii=False, indent=2), "```", ""]
    _write_text(run / "stage3_6_gate2c_fast_screen_summary.md", "\n".join(lines))
    _write_text(run / AUDIT_STOP_MARKER, "STAGE3_6_GATE2C_DOF_AUDIT_STOP\nProduction optimization was not started.\n")


def run_stage36_gate2c(config_path: str | Path, run: str | Path, *, resume: bool = False) -> dict[str, Any]:
    config_path = Path(config_path).resolve()
    base = normalize_convergence_config(load_experiment_config(config_path))
    section = _stage_section(base)
    s1, s1_path = _load_s1(base)
    b_reference = _b_reference(base, s1_path)
    run = initialize(Path(run).resolve(), base)
    starting_commit = _git(["rev-parse", "HEAD"])
    starting_branch = _git(["branch", "--show-current"])
    status = _git(["status", "--short"])
    diff_summary = _git(["diff", "--stat"])
    s0_snapshot = _space_snapshot(S0_GROUP, s1)
    s1_snapshot = _space_snapshot(S1_GROUP, s1)
    save(run / "s0_search_space_snapshot.json", s0_snapshot)
    save(run / "s1_search_space_snapshot.json", s1_snapshot)
    save(run / "experiment_manifest.json", {
        "study_type": STUDY_TYPE,
        "config_path": str(config_path), "config_sha256": _sha256(config_path),
        "git_head": starting_commit, "git_branch": starting_branch,
        "git_status_at_start": status, "git_diff_summary_at_start": diff_summary,
        "s1_path": str(s1_path), "s1_sha256": _sha256(s1_path),
        "gate2b_b_run_dir": str(b_reference["run_dir"]),
        "gate2b_b_grid_id": b_reference["grid_id"],
        "s0_group": S0_GROUP, "s1_group": S1_GROUP,
        "s0_dimension": int(s0_snapshot["schema"]["dimension"]),
        "s1_dimension": int(s1_snapshot["schema"]["dimension"]),
        "backend": {
            "name": LShadeBackend.name,
            "population_schedule_identifier": LShadeBackend.population_schedule_identifier,
            "population_schedule_version": int(LShadeBackend.population_schedule_version),
        },
        "conditions": section["conditions"], "base_seeds": list(SEEDS),
        "optional_third_seed": OPTIONAL_THIRD_SEED, "budget": BUDGET,
        "checkpoints": list(CHECKPOINTS), "cold_start_per_cell_seed": True,
        "prohibited_dofs": ["metallization_ratio", "thickness_over_lambda"],
        "io_idt_pairs_hard_lower": int(s1_snapshot["io_idt_pairs_hard_lower"]),
        "production_started": False,
    })
    _write_text(run / "git_status.txt", status + "\n")
    _write_text(run / "git_diff_summary.txt", diff_summary + "\n")
    preflight = run_sensitivity_preflight(base, s1)
    save(run / "preflight_sensitivity.json", preflight)
    manifest = _json(run / "experiment_manifest.json")
    manifest["preflight"] = preflight
    if not preflight["passed"]:
        manifest["audit_stop"] = True
        save(run / "experiment_manifest.json", manifest)
        _write_audit_summary(run, "Existing S1 sensitivity preflight failed.", preflight)
        bundle = _build_audit_bundle(run)
        return {
            "study_type": STUDY_TYPE, "audit_stop": True,
            "preflight_passed": False, "review_bundle": str(bundle),
        }
    manifest["production_started"] = True
    save(run / "experiment_manifest.json", manifest)
    _write_text(run / "input_config.yaml", config_path.read_text(encoding="utf-8"))
    _write_text(
        run / "test_summary.md",
        "# Test summary\n\nThe Gate 2C targeted unit tests and the pre-production full regression were run before launch; see the launch record for the exact command/result.\n",
    )

    for cid, zin, zout in CONDITIONS:
        for group in (S0_GROUP, S1_GROUP):
            tasks = [
                (str(run), base, group, cid, zin, zout, s1, seed, CHECKPOINTS, bool(resume))
                for seed in SEEDS
            ]
            _run_workers(tasks, section["workers"], section["blas_threads_per_worker"])

    base_raw = []
    for cid, _zin, _zout in CONDITIONS:
        for group in (S0_GROUP, S1_GROUP):
            records = _final_records(run, cid, group, SEEDS)
            for record in records:
                if int(record.get("unique_decoded_evaluations", 0)) < BUDGET:
                    raise RuntimeError(f"{cid}/{group}/seed{record['seed']} did not complete the 16k budget")
                base_raw.append(record)
    base_validated = [_validate_record(base, record, b_reference["grid"]) for record in base_raw]
    decisions, promoted_cells = _promotion_decisions(base_validated, section["max_promoted_cells"])
    _write_csv(run / "promotion_decisions.csv", decisions)
    for cid, group in promoted_cells:
        condition = next(item for item in CONDITIONS if item[0] == cid)
        _run_workers([
            (str(run), base, group, cid, condition[1], condition[2], s1,
             OPTIONAL_THIRD_SEED, CHECKPOINTS, bool(resume))
        ], 1, section["blas_threads_per_worker"])

    final_raw: list[dict[str, Any]] = []
    snapshot_raw: list[dict[str, Any]] = []
    raw_final_map: dict[tuple[str, str, int], Mapping[str, Any]] = {}
    for cid, _zin, _zout in CONDITIONS:
        for group in (S0_GROUP, S1_GROUP):
            seeds = list(SEEDS) + ([OPTIONAL_THIRD_SEED] if (cid, group) in promoted_cells else [])
            finals = _final_records(run, cid, group, seeds)
            snapshots = _snapshot_records(run, cid, group, seeds)
            final_raw.extend(finals)
            snapshot_raw.extend(snapshots)
            for record in finals:
                if int(record.get("unique_decoded_evaluations", 0)) < BUDGET:
                    raise RuntimeError(f"{cid}/{group}/seed{record['seed']} did not complete the 16k budget")
                raw_final_map[(cid, group, int(record["seed"]))] = record
    final_rows = [_validate_record(base, record, b_reference["grid"]) for record in final_raw]
    snapshot_rows = [_validate_record(base, record, b_reference["grid"]) for record in snapshot_raw]
    space_detail, space_aggregate = _space_comparison(base_validated)
    impedance_rows = _impedance_comparison(final_rows)
    dof_rows = _dof_utilization(final_rows, s1)
    convergence = _build_convergence_lite(snapshot_rows, raw_final_map)
    boundary = _boundary_probe(base, final_rows, s1, b_reference["grid"])
    bottleneck = _bottleneck_summary(final_rows)
    results = run / "results"
    _write_csv(results / "all_seed_results.csv", final_rows)
    _write_csv(results / "search_space_comparison.csv", space_detail + space_aggregate)
    _write_csv(results / "impedance_comparison.csv", impedance_rows)
    _write_csv(results / "dof_utilization.csv", dof_rows)
    _write_csv(results / "boundary_probe_results.csv", boundary)
    _write_csv(results / "convergence_lite.csv", convergence)
    _write_csv(results / "constraint_bottleneck_summary.csv", bottleneck)
    np.savetxt(results / "common_validation_grid_hz.csv", b_reference["grid"], header="frequency_hz", comments="")
    save(results / "common_validation_grid.json", {
        "grid_id": b_reference["grid_id"], "frequency_count": int(len(b_reference["grid"])),
        "source": "Gate 2B-B common_validation_grid_hz.csv",
    })
    plot_paths = _plot_outputs(space_aggregate, impedance_rows, dof_rows, boundary, run / "plots")
    nominal = 16 * BUDGET + len(promoted_cells) * BUDGET
    summary = {
        "study_type": STUDY_TYPE, "s0_group": S0_GROUP, "s1_group": S1_GROUP,
        "s0_dimension": int(s0_snapshot["schema"]["dimension"]),
        "s1_dimension": int(s1_snapshot["schema"]["dimension"]),
        "added_dofs": [name for name in release_extra_names(S1_GROUP) if name not in release_extra_names(S0_GROUP)],
        "preflight_passed": bool(preflight["passed"]),
        "base_completed_cells": 8, "base_completed_runs": 16,
        "promoted_cells": len(promoted_cells), "promoted_cell_ids": [list(item) for item in promoted_cells],
        "promoted_runs": len(promoted_cells), "nominal_evaluations": nominal,
        "feasible_final_runs": sum(bool(row["feasible"]) for row in final_rows),
        "common_validation_grid_id": b_reference["grid_id"],
        "common_validation_frequency_count": int(len(b_reference["grid"])),
        "actual_starting_commit": starting_commit, "branch": starting_branch,
        "config_path": str(config_path), "config_sha256": _sha256(config_path),
        "s1_path": str(s1_path), "s1_sha256": _sha256(s1_path),
        "gate2b_b_reference_run_dir": str(b_reference["run_dir"]),
        "cold_start_per_cell_seed": True, "objective_unchanged": True,
        "constraints_unchanged": True, "topology_wiring": WIRING,
        "bounds_modified": False, "prohibited_work_started": False,
        "plots": [str(path.relative_to(run)) for path in plot_paths],
        "review_bundle": None,
    }
    _write_text(
        run / "stage3_6_gate2c_fast_screen_summary.md",
        _summary_markdown(summary, space_aggregate, impedance_rows, convergence, boundary, bottleneck),
    )
    save(run / "stage3_6_gate2c_summary.json", summary)
    save(run / "reproduction_metadata.json", {
        "study_type": STUDY_TYPE, "git_head": starting_commit, "git_branch": starting_branch,
        "git_status": status, "git_diff_summary": diff_summary,
        "config_path": str(config_path), "config_sha256": _sha256(config_path),
        "s0_snapshot": "s0_search_space_snapshot.json", "s1_snapshot": "s1_search_space_snapshot.json",
        "gate2b_b_run_dir": str(b_reference["run_dir"]), "common_validation_grid_id": b_reference["grid_id"],
        "backend": "L-SHADE", "population_schedule_identifier": LShadeBackend.population_schedule_identifier,
        "population_schedule_version": int(LShadeBackend.population_schedule_version),
        "test_command": ".venv\\Scripts\\python.exe -m pytest -q",
        "cold_start_per_cell_seed": True, "callback": "disabled by prior user instruction",
    })
    bundle = _build_review_bundle(run, summary, plot_paths)
    summary["review_bundle"] = str(bundle)
    save(run / "stage3_6_gate2c_summary.json", summary)
    _write_text(run / STOP_MARKER, "STAGE3_6_GATE2C_FAST_SCREEN_COMPLETE_STOP\nNo confirmation or next-stage run was started.\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 3.6 Gate 2C joint impedance / DOF fast screening")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_stage36_gate2c(args.config, args.run, resume=args.resume), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
