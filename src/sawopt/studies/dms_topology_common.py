"""Shared DMS design and validation helpers for current study protocols."""
from __future__ import annotations

import csv
import hashlib
import json
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
from ..problem.dms_topologies import (
    FiveIdtDesign, ParallelThreeIdtDesign, T0, T0_PORT_MATRIX, T1, T1_PORT_MATRIX,
    T2, TOPOLOGIES, decode_t1, decode_t2, simulate_topology,
)
from ..problem.released_dms import ReleasedFilterDesign, simulate_released_filter
from ..reporting.material_metadata import material_profile_metadata


ROOT = Path(__file__).resolve().parents[3]
MATERIALS = ("M0", "MLIT")


def evaluate_topology_design(design, provider, cfg, frequencies_hz, topology: str, *,
                            rs: float = 50.0, rl: float = 50.0) -> dict[str, Any]:
    """Evaluate one topology while preserving the existing metrics/objective."""
    _dims, geometry_violations = geometry(design, cfg["constraints"])
    if max(geometry_violations, default=0.0) > 0:
        return _invalid_record(design, geometry_violations, "manufacturing constraint")
    simulation = simulate_topology(design, provider, frequencies_hz, topology)
    network = evaluate(simulation.y_parameters, rs, rl)
    if network["gt"].max() > 1.0 + 1e-7:
        raise ValueError("Nonpassive power gain")
    record = measure(np.asarray(frequencies_hz), network, design, cfg)
    record = dict(record)
    record.update({
        "design": asdict(design),
        "topology": topology,
        "source_impedance_ohm": float(rs),
        "load_impedance_ohm": float(rl),
        "diagnostics": simulation.diagnostics,
        "search_scalar_objective": record["objective"],
    })
    return record


def _invalid_record(design, geometry_violations: Sequence[float], failure: str):
    violations = {
        "geometry": float(max(geometry_violations, default=0.0)),
        "numerical_failure": 1.0 if failure != "manufacturing constraint" else 0.0,
    }
    return {
        "design": asdict(design),
        "metrics": {"worst_il_db": float("inf"), "ripple_db": float("inf")},
        "violations": violations,
        "max_violation": float(max(violations.values(), default=1.0)),
        "sum_violation": float(sum(violations.values())),
        "feasible": False,
        "failure": failure,
        "objective": float("inf"),
        "search_scalar_objective": float("inf"),
        "topology": None,
    }

def decode_design(vector: Sequence[float], topology: str, cfg: Mapping[str, Any]):
    if topology == T0:
        values = np.asarray(list(vector), dtype=float)
        expected = len(NAMES) + 2
        if values.shape != (expected,) or not np.isfinite(values).all():
            raise ValueError(f"G1_G2 requires a finite vector with dimension {expected}")
        base = decode(values[:len(NAMES)])
        return ReleasedFilterDesign(
            **asdict(base),
            center_wavelength_um=float(values[len(NAMES)]),
            reflector_wavelength_um=float(values[len(NAMES) + 1]),
        )
    if topology == T1:
        return decode_t1(vector, int(cfg["stage3_8"]["t1_reflector_electrodes"]))
    if topology == T2:
        return decode_t2(vector)
    raise ValueError(topology)


def _provider(material: str, cfg: Mapping[str, Any]):
    section = cfg["stage3_8"]["materials"][material]
    if material == "M0":
        values = yaml.safe_load((ROOT / section["com_file"]).read_text(encoding="utf-8"))
        return FixedProvider(values), material_profile_metadata(profile_id="M0")
    profile_path = ROOT / section["profile_file"]
    profile_data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    provider = profile_from_mapping(profile_data)
    return provider, material_profile_metadata(
        profile_data, profile_id=provider.profile_id,
        com_parameter_source=str(profile_path),
    )


def _initial_t0(material: str, cfg: Mapping[str, Any]) -> ReleasedFilterDesign:
    path = ROOT / cfg["stage3_8"]["initial_designs"][material]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "design" in payload:
        payload = payload["design"]
    allowed = {field.name for field in ReleasedFilterDesign.__dataclass_fields__.values()}
    return ReleasedFilterDesign(**{key: payload[key] for key in allowed if key in payload})


