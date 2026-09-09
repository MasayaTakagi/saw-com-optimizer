"""Small-budget Stage 2 search-quality and population-fairness benchmark."""
from __future__ import annotations

import copy
import csv
import json
import sys
from pathlib import Path

import yaml

from sawopt.optimization.hybrid_study import optimize_case
from sawopt.optimization.study import rank


root = Path(__file__).resolve().parents[2]
base = yaml.safe_load((root/'configs/base/b28_dms_baseline.yaml').read_text(encoding='utf-8'))
hybrid = yaml.safe_load((root/'configs/studies/hybrid_50ohm.yaml').read_text(encoding='utf-8'))
base.update(hybrid)
base['com'] = yaml.safe_load((root/'configs/models/com_params_hypothetical.yaml').read_text(encoding='utf-8'))
base.update(population=7, population_reference_dimensions=7, dense_refinement_passes=2,
            dense_slope_threshold_db=.5, adaptive_frequency_tolerance_hz=1000,
            adaptive_max_points_per_round=32)
out = root/'runs/stage2-validation'
out.mkdir(parents=True, exist_ok=True)

rows = []
for topology in ('D', 'P_D', 'P_D_P'):
    for seed in (20260908, 20260909, 20260910):
        coarse_cfg = copy.deepcopy(base)
        coarse_cfg.update(adaptive_frequency_rounds=0, adaptive_iterations=0)
        coarse = optimize_case(out, coarse_cfg, topology, 'center_outer_same', seed,
                               'quality_coarse', 1, rs=50, rl=50)
        adaptive_cfg = copy.deepcopy(base)
        adaptive_cfg.update(adaptive_frequency_rounds=1, adaptive_iterations=0)
        adaptive = optimize_case(out, adaptive_cfg, topology, 'center_outer_same', seed,
                                 'quality_adaptive', 0, rs=50, rl=50)
        rows.append({
            'topology': topology, 'seed': seed,
            'coarse_evaluations': coarse['evaluations'], 'adaptive_evaluations': adaptive['evaluations'],
            'coarse_dense_il_db': coarse['metrics']['worst_il_db'],
            'adaptive_dense_il_db': adaptive['metrics']['worst_il_db'],
            'delta_il_db': adaptive['metrics']['worst_il_db']-coarse['metrics']['worst_il_db'],
            'coarse_input_vswr': coarse['metrics']['input_vswr'],
            'adaptive_input_vswr': adaptive['metrics']['input_vswr'],
            'coarse_max_violation': coarse['max_violation'],
            'adaptive_max_violation': adaptive['max_violation'],
            'adaptive_added_frequency_count': adaptive['search_frequency_count']-coarse['search_frequency_count'],
            'adaptive_rounds': adaptive['adaptive_rounds_completed'],
            'coarse_failures': coarse['failures'], 'adaptive_failures': adaptive['failures'],
            'coarse_runtime_s': coarse['elapsed_s'], 'adaptive_runtime_s': adaptive['elapsed_s'],
        })

with (out/'adaptive_quality.csv').open('w', newline='', encoding='utf-8-sig') as stream:
    writer = csv.DictWriter(stream, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)

population_rows = []
for reference_dimensions, label in ((13, 'fixed_7'), (7, 'scaled_13')):
    cfg = copy.deepcopy(base)
    cfg.update(population_reference_dimensions=reference_dimensions,
               adaptive_frequency_rounds=0, adaptive_iterations=0, dense_refinement_passes=1)
    records = [optimize_case(out, cfg, 'P_D_P', 'center_outer_same', seed,
                             'population_'+label, 0, rs=50, rl=50)
               for seed in (20260908, 20260909, 20260910)]
    winner = min(records, key=rank)
    population_rows.append({
        'mode': label, 'dimensions': winner['dimensions'], 'population': winner['population'],
        'best_max_violation': winner['max_violation'], 'best_dense_il_db': winner['metrics']['worst_il_db'],
        'total_evaluations': sum(r['evaluations'] for r in records),
        'total_runtime_s': sum(r['elapsed_s'] for r in records),
    })
with (out/'population_fairness.csv').open('w', newline='', encoding='utf-8-sig') as stream:
    writer = csv.DictWriter(stream, fieldnames=population_rows[0].keys()); writer.writeheader(); writer.writerows(population_rows)

summary = {
    'adaptive_cases': len(rows),
    'adaptive_cases_with_added_points': sum(r['adaptive_added_frequency_count'] > 0 for r in rows),
    'mean_delta_dense_il_db': sum(r['delta_il_db'] for r in rows)/len(rows),
    'mean_evaluation_ratio': sum(r['adaptive_evaluations']/r['coarse_evaluations'] for r in rows)/len(rows),
    'population_comparison': population_rows,
    'interpretation': 'Small-budget diagnostic only; stochastic deltas are not performance claims.',
}
(out/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))
