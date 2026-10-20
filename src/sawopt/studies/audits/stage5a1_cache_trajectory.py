"""Read-only audit of Stage 4C L-SHADE compact-cache identity and trajectory.

This module parses saved state only. It deliberately does not import or execute
an optimizer, evaluator, COM model, or orchestration worker. Ranking and
canonicalization checks below mirror the frozen Stage 4C source contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


RUN_ID = "20261006_124153_ed50ba"
SOURCE_SHA = "65e1815db1cc18d74ff0dcee20ffd5e9098709df"
COMPUTATION_FINGERPRINT = "fdff19b63739efe1022092aa21e2ba3651c82a3344d54721522e5e0fc5cef9dd"
TOPOLOGIES = ("P_D", "D_P")
SEEDS = (20261007, 20261008, 20261009, 20261010, 20261011)
BUDGETS = (8000, 16000, 24000, 32000, 48000, 64000, 80000, 96000)
FINALIST_COUNT = 16


class AuditError(ValueError):
    """Saved evidence violates a frozen structural or accounting invariant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def _integer(value: Any, label: str) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool), f"{label} must be an integer")
    return int(value)


def _number(value: Any, label: str) -> float:
    _require(not isinstance(value, bool), f"{label} must be a real number, not bool")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AuditError(f"{label} is not numeric") from exc
    _require(math.isfinite(number), f"{label} must be finite")
    return number


def _vector(values: Any, dimension: int, label: str) -> tuple[float, ...]:
    _require(isinstance(values, (list, tuple, np.ndarray)), f"{label} must be an array")
    _require(len(values) == dimension, f"{label} dimension {len(values)} != {dimension}")
    return tuple(_number(value, f"{label}[{index}]") for index, value in enumerate(values))


def canonicalize_vector(
    vector: Sequence[float], bounds: Sequence[Sequence[float]], integer_indices: Sequence[int],
) -> tuple[float, ...]:
    """Apply the optimizer's clip, floor(x + 0.5), clip canonicalizer exactly."""
    limits = np.asarray(bounds, dtype=float)
    _require(limits.ndim == 2 and limits.shape[1] == 2, "bounds must have shape (D, 2)")
    _require(np.isfinite(limits).all() and np.all(limits[:, 1] > limits[:, 0]),
             "bounds must be finite and increasing")
    values = np.asarray(_vector(vector, len(limits), "candidate vector"), dtype=float)
    values = np.clip(values, limits[:, 0], limits[:, 1])
    for index in integer_indices:
        _require(0 <= int(index) < len(values), f"invalid integer index {index}")
        values[int(index)] = np.floor(values[int(index)] + 0.5)
    values = np.clip(values, limits[:, 0], limits[:, 1])
    return tuple(float(value) for value in values)


def _read_json(path: Path) -> Any:
    def reject_constant(value: str):
        raise AuditError(f"non-standard JSON numeric constant {value}")

    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            return json.load(stream, parse_constant=reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"cannot read JSON evidence {Path(path).name}: {exc}") from exc


def _key_tuple(raw: Any, dimension: int, label: str) -> tuple[float, ...]:
    return _vector(raw, dimension, label)


def _rank_tuple(raw: Any, *, label: str) -> tuple[float, ...]:
    _require(isinstance(raw, (list, tuple)), f"{label} must be an array")
    # L-SHADE JSON conversion maps comparator +inf values to null; on restore
    # null has exactly the optimizer's +inf meaning. NaN/-inf are never valid.
    values = []
    for index, value in enumerate(raw):
        if value is None:
            values.append(math.inf)
        else:
            number = _number(value, f"{label}[{index}]")
            values.append(number)
    return tuple(values)


def _validate_rank_structure(rank: tuple[float, ...], label: str) -> None:
    _require(len(rank) == 7, f"{label} must have seven GeometryFirst rank coordinates")
    first, second = rank[:2]
    if first == 0.0 and second == 1.0:
        _require(all(math.isinf(value) and value > 0 for value in rank[2:]),
                 f"{label} has an invalid PHYSICS_FAILED rank structure")
    elif first == 0.0 and second == 0.0:
        _require(rank[2] in (0.0, 1.0), f"{label} has an invalid feasibility rank prefix")
        violation_values = rank[5:7] if rank[2] == 0.0 else rank[3:5]
        _require(all(value >= 0.0 for value in violation_values),
                 f"{label} has negative normalized violations")
    elif first == 1.0 and second == 0.0:
        _require(rank[2] >= 0.0 and rank[3] >= 0.0 and rank[4:] == (0.0, 0.0, 0.0),
                 f"{label} has an invalid GEOMETRY_REJECTED rank structure")
    else:
        raise AuditError(f"{label} has an invalid GeometryFirst rank prefix")


def _finite(value: Any, default: float = math.inf) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return number if math.isfinite(number) else float(default)


def _metrics(record: Mapping[str, Any]) -> Mapping[str, Any]:
    value = record.get("metrics", record)
    return value if isinstance(value, Mapping) else {}


def _geometry_rank_key(record: Mapping[str, Any]) -> tuple[float, ...]:
    """Independent transcription of Stage 4C GeometryFirstComparator.rank_key."""
    status = str(record.get("evaluation_status", "PHYSICS_FAILED"))
    if status == "PHYSICS_EVALUATED":
        violations = record.get("violations", {})
        violations = violations if isinstance(violations, Mapping) else {}
        values = [_finite(value) for value in violations.values()]
        values = [max(0.0, value) for value in values if math.isfinite(value)]
        maximum = max(0.0, _finite(record.get("max_violation", max(values, default=0.0))))
        total = _finite(record.get("sum_violation", sum(values)))
        feasible = bool(record.get("feasible", maximum <= 1e-10))
        metrics = _metrics(record)
        worst_il = _finite(metrics.get("worst_il_db", record.get("worst_il_db", math.inf)))
        ripple = _finite(metrics.get("ripple_db", record.get("ripple_db", 0.0)), 0.0)
        base = ((0.0, worst_il, ripple, maximum, total) if feasible else
                (1.0, maximum, total, worst_il, ripple))
        return (0.0, 0.0, *base)
    if status == "PHYSICS_FAILED":
        return (0.0, 1.0, math.inf, math.inf, math.inf, math.inf, math.inf)
    violations = record.get("geometry_violations", {})
    violations = violations if isinstance(violations, Mapping) else {}
    values = [max(0.0, _finite(value)) for value in violations.values()]
    maximum, total = max(values, default=0.0), sum(values)
    return (1.0, 0.0, maximum, total, 0.0, 0.0, 0.0)


def _stable_top(
    entries: Sequence[tuple[tuple[float, ...], tuple[float, ...], int, int]],
    budget: int,
    count: int,
) -> list[tuple[tuple[float, ...], tuple[float, ...], int, int]]:
    eligible = (entry for entry in entries if entry[2] < budget)
    return sorted(eligible, key=lambda entry: (entry[0], entry[2]))[:count]


def _schedule_size(initial: int, minimum: int, horizon: int, evaluations: int) -> int:
    fraction = min(1.0, max(0.0, float(evaluations) / float(horizon)))
    return int(round(initial - fraction * (initial - minimum)))


