"""Stage 3.7B-R2 / 3.7C literature-COM B28 fast screen.

This study owns the R2 gates and reuses the frozen Stage 3.6 G1_G2 release
schema and L-SHADE backend.  It never changes the COM equations, objective,
search bounds, topology, wiring, or validation-grid definition.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import matplotlib.pyplot as plt
import numpy as np
import yaml

from ..core.metrics import geometry, measure, search_grid
from ..core.models import FixedProvider
from ..core.network import evaluate
from ..io.config import load_experiment_config
from ..io.run_store import initialize
from ..io.serialization import save
from ..optimizers.lshade import LShadeBackend
from ..optimizers.selection import DEFAULT_COMPARATOR, rank
from ..optimization.convergence_metrics import last_significant_improvement
from ..studies.optimizer_ab import lshade_record
from .stage3_6_gate2a import (
    WIRING,
    ReleasedFilterDesign,
    decode_release,
    release_bounds,
    release_schema,
    simulate_released_filter,
)
from .stage3_7b_r1_normalized_literature_com_validation import (
    clean_value,
    fixed_response,
    load_reference,
    native_resonator,
    phase_sensitivity,
    plot_b28,
    plot_native,
    roundtrip,
    run_pytest,
)
from ..core.literature_com import profile_from_mapping


ROOT = Path(__file__).resolve().parents[3]
STUDY_TYPE = "stage3_7b_r2_stage3_7c_literature_com_b28_fast_screen"
RELEASE_GROUP = "G1_G2"
SEEDS = (20260917, 20260918)
BUDGET = 8000
CHECKPOINTS = (2000, 4000, 6000, 8000)
STOP_COMPLETE = "STAGE3_7C_LITERATURE_COM_B28_FAST_SCREEN_COMPLETE_STOP"
STOP_VALIDATION_FAIL = "STAGE3_7C_LITERATURE_COM_VALIDATION_FAIL_STOP"
STOP_FEM = "STAGE3_7C_FEM_EXTRACTION_RECOMMENDED_STOP"


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(args: list[str]) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True,
            check=True, encoding="utf-8",
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"UNAVAILABLE: {exc}"


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(set().union(*(row.keys() for row in rows))) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def _active_constraint(violations: Mapping[str, Any]) -> str:
    values = {str(key): float(value) for key, value in violations.items()}
    if not values:
        return "none"
    maximum = max(values.values())
    return ";".join(sorted(
        key for key, value in values.items() if abs(value - maximum) <= 1e-12
    ))


def _load_profile(config_path: Path, raw: Mapping[str, Any]):
    profile_path = (config_path.parent / raw["literature_profile_file"]).resolve()
    profile_data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    return profile_from_mapping(profile_data), profile_data, profile_path


def _native_gate(native: Mapping[str, Any], roundtrip_pass: bool) -> tuple[str, dict[str, Any]]:
    feature = native["feature"]
    diagnostics = native["diagnostics"]
    anti = feature.get("selected_antiresonance_frequency_hz")
    resonance = float(feature["resonance_frequency_hz"])
    separation = feature.get("frequency_separation_hz")
    passivity = feature.get("passivity_status") == "PASS"
    finite = all(np.isfinite(float(value)) for value in (
        feature["f_sync_hz"], feature["f_lower_coupling_edge_hz"],
        feature["f_upper_coupling_edge_hz"], resonance,
    ))
    plausible_order = (
        anti is not None and float(anti) > resonance
        and separation is not None
        and float(separation) >= float(feature["minimum_separation_hz"])
    )
    frequency_scale_ok = float(feature["resonance_frequency_relative_error"]) <= 0.05
    if roundtrip_pass and passivity and finite and plausible_order and frequency_scale_ok:
        status = "NATIVE_RESONATOR_PROVISIONAL_PASS"
    else:
        status = "NATIVE_RESONATOR_FAIL"
    return status, {
        "status": status,
        "roundtrip_pass": bool(roundtrip_pass),
        "passivity": bool(passivity),
        "finite_response": bool(np.isfinite(native["y"]).all()),
        "physically_separated_antiresonance": bool(plausible_order),
        "frequency_scale_ok": bool(frequency_scale_ok),
        "diagnostics": diagnostics,
    }


def _test_gate(out: Path) -> dict[str, Any]:
    commands = {
        "targeted_antiresonance_feature_tests": ["-q", "tests/unit/studies/test_stage3_7b_r2_features.py"],
        "normalization_and_provider_tests": [
            "-q", "tests/unit/core/test_literature_com.py", "tests/unit/core/test_material_profiles.py",
        ],
        "com_analytic_limit_tests": ["-q", "tests/unit/core/test_physics.py"],
        "network_tests": ["-q", "tests/unit/core/test_reference.py", "tests/unit/core/test_scalar_regression.py"],
        "full_regression": [],
    }
    results = {}
    output_dir = out / "metadata" / "test_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, args in commands.items():
        result = run_pytest(args)
        results[name] = result
        (output_dir / f"{name}.stdout.txt").write_text(result.get("stdout", ""), encoding="utf-8")
        (output_dir / f"{name}.stderr.txt").write_text(result.get("stderr", ""), encoding="utf-8")
    return results


def _metric_rows(m0: Mapping[str, Any], mlit: Mapping[str, Any], reference: Mapping[str, Any], design: Any) -> list[dict[str, Any]]:
    def row(profile_id: str, result: Mapping[str, Any], status: str) -> dict[str, Any]:
        metrics = result["metrics"]
        violations = result["violations"]
        return {
            "profile_id": profile_id,
            "status": status,
            "grid_id": reference["grid_id"],
            "zin_ohm": 50.0,
            "zout_ohm": 50.0,
            "wiring": WIRING,
            "wavelength_um": design.wavelength_um,
            "aperture_um": design.aperture_um,
            "max_violation": result["max_violation"],
            "sum_violation": float(sum(violations.values())),
            "worst_passband_il_db": metrics["worst_il_db"],
            "worst_il_db": metrics["worst_il_db"],
            "ripple_db": metrics["ripple_db"],
            "input_vswr": metrics["input_vswr"],
            "output_vswr": metrics["output_vswr"],
            "source_return_loss_db_min": metrics["source_return_loss_db_min"],
            "load_return_loss_db_min": metrics["load_return_loss_db_min"],
            "stop_0_attenuation_db": metrics["stop_attenuation_db"][0],
            "stop_1_attenuation_db": metrics["stop_attenuation_db"][1],
            "stop_2_attenuation_db": metrics["stop_attenuation_db"][2],
            "stop_3_attenuation_db": metrics["stop_attenuation_db"][3],
            "active_limiting_constraint": _active_constraint(violations),
            "mode_peak_frequency_hz": float(reference["grid"][np.argmax(result["network"]["gt"])]),
            "mode_peak_gain": float(np.max(result["network"]["gt"])),
            "passivity": result["network_passivity"],
            "reciprocity_error": result["diagnostics"]["reciprocity_error"],
            "finite_response": bool(np.isfinite(result["network"]["s"]).all()),
        }

    m0_row = row("M0", m0, "CURRENT_M0_CONTROL")
    mlit_row = row("MLIT", mlit, "LITERATURE_DERIVED_FIXED_GEOMETRY")
    delta = {"profile_id": "MLIT_MINUS_M0", "status": "METRIC_DELTA"}
    numeric_fields = [
        "max_violation", "sum_violation", "worst_passband_il_db", "worst_il_db",
        "ripple_db", "input_vswr", "output_vswr", "source_return_loss_db_min",
        "load_return_loss_db_min", "stop_0_attenuation_db", "stop_1_attenuation_db",
        "stop_2_attenuation_db", "stop_3_attenuation_db", "mode_peak_frequency_hz",
        "mode_peak_gain", "reciprocity_error",
    ]
    for field in numeric_fields:
        delta[field] = float(mlit_row[field]) - float(m0_row[field])
    delta["grid_id"] = reference["grid_id"]
    delta["zin_ohm"] = 50.0
    delta["zout_ohm"] = 50.0
    delta["wiring"] = WIRING
    delta["delta_definition"] = "MLIT - M0"
    return [m0_row, mlit_row, delta]


def _fixed_stability(m0: Mapping[str, Any], mlit: Mapping[str, Any], grid: np.ndarray) -> tuple[str, dict[str, Any]]:
    checks = {
        "finite_m0": bool(np.isfinite(m0["network"]["s"]).all()),
        "finite_mlit": bool(np.isfinite(mlit["network"]["s"]).all()),
        "m0_passive": bool(m0["network_passivity"]),
        "mlit_passive": bool(mlit["network_passivity"]),
        "m0_reciprocal": float(m0["diagnostics"]["reciprocity_error"]) <= 1e-7,
        "mlit_reciprocal": float(mlit["diagnostics"]["reciprocity_error"]) <= 1e-7,
        "b28_grid_present": bool(np.any((grid >= 758e6) & (grid <= 803e6))),
        "m0_b28_mode_finite": bool(np.isfinite(m0["network"]["gt"]).any()),
        "mlit_b28_mode_finite": bool(np.isfinite(mlit["network"]["gt"]).any()),
    }
    stable = all(checks.values())
    return ("B28_FIXED_PROFILE_STABLE" if stable else "B28_FIXED_PROFILE_UNSTABLE"), checks


def _backend_config(cfg: Mapping[str, Any], terminal: int, dimension: int, hard_bounds: np.ndarray) -> dict[str, Any]:
    values = dict(cfg.get("stage3_3", {}).get("lshade", {}))
    values.update({
        "total_budget": int(terminal),
        "hard_max_budget": int(terminal),
        "population_schedule_terminal_budget": int(terminal),
        "initial_population": max(4, 18 * int(dimension)),
        "hard_bounds": np.asarray(hard_bounds, dtype=float).tolist(),
    })
    return values


def _literature_evaluator(cfg: Mapping[str, Any], provider: Any, frequencies: np.ndarray):
    frequency_ref = [np.asarray(frequencies, dtype=float)]

    def evaluator(vector):
        design = decode_release(vector, RELEASE_GROUP)
        try:
            _dims, geometry_violations = geometry(design, cfg["constraints"])
            simulation = simulate_released_filter(
                design, provider, frequency_ref[0], cfg["center"], wiring=WIRING,
            )
            network = evaluate(simulation.y_parameters, 50.0, 50.0)
            if np.max(network["gt"]) > 1.0 + 1e-7:
                raise ValueError("Nonpassive power gain")
            record = measure(frequency_ref[0], network, design, cfg)
            record["diagnostics"] = simulation.diagnostics
        except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
            geometry_violations = locals().get("geometry_violations", [])
            return {
                "design": asdict(design),
                "metrics": {"worst_il_db": float("inf"), "ripple_db": float("inf")},
                "violations": {
                    "geometry": max(geometry_violations, default=0.0),
                    "numerical_failure": 1.0,
                },
                "max_violation": 1.0,
                "sum_violation": 1.0 + sum(geometry_violations),
                "feasible": False,
                "failure": str(exc),
                "objective": float("inf"),
                "search_scalar_objective": float("inf"),
            }
        record = dict(record)
        record["design"] = asdict(design)
        record.setdefault("violations", {})["geometry"] = max(geometry_violations, default=0.0)
        record["sum_violation"] = float(sum(record["violations"].values()))
        record["max_violation"] = float(max(record["violations"].values(), default=0.0))
        record["feasible"] = bool(record["max_violation"] <= 1e-10)
        return record

    evaluator.frequency_ref = frequency_ref
    return evaluator


def _checkpoint_row(record: Mapping[str, Any], seed: int, budget: int, provider_id: str) -> dict[str, Any]:
    metrics = record.get("metrics", {})
    violations = record.get("violations", {})
    trace = record.get("best_so_far_trace", [])
    # L-SHADE stores the canonical lexicographic rank in this trace rather
    # than the scalar ``primary_metric`` used by older convergence studies.
    if trace and "primary_metric" not in trace[0] and "rank_key" in trace[0]:
        trace_for_convergence = [
            {
                "unique_evaluation": row["unique_evaluation"],
                "primary_metric": row["rank_key"][1],
            }
            for row in trace
        ]
    else:
        trace_for_convergence = trace
    last_eval, last_fraction = last_significant_improvement(
        trace_for_convergence, budget,
    )
    return {
        "provider_id": provider_id,
        "seed": int(seed),
        "checkpoint_budget": int(budget),
        "best_max_violation": float(record.get("max_violation", np.inf)),
        "best_sum_violation": float(record.get("sum_violation", np.inf)),
        "best_objective": float(record.get("objective", np.inf)),
        "best_worst_il_db": float(metrics.get("worst_il_db", np.inf)),
        "best_ripple_db": float(metrics.get("ripple_db", np.inf)),
        "feasible": bool(record.get("feasible", False)),
        "active_limiting_constraint": _active_constraint(violations),
        "last_meaningful_improvement_evaluation": last_eval,
        "last_meaningful_improvement_fraction": last_fraction,
        "unique_evaluations": int(record.get("unique_decoded_evaluations", 0)),
        "geometry": json.dumps(clean_value(record.get("design", {})), sort_keys=True),
    }


def _optimize_seed(
    out: Path, cfg: Mapping[str, Any], provider: Any, provider_id: str,
    s1: Mapping[str, Any], seed: int, resume: bool,
) -> list[dict[str, Any]]:
    active_bounds, hard_bounds, integer_indices = release_bounds(RELEASE_GROUP, s1)
    schema = release_schema(RELEASE_GROUP, s1)
    seed_dir = out / "optimization" / provider_id / f"seed{int(seed)}"
    seed_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = seed_dir / "optimizer_checkpoint.json"
    trajectory_path = seed_dir / "trajectory_metadata.json"
    resume_used = bool(resume and checkpoint_path.exists())
    if resume_used:
        metadata = json.loads(trajectory_path.read_text(encoding="utf-8"))
        if metadata.get("release_schema") != schema:
            raise ValueError("R2 checkpoint release schema mismatch")
    else:
        metadata = {"last_completed_budget": 0}

    frequencies = np.unique(search_grid(cfg["spec"], cfg))
    evaluator = _literature_evaluator(cfg, provider, frequencies)
    fingerprint = hashlib.sha256(json.dumps({
        "cfg": cfg, "provider_id": provider_id, "seed": int(seed),
        "schema": schema, "active_bounds": active_bounds.tolist(),
        "hard_bounds": hard_bounds.tolist(), "checkpoints": list(CHECKPOINTS),
    }, sort_keys=True, default=str).encode()).hexdigest()
    backend = LShadeBackend(
        active_bounds,
        seed=int(seed),
        config=_backend_config(cfg, BUDGET, len(active_bounds), hard_bounds),
        integer_indices=integer_indices,
        comparator=DEFAULT_COMPARATOR,
        source_config_fingerprint=fingerprint,
    )
    if resume_used:
        backend.load_checkpoint(checkpoint_path)
        backend.set_evaluator(evaluator)
        if getattr(backend, "active_frequency_grid", []):
            evaluator.frequency_ref[0] = np.asarray(backend.active_frequency_grid, dtype=float)
    else:
        backend.initialize(evaluator)
        backend.set_frequency_grid(frequencies, version=1)

    snapshots = []
    events = []
    started_wall = time.monotonic()
    started_cpu = time.process_time()
    last_completed = int(metadata.get("last_completed_budget", 0))
    for trajectory_index, budget in enumerate(CHECKPOINTS):
        result_path = seed_dir / f"B{budget}.json"
        if resume_used and last_completed >= budget and result_path.exists():
            snapshots.append(json.loads(result_path.read_text(encoding="utf-8")))
            continue
        optimizer_started = time.monotonic()
        if backend.unique_evaluations < budget:
            backend.advance_to_unique_budget(budget)
        event = {
            "event": "convergence_checkpoint",
            "checkpoint_budget": int(budget),
            "frequency_grid_version": int(backend.frequency_grid_version),
            "grid_fixed": True,
            "unique_designs_charged": 0,
        }
        events.append(event)
        record = lshade_record(
            backend, WIRING, seed, budget, checkpoint_path, events,
            started_wall, started_cpu, disk_resume_used=resume_used,
            trajectory_index=trajectory_index,
            optimizer_wall_time_s=time.monotonic() - optimizer_started,
            validation_wall_time_s=0.0,
            total_trial_wall_time_s=time.monotonic() - started_wall,
        )
        record.update({
            "study_type": STUDY_TYPE,
            "provider_id": provider_id,
            "release_group": RELEASE_GROUP,
            "release_schema": schema,
            "release_dimension": int(schema["dimension"]),
            "source_impedance_ohm": 50.0,
            "load_impedance_ohm": 50.0,
            "termination": {"source_ohm": 50.0, "load_ohm": 50.0, "source_is_real": True, "load_is_real": True},
            "convergence_checkpoint_budget": int(budget),
            "cold_start": True,
            "warm_start": False,
            "bound_expansion": False,
            "dof_expansion": False,
        })
        record = clean_value(record)
        save(result_path, record)
        backend.save_checkpoint(checkpoint_path)
        metadata = {
            "last_completed_budget": int(budget),
            "provider_id": provider_id,
            "seed": int(seed),
            "release_schema": schema,
            "active_bounds": active_bounds.tolist(),
            "hard_bounds": hard_bounds.tolist(),
            "checkpoints": list(CHECKPOINTS),
            "budget": BUDGET,
            "cold_start": True,
            "warm_start": False,
        }
        save(trajectory_path, metadata)
        snapshots.append(record)
        last_completed = budget
    return snapshots


def _validated_final_rows(out: Path, provider: Any, cfg: Mapping[str, Any], reference: Mapping[str, Any], snapshots_by_seed: Mapping[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for seed, snapshots in snapshots_by_seed.items():
        if not snapshots:
            continue
        record = snapshots[-1]
        design = ReleasedFilterDesign(**{
            key: record["design"][key]
            for key in ReleasedFilterDesign.__dataclass_fields__
            if key in record.get("design", {})
        })
        result = fixed_response(design, provider, reference["grid"], cfg)
        metrics = result["metrics"]
        rows.append({
            "provider_id": provider.profile_id,
            "seed": int(seed),
            "checkpoint_budget": BUDGET,
            "validation_grid_id": reference["grid_id"],
            "max_violation": result["max_violation"],
            "sum_violation": float(sum(result["violations"].values())),
            "worst_passband_il_db": metrics["worst_il_db"],
            "ripple_db": metrics["ripple_db"],
            "input_vswr": metrics["input_vswr"],
            "output_vswr": metrics["output_vswr"],
            "stop_0_attenuation_db": metrics["stop_attenuation_db"][0],
            "stop_1_attenuation_db": metrics["stop_attenuation_db"][1],
            "stop_2_attenuation_db": metrics["stop_attenuation_db"][2],
            "stop_3_attenuation_db": metrics["stop_attenuation_db"][3],
            "active_limiting_constraint": _active_constraint(result["violations"]),
            "feasible": result["feasible"],
            "passivity": result["network_passivity"],
            "reciprocity_error": result["diagnostics"]["reciprocity_error"],
            "geometry": json.dumps(asdict(design), sort_keys=True),
            "objective": record.get("objective"),
            "search_best_max_violation": record.get("max_violation"),
            "search_best_feasible": record.get("feasible"),
        })
    return rows


def _geometry_rows(reference: Mapping[str, Any], final_rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [{
        "profile_id": "M0",
        "design_role": "STAGE3_6_50OHM_REFERENCE",
        "seed": reference["row"].get("seed"),
        **json.loads(reference["row"]["design"]),
    }]
    for row in final_rows:
        rows.append({
            "profile_id": row["provider_id"],
            "design_role": "MLIT_OPTIMIZED_FAST_SCREEN",
            "seed": row["seed"],
            **json.loads(row["geometry"]),
        })
    output = []
    for row in rows:
        wavelength = float(row["wavelength_um"])
        output.append({
            **row,
            "aperture_over_main_wavelength": float(row["aperture_um"]) / wavelength,
            "center_wavelength_over_main_wavelength": float(row.get("center_wavelength_um") or wavelength) / wavelength,
            "reflector_wavelength_over_main_wavelength": float(row.get("reflector_wavelength_um") or wavelength) / wavelength,
            "io_to_center_pair_ratio": float(row["io_idt_pairs"]) / max(float(row["center_idt_pairs"]), 1.0),
            "reflector_electrodes_per_side": float(row["reflector_electrodes"]) / 2.0,
            "idt_gap_over_wavelength": float(row["idt_gap_lambda"]),
            "reflector_gap_over_wavelength": float(row["reflector_gap_lambda"]),
        })
    return output


def _plot_seed_comparison(final_rows: list[Mapping[str, Any]], out: Path) -> None:
    if not final_rows:
        return
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    seeds = [str(row["seed"]) for row in final_rows]
    axes[0].bar(seeds, [float(row["max_violation"]) for row in final_rows])
    axes[0].set_title("MLIT best max violation")
    axes[0].set_ylabel("max violation")
    axes[1].bar(seeds, [float(row["worst_passband_il_db"]) for row in final_rows])
    axes[1].set_title("MLIT best passband IL")
    axes[1].set_ylabel("worst IL [dB]")
    fig.tight_layout()
    fig.savefig(out / "plots" / "b28_literature_com_seed_comparison.png", dpi=160)
    plt.close(fig)


def _plot_corrected_native(native: Mapping[str, Any], out: Path) -> None:
    frequencies = np.asarray(native["frequencies_hz"], dtype=float) / 1e9
    y = np.asarray(native["y"], dtype=complex)
    feature = native["feature"]
    fig, axes = plt.subplots(3, 1, figsize=(9, 9), sharex=True)
    axes[0].plot(frequencies, np.real(y), label="G = Re(Y)")
    axes[1].plot(frequencies, np.imag(y), label="B = Im(Y)")
    axes[2].plot(frequencies, np.abs(y), label="|Y|")
    for axis in axes:
        axis.axvline(feature["f_sync_hz"] / 1e9, color="k", linestyle="--", alpha=0.65, label="f_sync")
        axis.axvline(feature["f_lower_coupling_edge_hz"] / 1e9, color="tab:green", linestyle=":", alpha=0.8, label="lower edge")
        axis.axvline(feature["f_upper_coupling_edge_hz"] / 1e9, color="tab:orange", linestyle=":", alpha=0.8, label="upper edge")
        axis.grid(True, alpha=0.3)
        axis.legend(loc="best")
    axes[0].set_ylabel("G [S]")
    axes[1].set_ylabel("B [S]")
    axes[2].set_ylabel("|Y| [S]")
    axes[2].set_xlabel("Frequency [GHz]")
    fig.suptitle("R2 corrected native resonator features")
    fig.tight_layout()
    fig.savefig(out / "plots" / "corrected_native_resonator_g_b_abs_y.png", dpi=160)
    plt.close(fig)


def _plot_native_feature_locations(native: Mapping[str, Any], out: Path) -> None:
    frequencies = np.asarray(native["frequencies_hz"], dtype=float) / 1e9
    y = np.asarray(native["y"], dtype=complex)
    feature = native["feature"]
    fig, axis = plt.subplots(figsize=(9, 4.5))
    axis.plot(frequencies, np.real(y), label="G")
    axis.plot(frequencies, np.abs(y), label="|Y|")
    lines = (
        ("f_sync", feature["f_sync_hz"], "k", "--"),
        ("lower edge", feature["f_lower_coupling_edge_hz"], "tab:green", ":"),
        ("upper edge", feature["f_upper_coupling_edge_hz"], "tab:orange", ":"),
        ("selected resonance", feature["resonance_frequency_hz"], "tab:blue", "-"),
        ("selected antiresonance", feature["selected_antiresonance_frequency_hz"], "tab:red", "-"),
    )
    for label, value, color, linestyle in lines:
        if value is not None:
            axis.axvline(float(value) / 1e9, color=color, linestyle=linestyle, alpha=0.75, label=label)
    axis.set_xlabel("Frequency [GHz]")
    axis.set_ylabel("Admittance scale [S]")
    axis.set_title("Native feature locations and coupling-edge references")
    axis.grid(True, alpha=0.3)
    axis.legend(loc="best", ncol=2)
    fig.tight_layout()
    fig.savefig(out / "plots" / "native_feature_locations.png", dpi=160)
    plt.close(fig)


def _plot_geometry(rows: list[Mapping[str, Any]], out: Path) -> None:
    labels = [f"{row['profile_id']}\n{row.get('seed', '')}" for row in rows]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].bar(labels, [float(row["aperture_over_main_wavelength"]) for row in rows])
    axes[0].set_ylabel("aperture / main wavelength")
    axes[1].bar(labels, [float(row["idt_gap_over_wavelength"]) for row in rows])
    axes[1].set_ylabel("IDT gap / wavelength")
    fig.tight_layout()
    fig.savefig(out / "plots" / "b28_literature_com_normalized_geometry.png", dpi=160)
    plt.close(fig)


def _direction_and_recommendation(reference: Mapping[str, Any], final_rows: list[Mapping[str, Any]]) -> tuple[str, str]:
    if not final_rows:
        return "LITERATURE_PROFILE_NOT_READY", "FEM_BEFORE_STAGE3_8"
    reference_design = json.loads(reference["row"]["design"])
    optimized = [json.loads(row["geometry"]) for row in final_rows]
    io_boundary = all(int(item["io_idt_pairs"]) == 8 for item in optimized)
    stop_1_dominant = all("stop_1" in str(row["active_limiting_constraint"]) for row in final_rows)
    aperture_values = [float(item["aperture_um"]) / float(item["wavelength_um"]) for item in optimized]
    reference_aperture = float(reference_design["aperture_um"]) / float(reference_design["wavelength_um"])
    aperture_stable = all(abs(value - reference_aperture) / max(abs(reference_aperture), 1e-12) <= 0.25 for value in aperture_values)
    direction = "MATERIAL_DIRECTION_ROBUST" if io_boundary and stop_1_dominant and aperture_stable else "MATERIAL_DIRECTION_SENSITIVE"
    recommendation = "USE_MLIT_AS_PRIMARY" if direction == "MATERIAL_DIRECTION_ROBUST" else "USE_M0_AND_MLIT_AS_DUAL_BASELINE"
    return direction, recommendation


def run_stage37b_r2_stage37c(config_path: str | Path, run_path: str | Path, resume: bool = False) -> dict[str, Any]:
    config_path = Path(config_path).resolve()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    section = dict(raw.get("stage3_7b_r2_stage3_7c", {}))
    profile, profile_data, profile_path = _load_profile(config_path, raw)
    cfg = load_experiment_config(config_path)
    out = initialize(Path(run_path).resolve(), cfg)
    (out / "results").mkdir(parents=True, exist_ok=True)
    (out / "plots").mkdir(parents=True, exist_ok=True)
    (out / "metadata").mkdir(parents=True, exist_ok=True)

    reference = load_reference({
        "gate2b_b_run_dir": section.get(
            "gate2b_b_run_dir", "runs/stage3_7_material_com_50ohm_sanity_final"
        )
    })
    s1_path = ROOT / section.get("search_space_snapshot", "artifacts/stage3_5/phase_a_revised/search_space_s1.yaml")
    s1 = yaml.safe_load(s1_path.read_text(encoding="utf-8")) or {}
    active_bounds, hard_bounds, _integer_indices = release_bounds(RELEASE_GROUP, s1)

    (out / "metadata" / "profile_snapshot.yaml").write_text(
        yaml.safe_dump(clean_value(profile_data), sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    save(out / "metadata" / "m0_snapshot.json", {
        "profile_id": "M0",
        "source_config": "configs/models/com_params_hypothetical.yaml",
        "com": clean_value(cfg["com"]),
        "zin_ohm": 50.0,
        "zout_ohm": 50.0,
        "wiring": WIRING,
    })
    save(out / "metadata" / "stage3_6_reference_design.json", clean_value({
        "run_dir": reference["run_dir"],
        "row": reference["row"],
        "design": reference["design"],
    }))
    (out / "metadata" / "g1_g2_search_space_snapshot.yaml").write_text(
        yaml.safe_dump(clean_value(s1), sort_keys=False), encoding="utf-8"
    )
    save(out / "metadata" / "g1_g2_search_space.json", {
        "release_group": RELEASE_GROUP,
        "schema": release_schema(RELEASE_GROUP, s1),
        "active_bounds": active_bounds.tolist(),
        "hard_bounds": hard_bounds.tolist(),
        "source_sha256": _sha256(s1_path),
    })
    grid_path = reference["run_dir"] / "results" / "common_validation_grid_hz.csv"
    save(out / "metadata" / "validation_grid.json", {
        "grid_id": reference["grid_id"],
        "frequency_count": int(len(reference["grid"])),
        "source": str(grid_path),
        "sha256": _sha256(grid_path),
        "array_sha256": hashlib.sha256(np.asarray(reference["grid"], dtype="<f8").tobytes()).hexdigest(),
    })
    save(out / "metadata" / "repository_audit.json", {
        "branch": _git(["branch", "--show-current"]),
        "head": _git(["rev-parse", "HEAD"]),
        "status": _git(["status", "--short"]),
        "diff_summary": _git(["diff", "--stat"]),
        "r1_artifact": "runs/stage3_7b_r1_normalized_literature_com_validation_final",
        "stage3_6_reference": str(reference["run_dir"]),
        "literature_profile": str(profile_path),
    })

    roundtrip_rows, roundtrip_pass = roundtrip(profile, float(section.get("evaluation_aperture_um", 80.0)))
    _write_csv(out / "results" / "normalization_roundtrip_tests.csv", roundtrip_rows)
    native = native_resonator(profile, section, out)
    phase = phase_sensitivity(profile, section, native, out)
    plot_native(native, out)
    _plot_corrected_native(native, out)
    _plot_native_feature_locations(native, out)
    _write_csv(out / "results" / "native_resonator_phase_diagnostics.csv", phase["rows"])
    native_status, native_gate = _native_gate(native, roundtrip_pass)
    save(out / "metadata" / "native_gate.json", native_gate)

    test_results = _test_gate(out)
    save(out / "metadata" / "test_results.json", clean_value(test_results))
    tests_pass = all(bool(result.get("passed", False)) for result in test_results.values())
    if not tests_pass or native_status == "NATIVE_RESONATOR_FAIL":
        stop = STOP_VALIDATION_FAIL
        decision = "FEM_EXTRACTION_REQUIRED" if native_status == "NATIVE_RESONATOR_FAIL" else "VALIDATION_GATE_FAILED"
        _write_csv(out / "results" / "b28_fixed_design_material_comparison.csv", [{
            "status": "NOT_RUN_VALIDATION_GATE_FAILED",
            "native_status": native_status,
            "full_regression_pass": test_results["full_regression"].get("passed", False),
        }])
        (out / "stage3_7b_r2_stage3_7c_summary.md").write_text(
            f"# Stage 3.7B-R2 / 3.7C summary\n\nValidation gate failed.\n\n- native status: `{native_status}`\n- tests passed: `{tests_pass}`\n- decision: `{decision}`\n\nHard stop: `{stop}`\n",
            encoding="utf-8",
        )
        (out / "test_summary.md").write_text(
            "# Test summary\n\n" + "\n".join(
                f"- {name}: {result.get('summary')} (returncode {result.get('returncode')})"
                for name, result in test_results.items()
            ) + "\n",
            encoding="utf-8",
        )
        (out / f"{stop}.txt").write_text(stop + "\n", encoding="utf-8")
        return {"run": str(out), "decision": decision, "stop_marker": f"{stop}.txt", "native_status": native_status}

    design = ReleasedFilterDesign(**{
        key: reference["design"][key]
        for key in ReleasedFilterDesign.__dataclass_fields__
        if key in reference["design"]
    })
    m0 = fixed_response(design, FixedProvider(cfg["com"]), reference["grid"], cfg)
    mlit = fixed_response(design, profile, reference["grid"], cfg)
    fixed_rows = _metric_rows(m0, mlit, reference, design)
    _write_csv(out / "results" / "b28_fixed_design_material_comparison.csv", fixed_rows)
    np.savez_compressed(
        out / "results" / "b28_fixed_design_material_response.npz",
        frequencies_hz=reference["grid"], m0_s=m0["network"]["s"], mlit_s=mlit["network"]["s"],
    )
    plot_b28(reference["grid"], {"m0": m0, "literature": mlit}, out)
    fixed_status, fixed_checks = _fixed_stability(m0, mlit, reference["grid"])
    save(out / "metadata" / "fixed_design_gate.json", {"status": fixed_status, "checks": fixed_checks})
    if fixed_status != "B28_FIXED_PROFILE_STABLE":
        stop = STOP_FEM
        decision = "FEM_BEFORE_STAGE3_8"
        (out / "stage3_7c_b28_literature_com_summary.md").write_text(
            f"# Stage 3.7C B28 literature-COM summary\n\nFixed-design profile gate: `{fixed_status}`.\n\nRecommendation: `{decision}`\n\nHard stop: `{stop}`\n",
            encoding="utf-8",
        )
        (out / "test_summary.md").write_text(
            "# Test summary\n\n" + "\n".join(
                f"- {name}: {result.get('summary')} (returncode {result.get('returncode')})"
                for name, result in test_results.items()
            ) + "\n", encoding="utf-8",
        )
        (out / f"{stop}.txt").write_text(stop + "\n", encoding="utf-8")
        return {"run": str(out), "decision": decision, "stop_marker": f"{stop}.txt", "native_status": native_status, "fixed_status": fixed_status}

    snapshots_by_seed = {}
    for seed in SEEDS:
        snapshots_by_seed[int(seed)] = _optimize_seed(out, cfg, profile, profile.profile_id, s1, seed, resume)
    checkpoint_rows = [
        _checkpoint_row(snapshot, seed, int(snapshot["convergence_checkpoint_budget"]), profile.profile_id)
        for seed, snapshots in snapshots_by_seed.items() for snapshot in snapshots
    ]
    _write_csv(out / "results" / "b28_literature_com_convergence_lite.csv", checkpoint_rows)
    final_rows = _validated_final_rows(out, profile, cfg, reference, snapshots_by_seed)
    _write_csv(out / "results" / "b28_literature_com_seed_results.csv", final_rows)
    for row in final_rows:
        row["active_limiting_constraint"] = row.get("active_limiting_constraint", "none")
    geometry_rows = _geometry_rows(reference, final_rows)
    _write_csv(out / "results" / "b28_literature_com_geometry_comparison.csv", geometry_rows)
    bottleneck_rows = []
    reference_design = json.loads(reference["row"]["design"])
    bottleneck_rows.append({
        "profile_id": "M0", "seed": reference["row"].get("seed"),
        "active_limiting_constraint": reference["row"].get("active_limiting_constraint"),
        "max_violation": reference["row"].get("max_violation"),
        "sum_violation": reference["row"].get("sum_violation"),
        "io_idt_pairs": reference_design["io_idt_pairs"],
    })
    for row in final_rows:
        geometry_data = json.loads(row["geometry"])
        bottleneck_rows.append({
            "profile_id": row["provider_id"], "seed": row["seed"],
            "active_limiting_constraint": row["active_limiting_constraint"],
            "max_violation": row["max_violation"], "sum_violation": row["sum_violation"],
            "io_idt_pairs": geometry_data["io_idt_pairs"],
        })
    _write_csv(out / "results" / "constraint_bottleneck_comparison.csv", bottleneck_rows)
    _plot_seed_comparison(final_rows, out)
    _plot_geometry(geometry_rows, out)

    direction, recommendation = _direction_and_recommendation(reference, final_rows)
    save(out / "metadata" / "decision.json", {
        "native_status": native_status,
        "fixed_design_status": fixed_status,
        "material_direction": direction,
        "stage3_8_material_baseline_recommendation": recommendation,
        "convergence_claim": False,
        "automatic_seed_addition": False,
        "production_topology": "current 3-IDT DMS",
        "wiring": WIRING,
        "zin_ohm": 50.0,
        "zout_ohm": 50.0,
    })
    (out / "test_summary.md").write_text(
        "# Test summary\n\n" + "\n".join(
            f"- {name}: {result.get('summary')} (returncode {result.get('returncode')}, runtime {result.get('runtime_seconds'):.3f}s)"
            for name, result in test_results.items()
        ) + "\n",
        encoding="utf-8",
    )
    (out / "stage3_7b_r2_native_feature_correction.md").write_text(
        f"# Stage 3.7B-R2 native feature correction\n\n"
        f"- profile: `{profile.profile_id}`\n"
        f"- status: `{native_status}`\n"
        f"- f_sync: {native['feature']['f_sync_hz']:.6f} Hz\n"
        f"- lower coupling-edge reference: {native['feature']['f_lower_coupling_edge_hz']:.6f} Hz\n"
        f"- upper coupling-edge reference: {native['feature']['f_upper_coupling_edge_hz']:.6f} Hz\n"
        f"- selected resonance: {native['feature']['resonance_frequency_hz']:.6f} Hz\n"
        f"- corrected antiresonance: {native['feature']['selected_antiresonance_frequency_hz']:.6f} Hz\n"
        f"- frequency separation: {native['feature']['frequency_separation_hz']:.6f} Hz\n"
        f"- selection reason: `{native['feature']['selection_reason']}`\n"
        f"- alpha phase diagnostic robust: `{phase['robust_within_2pct_f0']}` (diagnostic only; not a gate)\n"
        f"- evaluation aperture: {section.get('evaluation_aperture_um', 80.0)} um; source-device aperture is not claimed\n",
        encoding="utf-8",
    )
    (out / "stage3_7c_b28_literature_com_summary.md").write_text(
        f"# Stage 3.7C B28 literature-COM summary\n\n"
        f"- fixed-design gate: `{fixed_status}`\n"
        f"- MLIT provider: `{profile.profile_id}`\n"
        f"- topology: current 3-IDT DMS; wiring: `{WIRING}`\n"
        f"- seeds: `{list(SEEDS)}`; checkpoints: `{list(CHECKPOINTS)}`; nominal total: 16000 unique evaluations\n"
        f"- convergence claim: **not made**\n"
        f"- material-direction decision: `{direction}`\n"
        f"- Stage 3.8 recommendation: `{recommendation}`\n\n"
        "The profile is literature-derived and normalized-COM reconstructed. This "
        "fast screen does not claim calibration, experimental validation, global "
        "optimality, convergence, or final B28 performance.\n",
        encoding="utf-8",
    )
    (out / f"{STOP_COMPLETE}.txt").write_text(STOP_COMPLETE + "\n", encoding="utf-8")
    return {
        "run": str(out),
        "decision": recommendation,
        "stop_marker": f"{STOP_COMPLETE}.txt",
        "native_status": native_status,
        "fixed_status": fixed_status,
        "material_direction": direction,
        "seeds": list(SEEDS),
        "budget_per_seed": BUDGET,
    }


__all__ = ["run_stage37b_r2_stage37c"]
