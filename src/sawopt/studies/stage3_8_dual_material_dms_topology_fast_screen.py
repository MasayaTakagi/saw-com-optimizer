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
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import yaml

from ..core.com import simulate_filter
from ..core.literature_com import profile_from_mapping
from ..core.metrics import geometry, measure, search_grid
from ..core.models import FilterDesign, FixedProvider
from ..core.network import evaluate
from ..core.topology import (
    AcousticSection,
    parallel_two_port_admittance,
    simulate_section_chain,
)
from ..io.config import load_experiment_config
from ..io.serialization import save
from ..optimizers.lshade import LShadeBackend
from ..optimizers.selection import DEFAULT_COMPARATOR, rank
from ..reporting.material_metadata import material_profile_metadata
from .optimizer_ab import lshade_record
from .stage3_6_gate2a import (
    ReleasedFilterDesign,
    decode_release,
    release_bounds,
    release_schema,
    simulate_released_filter,
)


ROOT = Path(__file__).resolve().parents[3]
STUDY_TYPE = "stage3_8_dual_material_dms_topology_fast_screen"
T0 = "T0_CURRENT_3IDT"
T1 = "T1_SYMMETRIC_5IDT"
T2 = "T2_PARALLEL_3IDT_X2"
TOPOLOGIES = (T0, T1, T2)
MATERIALS = ("M0", "MLIT")
SEEDS = (20260917, 20260918)
CHECKPOINTS = (2000, 4000, 6000, 8000)
T0_RELEASE_GROUP = "G1_G2"
T1_PORT_MATRIX = ((1.0, 0.0), (0.0, -1.0), (1.0, 0.0), (0.0, -1.0), (1.0, 0.0))
T0_PORT_MATRIX = ((0.0, 1.0), (1.0, 0.0), (0.0, 1.0))
STOP_COMPLETE = "STAGE3_8_DUAL_MATERIAL_TOPOLOGY_FAST_SCREEN_COMPLETE_STOP"
STOP_VALIDATION_FAIL = "STAGE3_8_TOPOLOGY_VALIDATION_FAIL_STOP"
STOP_BOUNDARY = "STAGE3_8_BOUNDARY_LIMITED_STOP"


@dataclass(frozen=True)
class FiveIdtDesign:
    """Mirror-symmetric R-A-B-C-B-A-R design with ten search variables."""

    wavelength_A_um: float = 5.0
    wavelength_B_um: float = 5.0
    wavelength_C_um: float = 5.0
    reflector_wavelength_um: float = 5.0
    pairs_A: int = 4
    pairs_B: int = 4
    pairs_C: int = 16
    common_idt_gap_lambda: float = 0.5
    reflector_gap_lambda: float = 0.5
    aperture_um: float = 80.0
    reflector_electrodes: int = 40
    metallization_ratio: float = 0.5
    thickness_over_lambda: float = 0.04

    def section_geometry(self) -> tuple[dict[str, Any], ...]:
        sections = _five_idt_sections(self)
        return tuple(section.as_dict() for section in sections)


@dataclass(frozen=True)
class ParallelThreeIdtDesign:
    """Two tracks with shared geometry and independent main wavelengths."""

    track_A_main_wavelength_um: float = 4.95
    track_B_main_wavelength_um: float = 5.05
    io_idt_pairs: int = 8
    center_idt_pairs: int = 15
    reflector_electrodes: int = 40
    idt_gap_lambda: float = 0.5
    reflector_gap_lambda: float = 0.5
    center_wavelength_ratio: float = 1.0
    reflector_wavelength_ratio: float = 1.0
    total_aperture_um: float = 80.0
    metallization_ratio: float = 0.5
    thickness_over_lambda: float = 0.04

    @property
    def aperture_um(self) -> float:
        return float(self.total_aperture_um)

    def track_aperture_um(self) -> float:
        return float(self.total_aperture_um) / 2.0

    def track_sections(self, main_wavelength_um: float) -> tuple[AcousticSection, ...]:
        return _three_idt_sections(
            main_wavelength_um=float(main_wavelength_um),
            center_wavelength_um=float(main_wavelength_um * self.center_wavelength_ratio),
            reflector_wavelength_um=float(main_wavelength_um * self.reflector_wavelength_ratio),
            io_idt_pairs=self.io_idt_pairs,
            center_idt_pairs=self.center_idt_pairs,
            reflector_electrodes=self.reflector_electrodes,
            idt_gap_lambda=self.idt_gap_lambda,
            reflector_gap_lambda=self.reflector_gap_lambda,
            aperture_um=self.track_aperture_um(),
            label_prefix="track",
        )

    def topology_geometry(self, constraints: Mapping[str, Any]):
        sections = self.track_sections(self.track_A_main_wavelength_um)
        other = self.track_sections(self.track_B_main_wavelength_um)
        active = [section for section in (*sections, *other) if section.region != "gap"]
        length = max(
            sum(section.length_lambda * section.wavelength_um for section in sections),
            sum(section.length_lambda * section.wavelength_um for section in other),
        )
        electrodes = sum(section.electrodes for section in (*sections, *other))
        wavelengths = [section.wavelength_um for section in active]
        widths = [value * self.metallization_ratio / 2 for value in wavelengths]
        gaps = [value * (1 - self.metallization_ratio) / 2 for value in wavelengths]
        dims = {
            "length_um": float(length),
            "width_um": float(self.total_aperture_um),
            "electrodes": float(electrodes),
        }
        violations = [
            max(0.0, dims["length_um"] / constraints["max_length_um"] - 1),
            max(0.0, dims["width_um"] / constraints["max_width_um"] - 1),
            max(0.0, constraints["min_electrode_width_um"] / min(widths) - 1),
            max(0.0, constraints["min_electrode_gap_um"] / min(gaps) - 1),
            max(0.0, dims["electrodes"] / constraints["max_electrodes"] - 1),
        ]
        return dims, violations


