"""Cold-seed 50-ohm DMS convergence benchmark and certificate.

The benchmark is evidence about a finite, explicitly counted search budget. It
does not claim a global optimum and deliberately keeps the calibrated/
hypothetical COM model and specification thresholds unchanged.
"""
from __future__ import annotations

import argparse
import copy
import csv
import html
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import yaml

from ..core.hybrid import response
from ..core.metrics import geometry, search_grid, validation_grid
from ..core.models import FilterDesign, NAMES, decode
from .optimizer_utils import (
    EvaluationCounters, common_validation_grid, critical_frequencies,
    new_frequency_points, paired_improvements,
)
from .study import dense, evaluate_design, initialize, optimize_one, rank
from .study import _mixed_variable_polish
from .study import save


DEFAULT_THRESHOLDS = {
    'infeasible': {
        'paired_median_primary_relative_improvement': 0.02,
        'paired_median_primary_absolute_improvement': 0.02,
        'final_seed_primary_iqr': 0.10,
        'validation_primary_gap': 0.02,
        'best_polish_primary_improvement': 0.02,
        'late_improvement_final_budget_fraction': 0.25,
    },
    'feasible': {
        'paired_median_il_improvement_db': 0.10,
        'final_seed_il_iqr_db': 0.20,
        'validation_il_gap_db': 0.10,
        'best_polish_il_improvement_db': 0.10,
        'late_improvement_final_budget_fraction': 0.25,
    },
}


def _deep_update(target, source):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


def _thresholds(cfg):
    thresholds = copy.deepcopy(DEFAULT_THRESHOLDS)
    supplied = cfg.get('convergence', {})
    aliases = {
        'budget_primary_relative_improvement': 'paired_median_primary_relative_improvement',
        'budget_primary_absolute_improvement': 'paired_median_primary_absolute_improvement',
        'micro_polish_primary_improvement': 'best_polish_primary_improvement',
        'micro_polish_il_improvement_db': 'best_polish_il_improvement_db',
    }
    for case in ('infeasible', 'feasible'):
        values = dict(supplied.get(case, {}))
        for old, new in aliases.items():
            if old in values and new not in values:
                values[new] = values[old]
        thresholds[case].update(values)
    return thresholds


def _load_config(path):
    path = Path(path)
    study = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    if 'base_config' in study:
        base_path = path.parent / study['base_config']
        cfg = yaml.safe_load(base_path.read_text(encoding='utf-8')) or {}
        cfg.update(study)
    else:
        base_path = path
        cfg = study
    fragment_paths = [path.parent / fragment for fragment in study.get('config_fragments', [])]
    for fragment_path in fragment_paths:
        _deep_update(cfg, yaml.safe_load(fragment_path.read_text(encoding='utf-8')) or {})
    com_path = base_path.parent / cfg['com_file']
    cfg['com'] = yaml.safe_load(com_path.read_text(encoding='utf-8'))
    # Preserve exact text for byte-for-byte review-bundle reproduction.
    cfg['inputs'] = {
        path.name: path.read_text(encoding='utf-8'),
        base_path.name: base_path.read_text(encoding='utf-8'),
        com_path.name: com_path.read_text(encoding='utf-8'),
    }
    for fragment_path in fragment_paths:
        cfg['inputs'][fragment_path.name] = fragment_path.read_text(encoding='utf-8')
    cfg['study_type'] = 'stage3_1_dms_convergence'
    cfg.setdefault(
        'source_impedance_ohm',
        cfg.get('convergence', {}).get('impedance_ohm', 50.0),
    )
    cfg.setdefault('load_impedance_ohm', cfg['source_impedance_ohm'])
    cfg.setdefault('layout', {
        'die_um': [900, 700], 'length_margin_um': 60,
        'width_margin_um': 60, 'max_total_electrodes': 500,
    })
    cfg['convergence'] = dict(cfg.get('convergence', {}))
    cfg['convergence'].update(_thresholds(cfg))
    return cfg


def _cold_seeds(cfg):
    convergence = cfg.get('convergence', {})
    seeds = [int(seed) for seed in convergence.get('seeds', cfg.get('seeds', []))]
    minimum = int(convergence.get('min_cold_seeds', 5))
    if not seeds:
        raise ValueError('At least one seed is required')
    next_seed = max(seeds) + 1
    while len(set(seeds)) < minimum:
        if next_seed not in seeds:
            seeds.append(next_seed)
        next_seed += 1
    return list(dict.fromkeys(seeds))


def parity_check(cfg, z0=50.0):
    """Check legacy DMS outer-port and topology-D outer-port parity."""
    d = FilterDesign()
    x = [getattr(d, name) for name in NAMES]
    f = search_grid(cfg['spec'], cfg)
    legacy = evaluate_design(d, cfg, f, z0, z0, wiring='outer_ports')[1]
    hybrid = response(x, 'D', 'outer_ports', cfg, f, rs=z0, rl=z0)[1]
    error = max(float(np.max(np.abs(legacy[key] - hybrid[key])))
                for key in ('gt', 'il', 'vswr', 's'))
    return {
        'passed': bool(error <= 1e-12), 'max_abs_error': error,
        'frequency_count': len(f), 'wiring': 'outer_ports',
    }


