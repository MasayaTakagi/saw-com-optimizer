"""Retained Stage 4B hybrid topology contract, report helpers, and cell code.

Legacy Stage 4B launch and authorization entrypoints have been retired. The
frozen matrix and historical cell implementation remain for report/evidence
interpretation; this module is not a current study entrypoint.
"""
from __future__ import annotations

import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .hybrid import (
    stage4a_active_bound_diagnostics,
    stage4a_clean,
    stage4a_counter_snapshot,
    stage4a_evaluate,
)


STUDY_TYPE = "hybrid_stage4b_topology_comparison"
PROTOCOL_REVISION = "stage4b_hybrid_topology_production_v1"
AUTHORIZATION_SCOPE = "stage4b-hybrid-topology-production-exact-protocol-v1"
TOPOLOGIES = ("D", "P_D", "D_P", "P_D_P")
SEEDS = (20261002, 20261003, 20261004, 20261005, 20261006)
BUDGET = 24000
CHECKPOINTS = (4000, 8000, 16000, 24000)
INITIAL_POPULATION_MULTIPLIER = 18
FINALIST_COUNT = 16


def _atomic_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(stage4a_clean(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _expected_matrix(*, seeds: Sequence[int] = SEEDS, budget: int = BUDGET,
                     checkpoints: Sequence[int] = CHECKPOINTS,
                     terminal_budget: int = BUDGET) -> list[dict[str, Any]]:
    dimensions = {"D": 10, "P_D": 13, "D_P": 13, "P_D_P": 16}
    return [
        {
            "topology": topology,
            "seed": int(seed),
            "dimension": dimensions[topology],
            "initial_population": INITIAL_POPULATION_MULTIPLIER * dimensions[topology],
            "budget": int(budget),
            "population_schedule_terminal_budget": int(terminal_budget),
            "checkpoints": [int(value) for value in checkpoints],
            "cold_start": True,
            "warm_start": False,
            "parent_transfer": False,
            "topology_transfer": False,
        }
        for topology in TOPOLOGIES for seed in seeds
    ]


def _sample_stage4b_population(space, cfg, seed: int, topology: str, population_size: int):
    import hashlib as _hashlib
    from ..design.geometry import hybrid_geometry

    max_attempts = int(cfg["hybrid"]["initializer"]["max_attempts"])
    if max_attempts <= 0:
        raise ValueError("Stage 4B initializer max_attempts must be positive")
    payload = f"stage4b-v1/{int(seed)}/MLIT/{topology}/initial_population"
    sampling_seed = int.from_bytes(_hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big") % (2**32)
    rng = np.random.default_rng(sampling_seed)
    low, high = space.bounds[:, 0], space.bounds[:, 1]
    accepted: list[np.ndarray] = []
    seen: set[tuple[float, ...]] = set()
    geometry_rejections = duplicate_rejections = draws = 0
    while len(accepted) < population_size and draws < max_attempts:
        draws += 1
        canonical, key = space.canonicalize(rng.uniform(low, high))
        if key in seen:
            duplicate_rejections += 1
            continue
        candidate = space.decode(canonical, reflector_electrodes=int(
            cfg["dms_topology"]["t1_reflector_electrodes"]))
        if hybrid_geometry(candidate, cfg)["max_violation"] > 0.0:
            geometry_rejections += 1
            continue
        seen.add(key)
        accepted.append((canonical - low) / (high - low))
    stats = {
        "method": "independent_uniform_rejection_v1",
        "seed": int(seed), "topology": topology,
        "initial_sampling_seed": int(sampling_seed),
        "requested_population_size": int(population_size),
        "accepted_population_size": int(len(accepted)),
        "candidate_draws": int(draws),
        "geometry_rejections": int(geometry_rejections),
        "duplicate_rejections": int(duplicate_rejections),
        "historical_seed_count": 0,
        "warm_start": False, "parent_transfer": False, "topology_transfer": False,
    }
    if draws != len(accepted) + geometry_rejections + duplicate_rejections:
        raise AssertionError("Stage 4B initializer accounting identity failed")
    if len(accepted) != population_size:
        raise RuntimeError("Stage 4B initializer exhausted max_attempts; cell cannot cold-start")
    return np.asarray(accepted, dtype=float), stats


def _cell_paths(run: Path, topology: str, seed: int) -> tuple[Path, Path, Path]:
    cell = run / "optimization" / topology / f"seed{int(seed)}"
    return cell, cell / "cell_manifest.json", cell / "cell_result.json"


def _counter_snapshot(counters, backend, search_frequency_count: int) -> dict[str, Any]:
    snapshot = stage4a_counter_snapshot(counters, backend, search_frequency_count)
    snapshot.update({
        "validation_evaluations": int(counters.validation_evaluations),
        "validation_physics_failures": int(counters.validation_physics_failures),
        "validation_frequency_points": int(counters.validation_solved_frequency_points),
    })
    return snapshot


def _summary_record(record: Mapping[str, Any], *, source_rank: int | None = None) -> dict[str, Any]:
    keys = (
        "evaluation_status", "topology", "candidate_vector", "dms_design",
        "resonator_designs", "metrics", "violations", "feasible", "max_violation",
        "sum_violation", "objective", "search_scalar_objective", "geometry_max_violation",
        "geometry_violations", "failure_stage", "failure",
    )
    result = {key: record[key] for key in keys if key in record}
    if source_rank is not None:
        result["search_source_rank"] = int(source_rank)
    return result


def _cell_failure_payload(identity: Mapping[str, Any], exc: BaseException, *,
                          phase: str, backend: Any, last_durable_budget: int,
                          checkpoint_reference: Mapping[str, Any] | None,
                          elapsed_wall_time_s: float) -> dict[str, Any]:
    trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    message = str(exc)
    return {
        **identity,
        "status": "INCOMPLETE",
        "error": (f"{type(exc).__name__}: {message}" if message
                  else f"{type(exc).__name__}: (no message)"),
        "error_type": type(exc).__name__,
        "error_message": message,
        "error_repr": repr(exc),
        "traceback": trace,
        "failing_stage": str(phase),
        "failing_cell": {"topology": identity["topology"], "seed": int(identity["seed"])},
        "unique_evaluations": int(backend.unique_evaluations),
        "last_durable_checkpoint_budget": int(last_durable_budget),
        "checkpoint_reference": (None if checkpoint_reference is None
                                  else dict(checkpoint_reference)),
        "elapsed_wall_time_s": float(elapsed_wall_time_s),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _run_cell(
    context: Mapping[str, Any], run: Path, *, topology: str, seed: int,
    budget: int, checkpoints: Sequence[int], terminal_budget: int,
    finalist_count: int, mode: str, source_commit_sha: str,
    resume: bool, compact_history_cache: bool = False,
) -> dict[str, Any]:
    if mode == "production":
        raise RuntimeError("legacy Stage 4B production cell execution is retired")
    from ..design.topology import RESONATOR_BOUNDS
    from ..optimization.counters import GeometryGateCounters, evaluation_status
    from ..optimization.checkpoint_session import LShadeCheckpointSession
    from ..optimization.lshade import LShadeBackend
    from ..optimization.selection import GeometryFirstComparator

    cfg = context["cfg"]
    space = context["spaces"][topology]
    cell, cell_manifest_path, result_path = _cell_paths(run, topology, seed)
    cell.mkdir(parents=True, exist_ok=True)
    cell_started = time.perf_counter()
    previous_status_path = cell / "cell_status.json"
    prior_elapsed = 0.0
    if previous_status_path.is_file():
        try:
            prior_elapsed = float(_read_json(previous_status_path).get("elapsed_wall_time_s", 0.0))
        except (OSError, ValueError, TypeError):
            prior_elapsed = 0.0
    expected_population = INITIAL_POPULATION_MULTIPLIER * space.dimension
    identity = {
        "schema_version": 1,
        "topology": topology,
        "seed": int(seed),
        "dimension": int(space.dimension),
        "budget": int(budget),
        "population_schedule_terminal_budget": int(terminal_budget),
        "checkpoints": [int(value) for value in checkpoints],
        "initial_population": expected_population,
        "initial_population_rule": "18 * dimension",
        "cold_start": True,
        "warm_start": False,
        "parent_transfer": False,
        "topology_transfer": False,
        "historical_population_injection": False,
        "mode": mode,
        "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
        "source_commit_sha": source_commit_sha,
        "common_validation_grid_id": context["common_grid_id"],
    }
    if result_path.is_file():
        previous = _read_json(result_path)
        if previous.get("status") == "COMPLETED":
            if any(previous.get(key) != value for key, value in identity.items()):
                raise RuntimeError(f"completed cell identity mismatch: {topology}/seed{seed}")
            if (int(previous.get("unique_evaluations", -1)) == budget
                    and previous.get("computation_fingerprint") == identity["computation_fingerprint"]):
                return previous
            raise RuntimeError(f"completed cell is corrupt and will not be replaced: {topology}/seed{seed}")
    checkpoint_directory = cell / "checkpoints"
    legacy_checkpoint = cell / "optimizer_checkpoint.json"
    cell_manifest_exists = cell_manifest_path.is_file()
    any_cell_data = any(path.name not in {"checkpoints"} for path in cell.iterdir()) or checkpoint_directory.exists()
    if cell_manifest_exists:
        saved_identity = _read_json(cell_manifest_path)
        if any(saved_identity.get(key) != value for key, value in identity.items()):
            raise RuntimeError(f"cell manifest/fingerprint mismatch: {topology}/seed{seed}")
    elif any_cell_data:
        raise RuntimeError(f"incomplete cell lacks immutable identity; refusing replacement: {topology}/seed{seed}")
    elif resume:
        # A requested resume may encounter cells not yet dispatched. They start
        # cold under this run's immutable manifest and their own stream.
        pass
    _atomic_json(cell_manifest_path, identity)
    _atomic_json(cell / "cell_status.json", {
        **identity, "status": "RUNNING", "elapsed_wall_time_s": prior_elapsed,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    present_checkpoint_records = [
        int(point) for point in checkpoints if (cell / f"B{int(point)}.json").is_file()
    ]
    if present_checkpoint_records != list(checkpoints[:len(present_checkpoint_records)]):
        raise RuntimeError(f"cell has a non-prefix checkpoint history: {topology}/seed{seed}")

    counters = GeometryGateCounters()
    timing = {"search_evaluation_wall_time_s": 0.0, "common_validation_wall_time_s": 0.0}
    hard = np.asarray(context["t1_hard_bounds"], dtype=float)
    hybrid_hard_bounds = np.vstack([
        hard,
        *([np.asarray(RESONATOR_BOUNDS, dtype=float)] * ((space.dimension - 10) // 3)),
    ])
    lshade_config = dict(cfg["dms_topology"].get("lshade", {}))
    lshade_config.update({
        "total_budget": int(budget),
        "requested_unique_budget": int(budget),
        "hard_max_budget": int(budget),
        "population_schedule_terminal_budget": int(terminal_budget),
        "initial_population": int(expected_population),
        "min_population": 4,
        "hard_bounds": hybrid_hard_bounds.tolist(),
        "compact_history_cache": bool(compact_history_cache),
        "historical_finalist_count": int(finalist_count),
    })

    def evaluator(vector):
        candidate = space.decode(vector, reflector_electrodes=int(
            cfg["dms_topology"]["t1_reflector_electrodes"]))
        started = time.perf_counter()
        record = stage4a_evaluate(
            candidate, context["provider"], cfg, context["search_frequencies"],
            context["source_impedance_ohm"], context["load_impedance_ohm"],
        )
        timing["search_evaluation_wall_time_s"] += time.perf_counter() - started
        counters.observe_search(record, len(context["search_frequencies"]))
        return record

    backend = LShadeBackend(
        space.bounds, seed=int(seed), config=lshade_config,
        integer_indices=space.integer_indices, canonicalizer=space.canonicalize,
        comparator=GeometryFirstComparator(),
        source_config_fingerprint=context["fingerprint"]["computation_fingerprint"],
    )
    backend.set_frequency_grid(context["search_frequencies"], version=1)
    checkpoint_session = LShadeCheckpointSession(
        checkpoint_directory, run_directory=run, legacy_path=legacy_checkpoint,
        resume=cell_manifest_exists,
    )
    has_checkpoint = checkpoint_session.has_checkpoint
    phase = "checkpoint_restore" if has_checkpoint else "initialization"
    last_durable_budget = 0
    if cell_manifest_exists and not has_checkpoint:
        raise RuntimeError(f"incomplete cell has no recoverable checkpoint: {topology}/seed{seed}")
    if has_checkpoint:
        try:
            checkpoint_session.load(backend)
            backend.set_evaluator(evaluator)
            last_durable_budget = int(backend.unique_evaluations)
            extra_state = (checkpoint_session.last_load.state.get("extra_state", {})
                           if checkpoint_session.last_load is not None else {})
            counters.restore_snapshot(extra_state.get("geometry_gate_counters", {}))
            existing_rows = []
            for point in checkpoints:
                record_path = cell / f"B{int(point)}.json"
                if record_path.is_file():
                    existing_rows.append(_read_json(record_path))
            if existing_rows:
                latest = max(existing_rows, key=lambda row: int(row["checkpoint_budget"]))
                counters.restore_validation(latest.get("counters", {}))
        except BaseException as exc:
            _atomic_json(cell / "cell_status.json", _cell_failure_payload(
                identity, exc, phase=phase, backend=backend,
                last_durable_budget=last_durable_budget,
                checkpoint_reference=checkpoint_session.reference_metadata,
                elapsed_wall_time_s=prior_elapsed + time.perf_counter() - cell_started,
            ))
            raise
    else:
        if cell_manifest_exists:
            raise RuntimeError(f"new cell already has an identity manifest: {topology}/seed{seed}")
        try:
            population, sampling = _sample_stage4b_population(
                space, cfg, seed, topology, expected_population,
            )
            if len(population) != expected_population:
                raise RuntimeError("dimension-scaled initial population shortfall")
            counters.initial_sampling = sampling
            _atomic_json(cell / "initializer.json", sampling)
            backend.initialize(evaluator, population=population)
            if backend.unique_evaluations != expected_population:
                raise RuntimeError("initial population did not decode to the expected unique size")
            # Preserve a recoverable optimizer state before the first scheduled
            # checkpoint. The declared scientific checkpoints remain unchanged.
            phase = "checkpoint_write"
            checkpoint_session.save(backend, extra_state={
                "geometry_gate_counters": counters.snapshot(),
            })
            last_durable_budget = int(backend.unique_evaluations)
            _atomic_json(cell / "initialization_checkpoint.json", {
                **identity,
                "unique_evaluations": int(backend.unique_evaluations),
                "checkpoint_reference": checkpoint_session.reference_metadata,
            })
        except BaseException as exc:
            _atomic_json(cell / "cell_status.json", _cell_failure_payload(
                identity, exc, phase=phase, backend=backend,
                last_durable_budget=last_durable_budget,
                checkpoint_reference=checkpoint_session.reference_metadata,
                elapsed_wall_time_s=prior_elapsed + time.perf_counter() - cell_started,
            ))
            raise

    checkpoint_rows: list[dict[str, Any]] = []
    try:
        for point in checkpoints:
            point = int(point)
            record_path = cell / f"B{point}.json"
            if record_path.is_file():
                saved = _read_json(record_path)
                if (saved.get("computation_fingerprint") != identity["computation_fingerprint"]
                        or int(saved.get("checkpoint_budget", -1)) != point):
                    raise RuntimeError("checkpoint summary identity mismatch")
                checkpoint_rows.append(saved)
                continue
            if backend.unique_evaluations < point:
                phase = "search_advance"
                started = time.perf_counter()
                backend.advance_to_unique_budget(point, evaluator=evaluator)
                optimizer_elapsed = time.perf_counter() - started
            else:
                optimizer_elapsed = 0.0
            if backend.unique_evaluations != point:
                raise RuntimeError(f"L-SHADE did not reach exact checkpoint {point}")
            phase = "checkpoint_write"
            checkpoint_session.save(backend, extra_state={
                "geometry_gate_counters": counters.snapshot(),
            })
            last_durable_budget = int(backend.unique_evaluations)
            finalists = backend.historical_finalists(int(finalist_count))
            if not finalists:
                raise RuntimeError(f"no physics-evaluated candidates at checkpoint {point}")
            common_started = time.perf_counter()
            phase = "finalist_validation"
            validated = []
            for source_rank, source in enumerate(finalists, start=1):
                candidate = space.decode(
                    source["candidate_vector"],
                    reflector_electrodes=int(cfg["dms_topology"]["t1_reflector_electrodes"]),
                )
                counters.validation_evaluations += 1
                result = stage4a_evaluate(
                    candidate, context["provider"], cfg, context["common_frequencies"],
                    context["source_impedance_ohm"], context["load_impedance_ohm"],
                )
                result["search_source_rank"] = source_rank
                result["search_source_rank_key"] = list(source.get(
                    "history_rank_key", backend.comparator.rank_key(source),
                ))
                if evaluation_status(result) == "PHYSICS_EVALUATED":
                    counters.validation_solved_frequency_points += len(context["common_frequencies"])
                else:
                    counters.validation_physics_failures += 1
                validated.append(result)
            timing["common_validation_wall_time_s"] += time.perf_counter() - common_started
            eligible = [row for row in validated if evaluation_status(row) == "PHYSICS_EVALUATED"]
            selected = min(eligible, key=backend.comparator.rank_key) if eligible else None
            snapshot = _counter_snapshot(counters, backend, len(context["search_frequencies"]))
            row = {
                **identity,
                "checkpoint_budget": point,
                "optimizer_wall_time_s": float(optimizer_elapsed),
                "checkpoint_reference": checkpoint_session.reference_metadata,
                "search_incumbent": _summary_record(backend.incumbent()),
                "common_grid_selected_finalist": (
                    _summary_record(selected) if selected is not None else None
                ),
                "validated_finalists": [
                    _summary_record(value, source_rank=value.get("search_source_rank"))
                    for value in validated
                ],
                "counters": snapshot,
                "lshade_summary": backend.summary(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            _atomic_json(record_path, row)
            phase = "checkpoint_summary_write"
            checkpoint_rows.append(row)

        if [int(row["checkpoint_budget"]) for row in checkpoint_rows] != list(checkpoints):
            raise RuntimeError("cell checkpoint disposition is incomplete or out of order")
        if backend.unique_evaluations != budget:
            raise RuntimeError("cell did not reach its exact unique-evaluation budget")
        final = _read_json(cell / f"B{int(checkpoints[-1])}.json")
        selected = final["common_grid_selected_finalist"]
        counters_snapshot = final["counters"]
        bounds = space.bounds
        result = {
            **identity,
            "status": "COMPLETED",
            "unique_evaluations": int(backend.unique_evaluations),
            "initialization": _read_json(cell / "initializer.json"),
            "search_incumbent": final["search_incumbent"],
            "common_grid_selected_finalist": selected,
            "active_bound_diagnostics": (
                stage4a_active_bound_diagnostics(selected["candidate_vector"], bounds)
                if selected is not None else []
            ),
            "checkpoint_records": [row["checkpoint_budget"] for row in checkpoint_rows],
            "checkpoint_summaries": [
                {"checkpoint_budget": row["checkpoint_budget"],
                 "selected_max_violation": (None if row["common_grid_selected_finalist"] is None
                                            else row["common_grid_selected_finalist"].get("max_violation")),
                 "selected_sum_violation": (None if row["common_grid_selected_finalist"] is None
                                            else row["common_grid_selected_finalist"].get("sum_violation")),
                 "selected_worst_il_db": (None if row["common_grid_selected_finalist"] is None else
                                           row["common_grid_selected_finalist"].get("metrics", {}).get("worst_il_db")),
                 "selected_ripple_db": (None if row["common_grid_selected_finalist"] is None else
                                        row["common_grid_selected_finalist"].get("metrics", {}).get("ripple_db")),
                 "unique_evaluations": row["counters"]["unique_decoded_evaluations"],
                 "generations": row["lshade_summary"]["generations"]}
                for row in checkpoint_rows
            ],
            "counters": counters_snapshot,
            "cache_statistics": {
                key: value for key, value in backend.summary().items()
                if key in {"cache_hits", "cache_hit_rate", "duplicate_count", "duplicate_rate",
                           "proposals_total", "raw_offspring_count", "search_space_exhausted"}
            },
            "physics_failures": int(counters.physics_failures),
            "validation_physics_failures": int(counters.validation_physics_failures),
            "geometry_rejections": int(counters.geometry_rejections),
            "runtime": {
                "search_evaluation_wall_time_s": float(timing["search_evaluation_wall_time_s"]),
                "common_validation_wall_time_s": float(timing["common_validation_wall_time_s"]),
                "cell_wall_time_s": float(prior_elapsed + time.perf_counter() - cell_started),
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_json(result_path, result)
        _atomic_json(cell / "cell_status.json", {
            **identity, "status": "COMPLETED",
            "elapsed_wall_time_s": result["runtime"]["cell_wall_time_s"],
            "updated_at": result["created_at"],
        })
        return result
    except BaseException as exc:
        _atomic_json(cell / "cell_status.json", _cell_failure_payload(
            identity, exc, phase=phase, backend=backend,
            last_durable_budget=last_durable_budget,
            checkpoint_reference=checkpoint_session.reference_metadata,
            elapsed_wall_time_s=prior_elapsed + time.perf_counter() - cell_started,
        ))
        raise


__all__ = [
    "AUTHORIZATION_SCOPE", "BUDGET", "CHECKPOINTS", "FINALIST_COUNT",
    "INITIAL_POPULATION_MULTIPLIER", "PROTOCOL_REVISION", "SEEDS",
    "STUDY_TYPE", "TOPOLOGIES", "matched_cell_paths", "write_atomic_json",
]

write_atomic_json = _atomic_json
matched_cell_paths = _cell_paths