def initial_design(material: str, topology: str, cfg: Mapping[str, Any]):
    t0 = _initial_t0(material, cfg)
    if topology == T0:
        return t0
    if topology == T1:
        center = t0.center_wavelength_um or t0.wavelength_um
        outer_pairs = max(4, int(round(t0.io_idt_pairs / 2)))
        return FiveIdtDesign(
            wavelength_A_um=t0.wavelength_um,
            wavelength_B_um=(t0.wavelength_um + center) / 2,
            wavelength_C_um=center,
            reflector_wavelength_um=t0.reflector_wavelength_um or t0.wavelength_um,
            pairs_A=outer_pairs, pairs_B=outer_pairs, pairs_C=t0.center_idt_pairs,
            common_idt_gap_lambda=t0.idt_gap_lambda,
            reflector_gap_lambda=t0.reflector_gap_lambda,
            aperture_um=t0.aperture_um,
            reflector_electrodes=int(cfg["stage3_8"]["t1_reflector_electrodes"]),
        )
    offset = float(cfg["stage3_8"].get("t2_initial_main_offset_fraction", 0.01))
    center = t0.center_wavelength_um or t0.wavelength_um
    reflector = t0.reflector_wavelength_um or t0.wavelength_um
    return ParallelThreeIdtDesign(
        track_A_main_wavelength_um=t0.wavelength_um * (1 - offset),
        track_B_main_wavelength_um=t0.wavelength_um * (1 + offset),
        io_idt_pairs=t0.io_idt_pairs, center_idt_pairs=t0.center_idt_pairs,
        reflector_electrodes=t0.reflector_electrodes,
        idt_gap_lambda=t0.idt_gap_lambda, reflector_gap_lambda=t0.reflector_gap_lambda,
        center_wavelength_ratio=center / t0.wavelength_um,
        reflector_wavelength_ratio=reflector / t0.wavelength_um,
        total_aperture_um=t0.aperture_um,
    )

def _clean(value: Any):
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


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]):
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(set().union(*(row.keys() for row in materialized))) if materialized else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(materialized)


