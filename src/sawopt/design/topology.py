"""Pure SAW topology records, variable decoding, and ordered section layouts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class DesignSection:
    """Design-side geometry input for one ordered acoustic section."""

    label: str
    region: str
    length_lambda: float
    wavelength_um: float
    aperture_um: float
    port: int | None = None
    electrodes: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "region": self.region,
            "length_lambda": self.length_lambda,
            "wavelength_um": self.wavelength_um,
            "aperture_um": self.aperture_um,
            "port": self.port,
            "electrodes": self.electrodes,
        }


@dataclass
class ResonatorDesign:
    wavelength_um: float = 5.0
    pairs: int = 25
    aperture_um: float = 70.0
    reflector_electrodes: int = 40
    gap_lambda: float = 0.0


RESONATOR_BOUNDS = [(4.5, 5.6), (10, 60), (30, 150)]


def decode_resonator(x):
    return ResonatorDesign(float(x[0]), int(np.floor(x[1] + .5)), float(x[2]))


STAGE4A_TOPOLOGIES = ("D", "P_D", "D_P", "P_D_P")


# (DMS nodes, resonator terminals, node count). Added resonators are independent.
TOPOLOGIES = {
    'D': ((0, 1), [], 2),
    'S_D': ((2, 1), [(0, 2)], 3),
    'D_S': ((0, 2), [(2, 1)], 3),
    'P_D': ((0, 1), [(0, -1)], 2),
    'D_P': ((0, 1), [(1, -1)], 2),
    'S_D_S': ((2, 3), [(0, 2), (3, 1)], 4),
    'P_D_P': ((0, 1), [(0, -1), (1, -1)], 2),
    'SP_D': ((2, 1), [(0, 2), (2, -1)], 3),
    'PS_D': ((2, 1), [(0, 2), (0, -1)], 3),
    'D_SP': ((0, 2), [(2, 1), (1, -1)], 3),
    'D_PS': ((0, 2), [(2, 1), (2, -1)], 3),
    'S_D_P': ((2, 1), [(0, 2), (1, -1)], 3),
    'P_D_S': ((0, 2), [(2, 1), (0, -1)], 3),
}


T0 = "T0_CURRENT_3IDT"
T1 = "T1_SYMMETRIC_5IDT"
T2 = "T2_PARALLEL_3IDT_X2"
DMS_TOPOLOGIES = (T0, T1, T2)
T1_PORT_MATRIX = ((1.0, 0.0), (0.0, -1.0), (1.0, 0.0), (0.0, -1.0), (1.0, 0.0))
T0_PORT_MATRIX = ((0.0, 1.0), (1.0, 0.0), (0.0, 1.0))


@dataclass(frozen=True)
class ThreeIdtDesign:
    """Current mirrored three-IDT design with per-section center/reflector overrides."""

    wavelength_um: float = 5.0
    io_idt_pairs: int = 24
    center_idt_pairs: int = 16
    reflector_electrodes: int = 40
    idt_gap_lambda: float = 0.5
    reflector_gap_lambda: float = 0.5
    aperture_um: float = 80.0
    metallization_ratio: float = 0.5
    thickness_over_lambda: float = 0.04
    center_wavelength_um: float | None = None
    reflector_wavelength_um: float | None = None
    center_aperture_um: float | None = None

    def section_geometry(self) -> tuple[dict[str, Any], ...]:
        center_lambda = self.center_wavelength_um or self.wavelength_um
        reflector_lambda = self.reflector_wavelength_um or self.wavelength_um
        center_aperture = self.center_aperture_um or self.aperture_um
        sections = _three_idt_sections(
            main_wavelength_um=self.wavelength_um,
            center_wavelength_um=center_lambda,
            reflector_wavelength_um=reflector_lambda,
            io_idt_pairs=self.io_idt_pairs,
            center_idt_pairs=self.center_idt_pairs,
            reflector_electrodes=self.reflector_electrodes,
            idt_gap_lambda=self.idt_gap_lambda,
            reflector_gap_lambda=self.reflector_gap_lambda,
            aperture_um=self.aperture_um,
        )
        return tuple({
            "region": section.region,
            "length_lambda": section.length_lambda,
            "wavelength_um": section.wavelength_um,
            "aperture_um": center_aperture if section.port == 1 else section.aperture_um,
            "electrodes": section.electrodes,
            "port": section.port,
            "metallization_ratio": self.metallization_ratio,
        } for section in sections)


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

    def sections(self) -> tuple[DesignSection, ...]:
        """Return the ordered physical-region geometry owned by this design."""
        return _five_idt_sections(self)

    def section_geometry(self) -> tuple[dict[str, Any], ...]:
        return tuple(section.as_dict() for section in self.sections())


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

    def track_sections(self, main_wavelength_um: float) -> tuple[DesignSection, ...]:
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
) -> tuple[DesignSection, ...]:
    prefix = f"{label_prefix}_" if label_prefix else ""
    return (
        DesignSection(f"{prefix}reflector_left", "reflector", reflector_electrodes / 2,
                      reflector_wavelength_um, aperture_um, None, reflector_electrodes),
        DesignSection(f"{prefix}reflector_gap_left", "gap", reflector_gap_lambda,
                      main_wavelength_um, aperture_um),
        DesignSection(f"{prefix}outer_left", "idt", io_idt_pairs,
                      main_wavelength_um, aperture_um, 0, 2 * io_idt_pairs),
        DesignSection(f"{prefix}idt_gap_left", "gap", idt_gap_lambda,
                      main_wavelength_um, aperture_um),
        DesignSection(f"{prefix}center", "idt", center_idt_pairs,
                      center_wavelength_um, aperture_um, 1, 2 * center_idt_pairs),
        DesignSection(f"{prefix}idt_gap_right", "gap", idt_gap_lambda,
                      main_wavelength_um, aperture_um),
        DesignSection(f"{prefix}outer_right", "idt", io_idt_pairs,
                      main_wavelength_um, aperture_um, 2, 2 * io_idt_pairs),
        DesignSection(f"{prefix}reflector_gap_right", "gap", reflector_gap_lambda,
                      main_wavelength_um, aperture_um),
        DesignSection(f"{prefix}reflector_right", "reflector", reflector_electrodes / 2,
                      reflector_wavelength_um, aperture_um, None, reflector_electrodes),
    )


def _sections_from_profile(profile: Iterable[Mapping[str, Any]]) -> tuple[DesignSection, ...]:
    return tuple(
        DesignSection(
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


def t0_sections(design: Any) -> tuple[DesignSection, ...]:
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


def _five_idt_sections(design: FiveIdtDesign) -> tuple[DesignSection, ...]:
    return (
        DesignSection("reflector_left", "reflector", design.reflector_electrodes / 2,
                      design.reflector_wavelength_um, design.aperture_um, None,
                      design.reflector_electrodes),
        DesignSection("reflector_gap_left", "gap", design.reflector_gap_lambda,
                      design.wavelength_A_um, design.aperture_um),
        DesignSection("A_left", "idt", design.pairs_A, design.wavelength_A_um,
                      design.aperture_um, 0, 2 * design.pairs_A),
        DesignSection("gap_A_B", "gap", design.common_idt_gap_lambda,
                      design.wavelength_A_um, design.aperture_um),
        DesignSection("B_left", "idt", design.pairs_B, design.wavelength_B_um,
                      design.aperture_um, 1, 2 * design.pairs_B),
        DesignSection("gap_B_C_left", "gap", design.common_idt_gap_lambda,
                      design.wavelength_B_um, design.aperture_um),
        DesignSection("C_center", "idt", design.pairs_C, design.wavelength_C_um,
                      design.aperture_um, 2, 2 * design.pairs_C),
        DesignSection("gap_C_B_right", "gap", design.common_idt_gap_lambda,
                      design.wavelength_C_um, design.aperture_um),
        DesignSection("B_right", "idt", design.pairs_B, design.wavelength_B_um,
                      design.aperture_um, 3, 2 * design.pairs_B),
        DesignSection("gap_B_A_right", "gap", design.common_idt_gap_lambda,
                      design.wavelength_B_um, design.aperture_um),
        DesignSection("A_right", "idt", design.pairs_A, design.wavelength_A_um,
                      design.aperture_um, 4, 2 * design.pairs_A),
        DesignSection("reflector_gap_right", "gap", design.reflector_gap_lambda,
                      design.wavelength_A_um, design.aperture_um),
        DesignSection("reflector_right", "reflector", design.reflector_electrodes / 2,
                      design.reflector_wavelength_um, design.aperture_um, None,
                      design.reflector_electrodes),
    )


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


__all__ = [
    "DMS_TOPOLOGIES", "DesignSection", "FiveIdtDesign", "ParallelThreeIdtDesign",
    "RESONATOR_BOUNDS", "ResonatorDesign", "STAGE4A_TOPOLOGIES", "T0",
    "ThreeIdtDesign", "T0_PORT_MATRIX", "T1", "T1_PORT_MATRIX", "T2", "TOPOLOGIES",
    "decode_resonator", "decode_t1", "decode_t2", "t0_sections",
]
