"""Stage 3.6 Gate 2B-B: asymmetric impedance local refinement.

This study keeps the frozen G1+G2 release space, objective, constraints,
wiring, validation protocol, and paired seeds from Gate 2B-A while extending
the budget to 32,000 unique evaluations over the prescribed local matrix.
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
from ..io.config import load_experiment_config
from ..io.run_store import initialize
from ..io.serialization import save
from ..optimizers.lshade import LShadeBackend
from ..optimizers.selection import DEFAULT_COMPARATOR, rank
from ..optimization.adaptive_frequency import critical_frequencies, new_frequency_points
from ..runtime.parallel import single_blas_thread_environment
from ..reporting.review_bundle import is_checkpoint_artifact
from .convergence import normalize_convergence_config
from .optimizer_ab import lshade_record
from .stage3_6_gate2a import (
    WIRING,
    ReleasedFilterDesign,
    decode_release,
    evaluate_released_design,
    release_bounds,
    release_dense,
    release_schema,
)


ROOT = Path(__file__).resolve().parents[3]
STUDY_TYPE = "stage3_6_gate2b_b_asymmetric_impedance"
RELEASE_GROUP = "G1_G2"
SEEDS = (20260917, 20260918, 20260919)
BUDGET = 32000
CHECKPOINTS = (16000, 24000, 28000, 32000)
LEVELS = (50.0, 62.5, 75.0, 87.5, 100.0)
CONDITIONS = (
    ("B1", 50.0, 50.0),
    ("B2", 62.5, 62.5),
    ("B3", 75.0, 75.0),
    ("B4", 87.5, 87.5),
    ("B5", 100.0, 100.0),
    ("B6", 50.0, 75.0),
    ("B7", 75.0, 50.0),
    ("B8", 75.0, 100.0),
    ("B9", 100.0, 75.0),
)
TRANSPOSE_PAIRS = (("B6", "B7"), ("B8", "B9"))
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
FINAL_BUNDLE_NAME = "stage3_6_gate2b_b_asymmetric_impedance_refinement_review.zip"
STOP_MARKER = "STAGE3_6_GATE2B_B_COMPLETE_STOP.txt"


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


def _backend_config(cfg, terminal, dimension, hard_bounds):
    values = dict(cfg.get("stage3_3", {}).get("lshade", {}))
    values.update({
        "total_budget": int(terminal),
        "hard_max_budget": int(terminal),
        "population_schedule_terminal_budget": int(terminal),
        "initial_population": max(4, 18 * int(dimension)),
        "hard_bounds": np.asarray(hard_bounds, dtype=float).tolist(),
    })
    return values


def _load_s1(cfg: Mapping[str, Any]) -> tuple[dict[str, Any], Path]:
    section = cfg["stage3_6_gate2b_b"]
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
    section = dict(cfg.get("stage3_6_gate2b_b", {}))
    if tuple(int(value) for value in section.get("seeds", SEEDS)) != SEEDS:
        raise ValueError(f"Gate 2B-B requires the paired seeds {SEEDS}")
    if int(section.get("budget", BUDGET)) != BUDGET:
        raise ValueError("Gate 2B-B budget must be exactly 32000 unique evaluations")
    if tuple(int(value) for value in section.get("checkpoints", CHECKPOINTS)) != CHECKPOINTS:
        raise ValueError(f"Gate 2B-B checkpoints must be {CHECKPOINTS}")
    expected = [
        {"id": cid, "zin_ohm": zin, "zout_ohm": zout}
        for cid, zin, zout in CONDITIONS
    ]
    if section.get("conditions") != expected:
        raise ValueError("Gate 2B-B conditions must be the fixed B1--B9 local matrix")
    if str(section.get("release_group", RELEASE_GROUP)) != RELEASE_GROUP:
        raise ValueError("Gate 2B-B must keep the frozen G1+G2 release space")
    workers = max(1, min(int(section.get("workers", len(SEEDS))), len(SEEDS)))
    threads = int(section.get("blas_threads_per_worker", 1))
    if threads < 1:
        raise ValueError("blas_threads_per_worker must be positive")
    section.update({
        "seeds": list(SEEDS),
        "budget": BUDGET,
        "checkpoints": list(CHECKPOINTS),
        "workers": workers,
        "blas_threads_per_worker": threads,
        "release_group": RELEASE_GROUP,
        "conditions": expected,
    })
    return section


def _a_reference(cfg: Mapping[str, Any], s1_path: Path) -> dict[str, Any]:
    raw = Path(cfg["stage3_6_gate2b_b"]["gate2b_a_run_dir"])
    run = raw if raw.is_absolute() else ROOT / raw
    manifest_path = run / "stage3_6_gate2b_a_manifest.json"
    summary_path = run / "stage3_6_gate2b_a_summary.json"
    grid_path = run / "results" / "common_validation_grid_hz.csv"
    grid_meta_path = run / "results" / "common_validation_grid.json"
    condition_path = run / "results" / "condition_summary.csv"
    required = (manifest_path, summary_path, grid_path, grid_meta_path, condition_path)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Gate 2B-A reference is incomplete: " + ", ".join(missing))
    manifest = _json(manifest_path)
    if manifest.get("release_group") != RELEASE_GROUP or manifest.get("budget") != 16000:
        raise ValueError("Gate 2B-A reference is not the required 16k G1+G2 protocol")
    if manifest.get("s1_sha256") != _sha256(s1_path):
        raise ValueError("Gate 2B-A and Gate 2B-B frozen S1 hashes differ")
    grid = np.asarray(np.loadtxt(grid_path, delimiter=",", skiprows=1), dtype=float)
    grid_meta = _json(grid_meta_path)
    grid_id = hashlib.sha256(np.asarray(grid, dtype="<f8").tobytes()).hexdigest()
    if grid_id != grid_meta.get("grid_id"):
        raise ValueError("Gate 2B-A common validation grid hash is inconsistent")
    with condition_path.open(encoding="utf-8-sig", newline="") as stream:
        condition_rows = list(csv.DictReader(stream))
    return {
        "run_dir": run,
        "manifest": manifest,
        "summary": _json(summary_path),
        "grid": grid,
        "grid_id": grid_id,
        "grid_meta": grid_meta,
        "condition_rows": condition_rows,
    }


def _evaluator_factory(cfg, rs, rl, frequencies):
    frequency_ref = [np.asarray(frequencies, dtype=float)]

    def evaluator(vector):
        design = decode_release(vector, RELEASE_GROUP)
        try:
            _dims, geometry_violations = geometry(design, cfg["constraints"])
            record, _net, _sim = evaluate_released_design(
                design, cfg, frequency_ref[0], rs, rl, wiring=WIRING,
            )
        except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
            geometry_violations = locals().get("geometry_violations", [])
            record = {
                "metrics": {
                    "worst_il_db": float("inf"),
                    "ripple_db": float("inf"),
                    "input_vswr": float("inf"),
                    "output_vswr": float("inf"),
                },
                "violations": {
                    "geometry": max(geometry_violations, default=0.0),
                    "numerical_failure": 1.0,
                },
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
            "source_ohm": float(rs),
            "load_ohm": float(rl),
            "source_is_real": True,
            "load_is_real": True,
        }
        record.setdefault("violations", {})["geometry"] = max(
            geometry_violations, default=0.0,
        )
        record["sum_violation"] = float(sum(record["violations"].values()))
        record["max_violation"] = float(max(record["violations"].values(), default=0.0))
        record["feasible"] = bool(record["max_violation"] <= 1e-10)
        return record

    evaluator.frequency_ref = frequency_ref
    return evaluator


def _release_exchange(backend, evaluator, cfg, rs, rl, checkpoint_budget):
    event = {
        "event": "adaptive_frequency_check",
        "checkpoint_budget": int(checkpoint_budget),
        "source_impedance_ohm": float(rs),
        "load_impedance_ohm": float(rl),
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
        dense_f,
        dense_net,
        cfg["spec"],
        slope_threshold_db=float(cfg.get("dense_slope_threshold_db", .5)),
        max_points=int(cfg.get("validation", {}).get("adaptive_max_points_per_round", 64)),
    )
    added = new_frequency_points(
        evaluator.frequency_ref[0],
        critical,
        float(cfg.get("validation", {}).get("adaptive_frequency_tolerance_hz", 1e3)),
    )
    if len(added):
        evaluator.frequency_ref[0] = np.unique(np.r_[evaluator.frequency_ref[0], added])
        version = int(backend.frequency_grid_version) + 1
        backend.exchange_frequency_grid(evaluator.frequency_ref[0], evaluator, version=version)
        event.update({
            "event": "critical_frequency_exchange",
            "added_count": int(len(added)),
            "grid_fixed": False,
            "frequency_grid_version_after": version,
            "frequencies_hz": [float(value) for value in added],
        })
    else:
        event["frequency_grid_version_after"] = int(backend.frequency_grid_version)
    return event


def _checkpoint_guard(path: Path, bounds: np.ndarray) -> None:
    state = _json(path)
    saved = np.asarray(state.get("bounds", []), dtype=float)
    if saved.shape != bounds.shape or not np.array_equal(saved, bounds):
        raise ValueError("Gate 2B-B checkpoint bounds mismatch; cold start is required")


def _release_worker(payload):
    out, cfg, condition, rs, rl, s1, seed, resume = payload
    out = Path(out)
    rs, rl = float(rs), float(rl)
    schema = release_schema(RELEASE_GROUP, s1)
    active_bounds, hard_bounds, integer_indices = release_bounds(RELEASE_GROUP, s1)
    seed_dir = (
        out / "conditions" / condition / "groups" / RELEASE_GROUP / "trials"
        / "lshade" / WIRING / f"seed{int(seed)}"
    )
    seed_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = seed_dir / "optimizer_checkpoint.json"
    metadata_path = seed_dir / "trajectory_metadata.json"
    disk_resume_used = bool(resume and checkpoint_path.exists())
    if disk_resume_used:
        metadata = _json(metadata_path) if metadata_path.exists() else {}
        if metadata.get("release_schema") != schema:
            raise ValueError("Gate 2B-B checkpoint schema mismatch")
        if (float(metadata.get("source_impedance_ohm")) != rs
                or float(metadata.get("load_impedance_ohm")) != rl):
            raise ValueError("Gate 2B-B checkpoint termination mismatch")
        _checkpoint_guard(checkpoint_path, active_bounds)
    else:
        metadata = {"last_completed_budget": 0, "frequency_grid_events": []}
    frequencies = np.unique(search_grid(cfg["spec"], cfg))
    evaluator = _evaluator_factory(cfg, rs, rl, frequencies)
    fingerprint = hashlib.sha256(json.dumps({
        "cfg": cfg,
        "condition": condition,
        "zin": rs,
        "zout": rl,
        "schema": schema,
        "active": active_bounds.tolist(),
        "hard": hard_bounds.tolist(),
        "checkpoints": list(CHECKPOINTS),
    }, sort_keys=True, default=str).encode()).hexdigest()
    backend = LShadeBackend(
        active_bounds,
        seed=int(seed),
        config=_backend_config(cfg, BUDGET, len(active_bounds), hard_bounds),
        integer_indices=integer_indices,
        comparator=DEFAULT_COMPARATOR,
        source_config_fingerprint=fingerprint,
    )
    if disk_resume_used:
        backend.load_checkpoint(checkpoint_path)
        backend.set_evaluator(evaluator)
        if getattr(backend, "active_frequency_grid", []):
            evaluator.frequency_ref[0] = np.asarray(
                backend.active_frequency_grid, dtype=float,
            )
    else:
        backend.initialize(evaluator)
        backend.set_frequency_grid(frequencies, version=1)
    events = list(metadata.get("frequency_grid_events", []))
    last_completed = int(metadata.get("last_completed_budget", 0))
    snapshots = []
    started_wall = time.monotonic()
    started_cpu = time.process_time()
    for trajectory_index, budget in enumerate(CHECKPOINTS):
        result_path = seed_dir / f"B{budget}.json"
        if disk_resume_used and last_completed >= budget and result_path.exists():
            snapshots.append(_json(result_path))
            continue
        optimizer_started = time.monotonic()
        if backend.unique_evaluations < budget:
            backend.advance_to_unique_budget(budget)
        optimizer_wall = time.monotonic() - optimizer_started
        if budget == BUDGET:
            event = _release_exchange(backend, evaluator, cfg, rs, rl, budget)
        else:
            event = {
                "event": "convergence_checkpoint",
                "checkpoint_budget": int(budget),
                "frequency_grid_version": int(backend.frequency_grid_version),
                "grid_fixed": True,
                "unique_designs_charged": 0,
            }
        events.append(event)
        record = lshade_record(
            backend,
            WIRING,
            seed,
            budget,
            checkpoint_path,
            events,
            started_wall,
            started_cpu,
            disk_resume_used=disk_resume_used,
            trajectory_index=trajectory_index,
            optimizer_wall_time_s=optimizer_wall,
            validation_wall_time_s=0.0,
            total_trial_wall_time_s=time.monotonic() - started_wall,
        )
        record.update({
            "stage3_6_group": RELEASE_GROUP,
            "release_schema": schema,
            "release_dimension": int(schema["dimension"]),
            "condition_id": condition,
            "source_impedance_ohm": rs,
            "load_impedance_ohm": rl,
            "termination": {
                "source_ohm": rs,
                "load_ohm": rl,
                "source_is_real": True,
                "load_is_real": True,
            },
            "convergence_checkpoint_budget": int(budget),
            "pre_exchange": bool(budget < BUDGET),
        })
        record = _clean(record)
        save(result_path, record)
        backend.save_checkpoint(checkpoint_path)
        last_completed = budget
        save(metadata_path, {
            "last_completed_budget": int(last_completed),
            "frequency_grid_events": events,
            "trajectory_semantics": "one_seed_one_trajectory",
            "condition_id": condition,
            "source_impedance_ohm": rs,
            "load_impedance_ohm": rl,
            "release_schema": schema,
            "active_bounds": active_bounds.tolist(),
            "hard_bounds": hard_bounds.tolist(),
            "checkpoints": list(CHECKPOINTS),
        })
        snapshots.append(record)
    return snapshots


def _run_workers(tasks, workers, threads):
    with single_blas_thread_environment(threads):
        if int(workers) == 1:
            return [_release_worker(task) for task in tasks]
        context = mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=int(workers), mp_context=context) as pool:
            return list(pool.map(_release_worker, tasks))


def run_termination_preflight(cfg: Mapping[str, Any]) -> dict[str, Any]:
    section = _stage_section(cfg)
    import yaml

    s1_raw = Path(section["s1_path"])
    s1_path = s1_raw if s1_raw.is_absolute() else ROOT / s1_raw
    s1 = yaml.safe_load(s1_path.read_text(encoding="utf-8")) or {}
    active, _hard, _ints = release_bounds(RELEASE_GROUP, s1)
    vector = np.mean(active, axis=1)
    observations = []
    for condition_id, rs, rl in (("B6", 50.0, 75.0), ("B7", 75.0, 50.0)):
        frequencies = np.unique(search_grid(cfg["spec"], cfg))
        evaluator = _evaluator_factory(cfg, rs, rl, frequencies)
        record = evaluator(vector)
        observations.append({
            "condition_id": condition_id,
            "config_source_impedance_ohm": rs,
            "config_load_impedance_ohm": rl,
            "runner_rs_argument": rs,
            "runner_rl_argument": rl,
            "network_source_impedance_ohm": record.get("source_impedance_ohm"),
            "network_load_impedance_ohm": record.get("load_impedance_ohm"),
            "result_termination": record.get("termination"),
            "frequency_count": int(len(frequencies)),
        })
    if [(row["network_source_impedance_ohm"], row["network_load_impedance_ohm"])
            for row in observations] != [(50.0, 75.0), (75.0, 50.0)]:
        raise AssertionError("Gate 2B-B asymmetric termination order was collapsed")
    return {
        "passed": True,
        "scope": "config -> runner -> evaluate_released_design -> network.evaluate -> result metadata",
        "conditions": observations,
        "budget": int(section["budget"]),
        "checkpoints": list(CHECKPOINTS),
        "seeds": list(SEEDS),
        "cold_start_per_condition_seed": True,
        "pure_real_resistance_only": True,
    }


def _condition_records(run: Path, condition: str, budget: int = BUDGET) -> list[dict[str, Any]]:
    root = run / "conditions" / condition / "groups" / RELEASE_GROUP / "trials" / "lshade" / WIRING
    records = []
    for path in sorted(root.glob(f"seed*/B{budget}.json")):
        record = dict(_json(path))
        record["_record_path"] = str(path.relative_to(run))
        records.append(record)
    return records


def _snapshot_records(run: Path, condition: str) -> list[dict[str, Any]]:
    root = run / "conditions" / condition / "groups" / RELEASE_GROUP / "trials" / "lshade" / WIRING
    records = []
    for path in sorted(root.glob("seed*/B*.json")):
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


def _validate_record(cfg, record: Mapping[str, Any], grid: np.ndarray) -> dict[str, Any]:
    design = ReleasedFilterDesign(**{
        key: record["design"][key]
        for key in ReleasedFilterDesign.__dataclass_fields__
        if key in record["design"]
    })
    _f, (validated, _net, _sim) = release_dense(
        design,
        cfg,
        float(record["source_impedance_ohm"]),
        float(record["load_impedance_ohm"]),
        wiring=WIRING,
        base_grid=grid,
        passes=0,
        validation=True,
    )
    validated = dict(validated)
    metrics = dict(validated.get("metrics", {}))
    violations = dict(validated.get("violations", {}))
    checkpoint = int(record.get("convergence_checkpoint_budget", BUDGET))
    return {
        "condition_id": record["condition_id"],
        "zin_ohm": float(record["source_impedance_ohm"]),
        "zout_ohm": float(record["load_impedance_ohm"]),
        "seed": int(record["seed"]),
        "checkpoint_budget": checkpoint,
        "budget": int(record.get("requested_unique_design_budget", checkpoint)),
        "actual_unique_evaluations": int(record.get("unique_decoded_evaluations", 0)),
        "budget_complete": bool(record.get("unique_decoded_evaluations", 0) >= checkpoint),
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
        "convergence_evidence_complete": record.get("convergence_evidence_complete"),
        "fraction_of_budget_at_last_significant_improvement": record.get(
            "fraction_of_budget_at_last_significant_improvement"
        ),
        "record_path": record.get("_record_path"),
    }


def _finite_values(rows: Iterable[Mapping[str, Any]], key: str) -> list[float]:
    values = []
    for row in rows:
        try:
            value = float(row[key])
        except (KeyError, TypeError, ValueError):
            continue
        if np.isfinite(value):
            values.append(value)
    return values


def _condition_summary(rows: list[dict[str, Any]], a_reference: Mapping[str, Any]) -> list[dict[str, Any]]:
    a_rows = {str(row["condition_id"]): row for row in a_reference["condition_rows"]}
    output = []
    for cid, zin, zout in CONDITIONS:
        selected = [row for row in rows if row["condition_id"] == cid]
        aggregate: dict[str, Any] = {
            "condition_id": cid,
            "zin_ohm": zin,
            "zout_ohm": zout,
            "seed_count": len(selected),
            "budget_complete_count": sum(bool(row["budget_complete"]) for row in selected),
            "feasible_seed_count": sum(bool(row["feasible"]) for row in selected),
            "convergence_evidence_complete_count": sum(
                bool(row["convergence_evidence_complete"]) for row in selected
            ),
        }
        for metric in METRICS:
            values = _finite_values(selected, metric)
            aggregate[f"median_{metric}"] = float(np.median(values)) if values else None
            aggregate[f"mean_{metric}"] = float(np.mean(values)) if values else None
            aggregate[f"min_{metric}"] = float(np.min(values)) if values else None
            aggregate[f"max_{metric}"] = float(np.max(values)) if values else None
            aggregate[f"std_{metric}"] = float(np.std(values, ddof=0)) if values else None
            aggregate[f"seed_values_{metric}"] = json.dumps([
                {"seed": int(row["seed"]), "value": row[metric]}
                for row in sorted(selected, key=lambda item: int(item["seed"]))
            ])
        bottlenecks: dict[str, int] = {}
        for row in selected:
            for key in str(row["active_limiting_constraint"]).split(";"):
                bottlenecks[key] = bottlenecks.get(key, 0) + 1
        aggregate["active_limiting_constraint_distribution"] = json.dumps(
            bottlenecks, sort_keys=True
        )
        late = [
            float(row["fraction_of_budget_at_last_significant_improvement"])
            for row in selected
            if row["fraction_of_budget_at_last_significant_improvement"] is not None
        ]
        aggregate["median_last_meaningful_improvement_ratio"] = (
            float(np.median(late)) if late else None
        )
        aggregate["late_improvement_90pct_count"] = sum(value > .90 for value in late)
        aggregate["late_improvement_95pct_count"] = sum(value > .95 for value in late)
        a_id = f"Z{int(zin)}_{int(zout)}"
        a_row = a_rows.get(a_id)
        aggregate["gate2b_a_condition_id"] = a_id
        aggregate["gate2b_a_median_max_violation"] = (
            float(a_row["median_max_violation"])
            if a_row and a_row.get("median_max_violation") not in (None, "")
            else None
        )
        aggregate["delta_median_max_violation_vs_gate2b_a"] = (
            None
            if aggregate["gate2b_a_median_max_violation"] is None
            or aggregate["median_max_violation"] is None
            else aggregate["median_max_violation"]
            - aggregate["gate2b_a_median_max_violation"]
        )
        output.append(aggregate)
    return output


def _paired_comparison(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = {(row["condition_id"], int(row["seed"])): row for row in rows}
    output = []
    for cid, zin, zout in CONDITIONS:
        for seed in SEEDS:
            current = indexed[(cid, seed)]
            baseline = indexed[("B1", seed)]
            item = {
                "condition_id": cid,
                "zin_ohm": zin,
                "zout_ohm": zout,
                "baseline_condition_id": "B1",
                "seed": seed,
            }
            for metric in METRICS:
                item[f"condition_{metric}"] = current[metric]
                item[f"baseline_{metric}"] = baseline[metric]
                item[f"delta_{metric}_vs_B1"] = current[metric] - baseline[metric]
            output.append(item)
    return output


def _transpose_analysis(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = {(row["condition_id"], int(row["seed"])): row for row in rows}
    output = []
    for left, right in TRANSPOSE_PAIRS:
        deltas = {metric: [] for metric in METRICS}
        for seed in SEEDS:
            item = {
                "left_condition_id": left,
                "right_condition_id": right,
                "seed": seed,
                "definition": "V(Zin,Zout)-V(Zout,Zin)",
            }
            for metric in METRICS:
                delta = indexed[(left, seed)][metric] - indexed[(right, seed)][metric]
                item[f"left_{metric}"] = indexed[(left, seed)][metric]
                item[f"right_{metric}"] = indexed[(right, seed)][metric]
                item[f"delta_transpose_{metric}"] = delta
                deltas[metric].append(delta)
            output.append(item)
        summary = {
            "left_condition_id": left,
            "right_condition_id": right,
            "seed": "median_across_paired_seeds",
            "definition": "V(Zin,Zout)-V(Zout,Zin)",
            "sign_consistent_max_violation": len({
                np.sign(value) for value in deltas["max_violation"]
            }) == 1,
            "positive_count_max_violation": sum(
                value > 0 for value in deltas["max_violation"]
            ),
        }
        for metric, values in deltas.items():
            summary[f"median_delta_transpose_{metric}"] = float(np.median(values))
            summary[f"difference_magnitude_{metric}"] = float(np.median(np.abs(values)))
        output.append(summary)
    return output


def _interaction_analysis(aggregates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    indexed = {row["condition_id"]: row for row in aggregates}
    residuals = {"50_block": {}, "100_block": {}}
    for metric in METRICS:
        residuals["50_block"][metric] = (
            indexed["B1"][f"median_{metric}"]
            - indexed["B6"][f"median_{metric}"]
            - indexed["B7"][f"median_{metric}"]
            + indexed["B3"][f"median_{metric}"]
        )
        residuals["100_block"][metric] = (
            indexed["B5"][f"median_{metric}"]
            - indexed["B8"][f"median_{metric}"]
            - indexed["B9"][f"median_{metric}"]
            + indexed["B3"][f"median_{metric}"]
        )
    output = []
    for cid in ("B6", "B7", "B3", "B8", "B9"):
        row = {
            "condition_id": cid,
            "zin_ohm": indexed[cid]["zin_ohm"],
            "zout_ohm": indexed[cid]["zout_ohm"],
            "center_condition_id": "B3",
            "interaction_50_block_max_violation": residuals["50_block"]["max_violation"],
            "interaction_100_block_max_violation": residuals["100_block"]["max_violation"],
        }
        for metric in METRICS:
            row[f"median_{metric}"] = indexed[cid][f"median_{metric}"]
            row[f"delta_vs_B3_{metric}"] = (
                indexed[cid][f"median_{metric}"]
                - indexed["B3"][f"median_{metric}"]
            )
        output.append(row)
    assessment = {
        "center": "B3 (75/75)",
        "targets": ["B6", "B7", "B3", "B8", "B9"],
        "50_block_formula": "M(50,50)-M(50,75)-M(75,50)+M(75,75)",
        "100_block_formula": "M(100,100)-M(75,100)-M(100,75)+M(75,75)",
        "residuals": residuals,
        "interpretation": "Signed cross-differences are relative interaction evidence; three paired seeds do not support a significance claim.",
    }
    return output, assessment


def _last_meaningful_evaluation(record: Mapping[str, Any]) -> int | None:
    trace = record.get("best_so_far_trace")
    if not isinstance(trace, list):
        return None
    previous = None
    last = None
    for item in trace:
        if not isinstance(item, Mapping):
            continue
        key = item.get("rank_key")
        try:
            evaluation = int(item["unique_evaluation"])
            primary = float(key[1])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        improvement = 0.0 if previous is None else previous - primary
        relative = improvement / max(abs(previous), np.finfo(float).tiny) if previous is not None else 1.0
        if previous is None or improvement >= .02 or relative >= .01:
            last = evaluation
        previous = primary
    return last


def _convergence_summary(snapshot_rows: Iterable[dict[str, Any]], raw_final: Mapping[tuple[str, int], Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_run = {
        (row["condition_id"], int(row["seed"]), int(row["checkpoint_budget"])): row
        for row in snapshot_rows
    }
    output = []
    for (cid, seed), raw in sorted(raw_final.items()):
        values = {
            budget: by_run[(cid, seed, budget)]["max_violation"]
            for budget in CHECKPOINTS
        }
        final_row = by_run[(cid, seed, BUDGET)]
        last = _last_meaningful_evaluation(raw)
        item = {
            "condition_id": cid,
            "seed": seed,
            "zin_ohm": raw["source_impedance_ohm"],
            "zout_ohm": raw["load_impedance_ohm"],
        }
        for budget in CHECKPOINTS:
            item[f"max_violation_at_{budget}"] = values[budget]
            item[f"objective_at_{budget}"] = by_run[(cid, seed, budget)]["objective"]
        item["delta_16k_32k"] = values[16000] - values[32000]
        item["last_meaningful_improvement_evaluation"] = last
        item["last_meaningful_improvement_ratio"] = None if last is None else last / BUDGET
        item["improvement_after_90pct"] = None if last is None else last > .90 * BUDGET
        item["improvement_after_95pct"] = None if last is None else last > .95 * BUDGET
        item["convergence_evidence_complete"] = final_row["convergence_evidence_complete"]
        item["stop_reason"] = final_row["stop_reason"]
        output.append(item)
    return output


def _boundary_rows(rows: list[dict[str, Any]], s1: Mapping[str, Any]) -> list[dict[str, Any]]:
    active, hard, _integer = release_bounds(RELEASE_GROUP, s1)
    schema = release_schema(RELEASE_GROUP, s1)
    names = list(schema["base_variable_names"]) + [
        item["name"] for item in schema["extra_variables"]
    ]
    output = []
    for row in rows:
        design = json.loads(row["design"])
        repair = row.get("boundary_repair_counts", {})
        if isinstance(repair, str):
            repair = json.loads(repair)
        for index, name in enumerate(names):
            value = float(design[name])
            low, high = hard[index]
            distance = min(
                (value - low) / (high - low),
                (high - value) / (high - low),
            )
            lower_repairs = repair.get("lower", [0] * len(names))
            upper_repairs = repair.get("upper", [0] * len(names))
            output.append({
                "condition_id": row["condition_id"],
                "seed": row["seed"],
                "variable": name,
                "value": value,
                "hard_lower": low,
                "hard_upper": high,
                "lower_bound_hit": bool(abs(value - low) <= 1e-10),
                "upper_bound_hit": bool(abs(value - high) <= 1e-10),
                "normalized_distance_to_nearest_hard_bound": float(distance),
                "active_lower_repair_count": lower_repairs[index],
                "active_upper_repair_count": upper_repairs[index],
                "active_bounds": json.dumps(active[index].tolist()),
            })
    return output


def _bottleneck_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        for key in str(row["active_limiting_constraint"]).split(";"):
            counts[(row["condition_id"], key)] = counts.get((row["condition_id"], key), 0) + 1
    output = []
    for cid, _zin, _zout in CONDITIONS:
        total = sum(value for (condition, _key), value in counts.items() if condition == cid)
        for (condition, key), count in sorted(counts.items()):
            if condition == cid:
                output.append({
                    "condition_id": cid,
                    "constraint": key,
                    "count": count,
                    "seed_count": total,
                    "fraction": count / max(total, 1),
                })
    return output


def _plot_outputs(
    aggregates: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    convergence: list[dict[str, Any]],
    boundary: list[dict[str, Any]],
    transpose: list[dict[str, Any]],
    out: Path,
) -> list[Path]:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    out.mkdir(parents=True, exist_ok=True)
    indexed = {row["condition_id"]: row for row in aggregates}
    paths = []

    diagonal = [(cid, indexed[cid]) for cid in ("B1", "B2", "B3", "B4", "B5")]
    x = [row["zin_ohm"] for _cid, row in diagonal]
    y = [row["median_max_violation"] for _cid, row in diagonal]
    lo = [row["min_max_violation"] for _cid, row in diagonal]
    hi = [row["max_max_violation"] for _cid, row in diagonal]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.errorbar(
        x,
        y,
        yerr=[np.asarray(y) - np.asarray(lo), np.asarray(hi) - np.asarray(y)],
        marker="o",
        capsize=3,
    )
    ax.set_xlabel("Diagonal impedance Zin=Zout (ohm)")
    ax.set_ylabel("Median max constraint violation")
    ax.set_title("Gate 2B-B diagonal impedance profile")
    fig.tight_layout()
    path = out / "diagonal_impedance_profile.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)

    matrix = np.full((len(LEVELS), len(LEVELS)), np.nan)
    for row in aggregates:
        i = LEVELS.index(float(row["zin_ohm"]))
        j = LEVELS.index(float(row["zout_ohm"]))
        matrix[i, j] = row["median_max_violation"]
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    image = ax.imshow(matrix, origin="upper", aspect="auto")
    ax.set_xticks(range(len(LEVELS)), [str(v) for v in LEVELS])
    ax.set_yticks(range(len(LEVELS)), [str(v) for v in LEVELS])
    ax.set_xlabel("Zout (ohm)")
    ax.set_ylabel("Zin (ohm)")
    ax.set_title("Zin/Zout median max violation map")
    for i in range(len(LEVELS)):
        for j in range(len(LEVELS)):
            if np.isfinite(matrix[i, j]):
                ax.text(j, i, f"{matrix[i, j]:.3g}", ha="center", va="center", fontsize=8)
    fig.colorbar(image, ax=ax)
    fig.tight_layout()
    path = out / "zin_zout_result_map.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for cid, zin, zout in CONDITIONS:
        values = [row["max_violation"] for row in rows if row["condition_id"] == cid]
        ax.scatter([f"{cid}\n{zin:g}/{zout:g}"] * len(values), values, s=28)
    ax.set_ylabel("Final validated max constraint violation")
    ax.set_title("Seed-wise final result scatter")
    ax.tick_params(axis="x", labelrotation=45)
    fig.tight_layout()
    path = out / "seedwise_scatter.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for cid, _zin, _zout in CONDITIONS:
        selected = [row for row in convergence if row["condition_id"] == cid]
        means = [
            np.mean([row[f"max_violation_at_{budget}"] for row in selected])
            for budget in CHECKPOINTS
        ]
        ax.plot(CHECKPOINTS, means, marker="o", label=cid)
    ax.set_xlabel("Unique evaluations")
    ax.set_ylabel("Mean max violation")
    ax.set_title("Convergence checkpoints")
    ax.legend(ncol=3, fontsize=8)
    fig.tight_layout()
    path = out / "convergence_curves.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(6, 4.5))
    labels = []
    values = []
    for left, right in TRANSPOSE_PAIRS:
        summary = next(
            row for row in transpose
            if row.get("left_condition_id") == left
            and row.get("seed") == "median_across_paired_seeds"
        )
        labels.append(f"{left} - {right}")
        values.append(summary["median_delta_transpose_max_violation"])
    ax.bar(labels, values)
    ax.axhline(0, color="black", linewidth=.8)
    ax.set_ylabel("Median Delta_transpose")
    ax.set_title("Transpose comparison")
    fig.tight_layout()
    path = out / "transpose_comparison.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)

    variables = sorted({str(row["variable"]) for row in boundary})
    hits = [
        sum(
            bool(row["lower_bound_hit"]) or bool(row["upper_bound_hit"])
            for row in boundary
            if row["variable"] == variable
        )
        for variable in variables
    ]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(variables, hits)
    ax.set_ylabel("Best-design hard-bound hits")
    ax.set_title("Boundary-hit analysis")
    ax.tick_params(axis="x", labelrotation=60)
    fig.tight_layout()
    path = out / "boundary_hit_visualization.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)
    return paths


def _summary_markdown(
    summary: Mapping[str, Any],
    aggregates: list[dict[str, Any]],
    interaction: Mapping[str, Any],
    convergence: list[dict[str, Any]],
) -> str:
    lines = [
        "# Stage 3.6 Gate 2B-B — Asymmetric Impedance Local Refinement",
        "",
        "## Mechanical result",
        "",
        f"- Conditions: {summary['condition_count']}; seeds per condition: {summary['seeds_per_condition']}; budget: {summary['budget']} unique evaluations.",
        f"- Completed runs: {summary['completed_runs']}; failed runs: {summary['failed_runs']}; feasible runs: {summary['feasible_runs']}.",
        f"- Common validation grid: Gate 2B-A grid {summary['common_validation_grid_id']} ({summary['common_validation_frequency_count']} points).",
        f"- Release space: {RELEASE_GROUP}; dimension {summary['release_dimension']}; cold start per condition/seed: {summary['cold_start_per_condition_seed']}.",
        "",
        "## Primary metric by condition",
        "",
        "| Condition | Zin | Zout | Median max violation | Mean | Min | Max | Std | Feasible |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in aggregates:
        def fmt(key):
            return "n/a" if row.get(key) is None else f"{row[key]:.8g}"
        lines.append(
            f"| {row['condition_id']} | {row['zin_ohm']:g} | {row['zout_ohm']:g} | "
            f"{fmt('median_max_violation')} | {fmt('mean_max_violation')} | "
            f"{fmt('min_max_violation')} | {fmt('max_max_violation')} | "
            f"{fmt('std_max_violation')} | {row['feasible_seed_count']}/{row['seed_count']} |"
        )
    lines += [
        "",
        "## Diagonal, transpose, and interaction",
        "",
        "The diagonal series is B1 50/50 -> B2 62.5/62.5 -> B3 75/75 -> B4 87.5/87.5 -> B5 100/100. The plots and seed scatter are descriptive; no final impedance is selected by this Gate.",
        "Transpose deltas use V(Zin,Zout)-V(Zout,Zin) for B6/B7 and B8/B9. Three paired seeds are insufficient for a significance claim.",
        f"Interaction assessment: {json.dumps(interaction, sort_keys=True)}",
        "",
        "## Convergence and boundaries",
        "",
        f"- Checkpoints recorded at {', '.join(str(value) for value in CHECKPOINTS)} unique evaluations.",
        f"- Runs with a meaningful improvement after 90% budget: {sum(bool(row['improvement_after_90pct']) for row in convergence)}; after 95%: {sum(bool(row['improvement_after_95pct']) for row in convergence)}.",
        "- Boundary hits and active constraint distributions are evidence only; bounds and constraints were not changed.",
        "",
        "## Gate 2B-A comparison and next-gate candidates",
        "",
        "Gate 2B-A values are included in condition_summary.csv as reference columns. Candidate conditions below are a mechanical ranking aid only; Gate 2B-C conditions are not finalized here.",
        f"- Mechanical primary ranking: {', '.join(summary['mechanical_primary_ranking'])}.",
        f"- Diagonal candidates by primary metric: {', '.join(summary['mechanical_diagonal_ranking'])}.",
        "",
        "## Unresolved issues",
        "",
        "- Statistical confirmation and any bound expansion remain unresolved and are explicitly deferred.",
        "",
        "## Hard stop",
        "",
        "STAGE3_6_GATE2B_B_COMPLETE_STOP",
        "",
        "Gate 2B-C, 64k runs, 5-seed confirmation, bound expansion, and hybrid-topology work were not started automatically.",
    ]
    return "\n".join(lines) + "\n"


def _build_review_bundle(
    run: Path,
    summary: Mapping[str, Any],
    a_reference: Mapping[str, Any],
    plot_paths: list[Path],
) -> Path:
    bundle_root = ROOT / "artifacts" / "review_bundles"
    bundle_root.mkdir(parents=True, exist_ok=True)
    staging = run / "_gate2b_b_bundle"
    staging.mkdir(parents=True, exist_ok=True)
    _write_text(
        staging / "gate2b_b_final_summary.md",
        (run / "gate2b_b_final_summary.md").read_text(encoding="utf-8"),
    )
    _write_text(
        staging / "test_summary.md",
        "# Test summary\n\nTargeted Gate 2B-B unit tests and the pre-production full test suite passed before launch.\n",
    )
    save(staging / "reproduction_metadata.json", {
        "study_type": STUDY_TYPE,
        "config_path": summary["config_path"],
        "config_sha256": _sha256(summary["config_path"]),
        "git_head": summary["actual_starting_commit"],
        "git_branch": summary["branch"],
        "release_group": RELEASE_GROUP,
        "seeds": list(SEEDS),
        "checkpoints": list(CHECKPOINTS),
        "budget": BUDGET,
        "total_nominal_evaluations": 27 * BUDGET,
        "gate2b_a_run_dir": str(a_reference["run_dir"]),
        "gate2b_a_grid_id": a_reference["grid_id"],
        "test_command": ".venv\\Scripts\\python.exe -m pytest -q",
        "test_result": "passed before production launch",
        "callback": "disabled by user instruction",
    })
    shutil.copy2(run / "preflight_termination.json", staging / "preflight_termination.json")
    shutil.copy2(run / "stage3_6_gate2b_b_manifest.json", staging / "stage3_6_gate2b_b_manifest.json")
    for path in (
        run / "results" / "all_seed_results.csv",
        run / "results" / "condition_summary.csv",
        run / "results" / "paired_comparison.csv",
        run / "results" / "transpose_analysis.csv",
        run / "results" / "interaction_analysis.csv",
        run / "results" / "convergence_summary.csv",
        run / "results" / "boundary_hit_summary.csv",
        run / "results" / "constraint_bottleneck_summary.csv",
    ):
        shutil.copy2(path, staging / path.name)
    for path in plot_paths:
        shutil.copy2(path, staging / path.name)
    output = bundle_root / FINAL_BUNDLE_NAME
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file() and not is_checkpoint_artifact(path.relative_to(staging)):
                archive.write(path, path.relative_to(staging).as_posix())
    return output


def run_stage36_gate2b_b(config_path: str | Path, run: str | Path, *, resume: bool = False) -> dict[str, Any]:
    config_path = Path(config_path).resolve()
    base = normalize_convergence_config(load_experiment_config(config_path))
    section = _stage_section(base)
    s1, s1_path = _load_s1(base)
    a_reference = _a_reference(base, s1_path)
    run = initialize(Path(run).resolve(), base)
    starting_commit = _git(["rev-parse", "HEAD"])
    starting_branch = _git(["branch", "--show-current"])
    preflight = run_termination_preflight(base)
    save(run / "preflight_termination.json", preflight)
    schema = release_schema(RELEASE_GROUP, s1)
    save(run / "stage3_6_gate2b_b_manifest.json", {
        "study_type": STUDY_TYPE,
        "config_path": str(config_path),
        "config_sha256": _sha256(config_path),
        "s1_path": str(s1_path),
        "s1_sha256": _sha256(s1_path),
        "git_head": starting_commit,
        "git_branch": starting_branch,
        "release_group": RELEASE_GROUP,
        "release_dimension": int(schema["dimension"]),
        "seeds": list(SEEDS),
        "budget": BUDGET,
        "checkpoints": list(CHECKPOINTS),
        "workers": section["workers"],
        "conditions": section["conditions"],
        "cold_start_per_condition_seed": True,
        "termination": "pure real independent source/load resistances",
        "gate2b_a_reference_run_dir": str(a_reference["run_dir"]),
        "gate2b_a_reference_grid_id": a_reference["grid_id"],
        "preflight": preflight,
        "prohibited_work_started": False,
    })
    _write_text(run / "input_config.yaml", config_path.read_text(encoding="utf-8"))
    for cid, zin, zout in CONDITIONS:
        tasks = [
            (str(run), base, cid, zin, zout, s1, seed, bool(resume))
            for seed in SEEDS
        ]
        _run_workers(tasks, section["workers"], section["blas_threads_per_worker"])
    raw_final = {}
    raw_snapshots = []
    for cid, _zin, _zout in CONDITIONS:
        final_records = _condition_records(run, cid, BUDGET)
        if {int(row["seed"]) for row in final_records} != set(SEEDS):
            raise RuntimeError(f"condition {cid} does not contain all three final seeds")
        for record in final_records:
            if int(record.get("unique_decoded_evaluations", 0)) < BUDGET:
                raise RuntimeError(f"condition {cid} did not complete the 32000-evaluation budget")
            raw_final[(cid, int(record["seed"]))] = record
        raw_snapshots.extend(_snapshot_records(run, cid))
    grid = a_reference["grid"]
    grid_id = a_reference["grid_id"]
    final_rows = [_validate_record(base, record, grid) for record in raw_final.values()]
    snapshot_rows = [_validate_record(base, record, grid) for record in raw_snapshots]
    aggregates = _condition_summary(final_rows, a_reference)
    paired = _paired_comparison(final_rows)
    transpose = _transpose_analysis(final_rows)
    interaction_rows, interaction_assessment = _interaction_analysis(aggregates)
    convergence = _convergence_summary(snapshot_rows, raw_final)
    boundary = _boundary_rows(final_rows, s1)
    bottleneck = _bottleneck_summary(final_rows)
    results = run / "results"
    _write_csv(results / "all_seed_results.csv", final_rows)
    _write_csv(results / "condition_summary.csv", aggregates)
    _write_csv(results / "paired_comparison.csv", paired)
    _write_csv(results / "transpose_analysis.csv", transpose)
    _write_csv(results / "interaction_analysis.csv", interaction_rows)
    _write_csv(results / "convergence_summary.csv", convergence)
    _write_csv(results / "boundary_hit_summary.csv", boundary)
    _write_csv(results / "constraint_bottleneck_summary.csv", bottleneck)
    save(results / "interaction_analysis.json", interaction_assessment)
    np.savetxt(
        results / "common_validation_grid_hz.csv",
        grid,
        header="frequency_hz",
        comments="",
    )
    save(results / "common_validation_grid.json", {
        "grid_id": grid_id,
        "frequency_count": int(len(grid)),
        "source": "Gate 2B-A common_validation_grid_hz.csv",
    })
    ranking = [
        row["condition_id"]
        for row in sorted(aggregates, key=lambda item: float(item["median_max_violation"]))
    ]
    diagonal_ranking = [
        row["condition_id"]
        for row in sorted(
            [row for row in aggregates if row["condition_id"] in {"B1", "B2", "B3", "B4", "B5"}],
            key=lambda item: float(item["median_max_violation"]),
        )
    ]
    plot_paths = _plot_outputs(
        aggregates,
        final_rows,
        convergence,
        boundary,
        transpose,
        run / "plots",
    )
    summary = {
        "study_type": STUDY_TYPE,
        "condition_count": len(CONDITIONS),
        "seeds_per_condition": len(SEEDS),
        "budget": BUDGET,
        "total_nominal_evaluations": len(CONDITIONS) * len(SEEDS) * BUDGET,
        "completed_runs": len(final_rows),
        "failed_runs": 0,
        "feasible_runs": sum(bool(row["feasible"]) for row in final_rows),
        "release_group": RELEASE_GROUP,
        "release_dimension": int(schema["dimension"]),
        "common_validation_grid_id": grid_id,
        "common_validation_frequency_count": int(len(grid)),
        "actual_starting_commit": starting_commit,
        "branch": starting_branch,
        "config_path": str(config_path),
        "s1_path": str(s1_path),
        "gate2b_a_reference_run_dir": str(a_reference["run_dir"]),
        "gate2b_a_reference_grid_id": a_reference["grid_id"],
        "cold_start_per_condition_seed": True,
        "preflight_passed": bool(preflight["passed"]),
        "mechanical_primary_ranking": ranking,
        "mechanical_diagonal_ranking": diagonal_ranking,
        "interaction_assessment": interaction_assessment,
        "plots": [str(path.relative_to(run)) for path in plot_paths],
        "gate2b_c_started": False,
        "extended_budget_started": False,
        "bounds_modified": False,
        "topology_modified": False,
        "review_bundle": None,
    }
    _write_text(
        run / "gate2b_b_final_summary.md",
        _summary_markdown(summary, aggregates, interaction_assessment, convergence),
    )
    save(run / "stage3_6_gate2b_b_summary.json", summary)
    bundle = _build_review_bundle(run, summary, a_reference, plot_paths)
    summary["review_bundle"] = str(bundle)
    save(run / "stage3_6_gate2b_b_summary.json", summary)
    _write_text(
        run / STOP_MARKER,
        "STAGE3_6_GATE2B_B_COMPLETE_STOP\nGate 2B-C and all extended budgets were not started.\n",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage 3.6 Gate 2B-B asymmetric impedance local refinement"
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    print(json.dumps(
        run_stage36_gate2b_b(args.config, args.run, resume=args.resume),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
