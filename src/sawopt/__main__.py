import argparse, json, sys
from pathlib import Path

import yaml
import numpy as np

from .core.models import FilterDesign
from .io.config import load_experiment_config
from .optimization.runner import run, initialize, dense, save
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
    from .optimization.runner import rank
    resistance = min(coarse, key=rank)['rs']
    return np.arange(max(20, resistance - 10), min(200, resistance + 10) + 1e-9, step).tolist()


def _run_study(config_path, run_path, *, workers=None, resume=False,
               run_parallelism=False):
    """Dispatch a config-declared protocol through an explicit registry."""
    cfg = load_experiment_config(config_path)
    study = cfg.get('study', {})
    protocol = study.get('type') if isinstance(study, dict) else None
    protocol = protocol or cfg.get('study_type')
    registry = {
        'topology_screening': 'stage2',
        'stage2_joint_impedance': 'stage2',
        'convergence': 'convergence',
        'stage3_1_dms_convergence': 'convergence',
        'continuation': 'continuation',
        'stage3_2_dms_convergence': 'continuation',
        'optimizer_ab': 'optimizer_ab',
        'stage3_3_optimizer_ab': 'optimizer_ab',
        'search_efficiency': 'search_efficiency',
        'stage3_5_search_efficiency': 'search_efficiency',
        'stage3_5_phase_c_supplement': 'phase_c_supplement',
        'stage3_5_phase_c_final_confirmation': 'phase_c_final_confirmation',
        'stage3_5_lshade_matched_protocol_parity': 'matched_protocol_parity',
        'stage3_6_phase_c1_c2_gate2a': 'stage3_6_gate2a',
        'stage3_6_gate2a_final_confirmation': 'stage3_6_gate2a_final_confirmation',
        'stage3_6_gate2b_a_asymmetric_impedance': 'stage3_6_gate2b_a',
        'stage3_6_gate2b_b_asymmetric_impedance': 'stage3_6_gate2b_b',
        'stage3_6_gate2c_joint_impedance_dof_fast_screening': 'stage3_6_gate2c',
        'stage3_7_material_com_50ohm_sanity': 'stage3_7_material_com_sanity',
        'stage3_7b_literature_com_reconstruction': 'stage3_7b_literature_com_reconstruction',
        'stage3_7b_r1_normalized_literature_com_validation': 'stage3_7b_r1_normalized_literature_com_validation',
        'stage3_7b_r2_stage3_7c_literature_com_b28_fast_screen': 'stage3_7b_r2_stage3_7c_literature_com_b28_fast_screen',
        'stage3_7d_mlit_aperture_boundary_and_metadata': 'stage3_7d_mlit_aperture_boundary_and_metadata',
        'stage3_8_dual_material_dms_topology_fast_screen': 'stage3_8_dual_material_dms_topology_fast_screen',
        'stage3_8c_r1_geometry_gate': 'stage3_8c_r1_geometry_gate',
        'preproduction': 'preproduction',
        'stage3_3_1_preproduction': 'preproduction',
    }
    kind = registry.get(protocol)
    if kind is None:
        raise ValueError(
            f'Unknown study.type {protocol!r}; expected one of {sorted(set(registry))}'
        )
    if kind == 'stage2':
        from .studies.topology_screening import load_config, run_stage2
        return run_stage2(Path(run_path), load_config(config_path))
    if kind == 'convergence':
        from .studies.convergence import normalize_convergence_config, run_convergence
        return run_convergence(run_path, normalize_convergence_config(cfg))
    if kind == 'continuation':
        from .studies.continuation import normalize_convergence_config, run_stage32
        return run_stage32(run_path, normalize_convergence_config(cfg),
                           run_parallelism=run_parallelism)
    if kind == 'optimizer_ab':
        from .studies.optimizer_ab import normalize_convergence_config, run_stage33
        return run_stage33(run_path, normalize_convergence_config(cfg),
                           resume=resume, workers=workers,
                           run_parallelism=run_parallelism)
    if kind == 'search_efficiency':
        from .studies.search_efficiency import run_stage35
        return run_stage35(config_path, run_path, resume=resume)
    if kind == 'phase_c_supplement':
        from .studies.phase_c_supplement import run_phase_c_supplement
        return run_phase_c_supplement(config_path, run_path, resume=resume)
    if kind == 'phase_c_final_confirmation':
        from .studies.phase_c_final_confirmation import run_phase_c_final_confirmation
        return run_phase_c_final_confirmation(config_path, run_path, resume=resume)
    if kind == 'matched_protocol_parity':
        from .studies.matched_protocol_parity import run_matched_protocol_parity
        return run_matched_protocol_parity(config_path, run_path, resume=resume)
    if kind == 'stage3_6_gate2a':
        from .studies.stage3_6_gate2a import run_stage36_gate2a
        return run_stage36_gate2a(config_path, run_path, resume=resume)
    if kind == 'stage3_6_gate2a_final_confirmation':
        from .studies.stage3_6_gate2a_final_confirmation import run_stage36_gate2a_final_confirmation
        return run_stage36_gate2a_final_confirmation(config_path, run_path, resume=resume)
    if kind == 'stage3_6_gate2b_a':
        from .studies.stage3_6_gate2b_a import run_stage36_gate2b_a
        return run_stage36_gate2b_a(config_path, run_path, resume=resume)
    if kind == 'stage3_6_gate2b_b':
        from .studies.stage3_6_gate2b_b import run_stage36_gate2b_b
        return run_stage36_gate2b_b(config_path, run_path, resume=resume)
    if kind == 'stage3_6_gate2c':
        from .studies.stage3_6_gate2c import run_stage36_gate2c
        return run_stage36_gate2c(config_path, run_path, resume=resume)
    if kind == 'stage3_7_material_com_sanity':
        from .studies.stage3_7_material_com_sanity import run_stage37
        return run_stage37(config_path, run_path, resume=resume)
    if kind == 'stage3_7b_literature_com_reconstruction':
        from .studies.stage3_7b_literature_com_reconstruction import run_stage37b
        return run_stage37b(config_path, run_path, resume=resume)
    if kind == 'stage3_7b_r1_normalized_literature_com_validation':
        from .studies.stage3_7b_r1_normalized_literature_com_validation import run_stage37b_r1
        return run_stage37b_r1(config_path, run_path, resume=resume)
    if kind == 'stage3_7b_r2_stage3_7c_literature_com_b28_fast_screen':
        from .studies.stage3_7b_r2_stage3_7c_literature_com_b28_fast_screen import run_stage37b_r2_stage37c
        return run_stage37b_r2_stage37c(config_path, run_path, resume=resume)
    if kind == 'stage3_7d_mlit_aperture_boundary_and_metadata':
        from .studies.stage3_7d_mlit_aperture_boundary_and_metadata import run_stage37d
        return run_stage37d(config_path, run_path, resume=resume)
    if kind == 'stage3_8_dual_material_dms_topology_fast_screen':
        from .studies.stage3_8_dual_material_dms_topology_fast_screen import run_stage38
        return run_stage38(config_path, run_path, resume=resume)
    if kind == 'stage3_8c_r1_geometry_gate':
        from .studies.stage3_8c_r1_geometry_gate import run_stage38c_r1
        return run_stage38c_r1(config_path, run_path, resume=resume)
    from .studies.preproduction import run_preproduction
    return run_preproduction(config_path, run_path)


