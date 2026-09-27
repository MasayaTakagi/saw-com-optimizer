"""Strict comparison of the Stage 3.9B overlap against canonical Stage 3.8C."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping, Sequence

import numpy as np

from ..core.metrics import search_grid
from ..io.config import load_experiment_config
from . import dms_topology_common as common
from . import dms_topology_screening as study


MATERIAL = "MLIT"
TOPOLOGY = "T1_SYMMETRIC_5IDT"
SEEDS = (20260917, 20260918)
CHECKPOINTS = (2000, 4000, 6000, 8000)
METRIC_RTOL = 1e-12
METRIC_ATOL = 1e-12
OBJECTIVE_RTOL = 1e-12
OBJECTIVE_ATOL = 1e-6
ROOT = Path(__file__).resolve().parents[3]
CANONICAL_RUN = ROOT / "runs" / "stage3_8c_production_20260924"
OVERLAP_CONFIG = ROOT / "configs" / "studies" / "stage3_9b_mlit_t1_50ohm_overlap_parity.yaml"
REVIEW_ROOT = ROOT / "artifacts" / "review_bundles" / "stage3_9b_overlap_parity_review"

CHECKPOINT_FIELDS = (
    "evaluation_status", "failure_stage", "geometry_valid", "geometry_dimensions",
    "geometry_violations", "geometry_max_violation", "metrics", "violations",
    "filter_metrics_available", "filter_feasible", "feasible", "max_violation",
    "sum_violation", "objective", "objective_parts", "design", "topology",
    "source_impedance_ohm", "load_impedance_ohm", "requested_unique_design_budget",
    "unique_decoded_evaluations", "actual_unique_design_evaluations",
    "actual_unique_budget", "budget_completion_fraction", "budget_completion_passed",
    "objective_calls", "raw_offspring_count", "duplicate_decoded_count",
    "duplicate_decoded_attempts", "duplicate_decoded_rate", "cache_hits",
    "cache_hit_rate", "population_size", "proposals_total", "duplicate_rate", "m_f",
    "m_cr", "archive_size", "archive_trace", "boundary_repair_counts",
    "population_schedule_terminal_budget", "terminal_budget", "current_budget",
    "initial_population", "current_population", "population_schedule_identifier",
    "population_schedule_version", "hard_max_budget", "search_space_exhausted",
    "stop_reason", "best_so_far_trace", "population_trace", "checkpoint_budget",
    "checkpoint_trajectory_index", "trajectory_semantics", "disk_resume_used",
    "frequency_grid_version", "frequency_grid_events", "design_space_version",
    "grid_converged", "recovery_pending_confirmation", "boundary_pending_confirmation",
    "hard_bound_unresolved", "micro_polish_improvement",
    "fraction_of_budget_at_last_significant_improvement", "convergence_evidence_complete",
    "convergence_evidence_missing_fields", "material", "seed", "active_bounds",
    "optimizer_hard_bounds", "search_bounds_are_not_manufacturing_limits",
    "cold_start", "warm_start", "parent_transfer", "neighbor_warm_start",
)
COUNTER_FIELDS = (
    "objective_calls", "canonical_candidates_seen", "unique_decoded_evaluations",
    "geometry_rejections", "geometry_valid_candidates", "valid_physics_evaluations",
    "physics_attempted_evaluations", "physics_failures", "cache_hits",
    "solved_frequency_points", "search_frequency_points", "validation_evaluations",
    "validation_physics_failures", "validation_frequency_points", "search_frequency_count",
)
INITIALIZER_SEMANTIC_FIELDS = {
    "initializer_method": ("initializer_method",),
    "initial_sampling_seed": ("initial_sampling_seed",),
    "requested_population_size": ("requested_population_size",),
    "max_attempts": ("max_attempts",),
    "max_attempts_exceeded": ("max_attempts_exceeded",),
    "total_candidate_draws": ("total_candidate_draws",),
    "valid_accepted_candidates": ("valid_accepted_candidates",),
    "geometry_valid_members": ("geometry_valid_members",),
    "rejected_candidates": ("rejected_candidates",),
    "initial_sampling_draws": ("initial_sampling_draws",),
    "initial_sampling_geometry_rejections": ("initial_sampling_geometry_rejections",),
    "initial_sampling_duplicate_rejections": ("initial_sampling_duplicate_rejections",),
    "initial_sampling_rejection_reason_counts": ("initial_sampling_rejection_reason_counts",),
    "fixed_seed_count": ("fixed_seed_count", "fixed_member_count"),
    "random_initial_accepts": ("random_initial_accepts", "random_member_count"),
    "unique_population_count": ("unique_population_count",),
    "variable_distributions": ("variable_distributions",),
    "geometry_metric_distributions": ("geometry_metric_distributions",),
    "random_member_variable_distributions": ("random_member_variable_distributions",),
    "random_member_geometry_metric_distributions": ("random_member_geometry_metric_distributions",),
}
PROVENANCE_IGNORED_FIELDS = (
    "source_config_fingerprint", "absolute paths", "timestamps and run IDs", "Git metadata",
    "study type/revision labels", "wall/CPU/generation timings", "checkpoint path",
    "historical-vs-current frequency-grid event wording", "historical raw initial vectors (not retained)",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_lf_normalized_file(path: Path) -> str:
    """Hash text bytes after normalizing Windows CRLF to the tracked LF form."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _validate_grid_provenance_hashes(
    source_path: Path, run_copy_path: Path, *, source_metadata_hash: str,
    run_metadata_hash: str | None,
) -> list[str]:
    """Validate source/copy hashes using the LF normalization recorded by grid metadata."""
    differences: list[str] = []
    source_hash = _sha256_lf_normalized_file(source_path)
    copy_hash = _sha256_lf_normalized_file(run_copy_path)
    if source_hash != source_metadata_hash:
        differences.append("configured common-grid source hash does not match its normalized metadata hash")
    if run_metadata_hash != source_hash:
        differences.append("run metadata common-grid hash does not match normalized source bytes")
    if copy_hash != source_hash:
        differences.append("run common-grid copy does not match normalized source bytes")
    return differences


def _float_policy(path: str) -> tuple[float, float] | None:
    lowered = path.lower()
    if lowered.endswith(".objective") and ".objective_parts" not in lowered:
        return OBJECTIVE_RTOL, OBJECTIVE_ATOL
    if any(token in lowered for token in (
        ".metrics", ".violations", ".max_violation", ".sum_violation",
        ".geometry_dimensions", ".geometry_violations", ".geometry_max_violation",
        ".objective_parts.primary", ".objective_parts.secondary", ".rank_key",
    )):
        return METRIC_RTOL, METRIC_ATOL
    return None


