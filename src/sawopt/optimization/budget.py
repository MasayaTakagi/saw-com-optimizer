"""Search-budget and plateau-stop services."""
from __future__ import annotations

import numpy as np


def adaptive_budget_limits(total_budget, adaptive_rounds, fractions):
    """Return cumulative total-budget limits for adaptive rounds."""
    total_budget = int(total_budget)
    if total_budget <= 0:
        raise ValueError("max_unique_decoded_evaluations must be positive")
    round_count = int(adaptive_rounds) + 1
    supplied = [float(value) for value in fractions]
    if not supplied or any(value < 0 for value in supplied):
        supplied = [1.0 / round_count] * round_count
    if len(supplied) < round_count:
        supplied.extend([0.0] * (round_count - len(supplied)))
    supplied = supplied[:round_count]
    if sum(supplied) <= 0:
        supplied = [1.0 / round_count] * round_count
    total_fraction = sum(supplied)
    limits = []
    cumulative = 0.0
    for fraction in supplied:
        cumulative += total_budget * fraction / total_fraction
        limits.append(min(total_budget, max(1, int(np.ceil(cumulative)))))
    limits[-1] = total_budget
    return limits


class PlateauStopper:
    """Conservative optional DE callback for production runs."""

    def __init__(self, *, min_generations=20, patience_generations=20,
                 feasible=False, improvement_abs=0.02, improvement_rel=0.02,
                 value_fn=None):
        self.min_generations = int(min_generations)
        self.patience_generations = int(patience_generations)
        if self.min_generations < 0 or self.patience_generations <= 0:
            raise ValueError("Invalid plateau stopper generation settings")
        self.feasible = bool(feasible)
        self.improvement_abs = float(improvement_abs)
        self.improvement_rel = float(improvement_rel)
        self.value_fn = value_fn
        self.generation = 0
        self.best = None
        self.last_improvement_generation = 0

    def _value(self, xk):
        value = xk
        if isinstance(xk, dict):
            value = xk.get("worst_il_db", xk.get("max_violation", np.inf))
        return float(value)

    def update(self, value):
        self.generation += 1
        value = float(value)
        if self.best is None:
            improved = True
        else:
            scale = max(abs(self.best), 1.0)
            improved = (self.best - value > self.improvement_abs or
                        (self.best - value) / scale > self.improvement_rel)
        if improved:
            self.best = value
            self.last_improvement_generation = self.generation
        return self.should_stop()

    def should_stop(self):
        return (
            self.generation >= self.min_generations and
            self.generation - self.last_improvement_generation >= self.patience_generations
        )

    def __call__(self, xk, convergence):
        del convergence
        if np.ndim(xk) != 0 and not isinstance(xk, dict):
            if self.value_fn is None:
                return False
            return self.update(self.value_fn(xk))
        return self.update(self._value(xk))


__all__ = ["adaptive_budget_limits", "PlateauStopper"]
