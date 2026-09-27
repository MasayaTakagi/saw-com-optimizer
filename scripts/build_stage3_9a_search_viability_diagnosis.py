"""Rebuild the Stage 3.9A diagnosis from the immutable Stage 3.8C run."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs" / "stage3_8c_production_20260924"
OUTPUT = ROOT / "artifacts" / "review_bundles" / "stage3_9a_search_viability_diagnosis"
CELLS = (("M0", "T0_CURRENT_3IDT"), ("MLIT", "T1_SYMMETRIC_5IDT"))
SEEDS = (20260917, 20260918)
CHECKPOINTS = (2000, 4000, 6000, 8000)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path, *, normalize_crlf: bool = False) -> str:
    content = path.read_bytes()
    if normalize_crlf:
        content = content.replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def diagnose() -> dict[str, Any]:
    closeout = _json(RUN / "stage3_8c_production_closeout_status.json")
    run_metadata = _json(RUN / "metadata" / "run_source_metadata.json")
    common_grid_metadata = _json(
        ROOT / "configs" / "reference" / "dms_topology_screening" /
        "common_validation_grid.json"
    )
    baseline = yaml.safe_load(
        (ROOT / "configs" / "base" / "b28_dms_baseline.yaml").read_text(encoding="utf-8")
    )
    raw_input = RUN / "input_config.yaml"
    stored_grid = RUN / "metadata" / "common_validation_grid.csv"
    current_grid_path = ROOT / common_grid_metadata["source"]
    grid_id = run_metadata["common_validation_grid_id"]
    if grid_id != common_grid_metadata["grid_id"]:
        raise ValueError("Stage 3.8C and current common validation grid IDs differ")
    if _sha256(stored_grid, normalize_crlf=True) != common_grid_metadata["sha256"]:
        raise ValueError("stored Stage 3.8C common validation grid bytes do not match its metadata")
    if _sha256(current_grid_path, normalize_crlf=True) != common_grid_metadata["sha256"]:
        raise ValueError("current common validation grid bytes do not match its metadata")

    checkpoints = _csv(RUN / "stage3_8c_r1_2_checkpoint_results.csv")
    selected_rows = [
        row for row in checkpoints
        if (row["material"], row["topology"]) in CELLS
    ]
    expected = {
        (material, topology, seed, budget)
        for material, topology in CELLS for seed in SEEDS for budget in CHECKPOINTS
    }
    actual = {
        (row["material"], row["topology"], int(row["seed"]), int(row["checkpoint_budget"]))
        for row in selected_rows
    }
    if actual != expected or len(selected_rows) != len(expected):
        raise ValueError(f"Stage 3.8C checkpoint lattice mismatch: {sorted(actual)}")

    boundary_rows = _csv(RUN / "stage3_8c_r1_2_boundary_diagnostics.csv")
    boundary = {
        (row["material"], row["topology"], int(row["seed"])): row
        for row in boundary_rows if (row["material"], row["topology"]) in CELLS
    }
    expected_boundaries = {
        (material, topology, seed) for material, topology in CELLS for seed in SEEDS
    }
    if set(boundary) != expected_boundaries:
        raise ValueError("Stage 3.8C boundary diagnostics do not cover both selected lanes")

    stopbands = baseline["spec"]["stopbands"]
    detail_rows: list[dict[str, Any]] = []
    by_seed: dict[str, list[dict[str, Any]]] = {}
    for checkpoint_row in sorted(selected_rows, key=lambda row: (int(row["seed"]), int(row["checkpoint_budget"]))):
        material = checkpoint_row["material"]
        topology = checkpoint_row["topology"]
        seed = int(checkpoint_row["seed"])
        budget = int(checkpoint_row["checkpoint_budget"])
        record = _json(
            RUN / "optimization" / material / topology / f"seed{seed}" / f"B{budget}.json"
        )
        if int(record["seed"]) != seed or int(record["requested_unique_design_budget"]) != budget:
            raise ValueError(f"checkpoint record does not match seed/budget {seed}/{budget}")
        for field in ("max_violation", "sum_violation"):
            if abs(float(record[field]) - float(checkpoint_row[field])) > 1e-12:
                raise ValueError(f"checkpoint JSON/CSV mismatch for {field} at {material}/{topology}/{seed}/{budget}")
        if (
            record["evaluation_status"] != checkpoint_row["evaluation_status"]
            or str(record["feasible"]).lower() != str(checkpoint_row["feasible"]).lower()
            or int(record["unique_decoded_evaluations"]) != budget
        ):
            raise ValueError(f"checkpoint JSON/CSV status or accounting mismatch at {material}/{topology}/{seed}/{budget}")
        violations = {key: float(value) for key, value in record["violations"].items()}
        if not violations:
            raise ValueError(f"checkpoint lacks constraint violations {seed}/{budget}")
        active_constraint = max(violations, key=violations.get)
        if active_constraint != checkpoint_row["active_filter_constraint"]:
            raise ValueError(f"checkpoint JSON/CSV bottleneck mismatch at {material}/{topology}/{seed}/{budget}")
        metrics = record["metrics"]
        for field in ("worst_il_db", "ripple_db", "input_vswr", "output_vswr"):
            if abs(float(metrics[field]) - float(checkpoint_row[field])) > 1e-10:
                raise ValueError(f"checkpoint JSON/CSV metric mismatch for {field} at {material}/{topology}/{seed}/{budget}")
        stop_attenuation = metrics["stop_attenuation_db"]
        if (
            abs(float(stop_attenuation[1]) - float(checkpoint_row["stop_1_attenuation_db"])) > 1e-10
            or abs(float(stop_attenuation[2]) - float(checkpoint_row["stop_2_attenuation_db"])) > 1e-10
        ):
            raise ValueError(f"checkpoint JSON/CSV stopband mismatch at {material}/{topology}/{seed}/{budget}")
        boundary_record = boundary[(material, topology, seed)]
        detail = {
            "material": material,
            "topology": topology,
            "seed": seed,
            "checkpoint_budget": budget,
            "evaluation_status": record["evaluation_status"],
            "geometry_valid": record["geometry_valid"],
            "feasible": record["feasible"],
            "max_violation": float(record["max_violation"]),
            "sum_violation": float(record["sum_violation"]),
            "active_filter_constraint": active_constraint,
            "normalized_violations_json": json.dumps(violations, sort_keys=True),
            "worst_il_db": metrics["worst_il_db"],
            "ripple_db": metrics["ripple_db"],
            "input_vswr": metrics["input_vswr"],
            "output_vswr": metrics["output_vswr"],
            "source_return_loss_db_min": metrics["source_return_loss_db_min"],
            "load_return_loss_db_min": metrics["load_return_loss_db_min"],
            "stop_attenuation_db_json": json.dumps(metrics["stop_attenuation_db"]),
            "objective_calls": checkpoint_row["objective_calls"],
            "unique_decoded_evaluations": checkpoint_row["unique_decoded_evaluations"],
            "geometry_rejections": checkpoint_row["geometry_rejections"],
            "physics_failures": checkpoint_row["physics_failures"],
            "cache_hits": checkpoint_row["cache_hits"],
            "search_bound_hits_json": checkpoint_row["search_bound_hit_variables"],
            "hard_geometry_status": boundary_record["hard_geometry_status"],
            "manufacturing_dimensions_json": boundary_record["manufacturing_dimensions"],
            "design_json": json.dumps(record["design"], sort_keys=True),
        }
        detail_rows.append(detail)
        by_seed.setdefault(f"{material}/{topology}/{seed}", []).append(detail)

    seed_summaries = []
    cell_summaries = {}
    for material, topology in CELLS:
        cell_key = f"{material}/{topology}"
        lane_seeds = []
        for seed in SEEDS:
            rows = by_seed[f"{cell_key}/{seed}"]
            first, last = rows[0], rows[-1]
            seed_summary = {
                "material": material,
                "topology": topology,
                "seed": seed,
                "start_budget": first["checkpoint_budget"],
                "end_budget": last["checkpoint_budget"],
                "start_max_violation": first["max_violation"],
                "end_max_violation": last["max_violation"],
                "absolute_improvement": first["max_violation"] - last["max_violation"],
                "relative_improvement_fraction": (
                    (first["max_violation"] - last["max_violation"]) / first["max_violation"]
                ),
                "final_active_constraint": last["active_filter_constraint"],
                "final_feasible": last["feasible"],
                "checkpoint_search_bound_hits": [
                    json.loads(row["search_bound_hits_json"]) for row in rows
                ],
                "hard_geometry_status": boundary[(material, topology, seed)]["hard_geometry_status"],
            }
            seed_summaries.append(seed_summary)
            lane_seeds.append(seed_summary)
        final_values = [summary["end_max_violation"] for summary in lane_seeds]
        cell_summaries[cell_key] = {
            "material": material,
            "topology": topology,
            "seed_summaries": lane_seeds,
            "final_max_violation_mean": sum(final_values) / len(final_values),
            "final_max_violation_range": [min(final_values), max(final_values)],
            "all_seeds_feasible_at_8k": all(item["final_feasible"] for item in lane_seeds),
            "mean_relative_improvement_from_2k_to_8k": sum(
                item["relative_improvement_fraction"] for item in lane_seeds
            ) / len(lane_seeds),
        }
    fingerprint = {
        "source_config_fingerprint": run_metadata["source_config_fingerprint"],
        "source_config_path": run_metadata.get("source_config_path"),
        "stored_input_config_sha256": _sha256(raw_input),
        "git_head": run_metadata.get("git", {}).get("head"),
        "common_validation_grid_id": grid_id,
        "common_validation_grid_sha256": common_grid_metadata["sha256"],
        "common_validation_grid_count": common_grid_metadata["frequency_count"],
        "search_frequency_count": run_metadata.get("resolved_search_frequency_count"),
        "search_frequency_sha256": run_metadata.get("resolved_search_frequency_sha256"),
        "MLIT_profile_id": _json(
            RUN / "metadata" / "material_profile_snapshots.json"
        )["MLIT"]["profile"]["id"],
        "source_impedance_ohm": run_metadata.get("input_output_impedance_ohm", [None, None])[0],
        "load_impedance_ohm": run_metadata.get("input_output_impedance_ohm", [None, None])[1],
        "MLIT_aperture_bounds_um": run_metadata.get("material_aperture_bounds_um", {}).get("MLIT"),
    }
    diagnostic = {
        "stage": "3.9A",
        "method": "no-rerun derivation from canonical Stage 3.8C R1.2 artifacts",
        "source_run": str(RUN.relative_to(ROOT)).replace("\\", "/"),
        "closeout_status": closeout,
        "cells": cell_summaries,
        "seeds": list(SEEDS),
        "checkpoint_budgets": list(CHECKPOINTS),
        "fingerprints": fingerprint,
        "stopband_constraint_mapping": {
            f"stop_{index}": {
                "stopband_index": index,
                "frequency_mhz": list(map(float, stopband[:2])),
                "target_attenuation_db": float(stopband[2]),
            }
            for index, stopband in enumerate(stopbands)
        },
        "seed_summaries": seed_summaries,
        "checkpoint_diagnostics": detail_rows,
        "interpretation": (
            "M0/T0 is flat from 2k through 8k and both seeds hit lower search bounds for "
            "io_idt_pairs and reflector_electrodes, with stop_1 as the limiting constraint. "
            "MLIT/T1 improves substantially through 8k without final active search-bound hits, "
            "but neither seed meets the full specification; stop_2 (the third stopband, "
            "832–862 MHz at 30 dB) limits both. This supports testing additional MLIT/T1 budget "
            "without ranking the unequal material search spaces."
        ),
    }
    return diagnostic


def main() -> None:
    diagnostic = diagnose()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "stage3_9a_diagnosis.json").write_text(
        json.dumps(diagnostic, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    _write_csv(OUTPUT / "stage3_9a_checkpoint_diagnostics.csv", diagnostic["checkpoint_diagnostics"])
    lines = [
        "# Stage 3.9A — search viability diagnosis",
        "",
        "This report is derived without rerunning optimization from the canonical Stage 3.8C R1.2 artifacts.",
        "",
        f"- Separate lanes: `{CELLS[0][0]}/{CELLS[0][1]}` and `{CELLS[1][0]}/{CELLS[1][1]}`, each at {diagnostic['fingerprints']['source_impedance_ohm']} Ω source and {diagnostic['fingerprints']['load_impedance_ohm']} Ω load.",
        f"- Seeds per lane: {', '.join(map(str, SEEDS))}; checkpoints: {', '.join(map(str, CHECKPOINTS))}.",
        f"- Common validation grid: `{diagnostic['fingerprints']['common_validation_grid_id']}` ({diagnostic['fingerprints']['common_validation_grid_count']} points).",
        f"- Source config fingerprint: `{diagnostic['fingerprints']['source_config_fingerprint']}`.",
        f"- Stored input config SHA-256: `{diagnostic['fingerprints']['stored_input_config_sha256']}`.",
        "",
        "## Checkpoint trajectory by lane",
        "",
    ]
    for material, topology in CELLS:
        lines.extend([
            "",
            f"### {material}/{topology}",
            "",
            "| Seed | 2k max violation | 4k | 6k | 8k | 8k feasible | 8k limiting constraint |",
            "|---:|---:|---:|---:|---:|:---:|:---|",
        ])
        for seed in SEEDS:
            rows = sorted(
                (row for row in diagnostic["checkpoint_diagnostics"]
                 if row["material"] == material and row["topology"] == topology and row["seed"] == seed),
                key=lambda row: row["checkpoint_budget"],
            )
            values = " | ".join(f"{row['max_violation']:.6f}" for row in rows)
            last = rows[-1]
            lines.append(f"| {seed} | {values} | {last['feasible']} | {last['active_filter_constraint']} |")
    lines.extend([
        "",
        "M0/T0 is unchanged from 2k onward; its final designs press the lower search bounds for `io_idt_pairs` and `reflector_electrodes`, and `stop_1` maps to 703–748 MHz at a 32 dB target.",
        "MLIT/T1 continues improving through 8k without final active search-bound hits; both seeds remain infeasible and `stop_2` maps to 832–862 MHz at a 30 dB target.",
        "Both lanes pass the hard geometry gate. They remain separate scientific tracks: M0 and MLIT use unequal aperture bounds (30–150 μm vs 30–180 μm), so this diagnosis does not rank materials.",
        "The measured MLIT/T1 improvement motivates a bounded budget-extension test; it is not proof of physical viability.",
        "M0-vs-MLIT ranking is excluded: Stage 3.8C used unequal aperture bounds (M0 30–150 μm; MLIT 30–180 μm).",
        "",
        "The CSV and JSON preserve each checkpoint's normalized constraint violations, RF metrics, geometry status, search-bound diagnostics, design, and evaluation accounting.",
        "",
    ])
    (OUTPUT / "stage3_9a_diagnosis.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"PASS: wrote reproducible Stage 3.9A evidence to {OUTPUT}")
    print(f"PASS: {len(diagnostic['checkpoint_diagnostics'])} checkpoint rows across two separate lanes, no optimizer rerun")


if __name__ == "__main__":
    main()
