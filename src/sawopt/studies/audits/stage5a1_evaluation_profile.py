"""Read-only Stage 4C finalist profiling for the Stage 5A-1 audit."""
from __future__ import annotations

import argparse
import contextlib
import csv
from dataclasses import asdict
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

import numpy as np
import scipy

from ...core.hybrid import compose_stage4a_y, resonator_admittance
from ...core.metrics import measure
from ...physics.network import evaluate
from ...problem.dms_topologies import T1, simulate_topology
from ...problem.hybrid import hybrid_geometry
from ...studies.hybrid import stage4a_evaluate
from ...studies.hybrid_stage4c import (
    COMMON_GRID_ID,
    COMMON_GRID_SHA256,
    SEARCH_GRID_SHA256,
    load_stage4c_context,
)


ROOT = Path(__file__).resolve().parents[4]
REVIEW_RELATIVE = Path("reports/experiment_reviews/stage4c/20261006_124153_ed50ba")
DEFAULT_CONFIG = "configs/studies/hybrid_stage4c_confirmatory.yaml"
DEFAULT_OUTPUT = Path("reports/benchmarks/stage5a1_evaluation_profile")
CELL_KEYS = tuple((topology, seed) for topology in ("P_D", "D_P")
                  for seed in (20261007, 20261009, 20261011))
TIMING_FIELDS = (
    "A_s", "B_s", "C_s", "D_s", "E_s", "F_s", "sum_A_to_F_s",
    "G_s", "G_stage4a_call_s", "G_decode_s",
)
CSV_FIELDS = (
    "topology", "seed", "grid", "frequency_count", "grid_identity",
    "repetition", "measurement_order", "stage4a_status",
    "candidate_evidence_path", "candidate_evidence_sha256", *TIMING_FIELDS,
)
THREAD_ENVIRONMENT = (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS",
)


def summarize_seconds(samples: Sequence[float]) -> dict[str, float | int]:
    values = np.asarray(samples, dtype=float)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("timing samples must be a non-empty one-dimensional sequence")
    if not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError("timing samples must be finite non-negative seconds")
    median = float(np.median(values))
    return {
        "n": int(values.size),
        "median_s": median,
        "min_s": float(values.min()),
        "max_s": float(values.max()),
        "mad_s": float(np.median(np.abs(values - median))),
    }


def summarize_samples(samples: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not samples:
        raise ValueError("at least one timing sample is required")
    groups: dict[tuple[str, int, str], list[Mapping[str, Any]]] = {}
    for row in samples:
        key = (str(row["topology"]), int(row["seed"]), str(row["grid"]))
        groups.setdefault(key, []).append(row)
    summaries = []
    for (topology, seed, grid), rows in sorted(groups.items()):
        for stage in TIMING_FIELDS:
            summaries.append({
                "topology": topology,
                "seed": seed,
                "grid": grid,
                "stage": stage,
                **summarize_seconds([float(row[stage]) for row in rows]),
            })
    return summaries


def write_profile_outputs(
    output_dir: str | Path,
    metadata: Mapping[str, Any],
    samples: Sequence[Mapping[str, Any]],
    parity_results: Sequence[Mapping[str, Any]],
) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    csv_path = output_dir / "measurements.csv"
    json_path = output_dir / "profile_summary.json"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=CSV_FIELDS, extrasaction="raise", lineterminator="\n",
        )
        writer.writeheader()
        for row in samples:
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})
    summary = {
        "schema_version": 1,
        **metadata,
        "sample_count": len(samples),
        "parity_results": list(parity_results),
        "summaries": summarize_samples(samples),
    }
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return csv_path, json_path


def _allclose(name: str, left: Any, right: Any, *, rtol: float, atol: float) -> float:
    left_array, right_array = np.asarray(left), np.asarray(right)
    np.testing.assert_allclose(
        left_array, right_array, rtol=rtol, atol=atol,
        err_msg=f"Stage 5A-1 profile parity failure: {name}",
    )
    difference = np.abs(left_array - right_array)
    return float(np.max(difference, initial=0.0))


