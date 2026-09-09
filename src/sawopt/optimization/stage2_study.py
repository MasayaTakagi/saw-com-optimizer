"""Fair Stage 2 topology/wiring and impedance study orchestration."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import yaml

from ..core.hybrid import TOPOLOGIES, response
from .hybrid_study import optimize_case, _dense_hybrid
from .study import initialize, rank, save


def _best(records):
    if not records:
        raise ValueError('No candidate results available')
    return min(records, key=rank)


def _pair_key(record):
    return record['topology'], record['wiring']


def _pair_results(records):
    grouped = {}
    for record in records:
        grouped.setdefault(_pair_key(record), []).append(record)
    return {pair: _best(values) for pair, values in grouped.items()}


def aggregate_pair_rank(records):
    """Aggregate all seed outcomes for one topology/wiring pair.

    Feasibility is deliberately the first criterion.  The remaining criteria
    use robust seed statistics so a single lucky low-budget seed cannot carry
    a pair whose median behavior is poor.
    """
    if not records:
        raise ValueError('No seed records available for pair aggregation')
    feasible = [bool(r.get('feasible', False)) for r in records]
    infeasible = [r for r in records if not r.get('feasible', False)]
    violations = [float(r.get('max_violation', 0.0)) for r in infeasible]
    sums = [float(sum(r.get('violations', {}).values())) for r in infeasible]
    ils = [float(r['metrics']['worst_il_db']) for r in records]
    best = min(records, key=rank)
    return (
        -float(sum(feasible)) / len(records),
        float(np.median(violations)) if violations else 0.0,
        float(np.percentile(violations, 75)) if violations else 0.0,
        float(np.median(sums)) if sums else 0.0,
        float(np.median(ils)),
        rank(best),
    )


def _aggregate_pair_results(records):
    grouped = {}
    for record in records:
        grouped.setdefault(_pair_key(record), []).append(record)
    return {pair: _best(values) for pair, values in grouped.items()}, grouped


def _select_pairs(pairs, grouped, keep_count, screening):
    ordered = sorted(pairs, key=lambda pair: aggregate_pair_rank(grouped[pair]))
    keep_count = min(len(ordered), int(keep_count))
    selected = ordered[:keep_count]
    tolerance = screening.get('cutoff_uncertainty', screening.get('cutoff_tolerance', 0.0))
    if isinstance(tolerance, bool):
        tolerance = 0.05 if tolerance else 0.0
    tolerance = float(tolerance)
    if tolerance <= 0 or keep_count >= len(ordered):
        return selected
    boundary = aggregate_pair_rank(grouped[selected[-1]])
    for pair in ordered[keep_count:]:
        score = aggregate_pair_rank(grouped[pair])
        if (score[0] == boundary[0] and
                abs(score[1] - boundary[1]) <= tolerance and
                abs(score[4] - boundary[4]) <= tolerance):
            selected.append(pair)
    return selected


def _run_pairs(out, cfg, z0, pairs, phase, iterations, parents=None, warm=None):
    results = []
    for topology, wiring in pairs:
        parent = (parents or {}).get((topology, wiring))
        starts = (warm or {}).get((topology, wiring), [])
        for seed in cfg['seeds']:
            results.append(optimize_case(
                out, cfg, topology, wiring, seed, phase, iterations,
                parent=parent, rs=z0, rl=z0, warm_starts=starts,
            ))
    return results


def successive_halving(out, cfg, z0):
    screening = cfg['screening']
    topologies = cfg.get('topologies', list(TOPOLOGIES))
    wirings = cfg['wirings']
    unknown = sorted(set(topologies) - set(TOPOLOGIES))
    if unknown:
        raise ValueError(f'Unknown topologies: {unknown}')
    pairs = [(topology, wiring) for topology in topologies for wiring in wirings]
    prefix = f'Z{z0:g}'

    low = _run_pairs(out, cfg, z0, pairs, prefix + '_low', int(screening['low_iterations']))
    low_best, low_grouped = _aggregate_pair_results(low)
    keep_count = max(1, int(math.ceil(len(pairs) * float(screening['keep_fraction']))))
    survivors = _select_pairs(pairs, low_grouped, keep_count, screening)

    medium = _run_pairs(
        out, cfg, z0, survivors, prefix + '_medium',
        int(screening['medium_iterations']), parents=low_best,
    )
    medium_best, medium_grouped = _aggregate_pair_results(medium)
    medium_keep = min(len(survivors), int(screening['medium_keep']))
    finalists = _select_pairs(survivors, medium_grouped, medium_keep, screening)

    refined = _run_pairs(
        out, cfg, z0, finalists, prefix + '_refine',
        int(screening['refine_iterations']), parents=medium_best,
    )
    refined_best, refined_grouped = _aggregate_pair_results(refined)
    latest = dict(low_best)
    latest.update(medium_best)
    latest.update(refined_best)
    save(out / f'{prefix}_selection.json', {
        'z0_ohm': z0,
        'all_pairs': [list(pair) for pair in pairs],
        'low_survivors': [list(pair) for pair in survivors],
        'finalists': [list(pair) for pair in finalists],
        'winner': min(refined_best.values(), key=rank)['result_file'] if refined_best else None,
        'policy': 'seed-aggregate dense/adaptive feasibility-first successive halving',
        'low_aggregate_rank': {f'{pair[0]}/{pair[1]}': aggregate_pair_rank(values)
                               for pair, values in low_grouped.items()},
        'medium_aggregate_rank': {f'{pair[0]}/{pair[1]}': aggregate_pair_rank(values)
                                  for pair, values in medium_grouped.items()},
        'refined_aggregate_rank': {f'{pair[0]}/{pair[1]}': aggregate_pair_rank(values)
                                   for pair, values in refined_grouped.items()},
    })
    return latest, finalists


def cold_confirm_pairs(out, cfg, z0, pairs):
    """Run optional fresh confirmations without parent or neighbor starts."""
    screening = cfg.get('screening', {})
    seeds = screening.get('cold_confirmation_seeds')
    if seeds is None:
        seeds = cfg.get('seeds', [])
    iterations = int(screening.get('cold_confirmation_iterations',
                                   screening.get('refine_iterations', 0)))
    records = []
    for topology, wiring in pairs:
        for seed in seeds:
            records.append(optimize_case(
                out, cfg, topology, wiring, int(seed), f'Z{z0:g}_cold_confirm',
                iterations, parent=None, rs=z0, rl=z0, warm_starts=None,
            ))
    return records


def neighbor_refinement(out, cfg, impedances, coarse, final_pairs):
    iterations = int(cfg['screening']['neighbor_iterations'])
    final = {}
    for index, z0 in enumerate(impedances):
        parents = {}
        warm = {}
        for pair in final_pairs:
            parents[pair] = coarse[z0][pair]
            starts = []
            for adjacent in (index - 1, index + 1):
                if 0 <= adjacent < len(impedances):
                    neighbor_z = impedances[adjacent]
                    if pair in coarse[neighbor_z]:
                        starts.append(coarse[neighbor_z][pair]['x'])
            warm[pair] = starts
        records = _run_pairs(
            out, cfg, z0, final_pairs, f'Z{z0:g}_neighbor', iterations,
            parents=parents, warm=warm,
        )
        refined = _pair_results(records)
        final[z0] = {
            pair: min((parents[pair], refined[pair]), key=rank)
            for pair in final_pairs
        }
        save(out / f'Z{z0:g}_final_selection.json', {
            '/'.join(pair): final[z0][pair]['result_file'] for pair in final_pairs
        })
    return final


def loading_only_control(out, cfg, impedances, final):
    reference_z = float(cfg.get('reference_impedance_ohm', 50.0))
    if reference_z not in final:
        raise ValueError('reference_impedance_ohm must be included in the impedance grid')
    reference = _best(list(final[reference_z].values()))
    rows = []
    for z0 in impedances:
        f, (result, net, y) = _dense_hybrid(
            reference['x'], reference['topology'], reference['wiring'], cfg, z0, z0,
        )
        tag = f'loading_control__R{z0:g}_L{z0:g}'
        np.savez_compressed(out / (tag + '.npz'), frequencies_hz=f, y=y, **net)
        result.update({
            'rs': z0, 'rl': z0, 'topology': reference['topology'],
            'wiring': reference['wiring'], 'reference_result': reference['result_file'],
            'response_file': tag + '.npz',
        })
        rows.append(result)
    save(out / 'loading_control.json', rows)
    return rows


def load_config(path):
    path = Path(path)
    study = yaml.safe_load(path.read_text(encoding='utf-8'))
    base = path.parent / study['base_config']
    cfg = yaml.safe_load(base.read_text(encoding='utf-8'))
    cfg.update(study)
    com = base.parent / cfg['com_file']
    cfg['com'] = yaml.safe_load(com.read_text(encoding='utf-8'))
    cfg['inputs'] = {p.name: p.read_text(encoding='utf-8') for p in (path, base, com)}
    cfg['study_type'] = 'stage2_joint_impedance'
    impedances = [float(z) for z in cfg['impedance_grid_ohm']]
    if not impedances or len(set(impedances)) != len(impedances):
        raise ValueError('impedance_grid_ohm must contain unique values')
    if any(not np.isfinite(z) or z <= 0 for z in impedances):
        raise ValueError('All impedances must be positive finite real values')
    cfg['impedance_grid_ohm'] = sorted(impedances)
    return cfg


def run_stage2(out, cfg):
    out = initialize(out, cfg)
    impedances = cfg['impedance_grid_ohm']
    coarse = {}
    finalists = {}
    # Independent pass: no impedance-neighbor candidate enters these runs.
    for z0 in impedances:
        coarse[z0], finalists[z0] = successive_halving(out, cfg, z0)

    # Use the union so each retained structural family receives the same
    # neighbor-refinement budget at every impedance, enabling fixed-family curves.
    final_pairs = sorted(set().union(*[set(values) for values in finalists.values()]))
    final = neighbor_refinement(out, cfg, impedances, coarse, final_pairs)
    control = loading_only_control(out, cfg, impedances, final)
    cold_confirmations = {}
    if cfg.get('screening', {}).get('cold_confirmation', False):
        for z0 in impedances:
            ordered = sorted(final[z0].items(), key=lambda item: rank(item[1]))
            pairs = [pair for pair, _record in ordered[:2]]
            cold_confirmations[z0] = [r['result_file'] for r in cold_confirm_pairs(out, cfg, z0, pairs)]
    save(out / 'stage2_summary.json', {
        'impedances_ohm': impedances,
        'final_pairs': [list(pair) for pair in final_pairs],
        'independent_pass': 'No cross-impedance warm starts',
        'neighbor_pass': 'Equal iteration budget; adjacent decoded designs added after independent pass; best of parent and refinement retained',
        'loading_control_count': len(control),
        'cold_confirmation': cold_confirmations,
    })
    from ..reporting.stage2_report import report
    return report(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='configs/studies/stage2_pilot.yaml')
    parser.add_argument('--run', default='runs/stage2-pilot')
    parser.add_argument('--report-only', action='store_true')
    args = parser.parse_args()
    if args.report_only:
        from ..reporting.stage2_report import report
        print(json.dumps({'report': report(args.run)}))
        return
    cfg = load_config(args.config)
    print(json.dumps({'report': run_stage2(Path(args.run), cfg)}), flush=True)


if __name__ == '__main__':
    main()