def compare_values(left: Any, right: Any, path: str = "$", *, limit: int = 20) -> list[str]:
    """Compare deterministic state exactly, allowing only predeclared RF tolerances."""
    mismatches: list[str] = []

    def visit(a: Any, b: Any, current: str) -> None:
        if len(mismatches) >= limit:
            return
        if isinstance(a, bool) or isinstance(b, bool):
            if type(a) is not type(b) or a != b:
                mismatches.append(f"{current}: {a!r} != {b!r}")
            return
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if isinstance(a, int) and isinstance(b, int):
                if a != b:
                    mismatches.append(f"{current}: {a!r} != {b!r}")
                return
            af, bf = float(a), float(b)
            if not math.isfinite(af) or not math.isfinite(bf):
                if af != bf:
                    mismatches.append(f"{current}: non-finite values differ ({af!r}, {bf!r})")
                return
            policy = _float_policy(current)
            if policy is None:
                if af != bf:
                    mismatches.append(f"{current}: exact control float differs ({af!r}, {bf!r})")
            elif not math.isclose(af, bf, rel_tol=policy[0], abs_tol=policy[1]):
                mismatches.append(f"{current}: outside tolerance ({af!r}, {bf!r}; rtol={policy[0]}, atol={policy[1]})")
            return
        if type(a) is not type(b):
            mismatches.append(f"{current}: types differ ({type(a).__name__}, {type(b).__name__})")
            return
        if isinstance(a, Mapping):
            akeys, bkeys = set(a), set(b)
            if akeys != bkeys:
                mismatches.append(f"{current}: keys differ (left-only={sorted(akeys-bkeys)}, right-only={sorted(bkeys-akeys)})")
                if len(mismatches) >= limit:
                    return
            for key in sorted(akeys & bkeys, key=str):
                visit(a[key], b[key], f"{current}.{key}")
            return
        if isinstance(a, (list, tuple)):
            if len(a) != len(b):
                mismatches.append(f"{current}: lengths differ ({len(a)}, {len(b)})")
            for index, (av, bv) in enumerate(zip(a, b)):
                visit(av, bv, f"{current}[{index}]")
            return
        if a != b:
            mismatches.append(f"{current}: {a!r} != {b!r}")

    visit(left, right, path)
    return mismatches


def _initializer_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    missing: list[str] = []
    for semantic, aliases in INITIALIZER_SEMANTIC_FIELDS.items():
        present = [alias for alias in aliases if alias in value]
        if not present:
            missing.append(semantic)
            continue
        selected = value[present[0]]
        if any(value[alias] != selected for alias in present[1:]):
            raise ValueError(f"initializer aliases disagree for {semantic}: {present}")
        projected[semantic] = selected
    if missing:
        raise ValueError(f"initializer semantic evidence missing fields: {missing}")
    return projected


