"""Common SAW design decoding and canonicalization primitives."""
from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ..core.models import BOUNDS, NAMES, decode


def canonical_design(x):
    """Decode a search vector and return its canonical vector/cache key."""
    d = decode(x)
    vector = np.asarray([asdict(d)[key] for key in NAMES], dtype=float)
    return d, vector, tuple(float(value) for value in vector)


def canonicalize(vector, bounds=None):
    """Public alias for common decoding; optional bounds are for API clarity.

    The legacy single-mode study decoded directly without clipping.  The
    optional ``bounds`` argument is accepted for callers that already enforce
    active bounds, but is intentionally not applied here to preserve behavior.
    """
    del bounds
    return canonical_design(vector)


__all__ = ["BOUNDS", "NAMES", "canonical_design", "canonicalize"]
