"""Shared optimizer helpers for Stage 2/3 SAW studies.

These helpers intentionally do not alter COM physics. They only make the search
budget and adaptive frequency-grid logic explicit and testable.
"""
from __future__ import annotations

import numpy as np
import time
from dataclasses import dataclass, asdict


def aggregate_diagnostics(diagnostics):
    """Merge diagnostics from disjoint frequency batches conservatively.

    The incremental evaluator receives one aggregate diagnostic mapping per
    batch.  Aggregation is deliberately based on the direction of each
    diagnostic rather than on whichever batch happened to run last.
    """
    items = [dict(item) for item in diagnostics if item]
    if not items:
        return {}
    keys = set().union(*(item for item in items))
    minimum_keys = {'min_conductance_eigenvalue'}
    maximum_keys = {
        'reciprocity_error', 'max_acoustic_solve_residual',
        'max_acoustic_condition_number', 'admittance_scale',
        'passivity_tolerance', 'reciprocity_tolerance',
    }
    frequency_for = {
        'min_conductance_eigenvalue': 'worst_conductance_frequency_hz',
        'reciprocity_error': 'worst_reciprocity_frequency_hz',
        'max_acoustic_solve_residual': 'worst_acoustic_residual_frequency_hz',
        'max_acoustic_condition_number': 'worst_acoustic_condition_frequency_hz',
    }
    frequency_keys = set(frequency_for.values())
    result = {}
    for key in sorted(keys):
        values = [item[key] for item in items if key in item]
        if not values:
            continue
        if key in frequency_keys:
            # Set together with the controlling value below so a later loop
            # iteration cannot overwrite the winning frequency.
            continue
        if isinstance(values[0], (bool, np.bool_)) or key.startswith(('has_', 'nonfinite', 'failure')) or key.endswith('_failure'):
            result[key] = bool(any(bool(value) for value in values))
            continue
        numeric = all(np.isscalar(value) and np.isreal(value) for value in values)
        if key in minimum_keys and numeric:
            index = int(np.argmin(np.asarray(values, dtype=float)))
            result[key] = float(values[index])
        elif key in maximum_keys and numeric:
            index = int(np.argmax(np.asarray(values, dtype=float)))
            result[key] = float(values[index])
        elif numeric:
            # Unknown scalar metadata is expected to be invariant.  Keep the
            # most conservative value for tolerances and the first value for
            # ordinary metadata.
            result[key] = float(max(values)) if 'tolerance' in key else values[0]
        else:
            result[key] = values[0]

        controlling_key = frequency_for.get(key)
        if controlling_key and controlling_key in keys:
            control_values = [
                item.get(controlling_key) for item in items
                if key in item and controlling_key in item
            ]
            if control_values:
                if key in minimum_keys:
                    control_index = int(np.argmin([
                        item[key] for item in items
                        if key in item and controlling_key in item
                    ]))
                else:
                    control_index = int(np.argmax([
                        item[key] for item in items
                        if key in item and controlling_key in item
                    ]))
                result[controlling_key] = float(control_values[control_index])
    return result


def scaled_population(base_population, dimensions, reference_dimensions=7, minimum=5):
    """Scale an explicit DE initial population with problem dimension.

    Existing hybrid code supplies an explicit init population, so SciPy's
    ``popsize`` parameter is not used. ``base_population`` is interpreted as
    the desired population at ``reference_dimensions``.
    """
    base_population = int(base_population)
    dimensions = int(dimensions)
    reference_dimensions = int(reference_dimensions)
    minimum = int(minimum)
    if base_population < minimum:
        raise ValueError(f'Population must be at least {minimum}')
    if dimensions <= 0 or reference_dimensions <= 0:
        raise ValueError('Dimensions must be positive')
    return max(minimum, int(np.ceil(base_population * dimensions / reference_dimensions)))


