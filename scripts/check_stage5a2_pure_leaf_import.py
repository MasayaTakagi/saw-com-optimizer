#!/usr/bin/env python3
"""Fresh-process proof that the design canonicalization leaf is physics-free."""
from __future__ import annotations

import json
import sys

import numpy as np

from sawopt.design.canonicalization import canonicalize_hybrid_vector

bounds = np.asarray([[0.0, 1.0], [2.0, 4.0]], dtype=np.float64)
vector, key = canonicalize_hybrid_vector(
    [0.25, 2.5], bounds=bounds, integer_indices=(1,), dimension=2, topology="synthetic",
)
assert vector.tobytes() == np.asarray([0.25, 3.0], dtype=np.float64).tobytes()
assert key == (0.25, 3.0)
forbidden_prefixes = (
    "sawopt.problem",
    "sawopt.core.com",
    "sawopt.core.literature_com",
    "sawopt.core.models",
    "sawopt.core.metrics",
    "sawopt.core.network",
    "sawopt.core.topology",
    "sawopt.core.hybrid",
    "sawopt.studies.dms_topology_common",
    "sawopt.studies.hybrid_stage4b",
    "sawopt.studies.hybrid_stage4c",
    "sawopt.orchestration",
    "sawopt.runtime",
)
loaded = sorted(
    name for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
)
if loaded:
    raise SystemExit(f"forbidden Q1 runtime imports observed: {loaded}")
print(json.dumps({"imports_checked": True, "forbidden_imports": loaded, "result": key}))
