"""Released geometry for the mirrored three-IDT DMS reference structure."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from types import SimpleNamespace
from typing import Any

import numpy as np

from ..physics.com import SimulationResult, acoustic_admittance, validate_admittance


@dataclass(frozen=True)
class ReleaseSection:
    region: str
    length_lambda: float
    wavelength_um: float
    aperture_um: float
    electrodes: float
    port: int | None
    metallization_ratio: float


@dataclass(frozen=True)
class ReleasedFilterDesign:
    """Legacy design fields plus optional section-class overrides."""

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
        """Return the immutable mirrored R-gap-O-gap-C-gap-O-gap-R profile."""
        center_lambda = self.center_wavelength_um or self.wavelength_um
        reflector_lambda = self.reflector_wavelength_um or self.wavelength_um
        center_aperture = self.center_aperture_um or self.aperture_um
        # Gap lengths intentionally retain the global wavelength reference.
        return (
            asdict(ReleaseSection("reflector", self.reflector_electrodes / 2,
                                  reflector_lambda, self.aperture_um,
                                  self.reflector_electrodes, None,
                                  self.metallization_ratio)),
            asdict(ReleaseSection("gap", self.reflector_gap_lambda,
                                  self.wavelength_um, self.aperture_um,
                                  0.0, None, self.metallization_ratio)),
            asdict(ReleaseSection("idt", self.io_idt_pairs,
                                  self.wavelength_um, self.aperture_um,
                                  2 * self.io_idt_pairs, 0,
                                  self.metallization_ratio)),
            asdict(ReleaseSection("gap", self.idt_gap_lambda,
                                  self.wavelength_um, self.aperture_um,
                                  0.0, None, self.metallization_ratio)),
            asdict(ReleaseSection("idt", self.center_idt_pairs,
                                  center_lambda, center_aperture,
                                  2 * self.center_idt_pairs, 1,
                                  self.metallization_ratio)),
            asdict(ReleaseSection("gap", self.idt_gap_lambda,
                                  self.wavelength_um, self.aperture_um,
                                  0.0, None, self.metallization_ratio)),
            asdict(ReleaseSection("idt", self.io_idt_pairs,
                                  self.wavelength_um, self.aperture_um,
                                  2 * self.io_idt_pairs, 2,
                                  self.metallization_ratio)),
            asdict(ReleaseSection("gap", self.reflector_gap_lambda,
                                  self.wavelength_um, self.aperture_um,
                                  0.0, None, self.metallization_ratio)),
            asdict(ReleaseSection("reflector", self.reflector_electrodes / 2,
                                  reflector_lambda, self.aperture_um,
                                  self.reflector_electrodes, None,
                                  self.metallization_ratio)),
        )


def simulate_released_filter(
    design: ReleasedFilterDesign, com_provider: Any, frequencies_hz: Any,
    center: str = "grounded", wiring: str = "center_outer_same",
    debug_diagnostics: bool = False,
) -> SimulationResult:
    """Simulate the released three-IDT geometry with its legacy port wiring."""
    if center not in ("grounded", "floating"):
        raise ValueError("Unknown center termination")
    profile = design.section_geometry()
    regions = [(item["region"], item["length_lambda"], item["port"]) for item in profile]
    section_geometries = [SimpleNamespace(
        wavelength_um=float(item["wavelength_um"]),
        aperture_um=float(item["aperture_um"]),
    ) for item in profile]
    frequencies_hz = np.asarray(frequencies_hz, dtype=float)
    y, solve_diagnostics = acoustic_admittance(
        design, com_provider, frequencies_hz, regions, 3,
        return_diagnostics=True, debug_diagnostics=debug_diagnostics,
        section_geometries=section_geometries,
    )
    if wiring in ("center_outer_same", "center_outer_opposite"):
        sign = 1 if wiring == "center_outer_same" else -1
        B = np.array([[0, 1], [1, 0], [0, sign]])
        out = B.T @ y @ B
    elif wiring == "outer_ports":
        out = y[:, [0, 2]][:, :, [0, 2]]
        if center == "floating":
            ycc = y[:, 1, 1]
            if np.any(np.abs(ycc) < np.finfo(float).tiny):
                raise ValueError("Floating-center elimination is singular (Ycc is zero)")
            out -= y[:, [0, 2], 1, None] * y[:, None, 1, [0, 2]] / ycc[:, None, None]
    else:
        raise ValueError("Unknown DMS wiring")
    diagnostics = validate_admittance(out, frequencies_hz=frequencies_hz)
    diagnostics.update(solve_diagnostics)
    return SimulationResult(frequencies_hz, out, diagnostics)


__all__ = ["ReleaseSection", "ReleasedFilterDesign", "simulate_released_filter"]