@dataclass
class EvaluationCounters:
    """Counters used to distinguish optimizer calls from actual work."""

    objective_calls: int = 0
    canonical_candidates_seen: int = 0
    unique_decoded_evaluations: int = 0
    valid_physics_evaluations: int = 0
    geometry_rejections: int = 0
    cache_hits: int = 0
    solved_frequency_points: int = 0
    validation_frequency_points: int = 0
    polish_evaluations: int = 0
    polish_solved_frequency_points: int = 0
    optimization_wall_time_s: float = 0.0
    global_search_wall_time_s: float = 0.0
    validation_wall_time_s: float = 0.0
    polish_wall_time_s: float = 0.0
    com_network_evaluation_wall_time_s: float = 0.0
    history_io_time_s: float = 0.0

    def add_solved(self, count, *, validation=False, polish=False):
        count = int(count)
        self.solved_frequency_points += count
        if validation:
            self.validation_frequency_points += count
        if polish:
            self.polish_solved_frequency_points += count

    def add_polish(self, count, elapsed):
        self.polish_evaluations += int(count)
        self.polish_wall_time_s += float(elapsed)

    def add_evaluation_time(self, elapsed, *, validation=False):
        elapsed = float(elapsed)
        self.com_network_evaluation_wall_time_s += elapsed
        if validation:
            self.validation_wall_time_s += elapsed
        else:
            self.optimization_wall_time_s += elapsed

    def as_dict(self):
        values = asdict(self)
        values['unique_evaluations'] = self.unique_decoded_evaluations
        values['validation_solved_frequency_points'] = self.validation_frequency_points
        values['global_search_evaluations'] = self.unique_decoded_evaluations
        return values


class IncrementalFrequencyCache:
    """Cache a fixed candidate's frequency-point response without approximation.

    The evaluator must return a mapping whose array values have the same first
    dimension as the requested frequency vector. Scalar metadata is retained.
    New frequencies are evaluated exactly once and merged in sorted order.
    """

    def __init__(self, evaluator):
        self.evaluator = evaluator
        self._values = {}
        self._metadata = {}
        self._diagnostic_batches = []
        self.solved_points = 0
        self.last_evaluation_wall_time_s = 0.0

    @property
    def cached_frequencies(self):
        return np.asarray(sorted(self._values), dtype=float)

    def evaluate(self, frequencies_hz):
        frequencies = np.unique(np.asarray(frequencies_hz, dtype=float))
        if frequencies.ndim != 1 or len(frequencies) == 0:
            raise ValueError('frequencies must be a non-empty one-dimensional array')
        missing = np.asarray([x for x in frequencies if float(x) not in self._values])
        self.last_evaluation_wall_time_s = 0.0
        if len(missing):
            started = time.time()
            payload = self.evaluator(missing)
            self.last_evaluation_wall_time_s = time.time() - started
            if not isinstance(payload, dict):
                raise TypeError('Incremental evaluator must return a mapping')
            for key, value in payload.items():
                if key == '_diagnostics' and isinstance(value, dict):
                    self._diagnostic_batches.append(value)
                    self._metadata[key] = aggregate_diagnostics(self._diagnostic_batches)
                    continue
                array = np.asarray(value)
                if array.ndim and array.shape[0] == len(missing):
                    if key == 'frequencies_hz':
                        continue
                    for index, frequency in enumerate(missing):
                        self._values.setdefault(float(frequency), {})[key] = array[index]
                else:
                    self._metadata[key] = value
            self.solved_points += len(missing)

        result = {'frequencies_hz': frequencies.copy()}
        keys = set(self._metadata)
        for value in self._values.values():
            keys.update(value)
        for key in sorted(keys):
            if key in self._metadata and key not in self._values.get(float(frequencies[0]), {}):
                result[key] = self._metadata[key]
                continue
            rows = []
            for frequency in frequencies:
                if float(frequency) not in self._values or key not in self._values[float(frequency)]:
                    raise ValueError(f'Frequency evaluator omitted array value {key!r}')
                rows.append(self._values[float(frequency)][key])
            result[key] = np.asarray(rows)
        return result


