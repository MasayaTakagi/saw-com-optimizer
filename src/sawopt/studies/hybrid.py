"""Hybrid DMS + resonator optimization with impedance and adaptive-grid plumbing.

Stage 2A reference implementation. It intentionally keeps the existing
Differential Evolution / topology architecture and COM physics. Stage 2B
(successive-halving across all topology x wiring combinations and independent
impedance coarse passes) is specified in CODEX_STAGE2_TASK.md rather than
silently changing the study semantics here.
"""
import argparse, json, time
from pathlib import Path
from dataclasses import asdict

import numpy as np
import yaml
from scipy.optimize import differential_evolution

from ..core.models import FilterDesign, BOUNDS, NAMES, decode
from ..core.hybrid import TOPOLOGIES, RESONATOR_BOUNDS, response, layout, decode_resonator
from ..core.metrics import search_grid, validation_grid, measure
from ..io.run_store import initialize
from ..io.serialization import save
from ..optimizers.selection import rank
from ..optimization.adaptive_frequency import adaptive_settings, common_validation_grid, critical_frequencies, new_frequency_points
from ..optimization.budget import PlateauStopper
from ..optimization.cache import IncrementalFrequencyCache
from ..optimization.counters import EvaluationCounters
from ..optimization.history import HistoryBuffer
from ..optimization.population import scaled_population

_HistoryBuffer = HistoryBuffer
_adaptive_settings = adaptive_settings


def _resolve_terminations(cfg, rs=None, rl=None):
    if rs is None:
        rs = cfg.get('source_impedance_ohm', 50.0)
    if rl is None:
        rl = cfg.get('load_impedance_ohm', rs)
    rs, rl = float(rs), float(rl)
    if not np.isfinite(rs) or not np.isfinite(rl) or rs <= 0 or rl <= 0:
        raise ValueError('Positive finite real source/load impedances required')
    return rs, rl


def _canonical_candidate(x):
    """Decode integer variables before cache/checkpoint identity is formed."""
    d = decode(x[:7])
    resonators = [decode_resonator(x[i:i+3]) for i in range(7, len(x), 3)]
    vector = [asdict(d)[k] for k in NAMES]
    for r in resonators:
        vector.extend([r.wavelength_um, r.pairs, r.aperture_um])
    key = tuple(float(v) for v in vector)
    return d, resonators, np.asarray(vector, dtype=float), key


def _initial_base(topology, parent=None):
    count_res = len(TOPOLOGIES[topology][1])
    base = [asdict(FilterDesign())[k] for k in NAMES]
    if parent:
        base = [parent['design'][k] for k in NAMES]
    for i in range(count_res):
        if parent and len(parent.get('resonators', [])) == count_res:
            r = parent['resonators'][i]
            base.extend([r['wavelength_um'], r['pairs'], r['aperture_um']])
        else:
            # Keep the existing series/shunt-biased initial wavelengths.
            shunt = -1 in TOPOLOGIES[topology][1][i]
            base.extend([5.15 if shunt else 5.0, 15, 60])
    return np.asarray(base, dtype=float)


def _build_population(base, bounds, topology, cfg, rng, population, warm_starts=None):
    valid = []
    attempts = 0
    while len(valid) < population:
        attempts += 1
        if attempts > 100000:
            raise ValueError('No feasible initial population')
        if attempts == 1:
            x = base.copy()
        elif len(valid) < population * 3 // 4:
            x = np.clip(
                base + rng.normal(0, .06, len(base)) * (bounds[:, 1] - bounds[:, 0]),
                bounds[:, 0], bounds[:, 1],
            )
        else:
            x = rng.uniform(bounds[:, 0], bounds[:, 1])
        d, resonators, canonical, _ = _canonical_candidate(x)
        if layout(d, resonators, cfg)[1] == 0:
            valid.append(canonical)
    pop = np.asarray(valid)
    for index, warm in enumerate(warm_starts or (), start=1):
        if index >= len(pop):
            break
        _d, _resonators, canonical, _key = _canonical_candidate(warm)
        if np.all(canonical >= bounds[:, 0]) and np.all(canonical <= bounds[:, 1]):
            pop[index] = canonical
    return pop


