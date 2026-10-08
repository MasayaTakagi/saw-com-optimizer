"""Benchmark Stage 5A-1 evaluations under isolated BLAS thread settings."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[4]
PROFILE_MODULE = "sawopt.studies.audits.stage5a1_evaluation_profile"
PROFILE_TOOL = ROOT / "src/sawopt/studies/audits/stage5a1_evaluation_profile.py"
DEFAULT_CONFIG = "configs/studies/hybrid_stage4c_confirmatory.yaml"
REVIEW_RELATIVE = Path("reports/experiment_reviews/stage4c/20261006_124153_ed50ba")
BLAS_SETTINGS: dict[str, str | None] = {
    "single": "1", "dual": "2", "quad": "4", "default": None,
}
THREAD_VARIABLES = (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS",
)
PROFILE_STAGES = ("B_s", "C_s", "D_s", "E_s", "F_s", "G_stage4a_call_s")
CELL_IDENTITIES = tuple(
    (topology, seed)
    for topology in ("P_D", "D_P")
    for seed in (20261007, 20261009, 20261011)
)
GRID_IDENTITIES = {
    "search": {
        "frequency_count": 1001,
        "sha256": "212dd2b0b71ddeffb7a8865937d132ee596870f25c989ac7d90c5dab6fd7faa0",
    },
    "common": {
        "frequency_count": 9113,
        "grid_id": "2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f",
    },
}
WORKER_COUNTS = (1, 2, 4)


def build_child_environment(
    setting: str, parent_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    if setting not in BLAS_SETTINGS:
        raise ValueError(f"unknown BLAS setting: {setting}")
    environment = dict(os.environ if parent_environment is None else parent_environment)
    requested = BLAS_SETTINGS[setting]
    if requested is None:
        environment.pop("OPENBLAS_NUM_THREADS", None)
    else:
        environment["OPENBLAS_NUM_THREADS"] = requested
    return environment


def validate_blas_pools(
    setting: str, environment: Mapping[str, str], pools: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    if setting not in BLAS_SETTINGS:
        raise ValueError(f"unknown BLAS setting: {setting}")
    requested = BLAS_SETTINGS[setting]
    if requested is None:
        if "OPENBLAS_NUM_THREADS" in environment:
            raise ValueError("OPENBLAS_NUM_THREADS must be unset for Default")
    elif environment.get("OPENBLAS_NUM_THREADS") != requested:
        raise ValueError("child OPENBLAS_NUM_THREADS does not match requested setting")
    if not pools:
        raise ValueError("threadpoolctl reported no active BLAS pools")
    blas_pools = [pool for pool in pools if pool.get("user_api") == "blas"]
    if not blas_pools:
        raise ValueError("threadpoolctl reported no active BLAS pools")
    effective: list[int] = []
    libraries = []
    for pool in blas_pools:
        try:
            count = int(pool["num_threads"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("an active BLAS pool has no valid thread count") from exc
        if count < 1:
            raise ValueError("an active BLAS pool has an invalid thread count")
        effective.append(count)
        libraries.append({
            key: pool.get(key)
            for key in ("internal_api", "prefix", "filepath", "version", "architecture")
            if pool.get(key) is not None
        } | {"num_threads": count})
    if requested is not None and any(count != int(requested) for count in effective):
        raise ValueError(
            f"an effective BLAS thread count {effective} does not match requested {requested}"
        )
    conflicts = {
        name: environment[name]
        for name in THREAD_VARIABLES
        if name != "OPENBLAS_NUM_THREADS" and environment.get(name)
    }
    return {
        "valid": True,
        "setting": setting,
        "requested_openblas_threads": requested,
        "openblas_environment_unset": "OPENBLAS_NUM_THREADS" not in environment,
        "active_blas_libraries": libraries,
        "effective_blas_threads": effective,
        "potential_conflicts": conflicts,
    }


def shuffled_single_order(seed: int) -> list[str]:
    settings = list(BLAS_SETTINGS)
    random.Random(seed).shuffle(settings)
    return settings


def shuffled_parallel_order(
    seed: int, repetitions: int, settings: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    if repetitions < 1:
        raise ValueError("at least one parallel repetition is required")
    settings = tuple(BLAS_SETTINGS) if settings is None else tuple(settings)
    if not settings or set(settings) - set(BLAS_SETTINGS):
        raise ValueError("parallel settings must be a non-empty subset of BLAS settings")
    if len(set(settings)) != len(settings):
        raise ValueError("parallel settings may not be repeated")
    rng = random.Random(seed)
    conditions = [(setting, workers) for setting in settings for workers in WORKER_COUNTS]
    ordered = []
    for repetition in range(1, repetitions + 1):
        block = list(conditions)
        rng.shuffle(block)
        ordered.extend(
            {"run_order": len(ordered) + 1, "setting": setting,
             "workers": workers, "repetition": repetition}
            for setting, workers in block
        )
    return ordered


def validate_parallel_settings(settings: Sequence[str]) -> tuple[str, ...]:
    selected = tuple(settings)
    if (not selected or set(selected) - set(BLAS_SETTINGS)
            or len(set(selected)) != len(selected)):
        raise ValueError("parallel settings must be a unique non-empty subset of BLAS settings")
    if not {"single", "default"}.issubset(selected):
        raise ValueError("parallel settings must include Single and Default")
    return selected


def estimate_parallel_matrix_seconds(
    pilot: Mapping[str, Any], *, jobs_per_batch: int,
    repetitions: int, settings: Sequence[str], safety_factor: float = 1.25,
) -> float:
    """Scale the pilot evaluation window while charging process setup once per batch."""
    if jobs_per_batch < 1 or repetitions < 1 or safety_factor < 1:
        raise ValueError("invalid parallel matrix projection inputs")
    setup_seconds = float(pilot["setup_wall_s"])
    evaluation_seconds = float(pilot["evaluation_window_wall_s"])
    if not math.isfinite(setup_seconds) or not math.isfinite(evaluation_seconds):
        raise ValueError("parallel pilot times must be finite")
    if setup_seconds < 0 or evaluation_seconds <= 0:
        raise ValueError("parallel pilot times must be non-negative with a positive evaluation window")
    return (setup_seconds + evaluation_seconds * jobs_per_batch / 24.0) * (
        repetitions * len(settings) * len(WORKER_COUNTS) * safety_factor
    )


def validate_parallel_job_results(
    worker_results: Sequence[Mapping[str, Any]], *, rtol: float, atol: float,
) -> float:
    references: dict[str, Mapping[str, Any]] = {}
    maximum_difference = 0.0
    for worker in worker_results:
        for result in worker.get("jobs", []):
            candidate = str(result["candidate"])
            reference = references.setdefault(candidate, result)
            if bool(result["feasible"]) != bool(reference["feasible"]):
                raise ValueError(f"parallel feasibility mismatch for {candidate}")
            for field in ("objective", "max_violation", "sum_violation"):
                actual_value, expected_value = float(result[field]), float(reference[field])
                if not math.isfinite(actual_value) or not math.isfinite(expected_value):
                    raise ValueError(f"parallel {field} is non-finite for {candidate}")
                difference = abs(actual_value - expected_value)
                maximum_difference = max(maximum_difference, difference)
                if not math.isclose(actual_value, expected_value, rel_tol=rtol, abs_tol=atol):
                    raise ValueError(f"parallel {field} mismatch for {candidate}")
    if set(references) != {f"{topology}/{seed}" for topology, seed in CELL_IDENTITIES}:
        raise ValueError("parallel jobs did not cover all six saved finalists")
    return maximum_difference


def blas_pool_signature(pools: Sequence[Mapping[str, Any]]) -> tuple[tuple[Any, ...], ...]:
    """Canonicalize threadpoolctl results whose enumeration order can vary by process."""
    return tuple(sorted(
        (
            str(pool.get("filepath", "")), str(pool.get("internal_api", "")),
            str(pool.get("version", "")), int(pool["num_threads"]),
        )
        for pool in pools
    ))


def validate_reusable_single_results(
    summary: Mapping[str, Any],
    sample_rows: Sequence[Mapping[str, Any]],
    single_summary_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Validate completed serial profiles from an earlier committed runner."""
    if summary.get("status") not in ("COMPLETE", "PARTIAL"):
        raise ValueError("reusable serial benchmark output has no completed run")
    if summary.get("runner_tree_dirty") is not False or not summary.get("runner_commit_sha"):
        raise ValueError("reusable serial benchmark source identity is invalid")
    if not summary.get("runner_sha256") or not summary.get("base_main_commit_sha"):
        raise ValueError("reusable serial benchmark provenance is incomplete")
    records = list(summary.get("single_process_profiles", []))
    if len(records) != len(BLAS_SETTINGS) or {row.get("setting") for row in records} != set(BLAS_SETTINGS):
        raise ValueError("reusable serial results do not contain all four BLAS settings")
    expected_candidates = {
        f"cells/{topology}/{seed}_result.json" for topology, seed in CELL_IDENTITIES
    }
    expected_candidate_hashes = None
    expected_grids = None
    profile_commits = set()
    profile_hashes = set()
    for record in records:
        setting = record["setting"]
        if record.get("sample_count") != 84 or len(record.get("parity_results", [])) != 12:
            raise ValueError(f"reusable {setting} profile is incomplete")
        if any(result.get("status") != "PASS" for result in record["parity_results"]):
            raise ValueError(f"reusable {setting} parity did not pass")
        environment = record.get("environment", {})
        thread_environment = {
            key: value for key, value in environment.get("thread_environment", {}).items()
            if value is not None
        }
        pool_evidence = validate_blas_pools(
            setting, thread_environment, environment.get("threadpools"),
        )
        if pool_evidence.get("valid") is not True:
            raise ValueError(f"reusable {setting} effective BLAS setting is invalid")
        if record.get("blas_validation", {}).get("valid") is not True:
            raise ValueError(f"reusable {setting} BLAS evidence is invalid")
        current_candidates = record.get("candidate_input_files")
        current_grids = record.get("grid_identities")
        if set(current_candidates or {}) != expected_candidates:
            raise ValueError("reusable serial profiles do not contain the six fixed candidates")
        if any(not current_candidates.get(candidate) for candidate in expected_candidates):
            raise ValueError("reusable serial profile has a missing candidate hash")
        if expected_candidate_hashes is None:
            expected_candidate_hashes, expected_grids = current_candidates, current_grids
        elif current_candidates != expected_candidate_hashes or current_grids != expected_grids:
            raise ValueError("reusable serial profiles do not share candidate/grid identities")
        for grid, expected in GRID_IDENTITIES.items():
            actual = (current_grids or {}).get(grid, {})
            if any(actual.get(key) != value for key, value in expected.items()):
                raise ValueError(f"reusable {setting} profile has the wrong {grid} grid")
        profile_commits.add(record.get("profile_commit_sha"))
        profile_hashes.add(record.get("profile_tool_sha256"))
    if len(profile_commits) != 1 or None in profile_commits or len(profile_hashes) != 1 or None in profile_hashes:
        raise ValueError("reusable serial profiles have inconsistent source identities")

    setting_counts = {setting: 0 for setting in BLAS_SETTINGS}
    sample_groups: dict[tuple[str, str, int, str], int] = {}
    sample_repetitions: dict[tuple[str, str, int, str], set[int]] = {}
    for row in sample_rows:
        setting = str(row.get("setting"))
        if setting not in setting_counts or row.get("stage4a_status") != "PHYSICS_EVALUATED":
            raise ValueError("reusable serial sample has an invalid setting or evaluation status")
        setting_counts[setting] += 1
        topology, seed, grid = str(row.get("topology")), int(row.get("seed", -1)), str(row.get("grid"))
        key = (setting, topology, seed, grid)
        expected_grid = GRID_IDENTITIES.get(grid)
        if (topology, seed) not in CELL_IDENTITIES or expected_grid is None:
            raise ValueError("reusable serial sample has an unknown candidate or grid")
        identity = expected_grid.get("sha256", expected_grid.get("grid_id"))
        if (int(row.get("frequency_count", -1)) != expected_grid["frequency_count"]
                or row.get("grid_identity") != identity):
            raise ValueError("reusable serial sample has the wrong grid identity")
        candidate_path = f"cells/{topology}/{seed}_result.json"
        if row.get("candidate_evidence_sha256") != expected_candidate_hashes.get(candidate_path):
            raise ValueError("reusable serial sample candidate hash differs from profile evidence")
        sample_groups[key] = sample_groups.get(key, 0) + 1
        sample_repetitions.setdefault(key, set()).add(int(row.get("repetition", -1)))
    if any(count != 84 for count in setting_counts.values()):
        raise ValueError("reusable serial sample rows are incomplete")
    expected_sample_groups = {
        (setting, topology, seed, grid)
        for setting in BLAS_SETTINGS
        for topology, seed in CELL_IDENTITIES
        for grid in ("search", "common")
    }
    if (set(sample_groups) != expected_sample_groups
            or any(count != 7 for count in sample_groups.values())
            or any(repetitions != set(range(1, 8)) for repetitions in sample_repetitions.values())):
        raise ValueError("reusable serial candidate/grid repetitions are incomplete")
    if len(single_summary_rows) != len(BLAS_SETTINGS) * len(PROFILE_STAGES) * 2:
        raise ValueError("reusable serial summary rows are incomplete")
    summary_conditions = set()
    for row in single_summary_rows:
        setting = str(row.get("setting"))
        if (int(row.get("candidate_count", -1)) != 6
                or int(row.get("samples_per_candidate", -1)) != 7
                or setting not in BLAS_SETTINGS
                or row.get("grid") not in GRID_IDENTITIES or row.get("stage") not in PROFILE_STAGES):
            raise ValueError("reusable serial summary has an incomplete condition")
        summary_conditions.add((setting, row["grid"], row["stage"]))
    expected_summary_conditions = {
        (setting, grid, stage)
        for setting in BLAS_SETTINGS for grid in GRID_IDENTITIES for stage in PROFILE_STAGES
    }
    if summary_conditions != expected_summary_conditions:
        raise ValueError("reusable serial summary conditions are incomplete or duplicated")
    return records


