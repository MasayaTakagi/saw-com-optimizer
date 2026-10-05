"""Command-line entry points for the optimizer and current DMS study."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

from .core.models import FilterDesign
from .io.checkpoints import complete_study_run
from .io.config import load_experiment_config
from .io.legacy_lifecycle import legacy_process_disposition
from .optimization.runner import dense, initialize, run, save
from .reporting.report import report


def _refinement_points(command, step, records, configured_resistances):
    if command != "sweep":
        raise ValueError("--refine-step is only defined for symmetric impedance sweep mode")
    if not 2 <= step <= 5:
        raise ValueError("Refinement step must be 2..5 ohm")
    configured = {float(value) for value in configured_resistances}
    coarse = [
        record for record in records
        if float(record["rs"]) in configured and float(record["rl"]) == float(record["rs"])
    ]
    if not coarse:
        raise ValueError("No completed symmetric coarse sweep results available for refinement")
    from .optimization.runner import rank

    resistance = min(coarse, key=rank)["rs"]
    return np.arange(max(20, resistance - 10), min(200, resistance + 10) + 1e-9, step).tolist()


def _run_study(
    config_path, run_path, *, resume=False,
    stage4b_authorization_manifest=None,
    stage4c_authorization_manifest=None,
):
    cfg = load_experiment_config(config_path)
    study = cfg.get("study", {})
    protocol = study.get("type") if isinstance(study, dict) else None
    if protocol == "hybrid_stage4b_topology_comparison":
        if not stage4b_authorization_manifest:
            raise PermissionError("Stage 4B production requires a bound orchestration authorization manifest")
        from .studies.hybrid_stage4b import run_stage4b_production

        return run_stage4b_production(
            config_path, run_path, stage4b_authorization_manifest,
        )
    if protocol == "hybrid_stage4c_confirmatory":
        if not stage4c_authorization_manifest:
            raise PermissionError("Stage 4C production requires a bound orchestration authorization manifest")
        from .studies.hybrid_stage4c import run_stage4c_production

        return run_stage4c_production(
            config_path, run_path, stage4c_authorization_manifest,
        )
    if protocol == "postrun_workflow_qualification":
        from .studies.postrun_workflow_qualification import run_qualification_fixture

        return run_qualification_fixture(config_path, run_path)
    if protocol != "dms_topology_screening":
        raise ValueError(
            f"Unknown study.type {protocol!r}; expected 'dms_topology_screening', Stage 4B, or Stage 4C production"
        )
    from .studies.dms_topology_screening import run_dms_topology_screening

    return run_dms_topology_screening(config_path, run_path, resume=resume)


def main():
    parser = argparse.ArgumentParser(description="SAW COM impedance optimizer")
    parser.add_argument(
        "command", choices=["simulate", "optimize", "sweep", "report", "run-study", "stage4b-shakedown", "export-review"],
    )
    parser.add_argument("--config", default="configs/base/b28_dms_baseline.yaml")
    parser.add_argument("--run", default="runs/prototype")
    parser.add_argument("--rs", type=float, default=50)
    parser.add_argument("--rl", type=float, default=50)
    parser.add_argument("--maxiter", type=int)
    parser.add_argument("--refine-step", type=float)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--stage4b-authorization-manifest")
    parser.add_argument("--stage4c-authorization-manifest")
    parser.add_argument("--destination", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.command == "export-review":
        from .reporting.github_review import main as export_main

        export_args = ["--run", args.run]
        if args.destination:
            export_args.extend(["--destination", args.destination])
        export_main(export_args)
        return

    if args.command == "run-study":
        result = _run_study(
            args.config, args.run, resume=args.resume,
            stage4b_authorization_manifest=args.stage4b_authorization_manifest,
            stage4c_authorization_manifest=args.stage4c_authorization_manifest,
        )
        complete_study_run(
            args.run, result,
            disposition=legacy_process_disposition(args.run, return_code=0),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "stage4b-shakedown":
        from .studies.hybrid_stage4b import run_stage4b_shakedown

        result = run_stage4b_shakedown(args.config, args.run, resume=args.resume)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "report":
        print(json.dumps({"report": report(args.run)}))
        return

    path = Path(args.config)
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    com_path = path.parent / cfg["com_file"]
    cfg["com"] = yaml.safe_load(com_path.read_text(encoding="utf-8"))
    cfg["source_config_text"] = path.read_text(encoding="utf-8")
    cfg["source_com_text"] = com_path.read_text(encoding="utf-8")
    if args.maxiter is not None:
        cfg["optimizer"]["maxiter"] = args.maxiter
    if cfg["optimizer"]["workers"] != 1:
        raise ValueError("Prototype supports workers=1 only")
    if args.rs <= 0 or args.rl <= 0:
        raise ValueError("Positive real resistance required")

    cfg["command"] = args.command
    cfg["rs"] = args.rs
    cfg["rl"] = args.rl
    cfg["refine_step"] = args.refine_step
    out = initialize(args.run, cfg)
    (out / "input.yaml").write_text(cfg["source_config_text"], encoding="utf-8")
    (out / "com_input.yaml").write_text(cfg["source_com_text"], encoding="utf-8")

    if args.command == "simulate":
        frequencies, (result, network, simulation) = dense(FilterDesign(), cfg, args.rs, args.rl)
        save(out / "baseline.json", result)
        np.savez_compressed(
            out / "baseline.npz", frequencies_hz=frequencies,
            y=simulation.y_parameters, **network,
        )
        print(json.dumps(result))
        return

    use_neighbor = bool(cfg["optimizer"].get("use_neighbor_warm_start", True))
    run(
        out,
        cfg,
        [args.rs] if args.command == "optimize" else cfg["resistances"],
        args.rl if args.command == "optimize" else None,
        use_neighbor=use_neighbor,
    )
    if args.refine_step is not None:
        records = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in out.glob("R*_seed*.json")
            if ".checkpoint." not in path.name
        ]
        points = _refinement_points(args.command, args.refine_step, records, cfg["resistances"])
        run(out, cfg, points, use_neighbor=use_neighbor)
    print(json.dumps({"report": report(out)}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
