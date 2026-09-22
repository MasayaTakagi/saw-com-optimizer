"""Stage 3.7B-R1 normalized literature COM validation.

R1 is deliberately a frequency-only validation stage.  It uses an explicit
80 um evaluation aperture for unit and mode checks, never treats that value as
the source-device aperture, and never launches re-optimization.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import matplotlib.pyplot as plt
import numpy as np
import yaml

from ..core.com import validate_admittance
from ..core.hybrid import ResonatorDesign, resonator_y
from ..core.literature_com import profile_from_mapping
from ..core.metrics import measure
from ..core.models import FixedProvider
from ..core.network import evaluate
from ..io.config import load_experiment_config
from .stage3_6_gate2a import ReleasedFilterDesign, WIRING, simulate_released_filter


ROOT = Path(__file__).resolve().parents[3]
SUCCESS_STOP = "STAGE3_7B_R1_NORMALIZED_COM_VALIDATION_COMPLETE_STOP"
FAIL_STOP = "STAGE3_7B_R1_VALIDATION_FAIL_STOP"


def _write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(set().union(*(row.keys() for row in rows))) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def _clean(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
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


def _git(args: list[str]) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True,
            check=True, encoding="utf-8",
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"UNAVAILABLE: {exc}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _profile_geometry(profile: Any, aperture_um: float) -> SimpleNamespace:
    return SimpleNamespace(
        wavelength_um=float(profile.wavelength_um),
        aperture_um=float(aperture_um),
    )


def _roundtrip(profile: Any, aperture_um: float) -> tuple[list[dict[str, Any]], bool]:
    geometry = _profile_geometry(profile, aperture_um)
    actual = profile.normalized_identities(geometry)
    expected = {
        "kappa_p": profile.kappa_p,
        "alpha_n": profile.alpha_n_sqrt_s,
        "capacitance_n": profile.capacitance_n_f_per_m,
        "gamma_p": profile.gamma_p,
    }
    rows = []
    for name in ("kappa_p", "alpha_n", "capacitance_n", "gamma_p"):
        value = float(actual[name])
        target = float(expected[name])
        error = abs(value - target)
        scale = max(abs(target), np.finfo(float).tiny)
        passed = bool(error / scale <= 1e-12)
        rows.append({
            "parameter": name,
            "actual": value,
            "expected": target,
            "relative_error": error / scale,
            "rtol": 1e-12,
            "status": "PASS" if passed else "FAIL",
        })
    return rows, all(row["status"] == "PASS" for row in rows)


def _local_extrema(values: np.ndarray, *, maximum: bool) -> np.ndarray:
    if maximum:
        return np.flatnonzero((values[1:-1] >= values[:-2]) & (values[1:-1] >= values[2:])) + 1
    return np.flatnonzero((values[1:-1] <= values[:-2]) & (values[1:-1] <= values[2:])) + 1


def _zero_crossings(frequencies: np.ndarray, values: np.ndarray) -> list[dict[str, float]]:
    """Return linearly interpolated zero crossings with their bracket index."""
    frequencies = np.asarray(frequencies, dtype=float)
    values = np.asarray(values, dtype=float)
    crossings: list[dict[str, float]] = []
    for index in range(len(values) - 1):
        left, right = float(values[index]), float(values[index + 1])
        if left == 0.0:
            crossing = float(frequencies[index])
        elif left * right > 0.0:
            continue
        elif right == left:
            crossing = float(frequencies[index])
        else:
            fraction = -left / (right - left)
            crossing = float(
                frequencies[index]
                + fraction * (frequencies[index + 1] - frequencies[index])
            )
        if crossings and abs(crossings[-1]["frequency_hz"] - crossing) <= np.finfo(float).eps:
            continue
        crossings.append({"frequency_hz": crossing, "bracket_index": float(index)})
    return crossings


def _zero_crossing(frequencies: np.ndarray, values: np.ndarray, near_hz: float) -> float | None:
    """Compatibility wrapper selecting the crossing nearest ``near_hz``."""
    candidates = _zero_crossings(frequencies, values)
    if not candidates:
        return None
    return min(candidates, key=lambda value: abs(value["frequency_hz"] - near_hz))["frequency_hz"]


def _extract_native_features(
    frequencies: np.ndarray,
    admittance: np.ndarray,
    resonance_index: int,
    f_sync_hz: float,
) -> dict[str, Any]:
    """Extract one physically separated resonance/antiresonance pair.

    The old diagnostic selected the nearest susceptance zero, which can be the
    resonance's own zero crossing.  Here the antiresonance must be on the
    higher-frequency side and outside a documented minimum separation.  A
    ``|Y|`` local minimum is preferred when it has a nearby susceptance zero;
    depth is the next ranking criterion and frequency is the final tie-breaker.
    """
    frequencies = np.asarray(frequencies, dtype=float)
    admittance = np.asarray(admittance, dtype=complex)
    conductance = np.real(admittance)
    susceptance = np.imag(admittance)
    admittance_abs = np.abs(admittance)
    sample_spacing = float(np.median(np.diff(frequencies)))
    minimum_separation_hz = max(5.0 * sample_spacing, 0.005 * float(f_sync_hz))
    zero_tolerance_hz = max(3.0 * sample_spacing, 0.0025 * float(f_sync_hz))

    window = (frequencies >= 0.95 * f_sync_hz) & (frequencies <= 1.05 * f_sync_hz)
    window_indices = np.flatnonzero(window)
    if len(window_indices) < 3:
        raise ValueError("native feature window must contain at least three samples")
    local_conductance_peaks = _local_extrema(conductance[window], maximum=True)
    local_abs_minima = _local_extrema(admittance_abs[window], maximum=False)
    conductance_peak_indices = window_indices[local_conductance_peaks]
    abs_minimum_indices = window_indices[local_abs_minima]
    zero_crossings = _zero_crossings(frequencies[window], susceptance[window])

    post_resonance_minima = []
    resonance_frequency_hz = float(frequencies[resonance_index])
    for index in abs_minimum_indices:
        frequency_hz = float(frequencies[index])
        separation_hz = frequency_hz - resonance_frequency_hz
        if separation_hz < minimum_separation_hz:
            continue
        nearest_zero = min(
            zero_crossings,
            key=lambda item: abs(item["frequency_hz"] - frequency_hz),
            default=None,
        )
        zero_distance_hz = (
            abs(float(nearest_zero["frequency_hz"]) - frequency_hz)
            if nearest_zero is not None else float("inf")
        )
        post_resonance_minima.append({
            "frequency_hz": frequency_hz,
            "index": int(index),
            "admittance_abs_S": float(admittance_abs[index]),
            "separation_from_resonance_hz": separation_hz,
            "nearest_b_zero_hz": (
                float(nearest_zero["frequency_hz"]) if nearest_zero is not None else None
            ),
            "b_zero_distance_hz": zero_distance_hz,
            "nearby_b_zero": bool(zero_distance_hz <= zero_tolerance_hz),
        })

    nearby = [item for item in post_resonance_minima if item["nearby_b_zero"]]
    ranked = nearby or post_resonance_minima
    selected = min(
        ranked,
        key=lambda item: (
            float(item["admittance_abs_S"]),
            float(item["b_zero_distance_hz"]),
            float(item["frequency_hz"]),
        ),
        default=None,
    )
    if selected is None:
        selection_reason = "NO_POST_RESONANCE_ABS_Y_MINIMUM_AFTER_MINIMUM_SEPARATION"
        selected_antiresonance_hz = None
        selected_b_zero_hz = None
        separation_hz = None
    else:
        selection_reason = (
            "POST_RESONANCE_ABS_Y_MINIMUM_WITH_NEARBY_B_ZERO"
            if nearby else
            "POST_RESONANCE_ABS_Y_MINIMUM_WITHOUT_NEARBY_B_ZERO"
        )
        selected_antiresonance_hz = float(selected["frequency_hz"])
        selected_b_zero_hz = selected["nearest_b_zero_hz"]
        separation_hz = float(selected["separation_from_resonance_hz"])

    candidate_rows = []
    for index in conductance_peak_indices:
        candidate_rows.append({
            "feature_type": "conductance_local_maximum",
            "frequency_hz": float(frequencies[index]),
            "index": int(index),
            "conductance_S": float(conductance[index]),
            "admittance_abs_S": float(admittance_abs[index]),
            "susceptance_S": float(susceptance[index]),
            "selected": bool(index == resonance_index),
        })
    for index in abs_minimum_indices:
        candidate_rows.append({
            "feature_type": "admittance_abs_local_minimum",
            "frequency_hz": float(frequencies[index]),
            "index": int(index),
            "conductance_S": float(conductance[index]),
            "admittance_abs_S": float(admittance_abs[index]),
            "susceptance_S": float(susceptance[index]),
            "selected": bool(selected is not None and index == selected["index"]),
            "separation_from_resonance_hz": float(frequencies[index] - resonance_frequency_hz),
            "minimum_separation_hz": minimum_separation_hz,
        })
    for crossing in zero_crossings:
        candidate_rows.append({
            "feature_type": "susceptance_zero_crossing",
            "frequency_hz": float(crossing["frequency_hz"]),
            "bracket_index": int(crossing["bracket_index"]),
            "selected": bool(
                selected_b_zero_hz is not None
                and np.isclose(crossing["frequency_hz"], selected_b_zero_hz, rtol=0.0, atol=1e-6)
            ),
            "separation_from_resonance_hz": float(crossing["frequency_hz"] - resonance_frequency_hz),
            "minimum_separation_hz": minimum_separation_hz,
        })

    return {
        "conductance_peak_indices": conductance_peak_indices,
        "abs_minimum_indices": abs_minimum_indices,
        "zero_crossings": zero_crossings,
        "post_resonance_minima": post_resonance_minima,
        "candidate_rows": candidate_rows,
        "selected_antiresonance_frequency_hz": selected_antiresonance_hz,
        "selected_b_zero_crossing_hz": selected_b_zero_hz,
        "frequency_separation_hz": separation_hz,
        "minimum_separation_hz": minimum_separation_hz,
        "zero_tolerance_hz": zero_tolerance_hz,
        "selection_reason": selection_reason,
    }


def _native_resonator(profile: Any, section: Mapping[str, Any], out: Path) -> dict[str, Any]:
    aperture_um = float(section["evaluation_aperture_um"])
    f0 = profile.velocity_m_s / (profile.wavelength_um * 1e-6)
    lo, hi = map(float, section.get("native_frequency_fraction", [0.8, 1.2]))
    points = int(section.get("native_frequency_points", 2401))
    frequencies = np.linspace(lo * f0, hi * f0, points)
    design = ResonatorDesign(
        wavelength_um=profile.wavelength_um,
        pairs=30,
        aperture_um=aperture_um,
        reflector_electrodes=30,
        gap_lambda=0.0,
    )
    y = resonator_y(design, profile, frequencies)
    diagnostics = validate_admittance(
        y[:, None, None], frequencies_hz=frequencies,
    )
    conductance = np.real(y)
    susceptance = np.imag(y)
    window = (frequencies >= 0.95 * f0) & (frequencies <= 1.05 * f0)
    candidate_indices = np.flatnonzero(window)
    resonance_index = int(candidate_indices[np.argmax(conductance[window])])
    extracted = _extract_native_features(frequencies, y, resonance_index, f0)
    anti = extracted["selected_antiresonance_frequency_hz"]
    extrema = extracted["conductance_peak_indices"]
    feature_count = int(len(extrema))
    resonance_hz = float(frequencies[resonance_index])
    scale_error = abs(resonance_hz - f0) / f0
    source_feature_comparison = "NOT_NUMERICALLY_DIGITIZED"
    if scale_error > 0.05:
        status = "RESONATOR_FREQ_FAIL"
    else:
        # The source plot does not expose machine-readable fs/fp values and
        # the phase policy is an explicit diagnostic assumption.
        status = "RESONATOR_FREQ_INCONCLUSIVE"

    rows = [{
        "frequency_hz": float(frequency),
        "conductance_S": float(g),
        "susceptance_S": float(b),
        "admittance_abs_S": float(abs(value)),
        "evaluation_aperture_um": aperture_um,
        "evaluation_aperture_not_source_geometry": True,
        "absolute_admittance_validation": "NOT_CLAIMED",
    } for frequency, g, b, value in zip(frequencies, conductance, susceptance, y)]
    _write_csv(out / "results" / "native_resonator_results.csv", rows)
    feature = {
        "status": status,
        "wavelength_um": profile.wavelength_um,
        "f0_expected_hz": f0,
        "resonance_frequency_hz": resonance_hz,
        "resonance_frequency_relative_error": scale_error,
        "antiresonance_frequency_hz": anti,
        "selected_antiresonance_frequency_hz": anti,
        "selected_b_zero_crossing_hz": extracted["selected_b_zero_crossing_hz"],
        "frequency_separation_hz": extracted["frequency_separation_hz"],
        "minimum_separation_hz": extracted["minimum_separation_hz"],
        "zero_tolerance_hz": extracted["zero_tolerance_hz"],
        "selection_reason": extracted["selection_reason"],
        "resonance_g_peak_S": float(conductance[resonance_index]),
        "selected_antiresonance_abs_y_min_S": (
            float(abs(y[np.argmin(np.abs(frequencies - anti))])) if anti is not None else None
        ),
        "selected_antiresonance_offset_nearest_edge_hz": None,
        "f_sync_hz": float(f0),
        "f_lower_coupling_edge_hz": float(f0 * (1.0 - abs(profile.kappa_p) / (2.0 * np.pi))),
        "f_upper_coupling_edge_hz": float(f0 * (1.0 + abs(profile.kappa_p) / (2.0 * np.pi))),
        "dominant_feature_count": feature_count,
        "idt_fingers": 60,
        "idt_pairs_interpretation": "60 fingers interpreted as 30 pairs",
        "reflector_gratings_each_side": 30,
        "reflector_helper_electrodes": 30,
        "evaluation_aperture_um": aperture_um,
        "evaluation_aperture_not_source_geometry": True,
        "phase_policy": profile.phase_policy,
        "loss_policy": profile.loss_policy,
        "source_feature_comparison": source_feature_comparison,
        "passivity_status": "PASS",
        "reciprocity_status": "NOT_APPLICABLE_ONE_PORT",
        **{f"diagnostic_{key}": value for key, value in diagnostics.items()},
    }
    coupling_edges = np.asarray([
        feature["f_lower_coupling_edge_hz"], feature["f_upper_coupling_edge_hz"]
    ])
    feature["resonance_offset_nearest_edge_hz"] = float(
        resonance_hz - coupling_edges[np.argmin(np.abs(coupling_edges - resonance_hz))]
    )
    if anti is not None:
        feature["selected_antiresonance_offset_nearest_edge_hz"] = float(
            anti - coupling_edges[np.argmin(np.abs(coupling_edges - anti))]
        )
    _write_csv(out / "results" / "native_resonator_features.csv", [feature])
    _write_csv(out / "results" / "native_resonator_corrected_features.csv", [feature])
    _write_csv(out / "results" / "native_resonator_feature_candidates.csv", extracted["candidate_rows"])
    np.savez_compressed(out / "results" / "native_resonator_response.npz",
                        frequencies_hz=frequencies, y=y)
    return {
        "status": status,
        "feature": feature,
        "frequencies_hz": frequencies,
        "y": y,
        "f0_hz": f0,
        "diagnostics": diagnostics,
        "extracted_features": extracted,
    }


def _phase_sensitivity(profile: Any, section: Mapping[str, Any], native: Mapping[str, Any], out: Path) -> dict[str, Any]:
    rows = []
    base_frequency = float(native["feature"]["resonance_frequency_hz"])
    frequencies = native["frequencies_hz"]
    f0 = float(native["f0_hz"])
    for phase in section.get("phase_sensitivity_alpha_rad", [0.0]):
        variant = replace(profile, alpha_phase_rad=float(phase))
        design = ResonatorDesign(
            wavelength_um=variant.wavelength_um, pairs=30,
            aperture_um=float(section["evaluation_aperture_um"]),
            reflector_electrodes=30, gap_lambda=0.0,
        )
        y = resonator_y(design, variant, frequencies)
        mask = (frequencies >= 0.95 * f0) & (frequencies <= 1.05 * f0)
        candidates = np.flatnonzero(mask)
        index = int(candidates[np.argmax(np.real(y[mask]))])
        frequency = float(frequencies[index])
        rows.append({
            "alpha_phase_rad": float(phase),
            "resonance_frequency_hz": frequency,
            "relative_to_signed_real_hz": frequency - base_frequency,
            "relative_to_f0": abs(frequency - f0) / f0,
        })
    _write_csv(out / "results" / "native_phase_sensitivity.csv", rows)
    _write_csv(out / "results" / "native_resonator_phase_diagnostics.csv", rows)
    max_shift = max(abs(float(row["relative_to_signed_real_hz"])) for row in rows)
    robust = max_shift / f0 <= 0.02
    return {"rows": rows, "max_shift_hz": max_shift, "robust_within_2pct_f0": robust}


def _load_reference(section: Mapping[str, Any]) -> dict[str, Any]:
    raw = Path(section["gate2b_b_run_dir"])
    run = raw if raw.is_absolute() else ROOT / raw
    metadata = json.loads((run / "metadata" / "gate2b_b_reference.json").read_text(encoding="utf-8"))
    row = metadata["row"]
    grid_path = run / "results" / "common_validation_grid_hz.csv"
    grid = np.asarray(np.loadtxt(grid_path, delimiter=",", skiprows=1), dtype=float)
    grid_id = hashlib.sha256(np.asarray(grid, dtype="<f8").tobytes()).hexdigest()
    if grid_id != metadata["grid_id"]:
        raise ValueError("R1 Gate 2B-B validation grid hash mismatch")
    return {"run_dir": run, "row": row, "design": json.loads(row["design"]), "grid": grid,
            "grid_id": grid_id, "grid_sha256_file": _sha256(grid_path)}


def _released_design(value: Mapping[str, Any]) -> ReleasedFilterDesign:
    allowed = {field.name for field in ReleasedFilterDesign.__dataclass_fields__.values()}
    return ReleasedFilterDesign(**{key: value[key] for key in allowed if key in value})


def _fixed_response(design: ReleasedFilterDesign, provider: Any, frequencies: np.ndarray, cfg: Mapping[str, Any]) -> dict[str, Any]:
    simulation = simulate_released_filter(
        design, provider, frequencies, cfg["center"], wiring=WIRING,
    )
    network = evaluate(simulation.y_parameters, 50.0, 50.0)
    result = measure(frequencies, network, design, cfg)
    result["diagnostics"] = simulation.diagnostics
    result["network_passivity"] = bool(float(np.max(network["gt"])) <= 1.0 + 1e-7)
    result["network_max_gain"] = float(np.max(network["gt"]))
    result["network"] = network
    result["simulation"] = simulation
    return result


def _fixed_design_sensitivity(profile: Any, cfg: Mapping[str, Any], reference: Mapping[str, Any], out: Path) -> dict[str, Any]:
    design = _released_design(reference["design"])
    m0 = _fixed_response(design, FixedProvider(cfg["com"]), reference["grid"], cfg)
    literature = _fixed_response(design, profile, reference["grid"], cfg)
    rows = []
    for profile_id, result in (("M0", m0), (profile.profile_id, literature)):
        metrics = result["metrics"]
        rows.append({
            "profile_id": profile_id,
            "status": "BASELINE_CONTROL" if profile_id == "M0" else "B28_FIXED_DESIGN_SENSITIVITY_EXPLORATORY",
            "grid_id": reference["grid_id"],
            "zin_ohm": 50.0,
            "zout_ohm": 50.0,
            "wiring": WIRING,
            "wavelength_um": design.wavelength_um,
            "aperture_um": design.aperture_um,
            "h_over_lambda": profile.h_over_lambda if profile_id != "M0" else design.thickness_over_lambda,
            "metallization_ratio": profile.metallization_ratio if profile_id != "M0" else design.metallization_ratio,
            "worst_il_db": metrics["worst_il_db"],
            "ripple_db": metrics["ripple_db"],
            "input_vswr": metrics["input_vswr"],
            "output_vswr": metrics["output_vswr"],
            "stop_1_attenuation_db": metrics["stop_attenuation_db"][1],
            "stop_2_attenuation_db": metrics["stop_attenuation_db"][2],
            "max_violation": result["max_violation"],
            "active_limiting_constraint": max(result["violations"], key=result["violations"].get),
            "network_passivity": result["network_passivity"],
            "network_max_gain": result["network_max_gain"],
            "admittance_reciprocity_error": result["diagnostics"]["reciprocity_error"],
        })
    _write_csv(out / "results" / "b28_fixed_design_sensitivity.csv", rows)
    np.savez_compressed(out / "results" / "b28_fixed_design_responses.npz",
                        frequencies_hz=reference["grid"],
                        m0_s=m0["network"]["s"], literature_s=literature["network"]["s"])
    return {"rows": rows, "m0": m0, "literature": literature, "design": asdict(design)}


def _run_pytest(args: list[str]) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *args], cwd=ROOT,
        capture_output=True,
    )
    elapsed = time.perf_counter() - started
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    summary = re.findall(r"(\d+ passed(?:, \d+ failed)?(?:, \d+ skipped)?(?:, \d+ warning[s]?)?)", stdout)
    return {
        "command": [sys.executable, "-m", "pytest", *args],
        "returncode": result.returncode,
        "passed": result.returncode == 0,
        "runtime_seconds": elapsed,
        "summary": summary[-1] if summary else "not parsed",
        "stdout": stdout,
        "stderr": stderr,
    }


def _plot_native(native: Mapping[str, Any], out: Path) -> None:
    frequencies = native["frequencies_hz"] / 1e9
    y = native["y"]
    fig, axes = plt.subplots(2, 1, figsize=(8, 7), sharex=True)
    axes[0].plot(frequencies, np.real(y), label="conductance G")
    axes[0].set_ylabel("G [S]")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()
    axes[1].plot(frequencies, np.imag(y), label="susceptance B")
    axes[1].set_xlabel("Frequency [GHz]")
    axes[1].set_ylabel("B [S]")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()
    fig.suptitle("R1 native resonator: frequency-only diagnostic")
    fig.tight_layout()
    fig.savefig(out / "plots" / "native_resonator_admittance.png", dpi=160)
    plt.close(fig)


def _plot_b28(frequencies: np.ndarray, fixed: Mapping[str, Any], out: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(8, 7), sharex=True)
    for label, result in (("M0", fixed["m0"]), ("literature-derived", fixed["literature"])):
        axes[0].plot(frequencies / 1e6, result["network"]["il"], label=label)
        axes[1].plot(frequencies / 1e6, result["network"]["vswr"][:, 0], label=label)
    axes[0].set_ylabel("IL [dB]")
    axes[1].set_ylabel("Input VSWR")
    axes[1].set_xlabel("Frequency [MHz]")
    for axis in axes:
        axis.grid(True, alpha=0.3)
        axis.legend()
    fig.suptitle("R1 B28 fixed geometry sensitivity (exploratory)")
    fig.tight_layout()
    fig.savefig(out / "plots" / "b28_fixed_design_sensitivity.png", dpi=160)
    plt.close(fig)


def run_stage37b_r1(config_path: str | Path, run_path: str | Path, resume: bool = False) -> dict[str, Any]:
    del resume
    config_path = Path(config_path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    section = raw.get("stage3_7b_r1", {})
    profile_path = (config_path.parent / raw["literature_profile_file"]).resolve()
    profile_data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    profile = profile_from_mapping(profile_data)
    cfg = load_experiment_config(config_path)
    out = Path(run_path)
    (out / "results").mkdir(parents=True, exist_ok=True)
    (out / "plots").mkdir(parents=True, exist_ok=True)
    (out / "metadata").mkdir(parents=True, exist_ok=True)

    targeted = _run_pytest(["-q", "tests/unit/core/test_literature_com.py", "tests/unit/core/test_material_profiles.py"])
    (out / "metadata" / "targeted_test_result.json").write_text(
        json.dumps(_clean(targeted), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    roundtrip_rows, roundtrip_pass = _roundtrip(profile, float(section.get("evaluation_aperture_um", 80.0)))
    _write_csv(out / "results" / "normalization_roundtrip_tests.csv", roundtrip_rows)
    _write_csv(out / "results" / "normalized_com_source_values.csv", [
        {
            "profile_id": profile.profile_id,
            "parameter": name,
            "source_value": source_value,
            "source_scale": source_scale,
            "source_scaled_value": source_value * source_scale,
            "source_unit": source_unit,
            "converted_si_value": converted_value,
            "converted_si_unit": converted_unit,
            "source_role": "2024_numeric_source",
            "status": "RAW_SOURCE_VALUE_WITH_EXPLICIT_CONVERSION",
        }
        for name, source_value, source_scale, source_unit, converted_value, converted_unit in (
            ("velocity", profile.velocity_m_s, 1.0, "m/s", profile.velocity_m_s, "m/s"),
            ("kappa_p", profile.kappa_p_percent, 0.01, "%", profile.kappa_p, "dimensionless"),
            ("alpha_n", profile.alpha_n_value, profile.alpha_n_scale,
             profile.alpha_n_unit, profile.alpha_n_sqrt_s, "sqrt(S)"),
            ("capacitance_n", profile.capacitance_n_value, profile.capacitance_n_scale,
             profile.capacitance_n_unit, profile.capacitance_n_f_per_m, "F/m"),
            ("gamma_p", profile.gamma_p, 1.0, "dimensionless", profile.gamma_p, "dimensionless"),
            ("wavelength", profile.wavelength_um, 1.0, "um", profile.wavelength_um, "um"),
            ("h_over_lambda", profile.h_over_lambda, 1.0, "dimensionless",
             profile.h_over_lambda, "dimensionless"),
            ("metallization_ratio", profile.metallization_ratio, 1.0, "dimensionless",
             profile.metallization_ratio, "dimensionless"),
        )
    ])

    native = _native_resonator(profile, section, out)
    phase = _phase_sensitivity(profile, section, native, out)
    _plot_native(native, out)
    _write_csv(out / "results" / "native_dms_partial_results.csv", [{
        "status": "NOT_ATTEMPTED_INCOMPLETE_SOURCE_GEOMETRY",
        "input_pitch_um": profile_data["device_geometry"]["dms_pitch_input_um"],
        "output_pitch_um": profile_data["device_geometry"]["dms_pitch_output_um"],
        "reflector_pitch_um": profile_data["device_geometry"]["dms_pitch_reflector_um"],
        "production_acceptance": False,
        "missing": "IDT counts, aperture, gap, terminal and polarity registry",
    }])

    full = _run_pytest([]) if section.get("run_full_regression", True) else {
        "passed": False, "returncode": None, "summary": "NOT_RUN_BY_CONFIGURATION",
    }
    (out / "metadata" / "full_regression_result.json").write_text(
        json.dumps(_clean(full), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    reference = None
    fixed = None
    fixed_allowed = bool(
        section.get("run_fixed_design_sensitivity", True)
        and roundtrip_pass
        and native["status"] in {"RESONATOR_FREQ_PASS", "RESONATOR_FREQ_INCONCLUSIVE"}
        and full.get("passed", False)
        and targeted.get("passed", False)
        and phase["robust_within_2pct_f0"]
    )
    if fixed_allowed:
        reference = _load_reference(section)
        fixed = _fixed_design_sensitivity(profile, cfg, reference, out)
        _plot_b28(reference["grid"], fixed, out)
    else:
        _write_csv(out / "results" / "b28_fixed_design_sensitivity.csv", [{
            "status": "NOT_RUN_GATE_NOT_MET",
            "roundtrip_pass": roundtrip_pass,
            "native_status": native["status"],
            "targeted_tests_pass": targeted.get("passed", False),
            "full_regression_pass": full.get("passed", False),
            "phase_sensitivity_robust": phase["robust_within_2pct_f0"],
            "reason": "R1 fixed-design gate requires mapping/tests/native frequency/phase robustness.",
        }])

    source = profile_data["source"]
    definition = profile_data["definition_source"]
    (out / "metadata" / "profile_snapshot.yaml").write_text(
        yaml.safe_dump(_clean(profile_data), sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    (out / "metadata" / "repository_audit.json").write_text(json.dumps({
        "branch": _git(["branch", "--show-current"]),
        "head": _git(["rev-parse", "HEAD"]),
        "status": _git(["status", "--short"]),
        "diff_summary": _git(["diff", "--stat"]),
        "stage3_7b_artifact": "runs/stage3_7b_literature_com_reconstruction_final",
        "m0_config": "configs/models/com_params_hypothetical.yaml",
        "gate2b_reference": _clean(reference) if reference else "not_used",
        "numeric_source": source,
        "definition_source": definition,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (out / "stage3_7b_r1_mapping_notes.md").write_text(f"""# R1 mapping notes