def assert_profile_equivalence(
    decomposed: Mapping[str, Any],
    reference: Mapping[str, Any],
    *, rtol: float, atol: float,
) -> dict[str, float]:
    differences: dict[str, float] = {}
    differences["y_parameters"] = _allclose(
        "Y parameters", decomposed["y_parameters"], reference["y_parameters"],
        rtol=rtol, atol=atol,
    )
    for field in ("s", "gt", "il", "vswr"):
        differences[f"network.{field}"] = _allclose(
            f"network {field}", decomposed["network"][field], reference["network"][field],
            rtol=rtol, atol=atol,
        )

    left, right = decomposed["record"], reference["record"]
    for field in ("evaluation_status", "feasible"):
        if left.get(field) != right.get(field):
            raise AssertionError(
                f"Stage 5A-1 profile parity failure: {field}: "
                f"{left.get(field)!r} != {right.get(field)!r}"
            )
    for field in ("max_violation", "sum_violation", "objective", "geometry_max_violation"):
        differences[field] = _allclose(
            field, left[field], right[field], rtol=rtol, atol=atol,
        )
    for category in ("metrics", "violations", "geometry_violations"):
        if set(left[category]) != set(right[category]):
            raise AssertionError(f"Stage 5A-1 profile parity failure: {category} keys differ")
        for key in sorted(left[category]):
            differences[f"{category}.{key}"] = _allclose(
                f"{category}.{key}", left[category][key], right[category][key],
                rtol=rtol, atol=atol,
            )
    return differences


def assert_saved_finalist_equivalence(
    actual: Mapping[str, Any], saved: Mapping[str, Any], *, rtol: float, atol: float,
) -> dict[str, float]:
    differences: dict[str, float] = {}
    for field in ("evaluation_status", "feasible"):
        if actual.get(field) != saved.get(field):
            raise AssertionError(
                f"Stage 4C finalist mismatch: {field}: "
                f"{actual.get(field)!r} != {saved.get(field)!r}"
            )
    for field in ("max_violation", "sum_violation", "objective"):
        differences[field] = _allclose(
            f"saved finalist {field}", actual[field], saved[field], rtol=rtol, atol=atol,
        )
    for category in ("metrics", "violations"):
        if set(actual[category]) != set(saved[category]):
            raise AssertionError(f"Stage 4C finalist mismatch: {category} keys differ")
        for key in sorted(actual[category]):
            differences[f"{category}.{key}"] = _allclose(
                f"saved finalist {category}.{key}", actual[category][key],
                saved[category][key], rtol=rtol, atol=atol,
            )
    return differences


def _candidate(vector: Sequence[float], topology: str, context: Mapping[str, Any]):
    reflector_count = int(context["cfg"]["dms_topology"]["t1_reflector_electrodes"])
    return context["spaces"][topology].decode(vector, reflector_electrodes=reflector_count)


def _geometry_violations(layout: Mapping[str, Any]) -> dict[str, float]:
    return {
        **{f"dms_{key}": float(value)
           for key, value in layout["dms"]["violations"].items()},
        **{str(key): float(value) for key, value in layout["resonator_violations"].items()},
        **{f"combined_{key}": float(value)
           for key, value in layout["combined"]["violations"].items()},
    }


def _record_from_measure(candidate: Any, layout: Mapping[str, Any], raw: Mapping[str, Any],
                         dms_diagnostics: Mapping[str, Any], rs: float, rl: float) -> dict[str, Any]:
    violations = {str(key): float(value) for key, value in raw["violations"].items()
                  if key != "geometry"}
    metrics = dict(raw["metrics"])
    for key in ("length_um", "width_um", "electrodes"):
        metrics.pop(key, None)
    maximum = max(violations.values(), default=math.inf)
    return {
        "evaluation_status": "PHYSICS_EVALUATED",
        "geometry_valid": True,
        "geometry_dimensions": layout,
        "geometry_violations": _geometry_violations(layout),
        "geometry_max_violation": 0.0,
        "metrics": metrics,
        "violations": violations,
        "feasible": maximum <= 1e-10,
        "max_violation": maximum,
        "sum_violation": sum(violations.values()),
        "objective": float(raw["objective"]),
        "dms_design": asdict(candidate.dms_design),
        "resonator_designs": [asdict(item) for item in candidate.resonator_designs],
        "candidate_vector": list(candidate.vector),
        "topology": candidate.topology,
        "source_impedance_ohm": float(rs),
        "load_impedance_ohm": float(rl),
        "dms_diagnostics": dict(dms_diagnostics),
    }


