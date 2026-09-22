"""Stage 3.7 literature/COM audit and 50-ohm sanity screen.

The current evidence set does not contain a complete, convention-mappable
42-degree YX-LiTaO3/Al COM profile.  This runner therefore performs the safe
part of the stage (reference audit, M0 parity/control evaluation, and report
generation) and stops before any literature-profile simulation or optimizer
run.  It must not fill missing literature parameters from M0.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import matplotlib.pyplot as plt
import numpy as np
import yaml

from ..core.metrics import measure
from ..core.models import FixedProvider
from ..core.network import evaluate
from ..io.config import load_experiment_config
from ..io.run_store import initialize
from ..io.serialization import save
from .stage3_6_gate2a import ReleasedFilterDesign, WIRING, simulate_released_filter


ROOT = Path(__file__).resolve().parents[3]
STUDY_TYPE = "stage3_7_material_com_50ohm_sanity"
GATE2B_B_DEFAULT = ROOT / "runs" / "stage3_6_gate2b_b_asymmetric_impedance"
REGISTRY_DEFAULT = ROOT / "configs" / "models" / "stage3_7_literature_profiles.yaml"
STOP_MARKER = "STAGE3_7_COM_MAPPING_BLOCKED_STOP.txt"


def _json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(args: list[str]) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"git {' '.join(args)} failed: {exc}"


def _write_csv(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    rows = list(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(set().union(*(row.keys() for row in rows))) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)


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


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def _load_registry(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document.get("profiles"), dict):
        raise ValueError("Stage 3.7 profile registry must contain profiles")
    return document


def _audit_rows(registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for profile_id, profile in registry["profiles"].items():
        target = profile.get("target", profile.get("metadata", {}))
        metadata = profile.get("metadata", {})
        rows.append({
            "profile_id": profile_id,
            "classification": profile.get("classification", "UNUSABLE"),
            "substrate": target.get("substrate"),
            "electrode_material": target.get("electrode_material"),
            "h_over_lambda": target.get("h_over_lambda", metadata.get("h_over_lambda")),
            "metallization_ratio": target.get(
                "metallization_ratio", metadata.get("metallization_ratio")
            ),
            "frequency_context": target.get(
                "frequency_context", metadata.get("frequency_context")
            ),
            "source_citation": json.dumps(_clean(profile.get("source_citation", [])), ensure_ascii=False),
            "missing_fields": json.dumps(_clean(profile.get("missing_fields", [])), ensure_ascii=False),
            "reason": profile.get("reason", profile.get("audit_note", "")),
            "production_eligible": profile.get("classification") in {
                "DIRECT_COMPATIBLE", "CONVERTIBLE_WITH_DERIVATION"
            },
        })
    return rows


def _gate2b_reference(cfg: Mapping[str, Any]) -> dict[str, Any]:
    section = cfg.get("stage3_7", {})
    run = _resolve(section.get("gate2b_b_run_dir", GATE2B_B_DEFAULT))
    csv_path = run / "results" / "all_seed_results.csv"
    grid_path = run / "results" / "common_validation_grid_hz.csv"
    grid_meta_path = run / "results" / "common_validation_grid.json"
    required = (csv_path, grid_path, grid_meta_path)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Gate 2B-B reference is incomplete: " + ", ".join(missing))

    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    candidates = [row for row in rows if (
        row.get("condition_id") == "B1"
        and float(row.get("zin_ohm", 0.0)) == 50.0
        and float(row.get("zout_ohm", 0.0)) == 50.0
        and int(row.get("actual_unique_evaluations", 0)) == 32000
        and "G1_G2" in row.get("record_path", "")
    )]
    if not candidates:
        raise ValueError("Gate 2B-B has no 50/50-ohm 32k G1_G2 reference rows")
    row = min(candidates, key=lambda item: float(item["max_violation"]))
    design = json.loads(row["design"])

    grid = np.asarray(np.loadtxt(grid_path, delimiter=",", skiprows=1), dtype=float)
    grid_meta = _json(grid_meta_path)
    grid_id = hashlib.sha256(np.asarray(grid, dtype="<f8").tobytes()).hexdigest()
    if grid_id != grid_meta.get("grid_id"):
        raise ValueError("Gate 2B-B common validation grid hash is inconsistent")
    if grid_id != "2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f":
        raise ValueError("Stage 3.7 requires the frozen Gate 2B-B common grid")
    return {
        "run_dir": str(run),
        "row": row,
        "design": design,
        "grid": grid,
        "grid_id": grid_id,
        "grid_sha256_file": _sha256(grid_path),
    }


def _released_design(value: Mapping[str, Any]) -> ReleasedFilterDesign:
    allowed = {field.name for field in ReleasedFilterDesign.__dataclass_fields__.values()}
    return ReleasedFilterDesign(**{key: value[key] for key in allowed if key in value})


def _m0_fixed_evaluation(cfg: Mapping[str, Any], reference: Mapping[str, Any]) -> dict[str, Any]:
    design = _released_design(reference["design"])
    sim = simulate_released_filter(
        design,
        FixedProvider(cfg["com"]),
        reference["grid"],
        cfg["center"],
        wiring=WIRING,
    )
    net = evaluate(sim.y_parameters, 50.0, 50.0)
    result = measure(reference["grid"], net, design, cfg)
    metrics = result["metrics"]
    violations = result["violations"]
    active = max(violations, key=violations.get)
    return {
        "profile_id": "M0",
        "classification": "CURRENT_BASELINE",
        "status": "BASELINE_CONTROL_EVALUATED",
        "zin_ohm": 50.0,
        "zout_ohm": 50.0,
        "wiring": WIRING,
        "grid_id": reference["grid_id"],
        "worst_il_db": metrics["worst_il_db"],
        "ripple_db": metrics["ripple_db"],
        "input_vswr": metrics["input_vswr"],
        "output_vswr": metrics["output_vswr"],
        "source_return_loss_db_min": metrics["source_return_loss_db_min"],
        "load_return_loss_db_min": metrics["load_return_loss_db_min"],
        "stop_attenuation_db": json.dumps(metrics["stop_attenuation_db"]),
        "max_violation": result["max_violation"],
        "sum_violation": sum(violations.values()),
        "individual_violations": json.dumps(_clean(violations), sort_keys=True),
        "active_limiting_constraint": active,
        "feasible": result["feasible"],
        "diagnostics": json.dumps(_clean(sim.diagnostics), sort_keys=True),
    }


def _geometry_row(profile_id: str, classification: str, design: Mapping[str, Any] | None,
                  status: str, reason: str = "") -> dict[str, Any]:
    if design is None:
        return {
            "profile_id": profile_id,
            "classification": classification,
            "status": status,
            "reason": reason,
        }
    wavelength = float(design["wavelength_um"])
    center = design.get("center_wavelength_um")
    reflector = design.get("reflector_wavelength_um")
    center_pairs = float(design["center_idt_pairs"])
    return {
        "profile_id": profile_id,
        "classification": classification,
        "status": status,
        "reason": reason,
        "wavelength_um": wavelength,
        "center_wavelength_um": center,
        "reflector_wavelength_um": reflector,
        "io_idt_pairs": design["io_idt_pairs"],
        "center_idt_pairs": design["center_idt_pairs"],
        "reflector_electrodes": design["reflector_electrodes"],
        "idt_gap_lambda": design["idt_gap_lambda"],
        "reflector_gap_lambda": design["reflector_gap_lambda"],
        "aperture_um": design["aperture_um"],
        "aperture_over_lambda": float(design["aperture_um"]) / wavelength,
        "io_over_center": float(design["io_idt_pairs"]) / center_pairs,
        "reflector_electrodes_per_side": float(design["reflector_electrodes"]) / 2.0,
        "metallization_ratio": design.get("metallization_ratio"),
        "thickness_over_lambda": design.get("thickness_over_lambda"),
        "io_at_hard_lower_bound": int(design["io_idt_pairs"]) == 8,
    }


def _write_plots(out: Path, reference: Mapping[str, Any], m0: Mapping[str, Any]) -> None:
    plot_dir = out / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    design = _released_design(reference["design"])
    sim = simulate_released_filter(
        design, FixedProvider(reference["cfg"]["com"]), reference["grid"],
        reference["cfg"]["center"], wiring=WIRING,
    )
    net = evaluate(sim.y_parameters, 50.0, 50.0)
    freq_mhz = reference["grid"] / 1e6

    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    axes[0].plot(freq_mhz, net["il"], label="M0 fixed reference")
    axes[0].set_ylabel("Insertion loss (dB)")
    axes[0].grid(True, alpha=.25)
    axes[0].legend()
    axes[1].plot(freq_mhz, 20 * np.log10(np.maximum(np.abs(net["s"][:, 0, 0]), 1e-15)), label="S11")
    axes[1].plot(freq_mhz, 20 * np.log10(np.maximum(np.abs(net["s"][:, 1, 0]), 1e-15)), label="S21")
    axes[1].set_xlabel("Frequency (MHz)")
    axes[1].set_ylabel("Magnitude (dB)")
    axes[1].grid(True, alpha=.25)
    axes[1].legend()
    fig.suptitle("Stage 3.7 fixed-design control; literature profiles not simulated")
    fig.tight_layout()
    fig.savefig(plot_dir / "fixed_design_response_by_profile.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(["M0"], [float(m0["max_violation"])])
    ax.text(.5, .5, "Phase D not run\nCOM mapping blocked", transform=ax.transAxes,
            ha="center", va="center", bbox={"facecolor": "white", "alpha": .8})
    ax.set_ylabel("Max violation")
    ax.set_title("Reoptimized comparison (no production profiles)")
    ax.grid(True, axis="y", alpha=.25)
    fig.tight_layout()
    fig.savefig(plot_dir / "reoptimized_max_violation_by_profile_seed.png", dpi=140)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    axes[0].bar(["M0"], [float(reference["design"]["aperture_um"]) / float(reference["design"]["wavelength_um"])])
    axes[0].set_ylabel("Aperture / wavelength")
    axes[1].bar(["M0"], [float(reference["design"]["io_idt_pairs"])])
    axes[1].set_ylabel("Outer IDT pairs")
    fig.suptitle("Normalized geometry control; literature geometry unavailable")
    fig.tight_layout()
    fig.savefig(plot_dir / "normalized_geometry_comparison.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.axis("off")
    ax.text(.5, .5, "No complete literature geometry table was numerically extracted.\n"
            "Reviewed sources remain reference-only.", ha="center", va="center")
    ax.set_title("Literature vs optimized geometry comparison")
    fig.tight_layout()
    fig.savefig(plot_dir / "literature_vs_optimized_geometry.png", dpi=140)
    plt.close(fig)


def _summary_text(reference: Mapping[str, Any], audit_rows: list[dict[str, Any]],
                  m0: Mapping[str, Any], grid_file_hash: str) -> str:
    d = reference["design"]
    rows = "\n".join(
        f"| {row['profile_id']} | {row['classification']} | {row['production_eligible']} | {row['reason']} |"
        for row in audit_rows
    )
    return f"""# Stage 3.7 Material / COM 50-ohm Sanity Screen