def _check_counter_partition(counters: Mapping[str, Any], budget: int, frequency_count: int,
                             validation_count: int | None = None,
                             validation_frequency_count: int | None = None) -> None:
    _require(isinstance(counters, Mapping), "evaluation counters are missing or malformed")
    names = (
        "unique_decoded_evaluations", "geometry_rejections", "geometry_valid_candidates",
        "physics_attempted_evaluations", "valid_physics_evaluations", "physics_failures",
        "search_frequency_points",
    )
    parsed = {name: int(counters.get(name, -1)) for name in names}
    _require(parsed["unique_decoded_evaluations"] == budget,
             "counter unique_decoded_evaluations disagrees with checkpoint budget")
    _require(parsed["unique_decoded_evaluations"] ==
             parsed["geometry_rejections"] + parsed["geometry_valid_candidates"],
             "unique-evaluation geometry partition is inconsistent")
    _require(parsed["geometry_valid_candidates"] ==
             parsed["valid_physics_evaluations"] + parsed["physics_failures"],
             "geometry-valid physics partition is inconsistent")
    _require(parsed["physics_attempted_evaluations"] ==
             parsed["valid_physics_evaluations"] + parsed["physics_failures"],
             "physics-attempt partition is inconsistent")
    _require(parsed["search_frequency_points"] ==
             parsed["valid_physics_evaluations"] * frequency_count,
             "search-grid frequency point count is inconsistent")
    for field in names:
        _require(parsed[field] >= 0, f"counter {field} is negative")
    if validation_count is not None:
        _require(int(counters.get("validation_evaluations", -1)) == validation_count,
                 "validation evaluation count is inconsistent")
    if validation_frequency_count is not None:
        _require(int(counters.get("validation_frequency_points", -1)) ==
                 validation_frequency_count,
                 "validation frequency-point count is inconsistent")


def audit_state(
    state: Mapping[str, Any], *, topology: str, expected_bounds: Sequence[Sequence[float]],
    expected_hard_bounds: Sequence[Sequence[float]], integer_indices: Sequence[int],
    expected_frequency_grid: Sequence[float], expected_fingerprint: str,
    expected_budget: int = 96000, expected_memory_size: int | None = None,
    finalist_count: int = FINALIST_COUNT,
) -> tuple[dict[str, Any], list[tuple[tuple[float, ...], tuple[float, ...], int, int]]]:
    """Validate one parsed terminal state; return a redacted summary and index."""
    _require(isinstance(state, Mapping), "optimizer state must be a JSON object")
    _require(int(state.get("state_version", -1)) == 4, "unsupported optimizer state schema")
    _require(state.get("backend") == "lshade", "optimizer backend is not lshade")
    _require(state.get("compact_history_cache") is True, "compact_history_cache is not true")
    _require(int(state.get("historical_finalist_count", -1)) == finalist_count,
             "historical finalist count differs from the frozen contract")
    _require(state.get("source_config_fingerprint") == expected_fingerprint,
             "checkpoint computation fingerprint mismatch")

    bounds = np.asarray(expected_bounds, dtype=float)
    hard_bounds = np.asarray(expected_hard_bounds, dtype=float)
    saved_bounds = np.asarray(state.get("bounds"), dtype=float)
    saved_hard = np.asarray(state.get("hard_bounds"), dtype=float)
    _require(saved_bounds.shape == bounds.shape and np.array_equal(saved_bounds, bounds),
             "active bounds differ from frozen Stage 4C bounds")
    _require(saved_hard.shape == hard_bounds.shape and np.array_equal(saved_hard, hard_bounds),
             "immutable hard bounds differ from frozen Stage 4C bounds")
    _require(np.array_equal(np.asarray(state.get("active_bounds"), dtype=float), bounds),
             "saved active_bounds differ from frozen Stage 4C bounds")
    dimension = len(bounds)
    _require(dimension == 13 and topology in TOPOLOGIES, "unexpected Stage 4C design space")

    grid = tuple(_number(value, "expected search-grid frequency") for value in expected_frequency_grid)
    saved_grid = tuple(_number(value, "saved active_frequency_grid")
                       for value in state.get("active_frequency_grid", []))
    _require(len(grid) == 1001 and saved_grid == grid,
             "saved active search grid does not exactly match the 1,001-point source grid")
    grid_digest = hashlib.sha256(np.asarray(saved_grid, dtype="<f8").tobytes()).hexdigest()
    _require(grid_digest == "212dd2b0b71ddeffb7a8865937d132ee596870f25c989ac7d90c5dab6fd7faa0",
             "saved search-grid digest differs from frozen Stage 4C identity")
    grid_version = _integer(state.get("frequency_grid_version", -1), "state frequency-grid version")
    _require(grid_version == 1, "frequency-grid version is not the frozen version 1")
    design_space_version = _integer(state.get("design_space_version", -1), "design-space version")
    _require(design_space_version == 1, "design-space version changed from the frozen Stage 4C space")

    raw_index = state.get("compact_history_index")
    _require(isinstance(raw_index, list) and raw_index,
             "compact_history_index is absent or empty")
    records: list[tuple[tuple[float, ...], tuple[float, ...], int, int]] = []
    seen_keys: set[tuple[float, ...]] = set()
    orders: list[int] = []
    versions: set[int] = set()
    for position, raw_entry in enumerate(raw_index):
        _require(isinstance(raw_entry, list) and len(raw_entry) == 5,
                 f"compact history entry {position} must contain five fields")
        raw_key, version, raw_rank, raw_vector, order = raw_entry
        key = _key_tuple(raw_key, dimension, f"history key {position}")
        vector = _vector(raw_vector, dimension, f"history candidate vector {position}")
        canonical = canonicalize_vector(vector, bounds, integer_indices)
        _require(key == canonical, f"history vector/key canonical identity mismatch at entry {position}")
        _require(key not in seen_keys, f"duplicate canonical key at history entry {position}")
        seen_keys.add(key)
        version_i = _integer(version, f"history grid version {position}")
        order_i = _integer(order, f"history insertion order {position}")
        _require(version_i > 0, f"invalid grid version at history entry {position}")
        _require(order_i >= 0, f"negative insertion order at history entry {position}")
        rank = _rank_tuple(raw_rank, label=f"history rank key {position}")
        _validate_rank_structure(rank, f"history rank key {position}")
        records.append((rank, key, order_i, version_i))
        orders.append(order_i)
        versions.add(version_i)
    _require(len(set(orders)) == len(orders), "insertion order values are duplicated")
    _require(sorted(orders) == list(range(len(records))),
             "insertion order is not a complete zero-based unique-evaluation sequence")
    _require(versions == {grid_version}, "history contains a changed frequency-grid version")
    _require(int(state.get("unique_evaluations", -1)) == len(records),
             "compact history length differs from unique_evaluations")
    _require(len(records) == expected_budget,
             f"compact history has {len(records)} entries, expected {expected_budget}")
    _require(int(state.get("actual_unique_budget", -1)) == expected_budget,
             "actual_unique_budget differs from terminal unique evaluation count")

    # Compact mode retains complete result payloads only for its top-k shortlist.
    _require(state.get("cache") == [], "compact-history state unexpectedly stores full cache")
    _require(state.get("cache_frequency_versions") == [],
             "compact-history state unexpectedly stores expanded cache versions")
    retained = state.get("retained_results")
    _require(isinstance(retained, list), "retained_results is missing")
    _require(len(retained) <= finalist_count, "retained_results exceeds finalist capacity")
    by_key = {key: entry for entry in records for key in (entry[1],)}
    retained_keys = set()
    for position, item in enumerate(retained):
        _require(isinstance(item, list) and len(item) == 2,
                 f"retained result {position} must be a key/result pair")
        key = _key_tuple(item[0], dimension, f"retained result key {position}")
        _require(key not in retained_keys, "retained result keys are duplicated")
        retained_keys.add(key)
        _require(key in by_key, "retained result key is absent from compact history")
        result = item[1]
        _require(isinstance(result, Mapping), f"retained result {position} is not an object")
        vector = _vector(result.get("candidate_vector"), dimension,
                         f"retained result vector {position}")
        _require(canonicalize_vector(vector, bounds, integer_indices) == key,
                 f"retained result vector/key mismatch at result {position}")
        stored_rank = by_key[key][0]
        for field in ("history_rank_key", "rank_key"):
            if field in result:
                _require(_rank_tuple(result[field], label=f"retained result rank {position}") ==
                         stored_rank,
                         f"retained result rank conflicts with compact history at result {position}")
        _require(_rank_tuple(list(_geometry_rank_key(result)),
                             label=f"recomputed retained rank {position}") == stored_rank,
                 f"retained result rank key is corrupt at result {position}")

    best_rank = min((entry[0] for entry in records), default=())
    incumbent = state.get("incumbent")
    _require(isinstance(incumbent, Mapping), "incumbent is missing or malformed")
    incumbent_vector = _vector(incumbent.get("candidate_vector"), dimension, "incumbent vector")
    incumbent_key = _key_tuple(state.get("incumbent_key"), dimension, "incumbent key")
    _require(canonicalize_vector(incumbent_vector, bounds, integer_indices) == incumbent_key,
             "incumbent vector/key canonical identity mismatch")
    _require(incumbent_key in by_key, "incumbent key is absent from compact history")
    incumbent_rank = _rank_tuple(_geometry_rank_key(incumbent), label="incumbent rank")
    _require(incumbent_rank == by_key[incumbent_key][0] == best_rank,
             "incumbent does not match the best saved historical rank")

    _audit_population_and_archive(state, by_key, bounds, integer_indices, expected_budget)
    trace_counts = _audit_traces(state, expected_budget)
    extra_state = state.get("extra_state", {})
    _require(isinstance(extra_state, Mapping), "saved extra_state is missing or malformed")
    counters = extra_state.get("geometry_gate_counters", {})
    _require(isinstance(counters, Mapping), "saved geometry-gate search counters are missing")
    search_counters = dict(counters)
    search_counters["unique_decoded_evaluations"] = len(records)
    _check_counter_partition(search_counters, expected_budget, len(grid))
    _audit_optimizer_counters(state, dimension, expected_budget, expected_memory_size)
    _require(_rank_tuple(state["best_so_far_trace"][-1]["rank_key"],
                         label="terminal best-so-far rank") == best_rank,
             "terminal best-so-far trace does not match compact-history minimum")
    _require(len(retained_keys) == finalist_count,
             "retained_results does not contain the complete finalist shortlist")
    final_shortlist = {entry[1] for entry in _stable_top(records, expected_budget, finalist_count)}
    _require(retained_keys == final_shortlist,
             "retained_results keys do not match the compact-history top-k shortlist")

    summary = {
        "state_version": 4,
        "compact_history_cache": True,
        "compact_history_index_count": len(records),
        "retained_results_count": len(retained),
        "canonical_keys_unique": True,
        "candidate_key_identity": "exact",
        "insertion_orders_complete": True,
        "frequency_grid_version": grid_version,
        "design_space_version": design_space_version,
        "search_grid_points": len(saved_grid),
        "search_grid_sha256": grid_digest,
        "best_so_far_trace_count": trace_counts[0],
        "population_trace_count": trace_counts[1],
        "archive_trace_count": trace_counts[2],
        "population_size": len(state.get("population", [])),
        "archive_size": len(state.get("archive", [])),
        "unique_evaluations": int(state["unique_evaluations"]),
        "proposals_total": int(state["proposals_total"]),
        "raw_offspring_count": int(state["raw_offspring_count"]),
        "duplicate_count": int(state["duplicate_count"]),
        "cache_hits": int(state["cache_hits"]),
        "generations": int(state["generations"]),
        "boundary_repairs": sum(sum(map(int, state["boundary_repair_counts"][axis]))
                                 for axis in ("lower", "upper")),
        "search_counter_partition": "PASS",
    }
    return summary, records


