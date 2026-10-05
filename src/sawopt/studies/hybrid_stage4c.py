"""Frozen Stage 4C confirmatory P_D versus D_P protocol.

This is a narrow adapter over the qualified Stage 4A context and Stage 4B
cell engine. Stage 4B's implementation is imported unchanged; Stage 4C owns
the frozen contract, fresh matched matrix, manifest, and post-run handoff.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping, Sequence

import numpy as np

from .hybrid import stage4a_load_context


STUDY_TYPE = "hybrid_stage4c_confirmatory"
PROTOCOL_REVISION = "stage4c_confirmatory_v1"
AUTHORIZATION_SCOPE = "stage4c-confirmatory-production-v1"
TOPOLOGIES = ("P_D", "D_P")
SEEDS = (20261007, 20261008, 20261009, 20261010, 20261011)
STAGE4B_SEEDS = (20261002, 20261003, 20261004, 20261005, 20261006)
BUDGET = 96000
CHECKPOINTS = (8000, 16000, 24000, 32000, 48000, 64000, 80000, 96000)
INITIAL_POPULATION_MULTIPLIER = 18
FINALIST_COUNT = 16
PRODUCTION_TOTAL_EVALUATIONS = len(TOPOLOGIES) * len(SEEDS) * BUDGET
SHAKEDOWN_SEED = 20261012
SHAKEDOWN_BUDGET = 512
SHAKEDOWN_CHECKPOINTS = (400, 512)
SEARCH_GRID_SHA256 = "212dd2b0b71ddeffb7a8865937d132ee596870f25c989ac7d90c5dab6fd7faa0"
COMMON_GRID_ID = "2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f"
COMMON_GRID_SHA256 = "54c1daf67dd2bb9242f95e638d7bd801db536acc2c7d6f00c1f62a788bead554"
PRODUCTION_RUN_ROOT = "C:/Users/sub/Documents/ChatGPT/saw-com-optimizer-runs/production"
QUALIFICATION_RUN_ROOT = "C:/Users/sub/Documents/ChatGPT/saw-com-optimizer-runs/qualification/stage4c"
NETWORK_CONVENTION = "Stage 4A; exp(+jωt), left-to-right, power-normalized acoustic waves"
MATURITY_CRITERIA = {
    "convergence_evidence_complete": True,
    "grid_converged": True,
    "recovery_pending_confirmation": False,
    "historical_bound_hit_alone_blocks_maturity": False,
    "hard_bound_unresolved": False,
    "boundary_pending_confirmation": False,
    "significant_improvement_80k_to_96k": False,
    "fraction_of_budget_at_last_significant_improvement_max": 0.80,
}
CLOSEOUT_CRITERIA = {
    "primary_comparator": "feasibility_first_lexicographic",
    "comparator_fields": ["feasible", "max_violation", "sum_violation", "worst_il_db"],
    "no_weighted_scalar_score": True,
    "model_level_materiality": {
        "primary_metric": "max_normalized_violation",
        "absolute_difference_threshold": 0.02,
        "meaning": "internal_computational_interpretation_threshold",
        "manufacturing_or_measurement_tolerance": False,
    },
    "clear_winner": {
        "minimum_matched_seed_wins": 4,
        "late_checkpoints": [64000, 80000, 96000],
        "same_seed_wins_required_at_each_late_checkpoint": 4,
        "require_all_cells_mature": True,
        "terminal_winner_pairs_required": 4,
        "material_pair_rule": (
            "feasibility_differs_in_favor_of_winner OR both_infeasible_and_abs_delta_max_violation_at_least_0.02"
        ),
        "require_no_convergence_or_boundary_caveat": True,
    },
    "practically_equivalent": {
        "require_all_cells_mature": True,
        "require_no_stable_four_of_five_late_preference": True,
        "require_matched_feasibility_status_for_every_seed": True,
        "all_five_terminal_abs_delta_max_violation_strictly_below": 0.02,
    },
    "otherwise": "STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED",
}


def expected_matrix(
    *, seeds: Sequence[int] = SEEDS, budget: int = BUDGET,
    terminal_budget: int = BUDGET, checkpoints: Sequence[int] = CHECKPOINTS,
    topologies: Sequence[str] = TOPOLOGIES,
) -> list[dict[str, Any]]:
    """Return the complete, cold-started matched-seed cell matrix."""
    dimensions = {"P_D": 13, "D_P": 13}
    if set(topologies) != set(TOPOLOGIES) or len(topologies) != len(TOPOLOGIES):
        raise ValueError("Stage 4C topology set must be exactly P_D and D_P")
    return [{
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
        "historical_population_injection": False,
    } for topology in topologies for seed in seeds]


def expected_shakedown_matrix() -> list[dict[str, Any]]:
    """Return the isolated two-topology matrix for non-scientific qualification."""
    return expected_matrix(
        seeds=(SHAKEDOWN_SEED,), budget=SHAKEDOWN_BUDGET,
        terminal_budget=SHAKEDOWN_BUDGET, checkpoints=SHAKEDOWN_CHECKPOINTS,
    )


def _require_equal(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise ValueError(f"Stage 4C protected/frozen input mismatch: {label}")


def validate_frozen_config(cfg: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed on protocol drift or any protected Stage 4B input change."""
    study = cfg.get("study", {})
    dms = cfg.get("dms_topology", {})
    hybrid = cfg.get("hybrid", {})
    stage = cfg.get("stage4c", {})
    storage = cfg.get("storage_contract", {})
    base_dms = baseline["dms_topology"]
    base_hybrid = baseline["hybrid"]
    _require_equal("study type", study.get("type"), STUDY_TYPE)
    _require_equal("protocol revision", study.get("revision"), PROTOCOL_REVISION)
    _require_equal("comparison topologies", tuple(hybrid.get("supported_topologies", ())), TOPOLOGIES)
    _require_equal("Stage 4C supported topologies", tuple(stage.get("supported_hybrid_topologies", ())), TOPOLOGIES)
    _require_equal("study topology declaration", tuple(study.get("topologies", ())), TOPOLOGIES)
    _require_equal("study seeds", tuple(study.get("seeds", ())), SEEDS)
    _require_equal("DMS seeds", tuple(dms.get("seeds", ())), SEEDS)
    _require_equal("Stage 4C seeds", tuple(stage.get("seeds", ())), SEEDS)
    if set(SEEDS) & set(STAGE4B_SEEDS):
        raise ValueError("Stage 4C production seeds overlap Stage 4B seeds")
    _require_equal("budget", int(dms.get("budget", -1)), BUDGET)
    _require_equal("study budget", int(study.get("budget_per_cell", -1)), BUDGET)
    _require_equal("Stage 4C budget", int(stage.get("budget_per_cell", -1)), BUDGET)
    _require_equal("terminal schedule budget", int(dms.get("population_schedule_terminal_budget", -1)), BUDGET)
    _require_equal("study terminal budget", int(study.get("population_schedule_terminal_budget", -1)), BUDGET)
    _require_equal("Stage 4C terminal budget", int(stage.get("population_schedule_terminal_budget", -1)), BUDGET)
    _require_equal("checkpoints", tuple(int(x) for x in dms.get("checkpoints", ())), CHECKPOINTS)
    _require_equal("study checkpoints", tuple(int(x) for x in study.get("checkpoints", ())), CHECKPOINTS)
    _require_equal("Stage 4C checkpoints", tuple(int(x) for x in stage.get("checkpoints", ())), CHECKPOINTS)
    _require_equal("initial population rule", dms.get("initial_population_per_dimension"), INITIAL_POPULATION_MULTIPLIER)
    _require_equal("cold start", dms.get("cold_start"), True)
    _require_equal("no explicit population override", dms.get("initial_population"), None)
    _require_equal("material", tuple(dms.get("selection", {}).get("materials", ())), ("MLIT",))
    _require_equal("DMS model", tuple(dms.get("selection", {}).get("topologies", ())), ("T1_SYMMETRIC_5IDT",))
    _require_equal("study material", stage.get("material"), "MLIT")
    _require_equal("study DMS topology", stage.get("dms_topology"), "T1_SYMMETRIC_5IDT")
    _require_equal("optimizer", stage.get("optimizer"), "L-SHADE")
    _require_equal("ports", (float(hybrid.get("source_impedance_ohm", 0)),
                              float(hybrid.get("load_impedance_ohm", 0)),
                              float(dms.get("impedance_ohm", 0))), (50.0, 50.0, 50.0))
    _require_equal("stage ports", (float(stage.get("source_impedance_ohm", 0)),
                                    float(stage.get("load_impedance_ohm", 0))), (50.0, 50.0))
    _require_equal("warm start", stage.get("warm_start"), False)
    _require_equal("parent transfer", stage.get("parent_transfer"), False)
    _require_equal("topology transfer", stage.get("topology_transfer"), False)
    _require_equal("historical population injection", stage.get("historical_population_injection"), False)
    _require_equal("production early stop", stage.get("production_early_stop"), False)
    _require_equal("production launch gate", stage.get("production_launch_authorized"), False)
    _require_equal("hybrid production launch gate", hybrid.get("production_launch_authorized"), False)
    _require_equal("production storage policy", storage.get("production_policy"), "external_persistent_v1")
    _require_equal("production persistent root", storage.get("production_root"), PRODUCTION_RUN_ROOT)
    _require_equal("qualification storage policy", storage.get("qualification_policy"), "external_qualification_v1")
    _require_equal("qualification persistent root", storage.get("qualification_root"), QUALIFICATION_RUN_ROOT)
    _require_equal("initial population rule declaration", stage.get("initial_population_rule"), "18 * topology_dimension")
    _require_equal("initial populations", stage.get("initial_populations"), {"P_D": 234, "D_P": 234})
    _require_equal("finalist count", hybrid.get("common_grid_finalists"), FINALIST_COUNT)
    _require_equal("stage finalist count", stage.get("common_grid_finalists"), FINALIST_COUNT)

    protected = stage.get("protected_inputs", {})
    _require_equal("protected specification", protected.get("specification"), baseline["spec"])
    _require_equal("protected geometry constraints", protected.get("geometry_constraints"), baseline["constraints"])
    _require_equal("protected MLIT profile config", protected.get("mlit_profile"), base_dms["materials"]["MLIT"])
    _require_equal("protected T1 active bounds", protected.get("t1_active_bounds"), baseline["_stage4c_t1_active_bounds"])
    _require_equal("protected T1 hard bounds", protected.get("t1_hard_bounds"), baseline["_stage4c_t1_hard_bounds"])
    for label, key, expected in (
        ("specification", "spec", baseline["spec"]),
        ("geometry constraints", "constraints", baseline["constraints"]),
        ("MLIT profile", "materials", base_dms["materials"]["MLIT"]),
        ("resonator wavelength/pair bounds", "resonator_bounds", base_hybrid["resonator_bounds"]),
        ("resonator aperture bounds", "resonator_aperture_bounds_um", base_hybrid["resonator_aperture_bounds_um"]),
        ("resonator model", "resonator_model", base_hybrid["resonator_model"]),
        ("layout", "layout", base_hybrid["layout"]),
    ):
        actual = cfg.get(key) if key in {"spec", "constraints"} else (
            dms.get("materials", {}).get("MLIT") if key == "materials" else hybrid.get(key)
        )
        _require_equal(label, actual, expected)
    _require_equal("protected resonator bounds", protected.get("resonator_bounds"), base_hybrid["resonator_bounds"])
    _require_equal("protected aperture bounds", protected.get("resonator_aperture_bounds_um"), base_hybrid["resonator_aperture_bounds_um"])
    _require_equal("T1 reflector electrodes", protected.get("t1_reflector_electrodes"), base_dms.get("t1_reflector_electrodes"))
    model = base_hybrid["resonator_model"]
    _require_equal("protected metallization ratio", protected.get("metallization_ratio"), model["metallization_ratio"])
    _require_equal("protected thickness/lambda", protected.get("thickness_over_lambda"), model["thickness_over_lambda"])
    _require_equal("protected resonator gap/lambda", protected.get("gap_lambda"), model["gap_lambda"])
    _require_equal("protected layout", protected.get("layout"), base_hybrid["layout"])
    _require_equal("search grid point count", protected.get("search_grid_points"), 1001)
    _require_equal("search grid SHA", protected.get("search_grid_sha256"), SEARCH_GRID_SHA256)
    _require_equal("common grid point count", protected.get("common_validation_grid_points"), 9113)
    _require_equal("common grid ID", protected.get("common_validation_grid_id"), COMMON_GRID_ID)
    _require_equal("common grid SHA", protected.get("common_validation_grid_sha256"), COMMON_GRID_SHA256)
    _require_equal("network convention", protected.get("network_convention"), NETWORK_CONVENTION)
    _require_equal("maturity criteria", stage.get("maturity_criteria"), MATURITY_CRITERIA)
    closeout = stage.get("closeout_criteria", {})
    _require_equal("closeout classification criteria", closeout, CLOSEOUT_CRITERIA)
    initializer = hybrid.get("initializer", {})
    _require_equal("initializer method", initializer.get("method"), "independent_uniform_rejection_v1")
    _require_equal("initializer attempt budget", initializer.get("max_attempts"), 10000)
    _require_equal("initializer historical-seed policy", initializer.get("include_historical_seed"), False)
    _require_equal("initializer derivation", initializer.get("seed_derivation"),
                   "sha256(stage4b-v1/seed/material/topology/initial_population)")
    _require_equal("stage initializer", stage.get("initializer"), initializer)
    _require_equal("layout model", hybrid.get("layout"), base_hybrid["layout"])
    return {
        "specification": cfg["spec"],
        "geometry_constraints": cfg["constraints"],
        "material_profile_config": dms["materials"]["MLIT"],
        "material": "MLIT",
        "dms_topology": "T1_SYMMETRIC_5IDT",
        "t1_active_bounds": baseline["_stage4c_t1_active_bounds"],
        "t1_hard_bounds": baseline["_stage4c_t1_hard_bounds"],
        "t1_reflector_electrodes": int(base_dms["t1_reflector_electrodes"]),
        "mlit_profile_metadata": baseline["_stage4c_profile_metadata"],
        "resonator_bounds": hybrid["resonator_bounds"],
        "resonator_aperture_bounds_um": hybrid["resonator_aperture_bounds_um"],
        "resonator_model": hybrid["resonator_model"],
        "layout": hybrid["layout"],
        "source_impedance_ohm": 50.0,
        "load_impedance_ohm": 50.0,
        "network_convention": NETWORK_CONVENTION,
        "search_grid_points": 1001,
        "search_grid_sha256": SEARCH_GRID_SHA256,
        "common_validation_grid_points": 9113,
        "common_validation_grid_id": COMMON_GRID_ID,
        "common_validation_grid_sha256": COMMON_GRID_SHA256,
    }


