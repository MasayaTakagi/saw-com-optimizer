"""Reusable SAW filter and dense frequency-grid evaluation."""
from __future__ import annotations

import numpy as np

from ..evaluation import evaluate_response, measure, validation_grid
from ..physics.com import SimulationResult
from ..optimization.adaptive_frequency import critical_frequencies, new_frequency_points
from ..optimization.cache import IncrementalFrequencyCache


def dense(d, cfg, rs, rl, wiring="outer_ports", counters=None, *,
         base_grid=None, passes=None, validation=False):
    """Dense-evaluate one fixed design with exact incremental frequency caching."""
    f = validation_grid(cfg["spec"], cfg) if base_grid is None else np.unique(np.asarray(base_grid, dtype=float))
    passes = int(cfg.get("validation", {}).get("dense_refinement_passes",
                       cfg.get("dense_refinement_passes", 2))) if passes is None else int(passes)
    slope = float(cfg.get("dense_slope_threshold_db", .5))
    tolerance = float(cfg.get("validation", {}).get(
        "adaptive_frequency_tolerance_hz",
        cfg.get("adaptive_frequency_tolerance_hz", 1e3),
    ))

    def point_evaluate(points):
        net, sim = evaluate_response(d, cfg, points, rs, rl, wiring=wiring)
        payload = dict(net)
        payload["y_parameters"] = sim.y_parameters
        payload["_diagnostics"] = sim.diagnostics
        return payload

    cache = IncrementalFrequencyCache(point_evaluate)

    def cached_evaluate(points):
        nonlocal solved_seen
        payload = cache.evaluate(points)
        solved_delta = cache.solved_points - solved_seen
        solved_seen = cache.solved_points
        if counters is not None:
            counters.add_solved(solved_delta, validation=validation)
            counters.add_evaluation_time(cache.last_evaluation_wall_time_s, validation=validation)
        net = {key: value for key, value in payload.items()
               if key not in ("frequencies_hz", "y_parameters", "_diagnostics")}
        evaluated_frequencies = np.asarray(payload["frequencies_hz"], dtype=float)
        sim = SimulationResult(
            frequencies_hz=evaluated_frequencies,
            y_parameters=np.asarray(payload["y_parameters"]),
            diagnostics=payload.get("_diagnostics", {}),
        )
        result = measure(evaluated_frequencies, net, d, cfg)
        result["diagnostics"] = sim.diagnostics
        return result, net, sim

    solved_seen = 0
    for _ in range(max(0, passes)):
        result, net, sim = cached_evaluate(f)
        critical = critical_frequencies(
            f, net, cfg["spec"], slope_threshold_db=slope,
            max_points=int(cfg.get("adaptive_max_points_per_round",
                                   cfg.get("validation", {}).get("adaptive_max_points_per_round", 64))),
        )
        added = new_frequency_points(f, critical, tolerance)
        if len(added) == 0:
            break
        f = np.unique(np.r_[f, added])
    return f, cached_evaluate(f)


__all__ = ["dense"]
