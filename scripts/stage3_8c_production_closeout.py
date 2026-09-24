"""Re-audit and close out existing Stage 3.8C Production artifacts.

This tool is report-only: it reads an already completed production run and
never invokes the optimizer or COM/physics solver.
"""
from __future__ import annotations

import csv
import difflib
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sawopt.studies.stage3_8c_r1_geometry_gate import _audit_counter_accounting_rows  # noqa: E402

RUN_REL = Path("runs/stage3_8c_production_20260924")
CONFIRMATION_REL = Path("runs/stage3_8c_r1_2_final_confirmation_20260924")
ORIGINAL_BUNDLE_REL = Path("artifacts/review_bundles/stage3_8c_production_review")
CORRECTED_BUNDLE_NAME = "stage3_8c_production_closeout_corrected_review"
RESULT_COPIES = {
    "stage3_8c_r1_2_all_seed_results.csv": (
        "stage3_8c_production_results.csv", "stage3_8c_all_seed_results.csv",
    ),
    "stage3_8c_r1_2_counter_accounting.csv": ("stage3_8c_counter_accounting.csv",),
    "stage3_8c_r1_2_validated_responses.csv": ("stage3_8c_validated_responses.csv",),
    "stage3_8c_r1_2_boundary_diagnostics.csv": ("stage3_8c_boundary_diagnostics.csv",),
    "stage3_8c_seed_comparison.csv": ("stage3_8c_seed_comparison.csv",),
}
METRIC_FIELDS = (
    "search_max_violation", "search_sum_violation", "search_worst_il_db",
    "search_ripple_db", "search_input_vswr", "search_output_vswr",
    "common_grid_max_violation", "common_grid_sum_violation",
    "common_grid_worst_il_db", "common_grid_ripple_db",
    "common_grid_input_vswr", "common_grid_output_vswr",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def _is_true(value: Any) -> bool:
    return value is True or str(value).strip().lower() == "true"


def _finite_row(row: dict[str, str]) -> bool:
    try:
        if not _is_true(row.get("finite_search_metrics")) or not _is_true(row.get("finite_common_metrics")):
            return False
        if not all(math.isfinite(float(row[name])) for name in METRIC_FIELDS):
            return False
        stop = json.loads(row["common_grid_stop_attenuation_db"])
        return isinstance(stop, list) and all(math.isfinite(float(value)) for value in stop)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    return completed.stdout.strip()


def _verify_manifest(directory: Path) -> list[str]:
    manifest_path = directory / "bundle_manifest.json"
    manifest = _read_json(manifest_path)
    errors = []
    for relative, expected_hash in manifest.get("files", {}).items():
        path = directory / relative
        if not path.is_file() or _sha256(path) != expected_hash:
            errors.append(relative)
    return errors


def _build_audit() -> dict[str, Any]:
    run = ROOT / RUN_REL
    confirmation = ROOT / CONFIRMATION_REL
    original_bundle = ROOT / ORIGINAL_BUNDLE_REL
    config_path = ROOT / "configs/studies/stage3_8c_r1_2_production.yaml"
    freeze_path = ROOT / "reports/stage3_8c_r1_2_final_confirmation_source_freeze.json"
    test_summary_path = ROOT / "reports/stage3_8c_production_closeout_test_summary.md"
    required_paths = (
        run / "metadata/run_source_metadata.json", run / "input_config.yaml",
        run / "stage3_8c_r1_2_all_seed_results.csv",
        run / "stage3_8c_r1_2_counter_accounting.csv",
        run / "stage3_8c_r1_2_checkpoint_results.csv",
        run / "stage3_8c_r1_2_fixed_design_sanity.csv",
        confirmation / "stage3_8c_r1_2_final_confirmation_gate.json",
        freeze_path, config_path, test_summary_path,
        original_bundle / "bundle_manifest.json",
    )
    missing = [str(path.relative_to(ROOT)) for path in required_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"required closeout inputs missing: {missing}")

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    settings = config["stage3_8"]
    materials = tuple(settings["materials"])
    topologies = tuple(settings["topologies"])
    seeds = tuple(map(int, settings["seeds"]))
    checkpoints = tuple(map(int, settings["checkpoints"]))
    budget = int(settings["budget"])
    expected_runs = len(materials) * len(topologies) * len(seeds)
    expected_evaluations = budget * expected_runs

    source = _read_json(run / "metadata/run_source_metadata.json")
    final_gate = _read_json(confirmation / "stage3_8c_r1_2_final_confirmation_gate.json")
    initial_gate = _read_json(run / "stage3_8c_production_gate.json")
    freeze = _read_json(freeze_path)
    results = _read_csv(run / "stage3_8c_r1_2_all_seed_results.csv")
    counters = _read_csv(run / "stage3_8c_r1_2_counter_accounting.csv")
    checkpoint_rows = _read_csv(run / "stage3_8c_r1_2_checkpoint_results.csv")
    fixed_rows = _read_csv(run / "stage3_8c_r1_2_fixed_design_sanity.csv")

    counter_gate = _audit_counter_accounting_rows(
        counters, materials=materials, topologies=topologies,
        seeds=seeds, checkpoints=checkpoints,
    )
    expected_result_keys = {
        (material, topology, seed)
        for material in materials for topology in topologies for seed in seeds
    }
    expected_checkpoint_keys = {
        (material, topology, seed, checkpoint)
        for material in materials for topology in topologies
        for seed in seeds for checkpoint in checkpoints
    }
    result_keys = []
    result_rows_valid = True
    for row in results:
        try:
            key = (row["material"], row["topology"], int(row["seed"]))
            result_keys.append(key)
            result_rows_valid &= (
                row["run_status"] == "VALID_RUN"
                and int(row["unique_decoded_evaluations"]) == budget
                and int(row["physics_failures"]) == 0
                and _finite_row(row)
            )
        except (KeyError, TypeError, ValueError):
            result_rows_valid = False
    result_counts: dict[tuple[str, str, int], int] = {}
    for key in result_keys:
        result_counts[key] = result_counts.get(key, 0) + 1
    result_identity_pass = (
        len(results) == expected_runs
        and len(result_keys) == len(expected_result_keys)
        and set(result_keys) == expected_result_keys
        and all(count == 1 for count in result_counts.values())
    )
    checkpoint_keys = []
    checkpoint_rows_valid = True
    for row in checkpoint_rows:
        try:
            key = (row["material"], row["topology"], int(row["seed"]), int(row["checkpoint_budget"]))
            checkpoint_keys.append(key)
            numeric = ("unique_decoded_evaluations", "max_violation", "sum_violation",
                       "worst_il_db", "ripple_db", "input_vswr", "output_vswr")
            checkpoint_rows_valid &= (
                row.get("evaluation_status") == "PHYSICS_EVALUATED"
                and _is_true(row.get("geometry_valid"))
                and int(row["unique_decoded_evaluations"]) == key[3]
                and all(math.isfinite(float(row[name])) for name in numeric)
            )
        except (KeyError, TypeError, ValueError):
            checkpoint_rows_valid = False
    checkpoint_key_counts: dict[tuple[str, str, int, int], int] = {}
    for key in checkpoint_keys:
        checkpoint_key_counts[key] = checkpoint_key_counts.get(key, 0) + 1
    checkpoint_results_pass = (
        len(checkpoint_rows) == len(expected_checkpoint_keys)
        and len(checkpoint_keys) == len(expected_checkpoint_keys)
        and set(checkpoint_keys) == expected_checkpoint_keys
        and all(count == 1 for count in checkpoint_key_counts.values())
        and checkpoint_rows_valid
    )
    valid_runs = [row for row in results if row.get("run_status") == "VALID_RUN"]
    completed_evaluations = sum(int(row.get("unique_decoded_evaluations", 0)) for row in valid_runs)
    cells_completed = sum(
        all((material, topology, seed) in result_counts for seed in seeds)
        and all(result_counts.get((material, topology, seed), 0) == 1 for seed in seeds)
        for material in materials for topology in topologies
    )
    seed_runs_completed = sum(
        result_counts.get(key, 0) == 1 and any(
            row.get("material") == key[0] and row.get("topology") == key[1]
            and int(row.get("seed", -1)) == key[2] and row.get("run_status") == "VALID_RUN"
            for row in results
        )
        for key in expected_result_keys
    )
    physics_failures = sum(int(row.get("physics_failures", 0)) for row in results)

    grid_id = source.get("common_validation_grid_id")
    common_grid_pass = len(results) == expected_runs and all(
        row.get("common_grid_status") == "PHYSICS_EVALUATED"
        and _is_true(row.get("common_grid_geometry_valid"))
        and row.get("common_validation_grid_id") == grid_id
        and _is_true(row.get("finite_common_metrics"))
        for row in results
    )
    finite_metrics_pass = len(results) == expected_runs and all(_finite_row(row) for row in results)
    fixed_sanity_pass = len(fixed_rows) == len(materials) * len(topologies) and all(
        row.get("status") == "PASS"
        and _is_true(row.get("passivity"))
        and math.isfinite(float(row.get("reciprocity_error", "nan")))
        and float(row["reciprocity_error"]) <= 1e-7
        and row.get("grid_id") == grid_id
        for row in fixed_rows
    )
    fingerprint_values = {
        source.get("source_config_fingerprint"),
        final_gate.get("final_confirmation_fingerprint"),
        final_gate.get("production_candidate_fingerprint"),
        initial_gate.get("source_config_fingerprint"),
        freeze.get("source_config_fingerprint"),
        freeze.get("production_candidate_fingerprint"),
    }
    result_fingerprints = {row.get("source_config_fingerprint") for row in results}
    fingerprint_match = len(fingerprint_values) == 1 and None not in fingerprint_values and result_fingerprints == fingerprint_values
    config_freeze_hash = freeze.get("sha256_files", {}).get("configs/studies/stage3_8c_r1_2_production.yaml")
    config_hash_match = (
        config_freeze_hash is not None
        and _sha256(config_path) == config_freeze_hash
        and _sha256(run / "input_config.yaml") == config_freeze_hash
    )
    snapshot_map = {
        "src/sawopt/studies/stage3_8c_r1_geometry_gate.py": "source_snapshot/src/sawopt/studies/stage3_8c_r1_geometry_gate.py",
        "src/sawopt/studies/stage3_8_dual_material_dms_topology_fast_screen.py": "source_snapshot/src/sawopt/studies/stage3_8_dual_material_dms_topology_fast_screen.py",
        "configs/studies/stage3_8c_r1_2_production.yaml": "source_snapshot/configs/studies/stage3_8c_r1_2_production.yaml",
    }
    source_snapshot_match = all(
        key in freeze.get("sha256_files", {})
        and (original_bundle / relative).is_file()
        and _sha256(original_bundle / relative) == freeze["sha256_files"][key]
        for key, relative in snapshot_map.items()
    )
    final_confirmation_pass = (
        final_gate.get("status") == "PASS"
        and all(final_gate.get("gates", {}).values())
        and source.get("source_config_fingerprint") == final_gate.get("final_confirmation_fingerprint")
    )
    original_bundle_errors = _verify_manifest(original_bundle)
    initial_gate_cause_confirmed = (
        initial_gate.get("status") == "FAILED"
        and initial_gate.get("failures") == ["production counter accounting failed"]
        and int(initial_gate.get("completed_evaluations", -1)) == expected_evaluations
        and int(initial_gate.get("cells_completed", -1)) == len(materials) * len(topologies)
        and int(initial_gate.get("seed_runs_completed", -1)) == expected_runs
        and int(initial_gate.get("physics_failures", -1)) == 0
    )
    result_copy_hashes = {}
    result_copy_match = True
    missing_result_bundle_copies = []
    for run_name, bundle_names in RESULT_COPIES.items():
        run_file = run / run_name
        if not run_file.is_file():
            result_copy_match = False
            continue
        result_copy_hashes[run_name] = _sha256(run_file)
        for bundle_name in bundle_names:
            candidate = original_bundle / bundle_name
            if not candidate.is_file():
                missing_result_bundle_copies.append(bundle_name)
            else:
                result_copy_match &= _sha256(candidate) == _sha256(run_file)

    failures = []
    if not counter_gate["passed"]:
        failures.append("checkpoint counter accounting incomplete or inconsistent")
    if not checkpoint_results_pass:
        failures.append("checkpoint result rows are missing, duplicated, invalid, or non-finite")
    if not initial_gate_cause_confirmed:
        failures.append("initial FAILED status has causes beyond the confirmed counter-row gate bug")
    if not result_identity_pass or not result_rows_valid:
        failures.append("production per-seed result rows are missing, duplicated, invalid, or non-finite")
    if completed_evaluations != expected_evaluations:
        failures.append(f"evaluations {completed_evaluations}/{expected_evaluations}")
    if cells_completed != len(materials) * len(topologies):
        failures.append(f"cells {cells_completed}/{len(materials) * len(topologies)}")
    if seed_runs_completed != expected_runs:
        failures.append(f"seed runs {seed_runs_completed}/{expected_runs}")
    if physics_failures != 0:
        failures.append(f"physics failures {physics_failures}")
    if not finite_metrics_pass:
        failures.append("finite production metrics check failed")
    if not common_grid_pass:
        failures.append("common-grid validation failed")
    if not fixed_sanity_pass:
        failures.append("fixed-design sanity failed")
    if not fingerprint_match or not config_hash_match or not source_snapshot_match:
        failures.append("recorded source/config fingerprint or frozen source snapshot mismatch")
    if not final_confirmation_pass:
        failures.append("Final Confirmation gate is not PASS")
    if original_bundle_errors or not result_copy_match:
        failures.append("original review bundle manifest or result-copy integrity failed")

    medians = {}
    for material in materials:
        for topology in topologies:
            values = [float(row["common_grid_max_violation"]) for row in results
                      if row.get("material") == material and row.get("topology") == topology]
            if len(values) == len(seeds):
                medians[f"{material}/{topology}"] = statistics.median(values)
    all_candidates_infeasible = bool(results) and all(
        float(row["common_grid_max_violation"]) > 0 for row in results
    )

    gate = {
        "schema_version": 1,
        "study_revision": "R1.2",
        "mode": "production",
        "status": "COMPLETED" if not failures else "FAILED",
        "closeout_status": "PASS" if not failures else "FAIL",
        "run_dir": str(run),
        "canonical_results_reused": True,
        "optimizer_rerun_performed": False,
        "physics_recomputed": False,
        "historical_initial_status": initial_gate.get("status"),
        "historical_initial_failure": initial_gate.get("failures", []),
        "historical_failure_cause_confirmed_as_counter_row_bug": initial_gate_cause_confirmed,
        "source_config_fingerprint": source.get("source_config_fingerprint"),
        "final_confirmation_fingerprint": final_gate.get("final_confirmation_fingerprint"),
        "source_config_fingerprint_match": fingerprint_match and config_hash_match and source_snapshot_match,
        "common_validation_grid_id": grid_id,
        "expected_evaluations": expected_evaluations,
        "completed_evaluations": completed_evaluations,
        "cells_completed": cells_completed,
        "cells_total": len(materials) * len(topologies),
        "seed_runs_completed": seed_runs_completed,
        "seed_runs_total": expected_runs,
        "checkpoint_budgets": list(checkpoints),
        "counter_accounting_expected_rows": counter_gate["expected_rows"],
        "counter_accounting_actual_rows": counter_gate["actual_rows"],
        "counter_accounting_rows_passed": counter_gate["actual_rows"] if counter_gate["passed"] else 0,
        "counter_accounting": counter_gate,
        "checkpoint_result_rows_passed": checkpoint_results_pass,
        "checkpoint_result_rows": len(checkpoint_rows),
        "physics_failures": physics_failures,
        "finite_production_metrics_passed": finite_metrics_pass,
        "common_grid_validation_passed": common_grid_pass,
        "fixed_design_sanity_passed": fixed_sanity_pass,
        "all_candidates_filter_feasible": not all_candidates_infeasible,
        "median_common_grid_max_violation_by_material_topology": medians,
        "final_confirmation_passed": final_confirmation_pass,
        "original_review_bundle_integrity_passed": not original_bundle_errors,
        "production_result_copy_integrity_passed": result_copy_match,
        "missing_result_copies_added_from_canonical_run": missing_result_bundle_copies,
        "stage3_9_started": False,
        "failures": failures,
    }
    return {
        "run": run, "confirmation": confirmation, "original_bundle": original_bundle,
        "config_path": config_path, "config": config, "freeze": freeze, "source": source,
        "initial_gate": initial_gate, "final_gate": final_gate, "results": results,
        "counters": counters, "checkpoint_rows": checkpoint_rows, "fixed_rows": fixed_rows,
        "counter_gate": counter_gate, "gate": gate, "failures": failures,
        "fingerprint_match": fingerprint_match, "config_hash_match": config_hash_match,
        "source_snapshot_match": source_snapshot_match,
        "original_bundle_errors": original_bundle_errors,
        "result_copy_match": result_copy_match, "result_copy_hashes": result_copy_hashes,
        "medians": medians, "all_candidates_infeasible": all_candidates_infeasible,
        "cells_completed": cells_completed, "expected_runs": expected_runs,
        "expected_evaluations": expected_evaluations,
        "completed_evaluations": completed_evaluations,
        "seed_runs_completed": seed_runs_completed, "physics_failures": physics_failures,
        "finite_metrics_pass": finite_metrics_pass, "common_grid_pass": common_grid_pass,
        "fixed_sanity_pass": fixed_sanity_pass, "grid_id": grid_id,
        "materials": materials, "topologies": topologies, "seeds": seeds,
        "checkpoints": checkpoints, "budget": budget,
    }


def _summary(audit: dict[str, Any]) -> str:
    gate = audit["gate"]
    config = audit["config"]
    apertures = {
        material: config["stage3_8"]["materials"][material]["aperture_bounds_um"]
        for material in audit["materials"]
    }
    pretty = {
        "T0_CURRENT_3IDT": "T0",
        "T1_SYMMETRIC_5IDT": "T1",
        "T2_PARALLEL_3IDT_X2": "T2",
    }
    rows = []
    for material in audit["materials"]:
        for topology in audit["topologies"]:
            median = audit["medians"].get(f"{material}/{topology}")
            rows.append(f"| {material} | {pretty.get(topology, topology)} | {median:.6f} |")
    return f"""# Stage 3.8C Production Closeout Summary

## Corrected closeout

- Corrected Production status: **{gate['status']}**.
- Initial closeout status: **FAILED** because the counter gate expected 12 seed-run rows instead of 48 checkpoint rows.
- Corrected counter accounting: **{gate['counter_accounting_rows_passed']} / {gate['counter_accounting_expected_rows']} checkpoint rows PASS**; expected budgets are {', '.join(map(str, audit['checkpoints']))} for each of {audit['expected_runs']} seed runs.
- 96k optimizer/physics rerun: **NOT PERFORMED**; canonical existing results were retained.
- Evaluations: **{gate['completed_evaluations']} / {gate['expected_evaluations']}**.
- Cells: **{gate['cells_completed']} / {gate['cells_total']}**; seed runs: **{gate['seed_runs_completed']} / {gate['seed_runs_total']}**.
- Physics failures: **{gate['physics_failures']}**.
- Source/config fingerprint: **{'MATCH' if gate['source_config_fingerprint_match'] else 'MISMATCH'}** — `{gate['source_config_fingerprint']}`.
- Finite metrics: **{'PASS' if gate['finite_production_metrics_passed'] else 'FAIL'}**; common-grid validation: **{'PASS' if gate['common_grid_validation_passed'] else 'FAIL'}**; fixed-design sanity: **{'PASS' if gate['fixed_design_sanity_passed'] else 'FAIL'}**.
- Final Confirmation: **{'PASS' if gate['final_confirmation_passed'] else 'FAIL'}**; common validation grid: `{gate['common_validation_grid_id']}`.

## Performance interpretation

All production seed runs completed and yielded finite common-grid metrics, but **no candidate filter-feasible design was obtained**. Median common-grid maximum violation across the two seeds:

| Material | Topology | Median maximum violation |
|---|---:|---:|
{chr(10).join(rows)}

- M0 T0 had the lowest violation in this screen. M0 uses a hypothetical COM profile and shows active search-bound activity; T1 and T2 remain screening observations, not proof of absolute topology superiority.
- For the literature-profile MLIT material, T1 is the primary DMS candidate from this screen. T2 remains a secondary, unresolved candidate because improvement continued through the 8k checkpoints; T2 is not dropped.
- The material search spaces differ: M0 aperture {apertures['M0'][0]}–{apertures['M0'][1]} µm; MLIT aperture {apertures['MLIT'][0]}–{apertures['MLIT'][1]} µm. Their COM provenance also differs, so these results do not support direct material superiority claims.

## Stage disposition

Stage 3.8 successfully identified topology trends, but did not produce a fully filter-feasible final B28 design. Stage 3.8 is ready for closeout review as a DMS topology fast screen. **Stage 3.9 was not started**; no topology promotion or next-stage exploration is authorized by this report.
"""


def _review_me(audit: dict[str, Any]) -> str:
    gate = audit["gate"]
    return f"""Stage 3.8C Production:
COMPLETED

96k rerun:
NOT PERFORMED

Original FAILED reason:
counter accounting row-count gate bug

Corrected counter accounting:
{gate['counter_accounting_rows_passed']} / {gate['counter_accounting_expected_rows']} checkpoint rows PASS

Stage 3.8:
READY FOR CLOSEOUT REVIEW

Stage 3.9:
NOT STARTED

# Review bundle

- Existing production results are the canonical 96,000-evaluation results; no optimizer or physics calculation was repeated.
- Cells: {gate['cells_completed']}/{gate['cells_total']}; seed runs: {gate['seed_runs_completed']}/{gate['seed_runs_total']}; physics failures: {gate['physics_failures']}.
- Recorded Production and Final Confirmation fingerprints match: `{gate['source_config_fingerprint']}`.
- Filter-feasibility was not achieved. MLIT T1 is the primary candidate from this screen; T2 remains unresolved and retained. M0/MLIT comparisons are confounded by different aperture ranges and COM provenance.
- The original false-failure gate, summary, status, and marker are retained under `history/initial_false_failure/`.
- See `stage3_8c_production_closeout_summary.md`, `counter_gate_correction_report.md`, and `stage3_8c_production_gate_corrected.json` for the closeout audit.
"""


def _correction_report(audit: dict[str, Any]) -> str:
    counter = audit["counter_gate"]
    return f"""# Counter Gate Correction Report

## Original false failure

The initial production gate expected one accounting row per cell and seed (6 × 2 = 12). The stored accounting artifact is checkpoint-granular: six cells × two seeds × four configured checkpoints ({', '.join(map(str, audit['checkpoints']))}) = {counter['expected_rows']} rows. The optimizer and physics run completed successfully; the closeout aggregation alone incorrectly marked Production FAILED.

## Corrected validation

- Expected checkpoint rows, derived from configured material/topology/seed/checkpoint axes: {counter['expected_rows']}.
- Actual rows: {counter['actual_rows']}; unique rows: {counter['unique_rows']}.
- Seed runs with all configured checkpoints: {counter['seed_runs_with_complete_checkpoints']} / {counter['expected_seed_runs']}.
- Final {counter['final_checkpoint_budget']} checkpoint rows: {counter['final_checkpoint_rows']} / {counter['expected_seed_runs']}.
- Missing keys: {len(counter['missing_keys'])}; duplicate keys: {len(counter['duplicate_keys'])}; unexpected keys: {len(counter['unexpected_keys'])}; invariant failures: {len(counter['invalid_rows'])}.
- Required counter identity, physics partition, valid-physics bounds, and physics-attempt identity: **PASS for every row**.

The corrected gate also revalidated evaluation totals, all 12 unique seed-run results, finite search/common-grid metrics, common-grid identity and validation, zero physics failures, fixed-design sanity, Final Confirmation PASS, the recorded source/config fingerprint, original review-bundle hashes, and result-copy hashes.

## No recomputation

No 96k optimizer run was restarted. No COM/physics calculation, objective value, design parameter, checkpoint, seed result, or raw production result was changed. The initial FAILED gate and summary remain available in `history/initial_false_failure/` as historical evidence.
"""


def _make_closeout_status(audit: dict[str, Any], original_status: dict[str, Any]) -> dict[str, Any]:
    gate = audit["gate"]
    return {
        "schema_version": 1,
        "status": gate["status"],
        "closeout_status": gate["closeout_status"],
        "production_final_state": gate["status"],
        "optimizer_rerun_performed": False,
        "physics_recomputed": False,
        "evaluations_completed": gate["completed_evaluations"],
        "evaluations_expected": gate["expected_evaluations"],
        "cells_completed": gate["cells_completed"],
        "seed_runs_completed": gate["seed_runs_completed"],
        "physics_failures": gate["physics_failures"],
        "counter_accounting": f"{gate['counter_accounting_rows_passed']}/{gate['counter_accounting_expected_rows']} PASS",
        "counter_accounting_gate": gate["counter_accounting"],
        "source_config_fingerprint": gate["source_config_fingerprint"],
        "source_config_fingerprint_match": gate["source_config_fingerprint_match"],
        "historical_initial_closeout_status": "FAILED",
        "historical_initial_failure": gate["historical_initial_failure"],
        "orchestration_state_before_correction": original_status.get("state"),
        "historical_callback_completed": original_status.get("callback_completed"),
        "historical_callback_exit_code": original_status.get("callback_exit_code"),
        "orchestration_final_state": "REVIEW_WAITING",
        "canonical_results_path": str(ROOT / RUN_REL),
        "corrected_review_bundle": str(ROOT / "artifacts/review_bundles" / f"{CORRECTED_BUNDLE_NAME}.zip"),
        "stage3_9_started": False,
        "failures": gate["failures"],
    }


def _scoped_diff(original_bundle: Path) -> str:
    chunks = []
    old_source = original_bundle / "source_snapshot/src/sawopt/studies/stage3_8c_r1_geometry_gate.py"
    current_source = ROOT / "src/sawopt/studies/stage3_8c_r1_geometry_gate.py"
    if old_source.is_file():
        chunks.extend(difflib.unified_diff(
            old_source.read_text(encoding="utf-8").splitlines(keepends=True),
            current_source.read_text(encoding="utf-8").splitlines(keepends=True),
            fromfile="a/source_snapshot/src/sawopt/studies/stage3_8c_r1_geometry_gate.py",
            tofile="b/src/sawopt/studies/stage3_8c_r1_geometry_gate.py",
        ))
    for relative in (
        "tests/unit/studies/test_stage3_8c_production_closeout.py",
        "scripts/stage3_8c_production_closeout.py",
    ):
        current = ROOT / relative
        if current.is_file():
            chunks.extend(difflib.unified_diff(
                [], current.read_text(encoding="utf-8").splitlines(keepends=True),
                fromfile="/dev/null", tofile=f"b/{relative}",
            ))
    return "".join(chunks)


def _make_repro_metadata(audit: dict[str, Any]) -> dict[str, Any]:
    tracked = (
        "src/sawopt/studies/stage3_8c_r1_geometry_gate.py",
        "tests/unit/studies/test_stage3_8c_production_closeout.py",
        "scripts/stage3_8c_production_closeout.py",
        "reports/stage3_8c_production_closeout_test_summary.md",
    )
    hashes = {name: _sha256(ROOT / name) for name in tracked if (ROOT / name).is_file()}
    return {
        "schema_version": 1,
        "closeout_type": "reporting_and_validation_only",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "recorded_production_source_config_fingerprint": audit["source"].get("source_config_fingerprint"),
        "final_confirmation_source_config_fingerprint": audit["final_gate"].get("final_confirmation_fingerprint"),
        "recorded_source_config_match": audit["gate"]["source_config_fingerprint_match"],
        "git_head": _git("rev-parse", "HEAD"),
        "git_branch": _git("branch", "--show-current"),
        "git_status_short": _git("status", "--short").splitlines(),
        "scoped_closeout_source_sha256": hashes,
        "production_run_source_snapshot": "source_snapshot/ (frozen at original production run)",
        "scope_note": "Closeout gate code changed after the completed run. Recorded production and Final Confirmation fingerprints are verified against the frozen production source snapshot; the new closeout code did not evaluate candidates or physics.",
    }


def _build_bundle(audit: dict[str, Any], closeout_status: dict[str, Any], original_status: dict[str, Any]) -> tuple[Path, str]:
    artifact_root = ROOT / "artifacts/review_bundles"
    original = audit["original_bundle"]
    name = CORRECTED_BUNDLE_NAME
    target = artifact_root / name
    zip_target = artifact_root / f"{name}.zip"
    if target.exists() or zip_target.exists():
        raise FileExistsError(f"corrected review bundle already exists: {target} or {zip_target}")
    staging = artifact_root / f".{name}.building"
    zip_staging = artifact_root / f".{name}.zip.building"
    if staging.exists() or zip_staging.exists():
        raise FileExistsError("closeout bundle staging path already exists")
    shutil.copytree(original, staging)
    history = staging / "history/initial_false_failure"
    history.mkdir(parents=True, exist_ok=True)
    for source_rel, target_name in (
        (Path("stage3_8c_production_gate.json"), "stage3_8c_production_gate_initial_failed.json"),
        (Path("stage3_8c_production_summary.md"), "stage3_8c_production_summary_initial_failed.md"),
        (Path("REVIEW_ME.md"), "REVIEW_ME_initial_failed.md"),
    ):
        shutil.copy2(staging / source_rel, history / target_name)
    bundle_run = staging / "run"
    if (bundle_run / "status.json").is_file():
        shutil.copy2(bundle_run / "status.json", history / "status_before_closeout.json")
    for marker in ("STAGE3_8C_PRODUCTION_FAILED.txt", "STAGE3_8C_PRODUCTION_COMPLETED.txt"):
        marker_path = bundle_run / marker
        if marker_path.is_file():
            shutil.copy2(marker_path, history / marker)
            marker_path.unlink()

    gate = audit["gate"]
    _write_json(staging / "stage3_8c_production_gate.json", gate)
    _write_json(staging / "stage3_8c_production_gate_corrected.json", gate)
    _write_json(staging / "stage3_8c_production_closeout_status.json", closeout_status)
    production_summary = _summary(audit)
    _write_text(staging / "stage3_8c_production_summary.md", production_summary)
    _write_text(staging / "stage3_8c_production_closeout_summary.md", production_summary)
    _write_text(staging / "counter_gate_correction_report.md", _correction_report(audit))
    _write_text(staging / "REVIEW_ME.md", _review_me(audit))
    test_summary = (ROOT / "reports/stage3_8c_production_closeout_test_summary.md").read_text(encoding="utf-8")
    _write_text(staging / "test_summary.md", test_summary)
    _write_text(staging / "HISTORICAL_ARTIFACTS.md", """# Historical and pre-production artifacts in this bundle

The canonical execution status is in the bundle-root `REVIEW_ME.md`, `stage3_8c_production_closeout_summary.md`, and corrected Production gate.

- `history/initial_false_failure/` preserves the first closeout's FAILED gate, summary, REVIEW_ME, status, and marker. Its FAILED label came from expecting 12 rows in a checkpoint-level accounting table that correctly contains 48 rows.
- `stage3_8c_r1_topology_fast_screen_summary.md` is an earlier pre-R1 screen summary. Its “production screen not run” statement describes that earlier screen, not this completed R1.2 Production run.
- `source_snapshot/reports/stage3_8c_r1_2_test_summary.md` was frozen at Final Confirmation, before Production began. Its “Production: NOT STARTED” statement was true at snapshot time and is not the final execution status.
- `source_snapshot/**` is the source/config snapshot from the Production launch. Any embedded pilot-only or not-started wording records source/report state at that time, not current run status.
- `reproducibility/scoped_closeout_diff.patch` includes old source/report context as diff material. It is not a canonical status report.

These historical and pre-production files are retained unchanged. Use the corrected bundle-root summary and gate for final status.
""")
    for run_name, bundle_names in RESULT_COPIES.items():
        run_file = ROOT / RUN_REL / run_name
        for bundle_name in bundle_names:
            bundle_file = staging / bundle_name
            if not bundle_file.is_file():
                bundle_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(run_file, bundle_file)
            elif _sha256(bundle_file) != _sha256(run_file):
                raise RuntimeError(f"production result differs from the original bundle copy: {bundle_name}")
    corrected_run_status = dict(original_status)
    corrected_run_status.update({
        "state": "REVIEW_WAITING",
        "updated_at": closeout_status["created_at_utc"],
        "optimizer_state": "COMPLETED",
        "exit_code": 0,
        "error": "Historical callback exited nonzero because the initial checkpoint-row gate falsely failed; corrected closeout passed. See stage3_8c_production_closeout_status.json.",
        "evaluations_completed": gate["completed_evaluations"],
        "evaluations_expected": gate["expected_evaluations"],
        "cells_completed": gate["cells_completed"],
        "seed_runs_completed": gate["seed_runs_completed"],
        "physics_failures": gate["physics_failures"],
        "counter_accounting": f"{gate['counter_accounting_rows_passed']}/{gate['counter_accounting_expected_rows']} PASS",
        "closeout_status": "COMPLETED",
        "closeout_corrected_at": closeout_status["created_at_utc"],
    })
    _write_json(bundle_run / "status.json", corrected_run_status)
    _write_text(bundle_run / "STAGE3_8C_PRODUCTION_COMPLETED.txt", "STAGE3_8C_PRODUCTION_COMPLETED\n")
    _write_json(staging / "reproducibility/closeout_metadata.json", _make_repro_metadata(audit))
    _write_text(staging / "reproducibility/scoped_closeout_diff.patch", _scoped_diff(original))
    (staging / "reproducibility/closeout_correction_source").mkdir(parents=True, exist_ok=True)
    for relative in (
        "tests/unit/studies/test_stage3_8c_production_closeout.py",
        "scripts/stage3_8c_production_closeout.py",
    ):
        shutil.copy2(ROOT / relative, staging / "reproducibility/closeout_correction_source" / Path(relative).name)

    # Keep the frozen production snapshots untouched, but record corrected status for review.
    _write_json(staging / "bundle_manifest.json", {
        "schema_version": 1,
        "mode": "production_closeout_corrected",
        "run_directory": str(ROOT / RUN_REL),
        "source_config_fingerprint": gate["source_config_fingerprint"],
        "closeout_status": gate["status"],
        "files": {
            str(path.relative_to(staging)).replace("\\", "/"): _sha256(path)
            for path in sorted(staging.rglob("*"))
            if path.is_file() and path.name != "bundle_manifest.json"
        },
    })
    with zipfile.ZipFile(zip_staging, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.write(path, Path(name) / path.relative_to(staging))
    with zipfile.ZipFile(zip_staging, "r") as archive:
        names = set(archive.namelist())
        for relative, expected in _read_json(staging / "bundle_manifest.json")["files"].items():
            member = (Path(name) / relative).as_posix()
            if member not in names or hashlib.sha256(archive.read(member)).hexdigest() != expected:
                raise RuntimeError(f"corrected review bundle SHA validation failed: {relative}")
    directory_errors = _verify_manifest(staging)
    if directory_errors:
        raise RuntimeError(f"corrected review directory manifest failed: {directory_errors[:10]}")
    staging.rename(target)
    os.replace(zip_staging, zip_target)
    zip_hash = _sha256(zip_target)
    _write_text(zip_target.with_suffix(zip_target.suffix + ".sha256"), f"{zip_hash}  {zip_target.name}\n")
    return target, zip_hash


def closeout(*, validate_only: bool = False) -> dict[str, Any]:
    audit = _build_audit()
    if validate_only:
        return audit["gate"]
    if audit["gate"]["status"] != "COMPLETED":
        raise RuntimeError(f"production closeout gates failed: {audit['failures']}")

    run = audit["run"]
    original_status = _read_json(run / "status.json")
    if original_status.get("optimizer_state") != "COMPLETED" or original_status.get("exit_code") != 0:
        raise RuntimeError("orchestration record does not show a successful completed optimizer")
    status = _make_closeout_status(audit, original_status)
    closeout_at = datetime.now(timezone.utc).isoformat()
    status["created_at_utc"] = closeout_at
    new_orchestration_status = dict(original_status)
    new_orchestration_status.update({
        "state": "REVIEW_WAITING",
        "updated_at": closeout_at,
        "optimizer_state": "COMPLETED",
        "exit_code": 0,
        "error": "Historical callback exited nonzero because the original checkpoint-row gate falsely failed; corrected closeout passed. See stage3_8c_production_closeout_status.json.",
        "evaluations_completed": audit["completed_evaluations"],
        "evaluations_expected": audit["expected_evaluations"],
        "cells_completed": audit["cells_completed"],
        "seed_runs_completed": audit["seed_runs_completed"],
        "physics_failures": audit["physics_failures"],
        "counter_accounting": status["counter_accounting"],
        "closeout_status": "COMPLETED",
        "closeout_corrected_at": closeout_at,
    })

    bundle_dir, bundle_sha = _build_bundle(audit, status, original_status)
    _write_json(run / "closeout/history/status_before_closeout.json", original_status)
    _write_json(run / "closeout/history/stage3_8c_production_gate_initial_failed.json", audit["initial_gate"])
    shutil.copy2(run / "stage3_8c_production_summary.md",
                 run / "closeout/history/stage3_8c_production_summary_initial_failed.md")
    failed_marker = run / "STAGE3_8C_PRODUCTION_FAILED.txt"
    if failed_marker.is_file():
        shutil.copy2(failed_marker, run / "closeout/history/STAGE3_8C_PRODUCTION_FAILED_initial.txt")
        failed_marker.unlink()
    completed_marker = run / "STAGE3_8C_PRODUCTION_COMPLETED.txt"
    _write_text(completed_marker, "STAGE3_8C_PRODUCTION_COMPLETED\n")
    _write_json(run / "stage3_8c_production_gate_corrected.json", audit["gate"])
    _write_json(run / "stage3_8c_production_gate.json", audit["gate"])
    production_summary = _summary(audit)
    _write_text(run / "stage3_8c_production_summary.md", production_summary)
    _write_text(run / "stage3_8c_production_closeout_summary.md", production_summary)
    _write_text(run / "counter_gate_correction_report.md", _correction_report(audit))
    _write_json(run / "stage3_8c_production_closeout_status.json", status)
    _write_json(run / "status.json", new_orchestration_status)
    return {
        "status": audit["gate"]["status"],
        "run_dir": str(run),
        "bundle_dir": str(bundle_dir),
        "bundle_zip": str(bundle_dir) + ".zip",
        "bundle_zip_sha256": bundle_sha,
        "counter_rows": f"{audit['counter_gate']['actual_rows']}/{audit['counter_gate']['expected_rows']} PASS",
    }


if __name__ == "__main__":
    validate_only = "--validate-only" in sys.argv[1:]
    result = closeout(validate_only=validate_only)
    print(json.dumps(result, indent=2, sort_keys=True))