def _primary(record):
    if not record.get('feasible', False):
        return float(record.get('max_violation', np.inf))
    return float(record['metrics']['worst_il_db'])


def _record_polish(record):
    polish = record.get('polish')
    if isinstance(polish, dict):
        return {
            'enabled': bool(polish.get('enabled', True)),
            'promoted': bool(polish.get('promoted', False)),
            'improvement': float(polish.get('improvement', 0.0)),
            'evaluations': int(polish.get('evaluations', 0)),
            'solved_frequency_points': int(polish.get('solved_frequency_points', 0)),
            'polish_wall_time_s': float(polish.get('polish_wall_time_s', 0.0)),
        }
    return {'enabled': False, 'promoted': False, 'improvement': 0.0, 'evaluations': 0}


def micro_polish(record, cfg, z0, wiring):
    """Return the shared mixed-variable polish diagnostic for a trial."""
    if isinstance(record.get('polish'), dict):
        return _record_polish(record)
    common_f = np.asarray(record.get(
        'common_validation_frequencies_hz', validation_grid(cfg['spec'], cfg)), dtype=float)
    polished, diagnostic = _mixed_variable_polish(
        record, cfg, z0, z0, wiring, common_f)
    del polished
    return diagnostic


def _trial_row(record, wiring, budget, micro=None):
    metrics = record['metrics']
    micro = micro or _record_polish(record)
    return {
        'wiring': wiring,
        'budget': int(budget),
        'budget_unique_designs': int(budget),
        'budget_multiplier': None,
        'seed': int(record['seed']),
        'feasible': bool(record['feasible']),
        'max_violation': float(record['max_violation']),
        'sum_violation': float(sum(record['violations'].values())),
        'worst_il_db': float(metrics['worst_il_db']),
        'ripple_db': float(metrics['ripple_db']),
        'input_vswr': float(metrics['input_vswr']),
        'output_vswr': float(metrics['output_vswr']),
        'objective_calls': int(record.get('objective_calls', 0)),
        'canonical_candidates_seen': int(record.get('canonical_candidates_seen', 0)),
        'unique_decoded_evaluations': int(record.get('unique_decoded_evaluations', 0)),
        'valid_physics_evaluations': int(record.get('valid_physics_evaluations', 0)),
        'geometry_rejections': int(record.get('geometry_rejections', 0)),
        'cache_hits': int(record.get('cache_hits', 0)),
        'solved_frequency_points': int(record.get('solved_frequency_points', 0)),
        'validation_solved_frequency_points': int(record.get('validation_solved_frequency_points', 0)),
        'polish_evaluations': int(record.get('polish_evaluations', micro.get('evaluations', 0))),
        'polish_solved_frequency_points': int(record.get('polish_solved_frequency_points', micro.get('solved_frequency_points', 0))),
        'search_frequency_count': int(record.get('search_frequency_count', 0)),
        'validation_frequency_count': int(record.get('validation_frequency_count', 0)),
        'search_scalar_objective': record.get('search_scalar_objective'),
        'search_primary_metric': record.get('search_primary_metric'),
        'validated_rank_tuple': json.dumps(record.get('validated_rank_tuple', list(rank(record)))),
        'selected_adaptive_round': record.get('selected_adaptive_round'),
        'validation_gap_primary': float(record.get('validation_gap_primary', 0.0)),
        'micro_polish_improvement': float(micro.get('improvement', 0.0)),
        'last_significant_improvement_unique_eval': record.get('last_significant_improvement_unique_eval'),
        'fraction_of_budget_at_last_significant_improvement': record.get('fraction_of_budget_at_last_significant_improvement'),
        'global_search_wall_time_s': float(record.get('global_search_wall_time_s', 0.0)),
        'validation_wall_time_s': float(record.get('validation_wall_time_s', 0.0)),
        'polish_wall_time_s': float(record.get('polish_wall_time_s', 0.0)),
        'com_network_evaluation_wall_time_s': float(record.get('com_network_evaluation_wall_time_s', 0.0)),
        'history_io_time_s': float(record.get('history_io_time_s', 0.0)),
        'elapsed_s': float(record.get('elapsed_s', 0.0)),
    }


def _group_records(rows):
    grouped = {}
    for row in rows:
        budget = row.get('budget', row.get('budget_unique_designs', row.get('budget_multiplier')))
        grouped.setdefault(int(budget), []).append(row)
    return grouped


def _late_improvement_pass(record, threshold):
    fraction = record.get('fraction_of_budget_at_last_significant_improvement')
    if fraction is None:
        trace = record.get('best_so_far_trace', [])
        if not trace:
            return True
        budget = float(record.get('requested_unique_design_budget', 0) or 0)
        if budget <= 0:
            return False
        fraction = float(trace[-1]['unique_evaluation']) / budget
    return float(fraction) <= 1.0 - float(threshold)