def profile_decomposed_evaluation(
    vector: Sequence[float], topology: str, context: Mapping[str, Any], frequencies: Sequence[float],
) -> dict[str, Any]:
    """Run one A-F decomposition and retain arrays needed for parity checks."""
    cfg = context["cfg"]
    frequencies = np.asarray(frequencies, dtype=float)
    stage_seconds: dict[str, float] = {}

    started = time.perf_counter()
    candidate = _candidate(vector, topology, context)
    layout = hybrid_geometry(candidate, cfg)
    if layout["max_violation"] > 0.0:
        raise ValueError(f"selected finalist fails geometry validation: {topology}")
    stage_seconds["A_s"] = time.perf_counter() - started

    started = time.perf_counter()
    dms_simulation = simulate_topology(candidate.dms_design, context["provider"], frequencies, T1)
    stage_seconds["B_s"] = time.perf_counter() - started

    started = time.perf_counter()
    resonator_ys = [resonator_admittance(item, context["provider"], frequencies)
                    for item in candidate.resonator_designs]
    stage_seconds["C_s"] = time.perf_counter() - started

    started = time.perf_counter()
    y_parameters = compose_stage4a_y(
        dms_simulation.y_parameters, topology, resonator_ys,
    )
    stage_seconds["D_s"] = time.perf_counter() - started

    started = time.perf_counter()
    network = evaluate(
        y_parameters, context["source_impedance_ohm"], context["load_impedance_ohm"],
    )
    if not np.isfinite(network["gt"]).all() or network["gt"].max(initial=0.0) > 1.0 + 1e-7:
        raise ValueError("non-finite or nonpassive transducer power gain")
    stage_seconds["E_s"] = time.perf_counter() - started

    started = time.perf_counter()
    raw = measure(frequencies, network, candidate.dms_design, cfg)
    record = _record_from_measure(
        candidate, layout, raw, dms_simulation.diagnostics,
        context["source_impedance_ohm"], context["load_impedance_ohm"],
    )
    finite_metrics = [float(value) for metric in record["metrics"].values()
                      for value in (metric if isinstance(metric, (list, tuple, np.ndarray))
                                    else [metric])]
    if (not finite_metrics or not np.isfinite(finite_metrics).all()
            or not np.isfinite(list(record["violations"].values())).all()
            or not math.isfinite(record["objective"])):
        raise ValueError("non-finite or incomplete filter metrics")
    stage_seconds["F_s"] = time.perf_counter() - started
    stage_seconds["sum_A_to_F_s"] = sum(stage_seconds[f"{stage}_s"] for stage in "ABCDEF")
    return {
        "candidate": candidate,
        "layout": layout,
        "dms_simulation": dms_simulation,
        "resonator_y_parameters": resonator_ys,
        "y_parameters": y_parameters,
        "network": network,
        "record": record,
        "stage_seconds": stage_seconds,
    }


def capture_stage4a_reference(
    vector: Sequence[float], topology: str, context: Mapping[str, Any], frequencies: Sequence[float],
) -> dict[str, Any]:
    """Run the unmodified Stage 4A evaluator while capturing its Y/network outputs."""
    from unittest.mock import patch
    from ...physics import network as network_module

    candidate = _candidate(vector, topology, context)
    captured: dict[str, Any] = {}
    original_evaluate = network_module.evaluate

    def capture(y_parameters, rs, rl):
        result = original_evaluate(y_parameters, rs, rl)
        captured["y_parameters"] = np.array(y_parameters, copy=True)
        captured["network"] = result
        return result

    with patch.object(network_module, "evaluate", side_effect=capture):
        record = stage4a_evaluate(
            candidate, context["provider"], context["cfg"], frequencies,
            context["source_impedance_ohm"], context["load_impedance_ohm"],
        )
    if "network" not in captured:
        raise AssertionError("normal Stage 4A evaluation did not reach network evaluation")
    return {**captured, "record": record}


