#!/usr/bin/env python3
"""Small deterministic SAW evaluator and checkpoint-v4 smoke for WSL parity."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import math
import os
import platform
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import scipy


ROOT = Path(__file__).resolve().parents[2]
CONFIG = "configs/studies/hybrid_stage4c_confirmatory.yaml"
FIXED_SEED = 20261021
OPTIMIZER_SEED = 20261022
SMOKE_BUDGET = 270
SMOKE_CHECKPOINTS = (250, 270)
METRIC_RTOL = 1e-12
METRIC_ATOL = 1e-12
OBJECTIVE_RTOL = 1e-12
OBJECTIVE_ATOL = 1e-6


def _clean(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return [_clean(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _clean(value.item())
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _finite_numeric_tree(value: Any) -> bool:
    """Return whether every numeric leaf is finite and no numeric leaf is missing."""
    if value is None:
        return False
    if isinstance(value, (bool, str)):
        return True
    if isinstance(value, (int, float, np.number)):
        return math.isfinite(float(value))
    if isinstance(value, dict):
        return all(_finite_numeric_tree(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite_numeric_tree(item) for item in value)
    return True


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    )
    return result.stdout.strip()


def _context():
    from sawopt.studies.hybrid_stage4c import load_stage4c_context

    return load_stage4c_context(CONFIG)


def _environment(context: dict[str, Any]) -> dict[str, Any]:
    import matplotlib
    import yaml

    blas = io.StringIO()
    with contextlib.redirect_stdout(blas):
        np.__config__.show()
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "matplotlib": matplotlib.__version__,
        "pyyaml": yaml.__version__,
        "blas_configuration": blas.getvalue().strip(),
        "source_commit_sha": _git("rev-parse", "HEAD"),
        "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
        "frequency_grid_sha256": context["contract"]["search_frequency_sha256"],
        "common_validation_grid_sha256": context["contract"]["common_validation_grid_sha256"],
        "dtype": "float64/complex128",
    }


def _fixed_evaluator(context: dict[str, Any], vector: list[float] | None = None) -> dict[str, Any]:
    from sawopt.studies.hybrid import stage4a_evaluate
    from sawopt.studies.hybrid_stage4b import _sample_stage4b_population

    space = context["spaces"]["P_D"]
    if vector is None:
        population, _ = _sample_stage4b_population(
            space, context["cfg"], FIXED_SEED, "P_D", 1,
        )
        vector = population[0].tolist()
    candidate = space.decode(
        vector,
        reflector_electrodes=int(context["cfg"]["dms_topology"]["t1_reflector_electrodes"]),
    )
    result = stage4a_evaluate(
        candidate, context["provider"], context["cfg"], context["search_frequencies"],
        context["source_impedance_ohm"], context["load_impedance_ohm"],
        include_spectrum=True,
    )
    spectrum = result.get("spectrum", {})
    return _clean({
        "topology": "P_D",
        "seed": FIXED_SEED,
        "candidate_input_vector": vector,
        "source_impedance_ohm": context["source_impedance_ohm"],
        "load_impedance_ohm": context["load_impedance_ohm"],
        "frequency_hz": spectrum.get("frequency_hz", context["search_frequencies"]),
        "s11_db": spectrum.get("s11_db", []),
        "s21_db": spectrum.get("s21_db", []),
        "evaluation_status": result.get("evaluation_status"),
        "geometry_max_violation": result.get("geometry_max_violation"),
        "objective": result.get("objective"),
        "max_violation": result.get("max_violation"),
        "sum_violation": result.get("sum_violation"),
        "violations": result.get("violations", {}),
        "metrics": result.get("metrics", {}),
    })


class _IntentionalStop(Exception):
    """Simulate a process stop after a durable optimizer checkpoint."""


def _run_optimizer_smoke(context: dict[str, Any], root: Path) -> dict[str, Any]:
    from sawopt.optimization.checkpoint_session import LShadeCheckpointSession
    from sawopt.studies.hybrid_stage4b import read_source_state, run_matched_cell

    source_sha = read_source_state(ROOT)["head"]
    if not source_sha:
        raise RuntimeError("Git HEAD is required for the checkpoint smoke")

    def run_cell(path: Path, *, resume: bool, stop_at: int | None = None):
        original_save = LShadeCheckpointSession.save

        def save_then_maybe_stop(session, backend, *, extra_state=None):
            saved = original_save(session, backend, extra_state=extra_state)
            if stop_at is not None and int(backend.unique_evaluations) == stop_at:
                raise _IntentionalStop(f"qualification stop after checkpoint {stop_at}")
            return saved

        try:
            if stop_at is not None:
                LShadeCheckpointSession.save = save_then_maybe_stop
            return run_matched_cell(
                context, path, topology="P_D", seed=OPTIMIZER_SEED,
                budget=SMOKE_BUDGET, checkpoints=SMOKE_CHECKPOINTS,
                terminal_budget=SMOKE_BUDGET, finalist_count=16,
                mode="wsl2_qualification", source_commit_sha=source_sha,
                resume=resume, compact_history_cache=True,
            )
        finally:
            LShadeCheckpointSession.save = original_save

    resume_path = root / "resume"
    interruptions: list[str] = []
    for stop_at, resume in ((250, False), (270, True)):
        try:
            run_cell(resume_path, resume=resume, stop_at=stop_at)
        except _IntentionalStop as exc:
            interruptions.append(str(exc))
        else:
            raise RuntimeError(f"expected controlled stop at checkpoint {stop_at}")
    resumed = run_cell(resume_path, resume=True)

    control_path = root / "uninterrupted"
    control = run_cell(control_path, resume=False)
    selected = resumed.get("common_grid_selected_finalist") or {}
    control_selected = control.get("common_grid_selected_finalist") or {}
    checkpoint = resume_path / "optimization" / "P_D" / f"seed{OPTIMIZER_SEED}" / "checkpoints" / "latest.json"
    if not checkpoint.is_file():
        raise RuntimeError("latest checkpoint missing after resume")
    checkpoint_payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    state = checkpoint_payload.get("state", checkpoint_payload)
    same_seed = (
        resumed.get("unique_evaluations") == control.get("unique_evaluations") == SMOKE_BUDGET
        and resumed.get("checkpoint_records") == control.get("checkpoint_records") == list(SMOKE_CHECKPOINTS)
        and selected.get("candidate_vector") == control_selected.get("candidate_vector")
        and selected.get("objective") == control_selected.get("objective")
        and selected.get("violations") == control_selected.get("violations")
    )
    validation_pass = (
        selected.get("evaluation_status") == "PHYSICS_EVALUATED"
        and bool(selected.get("candidate_vector"))
        and bool(selected.get("metrics"))
        and bool(selected.get("violations"))
        and _finite_numeric_tree(selected.get("candidate_vector"))
        and _finite_numeric_tree(selected.get("objective"))
        and _finite_numeric_tree(selected.get("max_violation"))
        and _finite_numeric_tree(selected.get("sum_violation"))
        and _finite_numeric_tree(selected.get("violations"))
        and _finite_numeric_tree(selected.get("metrics"))
    )
    finite_result = (
        _finite_numeric_tree(selected.get("candidate_vector"))
        and _finite_numeric_tree(selected.get("objective"))
        and _finite_numeric_tree(selected.get("max_violation"))
        and _finite_numeric_tree(selected.get("sum_violation"))
        and _finite_numeric_tree(selected.get("violations"))
        and _finite_numeric_tree(selected.get("metrics"))
    )
    smoke_pass = resumed.get("status") == "COMPLETED" and same_seed and validation_pass and finite_result
    return _clean({
        "status": "PASS" if smoke_pass else "FAIL",
        "topology": "P_D",
        "seed": OPTIMIZER_SEED,
        "budget": SMOKE_BUDGET,
        "initial_population": int(resumed.get("initialization", {}).get("accepted_population_size", 0)),
        "unique_evaluations": resumed.get("unique_evaluations"),
        "checkpoint_records": resumed.get("checkpoint_records"),
        "controlled_stops": interruptions,
        "resume_status": resumed.get("status"),
        "same_seed_reproducible_vs_uninterrupted": same_seed,
        "selected_finalist_validation": "PASS" if validation_pass else "FAIL",
        "selected_finalist_evaluation_status": selected.get("evaluation_status"),
        "finite_metrics_and_constraints": finite_result,
        "candidate_vector": selected.get("candidate_vector"),
        "objective": selected.get("objective"),
        "max_violation": selected.get("max_violation"),
        "sum_violation": selected.get("sum_violation"),
        "violations": selected.get("violations"),
        "metrics": selected.get("metrics"),
        "cache_statistics": resumed.get("cache_statistics"),
        "checkpoint": {
            "state_version": state.get("state_version"),
            "bytes": checkpoint.stat().st_size,
            "has_population": bool(state.get("population")),
            "has_historical_finalists": bool(state.get("compact_history_index") or state.get("historical_finalists")),
            "unique_evaluations": state.get("unique_evaluations"),
            "grid_version": state.get("frequency_grid_version"),
            "cache_entries": (len(state.get("cache", {})) if isinstance(state.get("cache"), dict)
                              else len(state.get("compact_history_index", []))),
        },
        "runtime_seconds": resumed.get("runtime"),
        "peak_rss_bytes": _peak_rss_bytes(),
        "raw_run_root": str(root),
    })


def _peak_rss_bytes() -> int | None:
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value * (1024 if sys.platform != "darwin" else 1)
    except (ImportError, AttributeError, OSError):
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes

                class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

                counters = PROCESS_MEMORY_COUNTERS()
                counters.cb = ctypes.sizeof(counters)
                if ctypes.windll.psapi.GetProcessMemoryInfo(
                    ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb,
                ):
                    return int(counters.PeakWorkingSetSize)
            except (AttributeError, OSError):
                pass
    return None


def _compare(reference: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    from numpy.testing import assert_allclose

    expected = reference["evaluator"]
    differences: list[str] = []
    max_s11 = max_s21 = max_frequency = None
    try:
        if actual["candidate_input_vector"] != expected["candidate_input_vector"]:
            differences.append("candidate vector changed")
        for field in ("frequency_hz", "s11_db", "s21_db"):
            left = np.asarray(expected[field], dtype=np.float64)
            right = np.asarray(actual[field], dtype=np.float64)
            if left.shape != right.shape:
                differences.append(f"{field} shape mismatch")
                continue
            delta = np.abs(left - right)
            if field == "frequency_hz":
                max_frequency = float(delta.max(initial=0.0))
                assert_allclose(left, right, rtol=0.0, atol=0.0)
            else:
                maximum = float(delta.max(initial=0.0))
                if field == "s11_db":
                    max_s11 = maximum
                else:
                    max_s21 = maximum
                assert_allclose(left, right, rtol=METRIC_RTOL, atol=METRIC_ATOL)
        for field in ("objective", "max_violation", "sum_violation"):
            left, right = expected.get(field), actual.get(field)
            if left is None or right is None:
                if left != right:
                    differences.append(f"{field} availability differs")
                continue
            rtol, atol = ((OBJECTIVE_RTOL, OBJECTIVE_ATOL) if field == "objective"
                          else (METRIC_RTOL, METRIC_ATOL))
            if not math.isclose(float(left), float(right), rel_tol=rtol, abs_tol=atol):
                differences.append(f"{field} outside declared parity tolerance")
        if expected.get("evaluation_status") != actual.get("evaluation_status"):
            differences.append("evaluation_status differs")
        expected_metrics = expected.get("metrics", {})
        actual_metrics = actual.get("metrics", {})
        if expected_metrics.keys() != actual_metrics.keys():
            differences.append("metric set differs")
        else:
            for key, left in expected_metrics.items():
                right = actual_metrics[key]
                left_values = np.asarray(left, dtype=np.float64)
                right_values = np.asarray(right, dtype=np.float64)
                if left_values.shape != right_values.shape:
                    differences.append(f"metric {key} shape differs")
                elif not np.allclose(left_values, right_values, rtol=METRIC_RTOL, atol=METRIC_ATOL):
                    differences.append(f"metric {key} outside declared parity tolerance")
        if expected.get("violations", {}).keys() != actual.get("violations", {}).keys():
            differences.append("constraint set differs")
        else:
            for key, left in expected.get("violations", {}).items():
                right = actual["violations"][key]
                if not math.isclose(float(left), float(right), rel_tol=METRIC_RTOL, abs_tol=METRIC_ATOL):
                    differences.append(f"constraint {key} outside declared parity tolerance")
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        differences.append(f"comparison error: {exc}")
    return {
        "status": "PASS" if not differences else "DIFFERENCE_REVIEW",
        "differences": differences,
        "maximum_absolute_difference": {
            "frequency_hz": max_frequency,
            "s11_db": max_s11,
            "s21_db": max_s21,
        },
        "tolerances": {
            "metrics_rtol": METRIC_RTOL, "metrics_atol": METRIC_ATOL,
            "objective_rtol": OBJECTIVE_RTOL, "objective_atol": OBJECTIVE_ATOL,
        },
    }


def capture(output: Path, run_root: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    context = _context()
    payload = {
        "schema_version": 1,
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "environment": _environment(context),
        "evaluator": _fixed_evaluator(context),
        "optimizer": _run_optimizer_smoke(context, run_root),
    }
    output.write_text(json.dumps(_clean(payload), indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def qualify(reference_path: Path, output: Path, run_root: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    context = _context()
    evaluator = _fixed_evaluator(context, reference["evaluator"]["candidate_input_vector"])
    comparison = _compare(reference, evaluator)
    optimizer = _run_optimizer_smoke(context, run_root)
    payload = {
        "schema_version": 1,
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "environment": _environment(context),
        "evaluator": evaluator,
        "evaluator_parity": comparison,
        "optimizer": optimizer,
    }
    payload["status"] = "PASS" if comparison["status"] == "PASS" and optimizer["status"] == "PASS" else "BLOCKED"
    output.write_text(json.dumps(_clean(payload), indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture_parser = sub.add_parser("capture", help="capture sanitized Windows evaluator and smoke baseline")
    capture_parser.add_argument("--output", type=Path, required=True)
    capture_parser.add_argument("--run-root", type=Path, required=True)
    qualify_parser = sub.add_parser("qualify", help="compare evaluator parity and run WSL optimizer/checkpoint smoke")
    qualify_parser.add_argument("--reference", type=Path, required=True)
    qualify_parser.add_argument("--output", type=Path, required=True)
    qualify_parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "capture":
            capture(args.output.resolve(), args.run_root.resolve())
        else:
            qualify(args.reference.resolve(), args.output.resolve(), args.run_root.resolve())
    except Exception as exc:
        print(f"WSL qualification smoke failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1
    print(json.dumps({"status": "PASS" if args.command == "capture" else json.loads(args.output.read_text(encoding="utf-8"))["status"], "output": str(args.output.resolve())}, ensure_ascii=False))
    return 0 if args.command == "capture" or json.loads(args.output.read_text(encoding="utf-8"))["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