## Decision

`COM_MAPPING_BLOCKED` — no literature profile met the complete single-source
mapping gate. Phase D was not started, no literature profile was simulated,
and no Stage 3.8 material baseline was selected.

Hard stop: `STAGE3_7_COM_MAPPING_BLOCKED_STOP`

## Current M0 audit

- Git branch: `{_git(['branch', '--show-current'])}`
- Git HEAD: `{_git(['rev-parse', 'HEAD'])}`
- Current provider: `src/sawopt/core/models.py:FixedProvider`
- COM config: `configs/models/com_params_hypothetical.yaml`
- Convention: `docs/conventions/com_convention.md`; exp(+j omega t), x left-to-right, power-flux normalization.
- M0 values: velocity 3900 m/s; kappa_lambda 0.020; alpha 1200 sqrt(S)/m; C 1e-8 F/m; loss 0.015 dB/lambda; reference aperture 80 um.
- Fixed design metadata: metallization ratio 0.5; thickness/lambda 0.04.
- Topology/wiring: current 3-IDT DMS, `{WIRING}`, 50/50 ohm.

## Frozen Stage 3.6 reference

The reference is the Gate 2B-B B1 50/50-ohm G1_G2 32k row with the smallest
validated max violation, seed `{reference['row']['seed']}`. The design was
read from the existing record and not hand-edited.

