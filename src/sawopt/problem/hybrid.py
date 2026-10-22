"""Legacy Q1-A public canonicalization import path.

The implementation is owned by :mod:`sawopt.design.space`; this import keeps
only the explicitly retained 92-case public-method characterization path.
Stage 4A/B/C callers import the design API directly.
"""
from ..design.space import HYBRID_TOPOLOGIES, HybridDesignSpace

__all__ = ["HYBRID_TOPOLOGIES", "HybridDesignSpace"]