def paired_improvements(records_by_budget, metric_fn):
    """Return paired same-seed deltas for consecutive numeric budgets."""
    budgets = sorted(int(budget) for budget in records_by_budget)
    out = []
    for lower, upper in zip(budgets, budgets[1:]):
        lower_by_seed = {int(record['seed']): record for record in records_by_budget[lower]}
        upper_by_seed = {int(record['seed']): record for record in records_by_budget[upper]}
        common = sorted(set(lower_by_seed) & set(upper_by_seed))
        deltas = [
            float(metric_fn(lower_by_seed[seed]) - metric_fn(upper_by_seed[seed]))
            for seed in common
        ]
        out.append({
            'lower_budget': lower,
            'upper_budget': upper,
            'seed_count': len(deltas),
            'seeds': common,
            'deltas': deltas,
            'median_improvement': float(np.median(deltas)) if deltas else None,
            'mean_improvement': float(np.mean(deltas)) if deltas else None,
            'iqr_improvement': float(np.percentile(deltas, 75) - np.percentile(deltas, 25)) if deltas else None,
        })
    return out


def last_significant_improvement(trace, budget, *, absolute=0.02, relative=0.01):
    """Find the last meaningful best-so-far update in a compact trace."""
    if not trace:
        return None, None
    significant = [trace[0]]
    for row in trace[1:]:
        old = float(significant[-1]['primary_metric'])
        new = float(row['primary_metric'])
        improvement = old - new
        scale = max(abs(old), np.finfo(float).tiny)
        if improvement >= float(absolute) or improvement / scale >= float(relative):
            significant.append(row)
    last = significant[-1]
    return int(last['unique_evaluation']), float(last['unique_evaluation']) / max(float(budget), 1.0)


def _region_indices(mhz, band):
    lo, hi = band[:2]
    return np.flatnonzero((mhz >= lo) & (mhz <= hi))


def _append_series_controls(points, f, values, indices, threshold, *, refine_extrema=False):
    if len(indices) == 0:
        return
    local = np.asarray(values)[indices]
    # Both extrema matter: a low IL / high VSWR point can control a different
    # constraint than the worst point already added by the caller.
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
    """Return dense-grid frequencies most likely to control the specification.

    Includes passband IL and input/output VSWR extrema/slopes, each stopband
    worst attenuation, and IL extrema/slopes.  This is a candidate generator
    for an exchange/refinement loop; it does not itself change the objective.
    """
    f = np.asarray(frequencies_hz, dtype=float)
    il = np.asarray(net['il'], dtype=float)
    vswr = np.asarray(net['vswr'], dtype=float)
    if f.ndim != 1 or il.shape != f.shape or vswr.shape != (len(f), 2):
        raise ValueError('Unexpected frequency/network array shapes')
    if len(f) < 2:
        return f.copy()

    mhz = f / 1e6
    points = []
    vswr_threshold = slope_threshold_db if vswr_slope_threshold is None else vswr_slope_threshold
    p_lo, p_hi = spec['passband']
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

    for lo, hi, _target in spec['stopbands']:
        idx = np.flatnonzero((mhz >= lo) & (mhz <= hi))
        if len(idx):
            points.append(f[idx[np.argmin(il[idx])]])
            _append_series_controls(points, f, il, idx, slope_threshold_db)

    if not points:
        return np.empty(0, dtype=float)
    pts = np.unique(np.asarray(points, dtype=float))

    # Prefer points controlling explicit pass/stop specs before filling with
    # general extrema. Preserve deterministic ordering by frequency after cap.
    if len(pts) > int(max_points):
        priority = []
        if len(pidx):
            priority.extend([
                f[pidx[np.argmax(il[pidx])]],
                f[pidx[np.argmax(vswr[pidx, 0])]],
                f[pidx[np.argmax(vswr[pidx, 1])]],
            ])
        for lo, hi, _target in spec['stopbands']:
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
        raise ValueError('tolerance_hz must be non-negative')
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
        raise ValueError('Base validation grid must be a non-empty 1-D array')
    points = [base]
    for critical in critical_by_candidate:
        points.append(new_frequency_points(base, critical, tolerance_hz))
    return np.unique(np.concatenate(points))


