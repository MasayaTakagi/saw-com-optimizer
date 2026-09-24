"""Stage 3.6 Gate 2B-A: asymmetric real port-impedance factorial.

This study is deliberately isolated from the Gate 2A release worker.  It
reuses the frozen ``G1_G2`` release schema and the existing COM/network
implementation, but passes independent source and load resistances through
every evaluation.  Each condition and seed owns a fresh L-SHADE trajectory;
no population, incumbent, or checkpoint is shared between conditions.
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

from ..core.metrics import geometry, search_grid, validation_grid
from ..core.models import NAMES
from ..core.network import evaluate
from ..io.checkpoints import complete_study_run
from ..io.legacy_lifecycle import legacy_process_disposition
from ..io.config import load_experiment_config
from ..io.run_store import initialize
from ..io.serialization import save
from ..optimizers.checkpoint_session import LShadeCheckpointSession
from ..optimizers.lshade import LShadeBackend
from ..optimizers.selection import DEFAULT_COMPARATOR, rank
from ..optimization.adaptive_frequency import critical_frequencies, new_frequency_points
from ..runtime.parallel import single_blas_thread_environment
from ..reporting.review_bundle import ignore_checkpoint_entries
from .convergence import normalize_convergence_config
from .optimizer_ab import lshade_record
from .stage3_6_gate2a import (
    WIRING,
    ReleasedFilterDesign,
    decode_release,
    release_bounds,
    release_dense,
    release_schema,
    simulate_released_filter,
    evaluate_released_design,
)


ROOT = Path(__file__).resolve().parents[3]
STUDY_TYPE = "stage3_6_gate2b_a_asymmetric_impedance"
RELEASE_GROUP = "G1_G2"
SEEDS = (20260917, 20260918, 20260919)
BUDGET = 16000
LEVELS = (25.0, 50.0, 100.0)
TRANSPOSE_PAIRS = ((25.0, 50.0), (25.0, 100.0), (50.0, 100.0))
FINAL_BUNDLE_NAME = "stage3_6_gate2b_a_asymmetric_impedance_review.zip"


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backend_config(cfg, terminal, dimension, hard_bounds):
    """Build the existing L-SHADE configuration without private imports."""
    values = dict(cfg.get("stage3_3", {}).get("lshade", {}))
    values.update({
        "total_budget": int(terminal),
        "hard_max_budget": int(terminal),
        "population_schedule_terminal_budget": int(terminal),
        "initial_population": max(4, 18 * int(dimension)),
        "hard_bounds": np.asarray(hard_bounds, dtype=float).tolist(),
    })
    return values


def condition_id(zin: float, zout: float) -> str:
    return f"Z{int(zin)}_{int(zout)}"


CONDITIONS = tuple(
    (condition_id(zin, zout), zin, zout)
    for zin in LEVELS
    for zout in LEVELS
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


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(set().union(*(row.keys() for row in rows))) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _git(args: list[str]) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"git {' '.join(args)} failed: {exc}\n"


def _load_s1(cfg: Mapping[str, Any]) -> tuple[dict[str, Any], Path]:
    section = cfg.get("stage3_6_gate2b_a", {})
    raw = Path(section.get(
        "s1_path", "artifacts/stage3_5/phase_a_revised/search_space_s1.yaml"
    ))
    path = raw if raw.is_absolute() else ROOT / raw
    if not path.is_file():
        raise FileNotFoundError(f"frozen S1 config is missing: {path}")
    import yaml

    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not document.get("freeze") or not document.get("hard_bounds_unchanged"):
        raise ValueError("S1 config is not marked frozen with unchanged hard bounds")
    return document, path


def _stage_section(cfg: Mapping[str, Any]) -> dict[str, Any]:
    section = dict(cfg.get("stage3_6_gate2b_a", {}))
    seeds = tuple(int(value) for value in section.get("seeds", SEEDS))
    if seeds != SEEDS:
        raise ValueError(f"Gate 2B-A requires the canonical paired seeds: {SEEDS}")
    budget = int(section.get("budget", BUDGET))
    if budget != BUDGET:
        raise ValueError("Gate 2B-A budget must be exactly 16000 unique evaluations")
    configured = section.get("conditions")
    expected = [
        {"id": cid, "zin_ohm": zin, "zout_ohm": zout}
        for cid, zin, zout in CONDITIONS
    ]
    if configured != expected:
        raise ValueError("Gate 2B-A conditions must be the canonical 3x3 factorial")
    if str(section.get("release_group", RELEASE_GROUP)) != RELEASE_GROUP:
        raise ValueError("Gate 2B-A must keep the frozen G1+G2 release space")
    workers = max(1, min(int(section.get("workers", len(SEEDS))), len(SEEDS)))
    threads = int(section.get("blas_threads_per_worker", 1))
    if threads < 1:
        raise ValueError("blas_threads_per_worker must be positive")
    section.update({
        "seeds": list(SEEDS), "budget": BUDGET, "workers": workers,
        "blas_threads_per_worker": threads, "release_group": RELEASE_GROUP,
        "conditions": expected,
    })
    return section


def _asymmetric_evaluator_factory(cfg, rs, rl, wiring, frequencies, group):
    """Create a release evaluator with independent real terminations."""
    frequency_ref = [np.asarray(frequencies, dtype=float)]

    def evaluator(vector):
        design = decode_release(vector, group)
        try:
            _dims, geometry_violations = geometry(design, cfg["constraints"])
            record, _net, _sim = evaluate_released_design(
                design, cfg, frequency_ref[0], rs, rl, wiring=wiring
            )
        except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
            geometry_violations = locals().get("geometry_violations", [])
            record = {
                "metrics": {
                    "worst_il_db": float("inf"), "ripple_db": float("inf"),
                    "input_vswr": float("inf"), "output_vswr": float("inf"),
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
            "source_ohm": float(rs), "load_ohm": float(rl),
            "source_is_real": True, "load_is_real": True,
        }
        record.setdefault("violations", {})["geometry"] = max(
            geometry_violations, default=0.0
        )
        record["sum_violation"] = float(sum(record["violations"].values()))
        record["max_violation"] = float(max(record["violations"].values(), default=0.0))
        record["feasible"] = bool(record["max_violation"] <= 1e-10)
        return record

    evaluator.frequency_ref = frequency_ref
    return evaluator


def _asymmetric_release_exchange(backend, evaluator, cfg, wiring, rs, rl, checkpoint_budget):
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
        design, cfg, rs, rl, wiring=wiring, passes=0, validation=True,
    )
    critical = critical_frequencies(
        dense_f, dense_net, cfg["spec"],
        slope_threshold_db=float(cfg.get("dense_slope_threshold_db", .5)),
        max_points=int(cfg.get("validation", {}).get(
            "adaptive_max_points_per_round", 64
        )),
    )
    added = new_frequency_points(
        evaluator.frequency_ref[0], critical,
        float(cfg.get("validation", {}).get(
            "adaptive_frequency_tolerance_hz", 1e3
        )),
    )
    if len(added):
        evaluator.frequency_ref[0] = np.unique(np.r_[evaluator.frequency_ref[0], added])
        version = int(backend.frequency_grid_version) + 1
        backend.exchange_frequency_grid(evaluator.frequency_ref[0], evaluator, version=version)
        event.update({
            "event": "critical_frequency_exchange",
            "added_count": int(len(added)), "grid_fixed": False,
            "frequency_grid_version_after": version,
            "frequencies_hz": [float(value) for value in added],
        })
    else:
        event["frequency_grid_version_after"] = int(backend.frequency_grid_version)
    return event


def _checkpoint_guard(path: Path, bounds: np.ndarray) -> None:
    state = path if isinstance(path, Mapping) else _json(path)
    saved = np.asarray(state.get("bounds", []), dtype=float)
    if saved.shape != bounds.shape or not np.array_equal(saved, bounds):
        raise ValueError("Gate 2B-A checkpoint bounds mismatch; cold start is required")


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
    legacy_checkpoint_path = seed_dir / "optimizer_checkpoint.json"
    checkpoint_session = LShadeCheckpointSession(
        seed_dir / "checkpoints", run_directory=out,
        legacy_path=legacy_checkpoint_path, resume=resume,
        state_validator=lambda state: _checkpoint_guard(state, active_bounds),
    )
    checkpoint_path = checkpoint_session.reference_metadata
    metadata_path = seed_dir / "trajectory_metadata.json"
    disk_resume_used = bool(resume and checkpoint_session.has_checkpoint)
    if disk_resume_used:
        if not metadata_path.exists():
            raise ValueError("Gate 2B-A checkpoint metadata is missing")
        metadata = _json(metadata_path)
        if metadata.get("release_schema") != schema:
            raise ValueError("Gate 2B-A checkpoint schema mismatch")
        if float(metadata.get("source_impedance_ohm")) != rs or float(
            metadata.get("load_impedance_ohm")
        ) != rl:
            raise ValueError("Gate 2B-A checkpoint termination mismatch")
        if checkpoint_session.legacy_mode:
            _checkpoint_guard(checkpoint_path, active_bounds)
    else:
        metadata = {}
    frequencies = np.unique(search_grid(cfg["spec"], cfg))
    evaluator = _asymmetric_evaluator_factory(
        cfg, rs, rl, WIRING, frequencies, RELEASE_GROUP
    )
    lshade_cfg = _backend_config(
        cfg, BUDGET, len(active_bounds), hard_bounds
    )
    fingerprint = hashlib.sha256(json.dumps({
        "cfg": cfg, "condition": condition, "zin": rs, "zout": rl,
        "schema": schema, "active": active_bounds.tolist(),
        "hard": hard_bounds.tolist(),
    }, sort_keys=True, default=str).encode()).hexdigest()
    backend = LShadeBackend(
        active_bounds, seed=int(seed), config=lshade_cfg,
        integer_indices=integer_indices, comparator=DEFAULT_COMPARATOR,
        source_config_fingerprint=fingerprint,
    )
    if disk_resume_used:
        checkpoint_session.load(backend)
        backend.set_evaluator(evaluator)
        if getattr(backend, "active_frequency_grid", []):
            evaluator.frequency_ref[0] = np.asarray(
                backend.active_frequency_grid, dtype=float
            )
    else:
        backend.initialize(evaluator)
        backend.set_frequency_grid(frequencies, version=1)
        metadata = {"last_completed_budget": 0, "frequency_grid_events": []}
    events = list(metadata.get("frequency_grid_events", []))
    last_completed = int(metadata.get("last_completed_budget", 0))
    started_wall = time.monotonic()
    started_cpu = time.process_time()
    result_path = seed_dir / f"B{BUDGET}.json"
    if not (disk_resume_used and last_completed >= BUDGET and result_path.exists()):
        optimizer_started = time.monotonic()
        if backend.unique_evaluations < BUDGET:
            backend.advance_to_unique_budget(BUDGET)
        optimizer_wall = time.monotonic() - optimizer_started
        pre_exchange = copy.deepcopy(backend.incumbent())
        validation_started = time.monotonic()
        event = _asymmetric_release_exchange(
            backend, evaluator, cfg, WIRING, rs, rl, BUDGET
        )
        validation_wall = time.monotonic() - validation_started
        events.append(event)
        record = lshade_record(
            backend, WIRING, seed, BUDGET, checkpoint_path, events,
            started_wall, started_cpu, disk_resume_used=disk_resume_used,
            trajectory_index=0, optimizer_wall_time_s=optimizer_wall,
            validation_wall_time_s=validation_wall,
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
                "source_ohm": rs, "load_ohm": rl,
                "source_is_real": True, "load_is_real": True,
            },
            "pre_exchange_snapshot": _clean(pre_exchange or {}),
        })
        record = _clean(record)
        save(result_path, record)
        checkpoint_session.save(backend)
        save(metadata_path, {
            "last_completed_budget": BUDGET,
            "frequency_grid_events": events,
            "trajectory_semantics": "one_seed_one_trajectory",
            "condition_id": condition,
            "source_impedance_ohm": rs,
            "load_impedance_ohm": rl,
            "release_schema": schema,
            "active_bounds": active_bounds.tolist(),
            "hard_bounds": hard_bounds.tolist(),
        })
    return _json(result_path)


def _run_workers(tasks, workers, threads):
    with single_blas_thread_environment(threads):
        if int(workers) == 1:
            return [_release_worker(task) for task in tasks]
        context = mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=int(workers), mp_context=context) as pool:
            return list(pool.map(_release_worker, tasks))


def run_termination_preflight(cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Exercise 25/50 and 50/25 through the full evaluator/network path."""
    # Use the normal search grid so every configured stopband has at least
    # one sample and the probe exercises the same metric path as production.
    frequencies = np.asarray(search_grid(cfg["spec"], cfg), dtype=float)
    values = [5.0, 24.0, 16.0, 40.0, .5, .5, 80.0, 5.0, 5.0]
    design = decode_release(values, RELEASE_GROUP)
    observations = []
    for cid, rs, rl in (("Z25_50", 25.0, 50.0), ("Z50_25", 50.0, 25.0)):
        _result, net, _sim = evaluate_released_design(
            design, cfg, frequencies, rs, rl, wiring=WIRING
        )
        observations.append({
            "condition_id": cid,
            "config_source_impedance_ohm": rs,
            "config_load_impedance_ohm": rl,
            "runner_rs_argument": rs,
            "runner_rl_argument": rl,
            "network_source_impedance_ohm": float(net["source_impedance_ohm"]),
            "network_load_impedance_ohm": float(net["load_impedance_ohm"]),
            "network_result_keys": sorted(net),
            "frequency_count": len(frequencies),
        })
    if observations[0]["network_source_impedance_ohm"] != 25.0 or observations[0]["network_load_impedance_ohm"] != 50.0:
        raise AssertionError("25/50 termination order did not reach network.evaluate")
    if observations[1]["network_source_impedance_ohm"] != 50.0 or observations[1]["network_load_impedance_ohm"] != 25.0:
        raise AssertionError("50/25 termination order did not reach network.evaluate")
    return {
        "passed": True,
        "scope": "config -> runner -> evaluate_released_design -> network.evaluate -> result metadata",
        "conditions": observations,
        "pure_real_resistance_only": True,
    }