| field | value |
|---|---:|
| wavelength_um | {d['wavelength_um']} |
| center_wavelength_um | {d.get('center_wavelength_um')} |
| io_idt_pairs | {d['io_idt_pairs']} |
| center_idt_pairs | {d['center_idt_pairs']} |
| reflector_electrodes | {d['reflector_electrodes']} |
| idt_gap_lambda | {d['idt_gap_lambda']} |
| reflector_gap_lambda | {d['reflector_gap_lambda']} |
| aperture_um | {d['aperture_um']} |
| aperture/lambda | {float(d['aperture_um']) / float(d['wavelength_um'])} |
| metallization_ratio | {d['metallization_ratio']} |
| thickness_over_lambda | {d['thickness_over_lambda']} |
| active constraint | {reference['row']['active_limiting_constraint']} |

Common validation grid ID: `{reference['grid_id']}`; file SHA-256:
`{grid_file_hash}`; point count: `{len(reference['grid'])}`.

## Literature profile audit

| profile | classification | production eligible | decision |
|---|---|---:|---|
{rows}

The reviewed 42-degree YX/Al sources provide useful geometry, thickness,
velocity, coupling, reflection, or loss context, but not a complete
repository-compatible complex kappa/alpha/distributed-C/loss set with phase
and normalization. The 2022 extraction paper is a convention/mapping
reference, not a same-stack 42-degree YX-Al profile. No values were mixed or
filled from M0.