def dense_hybrid(x, topology, wiring, cfg, rs, rl, counters=None, *,
                 base_grid=None, passes=None, validation=False):
    f = validation_grid(cfg['spec'], cfg) if base_grid is None else np.unique(np.asarray(base_grid, dtype=float))
    passes = int(cfg.get('validation', {}).get('dense_refinement_passes',
                       cfg.get('dense_refinement_passes', 2))) if passes is None else int(passes)
    slope = float(cfg.get('dense_slope_threshold_db', .5))
    tolerance = float(cfg.get('validation', {}).get(
        'adaptive_frequency_tolerance_hz',
        cfg.get('adaptive_frequency_tolerance_hz', 1e3),
    ))

    d, resonators, _canonical, _key = _canonical_candidate(x)

    def point_evaluate(points):
        _result, net, y = response(
            x, topology, wiring, cfg, points, rs=rs, rl=rl,
            measure_result=False,
        )
        payload = dict(net)
        payload['y_parameters'] = y
        return payload

    cache = IncrementalFrequencyCache(point_evaluate)
    solved_seen = 0

    def cached_evaluate(points):
        nonlocal solved_seen
        payload = cache.evaluate(points)
        solved_delta = cache.solved_points - solved_seen
        solved_seen = cache.solved_points
        if counters is not None:
            counters.add_solved(solved_delta, validation=validation)
            counters.add_evaluation_time(cache.last_evaluation_wall_time_s, validation=True)
        net = {key: value for key, value in payload.items()
               if key not in ('frequencies_hz', 'y_parameters')}
        result = measure(points, net, d, cfg)
        result.update(
            design=asdict(d),
            resonators=[asdict(r) for r in resonators],
            layout=layout(d, resonators, cfg)[0],
            source_impedance_ohm=rs,
            load_impedance_ohm=rl,
        )
        return result, net, payload['y_parameters']

    for _ in range(max(0, passes)):
        _r, net, _y = cached_evaluate(f)
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


_dense_hybrid = dense_hybrid