def _three_idt_sections(
    *, main_wavelength_um: float, center_wavelength_um: float,
    reflector_wavelength_um: float, io_idt_pairs: int, center_idt_pairs: int,
    reflector_electrodes: int, idt_gap_lambda: float,
    reflector_gap_lambda: float, aperture_um: float, label_prefix: str = "",
) -> tuple[AcousticSection, ...]:
    prefix = f"{label_prefix}_" if label_prefix else ""
    return (
        AcousticSection(f"{prefix}reflector_left", "reflector", reflector_electrodes / 2,
                        reflector_wavelength_um, aperture_um, None, reflector_electrodes),
        AcousticSection(f"{prefix}reflector_gap_left", "gap", reflector_gap_lambda,
                        main_wavelength_um, aperture_um),
        AcousticSection(f"{prefix}outer_left", "idt", io_idt_pairs,
                        main_wavelength_um, aperture_um, 0, 2 * io_idt_pairs),
        AcousticSection(f"{prefix}idt_gap_left", "gap", idt_gap_lambda,
                        main_wavelength_um, aperture_um),
        AcousticSection(f"{prefix}center", "idt", center_idt_pairs,
                        center_wavelength_um, aperture_um, 1, 2 * center_idt_pairs),
        AcousticSection(f"{prefix}idt_gap_right", "gap", idt_gap_lambda,
                        main_wavelength_um, aperture_um),
        AcousticSection(f"{prefix}outer_right", "idt", io_idt_pairs,
                        main_wavelength_um, aperture_um, 2, 2 * io_idt_pairs),
        AcousticSection(f"{prefix}reflector_gap_right", "gap", reflector_gap_lambda,
                        main_wavelength_um, aperture_um),
        AcousticSection(f"{prefix}reflector_right", "reflector", reflector_electrodes / 2,
                        reflector_wavelength_um, aperture_um, None, reflector_electrodes),
    )


def _sections_from_profile(profile: Iterable[Mapping[str, Any]]) -> tuple[AcousticSection, ...]:
    return tuple(
        AcousticSection(
            str(item.get("label", f"section_{index}")),
            str(item["region"]),
            float(item["length_lambda"]),
            float(item["wavelength_um"]),
            float(item["aperture_um"]),
            None if item.get("port") is None else int(item["port"]),
            float(item.get("electrodes", 0.0)),
        )
        for index, item in enumerate(profile)
    )


def t0_sections(design: ReleasedFilterDesign | FilterDesign) -> tuple[AcousticSection, ...]:
    if hasattr(design, "section_geometry"):
        return _sections_from_profile(design.section_geometry())
    return _three_idt_sections(
        main_wavelength_um=design.wavelength_um,
        center_wavelength_um=design.wavelength_um,
        reflector_wavelength_um=design.wavelength_um,
        io_idt_pairs=design.io_idt_pairs,
        center_idt_pairs=design.center_idt_pairs,
        reflector_electrodes=design.reflector_electrodes,
        idt_gap_lambda=design.idt_gap_lambda,
        reflector_gap_lambda=design.reflector_gap_lambda,
        aperture_um=design.aperture_um,
    )