def load_stage4c_context(config_path: str | Path) -> dict[str, Any]:
    """Load Stage 4C over the qualified Stage 4A model and freeze its inputs."""
    from ..core.hybrid import RESONATOR_BOUNDS
    from ..io.config import load_experiment_config
    from ..io.provenance import build_fingerprint_metadata
    import yaml

    root = Path(__file__).resolve().parents[3]
    baseline_context = stage4a_load_context(root / "configs/studies/hybrid_stage4a_qualification.yaml")
    cfg_path = Path(config_path)
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    cfg_path = cfg_path.resolve()
    raw_cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    _require_equal("base configuration", raw_cfg.get("base_config"), "dms_topology_screening.yaml")
    cfg = load_experiment_config(cfg_path)
    baseline = dict(baseline_context["cfg"])
    baseline["_stage4c_t1_active_bounds"] = baseline_context["contract"]["dms_active_bounds"]
    baseline["_stage4c_t1_hard_bounds"] = baseline_context["contract"]["dms_hard_bounds"]
    baseline["_stage4c_profile_metadata"] = baseline_context["profile_metadata"]
    protected = validate_frozen_config(cfg, baseline)
    _require_equal("qualified resonator bounds", cfg["hybrid"]["resonator_bounds"],
                   np.asarray(RESONATOR_BOUNDS, dtype=float).tolist())
    _require_equal("search grid identity", len(baseline_context["search_frequencies"]), 1001)
    _require_equal("computed search grid SHA", baseline_context["contract"]["search_frequency_sha256"], SEARCH_GRID_SHA256)
    _require_equal("common validation grid identity", len(baseline_context["common_frequencies"]), 9113)
    _require_equal("computed common grid ID", baseline_context["common_grid_id"], COMMON_GRID_ID)
    _require_equal("computed common grid SHA", baseline_context["grid_metadata"]["sha256"], COMMON_GRID_SHA256)
    if {name: baseline_context["spaces"][name].dimension for name in TOPOLOGIES} != {"P_D": 13, "D_P": 13}:
        raise ValueError("Stage 4C topology dimensions must both be 13")

    dimensions = {"P_D": 13, "D_P": 13}
    contract = {
        "study_type": STUDY_TYPE,
        "protocol_revision": PROTOCOL_REVISION,
        "optimizer": "L-SHADE",
        "material": "MLIT",
        "dms_topology": "T1_SYMMETRIC_5IDT",
        "topologies": list(TOPOLOGIES),
        "source_impedance_ohm": 50.0,
        "load_impedance_ohm": 50.0,
        "seeds": list(SEEDS),
        "budget_per_cell": BUDGET,
        "population_schedule_terminal_budget": BUDGET,
        "checkpoints": list(CHECKPOINTS),
        "initial_population_rule": "18 * topology_dimension",
        "initial_populations": {name: INITIAL_POPULATION_MULTIPLIER * dimension
                                 for name, dimension in dimensions.items()},
        "cold_start": True,
        "warm_start": False,
        "parent_transfer": False,
        "topology_transfer": False,
        "historical_population_injection": False,
        "production_early_stop": False,
        "storage_contract": cfg["storage_contract"],
        "finalist_count_per_checkpoint": FINALIST_COUNT,
        "search_frequency_count": 1001,
        "search_frequency_sha256": SEARCH_GRID_SHA256,
        "common_validation_grid_id": COMMON_GRID_ID,
        "common_validation_frequency_count": 9113,
        "common_validation_grid_sha256": COMMON_GRID_SHA256,
        "protected_scientific_inputs": protected,
        "com_provider": baseline_context["profile_metadata"],
        "matrix": expected_matrix(),
        "total_unique_evaluations": PRODUCTION_TOTAL_EVALUATIONS,
        "initializer_contract": cfg["stage4c"]["initializer"],
        "maturity_criteria": cfg["stage4c"]["maturity_criteria"],
        "closeout_criteria": cfg["stage4c"]["closeout_criteria"],
        "run_storage_policy": "external_persistent_v1",
    }
    config_relative = cfg_path.relative_to(root).as_posix()
    computation_paths = tuple(dict.fromkeys((*baseline_context["computation_paths"], config_relative,
                                              "src/sawopt/studies/hybrid_stage4c.py",
                                              "src/sawopt/studies/hybrid_stage4b.py",
                                              "src/sawopt/optimization/convergence_evidence.py")))
    reporting_paths = (
        "src/sawopt/reporting/hybrid_stage4c.py",
        "src/sawopt/reporting/github_review.py",
    )
    fingerprint = build_fingerprint_metadata(
        root, contract, computation_paths=computation_paths,
        reporting_paths=reporting_paths,
    )
    context = dict(baseline_context)
    context.update({
        "root": root,
        "config_path": cfg_path,
        "cfg": cfg,
        "contract": contract,
        "fingerprint": fingerprint,
        "matrix": expected_matrix(),
        "initial_populations": {"P_D": 234, "D_P": 234},
        "t1_hard_bounds": baseline_context["contract"]["dms_hard_bounds"],
        "protected_scientific_inputs": protected,
        "computation_paths": computation_paths,
        "reporting_paths": reporting_paths,
        "source_impedance_ohm": 50.0,
        "load_impedance_ohm": 50.0,
    })
    return context


