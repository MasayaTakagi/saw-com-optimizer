"""Generic acoustic-section and IDT-to-port composition helpers.

The COM equations remain in :mod:`sawopt.core.com`.  This module only owns
the ordered section list and the explicit electrical port map used to turn an
N-IDT acoustic admittance into the two-port admittance consumed by the
existing network evaluator.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from types import SimpleNamespace
from typing import Any, Iterable, Sequence

import numpy as np

from .com import acoustic_admittance, validate_admittance
from .models import SimulationResult


@dataclass(frozen=True)
class AcousticSection:
    """One uniform COM section in the ordered acoustic chain.

    ``length_lambda`` is dimensionless and is multiplied by the local
    ``wavelength_um``.  ``port`` identifies an IDT electrical terminal; gaps
    and reflectors use ``None``.
    """

    label: str
    region: str
    length_lambda: float
    wavelength_um: float
    aperture_um: float
    port: int | None = None
    electrodes: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_port_matrix(port_matrix: Sequence[Sequence[float]], idt_ports: int) -> np.ndarray:
    """Validate and return a deterministic real IDT-to-two-port matrix."""
    matrix = np.asarray(port_matrix, dtype=float)
    if matrix.shape != (int(idt_ports), 2):
        raise ValueError(
            f"port_matrix must have shape ({int(idt_ports)}, 2), got {matrix.shape}"
        )
    if not np.isfinite(matrix).all():
        raise ValueError("port_matrix must contain only finite values")
    if np.allclose(matrix, 0.0):
        raise ValueError("port_matrix must connect at least one IDT to a port")
    return matrix


def _reference_geometry(sections: Sequence[AcousticSection]) -> SimpleNamespace:
    active = [section for section in sections if section.region != "gap"]
    if not active:
        raise ValueError("at least one non-gap acoustic section is required")
    return SimpleNamespace(
        wavelength_um=float(active[0].wavelength_um),
        aperture_um=float(max(section.aperture_um for section in active)),
    )


def simulate_section_chain(
    sections: Iterable[AcousticSection],
    com_provider: Any,
    frequencies_hz: Sequence[float],
    port_matrix: Sequence[Sequence[float]],
    *,
    topology_id: str,
    debug_diagnostics: bool = False,
) -> SimulationResult:
    """Simulate an ordered acoustic chain with an explicit port map.

    The acoustic solve is the existing global ``acoustic_admittance`` solve.
    The returned two-port Y is ``B.T @ Y_idt @ B`` where ``B`` is the signed
    real port matrix.  No electrical termination is applied here.
    """
    sections = tuple(sections)
    if not sections:
        raise ValueError("sections must not be empty")
    idt_ports = [section.port for section in sections if section.port is not None]
    if not idt_ports or sorted(idt_ports) != list(range(max(idt_ports) + 1)):
        raise ValueError("IDT section ports must be contiguous starting at zero")
    matrix = validate_port_matrix(port_matrix, max(idt_ports) + 1)
    frequencies = np.asarray(frequencies_hz, dtype=float)
    if frequencies.ndim != 1 or len(frequencies) == 0:
        raise ValueError("frequencies_hz must be a non-empty one-dimensional array")

    regions = tuple(
        (section.region, float(section.length_lambda), section.port)
        for section in sections
    )
    local_geometries = tuple(
        SimpleNamespace(
            wavelength_um=float(section.wavelength_um),
            aperture_um=float(section.aperture_um),
        )
        for section in sections
    )
    reference = _reference_geometry(sections)
    y_idt, solve_diagnostics = acoustic_admittance(
        reference,
        com_provider,
        frequencies,
        regions,
        max(idt_ports) + 1,
        return_diagnostics=True,
        debug_diagnostics=debug_diagnostics,
        section_geometries=local_geometries,
    )
    y_two_port = np.einsum("ia,nij,jb->nab", matrix, y_idt, matrix)
    diagnostics = validate_admittance(y_two_port, frequencies_hz=frequencies)
    diagnostics.update(solve_diagnostics)
    diagnostics.update({
        "topology_id": str(topology_id),
        "section_count": len(sections),
        "idt_port_count": max(idt_ports) + 1,
        "port_matrix": matrix.tolist(),
        "sections": [section.as_dict() for section in sections],
    })
    return SimulationResult(frequencies, y_two_port, diagnostics)


def parallel_two_port_admittance(
    simulations: Sequence[SimulationResult], *, topology_id: str,
) -> SimulationResult:
    """Sum unterminated two-port Y matrices for parallel acoustic tracks."""
    if not simulations:
        raise ValueError("at least one track simulation is required")
    reference_frequencies = np.asarray(simulations[0].frequencies_hz, dtype=float)
    total = np.zeros_like(simulations[0].y_parameters, dtype=complex)
    track_diagnostics = []
    for simulation in simulations:
        if not np.array_equal(reference_frequencies, simulation.frequencies_hz):
            raise ValueError("parallel tracks must use the same frequency grid")
        if simulation.y_parameters.shape != total.shape:
            raise ValueError("parallel tracks must have identical two-port shapes")
        total += simulation.y_parameters
        track_diagnostics.append(simulation.diagnostics)
    diagnostics = validate_admittance(total, frequencies_hz=reference_frequencies)
    diagnostics.update({
        "topology_id": str(topology_id),
        "track_count": len(simulations),
        "parallel_composition": "sum_unterminated_two_port_Y",
        "track_diagnostics": track_diagnostics,
    })
    return SimulationResult(reference_frequencies, total, diagnostics)


__all__ = [
    "AcousticSection",
    "parallel_two_port_admittance",
    "simulate_section_chain",
    "validate_port_matrix",
]
