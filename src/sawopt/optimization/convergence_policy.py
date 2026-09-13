"""Shared convergence thresholds and certificate policy."""
from __future__ import annotations

import copy

import numpy as np

from .convergence_metrics import paired_improvements


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


def thresholds(cfg):
    values = copy.deepcopy(DEFAULT_THRESHOLDS)
    supplied = cfg.get('convergence', {})
    aliases = {
        'budget_primary_relative_improvement': 'paired_median_primary_relative_improvement',
        'budget_primary_absolute_improvement': 'paired_median_primary_absolute_improvement',
        'micro_polish_primary_improvement': 'best_polish_primary_improvement',
        'micro_polish_il_improvement_db': 'best_polish_il_improvement_db',
    }
    for case in ('infeasible', 'feasible'):
        case_values = dict(supplied.get(case, {}))
        for old, new in aliases.items():
            if old in case_values and new not in case_values:
                case_values[new] = case_values[old]
        values[case].update(case_values)
    stage34b = bool(supplied.get(
        'stage3_4b', supplied.get('enable_stage34b_gates', False)
    ))
    if not stage34b:
        return values
    values['_stage34b'] = True
    values['infeasible'].setdefault('final_seed_primary_worst_minus_median', 0.10)
    values['infeasible'].setdefault('max_fraction_seeds_materially_improving', 0.25)
    values['feasible'].setdefault('final_seed_il_worst_minus_median_db', 0.20)
    values['feasible'].setdefault('max_fraction_seeds_materially_improving', 0.25)
    values['_min_grid_converged_seed_fraction'] = float(
        supplied.get('min_grid_converged_seed_fraction', 0.875)
    )
    values['_max_validation_gap_primary'] = supplied.get(
        'max_validation_gap_primary'
    )
    return values


def primary_metric(record):
    if not record.get('feasible', False):
        return float(record.get('max_violation', np.inf))
    return float(record['metrics']['worst_il_db'])


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


def _stage34b_evidence(final, intervals, threshold_values, case):
    """Evaluate the additional Stage 3.4b certificate gates.

    These checks are deliberately fail-closed: when the coordinator did not
    serialize a required piece of evidence, the certificate cannot pass.
    """
    required = (
        'grid_converged',
        'recovery_fired_at_current_checkpoint',
        'recovery_pending_confirmation',
        'boundary_pressure_first_seen_at_current_checkpoint',
        'boundary_pending_confirmation',
        'hard_bound_reached_by_variable',
    )
    missing = sorted({key for row in final for key in required if key not in row})
    if missing:
        return {
            'enabled': True,
            'missing_evidence': missing,
            'pass': False,
            'reason': 'required Stage 3.4b evidence is missing',
        }

    last_intervals = intervals[-2:]
    material_limit = float(
        threshold_values[case].get('max_fraction_seeds_materially_improving', .25)
    )
    material_values = [
        item.get('fraction_seeds_improving_by_threshold')
        for item in last_intervals
    ]
    material_pass = (
        len(last_intervals) == 2 and
        all(value is not None and float(value) <= material_limit
            for value in material_values)
    )
    grid_count = int(sum(bool(row['grid_converged']) for row in final))
    grid_fraction = grid_count / max(len(final), 1)
    grid_limit = float(threshold_values.get(
        '_min_grid_converged_seed_fraction', .875
    ))
    grid_pass = bool(final and grid_fraction >= grid_limit)
    current_recovery = any(
        bool(row['recovery_fired_at_current_checkpoint']) for row in final
    )
    recovery_pending = any(
        bool(row['recovery_pending_confirmation']) for row in final
    )
    boundary_first_seen = any(
        bool(row['boundary_pressure_first_seen_at_current_checkpoint'])
        for row in final
    )
    boundary_pending = any(
        bool(row['boundary_pending_confirmation']) for row in final
    )
    hard_bound_unresolved = any(
        bool(row.get('hard_bound_unresolved', False)) for row in final
    )
    max_gap = max(
        abs(float(row.get('validation_gap_primary', 0.0))) for row in final
    ) if final else float('inf')
    configured_max_gap = threshold_values.get('_max_validation_gap_primary')
    max_gap_pass = (
        configured_max_gap is None or max_gap <= float(configured_max_gap)
    )
    passed = bool(
        material_pass and grid_pass and not current_recovery and
        not recovery_pending and not boundary_first_seen and
        not boundary_pending and not hard_bound_unresolved and max_gap_pass
    )
    return {
        'enabled': True,
        'missing_evidence': [],
        'materially_improving_seed_fraction': material_values,
        'materially_improving_seed_fraction_limit': material_limit,
        'materially_improving_seed_fraction_pass': material_pass,
        'grid_converged_seed_count': grid_count,
        'grid_converged_seed_fraction': float(grid_fraction),
        'min_grid_converged_seed_fraction': grid_limit,
        'grid_converged_fraction_pass': grid_pass,
        'recovery_fired_at_current_checkpoint': current_recovery,
        'recovery_pending_confirmation': recovery_pending,
        'recovery_confirmed': not current_recovery and not recovery_pending,
        'boundary_pressure_first_seen_at_current_checkpoint': boundary_first_seen,
        'boundary_pending_confirmation': boundary_pending,
        'boundary_confirmed': not boundary_first_seen and not boundary_pending,
        'hard_bound_unresolved': hard_bound_unresolved,
        'validation_gap_primary_max': float(max_gap),
        'max_validation_gap_primary_pass': max_gap_pass,
        'pass': passed,
    }


