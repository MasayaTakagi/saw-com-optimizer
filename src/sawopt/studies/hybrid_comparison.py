"""Current, matched-budget study over the qualified hybrid topology families."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..core.hybrid import RESONATOR_BOUNDS
from ..io.checkpoints import complete_study_run
from ..io.config import load_experiment_config
from ..io.lifecycle import RunDisposition
from ..io.provenance import build_fingerprint_metadata
from ..optimization.counters import GeometryGateCounters, evaluation_status
from ..optimizers.checkpoint_session import LShadeCheckpointSession
from ..optimizers.lshade import LShadeBackend
from ..optimizers.selection import GeometryFirstComparator
from ..problem.dms_topologies import T1
from ..problem.hybrid import HYBRID_TOPOLOGIES, HybridDesignSpace, hybrid_geometry
from ..reporting.review_bundle import ReviewBundleSpec, build_review_bundle
from .dms_topology_screening import material_bounds
from .hybrid import (
    active_bound_diagnostics,
    clean_json_value,
    evaluate_hybrid_candidate,
    git_state_snapshot,
    load_hybrid_context,
    write_json_artifact,
    validate_hybrid_d_only_parity,
    validate_hybrid_structure,
)


ROOT = Path(__file__).resolve().parents[3]
STUDY_TYPE = "hybrid_topology_screening"
PRODUCTION_SEEDS = (20260917, 20260918)
PRODUCTION_TOPOLOGIES = ("D", "P_D", "D_P", "P_D_P")
STAGE4B_DECISION_POLICY = {
    "study_role": "screening_only",
    "authoritative_primary_stratum": "equal_budget_B4000",
    "normalized_sensitivity_may_replace_primary": False,
    "automatic_topology_promotion": False,
    "automatic_topology_elimination": False,
    "post_stage4b_candidate_topologies": list(PRODUCTION_TOPOLOGIES),
    "narrowing_gate": "separately_predeclared_selection_gate",
}
STAGE4B_REQUIRED_ARTIFACTS = (
    "summary.md", "REVIEW_ME.md", "config_snapshot.yaml", "topology_results.json",
    "topology_results.csv", "metadata/resolved_contract.json",
    "metadata/computation_fingerprint.json", "metadata/run_source_metadata.json",
    "metadata/implementation_validation.json", "metadata/fairness_contract.json",
    "metadata/initializer_accounting.json", "metadata/checkpoint_accounting.json",
    "metadata/c2c_review_status.json", "metadata/run_completion.json",
    "metadata/recovery_policy.json", "metadata/trajectory.csv",
    "metadata/review_bundle.json",
)


def _json_clean(value: Any) -> Any:
    return clean_json_value(value)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(set().union(*(row.keys() for row in rows))) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(_json_clean(row) for row in rows)


def _topology_selection(cfg: Mapping[str, Any], *, mode: str) -> tuple[str, ...]:
    selected = tuple(str(item) for item in cfg["hybrid_comparison"].get(
        "topologies", PRODUCTION_TOPOLOGIES,
    ))
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("hybrid_comparison.topologies must be a unique non-empty list")
    unknown = [value for value in selected if value not in PRODUCTION_TOPOLOGIES]
    if unknown:
        raise ValueError(f"unsupported Stage 4B topology: {unknown}")
    if mode == "production" and selected != PRODUCTION_TOPOLOGIES:
        raise ValueError("production configuration must contain D, P_D, D_P, and P_D_P in order")
    return selected


def _resolved_context(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    if not path.is_absolute():
        path = ROOT / path
    raw_text = path.read_text(encoding="utf-8")
    cfg = load_experiment_config(path)
    study = cfg.get("study", {})
    if study.get("type") != STUDY_TYPE:
        raise ValueError(f"expected study.type={STUDY_TYPE!r}")
    mode = str(study.get("mode", "production"))
    if mode not in {"production", "orchestration_smoke"}:
        raise ValueError("study.mode must be 'production' or 'orchestration_smoke'")

    # Reuse the Stage 4A-qualified current T1/provider/grid/design-space
    # resolver. Its qualification fingerprint is replaced below with the
    # Stage 4B contract and dependency set.
    context = load_hybrid_context(path)
    settings = cfg.get("hybrid_comparison", {})
    topologies = _topology_selection(cfg, mode=mode)
    decision_policy = settings.get("decision_policy")
    if (not isinstance(decision_policy, Mapping)
            or dict(decision_policy) != STAGE4B_DECISION_POLICY):
        raise ValueError(
            "Stage 4B decision_policy must preserve screening-only, B4000-primary, "
            "no-automatic-promotion/elimination behavior"
        )
    seeds = tuple(int(seed) for seed in cfg["dms_topology"].get("seeds", ()))
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("dms_topology.seeds must be a unique non-empty list")
    if mode == "production" and seeds != PRODUCTION_SEEDS:
        raise ValueError(f"production seed contract must be {list(PRODUCTION_SEEDS)}")
    if cfg["dms_topology"].get("cold_start") is not True or settings.get("cold_start") is not True:
        raise ValueError("Stage 4B requires independent cold starts")
    if settings.get("material") != "MLIT" or settings.get("dms_topology") != T1:
        raise ValueError("Stage 4B is fixed to MLIT / current T1")
    if float(cfg["hybrid"]["source_impedance_ohm"]) != 50.0 or float(
        cfg["hybrid"]["load_impedance_ohm"]
    ) != 50.0:
        raise ValueError("Stage 4B is fixed to 50/50 ohm")

    primary_budget = int(settings.get("primary_budget", 0))
    baseline_dimension = int(settings.get("baseline_dimension", 0))
    evaluations_per_dimension = int(settings.get("evaluations_per_dimension", 0))
    schedule_horizon = int(settings.get("population_schedule_terminal_budget", 0))
    if primary_budget <= 0 or evaluations_per_dimension <= 0:
        raise ValueError("primary_budget and evaluations_per_dimension must be positive")
    if schedule_horizon != primary_budget:
        raise ValueError("L-SHADE schedule horizon must remain the primary B4000 budget")
    if mode == "production" and primary_budget != 4000:
        raise ValueError("production primary budget must be exactly 4,000 unique evaluations")
    dimensions = {name: context["spaces"][name].dimension for name in PRODUCTION_TOPOLOGIES}
    if mode == "production":
        if baseline_dimension != dimensions["D"]:
            raise ValueError("the normalized-budget baseline dimension must match D")
        if primary_budget / baseline_dimension != evaluations_per_dimension:
            raise ValueError(
                "evaluations_per_dimension must equal primary_budget / baseline_dimension"
            )
    targets = {
        name: max(primary_budget, evaluations_per_dimension * dimensions[name])
        for name in topologies
    }
    declared_targets = {
        str(name): int(value)
        for name, value in settings.get("normalized_targets", {}).items()
    }
    derived_selected_targets = {name: targets[name] for name in topologies}
    derived_production_targets = {name: max(
        primary_budget, evaluations_per_dimension * dimensions[name],
    ) for name in PRODUCTION_TOPOLOGIES}
    if mode == "production" and declared_targets != derived_production_targets:
        raise ValueError(
            "configured normalized_targets must exactly match the dimension formula "
            "for all production topologies"
        )
    if mode != "production" and declared_targets and declared_targets != derived_selected_targets:
        raise ValueError("smoke normalized_targets disagree with the derived target formula")
    per_dimension = cfg["dms_topology"].get("initial_population_per_dimension")
    population_override = cfg["dms_topology"].get("initial_population")
    initial_populations = {
        name: max(4, int(population_override if population_override is not None
                         else int(per_dimension) * dimensions[name]))
        for name in topologies
    }
    if mode == "production":
        if int(per_dimension or 0) != 18 or population_override is not None:
            raise ValueError("production initialization must use exactly 18 × dimension members")
        if tuple(cfg["hybrid"]["supported_topologies"]) != PRODUCTION_TOPOLOGIES:
            raise ValueError("production hybrid topology contract is not the four approved families")
        if settings.get("primary_and_sensitivity_are_separate") is not True:
            raise ValueError("primary and normalized sensitivity strata must remain separate")
    else:
        if settings.get("production_launch_authorized") is True or cfg["hybrid"].get(
            "production_launch_authorized", False,
        ) is True:
            raise ValueError("smoke fixtures cannot authorize Stage 4B production")
        if any(target > 256 for target in targets.values()):
            raise ValueError("orchestration smoke budgets must remain at or below 256")
        if len(topologies) > 2 or len(seeds) > 1:
            raise ValueError("orchestration smoke must be a small bounded fixture")
        if any(initial_populations[name] > primary_budget for name in topologies):
            raise ValueError("smoke population must fit within its bounded budget")

    configured_checkpoints = tuple(int(value) for value in settings.get(
        "checkpoint_budgets", cfg["dms_topology"].get("checkpoints", ()),
    ))
    if not configured_checkpoints or tuple(sorted(set(configured_checkpoints))) != configured_checkpoints:
        raise ValueError("checkpoint_budgets must be a strictly increasing unique sequence")
    if primary_budget not in configured_checkpoints:
        raise ValueError("the common B4000 primary endpoint must be checkpointed")
    diagnostic_factors = tuple(int(value) for value in settings.get(
        "diagnostic_lattice_evaluations_per_dimension", (),
    ))
    if (any(value <= 0 for value in diagnostic_factors)
            or tuple(sorted(set(diagnostic_factors))) != diagnostic_factors):
        raise ValueError(
            "diagnostic_lattice_evaluations_per_dimension must be a strictly increasing "
            "sequence of positive integers"
        )
    diagnostic_checkpoints = {
        name: tuple(factor * dimensions[name] for factor in diagnostic_factors
                    if factor * dimensions[name] <= targets[name])
        for name in topologies
    }
    checkpoints = {
        name: tuple(sorted(set(value for value in (
            *configured_checkpoints, *diagnostic_checkpoints[name], targets[name],
        )
                               if value <= targets[name])))
        for name in topologies
    }
    if any(value < initial_populations[name] for name in topologies for value in checkpoints[name]):
        raise ValueError("checkpoints cannot precede the initial population")
    finalists = int(settings.get("common_grid_finalists", cfg["hybrid"].get(
        "common_grid_finalists", 16,
    )))
    if finalists <= 0:
        raise ValueError("common_grid_finalists must be positive")

    dms_active, dms_hard, _ = material_bounds(cfg, "MLIT", T1)
    dimensions_contract = {
        name: {
            "dimension": dimensions[name],
            "initial_population": initial_populations[name],
            "primary_budget": primary_budget,
            "primary_evaluations_per_dimension": primary_budget / dimensions[name],
            "normalized_target": targets[name],
            "normalized_target_evaluations_per_dimension": targets[name] / dimensions[name],
            "hard_max_budget_from_cold_start": targets[name],
            "population_schedule_terminal_budget": schedule_horizon,
            "checkpoints": list(checkpoints[name]),
            "diagnostic_lattice_checkpoint_budgets": list(diagnostic_checkpoints[name]),
        }
        for name in topologies
    }
    cfg_path_for_hash = None
    try:
        cfg_path_for_hash = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        pass
    grid_metadata_path = Path(context["grid_metadata"]["metadata_path"])
    grid_file = Path(context["grid_metadata"]["source"])
    if not grid_file.is_absolute():
        grid_file = ROOT / grid_file
    profile_path = Path(cfg["dms_topology"]["materials"]["MLIT"]["profile_file"])
    if not profile_path.is_absolute():
        profile_path = ROOT / profile_path
    paths = [
        "configs/studies/dms_topology_screening.yaml",
        "configs/base/b28_dms_baseline.yaml",
        "src/sawopt/problem/hybrid.py", "src/sawopt/problem/dms_topologies.py",
        "src/sawopt/core/hybrid.py", "src/sawopt/core/topology.py",
        "src/sawopt/core/com.py", "src/sawopt/core/models.py",
        "src/sawopt/core/metrics.py", "src/sawopt/core/network.py",
        "src/sawopt/core/literature_com.py",
        "src/sawopt/studies/hybrid.py", "src/sawopt/studies/hybrid_comparison.py",
        "src/sawopt/studies/dms_topology_common.py",
        "src/sawopt/studies/dms_topology_screening.py",
        "src/sawopt/optimizers/lshade.py", "src/sawopt/optimizers/selection.py",
        "src/sawopt/optimizers/checkpoint_session.py",
        "src/sawopt/optimization/counters.py", "src/sawopt/optimization/population.py",
        "src/sawopt/io/config.py", "src/sawopt/io/provenance.py",
        "src/sawopt/io/checkpoints.py", "src/sawopt/io/lifecycle.py",
        "src/sawopt/io/legacy_lifecycle.py", "src/sawopt/__main__.py",
        "src/sawopt/orchestration/worker.py",
        grid_metadata_path.resolve().relative_to(ROOT).as_posix(),
        grid_file.resolve().relative_to(ROOT).as_posix(),
        profile_path.resolve().relative_to(ROOT).as_posix(),
    ]
    if cfg_path_for_hash:
        paths.append(cfg_path_for_hash)
    computation_paths = tuple(dict.fromkeys(paths))
    reporting_paths = (
        "src/sawopt/reporting/review_bundle.py",
        "src/sawopt/reporting/hybrid_topology_report.py",
    )
    contract = {
        "study_type": STUDY_TYPE,
        "study_revision": study.get("revision"),
        "input_config_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "material": "MLIT", "material_profile_metadata": context["profile_metadata"],
        "dms_topology": T1,
        "dms_active_bounds": np.asarray(dms_active, dtype=float).tolist(),
        "dms_hard_bounds": np.asarray(dms_hard, dtype=float).tolist(),
        "resonator_bounds": np.asarray(cfg["hybrid"]["resonator_bounds"], dtype=float).tolist(),
        "topologies": list(topologies), "dimensions": dimensions_contract,
        "seeds": list(seeds), "cold_start": True,
        "initializer": {
            "method": cfg["hybrid"]["initializer"]["method"],
            "seed_derivation": cfg["hybrid"]["initializer"]["seed_derivation"],
            "max_attempts": int(cfg["hybrid"]["initializer"]["max_attempts"]),
            "historical_designs_included": False,
        },
        "source_impedance_ohm": 50.0, "load_impedance_ohm": 50.0,
        "specification": cfg["spec"], "geometry_constraints": cfg["constraints"],
        "search_frequency_count": int(len(context["search_frequencies"])),
        "search_frequency_sha256": context["contract"]["search_frequency_sha256"],
        "common_validation_grid_id": context["common_grid_id"],
        "common_validation_frequency_count": int(len(context["common_frequencies"])),
        "common_validation_grid_sha256": context["grid_metadata"]["sha256"],
        "primary_budget_unit": "unique decoded canonical evaluations",
        "primary_budget": primary_budget,
        "normalized_budget_formula": "max(primary_budget, evaluations_per_dimension * dimension)",
        "evaluations_per_dimension": evaluations_per_dimension,
        "baseline_dimension": baseline_dimension,
        "normalized_targets": derived_selected_targets,
        "decision_policy": decision_policy,
        "production_launch_authorized": bool(
            settings.get("production_launch_authorized", False)
        ),
        "diagnostic_lattice_evaluations_per_dimension": list(diagnostic_factors),
        "population_schedule_terminal_budget": schedule_horizon,
        "common_grid_finalists": finalists,
        "lshade": cfg["dms_topology"].get("lshade", {}),
        "geometry_first_comparator": True,
        "mode": mode,
    }
    fingerprint = build_fingerprint_metadata(
        ROOT, contract, computation_paths=computation_paths,
        reporting_paths=reporting_paths,
    )
    context.update({
        "cfg": cfg, "config_path": path.resolve(), "root": ROOT,
        "contract": contract, "fingerprint": fingerprint,
        "computation_paths": computation_paths, "reporting_paths": reporting_paths,
        "topologies": topologies, "seeds": seeds,
        "primary_budget": primary_budget, "evaluations_per_dimension": evaluations_per_dimension,
        "targets": targets, "dimensions": dimensions,
        "initial_populations": initial_populations, "checkpoints": checkpoints,
        "diagnostic_factors": diagnostic_factors,
        "diagnostic_checkpoints": diagnostic_checkpoints,
        "finalists": finalists, "mode": mode,
    })
    return context


def _sample_initial_population(space: HybridDesignSpace, cfg: Mapping[str, Any], *,
                               seed: int, topology: str, population_size: int,
                               max_attempts: int) -> tuple[np.ndarray, dict[str, Any]]:
    payload = (
        f"hybrid-topology-screening-v1/{int(seed)}/MLIT/{topology}/initial_population"
    )
    sampling_seed = int.from_bytes(
        hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big",
    ) % (2**32)
    rng = np.random.default_rng(sampling_seed)
    low, high = space.bounds[:, 0], space.bounds[:, 1]
    accepted: list[np.ndarray] = []
    seen: set[tuple[float, ...]] = set()
    draws = geometry_rejections = duplicate_rejections = 0
    feasible_draws = 0
    rejection_reasons: dict[str, int] = {}
    while len(accepted) < population_size and draws < max_attempts:
        draws += 1
        proposed = low + rng.random(space.dimension) * (high - low)
        canonical, key = space.canonicalize(proposed)
        layout = hybrid_geometry(space.decode(canonical), cfg)
        if not math.isfinite(float(layout["max_violation"])) or float(layout["max_violation"]) > 0.0:
            geometry_rejections += 1
            violations = {
                **{f"dms_{key}": value for key, value in layout["dms"]["violations"].items()},
                **layout["resonator_violations"],
                **{f"combined_{key}": value for key, value in layout["combined"]["violations"].items()},
            }
            for reason, value in violations.items():
                if float(value) > 0.0:
                    rejection_reasons[str(reason)] = rejection_reasons.get(str(reason), 0) + 1
            continue
        feasible_draws += 1
        if key in seen:
            duplicate_rejections += 1
            continue
        seen.add(key)
        accepted.append(np.asarray(canonical, dtype=float))
    if len(accepted) != population_size:
        raise RuntimeError(
            f"{topology} initializer accepted {len(accepted)}/{population_size} members "
            f"after {draws}/{max_attempts} proposals"
        )
    physical = np.asarray(accepted, dtype=float)
    normalized = (physical - low) / (high - low)
    integer_distribution = {}
    for index in space.integer_indices:
        values, counts = np.unique(physical[:, index].astype(int), return_counts=True)
        integer_distribution[str(index)] = {
            "variable": space.variable_names[index] if hasattr(space, "variable_names") else f"x{index}",
            "counts": {str(int(value)): int(count) for value, count in zip(values, counts)},
        }
    coverage = []
    for index in range(space.dimension):
        coverage.append({
            "index": index, "lower": float(physical[:, index].min()),
            "upper": float(physical[:, index].max()),
            "normalized_width": float(normalized[:, index].max() - normalized[:, index].min()),
        })
    diagnostics = {
        "method": "independent_uniform_rejection_v1",
        "seed": int(seed), "topology": topology,
        "initial_population_seed": sampling_seed,
        "requested_population_size": int(population_size),
        "accepted_population_size": int(len(accepted)),
        "candidate_draws": int(draws), "geometry_rejections": int(geometry_rejections),
        "duplicate_rejections": int(duplicate_rejections),
        "feasible_unique_volume_estimate": (
            float(feasible_draws / draws) if draws else None
        ),
        "geometry_rejection_reasons": rejection_reasons,
        "integer_variable_distribution": integer_distribution,
        "per_coordinate_coverage": coverage,
        "historical_designs_included": False,
        "warm_start": False, "parent_transfer": False,
    }
    if draws != geometry_rejections + duplicate_rejections + len(accepted):
        raise AssertionError("initializer proposal accounting identity failed")
    return normalized, diagnostics


def _runtime_targets(context: Mapping[str, Any], topology: str) -> tuple[int, ...]:
    return context["checkpoints"][topology]


def _search_counter_snapshot(counters: GeometryGateCounters, backend: LShadeBackend,
                             frequency_count: int) -> dict[str, Any]:
    unique = int(backend.unique_evaluations)
    if unique != counters.geometry_rejections + counters.geometry_valid_candidates:
        raise AssertionError("unique evaluation accounting partition failed")
    if counters.geometry_valid_candidates != counters.valid_physics_evaluations + counters.physics_failures:
        raise AssertionError("geometry/physics accounting partition failed")
    if counters.search_frequency_points != counters.valid_physics_evaluations * int(frequency_count):
        raise AssertionError("search frequency point accounting failed")
    summary = backend.summary()
    return {
        "unique_decoded_evaluations": unique,
        "geometry_rejections": int(counters.geometry_rejections),
        "geometry_valid_candidates": int(counters.geometry_valid_candidates),
        "physics_attempted_evaluations": int(counters.physics_attempted_evaluations),
        "valid_physics_evaluations": int(counters.valid_physics_evaluations),
        "physics_failures": int(counters.physics_failures),
        "search_frequency_points_solved": int(counters.search_frequency_points),
        "validation_evaluations": int(counters.validation_evaluations),
        "validation_frequency_points_solved": int(counters.validation_solved_frequency_points),
        "cache_hits": int(summary["cache_hits"]),
        "objective_proposals": int(summary["proposals_total"]),
        "duplicate_proposals": int(summary["duplicate_count"]),
        "generations": int(summary["generations"]),
        "population_size": int(summary["population_size"]),
        "initial_population": int(summary["initial_population"]),
        "population_schedule_terminal_budget": int(summary["population_schedule_terminal_budget"]),
    }


def _common_validation(
    context: Mapping[str, Any], topology: str, seed: int, budget: int,
    backend: LShadeBackend, counters: GeometryGateCounters,
) -> dict[str, Any]:
    space = context["spaces"][topology]
    cache = [value for value in backend._cache.values()
             if evaluation_status(value) == "PHYSICS_EVALUATED"]
    cache.sort(key=backend.comparator.rank_key)
    finalists = cache[:int(context["finalists"])]
    if not finalists:
        raise RuntimeError(f"{topology}/seed{seed}/B{budget} has no physics-evaluated finalist")
    started = time.perf_counter()
    validated: list[dict[str, Any]] = []
    for rank, source in enumerate(finalists, start=1):
        candidate = space.decode(source["candidate_vector"])
        counters.validation_evaluations += 1
        record = evaluate_hybrid_candidate(
            candidate, context["provider"], context["cfg"], context["common_frequencies"],
            context["source_impedance_ohm"], context["load_impedance_ohm"],
            include_spectrum=True,
        )
        if evaluation_status(record) == "PHYSICS_EVALUATED":
            counters.validation_solved_frequency_points += len(context["common_frequencies"])
        else:
            counters.validation_physics_failures += 1
        record["search_source_rank"] = rank
        record["search_source_rank_key"] = list(backend.comparator.rank_key(source))
        validated.append(record)
    elapsed = time.perf_counter() - started
    eligible = [record for record in validated if evaluation_status(record) == "PHYSICS_EVALUATED"]
    if not eligible:
        raise RuntimeError(f"{topology}/seed{seed}/B{budget} common-grid validation failed")
    selected = min(eligible, key=backend.comparator.rank_key)
    return {
        "status": "PASS", "topology": topology, "seed": int(seed),
        "absolute_unique_evaluations": int(budget),
        "evaluations_per_dimension": float(budget / space.dimension),
        "common_validation_grid_id": context["common_grid_id"],
        "frequency_count": int(len(context["common_frequencies"])),
        "validation_wall_time_s": float(elapsed),
        "finalists_requested": int(context["finalists"]),
        "finalists_validated": len(validated),
        "selected": selected,
        "validated_finalists": validated,
    }


def _cell_result(
    context: Mapping[str, Any], topology: str, seed: int, budget: int,
    backend: LShadeBackend, counters: GeometryGateCounters,
    validation: Mapping[str, Any], initializer: Mapping[str, Any],
    checkpoint_rows: Sequence[Mapping[str, Any]], wall_time_s: float,
    evaluation_time_s: float,
) -> dict[str, Any]:
    selected = validation["selected"]
    violations = selected.get("violations", {})
    dominant = sorted(
        ((str(key), float(value)) for key, value in violations.items() if float(value) > 0.0),
        key=lambda item: item[1], reverse=True,
    )[:5]
    if not dominant:
        dominant = [("none", 0.0)]
    metrics = selected.get("metrics", {})
    vector = selected["candidate_vector"]
    return {
        "material": "MLIT", "dms_topology": T1, "hybrid_topology": topology,
        "topology": topology, "seed": int(seed), "absolute_unique_evaluations": int(budget),
        "evaluations_per_dimension": float(budget / context["dimensions"][topology]),
        "search_objective": float(selected["objective"]),
        "common_grid_result": {
            "validation_status": validation["status"],
            "grid_id": validation["common_validation_grid_id"],
            "frequency_count": validation["frequency_count"],
            "max_violation": float(selected["max_violation"]),
            "sum_violation": float(selected["sum_violation"]),
            "feasible": bool(selected["feasible"]),
            "worst_il_db": metrics.get("worst_il_db"),
            "ripple_db": metrics.get("ripple_db"),
            "dominant_violations": dominant,
            "constraint_decomposition": {
                "violations": violations,
                "geometry_violations": selected.get("geometry_violations", {}),
            },
        },
        "decoded_dms_design": selected.get("dms_design"),
        "dms_design_vector": selected["candidate_vector"][:10],
        "decoded_resonator_designs": selected.get("resonator_designs", []),
        "resonator_vectors": selected["candidate_vector"][10:],
        "design_vector": vector,
        "geometry_layout_diagnostics": selected.get("geometry_dimensions"),
        "active_bound_diagnostics": active_bound_diagnostics(vector, context["spaces"][topology].bounds),
        "source_impedance_ohm": 50.0, "load_impedance_ohm": 50.0,
        "cold_start": True, "warm_start": False, "parent_transfer": False,
        "initializer_diagnostics": initializer,
        "optimizer": {
            "backend": "LShadeBackend", "comparator": "GeometryFirstComparator",
            "hard_max_budget": int(context["targets"][topology]),
            "population_schedule_terminal_budget": int(context["primary_budget"]),
            "initial_population": int(context["initial_populations"][topology]),
            "unique_evaluations": int(backend.unique_evaluations),
            "accounting": _search_counter_snapshot(
                counters, backend, len(context["search_frequencies"]),
            ),
        },
        "runtime": {
            "wall_time_s": float(wall_time_s),
            "validation_time_s": float(validation["validation_wall_time_s"]),
            "com_network_evaluation_time_s": float(evaluation_time_s),
            "frequency_points_solved": int(counters.solved_frequency_points),
            "cache_hits": int(backend.summary()["cache_hits"]),
            "failure_count": int(counters.physics_failures + counters.validation_physics_failures),
        },
        "checkpoint_snapshots": list(checkpoint_rows),
        "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
        "fingerprint_schema_version": 2,
        "common_validation_grid_id": context["common_grid_id"],
        "source_revision": git_state_snapshot(context["root"]),
    }


def _write_reports(run: Path, result: Mapping[str, Any], context: Mapping[str, Any]) -> None:
    from ..reporting.hybrid_topology_report import write_hybrid_topology_reports
    write_hybrid_topology_reports(run, result, context)


def validate_hybrid_topology_screening(config_path: str | Path,
                                       run_path: str | Path) -> dict[str, Any]:
    """Fail-closed implementation validation; it never starts optimization."""
    context = _resolved_context(config_path)
    run = Path(run_path)
    if not run.is_absolute():
        run = ROOT / run
    run.mkdir(parents=True, exist_ok=True)
    metadata = run / "metadata"
    metadata.mkdir(parents=True, exist_ok=True)
    (run / "config_snapshot.yaml").write_text(
        context["config_path"].read_text(encoding="utf-8"), encoding="utf-8",
    )
    write_json_artifact(metadata / "resolved_contract.json", context["contract"])
    write_json_artifact(metadata / "computation_fingerprint.json", context["fingerprint"])
    write_json_artifact(metadata / "run_source_metadata.json", {
        "study_type": STUDY_TYPE, "git": git_state_snapshot(context["root"]),
        "fingerprint_schema_version": 2,
        "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
        "reporting_fingerprint": context["fingerprint"]["reporting_fingerprint"],
        "stage4b_launched": False,
        "cold_start": True,
    })
    checks: dict[str, Any] = {"status": "PASS", "stage4b_launched": False}
    try:
        parity = validate_hybrid_d_only_parity(context)
        structure = validate_hybrid_structure(context)
        structure["status"] = "PASS"
        populations = {}
        for topology in context["topologies"]:
            size = context["initial_populations"][topology]
            _population, diagnostics = _sample_initial_population(
                context["spaces"][topology], context["cfg"], seed=context["seeds"][0],
                topology=topology, population_size=size,
                max_attempts=int(context["cfg"]["hybrid"]["initializer"]["max_attempts"]),
            )
            populations[topology] = diagnostics
        optimizer = {
            topology: {
                "dimension": context["dimensions"][topology],
                "initial_population": context["initial_populations"][topology],
                "population_fraction_of_primary_budget": (
                    context["initial_populations"][topology] / context["primary_budget"]
                ),
                "primary_budget": context["primary_budget"],
                "hard_max_budget": context["targets"][topology],
                "population_schedule_terminal_budget": context["primary_budget"],
                "checkpoints": list(context["checkpoints"][topology]),
                "diagnostic_lattice_checkpoint_budgets": list(
                    context["diagnostic_checkpoints"][topology]
                ),
                "backend": LShadeBackend.__name__,
                "scipy_differential_evolution_used": False,
            }
            for topology in context["topologies"]
        }
        checks.update({
            "d_only_parity": parity,
            "hybrid_structure": structure,
            "initial_population": populations,
            "optimizer_and_accounting": optimizer,
            "validation_grid_contract": {
                "search_frequency_count": len(context["search_frequencies"]),
                "search_frequency_sha256": context["contract"]["search_frequency_sha256"],
                "common_validation_grid_id": context["common_grid_id"],
                "common_validation_frequency_count": len(context["common_frequencies"]),
                "same_common_grid_for_all_topologies": True,
                "stopbands": context["cfg"]["spec"]["stopbands"],
            },
            "provenance_status": {
                "schema_version": 2,
                "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
                "computation_dependencies": context["fingerprint"]["dependency_manifest"]["computation"],
                "reporting_dependencies": context["fingerprint"]["dependency_manifest"]["reporting"],
            },
            "checkpoint_lifecycle": {
                "checkpoint_session": "LShadeCheckpointSession",
                "success_disposition": "REVIEW_WAITING",
                "execution_failure_disposition": "FAILED",
                "worker_explicit_disposition_resolver": "resolve_process_disposition",
            },
            "launch_authorization": {
                "production_launch_authorized": context["contract"][
                    "production_launch_authorized"
                ],
                "stage4b_launched": False,
            },
        })
    except Exception as exc:
        checks.update({"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)})
    write_json_artifact(metadata / "implementation_validation.json", checks)
    return checks


def _ensure_implementation_gate(config_path: str | Path, run: Path) -> dict[str, Any]:
    path = run / "metadata" / "implementation_validation.json"
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = {}
        if value.get("status") == "PASS":
            return value
    value = validate_hybrid_topology_screening(config_path, run)
    if value.get("status") != "PASS":
        raise RuntimeError("hybrid implementation validation did not PASS; optimizer not started")
    return value


def _run_cell(context: Mapping[str, Any], run: Path, topology: str, seed: int,
              *, resume: bool, initializer_registry: list, checkpoint_registry: list) -> tuple[dict, dict]:
    space = context["spaces"][topology]
    target = int(context["targets"][topology])
    initial_size = int(context["initial_populations"][topology])
    topology_dir = run / "optimization" / topology / f"seed{seed}"
    topology_dir.mkdir(parents=True, exist_ok=True)
    initializer_path = topology_dir / "initializer.json"
    if resume:
        if not initializer_path.is_file():
            raise FileNotFoundError(f"resume is missing initializer evidence: {initializer_path}")
        initializer = json.loads(initializer_path.read_text(encoding="utf-8"))
        if (int(initializer.get("accepted_population_size", -1)) != initial_size
                or int(initializer.get("seed", -1)) != int(seed)
                or initializer.get("topology") != topology):
            raise ValueError("resume initializer evidence does not match the current cell contract")
        population = None
    else:
        population, initializer = _sample_initial_population(
            space, context["cfg"], seed=seed, topology=topology,
            population_size=initial_size,
            max_attempts=int(context["cfg"]["hybrid"]["initializer"]["max_attempts"]),
        )
        write_json_artifact(initializer_path, initializer)
    initializer_registry.append({"topology": topology, "seed": seed, **initializer})
    hard_bounds = np.vstack([
        np.asarray(context["contract"]["dms_hard_bounds"], dtype=float),
        *([np.asarray(context["cfg"]["hybrid"]["resonator_bounds"], dtype=float)]
          * (len(space.integer_indices) - 3)),
    ])
    lshade_config = dict(context["cfg"]["dms_topology"].get("lshade", {}))
    lshade_config.update({
        "total_budget": context["primary_budget"],
        "requested_unique_budget": context["primary_budget"],
        "hard_max_budget": target,
        "population_schedule_terminal_budget": context["primary_budget"],
        "initial_population": initial_size,
        "min_population": 4,
        "hard_bounds": hard_bounds.tolist(),
    })
    backend = LShadeBackend(
        space.bounds, seed=seed, config=lshade_config,
        integer_indices=space.integer_indices, canonicalizer=space.canonicalize,
        comparator=GeometryFirstComparator(),
        source_config_fingerprint=context["fingerprint"]["computation_fingerprint"],
    )
    backend.set_frequency_grid(context["search_frequencies"], version=1)
    counters = GeometryGateCounters(initial_sampling={
        "candidate_draws": int(initializer["candidate_draws"]),
        "geometry_rejections": int(initializer["geometry_rejections"]),
        "duplicate_rejections": int(initializer["duplicate_rejections"]),
        "accepted_population_size": int(initializer["accepted_population_size"]),
    })
    timing = {"com_network_evaluation_wall_time_s": 0.0}

    def evaluator(vector):
        candidate = space.decode(vector)
        start = time.perf_counter()
        record = evaluate_hybrid_candidate(
            candidate, context["provider"], context["cfg"], context["search_frequencies"],
            context["source_impedance_ohm"], context["load_impedance_ohm"],
        )
        timing["com_network_evaluation_wall_time_s"] += time.perf_counter() - start
        counters.observe_search(record, len(context["search_frequencies"]))
        return record

    session = LShadeCheckpointSession(
        topology_dir / "checkpoints", run_directory=run,
        legacy_path=topology_dir / "optimizer_checkpoint.json", resume=resume,
    )
    started = time.perf_counter()
    if resume:
        session.load(backend)
        backend.set_evaluator(evaluator)
        counters.restore_from_cache(list(backend._cache.values()), len(context["search_frequencies"]))
        if not backend._population:
            raise ValueError("checkpoint loaded without an optimizer population")
    else:
        if population is None:
            raise AssertionError("cold-start population was not sampled")
        backend.initialize(evaluator, population=population)
    if int(backend.hard_max_budget) != target:
        raise AssertionError("backend hard maximum differs from the predeclared endpoint")
    if int(backend.population_schedule_terminal_budget) != context["primary_budget"]:
        raise AssertionError("rescue changed the L-SHADE schedule horizon")

    trajectory_path = topology_dir / "trajectory.jsonl"
    existing_rows = []
    if resume and trajectory_path.is_file():
        existing_rows = [json.loads(line) for line in trajectory_path.read_text(
            encoding="utf-8",
        ).splitlines() if line.strip()]
    recorded_budgets = {int(row["absolute_unique_evaluations"]) for row in existing_rows}
    checkpoint_rows = list(existing_rows)
    primary_path = topology_dir / "primary_result.json"
    sensitivity_path = topology_dir / "normalized_sensitivity_result.json"
    primary_validation_path = topology_dir / "primary_common_validation.json"
    final_validation_path = topology_dir / "normalized_common_validation.json"
    if resume and backend.unique_evaluations > context["primary_budget"] and not primary_path.is_file():
        raise ValueError("checkpoint passed B4000 without its durable primary result")
    for point in _runtime_targets(context, topology):
        if backend.unique_evaluations > point:
            if point not in recorded_budgets:
                raise ValueError(
                    f"resume checkpoint advanced past B{point} without its trajectory record"
                )
            row = next(item for item in existing_rows
                       if int(item["absolute_unique_evaluations"]) == point)
            if not any(int(item["absolute_unique_evaluations"]) == point
                       for item in checkpoint_rows):
                checkpoint_rows.append(row)
            continue
        if backend.unique_evaluations < point:
            backend.advance_to_unique_budget(point)
        if backend.unique_evaluations != point:
            if backend.search_space_exhausted:
                raise RuntimeError(
                    f"{topology}/seed{seed} exhausted canonical space at "
                    f"{backend.unique_evaluations}, before budget {point}"
                )
            raise AssertionError(f"{topology}/seed{seed} missed exact checkpoint B{point}")
        if point not in recorded_budgets:
            checkpoint_path = session.save(backend)
            snapshot = _search_counter_snapshot(counters, backend, len(context["search_frequencies"]))
            row = {
                "material": "MLIT", "topology": topology, "seed": int(seed),
                "absolute_unique_evaluations": point,
                "evaluations_per_dimension": point / space.dimension,
                "is_primary_endpoint": point == context["primary_budget"],
                "is_dimension_normalized_lattice_checkpoint": (
                    point in context["diagnostic_checkpoints"][topology]
                ),
                "diagnostic_lattice_factor": (
                    point / space.dimension
                    if point in context["diagnostic_checkpoints"][topology] else None
                ),
                "primary_budget": context["primary_budget"],
                "normalized_target": target,
                "hard_max_budget": int(backend.hard_max_budget),
                "population_schedule_terminal_budget": int(backend.population_schedule_terminal_budget),
                "checkpoint_reference": session.reference_metadata,
                "checkpoint_exists": bool(checkpoint_path.is_file()),
                "counters": snapshot,
            }
            with trajectory_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(_json_clean(row), ensure_ascii=False, allow_nan=False) + "\n")
            checkpoint_rows.append(row)
            checkpoint_registry.append(row)
            recorded_budgets.add(point)
            pin_name = f"B{point}"
            if (point == context["primary_budget"]
                    and not session.store.pinned_directory.joinpath(f"{pin_name}.json").is_file()):
                session.store.pin(pin_name, source="latest")
        else:
            row = next(item for item in existing_rows
                       if int(item["absolute_unique_evaluations"]) == point)
            checkpoint_rows = [item for item in checkpoint_rows
                               if int(item["absolute_unique_evaluations"]) != point]
            checkpoint_rows.append(row)
        if point == context["primary_budget"] and not primary_path.is_file():
            validation = _common_validation(
                context, topology, seed, point, backend, counters,
            )
            primary = _cell_result(
                context, topology, seed, point, backend, counters, validation,
                initializer, checkpoint_rows, time.perf_counter() - started,
                timing["com_network_evaluation_wall_time_s"],
            )
            write_json_artifact(primary_validation_path, validation)
            write_json_artifact(primary_path, primary)
        if point == target and not sensitivity_path.is_file():
            if target == context["primary_budget"] and primary_path.is_file():
                primary = json.loads(primary_path.read_text(encoding="utf-8"))
                validation = json.loads(primary_validation_path.read_text(encoding="utf-8"))
                sensitivity = dict(primary)
                sensitivity["stratum"] = "dimension_normalized_sensitivity_alias_of_primary"
                sensitivity["absolute_unique_evaluations"] = target
                sensitivity["evaluations_per_dimension"] = target / space.dimension
                validation = dict(validation)
                validation["stratum"] = "dimension_normalized_sensitivity_alias_of_primary"
            else:
                validation = _common_validation(
                    context, topology, seed, point, backend, counters,
                )
                sensitivity = _cell_result(
                    context, topology, seed, point, backend, counters, validation,
                    initializer, checkpoint_rows, time.perf_counter() - started,
                    timing["com_network_evaluation_wall_time_s"],
                )
                sensitivity["stratum"] = "dimension_normalized_sensitivity"
            write_json_artifact(final_validation_path, validation)
            write_json_artifact(sensitivity_path, sensitivity)
    if not primary_path.is_file() or not sensitivity_path.is_file():
        raise RuntimeError(f"{topology}/seed{seed} ended without both comparison strata")
    primary = json.loads(primary_path.read_text(encoding="utf-8"))
    sensitivity = json.loads(sensitivity_path.read_text(encoding="utf-8"))
    if int(backend.unique_evaluations) != target:
        raise AssertionError("cell final unique evaluation count differs from its endpoint")
    return primary, sensitivity


def run_hybrid_topology_screening(config_path: str | Path, run_path: str | Path,
                                  *, resume: bool = False) -> dict[str, Any]:
    """Execute one current hybrid comparison protocol, resumably and fail-closed."""
    context = _resolved_context(config_path)
    if (context["mode"] == "production"
            and not context["contract"]["production_launch_authorized"]):
        raise PermissionError(
            "production config is pre-launch only; set "
            "hybrid_comparison.production_launch_authorized=true after separate launch review"
        )
    run = Path(run_path)
    if not run.is_absolute():
        run = ROOT / run
    run.mkdir(parents=True, exist_ok=True)
    if not resume and any(run.iterdir()):
        raise FileExistsError(f"study output directory is not empty: {run}")
    top_results: list[dict[str, Any]] = []
    sensitivity_results: list[dict[str, Any]] = []
    initializer_registry: list[dict[str, Any]] = []
    checkpoint_registry: list[dict[str, Any]] = []
    start_all = time.perf_counter()
    try:
        validation = _ensure_implementation_gate(config_path, run)
        if validation.get("status") != "PASS":
            raise RuntimeError("implementation validation is not PASS")
        for topology in context["topologies"]:
            for seed in context["seeds"]:
                primary, sensitivity = _run_cell(
                    context, run, topology, seed, resume=resume,
                    initializer_registry=initializer_registry,
                    checkpoint_registry=checkpoint_registry,
                )
                top_results.append(primary)
                sensitivity_results.append(sensitivity)
        total_wall = time.perf_counter() - start_all
        checkpoint_registry = []
        for trajectory in sorted((run / "optimization").glob("*/seed*/trajectory.jsonl")):
            checkpoint_registry.extend(
                json.loads(line) for line in trajectory.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        checkpoint_registry.sort(key=lambda row: (
            str(row["topology"]), int(row["seed"]),
            int(row["absolute_unique_evaluations"]),
        ))
        _write_csv(run / "metadata" / "trajectory.csv", checkpoint_registry)
        fairness = {
            "status": "PASS", "primary_stratum": "equal_unique_evaluation_budget",
            "decision_policy": context["contract"]["decision_policy"],
            "primary_budget_per_topology_seed": context["primary_budget"],
            "primary_total_unique_evaluations": context["primary_budget"] * len(context["topologies"]) * len(context["seeds"]),
            "normalized_rule": context["contract"]["normalized_budget_formula"],
            "evaluations_per_dimension": context["evaluations_per_dimension"],
            "diagnostic_lattice_evaluations_per_dimension": list(
                context["diagnostic_factors"]
            ),
            "diagnostic_lattice_checkpoint_budgets": {
                name: list(context["diagnostic_checkpoints"][name])
                for name in context["topologies"]
            },
            "unconditional_structural_continuation": True,
            "continuation_uses_observed_results": False,
            "sensitivity_total_unique_evaluations": sum(
                int(row["absolute_unique_evaluations"]) for row in sensitivity_results
            ),
            "topologies": context["contract"]["dimensions"],
            "two_seed_interpretation": "screening only; not a definitive topology ranking",
        }
        checkpoint_accounting = {
            "status": "PASS", "budget_unit": "unique decoded canonical evaluations",
            "checkpoints": checkpoint_registry,
            "stage4b_launched": context["mode"] == "production",
        }
        write_json_artifact(run / "metadata" / "fairness_contract.json", fairness)
        write_json_artifact(run / "metadata" / "initializer_accounting.json", initializer_registry)
        write_json_artifact(run / "metadata" / "checkpoint_accounting.json", checkpoint_accounting)
        c2c_path = run / "metadata" / "c2c_review_status.json"
        if not c2c_path.is_file():
            write_json_artifact(c2c_path, {
                "task_id": None, "status": "EXECUTED_PENDING_REVIEW",
                "iterations": 0, "decision": None, "mandatory_findings": [],
            })
        result = {
            "status": "HYBRID_TOPOLOGY_SCREENING_COMPLETE",
            "scientific_conclusion": False,
            "interpretation": "two-seed screening only; not a definitive topology ranking",
            "stage4b_launched": context["mode"] == "production",
            "topologies": top_results,
            "normalized_sensitivity": sensitivity_results,
            "total_wall_time_s": float(total_wall),
            "fairness_contract": fairness,
            "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
            "fingerprint_schema_version": 2,
            "common_validation_grid_id": context["common_grid_id"],
            "run_disposition": RunDisposition.REVIEW_WAITING.value,
        }
        source_metadata_path = run / "metadata" / "run_source_metadata.json"
        source_metadata = json.loads(source_metadata_path.read_text(encoding="utf-8"))
        source_metadata["stage4b_launched"] = bool(result["stage4b_launched"])
        write_json_artifact(source_metadata_path, source_metadata)
        write_json_artifact(run / "topology_results.json", result)
        _write_csv(run / "topology_results.csv", [
            {"stratum": "primary", **row} for row in top_results
        ] + [
            {"stratum": "dimension_normalized_sensitivity", **row}
            for row in sensitivity_results
        ])
        _write_reports(run, result, context)
        complete_study_run(run, result, disposition=RunDisposition.REVIEW_WAITING)
        from ..reporting.hybrid_topology_report import build_hybrid_topology_review_bundle
        anticipated_bundle = ROOT / "artifacts" / "review_bundles" / f"{run.name}_review.zip"
        write_json_artifact(run / "metadata" / "review_bundle.json", {
            "path": str(anticipated_bundle),
        })
        bundle = build_hybrid_topology_review_bundle(run, context)
        write_json_artifact(run / "metadata" / "review_bundle.json", {"path": str(bundle)})
        result["review_bundle_path"] = str(bundle)
        write_json_artifact(run / "topology_results.json", result)
        _write_reports(run, result, context)
        bundle = build_hybrid_topology_review_bundle(run, context)
        result["review_bundle_path"] = str(bundle)
        return result
    except Exception as exc:
        write_json_artifact(run / "metadata" / "execution_failure.json", {
            "status": "FAILED", "error_type": type(exc).__name__, "error": str(exc),
        })
        complete_study_run(run, {"status": "FAILED", "error": str(exc)},
                           disposition=RunDisposition.FAILED)
        raise


__all__ = [
    "PRODUCTION_SEEDS", "PRODUCTION_TOPOLOGIES", "STAGE4B_REQUIRED_ARTIFACTS",
    "run_hybrid_topology_screening", "validate_hybrid_topology_screening",
]