def _profile_thread_environment(summary: Mapping[str, Any]) -> Mapping[str, Any]:
    return summary.get("environment", {}).get("thread_environment", {})


def validate_profile_summary(setting: str, summary: Mapping[str, Any]) -> dict[str, Any]:
    if summary.get("status") != "COMPLETE":
        raise ValueError("single-process profile is incomplete")
    if summary.get("benchmark_tree_dirty") is not False:
        raise ValueError("profile source tree must be clean at measurement time")
    if not summary.get("benchmark_commit_sha") or not summary.get("benchmark_utility_sha256"):
        raise ValueError("profile source identity is incomplete")
    if summary.get("sample_count") != 6 * 2 * 7:
        raise ValueError("profile sample count is incomplete")
    if summary.get("timed_repetitions_per_condition", 0) < 7:
        raise ValueError("profile must have at least seven timed repetitions")
    if summary.get("warmups_per_condition_and_method", 0) < 2:
        raise ValueError("profile must have at least two warm-ups")
    if len(summary.get("candidate_input_files", {})) != len(CELL_IDENTITIES):
        raise ValueError("profile does not contain all six saved candidates")
    grid_data = summary.get("grid_identities", {})
    for name, expected in GRID_IDENTITIES.items():
        actual = grid_data.get(name, {})
        if any(actual.get(key) != value for key, value in expected.items()):
            raise ValueError(f"profile {name} grid identity mismatch")
    parity = summary.get("parity_results", [])
    if len(parity) != 12 or any(result.get("status") != "PASS" for result in parity):
        raise ValueError("profile parity results are absent or incomplete")
    expected_pairs = {
        (topology, seed, grid)
        for topology, seed in CELL_IDENTITIES
        for grid in ("search", "common")
    }
    for stage in PROFILE_STAGES:
        rows = [row for row in summary.get("summaries", []) if row.get("stage") == stage]
        actual_pairs = {(row.get("topology"), row.get("seed"), row.get("grid")) for row in rows}
        if actual_pairs != expected_pairs or any(row.get("n", 0) < 7 for row in rows):
            raise ValueError(f"profile {stage} summary is incomplete")
    environment = _profile_thread_environment(summary)
    expected_openblas = BLAS_SETTINGS.get(setting)
    if environment.get("OPENBLAS_NUM_THREADS") != expected_openblas:
        raise ValueError("profile did not record the requested child BLAS environment")
    effective_environment = {name: value for name, value in environment.items() if value is not None}
    return validate_blas_pools(
        setting, effective_environment, summary.get("environment", {}).get("threadpools"),
    )