def _normalized_counters(record: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize historical r1_counters and current evaluation_counters."""
    available = []
    for name in ("r1_counters", "evaluation_counters"):
        raw = record.get(name)
        if isinstance(raw, Mapping) and any(key in raw for key in COUNTER_FIELDS):
            available.append((name, raw))
    if not available:
        raise ValueError("checkpoint has neither populated r1_counters nor evaluation_counters")
    projections = []
    for name, raw in available:
        missing = set(COUNTER_FIELDS) - set(raw)
        if missing:
            raise ValueError(f"{name} missing required counter fields: {sorted(missing)}")
        projections.append((name, {key: raw[key] for key in COUNTER_FIELDS}))
    first_name, first = projections[0]
    for name, other in projections[1:]:
        differences = compare_values(first, other, "normalized_counters")
        if differences:
            raise ValueError(f"populated counter containers disagree ({first_name} vs {name}): {differences[:3]}")
    return first


def _normalize_frequency_events(value: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{key: item for key, item in event.items() if key != "event"} for event in value]


def _record_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    missing = set(CHECKPOINT_FIELDS) - set(record)
    if missing:
        raise ValueError(f"checkpoint record missing required fields: {sorted(missing)}")
    projection = {key: record[key] for key in CHECKPOINT_FIELDS}
    projection["frequency_grid_events"] = _normalize_frequency_events(record["frequency_grid_events"])
    projection["objective_parts"] = dict(record["objective_parts"])
    projection["evaluation_counters"] = _normalized_counters(record)
    projection["initial_population_sampling"] = _initializer_projection(
        record["initial_population_sampling"]
    )
    return projection


def _evaluation_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "evaluation_status", "failure_stage", "geometry_valid", "geometry_dimensions",
        "geometry_violations", "geometry_max_violation", "metrics", "violations",
        "filter_metrics_available", "filter_feasible", "feasible", "max_violation",
        "sum_violation", "objective", "objective_parts", "design", "topology",
        "source_impedance_ohm", "load_impedance_ohm",
    )
    if "evaluation_status" not in value:
        raise ValueError("cached evaluation has no evaluation_status")
    return {field: value[field] for field in fields if field in value}


def _optimizer_projection(state: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(state)
    result.pop("source_config_fingerprint", None)
    cache = result.pop("cache")
    result["cache_sequence"] = [
        {"key": row[0], "result": _evaluation_projection(row[1])}
        for row in cache
    ]
    result.pop("cache_frequency_versions", None)
    result["cache_frequency_versions"] = state["cache_frequency_versions"]
    result["population"] = [
        {
            **{key: value for key, value in member.items() if key != "result"},
            "result": _evaluation_projection(member["result"]),
        }
        for member in state["population"]
    ]
    if state.get("incumbent") is not None:
        result["incumbent"] = _evaluation_projection(state["incumbent"])
    return result


def _counter_failures(record: Mapping[str, Any]) -> list[str]:
    try:
        counters = _normalized_counters(record)
    except (TypeError, ValueError) as exc:
        return [f"counter normalization failed: {exc}"]
    failures: list[str] = []
    unique = int(counters["unique_decoded_evaluations"])
    geometry_rejections = int(counters["geometry_rejections"])
    geometry_valid = int(counters["geometry_valid_candidates"])
    physics_ok = int(counters["valid_physics_evaluations"])
    physics_fail = int(counters["physics_failures"])
    attempted = int(counters["physics_attempted_evaluations"])
    if unique != geometry_rejections + geometry_valid:
        failures.append("unique = geometry_rejections + geometry_valid_candidates identity failed")
    if geometry_valid != physics_ok + physics_fail:
        failures.append("geometry_valid_candidates = valid_physics_evaluations + physics_failures identity failed")
    if attempted != physics_ok + physics_fail:
        failures.append("physics_attempted_evaluations = valid_physics_evaluations + physics_failures identity failed")
    if physics_fail != 0:
        failures.append(f"physics_failures={physics_fail}, expected 0")
    if int(counters["search_frequency_count"]) != 1001:
        failures.append(f"search_frequency_count={counters['search_frequency_count']}, expected 1001")
    return failures


def validate_checkpoint_lattice(cells: Mapping[tuple[int, int], Any]) -> list[str]:
    expected = {(seed, budget) for seed in SEEDS for budget in CHECKPOINTS}
    actual = set(cells)
    if actual == expected:
        return []
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    return [f"checkpoint lattice mismatch: missing={missing}, extra={extra}"]


def _metadata_protocol(path: Path) -> dict[str, Any]:
    """Read and normalize the retained Stage 3.8C protocol snapshot."""
    run = _read_json(path / "metadata" / "run_source_metadata.json")
    snapshots = _read_json(path / "metadata" / "resolved_search_space_snapshots.json")
    profiles = _read_json(path / "metadata" / "material_profile_snapshots.json")
    grid = _read_frequency_grid(path / "metadata" / "common_validation_grid.csv")
    profile = dict(profiles[MATERIAL])
    if isinstance(profile.get("profile"), Mapping):
        profile["profile"] = dict(profile["profile"])
        source = profile["profile"].get("com_parameter_source")
        if isinstance(source, str):
            profile["profile"]["com_parameter_source"] = PureWindowsPath(source).name
    return {
        "run": _normalized_run_metadata(
            run,
            common_grid_count=len(grid),
            common_grid_array_sha256=_array_sha256(grid),
        ),
        "search_space": _search_space_projection(snapshots[MATERIAL][TOPOLOGY]),
        "profile": _profile_projection(profile),
    }


def _read_frequency_grid(path: Path) -> np.ndarray:
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError(f"frequency grid CSV has no header: {path}")
        field = "frequency_hz" if "frequency_hz" in reader.fieldnames else reader.fieldnames[0]
        values = [float(row[field]) for row in reader]
    grid = np.asarray(values, dtype=np.float64)
    if grid.ndim != 1 or not len(grid) or not np.isfinite(grid).all():
        raise ValueError(f"frequency grid CSV is empty or invalid: {path}")
    return grid


def _array_sha256(values: Sequence[float]) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()


def _normalized_run_metadata(
    run: Mapping[str, Any], *, common_grid_count: int, common_grid_array_sha256: str,
) -> dict[str, Any]:
    """Map Stage 3.8C and current DMS run-source names to shared meanings."""
    pair = run.get("input_output_impedance_ohm")
    if pair is not None:
        if not isinstance(pair, Sequence) or len(pair) != 2:
            raise ValueError("input_output_impedance_ohm must be a source/load pair")
        source_impedance, load_impedance = pair
    else:
        source_impedance = run.get("source_impedance_ohm")
        load_impedance = run.get("load_impedance_ohm")
    search_count = run.get("resolved_search_frequency_count", run.get("search_frequency_count"))
    search_sha = run.get("resolved_search_frequency_sha256", run.get("search_frequency_sha256"))
    required = {
        "budget": run.get("budget"),
        "common_grid_count": run.get("common_validation_grid_count"),
        "common_grid_id": run.get("common_validation_grid_id"),
        "initializer_method": run.get("initializer_method", run.get("initialization_policy")),
        "source_impedance_ohm": source_impedance,
        "load_impedance_ohm": load_impedance,
        "search_frequency_count": search_count,
        "search_frequency_sha256": search_sha,
        "seeds": run.get("seeds"),
    }
    missing = [key for key, value in required.items() if value is None]
    if missing:
        raise ValueError(f"run_source_metadata missing normalized fields: {missing}")
    if int(required["common_grid_count"]) != int(common_grid_count):
        raise ValueError(
            f"run metadata common-grid count {required['common_grid_count']} != artifact count {common_grid_count}"
        )
    if required["common_grid_id"] != common_grid_array_sha256:
        raise ValueError("run metadata common-grid ID does not match normalized array content")
    return {
        **required,
        # The historical field hashed the normalized frequency array; the new
        # runner stores the CSV byte hash. Always derive array identity from the
        # actual artifact, and validate the current byte hash separately.
        "common_grid_count": int(common_grid_count),
        "common_grid_array_sha256": common_grid_array_sha256,
        "initialization_policy": run.get("initialization_policy", run.get("initializer_method")),
        "manufacturing_geometry_limits": run.get("manufacturing_geometry_limits"),
        "material_aperture_bounds_um": run.get("material_aperture_bounds_um", {}).get(MATERIAL),
    }


def _search_space_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "active_search_bounds", "optimizer_hard_bounds", "integer_indices",
        "manufacturing_hard_limits",
    )
    missing = set(fields) - set(value)
    if missing:
        raise ValueError(f"search-space snapshot missing fields: {sorted(missing)}")
    return {field: value[field] for field in fields}


def _profile_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    raw_profile = value.get("profile")
    if not isinstance(raw_profile, Mapping):
        raise ValueError("material profile snapshot is missing profile mapping")
    profile_fields = (
        "id", "source", "substrate", "electrode_material", "temperature_c",
        "effective_h_over_lambda", "effective_duty", "phase_policy",
    )
    missing = set(profile_fields) - set(raw_profile)
    if missing:
        raise ValueError(f"material profile snapshot missing fields: {sorted(missing)}")
    source = raw_profile.get("com_parameter_source")
    return {
        "profile_id": value.get("profile_id"),
        "aperture_bounds_um": value.get("aperture_bounds_um"),
        "profile": {
            **{field: raw_profile[field] for field in profile_fields},
            "com_parameter_source_basename": PureWindowsPath(str(source or "")).name,
        },
    }


def _config_metadata_protocol(protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Project current resolved config values into the historical semantic shape."""
    return {
        "run": {
            "budget": protocol["budget"],
            "common_grid_count": protocol["common_grid_count"],
            "common_grid_id": protocol["common_grid_id"],
            "common_grid_array_sha256": protocol["common_grid_array_sha256"],
            "initializer_method": protocol["initializer_method"],
            "source_impedance_ohm": protocol["impedance_ohm"],
            "load_impedance_ohm": protocol["impedance_ohm"],
            "search_frequency_count": protocol["search_grid_count"],
            "search_frequency_sha256": protocol["search_grid_sha256"],
            "seeds": list(protocol["seeds"]),
            "initialization_policy": protocol["initializer_method"],
            "manufacturing_geometry_limits": protocol["manufacturing_constraints"],
            "material_aperture_bounds_um": protocol["aperture_bounds_um"],
        },
        "search_space": {
            "active_search_bounds": protocol["active_bounds"],
            "optimizer_hard_bounds": protocol["hard_bounds"],
            "integer_indices": protocol["integer_indices"],
            "manufacturing_hard_limits": protocol["manufacturing_geometry_limits"],
        },
        "profile": {
            "profile_id": protocol["profile_id"],
            "aperture_bounds_um": protocol["aperture_bounds_um"],
            "profile": {
                **{key: protocol["profile_parameters"][key] for key in (
                    "id", "source", "substrate", "electrode_material", "temperature_c",
                    "effective_h_over_lambda", "effective_duty", "phase_policy",
                )},
                "com_parameter_source_basename": protocol["profile_source_basename"],
            },
        },
    }


def _validate_current_run_metadata(run_dir: Path, protocol: Mapping[str, Any]) -> list[str]:
    """Validate fields the current runner persists, allowing its own schema names."""
    run = _read_json(run_dir / "metadata" / "run_source_metadata.json")
    grid_path = run_dir / "metadata" / "common_validation_grid.csv"
    grid = _read_frequency_grid(grid_path)
    expected = {
        "budget": protocol["budget"],
        "common_validation_grid_count": protocol["common_grid_count"],
        "common_validation_grid_id": protocol["common_grid_id"],
        "initializer_method": protocol["initializer_method"],
        "initial_population_seed_contract": protocol["initial_population_seed_contract"],
        "initial_sampling_seeds": protocol["initial_sampling_seeds"],
        "source_impedance_ohm": protocol["impedance_ohm"],
        "load_impedance_ohm": protocol["impedance_ohm"],
        "search_frequency_count": protocol["search_grid_count"],
        "search_frequency_sha256": protocol["search_grid_sha256"],
        "seeds": list(protocol["seeds"]),
        "selected_materials": [MATERIAL],
        "selected_topologies": [TOPOLOGY],
        "cold_start": True,
        "warm_start": False,
        "parent_transfer": False,
        "neighbor_warm_start": False,
    }
    differences: list[str] = []
    for key, value in expected.items():
        differences.extend(compare_values(run.get(key), value, f"overlap_run_source_metadata.{key}"))
    differences.extend(compare_values(len(grid), protocol["common_grid_count"], "overlap_common_grid.count"))
    differences.extend(compare_values(
        _array_sha256(grid), protocol["common_grid_array_sha256"], "overlap_common_grid.array_sha256",
    ))
    source_grid_path = ROOT / protocol["common_grid_source"]
    differences.extend(
        f"overlap_common_grid.provenance: {item}"
        for item in _validate_grid_provenance_hashes(
            source_grid_path,
            grid_path,
            source_metadata_hash=protocol["common_grid_sha256"],
            run_metadata_hash=run.get("common_validation_grid_sha256"),
        )
    )
    return differences


def _config_protocol(cfg: Mapping[str, Any]) -> dict[str, Any]:
    settings = cfg["dms_topology"]
    selected_materials, selected_topologies = study._selected_study_axes(cfg)
    if selected_materials != (MATERIAL,) or selected_topologies != (TOPOLOGY,):
        raise ValueError("overlap configuration must select only MLIT/T1")
    active, hard, integer_indices = study.material_bounds(cfg, MATERIAL, TOPOLOGY)
    hard_limits = cfg["constraints"]
    common_grid, common_grid_id, _metadata_path, grid_metadata = study._load_common_grid(cfg)
    seed_contract = study.resolve_initial_population_seed_contract(cfg)
    expected_seed_contract = study.STAGE3_8C_R1_2_INITIAL_POPULATION_SEED_CONTRACT
    extension_config = load_experiment_config(
        ROOT / "configs/studies/stage3_9b_mlit_t1_50ohm_budget_extension.yaml"
    )
    extension_seed_contract = study.resolve_initial_population_seed_contract(extension_config)
    if seed_contract.identifier != expected_seed_contract:
        raise ValueError("overlap config must explicitly select the Stage 3.8C R1.2 seed contract")
    if extension_seed_contract != seed_contract:
        raise ValueError("overlap and budget-extension configs must share one initializer seed contract")
    frequencies = np.unique(search_grid(cfg["spec"], cfg))
    provider, profile_meta = study.provider_for_material(MATERIAL, cfg)
    design = common.initial_design(MATERIAL, TOPOLOGY, cfg)
    design_vector = study._design_vector(design, TOPOLOGY)
    initializer_keys = (
        "initial_population", "initial_population_per_dimension", "max_initial_population_attempts",
        "initial_population_attempt_multiplier", "initializer_reference_proposals",
        "distribution_bootstrap_replicates", "initial_designs", "t1_reflector_electrodes",
    )
    initializer = {key: settings[key] for key in initializer_keys if key in settings}
    initial_design_path = ROOT / str(settings["initial_designs"][MATERIAL])
    return {
        "material": MATERIAL,
        "topology": TOPOLOGY,
        "impedance_ohm": float(settings["impedance_ohm"]),
        "active_bounds": active.tolist(),
        "hard_bounds": hard.tolist(),
        "integer_indices": list(integer_indices),
        "manufacturing_geometry_limits": hard_limits,
        "profile_id": profile_meta["id"],
        "profile_parameters": {
            key: value for key, value in profile_meta.items()
            if key not in {"com_parameter_source", "normalization_definition_source", "display_note"}
        },
        "profile_source_basename": PureWindowsPath(str(profile_meta.get("com_parameter_source", ""))).name,
        "aperture_bounds_um": settings["materials"][MATERIAL]["aperture_bounds_um"],
        "initializer_method": "independent_uniform_rejection_v1",
        "initial_population_seed_contract": {
            "identifier": seed_contract.identifier,
            "namespace": seed_contract.namespace,
            "derivation_suffix": seed_contract.derivation_suffix,
        },
        "initial_sampling_seeds": {
            f"{MATERIAL}/{TOPOLOGY}/{seed}": study.initial_population_sampling_seed(
                cfg, seed, MATERIAL, TOPOLOGY,
            )
            for seed in SEEDS
        },
        "population_size": study._population_size(cfg, TOPOLOGY, 8000, hard),
        "backend_config": study._backend_config(cfg, TOPOLOGY, 8000, hard),
        "initializer": initializer,
        "initial_design_vector": design_vector.tolist(),
        "initial_design_vector_sha256": hashlib.sha256(
            np.asarray(design_vector, dtype="<f8").tobytes()
        ).hexdigest(),
        "initial_design_source": PureWindowsPath(str(settings["initial_designs"][MATERIAL])).as_posix(),
        "initial_design_source_sha256": _sha256_file(initial_design_path),
        "specification": cfg["spec"],
        "manufacturing_constraints": cfg["constraints"],
        "common_grid_id": common_grid_id,
        "common_grid_sha256": grid_metadata["sha256"],
        "common_grid_source": grid_metadata["source"],
        "common_grid_array_sha256": hashlib.sha256(np.asarray(common_grid, dtype="<f8").tobytes()).hexdigest(),
        "common_grid_count": int(len(common_grid)),
        "search_grid_sha256": hashlib.sha256(np.asarray(frequencies, dtype="<f8").tobytes()).hexdigest(),
        "search_grid_count": int(len(frequencies)),
        "seeds": tuple(int(seed) for seed in settings["seeds"]),
        "budget": int(settings["budget"]),
        "checkpoints": tuple(int(point) for point in settings["checkpoints"]),
        "cold_start": settings.get("cold_start", False),
    }


def _compare_persisted_protocol(run_dir: Path, protocol: Mapping[str, Any]) -> list[str]:
    """Check current inputs against the canonical run's retained protocol snapshots."""
    run = _read_json(run_dir / "metadata" / "run_source_metadata.json")
    snapshots = _read_json(run_dir / "metadata" / "resolved_search_space_snapshots.json")
    profiles = _read_json(run_dir / "metadata" / "material_profile_snapshots.json")
    mismatches: list[str] = []
    persisted_fields = {
        "budget": protocol["budget"],
        "common_validation_grid_count": protocol["common_grid_count"],
        "common_validation_grid_id": protocol["common_grid_id"],
        "common_validation_grid_sha256": protocol["common_grid_array_sha256"],
        "initializer_method": protocol["initializer_method"],
        "input_output_impedance_ohm": [protocol["impedance_ohm"], protocol["impedance_ohm"]],
        "manufacturing_geometry_limits": protocol["manufacturing_constraints"],
        "resolved_search_frequency_count": protocol["search_grid_count"],
        "resolved_search_frequency_sha256": protocol["search_grid_sha256"],
        "seeds": list(protocol["seeds"]),
    }
    for key, expected in persisted_fields.items():
        mismatches.extend(compare_values(run.get(key), expected, f"canonical_snapshot.run.{key}"))
    aperture = run.get("material_aperture_bounds_um", {}).get(MATERIAL)
    mismatches.extend(compare_values(aperture, protocol["aperture_bounds_um"], "canonical_snapshot.aperture_bounds_um"))
    mismatches.extend(compare_values(
        snapshots[MATERIAL][TOPOLOGY],
        {
            "active_search_bounds": protocol["active_bounds"],
            "optimizer_hard_bounds": protocol["hard_bounds"],
            "integer_indices": protocol["integer_indices"],
            "manufacturing_hard_limits": protocol["manufacturing_geometry_limits"],
        },
        "canonical_snapshot.search_space",
    ))
    profile = profiles[MATERIAL]
    if profile.get("profile_id") != protocol["profile_id"]:
        mismatches.append("canonical_snapshot.profile_id differs from current profile")
    old_profile = profile.get("profile", {})
    current_profile = protocol["profile_parameters"]
    for key in ("id", "source", "substrate", "electrode_material", "temperature_c",
                "effective_h_over_lambda", "effective_duty", "phase_policy"):
        mismatches.extend(compare_values(old_profile.get(key), current_profile.get(key), f"canonical_snapshot.profile.{key}"))
    old_profile_source = old_profile.get("com_parameter_source")
    if isinstance(old_profile_source, str) and PureWindowsPath(old_profile_source).name != protocol["profile_source_basename"]:
        mismatches.append("canonical_snapshot profile source file basename differs")
    return mismatches


def _canonical_protocol_evidence(
    run_dir: Path, protocol: Mapping[str, Any],
) -> dict[str, Any]:
    """Use persisted canonical snapshots regardless of legacy config availability."""
    root = _read_json(run_dir / "metadata" / "run_source_metadata.json")
    source_config_path = Path(str(root.get("source_config_path", "")))
    config_status = "present_optional_corroboration" if source_config_path.is_file() else "absent"
    return {
        "differences": _compare_persisted_protocol(run_dir, protocol),
        "source_config_path": str(source_config_path),
        "source_config_status": config_status,
        "evidence": "retained canonical run metadata/search-space/profile snapshots are authoritative; legacy config is not parsed by the current schema",
    }


def _final_selection_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "evaluation_status", "failure_stage", "geometry_valid", "geometry_dimensions",
        "geometry_violations", "geometry_max_violation", "metrics", "violations",
        "filter_metrics_available", "filter_feasible", "feasible", "max_violation",
        "sum_violation", "objective", "objective_parts", "design", "topology",
        "source_impedance_ohm", "load_impedance_ohm", "search_source_rank_key",
    )
    missing = set(fields) - set(payload)
    if missing:
        raise ValueError(f"common-grid record missing fields: {sorted(missing)}")
    return {field: payload[field] for field in fields}


