"""Hybrid DMS and resonator optimization with impedance and adaptive-grid support."""
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
    p.add_argument('--config')
    p.add_argument('--run')
    p.add_argument('--rs', type=float)
    p.add_argument('--rl', type=float)
    p.add_argument('--report-only', action='store_true')
    p.add_argument('--stage4a-validate', action='store_true',
                   help='run current-architecture Stage 4A implementation validation only')
    p.add_argument('--stage4a-smoke', action='store_true',
                   help='run Stage 4A smoke after a passing implementation validation')
    args = p.parse_args()
    if args.stage4a_validate and args.stage4a_smoke:
        p.error('--stage4a-validate and --stage4a-smoke are mutually exclusive')
    if args.stage4a_validate or args.stage4a_smoke:
        config_path = args.config or 'configs/studies/hybrid_stage4a_qualification.yaml'
        run_path = args.run or 'runs/stage4a-hybrid-protocol-qualification'
        if args.stage4a_validate:
            result = run_stage4a_implementation_validation(config_path, run_path)
        else:
            result = run_stage4a_smoke(config_path, run_path)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), flush=True)
        if result.get('status') not in {'PASS', 'STAGE4A_SMOKE_COMPLETE'}:
            raise SystemExit(2)
        return
    config = args.config or 'configs/studies/hybrid_50ohm.yaml'
    run = args.run or 'runs/hybrid-study'
    out = Path(run)
    if args.report_only:
        from ..reporting.hybrid_report import report
        print(report(out))
        return

    path = Path(config)
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
    out = initialize(Path(run), cfg)

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


