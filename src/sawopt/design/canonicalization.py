"""Physics-free canonicalization for the existing hybrid design vector.

This leaf intentionally depends only on NumPy and typing. The numerical
statement order is kept identical to the pre-extraction
``HybridDesignSpace.canonicalize`` implementation.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np


def canonicalize_hybrid_vector(
    vector: Sequence[float],
    *,
    bounds: np.ndarray,
    integer_indices: tuple[int, ...],
    dimension: int,
    topology: str,
) -> tuple[np.ndarray, tuple[float, ...]]:
    """Return the legacy mixed-vector canonical form and ordered float key.

    Bounds and integer-index metadata are owned/validated by the caller. The
    ``dimension`` and ``topology`` values retain the legacy shape-error
    contract verbatim.
    """
    values = np.asarray(vector, dtype=float)
    if values.shape != (dimension,) or not np.isfinite(values).all():
        raise ValueError(f"{topology} requires a finite {dimension}-dimensional vector")
    canonical = np.clip(values.copy(), bounds[:, 0], bounds[:, 1])
    for index in integer_indices:
        canonical[index] = np.floor(canonical[index] + 0.5)
    canonical = np.clip(canonical, bounds[:, 0], bounds[:, 1])
    key = tuple(float(value) for value in canonical)
    return canonical, key


__all__ = ["canonicalize_hybrid_vector"]