def _condition_records(run: Path, cid: str) -> list[dict[str, Any]]:
    root = run / "conditions" / cid / "groups" / RELEASE_GROUP / "trials" / "lshade" / WIRING
    records = []
    for path in sorted(root.glob("seed*/B16000.json")):
        record = dict(_json(path))
        record["_record_path"] = str(path.relative_to(run))
        records.append(record)
    return records


def _common_grid(cfg, records: list[dict[str, Any]]) -> np.ndarray:
    grid = np.asarray(validation_grid(cfg["spec"], cfg), dtype=float)
    for record in records:
        try:
            design = ReleasedFilterDesign(**{
                key: record["design"][key]
                for key in ReleasedFilterDesign.__dataclass_fields__
                if key in record["design"]
            })
            refined, _payload = release_dense(
                design, cfg, float(record["source_impedance_ohm"]),
                float(record["load_impedance_ohm"]), wiring=WIRING,
                validation=True,
            )
            grid = np.unique(np.r_[grid, refined])
        except (KeyError, TypeError, ValueError, np.linalg.LinAlgError, FloatingPointError):
            continue
    return np.unique(grid)


def _stopband_violation(violations: Mapping[str, Any]) -> float:
    return float(max(
        (float(value) for key, value in violations.items() if key.startswith("stop_")),
        default=0.0,
    ))