def summarize_single_profiles(profiles: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    if set(profiles) - set(BLAS_SETTINGS):
        raise ValueError("unknown setting in single-process profile results")
    candidate_rows: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for setting, summary in profiles.items():
        validate_profile_summary(setting, summary)
        for row in summary["summaries"]:
            if row.get("stage") in PROFILE_STAGES:
                candidate_rows.setdefault(
                    (setting, str(row["grid"]), str(row["stage"])), []
                ).append(row)
    raw = []
    for (setting, grid, stage), rows in sorted(candidate_rows.items()):
        if len(rows) != len(CELL_IDENTITIES):
            raise ValueError(f"incomplete candidate summaries: {setting}/{grid}/{stage}")
        candidate_medians = [float(row["median_s"]) for row in rows]
        median = statistics.median(candidate_medians)
        raw.append({
            "setting": setting,
            "grid": grid,
            "frequency_count": GRID_IDENTITIES[grid]["frequency_count"],
            "stage": stage,
            "candidate_count": len(rows),
            "samples_per_candidate": min(int(row["n"]) for row in rows),
            "median_s": median,
            "min_s": min(float(row["min_s"]) for row in rows),
            "max_s": max(float(row["max_s"]) for row in rows),
            "mad_s": statistics.median(float(row["mad_s"]) for row in rows),
            "min_candidate_median_s": min(candidate_medians),
            "max_candidate_median_s": max(candidate_medians),
            "candidate_median_mad_s": statistics.median(
                abs(value - median) for value in candidate_medians
            ),
            "median_within_candidate_mad_s": statistics.median(
                float(row["mad_s"]) for row in rows
            ),
        })
    default_values = {
        (row["grid"], row["stage"]): row["median_s"]
        for row in raw if row["setting"] == "default"
    }
    for row in raw:
        baseline = default_values.get((row["grid"], row["stage"]))
        row["speedup_vs_default"] = baseline / row["median_s"] if baseline else None
    return raw


def summarize_throughput(
    rows: Sequence[Mapping[str, Any]], *, repetitions_per_condition: int = 2,
    expected_jobs_per_batch: int = 96, settings: Sequence[str] | None = None,
) -> dict[str, Any]:
    if repetitions_per_condition < 1:
        raise ValueError("at least one throughput repetition is required")
    settings = tuple(BLAS_SETTINGS) if settings is None else tuple(settings)
    if not settings or set(settings) - set(BLAS_SETTINGS):
        raise ValueError("throughput settings must be a non-empty subset of BLAS settings")
    if len(set(settings)) != len(settings):
        raise ValueError("throughput settings may not be repeated")
    by_condition: dict[tuple[str, int], list[Mapping[str, Any]]] = {}
    seen: set[tuple[str, int, int]] = set()
    for row in rows:
        setting, workers, repetition = str(row["setting"]), int(row["workers"]), int(row["repetition"])
        if setting not in settings or workers not in WORKER_COUNTS:
            raise ValueError("unknown throughput condition")
        if repetition < 1 or repetition > repetitions_per_condition:
            raise ValueError("throughput repetition is outside the requested range")
        key = (setting, workers, repetition)
        if key in seen:
            raise ValueError(f"duplicate throughput run: {key}")
        seen.add(key)
        for field in ("job_count", "evaluation_window_wall_s", "total_batch_wall_s",
                      "setup_wall_s", "worker_cpu_time_s", "affinity_cpu_count",
                      "peak_aggregate_rss_kib", "peak_total_process_threads"):
            value = float(row[field])
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid throughput field {field}")
        if float(row["job_count"]) <= 0 or float(row["evaluation_window_wall_s"]) <= 0:
            raise ValueError("throughput runs need jobs and positive evaluation time")
        if int(row["job_count"]) != expected_jobs_per_batch:
            raise ValueError("throughput batch has an incomplete job count")
        by_condition.setdefault((setting, workers), []).append(row)

    missing = [
        {"setting": setting, "workers": workers, "repetition": repetition}
        for setting in settings
        for workers in WORKER_COUNTS
        for repetition in range(1, repetitions_per_condition + 1)
        if (setting, workers, repetition) not in seen
    ]
    summaries = []
    for (setting, workers), group in sorted(by_condition.items()):
        throughputs = [float(row["job_count"]) / float(row["evaluation_window_wall_s"])
                       for row in group]
        median_throughput = statistics.median(throughputs)
        summaries.append({
            "setting": setting,
            "workers": workers,
            "batch_count": len(group),
            "median_jobs_per_second": median_throughput,
            "min_jobs_per_second": min(throughputs),
            "max_jobs_per_second": max(throughputs),
            "mad_jobs_per_second": statistics.median(
                abs(value - median_throughput) for value in throughputs
            ),
            "median_setup_wall_s": statistics.median(float(row["setup_wall_s"]) for row in group),
            "median_evaluation_window_wall_s": statistics.median(
                float(row["evaluation_window_wall_s"]) for row in group
            ),
            "median_total_batch_wall_s": statistics.median(
                float(row["total_batch_wall_s"]) for row in group
            ),
            "median_worker_cpu_time_s": statistics.median(
                float(row["worker_cpu_time_s"]) for row in group
            ),
            "median_cpu_utilization_pct": statistics.median(
                float(row["worker_cpu_time_s"])
                / float(row["evaluation_window_wall_s"])
                / max(1, int(row["affinity_cpu_count"])) * 100.0
                for row in group
            ),
            "peak_aggregate_rss_kib": max(int(row["peak_aggregate_rss_kib"]) for row in group),
            "peak_total_process_threads": max(
                int(row["peak_total_process_threads"]) for row in group
            ),
        })
    baseline = {
        row["setting"]: row["median_jobs_per_second"]
        for row in summaries if row["workers"] == 1
    }
    for row in summaries:
        base = baseline.get(row["setting"])
        row["speedup_vs_one_worker"] = (
            row["median_jobs_per_second"] / base if base else None
        )
    return {
        "status": "COMPLETE" if not missing else "PARTIAL",
        "settings": list(settings),
        "expected_repetitions_per_condition": repetitions_per_condition,
        "missing_runs": missing,
        "conditions": summaries,
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row)) or ["status"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (Mapping, list, tuple)) else value
                for key, value in row.items()
            })