def optimize_case(out, cfg, topology, wiring, seed, phase, iterations, parent=None,
                  rs=None, rl=None, warm_starts=None):
    rs, rl = _resolve_terminations(cfg, rs, rl)
    tag = f'{phase}__R{rs:g}_L{rl:g}__{topology}__{wiring}__{seed}'
    path = out / (tag + '.json')
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))

    count_res = len(TOPOLOGIES[topology][1])
    bounds = np.asarray(BOUNDS + RESONATOR_BOUNDS * count_res, dtype=float)
    ndim = len(bounds)
    population = scaled_population(
        cfg['population'], ndim,
        reference_dimensions=cfg.get('population_reference_dimensions', 7),
    )
    base = _initial_base(topology, parent)
    rng = np.random.default_rng(seed)
    search_f = search_grid(cfg['spec'], cfg)
    counters = EvaluationCounters()
    failures = 0
    started = time.time()
    current_best = None
    adaptive_rounds, adaptive_iterations, adaptive_tol_hz, adaptive_max_points = _adaptive_settings(cfg)
    if adaptive_iterations <= 0:
        adaptive_iterations = max(1, int(iterations) // 3)
    slope_threshold = float(cfg.get('dense_slope_threshold_db', .5))
    runtime = cfg.get('optimizer_runtime', {})
    checkpoint_path = out / (tag + '.checkpoint.json')
    warm_resume = bool(runtime.get('warm_resume', cfg.get('optimizer', {}).get('warm_resume', False)))
    resume_info = dict(used=False, non_exact_de_resume=True,
                       source=str(checkpoint_path.name) if checkpoint_path.exists() else None)
    checkpoint_best = None
    if warm_resume and checkpoint_path.exists():
        checkpoint_best = json.loads(checkpoint_path.read_text(encoding='utf-8')).get('best')
        if checkpoint_best and checkpoint_best.get('x'):
            base = np.asarray(checkpoint_best['x'], dtype=float)
            resume_info['used'] = True
    adaptive_candidates = []
    seen_decoded = set()
    history = _HistoryBuffer(out / (tag + '.jsonl'), runtime.get('history_flush_every', 100))
    try:
        for adaptive_round in range(adaptive_rounds + 1):
            cache = {}
            round_best = None
            round_iterations = iterations if adaptive_round == 0 else adaptive_iterations
            if current_best is not None:
                base = np.asarray(current_best['x'], dtype=float)
            starts = warm_starts if adaptive_round == 0 else None
            if checkpoint_best and adaptive_round == 0 and not starts:
                starts = [checkpoint_best['x']]
            valid = _build_population(base, bounds, topology, cfg, rng, population,
                                      warm_starts=starts)

            def objective(x):
                nonlocal round_best, failures
                counters.objective_calls += 1
                d, resonators, canonical, key = _canonical_candidate(x)
                if key in cache:
                    counters.cache_hits += 1
                    return cache[key]
                if key not in seen_decoded:
                    seen_decoded.add(key)
                    counters.unique_decoded_evaluations += 1
                try:
                    if layout(d, resonators, cfg)[1] > 0:
                        raise ValueError('Layout/manufacturing constraint violation')
                    evaluation_started = time.time()
                    try:
                        r, _, _ = response(canonical, topology, wiring, cfg, search_f, rs=rs, rl=rl)
                    finally:
                        counters.add_evaluation_time(time.time() - evaluation_started)
                    if not np.isfinite(r['objective']):
                        raise ValueError('Nonfinite objective')
                    counters.add_solved(len(search_f))
                    candidate = dict(r, x=canonical.tolist())
                    if round_best is None or r['objective'] < round_best['objective']:
                        round_best = candidate
                        save(checkpoint_path, dict(
                            adaptive_round=adaptive_round,
                            search_frequency_count=len(search_f),
                            objective_calls=counters.objective_calls,
                            unique_decoded_evaluations=counters.unique_decoded_evaluations,
                            cache_hits=counters.cache_hits,
                            solved_frequency_points=counters.solved_frequency_points,
                            best=round_best,
                        ))
                        history.flush()
                    row = dict(
                        evaluation=counters.unique_decoded_evaluations,
                        adaptive_round=adaptive_round,
                        objective=r['objective'],
                        max_violation=r['max_violation'],
                        x=canonical.tolist(),
                    )
                except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                    failures += 1
                    row = dict(
                        evaluation=counters.unique_decoded_evaluations,
                        adaptive_round=adaptive_round,
                        objective=1e15,
                        failure=str(exc),
                        x=canonical.tolist(),
                    )
                history.write(row)
                cache[key] = row['objective']
                return row['objective']

            callback = None
            early_stop = bool(runtime.get('production_early_stop', False))
            if cfg.get('run_mode') == 'benchmark' or cfg.get('convergence', {}).get('benchmark_early_stop') is False:
                early_stop = False
            if early_stop:
                minimum = int(runtime.get('min_generations_before_stop', 20))
                patience = int(runtime.get('patience_generations', 20))
                callback = PlateauStopper(
                    min_generations=minimum, patience_generations=patience,
                    improvement_abs=.02, improvement_rel=.02,
                    value_fn=objective,
                )

            differential_evolution(
                objective, bounds, init=valid, maxiter=round_iterations,
                seed=seed + adaptive_round, polish=False, tol=0, atol=0,
                workers=1, callback=callback,
            )
            if round_best is None:
                raise RuntimeError(f'No valid design: {tag}, adaptive round {adaptive_round}')
            current_best = round_best
            dense_f, (_dense_r, dense_net, _dense_y) = dense_hybrid(
                current_best['x'], topology, wiring, cfg, rs, rl, counters=counters,
            )
            critical = critical_frequencies(
                dense_f, dense_net, cfg['spec'], slope_threshold_db=slope_threshold,
                max_points=adaptive_max_points,
            )
            adaptive_candidates.append(dict(
                current_best, search_objective=current_best['objective'],
                adaptive_round=adaptive_round,
                dense_critical_frequencies=critical.tolist(),
            ))
            added = new_frequency_points(search_f, critical, adaptive_tol_hz)
            if adaptive_round >= adaptive_rounds or len(added) == 0:
                break
            search_f = np.unique(np.r_[search_f, added])
    finally:
        history.close()

    if not adaptive_candidates:
        raise RuntimeError(f'No valid design: {tag}')
    base_validation_f = validation_grid(cfg['spec'], cfg)
    common_f = common_validation_grid(
        base_validation_f,
        [candidate['dense_critical_frequencies'] for candidate in adaptive_candidates],
        adaptive_tol_hz,
    )
    validated = []
    for candidate in adaptive_candidates:
        f, (validation_result, net, y) = dense_hybrid(
            candidate['x'], topology, wiring, cfg, rs, rl, counters=counters,
            base_grid=common_f, passes=0, validation=True,
        )
        record = dict(validation_result)
        record.update(
            x=candidate['x'], topology=topology, wiring=wiring, seed=seed, phase=phase,
            rs=rs, rl=rl, search_objective=candidate['search_objective'],
            selected_adaptive_round=candidate['adaptive_round'],
            adaptive_round=candidate['adaptive_round'],
            dense_critical_frequencies=candidate['dense_critical_frequencies'],
        )
        if candidate['feasible'] and record['feasible']:
            record['validation_gap_primary'] = record['metrics']['worst_il_db'] - candidate['metrics']['worst_il_db']
        else:
            record['validation_gap_primary'] = record['max_violation'] - candidate['max_violation']
        validated.append((record, net, y, f))
    selected, net, y, f = min(validated, key=lambda item: rank(item[0]))
    search_best = min(adaptive_candidates, key=rank)
    selected.update(
        parent=parent.get('result_file') if parent else None,
        evaluations=counters.unique_decoded_evaluations,
        objective_calls=counters.objective_calls,
        unique_decoded_evaluations=counters.unique_decoded_evaluations,
        cache_hits=counters.cache_hits,
        solved_frequency_points=counters.solved_frequency_points,
        validation_solved_frequency_points=counters.validation_frequency_points,
        optimization_wall_time_s=counters.optimization_wall_time_s,
        validation_wall_time_s=counters.validation_wall_time_s,
        com_network_evaluation_wall_time_s=counters.com_network_evaluation_wall_time_s,
        history_io_time_s=history.io_time_s,
        failures=failures, elapsed_s=time.time() - started,
        search_best_objective=search_best['objective'],
        search_frequency_count=len(search_f), validation_frequency_count=len(common_f),
        common_validation_frequencies_hz=common_f.tolist(),
        adaptive_rounds_completed=adaptive_candidates[-1]['adaptive_round'],
        adaptive_candidate_count=len(adaptive_candidates), resume=resume_info,
        adaptive_candidates=[{
            'adaptive_round': candidate['adaptive_round'],
            'x': candidate['x'],
            'search_objective': candidate['search_objective'],
            'dense_critical_frequencies': candidate['dense_critical_frequencies'],
        } for candidate in adaptive_candidates],
        population=population, dimensions=ndim,
        response_file=tag + '.npz', result_file=tag + '.json',
    )
    np.savez_compressed(out / selected['response_file'], frequencies_hz=f, y=y, **net)
    save(path, selected)
    print(json.dumps(dict(
        phase=phase, topology=topology, wiring=wiring, seed=seed,
        rs=rs, rl=rl, il=selected['metrics']['worst_il_db'],
        violation=selected['max_violation'],
        adaptive_rounds=selected['adaptive_rounds_completed'],
    )), flush=True)
    return selected


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', default='configs/studies/hybrid_50ohm.yaml')
    p.add_argument('--run', default='runs/hybrid-study')
    p.add_argument('--rs', type=float)
    p.add_argument('--rl', type=float)
    p.add_argument('--report-only', action='store_true')
    args = p.parse_args()
    out = Path(args.run)
    if args.report_only:
        from ..reporting.hybrid_report import report
        print(report(out))
        return

    path = Path(args.config)
    study = yaml.safe_load(path.read_text(encoding='utf-8'))
    base = path.parent / study['base_config']
    cfg = yaml.safe_load(base.read_text(encoding='utf-8'))
    cfg.update(study)
    com = base.parent / cfg['com_file']
    cfg['com'] = yaml.safe_load(com.read_text(encoding='utf-8'))
    cfg['inputs'] = {p.name: p.read_text(encoding='utf-8') for p in [path, base, com]}
    rs, rl = _resolve_terminations(cfg, args.rs, args.rl)
    cfg['source_impedance_ohm'] = rs
    cfg['load_impedance_ohm'] = rl
    cfg['resistances'] = [rs]
    cfg['study_type'] = 'hybrid_impedance'
    out = initialize(out, cfg)

    # Stage 2A keeps the historical staged topology selection for backwards
    # compatibility. CODEX_STAGE2_TASK.md requires Stage 2B to replace this
    # early single-wiring pruning with all-combination low-budget screening.
    baseline = []
    for wiring in cfg['wirings']:
        baseline.extend(
            optimize_case(out, cfg, 'D', wiring, seed, 'baseline', cfg['baseline_iterations'], rs=rs, rl=rl)
            for seed in cfg['seeds']
        )
    parent = min(baseline, key=rank)
    wiring = parent['wiring']
    save(out / 'selection.json', dict(
        wiring=wiring,
        baseline_parent=parent['result_file'],
        reason='Stage 2A compatibility path: best dense-grid D-only wiring; Stage 2B must screen topology x wiring jointly.',
    ))

    candidates = []
    for topology in TOPOLOGIES:
        if topology == 'D':
            continue
        cases = [
            optimize_case(out, cfg, topology, wiring, seed, 'screen', cfg['screen_iterations'], parent, rs, rl)
            for seed in cfg['seeds']
        ]
        candidates.append(min(cases, key=rank))

    chosen = [parent] + sorted(candidates, key=rank)[:cfg['refine_top']]
    save(out / 'refinement_selection.json', [r['result_file'] for r in chosen])
    for candidate in chosen:
        for seed in cfg['seeds']:
            optimize_case(
                out, cfg, candidate['topology'], candidate['wiring'], seed,
                'refine', cfg['refine_iterations'], candidate, rs, rl,
            )
    from ..reporting.hybrid_report import report
    print(json.dumps({'report': report(out)}), flush=True)


if __name__ == '__main__':
    main()
