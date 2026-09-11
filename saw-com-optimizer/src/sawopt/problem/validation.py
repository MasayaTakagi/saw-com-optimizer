"""Shared manufacturing-constraint validation primitives."""
from __future__ import annotations

from ..core.metrics import geometry


def geometry_violations(design, constraints):
    """Return geometry dimensions and signed constraint violations."""
    return geometry(design, constraints)


__all__ = ["geometry_violations"]