def _stage4a_clean(value):
    """Convert NumPy/container values to strict JSON-compatible data."""
    if isinstance(value, np.ndarray):
        return [_stage4a_clean(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _stage4a_clean(value.item())
    if isinstance(value, dict):
        return {str(key): _stage4a_clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stage4a_clean(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _stage4a_write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_stage4a_clean(value), ensure_ascii=False,
                               indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _stage4a_git_state(root):
    import subprocess

    def run(*args):
        result = subprocess.run(["git", *args], cwd=root, capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
        return result.stdout.strip()
    return {
        "branch": run("branch", "--show-current"),
        "head": run("rev-parse", "HEAD"),
        "status_short": run("status", "--short"),
    }


def _stage4a_dependency_paths(config_path, cfg, grid_metadata):
    root = Path(__file__).resolve().parents[3]
    paths = [
        "configs/studies/hybrid_stage4a_qualification.yaml",
        "configs/studies/stage3_9b_mlit_t1_50ohm_overlap_parity.yaml",
        "configs/studies/dms_topology_screening.yaml",
        "configs/base/b28_dms_baseline.yaml",
        "src/sawopt/problem/hybrid.py",
        "src/sawopt/problem/dms_topologies.py",
        "src/sawopt/core/hybrid.py",
        "src/sawopt/core/topology.py",
        "src/sawopt/core/com.py",
        "src/sawopt/core/models.py",
        "src/sawopt/core/metrics.py",
        "src/sawopt/core/network.py",
        "src/sawopt/core/literature_com.py",
        "src/sawopt/studies/hybrid.py",
        "src/sawopt/studies/dms_topology_common.py",
        "src/sawopt/studies/dms_topology_screening.py",
        "src/sawopt/optimizers/lshade.py",
        "src/sawopt/optimizers/selection.py",
        "src/sawopt/optimizers/checkpoint_session.py",
        "src/sawopt/optimization/counters.py",
        "src/sawopt/io/config.py",
        "src/sawopt/io/provenance.py",
        "src/sawopt/io/checkpoints.py",
        "src/sawopt/io/lifecycle.py",
    ]
    profile = cfg["dms_topology"]["materials"]["MLIT"]["profile_file"]
    paths.append(str(profile).replace("\\", "/"))
    grid_path = Path(grid_metadata["source"])
    if not grid_path.is_absolute():
        grid_path = root / grid_path
    paths.append(grid_path.resolve().relative_to(root).as_posix())
    grid_meta = Path(cfg["dms_topology"]["common_validation_grid_metadata"])
    paths.append(grid_meta.as_posix())
    # Preserve the exact invoked study wrapper if a caller uses a copied config.
    try:
        config_relative = Path(config_path).resolve().relative_to(root).as_posix()
        if config_relative not in paths:
            paths.append(config_relative)
    except ValueError:
        pass
    return tuple(dict.fromkeys(paths))


def _stage4a_load_context(config_path):
    import hashlib
    from ..core.hybrid import RESONATOR_BOUNDS
    from ..core.metrics import search_grid
    from ..io.config import load_experiment_config
    from ..problem.hybrid import HYBRID_TOPOLOGIES, HybridDesignSpace
    from ..problem.dms_topologies import T1
    from ..studies.dms_topology_common import load_common_validation_grid, provider_for_material
    from ..studies.dms_topology_screening import material_bounds

    root = Path(__file__).resolve().parents[3]
    config_path = Path(config_path)
    if not config_path.is_absolute():
        config_path = root / config_path
    cfg = load_experiment_config(config_path)
    settings = cfg["dms_topology"]
    hybrid = cfg["hybrid"]
    if tuple(hybrid.get("supported_topologies", ())) != HYBRID_TOPOLOGIES:
        raise ValueError("Stage 4A must support exactly D, P_D, D_P, and P_D_P in that order")
    if tuple(settings.get("selection", {}).get("materials", ())) != ("MLIT",):
        raise ValueError("Stage 4A material contract must select only MLIT")
    if tuple(settings.get("selection", {}).get("topologies", ())) != (T1,):
        raise ValueError("Stage 4A DMS contract must select current T1_SYMMETRIC_5IDT")
    if float(settings.get("impedance_ohm", 0.0)) != 50.0:
        raise ValueError("Stage 4A inherits the fixed 50-ohm Stage 3.9 DMS reference")
    rs = float(hybrid.get("source_impedance_ohm", 50.0))
    rl = float(hybrid.get("load_impedance_ohm", 50.0))
    if rs != 50.0 or rl != 50.0:
        raise ValueError("Stage 4A qualification is fixed at 50/50 ohm")
    if bool(settings.get("cold_start")) is not True:
        raise ValueError("Stage 4A requires cold_start=true")
    if bool(hybrid.get("production_launch_authorized")):
        raise ValueError("Stage 4A configuration must prohibit production launch")
    resonator_bounds = np.asarray(hybrid.get("resonator_bounds", RESONATOR_BOUNDS), dtype=float)
    if not np.array_equal(resonator_bounds, np.asarray(RESONATOR_BOUNDS, dtype=float)):
        raise ValueError("Stage 4A resonator bounds must preserve the existing one-port model bounds")
    mlit_aperture = np.asarray(settings["materials"]["MLIT"]["aperture_bounds_um"], dtype=float)
    resonator_aperture = np.asarray(hybrid["resonator_aperture_bounds_um"], dtype=float)
    if (resonator_aperture.shape != (2,) or np.any(resonator_aperture < mlit_aperture[0])
            or np.any(resonator_aperture > mlit_aperture[1])
            or resonator_aperture[1] <= resonator_aperture[0]):
        raise ValueError("resonator aperture bounds must be ordered within the MLIT aperture contract")
    dms_active, dms_hard, _ = material_bounds(cfg, "MLIT", T1)
    spaces = {
        topology: HybridDesignSpace.from_contract(
            topology, dms_active, dms_hard, resonator_bounds,
        ) for topology in HYBRID_TOPOLOGIES
    }
    provider, profile_metadata = provider_for_material("MLIT", cfg)
    search_frequencies = np.unique(search_grid(cfg["spec"], cfg))
    common_frequencies, common_grid_id, common_meta_path, grid_metadata = load_common_validation_grid(cfg)
    grid_metadata = dict(grid_metadata)
    grid_metadata["metadata_path"] = common_meta_path
    paths = _stage4a_dependency_paths(config_path, cfg, grid_metadata)
    from ..io.provenance import build_fingerprint_metadata
    computation_paths = paths
    reporting_paths = (
        "src/sawopt/reporting/review_bundle.py",
        "src/sawopt/reporting/hybrid_qualification.py",
    )
    contract = {
        "study_type": cfg.get("study", {}).get("type"),
        "study_revision": cfg.get("study", {}).get("revision"),
        "material": "MLIT",
        "material_profile_metadata": profile_metadata,
        "dms_topology": T1,
        "dms_active_bounds": dms_active.tolist(),
        "dms_hard_bounds": dms_hard.tolist(),
        "resonator_bounds": resonator_bounds.tolist(),
        "resonator_aperture_bounds_um": resonator_aperture.tolist(),
        "topologies": list(HYBRID_TOPOLOGIES),
        "source_impedance_ohm": rs,
        "load_impedance_ohm": rl,
        "specification": cfg["spec"],
        "geometry_constraints": cfg["constraints"],
        "search_frequency_count": int(len(search_frequencies)),
        "search_frequency_sha256": hashlib.sha256(
            np.asarray(search_frequencies, dtype="<f8").tobytes()
        ).hexdigest(),
        "common_validation_grid_id": common_grid_id,
        "common_validation_frequency_count": int(len(common_frequencies)),
        "common_validation_grid_sha256": grid_metadata["sha256"],
        "budget": int(settings["budget"]),
        "checkpoints": [int(value) for value in settings["checkpoints"]],
        "seed": int(settings["seeds"][0]),
        "lshade": hybrid.get("lshade", settings.get("lshade", {})),
        "cold_start": True,
        "production_launch_authorized": False,
    }
    fingerprint = build_fingerprint_metadata(
        root, contract, computation_paths=computation_paths,
        reporting_paths=reporting_paths,
    )
    return {
        "root": root, "config_path": config_path, "cfg": cfg,
        "spaces": spaces, "provider": provider, "profile_metadata": profile_metadata,
        "search_frequencies": search_frequencies,
        "common_frequencies": common_frequencies,
        "common_grid_id": common_grid_id, "grid_metadata": grid_metadata,
        "contract": contract, "fingerprint": fingerprint,
        "computation_paths": computation_paths, "reporting_paths": reporting_paths,
        "source_impedance_ohm": rs, "load_impedance_ohm": rl,
    }


def _stage4a_y(candidate, provider, frequencies):
    from ..core.hybrid import compose_stage4a_y, resonator_y
    from ..problem.dms_topologies import T1, simulate_topology

    dms_simulation = simulate_topology(candidate.dms_design, provider, frequencies, T1)
    resonator_ys = [resonator_y(design, provider, frequencies)
                    for design in candidate.resonator_designs]
    y = compose_stage4a_y(dms_simulation.y_parameters, candidate.topology, resonator_ys)
    return y, dms_simulation.diagnostics


def _stage4a_evaluate(candidate, provider, cfg, frequencies, rs, rl, *, include_spectrum=False):
    import math
    from ..core.metrics import measure
    from ..core.network import evaluate
    from ..problem.hybrid import hybrid_geometry

    layout = hybrid_geometry(candidate, cfg)
    gviolations = {
        **{f"dms_{key}": value for key, value in layout["dms"]["violations"].items()},
        **layout["resonator_violations"],
        **{f"combined_{key}": value for key, value in layout["combined"]["violations"].items()},
    }
    if layout["max_violation"] > 0.0:
        return {
            "evaluation_status": "GEOMETRY_REJECTED", "failure_stage": "hard_geometry_gate",
            "geometry_valid": False, "geometry_dimensions": layout,
            "geometry_violations": gviolations,
            "geometry_max_violation": float(layout["max_violation"]),
            "metrics": {}, "violations": {}, "filter_metrics_available": False,
            "feasible": False, "max_violation": None, "sum_violation": None,
            "objective": None, "search_scalar_objective": None,
            "dms_design": asdict(candidate.dms_design),
            "resonator_designs": [asdict(value) for value in candidate.resonator_designs],
            "candidate_vector": list(candidate.vector), "topology": candidate.topology,
        }
    try:
        y, dms_diagnostics = _stage4a_y(candidate, provider, frequencies)
        network = evaluate(y, rs, rl)
        gain = np.asarray(network["gt"], dtype=float)
        if not np.isfinite(gain).all():
            raise ValueError("non-finite transducer power gain")
        if gain.max(initial=0.0) > 1.0 + 1e-7:
            raise ValueError("Nonpassive power gain")
        raw = dict(measure(np.asarray(frequencies), network, candidate.dms_design, cfg))
        violations = {str(key): float(value) for key, value in raw.get("violations", {}).items()
                      if key != "geometry"}
        metrics = dict(raw.get("metrics", {}))
        for key in ("length_um", "width_um", "electrodes"):
            metrics.pop(key, None)
        result = {
            "evaluation_status": "PHYSICS_EVALUATED", "failure_stage": None,
            "geometry_valid": True, "geometry_dimensions": layout,
            "geometry_violations": gviolations, "geometry_max_violation": 0.0,
            "metrics": metrics, "violations": violations,
            "filter_metrics_available": True,
            "filter_feasible": max(violations.values(), default=math.inf) <= 1e-10,
            "feasible": max(violations.values(), default=math.inf) <= 1e-10,
            "max_violation": max(violations.values(), default=math.inf),
            "sum_violation": sum(violations.values()),
            "objective": float(raw["objective"]),
            "search_scalar_objective": float(raw["objective"]),
            "objective_parts": raw.get("objective_parts", {}),
            "dms_design": asdict(candidate.dms_design),
            "resonator_designs": [asdict(value) for value in candidate.resonator_designs],
            "candidate_vector": list(candidate.vector), "topology": candidate.topology,
            "source_impedance_ohm": float(rs), "load_impedance_ohm": float(rl),
            "dms_diagnostics": dms_diagnostics,
        }
        if include_spectrum:
            scattering = np.asarray(network["s"])
            with np.errstate(divide="ignore", invalid="ignore"):
                result["spectrum"] = {
                    "frequency_hz": np.asarray(frequencies, dtype=float).tolist(),
                    "s11_db": (20 * np.log10(np.maximum(np.abs(scattering[:, 0, 0]), 1e-300))).tolist(),
                    "s21_db": (20 * np.log10(np.maximum(np.abs(scattering[:, 1, 0]), 1e-300))).tolist(),
                }
        finite_metrics = [float(value) for metric in metrics.values()
                          for value in (metric if isinstance(metric, (list, tuple, np.ndarray)) else [metric])]
        if (not finite_metrics or not np.isfinite(finite_metrics).all()
                or not np.isfinite(list(violations.values())).all()
                or not math.isfinite(float(result["objective"]))):
            raise ValueError("non-finite or incomplete hybrid metrics")
        return result
    except (ValueError, np.linalg.LinAlgError, FloatingPointError, OverflowError) as exc:
        return {
            "evaluation_status": "PHYSICS_FAILED", "failure_stage": "com_network_or_metrics",
            "failure": f"{type(exc).__name__}: {exc}", "geometry_valid": True,
            "geometry_dimensions": layout, "geometry_violations": gviolations,
            "geometry_max_violation": 0.0, "metrics": {}, "violations": {},
            "filter_metrics_available": False, "feasible": False,
            "max_violation": None, "sum_violation": None, "objective": None,
            "search_scalar_objective": None,
            "dms_design": asdict(candidate.dms_design),
            "resonator_designs": [asdict(value) for value in candidate.resonator_designs],
            "candidate_vector": list(candidate.vector), "topology": candidate.topology,
        }


def _stage4a_assert_close(name, left, right, *, rtol=1e-10, atol=1e-12):
    left_array, right_array = np.asarray(left), np.asarray(right)
    np.testing.assert_allclose(left_array, right_array, rtol=rtol, atol=atol,
                               err_msg=f"Stage 4A D-only parity failure: {name}")
    difference = np.abs(left_array - right_array)
    return float(np.max(difference, initial=0.0))


def _stage4a_d_only_parity(context):
    from dataclasses import asdict
    from ..core.network import evaluate
    from ..problem.dms_topologies import T1, simulate_topology
    from ..studies.dms_topology_common import decode_design
    from ..studies.dms_topology_screening import evaluate_dms_design

    cfg = context["cfg"]
    space = context["spaces"]["D"]
    dms_active = context["contract"]["dms_active_bounds"]
    # Stage 3.9's current MLIT/T1 fixed design is inside the active contract.
    vector = np.mean(np.asarray(dms_active, dtype=float), axis=1)
    for index in (4, 5, 6):
        vector[index] = np.floor(vector[index] + 0.5)
    current_design = decode_design(vector, T1, cfg)
    hybrid_candidate = space.decode(vector)
    if asdict(current_design) != asdict(hybrid_candidate.dms_design):
        raise AssertionError("hybrid D-only vector does not decode identically to current DMS T1")
    tolerances = cfg["hybrid"]["parity"]
    rtol, atol = float(tolerances["rtol"]), float(tolerances["atol"])
    details = {"status": "PASS", "dms_design_vector": vector.tolist(),
               "decoded_dms_design": asdict(current_design), "rtol": rtol, "atol": atol,
               "grids": {}, "maximum_absolute_differences": {}}
    for grid_name, frequencies in (
        ("search", context["search_frequencies"]),
        ("common", context["common_frequencies"]),
    ):
        dms_simulation = simulate_topology(current_design, context["provider"], frequencies, T1)
        current_network = evaluate(dms_simulation.y_parameters,
                                  context["source_impedance_ohm"],
                                  context["load_impedance_ohm"])
        hybrid_y, _diagnostics = _stage4a_y(hybrid_candidate, context["provider"], frequencies)
        hybrid_network = evaluate(hybrid_y, context["source_impedance_ohm"],
                                  context["load_impedance_ohm"])
        differences = {}
        differences["y_parameters"] = _stage4a_assert_close(
            "Y parameters", dms_simulation.y_parameters, hybrid_y, rtol=rtol, atol=atol,
        )
        for key in ("s", "gt", "il", "vswr"):
            differences[key] = _stage4a_assert_close(
                f"network {key}", current_network[key], hybrid_network[key], rtol=rtol, atol=atol,
            )
        current_record = evaluate_dms_design(
            current_design, context["provider"], cfg, frequencies, T1,
            rs=context["source_impedance_ohm"], rl=context["load_impedance_ohm"],
        )
        hybrid_record = _stage4a_evaluate(
            hybrid_candidate, context["provider"], cfg, frequencies,
            context["source_impedance_ohm"], context["load_impedance_ohm"],
        )
        for key in ("evaluation_status", "feasible"):
            if current_record[key] != hybrid_record[key]:
                raise AssertionError(f"D-only parity failure: {key}: {current_record[key]} != {hybrid_record[key]}")
        for key in ("max_violation", "sum_violation", "objective"):
            differences[key] = _stage4a_assert_close(
                key, current_record[key], hybrid_record[key], rtol=rtol, atol=atol,
            )
        for key in sorted(current_record["metrics"]):
            differences[f"metric.{key}"] = _stage4a_assert_close(
                f"metric.{key}", current_record["metrics"][key],
                hybrid_record["metrics"][key], rtol=rtol, atol=atol,
            )
        for key in sorted(current_record["violations"]):
            differences[f"violation.{key}"] = _stage4a_assert_close(
                f"violation.{key}", current_record["violations"][key],
                hybrid_record["violations"][key], rtol=rtol, atol=atol,
            )
        details["grids"][grid_name] = {"frequency_count": int(len(frequencies))}
        details["maximum_absolute_differences"][grid_name] = differences
    details["overall_maximum_absolute_difference"] = max(
        (value for grid in details["maximum_absolute_differences"].values()
         for value in grid.values()), default=0.0,
    )
    details["parity_fields"] = [
        "Y parameters", "S parameters", "transducer gain", "insertion loss", "VSWR",
        "stopband attenuation", "worst IL", "ripple", "max violation", "sum violation",
        "feasible flag", "scalar search objective",
    ]
    return details


def _stage4a_structural_validation(context):
    from ..core.hybrid import resonator_y
    from ..problem.hybrid import assumptions, hybrid_geometry
    from ..problem.dms_topologies import T1, simulate_topology

    checks = {"topologies": {}, "resonator_model_assumptions": assumptions()}
    frequencies = context["search_frequencies"]
    # A short deterministic subset is sufficient for structure/passivity checks;
    # full search and common grids are covered by D-only parity and smoke.
    sample = frequencies[np.unique(np.linspace(0, len(frequencies) - 1,
                                               min(9, len(frequencies))).astype(int))]
    for topology, space in context["spaces"].items():
        vector = np.mean(space.bounds, axis=1)
        # Two resonators at the bounds midpoint exceed the unchanged 500-
        # electrode combined-layout limit. Use a representative in-bounds
        # count that allows all four topologies to exercise valid structures.
        for start in range(11, space.dimension, 3):
            vector[start] = 20
        candidate = space.decode(vector)
        layout = hybrid_geometry(candidate, context["cfg"])
        if layout["max_violation"] > 0:
            raise AssertionError(f"structural midpoint is not layout-valid for {topology}")
        y, _diagnostics = _stage4a_y(candidate, context["provider"], sample)
        dms_y = simulate_topology(candidate.dms_design, context["provider"], sample, T1).y_parameters
        if topology == "D" and not np.array_equal(y, dms_y):
            raise AssertionError("D topology must be the exact zero-resonator identity")
        conductance = (y + np.swapaxes(y.conj(), 1, 2)) / 2.0
        minimum_eigenvalue = float(np.linalg.eigvalsh(conductance).min())
        reciprocity_error = float(np.max(np.abs(y - np.swapaxes(y, 1, 2)), initial=0.0))
        network = __import__("sawopt.core.network", fromlist=["evaluate"]).evaluate(
            y, context["source_impedance_ohm"], context["load_impedance_ohm"],
        )
        if minimum_eigenvalue < -1e-8 or float(np.max(network["gt"])) > 1.0 + 1e-7:
            raise AssertionError(f"nonpassive hybrid network for structurally valid {topology}")
        if reciprocity_error > 1e-8:
            raise AssertionError(f"hybrid network reciprocity failure for {topology}")
        resonator_checks = []
        for resonator in candidate.resonator_designs:
            one_port = resonator_y(resonator, context["provider"], sample)
            minimum_conductance = float(np.min(np.real(one_port)))
            if minimum_conductance < -1e-8 or not np.isfinite(one_port).all():
                raise AssertionError(f"invalid resonator admittance for {topology}")
            resonator_checks.append({"finite": True, "minimum_conductance_s": minimum_conductance})
        checks["topologies"][topology] = {
            "dimension": space.dimension, "resonator_count": len(candidate.resonator_designs),
            "zero_resonator_identity": (
                bool(np.array_equal(y, dms_y)) if topology == "D" else None
            ),
            "layout_max_violation": layout["max_violation"],
            "minimum_conductance_eigenvalue_s": minimum_eigenvalue,
            "reciprocity_error": reciprocity_error,
            "passive": True, "reciprocal": True,
            "resonators": resonator_checks,
        }
    return checks


def run_stage4a_implementation_validation(config_path, run_path):
    """Run the fail-closed Stage 4A contract, parity, and structural gate."""
    import shutil
    from ..problem.hybrid import HYBRID_TOPOLOGIES
    from ..optimizers.lshade import LShadeBackend
    from ..optimizers.selection import GeometryFirstComparator
    from ..optimization.counters import GeometryGateCounters
    from ..core.hybrid import RESONATOR_BOUNDS
    from ..problem.dms_topologies import T1

    context = _stage4a_load_context(config_path)
    run = Path(run_path)
    if not run.is_absolute():
        run = context["root"] / run
    run.mkdir(parents=True, exist_ok=True)
    (run / "metadata").mkdir(exist_ok=True)
    raw_config = context["config_path"].read_text(encoding="utf-8")
    (run / "config_snapshot.yaml").write_text(raw_config, encoding="utf-8")
    _stage4a_write_json(run / "metadata" / "resolved_contract.json", context["contract"])
    _stage4a_write_json(run / "metadata" / "computation_fingerprint.json", context["fingerprint"])
    _stage4a_write_json(run / "metadata" / "run_source_metadata.json", {
        "study_type": "hybrid_stage4a_qualification",
        "git": _stage4a_git_state(context["root"]),
        "fingerprint_schema_version": context["fingerprint"]["fingerprint_schema_version"],
        "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
        "reporting_fingerprint": context["fingerprint"]["reporting_fingerprint"],
        "common_validation_grid_id": context["common_grid_id"],
        "common_validation_frequency_count": int(len(context["common_frequencies"])),
        "production_launch_authorized": False,
        "cold_start": True,
    })
    checks = {
        "status": "PASS",
        "dms_contract": {"material": "MLIT", "dms_topology": T1,
                          "source_impedance_ohm": context["source_impedance_ohm"],
                          "load_impedance_ohm": context["load_impedance_ohm"],
                          "t1_bounds_from_current_contract": context["contract"]["dms_active_bounds"]},
        "supported_topologies": list(HYBRID_TOPOLOGIES),
        "d_only_parity": _stage4a_d_only_parity(context),
        "hybrid_structure": _stage4a_structural_validation(context),
        "optimizer_selection": {
            "backend": LShadeBackend.name,
            "backend_class": LShadeBackend.__name__,
            "comparator": GeometryFirstComparator.__name__,
            "scipy_differential_evolution_used": False,
        },
        "accounting_contract": {
            "unique_budget_unit": "unique decoded canonical designs",
            "counter_type": GeometryGateCounters.__name__,
            "identities": [
                "unique = geometry_rejections + geometry_valid_candidates",
                "geometry_valid_candidates = valid_physics_evaluations + physics_failures",
                "physics_attempted_evaluations = valid_physics_evaluations + physics_failures",
            ],
            "canonical_integer_indices": {
                topology: list(space.integer_indices)
                for topology, space in context["spaces"].items()
            },
            "resonator_bounds": np.asarray(
                context["cfg"]["hybrid"]["resonator_bounds"], dtype=float,
            ).tolist(),
            "model_bounds_match_existing": np.array_equal(
                np.asarray(context["cfg"]["hybrid"]["resonator_bounds"], dtype=float),
                np.asarray(RESONATOR_BOUNDS, dtype=float),
            ),
        },
        "validation_grid_contract": {
            "search_frequency_count": int(len(context["search_frequencies"])),
            "search_frequency_sha256": context["contract"]["search_frequency_sha256"],
            "common_validation_grid_id": context["common_grid_id"],
            "common_validation_frequency_count": int(len(context["common_frequencies"])),
            "same_common_grid_for_all_topologies": True,
            "required_stopbands_mhz": [[703.0, 748.0], [832.0, 862.0]],
            "configured_stopbands": context["cfg"]["spec"]["stopbands"],
        },
        "provenance_status": {
            "schema_version": context["fingerprint"]["fingerprint_schema_version"],
            "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
            "reporting_fingerprint": context["fingerprint"]["reporting_fingerprint"],
            "computation_dependencies": context["fingerprint"]["dependency_manifest"]["computation"],
            "reporting_dependencies": context["fingerprint"]["dependency_manifest"]["reporting"],
        },
        "checkpoint_lifecycle": {
            "session": "LShadeCheckpointSession",
            "disposition_after_success": "REVIEW_WAITING",
            "execution_failure_disposition": "FAILED",
        },
        "layout_contract": {
            "dms_geometry": "current core.metrics.geometry on T1",
            "resonator_geometry": "bounds/features/count from existing one-port model",
            "combined_layout": context["cfg"]["hybrid"]["layout"],
            "model_status": "hypothetical separate rows; qualification only",
        },
    }
    _stage4a_write_json(run / "metadata" / "d_only_parity.json", checks["d_only_parity"])
    _stage4a_write_json(run / "metadata" / "implementation_validation.json", checks)
    return checks


def _stage4a_sample_population(space, cfg, seed, topology, population_size, max_attempts):
    import hashlib
    from ..problem.hybrid import hybrid_geometry

    payload = f"stage4a-v1/{int(seed)}/MLIT/{topology}/initial_population"
    sampling_seed = int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big") % (2**32)
    rng = np.random.default_rng(sampling_seed)
    low, high = space.bounds[:, 0], space.bounds[:, 1]
    accepted, seen = [], set()
    rejection_count, duplicate_count, draws = 0, 0, 0
    while len(accepted) < population_size and draws < max_attempts:
        draws += 1
        proposal = rng.uniform(low, high)
        canonical, key = space.canonicalize(proposal)
        if key in seen:
            duplicate_count += 1
            continue
        candidate = space.decode(canonical)
        layout = hybrid_geometry(candidate, cfg)
        if layout["max_violation"] > 0.0:
            rejection_count += 1
            continue
        seen.add(key)
        accepted.append((canonical - low) / (high - low))
    stats = {
        "method": "independent_uniform_rejection_v1",
        "seed": int(seed), "topology": topology,
        "initial_sampling_seed": sampling_seed,
        "requested_population_size": int(population_size),
        "accepted_population_size": int(len(accepted)),
        "candidate_draws": int(draws),
        "geometry_rejections": int(rejection_count),
        "duplicate_rejections": int(duplicate_count),
        "historical_seed_count": 0,
        "parent_transfer": False,
        "warm_start": False,
    }
    if draws != len(accepted) + rejection_count + duplicate_count:
        raise AssertionError("Stage 4A initializer accounting identity failed")
    if len(accepted) != population_size:
        raise RuntimeError("Stage 4A initializer exhausted its configured rejection cap")
    return np.asarray(accepted, dtype=float), stats


def _stage4a_counter_snapshot(counters, backend, frequency_count):
    unique = int(backend.unique_evaluations)
    if unique != counters.geometry_rejections + counters.geometry_valid_candidates:
        raise AssertionError("unique evaluation partition failed")
    if counters.geometry_valid_candidates != counters.valid_physics_evaluations + counters.physics_failures:
        raise AssertionError("geometry-valid physics partition failed")
    if counters.physics_attempted_evaluations != counters.valid_physics_evaluations + counters.physics_failures:
        raise AssertionError("physics-attempt counter partition failed")
    if counters.search_frequency_points != counters.valid_physics_evaluations * int(frequency_count):
        raise AssertionError("search frequency-point accounting failed")
    summary = backend.summary()
    return {
        "unique_decoded_evaluations": unique,
        "geometry_rejections": counters.geometry_rejections,
        "geometry_valid_candidates": counters.geometry_valid_candidates,
        "physics_attempted_evaluations": counters.physics_attempted_evaluations,
        "valid_physics_evaluations": counters.valid_physics_evaluations,
        "physics_failures": counters.physics_failures,
        "search_frequency_points": counters.search_frequency_points,
        "cache_hits": int(summary["cache_hits"]),
        "objective_proposals": int(summary["proposals_total"]),
        "duplicate_proposals": int(summary["duplicate_count"]),
        "raw_offspring_count": int(summary["raw_offspring_count"]),
        "generations": int(summary["generations"]),
        "population_size": int(summary["population_size"]),
        "initial_population": int(summary["initial_population"]),
        "population_schedule_identifier": summary["population_schedule_identifier"],
        "population_schedule_terminal_budget": int(summary["population_schedule_terminal_budget"]),
        "m_f": summary["m_f"], "m_cr": summary["m_cr"],
    }


def _stage4a_active_bound_diagnostics(vector, bounds):
    names = (
        "wavelength_A_um", "wavelength_B_um", "wavelength_C_um",
        "reflector_wavelength_um", "pairs_A", "pairs_B", "pairs_C",
        "common_idt_gap_lambda", "reflector_gap_lambda", "dms_aperture_um",
    )
    resonator_names = ("wavelength_um", "pairs", "aperture_um")
    rows = []
    for index, (value, (low, high)) in enumerate(zip(vector, bounds)):
        if index < 10:
            name = names[index]
        else:
            local = (index - 10) % 3
            resonator_index = (index - 10) // 3
            name = f"resonator_{resonator_index}_{resonator_names[local]}"
        rows.append({
            "variable": name, "value": float(value),
            "lower_bound": float(low), "upper_bound": float(high),
            "at_lower_bound": abs(float(value) - float(low)) <= 1e-9,
            "at_upper_bound": abs(float(value) - float(high)) <= 1e-9,
        })
    return rows


def _stage4a_estimate_stage4b(topologies, *, finalist_count=16):
    """Scale measured smoke throughput with an explicit finalist-grid workload."""
    cells_per_topology = 2
    target_evaluations = 4000
    search_seconds = 0.0
    validation_seconds = 0.0
    per_topology = {}
    for row in topologies:
        unique = max(int(row["unique_evaluations"]), 1)
        measured_search_wall = max(float(row["wall_time_s"]) - float(row["validation_time_s"]), 0.0)
        seconds_per_unique = measured_search_wall / unique
        search_seconds += cells_per_topology * target_evaluations * seconds_per_unique
        candidates = max(int(row.get("common_grid_finalists_validated", 0)), 1)
        seconds_per_finalist = float(row["validation_time_s"]) / candidates
        validation_seconds += cells_per_topology * finalist_count * seconds_per_finalist
        per_topology[row["topology"]] = {
            "observed_wall_seconds_per_unique_evaluation": seconds_per_unique,
            "observed_validation_seconds_per_finalist": seconds_per_finalist,
            "projected_search_hours": cells_per_topology * target_evaluations * seconds_per_unique / 3600.0,
            "projected_validation_hours": cells_per_topology * finalist_count * seconds_per_finalist / 3600.0,
        }
    central = search_seconds + validation_seconds
    return {
        "target": "4 topologies x 2 seeds x 4000 unique evaluations",
        "assumed_common_grid_finalists_per_cell": int(finalist_count),
        "common_validation_frequency_count": int(topologies[0]["common_validation_frequency_count"]),
        "central_seconds": float(central), "central_hours": float(central / 3600.0),
        "low_hours": float(central * 0.75 / 3600.0),
        "high_hours": float(central * 1.50 / 3600.0),
        "uncertainty_multiplier_range": [0.75, 1.50],
        "components": {
            "search_seconds": float(search_seconds),
            "common_validation_seconds": float(validation_seconds),
        },
        "per_topology": per_topology,
        "stage4b_launched": False,
    }


def run_stage4a_smoke(config_path, run_path):
    """Run the deterministic 256-unique-evaluation protocol smoke for four topologies."""
    import math
    import time
    from ..io.checkpoints import complete_study_run
    from ..io.lifecycle import RunDisposition
    from ..optimizers.checkpoint_session import LShadeCheckpointSession
    from ..optimizers.lshade import LShadeBackend
    from ..optimizers.selection import GeometryFirstComparator
    from ..optimization.counters import GeometryGateCounters, evaluation_status
    from ..problem.hybrid import HYBRID_TOPOLOGIES, hybrid_geometry

    context = _stage4a_load_context(config_path)
    root = context["root"]
    run = Path(run_path)
    if not run.is_absolute():
        run = root / run
    validation_path = run / "metadata" / "implementation_validation.json"
    if not validation_path.is_file():
        raise RuntimeError("implementation validation must be run and pass before Stage 4A smoke")
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if validation.get("status") != "PASS":
        raise RuntimeError("implementation validation did not PASS; optimizer smoke is prohibited")
    if validation.get("provenance_status", {}).get("computation_fingerprint") != context["fingerprint"]["computation_fingerprint"]:
        raise RuntimeError("implementation validation fingerprint is stale; rerun the validation gate")
    settings = context["cfg"]["dms_topology"]
    hybrid_cfg = context["cfg"]["hybrid"]
    budget = int(settings["budget"])
    checkpoints = tuple(int(value) for value in settings["checkpoints"])
    seed = int(settings["seeds"][0])
    initial_size = int(settings.get("initial_population", 32))
    if budget != 256 or initial_size != 32 or checkpoints != (128, 256):
        raise ValueError("Stage 4A qualification smoke contract is fixed at 256 unique / pop 32 / checkpoints 128,256")
    if not run.is_dir():
        raise FileNotFoundError("run path must be initialized by --stage4a-validate first")
    from ..core.hybrid import RESONATOR_BOUNDS
    from ..problem.dms_topologies import T1
    from ..studies.dms_topology_screening import material_bounds
    active, hard, _ = material_bounds(context["cfg"], "MLIT", T1)
    top_results, initializer_rows, checkpoint_rows, cache_probe_rows = [], [], [], []
    start_all = time.perf_counter()
    try:
        for topology in HYBRID_TOPOLOGIES:
            topology_started = time.perf_counter()
            space = context["spaces"][topology]
            population, sampling = _stage4a_sample_population(
                space, context["cfg"], seed, topology, initial_size,
                int(hybrid_cfg["initializer"]["max_attempts"]),
            )
            initializer_rows.append(sampling)
            topology_dir = run / "optimization" / topology / f"seed{seed}"
            topology_dir.mkdir(parents=True, exist_ok=True)
            counters = GeometryGateCounters(initial_sampling=dict(sampling))
            timing = {"com_network_evaluation_wall_time_s": 0.0}
            hybrid_hard_bounds = np.vstack([
                hard,
                *([np.asarray(hybrid_cfg["resonator_bounds"], dtype=float)]
                  * (len(space.integer_indices) - 3)),
            ])

            def evaluator(vector):
                candidate = space.decode(vector, reflector_electrodes=int(
                    context["cfg"]["dms_topology"]["t1_reflector_electrodes"]))
                started = time.perf_counter()
                record = _stage4a_evaluate(
                    candidate, context["provider"], context["cfg"],
                    context["search_frequencies"], context["source_impedance_ohm"],
                    context["load_impedance_ohm"],
                )
                timing["com_network_evaluation_wall_time_s"] += time.perf_counter() - started
                counters.observe_search(record, len(context["search_frequencies"]))
                return record

            lshade_config = dict(settings.get("lshade", {}))
            lshade_config.update({
                "total_budget": budget, "requested_unique_budget": budget,
                "hard_max_budget": budget, "population_schedule_terminal_budget": budget,
                "initial_population": initial_size,
                "min_population": 4, "hard_bounds": hybrid_hard_bounds.tolist(),
            })
            backend = LShadeBackend(
                space.bounds, seed=seed, config=lshade_config,
                integer_indices=space.integer_indices, canonicalizer=space.canonicalize,
                comparator=GeometryFirstComparator(),
                source_config_fingerprint=context["fingerprint"]["computation_fingerprint"],
            )
            backend.set_frequency_grid(context["search_frequencies"], version=1)
            # Replay one canonical initial member once so every smoke cell
            # proves cache identity without consuming another unique evaluation.
            optimizer_population = np.vstack([population, population[0]])
            backend.initialize(evaluator, population=optimizer_population)
            cache_probe = {
                "topology": topology,
                "submitted_duplicate_population_member": True,
                "unique_evaluations_after_probe": int(backend.unique_evaluations),
                "cache_hits_after_probe": int(backend.summary()["cache_hits"]),
                "population_size_after_deduplication": int(backend.summary()["population_size"]),
            }
            if (cache_probe["cache_hits_after_probe"] < 1
                    or cache_probe["unique_evaluations_after_probe"] != initial_size
                    or cache_probe["population_size_after_deduplication"] != initial_size):
                raise AssertionError(f"{topology} failed canonical cache idempotency probe")
            cache_probe_rows.append(cache_probe)
            checkpoint_session = LShadeCheckpointSession(
                topology_dir / "checkpoints", run_directory=run,
                legacy_path=topology_dir / "optimizer_checkpoint.json", resume=False,
            )
            checkpoint_snapshots = []
            for point in checkpoints:
                optimizer_started = time.perf_counter()
                backend.advance_to_unique_budget(point)
                optimizer_elapsed = time.perf_counter() - optimizer_started
                if backend.unique_evaluations != point:
                    raise AssertionError(f"{topology} failed exact unique-evaluation budget {point}")
                checkpoint_path = checkpoint_session.save(backend)
                snapshot = _stage4a_counter_snapshot(
                    counters, backend, len(context["search_frequencies"]),
                )
                row = {
                    "topology": topology, "seed": seed, "checkpoint_budget": point,
                    "optimizer_wall_time_s": optimizer_elapsed,
                    "checkpoint_reference": checkpoint_session.reference_metadata,
                    "checkpoint_path_exists": bool(checkpoint_path.is_file()),
                    "counters": snapshot,
                }
                checkpoint_snapshots.append(row)
                checkpoint_rows.append(row)
                _stage4a_write_json(topology_dir / f"B{point}.json", row)
            final_candidates = [dict(value) for value in backend._cache.values()
                                if evaluation_status(value) == "PHYSICS_EVALUATED"]
            final_candidates.sort(key=backend.comparator.rank_key)
            finalist_count = int(hybrid_cfg.get("common_grid_finalists", 4))
            common_started = time.perf_counter()
            validated = []
            for source_rank, source in enumerate(final_candidates[:finalist_count], start=1):
                candidate = space.decode(
                    source["candidate_vector"],
                    reflector_electrodes=int(context["cfg"]["dms_topology"]["t1_reflector_electrodes"]),
                )
                counters.validation_evaluations += 1
                record = _stage4a_evaluate(
                    candidate, context["provider"], context["cfg"],
                    context["common_frequencies"], context["source_impedance_ohm"],
                    context["load_impedance_ohm"], include_spectrum=True,
                )
                record["search_source_rank_key"] = list(backend.comparator.rank_key(source))
                record["search_source_rank"] = source_rank
                if evaluation_status(record) == "PHYSICS_EVALUATED":
                    counters.validation_solved_frequency_points += len(context["common_frequencies"])
                else:
                    counters.validation_physics_failures += 1
                validated.append(record)
            validation_time = time.perf_counter() - common_started
            eligible = [row for row in validated if evaluation_status(row) == "PHYSICS_EVALUATED"]
            common_selected = min(eligible, key=backend.comparator.rank_key) if eligible else None
            if not eligible:
                raise RuntimeError(f"{topology} produced no valid common-grid finalist")
            snapshot = _stage4a_counter_snapshot(counters, backend, len(context["search_frequencies"]))
            final_summary = backend.summary()
            if int(final_summary["generations"]) <= 0 or int(final_summary["raw_offspring_count"]) <= 0:
                raise AssertionError(f"{topology} did not exercise L-SHADE mutation/update")
            if int(snapshot["unique_decoded_evaluations"]) != budget:
                raise AssertionError(f"{topology} unique accounting does not match configured budget")
            wall_time = time.perf_counter() - topology_started
            failures = int(counters.physics_failures + counters.validation_physics_failures)
            metrics = common_selected.get("metrics", {})
            violations = common_selected.get("violations", {})
            dominant = sorted(
                ((key, float(value)) for key, value in violations.items() if float(value) > 0),
                key=lambda item: item[1], reverse=True,
            )[:3]
            if not dominant:
                dominant = [("none", 0.0)]
            result = {
                "topology": topology, "material": "MLIT", "dms_topology": T1,
                "seed": seed, "budget": budget,
                "optimizer_settings": _stage4a_clean(lshade_config),
                "active_bounds": space.bounds.tolist(),
                "optimizer_hard_bounds": hybrid_hard_bounds.tolist(),
                "active_bound_diagnostics": _stage4a_active_bound_diagnostics(
                    common_selected["candidate_vector"], space.bounds,
                ),
                "unique_evaluations": int(backend.unique_evaluations),
                "wall_time_s": float(wall_time),
                "com_network_evaluation_time_s": float(timing["com_network_evaluation_wall_time_s"]),
                "validation_time_s": float(validation_time),
                "search_frequency_points_solved": int(counters.search_frequency_points),
                "validation_frequency_points_solved": int(counters.validation_solved_frequency_points),
                "total_frequency_points_solved": int(counters.solved_frequency_points),
                "cache_hits": int(final_summary["cache_hits"]),
                "failure_count": failures,
                "physics_failure_count": int(counters.physics_failures),
                "validation_failure_count": int(counters.validation_physics_failures),
                "generations": int(final_summary["generations"]),
                "raw_offspring_count": int(final_summary["raw_offspring_count"]),
                "initial_population": int(final_summary["initial_population"]),
                "final_max_violation": float(common_selected["max_violation"]),
                "worst_il_db": float(metrics["worst_il_db"]),
                "ripple_db": float(metrics["ripple_db"]),
                "dominant_violations": dominant,
                "evaluation_status": evaluation_status(common_selected),
                "validation_status": "PASS",
                "common_validation_grid_id": context["common_grid_id"],
                "common_validation_frequency_count": int(len(context["common_frequencies"])),
                "search_frequency_sha256": context["contract"]["search_frequency_sha256"],
                "search_frequency_count": int(len(context["search_frequencies"])),
                "source_impedance_ohm": context["source_impedance_ohm"],
                "load_impedance_ohm": context["load_impedance_ohm"],
                "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
                "fingerprint_schema_version": 2,
                "source_revision": _stage4a_git_state(root),
                "geometry_layout": common_selected["geometry_dimensions"],
                "design_vector": common_selected["candidate_vector"],
                "dms_design": common_selected["dms_design"],
                "resonator_designs": common_selected["resonator_designs"],
                "search_incumbent": backend.incumbent(),
                "common_grid_metrics": metrics,
                "common_grid_violations": violations,
                "constraint_decomposition": {
                    "search_violations": (backend.incumbent() or {}).get("violations", {}),
                    "common_grid_violations": violations,
                    "common_grid_geometry_violations": common_selected.get("geometry_violations", {}),
                },
                "evaluation_counters": snapshot,
                "cache_idempotency_probe": cache_probe,
                "common_grid_finalists_validated": len(validated),
                "checkpoint_snapshots": checkpoint_snapshots,
                "initializer": sampling,
                "cold_start": True, "warm_start": False, "parent_transfer": False,
                "scientific_ranking_claim": False,
            }
            top_results.append(result)
            _stage4a_write_json(topology_dir / "common_validation.json", {
                "selected": common_selected, "validated_finalists": validated,
                "common_validation_grid_id": context["common_grid_id"],
                "common_validation_frequency_count": len(context["common_frequencies"]),
            })
            _stage4a_write_json(topology_dir / "smoke_result.json", result)

    except Exception as exc:
        _stage4a_write_json(run / "metadata" / "execution_failure.json", {
            "status": "FAILED", "error_type": type(exc).__name__, "error": str(exc),
        })
        complete_study_run(run, {"status": "FAILED", "error": str(exc)},
                            disposition=RunDisposition.FAILED)
        raise

    total_wall = time.perf_counter() - start_all
    accounting = {
        "status": "PASS",
        "budget_unit": "unique decoded canonical designs",
        "topologies": {
            row["topology"]: row["evaluation_counters"] for row in top_results
        },
        "checkpoint_states": checkpoint_rows,
        "invariants_passed": True,
    }
    _stage4a_write_json(run / "metadata" / "checkpoint_accounting.json", accounting)
    _stage4a_write_json(run / "metadata" / "initializer_accounting.json", initializer_rows)
    _stage4a_write_json(run / "metadata" / "cache_idempotency.json", {
        "status": "PASS", "policy": "one duplicate canonical initial member per topology",
        "unique_budget_consumed": 0, "topologies": cache_probe_rows,
    })
    _stage4a_write_json(run / "metadata" / "validated_finalists.json", {
        "common_validation_grid_id": context["common_grid_id"],
        "finalist_count_per_topology": int(hybrid_cfg.get("common_grid_finalists", 4)),
        "topologies": [row["topology"] for row in top_results],
    })
    test_summary_path = run / "metadata" / "test_summary.json"
    if not test_summary_path.is_file():
        _stage4a_write_json(test_summary_path, {
            "status": "NOT_RECORDED", "note": "Focused test command results are recorded before bundle finalization.",
        })
    c2c_path = run / "metadata" / "c2c_review_status.json"
    if not c2c_path.is_file():
        _stage4a_write_json(c2c_path, {
            "task_id": "c2c_0b52", "status": "EXECUTED_PENDING_REVIEW",
            "iterations": 0, "decision": None, "mandatory_findings": [],
        })
    result = {
        "status": "STAGE4A_SMOKE_COMPLETE", "scientific_conclusion": False,
        "topologies": top_results, "total_wall_time_s": float(total_wall),
        "stage4b_runtime_estimate": _stage4a_estimate_stage4b(top_results, finalist_count=16),
        "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
        "fingerprint_schema_version": 2,
        "common_validation_grid_id": context["common_grid_id"],
        "run_disposition": "REVIEW_WAITING",
        "stage4b_launched": False,
    }
    _stage4a_write_json(
        run / "metadata" / "stage4b_runtime_estimate.json",
        result["stage4b_runtime_estimate"],
    )
    _stage4a_write_json(run / "smoke_results.json", result)
    from ..reporting.hybrid_qualification import write_stage4a_reports
    parity = json.loads((run / "metadata" / "d_only_parity.json").read_text(encoding="utf-8"))
    test_summary = json.loads(test_summary_path.read_text(encoding="utf-8"))
    write_stage4a_reports(run, result, context, top_results, parity, test_summary)
    complete_study_run(run, result, disposition=RunDisposition.REVIEW_WAITING)
    from ..reporting.hybrid_qualification import build_stage4a_review_bundle
    bundle_path = build_stage4a_review_bundle(run, context)
    result["review_bundle_path"] = str(bundle_path)
    _stage4a_write_json(run / "smoke_results.json", result)
    # Refresh the archive with the final path and lifecycle evidence included.
    bundle_path = build_stage4a_review_bundle(run, context)
    result["review_bundle_path"] = str(bundle_path)
    return result


# Stable helpers reused by later hybrid studies without coupling them to
# Stage 4A's private runner implementation details.
stage4a_active_bound_diagnostics = _stage4a_active_bound_diagnostics
stage4a_clean = _stage4a_clean
stage4a_counter_snapshot = _stage4a_counter_snapshot
stage4a_evaluate = _stage4a_evaluate
stage4a_load_context = _stage4a_load_context


if __name__ == '__main__':
    main()
