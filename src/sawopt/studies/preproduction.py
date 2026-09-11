"""Stage 3.3.1 pre-production validation and review-bundle driver.

The command in this module owns the finite pre-production workflow described in
the Stage 3.3.1 handoff.  It intentionally stops after creating
``stage3_3_1_preprod_review.zip``; long A/B and 50-ohm production runs are a
separate, explicitly approved step.
"""
from __future__ import annotations

import copy
import argparse
import hashlib
import json
import multiprocessing as mp
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np

from ..core.metrics import search_grid
from ..core.models import BOUNDS
from ..io.config import load_experiment_config, load_study_config
from ..optimizers.lshade import LShadeBackend, parent_midpoint_repair, shade_success_memory
from ..optimizers.selection import DEFAULT_COMPARATOR, time_to_target
from .convergence import normalize_convergence_config
from .optimizer_ab import (
    evaluate_promotion_gate,
    evaluator_factory,
    lshade_exchange_at_checkpoint,
)
from ..optimization.runner import optimize_one

_evaluate_promotion_gate = evaluate_promotion_gate
_evaluator_factory = evaluator_factory
_lshade_exchange_at_checkpoint = lshade_exchange_at_checkpoint


STAGE331_TYPE = "stage3_3_1_preproduction"


def _safe(value):
    """Convert NumPy/non-finite values to review-safe JSON values."""
    if isinstance(value, np.ndarray):
        return [_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _safe(value.item())
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    return value


def _save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_safe(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_hash(repo: Path):
    digest = hashlib.sha256()
    for path in sorted((repo / "src").rglob("*.py")):
        digest.update(path.relative_to(repo / "src").as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


SOURCE_HASH_CHECKPOINT_NAMES = (
    "source_hash_before_preflight",
    "source_hash_after_invariants",
    "source_hash_after_regression",
    "source_hash_after_smoke",
    "source_hash_before_bundle",
    "bundle_source_hash",
)


def evaluate_source_hash_gate(checkpoints):
    """Return the immutable-source gate result for a preflight run.

    This helper is intentionally independent of filesystem access so a
    source-edit fixture can prove that a run is invalidated before any
    performance result is interpreted.
    """
    checkpoints = dict(checkpoints or {})
    missing = [name for name in SOURCE_HASH_CHECKPOINT_NAMES if not checkpoints.get(name)]
    values = [checkpoints[name] for name in SOURCE_HASH_CHECKPOINT_NAMES if checkpoints.get(name)]
    consistent = bool(not missing and values and len(set(values)) == 1)
    return {
        "passed": consistent,
        "production_allowed": False,
        "source_hash_consistent": consistent,
        "missing_checkpoints": missing,
        "checkpoints": checkpoints,
        "message": (
            "source hash freeze passed"
            if consistent else "PREPROD INVALIDATED: SOURCE CHANGED DURING VALIDATION"
        ),
    }


def _git(repo: Path, args):
    try:
        return subprocess.check_output(
            ["git", *args], cwd=repo, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"git unavailable: {exc}"


def freeze_baseline(repo: Path, cfg, out: Path):
    """Capture the immutable Stage 3.3 baseline and machine information."""
    inputs = cfg.get("inputs", {})
    manifest = {
        "study_type": STAGE331_TYPE,
        "captured_at_unix": time.time(),
        "git_commit": _git(repo, ["rev-parse", "HEAD"]),
        "git_branch": _git(repo, ["branch", "--show-current"]),
        "git_status": _git(repo, ["status", "--short"]),
        "git_diff_sha256": hashlib.sha256(_git(repo, ["diff", "--binary"]).encode("utf-8")).hexdigest(),
        "source_sha256": _source_hash(repo),
        "config_inputs": {
            name: hashlib.sha256(str(text).encode("utf-8")).hexdigest()
            for name, text in inputs.items()
        },
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "policy": {
            "historical_stage3_3_lshade_comparison": "invalid_for_promotion",
            "long_production_started": False,
        },
    }
    _save(out / "baseline_manifest.json", manifest)
    (out / "environment").mkdir(exist_ok=True)
    (out / "environment" / "python.txt").write_text(sys.version, encoding="utf-8")
    (out / "environment" / "platform.txt").write_text(platform.platform(), encoding="utf-8")
    (out / "environment" / "numpy.txt").write_text(np.__version__, encoding="utf-8")
    (out / "environment" / "git_diff.patch").write_text(_git(repo, ["diff", "--binary"]) + "\n", encoding="utf-8")
    return manifest


def _synthetic_evaluator(vector):
    value = float(np.sum((np.asarray(vector, dtype=float) - 0.37) ** 2))
    return {
        "feasible": True,
        "max_violation": 0.0,
        "sum_violation": 0.0,
        "violations": {},
        "metrics": {"worst_il_db": value, "ripple_db": value / 2.0},
    }


def _synthetic_backend(seed, *, bounds=((0.0, 1.0),) * 3, config=None,
                       integer_indices=(), canonicalizer=None):
    values = {"initial_population": 8, "min_population": 4, "history_size": 4,
              "total_budget": 100, "hard_max_budget": 4000,
              "population_schedule_terminal_budget": 4000,
              "memory_update_batch_size": 8}
    values.update(config or {})
    return LShadeBackend(bounds, seed=seed, config=values,
                         integer_indices=integer_indices,
                         canonicalizer=canonicalizer)


def _fixed_population():
    return np.asarray([
        [0.05, 0.15, 0.25], [0.15, 0.25, 0.35],
        [0.25, 0.35, 0.45], [0.35, 0.45, 0.55],
        [0.45, 0.55, 0.65], [0.55, 0.65, 0.75],
        [0.65, 0.75, 0.85], [0.75, 0.85, 0.95],
    ])


def _state_json(state):
    return json.dumps(_safe(state), sort_keys=True, separators=(",", ":"))


def run_optimizer_invariants():
    """Run the synthetic correctness fixtures required by the handoff."""
    results = {}

    backend = _synthetic_backend(7, config={"total_budget": 100})
    backend.initialize(_synthetic_evaluator, population=_fixed_population())
    summary = backend.advance_to_unique_budget(100)
    results["exact_unique_budget"] = {
        "passed": summary["unique_evaluations"] == 100,
        "requested": 100, "actual": summary["unique_evaluations"],
        "proposals_total": summary["proposals_total"],
    }

    def integer_canonicalizer(vector):
        value = np.rint(np.asarray(vector, dtype=float))
        return value, tuple(value.tolist())

    duplicate_backend = LShadeBackend(
        [(0, 2), (0, 2)], seed=3,
        config={"initial_population": 4, "min_population": 4, "total_budget": 12,
                "max_duplicate_retries": 2},
        integer_indices=(0, 1), canonicalizer=integer_canonicalizer,
    )
    duplicate_backend.initialize(
        lambda x: {"feasible": True, "max_violation": 0.0, "sum_violation": 0.0,
                   "violations": {}, "metrics": {"worst_il_db": float(np.sum(x))}},
        population=np.asarray([[0.01, 0.01], [0.49, 0.49], [0.99, 0.99], [0.01, 0.99]]),
    )
    duplicate_summary = duplicate_backend.advance_to_unique_budget(8)
    results["duplicate_retry"] = {
        "passed": duplicate_summary["unique_evaluations"] == 8,
        "actual": duplicate_summary["unique_evaluations"],
        "duplicate_count": duplicate_summary["duplicate_count"],
    }

    exhausted = LShadeBackend(
        [(0, 1), (0, 1)], seed=4,
        config={"initial_population": 4, "min_population": 4, "total_budget": 5},
        integer_indices=(0, 1), canonicalizer=integer_canonicalizer,
    )
    exhausted.initialize(
        lambda x: {"feasible": True, "max_violation": 0.0, "sum_violation": 0.0,
                   "violations": {}, "metrics": {"worst_il_db": float(np.sum(x))}},
        population=np.asarray([[0, 0], [0, 1], [1, 0], [1, 1]], dtype=float),
    )
    exhausted_summary = exhausted.advance_to_unique_budget(5)
    results["formal_search_space_exhaustion"] = {
        "passed": exhausted_summary["search_space_exhausted"] and exhausted_summary["unique_evaluations"] == 4,
        "actual": exhausted_summary["unique_evaluations"],
        "search_space_exhausted": exhausted_summary["search_space_exhausted"],
    }

    schedule = _synthetic_backend(9, config={"total_budget": 4000,
                                              "hard_max_budget": 4000,
                                              "population_schedule_terminal_budget": 4000})
    schedule.initialize(_synthetic_evaluator, population=_fixed_population())
    schedule_sizes = {str(budget): schedule.population_size_for_budget(budget)
                      for budget in (0, 1000, 2000, 4000)}
    results["population_schedule"] = {
        "passed": schedule_sizes["0"] == 8 and schedule_sizes["4000"] == 4
        and schedule_sizes["0"] > schedule_sizes["1000"] > schedule_sizes["2000"] > schedule_sizes["4000"],
        "terminal_budget": schedule.population_schedule_terminal_budget,
        "sizes": schedule_sizes,
    }

    def make_trajectory():
        value = _synthetic_backend(17, config={"total_budget": 4000,
                                                "hard_max_budget": 4000,
                                                "population_schedule_terminal_budget": 4000})
        value.initialize(_synthetic_evaluator, population=_fixed_population())
        return value

    direct = make_trajectory()
    direct.advance_to_unique_budget(4000)
    checkpoint_observations = make_trajectory()
    for budget in (1000, 2000, 4000):
        checkpoint_observations.advance_to_unique_budget(budget)
    results["checkpoint_observation_equivalence"] = {
        "passed": _state_json(direct.state_dict()) == _state_json(checkpoint_observations.state_dict()),
        "direct_unique": direct.unique_evaluations,
        "checkpoint_unique": checkpoint_observations.unique_evaluations,
    }

    split = make_trajectory()
    split.advance_to_unique_budget(2000)
    state = split.save_state()
    resumed = make_trajectory()
    resumed.load_state(state)
    resumed.set_evaluator(_synthetic_evaluator)
    resumed.advance_to_unique_budget(4000)
    results["save_load_resume_equivalence"] = {
        "passed": _state_json(direct.state_dict()) == _state_json(resumed.state_dict()),
        "direct_unique": direct.unique_evaluations,
        "resumed_unique": resumed.unique_evaluations,
    }

    fixture_f, fixture_cr = shade_success_memory([0.2, 0.8], [0.1, 0.8], [1.0, 2.0])
    results["shade_memory_fixture"] = {
        "passed": np.isclose(fixture_f, 0.7333333333333333)
        and np.isclose(fixture_cr, 0.5666666666666667),
        "m_f": fixture_f, "m_cr": fixture_cr,
    }

    archive = make_trajectory()
    archive._archive_insert(archive.population()[0])
    archive._archive_insert(archive.population()[1])
    before_trim = len(archive._archive)
    archive._trim_archive(1)
    results["archive_rules"] = {
        "passed": before_trim == 2 and len(archive._archive) == 1,
        "inserted": before_trim, "after_trim": len(archive._archive),
    }

    repaired, events = parent_midpoint_repair(np.asarray([-0.5, 1.5, 0.4]),
                                               np.asarray([0.2, 0.6, 0.4]))
    results["parent_boundary_repair"] = {
        "passed": np.all((repaired >= 0) & (repaired <= 1))
        and np.allclose(repaired, [0.1, 0.8, 0.4])
        and events == {"lower": [0], "upper": [1]},
        "repaired": repaired.tolist(), "events": events,
    }

    feasible = {"feasible": True, "max_violation": 0.0, "violations": {},
                "metrics": {"worst_il_db": 10.0}}
    infeasible = {"feasible": False, "max_violation": 0.01,
                  "violations": {"il": 0.01}, "metrics": {"worst_il_db": 0.1}}
    results["feasibility_comparator"] = {
        "passed": DEFAULT_COMPARATOR.better(feasible, infeasible),
    }

    target = {"feasible": True, "max_violation": 0.0, "violations": {},
              "metrics": {"worst_il_db": 1.0, "ripple_db": 0.1}}
    target_key = list(DEFAULT_COMPARATOR.rank_key(target))
    metric = time_to_target([
        {"unique_evaluation": 4, "rank_key": [0.0, 2.0, 0.1, 0.0, 0.0]},
        {"unique_evaluation": 7, "rank_key": target_key},
    ], target, requested_unique_budget=20)
    results["time_to_target_fixture"] = {
        "passed": metric.get("status") == "reached"
        and metric.get("evals_to_target") == 7
        and np.isclose(metric.get("eval_fraction_to_target"), 0.35),
        **metric,
    }

    # Stale-incumbent fixture: A is best on the old grid, B is best after the
    # refresh.  The refresh must not let A survive merely because it won on v1.
    grid_state = {"new": False}

    def grid_evaluator(vector):
        value = float(
            2.0 if grid_state["new"] and vector[0] == 0.0
            else 1.0 if grid_state["new"]
            else 0.0 if vector[0] == 0.0
            else 0.5
        )
        return {"feasible": True, "max_violation": 0.0,
                "sum_violation": 0.0, "violations": {},
                "metrics": {"worst_il_db": value}}

    grid_backend = LShadeBackend(
        [(0, 1)], seed=31,
        config={"initial_population": 4, "min_population": 4,
                "total_budget": 4, "canonical_space_size": 100},
        integer_indices=(),
    )
    grid_backend.initialize(
        grid_evaluator, population=np.asarray([[0.0], [0.5], [0.2], [0.8]])
    )
    grid_state["new"] = True
    grid_backend.exchange_frequency_grid([2.0], grid_evaluator, version=2)
    results["grid_exchange_rebuilds_incumbent"] = {
        "passed": grid_backend.incumbent()["metrics"]["worst_il_db"] == 1.0
        and grid_backend.best_so_far_trace[-1]["frequency_grid_version"] == 2,
        "incumbent_metric": grid_backend.incumbent()["metrics"]["worst_il_db"],
        "frequency_grid_version": grid_backend.frequency_grid_version,
    }

    budget_gate_summary = {
        "wirings": ["center_outer_same"], "budgets": [4000],
        "budget_summary": {
            "scipy_de_legacy": {"center_outer_same": {"4000": {
                "budget_completion_passed": False,
                "search_space_exhausted_seed_count": 0,
            }}},
            "lshade": {"center_outer_same": {"4000": {
                "budget_completion_passed": True,
                "search_space_exhausted_seed_count": 0,
            }}},
        },
        "promotion_gate": {},
    }
    results["ab_gate_rejects_budget_shortfall"] = {
        "passed": _evaluate_promotion_gate(budget_gate_summary)["decision"]
        == "invalid_ab_due_to_budget_shortfall",
        "decision": _evaluate_promotion_gate(budget_gate_summary)["decision"],
    }

    results["source_hash_change_invalidates_preprod"] = {
        "passed": not evaluate_source_hash_gate({
            name: ("changed" if name == "bundle_source_hash" else "same")
            for name in SOURCE_HASH_CHECKPOINT_NAMES
        })["passed"],
    }

    adaptation = _synthetic_backend(29, config={
        "total_budget": 80, "hard_max_budget": 80,
        "population_schedule_terminal_budget": 80,
        "memory_update_batch_size": 4,
    })
    adaptation.initialize(_synthetic_evaluator, population=_fixed_population())
    adaptation.advance_to_unique_budget(80)
    results["success_memory_adaptation"] = {
        "passed": bool(
            any(not np.isclose(value, .5) for value in adaptation.m_f)
            or any(not np.isclose(value, .5) for value in adaptation.m_cr)
        ),
        "m_f": adaptation.m_f.tolist(), "m_cr": adaptation.m_cr.tolist(),
    }

    failed = [name for name, value in results.items() if not value.get("passed", False)]
    return {"passed": not failed, "failed": failed, "cases": results}


def _synthetic_worker(payload):
    seed, budget = payload
    backend = _synthetic_backend(int(seed), config={"total_budget": int(budget),
                                                     "hard_max_budget": int(budget),
                                                     "population_schedule_terminal_budget": int(budget)})
    backend.initialize(_synthetic_evaluator, population=_fixed_population())
    backend.advance_to_unique_budget(int(budget))
    return {"seed": int(seed), "rank_key": list(DEFAULT_COMPARATOR.rank_key(backend.incumbent())),
            "population": backend.population().tolist(),
            "unique_evaluations": backend.unique_evaluations}


def run_parallel_parity(out: Path, *, seeds=(20260909, 20260910), budget=80,
                        worker_counts=None):
    """Benchmark spawn workers and compare each seed against workers=1."""
    if worker_counts is None:
        worker_counts = (1, 2, 4, 5)
    results, baseline = {}, None
    for requested in worker_counts:
        workers = max(1, int(requested))
        started = time.time()
        payloads = [(int(seed), int(budget)) for seed in seeds]
        if workers == 1:
            records = [_synthetic_worker(payload) for payload in payloads]
        else:
            with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as pool:
                records = list(pool.map(_synthetic_worker, payloads))
        records.sort(key=lambda item: item["seed"])
        signature = [(row["seed"], row["rank_key"], row["population"]) for row in records]
        if baseline is None:
            baseline = signature
        results[str(workers)] = {
            "workers": workers, "budget": int(budget), "seed_count": len(records),
            "wall_time_s": time.time() - started,
            "seed_result_parity": signature == baseline,
            "per_seed_elapsed_not_applicable": True,
        }
    baseline_wall = results[str(max(1, int(worker_counts[0])))] ["wall_time_s"]
    for item in results.values():
        item["speedup_vs_workers_1"] = baseline_wall / max(item["wall_time_s"], np.finfo(float).tiny)
        item["parallel_efficiency"] = item["speedup_vs_workers_1"] / max(item["workers"], 1)
    stable = [item for item in results.values() if item["seed_result_parity"]]
    selected = min(stable, key=lambda item: item["wall_time_s"])["workers"] if stable else None
    report = {
        "executed": True, "backend": "lshade_synthetic", "seeds": [int(seed) for seed in seeds],
        "worker_counts": [int(value) for value in worker_counts], "workers": results,
        "selected_workers": selected,
        "selection_reason": "fastest configuration with exact seed parity" if selected is not None else "no parity-preserving configuration",
        "mp_context": "spawn", "blas_threads_per_worker": 1,
        "environment_policy": {name: "1" for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
    }
    _save(out / "parallel_parity_timing.json", report)
    return report


def run_saw_smoke(out: Path, cfg):
    """Run the small real 50-ohm smoke case with one checkpoint/resume."""
    section = cfg.get("stage3_3_1", {})
    fix_section = cfg.get("stage3_3_1a", {})
    tiny_section = fix_section.get("tiny_smoke", {})
    legacy_section = cfg.get("stage3_3", {})
    seeds = [int(seed) for seed in tiny_section.get(
        "seeds", section.get("tiny_smoke_seeds", [20260909, 20260910])
    )]
    budget = int(tiny_section.get(
        "unique_budget", section.get("tiny_smoke_unique_budget", 200)
    ))
    checkpoint_budget = max(1, budget // 2)
    wiring = str(tiny_section.get(
        "wiring", section.get("tiny_smoke_wiring", "center_outer_same")
    ))
    z0 = float(cfg.get("convergence", {}).get("impedance_ohm", 50.0))
    frequencies = np.unique(search_grid(cfg["spec"], cfg))
    smoke_cfg = copy.deepcopy(cfg)
    smoke_cfg.setdefault("stage3_3", {})["adaptive_frequency_exchange"] = True
    lshade = dict(legacy_section.get("lshade", {}))
    lshade.update({
        "total_budget": budget, "hard_max_budget": budget,
        "population_schedule_terminal_budget": budget,
        "initial_population": int(lshade.get("initial_population_per_dimension", 18)) * len(BOUNDS),
    })
    rows, traces = [], {}
    started_all = time.time()
    for index, seed in enumerate(seeds):
        started = time.time()

        def make_backend(evaluator):
            value = LShadeBackend(
                BOUNDS, seed=seed, config=lshade,
                integer_indices=(1, 2, 3), comparator=DEFAULT_COMPARATOR,
            )
            value.initialize(evaluator)
            value.set_frequency_grid(evaluator.frequency_ref[0], version=1)
            return value

        def run_trajectory():
            local_frequencies = np.unique(search_grid(smoke_cfg["spec"], smoke_cfg))
            local_evaluator = _evaluator_factory(smoke_cfg, z0, wiring, local_frequencies)
            value = make_backend(local_evaluator)
            value.advance_to_unique_budget(checkpoint_budget)
            events = [_lshade_exchange_at_checkpoint(
                value, local_evaluator, smoke_cfg, wiring, z0, checkpoint_budget
            )]
            checkpoint_summaries = [{
                "checkpoint_budget": checkpoint_budget,
                **value.summary(),
            }]
            value.advance_to_unique_budget(budget)
            events.append(_lshade_exchange_at_checkpoint(
                value, local_evaluator, smoke_cfg, wiring, z0, budget
            ))
            checkpoint_summaries.append({
                "checkpoint_budget": budget,
                **value.summary(),
            })
            return value, events, checkpoint_summaries

        if index == 0:
            baseline_backend, baseline_events, _baseline_summaries = run_trajectory()
            checkpoint = make_backend(_evaluator_factory(
                smoke_cfg, z0, wiring, frequencies
            ))
            # Save/load at the checkpoint before the adaptive exchange, then
            # continue on the same newly exchanged grid.
            checkpoint.advance_to_unique_budget(checkpoint_budget)
            checkpoint_state = checkpoint.save_state()
            resumed = LShadeBackend(
                BOUNDS, seed=seed, config=lshade,
                integer_indices=(1, 2, 3), comparator=DEFAULT_COMPARATOR,
            )
            resumed.load_state(checkpoint_state)
            resumed_evaluator = _evaluator_factory(smoke_cfg, z0, wiring, frequencies)
            resumed.set_evaluator(resumed_evaluator)
            resumed_evaluator.frequency_ref[0] = np.asarray(
                resumed.active_frequency_grid, dtype=float
            )
            resumed_events = [_lshade_exchange_at_checkpoint(
                resumed, resumed_evaluator, smoke_cfg, wiring, z0, checkpoint_budget
            )]
            checkpoint_summaries = [{
                "checkpoint_budget": checkpoint_budget,
                **resumed.summary(),
            }]
            resumed.advance_to_unique_budget(budget)
            resumed_events.append(_lshade_exchange_at_checkpoint(
                resumed, resumed_evaluator, smoke_cfg, wiring, z0, budget
            ))
            checkpoint_summaries.append({
                "checkpoint_budget": budget,
                **resumed.summary(),
            })
            checkpoint_parity = _state_json(baseline_backend.state_dict()) == _state_json(resumed.state_dict())
            backend, frequency_events = resumed, resumed_events
        else:
            backend, frequency_events, checkpoint_summaries = run_trajectory()
            checkpoint_parity = True
        elapsed = time.time() - started
        summary = backend.summary()
        row = {
            "algorithm": "lshade",
            "seed": seed, "wiring": wiring, "resistance_ohm": z0,
            "requested_unique_budget": budget,
            "actual_unique_budget": int(summary["unique_evaluations"]),
            "budget_completion_fraction": float(summary["unique_evaluations"] / budget),
            "budget_passed": bool(summary["unique_evaluations"] >= budget),
            "stop_reason": (
                "requested_budget_reached"
                if summary["unique_evaluations"] >= budget
                else "search_space_exhausted"
                if summary.get("search_space_exhausted")
                else "numerical_failure"
            ),
            "checkpoint_resume_parity": checkpoint_parity,
            "duplicate_count": int(summary["duplicate_count"]),
            "proposals_total": int(summary["proposals_total"]),
            "cache_hits": int(summary["cache_hits"]),
            "population_size": int(summary["population_size"]),
            "best_so_far_trace": summary["best_so_far_trace"],
            "population_trace": summary["population_trace"],
            "archive_trace": summary.get("archive_trace", []),
            "m_f": summary["m_f"], "m_cr": summary["m_cr"],
            "archive_size": int(summary["archive_size"]),
            "wall_time_s": elapsed,
            "frequency_point_solves_estimate": int(
                summary["unique_evaluations"] * len(backend.active_frequency_grid)
            ),
            "frequency_count": int(len(backend.active_frequency_grid)),
            "frequency_grid_version": int(backend.frequency_grid_version),
            "frequency_grid_events": frequency_events,
            "checkpoint_state_summaries": checkpoint_summaries,
            "incumbent": summary["incumbent"],
        }
        rows.append(row)
        traces[str(seed)] = {
            "best_so_far_trace": summary["best_so_far_trace"],
            "population_trace": summary["population_trace"],
            "archive_trace": summary.get("archive_trace", []),
            "frequency_grid_events": frequency_events,
            "checkpoint_state_summaries": checkpoint_summaries,
        }

    # Legacy DE is intentionally run through the historical orchestration for
    # the same tiny terminal budget.  Its budget accounting is part of the
    # correctness gate; it is not used to replace the legacy optimizer.
    legacy_cfg = copy.deepcopy(smoke_cfg)
    legacy_cfg["max_unique_decoded_evaluations"] = budget
    legacy_cfg.setdefault("optimizer", {})["max_unique_decoded_evaluations"] = budget
    legacy_cfg["optimizer"]["warm_resume"] = False
    legacy_cfg["convergence"]["benchmark_early_stop"] = False
    legacy_out = out / "legacy_smoke_trials"
    legacy_out.mkdir(parents=True, exist_ok=True)
    legacy_rows = []
    for seed in seeds:
        try:
            legacy = optimize_one(
                legacy_out, legacy_cfg, z0, z0, seed, neighbor=None,
                wiring=wiring, mode="benchmark", run_label="legacy_smoke",
                warm_resume=False,
            )
            actual = int(legacy.get("unique_decoded_evaluations", 0))
            requested = int(legacy.get("requested_unique_design_budget", budget))
            legacy_rows.append({
                "algorithm": "scipy_de_legacy", "seed": seed, "wiring": wiring,
                "resistance_ohm": z0, "requested_unique_budget": requested,
                "actual_unique_budget": actual,
                "budget_completion_fraction": float(actual / max(requested, 1)),
                "budget_passed": bool(actual >= .98 * requested),
                "stop_reason": legacy.get("stop_reason"),
                "frequency_grid_events": legacy.get("frequency_grid_events", []),
                "frequency_grid_version": int(len(legacy.get("frequency_grid_events", [])) + 1),
                "incumbent": legacy,
            })
        except Exception as exc:
            legacy_rows.append({
                "algorithm": "scipy_de_legacy", "seed": seed, "wiring": wiring,
                "resistance_ohm": z0, "requested_unique_budget": budget,
                "actual_unique_budget": 0, "budget_completion_fraction": 0.0,
                "budget_passed": False, "stop_reason": "numerical_failure",
                "error": str(exc),
            })
    rows.extend(legacy_rows)
    _save(out / "budget_completion_table.json", [
        {
            "algorithm": row.get("algorithm"), "seed": row.get("seed"),
            "wiring": row.get("wiring"),
            "requested_unique_budget": row.get("requested_unique_budget"),
            "actual_unique_budget": row.get("actual_unique_budget"),
            "budget_completion_fraction": row.get("budget_completion_fraction"),
            "budget_passed": row.get("budget_passed"),
            "search_space_exhausted": row.get("search_space_exhausted", False),
            "stop_reason": row.get("stop_reason"),
        }
        for row in rows
    ])
    _save(out / "frequency_grid_event_table.json", [
        {
            "algorithm": row.get("algorithm"), "seed": row.get("seed"),
            "wiring": row.get("wiring"), **event,
        }
        for row in rows for event in row.get("frequency_grid_events", [])
    ])
    _save(out / "checkpoint_state_summaries.json", [
        {
            "algorithm": row.get("algorithm"), "seed": row.get("seed"),
            "wiring": row.get("wiring"), **checkpoint,
        }
        for row in rows for checkpoint in row.get("checkpoint_state_summaries", [])
    ])
    smoke = {
        "stage": STAGE331_TYPE, "wiring": wiring, "resistance_ohm": z0,
        "seeds": seeds, "requested_unique_budget": budget,
        "checkpoint_budget": checkpoint_budget, "frequency_count": len(frequencies),
        "rows": rows, "legacy_rows": legacy_rows, "elapsed_s": time.time() - started_all,
        "passed": (
            all(row["budget_passed"] and row["checkpoint_resume_parity"]
                for row in rows if row.get("algorithm") == "lshade")
            and all(row["budget_passed"] for row in legacy_rows)
        ),
    }
    _save(out / "saw_smoke_results.json", smoke)
    _save(out / "saw_smoke_traces.json", traces)
    return smoke


def run_full_test_suite(repo: Path, out: Path):
    """Run the canonical full pytest suite and persist its log."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo / "src")
    command = [sys.executable, "-m", "pytest", "-q"]
    started = time.time()
    result = subprocess.run(command, cwd=repo, env=env, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    log = (result.stdout or "") + (result.stderr or "")
    (out / "tests").mkdir(parents=True, exist_ok=True)
    (out / "tests" / "full_test_log.txt").write_text(log, encoding="utf-8")
    summary = {
        "command": "PYTHONPATH=src python -m pytest -q",
        "exit_code": int(result.returncode), "passed": result.returncode == 0,
        "elapsed_s": time.time() - started,
    }
    _save(out / "tests" / "test_summary.json", summary)
    return summary


def _copy_tree_files(source_root: Path, destination_root: Path, suffixes=None):
    if not source_root.exists():
        return
    for source in sorted(source_root.rglob("*")):
        if not source.is_file() or (suffixes and source.suffix.lower() not in suffixes):
            continue
        destination = destination_root / source.relative_to(source_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def create_preprod_bundle(repo: Path, run: Path):
    """Create, clean-extract-test and hash-verify the mandatory review ZIP."""
    output = run / "stage3_3_1_preprod_review.zip"
    with tempfile.TemporaryDirectory(prefix="stage331_bundle_", dir=str(run)) as temp_name:
        staging = Path(temp_name) / "bundle"
        staging.mkdir(parents=True)
        _copy_tree_files(repo / "src", staging / "src", {".py"})
        _copy_tree_files(repo / "tests", staging / "tests", {".py"})
        _copy_tree_files(repo / "configs", staging / "configs")
        _copy_tree_files(repo / "experiments", staging / "experiments")
        _copy_tree_files(repo / "codex_stage331_handoff", staging / "handoff")
        _copy_tree_files(
            repo / "saw_com_codex_stage3_3_1a_fix_handoff", staging / "handoff"
        )
        shutil.copy2(repo / "pyproject.toml", staging / "pyproject.toml")
        for source in sorted(run.rglob("*")):
            if (not source.is_file() or output == source or staging in source.parents
                    or source.name == output.name):
                continue
            relative = source.relative_to(run)
            destination = (staging / relative
                           if relative.parts and relative.parts[0] == "tests"
                           else staging / "results" / relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        # Keep the review entry points at stable bundle-root paths as well as
        # under results/, so a reviewer does not need to reconstruct the run
        # directory layout.
        for name in ("baseline_manifest.json", "preflight_summary.json", "stage331_manifest.json"):
            source = run / name
            if source.exists():
                shutil.copy2(source, staging / name)
        (staging / "REVIEW_ME.md").write_text(
            "# Stage 3.3.1 pre-production review\n\n"
            "This bundle is the mandatory one-time gate for the corrected L-SHADE engine.\n"
            "The Stage 3.3.1 run stops here; no long A/B or 50-ohm production run is included.\n\n"
            "## Reproduce from a clean extraction\n\n"
            "```powershell\n"
            "$env:PYTHONPATH = (Join-Path (Get-Location) 'src')\n"
            "python -m pytest -q\n"
            "```\n\n"
            "Review `results/preflight_summary.json`, `results/saw_smoke_results.json`, "
            "`results/parallel_parity_timing.json`, and `tests/full_test_log.txt`.\n"
            "`center_outer_same` is a wiring mode, not a geometry-sharing switch.\n",
            encoding="utf-8",
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = str(staging / "src")
        command = [sys.executable, "-m", "pytest", "-q"]
        started = time.time()
        result = subprocess.run(command, cwd=staging, env=env, capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
        clean_log = (result.stdout or "") + (result.stderr or "")
        (staging / "tests" / "clean_extract_test_log.txt").write_text(clean_log, encoding="utf-8")
        clean_summary = {
            "command": "PYTHONPATH=src python -m pytest -q",
            "exit_code": int(result.returncode), "passed": result.returncode == 0,
            "elapsed_s": time.time() - started,
        }
        (staging / "tests" / "clean_extract_test_summary.json").write_text(
            json.dumps(clean_summary, indent=2) + "\n", encoding="utf-8"
        )
        files = []
        for source in sorted(path for path in staging.rglob("*") if path.is_file()):
            relative = source.relative_to(staging).as_posix()
            files.append({"path": relative, "sha256": _sha256(source), "bytes": source.stat().st_size})
        manifest = {
            "bundle_format_version": 1, "study_type": STAGE331_TYPE,
            "source_sha256": _source_hash(repo), "clean_extract_test": clean_summary,
            "files": files,
        }
        (staging / "bundle_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            for source in sorted(path for path in staging.rglob("*") if path.is_file()):
                archive.write(source, source.relative_to(staging).as_posix())
        with ZipFile(output) as archive:
            names = set(archive.namelist())
            for item in files:
                if item["path"] not in names or hashlib.sha256(archive.read(item["path"])).hexdigest() != item["sha256"]:
                    raise RuntimeError(f"pre-production bundle hash failure: {item['path']}")
        _save(run / "bundle_self_test.json", {
            "zip": output.name, "clean_extract_test": clean_summary,
            "hashed_file_count": len(files), "sha256_verification": True,
        })
    return output


def run_preproduction(config_path, run_path):
    repo = Path(__file__).resolve().parents[3]
    run = Path(run_path).resolve()
    run.mkdir(parents=True, exist_ok=True)
    raw = load_experiment_config(config_path)
    cfg = normalize_convergence_config(raw)
    cfg.setdefault("stage3_3_1", {})
    cfg["stage3_3_1"].setdefault("tiny_smoke_seeds", [20260909, 20260910])
    cfg["stage3_3_1"].setdefault("tiny_smoke_unique_budget", 200)
    cfg["stage3_3_1"].setdefault("tiny_smoke_wiring", "center_outer_same")
    started = time.time()
    source_hashes = {
        "source_hash_before_preflight": _source_hash(repo),
    }
    baseline = freeze_baseline(repo, cfg, run)
    blocking_checks = []

    invariants = run_optimizer_invariants()
    _save(run / "tests" / "optimizer_invariants.json", invariants)
    source_hashes["source_hash_after_invariants"] = _source_hash(repo)
    if not invariants["passed"]:
        blocking_checks.extend(f"invariant:{name}" for name in invariants["failed"])

    tests = run_full_test_suite(repo, run)
    source_hashes["source_hash_after_regression"] = _source_hash(repo)
    if not tests["passed"]:
        blocking_checks.append("full_regression")

    smoke = run_saw_smoke(run, cfg)
    source_hashes["source_hash_after_smoke"] = _source_hash(repo)
    if not smoke["passed"]:
        blocking_checks.append("tiny_saw_smoke")

    parity_cfg = cfg.get("stage3_3_1a", {}).get("parallel_parity", {})
    parallel = run_parallel_parity(
        run,
        seeds=tuple(smoke.get("seeds", [20260909, 20260910])),
        worker_counts=tuple(parity_cfg.get("worker_counts", (1, 2))),
    )
    parity_passed = all(item["seed_result_parity"] for item in parallel["workers"].values())
    if not parity_passed:
        blocking_checks.append("serial_process_parity")

    source_hashes["source_hash_before_bundle"] = _source_hash(repo)
    # The bundle builder copies source files without modifying them.  The
    # immediate post-build check below confirms this expected hash.
    source_hashes["bundle_source_hash"] = source_hashes["source_hash_before_bundle"]
    source_gate = evaluate_source_hash_gate(source_hashes)
    if not source_gate["passed"]:
        blocking_checks.append("source_hash_consistency")
    _save(run / "source_hash_checkpoints.json", source_gate)

    preflight = {
        "study_type": STAGE331_TYPE, "passed": bool(not blocking_checks),
        "elapsed_s": time.time() - started,
        "baseline_manifest": "baseline_manifest.json",
        "mandatory_invariants": invariants,
        "full_regression": tests,
        "saw_smoke": {"passed": smoke["passed"], "seed_count": len(smoke["seeds"]),
                       "budget": smoke["requested_unique_budget"]},
        "parallel_parity": {"passed": parity_passed, "worker_counts": parallel["worker_counts"],
                            "selected_workers": parallel.get("selected_workers")},
        "blocking_checks": blocking_checks,
        "source_hash_checkpoints": source_gate["checkpoints"],
        "source_hash_consistent": bool(source_gate["passed"]),
        "budget_completion_passed": bool(smoke.get("passed", False)),
        "frequency_exchange_passed": bool(smoke.get("passed", False)),
        "trajectory_passed": bool(smoke.get("passed", False)),
        "production_allowed": False,
        "human_review_required": True,
        "stop_reason": "mandatory human review gate; wait for explicit GO",
    }
    preflight["review_bundle"] = "stage3_3_1_preprod_review.zip"
    _save(run / "preflight_summary.json", preflight)
    _save(run / "stage331_manifest.json", {
        "study_type": STAGE331_TYPE, "baseline": baseline,
        "preflight": "preflight_summary.json", "review_bundle": preflight["review_bundle"],
        "production_started": False, "selected_worker_count": parallel.get("selected_workers"),
        "manual_gate": "STOP until explicit GO",
        "source_hash_checkpoints": "source_hash_checkpoints.json",
    })
    bundle = create_preprod_bundle(repo, run)
    source_hashes["bundle_source_hash"] = _source_hash(repo)
    source_gate = evaluate_source_hash_gate(source_hashes)
    if not source_gate["passed"]:
        if "source_hash_consistency" not in blocking_checks:
            blocking_checks.append("source_hash_consistency")
        preflight["passed"] = False
        preflight["blocking_checks"] = blocking_checks
        preflight["source_hash_checkpoints"] = source_gate["checkpoints"]
        preflight["source_hash_consistent"] = False
        _save(run / "source_hash_checkpoints.json", source_gate)
        _save(run / "preflight_summary.json", preflight)
        # Keep the invalidation visible inside the review artifact too.
        bundle = create_preprod_bundle(repo, run)
    _save(run / "stage331_manifest.json", {
        "study_type": STAGE331_TYPE, "baseline": baseline,
        "preflight": "preflight_summary.json", "review_bundle": bundle.name,
        "production_started": False, "selected_worker_count": parallel.get("selected_workers"),
        "manual_gate": "STOP until explicit GO",
        "source_hash_checkpoints": "source_hash_checkpoints.json",
    })
    return _safe({**preflight, "review_bundle_path": str(bundle)})


def main():
    parser = argparse.ArgumentParser(description="Stage 3.3.1 pre-production gate")
    parser.add_argument("--config", default="configs/studies/stage3_3_1_preprod.yaml")
    parser.add_argument("--run", default="runs/stage3_3_1_preprod")
    args = parser.parse_args()
    result = run_preproduction(args.config, args.run)
    print(json.dumps(_safe(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