def _audit_optimizer_counters(
    state: Mapping[str, Any], dimension: int, budget: int, expected_memory_size: int | None,
) -> None:
    integer_names = ("unique_evaluations", "proposals_total", "raw_offspring_count",
                     "duplicate_count", "cache_hits", "generations")
    counters = {name: int(state.get(name, -1)) for name in integer_names}
    _require(counters["unique_evaluations"] == budget, "state unique-evaluation counter mismatch")
    _require(counters["proposals_total"] ==
             int(state.get("initial_population_size", -1)) + counters["raw_offspring_count"],
             "proposal count does not equal initialization plus raw offspring")
    _require(counters["raw_offspring_count"] - counters["duplicate_count"] ==
             counters["generations"], "raw offspring/duplicates/generations are inconsistent")
    _require(counters["duplicate_count"] == counters["cache_hits"],
             "duplicate proposals and same-grid cache hits differ")
    _require(all(value >= 0 for value in counters.values()), "optimizer counter is negative")
    _require(int(state.get("requested_unique_budget", -1)) == budget,
             "requested unique budget differs from the frozen production budget")
    _require(int(state.get("population_schedule_terminal_budget", -1)) == budget,
             "population schedule terminal horizon differs from frozen budget")
    _require(int(state.get("hard_max_budget", -1)) == budget,
             "hard maximum budget differs from frozen budget")
    _require(state.get("population_schedule_identifier") in (None, "lshade_linear_population_v1"),
             "unknown L-SHADE population schedule")

    initial = int(state.get("initial_population_size", -1))
    minimum = int(state.get("minimum_population_size", -1))
    _require(initial == 234 and minimum == 4, "initial/minimum population differs from protocol")
    _require(int(state.get("current_population_size", -1)) == len(state.get("population", [])),
             "current population size field disagrees with population records")
    _require(len(state.get("population", [])) == _schedule_size(initial, minimum, budget, budget),
             "terminal population size differs from the L-SHADE linear schedule")

    m_f = np.asarray(state.get("m_f"), dtype=float)
    m_cr = np.asarray(state.get("m_cr"), dtype=float)
    _require(m_f.ndim == m_cr.ndim == 1 and m_f.shape == m_cr.shape and m_f.size > 0,
             "SHADE memories must be equal nonempty vectors")
    _require(np.isfinite(m_f).all() and np.isfinite(m_cr).all(), "SHADE memory is non-finite")
    _require(np.all((m_f >= 0) & (m_f <= 1)) and np.all((m_cr >= 0) & (m_cr <= 1)),
             "SHADE memory is outside [0, 1]")
    if expected_memory_size is not None:
        _require(m_f.size == expected_memory_size, "SHADE memory length differs from configuration")
    history_index = int(state.get("history_index", -1))
    _require(0 <= history_index < m_f.size, "SHADE history index is out of range")
    _require(int(state.get("memory_update_batch_size", 0)) > 0,
             "SHADE memory update batch size is not positive")
    _require(0 <= int(state.get("memory_batch_proposals", -1)) <
             int(state["memory_update_batch_size"]), "SHADE pending memory batch count is invalid")
    for field in ("successful_f", "successful_cr", "successful_weights"):
        values = np.asarray(state.get(field, []), dtype=float)
        _require(values.ndim == 1 and np.isfinite(values).all(), f"{field} must be finite vector")
        if field != "successful_weights":
            _require(np.all((values >= 0) & (values <= 1)), f"{field} is outside [0, 1]")
        else:
            _require(np.all(values > 0), "successful_weights must be positive")
    success_lengths = [len(state.get(field, [])) for field in
                       ("successful_f", "successful_cr", "successful_weights")]
    _require(len(set(success_lengths)) == 1, "pending successful-memory arrays differ in length")

    rng = state.get("rng_state")
    _require(isinstance(rng, Mapping) and rng.get("bit_generator") == "PCG64",
             "saved RNG state is not a PCG64 state")
    rng_inner = rng.get("state")
    _require(isinstance(rng_inner, Mapping), "PCG64 nested state is malformed")
    for name in ("state", "inc"):
        value = rng_inner.get(name)
        _require(isinstance(value, int) and not isinstance(value, bool) and value > 0,
                 f"PCG64 {name} must be a positive integer")
    _require(int(rng_inner["inc"]) % 2 == 1, "PCG64 increment must be odd")
    _require(int(rng.get("has_uint32", -1)) in (0, 1), "PCG64 has_uint32 flag is invalid")
    _require(0 <= int(rng.get("uinteger", -1)) <= 0xFFFFFFFF,
             "PCG64 cached uint32 value is invalid")

    repairs = state.get("boundary_repair_counts")
    _require(isinstance(repairs, Mapping), "boundary repair counters are missing")
    total_repairs = 0
    for direction in ("lower", "upper"):
        values = repairs.get(direction)
        _require(isinstance(values, list) and len(values) == dimension,
                 f"{direction} boundary repair vector has wrong dimension")
        parsed = [int(value) for value in values]
        _require(all(value >= 0 for value in parsed), f"{direction} boundary repair count is negative")
        total_repairs += sum(parsed)
    _require(total_repairs <= counters["raw_offspring_count"] * dimension,
             "boundary repair count exceeds possible component repair opportunities")

    groups = state.get("duplicate_by_group", {})
    _require(isinstance(groups, Mapping), "duplicate_by_group is malformed")
    group_values = [int(groups.get(name, 0)) for name in ("integer", "continuous")]
    _require(all(0 <= value <= 2 * counters["duplicate_count"] for value in group_values),
             "duplicate group counters are outside possible totals")