def _compare_common_grid(
    old_dir: Path, new_dir: Path, *, expected_grid_id: str | None = None,
) -> list[str]:
    def read_payload(seed_dir: Path) -> Mapping[str, Any]:
        candidates = (
            seed_dir / "final_common_grid_selection.json",
            seed_dir / "common_grid_selection.json",
        )
        present = [path for path in candidates if path.is_file()]
        if len(present) != 1:
            raise ValueError(
                f"expected exactly one recognized common-grid artifact under {seed_dir}; found {present}"
            )
        return _read_json(present[0])

    old = read_payload(old_dir)
    new = read_payload(new_dir)
    mismatches: list[str] = []
    for field in ("common_validation_grid_id",):
        mismatches.extend(compare_values(old.get(field), new.get(field), f"common_grid.{field}"))
    if expected_grid_id is not None:
        mismatches.extend(compare_values(old.get("common_validation_grid_id"), expected_grid_id,
                                         "canonical_common_grid.expected_id"))
        mismatches.extend(compare_values(new.get("common_validation_grid_id"), expected_grid_id,
                                         "overlap_common_grid.expected_id"))
    mismatches.extend(compare_values(
        _final_selection_projection(old["selected"]),
        _final_selection_projection(new["selected"]), "common_grid.selected",
    ))
    old_finalists = [_final_selection_projection(row) for row in old.get("validated_finalists", [])]
    new_finalists = [_final_selection_projection(row) for row in new.get("validated_finalists", [])]
    mismatches.extend(compare_values(old_finalists, new_finalists, "common_grid.validated_finalists"))
    return mismatches