Numeric source: {source['title']} ([{source['doi']}]({source['url']})), Table 2 only.
Definition source: {definition['title']} ([{definition['doi']}]({definition['url']})), normalization definitions only.

The 2022 source defines `kappa_p=kappa*lambda`, `alpha_p=alpha*lambda`,
`alpha_n=alpha_p/sqrt(W/lambda)`, `C_p=C*lambda`, `C_n=C_p/W`, and hence
`C=C_n*W/lambda`. Its V/I description uses half-power amplitude values; the
current solver uses peak V and current into the transducer. R1 therefore does
not claim absolute admittance compatibility. `gamma_p` is converted as an
explicit amplitude-loss assumption only.

The signed-real phase policy is explicit: `kappa` retains the negative table
sign and `alpha` is positive real. No fitting, sign flip, interpolation,
thickness/duty interpolation, or M0 fallback is used.
""", encoding="utf-8")
    (out / "stage3_7b_r1_native_resonator_validation.md").write_text(f"""# R1 native resonator validation

- evaluation aperture: {section.get('evaluation_aperture_um', 80.0)} um
- evaluation aperture is source geometry: **false**
- absolute admittance validation: **NOT_CLAIMED**
- source lambda: {profile.wavelength_um} um
- source h/lambda: {profile.h_over_lambda}
- source duty: {profile.metallization_ratio}
- IDT interpretation: 60 fingers -> 30 pairs
- reflector interpretation: 30 gratings/side -> helper `reflector_electrodes=30`
- expected f0=v/lambda: {native['f0_hz']:.6f} Hz
- resonator status: `{native['status']}`
- phase sensitivity robust within 2% f0: `{phase['robust_within_2pct_f0']}`
- maximum alpha-phase feature shift: {phase['max_shift_hz']:.6f} Hz