def write_benchmark_outputs(
    output_dir: str | Path,
    single_rows: Sequence[Mapping[str, Any]],
    throughput_rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> tuple[Path, Path, Path]:
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite benchmark output: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_csv(output_dir / "single_process_samples.csv", single_rows)
    single_summary_path = output_dir / "single_process_summary.csv"
    _write_csv(single_summary_path, summary.get("single_process_summary", []))
    throughput_batches_path = output_dir / "parallel_batches.csv"
    _write_csv(throughput_batches_path, throughput_rows)
    _write_csv(output_dir / "parallel_summary.csv", summary.get("parallel_summary", {}).get("conditions", []))
    summary_path = output_dir / "benchmark_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return single_summary_path, throughput_batches_path, summary_path


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _proc_stats(pid: int) -> dict[str, int] | None:
    try:
        lines = Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    stats = {}
    for line in lines:
        if line.startswith("VmRSS:"):
            stats["rss_kib"] = int(line.split()[1])
        elif line.startswith("Threads:"):
            stats["threads"] = int(line.split()[1])
    return stats if "rss_kib" in stats and "threads" in stats else None


def _environment_metadata() -> dict[str, Any]:
    return {
        "os": platform.platform(),
        "machine": platform.machine(),
        "cpu_model": _cpu_model(),
        "python": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "affinity_cpu_count": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "parent_thread_environment": {name: os.environ.get(name) for name in THREAD_VARIABLES},
    }


def _cpu_model() -> str | None:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name\t:"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("15-minute benchmark time limit reached")
    return remaining


def _sample_processes(pids: Sequence[int]) -> tuple[int, int]:
    stats = [_proc_stats(pid) for pid in pids]
    alive = [item for item in stats if item is not None]
    return sum(item["rss_kib"] for item in alive), sum(item["threads"] for item in alive)


def _terminate(processes: Sequence[subprocess.Popen[str]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    until = time.monotonic() + 2.0
    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=max(0.0, until - time.monotonic()))
            except subprocess.TimeoutExpired:
                process.kill()
    for process in processes:
        if process.poll() is None:
            process.wait()


def _single_worker_main(args: argparse.Namespace) -> int:
    import numpy  # imported only after the parent applied the child environment
    import scipy
    from threadpoolctl import threadpool_info
    from sawopt.studies.audits.stage5a1_evaluation_profile import run_profile

    del numpy, scipy
    validation = validate_blas_pools(args.setting, os.environ, threadpool_info())

    output_dir = Path(args.output_dir)
    run_profile(
        config=args.config, output_dir=output_dir, repeats=args.repeats,
        warmups=args.warmups, measurement_order_seed=args.measurement_order_seed,
    )
    _write_json(output_dir / "active_blas.json", validation)
    return 0


def _parallel_worker_main(args: argparse.Namespace) -> int:
    config = json.loads(Path(args.worker_config).read_text(encoding="utf-8"))
    import numpy  # imported only after the parent applied the child environment
    import scipy
    from threadpoolctl import threadpool_info
    from sawopt.studies.audits import stage5a1_evaluation_profile as profile

    del numpy, scipy
    validation = validate_blas_pools(config["setting"], os.environ, threadpool_info())

    setup_started = time.perf_counter()
    context = profile.load_stage4c_context(config["config"])
    grids = profile._validate_grids(context)
    if grids["search"]["sha256"] != GRID_IDENTITIES["search"]["sha256"]:
        raise ValueError("parallel worker search grid identity mismatch")
    if grids["common"]["grid_id"] != GRID_IDENTITIES["common"]["grid_id"]:
        raise ValueError("parallel worker common grid identity mismatch")
    cases, read_seconds, input_hashes = profile._load_cases(
        context, ROOT / REVIEW_RELATIVE,
    )
    frequencies = context["search_frequencies"]
    candidates = [profile._candidate(case["vector"], case["topology"], context) for case in cases]
    tolerances = context["cfg"]["hybrid"]["parity"]
    max_difference = 0.0
    for case in cases:
        decomposed = profile.profile_decomposed_evaluation(
            case["vector"], case["topology"], context, frequencies,
        )
        reference = profile.capture_stage4a_reference(
            case["vector"], case["topology"], context, frequencies,
        )
        differences = profile.assert_profile_equivalence(
            decomposed, reference,
            rtol=float(tolerances["rtol"]), atol=float(tolerances["atol"]),
        )
        max_difference = max(max_difference, max(differences.values(), default=0.0))
    for _ in range(config["warmups"]):
        record = profile.stage4a_evaluate(
            candidates[0], context["provider"], context["cfg"], frequencies,
            context["source_impedance_ohm"], context["load_impedance_ohm"],
        )
        if record.get("evaluation_status") != "PHYSICS_EVALUATED":
            raise RuntimeError("parallel worker warm-up evaluation failed")
    # Evaluation imports may lazily load another library; verify every pool
    # that will be active during the timed evaluation window.
    validation = validate_blas_pools(config["setting"], os.environ, threadpool_info())
    setup_seconds = time.perf_counter() - setup_started
    thread_count = len(os.listdir("/proc/self/task")) if Path("/proc/self/task").exists() else None
    rss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    ready = {
        "status": "READY", "blas_validation": validation,
        "preflight_status": "PASS", "preflight_candidate_count": len(cases),
        "preflight_maximum_absolute_difference": max_difference,
        "parity_rtol": float(tolerances["rtol"]), "parity_atol": float(tolerances["atol"]),
        "setup_seconds": setup_seconds, "candidate_evidence_sha256": input_hashes,
        "candidate_evidence_read_seconds": read_seconds,
        "grid_identities": grids,
        "process_thread_count": thread_count, "process_peak_rss_kib": rss_kib,
    }
    _write_json(Path(config["ready_file"]), ready)
    start_file = Path(config["start_file"])
    while not start_file.exists():
        time.sleep(0.005)
    started = time.perf_counter()
    cpu_started = time.process_time()
    job_results = []
    for job_number, candidate_index in enumerate(config["candidate_indices"]):
        case = cases[candidate_index]
        timer = time.perf_counter()
        record = profile.stage4a_evaluate(
            candidates[candidate_index], context["provider"], context["cfg"], frequencies,
            context["source_impedance_ohm"], context["load_impedance_ohm"],
        )
        elapsed = time.perf_counter() - timer
        if record.get("evaluation_status") != "PHYSICS_EVALUATED":
            raise RuntimeError(f"parallel job {job_number} did not evaluate physics")
        job_results.append({
            "job_number": job_number,
            "candidate": f"{case['topology']}/{case['seed']}",
            "elapsed_s": elapsed,
            "objective": float(record["objective"]),
            "max_violation": float(record["max_violation"]),
            "sum_violation": float(record["sum_violation"]),
            "feasible": bool(record["feasible"]),
        })
    result = {
        **ready,
        "status": "COMPLETE", "job_count": len(job_results),
        "worker_evaluation_wall_s": time.perf_counter() - started,
        "worker_cpu_time_s": time.process_time() - cpu_started,
        "worker_peak_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "worker_peak_thread_count": len(os.listdir("/proc/self/task")) if Path("/proc/self/task").exists() else None,
        "jobs": job_results,
    }
    _write_json(Path(config["result_file"]), result)
    return 0


def _spawn_monitored(
    command: Sequence[str], environment: Mapping[str, str], deadline: float,
) -> tuple[subprocess.Popen[str], float, int, int]:
    process = subprocess.Popen(
        list(command), cwd=ROOT, env=dict(environment), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    started = time.perf_counter()
    peak_rss = peak_threads = 0
    timed_out = False
    while process.poll() is None:
        rss, threads = _sample_processes([process.pid])
        peak_rss, peak_threads = max(peak_rss, rss), max(peak_threads, threads)
        if time.monotonic() >= deadline:
            timed_out = True
            _terminate([process])
            break
        time.sleep(0.05)
    stdout, stderr = process.communicate()
    if timed_out:
        raise TimeoutError("15-minute benchmark time limit reached during subprocess")
    if process.returncode != 0:
        raise RuntimeError(
            f"benchmark subprocess exited {process.returncode}: {stderr[-4000:]} {stdout[-1000:]}"
        )
    return process, time.perf_counter() - started, peak_rss, peak_threads


def _run_parallel_condition(
    *, setting: str, workers: int, repetition: int, jobs: int,
    config_path: str, warmups: int, scratch: Path, deadline: float,
) -> dict[str, Any]:
    if workers not in WORKER_COUNTS or jobs < workers:
        raise ValueError("invalid independent-worker benchmark size")
    condition_dir = scratch / f"parallel-{setting}-w{workers}-r{repetition}"
    condition_dir.mkdir()
    start_file = condition_dir / "start.json"
    processes: list[subprocess.Popen[str]] = []
    process_paths = []
    started = time.perf_counter()
    peak_rss = peak_threads = 0
    try:
        for worker_id in range(workers):
            candidate_indices = [index % len(CELL_IDENTITIES) for index in range(jobs)
                                 if index % workers == worker_id]
            worker_config = {
                "setting": setting, "config": config_path, "warmups": warmups,
                "candidate_indices": candidate_indices,
                "ready_file": str(condition_dir / f"worker-{worker_id}.ready.json"),
                "result_file": str(condition_dir / f"worker-{worker_id}.result.json"),
                "start_file": str(start_file),
            }
            config_file = condition_dir / f"worker-{worker_id}.config.json"
            _write_json(config_file, worker_config)
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--parallel-worker",
                 "--worker-config", str(config_file)],
                cwd=ROOT, env=build_child_environment(setting), text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            processes.append(process)
            process_paths.append((worker_id, worker_config))

        while True:
            rss, threads = _sample_processes([process.pid for process in processes])
            peak_rss, peak_threads = max(peak_rss, rss), max(peak_threads, threads)
            ready_paths = [Path(item[1]["ready_file"]) for item in process_paths]
            if all(path.exists() for path in ready_paths):
                break
            failed = [proc for proc in processes if proc.poll() is not None]
            if failed:
                messages = [proc.communicate()[1][-2000:] for proc in failed]
                raise RuntimeError("parallel worker failed during startup: " + "\n".join(messages))
            if time.monotonic() >= deadline:
                raise TimeoutError("15-minute benchmark time limit reached during worker setup")
            time.sleep(0.02)
        ready_data = [json.loads(path.read_text(encoding="utf-8")) for path in ready_paths]
        if any(item.get("status") != "READY" or item.get("preflight_status") != "PASS"
               for item in ready_data):
            raise ValueError("parallel workers did not pass preflight")
        pool_signatures = {
            blas_pool_signature(item["blas_validation"]["active_blas_libraries"])
            for item in ready_data
        }
        if len(pool_signatures) != 1:
            raise ValueError(
                "parallel workers loaded different BLAS libraries or thread counts: "
                f"{sorted(pool_signatures)!r}"
            )
        setup_wall = time.perf_counter() - started
        eval_started = time.perf_counter()
        _write_json(start_file, {"start": True})
        while any(process.poll() is None for process in processes):
            rss, threads = _sample_processes([process.pid for process in processes])
            peak_rss, peak_threads = max(peak_rss, rss), max(peak_threads, threads)
            if time.monotonic() >= deadline:
                raise TimeoutError("15-minute benchmark time limit reached during parallel evaluation")
            time.sleep(0.02)
        completed = time.perf_counter()
        outputs = []
        for (worker_id, worker_config), process in zip(process_paths, processes, strict=True):
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                raise RuntimeError(
                    f"parallel worker {worker_id} failed: {stderr[-3000:]} {stdout[-500:]}"
                )
            output = json.loads(Path(worker_config["result_file"]).read_text(encoding="utf-8"))
            if output.get("status") != "COMPLETE" or output.get("job_count") != len(worker_config["candidate_indices"]):
                raise ValueError(f"parallel worker {worker_id} returned incomplete results")
            if output["blas_validation"].get("valid") is not True:
                raise ValueError(f"parallel worker {worker_id} BLAS setting is invalid")
            outputs.append(output)
        tolerances = outputs[0]["parity_rtol"], outputs[0]["parity_atol"]
        repeat_difference = validate_parallel_job_results(
            outputs, rtol=float(tolerances[0]), atol=float(tolerances[1]),
        )
        affinity_count = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count() or 1
        libraries = outputs[0]["blas_validation"]["active_blas_libraries"]
        pool_counts = [int(item["num_threads"]) for item in libraries]
        configured_thread_demand = workers * sum(pool_counts)
        return {
            "setting": setting, "workers": workers, "repetition": repetition,
            "job_count": sum(item["job_count"] for item in outputs),
            "setup_wall_s": setup_wall,
            "evaluation_window_wall_s": completed - eval_started,
            "total_batch_wall_s": completed - started,
            "jobs_per_second": sum(item["job_count"] for item in outputs) / (completed - eval_started),
            "worker_cpu_time_s": sum(item["worker_cpu_time_s"] for item in outputs),
            "affinity_cpu_count": affinity_count,
            "cpu_utilization_pct": sum(item["worker_cpu_time_s"] for item in outputs)
            / max(completed - eval_started, 1e-12) / affinity_count * 100.0,
            "peak_aggregate_rss_kib": peak_rss,
            "sum_worker_peak_rss_kib": sum(item["worker_peak_rss_kib"] for item in outputs),
            "peak_total_process_threads": peak_threads,
            "worker_process_thread_counts": [item["process_thread_count"] for item in ready_data],
            "worker_peak_thread_counts": [item["worker_peak_thread_count"] for item in outputs],
            "effective_blas_libraries": libraries,
            "blas_environment_validation": outputs[0]["blas_validation"],
            "parallel_repeat_maximum_absolute_difference": repeat_difference,
            "configured_thread_demand": configured_thread_demand,
            "configured_thread_oversubscription": configured_thread_demand > affinity_count,
            "observed_thread_oversubscription": peak_threads > affinity_count,
            "preflight_candidate_count_total": sum(item["preflight_candidate_count"] for item in ready_data),
            "preflight_maximum_absolute_difference": max(
                item["preflight_maximum_absolute_difference"] for item in ready_data
            ),
            "preflight_rtol": max(item["parity_rtol"] for item in ready_data),
            "preflight_atol": max(item["parity_atol"] for item in ready_data),
            "worker_setup_seconds": [item["setup_seconds"] for item in ready_data],
        }
    except BaseException:
        _terminate(processes)
        raise


def run_benchmark(
    *, output_dir: str | Path, config: str = DEFAULT_CONFIG,
    repeats: int = 7, warmups: int = 2, parallel_repetitions: int = 2,
    jobs_per_batch: int = 96, order_seed: int = 20261009,
    max_runtime_seconds: float = 900.0,
    parallel_settings: Sequence[str] = tuple(BLAS_SETTINGS),
    reuse_single_process_results: str | Path | None = None,
    prior_elapsed_seconds: float = 0.0,
) -> tuple[Path, Path, Path]:
    if repeats < 7 or warmups < 2 or parallel_repetitions < 1:
        raise ValueError("single profiles need 7 repeats/2 warm-ups and parallel runs need repetitions")
    if jobs_per_batch < 4:
        raise ValueError("parallel batch must have at least four jobs")
    if not 0 < max_runtime_seconds <= 900:
        raise ValueError("benchmark runtime limit must be positive and no more than 900 seconds")
    parallel_settings = validate_parallel_settings(parallel_settings)
    if not math.isfinite(prior_elapsed_seconds) or prior_elapsed_seconds < 0:
        raise ValueError("prior elapsed seconds must be finite and non-negative")
    output_dir = Path(output_dir).resolve()
    if output_dir == ROOT or ROOT in output_dir.parents:
        raise ValueError("benchmark output must be outside the repository")
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite benchmark output: {output_dir}")
    run_started = time.perf_counter()
    parent_environment = {name: os.environ.get(name) for name in THREAD_VARIABLES}
    single_profiles: dict[str, Mapping[str, Any]] = {}
    profile_records = []
    single_rows = []
    single_summary_rows = []
    throughput_rows = []
    errors = []
    partial_reason = None
    setting_order = shuffled_single_order(order_seed)
    single_process_source = None
    prior_elapsed = prior_elapsed_seconds

    if reuse_single_process_results is not None:
        source_dir = Path(reuse_single_process_results).resolve()
        if source_dir == ROOT or ROOT in source_dir.parents:
            raise ValueError("reused serial results must be outside the repository")
        source_summary = json.loads(
            (source_dir / "benchmark_summary.json").read_text(encoding="utf-8")
        )
        with (source_dir / "single_process_samples.csv").open(newline="", encoding="utf-8") as stream:
            source_samples = list(csv.DictReader(stream))
        with (source_dir / "single_process_summary.csv").open(newline="", encoding="utf-8") as stream:
            single_summary_rows = list(csv.DictReader(stream))
        profile_records = validate_reusable_single_results(
            source_summary, source_samples, single_summary_rows,
        )
        if source_summary.get("base_main_commit_sha") != _git_output("rev-parse", "origin/main"):
            raise ValueError("reusable serial results were measured against a different main commit")
        if source_summary.get("config") != config:
            raise ValueError("reusable serial results use a different configuration")
        if source_summary.get("parent_thread_environment") != parent_environment:
            raise ValueError("reusable serial results have a different parent thread environment")
        if prior_elapsed < float(source_summary.get("elapsed_wall_s", 0.0)):
            prior_elapsed = float(source_summary["elapsed_wall_s"])
        single_rows = source_samples
        setting_order = list(source_summary.get("single_process_setting_order", []))
        single_process_source = {
            "output_id": source_dir.name,
            "status": source_summary.get("status"),
            "runner_commit_sha": source_summary["runner_commit_sha"],
            "runner_sha256": source_summary["runner_sha256"],
            "profile_tool_sha256": profile_records[0]["profile_tool_sha256"],
            "metadata_json_sha256": hashlib.sha256(
                (source_dir / "benchmark_summary.json").read_bytes()
            ).hexdigest(),
            "samples_csv_sha256": hashlib.sha256(
                (source_dir / "single_process_samples.csv").read_bytes()
            ).hexdigest(),
            "summary_csv_sha256": hashlib.sha256(
                (source_dir / "single_process_summary.csv").read_bytes()
            ).hexdigest(),
            "elapsed_wall_s": source_summary["elapsed_wall_s"],
            "profile_setting_order": setting_order,
        }
        if source_summary.get("partial_reason"):
            raise ValueError("reusable serial results contain a partial serial phase")
        if any(error.get("phase") != "parallel_pilot"
               for error in source_summary.get("errors", [])):
            raise ValueError("reusable serial source has errors outside its parallel pilot")

    if prior_elapsed >= max_runtime_seconds:
        raise ValueError("prior benchmark time already reaches the 15-minute limit")
    deadline = time.monotonic() + max_runtime_seconds - prior_elapsed

    with tempfile.TemporaryDirectory(prefix="stage5a1-blas-raw-") as temp_name:
        scratch = Path(temp_name)
        if reuse_single_process_results is None:
            for order_index, setting in enumerate(setting_order, start=1):
                try:
                    _remaining(deadline)
                    child_output = scratch / f"single-{setting}"
                    command = [
                        sys.executable, str(Path(__file__).resolve()), "--single-worker",
                        "--setting", setting, "--config", config,
                        "--output-dir", str(child_output), "--repeats", str(repeats),
                        "--warmups", str(warmups), "--measurement-order-seed", str(order_seed),
                    ]
                    process, wall_seconds, peak_rss, peak_threads = _spawn_monitored(
                        command, build_child_environment(setting), deadline,
                    )
                    del process
                    summary = json.loads(
                        (child_output / "profile_summary.json").read_text(encoding="utf-8")
                    )
                    pool_validation = validate_profile_summary(setting, summary)
                    profile = {
                        "setting": setting, "run_order": order_index,
                        "process_wall_s": wall_seconds,
                        "peak_rss_kib": peak_rss,
                        "peak_process_threads": peak_threads,
                        "blas_validation": pool_validation,
                        "profile_commit_sha": summary["benchmark_commit_sha"],
                        "profile_tool_sha256": summary["benchmark_utility_sha256"],
                        "context_load_seconds": summary["context_load_seconds"],
                        "candidate_evidence_read_seconds": summary["candidate_evidence_total_read_seconds"],
                        "parity_validation_seconds": summary["parity_validation_seconds"],
                        "candidate_input_files": summary["candidate_input_files"],
                        "grid_identities": summary["grid_identities"],
                        "parity_results": summary["parity_results"],
                        "environment": summary["environment"],
                        "sample_count": summary["sample_count"],
                    }
                    profile_records.append(profile)
                    single_profiles[setting] = summary
                    with (child_output / "measurements.csv").open(newline="", encoding="utf-8") as stream:
                        for row in csv.DictReader(stream):
                            single_rows.append({
                                "setting": setting, "setting_run_order": order_index,
                                "effective_blas_libraries": json.dumps(
                                    pool_validation["active_blas_libraries"], sort_keys=True,
                                ),
                                **row,
                            })
                except TimeoutError as exc:
                    partial_reason = str(exc)
                    errors.append({"phase": "single", "setting": setting, "error": str(exc)})
                    break
                except Exception as exc:
                    errors.append({"phase": "single", "setting": setting,
                                   "error": f"{type(exc).__name__}: {exc}"})

            single_summary_rows = summarize_single_profiles(single_profiles) if single_profiles else []
        pilot = None
        parallel_order = []
        projected_matrix_seconds = None
        if len(profile_records) == len(BLAS_SETTINGS) and not partial_reason:
            try:
                pilot = _run_parallel_condition(
                    setting="default", workers=4, repetition=0, jobs=24,
                    config_path=config, warmups=warmups, scratch=scratch, deadline=deadline,
                )
                pilot["kind"] = "pilot"
                throughput_rows.append(pilot)
                projected_matrix_seconds = estimate_parallel_matrix_seconds(
                    pilot, jobs_per_batch=jobs_per_batch,
                    repetitions=parallel_repetitions, settings=parallel_settings,
                )
                if projected_matrix_seconds > max(0.0, deadline - time.monotonic()):
                    partial_reason = (
                        f"parallel matrix projection {projected_matrix_seconds:.1f}s exceeds "
                        "the remaining 15-minute allowance"
                    )
            except TimeoutError as exc:
                partial_reason = str(exc)
                errors.append({"phase": "parallel_pilot", "error": str(exc)})
            except Exception as exc:
                errors.append({"phase": "parallel_pilot", "error": f"{type(exc).__name__}: {exc}"})

        if pilot and not partial_reason and not errors:
            parallel_order = shuffled_parallel_order(
                order_seed + 1, parallel_repetitions, settings=parallel_settings,
            )
            for condition in parallel_order:
                setting, workers, repetition = (
                    condition["setting"], condition["workers"], condition["repetition"]
                )
                try:
                    _remaining(deadline)
                    row = _run_parallel_condition(
                        setting=setting, workers=workers, repetition=repetition,
                        jobs=jobs_per_batch, config_path=config, warmups=warmups,
                        scratch=scratch, deadline=deadline,
                    )
                    row["kind"] = "measurement"
                    throughput_rows.append(row)
                except TimeoutError as exc:
                    partial_reason = str(exc)
                    errors.append({
                        "phase": "parallel", "setting": setting,
                        "workers": workers, "repetition": repetition, "error": str(exc),
                    })
                    break
                except Exception as exc:
                    errors.append({
                        "phase": "parallel", "setting": setting,
                        "workers": workers, "repetition": repetition,
                        "error": f"{type(exc).__name__}: {exc}",
                    })

        measurement_rows = [row for row in throughput_rows if row.get("kind") == "measurement"]
        parallel_summary = summarize_throughput(
            measurement_rows, repetitions_per_condition=parallel_repetitions,
            expected_jobs_per_batch=jobs_per_batch, settings=parallel_settings,
        )
        complete = (
            len(profile_records) == len(BLAS_SETTINGS)
            and parallel_summary["status"] == "COMPLETE"
            and not errors and not partial_reason
        )
        summary = {
            "schema_version": 1,
            "status": "COMPLETE" if complete else ("PARTIAL" if profile_records or throughput_rows else "BLOCKED"),
            "base_main_commit_sha": _git_output("rev-parse", "origin/main"),
            "runner_commit_sha": _git_output("rev-parse", "HEAD"),
            "runner_tree_dirty": bool(_git_output("status", "--porcelain")),
            "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "existing_profile_sha256": hashlib.sha256(PROFILE_TOOL.read_bytes()).hexdigest(),
            "config": config,
            "measurement_order_seed": order_seed,
            "single_process_setting_order": setting_order,
            "single_process_repetitions": repeats,
            "single_process_warmups": warmups,
            "parallel_condition_order": parallel_order,
            "parallel_settings": parallel_settings,
            "parallel_repetitions": parallel_repetitions,
            "parallel_jobs_per_batch": jobs_per_batch,
            "parallel_worker_counts": list(WORKER_COUNTS),
            "blas_settings": BLAS_SETTINGS,
            "parent_thread_environment": parent_environment,
            "environment": _environment_metadata(),
            "single_process_profiles": profile_records,
            "single_process_summary": single_summary_rows,
            "single_process_source": single_process_source,
            "parallel_pilot": pilot,
            "projected_parallel_matrix_seconds": projected_matrix_seconds,
            "parallel_summary": parallel_summary,
            "errors": errors,
            "partial_reason": partial_reason,
            "elapsed_wall_s": prior_elapsed + time.perf_counter() - run_started,
            "prior_elapsed_seconds": prior_elapsed,
            "max_runtime_seconds": max_runtime_seconds,
            "input_evidence_root": REVIEW_RELATIVE.as_posix(),
        }
        return write_benchmark_outputs(output_dir, single_rows, throughput_rows, summary)


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--parallel-repetitions", type=int, default=2)
    parser.add_argument("--jobs-per-batch", type=int, default=96)
    parser.add_argument("--order-seed", type=int, default=20261009)
    parser.add_argument("--max-runtime-seconds", type=float, default=900.0)
    parser.add_argument("--parallel-settings", nargs="+", choices=tuple(BLAS_SETTINGS),
                        default=list(BLAS_SETTINGS))
    parser.add_argument("--reuse-single-process-results", type=Path)
    parser.add_argument("--prior-elapsed-seconds", type=float, default=0.0)
    parser.add_argument("--single-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--parallel-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--setting", choices=tuple(BLAS_SETTINGS))
    parser.add_argument("--worker-config", type=Path)
    parser.add_argument("--measurement-order-seed", type=int, default=20261009)
    args = parser.parse_args(argv)
    if args.single_worker:
        if not args.setting or not args.output_dir:
            parser.error("single worker requires --setting and --output-dir")
        return _single_worker_main(args)
    if args.parallel_worker:
        if not args.worker_config:
            parser.error("parallel worker requires --worker-config")
        return _parallel_worker_main(args)
    if not args.output_dir:
        parser.error("--output-dir is required and must be outside the repository")
    paths = run_benchmark(
        output_dir=args.output_dir, config=args.config, repeats=args.repeats,
        warmups=args.warmups, parallel_repetitions=args.parallel_repetitions,
        jobs_per_batch=args.jobs_per_batch, order_seed=args.order_seed,
        max_runtime_seconds=args.max_runtime_seconds,
        parallel_settings=args.parallel_settings,
        reuse_single_process_results=args.reuse_single_process_results,
        prior_elapsed_seconds=args.prior_elapsed_seconds,
    )
    print(json.dumps({"outputs": [str(path) for path in paths]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
