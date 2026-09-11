"""Frequency sampling and adaptive-grid exchange primitives."""
from __future__ import annotations

import numpy as np


def _region_indices(mhz, band):
    lo, hi = band[:2]
    return np.flatnonzero((mhz >= lo) & (mhz <= hi))


def _append_series_controls(points, f, values, indices, threshold, *, refine_extrema=False):
    if len(indices) == 0:
        return
    local = np.asarray(values)[indices]
    points.extend([f[indices[np.argmin(local)]], f[indices[np.argmax(local)]]])
    if len(indices) > 1:
        slope = np.abs(np.diff(local))
        steep = np.flatnonzero(slope > float(threshold))
        points.extend(((f[indices[steep]] + f[indices[steep + 1]]) / 2).tolist())
    if len(indices) > 2:
        delta = np.diff(local)
        extrema = np.flatnonzero(delta[:-1] * delta[1:] < 0) + 1
        points.extend(f[indices[extrema]].tolist())
        if refine_extrema:
            for peak in indices[extrema]:
                if peak > 0:
                    points.append((f[peak - 1] + f[peak]) / 2)
                if peak < len(f) - 1:
                    points.append((f[peak] + f[peak + 1]) / 2)


def critical_frequencies(frequencies_hz, net, spec, slope_threshold_db=0.5,
                         max_points=64, vswr_slope_threshold=None):
    """Return dense-grid frequencies most likely to control the specification."""
    f = np.asarray(frequencies_hz, dtype=float)
    il = np.asarray(net["il"], dtype=float)
    vswr = np.asarray(net["vswr"], dtype=float)
    if f.ndim != 1 or il.shape != f.shape or vswr.shape != (len(f), 2):
        raise ValueError("Unexpected frequency/network array shapes")
    if len(f) < 2:
        return f.copy()

    mhz = f / 1e6
    points = []
    vswr_threshold = slope_threshold_db if vswr_slope_threshold is None else vswr_slope_threshold
    p_lo, p_hi = spec["passband"]
    pmask = (mhz >= p_lo) & (mhz <= p_hi)
    pidx = np.flatnonzero(pmask)
    if len(pidx):
        points.extend([
            f[pidx[np.argmax(il[pidx])]],
            f[pidx[np.argmax(vswr[pidx, 0])]],
            f[pidx[np.argmax(vswr[pidx, 1])]],
        ])
        _append_series_controls(points, f, il, pidx, slope_threshold_db)
        _append_series_controls(points, f, vswr[:, 0], pidx, vswr_threshold, refine_extrema=True)
        _append_series_controls(points, f, vswr[:, 1], pidx, vswr_threshold, refine_extrema=True)

    for lo, hi, _target in spec["stopbands"]:
        idx = np.flatnonzero((mhz >= lo) & (mhz <= hi))
        if len(idx):
            points.append(f[idx[np.argmin(il[idx])]])
            _append_series_controls(points, f, il, idx, slope_threshold_db)

    if not points:
        return np.empty(0, dtype=float)
    pts = np.unique(np.asarray(points, dtype=float))
    if len(pts) > int(max_points):
        priority = []
        if len(pidx):
            priority.extend([
                f[pidx[np.argmax(il[pidx])]],
                f[pidx[np.argmax(vswr[pidx, 0])]],
                f[pidx[np.argmax(vswr[pidx, 1])]],
            ])
        for lo, hi, _target in spec["stopbands"]:
            idx = np.flatnonzero((mhz >= lo) & (mhz <= hi))
            if len(idx):
                priority.append(f[idx[np.argmin(il[idx])]])
        keep = list(dict.fromkeys(float(x) for x in priority))
        for x in pts:
            if len(keep) >= int(max_points):
                break
            xf = float(x)
            if xf not in keep:
                keep.append(xf)
        pts = np.asarray(sorted(keep), dtype=float)
    return pts


def new_frequency_points(search_f, candidate_f, tolerance_hz=1e3):
    """Filter candidate frequencies already represented by the search grid."""
    current = np.sort(np.asarray(search_f, dtype=float))
    candidates = np.sort(np.asarray(candidate_f, dtype=float))
    tol = float(tolerance_hz)
    if tol < 0:
        raise ValueError("tolerance_hz must be non-negative")
    if len(current) == 0:
        return candidates
    out = []
    for x in candidates:
        i = np.searchsorted(current, x)
        distances = []
        if i:
            distances.append(abs(x - current[i - 1]))
        if i < len(current):
            distances.append(abs(current[i] - x))
        if not distances or min(distances) > tol:
            out.append(float(x))
    return np.asarray(out, dtype=float)


def common_validation_grid(base_frequencies, critical_by_candidate, tolerance_hz=1e3):
    """Build one validation grid shared by every adaptive-round candidate."""
    base = np.unique(np.asarray(base_frequencies, dtype=float))
    if base.ndim != 1 or len(base) == 0:
        raise ValueError("Base validation grid must be a non-empty 1-D array")
    points = [base]
    for critical in critical_by_candidate:
        points.append(new_frequency_points(base, critical, tolerance_hz))
    return np.unique(np.concatenate(points))


def adaptive_exchange(search_f, optimize, dense_evaluate, spec, *, rounds=2,
                      tolerance_hz=1e3, slope_threshold_db=.5, max_points=64):
    """Run the tested optimize/dense-evaluate frequency-grid exchange loop."""
    current = np.unique(np.asarray(search_f, dtype=float))
    candidate = None
    completed = 0
    for completed in range(int(rounds) + 1):
        candidate = optimize(current)
        dense_f, net = dense_evaluate(candidate)
        critical = critical_frequencies(
            dense_f, net, spec, slope_threshold_db=slope_threshold_db,
            max_points=max_points,
        )
        added = new_frequency_points(current, critical, tolerance_hz)
        if completed >= int(rounds) or len(added) == 0:
            break
        current = np.unique(np.r_[current, added])
    return candidate, current, completed


def adaptive_settings(cfg, section="optimizer"):
    """Resolve adaptive-frequency settings using the historical precedence."""
    nested = cfg.get("validation", {})
    source = cfg.get(section, {})
    return (
        int(nested.get("adaptive_frequency_rounds", source.get("adaptive_frequency_rounds", cfg.get("adaptive_frequency_rounds", 2)))),
        int(nested.get("adaptive_iterations", source.get("adaptive_iterations", cfg.get("adaptive_iterations", 0)))),
        float(nested.get("adaptive_frequency_tolerance_hz", source.get("adaptive_frequency_tolerance_hz", cfg.get("adaptive_frequency_tolerance_hz", 1e3)))),
        int(nested.get("adaptive_max_points_per_round", source.get("adaptive_max_points_per_round", cfg.get("adaptive_max_points_per_round", 64)))),
    )


__all__ = [
    "adaptive_exchange", "adaptive_settings", "common_validation_grid",
    "critical_frequencies", "new_frequency_points",
]
