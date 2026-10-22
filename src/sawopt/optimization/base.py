"""Backend contracts shared by reusable optimizer implementations."""
from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol

import numpy as np


Evaluation = Mapping[str, Any]
Evaluator = Callable[[np.ndarray], Evaluation]


class OptimizerBackend(Protocol):
    """Minimal stateful optimizer interface.

    Implementations count unique canonical designs, not raw floating-point
    proposals.  The evaluator is deliberately opaque so synthetic tests and
    the COM evaluator share exactly the same backend.
    """

    def initialize(self, evaluator: Evaluator, *, population: np.ndarray | None = None,
                   comparator: Any = None) -> None: ...

    def advance_to_unique_budget(self, target_unique_evals: int) -> Mapping[str, Any]: ...

    def state_dict(self) -> dict[str, Any]: ...

    def load_state_dict(self, state: Mapping[str, Any]) -> None: ...

    def population(self) -> np.ndarray: ...

    def incumbent(self) -> Evaluation | None: ...


def backend_name(backend: Any) -> str:
    return str(getattr(backend, "name", backend.__class__.__name__))


__all__ = ["Evaluation", "Evaluator", "OptimizerBackend", "backend_name"]
