"""Validate Stage 3.9B inputs and a short optimizer path without production launch."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

from sawopt.evaluation import search_grid
from sawopt.io.config import load_experiment_config
from sawopt.studies import dms_topology_screening as study
from sawopt.studies.dms_topology_common import fixed_design_sanity, implementation_validation


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "studies" / "stage3_9b_mlit_t1_50ohm_budget_extension.yaml"
OUTPUT = ROOT / "artifacts" / "review_bundles" / "stage3_9b_budget_extension_preflight"
MATERIAL = "MLIT"
TOPOLOGY = "T1_SYMMETRIC_5IDT"
SMOKE_BUDGET = 200


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    cfg = load_experiment_config(CONFIG)
    settings = cfg["dms_topology"]
    materials, topologies = study._selected_study_axes(cfg)
    if materials != (MATERIAL,) or topologies != (TOPOLOGY,):
        raise ValueError("Stage 3.9B must select only MLIT/T1")
    if float(settings.get("impedance_ohm", -1)) != 50.0:
        raise ValueError("Stage 3.9B must use the symmetric 50 ohm port cell")
    if int(settings["budget"]) != 16000 or tuple(settings["checkpoints"]) != tuple(range(2000, 16001, 2000)):
        raise ValueError("Stage 3.9B budget/checkpoint lattice does not match the approved plan")
    if tuple(settings["seeds"]) != (20260917, 20260918):
        raise ValueError("Stage 3.9B seed set differs from the approved plan")
    if settings.get("cold_start") is not True:
        raise ValueError("Stage 3.9B must explicitly use cold starts")
    if int(settings["population_schedule_terminal_budget"]) != 8000:
        raise ValueError("Stage 3.9B must preserve the 8k L-SHADE schedule horizon")

    common_grid, common_grid_id, metadata_path, grid_metadata = study._load_common_grid(cfg)
    search_frequencies = np.unique(search_grid(cfg["spec"], cfg))
    implementation = implementation_validation(cfg)
    if implementation.get("status") != "PASS":
        raise RuntimeError("COM implementation validation failed")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CONFIG, OUTPUT / CONFIG.name)
    _write_json(OUTPUT / "implementation_validation.json", implementation)
    known = study._known_design_preflight(
        cfg, search_frequencies, common_grid, materials=materials, topologies=topologies,
    )
    study._write_csv(OUTPUT / "known_design_preflight.csv", known)
    if len(known) != 1 or any(
        not row["search_metrics_finite"] or not row["common_metrics_finite"] or not row["geometry_valid"]
        for row in known
    ):
        raise RuntimeError("selected known-design preflight failed")

    fixed = fixed_design_sanity(
        OUTPUT, cfg, common_grid, materials=materials, topologies=topologies,
    )
    if len(fixed) != 1 or any(
        row["status"] != "PASS" or not row["passivity"]
        or float(row["reciprocity_error"]) > 1e-7
        for row in fixed
    ):
        raise RuntimeError("selected common-grid fixed-design sanity failed")

    _active, hard, _integer_indices = study.material_bounds(cfg, MATERIAL, TOPOLOGY)
    original_budget = int(settings["budget"])
    original_horizon = int(settings["population_schedule_terminal_budget"])
    smoke_cfg = copy.deepcopy(cfg)
    smoke_settings = smoke_cfg["dms_topology"]
    smoke_settings["budget"] = SMOKE_BUDGET
    smoke_settings["population_schedule_terminal_budget"] = SMOKE_BUDGET
    smoke_settings["checkpoints"] = [SMOKE_BUDGET]
    smoke_settings["initial_population"] = 180
    smoke_settings["initializer_reference_proposals"] = 0
    smoke_settings["distribution_bootstrap_replicates"] = 0
    population_size = study._population_size(smoke_cfg, TOPOLOGY, SMOKE_BUDGET, hard)
    if population_size != 180 or SMOKE_BUDGET <= population_size:
        raise RuntimeError("smoke budget does not cover one configured initial population plus trials")
    provider, _profile_metadata = study.provider_for_material(MATERIAL, smoke_cfg)
    smoke_dir = OUTPUT / "smoke"
    records, backend, counters, _sampling = study._optimize_cell(
        smoke_dir, smoke_cfg, MATERIAL, TOPOLOGY, 20260917, provider, search_frequencies,
        budget=SMOKE_BUDGET, checkpoints=(SMOKE_BUDGET,),
        fingerprint=hashlib.sha256(b"stage3_9b_preflight_smoke_only").hexdigest(),
        sampling_seed_data={}, max_attempts=10000, resume=False,
    )
    smoke_record = records[-1]
    smoke_counters = smoke_record.get("evaluation_counters", {})
    if backend.unique_evaluations < SMOKE_BUDGET or not smoke_record.get("metrics"):
        raise RuntimeError("short Stage 3.9B optimizer smoke test did not complete")

    extended_backend_config = study._backend_config(cfg, TOPOLOGY, original_budget, hard)
    if (
        extended_backend_config["total_budget"] != original_budget
        or extended_backend_config["hard_max_budget"] != original_budget
        or extended_backend_config["population_schedule_terminal_budget"] != original_horizon
    ):
        raise RuntimeError("Stage 3.9B production backend configuration changed during smoke test")
    summary = {
        "status": "PRELAUNCH_GATES_PASS",
        "production_run_launched": False,
        "implementation_validation": implementation["status"],
        "selected_cell": {"material": MATERIAL, "topology": TOPOLOGY},
        "impedance_ohm": 50.0,
        "seeds": list(settings["seeds"]),
        "cold_start": True,
        "warm_start": False,
        "parent_transfer": False,
        "neighbor_warm_start": False,
        "production_budget_per_seed": original_budget,
        "production_checkpoints": list(range(2000, original_budget + 1, 2000)),
        "population_schedule_terminal_budget": original_horizon,
        "common_validation_grid_id": common_grid_id,
        "common_validation_grid_sha256": grid_metadata["sha256"],
        "common_validation_grid_count": len(common_grid),
        "common_validation_grid_metadata_path": str(metadata_path),
        "search_frequency_count": len(search_frequencies),
        "search_frequency_sha256": hashlib.sha256(search_frequencies.tobytes()).hexdigest(),
        "known_design_preflight_rows": len(known),
        "fixed_design_sanity_rows": len(fixed),
        "smoke": {
            "budget": SMOKE_BUDGET,
            "initial_population": population_size,
            "unique_evaluations": backend.unique_evaluations,
            "evaluation_status": smoke_record.get("evaluation_status"),
            "max_violation": smoke_record.get("max_violation"),
            "objective_calls": smoke_counters.get("objective_calls"),
            "output_directory": str(smoke_dir),
        },
        "production_parity_gate": (
            "At 2k/4k/6k/8k compare initial samples, incumbent decoded designs, objective/components, "
            "population size and trajectory/cache evidence, and evaluation accounting against Stage 3.8C. "
            "Unexplained mismatch invalidates interpretation."
        ),
    }
    _write_json(OUTPUT / "preflight_summary.json", summary)
    print("PASS: implementation, known-design, fixed-design, grid identity, and short optimizer smoke gates")
    print(f"PASS: {common_grid_id}; {len(common_grid)} common-grid points; {len(search_frequencies)} search frequencies")
    print(f"PASS: {backend.unique_evaluations} smoke evaluations; production optimizer not launched")


if __name__ == "__main__":
    main()
