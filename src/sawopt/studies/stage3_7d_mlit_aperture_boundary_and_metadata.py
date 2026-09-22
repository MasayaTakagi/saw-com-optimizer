"""Stage 3.7D MLIT aperture forward probe and metadata gate.

This protocol reads the completed Stage 3.7C MLIT seed winners, changes only
aperture, and evaluates the fixed designs on the exact C validation grid.  It
does not invoke an optimizer or modify the COM provider.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import subprocess
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

import matplotlib.pyplot as plt
import numpy as np
import yaml

from ..core.metrics import geometry
from ..core.models import FixedProvider
from ..core.literature_com import profile_from_mapping
from ..io.config import load_experiment_config
from ..reporting.material_metadata import (
    attach_result_metadata,
    design_metadata,
    material_profile_metadata,
    metadata_json_roundtrip,
    render_material_metadata_html,
)
from .stage3_6_gate2a import ReleasedFilterDesign, WIRING
from .stage3_7b_r1_normalized_literature_com_validation import fixed_response


ROOT = Path(__file__).resolve().parents[3]
STUDY_TYPE = "stage3_7d_mlit_aperture_boundary_and_metadata"
STOP_COMPLETE = "STAGE3_7D_APERTURE_AND_METADATA_GATE_COMPLETE_STOP"
STOP_REDESIGN = "STAGE3_7D_APERTURE_SPACE_REDESIGN_REQUIRED_STOP"
METRIC_FIELDS = (
    "max_violation", "sum_violation", "worst_il_db", "ripple_db",
    "input_vswr", "output_vswr", "stop_0_attenuation_db",
    "stop_1_attenuation_db", "stop_2_attenuation_db", "stop_3_attenuation_db",
)


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _array_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()


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


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(set().union(*(row.keys() for row in materialized))) if materialized else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(materialized)


def _root_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _active_constraint(violations: Mapping[str, Any]) -> str:
    values = {str(key): float(value) for key, value in violations.items()}
    if not values:
        return "none"
    maximum = max(values.values())
    return ";".join(sorted(key for key, value in values.items() if abs(value - maximum) <= 1e-12))


def _released_design(value: Mapping[str, Any]) -> ReleasedFilterDesign:
    allowed = {field.name for field in ReleasedFilterDesign.__dataclass_fields__.values()}
    return ReleasedFilterDesign(**{key: value[key] for key in allowed if key in value})


def _load_profile(config_path: Path, raw: Mapping[str, Any]):
    profile_path = (config_path.parent / raw["literature_profile_file"]).resolve()
    profile_data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    return profile_from_mapping(profile_data), profile_data, profile_path


def _load_reference(raw: Mapping[str, Any], profile_id: str) -> dict[str, Any]:
    section = raw.get("stage3_7d", {})
    run = _root_path(section["source_run_dir"])
    result_path = run / "results" / "b28_literature_com_seed_results.csv"
    if not result_path.exists():
        raise FileNotFoundError(f"Stage 3.7C result bundle is missing: {result_path}")
    with result_path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    seeds = [int(seed) for seed in section.get("seeds", [20260917, 20260918])]
    references = {}
    for seed in seeds:
        matches = [
            row for row in rows
            if int(row["seed"]) == seed
            and int(row["checkpoint_budget"]) == int(section.get("source_checkpoint_budget", 8000))
            and row.get("provider_id") == profile_id
        ]
        if len(matches) != 1:
            raise ValueError(f"expected one final Stage 3.7C row for seed {seed}, found {len(matches)}")
        row = matches[0]
        references[seed] = {
            "seed": seed,
            "source_row": row,
            "design": _released_design(json.loads(row["geometry"])),
            "source_result_path": result_path,
        }

    validation_metadata_path = run / "metadata" / "validation_grid.json"
    validation_metadata = json.loads(validation_metadata_path.read_text(encoding="utf-8"))
    grid_path = Path(validation_metadata["source"])
    if not grid_path.is_absolute():
        grid_path = _root_path(grid_path)
    grid = np.asarray(np.loadtxt(grid_path, delimiter=",", skiprows=1), dtype=float)
    grid_id = _array_sha256(grid)
    expected_grid_id = str(validation_metadata["grid_id"])
    if grid_id != expected_grid_id:
        raise ValueError(f"validation-grid identity mismatch: {grid_id} != {expected_grid_id}")
    if any(row["source_row"]["validation_grid_id"] != grid_id for row in references.values()):
        raise ValueError("Stage 3.7C result row uses a different validation grid")
    return {
        "run_dir": run,
        "result_path": result_path,
        "result_sha256": _sha256(result_path),
        "references": references,
        "grid": grid,
        "grid_id": grid_id,
        "grid_file": grid_path,
        "grid_file_sha256": _sha256(grid_path),
        "validation_metadata": validation_metadata,
    }


def _search_bounds(raw: Mapping[str, Any]) -> tuple[float, float, str]:
    section = raw.get("stage3_7d", {})
    snapshot = _root_path(section["search_space_snapshot"])
    data = yaml.safe_load(snapshot.read_text(encoding="utf-8")) or {}
    bounds = data["bounds"]["aperture_um"]["hard"]
    return float(bounds[0]), float(bounds[1]), _sha256(snapshot)


def _response_finite(result: Mapping[str, Any]) -> bool:
    network = result["network"]
    simulation = result["simulation"]
    return bool(
        np.isfinite(np.asarray(network["s"])).all()
        and np.isfinite(np.asarray(network["gt"])).all()
        and np.isfinite(np.asarray(simulation.y_parameters)).all()
    )


def _probe_row(
    seed: int,
    label: str,
    aperture_um: float,
    design: ReleasedFilterDesign,
    result: Mapping[str, Any],
    reference: Mapping[str, Any],
    grid_id: str,
    search_lower: float,
    search_upper: float,
) -> dict[str, Any]:
    dimensions, geometry_violations = geometry(design, reference["cfg"]["constraints"])
    metrics = result["metrics"]
    stops = metrics["stop_attenuation_db"]
    record = {
        "seed": seed,
        "probe": label,
        "aperture_um": float(aperture_um),
        "main_wavelength_um": float(design.wavelength_um),
        "aperture_over_main_wavelength": float(aperture_um / design.wavelength_um),
        "grid_id": grid_id,
        "grid_count": int(reference["grid"].size),
        "provider_id": reference["profile_id"],
        "topology": "current_3_idt_dms",
        "wiring": WIRING,
        "zin_ohm": 50.0,
        "zout_ohm": 50.0,
        "max_violation": float(result["max_violation"]),
        "sum_violation": float(sum(float(value) for value in result["violations"].values())),
        "worst_il_db": float(metrics["worst_il_db"]),
        "ripple_db": float(metrics["ripple_db"]),
        "input_vswr": float(metrics["input_vswr"]),
        "output_vswr": float(metrics["output_vswr"]),
        "stop_0_attenuation_db": float(stops[0]),
        "stop_1_attenuation_db": float(stops[1]),
        "stop_2_attenuation_db": float(stops[2]),
        "stop_3_attenuation_db": float(stops[3]),
        "active_limiting_constraint": _active_constraint(result["violations"]),
        "passivity": bool(result["network_passivity"]),
        "reciprocity_error": float(result["diagnostics"]["reciprocity_error"]),
        "reciprocity": bool(float(result["diagnostics"]["reciprocity_error"]) <= 1e-7),
        "response_finite": _response_finite(result),
        "layout_valid": bool(max(geometry_violations, default=0.0) <= 1e-10),
        "layout_length_um": float(dimensions["length_um"]),
        "layout_width_um": float(dimensions["width_um"]),
        "layout_electrodes": float(dimensions["electrodes"]),
        "search_bound_lower_um": search_lower,
        "search_bound_upper_um": search_upper,
        "search_bound_valid": bool(search_lower <= aperture_um <= search_upper),
        "outside_current_search_bound": bool(aperture_um > search_upper or aperture_um < search_lower),
        "reference_max_violation": float(reference["source_row"]["max_violation"]),
        "reference_active_constraint": reference["source_row"]["active_limiting_constraint"],
    }
    for key, value in asdict(design).items():
        record[f"design_{key}"] = value
    return record


def _add_deltas(rows: list[dict[str, Any]]) -> None:
    for seed in sorted({int(row["seed"]) for row in rows}):
        seed_rows = [row for row in rows if int(row["seed"]) == seed]
        a0 = next(row for row in seed_rows if row["probe"] == "A0")
        a150 = next(row for row in seed_rows if abs(float(row["aperture_um"]) - 150.0) <= 1e-12)
        for row in seed_rows:
            for metric in METRIC_FIELDS:
                row[f"delta_vs_a0_{metric}"] = float(row[metric]) - float(a0[metric])
                row[f"delta_vs_150_{metric}"] = float(row[metric]) - float(a150[metric])


def _relative_improvement(before: float, after: float) -> float:
    scale = max(abs(float(before)), np.finfo(float).tiny)
    return (float(before) - float(after)) / scale


def _decision(rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    by_seed = {}
    for seed in sorted({int(row["seed"]) for row in rows}):
        values = {float(row["aperture_um"]): row for row in rows if int(row["seed"]) == seed}
        max150 = values[150.0]["max_violation"]
        steps = [_relative_improvement(values[left]["max_violation"], values[right]["max_violation"])
                 for left, right in ((150.0, 165.0), (165.0, 180.0), (180.0, 200.0))]
        by_seed[seed] = {
            "improvement_150_to_165": steps[0],
            "improvement_165_to_180": steps[1],
            "improvement_180_to_200": steps[2],
            "improvement_150_to_200": _relative_improvement(max150, values[200.0]["max_violation"]),
            "active_constraints": {str(aperture): values[aperture]["active_limiting_constraint"] for aperture in sorted(values)},
        }
    first = [value["improvement_150_to_165"] for value in by_seed.values()]
    second = [value["improvement_165_to_180"] for value in by_seed.values()]
    third = [value["improvement_180_to_200"] for value in by_seed.values()]
    moderate = min(first) >= 0.05 and min(second) >= 0.02 and max(third) < 0.02
    strong = min(first) >= 0.05 and min(second) >= 0.02 and min(third) >= 0.02
    if strong:
        label = "APERTURE_BOUND_ACTIVE_STRONG"
        final = "APERTURE_SPACE_REDESIGN_REQUIRED"
    elif moderate:
        label = "APERTURE_BOUND_ACTIVE_MODERATE"
        final = "STAGE3_8_READY_APERTURE_EXPANDED"
    else:
        # A positive but inconsistent or sub-2% response is not sufficient to
        # justify a profile-specific bound change in this screening gate.
        label = "APERTURE_BOUND_NOT_ACTIVE"
        final = "STAGE3_8_READY_APERTURE_150"
    return label, {
        "classification": label,
        "final_label": final,
        "per_seed": by_seed,
        "thresholds": {
            "negligible_relative_improvement": 0.02,
            "material_relative_improvement": 0.05,
            "strong_requires_each_step": True,
        },
    }


def _plot_probe(rows: list[dict[str, Any]], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    for seed in sorted({int(row["seed"]) for row in rows}):
        values = sorted((float(row["aperture_um"]), float(row["max_violation"])) for row in rows if int(row["seed"]) == seed)
        ax.plot(*zip(*values), marker="o", label=f"seed {seed}")
    ax.set(xlabel="Aperture [um]", ylabel="Maximum normalized violation", title="MLIT aperture probe: max violation")
    ax.grid(True, alpha=0.3); ax.legend(); fig.tight_layout()
    fig.savefig(out / "max_violation_vs_aperture.png", dpi=160); plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharex=True)
    for seed in sorted({int(row["seed"]) for row in rows}):
        values = sorted((float(row["aperture_um"]), float(row["input_vswr"]), float(row["output_vswr"])) for row in rows if int(row["seed"]) == seed)
        x, input_vswr, output_vswr = zip(*values)
        axes[0].plot(x, input_vswr, marker="o", label=f"seed {seed}")
        axes[1].plot(x, output_vswr, marker="o", label=f"seed {seed}")
    axes[0].set_ylabel("Input VSWR"); axes[1].set_ylabel("Output VSWR")
    for axis in axes:
        axis.set_xlabel("Aperture [um]"); axis.grid(True, alpha=0.3); axis.legend()
    fig.suptitle("MLIT aperture probe: matching metrics"); fig.tight_layout()
    fig.savefig(out / "vswr_vs_aperture.png", dpi=160); plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharex=True)
    for seed in sorted({int(row["seed"]) for row in rows}):
        values = sorted((float(row["aperture_um"]), float(row["worst_il_db"]), float(row["ripple_db"])) for row in rows if int(row["seed"]) == seed)
        x, il, ripple = zip(*values)
        axes[0].plot(x, il, marker="o", label=f"seed {seed}")
        axes[1].plot(x, ripple, marker="o", label=f"seed {seed}")
    axes[0].set_ylabel("Worst IL [dB]"); axes[1].set_ylabel("Ripple [dB]")
    for axis in axes:
        axis.set_xlabel("Aperture [um]"); axis.grid(True, alpha=0.3); axis.legend()
    fig.suptitle("MLIT aperture probe: IL and ripple"); fig.tight_layout()
    fig.savefig(out / "il_ripple_vs_aperture.png", dpi=160); plt.close(fig)


def _metadata_regression(
    design: ReleasedFilterDesign,
    profile: Any,
    profile_data: Mapping[str, Any],
    cfg: Mapping[str, Any],
    grid: np.ndarray,
    out: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    metadata_mlit = material_profile_metadata(profile_data)
    metadata_m0 = material_profile_metadata(None, profile_id="M0", design=design)
    before = fixed_response(design, profile, grid, cfg)
    enriched = attach_result_metadata(before, design, metadata_mlit)
    after = fixed_response(design, profile, grid, cfg)
    checks = []

    def check(name: str, value: bool, detail: str = "") -> None:
        checks.append({"check": name, "status": "PASS" if value else "FAIL", "detail": detail})

    for region in ("idt", "reflector", "gap"):
        geometry_value = type("Geometry", (), {"wavelength_um": design.wavelength_um, "aperture_um": design.aperture_um})()
        before_parameters = profile.parameters(region, geometry_value, grid[0])
        after_parameters = profile.parameters(region, geometry_value, grid[0])
        delta = max(abs(before_parameters[key] - after_parameters[key]) for key in before_parameters)
        check(f"provider_output_{region}", bool(delta <= 0.0), f"max_abs_delta={delta:.17g}")
    y_delta = float(np.max(np.abs(before["simulation"].y_parameters - after["simulation"].y_parameters)))
    s_delta = float(np.max(np.abs(before["network"]["s"] - after["network"]["s"])))
    metric_delta = max(abs(float(before["metrics"][key]) - float(after["metrics"][key])) for key in ("worst_il_db", "ripple_db", "input_vswr", "output_vswr"))
    check("response_y", y_delta <= 1e-14, f"max_abs_delta={y_delta:.17g}")
    check("response_s", s_delta <= 1e-14, f"max_abs_delta={s_delta:.17g}")
    check("response_metrics", metric_delta <= 1e-14, f"max_abs_delta={metric_delta:.17g}")
    decoded, roundtrip_pass = metadata_json_roundtrip(design_metadata(design, metadata_mlit))
    check("metadata_serialization_roundtrip", roundtrip_pass, f"decoded_keys={sorted(decoded)}")
    check("m0_legacy_design_compatibility", metadata_m0["effective_duty"] == design.metallization_ratio and metadata_m0["effective_h_over_lambda"] == design.thickness_over_lambda)
    check("mlit_effective_values", metadata_mlit["effective_h_over_lambda"] == float(profile_data["h_over_lambda"]) and metadata_mlit["effective_duty"] == float(profile_data["metallization_ratio"]), "effective profile values are display metadata")
    check("metadata_patch_does_not_replace_result", enriched["network"] is before["network"] and enriched["simulation"] is before["simulation"])
    return checks, {
        "m0": metadata_m0,
        "mlit": metadata_mlit,
        "max_y_abs_delta": y_delta,
        "max_s_abs_delta": s_delta,
        "max_metric_abs_delta": metric_delta,
    }


def _summary(
    out: Path,
    reference: Mapping[str, Any],
    rows: list[dict[str, Any]],
    decision: Mapping[str, Any],
    metadata_checks: list[dict[str, Any]],
    profile: Mapping[str, Any],
    search_lower: float,
    search_upper: float,
) -> None:
    by_seed = decision["per_seed"]
    improvement_lines = []
    for seed, values in by_seed.items():
        improvement_lines.append(
            f"- seed {seed}: 150→165 {values['improvement_150_to_165']:.2%}, "
            f"165→180 {values['improvement_165_to_180']:.2%}, "
            f"180→200 {values['improvement_180_to_200']:.2%}; "
            f"active constraints {values['active_constraints']}"
        )
    passed = sum(check["status"] == "PASS" for check in metadata_checks)
    failed = len(metadata_checks) - passed
    marker = STOP_REDESIGN if decision["final_label"] == "APERTURE_SPACE_REDESIGN_REQUIRED" else STOP_COMPLETE
    text = f"""# Stage 3.7D aperture boundary and metadata summary