def _status(records, thresholds):
    """Return status and evidence, requiring two consecutive plateaus."""
    by_budget = _group_records(records)
    budgets = sorted(by_budget)
    if len(budgets) < 3:
        return 'inconclusive', {
            'reason': 'two consecutive budget intervals require at least three budgets',
            'budgets': budgets, 'paired_budget_deltas': [],
        }
    final = by_budget[budgets[-1]]
    feasible_fraction = sum(bool(row.get('feasible', False)) for row in final) / len(final)
    if feasible_fraction not in (0.0, 1.0):
        return 'inconclusive', {
            'reason': 'mixed feasible and infeasible final seeds',
            'budgets': budgets, 'paired_budget_deltas': [],
        }
    case = 'feasible' if feasible_fraction == 1.0 else 'infeasible'
    if case == 'feasible' and any(
        not bool(row.get('feasible', False))
        for budget_rows in by_budget.values() for row in budget_rows
    ):
        return 'inconclusive', {
            'reason': 'feasible convergence certificate contains an earlier infeasible budget',
            'budgets': budgets, 'paired_budget_deltas': [],
        }
    metric = lambda row: float(row['worst_il_db']) if case == 'feasible' else float(row['max_violation'])
    intervals = paired_improvements(by_budget, metric)
    if any(item['seed_count'] == 0 for item in intervals):
        return 'inconclusive', {
            'reason': 'paired comparison has no common seed',
            'budgets': budgets, 'paired_budget_deltas': intervals,
        }
    t = thresholds[case]
    if case == 'feasible':
        for item in intervals:
            item['fraction_seeds_improving_by_threshold'] = float(np.mean(
                np.asarray(item['deltas']) > float(t['paired_median_il_improvement_db'])
            ))
        interval_pass = [item['median_improvement'] < float(t['paired_median_il_improvement_db'])
                         for item in intervals]
        final_values = [metric(row) for row in final]
        final_iqr = float(np.percentile(final_values, 75) - np.percentile(final_values, 25))
        validation_gap = float(np.median([abs(float(row.get('validation_gap_primary', 0.0))) for row in final]))
        polish_improvement = float(max(float(row.get('micro_polish_improvement', 0.0)) for row in final))
        late_pass = all(_late_improvement_pass(row, t['late_improvement_final_budget_fraction']) for row in final)
        final_pass = (final_iqr < float(t['final_seed_il_iqr_db']) and
                      validation_gap < float(t['validation_il_gap_db']) and
                      polish_improvement < float(t['best_polish_il_improvement_db']) and late_pass)
        evidence = {
            'case': case, 'budgets': budgets, 'paired_budget_deltas': intervals,
            'interval_plateau_pass': interval_pass, 'final_seed_iqr_db': final_iqr,
            'validation_il_gap_db': validation_gap,
            'best_polish_il_improvement_db': polish_improvement,
            'late_improvement_pass': late_pass, 'final_gates_pass': final_pass,
        }
    else:
        interval_pass = []
        for item in intervals:
            baseline = float(np.median([metric(row) for row in by_budget[item['lower_budget']]]))
            relative = item['median_improvement'] / max(abs(baseline), 1e-12)
            item['median_relative_improvement'] = float(relative)
            item['fraction_seeds_improving_by_threshold'] = float(np.mean(
                np.asarray(item['deltas']) > float(t['paired_median_primary_absolute_improvement'])
            ))
            interval_pass.append(
                relative < float(t['paired_median_primary_relative_improvement']) and
                item['median_improvement'] < float(t['paired_median_primary_absolute_improvement'])
            )
        final_values = [metric(row) for row in final]
        final_iqr = float(np.percentile(final_values, 75) - np.percentile(final_values, 25))
        validation_gap = float(np.median([abs(float(row.get('validation_gap_primary', 0.0))) for row in final]))
        polish_improvement = float(max(float(row.get('micro_polish_improvement', 0.0)) for row in final))
        late_pass = all(_late_improvement_pass(row, t['late_improvement_final_budget_fraction']) for row in final)
        final_pass = (final_iqr < float(t['final_seed_primary_iqr']) and
                      validation_gap < float(t['validation_primary_gap']) and
                      polish_improvement < float(t['best_polish_primary_improvement']) and late_pass)
        evidence = {
            'case': case, 'budgets': budgets, 'paired_budget_deltas': intervals,
            'interval_plateau_pass': interval_pass, 'final_seed_primary_iqr': final_iqr,
            'validation_primary_gap': validation_gap,
            'best_polish_primary_improvement': polish_improvement,
            'late_improvement_pass': late_pass, 'final_gates_pass': final_pass,
        }
    if len(intervals) >= 2 and all(interval_pass) and final_pass:
        return 'converged', evidence
    return 'likely_underoptimized', evidence


