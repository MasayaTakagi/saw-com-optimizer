"""Current hybrid DMS/ladder design-space semantics for Stage 4A."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from ..core.hybrid import RESONATOR_BOUNDS, ResonatorDesign, decode_resonator
from ..core.metrics import geometry
from ..design.canonicalization import canonicalize_hybrid_vector
from .dms_topologies import T1, FiveIdtDesign, decode_t1


HYBRID_TOPOLOGIES = ("D", "P_D", "D_P", "P_D_P")
T1_DIMENSION = 10
RESONATOR_DIMENSION = 3
T1_INTEGER_INDICES = (4, 5, 6)
RESONATOR_INTEGER_OFFSET = 1


def resonator_count(topology: str) -> int:
    try:
        return {"D": 0, "P_D": 1, "D_P": 1, "P_D_P": 2}[topology]
    except KeyError as exc:
        raise ValueError(f"unsupported Stage 4A topology {topology!r}") from exc


@dataclass(frozen=True)
class HybridCandidate:
    topology: str
    vector: tuple[float, ...]
    key: tuple[float, ...]
    dms_design: FiveIdtDesign
    resonator_designs: tuple[ResonatorDesign, ...]


@dataclass(frozen=True)
class HybridDesignSpace:
    """Per-topology bounds and canonical mixed continuous/integer vector."""

    topology: str
    bounds: np.ndarray
    integer_indices: tuple[int, ...]

    @classmethod
    def from_contract(
        cls,
        topology: str,
        dms_active_bounds: Sequence[Sequence[float]],
        dms_hard_bounds: Sequence[Sequence[float]],
        resonator_bounds: Sequence[Sequence[float]] = RESONATOR_BOUNDS,
    ) -> "HybridDesignSpace":
        count = resonator_count(topology)
        dms_active = np.asarray(dms_active_bounds, dtype=float)
        dms_hard = np.asarray(dms_hard_bounds, dtype=float)
        resonator = np.asarray(resonator_bounds, dtype=float)
        if dms_active.shape != (T1_DIMENSION, 2) or dms_hard.shape != dms_active.shape:
            raise ValueError("current T1 active and hard bounds must both have shape (10, 2)")
        if resonator.shape != (RESONATOR_DIMENSION, 2):
            raise ValueError("resonator bounds must have shape (3, 2)")
        if (not np.isfinite(dms_active).all() or not np.isfinite(dms_hard).all()
                or not np.isfinite(resonator).all()
                or np.any(dms_active[:, 1] <= dms_active[:, 0])
                or np.any(dms_hard[:, 1] <= dms_hard[:, 0])
                or np.any(dms_active[:, 0] < dms_hard[:, 0])
                or np.any(dms_active[:, 1] > dms_hard[:, 1])
                or np.any(resonator[:, 1] <= resonator[:, 0])):
            raise ValueError("hybrid bounds must be finite, ordered, and contained by T1 hard bounds")
        bounds = np.vstack([dms_active, *([resonator] * count)])
        integer_indices = list(T1_INTEGER_INDICES)
        integer_indices.extend(
            T1_DIMENSION + index * RESONATOR_DIMENSION + RESONATOR_INTEGER_OFFSET
            for index in range(count)
        )
        return cls(topology, bounds, tuple(integer_indices))

    @property
    def dimension(self) -> int:
        return int(len(self.bounds))

    def canonicalize(self, vector: Sequence[float]) -> tuple[np.ndarray, tuple[float, ...]]:
        return canonicalize_hybrid_vector(
            vector,
            bounds=self.bounds,
            integer_indices=self.integer_indices,
            dimension=self.dimension,
            topology=self.topology,
        )

    def decode(self, vector: Sequence[float], *, reflector_electrodes: int = 40) -> HybridCandidate:
        canonical, key = self.canonicalize(vector)
        dms = decode_t1(canonical[:T1_DIMENSION], reflector_electrodes)
        resonators = tuple(
            decode_resonator(canonical[start:start + RESONATOR_DIMENSION])
            for start in range(T1_DIMENSION, self.dimension, RESONATOR_DIMENSION)
        )
        return HybridCandidate(
            self.topology, tuple(float(value) for value in canonical), key, dms, resonators,
        )


def hybrid_geometry(
    candidate: HybridCandidate,
    cfg: Mapping[str, Any],
    *,
    resonator_bounds: Sequence[Sequence[float]] = RESONATOR_BOUNDS,
) -> dict[str, Any]:
    """Return separate DMS, resonator, and combined hypothetical-layout checks.

    The combined layout retains the historical conservative row-placement
    approximation: each resonator occupies a row below the DMS, with the
    configured margins applied to every row. It is a qualification constraint,
    not a foundry layout or a calibrated die estimate.
    """
    settings = cfg["hybrid"]
    dms_dims, dms_values = geometry(candidate.dms_design, cfg["constraints"])
    dms_names = (
        "max_total_acoustic_length", "max_aperture_width", "minimum_electrode_width",
        "minimum_electrode_gap", "max_total_electrode_count",
    )
    dms_violations = {name: float(value) for name, value in zip(dms_names, dms_values)}
    r_bounds = np.asarray(resonator_bounds, dtype=float)
    aperture_bounds = np.asarray(settings["resonator_aperture_bounds_um"], dtype=float)
    min_width = float(cfg["constraints"]["min_electrode_width_um"])
    min_gap = float(cfg["constraints"]["min_electrode_gap_um"])
    resonator_rows = []
    resonator_violations: dict[str, float] = {}
    rows = [(float(dms_dims["length_um"]), float(candidate.dms_design.aperture_um))]
    total_electrodes = float(dms_dims["electrodes"])
    for index, design in enumerate(candidate.resonator_designs):
        vector = candidate.vector[T1_DIMENSION + index * RESONATOR_DIMENSION:
                                  T1_DIMENSION + (index + 1) * RESONATOR_DIMENSION]
        local = np.asarray(vector, dtype=float)
        wavelength, pairs, aperture = map(float, local)
        feature_width = wavelength * 0.25  # fixed FilterDesign metallization_ratio = 0.5
        feature_gap = wavelength * 0.25
        length = wavelength * (pairs + design.reflector_electrodes + 2.0 * design.gap_lambda)
        values = {
            "wavelength_lower": max(0.0, r_bounds[0, 0] / wavelength - 1.0),
            "wavelength_upper": max(0.0, wavelength / r_bounds[0, 1] - 1.0),
            "pairs_lower": max(0.0, r_bounds[1, 0] / pairs - 1.0),
            "pairs_upper": max(0.0, pairs / r_bounds[1, 1] - 1.0),
            "aperture_lower": max(0.0, aperture_bounds[0] / aperture - 1.0),
            "aperture_upper": max(0.0, aperture / aperture_bounds[1] - 1.0),
            "minimum_electrode_width": max(0.0, min_width / feature_width - 1.0),
            "minimum_electrode_gap": max(0.0, min_gap / feature_gap - 1.0),
            "max_acoustic_length": max(0.0, length / float(cfg["constraints"]["max_length_um"]) - 1.0),
            "max_aperture_width": max(0.0, aperture / float(cfg["constraints"]["max_width_um"]) - 1.0),
        }
        resonator_violations.update({f"resonator_{index}_{name}": value
                                     for name, value in values.items()})
        electrode_count = float(2 * design.pairs + 2 * design.reflector_electrodes)
        resonator_rows.append({
            "design": asdict(design), "length_um": length, "aperture_um": aperture,
            "electrodes": electrode_count, "feature_width_um": feature_width,
            "feature_gap_um": feature_gap, "violations": values,
            "max_violation": max(values.values(), default=0.0),
        })
        rows.append((length, aperture))
        total_electrodes += electrode_count

    layout = settings["layout"]
    margin_length = float(layout["length_margin_um"])
    margin_width = float(layout["width_margin_um"])
    footprint_width = max(length + margin_length for length, _ in rows)
    footprint_height = sum(aperture + margin_width for _, aperture in rows)
    die_length, die_width = map(float, layout["die_um"])
    combined_violations = {
        "die_length": max(0.0, footprint_width / die_length - 1.0),
        "die_width": max(0.0, footprint_height / die_width - 1.0),
        "max_total_electrodes": max(
            0.0, total_electrodes / float(layout["max_total_electrodes"]) - 1.0,
        ),
    }
    return {
        "dms": {"dimensions": {key: float(value) for key, value in dms_dims.items()},
                "violations": dms_violations,
                "max_violation": max(dms_violations.values(), default=0.0)},
        "resonators": resonator_rows,
        "resonator_violations": resonator_violations,
        "combined": {
            "footprint_width_um": footprint_width,
            "footprint_height_um": footprint_height,
            "footprint_mm2": footprint_width * footprint_height / 1e6,
            "total_electrodes": total_electrodes,
            "violations": combined_violations,
            "max_violation": max(combined_violations.values(), default=0.0),
        },
        "max_violation": max(
            [*dms_violations.values(), *resonator_violations.values(),
             *combined_violations.values()], default=0.0,
        ),
    }


def assumptions() -> dict[str, Any]:
    """Document fixed one-port model settings already used by resonator_y."""
    return {
        "reflector_electrodes": 40,
        "gap_lambda": 0.0,
        "metallization_ratio": 0.5,
        "thickness_over_lambda": 0.04,
        "source": "existing ResonatorDesign and FilterDesign defaults in core.hybrid/core.models",
    }


__all__ = [
    "HYBRID_TOPOLOGIES", "HybridCandidate", "HybridDesignSpace", "T1_DIMENSION",
    "assumptions", "hybrid_geometry", "resonator_count",
]