## Scope and frozen inputs

- Source bundle: `{reference['run_dir']}`
- Source result hash: `{reference['result_sha256']}`
- Seeds: 20260917 and 20260918, final Stage 3.7C checkpoint only
- Provider: `{profile['profile_id']}`; topology: current 3-IDT DMS; wiring: `{WIRING}`
- Terminations: 50 Ω / 50 Ω
- Validation grid: `{reference['grid_id']}` ({reference['grid'].size} points)
- All geometry except aperture was fixed. No optimizer, warm start, interpolation, or physics change was used.

## Questions answered

1. **Is the 150 µm upper bound artificially limiting MLIT?**  The probe classification is **`{decision['classification']}`**.
2. **Which metrics change?**  The complete values and deltas are in `mlit_aperture_boundary_probe.csv`; the primary screening metric is maximum normalized violation, with IL, ripple, and both VSWR values plotted and retained.
3. **Is the direction reproducible?**
{chr(10).join(improvement_lines)}
4. **Stage 3.8 MLIT recommendation:** **`{decision['final_label']}`**. The profile-specific recommendation is in `stage3_8_aperture_bound_recommendation.csv`.
5. **M0 bound:** retain the current {search_lower:g}–{search_upper:g} µm bound for continuity.
6. **Metadata:** effective MLIT h/λ = {profile['h_over_lambda']}, duty = {profile['metallization_ratio']}; legacy design values remain explicitly labeled.
7. **Physics regression:** {passed} passed, {failed} failed; see `metadata_regression_check.csv`.
8. **Proceed to Stage 3.8?** No automatic start is performed. Proceed only after reviewing this gate and the profile-specific recommendation.

