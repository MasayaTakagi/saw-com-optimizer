"""Population sizing primitives independent of any SAW topology."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

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


def independent_uniform_candidate(rng, low, high, integer_indices, canonicalize):
    """Draw and canonicalize one independent real-uniform proposal.

    The proposal uses the historical draw expression and applies the caller's
    canonicalizer after drawing every coordinate, preserving seeded draw order.
    """
    low = np.asarray(low, dtype=float)
    high = np.asarray(high, dtype=float)
    proposal = low + rng.random(len(low)) * (high - low)
    if np.any(proposal < low) or np.any(proposal >= high):
        raise AssertionError("uniform proposal escaped its declared half-open interval")
    active = np.column_stack((low, high))
    candidate = canonicalize(proposal, active, integer_indices)
    for index in range(len(low)):
        expected = np.floor(proposal[index] + 0.5) if index in integer_indices else proposal[index]
        if candidate[index] != expected:
            raise AssertionError("canonicalization clipped or repaired an in-bounds proposal")
    return candidate


def sample_independent_uniform_population(
    *,
    rng,
    low,
    high,
    integer_indices: Sequence[int],
    first_candidate,
    population_size: int,
    max_attempts: int,
    reason_names: Sequence[str],
    candidate_proposer: Callable,
    geometry_check: Callable[[np.ndarray], tuple[Mapping, Mapping, float]],
):
    """Apply canonicalization, geometry rejection, and uniqueness in draw order.

    Topology-specific decoding and geometry evaluation are supplied by the
    problem layer through ``candidate_proposer`` and ``geometry_check``.
    """
    physical_population = [first_candidate.copy()]
    random_population = []
    seen = {tuple(float(value) for value in first_candidate)}
    draws = geometry_rejections = duplicate_rejections = 0
    reasons = {name: 0 for name in reason_names}
    while len(physical_population) < population_size and draws < max_attempts:
        draws += 1
        candidate = candidate_proposer(rng, low, high, integer_indices)
        _dimensions, violations, maximum = geometry_check(candidate)
        if not np.isfinite(maximum) or maximum > 0.0:
            geometry_rejections += 1
            for name, value in violations.items():
                if value > 0.0:
                    reasons[name] += 1
            continue
        key = tuple(float(value) for value in candidate)
        if key in seen:
            duplicate_rejections += 1
            continue
        seen.add(key)
        physical_population.append(candidate)
        random_population.append(candidate)
    return (
        physical_population,
        random_population,
        draws,
        geometry_rejections,
        duplicate_rejections,
        reasons,
    )


__all__ = [
    "independent_uniform_candidate",
    "sample_independent_uniform_population",
    "scaled_population",
]