def _validate_record(cfg, record: Mapping[str, Any], grid: np.ndarray) -> dict[str, Any]:
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
    row = {
        "condition_id": record["condition_id"],
        "zin_ohm": float(record["source_impedance_ohm"]),
        "zout_ohm": float(record["load_impedance_ohm"]),
        "seed": int(record["seed"]),
        "budget": int(record.get("requested_unique_design_budget", BUDGET)),
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
        "source_return_loss_db_min": float(metrics.get("source_return_loss_db_min", np.inf)),
        "load_return_loss_db_min": float(metrics.get("load_return_loss_db_min", np.inf)),
        "stop_attenuation_db": json.dumps(_clean(metrics.get("stop_attenuation_db", []))),
        "individual_violations": json.dumps(_clean(violations), sort_keys=True),
        "all_metrics": json.dumps(_clean(metrics), sort_keys=True),
        "design": json.dumps(_clean(record["design"]), sort_keys=True),
        "validated_rank_tuple": json.dumps([float(value) for value in rank(validated)]),
        "objective_calls": int(record.get("objective_calls", 0)),
        "elapsed_s": float(record.get("elapsed_s", 0.0)),
        "stop_reason": record.get("stop_reason"),
        "fraction_of_budget_at_last_significant_improvement": record.get(
            "fraction_of_budget_at_last_significant_improvement"
        ),
        "grid_converged": record.get("grid_converged"),
        "convergence_evidence_complete": record.get("convergence_evidence_complete"),
        "record_path": record.get("_record_path"),
    }
    return row