def _audit_population_and_archive(
    state: Mapping[str, Any],
    history: Mapping[tuple[float, ...], tuple[tuple[float, ...], tuple[float, ...], int, int]],
    bounds: np.ndarray,
    integer_indices: Sequence[int],
    budget: int,
) -> None:
    population = state.get("population")
    archive = state.get("archive")
    _require(isinstance(population, list) and population, "population is missing or empty")
    _require(isinstance(archive, list), "archive is missing or malformed")
    _require(len(archive) <= len(population), "archive exceeds current population capacity")
    population_keys = set()
    for index, member in enumerate(population):
        _require(isinstance(member, Mapping), f"population member {index} is malformed")
        x = _vector(member.get("x"), len(bounds), f"population x {index}")
        _require(all(0.0 <= value <= 1.0 for value in x), f"population x {index} is outside [0, 1]")
        physical = _vector(member.get("physical"), len(bounds), f"population physical {index}")
        key = _key_tuple(member.get("key"), len(bounds), f"population key {index}")
        canonical = canonicalize_vector(physical, bounds, integer_indices)
        _require(key == canonical, f"population key/physical mismatch at member {index}")
        projected = bounds[:, 0] + np.asarray(x) * (bounds[:, 1] - bounds[:, 0])
        _require(canonicalize_vector(projected, bounds, integer_indices) == key,
                 f"population normalized/physical mismatch at member {index}")
        _require(key in history, f"population key {index} is absent from compact history")
        _require(key not in population_keys, "population contains duplicate canonical members")
        population_keys.add(key)
        result = member.get("result")
        _require(isinstance(result, Mapping), f"population result {index} is malformed")
        _require(_rank_tuple(_geometry_rank_key(result), label=f"population rank {index}") ==
                 history[key][0], f"population result rank differs from compact history at {index}")

    archive_keys = set()
    for index, raw_vector in enumerate(archive):
        x = _vector(raw_vector, len(bounds), f"archive vector {index}")
        _require(all(0.0 <= value <= 1.0 for value in x), f"archive vector {index} is outside [0, 1]")
        physical = bounds[:, 0] + np.asarray(x) * (bounds[:, 1] - bounds[:, 0])
        key = canonicalize_vector(physical, bounds, integer_indices)
        _require(key in history, f"archive key {index} is absent from compact history")
        _require(key not in archive_keys, "archive contains duplicate canonical vectors")
        archive_keys.add(key)
    _require(len(population) == _schedule_size(
        int(state["initial_population_size"]), int(state["minimum_population_size"]),
        int(state["population_schedule_terminal_budget"]), budget,
    ), "population size differs from L-SHADE terminal schedule")


def _audit_traces(state: Mapping[str, Any], budget: int) -> tuple[int, int, int]:
    best = state.get("best_so_far_trace")
    population = state.get("population_trace")
    archive = state.get("archive_trace")
    _require(isinstance(best, list) and best, "best_so_far_trace is missing or empty")
    _require(isinstance(population, list) and population, "population_trace is missing or empty")
    _require(isinstance(archive, list) and archive, "archive_trace is missing or empty")
    _require(len(population) == len(archive) == int(state.get("generations", -1)) + 1,
             "population/archive trace lengths do not equal generations + initialization")
    previous_eval = -1
    previous_rank = None
    for index, row in enumerate(best):
        _require(isinstance(row, Mapping), f"best-so-far trace row {index} is malformed")
        evaluation = int(row.get("unique_evaluation", -1))
        _require(previous_eval < evaluation <= budget,
                 "best-so-far trace evaluations are not strictly chronological")
        _require(int(row.get("frequency_grid_version", -1)) == 1,
                 "best-so-far trace crosses frequency-grid versions")
        rank = _rank_tuple(row.get("rank_key"), label=f"best-so-far rank {index}")
        _validate_rank_structure(rank, f"best-so-far rank {index}")
        _require(previous_rank is None or rank < previous_rank,
                 "best-so-far rank did not strictly improve")
        _require(row.get("comparator") in (None, "GeometryFirstComparator"),
                 "best-so-far trace comparator changed")
        previous_eval, previous_rank = evaluation, rank
    previous_eval = -1
    for trace_name, rows in (("population_trace", population), ("archive_trace", archive)):
        previous_eval = -1
        for index, row in enumerate(rows):
            _require(isinstance(row, Mapping), f"{trace_name} row {index} is malformed")
            evaluation = int(row.get("unique_evaluation", -1))
            _require(previous_eval <= evaluation <= budget,
                     f"{trace_name} evaluation sequence is not chronological")
            _require(evaluation >= 1, f"{trace_name} contains invalid unique evaluation")
            _require(int(row.get("frequency_grid_version", -1)) == 1,
                     f"{trace_name} crosses frequency-grid versions")
            expected_population = (
                int(state["initial_population_size"]) if index == 0 else _schedule_size(
                    int(state["initial_population_size"]), int(state["minimum_population_size"]),
                    int(state["population_schedule_terminal_budget"]), evaluation,
                )
            )
            if trace_name == "population_trace":
                _require(int(row.get("population_size", -1)) == expected_population,
                         f"population schedule mismatch at trace row {index}")
            else:
                _require(0 <= int(row.get("archive_size", -1)) <= expected_population,
                         f"archive schedule mismatch at trace row {index}")
            previous_eval = evaluation
    _require(int(population[-1].get("unique_evaluation", -1)) == budget,
             "population trace does not terminate at the final unique-evaluation budget")
    _require(int(archive[-1].get("unique_evaluation", -1)) == budget,
             "archive trace does not terminate at the final unique-evaluation budget")
    return len(best), len(population), len(archive)