def main():
    p = argparse.ArgumentParser(description='Hypothetical COM impedance optimizer')
    p.add_argument('command', choices=['simulate', 'optimize', 'sweep', 'report',
                                       'run-study', 'stage3_3', 'stage3_3_1_preprod'])
    p.add_argument('--config', default='configs/base/b28_dms_baseline.yaml')
    p.add_argument('--run', default='runs/prototype')
    p.add_argument('--rs', type=float, default=50)
    p.add_argument('--rl', type=float, default=50)
    p.add_argument('--maxiter', type=int)
    p.add_argument('--refine-step', type=float)
    p.add_argument('--workers', type=int)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--run-parallelism-benchmark', action='store_true')
    args = p.parse_args()

    if args.command == 'run-study':
        print(json.dumps(_run_study(
            args.config, args.run, workers=args.workers, resume=args.resume,
            run_parallelism=args.run_parallelism_benchmark,
        ), ensure_ascii=False, indent=2))
        return

    if args.command == 'report':
        print(json.dumps({'report': report(args.run)}))
        return

    if args.command == 'stage3_3':
        from .studies.convergence import _load_config
        from .studies.optimizer_ab import run_stage33
        cfg = _load_config(args.config)
        print(json.dumps(run_stage33(args.run, cfg, resume=args.resume, workers=args.workers,
                                     run_parallelism=args.run_parallelism_benchmark),
                         ensure_ascii=False, indent=2))
        return

    if args.command == 'stage3_3_1_preprod':
        from .studies.preproduction import run_preproduction
        print(json.dumps(run_preproduction(args.config, args.run), ensure_ascii=False, indent=2))
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