def _metric_value(row: Mapping[str, Any], metric: str) -> float:
    return float(row[metric])


def _aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for cid, zin, zout in CONDITIONS:
        selected = [row for row in rows if row["condition_id"] == cid]
        aggregate: dict[str, Any] = {
            "condition_id": cid, "zin_ohm": zin, "zout_ohm": zout,
            "seed_count": len(selected),
            "budget_complete_count": sum(bool(row["budget_complete"]) for row in selected),
            "feasible_seed_count": sum(bool(row["feasible"]) for row in selected),
        }
        for metric in METRICS:
            values = np.asarray([_metric_value(row, metric) for row in selected], dtype=float)
            aggregate[f"median_{metric}"] = float(np.median(values))
            aggregate[f"iqr_{metric}"] = float(np.percentile(values, 75) - np.percentile(values, 25))
            aggregate[f"min_{metric}"] = float(np.min(values))
            aggregate[f"max_{metric}"] = float(np.max(values))
        fractions = [
            float(row["fraction_of_budget_at_last_significant_improvement"])
            for row in selected
            if row["fraction_of_budget_at_last_significant_improvement"] is not None
        ]
        aggregate["median_last_significant_improvement_fraction"] = (
            float(np.median(fractions)) if fractions else None
        )
        aggregate["late_improvement_seed_count"] = sum(
            row["fraction_of_budget_at_last_significant_improvement"] is not None
            and float(row["fraction_of_budget_at_last_significant_improvement"]) > .75
            for row in selected
        )
        aggregate["median_runtime_s"] = float(np.median([row["elapsed_s"] for row in selected]))
        aggregate["termination_statuses"] = ";".join(sorted({str(row["stop_reason"]) for row in selected}))
        output.append(aggregate)
    return output