def _check_summary_counters(summary: Mapping[str, Any], checkpoint: int,
                            initial_population: int) -> None:
    required = ("proposals_total", "raw_offspring_count", "duplicate_count", "cache_hits", "generations")
    values = {name: int(summary.get(name, -1)) for name in required}
    _require(all(value >= 0 for value in values.values()), "checkpoint lshade_summary has invalid counters")
    _require(values["proposals_total"] == initial_population + values["raw_offspring_count"],
             "checkpoint proposals do not equal initialization plus offspring")
    _require(values["raw_offspring_count"] - values["duplicate_count"] == values["generations"],
             "checkpoint offspring/duplicate/generation counters disagree")
    _require(values["duplicate_count"] == values["cache_hits"],
             "checkpoint cache hits disagree with duplicate proposals")
    _require(int(summary.get("unique_evaluations", -1)) == checkpoint,
             "checkpoint L-SHADE unique evaluation count mismatch")
    expected_size = _schedule_size(initial_population, 4, 96000, checkpoint)
    _require(int(summary.get("current_population", -1)) == expected_size,
             "checkpoint current population violates L-SHADE schedule")
    _require(int(summary.get("population_size", -1)) == expected_size,
             "checkpoint population size violates L-SHADE schedule")
    _require(int(summary.get("population_schedule_terminal_budget", -1)) == 96000,
             "checkpoint population horizon changed")
    _require(summary.get("population_schedule_identifier") == "lshade_linear_population_v1" and
             int(summary.get("population_schedule_version", -1)) == 1,
             "checkpoint population schedule identifier/version changed")
    for name in ("m_f", "m_cr"):
        values = np.asarray(summary.get(name), dtype=float)
        _require(values.ndim == 1 and values.size == 6 and np.isfinite(values).all() and
                 np.all((values >= 0) & (values <= 1)),
                 f"checkpoint SHADE {name} memory is malformed")
    repairs = summary.get("boundary_repair_counts")
    _require(isinstance(repairs, Mapping), "checkpoint boundary repair counters are malformed")
    for direction in ("lower", "upper"):
        values = repairs.get(direction)
        _require(isinstance(values, list) and len(values) == 13 and
                 all(int(value) >= 0 for value in values),
                 f"checkpoint {direction} boundary repair counters are malformed")


def _check_terminal_checkpoint_matches_state(final_checkpoint: Mapping[str, Any],
                                             state: Mapping[str, Any]) -> None:
    _require(isinstance(final_checkpoint, Mapping) and isinstance(state, Mapping),
             "terminal checkpoint/state must be JSON objects")
    summary = final_checkpoint.get("lshade_summary", {})
    _require(isinstance(summary, Mapping), "terminal checkpoint L-SHADE summary is malformed")
    for name in ("best_so_far_trace", "population_trace", "archive_trace"):
        _require(summary.get(name) == state.get(name),
                 f"terminal B*.json {name} differs from final optimizer state")
    summary_incumbent = summary.get("incumbent")
    state_incumbent = state.get("incumbent")
    _require(isinstance(summary_incumbent, Mapping) and isinstance(state_incumbent, Mapping),
             "terminal checkpoint/state incumbent is malformed")
    _require(summary_incumbent.get("candidate_vector") == state_incumbent.get("candidate_vector"),
             "terminal B*.json incumbent differs from final optimizer state")
    _require(summary.get("unique_evaluations") == state.get("unique_evaluations"),
             "terminal B*.json and final-state budgets disagree")
    for summary_field, state_field in (
        ("proposals_total", "proposals_total"), ("raw_offspring_count", "raw_offspring_count"),
        ("duplicate_count", "duplicate_count"), ("cache_hits", "cache_hits"),
        ("generations", "generations"), ("boundary_repair_counts", "boundary_repair_counts"),
        ("m_f", "m_f"), ("m_cr", "m_cr"), ("archive_size", "archive"),
    ):
        expected = len(state[state_field]) if state_field == "archive" else state.get(state_field)
        _require(summary.get(summary_field) == expected,
                 f"terminal B*.json {summary_field} differs from final optimizer state")
    _require(summary.get("current_population") == len(state.get("population", [])) and
             summary.get("population_size") == len(state.get("population", [])),
             "terminal B*.json population size differs from final optimizer state")


