"""Diagnose fixed-input response parity without optimizer or production runs."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

EXPECTED_HASHES = {
    "filter_y": "6c21974996f08352b09f19d32f403cd13d5dc831d42cebe3157c7dbfa0ca49a5",
    "filter_s": "eee9da5fd0a706293f343faa2c20be72da71adc4791f72d7d136d9af8e273cdc",
    "filter_gt": "7c5a8e47cfddf62be58261225824d29839eee8123d92fd3d2320b2777c4ffd19",
    "t1_y": "4ee60a4ae1831825d46fdbc7d82ab54264235642e02e54e0b639962a9d51dbdc",
    "t2_y": "1f5a5bb278d35cc3070adf0f499c92705ba9b38f7dde57ffd8f09de13d22d3fd",
}
ARRAY_NAMES = ("filter_y", "filter_s", "filter_gt", "filter_il", "t1_y", "t1_s", "t1_gt", "t2_y", "t2_s", "t2_gt")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _array_sha(values: np.ndarray, dtype: str) -> str:
    return _sha(np.ascontiguousarray(values, dtype=dtype).tobytes())


def _runtime() -> dict:
    import scipy
    import threadpoolctl

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        np.show_runtime()
    cpu = {}
    for line in Path("/proc/cpuinfo").read_text(errors="replace").splitlines():
        if ":" in line:
            key, value = (part.strip() for part in line.split(":", 1))
            if key in {"model name", "vendor_id", "flags", "Features"}:
                cpu.setdefault(key, value)
    env_keys = (
        "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
        "OPENBLAS_CORETYPE", "GITHUB_ACTIONS", "ImageOS", "ImageVersion",
        "RUNNER_OS", "RUNNER_ARCH", "RUNNER_NAME",
    )
    os_release = Path("/etc/os-release")
    return {
        "platform": platform.platform(), "machine": platform.machine(),
        "python": sys.version, "numpy": np.__version__, "scipy": scipy.__version__,
        "threadpoolctl": threadpoolctl.__version__, "cpu": cpu,
        "cpu_count": os.cpu_count(),
        "environment": {key: os.environ.get(key) for key in env_keys},
        "os_release": os_release.read_text(errors="replace") if os_release.exists() else "",
        "numpy_show_runtime": output.getvalue(),
        "threadpools": threadpoolctl.threadpool_info(),
    }


def _evaluate() -> tuple[dict[str, np.ndarray], dict]:
    import yaml

    from sawopt.design.space import FilterDesign
    from sawopt.design.topology import (
        FiveIdtDesign, ParallelThreeIdtDesign, T1, T2,
    )
    from sawopt.evaluation import evaluate_design, search_grid, simulate_topology
    try:
        from sawopt.optimization.selection import DEFAULT_COMPARATOR
    except ModuleNotFoundError:  # R3 baseline predates the ownership move.
        from sawopt.optimizers.selection import DEFAULT_COMPARATOR
    from sawopt.physics.com import FixedProvider, simulate_filter
    from sawopt.physics.network import evaluate as evaluate_network

    root = Path.cwd()
    config_paths = (
        root / "configs/base/b28_dms_baseline.yaml",
        root / "configs/studies/hybrid_50ohm.yaml",
        root / "configs/models/com_params_hypothetical.yaml",
    )
    base, hybrid, com = (yaml.safe_load(path.read_text()) for path in config_paths)
    cfg = {**base, **hybrid, "com": com}
    frequencies = search_grid(cfg["spec"], cfg)
    topology_frequencies = np.asarray([730e6, 758e6, 780e6, 803e6, 830e6])
    design = FilterDesign()
    record, filter_network, simulation = evaluate_design(
        design, cfg, frequencies, 37.0, 91.0
    )
    debug = simulate_filter(
        design, FixedProvider(com), frequencies, cfg["center"], debug_diagnostics=True
    )
    provider = FixedProvider(com)
    t1 = simulate_topology(FiveIdtDesign(), provider, topology_frequencies, T1)
    t2 = simulate_topology(ParallelThreeIdtDesign(), provider, topology_frequencies, T2)
    t1_network = evaluate_network(t1.y_parameters, 37.0, 91.0)
    t2_network = evaluate_network(t2.y_parameters, 37.0, 91.0)
    arrays = {
        "filter_y": simulation.y_parameters,
        "filter_s": filter_network["s"],
        "filter_gt": filter_network["gt"],
        "filter_il": filter_network["il"],
        "t1_y": t1.y_parameters,
        "t1_s": t1_network["s"],
        "t1_gt": t1_network["gt"],
        "t2_y": t2.y_parameters,
        "t2_s": t2_network["s"],
        "t2_gt": t2_network["gt"],
    }
    hashes = {
        name: _array_sha(arrays[name], "<c16" if np.iscomplexobj(arrays[name]) else "<f8")
        for name in EXPECTED_HASHES
    }
    diagnostics = {
        "filter": {
            key: debug.diagnostics[key] for key in (
                "max_acoustic_solve_residual", "max_acoustic_condition_number",
                "min_conductance_eigenvalue", "reciprocity_error",
            )
        },
        "t1": {
            key: t1.diagnostics[key] for key in (
                "max_acoustic_solve_residual", "min_conductance_eigenvalue",
                "reciprocity_error",
            )
        },
        "t2_tracks": [
            {key: track[key] for key in (
                "max_acoustic_solve_residual", "min_conductance_eigenvalue",
                "reciprocity_error",
            )}
            for track in t2.diagnostics["track_diagnostics"]
        ],
    }
    report = {
        "revision": subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip(),
        "runtime": _runtime(),
        "input_identity": {
            "config_sha256": {str(path.relative_to(root)): _sha(path.read_bytes()) for path in config_paths},
            "filter_frequency_count": len(frequencies),
            "filter_frequency_sha256_le_f8": _array_sha(frequencies, "<f8"),
            "topology_frequencies_sha256_le_f8": _array_sha(topology_frequencies, "<f8"),
            "filter_design": {key: getattr(design, key) for key in design.__dataclass_fields__},
            "terminations_ohm": [37.0, 91.0],
        },
        "array_metadata": {
            name: {
                "shape": list(array.shape), "dtype": array.dtype.str,
                "byteorder": array.dtype.byteorder,
                "finite_count": int(np.isfinite(array).sum()),
                "nonfinite_count": int((~np.isfinite(array)).sum()),
            }
            for name, array in arrays.items()
        },
        "actual_hashes": hashes,
        "expected_hashes": EXPECTED_HASHES,
        "expected_hash_match": {name: hashes[name] == value for name, value in EXPECTED_HASHES.items()},
        "rank_inputs": {
            "metrics": record["metrics"], "violations": record["violations"],
            "feasible": record["feasible"], "max_violation": record["max_violation"],
            "objective": record["objective"],
            "search_scalar_objective": record["search_scalar_objective"],
            "feasibility_first_rank_key": DEFAULT_COMPARATOR.rank_key(record),
        },
        "physics_diagnostics": diagnostics,
        "network_checks": {
            name: float(np.max(np.abs(network["gt"] - np.abs(network["s"][:, 1, 0]) ** 2)))
            for name, network in (
                ("filter_gt_minus_abs_s21_squared", filter_network),
                ("t1_gt_minus_abs_s21_squared", t1_network),
                ("t2_gt_minus_abs_s21_squared", t2_network),
            )
        },
    }
    return arrays, report


def _ordered_bits(values: np.ndarray) -> np.ndarray:
    bits = np.ascontiguousarray(values, dtype=np.float64).view(np.uint64)
    sign = np.uint64(1 << 63)
    return np.where((bits & sign) != 0, ~bits, bits | sign)


def _delta(left: np.ndarray, right: np.ndarray, name: str) -> dict:
    left, right = np.asarray(left), np.asarray(right)
    if left.shape != right.shape:
        return {"shape_mismatch": [list(left.shape), list(right.shape)]}
    components = (("real", left.real, right.real), ("imag", left.imag, right.imag)) if np.iscomplexobj(left) else ((name, left, right),)
    bit_changes, absolute, relative, ulps = [], [], [], []
    first = None
    for component, x, y in components:
        x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
        changed = np.ascontiguousarray(x).view(np.uint64) != np.ascontiguousarray(y).view(np.uint64)
        if first is None and np.any(changed):
            first = {"component": component, "index": np.argwhere(changed)[0].tolist()}
        bit_changes.append(changed)
        delta = np.abs(x - y)
        absolute.append(delta)
        relative.append(delta / np.maximum(np.maximum(np.abs(x), np.abs(y)), np.finfo(float).tiny))
        xo, yo = _ordered_bits(x), _ordered_bits(y)
        ulps.append(np.maximum(xo, yo) - np.minimum(xo, yo))
    return {
        "shape": list(left.shape), "dtype": left.dtype.str, "byteorder": left.dtype.byteorder,
        "changed_cells": int(np.logical_or.reduce(bit_changes).sum()),
        "changed_components": int(sum(mask.sum() for mask in bit_changes)),
        "first_changed_component": first,
        "max_absolute_delta": float(max(part.max(initial=0.0) for part in absolute)),
        "max_scaled_relative_delta": float(max(part.max(initial=0.0) for part in relative)),
        "max_ulp_delta": max(
            (int(part[mask].max()) for part, mask in zip(ulps, bit_changes) if mask.any()),
            default=0,
        ),
    }


def _worker(directory: Path) -> None:
    arrays, report = _evaluate()
    repeated, repeated_report = _evaluate()
    report["same_process_repeat"] = {
        "rank_inputs_equal": report["rank_inputs"] == repeated_report["rank_inputs"],
        "arrays": {name: _delta(arrays[name], repeated[name], name) for name in ARRAY_NAMES},
    }
    directory.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(directory / "arrays.npz", **arrays)
    (directory / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def _compare(left_dir: Path, right_dir: Path, label: str) -> dict:
    with np.load(left_dir / "arrays.npz") as left, np.load(right_dir / "arrays.npz") as right:
        return {
            "comparison": label,
            "arrays": {name: _delta(left[name], right[name], name) for name in ARRAY_NAMES},
        }


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        _worker(Path(sys.argv[2]))
        return 0

    with tempfile.TemporaryDirectory(prefix="sawopt-evaluation-repro-") as temp:
        root = Path(temp)
        dirs = {
            name: root / name
            for name in ("default_1", "default_2", "single_thread", "haswell_core")
        }
        default_env = os.environ.copy()
        single_env = default_env | {
            "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
        }
        haswell_env = default_env | {"OPENBLAS_CORETYPE": "Haswell"}
        modes = (
            ("default_1", default_env),
            ("default_2", default_env),
            ("single_thread", single_env),
            ("haswell_core", haswell_env),
        )
        for name, env in modes:
            subprocess.run([sys.executable, __file__, "--worker", str(dirs[name])], check=True, env=env)
        reports = {name: json.loads((directory / "report.json").read_text()) for name, directory in dirs.items()}
        result = {
            "purpose": "fixed-input software regression diagnostics only; no optimizer or production FE",
            "runs": reports,
            "independent_default_processes": _compare(dirs["default_1"], dirs["default_2"], "default process 1 vs 2"),
            "default_vs_single_thread": _compare(dirs["default_1"], dirs["single_thread"], "default vs single-thread BLAS"),
            "default_vs_forced_haswell": _compare(dirs["default_1"], dirs["haswell_core"], "default vs OPENBLAS_CORETYPE=Haswell"),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
