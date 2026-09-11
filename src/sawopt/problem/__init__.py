"""The SAW optimization problem: design representation and evaluation."""

from .design_space import canonical_design
from .evaluator import dense, evaluate_design
from .validation import geometry_violations

__all__ = ["canonical_design", "dense", "evaluate_design", "geometry_violations"]