def _performance_gate(cfg, record, wiring, z0):
    """Compare full recomputation and exact incremental dense validation."""
    d = decode([record['design'][name] for name in NAMES])
    validation_cfg = cfg.get('validation', {})
    passes = int(validation_cfg.get('dense_refinement_passes', cfg.get('dense_refinement_passes', 2)))
    tolerance = float(validation_cfg.get('adaptive_frequency_tolerance_hz', cfg.get('adaptive_frequency_tolerance_hz', 1e3)))
    slope = float(cfg.get('dense_slope_threshold_db', .5))
    max_points = int(validation_cfg.get('adaptive_max_points_per_round', 64))
    legacy_f = validation_grid(cfg['spec'], cfg)
    legacy_solved = 0
    legacy_started = time.time()
    for _ in range(max(0, passes)):
        _r, net, _sim = evaluate_design(d, cfg, legacy_f, z0, z0, wiring=wiring)
        legacy_solved += len(legacy_f)
        critical = critical_frequencies(legacy_f, net, cfg['spec'], slope_threshold_db=slope, max_points=max_points)
        added = new_frequency_points(legacy_f, critical, tolerance)
        if len(added) == 0:
            break
        legacy_f = np.unique(np.r_[legacy_f, added])
    legacy_result, _legacy_net, _legacy_sim = evaluate_design(d, cfg, legacy_f, z0, z0, wiring=wiring)
    legacy_solved += len(legacy_f)
    legacy_wall = time.time() - legacy_started
    counters = EvaluationCounters()
    stage_started = time.time()
    stage_f, (stage_result, stage_net, stage_sim) = dense(d, cfg, z0, z0, wiring=wiring, counters=counters)
    stage_wall = time.time() - stage_started
    reference, reference_net, reference_sim = evaluate_design(d, cfg, stage_f, z0, z0, wiring=wiring)
    diagnostics_match = set(stage_result['diagnostics']) == set(reference['diagnostics']) and all(
        np.isclose(stage_result['diagnostics'].get(key), reference['diagnostics'].get(key), rtol=1e-10, atol=1e-10)
        for key in stage_result['diagnostics']
        if isinstance(stage_result['diagnostics'].get(key), (int, float))
    )
    numerical_match = bool(
        np.array_equal(stage_f, reference_sim.frequencies_hz) and
        np.allclose(stage_net['il'], reference_net['il'], rtol=1e-11, atol=1e-11) and
        np.allclose(stage_net['vswr'], reference_net['vswr'], rtol=1e-11, atol=1e-11) and
        diagnostics_match and rank(stage_result) == rank(reference)
    )
    speedup = legacy_wall / max(stage_wall, np.finfo(float).tiny)
    minimum_speedup = float(cfg.get('performance_min_speedup', 1.5))
    return {
        'candidate_rank': list(rank(record)),
        'legacy_full_recompute': {
            'wall_time_s': legacy_wall, 'objective_calls': 1,
            'unique_evaluations': 1, 'solved_frequency_points': legacy_solved,
            'validated_rank': list(rank(legacy_result)),
        },
        'stage3_1_incremental': {
            'wall_time_s': stage_wall, 'objective_calls': 1,
            'unique_evaluations': 1, 'solved_frequency_points': counters.solved_frequency_points,
            'validated_rank': list(rank(stage_result)),
        },
        'numerical_match_on_final_grid': numerical_match,
        'frequency_set_match': bool(np.array_equal(stage_f, reference_sim.frequencies_hz)),
        'rank_match': bool(rank(stage_result) == rank(reference)),
        'diagnostics_match': diagnostics_match,
        'speedup': speedup,
        'minimum_required_speedup': minimum_speedup,
        'speedup_gate_pass': bool(speedup >= minimum_speedup),
        'speedup_regression_explanation': None if speedup >= minimum_speedup else (
            'Incremental path was slower on this fixture; inspect validation grid size, '
            'adaptive critical-point count, and BLAS/runtime conditions.'
        ),
        'quality_comparison': 'same candidate, common equations, and unchanged validation thresholds',
    }


def _revalidate_on_wiring_common_grid(records, cfg, z0, wiring):
    """Put every budget/seed result for one wiring on one validation grid."""
    base = validation_grid(cfg['spec'], cfg)
    tolerance = float(cfg.get('validation', {}).get(
        'adaptive_frequency_tolerance_hz', cfg.get('adaptive_frequency_tolerance_hz', 1e3)))
    common = common_validation_grid(
        base,
        [record.get('dense_critical_frequencies', []) for _budget, record in records],
        tolerance,
    )
    output = []
    for budget, record in records:
        counters = EvaluationCounters()
        started = time.time()
        design = decode([record['design'][name] for name in NAMES])
        _frequencies, (validated, _net, _sim) = dense(
            design, cfg, z0, z0, wiring=wiring, counters=counters,
            base_grid=common, passes=0, validation=True,
        )
        elapsed = time.time() - started
        search_primary = float(record.get('search_primary_metric', _primary(record)))
        search_scalar = record.get('search_scalar_objective')
        updated = dict(record)
        updated.update(validated)
        updated.update({
            'design': dict(record['design']), 'seed': int(record['seed']),
            'wiring': wiring, 'search_scalar_objective': search_scalar,
            'search_primary_metric': search_primary,
            'validated_rank_tuple': list(rank(validated)),
            'common_validation_frequencies_hz': common.tolist(),
            'common_validation_grid_count': len(common),
            'validation_frequency_count': len(common),
            'validation_gap_primary': _primary(validated) - search_primary,
            'common_validation_revalidated': True,
            'common_validation_solved_frequency_points': counters.solved_frequency_points,
            'common_validation_wall_time_s': elapsed,
            'solved_frequency_points': int(record.get('solved_frequency_points', 0)) + counters.solved_frequency_points,
            'validation_solved_frequency_points': int(record.get('validation_solved_frequency_points', 0)) + counters.validation_frequency_points,
            'validation_wall_time_s': float(record.get('validation_wall_time_s', 0.0)) + counters.validation_wall_time_s,
            'com_network_evaluation_wall_time_s': float(record.get('com_network_evaluation_wall_time_s', 0.0)) + counters.com_network_evaluation_wall_time_s,
            'elapsed_s': float(record.get('elapsed_s', 0.0)) + elapsed,
        })
        output.append((int(budget), updated))
    return output, common