def build_stage4c_run_manifest(
    context: Mapping[str, Any], *, run_id: str, source_commit_sha: str,
    mode: str = "production", run_storage_policy: str = "external_persistent_v1",
) -> dict[str, Any]:
    """Build a small immutable protocol manifest without deprecated session fields."""
    if not run_id or not source_commit_sha:
        raise ValueError("Stage 4C run manifest requires run_id and source_commit_sha")
    if mode not in {"production", "shakedown"}:
        raise ValueError("Stage 4C run mode must be production or shakedown")
    expected_policy = "external_persistent_v1" if mode == "production" else "external_qualification_v1"
    if run_storage_policy != expected_policy:
        raise ValueError(f"Stage 4C {mode} requires storage policy {expected_policy}")
    contract = context["contract"]
    return {
        "schema_version": 1,
        "run_id": str(run_id),
        "mode": mode,
        "study_type": STUDY_TYPE,
        "protocol_revision": PROTOCOL_REVISION,
        "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
        "source_commit_sha": str(source_commit_sha),
        "topologies": list(TOPOLOGIES),
        "expected_cell_count": len(TOPOLOGIES) * (len(SEEDS) if mode == "production" else 1),
        "seeds": list(SEEDS) if mode == "production" else [SHAKEDOWN_SEED],
        "budget_per_cell": BUDGET if mode == "production" else SHAKEDOWN_BUDGET,
        "population_schedule_terminal_budget": BUDGET if mode == "production" else SHAKEDOWN_BUDGET,
        "checkpoints": list(CHECKPOINTS) if mode == "production" else list(SHAKEDOWN_CHECKPOINTS),
        "initial_population_rule": "18 * topology_dimension",
        "initial_populations": {"P_D": 234, "D_P": 234},
        "production_early_stop": False,
        "search_grid_sha256": SEARCH_GRID_SHA256,
        "common_validation_grid_id": COMMON_GRID_ID,
        "common_validation_grid_sha256": COMMON_GRID_SHA256,
        "model_profile_provenance": context["profile_metadata"],
        "source_impedance_ohm": 50.0,
        "load_impedance_ohm": 50.0,
        "cold_start": True,
        "warm_start": False,
        "parent_transfer": False,
        "topology_transfer": False,
        "historical_population_injection": False,
        "run_storage_policy": run_storage_policy,
        "required_storage_root": (PRODUCTION_RUN_ROOT if mode == "production"
                                  else QUALIFICATION_RUN_ROOT),
        "ranking_eligible": mode == "production",
        "scientific_evidence": mode == "production",
        "matrix": expected_matrix() if mode == "production" else expected_shakedown_matrix(),
        "fingerprint_schema_version": context["fingerprint"]["fingerprint_schema_version"],
        "dependency_manifest": context["fingerprint"]["dependency_manifest"],
    }


