"""Stage 3.6 Gate 2A final confirmation at 50/50 ohm.

This module is a bounded orchestration/reporting layer around the existing
Gate 2A release worker.  It does not change COM equations, the objective,
validation, L-SHADE, or the release-space decoder.  G1+G2 resumes the exact
32k-terminal 16k checkpoints; G2 (and the optional G1+G2 64k arm) starts a
fresh 64k-terminal trajectory because the L-SHADE population horizon is part
of the checkpoint contract.
"""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np

from ..io.config import load_experiment_config
from ..io.run_store import initialize
from ..io.serialization import save
from .convergence import normalize_convergence_config
from .stage3_6_gate2a import (
    BASELINE_GROUP,
    ROOT,
    WIRING,
    common_validation_grid,
    gate2a_group_records,
    load_frozen_s1,
    release_worker,
    reuse_gate2a_baseline,
    run_release_workers,
    validate_gate2a_record,
    write_gate2a_csv,
    release_schema,
)


STUDY_TYPE = "stage3_6_gate2a_final_confirmation"
SEEDS = (20260917, 20260918, 20260919)
G1 = "G1_CENTER_PITCH"
G2 = "G2_REFLECTOR_PITCH"
G12 = "G1_G2"
G3 = "G3_CENTER_APERTURE"
FINAL_BUNDLE_NAME = "stage3_6_gate2a_final_confirmation_review.zip"