def convergence_status(records, threshold_values):
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
    t = threshold_values[case]
    stage34b = bool(threshold_values.get('_stage34b', False))
    if case == 'feasible':
        for item in intervals:
            item['fraction_seeds_improving_by_threshold'] = float(np.mean(
                np.asarray(item['deltas']) > float(t['paired_median_il_improvement_db'])
            ))
        interval_pass = [item['median_improvement'] < float(t['paired_median_il_improvement_db'])
                         for item in intervals]
        final_values = [metric(row) for row in final]
        final_iqr = float(np.percentile(final_values, 75) - np.percentile(final_values, 25))
        final_median = float(np.median(final_values))
        final_worst = float(max(final_values))
        worst_minus_median = final_worst - final_median
        validation_gap = float(np.median([abs(float(row.get('validation_gap_primary', 0.0))) for row in final]))
        polish_improvement = float(max(float(row.get('micro_polish_improvement', 0.0)) for row in final))
        late_pass = all(_late_improvement_pass(row, t['late_improvement_final_budget_fraction']) for row in final)
        final_pass = (final_iqr < float(t['final_seed_il_iqr_db']) and
                      validation_gap < float(t['validation_il_gap_db']) and
                      polish_improvement < float(t['best_polish_il_improvement_db']) and late_pass)
        stage34b_evidence = _stage34b_evidence(final, intervals, threshold_values, case) if stage34b else None
        if stage34b:
            final_pass = bool(
                final_pass and
                worst_minus_median <= float(t['final_seed_il_worst_minus_median_db'])
                and stage34b_evidence['pass']
            )
        evidence = {
            'case': case, 'budgets': budgets, 'paired_budget_deltas': intervals,
            'interval_plateau_pass': interval_pass, 'final_seed_iqr_db': final_iqr,
            'final_seed_median_il_db': final_median,
            'final_seed_worst_il_db': final_worst,
            'final_seed_worst_minus_median_db': worst_minus_median,
            'validation_il_gap_db': validation_gap,
            'best_polish_il_improvement_db': polish_improvement,
            'late_improvement_pass': late_pass, 'final_gates_pass': final_pass,
        }
        if stage34b:
            evidence['stage34b_gates'] = stage34b_evidence
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
        final_median = float(np.median(final_values))
        final_worst = float(max(final_values))
        worst_minus_median = final_worst - final_median
        validation_gap = float(np.median([abs(float(row.get('validation_gap_primary', 0.0))) for row in final]))
        polish_improvement = float(max(float(row.get('micro_polish_improvement', 0.0)) for row in final))
        late_pass = all(_late_improvement_pass(row, t['late_improvement_final_budget_fraction']) for row in final)
        final_pass = (final_iqr < float(t['final_seed_primary_iqr']) and
                      validation_gap < float(t['validation_primary_gap']) and
                      polish_improvement < float(t['best_polish_primary_improvement']) and late_pass)
        stage34b_evidence = _stage34b_evidence(final, intervals, threshold_values, case) if stage34b else None
        if stage34b:
            final_pass = bool(
                final_pass and
                worst_minus_median <= float(t['final_seed_primary_worst_minus_median'])
                and stage34b_evidence['pass']
            )
        evidence = {
            'case': case, 'budgets': budgets, 'paired_budget_deltas': intervals,
            'interval_plateau_pass': interval_pass, 'final_seed_primary_iqr': final_iqr,
            'final_seed_primary_median': final_median,
            'final_seed_primary_worst': final_worst,
            'final_seed_primary_worst_minus_median': worst_minus_median,
            'validation_primary_gap': validation_gap,
            'best_polish_primary_improvement': polish_improvement,
            'late_improvement_pass': late_pass, 'final_gates_pass': final_pass,
        }
        if stage34b:
            evidence['stage34b_gates'] = stage34b_evidence
    plateau_pass = all(interval_pass)
    if stage34b:
        plateau_pass = len(interval_pass) >= 2 and all(interval_pass[-2:])
        evidence['plateau_gate_last_two_pass'] = plateau_pass
    if len(intervals) >= 2 and plateau_pass and final_pass:
        return 'converged', evidence
    return 'likely_underoptimized', evidence


__all__ = ['DEFAULT_THRESHOLDS', 'convergence_status', 'primary_metric', 'thresholds']
