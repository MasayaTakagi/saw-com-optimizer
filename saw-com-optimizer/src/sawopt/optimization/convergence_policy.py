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


__all__ = ['DEFAULT_THRESHOLDS', 'convergence_status', 'primary_metric', 'thresholds']
