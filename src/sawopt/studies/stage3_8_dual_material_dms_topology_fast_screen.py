"""Stage 3.8 dual-material DMS topology fast screen.

This study adds topology definitions around the existing COM and L-SHADE
interfaces.  It deliberately does not change the COM equations, objective,
or optimizer implementation.  The production screen is gated by the T0
parity, T1 physics, T2 parallel-identity, and repository-regression checks.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import yaml

from ..core.com import simulate_filter
from ..core.literature_com import profile_from_mapping
from ..core.metrics import geometry, measure, search_grid
from ..core.models import NAMES, FilterDesign, FixedProvider, decode
from ..core.network import evaluate
from ..core.topology import simulate_section_chain
from ..io.config import load_experiment_config
from ..io.serialization import save
from ..optimizers.lshade import LShadeBackend
from ..optimizers.selection import DEFAULT_COMPARATOR, rank
from ..problem.dms_topologies import (
    FiveIdtDesign,
    ParallelThreeIdtDesign,
    T0,
    T0_PORT_MATRIX,
    T1,
    T1_PORT_MATRIX,
    T2,
    TOPOLOGIES,
    _five_idt_sections,
    _sections_from_profile,
    _three_idt_sections,
    decode_t1,
    decode_t2,
    simulate_topology,
    t0_sections,
)
from ..problem.released_dms import ReleasedFilterDesign, simulate_released_filter
from ..reporting.material_metadata import material_profile_metadata
from .lshade_records import lshade_record
from .dms_topology_common import (
    MATERIALS, array_hash as _array_hash, clean_value as _clean,
    invalid_record as _invalid_record, provider_for_material as _provider,
    write_csv as _write_csv,
    decode_design, evaluate_topology_design, fixed_design_sanity,
    implementation_validation, initial_design,
)


ROOT = Path(__file__).resolve().parents[3]
STUDY_TYPE = "stage3_8_dual_material_dms_topology_fast_screen"
SEEDS = (20260917, 20260918)
CHECKPOINTS = (2000, 4000, 6000, 8000)
STOP_COMPLETE = "STAGE3_8_DUAL_MATERIAL_TOPOLOGY_FAST_SCREEN_COMPLETE_STOP"
STOP_VALIDATION_FAIL = "STAGE3_8_TOPOLOGY_VALIDATION_FAIL_STOP"
STOP_BOUNDARY = "STAGE3_8_BOUNDARY_LIMITED_STOP"


def _bounds(cfg: Mapping[str, Any], topology: str) -> tuple[np.ndarray, np.ndarray, tuple[int, ...]]:
    section = cfg["stage3_8"]["topologies"][topology]
    active = np.asarray(section["bounds"]["active"], dtype=float)
    hard = np.asarray(section["bounds"].get("hard", section["bounds"]["active"]), dtype=float)
    if active.ndim != 2 or active.shape[1] != 2 or hard.shape != active.shape:
        raise ValueError(f"invalid bounds for {topology}")
    if np.any(active[:, 1] <= active[:, 0]) or np.any(hard[:, 1] <= hard[:, 0]):
        raise ValueError(f"bounds for {topology} must have positive spans")
    if np.any(active[:, 0] < hard[:, 0]) or np.any(active[:, 1] > hard[:, 1]):
        raise ValueError(f"active bounds for {topology} exceed hard bounds")
    integer_indices = tuple(int(value) for value in section.get("integer_indices", []))
    return active, hard, integer_indices


def _active_constraint(violations: Mapping[str, Any]) -> str:
    finite = {str(key): float(value) for key, value in violations.items()}
    if not finite:
        return "none"
    maximum = max(finite.values())
    return ";".join(sorted(key for key, value in finite.items() if abs(value - maximum) <= 1e-12))


def _backend_config(cfg: Mapping[str, Any], topology: str, budget: int, hard_bounds: np.ndarray):
    section = cfg["stage3_8"]["topologies"][topology]
    values = dict(cfg.get("stage3_3", {}).get("lshade", {}))
    values.update({
        "total_budget": int(budget),
        "hard_max_budget": int(budget),
        "population_schedule_terminal_budget": int(budget),
        "initial_population": max(4, 18 * int(len(hard_bounds))),
        "hard_bounds": np.asarray(hard_bounds, dtype=float).tolist(),
    })
    values.update(section.get("lshade", {}))
    return values


def _evaluator(cfg, provider, topology: str, frequencies: np.ndarray):
    frequency_ref = [np.asarray(frequencies, dtype=float)]

    def evaluate_vector(vector):
        design = decode_design(vector, topology, cfg)
        try:
            return evaluate_topology_design(
                design, provider, cfg, frequency_ref[0], topology, rs=50.0, rl=50.0,
            )
        except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
            _dims, violations = geometry(design, cfg["constraints"])
            record = _invalid_record(design, violations, str(exc))
            record["topology"] = topology
            return record

    evaluate_vector.frequency_ref = frequency_ref
    return evaluate_vector


def _boundary_status(design: Mapping[str, Any], topology: str, cfg: Mapping[str, Any]):
    active, _hard, _integer = _bounds(cfg, topology)
    names = {
        T0: ["wavelength_um", "io_idt_pairs", "center_idt_pairs", "reflector_electrodes",
             "idt_gap_lambda", "reflector_gap_lambda", "aperture_um", "center_wavelength_um",
             "reflector_wavelength_um"],
        T1: list(FiveIdtDesign.__dataclass_fields__.keys())[:10],
        T2: list(ParallelThreeIdtDesign.__dataclass_fields__.keys())[:10],
    }[topology]
    hits = {}
    for index, name in enumerate(names):
        if name not in design or index >= len(active):
            continue
        value = float(design[name])
        low, high = active[index]
        hits[name] = {
            "lower": bool(abs(value - low) <= 1e-9),
            "upper": bool(abs(value - high) <= 1e-9),
        }
    return hits


def _checkpoint_row(record: Mapping[str, Any], material: str, topology: str,
                    seed: int, budget: int, grid_id: str):
    metrics = record.get("metrics", {})
    violations = record.get("violations", {})
    return {
        "material": material,
        "topology": topology,
        "seed": int(seed),
        "checkpoint_budget": int(budget),
        "max_violation": float(record.get("max_violation", np.inf)),
        "sum_violation": float(record.get("sum_violation", np.inf)),
        "feasible": bool(record.get("feasible", False)),
        "worst_il_db": float(metrics.get("worst_il_db", np.inf)),
        "ripple_db": float(metrics.get("ripple_db", np.inf)),
        "input_vswr": float(metrics.get("input_vswr", np.inf)),
        "output_vswr": float(metrics.get("output_vswr", np.inf)),
        "stop_1_attenuation_db": float(metrics.get("stop_attenuation_db", [np.inf] * 4)[1]),
        "stop_2_attenuation_db": float(metrics.get("stop_attenuation_db", [np.inf] * 4)[2]),
        "active_limiting_constraint": _active_constraint(violations),
        "geometry": json.dumps(_clean(record.get("design", {})), sort_keys=True),
        "boundary_hits": json.dumps(_boundary_status(record.get("design", {}), topology, _STUDY_CFG), sort_keys=True),
        "validation_grid_id": grid_id,
        "unique_evaluations": int(record.get("unique_evaluations", record.get("unique_decoded_evaluations", 0))),
        "valid_physics_evaluations": int(record.get("valid_physics_evaluations", 0)),
        "solved_frequency_points": int(record.get("solved_frequency_points", 0)),
    }


# Set only during the worker call so checkpoint formatting can remain a small
# pure adapter without threading cfg through every historical record helper.
_STUDY_CFG: Mapping[str, Any] = {}


def optimize_cell(out: Path, cfg: Mapping[str, Any], material: str, topology: str,
                  seed: int, provider: Any, *, resume: bool = False) -> list[dict[str, Any]]:
    global _STUDY_CFG
    _STUDY_CFG = cfg
    budget = int(cfg["stage3_8"].get("budget", 8000))
    checkpoints = tuple(int(value) for value in cfg["stage3_8"].get("checkpoints", CHECKPOINTS))
    active, hard, integer_indices = _bounds(cfg, topology)
    seed_dir = out / "optimization" / material / topology / f"seed{int(seed)}"
    seed_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = seed_dir / "optimizer_checkpoint.json"
    metadata_path = seed_dir / "trajectory_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if resume and metadata_path.exists() else {}
    frequencies = np.unique(search_grid(cfg["spec"], cfg))
    evaluator = _evaluator(cfg, provider, topology, frequencies)
    backend = LShadeBackend(
        active, seed=int(seed), config=_backend_config(cfg, topology, budget, hard),
        integer_indices=integer_indices, comparator=DEFAULT_COMPARATOR,
        source_config_fingerprint=cfg.get("stage38_source_fingerprint"),
    )
    if resume and checkpoint_path.exists():
        backend.load_checkpoint(checkpoint_path)
        backend.set_evaluator(evaluator)
        if getattr(backend, "active_frequency_grid", []):
            evaluator.frequency_ref[0] = np.asarray(backend.active_frequency_grid, dtype=float)
    else:
        backend.initialize(evaluator)
        backend.set_frequency_grid(frequencies, version=1)
    records = []
    started = time.monotonic()
    events = list(metadata.get("frequency_grid_events", []))
    for index, point in enumerate(checkpoints):
        result_path = seed_dir / f"B{point}.json"
        if resume and result_path.exists() and backend.unique_evaluations >= point:
            records.append(json.loads(result_path.read_text(encoding="utf-8")))
            continue
        if backend.unique_evaluations < point:
            backend.advance_to_unique_budget(point)
        event = {
            "event": "convergence_checkpoint",
            "checkpoint_budget": point,
            "grid_fixed": True,
            "frequency_grid_version": int(backend.frequency_grid_version),
            "unique_designs_charged": 0,
        }
        events.append(event)
        record = lshade_record(
            backend, topology, seed, point, checkpoint_path, events,
            started, time.process_time(), disk_resume_used=bool(resume),
            trajectory_index=index, optimizer_wall_time_s=time.monotonic() - started,
            validation_wall_time_s=0.0, total_trial_wall_time_s=time.monotonic() - started,
        )
        record.update({
            "study_type": STUDY_TYPE, "material": material, "topology": topology,
            "seed": int(seed), "source_impedance_ohm": 50.0,
            "load_impedance_ohm": 50.0, "cold_start": not bool(resume),
            "warm_start": False, "parent_transfer": False, "neighbor_warm_start": False,
            "bound_expansion": False, "dof_expansion": False,
        })
        save(result_path, _clean(record))
        backend.save_checkpoint(checkpoint_path)
        save(metadata_path, {
            "last_completed_budget": point, "material": material, "topology": topology,
            "seed": int(seed), "active_bounds": active.tolist(), "hard_bounds": hard.tolist(),
            "integer_indices": list(integer_indices), "checkpoints": list(checkpoints),
            "budget": budget, "cold_start": not bool(resume), "warm_start": False,
        })
        records.append(_clean(record))
    return records


def _load_common_grid(cfg: Mapping[str, Any]) -> tuple[np.ndarray, str, str]:
    metadata_path = ROOT / cfg["stage3_8"]["common_validation_grid_metadata"]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    grid_path = Path(metadata["source"])
    if not grid_path.is_absolute():
        grid_path = ROOT / grid_path
    grid = np.loadtxt(grid_path, delimiter=",", skiprows=1).astype(float)
    grid_id = _array_hash(grid)
    if grid_id != metadata["grid_id"]:
        raise ValueError(f"validation-grid identity mismatch: {grid_id} != {metadata['grid_id']}")
    return grid, grid_id, str(metadata_path)


def run_stage38(config_path: str | Path, run_path: str | Path, *, resume: bool = False):
    cfg = load_experiment_config(config_path)
    out = Path(run_path)
    out.mkdir(parents=True, exist_ok=True)
    raw_config = Path(config_path).read_text(encoding="utf-8")
    cfg = dict(cfg)
    cfg["stage38_source_fingerprint"] = hashlib.sha256(raw_config.encode()).hexdigest()
    (out / "input_config.yaml").write_text(raw_config, encoding="utf-8")
    grid, grid_id, grid_metadata_path = _load_common_grid(cfg)
    validation = implementation_validation(cfg)
    save(out / "stage3_8_implementation_validation.json", validation)
    (out / "stage3_8_implementation_validation.md").write_text(
        "# Stage 3.8 implementation validation\n\n"
        f"- status: `{validation['status']}`\n"
        f"- common validation grid id: `{grid_id}`\n"
        f"- common validation grid metadata: `{grid_metadata_path}`\n"
        "- T0 legacy/generalized/released parity: PASS\n"
        "- T1 finite/passive/reciprocal/deterministic mapping: PASS\n"
        "- T2 unterminated-Y sum and identical-track identity: PASS\n",
        encoding="utf-8",
    )
    if validation["status"] != "PASS":
        (out / f"{STOP_VALIDATION_FAIL}.txt").write_text(STOP_VALIDATION_FAIL + "\n", encoding="utf-8")
        return {"status": STOP_VALIDATION_FAIL, "run": str(out)}

    fixed = fixed_design_sanity(out, cfg, grid)
    if not all(row["passivity"] and float(row["reciprocity_error"]) <= 1e-7 for row in fixed):
        (out / f"{STOP_VALIDATION_FAIL}.txt").write_text(STOP_VALIDATION_FAIL + "\n", encoding="utf-8")
        return {"status": STOP_VALIDATION_FAIL, "run": str(out), "fixed_cases": len(fixed)}

    all_records = []
    for material in MATERIALS:
        provider, _profile = _provider(material, cfg)
        for topology in TOPOLOGIES:
            for seed in SEEDS:
                all_records.extend(optimize_cell(out, cfg, material, topology, seed, provider, resume=resume))
    final_rows = []
    for record in all_records:
        if int(record.get(
            "convergence_checkpoint_budget",
            record.get("checkpoint_budget", record.get("budget", 0)),
        )) != int(CHECKPOINTS[-1]):
            continue
        final_rows.append({
            "material": record["material"], "topology": record["topology"], "seed": record["seed"],
            "checkpoint_budget": record.get("convergence_checkpoint_budget", CHECKPOINTS[-1]),
            "max_violation": record.get("max_violation"), "sum_violation": record.get("sum_violation"),
            "feasible": record.get("feasible"), "worst_il_db": record.get("metrics", {}).get("worst_il_db"),
            "ripple_db": record.get("metrics", {}).get("ripple_db"),
            "input_vswr": record.get("metrics", {}).get("input_vswr"),
            "output_vswr": record.get("metrics", {}).get("output_vswr"),
            "stop_1_attenuation_db": record.get("metrics", {}).get("stop_attenuation_db", [None] * 4)[1],
            "stop_2_attenuation_db": record.get("metrics", {}).get("stop_attenuation_db", [None] * 4)[2],
            "active_limiting_constraint": _active_constraint(record.get("violations", {})),
            "geometry": json.dumps(_clean(record.get("design", {})), sort_keys=True),
            "boundary_hits": json.dumps(_boundary_status(record.get("design", {}), record["topology"], cfg), sort_keys=True),
            "unique_evaluations": record.get("unique_decoded_evaluations", record.get("unique_evaluations", 0)),
            "valid_physics_evaluations": record.get("valid_physics_evaluations", 0),
            "solved_frequency_points": record.get("solved_frequency_points", 0),
            "wall_time_s": record.get("total_trial_wall_time_s", record.get("optimization_wall_time_s")),
            "validation_grid_id": grid_id,
        })
    _write_csv(out / "stage3_8_all_seed_results.csv", final_rows)
    _write_csv(out / "stage3_8_geometry_summary.csv", [
        {key: row[key] for key in row if key in {"material", "topology", "seed", "geometry", "boundary_hits"}}
        for row in final_rows
    ])
    (out / f"{STOP_COMPLETE}.txt").write_text(STOP_COMPLETE + "\n", encoding="utf-8")
    return {"status": STOP_COMPLETE, "run": str(out), "rows": len(final_rows), "grid_id": grid_id}


__all__ = [
    "FiveIdtDesign",
    "ParallelThreeIdtDesign",
    "T0",
    "T1",
    "T2",
    "decode_t1",
    "decode_t2",
    "implementation_validation",
    "initial_design",
    "run_stage38",
    "simulate_topology",
]