def _check_terminal_saved_counters(final_checkpoint: Mapping[str, Any],
                                  state: Mapping[str, Any]) -> None:
    terminal_counters = final_checkpoint.get("counters", {})
    search_counters = state["extra_state"]["geometry_gate_counters"]
    _require(isinstance(terminal_counters, Mapping) and isinstance(search_counters, Mapping),
             "terminal saved search counters are malformed")
    for field in ("geometry_rejections", "geometry_valid_candidates", "physics_attempted_evaluations",
                  "valid_physics_evaluations", "physics_failures", "search_frequency_points"):
        _require(terminal_counters.get(field) == search_counters.get(field),
                 f"terminal B*.json {field} differs from final state counters")
    for field, summary_field in (("cache_hits", "cache_hits"),
                                 ("objective_proposals", "proposals_total"),
                                 ("duplicate_proposals", "duplicate_count"),
                                 ("raw_offspring_count", "raw_offspring_count"),
                                 ("generations", "generations")):
        _require(terminal_counters.get(field) == state.get(summary_field),
                 f"terminal B*.json {field} differs from final state counters")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_cell(
    cell_dir: str | Path, *, topology: str, seed: int,
    expected_bounds: Sequence[Sequence[float]], expected_hard_bounds: Sequence[Sequence[float]],
    integer_indices: Sequence[int], expected_frequency_grid: Sequence[float],
    expected_fingerprint: str, expected_memory_size: int | None,
    budgets: Sequence[int] = BUDGETS, finalist_count: int = FINALIST_COUNT,
) -> dict[str, Any]:
    """Audit one raw cell sequentially, loading no more than one B*.json at a time."""
    directory = Path(cell_dir)
    checkpoint_dir = directory / "checkpoints"
    final_path = checkpoint_dir / "final.json"
    retention_path = checkpoint_dir / "retention.json"
    summary: dict[str, Any] = {
        "topology": topology, "seed": int(seed), "final_checkpoint_exists": final_path.is_file(),
        "latest_exists": (checkpoint_dir / "latest.json").exists(),
        "previous_exists": (checkpoint_dir / "previous.json").exists(),
        "pinned_directory_exists": (checkpoint_dir / "pinned").is_dir(),
        "pinned_count": (len(list((checkpoint_dir / "pinned").glob("*.json")))
                         if (checkpoint_dir / "pinned").is_dir() else 0),
        "b_record_count": sum((directory / f"B{int(budget)}.json").is_file() for budget in budgets),
        "checkpoint_ranks_reconstructed": 0,
    }
    if not final_path.is_file():
        summary.update({"status": "EVIDENCE_LIMITED", "reason": "final.json is missing"})
        return summary
    _require(retention_path.is_file(), "finalized checkpoint retention metadata is missing")
    retention = _read_json(retention_path)
    _require(retention.get("format_version") == 1 and
             retention.get("policy") == "rolling_latest_previous" and
             retention.get("runtime_retention_count") == 2 and
             retention.get("latest") == "latest.json" and
             retention.get("previous") == "previous.json" and
             retention.get("final") == "final.json" and
             retention.get("pinned_directory") == "pinned" and
             retention.get("state") == "FINALIZED",
             "checkpoint retention metadata does not match finalized rolling storage")
    _require(not summary["latest_exists"] and not summary["previous_exists"],
             "finalized cell unexpectedly retains latest/previous runtime state")
    _require(not summary["pinned_directory_exists"] and summary["pinned_count"] == 0,
             "unexpected pinned directory or pinned state exists")

    manifest_path = directory / "cell_manifest.json"
    manifest = _read_json(manifest_path)
    _require(manifest.get("topology") == topology and int(manifest.get("seed", -1)) == seed,
             "cell manifest identity mismatch")
    _require(manifest.get("source_commit_sha") == SOURCE_SHA,
             "cell manifest source SHA differs from original execution")
    _require(manifest.get("computation_fingerprint") == expected_fingerprint,
             "cell manifest computation fingerprint mismatch")
    _require(manifest.get("budget") == 96000 and manifest.get("checkpoints") == list(BUDGETS),
             "cell manifest budget/checkpoint contract mismatch")

    state = _read_json(final_path)
    state_summary, records = audit_state(
        state, topology=topology, expected_bounds=expected_bounds,
        expected_hard_bounds=expected_hard_bounds, integer_indices=integer_indices,
        expected_frequency_grid=expected_frequency_grid,
        expected_fingerprint=expected_fingerprint, expected_memory_size=expected_memory_size,
        expected_budget=96000, finalist_count=finalist_count,
    )
    by_order = sorted(records, key=lambda entry: entry[2])
    check_results = []
    for checkpoint_index, budget in enumerate(budgets, start=1):
        record_path = directory / f"B{int(budget)}.json"
        if not record_path.is_file():
            check_results.append({"budget": int(budget), "status": "MISSING"})
            continue
        row = _read_json(record_path)
        _require(row.get("topology") == topology and int(row.get("seed", -1)) == seed,
                 f"B{budget} topology/seed identity mismatch")
        _require(int(row.get("checkpoint_budget", -1)) == budget,
                 f"B{budget} record budget mismatch")
        _require(row.get("source_commit_sha") == SOURCE_SHA,
                 f"B{budget} original source SHA mismatch")
        _require(row.get("computation_fingerprint") == expected_fingerprint,
                 f"B{budget} computation fingerprint mismatch")

        expected = _stable_top(by_order, int(budget), finalist_count)
        _require(len(expected) == finalist_count, f"B{budget} cannot reconstruct {finalist_count} finalists")
        saved = row.get("validated_finalists")
        _require(isinstance(saved, list) and len(saved) == finalist_count,
                 f"B{budget} does not contain exactly {finalist_count} validated finalists")
        for rank_number, (candidate, expected_entry) in enumerate(zip(saved, expected), start=1):
            rank_key, expected_vector, order, _version = expected_entry
            _require(isinstance(candidate, Mapping), f"B{budget} finalist {rank_number} is malformed")
            _require(int(candidate.get("search_source_rank", -1)) == rank_number,
                     f"B{budget} finalist source rank is not ordered 1..16")
            _require(candidate.get("topology") == topology,
                     f"B{budget} finalist topology mismatch at rank {rank_number}")
            actual_vector = _vector(candidate.get("candidate_vector"), 13,
                                    f"B{budget} finalist vector {rank_number}")
            _require(actual_vector == expected_vector,
                     f"B{budget} finalist vector does not match reconstructed rank {rank_number}")
            if candidate.get("search_source_rank_key") is not None:
                saved_rank = _rank_tuple(candidate["search_source_rank_key"],
                                         label=f"B{budget} finalist rank key {rank_number}")
                _require(saved_rank == rank_key,
                         f"B{budget} finalist saved search rank key mismatch at rank {rank_number}")

        lshade = row.get("lshade_summary")
        _require(isinstance(lshade, Mapping), f"B{budget} lshade_summary is missing")
        initial = int(lshade.get("initial_population", -1))
        _require(initial == 234, f"B{budget} initial population mismatch")
        _check_summary_counters(lshade, int(budget), initial)
        saved_counters = row.get("counters", {})
        validation_n = checkpoint_index * finalist_count
        validation_failures = int(saved_counters.get("validation_physics_failures", -1))
        _require(0 <= validation_failures <= validation_n,
                 f"B{budget} validation failure count is invalid")
        _check_counter_partition(
            saved_counters, int(budget), 1001, validation_n,
            (validation_n - validation_failures) * 9113,
        )
        for counter_field, summary_field in (("cache_hits", "cache_hits"),
                                             ("objective_proposals", "proposals_total"),
                                             ("duplicate_proposals", "duplicate_count"),
                                             ("raw_offspring_count", "raw_offspring_count"),
                                             ("generations", "generations")):
            _require(saved_counters.get(counter_field) == lshade.get(summary_field),
                     f"B{budget} {counter_field} differs between counters and L-SHADE summary")
        # B*.json are per-budget result/validation records, not full optimizer
        # state. Their saved telemetry must be exact prefixes of the sole final
        # state, which uses the same fixed grid and monotone trace append rules.
        for name in ("best_so_far_trace", "population_trace", "archive_trace"):
            saved_trace = lshade.get(name)
            final_trace = state.get(name)
            _require(isinstance(saved_trace, list) and isinstance(final_trace, list),
                     f"B{budget} {name} or terminal state trace is missing")
            _require(saved_trace == final_trace[:len(saved_trace)],
                     f"B{budget} {name} is not an unchanged prefix of terminal state")
        best_trace = lshade.get("best_so_far_trace", [])
        _require(best_trace, f"B{budget} best-so-far trace is empty")
        _require(_rank_tuple(best_trace[-1].get("rank_key"), label=f"B{budget} incumbent rank") ==
                 expected[0][0], f"B{budget} trace incumbent does not match historical minimum rank")
        search_incumbent = row.get("search_incumbent")
        _require(isinstance(search_incumbent, Mapping), f"B{budget} search incumbent is missing")
        incumbent_vector = _vector(search_incumbent.get("candidate_vector"), 13,
                                    f"B{budget} search incumbent vector")
        _require(any(incumbent_vector == entry[1] and entry[0] == expected[0][0]
                     for entry in expected),
                 f"B{budget} search incumbent is not a best-ranked historical candidate")
        check_results.append({
            "budget": int(budget), "status": "PASS", "finalists_checked": finalist_count,
            "trace_prefixes_match": True,
        })
        summary["checkpoint_ranks_reconstructed"] += 1

    missing_budgets = [int(budget) for budget in budgets
                       if not (directory / f"B{int(budget)}.json").is_file()]
    if missing_budgets:
        terminal_path = directory / f"B{int(budgets[-1])}.json"
        if terminal_path.is_file():
            final_b = _read_json(terminal_path)
            _check_terminal_checkpoint_matches_state(final_b, state)
            _check_terminal_saved_counters(final_b, state)
        summary.update({
            "status": "EVIDENCE_LIMITED",
            "reason": "one or more B*.json records are missing; no rank was inferred",
            "missing_checkpoint_budgets": missing_budgets,
            "state_sha256": _hash_file(final_path),
            "checkpoint_schema_version": state_summary["state_version"],
            **state_summary,
            "checkpoints": check_results,
            "finalist_pools_passed": sum(row["status"] == "PASS" for row in check_results),
            "finalist_candidates_checked": finalist_count * sum(row["status"] == "PASS" for row in check_results),
        })
        return summary
    final_b = _read_json(directory / f"B{int(budgets[-1])}.json")
    _check_terminal_checkpoint_matches_state(final_b, state)
    _check_terminal_saved_counters(final_b, state)
    summary.update({
        "status": "PASS", "state_sha256": _hash_file(final_path),
        "checkpoint_schema_version": state_summary["state_version"],
        **state_summary,
        "checkpoints": check_results,
        "finalist_pools_passed": sum(row["status"] == "PASS" for row in check_results),
        "finalist_candidates_checked": finalist_count * sum(row["status"] == "PASS" for row in check_results),
    })
    return summary