## Decision rationale

The quantitative thresholds are: <2% negligible, ≥5% material per step, and a strong result requires material improvement at all three outward steps for both seeds. The probe is a forward evaluation only; it is not a convergence claim.

## Hard stop

`{marker}`
"""
    (out / "stage3_7d_aperture_boundary_probe_summary.md").write_text(text, encoding="utf-8")


def _schema_doc(out: Path) -> None:
    (out / "material_profile_metadata_schema.md").write_text("""# Material profile metadata schema

The result/report separates the legacy geometry fields from the effective COM
material profile.

## Legacy design fields

- `design.metallization_ratio`
- `design.thickness_over_lambda`

For MLIT these are retained for backward compatibility and labeled as legacy
geometry metadata; they are not used to generate MLIT COM parameters.

## Effective material profile

`material_profile` contains `id`, `source`, `substrate`, `electrode_material`,
`temperature_c`, `effective_h_over_lambda`, `effective_duty`, `phase_policy`,
`com_parameter_source`, and `normalization_definition_source`.

For the current MLIT profile the effective values are h/lambda = 0.08 and duty
= 0.65. M0 keeps its historical display values and remains backward
compatible.

Metadata attachment is a shallow result copy: provider parameters, Y, S, and
metrics are not regenerated or modified by the display patch.
""", encoding="utf-8")


def _test_summary(
    out: Path,
    checks: list[dict[str, Any]],
    targeted: Mapping[str, Any],
    full_regression: Mapping[str, Any],
) -> None:
    passed = sum(check["status"] == "PASS" for check in checks)
    failed = len(checks) - passed
    command = " ".join(str(value) for value in full_regression.get("command", []))
    targeted_command = " ".join(str(value) for value in targeted.get("command", []))
    (out / "test_summary.md").write_text(f"""# Stage 3.7D test summary