def _array_hash(values: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()

def _assert_close(name: str, left: Any, right: Any, *, rtol=1e-10, atol=1e-12):
    try:
        np.testing.assert_allclose(left, right, rtol=rtol, atol=atol)
    except AssertionError as exc:
        raise AssertionError(f"{name} parity failure: {exc}") from exc


def implementation_validation(cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Run the pre-optimization T0/T1/T2 physics gate in memory."""
    # The metrics contract includes every configured stopband, so the gate
    # uses the same deterministic search-grid constructor as the optimizer.
    frequencies = np.unique(search_grid(cfg["spec"], cfg))
    provider, _metadata = _provider("M0", cfg)
    legacy_design = FilterDesign()
    generic_t0 = ReleasedFilterDesign()
    legacy = simulate_filter(legacy_design, provider, frequencies, cfg["center"], wiring="center_outer_same")
    generalized = simulate_topology(generic_t0, provider, frequencies, T0)
    released = simulate_released_filter(generic_t0, provider, frequencies, cfg["center"], wiring="center_outer_same")
    _assert_close("T0 Y legacy/generalized", legacy.y_parameters, generalized.y_parameters)
    _assert_close("T0 Y released/generalized", released.y_parameters, generalized.y_parameters)
    legacy_net = evaluate(legacy.y_parameters, 50.0, 50.0)
    generic_net = evaluate(generalized.y_parameters, 50.0, 50.0)
    _assert_close("T0 S", legacy_net["s"], generic_net["s"])
    _assert_close("T0 IL", legacy_net["il"], generic_net["il"])
    _assert_close("T0 VSWR", legacy_net["vswr"], generic_net["vswr"])
    legacy_metrics = measure(frequencies, legacy_net, legacy_design, cfg)
    generic_metrics = measure(frequencies, generic_net, generic_t0, cfg)
    for field in ("worst_il_db", "ripple_db", "input_vswr", "output_vswr", "stop_attenuation_db"):
        _assert_close(f"T0 metric {field}", legacy_metrics["metrics"][field], generic_metrics["metrics"][field])

    t1 = FiveIdtDesign()
    t1_sim = simulate_topology(t1, provider, frequencies, T1)
    t1_repeat = simulate_topology(t1, provider, frequencies, T1)
    _assert_close("T1 deterministic", t1_sim.y_parameters, t1_repeat.y_parameters, rtol=0, atol=0)
    t1_net = evaluate(t1_sim.y_parameters, 50.0, 50.0)
    if not np.isfinite(t1_sim.y_parameters).all() or t1_net["gt"].max() > 1 + 1e-7:
        raise AssertionError("T1 finite/passive gate failed")
    if t1_sim.diagnostics["reciprocity_error"] > 1e-7:
        raise AssertionError("T1 reciprocity gate failed")
    if t1.section_geometry()[2]["port"] != 0 or t1.section_geometry()[6]["port"] != 2:
        raise AssertionError("T1 deterministic port mapping gate failed")

    t2 = ParallelThreeIdtDesign(
        track_A_main_wavelength_um=5.0, track_B_main_wavelength_um=5.0,
        total_aperture_um=80.0,
    )
    track_a = simulate_section_chain(
        t2.track_sections(5.0), provider, frequencies, T0_PORT_MATRIX, topology_id="T2:A",
    )
    track_b = simulate_section_chain(
        t2.track_sections(5.0), provider, frequencies, T0_PORT_MATRIX, topology_id="T2:B",
    )
    parallel = simulate_topology(t2, provider, frequencies, T2)
    _assert_close("T2 Y sum identity", parallel.y_parameters, track_a.y_parameters + track_b.y_parameters)
    _assert_close("T2 identical-track identity", parallel.y_parameters, 2 * track_a.y_parameters)
    if abs(t2.track_aperture_um() * 2 - t2.total_aperture_um) > 1e-12:
        raise AssertionError("T2 aperture split gate failed")
    t2_net = evaluate(parallel.y_parameters, 50.0, 50.0)
    if t2_net["gt"].max() > 1 + 1e-7 or parallel.diagnostics["reciprocity_error"] > 1e-7:
        raise AssertionError("T2 passive/reciprocal gate failed")
    return {
        "status": "PASS",
        "frequency_count": len(frequencies),
        "t0": {"legacy_vs_generalized": "PASS", "released_vs_generalized": "PASS"},
        "t1": {"finite": True, "passive": True, "reciprocal": True, "port_mapping": list(T1_PORT_MATRIX)},
        "t2": {"sum_identity": "PASS", "identical_identity": "PASS", "aperture_split": "PASS"},
        "assumptions": {
            "t1_structure": "R-A-B-C-B-A-R",
            "t1_grouping": "P=A+C+A; Q=B+B",
            "t1_signed_polarity": [1, -1, 1, -1, 1],
            "t2_parallel_composition": "sum_unterminated_two_port_Y",
        },
    }

def fixed_design_sanity(out: Path, cfg: Mapping[str, Any], grid: np.ndarray):
    rows = []
    for material in MATERIALS:
        provider, profile_metadata = _provider(material, cfg)
        for topology in TOPOLOGIES:
            design = initial_design(material, topology, cfg)
            result = evaluate_topology_design(design, provider, cfg, grid, topology)
            metrics = result.get("metrics", {})
            rows.append({
                "material": material, "topology": topology, "status": "PASS",
                "grid_id": _array_hash(grid), "frequency_count": len(grid),
                "max_violation": result.get("max_violation"),
                "sum_violation": result.get("sum_violation"),
                "worst_il_db": metrics.get("worst_il_db"),
                "ripple_db": metrics.get("ripple_db"),
                "input_vswr": metrics.get("input_vswr"),
                "output_vswr": metrics.get("output_vswr"),
                "stop_1_attenuation_db": metrics.get("stop_attenuation_db", [None] * 4)[1],
                "stop_2_attenuation_db": metrics.get("stop_attenuation_db", [None] * 4)[2],
                "passivity": result["diagnostics"].get("min_conductance_eigenvalue", -np.inf) >= -1e-8,
                "reciprocity_error": result["diagnostics"].get("reciprocity_error"),
                "profile_id": profile_metadata["id"],
                "geometry": json.dumps(_clean(result.get("design", {})), sort_keys=True),
            })
    _write_csv(out / "stage3_8_fixed_design_sanity.csv", rows)
    return rows


def provider_for_material(material: str, cfg: Mapping[str, Any]):
    """Public material provider selector for current topology studies."""
    return _provider(material, cfg)


array_hash = _array_hash
clean_value = _clean
invalid_record = _invalid_record
write_csv = _write_csv


__all__ = [
    "MATERIALS", "array_hash", "clean_value", "decode_design",
    "evaluate_topology_design", "fixed_design_sanity", "implementation_validation",
    "initial_design", "invalid_record", "provider_for_material", "write_csv",
]