def _timed_end_to_end(
    vector: Sequence[float], topology: str, context: Mapping[str, Any], frequencies: Sequence[float],
) -> dict[str, Any]:
    started = time.perf_counter()
    decode_started = time.perf_counter()
    candidate = _candidate(vector, topology, context)
    decode_seconds = time.perf_counter() - decode_started
    evaluation_started = time.perf_counter()
    record = stage4a_evaluate(
        candidate, context["provider"], context["cfg"], frequencies,
        context["source_impedance_ohm"], context["load_impedance_ohm"],
    )
    evaluator_seconds = time.perf_counter() - evaluation_started
    return {
        "record": record,
        "stage_seconds": {
            "G_s": time.perf_counter() - started,
            "G_stage4a_call_s": evaluator_seconds,
            "G_decode_s": decode_seconds,
        },
    }


def _validate_grids(context: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    search = np.asarray(context["search_frequencies"], dtype="<f8")
    common = np.asarray(context["common_frequencies"], dtype="<f8")
    search_hash = hashlib.sha256(search.tobytes()).hexdigest()
    common_array_hash = hashlib.sha256(common.tobytes()).hexdigest()
    common_metadata_hash = context["grid_metadata"].get("sha256")
    contract = context["contract"]
    actual = {
        "search": {
            "frequencies": search,
            "frequency_count": int(search.size),
            "sha256": search_hash,
        },
        "common": {
            "frequencies": common,
            "frequency_count": int(common.size),
            "grid_id": context["common_grid_id"],
            "array_sha256": common_array_hash,
            "sha256": common_metadata_hash,
        },
    }
    if (search.size != 1001 or search_hash != SEARCH_GRID_SHA256
            or contract.get("search_frequency_sha256") != SEARCH_GRID_SHA256):
        raise ValueError("Stage 4C search-grid identity mismatch")
    if (common.size != 9113 or context["common_grid_id"] != COMMON_GRID_ID
            or common_array_hash != COMMON_GRID_ID
            or common_metadata_hash != COMMON_GRID_SHA256
            or contract.get("common_validation_grid_id") != COMMON_GRID_ID
            or contract.get("common_validation_grid_sha256") != COMMON_GRID_SHA256):
        raise ValueError("Stage 4C common-validation-grid identity mismatch")
    if (context["source_impedance_ohm"] != 50.0
            or context["load_impedance_ohm"] != 50.0):
        raise ValueError("Stage 4C profiling requires 50/50 ohm terminations")
    return {key: {name: value for name, value in item.items() if name != "frequencies"}
            for key, item in actual.items()}


def _load_cases(context: Mapping[str, Any], review_root: Path) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, str]]:
    read_seconds: dict[str, float] = {}
    input_hashes: dict[str, str] = {}
    cases = []
    for topology, seed in CELL_KEYS:
        relative = Path("cells") / topology / f"{seed}_result.json"
        path = review_root / relative
        started = time.perf_counter()
        payload_bytes = path.read_bytes()
        payload = json.loads(payload_bytes)
        read_seconds[relative.as_posix()] = time.perf_counter() - started
        input_hashes[relative.as_posix()] = hashlib.sha256(payload_bytes).hexdigest()
        if payload.get("topology") != topology or int(payload.get("seed", -1)) != seed:
            raise ValueError(f"Stage 4C evidence identity mismatch: {relative}")
        if payload.get("common_validation_grid_id") != context["common_grid_id"]:
            raise ValueError(f"Stage 4C common-grid identity mismatch: {relative}")
        finalist = payload.get("common_grid_selected_finalist")
        if not isinstance(finalist, Mapping) or finalist.get("evaluation_status") != "PHYSICS_EVALUATED":
            raise ValueError(f"Stage 4C selected finalist is absent or invalid: {relative}")
        if finalist.get("topology") != topology:
            raise ValueError(f"selected finalist topology mismatch: {relative}")
        vector = finalist.get("candidate_vector")
        if not isinstance(vector, list):
            raise ValueError(f"selected finalist candidate vector is absent: {relative}")
        candidate = _candidate(vector, topology, context)
        if candidate.dms_design.__dict__ != finalist.get("dms_design"):
            raise ValueError(f"saved DMS design does not match decoded candidate: {relative}")
        if [item.__dict__ for item in candidate.resonator_designs] != finalist.get("resonator_designs"):
            raise ValueError(f"saved resonator designs do not match decoded candidate: {relative}")
        if not np.array_equal(np.asarray(candidate.vector), np.asarray(vector, dtype=float)):
            raise ValueError(f"selected finalist vector is not canonical: {relative}")
        cases.append({
            "topology": topology,
            "seed": seed,
            "vector": vector,
            "candidate_evidence_path": relative.as_posix(),
            "candidate_evidence_sha256": input_hashes[relative.as_posix()],
            "stage4c_execution_source_sha": payload.get("source_commit_sha"),
            "saved_finalist": finalist,
        })
    return cases, read_seconds, input_hashes


