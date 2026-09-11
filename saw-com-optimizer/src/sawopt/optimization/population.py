"""Population sizing primitives independent of any SAW topology."""
from __future__ import annotations

import numpy as np


def scaled_population(base_population, dimensions, reference_dimensions=7, minimum=5):
    """Scale an explicit DE initial population with problem dimension."""
    base_population = int(base_population)
    dimensions = int(dimensions)
    reference_dimensions = int(reference_dimensions)
    minimum = int(minimum)
    if base_population < minimum:
        raise ValueError(f"Population must be at least {minimum}")
    if dimensions <= 0 or reference_dimensions <= 0:
        raise ValueError("Dimensions must be positive")
    return max(minimum, int(np.ceil(base_population * dimensions / reference_dimensions)))


__all__ = ["scaled_population"]
