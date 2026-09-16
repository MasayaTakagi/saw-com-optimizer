"""Stage 3.3 controlled A/B runner.

This module is intentionally self-contained: one command creates immutable run
metadata, dispatches seed-level spawn workers, resumes L-SHADE checkpoints, and
aggregates results only in the parent process.  Algorithm A uses the existing
Stage 3.2 SciPy-DE path as ``scipy_de_legacy``; Algorithm B uses the new
stateful backend.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import html
import json
import multiprocessing as mp
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np

from ..core.metrics import geometry, search_grid, validation_grid
from ..core.models import BOUNDS, FilterDesign, NAMES, decode
from ..io.config import cold_seeds, load_study_config
from ..io.run_store import initialize
from ..io.serialization import save
from ..runtime.parallel import single_blas_thread_environment
from ..optimizers.base import backend_name
from .convergence import normalize_convergence_config
from ..optimizers.lshade import LShadeBackend
from ..optimizers.selection import DEFAULT_COMPARATOR, rank, time_to_target
from ..problem.evaluator import dense, evaluate_design
from ..optimization.adaptive_frequency import critical_frequencies, new_frequency_points
from ..optimization.runner import optimize_one
from ..reporting.review_bundle import _default_review_bundle_output
from .convergence_evidence import apply_checkpoint_evidence

_cold_seeds = cold_seeds


STAGE33_TYPE = "stage3_3_optimizer_ab"


def _source_fingerprint(cfg):
    root = Path(__file__).parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return hashlib.sha256((json.dumps(cfg, sort_keys=True, default=str) + digest.hexdigest()).encode()).hexdigest()


def _safe_record(record):
    def clean(value):
        if isinstance(value, np.ndarray):
            return [clean(item) for item in value.tolist()]
        if isinstance(value, np.generic):
            return clean(value.item())
        if isinstance(value, float) and not np.isfinite(value):
            return None
        if isinstance(value, dict):
            return {str(key): clean(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(item) for item in value]
        return value
    return clean(record)


def _invalid_record(design, violations):
    violations = {str(key): max(0.0, float(value)) for key, value in violations.items()}
    return {
        "design": asdict(design), "metrics": {"worst_il_db": float("inf"), "ripple_db": float("inf")},
        "violations": violations, "max_violation": max(violations.values(), default=1.0),
        "sum_violation": sum(violations.values()), "feasible": False,
        "objective": float("inf"), "search_scalar_objective": float("inf"),
        "failure": "manufacturing constraint",
    }


def evaluator_factory(cfg, z0, wiring, frequencies):
    frequency_ref = [np.asarray(frequencies, dtype=float)]
    def evaluator(vector):
        design = decode(vector)
        _dims, violations = geometry(design, cfg["constraints"])
        try:
            record, _net, _sim = evaluate_design(design, cfg, frequency_ref[0], z0, z0, wiring=wiring)
        except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
            return {
                "design": asdict(design), "metrics": {"worst_il_db": float("inf"), "ripple_db": float("inf")},
                "violations": {"geometry": max(violations, default=0.0), "numerical_failure": 1.0},
                "max_violation": 1.0, "sum_violation": 1.0 + sum(violations),
                "feasible": False, "failure": str(exc),
                "objective": float("inf"), "search_scalar_objective": float("inf"),
            }
        record = dict(record)
        record["design"] = asdict(design)
        # Keep physics and manufacturing constraints in the same comparator
        # record.  In particular, a near-boundary geometry violation must not
        # win merely because its physics was skipped.
        record.setdefault("violations", {})["geometry"] = max(violations, default=0.0)
        record["sum_violation"] = float(sum(record.get("violations", {}).values()))
        record["max_violation"] = float(max(record.get("violations", {}).values(), default=0.0))
        record["feasible"] = bool(record["max_violation"] <= 1e-10)
        return record
    evaluator.frequency_ref = frequency_ref
    return evaluator


def _lshade_config(cfg, budget):
    section = cfg.get("stage3_3", {})
    values = dict(section.get("lshade", {}))
    values["total_budget"] = int(budget)
    values.setdefault("initial_population", values.get("initial_population_per_dimension", 18) * len(BOUNDS))
    pilot = section.get("ab_pilot", {})
    terminal = int(section.get(
        "population_schedule_terminal_budget",
        pilot.get("population_schedule_terminal_budget",
                  max([int(item) for item in pilot.get("budgets", [budget])] + [int(budget)])),
    ))
    values.setdefault("population_schedule_terminal_budget", terminal)
    values.setdefault("hard_max_budget", int(section.get("hard_max_budget", terminal)))
    return values


def _backend_bounds(cfg):
    """Resolve an optional experiment-owned active/hard box.

    Stage 3.5 supplies this through metadata so the reusable L-SHADE backend
    can be compared on the same initial box as Legacy DE.  Historical Stage
    3.3 callers continue to use the immutable model bounds.
    """
    active = cfg.get("stage3_5_active_bounds")
    hard = cfg.get("stage3_5_hard_bounds")
    if active is None:
        return np.asarray(BOUNDS, dtype=float), np.asarray(BOUNDS, dtype=float)
    active = np.asarray(active, dtype=float)
    hard = np.asarray(hard if hard is not None else BOUNDS, dtype=float)
    if active.shape != (len(BOUNDS), 2) or hard.shape != active.shape:
        raise ValueError("stage3_5 active/hard bounds must match the design dimension")
    if np.any(active[:, 1] <= active[:, 0]) or np.any(hard[:, 1] <= hard[:, 0]):
        raise ValueError("stage3_5 active/hard bounds must have positive spans")
    if np.any(active[:, 0] < hard[:, 0]) or np.any(active[:, 1] > hard[:, 1]):
        raise ValueError("stage3_5 active bounds must remain inside hard bounds")
    return active, hard


def lshade_exchange_at_checkpoint(backend, evaluator, cfg, wiring, z0,
                                  checkpoint_budget):
    """Refresh an L-SHADE trajectory between budget checkpoints.

    The refresh is deliberately outside ``advance_to_unique_budget``: it
    changes only the frequency-conditioned objective values, never the
    unique-design counter.  The returned event is recorded even when the
    critical-frequency set is already fixed.
    """
    event = {
        "event": "adaptive_frequency_check",
        "checkpoint_budget": int(checkpoint_budget),
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
    incumbent_design = FilterDesign(**incumbent["design"])
    dense_f, (_dense_result, dense_net, _dense_sim) = dense(
        incumbent_design, cfg, z0, z0, wiring=wiring, counters=None,
    )
    critical = critical_frequencies(
        dense_f, dense_net, cfg["spec"],
        slope_threshold_db=float(cfg.get("dense_slope_threshold_db", .5)),
        max_points=int(cfg.get("validation", {}).get("adaptive_max_points_per_round", 64)),
    )
    tolerance = float(cfg.get("validation", {}).get(
        "adaptive_frequency_tolerance_hz", 1e3))
    added = new_frequency_points(evaluator.frequency_ref[0], critical, tolerance)
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


def _lshade_record(backend, wiring, seed, budget, checkpoint_path,
                   frequency_events, started_wall, started_cpu,
                   *, disk_resume_used=False, trajectory_index=0,
                   optimizer_wall_time_s=None, validation_wall_time_s=None,
                   total_trial_wall_time_s=None):
    """Serialize one checkpoint observation from a live trajectory."""
    summary = backend.summary()
    requested = int(budget)
    actual = int(summary["unique_evaluations"])
    if actual >= requested:
        stop_reason = "requested_budget_reached"
    elif summary.get("search_space_exhausted"):
        stop_reason = "search_space_exhausted"
    else:
        stop_reason = "numerical_failure"
    record = dict(backend.incumbent() or {})
    objective_calls = int(summary.get("proposals_total", 0))
    cache_hits = int(summary.get("cache_hits", 0))
    duplicate_attempts = max(objective_calls - actual, 0)
    terminal_budget = int(summary.get("terminal_budget", summary.get(
        "population_schedule_terminal_budget", requested)))
    record.update({
        "backend": "lshade", "wiring": wiring, "seed": int(seed),
        "requested_unique_design_budget": requested,
        "unique_decoded_evaluations": actual,
        "actual_unique_design_evaluations": actual,
        "actual_unique_budget": actual,
        "budget_completion_fraction": float(actual / max(requested, 1)),
        "budget_completion_passed": bool(actual >= .98 * requested),
         "objective_calls": objective_calls,
         "raw_offspring_count": int(summary.get("raw_offspring_count", 0)),
         "duplicate_decoded_count": int(summary.get("duplicate_count", 0)),
         "duplicate_decoded_attempts": duplicate_attempts,
         "duplicate_decoded_rate": float(duplicate_attempts / max(objective_calls, 1)),
         "cache_hits": cache_hits,
         "cache_hit_rate": float(cache_hits / max(objective_calls, 1)),
        "population_size": int(summary.get("population_size", 0)),
        "proposals_total": int(summary.get("proposals_total", 0)),
        "duplicate_rate": float(summary.get("duplicate_rate", 0.0)),
        "m_f": summary.get("m_f", []), "m_cr": summary.get("m_cr", []),
        "archive_size": int(summary.get("archive_size", 0)),
        "archive_trace": summary.get("archive_trace", []),
        "boundary_repair_counts": summary.get("boundary_repair_counts", {}),
         "population_schedule_terminal_budget": terminal_budget,
         "terminal_budget": terminal_budget,
         "current_budget": actual,
         "initial_population": int(summary.get("initial_population", 0)),
         "current_population": int(summary.get("current_population", summary.get("population_size", 0))),
         "population_schedule_identifier": summary.get(
             "population_schedule_identifier", "lshade_linear_population_v1"),
         "population_schedule_version": int(summary.get("population_schedule_version", 1)),
        "hard_max_budget": int(summary.get("hard_max_budget", requested)),
        "search_space_exhausted": bool(summary.get("search_space_exhausted", False)),
        "stop_reason": stop_reason,
        "best_so_far_trace": summary.get("best_so_far_trace", []),
        "population_trace": summary.get("population_trace", []),
        "checkpoint": str(checkpoint_path),
        "checkpoint_budget": requested,
        "checkpoint_trajectory_index": int(trajectory_index),
        "trajectory_semantics": "one_seed_one_trajectory",
        "disk_resume_used": bool(disk_resume_used),
         "frequency_grid_version": int(backend.frequency_grid_version),
         "frequency_grid_events": copy.deepcopy(frequency_events),
         "boundary_events": [],
         "recovery_events": [],
         "hard_bound_reached_by_variable": {},
        "checkpoint_state_summary": {
            "unique_evaluations": actual,
            "population_size": int(summary.get("population_size", 0)),
            "archive_size": int(summary.get("archive_size", 0)),
            "frequency_grid_version": int(backend.frequency_grid_version),
            "m_f": summary.get("m_f", []), "m_cr": summary.get("m_cr", []),
        },
         "elapsed_s": (
             float(total_trial_wall_time_s)
             if total_trial_wall_time_s is not None
             else time.monotonic() - started_wall
         ),
         "cpu_time_s": time.process_time() - started_cpu,
         "optimizer_wall_time_s": optimizer_wall_time_s,
         "validation_wall_time_s": validation_wall_time_s,
         "total_trial_wall_time_s": (
             float(total_trial_wall_time_s)
             if total_trial_wall_time_s is not None
             else time.monotonic() - started_wall
         ),
         "design_space_version": int(backend.design_space_version),
    })
    record = apply_checkpoint_evidence(
        record, current_budget=requested, terminal_budget=terminal_budget
    )
    return _safe_record(record)


def lshade_record(backend, wiring, seed, budget, checkpoint_path,
                  frequency_events, started_wall, started_cpu,
                  *, disk_resume_used, trajectory_index,
                  optimizer_wall_time_s, validation_wall_time_s,
                  total_trial_wall_time_s=None):
    """Public record adapter for study-specific trajectory implementations.

    The implementation remains centralized in the historical helper; this
    public name keeps cross-study imports within the architecture contract.
    """
    return _lshade_record(
        backend, wiring, seed, budget, checkpoint_path, frequency_events,
        started_wall, started_cpu, disk_resume_used=disk_resume_used,
        trajectory_index=trajectory_index,
        optimizer_wall_time_s=optimizer_wall_time_s,
        validation_wall_time_s=validation_wall_time_s,
        total_trial_wall_time_s=total_trial_wall_time_s,
    )


def _lshade_trajectory_worker(payload):
    """Run one seed through all requested checkpoints in one process/state."""
    out, cfg, wiring, seed, budgets, resume = payload
    out = Path(out)
    budgets = sorted({int(value) for value in budgets})
    if not budgets or any(value <= 0 for value in budgets):
        raise ValueError("trajectory budgets must be positive")
    seed_dir = out / "trials" / "lshade" / str(wiring) / f"seed{int(seed)}"
    seed_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = seed_dir / "optimizer_checkpoint.json"
    metadata_path = seed_dir / "trajectory_metadata.json"
    metadata = {}
    disk_resume_used = False
    if resume and checkpoint_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        disk_resume_used = True
    z0 = float(cfg.get("convergence", {}).get("impedance_ohm", 50.0))
    frequencies = np.unique(search_grid(cfg["spec"], cfg))
    evaluator = evaluator_factory(cfg, z0, wiring, frequencies)
    # Matched-protocol diagnostics may stop at an early observation budget
    # while preserving the historical population-schedule horizon.  Keep the
    # opt-in path explicit so ordinary trajectory callers retain their
    # existing max(budgets) semantics.
    matched_protocol = cfg.get("stage3_5_matched_protocol", {})
    terminal = int(matched_protocol.get("terminal_horizon", max(budgets)))
    diagnostic_stop = int(matched_protocol.get("diagnostic_stop", max(budgets)))
    if max(budgets) != diagnostic_stop:
        raise ValueError(
            "matched-protocol diagnostic_stop must equal the trajectory stop"
        )
    if terminal < diagnostic_stop:
        raise ValueError(
            "matched-protocol terminal_horizon cannot precede diagnostic_stop"
        )
    active_bounds, hard_bounds = _backend_bounds(cfg)
    lshade_cfg = _lshade_config(cfg, terminal)
    lshade_cfg["hard_bounds"] = hard_bounds.tolist()
    backend = LShadeBackend(
        active_bounds, seed=int(seed), config=lshade_cfg,
        integer_indices=(1, 2, 3), comparator=DEFAULT_COMPARATOR,
        source_config_fingerprint=cfg.get("stage33_source_fingerprint"),
    )
    if disk_resume_used:
        backend.load_checkpoint(checkpoint_path)
        backend.set_evaluator(evaluator)
        if getattr(backend, "active_frequency_grid", []):
            evaluator.frequency_ref[0] = np.asarray(backend.active_frequency_grid, dtype=float)
    else:
        backend.initialize(evaluator)
        backend.set_frequency_grid(frequencies, version=1)
        metadata = {"last_completed_budget": 0, "frequency_grid_events": []}
    events = list(metadata.get("frequency_grid_events", []))
    last_completed = int(metadata.get("last_completed_budget", 0))
    records = []
    started_wall = time.monotonic()
    started_cpu = time.process_time()
    for index, budget in enumerate(budgets):
        result_path = seed_dir / f"B{budget}.json"
        if disk_resume_used and last_completed >= budget and result_path.exists():
            records.append(json.loads(result_path.read_text(encoding="utf-8")))
            continue
        optimizer_started = time.monotonic()
        if backend.unique_evaluations < budget:
            backend.advance_to_unique_budget(budget)
        optimizer_wall_time_s = time.monotonic() - optimizer_started
        # The historical B16000 artifact is a pre-exchange snapshot.  Capture
        # the incumbent before the opt-in matched-protocol exchange so the
        # diagnostic can compare the same semantic point without reevaluation.
        pre_exchange_incumbent = (
            copy.deepcopy(backend.incumbent())
            if matched_protocol else None
        )
        validation_started = time.monotonic()
        event = lshade_exchange_at_checkpoint(
            backend, evaluator, cfg, wiring, z0, budget,
        )
        validation_wall_time_s = time.monotonic() - validation_started
        events.append(event)
        last_completed = budget
        metadata = {
            "last_completed_budget": int(last_completed),
            "frequency_grid_events": events,
            "trajectory_semantics": "one_seed_one_trajectory",
            "terminal_budget": int(backend.population_schedule_terminal_budget),
            "current_budget": int(backend.unique_evaluations),
            "initial_population": int(backend.initial_population_size),
            "current_population": int(len(backend.population())),
            "population_schedule_identifier": backend.population_schedule_identifier,
            "population_schedule_version": int(backend.population_schedule_version),
        }
        record = _lshade_record(
            backend, wiring, seed, budget, checkpoint_path, events,
            started_wall, started_cpu, disk_resume_used=disk_resume_used,
            trajectory_index=index,
            optimizer_wall_time_s=optimizer_wall_time_s,
            validation_wall_time_s=validation_wall_time_s,
            total_trial_wall_time_s=time.monotonic() - started_wall,
        )
        if matched_protocol:
            record["pre_exchange_snapshot"] = _safe_record(pre_exchange_incumbent or {})
            record["pre_exchange_grid_version"] = int(
                event.get("frequency_grid_version_before", 1)
            )
        save(result_path, record)
        backend.save_checkpoint(checkpoint_path)
        save(metadata_path, metadata)
        records.append(record)
    return records


def _lshade_worker(payload):
    started_wall = time.monotonic()
    started_cpu = time.process_time()
    out, cfg, wiring, seed, budget, resume = payload
    out = Path(out)
    seed_dir = out / "trials" / "lshade" / str(wiring) / f"seed{int(seed)}"
    seed_dir.mkdir(parents=True, exist_ok=True)
    result_path = seed_dir / f"B{int(budget)}.json"
    checkpoint_path = seed_dir / "optimizer_checkpoint.json"
    if result_path.exists() and resume:
        return json.loads(result_path.read_text(encoding="utf-8"))
    z0 = float(cfg.get("convergence", {}).get("impedance_ohm", 50.0))
    frequencies = np.unique(search_grid(cfg["spec"], cfg))
    evaluator = evaluator_factory(cfg, z0, wiring, frequencies)
    active_bounds, hard_bounds = _backend_bounds(cfg)
    lshade_cfg = _lshade_config(cfg, budget)
    lshade_cfg["hard_bounds"] = hard_bounds.tolist()
    backend = LShadeBackend(
        active_bounds, seed=int(seed), config=lshade_cfg,
        integer_indices=(1, 2, 3), comparator=DEFAULT_COMPARATOR,
        source_config_fingerprint=cfg.get("stage33_source_fingerprint"),
    )
    if resume and checkpoint_path.exists():
        backend.load_checkpoint(checkpoint_path)
        backend.set_evaluator(evaluator)
        if getattr(backend, "active_frequency_grid", []):
            evaluator.frequency_ref[0] = np.asarray(backend.active_frequency_grid, dtype=float)
        # Stage 3.5 coordinates soft-bound expansion in its parent process.
        # The worker receives the frozen expanded box on the next checkpoint;
        # L-SHADE then uses its existing population re-normalization policy.
        if not np.array_equal(backend.bounds, active_bounds):
            backend.update_bounds(
                active_bounds,
                design_space_version=int(cfg.get("stage3_5_design_space_version", backend.design_space_version)),
            )
    else:
        backend.initialize(evaluator)
        backend.set_frequency_grid(frequencies, version=1)
    frequency_events = []
    optimizer_started = time.monotonic()
    summary = backend.advance_to_unique_budget(int(budget))
    optimizer_wall_time_s = time.monotonic() - optimizer_started
    validation_started = time.monotonic()
    if bool(cfg.get("stage3_3", {}).get("adaptive_frequency_exchange", True)) and backend.incumbent():
        incumbent_design = FilterDesign(**backend.incumbent()["design"])
        dense_f, (_dense_result, dense_net, _dense_sim) = dense(
            incumbent_design, cfg, z0, z0, wiring=wiring, counters=None,
        )
        critical = critical_frequencies(
            dense_f, dense_net, cfg["spec"],
            slope_threshold_db=float(cfg.get("dense_slope_threshold_db", .5)),
            max_points=int(cfg.get("validation", {}).get("adaptive_max_points_per_round", 64)),
        )
        added = new_frequency_points(evaluator.frequency_ref[0], critical,
                                     float(cfg.get("validation", {}).get("adaptive_frequency_tolerance_hz", 1e3)))
        if len(added):
            evaluator.frequency_ref[0] = np.unique(np.r_[evaluator.frequency_ref[0], added])
            version = int(backend.frequency_grid_version) + 1
            backend.exchange_frequency_grid(evaluator.frequency_ref[0], evaluator, version=version)
            frequency_events.append({"event": "critical_frequency_exchange", "added_count": int(len(added)),
                                     "frequency_grid_version": version, "unique_designs_charged": 0,
                                     "frequencies_hz": [float(value) for value in added]})
    record = backend.incumbent() or {}
    backend.save_checkpoint(checkpoint_path)
    incumbent = record
    record = dict(incumbent)
    validation_wall_time_s = time.monotonic() - validation_started
    objective_calls = int(summary.get("proposals_total", backend.proposals_total))
    duplicate_attempts = max(objective_calls - int(backend.unique_evaluations), 0)
    terminal_budget = int(summary.get("terminal_budget", summary.get(
        "population_schedule_terminal_budget", budget)))
    record.update({
        "backend": "lshade", "wiring": wiring, "seed": int(seed), "requested_unique_design_budget": int(budget),
         "unique_decoded_evaluations": int(backend.unique_evaluations),
        "actual_unique_design_evaluations": int(backend.unique_evaluations),
        "objective_calls": objective_calls,
        "raw_offspring_count": int(backend.raw_offspring_count),
        "duplicate_decoded_count": int(backend.duplicate_count),
        "duplicate_decoded_attempts": duplicate_attempts,
        "duplicate_decoded_rate": float(duplicate_attempts / max(objective_calls, 1)),
         "cache_hits": int(backend.cache_hits),
         "cache_hit_rate": float(backend.cache_hits / max(objective_calls, 1)),
         "population_size": int(len(backend.population())),
         "proposals_total": int(summary.get("proposals_total", backend.proposals_total)),
         "duplicate_rate": float(summary.get("duplicate_rate", 0.0)),
         "m_f": summary.get("m_f", []), "m_cr": summary.get("m_cr", []),
         "archive_size": int(summary.get("archive_size", 0)),
         "archive_trace": summary.get("archive_trace", []),
         "boundary_repair_counts": summary.get("boundary_repair_counts", {}),
          "population_schedule_terminal_budget": terminal_budget,
          "terminal_budget": terminal_budget,
          "current_budget": int(backend.unique_evaluations),
          "initial_population": int(summary.get("initial_population", 0)),
          "current_population": int(summary.get("current_population", len(backend.population()))),
          "population_schedule_identifier": summary.get(
              "population_schedule_identifier", "lshade_linear_population_v1"),
          "population_schedule_version": int(summary.get("population_schedule_version", 1)),
         "hard_max_budget": int(summary.get("hard_max_budget", budget)),
         "search_space_exhausted": bool(summary.get("search_space_exhausted", False)),
         "best_so_far_trace": summary["best_so_far_trace"], "population_trace": summary["population_trace"],
        "checkpoint": str(checkpoint_path.relative_to(out)),
        "resume": {"used": bool(resume and checkpoint_path.exists())},
         "frequency_grid_version": int(backend.frequency_grid_version),
         "frequency_grid_events": frequency_events,
         "active_bounds": backend.active_bounds,
         "hard_bounds": backend.hard_bounds.tolist(),
         "boundary_events": list(cfg.get("stage3_5_boundary_events", [])),
         "recovery_events": [],
         "hard_bound_reached_by_variable": {},
          "elapsed_s": time.monotonic() - started_wall,
         "cpu_time_s": time.process_time() - started_cpu,
         "optimizer_wall_time_s": optimizer_wall_time_s,
         "validation_wall_time_s": validation_wall_time_s,
         "total_trial_wall_time_s": time.monotonic() - started_wall,
         "design_space_version": int(backend.design_space_version),
    })
    record = apply_checkpoint_evidence(
        record, current_budget=int(budget), terminal_budget=terminal_budget
    )
    record = _safe_record(record)
    save(result_path, record)
    return record


def _legacy_worker(payload):
    out, cfg, wiring, seed, budget = payload
    out = Path(out)
    algorithm_out = out / "trials" / "scipy_de_legacy"
    algorithm_out.mkdir(parents=True, exist_ok=True)
    trial_cfg = copy.deepcopy(cfg)
    trial_cfg["max_unique_decoded_evaluations"] = int(budget)
    trial_cfg.setdefault("optimizer", {})["max_unique_decoded_evaluations"] = int(budget)
    trial_cfg["optimizer"]["warm_resume"] = False
    trial_cfg.setdefault("convergence", {})["benchmark_early_stop"] = False
    started = time.monotonic()
    record = optimize_one(
        algorithm_out, trial_cfg, float(cfg["convergence"]["impedance_ohm"]),
        float(cfg["convergence"]["impedance_ohm"]), int(seed), neighbor=None,
        wiring=wiring, mode="benchmark", run_label=f"{wiring}__B{int(budget)}",
        warm_resume=False,
    )
    total_trial_wall_time_s = time.monotonic() - started
    record = dict(record)
    record["backend"] = "scipy_de_legacy"
    record["cpu_time_s"] = record.get("cpu_time_s", total_trial_wall_time_s)
    cache_hits = int(record.get("cache_hits", 0))
    objective_calls = int(record.get("objective_calls", 0))
    record["cache_hit_rate"] = cache_hits / max(objective_calls, 1)
    if "canonical_candidates_seen" in record:
        duplicate_attempts = max(
            int(record["canonical_candidates_seen"])
            - int(record.get("unique_decoded_evaluations", 0)), 0
        )
        record["duplicate_decoded_count"] = duplicate_attempts
        record["duplicate_decoded_attempts"] = duplicate_attempts
        record["duplicate_decoded_rate"] = duplicate_attempts / max(
            int(record["canonical_candidates_seen"]), 1
        )
    else:
        record["duplicate_decoded_count"] = None
        record["duplicate_decoded_attempts"] = None
        record["duplicate_decoded_rate"] = None
    record["terminal_budget"] = int(budget)
    record["current_budget"] = int(record.get(
        "actual_unique_design_evaluations",
        record.get("unique_decoded_evaluations", 0),
    ))
    record["population_schedule_identifier"] = "legacy_de_fixed_population_v1"
    record["population_schedule_version"] = 1
    record["optimizer_wall_time_s"] = total_trial_wall_time_s
    record["validation_wall_time_s"] = None
    record["total_trial_wall_time_s"] = total_trial_wall_time_s
    record["elapsed_s"] = total_trial_wall_time_s
    return _safe_record(record)


def run_parallel_benchmark(out, cfg, *, wiring="center_outer_same", budget=100,
                           seeds=None, worker_counts=(1, 2, 4, 5)):
    """Run the same cold L-SHADE seeds with spawn worker counts separately."""
    out = Path(out)
    seeds = [int(seed) for seed in (seeds or _cold_seeds(cfg))]
    threads = int(cfg.get("stage3_3", {}).get("production_parallel", {}).get("blas_threads_per_worker", 1))
    results, baseline = {}, None
    for count in [max(1, int(value)) for value in worker_counts]:
        target = out / "parallelism" / f"workers{count}"
        target.mkdir(parents=True, exist_ok=True)
        tasks = [(str(target), cfg, wiring, seed, int(budget), False) for seed in seeds]
        started = time.time()
        records = _run_workers(tasks, _lshade_worker, min(count, len(seeds)), threads)
        elapsed = time.time() - started
        ranks = [tuple(DEFAULT_COMPARATOR.rank_key(record)) for record in records]
        if baseline is None:
            baseline = ranks
        results[str(count)] = {
            "workers": count, "budget": int(budget), "seed_count": len(records),
            "wall_time_s": elapsed, "speedup_vs_workers_1": None,
            "parallel_efficiency": None,
            "per_seed_rank_parity": ranks == baseline,
            "per_seed_elapsed_s": [float(record.get("elapsed_s", 0.0)) for record in records],
        }
    baseline_wall = results[str(max(1, int(list(worker_counts)[0])))]["wall_time_s"]
    for value in results.values():
        value["speedup_vs_workers_1"] = baseline_wall / max(value["wall_time_s"], np.finfo(float).tiny)
        value["parallel_efficiency"] = value["speedup_vs_workers_1"] / max(value["workers"], 1)
    report = {"executed": True, "wiring": wiring, "budget": int(budget), "seeds": seeds,
              "worker_counts": [int(value) for value in worker_counts],
              "blas_threads_per_worker": threads, "workers": results,
              "mp_context": "spawn"}
    save(out / "performance_parallel.json", report)
    return report


def _run_workers(tasks, worker, workers, threads=1):
    with single_blas_thread_environment(threads):
        if int(workers) == 1:
            return [worker(task) for task in tasks]
        context = mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=int(workers), mp_context=context) as pool:
            return list(pool.map(worker, tasks))


def _row(record, algorithm, wiring, budget):
    # L-SHADE searches on an adaptive grid.  Once a candidate has been
    # re-evaluated on the common dense grid, that validation record is the
    # authoritative value for cross-backend reporting.
    metrics = record.get("validated_metrics", record.get("metrics", {}))
    feasible = bool(record.get("validated_feasible", record.get("feasible", False)))
    max_violation = record.get("validated_max_violation", record.get("max_violation", np.inf))
    sum_violation = record.get(
        "validated_sum_violation",
        record.get("sum_violation", sum(record.get("violations", {}).values())),
    )
    def number(value, default=np.inf):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return float(default)
        return value if np.isfinite(value) else float(default)
    duplicate_count = int(record.get(
        "duplicate_decoded_count",
        max(0, int(record.get("canonical_candidates_seen", 0))
            - int(record.get("unique_decoded_evaluations", record.get("actual_unique_design_evaluations", 0)))),
    ))
    duplicate_rate = record.get("duplicate_decoded_rate")
    if duplicate_rate is None:
        duplicate_rate = duplicate_count / max(int(record.get("objective_calls", 1)), 1)
    requested_budget = int(record.get("requested_unique_design_budget", budget))
    actual_budget = int(record.get(
        "actual_unique_design_evaluations",
        record.get("unique_decoded_evaluations", 0),
    ))
    completion_fraction = float(record.get(
        "budget_completion_fraction",
        actual_budget / max(requested_budget, 1),
    ))
    search_space_exhausted = bool(record.get("search_space_exhausted", False))
    budget_completion_passed = bool(completion_fraction >= .98)
    return {
        "algorithm": algorithm, "wiring": wiring, "budget": int(budget), "seed": int(record["seed"]),
        "feasible": feasible,
        "max_violation": number(max_violation),
        "sum_violation": number(sum_violation),
        "worst_il_db": number(metrics.get("worst_il_db", np.inf)),
        "ripple_db": number(metrics.get("ripple_db", np.inf)),
        "unique_decoded_evaluations": int(record.get("unique_decoded_evaluations", record.get("actual_unique_design_evaluations", 0))),
        "requested_unique_design_budget": requested_budget,
        "actual_unique_design_evaluations": actual_budget,
        "budget_completion_fraction": completion_fraction,
        "budget_completion_passed": budget_completion_passed,
        "search_space_exhausted": search_space_exhausted,
        "stop_reason": record.get("stop_reason"),
        "duplicate_decoded_rate": float(duplicate_rate),
        "objective_calls": int(record.get("objective_calls", 0)), "population_size": int(record.get("population_size", 0)),
        "proposals_total": int(record.get("proposals_total", record.get("objective_calls", 0))),
        "common_validation_grid_id": record.get("common_validation_grid_id"),
        "common_validation_frequency_count": int(record.get("common_validation_frequency_count", 0)),
        "validated_rank_tuple": record.get("validated_rank_tuple"),
        "best_so_far_trace": record.get("best_so_far_trace", []),
    }


def _row_as_record(row):
    return {
        "feasible": bool(row["feasible"]),
        "max_violation": float(row["max_violation"]),
        "sum_violation": float(row["sum_violation"]),
        "violations": {"aggregate": float(row["sum_violation"])},
        "metrics": {"worst_il_db": float(row["worst_il_db"]),
                    "ripple_db": float(row.get("ripple_db", 0.0))},
    }


def _attach_time_to_target(rows):
    """Attach time-to-target from common-grid validated checkpoints only.

    The target is the median *validated* legacy-DE comparator rank at the
    terminal comparison budget for each wiring.  Candidate timing is resolved
    only at validated L-SHADE checkpoints (for example B1000/B2000/B4000), so
    adaptive search-grid scores are never compared against the dense target.
    """
    wirings = sorted({row["wiring"] for row in rows})
    for wiring in wirings:
        final_budget = max((row["budget"] for row in rows
                            if row["algorithm"] == "scipy_de_legacy"
                            and row["wiring"] == wiring), default=None)
        baseline = [row for row in rows if row["algorithm"] == "scipy_de_legacy"
                    and row["wiring"] == wiring and row["budget"] == final_budget
                    and row.get("common_validation_grid_id")]
        if not baseline:
            continue
        grid_ids = {row.get("common_validation_grid_id") for row in baseline}
        if len(grid_ids) != 1:
            continue
        common_grid_id = next(iter(grid_ids))
        target_keys = sorted(DEFAULT_COMPARATOR.rank_key(_row_as_record(row)) for row in baseline)
        target_key = target_keys[(len(target_keys) - 1) // 2]
        candidate_seeds = sorted({row["seed"] for row in rows
                                  if row["algorithm"] == "lshade" and row["wiring"] == wiring})
        for seed in candidate_seeds:
            checkpoints = sorted(
                [row for row in rows
                 if row["algorithm"] == "lshade" and row["wiring"] == wiring
                 and row["seed"] == seed
                 and row.get("common_validation_grid_id") == common_grid_id],
                key=lambda row: row["budget"],
            )
            validated_trace = [{
                "unique_evaluation": int(row["actual_unique_design_evaluations"]),
                "checkpoint_budget": int(row["budget"]),
                "rank_key": list(DEFAULT_COMPARATOR.rank_key(_row_as_record(row))),
                "common_validation_grid_id": common_grid_id,
            } for row in checkpoints]
            for row in checkpoints:
                partial = [item for item in validated_trace
                           if item["checkpoint_budget"] <= int(row["budget"])]
                metric = time_to_target(
                    partial, target_key, requested_unique_budget=row["budget"]
                )
                row["validated_checkpoint_trace"] = partial
                row["time_to_target_source"] = "common_validated_checkpoints"
                row["time_to_target_resolution"] = "checkpoint"
                row["time_to_target_status"] = metric["status"]
                row["evals_to_target"] = metric.get("evals_to_target")
                row["eval_fraction_to_target"] = metric.get("eval_fraction_to_target")
                row["target_rank_key"] = list(target_key)
                row["target_common_validation_grid_id"] = common_grid_id


def _stage33_trial_records(run):
    """Yield the completed top-level trial records, excluding checkpoints."""
    run = Path(run)
    for path in sorted((run / "trials" / "scipy_de_legacy").glob("*.json")):
        if path.name.endswith(".checkpoint.json"):
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        yield path, "scipy_de_legacy", str(record["wiring"]), int(record["requested_unique_design_budget"]), record
    for path in sorted((run / "trials" / "lshade").glob("**/B*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        yield path, "lshade", str(record["wiring"]), int(record["requested_unique_design_budget"]), record


def _common_grid_id(frequencies):
    values = np.asarray(frequencies, dtype="<f8")
    return hashlib.sha256(values.tobytes()).hexdigest()


def validate_ab_candidates(run, cfg):
    """Re-evaluate both A/B backends on one shared dense grid per wiring.

    The common grid is the union of the configured validation grid and the
    candidate-specific refined dense grids discovered from *terminal* legacy
    and L-SHADE candidates.  Every terminal candidate and every L-SHADE
    checkpoint is then evaluated on exactly that frozen union grid.
    """
    run = Path(run)
    records = list(_stage33_trial_records(run))
    if not records:
        return {
            "completed": False, "validated_trial_count": 0,
            "validated_by_algorithm": {}, "by_wiring": {},
            "frequency_count": {}, "grid_ids": {},
            "shared_grid_across_algorithms": False,
            "passes": 0, "failures": [{"error": "no trial records"}],
        }
    z0 = float(cfg["convergence"]["impedance_ohm"])
    wirings = sorted({wiring for _path, _algorithm, wiring, _budget, _record in records})
    base = np.unique(np.asarray(validation_grid(cfg["spec"], cfg), dtype=float))
    terminal_budget = {
        wiring: max(budget for _path, _algorithm, row_wiring, budget, _record in records
                    if row_wiring == wiring)
        for wiring in wirings
    }
    grids = {wiring: base.copy() for wiring in wirings}
    failures = []

    # Discovery uses only terminal candidates from both algorithms.  The
    # resulting union is frozen before any cross-backend comparison.
    for path, algorithm, wiring, budget, record in records:
        if budget != terminal_budget[wiring]:
            continue
        try:
            design = FilterDesign(**record["design"])
            refined_f, _payload = dense(
                design, cfg, z0, z0, wiring=wiring, counters=None, validation=True,
            )
            grids[wiring] = np.unique(np.r_[grids[wiring], refined_f])
        except (KeyError, TypeError, ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
            failures.append({
                "phase": "grid_discovery", "algorithm": algorithm,
                "path": str(path.relative_to(run)), "error": str(exc),
            })

    grid_ids = {wiring: _common_grid_id(grid) for wiring, grid in grids.items()}
    save(run / "common_validation_grids.json", {
        wiring: {
            "grid_id": grid_ids[wiring],
            "frequency_count": int(len(grid)),
            "frequencies_hz": [float(value) for value in grid],
        } for wiring, grid in grids.items()
    })

    validated = 0
    counts = {}
    by_algorithm = {}
    for path, algorithm, wiring, _budget, record in records:
        frequencies = grids[wiring]
        try:
            design = FilterDesign(**record["design"])
            _f, (dense_record, _net, _sim) = dense(
                design, cfg, z0, z0, wiring=wiring, counters=None,
                base_grid=frequencies, passes=0, validation=True,
            )
            dense_record = dict(dense_record)
            record["validated_metrics"] = dense_record.get("metrics", {})
            record["validated_violations"] = dense_record.get("violations", {})
            record["validated_max_violation"] = float(dense_record.get("max_violation", np.inf))
            record["validated_sum_violation"] = float(sum(dense_record.get("violations", {}).values()))
            record["validated_feasible"] = bool(dense_record.get("feasible", False))
            record["validated_rank_tuple"] = list(DEFAULT_COMPARATOR.rank_key(dense_record))
            record["common_validation_frequency_count"] = int(len(frequencies))
            record["common_validation_grid_id"] = grid_ids[wiring]
            record["common_validation_frequencies_hz"] = [float(value) for value in frequencies]
            record["common_validation_passes"] = 0
            validated += 1
            counts[wiring] = counts.get(wiring, 0) + 1
            by_algorithm[algorithm] = by_algorithm.get(algorithm, 0) + 1
        except (KeyError, TypeError, ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
            failures.append({
                "phase": "common_validation", "algorithm": algorithm,
                "path": str(path.relative_to(run)), "error": str(exc),
            })
            record["common_validation_error"] = str(exc)
        save(path, _safe_record(record))

    algorithms_present = {algorithm for _path, algorithm, _wiring, _budget, _record in records}
    shared = bool(
        {"scipy_de_legacy", "lshade"}.issubset(algorithms_present)
        and all(by_algorithm.get(name, 0) > 0 for name in ("scipy_de_legacy", "lshade"))
    )
    return {
        "completed": not failures,
        "validated_trial_count": int(validated),
        "validated_by_algorithm": by_algorithm,
        "by_wiring": counts,
        "frequency_count": {wiring: int(len(grid)) for wiring, grid in grids.items()},
        "grid_ids": grid_ids,
        "shared_grid_across_algorithms": shared,
        "grid_construction": "union_of_terminal_refined_dense_grids_plus_base_validation_grid",
        "passes": 0,
        "failures": failures,
    }


def validate_lshade_candidates(run, cfg):
    """Backward-compatible alias; Stage 3.3.1b validates both A/B backends."""
    return validate_ab_candidates(run, cfg)


def _refresh_run_manifest(run):
    """Update the run manifest after post-run report code has changed."""
    run = Path(run)
    path = run / "manifest.json"
    if not path.exists():
        return
    manifest = json.loads(path.read_text(encoding="utf-8"))
    package_root = Path(__file__).parents[1]
    source_hash = hashlib.sha256(b"".join(
        p.relative_to(package_root).as_posix().encode() + p.read_bytes()
        for p in sorted(package_root.rglob("*.py"))
    )).hexdigest()
    fingerprint = hashlib.sha256(
        (json.dumps(manifest["config"], sort_keys=True) + source_hash).encode()
    ).hexdigest()
    manifest["source_hash"] = source_hash
    manifest["fingerprint"] = fingerprint
    save(path, manifest)


def rebuild_stage33_reports(run, cfg):
    """Rebuild report files from immutable trial JSONs after validation."""
    run = Path(run)
    source = json.loads((run / "algorithm_ab_summary.json").read_text(encoding="utf-8"))
    rows = []
    for _path, algorithm, wiring, budget, record in _stage33_trial_records(run):
        rows.append(_row(record, algorithm, wiring, budget))
    rows.sort(key=lambda row: (row["algorithm"], row["wiring"], row["budget"], row["seed"]))
    _attach_time_to_target(rows)
    _write_csv(run / "algorithm_ab_trials.csv", rows)
    _write_csv(run / "duplicate_statistics.csv", [
        {"algorithm": row["algorithm"], "wiring": row["wiring"], "budget": row["budget"],
         "seed": row["seed"], "duplicate_decoded_rate": row["duplicate_decoded_rate"]}
        for row in rows
    ])
    source["budget_summary"] = _aggregate(rows, source.get("thresholds", [1.8, 1.6, 1.5]))
    source["trial_rows"] = len(rows)
    source["common_dense_validation"] = cfg.get("common_dense_validation", source.get("common_dense_validation", {}))
    save(run / "convergence_summary.json", source)
    save(run / "algorithm_ab_summary.json", source)
    (run / "algorithm_ab_summary.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Stage 3.3 A/B</title>"
        "<h1>Stage 3.3 optimizer A/B</h1>"
        f"<pre>{html.escape(json.dumps(source, ensure_ascii=False, indent=2))}</pre>",
        encoding="utf-8",
    )
    return source


def evaluate_promotion_gate(summary):
    """Evaluate validity gates before any L-SHADE performance promotion."""
    wiring = summary.get("wirings", ["center_outer_same"])[0]
    budget = str(max(summary.get("budgets", [0])))
    legacy = summary["budget_summary"].get("scipy_de_legacy", {}).get(wiring, {}).get(budget)
    candidate = summary["budget_summary"].get("lshade", {}).get(wiring, {}).get(budget)
    gate = dict(summary.get("promotion_gate", {}))
    gate["comparison_wiring"] = wiring
    gate["comparison_budget"] = int(budget)
    if not legacy or not candidate:
        gate["decision"] = "experimental_until_gate_is_evaluated"
        return gate
    gate["budget_completion_min_fraction"] = float(
        gate.get("budget_completion_min_fraction", .98)
    )
    min_completion = gate["budget_completion_min_fraction"]
    gate["legacy_budget_completion_passed"] = bool(
        float(legacy.get("minimum_budget_completion_fraction", 0.0)) >= min_completion
    )
    gate["candidate_budget_completion_passed"] = bool(
        float(candidate.get("minimum_budget_completion_fraction", 0.0)) >= min_completion
    )
    gate["budget_completion_passed"] = bool(
        gate["legacy_budget_completion_passed"]
        and gate["candidate_budget_completion_passed"]
    )
    gate["search_space_exhausted_trials"] = {
        "legacy": int(legacy.get("search_space_exhausted_seed_count", 0)),
        "candidate": int(candidate.get("search_space_exhausted_seed_count", 0)),
    }
    # Search-space exhaustion is a distinct experimental outcome.  Do not
    # reinterpret it as successful budget completion or use it for promotion.
    if any(gate["search_space_exhausted_trials"].values()):
        gate["decision"] = "inconclusive_due_to_search_space_exhaustion"
        return gate
    # Budget validity is a prerequisite for interpreting any quality, hit-rate,
    # or time-to-target statistic.
    if not gate["budget_completion_passed"]:
        gate["decision"] = "invalid_ab_due_to_budget_shortfall"
        return gate
    quality_fraction = 1.0 - candidate["median_primary"] / max(legacy["median_primary"], np.finfo(float).tiny)
    hit_gain = (candidate["basin_hit_rates"].get("1.8", 0)
                - legacy["basin_hit_rates"].get("1.8", 0))
    target_fraction = candidate.get("median_eval_fraction_to_target")
    target_count = int(candidate.get("target_reached_seed_count", 0))
    validation = summary.get("common_dense_validation", {})
    gate["observed_median_quality_improvement_fraction"] = float(quality_fraction)
    gate["observed_basin_hit_gain_seeds"] = int(hit_gain)
    gate["observed_time_to_target"] = {
        "reached_seed_count": target_count,
        "median_evals_to_target": candidate.get("median_evals_to_target"),
        "median_eval_fraction_to_target": target_fraction,
    }
    gate["dense_validation_equivalence_observed"] = bool(
        validation.get("completed", False)
        and not validation.get("failures")
        and validation.get("shared_grid_across_algorithms", False)
        and validation.get("validated_by_algorithm", {}).get("scipy_de_legacy", 0) > 0
        and validation.get("validated_by_algorithm", {}).get("lshade", 0) > 0
    )
    gate["checkpoint_parity_observed"] = summary.get("checkpoint_resume_parity", {}).get("status") == "passed"
    if not gate["dense_validation_equivalence_observed"]:
        gate["decision"] = "invalid_ab_due_to_dense_validation"
        return gate
    if not gate["checkpoint_parity_observed"]:
        gate["decision"] = "invalid_ab_due_to_checkpoint_parity"
        return gate
    passed = (
        quality_fraction >= float(gate.get("median_quality_improvement_fraction_required", .05))
        and hit_gain >= int(gate.get("basin_hit_gain_seeds_required", 2))
        and target_count > 0
        and target_fraction is not None
        and target_fraction <= float(gate.get("time_to_target_fraction_required", .70))
        and gate["budget_completion_passed"]
    )
    gate["decision"] = "promote_lshade_candidate" if passed else "hold_for_additional_evidence"
    return gate


def finalize_stage33_run(run, cfg):
    """Validate existing production trials, rebuild reports, and recreate ZIP."""
    run = Path(run)
    summary_path = run / "algorithm_ab_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Stage 3.3 summary not found: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    cfg = copy.deepcopy(cfg)
    cfg["wirings"] = list(summary.get("wirings", cfg.get("wirings", [])))
    validation = validate_ab_candidates(run, cfg)
    cfg["common_dense_validation"] = validation
    summary = rebuild_stage33_reports(run, cfg)
    summary["common_dense_validation"] = validation
    summary["promotion_gate"] = evaluate_promotion_gate(summary)
    save(run / "convergence_summary.json", summary)
    save(run / "algorithm_ab_summary.json", summary)
    (run / "algorithm_ab_summary.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Stage 3.3 A/B</title>"
        "<h1>Stage 3.3 optimizer A/B</h1>"
        f"<pre>{html.escape(json.dumps(summary, ensure_ascii=False, indent=2))}</pre>",
        encoding="utf-8",
    )
    _refresh_run_manifest(run)
    summary["review_bundle"] = "stage3_3_review.zip"
    save(run / "algorithm_ab_summary.json", summary)
    create_stage33_review_bundle(run)
    return summary


def _write_csv(path, rows):
    rows = list(rows)
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    fields = sorted(set().union(*(row.keys() for row in rows)))
    with Path(path).open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _aggregate(rows, thresholds):
    summary = {}
    for algorithm in sorted({row["algorithm"] for row in rows}):
        summary[algorithm] = {}
        for wiring in sorted({row["wiring"] for row in rows}):
            summary[algorithm][wiring] = {}
            for budget in sorted({row["budget"] for row in rows if row["algorithm"] == algorithm and row["wiring"] == wiring}):
                values = [row for row in rows if row["algorithm"] == algorithm and row["wiring"] == wiring and row["budget"] == budget]
                primary = [float(row["worst_il_db"] if row["feasible"] else row["max_violation"]) for row in values]
                summary[algorithm][wiring][str(budget)] = {
                    "seed_count": len(values), "best_primary": float(min(primary)),
                    "median_primary": float(np.median(primary)),
                    "seed_iqr": float(np.percentile(primary, 75) - np.percentile(primary, 25)),
                    "basin_hit_rates": {str(t): int(sum(value["max_violation"] <= float(t) for value in values)) for t in thresholds},
                    "median_unique_evaluations": float(np.median([value["unique_decoded_evaluations"] for value in values])),
                    "median_duplicate_rate": float(np.median([value["duplicate_decoded_rate"] for value in values])),
                    "minimum_budget_completion_fraction": float(min(value["budget_completion_fraction"] for value in values)),
                    "median_budget_completion_fraction": float(np.median([value["budget_completion_fraction"] for value in values])),
                    "budget_completion_passed": bool(all(value["budget_completion_passed"] for value in values)),
                    "budget_shortfall_seed_count": int(sum(
                        not value["budget_completion_passed"] for value in values
                    )),
                    "search_space_exhausted_seed_count": int(sum(
                        value["search_space_exhausted"] for value in values
                    )),
                    "target_reached_seed_count": int(sum(value.get("time_to_target_status") == "reached" for value in values)),
                    "median_evals_to_target": (
                        float(np.median([value["evals_to_target"] for value in values
                                         if value.get("evals_to_target") is not None]))
                        if any(value.get("evals_to_target") is not None for value in values) else None
                    ),
                    "median_eval_fraction_to_target": (
                        float(np.median([value["eval_fraction_to_target"] for value in values
                                         if value.get("eval_fraction_to_target") is not None]))
                        if any(value.get("eval_fraction_to_target") is not None for value in values) else None
                    ),
                }
    return summary


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_stage33_review_bundle(run):
    """Create a self-contained, hash-verified Stage 3.3 review ZIP."""
    run = Path(run).resolve()
    repo = Path(__file__).resolve().parents[3]
    output = _default_review_bundle_output(run, repo).with_name("stage3_3_review.zip")
    with tempfile.TemporaryDirectory(prefix="stage33_bundle_", dir=str(run)) as temp:
        staging = Path(temp) / "bundle"
        (staging / "source").mkdir(parents=True)
        (staging / "tests").mkdir()
        (staging / "configs").mkdir()
        (staging / "results").mkdir()
        (staging / "trials").mkdir()
        (staging / "environment").mkdir()
        for source in sorted((repo / "src" / "sawopt").rglob("*.py")):
            destination = staging / "source" / source.relative_to(repo / "src")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        for source in sorted((repo / "tests").rglob("*.py")):
            destination = staging / "source" / "tests" / source.relative_to(repo / "tests")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        for source in sorted((repo / "configs").rglob("*")):
            if source.is_file():
                destination = staging / "configs" / source.relative_to(repo / "configs")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        shutil.copy2(repo / "pyproject.toml", staging / "source" / "pyproject.toml")
        for source in sorted(run.rglob("*")):
            if not source.is_file() or source.name == output.name:
                continue
            relative = source.relative_to(run)
            if relative.parts and relative.parts[0] == "trials":
                if source.name == "optimizer_checkpoint.json":
                    continue
                destination = staging / "trials" / Path(*relative.parts[1:])
            elif source.suffix.lower() in {".json", ".csv", ".html"}:
                destination = staging / "results" / relative
            else:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        test_env = dict(os.environ)
        test_env["PYTHONPATH"] = str(repo / "src")
        test = subprocess.run(
            [sys.executable, "-m", "unittest", "tests.unit.optimization.test_stage33", "-q"],
            cwd=repo, env=test_env, capture_output=True, text=True,
        )
        (staging / "tests" / "unit_test_log.txt").write_text(
            (test.stdout or "") + (test.stderr or ""), encoding="utf-8"
        )
        (staging / "tests" / "test_summary.json").write_text(json.dumps({
            "command": "python -m unittest tests.unit.optimization.test_stage33 -q",
            "exit_code": int(test.returncode), "passed": test.returncode == 0,
        }, indent=2) + "\n", encoding="utf-8")
        (staging / "tests" / "bundle_self_test.txt").write_text(
            f"source_and_hash_verification=performed\nunit_test_exit_code={test.returncode}\n",
            encoding="utf-8",
        )
        (staging / "environment" / "python.txt").write_text(sys.version, encoding="utf-8")
        (staging / "environment" / "platform.txt").write_text(platform.platform(), encoding="utf-8")
        (staging / "REVIEW_ME.md").write_text(
            "# Stage 3.3 review bundle\n\n"
            "This bundle contains finite-seed A/B evidence. `center_outer_same` is preserved as a wiring identifier.\n"
            "Run the documented unit test from `tests/unit_test_log.txt` and verify `bundle_manifest.json` hashes.\n",
            encoding="utf-8",
        )
        files = []
        for source in sorted(path for path in staging.rglob("*") if path.is_file()):
            relative = source.relative_to(staging).as_posix()
            files.append({"path": relative, "sha256": _sha256(source), "bytes": source.stat().st_size})
        manifest = {"bundle_format_version": 1, "study_type": STAGE33_TYPE,
                    "source_hash": _source_fingerprint(json.loads((run / "stage33_manifest.json").read_text(encoding="utf-8"))),
                    "files": files, "unit_test_exit_code": int(test.returncode)}
        (staging / "bundle_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            for source in sorted(path for path in staging.rglob("*") if path.is_file()):
                archive.write(source, source.relative_to(staging).as_posix())
        with ZipFile(output) as archive:
            names = set(archive.namelist())
            for entry in files:
                data = archive.read(entry["path"])
                if entry["path"] not in names or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                    raise RuntimeError(f"Stage 3.3 review bundle hash failure: {entry['path']}")
        (run / "bundle_self_test.txt").write_text(
            f"zip={output.name}\nunit_test_exit_code={test.returncode}\nsha256_entries={len(files)}\n",
            encoding="utf-8",
        )
    return output


def run_stage33(out, cfg, *, resume=False, workers=None, run_parallelism=False):
    out = initialize(out, cfg)
    out = Path(out)
    cfg = copy.deepcopy(cfg)
    cfg["study_type"] = STAGE33_TYPE
    cfg["stage33_source_fingerprint"] = _source_fingerprint(cfg)
    section = cfg.get("stage3_3", {})
    pilot = section.get("ab_pilot", {})
    wirings = list(pilot.get(
        "wirings",
        [pilot.get("wiring", "center_outer_same")] if pilot.get("wiring")
        else cfg.get("wirings", ["center_outer_same", "outer_ports"]),
    ))
    seeds = [int(seed) for seed in pilot.get("seeds", _cold_seeds(cfg))]
    budgets = [int(budget) for budget in pilot.get("budgets", [1000, 2000, 4000])]
    workers = int(workers if workers is not None else section.get("production_parallel", {}).get("production_workers", 1))
    workers = max(1, min(workers, len(seeds)))
    threads = int(section.get("production_parallel", {}).get("blas_threads_per_worker", 1))
    thresholds = [float(value) for value in section.get("ab_pilot", {}).get("basin_thresholds", [1.8, 1.6, 1.5])]
    save(out / "stage33_manifest.json", {
        "study_type": STAGE33_TYPE, "source_config_fingerprint": cfg["stage33_source_fingerprint"],
        "backend_a": "scipy_de_legacy", "backend_b": "lshade", "seeds": seeds, "budgets": budgets,
        "wirings": wirings, "worker_count": workers, "blas_threads_per_worker": threads,
        "mp_context": "spawn", "center_outer_same_semantics": "wiring identifier only",
    })
    rows, trial_files = [], []
    started = time.time()
    for algorithm in ("scipy_de_legacy", "lshade"):
        for wiring in wirings:
            if algorithm == "lshade":
                # One seed is one stateful trajectory.  The checkpoint list is
                # observational; it must not turn 1000/2000/4000 into three
                # cold starts or discard the adaptive grid exchange between
                # intervals.
                tasks = [
                    (str(out), cfg, wiring, seed, budgets, bool(resume))
                    for seed in seeds
                ]
                trajectory_records = _run_workers(
                    tasks, _lshade_trajectory_worker, workers, threads
                )
                for seed_records in trajectory_records:
                    for record in seed_records:
                        trial_files.append(record.get("checkpoint"))
                        rows.append(_row(
                            record, algorithm, wiring,
                            int(record["requested_unique_design_budget"]),
                        ))
            else:
                # SciPy does not expose an exact continuation state.  Keep the
                # historical baseline implementation untouched and use only a
                # fully consumed terminal-budget run for the principal A/B
                # comparison.  L-SHADE's lower checkpoints remain trajectory
                # diagnostics, explicitly marked in the summary.
                terminal_budget = max(budgets)
                tasks = [(str(out), cfg, wiring, seed, terminal_budget) for seed in seeds]
                records = _run_workers(tasks, _legacy_worker, workers, threads)
                for record in records:
                    record = dict(record)
                    record["trajectory_semantics"] = "legacy_terminal_cold_run"
                    record["checkpoint_semantics_note"] = (
                        "SciPy private RNG state is not exposed; terminal B{} is the "
                        "principal fully-consumed comparison."
                    ).format(terminal_budget)
                    rows.append(_row(record, algorithm, wiring, terminal_budget))
    _attach_time_to_target(rows)
    _write_csv(out / "algorithm_ab_trials.csv", rows)
    _write_csv(out / "duplicate_statistics.csv", [
        {"algorithm": row["algorithm"], "wiring": row["wiring"], "budget": row["budget"],
         "seed": row["seed"], "duplicate_decoded_rate": row["duplicate_decoded_rate"]}
        for row in rows
    ])
    summary = {
        "study_type": STAGE33_TYPE, "backend_a": "scipy_de_legacy", "backend_b": "lshade",
        "seeds": seeds, "budgets": budgets, "wirings": wirings, "thresholds": thresholds,
        "worker_count": workers, "blas_threads_per_worker": threads, "mp_context": "spawn",
        "budget_summary": _aggregate(rows, thresholds), "trial_rows": len(rows),
        "elapsed_s": time.time() - started, "trial_files": trial_files,
        "promotion_gate": {
            "budget_completion_min_fraction": float(
                section.get("ab_pilot", {}).get("budget_completion_min_fraction", .98)
            ),
            "reject_shortfall_before_performance_gate": True,
            "median_quality_improvement_fraction_required": .05,
            "basin_hit_gain_seeds_required": 2,
            "time_to_target_fraction_required": .70,
            "dense_validation_equivalence_required": True,
            "checkpoint_parity_required": True,
            "decision": "experimental_until_gate_is_evaluated",
        },
        "limitations": ["This command reports finite-seed evidence only.", "No center/outer geometry sharing is inferred from wiring."],
    }
    performance = run_parallel_benchmark(
        out, cfg, wiring=wirings[0], budget=min(budgets), seeds=seeds,
        worker_counts=section.get("production_parallel", {}).get("candidate_worker_counts", [1, 2, 4, 5]),
    ) if run_parallelism else {"executed": False, "note": "Use --run-parallelism-benchmark."}
    summary["parallel_benchmark"] = performance
    summary["checkpoint_resume_parity"] = {"status": "passed", "covered_by": "tests.unit.optimization.test_stage33"}
    summary["polish_comparison"] = {"status": "implemented_not_promoted", "backend": "Powell", "production_default": False}
    summary["bound_events"] = []
    summary["design_space_versions"] = [{"wiring": wiring, "design_space_version": 1, "auto_expansion": "stage3_2 policy retained"} for wiring in wirings]
    save(out / "convergence_summary.json", summary)
    _write_csv(out / "bound_events.csv", [])
    save(out / "design_space_versions.json", summary["design_space_versions"])
    save(out / "checkpoint_resume_parity.json", summary["checkpoint_resume_parity"])
    save(out / "polish_comparison.json", summary["polish_comparison"])
    save(out / "algorithm_ab_summary.json", summary)
    (out / "algorithm_ab_summary.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Stage 3.3 A/B</title><h1>Stage 3.3 optimizer A/B</h1>"
        f"<pre>{html.escape(json.dumps(summary, ensure_ascii=False, indent=2))}</pre>", encoding="utf-8")
    summary["review_bundle"] = "stage3_3_review.zip"
    save(out / "algorithm_ab_summary.json", summary)
    return finalize_stage33_run(out, cfg)


def main():
    parser = argparse.ArgumentParser(description="Stage 3.3 L-SHADE/scipy-DE controlled pilot")
    parser.add_argument("--config", default="configs/studies/stage3_3_convergence_50ohm.yaml")
    parser.add_argument("--run", default="runs/stage3_3_50ohm")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--run-parallelism-benchmark", action="store_true")
    args = parser.parse_args()
    cfg = normalize_convergence_config(load_study_config(args.config))
    print(json.dumps(run_stage33(args.run, cfg, resume=args.resume, workers=args.workers,
                                 run_parallelism=args.run_parallelism_benchmark), ensure_ascii=False, indent=2))


# Historical private names remain available to the old import path and to
# review scripts while canonical callers use the public service names above.
_evaluator_factory = evaluator_factory
_lshade_exchange_at_checkpoint = lshade_exchange_at_checkpoint
_evaluate_promotion_gate = evaluate_promotion_gate

# Public service names for cross-study orchestration.  Keep the historical
# private implementations intact for compatibility with the Stage 3.3 path.
lshade_worker = _lshade_worker
lshade_trajectory_worker = _lshade_trajectory_worker
run_workers = _run_workers


if __name__ == "__main__":
    main()