def _cpu_model() -> str | None:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name\t:"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None


def _environment() -> dict[str, Any]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        np.show_config()
    try:
        from threadpoolctl import threadpool_info
        threadpools = threadpool_info()
    except ImportError:
        threadpools = None
    return {
        "os": platform.platform(),
        "machine": platform.machine(),
        "cpu_model": _cpu_model(),
        "logical_cpu_count": os.cpu_count(),
        "affinity_cpu_count": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "process_thread_count": len(os.listdir("/proc/self/task")) if Path("/proc/self/task").exists() else None,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "numpy_blas_configuration": stream.getvalue(),
        "threadpools": threadpools,
        "thread_environment": {name: os.environ.get(name) for name in THREAD_ENVIRONMENT},
    }


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def run_profile(
    *, config: str = DEFAULT_CONFIG, output_dir: str | Path = DEFAULT_OUTPUT,
    repeats: int = 7, warmups: int = 2, measurement_order_seed: int = 20261009,
    pilot: bool = False,
) -> tuple[Path, Path]:
    if pilot:
        repeats, warmups = 1, 1
    elif repeats < 7:
        raise ValueError("full profiling requires at least seven timed repetitions")
    if warmups < 1:
        raise ValueError("at least one untimed warm-up is required")
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite benchmark output: {output_dir}")

    setup_started = time.perf_counter()
    context = load_stage4c_context(config)
    context_load_seconds = time.perf_counter() - setup_started
    grids = _validate_grids(context)
    review_root = ROOT / REVIEW_RELATIVE
    case_load_started = time.perf_counter()
    cases, evidence_read_seconds, input_hashes = _load_cases(context, review_root)
    evidence_load_seconds = time.perf_counter() - case_load_started
    if pilot:
        cases = cases[:1]

    conditions = [
        (case, grid_name, np.asarray(context["search_frequencies" if grid_name == "search"
                                              else "common_frequencies"], dtype=float))
        for case in cases for grid_name in ("search", "common")
    ]
    parity_results = []
    parity_started = time.perf_counter()
    for case, grid_name, frequencies in conditions:
        decomposed = profile_decomposed_evaluation(
            case["vector"], case["topology"], context, frequencies,
        )
        reference = capture_stage4a_reference(
            case["vector"], case["topology"], context, frequencies,
        )
        tolerances = context["cfg"]["hybrid"]["parity"]
        differences = assert_profile_equivalence(
            decomposed, reference,
            rtol=float(tolerances["rtol"]), atol=float(tolerances["atol"]),
        )
        saved_finalist_differences = None
        if grid_name == "common":
            saved_finalist_differences = assert_saved_finalist_equivalence(
                reference["record"], case["saved_finalist"],
                rtol=float(tolerances["rtol"]), atol=float(tolerances["atol"]),
            )
        parity_results.append({
            "topology": case["topology"], "seed": case["seed"],
            "grid": grid_name, "frequency_count": len(frequencies),
            "status": "PASS", "rtol": float(tolerances["rtol"]),
            "atol": float(tolerances["atol"]),
            "maximum_absolute_difference": max(differences.values(), default=0.0),
            "maximum_absolute_differences": differences,
            "saved_finalist_maximum_absolute_difference": (
                max(saved_finalist_differences.values(), default=0.0)
                if saved_finalist_differences is not None else None
            ),
        })
    parity_seconds = time.perf_counter() - parity_started

    rng = random.Random(measurement_order_seed)
    warmup_order = list(conditions)
    rng.shuffle(warmup_order)
    for case, _grid_name, frequencies in warmup_order:
        for _ in range(warmups):
            profile_decomposed_evaluation(case["vector"], case["topology"], context, frequencies)
            _timed_end_to_end(case["vector"], case["topology"], context, frequencies)

    samples = []
    for repetition in range(1, repeats + 1):
        order = list(conditions)
        rng.shuffle(order)
        for case, grid_name, frequencies in order:
            decomposed_first = bool(rng.getrandbits(1))
            if decomposed_first:
                decomposed = profile_decomposed_evaluation(
                    case["vector"], case["topology"], context, frequencies,
                )
                end_to_end = _timed_end_to_end(
                    case["vector"], case["topology"], context, frequencies,
                )
                measurement_order = "A_to_F_then_G"
            else:
                end_to_end = _timed_end_to_end(
                    case["vector"], case["topology"], context, frequencies,
                )
                decomposed = profile_decomposed_evaluation(
                    case["vector"], case["topology"], context, frequencies,
                )
                measurement_order = "G_then_A_to_F"
            row = {
                "topology": case["topology"], "seed": case["seed"],
                "grid": grid_name, "frequency_count": len(frequencies),
                "grid_identity": grids[grid_name].get("grid_id", grids[grid_name]["sha256"]),
                "repetition": repetition,
                "measurement_order": measurement_order,
                "stage4a_status": end_to_end["record"]["evaluation_status"],
                "candidate_evidence_path": case["candidate_evidence_path"],
                "candidate_evidence_sha256": case["candidate_evidence_sha256"],
                **decomposed["stage_seconds"],
                **end_to_end["stage_seconds"],
            }
            if row["stage4a_status"] != "PHYSICS_EVALUATED":
                raise RuntimeError(
                    f"normal Stage 4A path failed for {case['topology']} seed {case['seed']}"
                )
            samples.append(row)

    try:
        import threadpoolctl  # noqa: F401
        threadpoolctl_version = threadpoolctl.__version__
    except ImportError:
        threadpoolctl_version = None
    metadata = {
        "status": "PILOT" if pilot else "COMPLETE",
        "benchmark_commit_sha": _git_output("rev-parse", "HEAD"),
        "benchmark_tree_dirty": bool(_git_output("status", "--porcelain")),
        "benchmark_utility_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "stage4c_run_id": "20261006_124153_ed50ba",
        "stage4c_execution_source_sha_by_cell": {
            f"{case['topology']}/{case['seed']}": case["stage4c_execution_source_sha"]
            for case in cases
        },
        "config": config,
        "review_evidence_root": REVIEW_RELATIVE.as_posix(),
        "candidate_input_files": input_hashes,
        "grid_identities": grids,
        "source_impedance_ohm": context["source_impedance_ohm"],
        "load_impedance_ohm": context["load_impedance_ohm"],
        "material_profile": context["profile_metadata"],
        "measurement_order_seed": measurement_order_seed,
        "timed_repetitions_per_condition": repeats,
        "warmups_per_condition_and_method": warmups,
        "context_load_seconds": context_load_seconds,
        "candidate_evidence_read_seconds": evidence_read_seconds,
        "candidate_evidence_total_read_seconds": evidence_load_seconds,
        "parity_validation_seconds": parity_seconds,
        "input_load_time_separate_from_evaluation": True,
        "caching": {
            "optimizer_cache_used": False,
            "candidate_result_cache_used": False,
            "same_provider_reused": True,
            "threadpoolctl_version": threadpoolctl_version,
        },
        "environment": _environment(),
        "command": sys.argv,
        "timing_fields": list(TIMING_FIELDS),
    }
    return write_profile_outputs(output_dir, metadata, samples, parity_results)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--measurement-order-seed", type=int, default=20261009)
    parser.add_argument(
        "--pilot", action="store_true",
        help="profile only P_D/20261007 on both grids with one warm-up and one repeat",
    )
    args = parser.parse_args(argv)
    if args.pilot and args.output_dir == DEFAULT_OUTPUT:
        parser.error("--pilot requires an explicit scratch --output-dir")
    csv_path, json_path = run_profile(
        config=args.config, output_dir=args.output_dir,
        repeats=args.repeats, warmups=args.warmups,
        measurement_order_seed=args.measurement_order_seed, pilot=args.pilot,
    )
    print(json.dumps({"measurements_csv": str(csv_path), "profile_summary_json": str(json_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