def _compare_cache(old_state: Mapping[str, Any], new_state: Mapping[str, Any]) -> list[str]:
    old_cache = old_state.get("cache")
    new_cache = new_state.get("cache")
    if not isinstance(old_cache, list) or not isinstance(new_cache, list):
        return ["optimizer checkpoint cache is missing or malformed"]
    mismatches: list[str] = []
    if len(old_cache) != len(new_cache):
        mismatches.append(f"cache lengths differ ({len(old_cache)}, {len(new_cache)})")
    for index, (old_row, new_row) in enumerate(zip(old_cache, new_cache)):
        if len(old_row) != 2 or len(new_row) != 2:
            mismatches.append(f"cache[{index}] malformed row")
            continue
        if old_row[0] != new_row[0]:
            mismatches.append(f"cache[{index}].key differs")
            continue
        try:
            old_value = _evaluation_projection(old_row[1])
            new_value = _evaluation_projection(new_row[1])
        except (TypeError, ValueError) as exc:
            mismatches.append(f"cache[{index}]: {exc}")
            continue
        differences = compare_values(old_value, new_value, f"cache[{index}].result", limit=3)
        mismatches.extend(differences)
        if len(mismatches) >= 20:
            break
    return mismatches


def _compare_optimizer_state(old_path: Path, new_path: Path, initial_vector: Sequence[float]) -> list[str]:
    old = _read_json(old_path)
    new = _read_json(new_path)
    mismatches: list[str] = []
    for label, state in (("canonical", old), ("overlap", new)):
        if int(state.get("unique_evaluations", -1)) != 8000:
            mismatches.append(f"{label} optimizer checkpoint unique_evaluations is not 8000")
        if int(state.get("population_schedule_terminal_budget", -1)) != 8000:
            mismatches.append(f"{label} optimizer checkpoint horizon is not 8000")
        if int(state.get("hard_max_budget", -1)) != 8000:
            mismatches.append(f"{label} optimizer checkpoint hard_max_budget is not 8000")
        keys = {tuple(float(item) for item in row[0]) for row in state.get("cache", []) if len(row) == 2}
        if tuple(float(item) for item in initial_vector) not in keys:
            mismatches.append(f"{label} optimizer cache does not contain the fixed initial-design vector")
    if mismatches:
        return mismatches
    try:
        mismatches.extend(_compare_cache(old, new))
        old_projected, new_projected = _optimizer_projection(old), _optimizer_projection(new)
        mismatches.extend(compare_values(old_projected, new_projected, "optimizer_state", limit=100))
    except (KeyError, TypeError, ValueError) as exc:
        mismatches.append(f"optimizer state projection failed: {exc}")
    return mismatches