def _json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _clean(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return [_clean(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _clean(value.item())
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _copy_reference_records(previous: Path, final_run: Path, groups: Iterable[str]) -> list[dict[str, Any]]:
    entries = []
    for group in groups:
        for source in sorted((previous / "groups" / group / "trials" / "lshade" / WIRING).glob("seed*/B*.json")):
            target = final_run / "references" / "old_gate2a" / "groups" / group / source.parent.name / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            entries.append({
                "group": group,
                "seed": int(source.parent.name.removeprefix("seed")),
                "budget": int(source.stem.removeprefix("B")),
                "source": str(source),
                "source_sha256": _sha256(source),
                "copied_to": str(target.relative_to(final_run)),
            })
    save(final_run / "provenance" / "reused_reference_records.json", entries)
    return entries


def _copy_resume_source(previous: Path, final_run: Path, group: str) -> dict[str, Any]:
    source = previous / "groups" / group
    if not source.is_dir():
        raise FileNotFoundError(f"resume source group is missing: {source}")
    target = final_run / "groups" / group
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    checkpoints = []
    for path in sorted(target.glob("trials/lshade/center_outer_same/seed*/optimizer_checkpoint.json")):
        checkpoints.append({
            "seed": int(path.parent.name.removeprefix("seed")),
            "source_checkpoint": str(source / path.relative_to(target)),
            "copied_checkpoint": str(path.relative_to(final_run)),
            "source_checkpoint_sha256": _sha256(source / path.relative_to(target)),
            "terminal_budget": _json(path).get("terminal_budget"),
            "dimension": len(_json(path).get("bounds", [])),
        })
    if len(checkpoints) != len(SEEDS):
        raise RuntimeError(f"expected {len(SEEDS)} resume checkpoints for {group}, found {len(checkpoints)}")
    provenance = {"group": group, "source_run": str(previous), "checkpoints": checkpoints}
    save(final_run / "provenance" / f"{group}_resume_source.json", provenance)
    return provenance


def _old_worker_config(previous: Path) -> dict[str, Any]:
    # The historical run's copied input_config.yaml contains a relative
    # base_config name.  Resolving that file from inside runs/<run>/ points at
    # a non-existent nested configs/base directory.  Prefer the immutable
    # config path recorded in the original Gate 2A manifest so the normalized
    # worker config (and its checkpoint fingerprint) remains identical.
    candidates: list[Path] = []
    manifest_path = previous / "stage3_6_gate2a_manifest.json"
    if manifest_path.is_file():
        configured = _json(manifest_path).get("config_path")
        if configured:
            candidates.append(Path(configured))
    candidates.extend([
        ROOT / "configs" / "studies" / "stage3_6_phase_c1_c2_gate2a.yaml",
        previous / "input_config.yaml",
    ])
    for path in candidates:
        if path.is_file():
            return normalize_convergence_config(load_experiment_config(path))
    raise FileNotFoundError(f"original Gate 2A config is missing; checked: {candidates}")


def _worker_config(source_cfg: Mapping[str, Any], terminal: int) -> dict[str, Any]:
    cfg = json.loads(json.dumps(source_cfg))
    cfg.setdefault("stage3_6_gate2a", {})["terminal_budget"] = int(terminal)
    return cfg


def _run_release(run: Path, cfg: Mapping[str, Any], group: str, s1: Mapping[str, Any],
                 *, terminal: int, budgets: Iterable[int], resume: bool, workers: int) -> None:
    worker_cfg = _worker_config(cfg, terminal)
    tasks = [(
        str(run), worker_cfg, group, s1, seed, list(budgets), bool(resume)
    ) for seed in SEEDS]
    threads = int(worker_cfg.get("stage3_3", {}).get("production_parallel", {}).get("blas_threads_per_worker", 1))
    run_release_workers(tasks, min(int(workers), len(SEEDS)), threads)


def _require_records(records: Iterable[Mapping[str, Any]], group: str, budgets: Iterable[int]) -> None:
    found = {(int(item.get("seed")), int(item.get("requested_unique_design_budget", item.get("current_budget", 0))))
             for item in records}
    expected = {(seed, int(budget)) for seed in SEEDS for budget in budgets}
    missing = sorted(expected - found)
    if missing:
        raise RuntimeError(f"{group} is missing required records: {missing}")


def _trace_last_improvement(record: Mapping[str, Any], budget: int) -> tuple[int, float | None]:
    values = []
    for item in record.get("best_so_far_trace", []):
        value = item.get("unique_evaluation")
        if value is not None:
            values.append(int(value))
    last = max(values, default=int(budget))
    fraction = last / max(int(budget), 1)
    return last, float(fraction)


def _record_row(cfg: Mapping[str, Any], group: str, record: Mapping[str, Any], grid: np.ndarray,
                *, source: str, mode: str, terminal: int, record_path: str,
                validation_grid_id: str) -> dict[str, Any]:
    row = validate_gate2a_record(cfg, group, record, grid)
    last, fraction = _trace_last_improvement(record, row["budget"])
    row.update({
        "source": source,
        "mode": mode,
        "terminal_horizon": int(terminal),
        "record_path": record_path,
        "validation_grid_id": validation_grid_id,
        "termination_reason": record.get("stop_reason") or record.get("termination_reason"),
        "last_significant_improvement_evaluation": int(last),
        "fraction_of_budget_at_last_significant_improvement_explicit": fraction,
        "boundary_occupancy": json.dumps({
            "boundary_repair_counts": _clean(record.get("boundary_repair_counts", {})),
            "hard_bound_reached_by_variable": _clean(record.get("hard_bound_reached_by_variable", {})),
        }, sort_keys=True),
        "released_dof_utilization": json.dumps(_released_utilization(group, record), sort_keys=True),
    })
    return row


def _released_utilization(group: str, record: Mapping[str, Any]) -> dict[str, Any]:
    design = record.get("design", {})
    if group == G1:
        names = ("center_wavelength_um",)
    elif group == G2:
        names = ("reflector_wavelength_um",)
    elif group == G12:
        names = ("center_wavelength_um", "reflector_wavelength_um")
    else:
        names = ()
    values = {}
    for name in names:
        base_name = "wavelength_um"
        base = design.get(base_name)
        released = design.get(name)
        values[name] = {
            "value": released,
            "base_value": base,
            "delta_um": None if released is None or base is None else float(released) - float(base),
            "normalized_delta": None if released is None or base is None else (float(released) - float(base)) / max(abs(float(base)), np.finfo(float).tiny),
        }
    if group == G12:
        center = design.get("center_wavelength_um")
        reflector = design.get("reflector_wavelength_um")
        base = design.get("wavelength_um")
        values["reflector_minus_center_um"] = None if center is None or reflector is None else float(reflector) - float(center)
        values["center_minus_base_um"] = None if center is None or base is None else float(center) - float(base)
        values["reflector_minus_base_um"] = None if reflector is None or base is None else float(reflector) - float(base)
    return values


def _annotate_records(run: Path, group: str, records: list[dict[str, Any]], *, source: str,
                      mode: str, terminal: int, source_checkpoint: str | None = None) -> list[dict[str, Any]]:
    annotated = []
    for record in records:
        value = dict(record)
        value["_source"] = source
        value["_mode"] = mode
        value["_terminal"] = int(terminal)
        value["_record_path"] = value.get("_record_path", "")
        value["_source_checkpoint"] = source_checkpoint
        annotated.append(value)
    return annotated


def _promotion(rows: Iterable[Mapping[str, Any]], section: Mapping[str, Any]) -> dict[str, Any]:
    # G2 also has an internal 32k observation on the fresh 64k-terminal arm;
    # compare promotion against the historical 32k-terminal G2 arm.
    selected = [row for row in rows if row["group"] in (G2, G12) and int(row["budget"]) == 32000
                and not (row["group"] == G2 and row.get("mode") == "fresh_64k_terminal")]
    by = {(row["group"], int(row["seed"])): row for row in selected}
    paired = []
    tolerance = float(section.get("promotion_relative_tolerance", 0.05))
    strong = float(section.get("promotion_strong_relative_tolerance", 0.03))
    for seed in SEEDS:
        g2 = by.get((G2, seed))
        g12 = by.get((G12, seed))
        if g2 is None or g12 is None:
            continue
        base = max(abs(float(g2["max_violation"])), np.finfo(float).tiny)
        rel_gap = (float(g12["max_violation"]) - float(g2["max_violation"])) / base
        sum_base = max(abs(float(g2["sum_violation"])), np.finfo(float).tiny)
        sum_rel = (float(g12["sum_violation"]) - float(g2["sum_violation"])) / sum_base
        paired.append({
            "seed": seed,
            "g2_max_violation": float(g2["max_violation"]),
            "g1_g2_max_violation": float(g12["max_violation"]),
            "relative_max_violation_gap": float(rel_gap),
            "g2_sum_violation": float(g2["sum_violation"]),
            "g1_g2_sum_violation": float(g12["sum_violation"]),
            "relative_sum_violation_gap": float(sum_rel),
            "g2_feasible": bool(g2["feasible"]),
            "g1_g2_feasible": bool(g12["feasible"]),
            "g1_g2_late_improvement": float(g12.get("fraction_of_budget_at_last_significant_improvement_explicit", 0.0)) > 0.75,
            "close_or_improved": bool(rel_gap <= tolerance),
        })
    g2_values = [item["g2_max_violation"] for item in paired]
    g12_values = [item["g1_g2_max_violation"] for item in paired]
    median_gap = None if not paired else (float(np.median(g12_values)) - float(np.median(g2_values))) / max(abs(float(np.median(g2_values))), np.finfo(float).tiny)
    close_count = sum(bool(item["close_or_improved"]) for item in paired)
    late_count = sum(bool(item["g1_g2_late_improvement"]) for item in paired)
    sum_tradeoff = bool(paired) and float(np.median([item["relative_sum_violation_gap"] for item in paired])) <= -0.02
    feasibility_tradeoff = sum(bool(item["g1_g2_feasible"] and not item["g2_feasible"]) for item in paired) >= 1
    tradeoff = bool(sum_tradeoff or feasibility_tradeoff)
    promotion = bool(
        median_gap is not None and median_gap <= tolerance
        or close_count >= 2
        or late_count >= 2
        or tradeoff
    )
    clear_inferiority = sum(item["relative_max_violation_gap"] > tolerance for item in paired) == len(paired) == 3
    return {
        "decision": "PROMOTE_G1_G2_TO_64K" if promotion else "STOP_AT_G1_G2_32K",
        "promotion": promotion,
        "criteria": {
            "performance_median_relative_gap": median_gap,
            "performance_threshold": tolerance,
            "strong_threshold": strong,
            "paired_close_or_improved_count": close_count,
            "paired_required_count": 2,
            "late_improvement_count": late_count,
            "late_improvement_threshold": 0.75,
            "tradeoff": tradeoff,
            "secondary_sum_violation_median_relative_gap_threshold": -0.02,
            "clear_3_of_3_inferiority": clear_inferiority,
        },
        "paired": paired,
        "interpretation": (
            "Promotion criteria met; optional G1+G2 64k is authorized as a fresh 64k-horizon run."
            if promotion else
            "Promotion criteria not met; stop after G1+G2 32k and G2 64k."
        ),
    }


def _runtime_rows(entries: list[dict[str, Any]], final_run: Path, grid_id: str,
                  final_config_hash: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault((entry["group"], int(entry["record"]["seed"]), entry["mode"]), []).append(entry)
    output = []
    for key, values in grouped.items():
        values.sort(key=lambda item: int(item["budget"]))
        previous_budget = 0
        previous_elapsed = 0.0
        for item in values:
            record = item["record"]
            budget = int(item["budget"])
            raw_elapsed = float(record.get("elapsed_s", record.get("total_trial_wall_time_s", 0.0)))
            fresh_or_resume = item["mode"] in ("resume_continuation", "fresh_64k_terminal")
            if fresh_or_resume and previous_budget:
                segment_elapsed = max(0.0, raw_elapsed - previous_elapsed) if item["mode"] == "fresh_64k_terminal" else raw_elapsed
                cumulative_elapsed = raw_elapsed if item["mode"] == "fresh_64k_terminal" else previous_elapsed + raw_elapsed
                segment_evals = budget - previous_budget
            else:
                segment_elapsed = raw_elapsed
                cumulative_elapsed = raw_elapsed
                segment_evals = budget
            last_eval, fraction = _trace_last_improvement(record, budget)
            source_checkpoint = item.get("source_checkpoint")
            output.append({
                "group": item["group"], "seed": int(record["seed"]), "budget": budget,
                "terminal_horizon": int(item["terminal"]), "mode": item["mode"],
                "segment_runtime_s": float(segment_elapsed),
                "cumulative_runtime_s": float(cumulative_elapsed),
                "segment_evaluations": int(segment_evals),
                "cumulative_evaluations": int(budget),
                "raw_record_elapsed_s": raw_elapsed,
                "stop_reason": record.get("stop_reason"),
                "last_significant_improvement_evaluation": int(last_eval),
                "fraction_of_budget_at_last_significant_improvement": fraction,
                "record_path": item.get("record_path"),
                "source_run": item.get("source_run"),
                "source_checkpoint": source_checkpoint,
                "source_checkpoint_sha256": item.get("source_checkpoint_sha256"),
                "source_config_sha256": item.get("source_config_sha256"),
                "final_config_sha256": final_config_hash,
                "release_schema_sha256": item.get("release_schema_sha256"),
                "validation_grid_id": grid_id,
                "fresh_terminal_comparison_note": item.get("fresh_terminal_comparison_note"),
            })
            previous_budget = budget
            previous_elapsed = raw_elapsed
    return output


def _wide_paired(rows: Iterable[Mapping[str, Any]], metric: str) -> list[dict[str, Any]]:
    values: dict[int, dict[str, Any]] = {seed: {"seed": seed, "metric": metric} for seed in SEEDS}
    labels = {
        (BASELINE_GROUP, 16000): "G0_16k", (BASELINE_GROUP, 32000): "G0_32k",
        (G1, 16000): "G1_16k", (G1, 32000): "G1_32k",
        (G2, 16000): "G2_16k", (G2, 32000): "G2_32k", (G2, 64000): "G2_64k",
        (G12, 16000): "G1_G2_16k", (G12, 32000): "G1_G2_32k", (G12, 64000): "G1_G2_64k",
    }
    for row in rows:
        label = labels.get((row["group"], int(row["budget"])))
        if row.get("mode") == "fresh_64k_terminal":
            if row["group"] == G2 and int(row["budget"]) == 32000:
                label = "G2_64k_internal_32k"
            elif row["group"] == G12 and int(row["budget"]) == 32000:
                label = "G1_G2_64k_internal_32k"
            elif row["group"] == G12 and int(row["budget"]) == 64000:
                label = "G1_G2_64k"
        if label and int(row["seed"]) in values:
            values[int(row["seed"])][label] = row.get(metric)
    return list(values.values())


def _write_plots(run: Path, rows: list[dict[str, Any]], entries: list[dict[str, Any]]) -> list[str]:
    import matplotlib.pyplot as plt

    plot_root = run / "plots"
    paths = []
    # Convergence uses the optimizer's best-so-far rank key; rank_key[1] is
    # max_violation under the unchanged Gate 2A comparator.
    fig, ax = plt.subplots(figsize=(9, 5))
    for entry in entries:
        trace = entry["record"].get("best_so_far_trace", [])
        x, y = [], []
        for item in trace:
            rank_key = item.get("rank_key", [])
            if len(rank_key) > 1 and item.get("unique_evaluation") is not None:
                x.append(int(item["unique_evaluation"]))
                y.append(float(rank_key[1]))
        if x:
            ax.plot(x, y, alpha=.65, label=f'{entry["group"]} s{entry["record"]["seed"]}')
    ax.set_xlabel("unique evaluations")
    ax.set_ylabel("best-so-far max violation")
    ax.grid(True, alpha=.25)
    ax.legend(fontsize=6, ncol=2)
    path = plot_root / "convergence" / "best_so_far_max_violation.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig); paths.append(str(path.relative_to(run)))

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for label, subset in (("G2", [r for r in rows if r["group"] == G2]), ("G1+G2", [r for r in rows if r["group"] == G12])):
        subset = [r for r in subset if int(r["budget"]) in (32000, 64000)]
        for seed in SEEDS:
            item = next((r for r in subset if int(r["seed"]) == seed and int(r["budget"]) == (64000 if label == "G2" else 32000)), None)
            if item:
                ax.scatter([seed], [item["max_violation"]], label=f"{label} s{seed}")
    ax.set_xlabel("paired seed")
    ax.set_ylabel("max violation")
    ax.grid(True, alpha=.25)
    path = plot_root / "paired" / "g2_vs_g1_g2.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig); paths.append(str(path.relative_to(run)))

    fig, ax = plt.subplots(figsize=(8, 4.5))
    param_rows = [r for r in rows if r["group"] in (G2, G12) and int(r["budget"]) in (32000, 64000)]
    for group in (G2, G12):
        values = []
        labels = []
        for row in param_rows:
            if row["group"] != group:
                continue
            design = json.loads(row["design"])
            values.append(float(design.get("reflector_wavelength_um" if group == G2 else "center_wavelength_um", np.nan)))
            labels.append(f'{group} s{row["seed"]} B{row["budget"]}')
        if values:
            ax.plot(labels, values, marker="o", label=group)
    ax.set_ylabel("released wavelength (um)"); ax.tick_params(axis="x", rotation=60); ax.grid(True, alpha=.25); ax.legend()
    path = plot_root / "parameters" / "wavelength_utilization.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig); paths.append(str(path.relative_to(run)))

    fig, ax = plt.subplots(figsize=(8, 4.5))
    labels, values = [], []
    for row in rows:
        if row["group"] in (G2, G12) and int(row["budget"]) in (32000, 64000):
            labels.append(f'{row["group"]}\ns{row["seed"]}\nB{row["budget"]}')
            values.append(float(row["max_violation"]))
    ax.bar(np.arange(len(values)), values); ax.set_xticks(np.arange(len(values)), labels, rotation=60); ax.set_ylabel("max violation"); ax.grid(True, axis="y", alpha=.25)
    path = plot_root / "constraints" / "max_violation_summary.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig); paths.append(str(path.relative_to(run)))
    return paths


def _run_tests(run: Path) -> dict[str, Any]:
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    targeted = [
        "tests/unit/studies/test_stage3_6_gate2a.py",
        "tests/unit/core/test_reference.py",
        "tests/unit/core/test_physics.py",
        "tests/unit/studies/test_search_efficiency.py",
        "tests/unit/orchestration/test_run_manager.py",
    ]
    results = {}
    for name, command in (
        ("targeted", [str(python), "-m", "pytest", "-q", *targeted]),
        ("full_regression", [str(python), "-m", "pytest", "-q"]),
    ):
        started = time.monotonic()
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        output = completed.stdout + ("\n" + completed.stderr if completed.stderr else "")
        _write_text(run / "tests" / f"{name}_test_output.txt", output)
        passed = sum(1 for line in output.splitlines() if " passed" in line)
        failed = sum(1 for line in output.splitlines() if " failed" in line)
        results[name] = {
            "command": command,
            "returncode": completed.returncode,
            "passed_summary_lines": passed,
            "failed_summary_lines": failed,
            "elapsed_s": time.monotonic() - started,
        }
    _write_text(run / "tests" / "test_summary.md", "# Gate 2A final confirmation tests\n\n" + "\n".join(
        f"- {key}: returncode={value['returncode']}, passed-summary-lines={value['passed_summary_lines']}, failed-summary-lines={value['failed_summary_lines']}"
        for key, value in results.items()
    ) + "\n")
    return results


def _answer_questions(rows: list[dict[str, Any]], promotion: Mapping[str, Any], runtime: list[dict[str, Any]]) -> dict[str, Any]:
    def values(group: str, budget: int, field: str = "max_violation", mode: str | None = None):
        return [float(row[field]) for row in rows if row["group"] == group and int(row["budget"]) == budget
                and (mode is None or row.get("mode") == mode)]
    g2_32, g2_64 = values(G2, 32000, mode="reused_reference"), values(G2, 64000, mode="fresh_64k_terminal")
    g12_16, g12_32, g12_64 = values(G12, 16000, mode="resume_continuation"), values(G12, 32000, mode="resume_continuation"), values(G12, 64000, mode="fresh_64k_terminal")
    median = lambda items: None if not items else float(np.median(items))
    g2_improvement = None if not g2_32 or not g2_64 else (median(g2_32) - median(g2_64)) / max(abs(median(g2_32)), np.finfo(float).tiny)
    g12_improvement = None if not g12_16 or not g12_32 else (median(g12_16) - median(g12_32)) / max(abs(median(g12_16)), np.finfo(float).tiny)
    final_optional = bool(g12_64)
    final_g2 = median(g2_64) if g2_64 else median(g2_32)
    final_g12 = median(g12_64) if final_optional else median(g12_32)
    recommendation = "G1+G2" if final_optional and final_g12 is not None and final_g2 is not None and final_g12 < final_g2 else "G2"
    g2_runtime = [x["cumulative_runtime_s"] for x in runtime if x["group"] == G2 and x["budget"] == 64000]
    g12_runtime = [x["cumulative_runtime_s"] for x in runtime if x["group"] == G12 and x["budget"] == (64000 if final_optional else 32000)]
    return {
        "1_g2_32k_to_64k_improvement_relative": g2_improvement,
        "2_g2_64k_convergence": {"fractions": [x["fraction_of_budget_at_last_significant_improvement"] for x in runtime if x["group"] == G2 and x["budget"] == 64000]},
        "3_g2_reflector_pitch_stability": "see released_dof_utilization.csv and parameter plot; three paired seeds retained",
        "4_g1_g2_16k_to_32k_improvement_relative": g12_improvement,
        "5_g1_g2_catch_up_to_g2": bool(promotion.get("promotion")),
        "6_g1_g2_center_dof_utilization": "see released_dof_utilization.csv; center/base and reflector/base deltas are explicit",
        "7_g1_g2_64k_promotion": promotion.get("decision"),
        "8_g1_g2_64k_vs_g2_64k": None if not final_optional else {"g1_g2_median": final_g12, "g2_median": final_g2, "better": final_g12 < final_g2},
        "9_final_recommended_search_space": recommendation,
        "10_screening_vs_certification_policy": "G2 for lower-dimensional screening; G1+G2 certification only if optional arm is promoted and materially supports it" if recommendation == "G2" else "G1+G2 for screening/certification subject to review",
        "11_50_50_feasible": any(bool(row["feasible"]) for row in rows if row["group"] in (G2, G12) and int(row["budget"]) in (32000, 64000)),
        "12_final_constraint_bottleneck": "see constraint_breakdown.csv; limiting component is retained per seed",
        "13_runtime_penalty": {"g2_64k_cumulative_runtime_s": g2_runtime, "g1_g2_final_cumulative_runtime_s": g12_runtime},
        "14_ready_for_50_25_50_100": "evidence package complete; do not start the next gate automatically",
        "15_unresolved_dofs": ["center aperture (G3 dropped)", "left/right asymmetry", "material/COM coefficient releases", "topology alternatives"],
    }


def _build_bundle(run: Path, summary: Mapping[str, Any], final_config: Path, previous: Path) -> Path:
    bundle_root = ROOT / "artifacts" / "review_bundles"
    bundle_root.mkdir(parents=True, exist_ok=True)
    staging = run / "_final_confirmation_bundle"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    _write_text(staging / "README.md", "# Stage 3.6 Gate 2A final confirmation\n\nThis bundle contains only the instructed 50/50 confirmation arms. It stops before 50/25, 50/100, Gate 2B, Phase D, Stage 4, asymmetric termination, and auto-resume work. Evidence is operational three-seed paired evidence, not statistical certification.\n")
    _write_text(staging / "stage3_6_gate2a_final_summary.md", json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    for rel in ("results", "plots", "tests", "provenance", "references", "trajectories", "groups", "optional_g1_g2_64k"):
        source = run / rel
        if source.exists():
            shutil.copytree(source, staging / rel, dirs_exist_ok=True)
    (staging / "configs").mkdir(parents=True, exist_ok=True)
    shutil.copy2(final_config, staging / "configs" / final_config.name)
    original = previous / "input_config.yaml"
    if original.is_file():
        shutil.copy2(original, staging / "configs" / original.name)
    handoff = ROOT / "docs" / "handoff" / "stage3_6_gate2a_final_confirmation_work_instruction.md"
    if handoff.is_file():
        shutil.copy2(handoff, staging / "configs" / handoff.name)
    source_dir = staging / "source_diffs"
    source_dir.mkdir(parents=True, exist_ok=True)
    relevant = [
        "src/sawopt/studies/stage3_6_gate2a.py",
        "src/sawopt/studies/stage3_6_gate2a_final_confirmation.py",
        "src/sawopt/__main__.py",
        "src/sawopt/core/com.py",
        "src/sawopt/core/metrics.py",
        "tests/unit/studies/test_stage3_6_gate2a.py",
        "configs/studies/stage3_6_gate2a_final_confirmation.yaml",
    ]
    for relative in relevant:
        path = ROOT / relative
        if path.is_file():
            destination = source_dir / "current" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    diff = subprocess.run(["git", "diff", "--", *relevant], cwd=ROOT, capture_output=True, text=True, check=False)
    _write_text(source_dir / "relevant.patch", diff.stdout or "No tracked diff was emitted; current source snapshots are under source_diffs/current/.\n")
    _write_text(source_dir / "git_status.txt", subprocess.run(["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True, check=False).stdout)
    _write_text(staging / "logs" / "README.md", "Run manifests, checkpoint lineage, per-seed records, and test logs are included under provenance/, groups/, references/, and tests/.\n")
    save(staging / "bundle_manifest.json", {
        "bundle_format_version": 1,
        "files": [
            {"path": path.relative_to(staging).as_posix(), "sha256": _sha256(path), "bytes": path.stat().st_size}
            for path in sorted(staging.rglob("*")) if path.is_file() and path.name != "bundle_manifest.json"
        ],
    })
    output = bundle_root / FINAL_BUNDLE_NAME
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(staging).as_posix())
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("final review bundle contains a corrupt member")
        manifest = _json(staging / "bundle_manifest.json")
        for item in manifest["files"]:
            if hashlib.sha256(archive.read(item["path"])).hexdigest() != item["sha256"]:
                raise RuntimeError(f"final review bundle hash mismatch: {item['path']}")
    return output


def run_stage36_gate2a_final_confirmation(config_path: str | Path, run: str | Path, *, resume: bool = False) -> dict[str, Any]:
    config_path = Path(config_path).resolve()
    run = Path(run).resolve()
    complete = run / "STAGE3_6_GATE2A_FINAL_CONFIRMATION_COMPLETE_STOP.txt"
    if complete.is_file() and (ROOT / "artifacts" / "review_bundles" / FINAL_BUNDLE_NAME).is_file():
        return _json(run / "stage3_6_gate2a_final_confirmation_summary.json")
    base = normalize_convergence_config(load_experiment_config(config_path))
    final_section = dict(base.get("stage3_6_gate2a_final", {}))
    if [int(x) for x in final_section.get("seeds", SEEDS)] != list(SEEDS):
        raise ValueError("final confirmation requires the canonical paired seeds")
    previous = Path(final_section.get("source_run", "runs/stage3_6_gate2a_dof_release_50ohm"))
    previous = previous if previous.is_absolute() else ROOT / previous
    if not previous.is_dir():
        raise FileNotFoundError(f"initial Gate 2A run is missing: {previous}")
    s1, s1_path = load_frozen_s1(base)
    run = initialize(run, base)
    for directory in ("configs", "provenance", "references", "results", "tests", "trajectories", "plots"):
        (run / directory).mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_path, run / "configs" / config_path.name)
    source_cfg = _old_worker_config(previous)
    source_cfg_path = previous / "input_config.yaml"
    save(run / "provenance" / "source_manifest.json", {
        "study_type": STUDY_TYPE,
        "source_run": str(previous),
        "source_config": str(source_cfg_path),
        "source_config_sha256": _sha256(source_cfg_path),
        "s1_path": str(s1_path),
        "s1_sha256": _sha256(s1_path),
        "final_config_sha256": _sha256(config_path),
        "termination": {"source_ohm": 50.0, "load_ohm": 50.0},
        "optimizer": "L-SHADE",
        "objective_unchanged": True,
        "validation_protocol_unchanged": True,
        "prohibited_work": ["G1 64k", "G3", "50/25", "50/100", "asymmetric", "Gate 2B", "Phase D", "Stage 4", "auto-resume"],
    })
    _copy_reference_records(previous, run, (G1, G2))
    resume_provenance = _copy_resume_source(previous, run, G12)
    g1_records = _annotate_records(run, G1, gate2a_group_records(previous, G1), source="historical_gate2a", mode="reused_reference", terminal=32000)
    g2_reference = _annotate_records(run, G2, gate2a_group_records(previous, G2), source="historical_gate2a", mode="reused_reference", terminal=32000)
    _require_records(g1_records, G1, (16000, 32000))
    _require_records(g2_reference, G2, (16000, 32000))

    # Exact 32k-terminal continuation of the existing G1+G2 16k checkpoints.
    _run_release(run, source_cfg, G12, s1, terminal=32000, budgets=(16000, 32000), resume=True,
                 workers=int(final_section.get("workers", 3)))
    g12_records = _annotate_records(run, G12, gate2a_group_records(run, G12), source="final_confirmation", mode="resume_continuation", terminal=32000)
    _require_records(g12_records, G12, (16000, 32000))

    # A 64k terminal horizon is intentionally a fresh run.  The historical
    # G2 checkpoint is retained only as a reference because the backend rejects
    # loading a 32k terminal checkpoint into a 64k terminal backend.
    g2_cfg = _worker_config(source_cfg, 64000)
    _run_release(run, g2_cfg, G2, s1, terminal=64000, budgets=(32000, 64000), resume=False,
                 workers=int(final_section.get("workers", 3)))
    g2_fresh = _annotate_records(run, G2, gate2a_group_records(run, G2), source="final_confirmation", mode="fresh_64k_terminal", terminal=64000)
    _require_records(g2_fresh, G2, (32000, 64000))

    baseline = reuse_gate2a_baseline(run, base.get("stage3_6_gate2a", {}), list(SEEDS))
    entries = []
    for record in baseline:
        entries.append({"group": BASELINE_GROUP, "record": record, "budget": int(record.get("requested_unique_design_budget", record.get("current_budget", 0))), "terminal": 32000, "mode": "reused_reference", "source_run": str(previous), "record_path": record.get("stage3_6_source"), "source_config_sha256": _sha256(source_cfg_path), "release_schema_sha256": None})
    for group_records in (g1_records, g2_reference, g12_records, g2_fresh):
        for record in group_records:
            source = record.get("_source", "final_confirmation")
            mode = record.get("_mode", "reused_reference")
            budget = int(record.get("requested_unique_design_budget", record.get("current_budget", 0)))
            checkpoint = None
            checkpoint_sha = None
            if group_records is g12_records and budget == 32000:
                item = next(x for x in resume_provenance["checkpoints"] if int(x["seed"]) == int(record["seed"]))
                checkpoint = item["source_checkpoint"]
                checkpoint_sha = item["source_checkpoint_sha256"]
            entries.append({
                "group": record["stage3_6_group"], "record": record, "budget": budget,
                "terminal": int(record.get("terminal_budget", record.get("population_schedule_terminal_budget", record.get("_terminal", 32000)))),
                "mode": mode, "source_run": str(previous) if source == "historical_gate2a" else str(run),
                "record_path": record.get("_record_path", record.get("stage3_6_source")),
                "source_checkpoint": checkpoint, "source_checkpoint_sha256": checkpoint_sha,
                "source_config_sha256": _sha256(source_cfg_path),
                "release_schema_sha256": hashlib.sha256(json.dumps(record.get("release_schema", {}), sort_keys=True).encode()).hexdigest() if record.get("release_schema") else None,
                "fresh_terminal_comparison_note": "fresh 64k-terminal trajectory; compare as an operational budget result, not a pure continuation" if mode == "fresh_64k_terminal" else None,
            })
    record_map = {BASELINE_GROUP: baseline, G1: [x["record"] for x in entries if x["group"] == G1], G2: [x["record"] for x in entries if x["group"] == G2], G12: [x["record"] for x in entries if x["group"] == G12]}
    grid = common_validation_grid(base, record_map)
    grid_id = hashlib.sha256(np.asarray(grid, dtype="<f8").tobytes()).hexdigest()
    rows = []
    for entry in entries:
        rows.append(_record_row(base, entry["group"], entry["record"], grid,
                                source=entry["source_run"], mode=entry["mode"], terminal=entry["terminal"],
                                record_path=str(entry.get("record_path")), validation_grid_id=grid_id))
    save(run / "results" / "common_validation_grid.json", {"grid_id": grid_id, "frequency_count": int(len(grid)), "grid_source": "final confirmation aggregate validation grid"})
    np.savetxt(run / "results" / "common_validation_grid_hz.csv", grid, header="frequency_hz", comments="")
    promotion = _promotion(rows, final_section)
    save(run / "results" / "g1_g2_64k_promotion_decision.json", promotion)

    optional_entries = []
    if bool(promotion["promotion"]) and bool(final_section.get("optional_g1_g2_64k", True)):
        optional_root = run / "optional_g1_g2_64k"
        optional_root.mkdir(parents=True, exist_ok=True)
        optional_cfg = _worker_config(source_cfg, 64000)
        _run_release(optional_root, optional_cfg, G12, s1, terminal=64000, budgets=(32000, 64000), resume=False,
                     workers=int(final_section.get("workers", 3)))
        optional_records = _annotate_records(optional_root, G12, gate2a_group_records(optional_root, G12), source="optional_confirmation", mode="fresh_64k_terminal", terminal=64000)
        _require_records(optional_records, G12, (32000, 64000))
        for record in optional_records:
            optional_entries.append({
                "group": G12, "record": record, "budget": int(record["requested_unique_design_budget"]),
                "terminal": 64000, "mode": "fresh_64k_terminal", "source_run": str(optional_root),
                "record_path": record.get("_record_path"), "source_config_sha256": _sha256(source_cfg_path),
                "release_schema_sha256": hashlib.sha256(json.dumps(record.get("release_schema", {}), sort_keys=True).encode()).hexdigest(),
                "fresh_terminal_comparison_note": "optional promoted G1+G2 fresh 64k-terminal trajectory",
            })
        entries.extend(optional_entries)
        for entry in optional_entries:
            rows.append(_record_row(base, G12, entry["record"], grid, source=entry["source_run"], mode=entry["mode"], terminal=64000, record_path=str(entry["record_path"]), validation_grid_id=grid_id))
    else:
        save(run / "results" / "optional_g1_g2_64k_status.json", {"status": "NOT_RUN", "reason": promotion["interpretation"]})

    write_gate2a_csv(run / "results" / "all_seed_results.csv", rows)
    write_gate2a_csv(run / "results" / "validation_metrics.csv", rows)
    write_gate2a_csv(run / "results" / "paired_comparison.csv", [item for metric in ("max_violation", "sum_violation", "worst_il_db", "ripple_db") for item in _wide_paired(rows, metric)])
    write_gate2a_csv(run / "results" / "optimized_parameters.csv", [{"group": row["group"], "seed": row["seed"], "budget": row["budget"], **json.loads(row["design"])} for row in rows])
    utilization = [{"group": row["group"], "seed": row["seed"], "budget": row["budget"], "utilization": row["released_dof_utilization"]} for row in rows if row["group"] not in (BASELINE_GROUP,)]
    write_gate2a_csv(run / "results" / "released_dof_utilization.csv", utilization)
    constraints = []
    for row in rows:
        for name, value in json.loads(row["all_violations"]).items():
            constraints.append({"group": row["group"], "seed": row["seed"], "budget": row["budget"], "constraint": name, "violation": value})
    write_gate2a_csv(run / "results" / "constraint_breakdown.csv", constraints)

    runtime = _runtime_rows(entries, run, grid_id, _sha256(config_path))
    write_gate2a_csv(run / "results" / "runtime_comparison.csv", runtime)
    convergence = [{"group": entry["group"], "seed": entry["record"]["seed"], "budget": entry["budget"], "terminal_horizon": entry["terminal"], "mode": entry["mode"], "last_significant_improvement_evaluation": _trace_last_improvement(entry["record"], entry["budget"])[0], "fraction_of_budget_at_last_significant_improvement": _trace_last_improvement(entry["record"], entry["budget"])[1], "trace_points": len(entry["record"].get("best_so_far_trace", []))} for entry in entries]
    write_gate2a_csv(run / "results" / "convergence_summary.csv", convergence)
    boundary = [{"group": entry["group"], "seed": entry["record"]["seed"], "budget": entry["budget"], "boundary_repair_counts": json.dumps(_clean(entry["record"].get("boundary_repair_counts", {})), sort_keys=True), "hard_bound_reached_by_variable": json.dumps(_clean(entry["record"].get("hard_bound_reached_by_variable", {})), sort_keys=True)} for entry in entries]
    write_gate2a_csv(run / "results" / "boundary_occupancy.csv", boundary)
    save(run / "trajectories" / "best_so_far.json", [{"group": entry["group"], "seed": entry["record"]["seed"], "budget": entry["budget"], **item} for entry in entries for item in entry["record"].get("best_so_far_trace", [])])
    write_gate2a_csv(run / "trajectories" / "best_so_far.csv", _json(run / "trajectories" / "best_so_far.json"))
    plot_paths = _write_plots(run, rows, entries)
    tests = _run_tests(run)
    questions = _answer_questions(rows, promotion, runtime)
    summary = {
        "study_type": STUDY_TYPE,
        "phase": "Gate2A_final_confirmation_complete",
        "decision": "FINAL_CONFIRMATION_READY_FOR_REVIEW",
        "zsource_ohm": 50.0, "zload_ohm": 50.0,
        "common_validation_grid_id": grid_id,
        "common_validation_frequency_count": int(len(grid)),
        "arms": {"G1_G2_32k": "completed_by_checkpoint_continuation", "G2_64k": "completed_fresh_64k_terminal", "G1_G2_64k": "completed" if optional_entries else "not_run"},
        "promotion_decision": promotion,
        "paired_seed_count": len(SEEDS),
        "statistical_claim": "operational paired evidence only; three seeds are not statistical certification",
        "tests": tests,
        "review_questions": questions,
        "plot_paths": plot_paths,
        "prohibited_work_started": False,
        "hard_stop_after_bundle": True,
    }
    save(run / "stage3_6_gate2a_final_confirmation_summary.json", summary)
    bundle = _build_bundle(run, summary, config_path, previous)
    summary["review_bundle"] = str(bundle)
    save(run / "stage3_6_gate2a_final_confirmation_summary.json", summary)
    _write_text(run / "STAGE3_6_GATE2A_FINAL_CONFIRMATION_COMPLETE_STOP.txt", f"Review bundle: {bundle}\nHard stop: no Gate 2B, Phase D, Stage 4, asymmetric termination, or additional high-budget run.\n")
    return summary


__all__ = ["run_stage36_gate2a_final_confirmation"]