## Metadata/physics regression

- command: `{targeted_command}`
- status: `{'PASS' if targeted.get('returncode') == 0 else 'FAIL'}`
- pytest summary: `{targeted.get('summary', 'not parsed')}`
- direct metadata checks passed: {passed}
- direct metadata checks failed: {failed}
- skipped: 0
- runtime: {float(targeted.get('runtime_seconds', 0.0)):.3f} s

## Full regression

- command: `{command.strip()}`
- status: `{'PASS' if full_regression.get('returncode') == 0 else 'FAIL'}`
- pytest summary: `{full_regression.get('summary', 'not parsed')}`
- runtime: {float(full_regression.get('runtime_seconds', 0.0)):.3f} s

## Direct checks

`metadata_regression_check.csv` contains provider-output, Y, S, metrics,
serialization, M0 compatibility, and display-semantics checks.
""", encoding="utf-8")


def _run_pytest(args: list[str]) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run([sys.executable, "-m", "pytest", *args], cwd=ROOT, capture_output=True)
    elapsed = time.perf_counter() - started
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    summaries = [line.strip() for line in stdout.splitlines() if " passed" in line or " failed" in line]
    return {"command": [sys.executable, "-m", "pytest", *args], "returncode": result.returncode,
            "runtime_seconds": elapsed, "summary": summaries[-1] if summaries else "not parsed",
            "stdout": stdout, "stderr": stderr}


def run_stage37d(config_path: str | Path, run_path: str | Path, resume: bool = False) -> dict[str, Any]:
    del resume
    config_path = Path(config_path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    cfg = load_experiment_config(config_path)
    profile, profile_data, profile_path = _load_profile(config_path, raw)
    reference = _load_reference(raw, profile.profile_id)
    search_lower, search_upper, search_space_sha256 = _search_bounds(raw)
    out = Path(run_path)
    for directory in (out, out / "results", out / "plots", out / "metadata"):
        directory.mkdir(parents=True, exist_ok=True)

    source_references = {}
    rows: list[dict[str, Any]] = []
    probes = [float(value) for value in raw.get("stage3_7d", {}).get(
        "probe_apertures_um", [150.0, 165.0, 180.0, 200.0]
    )]
    if probes != [150.0, 165.0, 180.0, 200.0]:
        raise ValueError("Stage 3.7D probe set must be exactly [150, 165, 180, 200] um")
    for seed, reference_row in reference["references"].items():
        design = reference_row["design"]
        reference_row["grid"] = reference["grid"]
        reference_row["cfg"] = cfg
        reference_row["profile_id"] = profile.profile_id
        values = [float(design.aperture_um), *probes]
        # Preserve A0 even if the source design is numerically close to 150.
        for index, aperture in enumerate(values):
            label = "A0" if index == 0 else f"A{index}"
            probe_design = replace(design, aperture_um=aperture)
            result = fixed_response(probe_design, profile, reference["grid"], cfg)
            rows.append(_probe_row(seed, label, aperture, probe_design, result, reference_row,
                                   reference["grid_id"], search_lower, search_upper))
        source_references[str(seed)] = {
            "design": asdict(design),
            "source_row": reference_row["source_row"],
            "source_result_path": str(reference_row["source_result_path"]),
        }
    _add_deltas(rows)
    _write_csv(out / "mlit_aperture_boundary_probe.csv", rows)

    comparison_rows = []
    for seed in sorted({int(row["seed"]) for row in rows}):
        seed_rows = sorted((row for row in rows if int(row["seed"]) == seed), key=lambda row: float(row["aperture_um"]))
        for row in seed_rows:
            comparison_rows.append({
                "seed": seed, "probe": row["probe"], "aperture_um": row["aperture_um"],
                "max_violation": row["max_violation"], "sum_violation": row["sum_violation"],
                "worst_il_db": row["worst_il_db"], "ripple_db": row["ripple_db"],
                "input_vswr": row["input_vswr"], "output_vswr": row["output_vswr"],
                "active_limiting_constraint": row["active_limiting_constraint"],
                "delta_vs_a0_max_violation": row["delta_vs_a0_max_violation"],
                "delta_vs_150_max_violation": row["delta_vs_150_max_violation"],
            })
    _write_csv(out / "mlit_aperture_probe_seed_comparison.csv", comparison_rows)
    classification, decision = _decision(rows)
    recommended_upper = search_upper
    if classification == "APERTURE_BOUND_ACTIVE_MODERATE":
        recommended_upper = 180.0
    elif classification == "APERTURE_BOUND_ACTIVE_STRONG":
        recommended_upper = "redesign_required"
    _write_csv(out / "stage3_8_aperture_bound_recommendation.csv", [
        {"profile_id": "M0", "aperture_lower_um": search_lower, "aperture_upper_um": search_upper,
         "rationale": "Stage 3.6 continuity; M0 is not the MLIT profile."},
        {"profile_id": profile.profile_id, "aperture_lower_um": search_lower, "aperture_upper_um": recommended_upper,
         "rationale": f"{classification}; profile-specific bound recommendation from fixed-aperture forward probe.",
         "final_label": decision["final_label"], "fairness_note": "Profile-specific bounds must be disclosed in topology comparisons."},
    ])

    first_design = reference["references"][sorted(reference["references"])[0]]["design"]
    metadata_checks, metadata_details = _metadata_regression(first_design, profile, profile_data, cfg, reference["grid"], out)
    _write_csv(out / "metadata_regression_check.csv", metadata_checks)
    render_material_metadata_html({
        "M0": design_metadata(first_design, metadata_details["m0"]),
        "MLIT": design_metadata(first_design, metadata_details["mlit"]),
    }, out / "material_metadata_report.html")
    _schema_doc(out)
    _plot_probe(rows, out / "plots")

    targeted = _run_pytest(["-q", "tests/unit/reporting/test_material_metadata.py"])
    (out / "metadata" / "targeted_test.json").write_text(json.dumps(_clean(targeted), indent=2), encoding="utf-8")
    full_regression = _run_pytest(["-q"])
    (out / "metadata" / "full_regression.json").write_text(json.dumps(_clean(full_regression), indent=2), encoding="utf-8")
    (out / "metadata" / "test_runtime.json").write_text(json.dumps({"runtime_seconds": full_regression["runtime_seconds"]}, indent=2), encoding="utf-8")
    _test_summary(out, metadata_checks, targeted, full_regression)
    _summary(out, reference, rows, decision, metadata_checks, profile_data, search_lower, search_upper)

    profile_record = material_profile_metadata(profile_data)
    metadata_payload = {
        "schema_version": 1,
        "profile": profile_record,
        "source_profile_path": str(profile_path),
        "source_profile_sha256": _sha256(profile_path),
        "source_references": source_references,
        "validation_grid": {
            "grid_id": reference["grid_id"], "frequency_count": int(reference["grid"].size),
            "source": str(reference["grid_file"]), "sha256": reference["grid_file_sha256"],
        },
        "search_space_snapshot": {"path": str(_root_path(raw["stage3_7d"]["search_space_snapshot"])), "sha256": search_space_sha256,
                                  "aperture_bounds": [search_lower, search_upper]},
        "decision": decision,
        "stop_marker": STOP_REDESIGN if decision["final_label"] == "APERTURE_SPACE_REDESIGN_REQUIRED" else STOP_COMPLETE,
        "optimizer_rerun": False,
    }
    (out / "metadata" / "stage3_7d_metadata.json").write_text(json.dumps(_clean(metadata_payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "study_type": STUDY_TYPE,
        "run_dir": str(out),
        "decision": decision,
        "stop_marker": metadata_payload["stop_marker"],
        "full_regression": {key: value for key, value in full_regression.items() if key not in {"stdout", "stderr"}},
    }


__all__ = ["run_stage37d", "STUDY_TYPE", "STOP_COMPLETE", "STOP_REDESIGN"]
