import hashlib, json, time, sys, subprocess, importlib.metadata
from pathlib import Path
from dataclasses import asdict

import numpy as np
from scipy.optimize import differential_evolution

from ..core.models import FilterDesign, FixedProvider, SimulationResult, decode, NAMES, BOUNDS
from ..core.com import simulate_filter
from ..core.network import evaluate
from ..core.metrics import search_grid, validation_grid, measure, geometry
from .optimizer_utils import (
    EvaluationCounters, IncrementalFrequencyCache, common_validation_grid,
    critical_frequencies, new_frequency_points, PlateauStopper,
)


def save(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    tmp.replace(path)


def evaluate_design(d, cfg, f, rs, rl, wiring='outer_ports'):
    sim = simulate_filter(d, FixedProvider(cfg['com']), f, cfg['center'], wiring=wiring)
    net = evaluate(sim.y_parameters, rs, rl)
    if net['gt'].max() > 1 + 1e-7:
        raise ValueError('Nonpassive power gain')
    result = measure(f, net, d, cfg)
    result['diagnostics'] = sim.diagnostics
    result['search_scalar_objective'] = result['objective']
    return result, net, sim


def dense(d, cfg, rs, rl, wiring='outer_ports', counters=None, *,
         base_grid=None, passes=None, validation=False):
    """Dense-evaluate one fixed design with exact incremental frequency caching."""
    f = validation_grid(cfg['spec'], cfg) if base_grid is None else np.unique(np.asarray(base_grid, dtype=float))
    passes = int(cfg.get('validation', {}).get('dense_refinement_passes',
                       cfg.get('dense_refinement_passes', 2))) if passes is None else int(passes)
    slope = float(cfg.get('dense_slope_threshold_db', .5))
    tolerance = float(cfg.get('validation', {}).get(
        'adaptive_frequency_tolerance_hz',
        cfg.get('adaptive_frequency_tolerance_hz', 1e3),
    ))

    def point_evaluate(points):
        sim = simulate_filter(d, FixedProvider(cfg['com']), points, cfg['center'], wiring=wiring)
        net = evaluate(sim.y_parameters, rs, rl)
        if net['gt'].max() > 1 + 1e-7:
            raise ValueError('Nonpassive power gain')
        payload = dict(net)
        payload['y_parameters'] = sim.y_parameters
        payload['_diagnostics'] = sim.diagnostics
        return payload

    cache = IncrementalFrequencyCache(point_evaluate)

    def cached_evaluate(points):
        nonlocal solved_seen
        payload = cache.evaluate(points)
        solved_delta = cache.solved_points - solved_seen
        solved_seen = cache.solved_points
        if counters is not None:
            counters.add_solved(solved_delta, validation=validation)
            counters.add_evaluation_time(
                cache.last_evaluation_wall_time_s, validation=validation
            )
        net = {key: value for key, value in payload.items()
               if key not in ('frequencies_hz', 'y_parameters', '_diagnostics')}
        evaluated_frequencies = np.asarray(payload['frequencies_hz'], dtype=float)
        sim = SimulationResult(
            frequencies_hz=evaluated_frequencies,
            y_parameters=np.asarray(payload['y_parameters']),
            diagnostics=payload.get('_diagnostics', {}),
        )
        result = measure(evaluated_frequencies, net, d, cfg)
        result['diagnostics'] = sim.diagnostics
        return result, net, sim

    solved_seen = 0
    for _ in range(max(0, passes)):
        result, net, sim = cached_evaluate(f)
        critical = critical_frequencies(
            f, net, cfg['spec'], slope_threshold_db=slope,
            max_points=int(cfg.get('adaptive_max_points_per_round',
                                   cfg.get('validation', {}).get('adaptive_max_points_per_round', 64))),
        )
        added = new_frequency_points(f, critical, tolerance)
        if len(added) == 0:
            break
        f = np.unique(np.r_[f, added])
    return f, cached_evaluate(f)


def initialize(out, cfg):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    package_root = Path(__file__).parents[1]
    source_hash = hashlib.sha256(b''.join(
        p.relative_to(package_root).as_posix().encode() + p.read_bytes()
        for p in sorted(package_root.rglob('*.py'))
    )).hexdigest()
    fingerprint = hashlib.sha256((json.dumps(cfg, sort_keys=True) + source_hash).encode()).hexdigest()
    if (out / 'manifest.json').exists():
        old = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
        if old['fingerprint'] != fingerprint:
            raise ValueError('Run config mismatch: use a new run directory')
    else:
        try:
            commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL, text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            commit = 'unknown'
        save(out / 'manifest.json', dict(
            fingerprint=fingerprint,
            source_hash=source_hash,
            config=cfg,
            git_commit=commit,
            python=sys.version,
            versions={x: importlib.metadata.version(x) for x in ['numpy', 'scipy', 'matplotlib', 'PyYAML']},
            rounding='floor(x+0.5)',
            limitations=[
                'Hypothetical COM; far-off-synchronous extrapolation is unvalidated',
                'Seed-level restart, not exact DE population continuation',
            ],
        ))
    return out


def _canonical_design(x):
    d = decode(x)
    vector = np.asarray([asdict(d)[k] for k in NAMES], dtype=float)
    return d, vector, tuple(float(v) for v in vector)


def _adaptive_budget_limits(total_budget, adaptive_rounds, fractions):
    """Return cumulative total-budget limits for the adaptive rounds."""
    total_budget = int(total_budget)
    if total_budget <= 0:
        raise ValueError('max_unique_decoded_evaluations must be positive')
    round_count = int(adaptive_rounds) + 1
    supplied = [float(value) for value in fractions]
    if not supplied or any(value < 0 for value in supplied):
        supplied = [1.0 / round_count] * round_count
    if len(supplied) < round_count:
        supplied.extend([0.0] * (round_count - len(supplied)))
    supplied = supplied[:round_count]
    if sum(supplied) <= 0:
        supplied = [1.0 / round_count] * round_count
    total_fraction = sum(supplied)
    limits = []
    cumulative = 0.0
    for fraction in supplied:
        cumulative += total_budget * fraction / total_fraction
        limits.append(min(total_budget, max(1, int(np.ceil(cumulative)))))
    limits[-1] = total_budget
    return limits


def _record_primary(record):
    if record.get('feasible', False):
        return float(record['metrics']['worst_il_db'])
    return float(record.get('max_violation', np.inf))


def _mixed_variable_polish(record, cfg, rs, rl, wiring, frequencies, counters=None,
                           promote=True):
    """Deterministic mixed integer/continuous coordinate polish.

    The routine is intentionally independent of SciPy's DE polish option.  It
    ranks every trial on the supplied common validation grid and returns the
    original record unless a trial is strictly better under :func:`rank`.
    """
    settings = cfg.get('micro_polish', {})
    if not settings.get('enabled', True):
        return record, {
            'enabled': False, 'promoted': False, 'evaluations': 0,
            'solved_frequency_points': 0, 'improvement': 0.0,
        }
    frequencies = np.unique(np.asarray(frequencies, dtype=float))
    current = np.asarray([record['design'][name] for name in NAMES], dtype=float)
    best, _, _ = evaluate_design(decode(current), cfg, frequencies, rs, rl, wiring=wiring)
    best['design'] = asdict(decode(current))
    before = best
    evaluations = 0
    solved_points = 0
    step_history = []
    integer_indices = {1, 2, 3}
    integer_steps = [float(value) for value in settings.get('integer_steps', [-1, 1])]
    second_integer_steps = [float(value) for value in settings.get(
        'optional_second_integer_steps', [])]
    fractions = [float(value) for value in settings.get(
        'continuous_steps_fraction_of_bound_span', [0.01, 0.005])]
    fractions = [value for value in fractions if value > 0]
    if not fractions:
        fractions = [0.005]
    shrink = float(settings.get('shrink_factor', 0.5))
    if not 0 < shrink < 1:
        raise ValueError('micro_polish.shrink_factor must be between 0 and 1')
    min_fraction = float(settings.get('minimum_step_fraction', min(fractions)))
    max_passes = max(0, int(settings.get('max_passes', 4)))
    bounds = np.asarray(BOUNDS, dtype=float)
    best_primary_before = _record_primary(record)
    polish_started = time.time()
    step_fraction = max(fractions)
    for polish_pass in range(max_passes):
        fraction = max(min_fraction, step_fraction)
        step_history.append(float(fraction))
        improved = False
        for index in range(len(BOUNDS)):
            if index in integer_indices:
                steps = integer_steps + (second_integer_steps if polish_pass >= 1 else [])
            else:
                span = bounds[index, 1] - bounds[index, 0]
                steps = [-fraction * span, fraction * span]
            for step in steps:
                trial = current.copy()
                trial[index] = np.clip(trial[index] + float(step), *BOUNDS[index])
                candidate = decode(trial)
                _dims, geometry_violation = geometry(candidate, cfg['constraints'])
                if max(geometry_violation) > 0:
                    if counters is not None:
                        counters.geometry_rejections += 1
                    continue
                started = time.time()
                candidate_result, _, _ = evaluate_design(
                    candidate, cfg, frequencies, rs, rl, wiring=wiring)
                elapsed = time.time() - started
                evaluations += 1
                solved_points += len(frequencies)
                if counters is not None:
                    counters.add_solved(len(frequencies), polish=True)
                    counters.add_polish(1, elapsed)
                candidate_result['design'] = asdict(candidate)
                if rank(candidate_result) < rank(best):
                    best = candidate_result
                    current = np.asarray([getattr(candidate, name) for name in NAMES], dtype=float)
                    improved = True
        if not improved:
            if fraction <= min_fraction:
                break
            step_fraction = max(min_fraction, fraction * shrink)
    polished_primary = _record_primary(best)
    promoted = bool(promote and rank(best) < rank(record))
    if not promoted:
        best = record
    elapsed = time.time() - polish_started
    return best, {
        'enabled': True,
        'promoted': promoted,
        'evaluations': evaluations,
        'solved_frequency_points': solved_points,
        'polish_wall_time_s': elapsed,
        'passes': len(step_history),
        'step_fraction_history': step_history,
        'before_rank': list(rank(record)),
        'after_rank': list(rank(best)),
        'improvement': float(best_primary_before - polished_primary),
        'best_feasible': bool(best.get('feasible', False)),
    }


def _build_population(cfg, rng, center, neighbor=None):
    bounds = np.asarray(BOUNDS, dtype=float)
    population = int(cfg['optimizer']['population'])
    if population < 5:
        raise ValueError('Population must be at least 5')
    valid = []
    attempts = 0
    while len(valid) < population:
        attempts += 1
        if attempts > 100000:
            raise ValueError('Could not build a manufacturable population')
        if attempts == 1:
            x = center.copy()
        elif len(valid) < population // 2:
            x = np.clip(center + rng.normal(0, .08, len(center)) * (bounds[:, 1] - bounds[:, 0]), bounds[:, 0], bounds[:, 1])
        else:
            x = rng.uniform(bounds[:, 0], bounds[:, 1])
        d, canonical, _ = _canonical_design(x)
        if max(geometry(d, cfg['constraints'])[1]) == 0:
            valid.append(canonical)
    pop = np.asarray(valid)
    pop[0] = center
    if neighbor is not None and len(pop) > 1:
        pop[1] = np.asarray([neighbor[k] for k in NAMES], dtype=float)
    return pop


class _HistoryBuffer:
    def __init__(self, path, flush_every=100):
        self.file = Path(path).open('a', encoding='utf-8')
        self.flush_every = max(1, int(flush_every))
        self.pending = []
        self.io_time_s = 0.0

    def write(self, record):
        self.pending.append(json.dumps(record, allow_nan=False) + '\n')
        if len(self.pending) >= self.flush_every:
            self.flush()

    def flush(self):
        started = time.time()
        if self.pending:
            self.file.writelines(self.pending)
            self.pending.clear()
        self.file.flush()
        self.io_time_s += time.time() - started

    def close(self):
        self.flush()
        self.file.close()


def _adaptive_settings(cfg, section='optimizer'):
    nested = cfg.get('validation', {})
    source = cfg.get(section, {})
    return (
        int(nested.get('adaptive_frequency_rounds', source.get('adaptive_frequency_rounds', cfg.get('adaptive_frequency_rounds', 2)))),
        int(nested.get('adaptive_iterations', source.get('adaptive_iterations', cfg.get('adaptive_iterations', 0)))),
        float(nested.get('adaptive_frequency_tolerance_hz', source.get('adaptive_frequency_tolerance_hz', cfg.get('adaptive_frequency_tolerance_hz', 1e3)))),
        int(nested.get('adaptive_max_points_per_round', source.get('adaptive_max_points_per_round', cfg.get('adaptive_max_points_per_round', 64)))),
    )


def optimize_one(out, cfg, rs, rl, seed, neighbor=None, *, wiring='outer_ports',
                 mode='production', run_label=None, warm_resume=None):
    out = Path(out)
    if run_label:
        tag = f'{run_label}__R{rs:g}_L{rl:g}_seed{seed}'
    elif wiring == 'outer_ports':
        tag = f'R{rs:g}_L{rl:g}_seed{seed}'
    else:
        tag = f'{wiring}__R{rs:g}_L{rl:g}_seed{seed}'
    dest = out / (tag + '.json')
    if dest.exists():
        return json.loads(dest.read_text(encoding='utf-8'))

    started = time.time()
    search_f = search_grid(cfg['spec'], cfg)
    counters = EvaluationCounters()
    failures = 0
    current_best = None
    global_best = None
    best_so_far_trace = []
    budget_stop = False
    budget_stop_candidates = 0
    history = out / (tag + '.jsonl')
    rng = np.random.default_rng(seed)
    center = np.asarray([asdict(FilterDesign())[k] for k in NAMES], dtype=float)
    adaptive_rounds, adaptive_iterations, adaptive_tol_hz, adaptive_max_points = _adaptive_settings(cfg)
    if adaptive_iterations <= 0:
        adaptive_iterations = max(1, int(cfg['optimizer']['maxiter']) // 3)
    slope_threshold = float(cfg.get('dense_slope_threshold_db', .5))
    runtime = cfg.get('optimizer_runtime', {})
    flush_every = int(runtime.get('history_flush_every', 100))
    if warm_resume is None:
        warm_resume = bool(cfg.get('optimizer', {}).get('warm_resume', False))
    checkpoint_path = out / (tag + '.checkpoint.json')
    resume_info = dict(used=False, non_exact_de_resume=True,
                       source=str(checkpoint_path.name) if checkpoint_path.exists() else None)
    checkpoint_best = None
    if warm_resume and checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8'))
        checkpoint_best = checkpoint.get('best')
        if checkpoint_best and checkpoint_best.get('design'):
            center = np.asarray([checkpoint_best['design'][k] for k in NAMES], dtype=float)
            resume_info['used'] = True
    adaptive_candidates = []
    objective_cache = {}
    seen_decoded = set()
    total_budget = cfg.get('max_unique_decoded_evaluations')
    if total_budget is None:
        total_budget = cfg.get('optimizer', {}).get('max_unique_decoded_evaluations')
    if total_budget is None and mode == 'benchmark':
        total_budget = cfg.get('convergence', {}).get('max_unique_decoded_evaluations')
    total_budget = None if total_budget is None else int(total_budget)
    if total_budget is not None and total_budget <= 0:
        raise ValueError('max_unique_decoded_evaluations must be positive')
    allocation = cfg.get('budget_allocation', {})
    fractions = allocation.get(
        'adaptive_round_fractions', [0.70, 0.20, 0.10])
    budget_limits = (_adaptive_budget_limits(total_budget, adaptive_rounds, fractions)
                     if total_budget is not None else None)

    def significant_update(old, new):
        if old is None:
            return True
        if bool(old.get('feasible')) != bool(new.get('feasible')):
            return True
        improvement = _record_primary(old) - _record_primary(new)
        threshold_cfg = cfg.get('convergence', {})
        absolute = float(threshold_cfg.get(
            'significant_improvement_absolute',
            threshold_cfg.get('infeasible', {}).get(
                'best_polish_primary_improvement', 0.02)))
        relative = float(threshold_cfg.get(
            'significant_improvement_relative', 0.01))
        scale = max(abs(_record_primary(old)), np.finfo(float).tiny)
        return improvement >= absolute or improvement / scale >= relative

    def trace_best(record):
        nonlocal global_best
        if 'metrics' not in record or 'violations' not in record:
            return
        if global_best is None or rank(record) < rank(global_best):
            if significant_update(global_best, record):
                best_so_far_trace.append({
                    'unique_evaluation': int(counters.unique_decoded_evaluations),
                    'rank_tuple': list(rank(record)),
                    'primary_metric': _record_primary(record),
                    'max_violation': float(record['max_violation']),
                    'sum_violation': float(sum(record['violations'].values())),
                    'worst_il_db': float(record['metrics']['worst_il_db']),
                    'design': dict(record['design']),
                })
            global_best = record

    history_writer = _HistoryBuffer(history, flush_every)
    try:
        for adaptive_round in range(adaptive_rounds + 1):
            round_budget_stop = False
            round_best = None
            if current_best is not None:
                center = np.asarray([current_best['design'][k] for k in NAMES], dtype=float)
            initial_neighbor = neighbor if adaptive_round == 0 else None
            if checkpoint_best and adaptive_round == 0 and initial_neighbor is None:
                initial_neighbor = checkpoint_best.get('design')
            pop = _build_population(cfg, rng, center, initial_neighbor)
            if budget_limits is None:
                round_limit = None
                round_iterations = cfg['optimizer']['maxiter'] if adaptive_round == 0 else adaptive_iterations
            else:
                round_limit = budget_limits[adaptive_round]
                population = max(5, int(cfg['optimizer']['population']))
                remaining = max(1, round_limit - counters.unique_decoded_evaluations)
                required_iterations = int(np.ceil(remaining / population)) + 2
                ceiling = int(cfg['optimizer'].get(
                    'maxiter_ceiling', max(required_iterations, cfg['optimizer']['maxiter'])))
                round_iterations = min(ceiling, max(
                    int(cfg['optimizer']['maxiter']), required_iterations))

            def objective(x):
                nonlocal failures, round_best, budget_stop, budget_stop_candidates, round_budget_stop
                counters.objective_calls += 1
                counters.canonical_candidates_seen += 1
                d, canonical, key = _canonical_design(x)
                cache_key = (key, tuple(np.asarray(search_f, dtype=float)))
                if cache_key in objective_cache:
                    counters.cache_hits += 1
                    return objective_cache[cache_key]
                is_new_design = key not in seen_decoded
                if ((is_new_design and total_budget is not None and
                     counters.unique_decoded_evaluations >= total_budget) or
                    (is_new_design and round_limit is not None and
                     counters.unique_decoded_evaluations >= round_limit)):
                    # The optimizer can submit one more point before SciPy
                    # observes the callback.  Do not count an unexecuted
                    # candidate as a physical design evaluation.
                    round_budget_stop = True
                    if total_budget is not None and counters.unique_decoded_evaluations >= total_budget:
                        budget_stop = True
                    budget_stop_candidates += 1
                    penalty = 1e15
                    objective_cache[cache_key] = penalty
                    return penalty
                if is_new_design:
                    seen_decoded.add(key)
                    counters.unique_decoded_evaluations += 1
                try:
                    _dims, gv = geometry(d, cfg['constraints'])
                    if max(gv) > 0:
                        counters.geometry_rejections += 1
                        record = dict(
                            objective=1e10 + 1e6 * sum(gv),
                            search_scalar_objective=1e10 + 1e6 * sum(gv),
                            failure='manufacturing constraint',
                            design=asdict(d),
                        )
                    else:
                        evaluation_started = time.time()
                        try:
                            record, _, _ = evaluate_design(d, cfg, search_f, rs, rl, wiring=wiring)
                        finally:
                            counters.add_evaluation_time(time.time() - evaluation_started)
                        counters.add_solved(len(search_f))
                        counters.valid_physics_evaluations += 1
                        record['design'] = asdict(d)
                        record['search_scalar_objective'] = record['objective']
                        trace_best(record)
                        if round_best is None or rank(record) < rank(round_best):
                            round_best = record
                            save(checkpoint_path, dict(
                                objective_calls=counters.objective_calls,
                                canonical_candidates_seen=counters.canonical_candidates_seen,
                                unique_decoded_evaluations=counters.unique_decoded_evaluations,
                                valid_physics_evaluations=counters.valid_physics_evaluations,
                                cache_hits=counters.cache_hits,
                                solved_frequency_points=counters.solved_frequency_points,
                                adaptive_round=adaptive_round,
                                search_frequency_count=len(search_f),
                                best=round_best,
                            ))
                            history_writer.flush()
                except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                    failures += 1
                    record = dict(objective=1e15, search_scalar_objective=1e15,
                                  failure=str(exc), design=asdict(d))
                record['evaluation'] = counters.unique_decoded_evaluations
                record['adaptive_round'] = adaptive_round
                history_writer.write(record)
                objective_cache[cache_key] = record['objective']
                return record['objective']

            callback = None
            early_stop = bool(runtime.get('production_early_stop',
                               cfg.get('optimizer', {}).get('production_early_stop', False)))
            if mode == 'benchmark' or cfg.get('convergence', {}).get('benchmark_early_stop') is False:
                early_stop = False
            if early_stop:
                min_gen = int(runtime.get('min_generations_before_stop', 20))
                patience = int(runtime.get('patience_generations', 20))
                callback = PlateauStopper(
                    min_generations=min_gen, patience_generations=patience,
                    improvement_abs=.02, improvement_rel=.02,
                    value_fn=objective,
                )

            def budget_callback(xk, convergence):
                if budget_stop or round_budget_stop or (round_limit is not None and
                                   counters.unique_decoded_evaluations >= round_limit):
                    return True
                return bool(callback(xk, convergence)) if callback is not None else False

            differential_evolution(
                objective, BOUNDS, init=pop, seed=seed + adaptive_round,
                maxiter=round_iterations, polish=False, tol=0, atol=0, workers=1,
                callback=budget_callback,
            )
            if round_best is None:
                if budget_stop and current_best is not None:
                    break
                raise RuntimeError('No numerically valid manufacturable candidate')
            current_best = round_best
            d = FilterDesign(**current_best['design'])
            dense_f, (_dense_result, dense_net, _dense_sim) = dense(
                d, cfg, rs, rl, wiring=wiring, counters=counters, validation=True,
            )
            critical = critical_frequencies(
                dense_f, dense_net, cfg['spec'], slope_threshold_db=slope_threshold,
                max_points=adaptive_max_points,
            )
            adaptive_candidates.append(dict(
                current_best,
                search_objective=current_best['objective'],
                adaptive_round=adaptive_round,
                dense_critical_frequencies=critical.tolist(),
            ))
            added = new_frequency_points(search_f, critical, adaptive_tol_hz)
            if (adaptive_round >= adaptive_rounds or len(added) == 0 or
                    budget_stop or (total_budget is not None and
                                    counters.unique_decoded_evaluations >= total_budget)):
                break
            search_f = np.unique(np.r_[search_f, added])
    finally:
        history_writer.close()
    counters.global_search_wall_time_s = time.time() - started
    counters.optimization_wall_time_s = counters.global_search_wall_time_s

    base_validation_f = validation_grid(cfg['spec'], cfg)
    common_f = common_validation_grid(
        base_validation_f,
        [candidate['dense_critical_frequencies'] for candidate in adaptive_candidates],
        adaptive_tol_hz,
    )
    validated = []
    for candidate in adaptive_candidates:
        candidate_design = FilterDesign(**candidate['design'])
        frequencies, (validation_result, net, sim) = dense(
            candidate_design, cfg, rs, rl, wiring=wiring, counters=counters,
            base_grid=common_f, passes=0, validation=True,
        )
        record = dict(validation_result)
        record.update(
            design=asdict(candidate_design), rs=rs, rl=rl, seed=seed,
            search_objective=candidate['search_objective'],
            search_primary_metric=_record_primary(candidate),
            selected_adaptive_round=candidate['adaptive_round'],
            adaptive_round=candidate['adaptive_round'],
            dense_critical_frequencies=candidate['dense_critical_frequencies'],
        )
        if candidate['feasible'] and record['feasible']:
            record['validation_gap_primary'] = record['metrics']['worst_il_db'] - candidate['metrics']['worst_il_db']
        else:
            record['validation_gap_primary'] = record['max_violation'] - candidate['max_violation']
        validated.append((record, sim, net, frequencies))
    selected, sim, net, frequencies = min(validated, key=lambda item: rank(item[0]))
    search_best = min(adaptive_candidates, key=rank)
    pre_polish = dict(selected)
    polished, polish = _mixed_variable_polish(
        selected, cfg, rs, rl, wiring, common_f, counters=counters,
        promote=(mode != 'production' or cfg.get('micro_polish', {}).get(
            'promote_in_production', True)))
    if polish.get('promoted'):
        selected = polished
        sim = simulate_filter(
            decode([selected['design'][name] for name in NAMES]),
            FixedProvider(cfg['com']), common_f, cfg['center'], wiring=wiring)
        net = evaluate(sim.y_parameters, rs, rl)
        frequencies = common_f
    post_polish = dict(selected)
    d = FilterDesign(**selected['design'])
    result = selected
    result.update(
        design=asdict(d), rs=rs, rl=rl, seed=seed, wiring=wiring,
        evaluations=counters.unique_decoded_evaluations,
        objective_calls=counters.objective_calls,
        canonical_candidates_seen=counters.canonical_candidates_seen,
        unique_decoded_evaluations=counters.unique_decoded_evaluations,
        requested_unique_design_budget=total_budget,
        valid_physics_evaluations=counters.valid_physics_evaluations,
        geometry_rejections=counters.geometry_rejections,
        cache_hits=counters.cache_hits,
        solved_frequency_points=counters.solved_frequency_points,
        validation_solved_frequency_points=counters.validation_frequency_points,
        polish_evaluations=counters.polish_evaluations,
        polish_solved_frequency_points=counters.polish_solved_frequency_points,
        optimization_wall_time_s=counters.optimization_wall_time_s,
        global_search_wall_time_s=counters.global_search_wall_time_s,
        validation_wall_time_s=counters.validation_wall_time_s,
        polish_wall_time_s=counters.polish_wall_time_s,
        com_network_evaluation_wall_time_s=counters.com_network_evaluation_wall_time_s,
        history_io_time_s=history_writer.io_time_s,
        failures=failures,
        elapsed_s=time.time() - started,
        search_best_objective=search_best['objective'],
        search_scalar_objective=search_best['objective'],
        validated_rank_tuple=list(rank(selected)),
        search_frequency_count=len(search_f),
        validation_frequency_count=len(common_f),
        common_validation_frequencies_hz=common_f.tolist(),
        adaptive_rounds_completed=adaptive_candidates[-1]['adaptive_round'],
        adaptive_candidate_count=len(adaptive_candidates),
        adaptive_round_budget_limits=budget_limits,
        budget_allocation_fractions=list(fractions) if budget_limits is not None else None,
        budget_stop=budget_stop,
        budget_stop_candidates=budget_stop_candidates,
        best_so_far_trace=best_so_far_trace,
        last_significant_improvement_unique_eval=(
            best_so_far_trace[-1]['unique_evaluation'] if best_so_far_trace else None),
        fraction_of_budget_at_last_significant_improvement=(
            best_so_far_trace[-1]['unique_evaluation'] / max(float(total_budget), 1.0)
            if best_so_far_trace and total_budget is not None else None),
        pre_polish_result=pre_polish,
        post_polish_result=post_polish,
        polish=polish,
        adaptive_candidates=[{
            'adaptive_round': candidate['adaptive_round'],
            'design': candidate['design'],
            'search_objective': candidate['search_objective'],
            'dense_critical_frequencies': candidate['dense_critical_frequencies'],
        } for candidate in adaptive_candidates],
        resume=resume_info,
        response_file=tag + '.npz',
    )
    np.savez_compressed(out / (tag + '.npz'), frequencies_hz=frequencies, y=sim.y_parameters, **net)
    save(dest, result)
    return result


def run(out, cfg, resistances, rl=None, use_neighbor=True):
    """Run the legacy ordered sweep, with optional neighbor warm-start.

    Stage 2B should add a separate independent-coarse first pass before enabling
    neighbor refinement. Keeping this switch makes that integration explicit.
    """
    out = initialize(out, cfg)
    neighbor = None
    for r in resistances:
        results = [
            optimize_one(out, cfg, r, r if rl is None else rl, seed, neighbor if use_neighbor else None)
            for seed in cfg['seeds']
        ]
        best = min(results, key=rank)
        neighbor = best['design'] if use_neighbor else None
        print(json.dumps(dict(
            resistance=r,
            worst_il_db=best['metrics']['worst_il_db'],
            feasible=best['feasible'],
        )), flush=True)


def rank(r):
    return (
        not r['feasible'],
        r['max_violation'] if not r['feasible'] else 0,
        sum(r['violations'].values()) if not r['feasible'] else 0,
        r['metrics']['worst_il_db'],
    )