def _validate_checkpoint_accounting(record: Mapping[str, Any], seed: int, budget: int) -> list[str]:
    failures = _counter_failures(record)
    expected = int(budget)
    for field in ("checkpoint_budget", "requested_unique_design_budget", "unique_decoded_evaluations", "actual_unique_budget"):
        if int(record.get(field, -1)) != expected:
            failures.append(f"{field}={record.get(field)!r}, expected {expected}")
    if int(record.get("seed", -1)) != int(seed):
        failures.append(f"seed={record.get('seed')!r}, expected {seed}")
    if record.get("evaluation_status") != "PHYSICS_EVALUATED":
        failures.append(f"evaluation_status={record.get('evaluation_status')!r}")
    if record.get("cold_start") is not True or record.get("warm_start") is not False:
        failures.append("checkpoint cold-start/warm-start flags are invalid")
    if any(record.get(field) is not False for field in ("parent_transfer", "neighbor_warm_start")):
        failures.append("checkpoint population-transfer flags are invalid")
    return failures


def _compare_checkpoint(old: Mapping[str, Any], new: Mapping[str, Any], seed: int, budget: int) -> list[str]:
    failures = _validate_checkpoint_accounting(old, seed, budget)
    failures.extend(_validate_checkpoint_accounting(new, seed, budget))
    try:
        failures.extend(compare_values(_record_projection(old), _record_projection(new), f"seed{seed}.B{budget}", limit=80))
    except (KeyError, TypeError, ValueError) as exc:
        failures.append(f"record projection failed: {exc}")
    return failures


def _read_cells(run_dir: Path) -> dict[tuple[int, int], tuple[Path, dict[str, Any]]]:
    cells: dict[tuple[int, int], tuple[Path, dict[str, Any]]] = {}
    topology_dir = run_dir / "optimization" / MATERIAL / TOPOLOGY
    for seed_dir in topology_dir.glob("seed*"):
        seed_match = re.fullmatch(r"seed(\d+)", seed_dir.name)
        seed = int(seed_match.group(1)) if seed_match else -1
        for path in seed_dir.glob("B*.json"):
            budget_match = re.fullmatch(r"B(\d+)\.json", path.name)
            budget = int(budget_match.group(1)) if budget_match else -1
            cells[(seed, budget)] = (path, _read_json(path))
    return cells