The native DMS is not used as a production gate. Its exploratory row records
the published pitches and the missing counts/aperture/gap/terminal/polarity
information.
""", encoding="utf-8")
    (out / "test_summary.md").write_text(
        f"""# R1 test summary

Targeted command: `{' '.join(targeted['command'])}`

- targeted result: `{targeted.get('summary')}`
- targeted return code: `{targeted.get('returncode')}`
- full command: `{' '.join(full.get('command', []))}`
- full result: `{full.get('summary')}`
- full return code: `{full.get('returncode')}`

No optimizer or FEM execution was performed.
""", encoding="utf-8")

    decision = "LITERATURE_COM_PHYSICALLY_PLAUSIBLE_BUT_UNCERTAIN" if fixed else "LITERATURE_COM_MAPPING_PASS"
    if native["status"] == "RESONATOR_FREQ_FAIL" or not roundtrip_pass or not full.get("passed", False):
        decision = "FEM_EXTRACTION_REQUIRED"
    if not full.get("passed", False) or native["status"] == "RESONATOR_FREQ_FAIL":
        stop = FAIL_STOP
    else:
        stop = SUCCESS_STOP
    (out / "stage3_7b_r1_summary.md").write_text(f"""# Stage 3.7B-R1 summary

Numeric source: {source['title']} ({source['doi']}).
Definition source: {definition['title']} ({definition['doi']}). These roles are
separate; no numeric values were mixed from the definition source.