def _polish_common_final_candidates(records, cfg, z0, wiring, common):
    """Polish the best and median final-budget candidates on the shared grid."""
    if not records:
        return records
    final_budget = max(budget for budget, _record in records)
    final_indices = [index for index, (budget, _record) in enumerate(records) if budget == final_budget]
    ordered = sorted(final_indices, key=lambda index: rank(records[index][1]))
    selected_indices = list(dict.fromkeys([ordered[0], ordered[(len(ordered) - 1) // 2]]))
    mutable = list(records)
    for index in selected_indices:
        budget, record = mutable[index]
        counters = EvaluationCounters()
        polished, diagnostic = _mixed_variable_polish(
            record, cfg, z0, z0, wiring, common, counters=counters,
            promote=cfg.get('micro_polish', {}).get('promote_in_production', True),
        )
        updated = dict(polished)
        if diagnostic.get('promoted'):
            for key in (
                'seed', 'wiring', 'rs', 'rl', 'search_objective',
                'search_scalar_objective', 'search_primary_metric',
                'selected_adaptive_round', 'adaptive_round',
                'dense_critical_frequencies', 'validation_gap_primary',
                'common_validation_frequencies_hz', 'common_validation_grid_count',
                'validation_frequency_count', 'common_validation_revalidated',
                'pre_polish_result', 'post_polish_result', 'polish',
                'best_so_far_trace', 'last_significant_improvement_unique_eval',
                'fraction_of_budget_at_last_significant_improvement',
            ):
                if key in record:
                    updated[key] = record[key]
            updated['design'] = dict(polished['design'])
            updated['post_polish_result'] = dict(polished)
        updated['pre_common_validation_polish'] = record.get('polish', {})
        updated['common_validation_polish'] = diagnostic
        updated['polish'] = diagnostic
        updated['polish_evaluations'] = int(record.get('polish_evaluations', 0)) + counters.polish_evaluations
        updated['polish_solved_frequency_points'] = int(record.get('polish_solved_frequency_points', 0)) + counters.polish_solved_frequency_points
        updated['polish_wall_time_s'] = float(record.get('polish_wall_time_s', 0.0)) + counters.polish_wall_time_s
        updated['solved_frequency_points'] = int(record.get('solved_frequency_points', 0)) + counters.polish_solved_frequency_points
        updated['elapsed_s'] = float(record.get('elapsed_s', 0.0)) + counters.polish_wall_time_s
        updated['validated_rank_tuple'] = list(rank(updated))
        mutable[index] = (budget, updated)
    return mutable


def _parallelism_metadata(cfg):
    runtime = cfg.get('optimizer_runtime', {})
    requested = runtime.get('parallel_benchmark_jobs', [1, 2, 4])
    return {
        'jobs_requested': [int(job) for job in requested],
        'jobs': {str(int(job)): {'jobs': int(job), 'status': 'not_run'} for job in requested},
        'blas_threads_per_worker': int(runtime.get('blas_threads_per_worker', 1)),
        'environment_policy': {'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'},
        'executed': bool(runtime.get('run_parallelism_benchmark', False)),
        'note': 'Certificate trials remain deterministic cold runs; enable the explicit parallel benchmark separately.',
    }


@contextmanager
def _single_blas_thread_environment(threads=1):
    """Prevent BLAS/OpenMP oversubscription in external-worker benchmarks."""
    names = ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS')
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


def _parallel_trial(payload):
    """Process-pool entry point kept top-level for Windows spawn semantics."""
    out, cfg, wiring, budget, seed, jobs = payload
    trial_cfg = copy.deepcopy(cfg)
    trial_cfg['max_unique_decoded_evaluations'] = int(budget)
    trial_cfg.setdefault('optimizer', {})['max_unique_decoded_evaluations'] = int(budget)
    trial_cfg['optimizer']['warm_resume'] = False
    trial_cfg.setdefault('convergence', {})['benchmark_early_stop'] = False
    return optimize_one(
        Path(out), trial_cfg, float(cfg['convergence']['impedance_ohm']),
        float(cfg['convergence']['impedance_ohm']), int(seed), neighbor=None,
        wiring=wiring, mode='benchmark',
        run_label=f'parallelism__jobs{jobs}__{wiring}__B{budget}',
        warm_resume=False,
    )


def run_parallelism_benchmark(out, cfg, tasks):
    """Benchmark independent trials with 1/2/4 external worker processes."""
    runtime = cfg.get('optimizer_runtime', {})
    jobs_list = [int(job) for job in runtime.get('parallel_benchmark_jobs', [1, 2, 4])]
    threads = int(runtime.get('blas_threads_per_worker', 1))
    results = {}
    baseline_ranks = None
    for jobs in jobs_list:
        jobs_out = Path(out) / 'parallelism' / f'jobs{jobs}'
        jobs_out.mkdir(parents=True, exist_ok=True)
        initialize(jobs_out, cfg)
        payloads = [(str(jobs_out), cfg, wiring, budget, seed, jobs)
                    for wiring, budget, seed in tasks]
        started = time.time()
        with _single_blas_thread_environment(threads):
            if jobs == 1:
                trial_results = [_parallel_trial(payload) for payload in payloads]
            else:
                with ProcessPoolExecutor(max_workers=jobs) as pool:
                    trial_results = list(pool.map(_parallel_trial, payloads))
        wall = time.time() - started
        ranks = [tuple(record.get('validated_rank_tuple', rank(record))) for record in trial_results]
        if baseline_ranks is None:
            baseline_ranks = ranks
        results[str(jobs)] = {
            'jobs': jobs, 'wall_time_s': wall, 'trial_count': len(trial_results),
            'numerical_ranks_match_jobs_1': ranks == baseline_ranks,
            'blas_threads_per_worker': threads,
        }
    if results:
        baseline_wall = results[str(jobs_list[0])]['wall_time_s']
        for values in results.values():
            values['speedup_vs_first'] = baseline_wall / max(values['wall_time_s'], np.finfo(float).tiny)
            values['parallel_efficiency_vs_first'] = values['speedup_vs_first'] / max(values['jobs'], 1)
    return {
        'executed': True, 'jobs': results, 'tasks': [list(task) for task in tasks],
        'blas_threads_per_worker': threads,
        'environment_policy': {'OMP_NUM_THREADS': str(threads), 'MKL_NUM_THREADS': str(threads),
                               'OPENBLAS_NUM_THREADS': str(threads)},
    }


def _write_csv(path, rows):
    path = Path(path)
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_html(out, summary, rows):
    columns = ['wiring', 'budget', 'seed', 'feasible', 'max_violation', 'worst_il_db', 'objective_calls',
               'unique_decoded_evaluations', 'cache_hits', 'solved_frequency_points', 'validation_gap_primary',
               'micro_polish_improvement', 'elapsed_s']
    head = ''.join(f'<th>{html.escape(c)}</th>' for c in columns)
    body = ''.join('<tr>' + ''.join(f'<td>{html.escape(str(row.get(c, "")))}</td>' for c in columns) + '</tr>' for row in rows)
    status = ''.join(f'<li>{html.escape(wiring)}: <b>{html.escape(value["status"])}</b></li>' for wiring, value in summary['statuses'].items())
    budget_rows = []
    for wiring, budgets_for_wiring in summary['budget_summary'].items():
        for budget, values in budgets_for_wiring.items():
            budget_rows.append('<tr>' + ''.join(f'<td>{html.escape(str(value))}</td>' for value in (
                wiring, budget, values['best_primary_metric'], values['median_primary_metric'],
                values['seed_iqr_primary_metric'], values['feasible_seed_count'],
                values['total_unique_evaluations'], values['total_solved_frequency_points'],
                values['total_wall_time_s'])) + '</tr>')
    budget_table = '''<table><tr><th>wiring</th><th>budget</th><th>best primary</th><th>median primary</th><th>seed IQR</th><th>feasible seeds</th><th>unique evals</th><th>solved points</th><th>wall time (s)</th></tr>''' + ''.join(budget_rows) + '</table>'
    page = f'''<!doctype html><html lang="ja"><meta charset="utf-8"><title>Stage 3.1 50-ohm DMS convergence certificate</title>
<style>body{{font:15px system-ui;max-width:1500px;margin:30px auto;padding:20px;background:#f5f7fa;color:#18253a}}table{{border-collapse:collapse;background:white;width:100%;font-size:12px}}td,th{{padding:7px;border-bottom:1px solid #ddd;text-align:right}}th:first-child,td:first-child{{text-align:left}}p{{line-height:1.7}}.note{{background:white;padding:14px}}</style>
<h1>Stage 3.1：50 Ω DMS convergence</h1><p class="note">Cold seed と一意デコード設計数の paired budget 比較です。global optimum は主張しません。</p>
<p>Parity: {html.escape(str(summary['parity']))}</p><ul>{status}</ul><h2>Budget / seed summary</h2>{budget_table}
<h2>Performance gate</h2><pre>{html.escape(json.dumps(summary['performance_gate'], ensure_ascii=False, indent=2))}</pre><table><tr>{head}</tr>{body}</table>
<p><a href="convergence_summary.json">convergence_summary.json</a> / <a href="paired_budget_deltas.csv">paired_budget_deltas.csv</a></p></html>'''
    (out / 'convergence_report.html').write_text(page, encoding='utf-8')


def run_convergence(out, cfg):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = copy.deepcopy(cfg)
    cfg['run_mode'] = 'benchmark'
    cfg.setdefault('convergence', {})['benchmark_early_stop'] = False
    initialize(out, cfg)
    z0 = float(cfg['convergence'].get('impedance_ohm', 50.0))
    wirings = list(cfg.get('wirings', ['outer_ports', 'center_outer_same']))
    convergence = cfg.get('convergence', {})
    budgets = convergence.get('unique_design_budgets', convergence.get('budget_unique_designs'))
    if budgets is None:
        legacy_multipliers = [int(x) for x in convergence.get('budget_multipliers', [1, 2, 4])]
        per_generation = int(cfg['optimizer']['population']) * (int(cfg['optimizer']['maxiter']) + 1)
        budgets = [per_generation * multiplier for multiplier in legacy_multipliers]
    budgets = sorted(dict.fromkeys(int(budget) for budget in budgets))
    if not budgets or any(budget <= 0 for budget in budgets):
        raise ValueError('convergence.unique_design_budgets must contain positive integers')
    seeds = _cold_seeds(cfg)
    rows = []
    records_by_wiring = {wiring: [] for wiring in wirings}
    trial_files = []
    started = time.time()
    runtime = cfg.get('optimizer_runtime', {})
    jobs = max(1, int(runtime.get('benchmark_jobs', runtime.get('parallel_jobs', 1))))
    auto_escalate = bool(convergence.get('auto_escalate', True))

    def run_trial(task):
        task_wiring, budget, seed = task
        trial_cfg = copy.deepcopy(cfg)
        trial_cfg['max_unique_decoded_evaluations'] = int(budget)
        trial_cfg.setdefault('optimizer', {})['max_unique_decoded_evaluations'] = int(budget)
        trial_cfg['optimizer']['use_neighbor_warm_start'] = False
        trial_cfg['optimizer']['warm_resume'] = False
        trial_cfg.setdefault('convergence', {})['current_unique_design_budget'] = int(budget)
        label = f'convergence__{task_wiring}__B{budget}'
        return budget, optimize_one(out, trial_cfg, z0, z0, seed, neighbor=None, wiring=task_wiring,
                                    mode='benchmark', run_label=label, warm_resume=False)

    for wiring in wirings:
        for budget in budgets:
            prior_rows = [row for row in rows if row['wiring'] == wiring]
            if auto_escalate and len({row['budget'] for row in prior_rows}) >= 3:
                checked, _checked_grid = _revalidate_on_wiring_common_grid(
                    records_by_wiring[wiring], cfg, z0, wiring)
                checked = _polish_common_final_candidates(
                    checked, cfg, z0, wiring, _checked_grid)
                prior_rows = [_trial_row(record, wiring, checked_budget)
                              for checked_budget, record in checked]
            prior_status = _status(prior_rows, _thresholds(cfg))[0] if prior_rows else 'inconclusive'
            if auto_escalate and prior_status == 'converged':
                break
            tasks = [(wiring, budget, seed) for seed in seeds]
            if jobs > 1:
                with _single_blas_thread_environment(
                    int(runtime.get('blas_threads_per_worker', 1))
                ):
                    with ThreadPoolExecutor(max_workers=jobs) as pool:
                        results = list(pool.map(run_trial, tasks))
            else:
                results = [run_trial(task) for task in tasks]
            for completed_budget, record in results:
                records_by_wiring[wiring].append((completed_budget, record))
                rows.append(_trial_row(record, wiring, completed_budget))
                trial_dir = out / 'trials'
                trial_dir.mkdir(parents=True, exist_ok=True)
                trial_path = trial_dir / f'{wiring}__B{completed_budget}__seed{record["seed"]}.json'
                save(trial_path, record)
                trial_files.append(trial_path.relative_to(out).as_posix())

    # The optimizer's adaptive grid is candidate-specific. Re-evaluate every
    # certificate member on one wiring-wide common grid before calculating any
    # paired statistic, so search-grid luck cannot become convergence evidence.
    common_validation_grids = {}
    for wiring in wirings:
        records_by_wiring[wiring], common_validation_grids[wiring] = _revalidate_on_wiring_common_grid(
            records_by_wiring[wiring], cfg, z0, wiring)
        records_by_wiring[wiring] = _polish_common_final_candidates(
            records_by_wiring[wiring], cfg, z0, wiring, common_validation_grids[wiring])

    rows = []
    for wiring in wirings:
        for budget, record in records_by_wiring[wiring]:
            rows.append(_trial_row(record, wiring, budget))
            trial_path = out / 'trials' / f'{wiring}__B{budget}__seed{record["seed"]}.json'
            save(trial_path, record)

    thresholds = _thresholds(cfg)
    statuses = {}
    paired_rows = []
    budget_summary = {}
    best_candidates = {}
    median_candidate_polish = {}
    last_improvement = {}
    performance = {}
    for wiring in wirings:
        trial_rows = [row for row in rows if row['wiring'] == wiring]
        status, evidence = _status(trial_rows, thresholds)
        statuses[wiring] = {'status': status, 'evidence': evidence, 'trial_count': len(trial_rows)}
        for interval in evidence.get('paired_budget_deltas', []):
            interval_row = dict(interval)
            interval_row['wiring'] = wiring
            interval_row['deltas'] = json.dumps(interval.get('deltas', []))
            paired_rows.append(interval_row)
        budget_summary[wiring] = {}
        for budget in sorted({row['budget'] for row in trial_rows}):
            budget_rows = [row for row in trial_rows if row['budget'] == budget]
            primary = [_primary(row) for row in budget_rows]
            budget_summary[wiring][str(budget)] = {
                'best_primary_metric': float(min(primary)), 'median_primary_metric': float(np.median(primary)),
                'seed_iqr_primary_metric': float(np.percentile(primary, 75) - np.percentile(primary, 25)),
                'feasible_seed_count': int(sum(bool(row['feasible']) for row in budget_rows)),
                'seed_count': len(budget_rows),
                'median_validation_gap_primary': float(np.median([abs(row['validation_gap_primary']) for row in budget_rows])),
                'median_micro_polish_improvement': float(np.median([row['micro_polish_improvement'] for row in budget_rows])),
                'total_unique_evaluations': int(sum(row['unique_decoded_evaluations'] for row in budget_rows)),
                'total_solved_frequency_points': int(sum(row['solved_frequency_points'] for row in budget_rows)),
                'total_wall_time_s': float(sum(row['elapsed_s'] for row in budget_rows)),
            }
            records = [record for completed_budget, record in records_by_wiring[wiring] if completed_budget == budget]
            best = min(records, key=rank)
            best_candidates.setdefault(wiring, {})[str(budget)] = {
                'seed': int(best['seed']),
                'result_file': f'trials/{wiring}__B{budget}__seed{best["seed"]}.json',
                'design': best['design'], 'validated_metrics': best['metrics'],
                'validated_rank_tuple': best.get('validated_rank_tuple', list(rank(best))),
                'polish': best.get('polish', {}),
            }
            ordered = sorted(records, key=rank)
            median_record = ordered[(len(ordered) - 1) // 2]
            median_candidate_polish.setdefault(wiring, {})[str(budget)] = {
                'seed': int(median_record['seed']),
                'polish': median_record.get('polish', {}),
            }
            last_improvement.setdefault(wiring, {})[str(budget)] = [
                {
                    'seed': int(record['seed']),
                    'unique_evaluation': record.get('last_significant_improvement_unique_eval'),
                    'fraction_of_budget': record.get('fraction_of_budget_at_last_significant_improvement'),
                }
                for record in records
            ]
        final_budget = max(budget_summary[wiring]) if budget_summary[wiring] else None
        final_records = [record for completed_budget, record in records_by_wiring[wiring]
                         if str(completed_budget) == final_budget]
        if final_records:
            performance[wiring] = _performance_gate(cfg, min(final_records, key=rank), wiring, z0)

    parallelism = _parallelism_metadata(cfg)
    if parallelism['executed']:
        final_budget_for_parallelism = max(budgets)
        parallel_tasks = [
            (wiring, final_budget_for_parallelism, seed)
            for wiring in wirings for seed in seeds
        ]
        parallelism = run_parallelism_benchmark(out, cfg, parallel_tasks)

    _write_csv(out / 'convergence_trials.csv', rows)
    _write_csv(out / 'paired_budget_deltas.csv', paired_rows)
    budget_rows = []
    for wiring, budgets_for_wiring in budget_summary.items():
        for budget, values in budgets_for_wiring.items():
            budget_rows.append(dict(wiring=wiring, budget=budget, **values))
    _write_csv(out / 'budget_summary.csv', budget_rows)
    save(out / 'best_candidates.json', best_candidates)
    save(out / 'performance_gate.json', performance)
    summary = {
        'bundle_format_version': 1, 'study_type': 'stage3_1_dms_convergence',
        'impedance_ohm': z0, 'wirings': wirings, 'unique_design_budgets': budgets,
        'budgets_run_by_wiring': {wiring: sorted(int(budget) for budget in budget_summary[wiring]) for wiring in wirings},
        'cold_seeds': seeds, 'min_cold_seeds': int(convergence.get('min_cold_seeds', 5)),
        'benchmark_early_stop': False, 'warm_starts': False, 'auto_escalate': auto_escalate,
        'parity': parity_check(cfg, z0), 'thresholds': thresholds, 'statuses': statuses,
        'budget_summary': budget_summary, 'paired_budget_deltas': paired_rows,
        'median_candidate_polish': median_candidate_polish,
        'last_significant_improvement': last_improvement,
        'common_validation_grid_counts': {
            wiring: len(common_validation_grids[wiring]) for wiring in wirings
        },
        'performance_gate': performance, 'parallelism_benchmark': parallelism,
        'trial_files': trial_files,
        'expected_trial_count': sum(
            len(budget_summary[wiring]) * len(seeds) for wiring in wirings
        ),
        'elapsed_s': time.time() - started,
        'command': cfg.get(
            'benchmark_command',
            'python -m sawopt.optimization.convergence_study --config configs/studies/stage3_convergence_50ohm.yaml --run runs/stage3_1_50ohm',
        ),
        'reports': {'trials_csv': 'convergence_trials.csv', 'paired_deltas_csv': 'paired_budget_deltas.csv',
                    'budget_summary_csv': 'budget_summary.csv', 'html': 'convergence_report.html'},
        'interpretation': 'Finite budget/seed evidence only; no global optimum is claimed.',
        'known_limitations': ['Hypothetical COM remains unvalidated for production design.',
                              'Benchmark trials are cold and non-resumed; production warm resume is non-exact.'],
    }
    save(out / 'convergence_summary.json', summary)
    _write_html(out, summary, rows)
    return summary


def main():
    parser = argparse.ArgumentParser(description='Stage 3.1 cold-seed DMS convergence benchmark')
    parser.add_argument('--config', default='configs/studies/stage3_convergence_50ohm.yaml')
    parser.add_argument('--run', default='runs/stage3_1_50ohm')
    parser.add_argument('--z0', type=float)
    parser.add_argument('--run-parallelism-benchmark', action='store_true',
                        help='also run the explicit 1/2/4 external-worker benchmark')
    args = parser.parse_args()
    cfg = _load_config(args.config)
    if args.z0 is not None:
        cfg.setdefault('convergence', {})['impedance_ohm'] = args.z0
    if args.run_parallelism_benchmark:
        cfg.setdefault('optimizer_runtime', {})['run_parallelism_benchmark'] = True
    print(json.dumps(run_convergence(args.run, cfg), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