def validate_stage4c_run_manifest(
    saved: Mapping[str, Any], expected: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate immutable protocol fields while preserving the original creation time."""
    if not isinstance(saved, Mapping):
        raise RuntimeError("existing Stage 4C run manifest is not an object")
    for key, value in expected.items():
        if saved.get(key) != value:
            raise RuntimeError(f"Stage 4C immutable run manifest mismatch: {key}")
    created_at = saved.get("created_at_utc")
    if not isinstance(created_at, str) or not created_at.strip():
        raise RuntimeError("Stage 4C immutable run manifest mismatch: created_at_utc")
    validated = dict(expected)
    validated["created_at_utc"] = created_at
    return validated


def ensure_stage4c_run_manifest(
    manifest_path: str | Path, expected: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Create the manifest once or validate its immutable contract on resume."""
    path = Path(manifest_path)
    if path.is_file():
        saved = json.loads(path.read_text(encoding="utf-8"))
        return validate_stage4c_run_manifest(saved, expected), False
    if path.exists():
        raise RuntimeError("Stage 4C run manifest path exists but is not a file")
    value = {
        **dict(expected),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_json(path, value)
    return value, True


def authorization_claim_id(metadata: Mapping[str, Any]) -> str:
    """Return the source/protocol-scoped one-shot authorization identity."""
    payload = "|".join((
        str(metadata.get("authorization_scope", "")),
        str(metadata.get("computation_fingerprint", "")),
        str(metadata.get("source_commit_sha", "")),
    ))
    if not all(payload.split("|")):
        raise ValueError("Stage 4C authorization claim key is incomplete")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_authorization_metadata(
    context: Mapping[str, Any], *, source_commit_sha: str, run_id: str,
    authorized_at: str,
) -> dict[str, Any]:
    """Bind a future explicit approval to this exact frozen protocol."""
    if not source_commit_sha or not run_id or not authorized_at:
        raise ValueError("Stage 4C authorization requires source, run ID, and timestamp")
    return {
        "user_authorized_production": True,
        "authorization_scope": AUTHORIZATION_SCOPE,
        "required_production_root": PRODUCTION_RUN_ROOT,
        "study_type": STUDY_TYPE,
        "protocol_revision": PROTOCOL_REVISION,
        "protocol_fingerprint": PROTOCOL_REVISION,
        "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
        "source_commit_sha": str(source_commit_sha),
        "run_id": str(run_id),
        "topologies": list(TOPOLOGIES),
        "comparison_arms": list(TOPOLOGIES),
        "seeds": list(SEEDS),
        "expected_cell_count": 10,
        "budget_per_cell": BUDGET,
        "population_schedule_terminal_budget": BUDGET,
        "checkpoints": list(CHECKPOINTS),
        "initial_population_rule": "18 * topology_dimension",
        "initial_populations": {"P_D": 234, "D_P": 234},
        "production_early_stop": False,
        "search_grid_sha256": SEARCH_GRID_SHA256,
        "search_grid_points": 1001,
        "common_validation_grid_id": COMMON_GRID_ID,
        "common_validation_grid_points": 9113,
        "common_validation_grid_sha256": COMMON_GRID_SHA256,
        "source_impedance_ohm": 50.0,
        "load_impedance_ohm": 50.0,
        "cold_start": True,
        "warm_start": False,
        "parent_transfer": False,
        "topology_transfer": False,
        "historical_population_injection": False,
        "run_storage_policy": "external_persistent_v1",
        "authorized_at": str(authorized_at),
    }


def verify_stage4c_authorization(
    context: Mapping[str, Any], manifest_path: str | Path,
) -> dict[str, Any]:
    """Verify a future caller-supplied orchestration manifest; never mint approval."""
    path = Path(manifest_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    metadata = raw.get("experiment_metadata", {})
    if not isinstance(metadata, Mapping):
        raise ValueError("Stage 4C orchestration manifest lacks experiment metadata")
    for key, expected in build_authorization_metadata(
        context, source_commit_sha=str(raw.get("source_commit_sha", "")),
        run_id=str(raw.get("run_id", "")),
        authorized_at=str(metadata.get("authorized_at", "")),
    ).items():
        if metadata.get(key) != expected:
            raise PermissionError(f"Stage 4C authorization manifest mismatch: {key}")
    if raw.get("study_type") != STUDY_TYPE:
        raise PermissionError("Stage 4C authorization manifest study type mismatch")
    if metadata.get("orchestration_run_dir") != raw.get("run_dir"):
        raise PermissionError("Stage 4C orchestration run path differs from its authorization metadata")
    if metadata.get("optimizer_run_dir") != raw.get("optimizer_run_dir"):
        raise PermissionError("Stage 4C optimizer run path differs from its authorization metadata")
    if raw.get("run_storage_policy") != "external_persistent_v1":
        raise PermissionError("Stage 4C production requires external_persistent_v1 storage")
    if not raw.get("persistent_run_root") or not _is_absolute_path(raw["persistent_run_root"]):
        raise PermissionError("Stage 4C production requires an absolute external persistent run root")
    if not _is_within(raw["persistent_run_root"], PRODUCTION_RUN_ROOT):
        raise PermissionError("Stage 4C production root must be below the frozen external production destination")
    if not _is_within(raw.get("run_dir", ""), raw["persistent_run_root"]):
        raise PermissionError("Stage 4C run directory is outside its declared persistent root")
    if (raw.get("continuation_mode") != "queue" or raw.get("review_after_completion") is not True
            or not raw.get("original_thread_id")
            or raw.get("queue_preflight", {}).get("status") != "PASS"
            or raw.get("queue_preflight", {}).get("thread_id") != raw.get("original_thread_id")):
        raise PermissionError("Stage 4C authorization must preserve the qualified exact-thread queue workflow")
    from ..reporting.github_review import _canonical_json_sha256, load_review_spec

    spec = raw.get("review_spec")
    if (raw.get("review_spec_id") != "hybrid_stage4c"
            or raw.get("review_stage") != "stage4c"
            or raw.get("review_contract_version") != "1"
            or raw.get("review_output_dir", "").replace("\\", "/").strip("/")
            != f"reports/experiment_reviews/stage4c/{raw.get('run_id', '')}"):
        raise PermissionError("Stage 4C authorization review destination/identity mismatch")
    declared_spec = load_review_spec("hybrid_stage4c", context["root"])
    if (not isinstance(spec, Mapping) or dict(spec) != declared_spec
            or _canonical_json_sha256(spec) != raw.get("review_spec_sha256")):
        raise PermissionError("Stage 4C authorization frozen review spec mismatch")
    if "codex_session_id" in metadata or "callback_enabled" in metadata:
        raise PermissionError("Stage 4C protocol metadata contains deprecated session/callback fields")

    from ..orchestration.active_runs import git_common_dir

    claim_id = authorization_claim_id(metadata)
    claim_path = (
        git_common_dir(Path(context["root"]))
        / "sawopt-stage4c-authorization-claims"
        / f"{claim_id}.json"
    )
    if metadata.get("authorization_claim_id") != claim_id:
        raise PermissionError("Stage 4C authorization claim identifier mismatch")
    recorded_claim_path = Path(str(metadata.get("authorization_claim_path", ""))).resolve(strict=False)
    if recorded_claim_path != claim_path.resolve(strict=False):
        raise PermissionError("Stage 4C authorization claim path mismatch")
    if not claim_path.is_file():
        raise PermissionError("Stage 4C one-shot authorization claim is missing")
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    if (
        not isinstance(claim, Mapping)
        or claim.get("schema_version") != 1
        or claim.get("claim_id") != claim_id
        or claim.get("authorization_scope") != AUTHORIZATION_SCOPE
        or claim.get("computation_fingerprint") != metadata.get("computation_fingerprint")
        or claim.get("source_commit_sha") != metadata.get("source_commit_sha")
        or claim.get("run_id") != raw.get("run_id")
    ):
        raise PermissionError("Stage 4C one-shot authorization claim does not match this run")
    return {
        "manifest": raw,
        "authorization": dict(metadata),
        "claim_id": claim_id,
        "claim_path": claim_path,
    }


def _is_absolute_path(candidate: str | Path) -> bool:
    """Recognize native absolute paths and frozen Windows paths during portable review/tests."""
    value = str(candidate)
    return Path(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _is_within(candidate: str | Path, parent: str | Path) -> bool:
    """Compare path components without accepting textual prefixes, including Windows paths on POSIX CI."""
    candidate_text, parent_text = str(candidate), str(parent)
    if PureWindowsPath(parent_text).is_absolute():
        try:
            PureWindowsPath(candidate_text).relative_to(PureWindowsPath(parent_text))
        except ValueError:
            return False
        return True
    try:
        Path(candidate).resolve(strict=False).relative_to(Path(parent).resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _atomic_json(path: Path, value: Any) -> None:
    from .hybrid import stage4a_clean
    from .hybrid_stage4b import write_atomic_json as _atomic

    # Keep the same finite-number normalization and atomic write convention as Stage 4B.
    _atomic(path, stage4a_clean(value))


def run_stage4c_production(
    config_path: str | Path, run_path: str | Path,
    authorization_manifest_path: str | Path,
) -> dict[str, Any]:
    """Execute/resume the exact 10-cell matrix after a separately authorized launch."""
    from .hybrid_stage4b import read_source_state, run_matched_cell

    context = load_stage4c_context(config_path)
    authorization = verify_stage4c_authorization(context, authorization_manifest_path)
    raw = authorization["manifest"]
    source = read_source_state(Path(context["root"]))
    if source["head"] != raw.get("source_commit_sha") or source["status_short"]:
        raise PermissionError("Stage 4C production source must match the clean authorized commit")
    run = Path(run_path)
    if not run.is_absolute():
        raise ValueError("Stage 4C production run directory must be absolute")
    run = run.resolve()
    parent_run = Path(raw["run_dir"]).resolve()
    if run != Path(raw["optimizer_run_dir"]).resolve():
        raise PermissionError("Stage 4C optimizer path differs from its authorized orchestration manifest")
    if not _is_within(parent_run, PRODUCTION_RUN_ROOT):
        raise PermissionError("Stage 4C run directory is outside the frozen external production destination")
    if _is_within(parent_run, context["root"]):
        raise PermissionError("Stage 4C production run directory is inside the repository worktree")
    existing_manifest = run / "metadata" / "stage4c_run_manifest.json"
    resume = existing_manifest.is_file()
    expected_manifest = build_stage4c_run_manifest(
        context, run_id=str(raw["run_id"]), source_commit_sha=str(raw["source_commit_sha"]),
    )
    run_manifest, manifest_created = ensure_stage4c_run_manifest(existing_manifest, expected_manifest)
    if manifest_created:
        (run / "metadata").mkdir(parents=True, exist_ok=True)
        _atomic_json(run / "metadata" / "protocol_snapshot.json", context["contract"])
        _atomic_json(run / "metadata" / "integrity_check.json", {
            "status": "RUNNING", "complete": False, "cells_present": 0,
            "cells_completed": 0, "expected_cells": 10,
        })
        (run / "metadata" / "config_snapshot.yaml").write_text(
            Path(context["config_path"]).read_text(encoding="utf-8"), encoding="utf-8",
        )
    results = []
    for item in context["matrix"]:
        results.append(run_matched_cell(
            context, run, topology=item["topology"], seed=item["seed"],
            budget=BUDGET, checkpoints=CHECKPOINTS, terminal_budget=BUDGET,
            finalist_count=FINALIST_COUNT, mode="production",
            source_commit_sha=str(raw["source_commit_sha"]),
            resume=resume, compact_history_cache=True,
        ))
    from ..reporting.hybrid_stage4c import write_stage4c_reports
    report = write_stage4c_reports(run, context, results)
    return {"status": report["integrity"]["status"], "run_dir": str(run),
            "cells": results, "integrity": report["integrity"],
            "classification": report["classification"]}


def run_stage4c_shakedown(
    config_path: str | Path, run_path: str | Path, *, resume: bool = False,
) -> dict[str, Any]:
    """Run the explicitly non-scientific two-cell Stage 4C qualification path."""
    from ..orchestration.persistent_storage import validate_persistent_run_location
    from .hybrid_stage4b import read_source_state, run_matched_cell

    context = load_stage4c_context(config_path)
    run = Path(run_path)
    if not run.is_absolute():
        raise ValueError("Stage 4C shakedown path must be absolute")
    run = run.resolve(strict=False)
    qualification_root = Path(QUALIFICATION_RUN_ROOT).resolve(strict=False)
    if run == qualification_root or not _is_within(run, qualification_root):
        raise ValueError("Stage 4C shakedown must be below the frozen external qualification root")
    if _is_within(run, context["root"]):
        raise ValueError("Stage 4C shakedown must be outside every repository worktree")
    storage_target = run if not run.exists() else run / f".storage-validation-{os.getpid()}"
    storage_validation = validate_persistent_run_location(storage_target, context["root"])
    if not storage_validation.passed:
        raise ValueError(f"Stage 4C shakedown storage validation failed: {storage_validation.reason}")

    source = read_source_state(Path(context["root"]))
    if source["status_short"]:
        raise RuntimeError("Stage 4C shakedown requires a clean committed source tree")
    manifest_path = run / "metadata" / "stage4c_run_manifest.json"
    expected_manifest = build_stage4c_run_manifest(
        context, run_id=run.name, source_commit_sha=source["head"],
        mode="shakedown", run_storage_policy="external_qualification_v1",
    )
    if manifest_path.is_file() and not resume:
        raise FileExistsError("Stage 4C shakedown already exists; pass resume=True to continue it")
    if not manifest_path.is_file() and resume:
        raise FileNotFoundError("cannot resume Stage 4C shakedown without its original manifest")
    if not manifest_path.exists() and run.exists() and any(run.iterdir()):
        raise FileExistsError("Stage 4C shakedown output is non-empty without its run manifest")
    run_manifest, manifest_created = ensure_stage4c_run_manifest(manifest_path, expected_manifest)
    if manifest_created:
        (run / "metadata").mkdir(parents=True, exist_ok=True)
        _atomic_json(run / "metadata" / "protocol_snapshot.json", context["contract"])
        _atomic_json(run / "metadata" / "integrity_check.json", {
            "status": "RUNNING", "complete": False,
            "cells_present": 0, "cells_completed": 0, "expected_cells": 2,
        })
        (run / "metadata" / "config_snapshot.yaml").write_text(
            Path(context["config_path"]).read_text(encoding="utf-8"), encoding="utf-8",
        )

    results = []
    for item in expected_shakedown_matrix():
        results.append(run_matched_cell(
            context, run, topology=item["topology"], seed=item["seed"],
            budget=SHAKEDOWN_BUDGET, checkpoints=SHAKEDOWN_CHECKPOINTS,
            terminal_budget=SHAKEDOWN_BUDGET, finalist_count=FINALIST_COUNT,
            mode="shakedown", source_commit_sha=source["head"], resume=resume,
            compact_history_cache=True,
        ))
    from ..reporting.hybrid_stage4c import write_stage4c_shakedown_reports

    report = write_stage4c_shakedown_reports(run, context, results, run_manifest)
    return {**report, "run_dir": str(run), "cells": results}


__all__ = [
    "BUDGET", "CHECKPOINTS", "COMMON_GRID_ID", "COMMON_GRID_SHA256",
    "FINALIST_COUNT", "INITIAL_POPULATION_MULTIPLIER", "PROTOCOL_REVISION",
    "PRODUCTION_TOTAL_EVALUATIONS", "SEARCH_GRID_SHA256", "SEEDS",
    "SHAKEDOWN_BUDGET", "SHAKEDOWN_CHECKPOINTS", "SHAKEDOWN_SEED",
    "STAGE4B_SEEDS", "STUDY_TYPE", "TOPOLOGIES", "PRODUCTION_RUN_ROOT",
    "QUALIFICATION_RUN_ROOT", "AUTHORIZATION_SCOPE", "authorization_claim_id", "build_authorization_metadata",
    "build_stage4c_run_manifest", "expected_matrix", "expected_shakedown_matrix", "load_stage4c_context",
    "run_stage4c_production", "run_stage4c_shakedown", "validate_frozen_config",
    "ensure_stage4c_run_manifest", "validate_stage4c_run_manifest",
    "verify_stage4c_authorization",
]