def _five_idt_sections(design: FiveIdtDesign) -> tuple[AcousticSection, ...]:
    return (
        AcousticSection("reflector_left", "reflector", design.reflector_electrodes / 2,
                        design.reflector_wavelength_um, design.aperture_um, None,
                        design.reflector_electrodes),
        AcousticSection("reflector_gap_left", "gap", design.reflector_gap_lambda,
                        design.wavelength_A_um, design.aperture_um),
        AcousticSection("A_left", "idt", design.pairs_A, design.wavelength_A_um,
                        design.aperture_um, 0, 2 * design.pairs_A),
        AcousticSection("gap_A_B", "gap", design.common_idt_gap_lambda,
                        design.wavelength_A_um, design.aperture_um),
        AcousticSection("B_left", "idt", design.pairs_B, design.wavelength_B_um,
                        design.aperture_um, 1, 2 * design.pairs_B),
        AcousticSection("gap_B_C_left", "gap", design.common_idt_gap_lambda,
                        design.wavelength_B_um, design.aperture_um),
        AcousticSection("C_center", "idt", design.pairs_C, design.wavelength_C_um,
                        design.aperture_um, 2, 2 * design.pairs_C),
        AcousticSection("gap_C_B_right", "gap", design.common_idt_gap_lambda,
                        design.wavelength_C_um, design.aperture_um),
        AcousticSection("B_right", "idt", design.pairs_B, design.wavelength_B_um,
                        design.aperture_um, 3, 2 * design.pairs_B),
        AcousticSection("gap_B_A_right", "gap", design.common_idt_gap_lambda,
                        design.wavelength_B_um, design.aperture_um),
        AcousticSection("A_right", "idt", design.pairs_A, design.wavelength_A_um,
                        design.aperture_um, 4, 2 * design.pairs_A),
        AcousticSection("reflector_gap_right", "gap", design.reflector_gap_lambda,
                        design.wavelength_A_um, design.aperture_um),
        AcousticSection("reflector_right", "reflector", design.reflector_electrodes / 2,
                        design.reflector_wavelength_um, design.aperture_um, None,
                        design.reflector_electrodes),
    )


def simulate_topology(design, provider, frequencies_hz, topology: str):
    """Return an unterminated two-port simulation for T0, T1, or T2."""
    if topology == T0:
        return simulate_section_chain(
            t0_sections(design), provider, frequencies_hz, T0_PORT_MATRIX,
            topology_id=T0,
        )
    if topology == T1:
        return simulate_section_chain(
            _five_idt_sections(design), provider, frequencies_hz, T1_PORT_MATRIX,
            topology_id=T1,
        )
    if topology == T2:
        tracks = [
            simulate_section_chain(
                design.track_sections(design.track_A_main_wavelength_um),
                provider, frequencies_hz, T0_PORT_MATRIX, topology_id=f"{T2}:A",
            ),
            simulate_section_chain(
                design.track_sections(design.track_B_main_wavelength_um),
                provider, frequencies_hz, T0_PORT_MATRIX, topology_id=f"{T2}:B",
            ),
        ]
        return parallel_two_port_admittance(tracks, topology_id=T2)
    raise ValueError(f"unknown topology {topology!r}")


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


def decode_t1(vector: Sequence[float], reflector_electrodes: int = 40) -> FiveIdtDesign:
    values = np.asarray(vector, dtype=float)
    if values.shape != (10,) or not np.isfinite(values).all():
        raise ValueError("T1 requires a finite ten-dimensional vector")
    rounded = np.floor(values[[4, 5, 6]] + 0.5).astype(int)
    return FiveIdtDesign(
        wavelength_A_um=float(values[0]), wavelength_B_um=float(values[1]),
        wavelength_C_um=float(values[2]), reflector_wavelength_um=float(values[3]),
        pairs_A=int(rounded[0]), pairs_B=int(rounded[1]), pairs_C=int(rounded[2]),
        common_idt_gap_lambda=float(values[7]), reflector_gap_lambda=float(values[8]),
        aperture_um=float(values[9]), reflector_electrodes=int(reflector_electrodes),
    )


def decode_t2(vector: Sequence[float]) -> ParallelThreeIdtDesign:
    values = np.asarray(vector, dtype=float)
    if values.shape != (10,) or not np.isfinite(values).all():
        raise ValueError("T2 requires a finite ten-dimensional vector")
    rounded = np.floor(values[[2, 3, 4]] + 0.5).astype(int)
    return ParallelThreeIdtDesign(
        track_A_main_wavelength_um=float(values[0]),
        track_B_main_wavelength_um=float(values[1]),
        io_idt_pairs=int(rounded[0]), center_idt_pairs=int(rounded[1]),
        reflector_electrodes=int(rounded[2]), idt_gap_lambda=float(values[5]),
        reflector_gap_lambda=float(values[6]), center_wavelength_ratio=float(values[7]),
        reflector_wavelength_ratio=float(values[8]), total_aperture_um=float(values[9]),
    )


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


def decode_design(vector: Sequence[float], topology: str, cfg: Mapping[str, Any]):
    if topology == T0:
        return decode_release(vector, T0_RELEASE_GROUP)
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


def _active_constraint(violations: Mapping[str, Any]) -> str:
    finite = {str(key): float(value) for key, value in violations.items()}
    if not finite:
        return "none"
    maximum = max(finite.values())
    return ";".join(sorted(key for key, value in finite.items() if abs(value - maximum) <= 1e-12))


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