## M0 fixed-design control

This is a control evaluation only, not a material ranking:

- worst IL: {m0['worst_il_db']:.9g} dB
- ripple: {m0['ripple_db']:.9g} dB
- input/output VSWR: {m0['input_vswr']:.9g} / {m0['output_vswr']:.9g}
- max violation: {m0['max_violation']:.9g}
- sum violation: {m0['sum_violation']:.9g}
- active limiting constraint: `{m0['active_limiting_constraint']}`

## Sol review boundary

The review approved the audit, M0 parity/control, and labeled fixed-design
work, but set a hard NO-GO on Phase D until one indivisible profile satisfies
the full convention, normalization, alpha/C/loss/phase, stack, and source
reproduction gate. A common grid and an 8k budget do not establish convergence.

## Recommended next action

Acquire or extract one complete 42-degree YX-LiTaO3/Al COM set (including
complex kappa and alpha, distributed C, loss definition, phases, aperture
normalization, and source reconstruction evidence). Re-run this stage from a
new run directory only after the profile passes provider/unit/passivity/
reciprocity tests. Do not start 5-IDT, impedance sweep, bound expansion,
continuous material interpolation, or higher-budget confirmation work.
"""


def run_stage37(config_path: str | Path, run_path: str | Path, *, resume: bool = False):
    del resume
    cfg = load_experiment_config(config_path)
    section = cfg.setdefault("stage3_7", {})
    registry_path = _resolve(section.get("profile_registry", REGISTRY_DEFAULT))
    registry = _load_registry(registry_path)
    reference = _gate2b_reference(cfg)
    reference["cfg"] = cfg
    out = initialize(run_path, cfg)
    results = out / "results"
    metadata = out / "metadata"
    results.mkdir(parents=True, exist_ok=True)
    metadata.mkdir(parents=True, exist_ok=True)

    audit_rows = _audit_rows(registry)
    _write_csv(results / "literature_com_profile_audit.csv", audit_rows)
    mapping_rows = []
    for row in audit_rows:
        mapping_rows.append({
            "profile_id": row["profile_id"],
            "classification": row["classification"],
            "mapping_confidence": "EXACT_M0_SNAPSHOT" if row["profile_id"] == "M0" else "BLOCKED",
            "mapping_formula": "repository FixedProvider for M0" if row["profile_id"] == "M0" else "not applied",
            "unit_check": "PASS" if row["profile_id"] == "M0" else "NOT_RUN",
            "source_reconstruction": "NOT_APPLICABLE" if row["profile_id"] == "M0" else "NOT_AVAILABLE",
            "decision": "CONTROL_ONLY" if row["profile_id"] == "M0" else "PHASE_D_EXCLUDED",
        })
    _write_csv(results / "com_convention_mapping.csv", mapping_rows)

    m0 = _m0_fixed_evaluation(cfg, reference)
    _write_csv(results / "fixed_design_profile_sensitivity.csv", [m0] + [
        {
            "profile_id": row["profile_id"],
            "classification": row["classification"],
            "status": "NOT_SIMULATED_MAPPING_BLOCKED",
            "reason": row["reason"],
        }
        for row in audit_rows if row["profile_id"] != "M0"
    ])

    geometry_rows = [_geometry_row("M0", "CURRENT_BASELINE", reference["design"], "REFERENCE_DESIGN")]
    geometry_rows.extend(
        _geometry_row(row["profile_id"], row["classification"], None,
                      "NOT_AVAILABLE_REFERENCE_ONLY", row["reason"])
        for row in audit_rows if row["profile_id"] != "M0"
    )
    _write_csv(results / "geometry_comparison.csv", geometry_rows)

    literature_rows = []
    for source in registry.get("reviewed_sources", []):
        geometry_reference = source.get("geometry_reference", {})
        literature_rows.append({
            "source_id": source.get("id"),
            "title": source.get("title"),
            "authors": source.get("authors"),
            "year": source.get("year"),
            "doi": source.get("doi"),
            "url": source.get("url"),
            "wavelength_um": geometry_reference.get("wavelength_um"),
            "idt_pair_counts": geometry_reference.get("idt_pair_counts"),
            "reflector_finger_count": geometry_reference.get("reflector_finger_count"),
            "aperture_over_lambda": geometry_reference.get("aperture_over_lambda"),
            "idt_gap_over_lambda": geometry_reference.get("idt_gap_over_lambda"),
            "metallization_ratio": geometry_reference.get("metallization_ratio"),
            "h_over_lambda": geometry_reference.get("h_over_lambda"),
            "dms_order": geometry_reference.get("dms_order"),
            "frequency_band": geometry_reference.get("frequency_band"),
            "classification": source.get("classification"),
            "evidence": source.get("evidence"),
        })
    _write_csv(results / "literature_geometry_comparison.csv", literature_rows)

    not_run_rows = []
    for row in audit_rows:
        for seed in (20260917, 20260918):
            not_run_rows.append({
                "profile_id": row["profile_id"],
                "seed": seed,
                "budget": 8000,
                "status": "NOT_RUN_COM_MAPPING_BLOCKED",
                "reason": "No production-eligible literature COM profile was available.",
            })
    _write_csv(results / "all_seed_results.csv", not_run_rows)
    _write_csv(results / "profile_summary.csv", [
        {
            "profile_id": row["profile_id"],
            "classification": row["classification"],
            "production_eligible": row["production_eligible"],
            "fixed_design_status": "CONTROL_ONLY" if row["profile_id"] == "M0" else "NOT_SIMULATED",
            "phase_d_status": "NOT_RUN_COM_MAPPING_BLOCKED",
            "stage3_8_baseline_eligible": False,
        }
        for row in audit_rows
    ])
    _write_csv(results / "convergence_lite.csv", not_run_rows)

    grid_path = results / "common_validation_grid_hz.csv"
    np.savetxt(grid_path, reference["grid"], header="frequency_hz", comments="")
    save(results / "common_validation_grid.json", {
        "grid_id": reference["grid_id"],
        "frequency_count": int(len(reference["grid"])),
        "source": str(Path(reference["run_dir"]) / "results" / "common_validation_grid_hz.csv"),
        "sha256": _sha256(grid_path),
    })
    save(metadata / "m0_snapshot.json", {
        "profile_id": "M0",
        "source_config": "configs/models/com_params_hypothetical.yaml",
        "com": _clean(cfg["com"]),
        "filter_design": _clean(reference["design"]),
        "zin_ohm": 50.0,
        "zout_ohm": 50.0,
        "wiring": WIRING,
        "common_validation_grid_id": reference["grid_id"],
    })
    save(metadata / "gate2b_b_reference.json", _clean({
        "run_dir": reference["run_dir"],
        "row": reference["row"],
        "grid_id": reference["grid_id"],
        "grid_file_sha256": reference["grid_sha256_file"],
    }))
    (metadata / "profile_registry_snapshot.yaml").write_text(
        registry_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    _write_plots(out, reference, m0)
    summary = _summary_text(reference, audit_rows, m0, reference["grid_sha256_file"])
    (out / "stage3_7_material_com_sanity_summary.md").write_text(summary, encoding="utf-8")
    (out / "com_profile_mapping_notes.md").write_text(
        "# COM profile mapping notes\n\n"
        "M0 is an exact repository control. The reviewed literature sources are "
        "reference-only because the complete complex kappa/alpha/distributed-C/loss "
        "and phase normalization cannot be reconstructed without mixing sources or "
        "guessing. Phase D is prohibited until a single coherent profile passes "
        "source reconstruction, unit, passivity, reciprocity, and synchronism checks.\n",
        encoding="utf-8",
    )
    (out / "test_summary.md").write_text(
        "# Test summary\n\n"
        "This artifact records the stage-run gate. Provider parity/unit tests are "
        "executed separately by the repository test command; no Phase D optimizer "
        "run was started because COM mapping was blocked.\n",
        encoding="utf-8",
    )
    (out / STOP_MARKER).write_text("STAGE3_7_COM_MAPPING_BLOCKED_STOP\n", encoding="utf-8")
    return {
        "run": str(out),
        "decision": "COM_MAPPING_BLOCKED",
        "stop_marker": STOP_MARKER,
        "usable_literature_profiles": 0,
        "reference_profile": "M0",
        "common_validation_grid_id": reference["grid_id"],
    }


__all__ = ["run_stage37"]
