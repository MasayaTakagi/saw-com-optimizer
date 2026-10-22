"""Filter records, vector decoding, and mixed-integer design spaces."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np

from .canonicalization import canonicalize_hybrid_vector
from .topology import (
    RESONATOR_BOUNDS,
    FiveIdtDesign,
    ResonatorDesign,
    ThreeIdtDesign,
    decode_resonator,
    decode_t1,
)


@dataclass
class FilterDesign:
    wavelength_um: float = 5.0
    io_idt_pairs: int = 24
    center_idt_pairs: int = 16
    reflector_electrodes: int = 40
    idt_gap_lambda: float = 0.5
    reflector_gap_lambda: float = 0.5
    aperture_um: float = 80.0
    metallization_ratio: float = 0.5
    thickness_over_lambda: float = 0.04


NAMES = list(asdict(FilterDesign()))[:7]
BOUNDS = [(4.6, 5.4), (20, 100), (10, 80), (40, 160), (0, 3), (0, 3), (30, 150)]


def decode(x):
    v = dict(zip(NAMES, map(float, x)))
    for k in NAMES[1:4]:
        v[k] = int(np.floor(v[k] + 0.5))
    return FilterDesign(**v)


def decode_t0(vector: Sequence[float]) -> ThreeIdtDesign:
    values = np.asarray(list(vector), dtype=float)
    expected = len(NAMES) + 2
    if values.shape != (expected,) or not np.isfinite(values).all():
        raise ValueError(f"G1_G2 requires a finite vector with dimension {expected}")
    base = decode(values[:len(NAMES)])
    return ThreeIdtDesign(
        **asdict(base),
        center_wavelength_um=float(values[len(NAMES)]),
        reflector_wavelength_um=float(values[len(NAMES) + 1]),
    )


def canonical_design(x):
    """Decode a search vector and return its canonical vector/cache key."""
    d = decode(x)
    vector = np.asarray([asdict(d)[key] for key in NAMES], dtype=float)
    return d, vector, tuple(float(value) for value in vector)


def canonicalize(vector, bounds=None):
    """Public alias for common decoding; optional bounds are for API clarity.

    The legacy single-mode study decoded directly without clipping. The
    optional ``bounds`` argument is accepted for callers that already enforce
    active bounds, but is intentionally not applied here to preserve behavior.
    """
    del bounds
    return canonical_design(vector)


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


__all__ = [
    "BOUNDS", "HYBRID_TOPOLOGIES", "NAMES", "FilterDesign", "HybridCandidate",
    "HybridDesignSpace", "RESONATOR_DIMENSION", "RESONATOR_INTEGER_OFFSET",
    "T1_DIMENSION", "T1_INTEGER_INDICES", "canonical_design", "canonicalize",
    "decode", "decode_t0", "resonator_count",
]
