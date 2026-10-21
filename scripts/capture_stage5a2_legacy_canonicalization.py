#!/usr/bin/env python3
"""Capture a pre-extraction, public HybridDesignSpace canonicalize corpus.

This characterization imports the legacy public module path (which has
transitive COM imports) but calls only ``HybridDesignSpace.canonicalize``.
It must run in a separate fresh Python process and must never be used by the
synthetic Stage 5A-2 runtime.

Run once, before moving the method body:
  uv run --locked python scripts/capture_stage5a2_legacy_canonicalization.py \
    --capture tests/fixtures/stage5a2/canonicalization_legacy_golden.json
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import platform
import struct
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from sawopt.problem.hybrid import HYBRID_TOPOLOGIES, HybridDesignSpace

ROOT = Path(__file__).resolve().parents[1]
STUDY_CONFIG = ROOT / "configs/studies/hybrid_stage4a_qualification.yaml"
BASE_CONFIG = ROOT / "configs/studies/dms_topology_screening.yaml"


def _read_bounds() -> dict[str, HybridDesignSpace]:
    """Read frozen Stage 4A metadata without constructing providers/evaluators."""
    study = yaml.safe_load(STUDY_CONFIG.read_text(encoding="utf-8"))
    base = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
    assert study["hybrid"]["supported_topologies"] == list(HYBRID_TOPOLOGIES)
    t1 = base["dms_topology"]["topologies"]["T1_SYMMETRIC_5IDT"]
    active = np.asarray(t1["bounds"]["active"], dtype=np.float64).copy()
    aperture = base["dms_topology"]["materials"]["MLIT"]["aperture_bounds_um"]
    active[9] = aperture
    resonator = np.asarray(study["hybrid"]["resonator_bounds"], dtype=np.float64)
    spaces: dict[str, HybridDesignSpace] = {}
    for topology in HYBRID_TOPOLOGIES:
        resonator_count = {"D": 0, "P_D": 1, "D_P": 1, "P_D_P": 2}[topology]
        bounds = np.vstack([active, *([resonator] * resonator_count)])
        indices = tuple(t1["integer_indices"]) + tuple(
            10 + 3 * index + 1 for index in range(resonator_count)
        )
        spaces[topology] = HybridDesignSpace(topology, bounds, indices)
    return spaces


def _f64_token(value: float) -> str:
    return struct.pack("<d", float(value)).hex()


def _input_record(value: Any) -> tuple[Any, dict[str, Any]]:
    """Create a JSON-safe input description plus the exact call argument."""
    if isinstance(value, np.ndarray):
        array = np.asarray(value)
        return value, {
            "kind": "ndarray",
            "dtype": array.dtype.str,
            "shape": list(array.shape),
            "bytes_hex": array.tobytes(order="C").hex(),
        }
    return value, {"kind": "python_value", "value": value}


def _make_cases(spaces: dict[str, HybridDesignSpace]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for topology, space in spaces.items():
        low = space.bounds[:, 0]
        high = space.bounds[:, 1]
        midpoint = low + (high - low) / 2.0
        cases.append({"name": f"{topology}/midpoint", "space": topology,
                      "values": midpoint.copy()})

        clipped = midpoint.copy()
        clipped[0] = np.nextafter(low[0], -np.inf)
        clipped[-1] = np.nextafter(high[-1], np.inf)
        cases.append({"name": f"{topology}/active_bounds_clip", "space": topology,
                      "values": clipped})

        for index in space.integer_indices:
            tie = np.floor(midpoint[index]) + 0.5
            for side, value in (
                ("below", np.nextafter(tie, -np.inf)),
                ("at", tie),
                ("above", np.nextafter(tie, np.inf)),
            ):
                vector = midpoint.copy()
                vector[index] = value
                cases.append({"name": f"{topology}/integer_{index}_tie_{side}",
                              "space": topology, "values": vector})

        for label, value in (("lower", 19.5), ("upper", 20.5)):
            index = space.integer_indices[0]
            custom_bounds = space.bounds.copy()
            custom_bounds[index] = (20.25, 20.75)
            custom = HybridDesignSpace(topology, custom_bounds, space.integer_indices)
            vector = midpoint.copy()
            vector[index] = value
            cases.append({"name": f"{topology}/rounded_integer_{label}_bound_clip",
                          "space": topology, "custom_bounds": custom_bounds,
                          "values": vector})

        zero_bounds = space.bounds.copy()
        zero_bounds[0] = (-1.0, 1.0)
        zero_space = HybridDesignSpace(topology, zero_bounds, space.integer_indices)
        signed_zero = midpoint.copy()
        signed_zero[0] = -0.0
        cases.append({"name": f"{topology}/signed_zero", "space": topology,
                      "custom_bounds": zero_bounds, "values": signed_zero})

        for kind, payload in (
            ("wrong_shape_short", np.zeros(space.dimension - 1, dtype=np.float64)),
            ("wrong_shape_matrix", np.zeros((1, space.dimension), dtype=np.float64)),
            ("nan", np.full(space.dimension, np.nan, dtype=np.float64)),
            ("positive_infinity", np.full(space.dimension, np.inf, dtype=np.float64)),
            ("negative_infinity", np.full(space.dimension, -np.inf, dtype=np.float64)),
            ("conversion_failure", ["not-a-float"]),
        ):
            cases.append({"name": f"{topology}/{kind}", "space": topology,
                          "values": payload})

    return cases


def _serialize_input(spec: dict[str, Any]) -> Any:
    if spec["kind"] == "ndarray":
        dtype = np.dtype(spec["dtype"])
        raw = bytes.fromhex(spec["bytes_hex"])
        return np.frombuffer(raw, dtype=dtype).copy().reshape(spec["shape"])
    return spec["value"]


def _record_case(case: dict[str, Any], spaces: dict[str, HybridDesignSpace]) -> dict[str, Any]:
    space = HybridDesignSpace(
        case["space"],
        case.get("custom_bounds", spaces[case["space"]].bounds),
        spaces[case["space"]].integer_indices,
    )
    call_value, input_spec = _input_record(case["values"])
    before = call_value.tobytes(order="C").hex() if isinstance(call_value, np.ndarray) else None
    record: dict[str, Any] = {"name": case["name"], "space": case["space"],
                              "input": input_spec,
                              "bounds_sha256": hashlib.sha256(
                                  np.asarray(space.bounds, dtype="<f8").tobytes()
                              ).hexdigest(),
                              "bounds_le_f64_hex": np.asarray(space.bounds, dtype="<f8").tobytes().hex(),
                              "integer_indices": list(space.integer_indices)}
    try:
        output, key = space.canonicalize(call_value)
    except Exception as exc:  # exact class/message are the golden contract
        record["error"] = {"class": f"{type(exc).__module__}.{type(exc).__qualname__}",
                           "message": str(exc)}
    else:
        record["output"] = {
            "dtype": output.dtype.str,
            "shape": list(output.shape),
            "owns_data": bool(output.flags.owndata),
            "writeable": bool(output.flags.writeable),
            "bytes_le_f64_hex": np.asarray(output, dtype="<f8").tobytes().hex(),
            "key_float64_le_hex": [_f64_token(item) for item in key],
            "key_order": list(range(len(key))),
            "key_type": type(key).__name__,
            "key_item_types": [type(item).__name__ for item in key],
            "shares_memory_with_input": (
                bool(np.shares_memory(output, call_value))
                if isinstance(call_value, np.ndarray) else False
            ),
        }
    after = call_value.tobytes(order="C").hex() if isinstance(call_value, np.ndarray) else None
    record["input_before_bytes_hex"] = before
    record["input_after_bytes_hex"] = after
    record["input_unchanged"] = before == after if before is not None else None
    return record


def _environment() -> dict[str, Any]:
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
    ).strip()
    canonicalizer_path = ROOT / "src/sawopt/problem/hybrid.py"
    return {
        "source_commit_sha": source_sha,
        "canonicalizer_source_sha256": hashlib.sha256(canonicalizer_path.read_bytes()).hexdigest(),
        "python": sys.version,
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "byteorder": sys.byteorder,
        "python_soabi": sysconfig.get_config_var("SOABI"),
        "numpy_version": np.__version__,
        "numpy_build_config": np.show_config(mode="dicts"),
        "study_config_sha256": hashlib.sha256(STUDY_CONFIG.read_bytes()).hexdigest(),
        "base_config_sha256": hashlib.sha256(BASE_CONFIG.read_bytes()).hexdigest(),
        "numpy_lock_entry": "numpy>=1.26 (exact environment pinned by uv.lock)",
    }


def main() -> None:
    legacy_method = inspect.getsource(HybridDesignSpace.canonicalize)
    if "return canonicalize_hybrid_vector(" in legacy_method:
        raise SystemExit("refusing capture after extraction; use the frozen pre-extraction corpus")
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path, required=True)
    args = parser.parse_args()
    spaces = _read_bounds()
    corpus = {
        "schema": "stage5a2_legacy_canonicalization_golden_v1",
        "purpose": "pre-extraction public-method characterization; canonicalize only",
        "topologies": list(HYBRID_TOPOLOGIES),
        "design_space_metadata": {
            topology: {
                "dimension": space.dimension,
                "bounds_le_f64_hex": np.asarray(space.bounds, dtype="<f8").tobytes().hex(),
                "integer_indices": list(space.integer_indices),
            }
            for topology, space in spaces.items()
        },
        "environment": _environment(),
        "cases": [_record_case(case, spaces) for case in _make_cases(spaces)],
    }
    args.capture.parent.mkdir(parents=True, exist_ok=True)
    args.capture.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.capture} ({len(corpus['cases'])} cases)")
    print(f"corpus_sha256={hashlib.sha256(args.capture.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