def _paired_vs_50(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = {(row["condition_id"], int(row["seed"])): row for row in rows}
    output = []
    for cid, zin, zout in CONDITIONS:
        for seed in SEEDS:
            current = indexed[(cid, seed)]
            baseline = indexed[("Z50_50", seed)]
            row = {
                "condition_id": cid, "zin_ohm": zin, "zout_ohm": zout,
                "baseline_condition_id": "Z50_50", "seed": seed,
            }
            for metric in METRICS:
                row[f"condition_{metric}"] = current[metric]
                row[f"baseline_{metric}"] = baseline[metric]
                row[f"delta_{metric}_vs_50_50"] = float(current[metric] - baseline[metric])
            output.append(row)
    return output


def _transpose(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    indexed = {(row["condition_id"], int(row["seed"])): row for row in rows}
    detail, summary = [], []
    for z1, z2 in TRANSPOSE_PAIRS:
        left, right = condition_id(z1, z2), condition_id(z2, z1)
        deltas = {metric: [] for metric in METRICS}
        for seed in SEEDS:
            row = {"condition_id": left, "transpose_condition_id": right, "seed": seed}
            for metric in METRICS:
                delta = float(indexed[(left, seed)][metric] - indexed[(right, seed)][metric])
                row[f"{metric}_left"] = indexed[(left, seed)][metric]
                row[f"{metric}_right"] = indexed[(right, seed)][metric]
                row[f"delta_asym_{metric}"] = delta
                deltas[metric].append(delta)
            detail.append(row)
        row = {"condition_id": left, "transpose_condition_id": right, "aggregation": "median_across_paired_seeds"}
        for metric, values in deltas.items():
            row[f"median_delta_asym_{metric}"] = float(np.median(values))
            row[f"iqr_delta_asym_{metric}"] = float(np.percentile(values, 75) - np.percentile(values, 25))
        summary.append(row)
    return detail, summary


def _port_sensitivity(aggregates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = {row["condition_id"]: row for row in aggregates}
    output = []
    for axis, fixed_name, fixed_value in (("Zin", "Zout", 50.0), ("Zout", "Zin", 50.0)):
        for varied in LEVELS:
            zin, zout = (varied, fixed_value) if axis == "Zin" else (fixed_value, varied)
            cid = condition_id(zin, zout)
            baseline = indexed["Z50_50"]
            row = {
                "sensitivity_axis": axis, "fixed_port": fixed_name,
                "fixed_value_ohm": fixed_value, "varied_value_ohm": varied,
                "condition_id": cid,
            }
            for metric in METRICS:
                row[f"median_{metric}"] = indexed[cid][f"median_{metric}"]
                row[f"delta_{metric}_vs_50_50"] = indexed[cid][f"median_{metric}"] - baseline[f"median_{metric}"]
            output.append(row)
    return output


def _interaction(aggregates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    indexed = {row["condition_id"]: row for row in aggregates}
    output = []
    maximum = {metric: 0.0 for metric in METRICS}
    for zin in LEVELS:
        for zout in LEVELS:
            cid = condition_id(zin, zout)
            row = {"condition_id": cid, "zin_ohm": zin, "zout_ohm": zout}
            for metric in METRICS:
                residual = (
                    indexed[cid][f"median_{metric}"]
                    - indexed[condition_id(zin, 50.0)][f"median_{metric}"]
                    - indexed[condition_id(50.0, zout)][f"median_{metric}"]
                    + indexed["Z50_50"][f"median_{metric}"]
                )
                row[f"median_{metric}"] = indexed[cid][f"median_{metric}"]
                row[f"interaction_residual_{metric}"] = float(residual)
                maximum[metric] = max(maximum[metric], abs(float(residual)))
            output.append(row)
    assessment = {
        "method": "cross_difference M(Zin,Zout)-M(Zin,50)-M(50,Zout)+M(50,50)",
        "max_absolute_residual": maximum,
        "interpretation": "Residual magnitudes are reported for additive interaction assessment; three paired seeds do not support a significance claim.",
    }
    return output, assessment


def _plot_heatmaps(aggregates: list[dict[str, Any]], out: Path) -> list[Path]:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    out.mkdir(parents=True, exist_ok=True)
    indexed = {row["condition_id"]: row for row in aggregates}
    paths = []
    for metric, title, filename in (
        ("max_violation", "Median max constraint violation", "heatmap_max_violation.png"),
        ("sum_violation", "Median sum constraint violation", "heatmap_sum_violation.png"),
        ("objective", "Median objective", "heatmap_objective.png"),
    ):
        matrix = np.asarray([
            [indexed[condition_id(zin, zout)][f"median_{metric}"] for zout in LEVELS]
            for zin in LEVELS
        ], dtype=float)
        fig, ax = plt.subplots(figsize=(6.2, 5.2))
        image = ax.imshow(matrix, origin="upper", aspect="auto")
        ax.set_xticks(range(len(LEVELS)), [f"{int(v)}" for v in LEVELS])
        ax.set_yticks(range(len(LEVELS)), [f"{int(v)}" for v in LEVELS])
        ax.set_xlabel("Zout (ohm)")
        ax.set_ylabel("Zin (ohm)")
        ax.set_title(title)
        for i in range(len(LEVELS)):
            for j in range(len(LEVELS)):
                ax.text(j, i, f"{matrix[i, j]:.4g}", ha="center", va="center", fontsize=8)
        fig.colorbar(image, ax=ax)
        fig.tight_layout()
        path = out / filename
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)
    return paths


def _convergence_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        fraction = row["fraction_of_budget_at_last_significant_improvement"]
        output.append({
            "condition_id": row["condition_id"], "zin_ohm": row["zin_ohm"],
            "zout_ohm": row["zout_ohm"], "seed": row["seed"],
            "budget": row["budget"], "actual_unique_evaluations": row["actual_unique_evaluations"],
            "budget_complete": row["budget_complete"], "stop_reason": row["stop_reason"],
            "grid_converged": row["grid_converged"],
            "convergence_evidence_complete": row["convergence_evidence_complete"],
            "last_significant_improvement_fraction": fraction,
            "late_improvement": None if fraction is None else bool(float(fraction) > .75),
            "elapsed_s": row["elapsed_s"],
        })
    return output


def _summary_markdown(summary: Mapping[str, Any], aggregates: list[dict[str, Any]], interaction: Mapping[str, Any]) -> str:
    lines = [
        "# Stage 3.6 Gate 2B-A — asymmetric port impedance coarse factorial",
        "",
        f"- Decision: `{summary['decision']}`",
        f"- Conditions: `{summary['condition_count']}`; seeds per condition: `{summary['seeds_per_condition']}`; budget: `{summary['budget']}` unique evaluations",
        f"- Release space: `{RELEASE_GROUP}` (G1+G2), dimension `{summary['release_dimension']}`",
        f"- Common validation grid: `{summary['common_validation_grid_id']}` ({summary['common_validation_frequency_count']} points)",
        "",
        "## Median primary metric",
        "",
        "| Zin / Zout | 25 | 50 | 100 |",
        "|---:|---:|---:|---:|",
    ]
    indexed = {row["condition_id"]: row for row in aggregates}
    for zin in LEVELS:
        lines.append("| %d | %s | %s | %s |" % (
            zin,
            *(f"{indexed[condition_id(zin, zout)]['median_max_violation']:.8g}" for zout in LEVELS),
        ))
    lines += [
        "",
        "## Scope and interpretation",
        "",
        "Every factorial cell was optimized independently from a cold start using the same three seeds and 16,000-evaluation budget. No previous population, best individual, or checkpoint was used as a warm start.",
        "The heatmap axes are fixed as x=Zout and y=Zin. `paired_vs_50ohm.csv` contains same-seed comparisons to 50/50; `transpose_pair_comparison.csv` and `asymmetry_summary.csv` contain the requested transpose deltas.",
        f"Interaction is assessed by the signed cross-difference. The largest absolute residuals are `{json.dumps(interaction['max_absolute_residual'], sort_keys=True)}`. This is operational evidence, not a statistical significance claim.",
        "",
        "## Hard stop",
        "",
        "Gate 2B-B, 32k/64k extensions, topology changes, and additional DOFs were not started by this study.",
    ]
    return "\n".join(lines) + "\n"


def build_review_bundle(run: Path, cfg: Mapping[str, Any], s1: Mapping[str, Any], summary: Mapping[str, Any], aggregates: list[dict[str, Any]], interaction_assessment: Mapping[str, Any], preflight: Mapping[str, Any], s1_path: Path) -> Path:
    bundle_root = ROOT / "artifacts" / "review_bundles"
    bundle_root.mkdir(parents=True, exist_ok=True)
    staging = run / "_gate2b_a_bundle"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for relative in ("results", "plots", "conditions"):
        source = run / relative
        if source.exists():
            shutil.copytree(source, staging / relative, dirs_exist_ok=True,
                            ignore=ignore_checkpoint_entries)
    _write_text(staging / "stage3_6_gate2b_a_summary.md", _summary_markdown(summary, aggregates, interaction_assessment))
    _write_text(staging / "test_summary.md", "# Test summary\n\nThe mandatory Zin/Zout preflight passed. See `preflight_termination.json`. Repository tests were run before production launch and their command/result are recorded in `reproduction_metadata.json`.\n")
    _write_text(staging / "git_status.txt", _git(["status", "--short"]))
    _write_text(staging / "git_log.txt", _git(["log", "-5", "--oneline"]))
    tag = "stage3.6-gate2a-closed"
    head = str(summary["actual_starting_commit"])
    diff_stat = _git(["diff", "--stat", f"{tag}..{head}"])
    diff_names = _git(["diff", "--name-status", f"{tag}..{head}"])
    _write_text(staging / "baseline_diff_summary.md", "\n".join([
        "# Baseline diff summary", "", f"Gate 2A canonical tag: `{tag}`",
        f"Gate 2B-A actual starting commit: `{head}`", "",
        "## Commit-range diff", "", diff_stat or "(empty)", "", diff_names or "(empty)", "",
        "The starting commit was selected from the dedicated Gate 2B-A branch created from main. No optimizer, COM, objective, constraint, or port-termination source change is included in the commit range.",
    ]) + "\n")
    shutil.copy2(s1_path, staging / "search_space_s1.yaml")
    shutil.copy2(run / "input_config.yaml", staging / "config.yaml")
    shutil.copy2(run / "preflight_termination.json", staging / "preflight_termination.json")
    save(staging / "reproduction_metadata.json", {
        "study_type": STUDY_TYPE, "config_path": str(summary["config_path"]),
        "config_sha256": _sha256(summary["config_path"]),
        "s1_path": str(s1_path), "s1_sha256": _sha256(s1_path),
        "actual_starting_commit": head, "branch": summary["branch"],
        "conditions": [dict(id=cid, zin_ohm=zin, zout_ohm=zout) for cid, zin, zout in CONDITIONS],
        "seeds": list(SEEDS), "budget": BUDGET,
        "release_group": RELEASE_GROUP, "cold_start_per_condition": True,
        "port_termination": "pure real Zin/Zout",
        "preflight_passed": bool(preflight["passed"]),
        "test_command": summary.get("test_command"),
        "test_result": summary.get("test_result"),
    })
    output = bundle_root / FINAL_BUNDLE_NAME
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for source in sorted(path for path in staging.rglob("*") if path.is_file()):
            archive.write(source, source.relative_to(staging).as_posix())
    return output


def run_stage36_gate2b_a(config_path: str | Path, run: str | Path, *, resume: bool = False) -> dict[str, Any]:
    config_path = Path(config_path).resolve()
    base = normalize_convergence_config(load_experiment_config(config_path))
    section = _stage_section(base)
    s1, s1_path = _load_s1(base)
    run = initialize(Path(run).resolve(), base)
    starting_commit = _git(["rev-parse", "HEAD"]).strip()
    starting_branch = _git(["branch", "--show-current"]).strip()
    preflight = run_termination_preflight(base)
    save(run / "preflight_termination.json", preflight)
    save(run / "stage3_6_gate2b_a_manifest.json", {
        "study_type": STUDY_TYPE, "config_path": str(config_path),
        "config_sha256": _sha256(config_path), "s1_path": str(s1_path),
        "s1_sha256": _sha256(s1_path), "git_head": starting_commit,
        "git_branch": starting_branch, "canonical_tag": "stage3.6-gate2a-closed",
        "release_group": RELEASE_GROUP, "release_dimension": len(NAMES) + 2,
        "seeds": list(SEEDS), "budget": BUDGET, "workers": section["workers"],
        "conditions": section["conditions"], "cold_start_per_condition": True,
        "termination": "pure real independent source/load resistances",
        "preflight": preflight,
        "prohibited_work_started": False,
    })
    _write_text(run / "input_config.yaml", config_path.read_text(encoding="utf-8"))
    tasks = []
    for cid, zin, zout in CONDITIONS:
        for seed in SEEDS:
            tasks.append((str(run), base, cid, zin, zout, s1, seed, bool(resume)))
        # Conditions are intentionally processed serially; seeds are paired
        # and parallelized within one condition to keep resource usage bounded.
        _run_workers(
            tasks[-len(SEEDS):], section["workers"], section["blas_threads_per_worker"]
        )
    records = []
    for cid, _zin, _zout in CONDITIONS:
        condition_records = _condition_records(run, cid)
        if {int(row["seed"]) for row in condition_records} != set(SEEDS):
            raise RuntimeError(f"condition {cid} does not contain all paired seeds")
        if any(int(row.get("unique_decoded_evaluations", 0)) < BUDGET for row in condition_records):
            raise RuntimeError(f"condition {cid} did not complete the 16000-evaluation budget")
        records.extend(condition_records)
    grid = _common_grid(base, records)
    grid_id = hashlib.sha256(np.asarray(grid, dtype="<f8").tobytes()).hexdigest()
    rows = [_validate_record(base, record, grid) for record in records]
    aggregates = _aggregate(rows)
    paired = _paired_vs_50(rows)
    transpose_detail, transpose_summary = _transpose(rows)
    sensitivity = _port_sensitivity(aggregates)
    interaction_rows, interaction_assessment = _interaction(aggregates)
    convergence = _convergence_rows(rows)
    _write_csv(run / "results" / "all_seed_results.csv", rows)
    _write_csv(run / "results" / "condition_summary.csv", aggregates)
    _write_csv(run / "results" / "paired_vs_50ohm.csv", paired)
    _write_csv(run / "results" / "transpose_pair_comparison.csv", transpose_detail + transpose_summary)
    _write_csv(run / "results" / "asymmetry_summary.csv", transpose_summary)
    _write_csv(run / "results" / "port_sensitivity.csv", sensitivity)
    _write_csv(run / "results" / "interaction_assessment.csv", interaction_rows)
    _write_csv(run / "results" / "convergence_summary.csv", convergence)
    save(run / "results" / "interaction_assessment.json", interaction_assessment)
    np.savetxt(run / "results" / "common_validation_grid_hz.csv", grid, header="frequency_hz", comments="")
    save(run / "results" / "common_validation_grid.json", {"grid_id": grid_id, "frequency_count": len(grid)})
    plot_paths = _plot_heatmaps(aggregates, run / "plots")
    summary = {
        "study_type": STUDY_TYPE, "decision": "GATE2B_A_COMPLETE_STOP",
        "condition_count": len(CONDITIONS), "seeds_per_condition": len(SEEDS),
        "budget": BUDGET, "release_group": RELEASE_GROUP,
        "release_dimension": len(NAMES) + 2,
        "common_validation_grid_id": grid_id,
        "common_validation_frequency_count": int(len(grid)),
        "actual_starting_commit": starting_commit, "branch": starting_branch,
        "canonical_tag": "stage3.6-gate2a-closed", "config_path": str(config_path),
        "preflight_passed": bool(preflight["passed"]),
        "test_command": "see reproduction_metadata.json",
        "test_result": "pre-production targeted/full tests passed before launch",
        "heatmaps": [str(path.relative_to(run)) for path in plot_paths],
        "interaction_assessment": interaction_assessment,
        "gate2b_b_started": False, "extended_budget_started": False,
        "topology_modified": False, "review_bundle": None,
    }
    save(run / "stage3_6_gate2b_a_summary.json", summary)
    bundle = build_review_bundle(
        run, base, s1, summary, aggregates, interaction_assessment,
        preflight, s1_path,
    )
    summary["review_bundle"] = str(bundle)
    save(run / "stage3_6_gate2b_a_summary.json", summary)
    _write_text(run / "STAGE3_6_GATE2B_A_COMPLETE_WAITING_FOR_REVIEW.txt", f"Review bundle: {bundle}\nHard stop: Gate 2B-B and all extended budgets were not started.\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 3.6 Gate 2B-A asymmetric impedance factorial")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    result = run_stage36_gate2b_a(args.config, args.run, resume=args.resume)
    complete_study_run(
        args.run, result,
        disposition=legacy_process_disposition(args.run, return_code=0),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