def primary_metric(record):
    """Return the convergence metric used for a validated record."""
    if record.get('feasible', False):
        return float(record['metrics']['worst_il_db'])
    return float(record.get('max_violation', np.inf))


def validated_candidate_selection(candidates, base_grid, critical_by_candidate,
                                  evaluate_candidate, tolerance_hz=1e3):
    """Re-evaluate all candidates on a common grid and return the best one.

    ``evaluate_candidate(candidate, frequencies)`` must return the complete
    result record.  The helper intentionally uses the supplied rank function
    rather than assuming that the last adaptive round is best.
    """
    if len(candidates) != len(critical_by_candidate) or not candidates:
        raise ValueError('Candidates and critical-frequency collections must match')
    from .study import rank  # local import avoids a module import cycle
    common = common_validation_grid(base_grid, critical_by_candidate, tolerance_hz)
    validated = []
    for candidate in candidates:
        record = evaluate_candidate(candidate, common)
        record['common_validation_grid_count'] = len(common)
        record['validated_objective'] = record.get('objective')
        validated.append(record)
    return min(validated, key=rank), validated, common


class PlateauStopper:
    """Conservative optional DE callback for production runs.

    The callback never activates before ``min_generations`` and requires a
    complete patience window without a meaningful improvement.  Benchmark
    mode should pass ``None`` to SciPy instead of using this callback.
    """

    def __init__(self, *, min_generations=20, patience_generations=20,
                 feasible=False, improvement_abs=0.02, improvement_rel=0.02,
                 value_fn=None):
        self.min_generations = int(min_generations)
        self.patience_generations = int(patience_generations)
        if self.min_generations < 0 or self.patience_generations <= 0:
            raise ValueError('Invalid plateau stopper generation settings')
        self.feasible = bool(feasible)
        self.improvement_abs = float(improvement_abs)
        self.improvement_rel = float(improvement_rel)
        self.value_fn = value_fn
        self.generation = 0
        self.best = None
        self.last_improvement_generation = 0

    def _value(self, xk):
        value = xk
        if isinstance(xk, dict):
            value = xk.get('worst_il_db', xk.get('max_violation', np.inf))
        return float(value)

    def update(self, value):
        self.generation += 1
        value = float(value)
        if self.best is None:
            improved = True
        else:
            scale = max(abs(self.best), 1.0)
            improved = (self.best - value > self.improvement_abs or
                        (self.best - value) / scale > self.improvement_rel)
        if improved:
            self.best = value
            self.last_improvement_generation = self.generation
        return self.should_stop()

    def should_stop(self):
        return (
            self.generation >= self.min_generations and
            self.generation - self.last_improvement_generation >= self.patience_generations
        )

    def __call__(self, xk, convergence):
        del convergence
        # A SciPy callback only receives xk.  A value function is therefore
        # required before this adapter can make a numerical plateau claim.
        if np.ndim(xk) != 0 and not isinstance(xk, dict):
            if self.value_fn is None:
                return False
            return self.update(self.value_fn(xk))
        return self.update(self._value(xk))


def adaptive_exchange(search_f, optimize, dense_evaluate, spec, *, rounds=2,
                      tolerance_hz=1e3, slope_threshold_db=.5, max_points=64):
    """Generic tested exchange loop used to validate adaptive-grid behavior.

    ``optimize`` receives the current search grid and returns a candidate.
    ``dense_evaluate`` returns ``(dense_f, net)`` for that candidate.
    """
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
