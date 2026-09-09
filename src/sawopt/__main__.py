import argparse, json, sys
from pathlib import Path

import yaml
import numpy as np

from .core.models import FilterDesign
from .optimization.study import run, initialize, dense, save
from .reporting.report import report


def _refinement_points(command, step, records, configured_resistances):
    if command != 'sweep':
        raise ValueError('--refine-step is only defined for symmetric impedance sweep mode')
    if not 2 <= step <= 5:
        raise ValueError('Refinement step must be 2..5 ohm')
    configured = {float(x) for x in configured_resistances}
    coarse = [
        record for record in records
        if float(record['rs']) in configured and float(record['rl']) == float(record['rs'])
    ]
    if not coarse:
        raise ValueError('No completed symmetric coarse sweep results available for refinement')
    from .optimization.study import rank
    resistance = min(coarse, key=rank)['rs']
    return np.arange(max(20, resistance - 10), min(200, resistance + 10) + 1e-9, step).tolist()


def main():
    p = argparse.ArgumentParser(description='Hypothetical COM impedance optimizer')
    p.add_argument('command', choices=['simulate', 'optimize', 'sweep', 'report'])
    p.add_argument('--config', default='configs/base/b28_dms_baseline.yaml')
    p.add_argument('--run', default='runs/prototype')
    p.add_argument('--rs', type=float, default=50)
    p.add_argument('--rl', type=float, default=50)
    p.add_argument('--maxiter', type=int)
    p.add_argument('--refine-step', type=float)
    args = p.parse_args()

    if args.command == 'report':
        print(json.dumps({'report': report(args.run)}))
        return

    path = Path(args.config)
    cfg = yaml.safe_load(path.read_text(encoding='utf-8'))
    com_path = path.parent / cfg['com_file']
    cfg['com'] = yaml.safe_load(com_path.read_text(encoding='utf-8'))
    cfg['source_config_text'] = path.read_text(encoding='utf-8')
    cfg['source_com_text'] = com_path.read_text(encoding='utf-8')
    if args.maxiter is not None:
        cfg['optimizer']['maxiter'] = args.maxiter
    if cfg['optimizer']['workers'] != 1:
        raise ValueError('Prototype supports workers=1 only')
    if args.rs <= 0 or args.rl <= 0:
        raise ValueError('Positive real resistance required')

    cfg['command'] = args.command
    cfg['rs'] = args.rs
    cfg['rl'] = args.rl
    cfg['refine_step'] = args.refine_step
    out = initialize(args.run, cfg)
    (out / 'input.yaml').write_text(cfg['source_config_text'], encoding='utf-8')
    (out / 'com_input.yaml').write_text(cfg['source_com_text'], encoding='utf-8')

    if args.command == 'simulate':
        f, (r, net, sim) = dense(FilterDesign(), cfg, args.rs, args.rl)
        save(out / 'baseline.json', r)
        np.savez_compressed(out / 'baseline.npz', frequencies_hz=f, y=sim.y_parameters, **net)
        print(json.dumps(r))
        return

    use_neighbor = bool(cfg['optimizer'].get('use_neighbor_warm_start', True))
    run(
        out,
        cfg,
        [args.rs] if args.command == 'optimize' else cfg['resistances'],
        args.rl if args.command == 'optimize' else None,
        use_neighbor=use_neighbor,
    )

    if args.refine_step is not None:
        records = [
            json.loads(q.read_text())
            for q in out.glob('R*_seed*.json')
            if '.checkpoint.' not in q.name
        ]
        points = _refinement_points(args.command, args.refine_step, records, cfg['resistances'])
        run(out, cfg, points, use_neighbor=use_neighbor)

    print(json.dumps({'report': report(out)}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