Raw 25 °C values: `v=4045 m/s`, `kappa_p=-18.96 %`,
`alpha_n=92.566e-5 ohm^(-1/2)`, `C_n=52.80e-5 pF/um`,
`gamma_p=0.002684`, `lambda=2.16 um`, `h/lambda=0.08`, `duty=0.65`.

- round-trip mapping: `{roundtrip_pass}`
- native resonator: `{native['status']}`
- phase policy: `{profile.phase_policy}`
- phase sensitivity robust: `{phase['robust_within_2pct_f0']}`
- targeted tests: `{targeted.get('summary')}`
- full regression: `{full.get('summary')}`
- B28 fixed design: `{'executed' if fixed else 'not executed'}`
- 8k re-optimization: **not executed**
- electrode material: `unspecified_metal`; the 2024 source is not called Al

The 80 um aperture is an evaluation aperture only, not reported source
geometry. Absolute admittance, impedance matching, and source-device
conductance are not claimed. Fixed-design output, if present, is exploratory
and must not be read as source-device matching.

Decision: `{decision}`

Recommendation: do not start R1 re-optimization automatically. If phase/loss
convention uncertainty materially affects the exploratory comparison, use
`FEM_EXTRACTION_REQUIRED` as the next branch.
""", encoding="utf-8")
    (out / f"{stop}.txt").write_text(f"{stop}\n", encoding="utf-8")
    return {
        "run": str(out), "decision": decision, "stop_marker": f"{stop}.txt",
        "native_status": native["status"], "b28_executed": fixed is not None,
        "full_regression_pass": full.get("passed", False),
    }


# Public adapters used by the follow-on R2/3.7C study.  Keeping these names
# explicit preserves the study-layer import boundary while the R1 helpers
# remain implementation details for its own orchestration.
clean_value = _clean
fixed_response = _fixed_response
load_reference = _load_reference
native_resonator = _native_resonator
phase_sensitivity = _phase_sensitivity
plot_b28 = _plot_b28
plot_native = _plot_native
roundtrip = _roundtrip
run_pytest = _run_pytest

__all__ = [
    "clean_value", "fixed_response", "load_reference", "native_resonator",
    "phase_sensitivity", "plot_b28", "plot_native", "roundtrip",
    "run_pytest", "run_stage37b_r1",
]