def _write_outputs(output_dir: Path, summary: Mapping[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "parity_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (output_dir / "checkpoint_comparisons.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ("seed", "checkpoint_budget", "status", "mismatch_count", "mismatches")
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in summary["checkpoint_comparisons"]:
            writer.writerow({**row, "mismatches": " | ".join(row["mismatches"])})
    lines = [
        "# Stage 3.9B overlap parity review", "",
        f"Status: **{summary['status']}**", "",
        f"Compared {summary['checkpoint_comparison_count']} checkpoint cells (two seeds × four checkpoints).", "",
        "## Gates", "",
    ]
    for gate, value in summary["gates"].items():
        lines.append(f"- `{gate}`: **{'PASS' if value else 'FAIL'}**")
    lines.extend(["", "## Checkpoint matrix", "", "| Seed | Budget | Status | Mismatches |", "|---:|---:|---|---:|"])
    for row in summary["checkpoint_comparisons"]:
        lines.append(f"| {row['seed']} | {row['checkpoint_budget']} | {row['status']} | {row['mismatch_count']} |")
    lines.extend(["", "## Tolerances", "", f"- RF metrics, normalized violations, geometry outputs and objective components: rtol={METRIC_RTOL:g}, atol={METRIC_ATOL:g}.", f"- Composite objective: rtol={OBJECTIVE_RTOL:g}, atol={OBJECTIVE_ATOL:g}.", "- Designs, ranking transitions, optimizer control state, counters, population/cache keys and population schedule: exact.", "", "## Provenance exclusions", ""])
    lines.extend(f"- {item}." for item in PROVENANCE_IGNORED_FIELDS)
    lines.extend(["", "## Mismatches", ""])
    if summary["mismatches"]:
        lines.extend(f"- {item}" for item in summary["mismatches"])
    else:
        lines.append("- None.")
    lines.append("")
    (output_dir / "parity_summary.md").write_text("\n".join(lines), encoding="utf-8")


def verify_overlap(
    canonical_run_dir: Path,
    overlap_run_dir: Path,
    overlap_config_path: Path = OVERLAP_CONFIG,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    canonical_run_dir = canonical_run_dir.resolve()
    overlap_run_dir = overlap_run_dir.resolve()
    same_run_self_check = canonical_run_dir == overlap_run_dir
    mismatches: list[str] = []
    gates: dict[str, bool] = {}

    old_cells = _read_cells(canonical_run_dir)
    new_cells = _read_cells(overlap_run_dir)
    expected_cells = {(seed, budget) for seed in SEEDS for budget in CHECKPOINTS}
    old_lattice = validate_checkpoint_lattice(old_cells)
    new_lattice = validate_checkpoint_lattice(new_cells)
    gates["canonical_checkpoint_lattice"] = not old_lattice
    gates["overlap_checkpoint_lattice"] = not new_lattice
    mismatches.extend(f"canonical: {item}" for item in old_lattice)
    mismatches.extend(f"overlap: {item}" for item in new_lattice)

    comparisons: list[dict[str, Any]] = []
    for seed, budget in sorted(expected_cells):
        row_mismatches: list[str] = []
        if (seed, budget) in old_cells and (seed, budget) in new_cells:
            row_mismatches = _compare_checkpoint(old_cells[(seed, budget)][1], new_cells[(seed, budget)][1], seed, budget)
        comparisons.append({
            "seed": seed, "checkpoint_budget": budget,
            "status": "PASS" if not row_mismatches else "FAIL",
            "mismatch_count": len(row_mismatches), "mismatches": row_mismatches,
        })
        mismatches.extend(f"seed{seed}/B{budget}: {item}" for item in row_mismatches)

    config_summary: dict[str, Any] = {}
    initial_vectors: dict[int, list[float]] = {}
    new_protocol: dict[str, Any] | None = None
    try:
        canonical_meta = _read_json(canonical_run_dir / "metadata" / "run_source_metadata.json")
        canonical_config = Path(canonical_meta["source_config_path"])
        new_cfg = load_experiment_config(overlap_config_path.resolve())
        new_protocol = _config_protocol(new_cfg)
        historical_evidence = _canonical_protocol_evidence(canonical_run_dir, new_protocol)
        config_differences = historical_evidence["differences"]
        # The historical checkpoint flags establish cold-start semantics for
        # both the legacy-config-present and legacy-config-absent paths.
        if any(old_cells.get((seed, 2000), (None, {}))[1].get("cold_start") is not True for seed in SEEDS):
            config_differences.append("canonical checkpoints do not confirm cold-start semantics")
        config_evidence = historical_evidence["evidence"]
        if new_protocol["impedance_ohm"] != 50.0:
            config_differences.append("protocol impedance is not 50 ohm")
        if new_protocol["population_size"] != 180:
            config_differences.append("initial population size is not 180")
        if new_protocol["budget"] != 8000:
            config_differences.append("overlap parity budget is not 8000")
        if new_protocol["checkpoints"] != CHECKPOINTS:
            config_differences.append("overlap checkpoint lattice differs from 2k/4k/6k/8k")
        for seed in SEEDS:
            initial_vectors[seed] = list(new_protocol["initial_design_vector"])
        gates["resolved_protocol_inputs"] = not config_differences
        mismatches.extend(config_differences)
        config_summary = {
            "canonical_config_path": str(canonical_config),
            "historical_config_evidence": config_evidence,
            "historical_source_config_status": historical_evidence["source_config_status"],
            "overlap_config_path": str(overlap_config_path.resolve()),
            "initial_design_vector_sha256": new_protocol["initial_design_vector_sha256"],
            "initial_design_source_sha256": new_protocol["initial_design_source_sha256"],
            "initial_population_seed_contract": new_protocol["initial_population_seed_contract"],
            "initial_sampling_seeds": new_protocol["initial_sampling_seeds"],
            "common_grid_id": new_protocol["common_grid_id"],
            "common_grid_count": new_protocol["common_grid_count"],
            "common_grid_array_sha256": new_protocol["common_grid_array_sha256"],
            "search_grid_count": new_protocol["search_grid_count"],
            "search_grid_sha256": new_protocol["search_grid_sha256"],
            "resolved_spec_optimizer_inputs_sha256": hashlib.sha256(_canonical_json({
                "specification": new_protocol["specification"],
                "manufacturing_constraints": new_protocol["manufacturing_constraints"],
                "backend_config": new_protocol["backend_config"],
                "profile_parameters": new_protocol["profile_parameters"],
                "active_bounds": new_protocol["active_bounds"],
                "hard_bounds": new_protocol["hard_bounds"],
                "integer_indices": new_protocol["integer_indices"],
            }).encode("utf-8")).hexdigest(),
        }
    except Exception as exc:
        gates["resolved_protocol_inputs"] = False
        mismatches.append(f"protocol input resolution failed: {type(exc).__name__}: {exc}")

    try:
        old_metadata = _metadata_protocol(canonical_run_dir)
        if new_protocol is None:
            raise ValueError("overlap config protocol could not be resolved")
        new_metadata = old_metadata if same_run_self_check else _config_metadata_protocol(new_protocol)
        metadata_differences = compare_values(old_metadata, new_metadata, "run_metadata", limit=50)
        if not same_run_self_check:
            metadata_differences.extend(_validate_current_run_metadata(overlap_run_dir, new_protocol))
        gates["run_metadata_snapshots"] = not metadata_differences
        mismatches.extend(metadata_differences)
        old_root = _read_json(canonical_run_dir / "metadata" / "run_source_metadata.json")
        new_root = _read_json(overlap_run_dir / "metadata" / "run_source_metadata.json")
        if old_root.get("budget") != 8000 or new_root.get("budget") != 8000:
            mismatches.append("run-source metadata budget does not equal 8000 for both runs")
            gates["run_metadata_snapshots"] = False
        if tuple(old_root.get("seeds", [])) != SEEDS or tuple(new_root.get("seeds", [])) != SEEDS:
            mismatches.append("run-source metadata seed list differs from the two approved seeds")
            gates["run_metadata_snapshots"] = False
    except Exception as exc:
        gates["run_metadata_snapshots"] = False
        mismatches.append(f"run metadata comparison failed: {type(exc).__name__}: {exc}")

    initializer_ok = True
    for seed in SEEDS:
        old_dir = canonical_run_dir / "optimization" / MATERIAL / TOPOLOGY / f"seed{seed}"
        new_dir = overlap_run_dir / "optimization" / MATERIAL / TOPOLOGY / f"seed{seed}"
        try:
            old_meta = _read_json(old_dir / "trajectory_metadata.json")
            new_meta = _read_json(new_dir / "trajectory_metadata.json")
            old_init = _initializer_projection(old_meta["initial_population_sampling"])
            new_init = _initializer_projection(new_meta["initial_population_sampling"])
            old_b2000 = old_cells[(seed, 2000)][1]["initial_population_sampling"]
            new_b2000 = new_cells[(seed, 2000)][1]["initial_population_sampling"]
            differences = compare_values(old_init, new_init, f"seed{seed}.initializer", limit=30)
            differences.extend(compare_values(old_init, _initializer_projection(old_b2000), f"seed{seed}.canonical_B2000_initializer", limit=10))
            differences.extend(compare_values(new_init, _initializer_projection(new_b2000), f"seed{seed}.overlap_B2000_initializer", limit=10))
            seed_contract = new_protocol["initial_population_seed_contract"] if new_protocol else {}
            for field, expected in (
                ("initial_sampling_seed_contract_id", seed_contract.get("identifier")),
                ("initial_sampling_seed_namespace", seed_contract.get("namespace")),
                ("initial_sampling_seed_derivation_suffix", seed_contract.get("derivation_suffix")),
                ("initial_sampling_seed", (new_protocol or {}).get("initial_sampling_seeds", {}).get(
                    f"{MATERIAL}/{TOPOLOGY}/{seed}"
                )),
            ):
                differences.extend(compare_values(
                    new_meta["initial_population_sampling"].get(field), expected,
                    f"seed{seed}.initializer.{field}",
                ))
            if differences:
                initializer_ok = False
                mismatches.extend(differences)
        except Exception as exc:
            initializer_ok = False
            mismatches.append(f"seed{seed} initializer comparison failed: {type(exc).__name__}: {exc}")
    gates["initializer_evidence"] = initializer_ok

    gates["checkpoint_comparisons"] = len(comparisons) == 8 and all(row["status"] == "PASS" for row in comparisons)
    common_grid_ok = True
    optimizer_state_ok = True
    for seed in SEEDS:
        old_dir = canonical_run_dir / "optimization" / MATERIAL / TOPOLOGY / f"seed{seed}"
        new_dir = overlap_run_dir / "optimization" / MATERIAL / TOPOLOGY / f"seed{seed}"
        try:
            vector = initial_vectors.get(seed)
            if vector is None:
                raise ValueError("initial design vector was not resolved")
            state_differences = _compare_optimizer_state(
                old_dir / "optimizer_checkpoint.json", new_dir / "optimizer_checkpoint.json", vector,
            )
            if state_differences:
                optimizer_state_ok = False
                mismatches.extend(f"seed{seed} optimizer state: {item}" for item in state_differences)
            grid_differences = _compare_common_grid(
                old_dir, new_dir,
                expected_grid_id=config_summary.get("common_grid_id"),
            )
            if grid_differences:
                common_grid_ok = False
                mismatches.extend(f"seed{seed} common grid: {item}" for item in grid_differences)
        except Exception as exc:
            optimizer_state_ok = False
            common_grid_ok = False
            mismatches.append(f"seed{seed} terminal comparison failed: {type(exc).__name__}: {exc}")
    gates["full_8k_optimizer_state_and_cache"] = optimizer_state_ok
    gates["8k_common_grid_finalists"] = common_grid_ok

    canonical_metadata_sha256 = _sha256_file(canonical_run_dir / "metadata" / "run_source_metadata.json")
    summary = {
        "status": "PASS" if all(gates.values()) and not mismatches else "FAIL",
        "canonical_run_dir": str(canonical_run_dir),
        "overlap_run_dir": str(overlap_run_dir),
        "overlap_config": config_summary,
        "canonical_run_source_metadata_sha256": canonical_metadata_sha256,
        "comparison_scope": {
            "material": MATERIAL, "topology": TOPOLOGY, "seeds": list(SEEDS),
            "checkpoints": list(CHECKPOINTS), "checkpoint_comparison_count": len(comparisons),
        },
        "checkpoint_comparison_count": len(comparisons),
        "checkpoint_comparisons": comparisons,
        "gates": gates,
        "tolerances": {
            "rf_metrics_violations_objective_components": {"rtol": METRIC_RTOL, "atol": METRIC_ATOL},
            "composite_objective": {"rtol": OBJECTIVE_RTOL, "atol": OBJECTIVE_ATOL},
            "decoded_design_optimizer_control_state_counters_population_cache_keys": "exact",
        },
        "provenance_exclusions": list(PROVENANCE_IGNORED_FIELDS),
        "mismatches": mismatches,
    }
    if output_dir is not None:
        _write_outputs(output_dir.resolve(), summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-run-dir", type=Path, default=CANONICAL_RUN)
    parser.add_argument("--overlap-run-dir", type=Path, required=True)
    parser.add_argument("--overlap-config", type=Path, default=OVERLAP_CONFIG)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error(f"output directory is not empty: {args.output_dir}")
    summary = verify_overlap(
        args.canonical_run_dir, args.overlap_run_dir, args.overlap_config, args.output_dir,
    )
    print(f"{summary['status']}: {summary['checkpoint_comparison_count']} overlap checkpoint comparisons")
    print(f"review artifacts: {args.output_dir.resolve()}")
    if summary["mismatches"]:
        print(f"mismatch count: {len(summary['mismatches'])}")
        for mismatch in summary["mismatches"][:20]:
            print(f"- {mismatch}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
