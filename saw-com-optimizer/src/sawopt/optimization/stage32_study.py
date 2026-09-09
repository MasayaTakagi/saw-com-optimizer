"""Stage 3.2 continuation benchmark for the 50-ohm DMS optimizer.

This module deliberately sits beside the Stage 3.1 cold-seed certificate.  It
keeps the verified COM/network implementation and adds the stateful
coordination needed to distinguish design-space convergence from frequency
grid convergence.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import subprocess
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

import numpy as np
from scipy.optimize import differential_evolution

from ..core.metrics import geometry, search_grid, validation_grid
from ..core.models import BOUNDS, FilterDesign, NAMES, decode
from .convergence_study import (
    _cold_seeds,
    _load_config,
    _primary,
    _status,
    _thresholds,
    parity_check,
)
from .optimizer_utils import critical_frequencies, new_frequency_points
from .study import dense, evaluate_design, initialize, rank, save


STAGE32_TYPE = "stage3_2_dms_convergence"


def _settings(cfg):
    section = cfg.get("optimizer_validation", {})
    budgets = [int(x) for x in section.get("budgets", [500, 1000, 2000, 4000])]
    optional = section.get("optional_max_budget", 8000)
    optional = None if optional is None else int(optional)
    if not budgets or any(value <= 0 for value in budgets):
        raise ValueError("optimizer_validation.budgets must be positive")
    return section, budgets, optional


def _bound_state(cfg):
    section = cfg.get("optimizer_validation", {}).get("bounds", {})
    result = {}
    for index, name in enumerate(NAMES):
        default = [float(x) for x in BOUNDS[index]]
        supplied = section.get(name, {})
        initial = [float(x) for x in supplied.get("initial", default)]
        hard = [float(x) for x in supplied.get("hard", initial)]
        if len(initial) != 2 or len(hard) != 2 or initial[0] > initial[1] or hard[0] > hard[1]:
            raise ValueError(f"Invalid bounds for {name}")
        if initial[0] < hard[0] or initial[1] > hard[1]:
            raise ValueError(f"Initial bounds for {name} exceed hard bounds")
        result[name] = {
            "initial": initial,
            "active": list(initial),
            "hard": hard,
            "expandable": bool(supplied.get("expandable", False)),
            "lower_steps": [float(x) for x in supplied.get("lower_steps", [])],
            "upper_steps": [float(x) for x in supplied.get("upper_steps", [])],
        }
    return result


def active_bounds(state):
    return [tuple(values["active"]) for values in (state[name] for name in NAMES)]


def _copy_bounds(state):
    return copy.deepcopy(state)


def _canonical_design(x, bounds):
    clipped = np.asarray(x, dtype=float).copy()
    low = np.asarray([item[0] for item in bounds], dtype=float)
    high = np.asarray([item[1] for item in bounds], dtype=float)
    d = decode(np.clip(clipped, low, high))
    vector = np.asarray([asdict(d)[key] for key in NAMES], dtype=float)
    return d, vector, tuple(float(value) for value in vector)


def _record_primary(record):
    return _primary(record)


def _valid_geometry(d, cfg):
    return max(geometry(d, cfg["constraints"])[1]) <= 0


def _build_population(cfg, rng, center, bounds, *, population=None):
    population = int(population or cfg.get("optimizer", {}).get("population", 14))
    if population < 5:
        raise ValueError("Optimizer population must be at least five")
    result = []
    attempts = 0
    center = np.asarray(center, dtype=float)
    low = np.asarray([item[0] for item in bounds], dtype=float)
    high = np.asarray([item[1] for item in bounds], dtype=float)
    while len(result) < population:
        attempts += 1
        if attempts > 100000:
            raise ValueError("Could not build a manufacturable Stage 3.2 population")
        if not result:
            vector = np.clip(center, low, high)
        elif len(result) < population // 2:
            vector = np.clip(center + rng.normal(0, .08, len(NAMES)) * (high - low), low, high)
        else:
            vector = rng.uniform(low, high)
        d, canonical, _key = _canonical_design(vector, bounds)
        if _valid_geometry(d, cfg):
            result.append(canonical)
    return np.asarray(result, dtype=float)


def _inject_new_region(population, old_bounds, new_bounds, rng, cfg, fraction=.20):
    """Keep the incumbent population and replace only a small injected slice."""
    if population is None or len(population) == 0:
        return population
    count = max(1, int(np.ceil(len(population) * float(fraction))))
    output = np.asarray(population, dtype=float).copy()
    changed = [
        index for index, name in enumerate(NAMES)
        if tuple(old_bounds[index]) != tuple(new_bounds[index])
    ]
    if not changed:
        return output
    low = np.asarray([item[0] for item in new_bounds], dtype=float)
    high = np.asarray([item[1] for item in new_bounds], dtype=float)
    old_low = np.asarray([item[0] for item in old_bounds], dtype=float)
    old_high = np.asarray([item[1] for item in old_bounds], dtype=float)
    for row in range(count):
        for _attempt in range(1000):
            vector = rng.uniform(low, high)
            # Prefer the newly opened slices instead of merely redrawing the
            # old region.  For future upper expansion this remains symmetric.
            for index in changed:
                if low[index] < old_low[index]:
                    vector[index] = rng.uniform(low[index], old_low[index])
                elif high[index] > old_high[index]:
                    vector[index] = rng.uniform(old_high[index], high[index])
            d, canonical, _key = _canonical_design(vector, new_bounds)
            if _valid_geometry(d, cfg):
                output[-1 - row] = canonical
                break
    return output


def _boundary_hit(design, name, values, *, tolerance=0.0):
    value = float(design[name])
    low, high = values["active"]
    span = max(high - low, 1.0)
    tol = max(float(tolerance), 0.01 * span if name not in NAMES[1:4] else 0.5)
    return ("lower" if abs(value - low) <= tol else
            "upper" if abs(value - high) <= tol else None)


def detect_boundary_pressure(records, state, cfg):
    """Aggregate multi-seed boundary pressure for one global checkpoint.

    A single seed cannot activate pressure.  The returned rows are designed
    for both the coordinator and synthetic unit tests.
    """
    section = cfg.get("optimizer_validation", {}).get("boundary_detection", {})
    if not section.get("enabled", True):
        return {"enabled": False, "pressures": []}
    records = list(records)
    if len(records) < 2:
        return {"enabled": True, "pressures": []}
    minimum_fraction = float(section.get("min_seed_fraction_at_boundary", .80))
    elite_fraction = float(section.get("elite_boundary_fraction", .50))
    elite_count = max(1, int(np.ceil(len(records) * elite_fraction)))
    ordered = sorted(records, key=rank)
    pressures = []
    for name, values in state.items():
        if not values.get("expandable", False):
            continue
        directions = []
        for direction in ("lower", "upper"):
            hits = [
                record for record in records
                if _boundary_hit(record["design"], name, values) == direction
            ]
            elite_hits = [
                record for record in ordered[:elite_count]
                if _boundary_hit(record["design"], name, values) == direction
            ]
            seed_fraction = len(hits) / max(len(records), 1)
            concentration = len(elite_hits) / max(elite_count, 1)
            if seed_fraction >= minimum_fraction and concentration >= elite_fraction:
                directions.append({
                    "variable": name,
                    "direction": direction,
                    "seed_count": len(hits),
                    "seed_fraction": float(seed_fraction),
                    "elite_count": len(elite_hits),
                    "elite_fraction": float(concentration),
                    "active_bound": float(values["active"][0 if direction == "lower" else 1]),
                    "hard_bound": float(values["hard"][0 if direction == "lower" else 1]),
                })
        pressures.extend(directions)
    return {"enabled": True, "seed_count": len(records), "pressures": pressures}


def _next_expansion(state, pressure):
    name = pressure["variable"]
    values = state[name]
    side = 0 if pressure["direction"] == "lower" else 1
    active = float(values["active"][side])
    hard = float(values["hard"][side])
    candidates = values["lower_steps" if side == 0 else "upper_steps"]
    if side == 0:
        candidates = [value for value in candidates if hard <= value < active]
        return max(candidates) if candidates else None
    candidates = [value for value in candidates if active < value <= hard]
    return min(candidates) if candidates else None


def boundary_probe(records, cfg, z0, wiring, state, pressure):
    """Probe the next bound step before changing the active design space."""
    target = _next_expansion(state, pressure)
    if target is None:
        return {
            "variable": pressure["variable"], "direction": pressure["direction"],
            "target": None, "positive": False, "hard_bound_reached": True,
            "evaluations": 0, "best_improvement": 0.0,
        }
    variable = pressure["variable"]
    f = search_grid(cfg["spec"], cfg)
    improvements = []
    tested = []
    for record in records:
        design = dict(record["design"])
        design[variable] = int(target) if variable in NAMES[1:4] else float(target)
        candidate = FilterDesign(**design)
        if not _valid_geometry(candidate, cfg):
            continue
        probe_record, _net, _sim = evaluate_design(candidate, cfg, f, z0, z0, wiring=wiring)
        tested.append({"seed": int(record["seed"]), "design": design,
                       "rank": list(rank(probe_record))})
        improvements.append(float(_record_primary(record) - _record_primary(probe_record)))
    best = max(improvements, default=0.0)
    positive = bool(best > float(cfg.get("optimizer_validation", {}).get(
        "boundary_detection", {}).get("probe_improvement_threshold", .02)))
    return {
        "variable": variable, "direction": pressure["direction"],
        "target": target, "positive": positive, "hard_bound_reached": False,
        "evaluations": len(tested), "best_improvement": best,
        "tested": tested,
    }


def _active_state_version(state):
    return {name: list(values["active"]) for name, values in state.items()}


def _stage32_row(record, budget):
    row = {
        "wiring": record["wiring"], "budget": int(budget),
        "budget_unique_designs": int(budget), "seed": int(record["seed"]),
        "feasible": bool(record["feasible"]),
        "max_violation": float(record["max_violation"]),
        "sum_violation": float(sum(record["violations"].values())),
        "worst_il_db": float(record["metrics"]["worst_il_db"]),
        "ripple_db": float(record["metrics"]["ripple_db"]),
        "input_vswr": float(record["metrics"]["input_vswr"]),
        "output_vswr": float(record["metrics"]["output_vswr"]),
        "objective_calls": int(record.get("objective_calls", 0)),
        "unique_decoded_evaluations": int(record.get("actual_unique_design_evaluations", 0)),
        "requested_unique_design_budget": int(record.get("requested_unique_design_budget", budget)),
        "solved_frequency_points": int(record.get("solved_frequency_points", 0)),
        "validation_frequency_count": int(record.get("validation_frequency_count", 0)),
        "validation_gap_primary": float(record.get("validation_gap_primary", 0.0)),
        "micro_polish_improvement": float(record.get("best_candidate_polish_improvement", 0.0)),
        "median_candidate_polish_improvement": float(record.get("median_candidate_polish_improvement", 0.0)),
        "last_significant_improvement_unique_eval": record.get("last_significant_improvement_unique_eval"),
        "fraction_of_budget_at_last_significant_improvement": record.get(
            "fraction_of_budget_at_last_significant_improvement"),
        "design_space_version": int(record.get("design_space_version", 1)),
        "grid_converged": bool(record.get("grid_converged", False)),
        "optimizer_converged": bool(record.get("optimizer_converged", False)),
    }
    return row


def _continuation_status(rows, thresholds, current_version):
    same_version = [row for row in rows if int(row.get("design_space_version", 1)) == int(current_version)]
    status, evidence = _status(same_version, thresholds)
    evidence["design_space_version"] = int(current_version)
    return status, evidence


def _polish_active(record, cfg, z0, wiring, bounds, *, promote):
    settings = cfg.get("micro_polish", {})
    if not settings.get("enabled", True):
        return record, {"enabled": False, "promoted": False, "evaluations": 0,
                        "improvement": 0.0, "before_rank": list(rank(record)),
                        "after_rank": list(rank(record))}
    current = np.asarray([record["design"][name] for name in NAMES], dtype=float)
    best = dict(record)
    baseline = _record_primary(record)
    evaluations = 0
    history = []
    integer_indices = {1, 2, 3}
    fractions = [float(x) for x in settings.get(
        "continuous_steps_fraction_of_bound_span", [.01, .005]) if float(x) > 0]
    if not fractions:
        fractions = [.005]
    minimum = float(settings.get("minimum_step_fraction", min(fractions)))
    shrink = float(settings.get("shrink_factor", .5))
    step = max(fractions)
    for polish_pass in range(max(0, int(settings.get("max_passes", 4)))):
        fraction = max(minimum, step)
        history.append(float(fraction))
        improved = False
        for index, (lo, hi) in enumerate(bounds):
            if index in integer_indices:
                steps = list(settings.get("integer_steps", [-1, 1]))
                if polish_pass >= 1:
                    steps += list(settings.get("optional_second_integer_steps", []))
            else:
                steps = [-(hi - lo) * fraction, (hi - lo) * fraction]
            for delta in steps:
                trial = current.copy()
                trial[index] = np.clip(trial[index] + float(delta), lo, hi)
                d, _canonical, _key = _canonical_design(trial, bounds)
                if not _valid_geometry(d, cfg):
                    continue
                candidate, _net, _sim = evaluate_design(d, cfg, np.asarray(record["validation_frequencies_hz"], dtype=float), z0, z0, wiring=wiring)
                evaluations += 1
                candidate["design"] = asdict(d)
                if rank(candidate) < rank(best):
                    best = dict(candidate)
                    current = np.asarray([getattr(d, name) for name in NAMES], dtype=float)
                    improved = True
        if not improved:
            if fraction <= minimum:
                break
            step = max(minimum, fraction * shrink)
    promoted = bool(promote and rank(best) < rank(record))
    if not promoted:
        best = record
    return best, {
        "enabled": True, "promoted": promoted, "evaluations": evaluations,
        "improvement": float(baseline - _record_primary(best)),
        "before_rank": list(rank(record)), "after_rank": list(rank(best)),
        "step_fraction_history": history,
    }


class ContinuationTrajectory:
    """One cold-seed trajectory with cumulative unique-design accounting."""

    def __init__(self, out, cfg, z0, seed, wiring, state, *, run_label=None):
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.cfg = cfg
        self.z0 = float(z0)
        self.seed = int(seed)
        self.wiring = str(wiring)
        self.state = _copy_bounds(state)
        self.run_label = run_label or f"{wiring}__seed{seed}"
        self.rng = np.random.default_rng(self.seed)
        self.search_f = np.unique(search_grid(cfg["spec"], cfg))
        self.population = None
        self.seen = set()
        self.cache = {}
        self.best = None
        self.segment_index = 0
        self.objective_calls = 0
        self.cache_hits = 0
        self.geometry_rejections = 0
        self.valid_physics_evaluations = 0
        self.solved_frequency_points = 0
        self.grid_extension_re_evaluations = 0
        self.grid_extension_events = []
        self.best_trace = []
        self.last_significant = None
        self.design_space_version = 1
        self.checkpoints = []
        self.stop_reason = None

    @property
    def actual_unique_design_evaluations(self):
        return len(self.seen)

    def _evaluate(self, vector, *, count_objective=True):
        bounds = active_bounds(self.state)
        d, canonical, key = _canonical_design(vector, bounds)
        if count_objective:
            self.objective_calls += 1
        cache_entry = self.cache.get(key)
        if cache_entry is not None and np.array_equal(cache_entry["frequencies"], self.search_f):
            self.cache_hits += 1
            return cache_entry["record"]
        is_new = key not in self.seen
        if is_new:
            self.seen.add(key)
        else:
            self.grid_extension_re_evaluations += 1
        self.solved_frequency_points += len(self.search_f)
        if not _valid_geometry(d, self.cfg):
            self.geometry_rejections += 1
            record = {
                "design": asdict(d), "objective": 1e10,
                "search_scalar_objective": 1e10,
                "failure": "manufacturing constraint",
                "feasible": False, "max_violation": 1e10,
                "violations": {"geometry": 1e10},
                "metrics": {"worst_il_db": 1e10, "ripple_db": 1e10,
                             "input_vswr": 1e10, "output_vswr": 1e10},
                "diagnostics": {},
            }
        else:
            record, _net, _sim = evaluate_design(d, self.cfg, self.search_f,
                                                 self.z0, self.z0, wiring=self.wiring)
            record = dict(record)
            record["design"] = asdict(d)
            self.valid_physics_evaluations += 1
        record["evaluation"] = int(self.actual_unique_design_evaluations)
        record["design_space_version"] = int(self.design_space_version)
        self.cache[key] = {"frequencies": self.search_f.copy(), "record": record}
        if record.get("metrics") and (self.best is None or rank(record) < rank(self.best)):
            previous = self.best
            self.best = record
            if previous is None or (
                _record_primary(previous) - _record_primary(record) >=
                max(.02, .01 * max(abs(_record_primary(previous)), 1e-12))
            ) or bool(previous.get("feasible")) != bool(record.get("feasible")):
                self.last_significant = self.actual_unique_design_evaluations
                self.best_trace.append({
                    "unique_evaluation": self.actual_unique_design_evaluations,
                    "design": dict(record["design"]),
                    "rank_tuple": list(rank(record)),
                    "primary_metric": _record_primary(record),
                })
        return record

    def _objective(self, vector, target):
        if self.actual_unique_design_evaluations >= int(target):
            return 1e15
        return float(self._evaluate(vector)["objective"])

    def _run_de(self, target):
        bounds = active_bounds(self.state)
        if self.population is None:
            center = np.asarray([getattr(FilterDesign(), name) for name in NAMES], dtype=float)
            self.population = _build_population(self.cfg, self.rng, center, bounds)
        remaining = max(1, int(target) - self.actual_unique_design_evaluations)
        population_size = len(self.population)
        required_iterations = int(np.ceil(remaining / max(population_size, 1))) + 2
        configured = int(self.cfg.get("optimizer", {}).get("maxiter", 20))
        ceiling = int(self.cfg.get("optimizer", {}).get("maxiter_ceiling", max(configured, required_iterations)))
        maxiter = min(max(1, ceiling), max(configured, required_iterations))
        before = self.actual_unique_design_evaluations
        result = differential_evolution(
            lambda vector: self._objective(vector, target), bounds,
            init=np.asarray(self.population, dtype=float),
            seed=self.seed + self.segment_index,
            maxiter=maxiter, polish=False, tol=0, atol=0, workers=1,
            updating="immediate",
        )
        self.segment_index += 1
        if hasattr(result, "population"):
            self.population = np.asarray(result.population, dtype=float)
        if self.actual_unique_design_evaluations == before:
            self.stop_reason = "no_new_unique_designs"
            return False
        return True

    def _update_grid(self):
        if self.best is None:
            return False, []
        design = FilterDesign(**self.best["design"])
        dense_f, (_dense_record, net, _sim) = dense(
            design, self.cfg, self.z0, self.z0, wiring=self.wiring,
            base_grid=validation_grid(self.cfg["spec"], self.cfg),
            passes=int(self.cfg.get("validation", {}).get("dense_refinement_passes", 2)),
            validation=True,
        )
        critical = critical_frequencies(
            dense_f, net, self.cfg["spec"],
            slope_threshold_db=float(self.cfg.get("dense_slope_threshold_db", .5)),
            max_points=int(self.cfg.get("validation", {}).get("adaptive_max_points_per_round", 64)),
        )
        tolerance = float(self.cfg.get("validation", {}).get("adaptive_frequency_tolerance_hz", 1e3))
        added = new_frequency_points(self.search_f, critical, tolerance)
        if len(added):
            old_count = len(self.search_f)
            self.search_f = np.unique(np.r_[self.search_f, added])
            self.grid_extension_events.append({
                "from_frequency_count": old_count,
                "to_frequency_count": len(self.search_f),
                "added_frequency_count": len(added),
                "added_frequencies_hz": added.tolist(),
                "unique_design_count_change": 0,
            })
            # Re-evaluate the active population on the expanded grid.  These
            # are existing geometries, so only solved frequency points grow.
            if self.population is not None:
                for vector in self.population:
                    self._evaluate(vector, count_objective=False)
            return False, added.tolist()
        return True, []

    def advance(self, target, *, design_space_version=None):
        target = int(target)
        if target < self.actual_unique_design_evaluations:
            raise ValueError("Continuation target cannot move backwards")
        if design_space_version is not None:
            self.design_space_version = int(design_space_version)
        while self.actual_unique_design_evaluations < target:
            if not self._run_de(target):
                break
        if self.best is None:
            raise RuntimeError(f"No valid Stage 3.2 candidate for seed {self.seed}")
        grid_converged, added = self._update_grid()
        validation_f = validation_grid(self.cfg["spec"], self.cfg)
        validation_record, _net, _sim = evaluate_design(
            FilterDesign(**self.best["design"]), self.cfg, validation_f,
            self.z0, self.z0, wiring=self.wiring)
        validation_record["design"] = dict(self.best["design"])
        validation_record["validation_frequencies_hz"] = validation_f.tolist()
        if self.best.get("feasible") and validation_record.get("feasible"):
            gap = _record_primary(validation_record) - _record_primary(self.best)
        else:
            gap = float(validation_record.get("max_violation", 0.0) - self.best.get("max_violation", 0.0))
        best_polished, best_polish = _polish_active(
            dict(validation_record), self.cfg, self.z0, self.wiring,
            active_bounds(self.state), promote=False)
        del best_polished
        median_polish = {"enabled": True, "promoted": False, "improvement": 0.0, "evaluations": 0}
        record = dict(self.best)
        record.update({
            "wiring": self.wiring, "seed": self.seed,
            "requested_unique_design_budget": target,
            "actual_unique_design_evaluations": self.actual_unique_design_evaluations,
            "unique_decoded_evaluations": self.actual_unique_design_evaluations,
            "objective_calls": self.objective_calls,
            "cache_hits": self.cache_hits,
            "geometry_rejections": self.geometry_rejections,
            "valid_physics_evaluations": self.valid_physics_evaluations,
            "solved_frequency_points": self.solved_frequency_points,
            "grid_extension_re_evaluations": self.grid_extension_re_evaluations,
            "search_frequency_count": len(self.search_f),
            "validation_frequency_count": len(validation_f),
            "validation_frequencies_hz": validation_f.tolist(),
            "validation_gap_primary": float(gap),
            "grid_converged": bool(grid_converged),
            "optimizer_converged": False,
            "design_space_version": int(self.design_space_version),
            "best_candidate_polish_improvement": float(best_polish.get("improvement", 0.0)),
            "median_candidate_polish_improvement": float(median_polish.get("improvement", 0.0)),
            "best_candidate_polish": best_polish,
            "median_candidate_polish": median_polish,
            "last_significant_improvement_unique_eval": self.last_significant,
            "fraction_of_budget_at_last_significant_improvement": (
                None if self.last_significant is None else self.last_significant / max(float(target), 1.0)),
            "best_so_far_trace": list(self.best_trace),
            "grid_extension_events": list(self.grid_extension_events),
            "active_bounds": _active_state_version(self.state),
            "stop_reason": self.stop_reason,
            "validation_record": validation_record,
        })
        self.checkpoints.append(record)
        return record

    def expand(self, old_state, new_state, version, fraction):
        old_bounds = active_bounds(old_state)
        new_bounds = active_bounds(new_state)
        self.state = _copy_bounds(new_state)
        self.design_space_version = int(version)
        self.population = _inject_new_region(
            self.population, old_bounds, new_bounds, self.rng, self.cfg, fraction=fraction)
        self.cache = {}
        self.grid_extension_events.append({
            "design_space_version": int(version),
            "event": "bound_expansion_population_injection",
            "injection_fraction": float(fraction),
        })

    def finalise(self, record):
        validation_f = np.asarray(record["validation_frequencies_hz"], dtype=float)
        polished, diagnostic = _polish_active(
            dict(record), self.cfg, self.z0, self.wiring,
            active_bounds(self.state), promote=True)
        if diagnostic.get("promoted"):
            original = dict(record)
            promoted = dict(polished)
            # The polish evaluator returns a fresh metric record. Preserve the
            # continuation/checkpoint metadata attached to the trajectory.
            for key, value in original.items():
                promoted.setdefault(key, value)
            record = promoted
        record["final_polish"] = diagnostic
        record["best_candidate_polish_improvement"] = float(diagnostic.get("improvement", 0.0))
        record["validated_rank_tuple"] = list(rank(record))
        record["optimizer_converged"] = False
        record["validation_frequencies_hz"] = validation_f.tolist()
        return record

    def save_checkpoint(self, record, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        save(path, {
            "wiring": self.wiring, "seed": self.seed,
            "budget": record["requested_unique_design_budget"],
            "actual_unique_design_evaluations": self.actual_unique_design_evaluations,
            "design_space_version": self.design_space_version,
            "grid_converged": record["grid_converged"],
            "active_bounds": _active_state_version(self.state),
            "population": np.asarray(self.population).tolist() if self.population is not None else [],
            "incumbent": record["design"],
            "best_so_far_trace": self.best_trace,
            "grid_extension_events": self.grid_extension_events,
        })


def _single_blas_environment(threads=1):
    names = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
    previous = {name: os.environ.get(name) for name in names}
    for name in names:
        os.environ[name] = str(int(threads))
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


_single_blas_environment = contextmanager(_single_blas_environment)


def _parallel_smoke_task(payload):
    out, cfg, wiring, seed, budget = payload
    with _single_blas_environment(int(cfg.get("optimizer_validation", {}).get(
            "parallel", {}).get("blas_threads_per_worker", 1))):
        trajectory = ContinuationTrajectory(out, cfg, 50.0, seed, wiring, _bound_state(cfg))
        return trajectory.advance(budget)


def run_parallelism_benchmark(out, cfg):
    section = cfg.get("optimizer_validation", {}).get("parallel", {})
    workers = [int(x) for x in section.get("benchmark_workers", [1, 2, 4, 5])]
    seeds = _cold_seeds(cfg)
    wirings = list(cfg.get("wirings", ["outer_ports", "center_outer_same"]))
    budget = int(section.get("benchmark_budget", 100))
    tasks = [(wiring, seed) for wiring in wirings for seed in seeds]
    results = {}
    baseline = None
    for worker_count in workers:
        target_root = Path(out) / "parallelism" / f"workers{worker_count}"
        target_root.mkdir(parents=True, exist_ok=True)
        payloads = [
            (str(target_root / f"{wiring}__seed{seed}"), cfg, wiring, seed, budget)
            for wiring, seed in tasks
        ]
        started = time.time()
        with _single_blas_environment(int(section.get("blas_threads_per_worker", 1))):
            if worker_count == 1:
                trial_results = [_parallel_smoke_task(payload) for payload in payloads]
            else:
                with ProcessPoolExecutor(max_workers=worker_count) as pool:
                    trial_results = list(pool.map(_parallel_smoke_task, payloads))
        elapsed = time.time() - started
        ranks = [tuple(result.get("validated_rank_tuple", rank(result))) for result in trial_results]
        if baseline is None:
            baseline = ranks
        results[str(worker_count)] = {
            "workers": worker_count, "budget": budget,
            "trial_count": len(trial_results), "wall_time_s": elapsed,
            "numerical_rank_parity_with_workers_1": ranks == baseline,
            "blas_threads_per_worker": int(section.get("blas_threads_per_worker", 1)),
        }
    first = results[str(workers[0])]["wall_time_s"]
    for values in results.values():
        values["speedup_vs_first"] = first / max(values["wall_time_s"], np.finfo(float).tiny)
        values["parallel_efficiency_vs_first"] = values["speedup_vs_first"] / max(values["workers"], 1)
    return {
        "executed": True, "workers_requested": workers, "workers": results,
        "seed_count": len(seeds), "wirings": wirings, "budget": budget,
        "blas_threads_per_worker": int(section.get("blas_threads_per_worker", 1)),
        "environment_policy": {name: "1" for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
    }


def _write_csv(path, rows):
    rows = list(rows)
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    fieldnames = sorted(set().union(*(row.keys() for row in rows)))
    with Path(path).open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list)) else value
                for key, value in row.items()
            })


def run_stage32(out, cfg, *, run_parallelism=False):
    """Run the continuation experiment and write review-ready artifacts."""
    out = Path(out)
    cfg = copy.deepcopy(cfg)
    cfg["study_type"] = STAGE32_TYPE
    initialize(out, cfg)
    section, budgets, optional_budget = _settings(cfg)
    z0 = float(cfg.get("convergence", {}).get("impedance_ohm", 50.0))
    seeds = _cold_seeds(cfg)
    wirings = list(cfg.get("wirings", ["outer_ports", "center_outer_same"]))
    thresholds = _thresholds(cfg)
    max_workers = int(section.get("parallel", {}).get("production_workers", 1))
    max_workers = max(1, min(max_workers, len(seeds)))
    auto_escalate = bool(section.get("auto_escalate", True))
    boundary_section = section.get("boundary_detection", {})
    injection_fraction = float(boundary_section.get("exploration_injection_fraction", .20))
    required_persistence = int(boundary_section.get("required_persistent_checkpoints", 2))
    all_rows = []
    trial_files = []
    boundary_events = []
    design_versions = []
    checkpoint_summary = []
    statuses = {}
    budget_run = {}
    best_candidates = {}
    budget_summaries = {}
    paired_deltas = []
    started = time.time()

    for wiring in wirings:
        state = _bound_state(cfg)
        trajectories = {
            seed: ContinuationTrajectory(out / "trajectory", cfg, z0, seed, wiring, state)
            for seed in seeds
        }
        rows_for_wiring = []
        pressure_history = {}
        version = 1
        design_versions.append({
            "wiring": wiring, "design_space_version": version,
            "active_bounds": _active_state_version(state), "reason": "initial",
        })
        budgets_for_wiring = []
        candidate_budgets = list(budgets)
        if optional_budget is not None and optional_budget > max(budgets):
            candidate_budgets.append(optional_budget)
        for budget in candidate_budgets:
            if budget == optional_budget and (not auto_escalate or (statuses.get(wiring, {}).get("status") == "converged")):
                break
            def advance(seed):
                return seed, trajectories[seed].advance(budget, design_space_version=version)
            if max_workers > 1:
                with _single_blas_environment(int(section.get("parallel", {}).get("blas_threads_per_worker", 1))):
                    with ThreadPoolExecutor(max_workers=max_workers) as pool:
                        checkpoint_records = dict(pool.map(advance, seeds))
            else:
                checkpoint_records = dict(advance(seed) for seed in seeds)
            current_records = list(checkpoint_records.values())
            current_rows = [_stage32_row(record, budget) for record in current_records]
            for row in current_rows:
                row["design_space_version"] = version
            all_rows.extend(current_rows)
            rows_for_wiring.extend(current_rows)
            budgets_for_wiring.append(int(budget))
            trial_dir = out / "trials"
            trial_dir.mkdir(parents=True, exist_ok=True)
            checkpoint_dir = out / "checkpoints" / wiring
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            for seed, record in checkpoint_records.items():
                record["design_space_version"] = version
                trial_path = trial_dir / f"{wiring}__B{budget}__seed{seed}.json"
                save(trial_path, record)
                trial_files.append(trial_path.relative_to(out).as_posix())
                checkpoint_path = checkpoint_dir / f"seed{seed}__B{budget}__v{version}.json"
                trajectories[seed].save_checkpoint(record, checkpoint_path)
                checkpoint_summary.append({
                    "wiring": wiring, "seed": int(seed), "budget": int(budget),
                    "design_space_version": version,
                    "path": checkpoint_path.relative_to(out).as_posix(),
                    "requested_unique_design_budget": int(record["requested_unique_design_budget"]),
                    "actual_unique_design_evaluations": int(record["actual_unique_design_evaluations"]),
                })
            pressure = detect_boundary_pressure(current_records, state, cfg)
            for item in pressure.get("pressures", []):
                key = (item["variable"], item["direction"])
                pressure_history[key] = pressure_history.get(key, 0) + 1
                item["persistence_count"] = pressure_history[key]
                item["budget"] = int(budget)
                item["wiring"] = wiring
                item["design_space_version"] = version
                if pressure_history[key] >= required_persistence:
                    probe = boundary_probe(current_records, cfg, z0, wiring, state, item)
                    item["probe"] = probe
                    item["probe_positive"] = bool(probe.get("positive"))
                    if probe.get("positive"):
                        old_state = _copy_bounds(state)
                        target = _next_expansion(state, item)
                        if target is not None:
                            state[item["variable"]]["active"][0 if item["direction"] == "lower" else 1] = target
                            version += 1
                            for trajectory in trajectories.values():
                                trajectory.expand(old_state, state, version, injection_fraction)
                            event = dict(item, event="bound_expansion", new_bound=float(target), new_design_space_version=version)
                            boundary_events.append(event)
                            design_versions.append({
                                "wiring": wiring, "design_space_version": version,
                                "active_bounds": _active_state_version(state),
                                "reason": "positive_boundary_probe",
                                "trigger": event,
                            })
                            pressure_history = {}
                        else:
                            boundary_events.append(dict(item, event="hard_bound_limited"))
                    elif probe.get("hard_bound_reached"):
                        boundary_events.append(dict(item, event="hard_bound_limited"))
                    else:
                        boundary_events.append(dict(item, event="boundary_probe_no_improvement"))
            for key in list(pressure_history):
                if not any((x["variable"], x["direction"]) == key for x in pressure.get("pressures", [])):
                    pressure_history[key] = 0
            status, evidence = _continuation_status(rows_for_wiring, thresholds, version)
            unresolved_hard = any(
                event.get("event") == "hard_bound_limited" and
                int(event.get("design_space_version", 1)) == version
                for event in boundary_events if event.get("wiring") == wiring
            )
            if unresolved_hard:
                status = "hard_bound_limited"
            statuses[wiring] = {"status": status, "evidence": evidence,
                                "trial_count": len(rows_for_wiring),
                                "design_space_version": version}
            if status == "converged" and not unresolved_hard:
                break
            if budget == max(budgets) and optional_budget is not None and auto_escalate:
                continue
        budget_run[wiring] = sorted(set(int(row["budget"]) for row in rows_for_wiring))
        best_candidates[wiring] = {}
        budget_summaries[wiring] = {}
        for completed_budget in budget_run[wiring]:
            budget_rows = [row for row in rows_for_wiring
                           if int(row["budget"]) == completed_budget]
            best_row = min(budget_rows, key=lambda row: (
                not row["feasible"], row["max_violation"],
                row["sum_violation"], row["worst_il_db"]))
            best_candidates[wiring][str(completed_budget)] = {
                "seed": int(best_row["seed"]),
                "result_file": (
                    f"trials/{wiring}__B{completed_budget}__seed{best_row['seed']}.json"
                ),
                "design_space_version": int(best_row["design_space_version"]),
                "validated_rank_tuple": list(best_row.get("validated_rank_tuple", [])),
            }
            primary = [float(_record_primary(row)) for row in budget_rows]
            budget_summaries[wiring][str(completed_budget)] = {
                "seed_count": len(budget_rows),
                "best_primary_metric": min(primary),
                "median_primary_metric": float(np.median(primary)),
                "seed_iqr_primary_metric": float(
                    np.percentile(primary, 75) - np.percentile(primary, 25)
                ),
                "feasible_seed_count": int(sum(bool(row["feasible"])
                                                for row in budget_rows)),
                "median_validation_gap_primary": float(np.median([
                    abs(float(row["validation_gap_primary"])) for row in budget_rows
                ])),
                "median_best_candidate_polish_improvement": float(np.median([
                    float(row["micro_polish_improvement"]) for row in budget_rows
                ])),
                "median_candidate_polish_improvement": float(np.median([
                    float(row["median_candidate_polish_improvement"])
                    for row in budget_rows
                ])),
                "total_unique_design_evaluations": int(sum(
                    row["unique_decoded_evaluations"] for row in budget_rows
                )),
                "budget_accounting_error": int(sum(
                    row["unique_decoded_evaluations"] - completed_budget
                    for row in budget_rows
                )),
            }
        for item in statuses[wiring]["evidence"].get("paired_budget_deltas", []):
            paired_deltas.append(dict(
                item, wiring=wiring,
                design_space_version=statuses[wiring]["design_space_version"],
            ))
        # Final common-grid polish is represented in the final checkpoint file.
        final_budget = max(budget_run[wiring])
        for seed in seeds:
            matching = [row for row in rows_for_wiring if row["seed"] == seed and row["budget"] == final_budget]
            if matching:
                path = out / "trials" / f"{wiring}__B{final_budget}__seed{seed}.json"
                data = json.loads(path.read_text(encoding="utf-8"))
                data = trajectories[seed].finalise(data)
                save(path, data)

    parallel = run_parallelism_benchmark(out, cfg) if run_parallelism else {
        "executed": False,
        "workers_requested": cfg.get("optimizer_validation", {}).get("parallel", {}).get("benchmark_workers", [1, 2, 4, 5]),
        "note": "Run with --run-parallelism-benchmark to execute the fixed-seed worker benchmark.",
    }
    _write_csv(out / "boundary_events.csv", boundary_events)
    save(out / "design_space_versions.json", design_versions)
    save(out / "checkpoints" / "checkpoint_summary.json", checkpoint_summary)
    _write_csv(out / "convergence_trials.csv", all_rows)
    summary = {
        "bundle_format_version": 2, "study_type": STAGE32_TYPE,
        "impedance_ohm": z0, "wirings": wirings, "cold_seeds": seeds,
        "min_cold_seeds": int(section.get("min_cold_seeds", 5)),
        "budgets": budgets, "optional_max_budget": optional_budget,
        "budgets_run_by_wiring": budget_run, "auto_escalate": auto_escalate,
        "statuses": statuses, "boundary_events": boundary_events,
        "design_space_versions": design_versions,
        "budget_summary": budget_summaries,
        "paired_budget_deltas": paired_deltas,
        "best_candidates": best_candidates,
        "parallelism_benchmark": parallel,
        "parity": parity_check(cfg, z0),
        "trial_files": trial_files, "expected_trial_count": len(trial_files),
        "checkpoint_count": len(checkpoint_summary),
        "elapsed_s": time.time() - started,
        "command": cfg.get("benchmark_command", "python -m sawopt.optimization.stage32_study --config configs/studies/stage3_2_convergence_50ohm.yaml --run runs/stage3_2_50ohm"),
        "deviations": [
            "SciPy differential_evolution is resumed with the previous population and incumbent; its private RNG state is not exposed, so each continuation segment uses a deterministic derived seed.",
            "Boundary probes use the existing search grid and are diagnostic; they do not consume trajectory unique-design budget.",
            "Parallel worker benchmark uses a small fixed budget to measure worker behavior without duplicating the production certificate.",
        ],
        "known_limitations": [
            "Hypothetical COM remains unvalidated for production design.",
            "Finite budget/seed evidence does not claim a global optimum.",
        ],
    }
    save(out / "best_candidates.json", best_candidates)
    save(out / "performance_gate.json", {
        "parallelism": parallel,
        "note": "Stage 3.2 seed-level benchmark is recorded in parallel_benchmark.json",
    })
    budget_rows = []
    for wiring, summaries in budget_summaries.items():
        for completed_budget, values in summaries.items():
            budget_rows.append(dict(wiring=wiring, budget=completed_budget, **values))
    _write_csv(out / "budget_summary.csv", budget_rows)
    _write_csv(out / "paired_budget_deltas.csv", [
        dict(item, deltas=json.dumps(item.get("deltas", [])))
        for item in paired_deltas
    ])
    save(out / "parallel_benchmark.json", parallel)
    save(out / "convergence_summary.json", summary)
    (out / "convergence_report.html").write_text(
        "<html><meta charset='utf-8'><title>Stage 3.2 DMS convergence</title>"
        "<h1>Stage 3.2 50 ohm DMS continuation</h1>"
        f"<pre>{json.dumps(summary, ensure_ascii=False, indent=2)}</pre></html>",
        encoding="utf-8",
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description="Stage 3.2 continuation benchmark")
    parser.add_argument("--config", default="configs/studies/stage3_2_convergence_50ohm.yaml")
    parser.add_argument("--run", default="runs/stage3_2_50ohm")
    parser.add_argument("--run-parallelism-benchmark", action="store_true")
    args = parser.parse_args()
    cfg = _load_config(args.config)
    print(json.dumps(run_stage32(args.run, cfg, run_parallelism=args.run_parallelism_benchmark),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