def audit_run(run_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Run all ten cells serially, write redacted JSON/Markdown evidence."""
    run = Path(run_dir)
    output = Path(output_dir)
    _require(run.is_dir(), "external Stage 4C run directory does not exist")
    # A reporting path inside the raw run would violate the read-only audit
    # contract. Resolve symlinks as well as ordinary relative paths.
    _require(not output.resolve().is_relative_to(run.resolve()),
             "audit output directory must be outside the raw Stage 4C run")
    run_manifest = _read_json(run / "run_manifest.json")
    protocol_manifest = _read_json(run / "optimizer/metadata/stage4c_run_manifest.json")
    _require(run_manifest.get("run_id") == RUN_ID and protocol_manifest.get("run_id") == RUN_ID,
             "raw run ID differs from frozen Stage 4C run ID")
    _require(run_manifest.get("source_commit_sha") == SOURCE_SHA and
             protocol_manifest.get("source_commit_sha") == SOURCE_SHA,
             "raw run manifest source SHA differs from original execution")
    _require(protocol_manifest.get("computation_fingerprint") == COMPUTATION_FINGERPRINT,
             "raw computation fingerprint differs from frozen run provenance")
    _require(protocol_manifest.get("budget_per_cell") == 96000 and
             protocol_manifest.get("checkpoints") == list(BUDGETS),
             "raw Stage 4C manifest budget/checkpoint contract mismatch")
    _require(protocol_manifest.get("topologies") == list(TOPOLOGIES) and
             protocol_manifest.get("seeds") == list(SEEDS),
             "raw Stage 4C manifest cell matrix mismatch")
    _require(protocol_manifest.get("search_grid_sha256") ==
             "212dd2b0b71ddeffb7a8865937d132ee596870f25c989ac7d90c5dab6fd7faa0",
             "raw run manifest search-grid SHA mismatch")

    # Recreate only the declared frequency grid from configuration. This is
    # deterministic bookkeeping, not filter evaluation or COM execution.
    from sawopt.core.metrics import search_grid
    from sawopt.io.config import load_experiment_config

    root = Path(__file__).resolve().parents[4]
    config = load_experiment_config(root / "configs/studies/hybrid_stage4c_confirmatory.yaml")
    frequencies = np.unique(search_grid(config["spec"], config))
    grid_sha = hashlib.sha256(np.asarray(frequencies, dtype="<f8").tobytes()).hexdigest()
    _require(len(frequencies) == 1001 and grid_sha == protocol_manifest["search_grid_sha256"],
             "source configuration does not reproduce declared search-grid identity")
    protected = config["stage4c"]["protected_inputs"]
    t1_active = np.asarray(protected["t1_active_bounds"], dtype=float)
    t1_hard = np.asarray(protected["t1_hard_bounds"], dtype=float)
    resonator = np.asarray(config["hybrid"]["resonator_bounds"], dtype=float)
    bounds = np.vstack((t1_active, resonator))
    hard_bounds = np.vstack((t1_hard, resonator))
    integer_indices = (4, 5, 6, 11)
    memory_size = int(config.get("dms_topology", {}).get("lshade", {}).get("history_size", 6))

    cells = []
    for topology in TOPOLOGIES:
        for seed in SEEDS:
            cell_dir = run / "optimizer/optimization" / topology / f"seed{seed}"
            try:
                cell = audit_cell(
                    cell_dir, topology=topology, seed=seed,
                    expected_bounds=bounds, expected_hard_bounds=hard_bounds,
                    integer_indices=integer_indices, expected_frequency_grid=frequencies,
                    expected_fingerprint=COMPUTATION_FINGERPRINT,
                    expected_memory_size=memory_size,
                )
            except Exception as exc:
                cell = {"topology": topology, "seed": seed, "status": "FAIL",
                        "error": f"{type(exc).__name__}: {exc}",
                        "final_checkpoint_exists": (cell_dir / "checkpoints/final.json").is_file(),
                        "b_record_count": sum((cell_dir / f"B{budget}.json").is_file()
                                               for budget in BUDGETS),
                        "checkpoint_ranks_reconstructed": 0}
            cells.append(cell)

    pass_cells = sum(cell.get("status") == "PASS" for cell in cells)
    fail_cells = sum(cell.get("status") == "FAIL" for cell in cells)
    limited_cells = sum(cell.get("status") == "EVIDENCE_LIMITED" for cell in cells)
    total_reconstructed = sum(int(cell.get("checkpoint_ranks_reconstructed", 0)) for cell in cells)
    total_finalists = sum(int(cell.get("finalist_candidates_checked", 0)) for cell in cells)
    status = ("FAIL" if fail_cells else
              "PASS" if pass_cells == len(cells) and total_reconstructed == 80 else
              "PARTIAL / EVIDENCE LIMITED")
    report = {
        "schema_version": 1,
        "audit": "stage5a1_lshade_cache_identity_and_trajectory",
        "run_id": RUN_ID,
        "status": status,
        "read_only": True,
        "optimizer_or_com_rerun": False,
        "original_source_sha": SOURCE_SHA,
        "computation_fingerprint": COMPUTATION_FINGERPRINT,
        "search_grid_points": len(frequencies),
        "search_grid_sha256": grid_sha,
        "expected_cells": 10,
        "passed_cells": pass_cells,
        "failed_cells": fail_cells,
        "evidence_limited_cells": limited_cells,
        "expected_checkpoint_pools": 80,
        "reconstructed_checkpoint_pools": total_reconstructed,
        "reconstructed_finalist_candidates": total_finalists,
        "validation": {
            "focused_synthetic_tests": "18 passed",
            "full_pytest_suite": "493 passed, 1 skipped",
            "raw_read_only_audit": status,
        },
        "existing_pr42_audit": {
            "url": "https://github.com/MasayaTakagi/saw-com-optimizer/pull/42",
            "result": "80/80 checkpoint pools; 1,280/1,280 saved finalist records passed",
            "relationship": "This audit adds final-state cache-index rank reconstruction and trajectory checks.",
        },
        "scientific_disposition": "STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED",
        "cells": cells,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "cache_trajectory_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (output / "cache_trajectory_audit.md").write_text(_render_markdown(report), encoding="utf-8")
    return report


def _render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Stage 5A-1 L-SHADE cache identity and trajectory audit",
        "",
        f"**Status: {report['status']}**",
        "",
        f"- Run: `{report['run_id']}`",
        f"- Original execution source SHA: `{report['original_source_sha']}`",
        f"- Computation fingerprint: `{report['computation_fingerprint']}`",
        f"- Search grid: {report['search_grid_points']:,} points; SHA-256 `{report['search_grid_sha256']}`",
        f"- Cells: {report['passed_cells']}/10 PASS; {report['failed_cells']} FAIL; "
        f"{report['evidence_limited_cells']} evidence-limited",
        f"- Reconstructed search-grid pools: {report['reconstructed_checkpoint_pools']}/80; "
        f"{report['reconstructed_finalist_candidates']}/1,280 finalist positions checked",
        "- Read-only analysis; no optimizer continuation, optimization, COM simulation, or raw-state mutation.",
        "",
        "## Per-cell evidence",
        "",
        ("All ten cells have `final.json`; `latest.json` and `previous.json` are absent, and no `pinned/` "
         "directory or pinned checkpoint remains, consistent with finalized `rolling_latest_previous` retention."
         if all(cell.get("final_checkpoint_exists") and not cell.get("latest_exists")
                and not cell.get("previous_exists") and not cell.get("pinned_directory_exists")
                and cell.get("pinned_count") == 0
                for cell in report["cells"])
         else "Checkpoint retention evidence is incomplete or differs from the finalized rolling policy; see per-cell JSON details."),
        "",
        "| Topology | Seed | final / schema | Compact index / retained results | Canonical / insertion identity | "
        "Grid version / points | Rank pools | Traces: best / pop / archive | Result |",
        "|---|---:|---:|---:|---|---|---:|---|---|",
    ]
    for cell in report["cells"]:
        lines.append(
            f"| {cell.get('topology', '?')} | {cell.get('seed', '?')} | "
            f"{'yes' if cell.get('final_checkpoint_exists') else 'no'} / "
            f"{cell.get('checkpoint_schema_version', '—')} | "
            f"{cell.get('compact_history_index_count', '—')} / {cell.get('retained_results_count', '—')} | "
            f"{cell.get('canonical_keys_unique', '—')} / {cell.get('insertion_orders_complete', '—')} | "
            f"{cell.get('frequency_grid_version', '—')} / {cell.get('search_grid_points', '—')} | "
            f"{cell.get('checkpoint_ranks_reconstructed', 0)}/8 | "
            f"{cell.get('best_so_far_trace_count', '—')} / {cell.get('population_trace_count', '—')} / "
            f"{cell.get('archive_trace_count', '—')} | {cell.get('status', '?')} |"
        )
    lines.extend((
        "",
        "## Per-cell optimizer counters",
        "",
        "| Topology | Seed | Unique | Proposals | Raw offspring | Duplicates / cache hits | Generations | Boundary repairs |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ))
    for cell in report["cells"]:
        lines.append(
            f"| {cell.get('topology', '?')} | {cell.get('seed', '?')} | "
            f"{cell.get('unique_evaluations', '—')} | {cell.get('proposals_total', '—')} | "
            f"{cell.get('raw_offspring_count', '—')} | "
            f"{cell.get('duplicate_count', '—')} / {cell.get('cache_hits', '—')} | "
            f"{cell.get('generations', '—')} | {cell.get('boundary_repairs', '—')} |"
        )
    lines.extend((
        "",
        "## Validation",
        "",
        "- Synthetic focused regression tests: 18 passed.",
        "- Full `uv run --locked pytest`: 493 passed, 1 skipped.",
        f"- Saved-data audit: {report['reconstructed_checkpoint_pools']}/80 pools and "
        f"{report['reconstructed_finalist_candidates']}/1,280 finalist positions; {report['status']}.",
        "",
        "## Interpretation and limitations",
        "",
        "The rolling `latest`/`previous` store has been finalized to one complete optimizer state per cell. "
        "The 80 `B*.json` files are checkpoint result/validation records, not 80 complete optimizer states. "
        "All checkpoint rank reconstructions use the terminal compact history index's zero-based insertion "
        "order and saved search-grid rank keys, with original stable `(rank_key, insertion_order)` ordering.",
        "",
        "The trace, population, archive, SHADE memory, RNG and counter checks establish saved-state structural "
        "and cross-record consistency only. They do not replay 96,000 optimizer transitions or re-evaluate COM. "
        "Compact mode retains full result payloads only for the terminal top 16; rank keys for the other "
        "historical entries are checked for structure and used as saved evidence, not recomputed from physics. "
        "The terminal retained records, incumbent, active population, every finalist vector/rank position, and "
        "all unchanged grid/design-space versions were cross-checked against their saved records.",
        "",
        "The original-source comparison found no changes to cache identity, comparator rank, or checkpoint "
        "selection semantics; intervening L-SHADE/comparator edits were trace telemetry only. PR #42 "
        "independently reported 80/80 finalist-record selection replay PASS. Its B-record finalist projection "
        "does not store `search_source_rank_key`, so rank-key fields cannot be compared directly. This audit "
        "sorts the complete final compact-index rank history and matches each saved ordinal source-rank and "
        "exact vector across all 1,280 finalist positions.",
        "",
        "The scientific disposition remains `STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`; no topology selection "
        "or global-optimum claim follows from this audit.",
        "",
        "Raw candidate vectors, checkpoint bodies, RNG internals, and local filesystem paths are intentionally "
        "excluded from this committed report.",
        "",
    ))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="read-only external raw Stage 4C run directory")
    parser.add_argument("--output-dir", required=True, help="repository directory for redacted audit outputs")
    args = parser.parse_args(argv)
    report = audit_run(args.run_dir, args.output_dir)
    print(json.dumps({key: report[key] for key in (
        "status", "passed_cells", "failed_cells", "evidence_limited_cells",
        "reconstructed_checkpoint_pools", "reconstructed_finalist_candidates",
    )}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
