"""Matched Stage 4B hybrid topology production protocol.

The runner reuses Stage 4A's physical model, design spaces, evaluator, and
L-SHADE checkpoint implementation. This module only owns the fixed Stage 4B
matrix, cell lifecycle, and production authorization binding.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
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
    stage4a_load_context,
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
SHAKEDOWN_SEED = 20261001
SHAKEDOWN_BUDGET = 512
SHAKEDOWN_CHECKPOINTS = (400, 512)


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


def _git_value(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    )
    return result.stdout.strip()


def _source_state(root: Path) -> dict[str, Any]:
    return {
        "branch": _git_value(root, "branch", "--show-current"),
        "head": _git_value(root, "rev-parse", "HEAD"),
        "status_short": _git_value(root, "status", "--short"),
    }


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


def load_stage4b_context(config_path: str | Path) -> dict[str, Any]:
    """Load and fail-closed validate the fixed production protocol."""
    from ..io.config import load_experiment_config
    from ..io.provenance import build_fingerprint_metadata
    from ..design.topology import RESONATOR_BOUNDS

    context = stage4a_load_context(config_path)
    stage4a_contract = context["contract"]
    context["t1_hard_bounds"] = stage4a_contract["dms_hard_bounds"]
    root = Path(context["root"]).resolve()
    cfg = context["cfg"]
    study = cfg.get("study", {})
    settings = cfg["dms_topology"]
    hybrid = cfg["hybrid"]
    stage4b = cfg.get("stage4b", {})
    if study.get("type") != STUDY_TYPE or study.get("revision") != PROTOCOL_REVISION:
        raise ValueError("Stage 4B study type/revision mismatch")
    if tuple(hybrid.get("supported_topologies", ())) != TOPOLOGIES:
        raise ValueError("Stage 4B requires exactly D, P_D, D_P, and P_D_P")
    if tuple(int(value) for value in settings.get("seeds", ())) != SEEDS:
        raise ValueError("Stage 4B production seed set/order mismatch")
    if int(settings.get("budget", -1)) != BUDGET:
        raise ValueError("Stage 4B per-cell unique budget must be 24000")
    if int(settings.get("population_schedule_terminal_budget", -1)) != BUDGET:
        raise ValueError("Stage 4B terminal population schedule budget must be 24000")
    if tuple(int(value) for value in settings.get("checkpoints", ())) != CHECKPOINTS:
        raise ValueError("Stage 4B checkpoint lattice must be 4000/8000/16000/24000")
    if settings.get("initial_population") is not None:
        raise ValueError("Stage 4B initial population must use the dimension-scaled rule")
    if int(settings.get("initial_population_per_dimension", -1)) != INITIAL_POPULATION_MULTIPLIER:
        raise ValueError("Stage 4B initial population multiplier must be 18")
    if int(stage4b.get("initial_population_multiplier", -1)) != INITIAL_POPULATION_MULTIPLIER:
        raise ValueError("Stage 4B initializer contract must declare multiplier 18")
    if int(hybrid.get("common_grid_finalists", -1)) != FINALIST_COUNT:
        raise ValueError("Stage 4B requires validation of the top 16 candidates per checkpoint")
    if settings.get("cold_start") is not True:
        raise ValueError("Stage 4B requires independent cold starts")
    if (tuple(settings.get("selection", {}).get("materials", ())) != ("MLIT",)
            or tuple(settings.get("selection", {}).get("topologies", ())) != ("T1_SYMMETRIC_5IDT",)):
        raise ValueError("Stage 4B requires MLIT / T1_SYMMETRIC_5IDT only")
    if (float(hybrid.get("source_impedance_ohm", 0)) != 50.0
            or float(hybrid.get("load_impedance_ohm", 0)) != 50.0
            or float(settings.get("impedance_ohm", 0)) != 50.0):
        raise ValueError("Stage 4B requires fixed 50/50 ohm ports")
    if context["contract"].get("dms_topology") != "T1_SYMMETRIC_5IDT":
        raise ValueError("Stage 4B DMS topology mismatch")
    if len(context["search_frequencies"]) != 1001 or len(context["common_frequencies"]) != 9113:
        raise ValueError("Stage 4B requires the Stage 4A 1001/9113 frequency grids")
    if not context["common_grid_id"] or context["grid_metadata"].get("sha256") is None:
        raise ValueError("Stage 4B common-grid identity is incomplete")
    if (hybrid.get("initializer", {}).get("method") != "independent_uniform_rejection_v1"
            or hybrid.get("initializer", {}).get("include_historical_seed") is not False
            or hybrid.get("initializer", {}).get("seed_derivation")
            != "sha256(stage4b-v1/seed/material/topology/initial_population)"):
        raise ValueError("Stage 4B requires independent rejection initialization without historical seeds")
    if stage4b.get("production_authorized") is not None:
        raise ValueError("Production authorization must not be embedded in scientific config")

    baseline_path = root / "configs/studies/hybrid_stage4a_qualification.yaml"
    baseline = load_experiment_config(baseline_path)
    protected_equal = (
        cfg["spec"] == baseline["spec"],
        cfg["constraints"] == baseline["constraints"],
        cfg["dms_topology"]["materials"]["MLIT"] == baseline["dms_topology"]["materials"]["MLIT"],
        int(cfg["dms_topology"]["t1_reflector_electrodes"])
        == int(baseline["dms_topology"]["t1_reflector_electrodes"]),
        hybrid["resonator_bounds"] == baseline["hybrid"]["resonator_bounds"],
        hybrid["resonator_aperture_bounds_um"] == baseline["hybrid"]["resonator_aperture_bounds_um"],
        hybrid["resonator_model"] == baseline["hybrid"]["resonator_model"],
        hybrid["layout"] == baseline["hybrid"]["layout"],
        np.array_equal(np.asarray(RESONATOR_BOUNDS, dtype=float),
                       np.asarray(hybrid["resonator_bounds"], dtype=float)),
    )
    if not all(protected_equal):
        raise ValueError("Stage 4B config changed a protected Stage 4A model/specification/bounds contract")

    expected_dimensions = {"D": 10, "P_D": 13, "D_P": 13, "P_D_P": 16}
    if {name: space.dimension for name, space in context["spaces"].items()} != expected_dimensions:
        raise ValueError("Stage 4B topology dimensions do not match the qualified design space")
    for space in context["spaces"].values():
        if space.dimension != 10 + 3 * ((space.dimension - 10) // 3):
            raise ValueError("Stage 4B hybrid design-space dimension is inconsistent")

    contract = {
        "study_type": STUDY_TYPE,
        "protocol_revision": PROTOCOL_REVISION,
        "material": "MLIT",
        "dms_topology": "T1_SYMMETRIC_5IDT",
        "source_impedance_ohm": 50.0,
        "load_impedance_ohm": 50.0,
        "topologies": list(TOPOLOGIES),
        "seeds": list(SEEDS),
        "budget_per_cell": BUDGET,
        "population_schedule_terminal_budget": BUDGET,
        "checkpoints": list(CHECKPOINTS),
        "initial_population_rule": "18 * topology_dimension",
        "initial_populations": {name: 18 * dimension for name, dimension in expected_dimensions.items()},
        "cold_start": True,
        "warm_start": False,
        "parent_transfer": False,
        "topology_transfer": False,
        "historical_population_injection": False,
        "finalist_count_per_checkpoint": FINALIST_COUNT,
        "search_frequency_count": 1001,
        "search_frequency_sha256": context["contract"]["search_frequency_sha256"],
        "common_validation_grid_id": context["common_grid_id"],
        "common_validation_frequency_count": 9113,
        "common_validation_grid_sha256": context["grid_metadata"]["sha256"],
        "specification": cfg["spec"],
        "geometry_constraints": cfg["constraints"],
        "resonator_bounds": hybrid["resonator_bounds"],
        "resonator_aperture_bounds_um": hybrid["resonator_aperture_bounds_um"],
        "resonator_model": hybrid["resonator_model"],
        "com_provider": context["profile_metadata"],
        "network_convention": "Stage 4A; exp(+jωt), left-to-right, power-normalized acoustic waves",
        "matrix": _expected_matrix(),
    }
    base_paths = list(context["computation_paths"])
    base_paths.extend((
        "src/sawopt/studies/hybrid_stage4b.py",
        "src/sawopt/__main__.py",
        "src/sawopt/orchestration/cli.py",
        "src/sawopt/orchestration/models.py",
        "src/sawopt/orchestration/worker.py",
        "src/sawopt/orchestration/run_manager.py",
        "src/sawopt/orchestration/codex_callback.py",
    ))
    reporting_paths = (
        "src/sawopt/reporting/hybrid_stage4b.py",
        "src/sawopt/reporting/review_bundle.py",
    )
    fingerprint = build_fingerprint_metadata(
        root, contract,
        computation_paths=tuple(dict.fromkeys(base_paths)),
        reporting_paths=reporting_paths,
    )
    if fingerprint["fingerprint_schema_version"] != 2:
        raise ValueError("Stage 4B requires schema-v2 computation fingerprint")
    context.update({
        "contract": contract,
        "fingerprint": fingerprint,
        "computation_paths": tuple(dict.fromkeys(base_paths)),
        "reporting_paths": reporting_paths,
        "matrix": _expected_matrix(),
        "initial_populations": {name: 18 * dimension for name, dimension in expected_dimensions.items()},
        "authorization_scope": str(stage4b.get("production_authorization_scope", "")),
    })
    if context["authorization_scope"] != AUTHORIZATION_SCOPE:
        raise ValueError("Stage 4B authorization scope mismatch")
    return context


def build_authorization_metadata(
    context: Mapping[str, Any], *, source_commit_sha: str, run_id: str,
    authorized_at: str,
) -> dict[str, Any]:
    """Build immutable metadata for the user's one-shot production approval."""
    if not source_commit_sha or not run_id or not authorized_at:
        raise ValueError("Stage 4B authorization metadata requires source, run id, and timestamp")
    return {
        "study_type": STUDY_TYPE,
        "protocol_revision": PROTOCOL_REVISION,
        "fingerprint_schema_version": 2,
        "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
        "source_commit_sha": str(source_commit_sha),
        "user_authorized_production": True,
        "authorization_scope": AUTHORIZATION_SCOPE,
        "authorized_at": str(authorized_at),
        "run_id": str(run_id),
        "topologies": list(TOPOLOGIES),
        "seeds": list(SEEDS),
        "budget_per_cell": BUDGET,
        "population_schedule_terminal_budget": BUDGET,
        "checkpoints": list(CHECKPOINTS),
        "matrix": context["matrix"],
        "total_unique_evaluations": BUDGET * len(TOPOLOGIES) * len(SEEDS),
        "cold_start": True,
        "warm_start": False,
        "parent_transfer": False,
        "topology_transfer": False,
    }


def authorization_claim_id(metadata: Mapping[str, Any]) -> str:
    payload = "|".join((
        str(metadata.get("authorization_scope", "")),
        str(metadata.get("computation_fingerprint", "")),
        str(metadata.get("source_commit_sha", "")),
    ))
    if not all(payload.split("|")):
        raise ValueError("Stage 4B authorization claim key is incomplete")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_production_manifest(
    context: Mapping[str, Any], run_path: str | Path, authorization_manifest_path: str | Path,
) -> dict[str, Any]:
    """Fail closed unless the child is bound to the one-shot orchestration manifest."""
    from ..orchestration.models import RunManifest

    root = Path(context["root"]).resolve()
    run = Path(run_path).resolve()
    manifest_path = Path(authorization_manifest_path).resolve()
    raw = _read_json(manifest_path)
    manifest = RunManifest.from_dict(raw)
    metadata = manifest.experiment_metadata or {}
    source = _source_state(root)
    if source["status_short"]:
        raise RuntimeError("Stage 4B source tree is dirty; authorized source cannot be verified")
    expected_fields = {
        "study_type": STUDY_TYPE,
        "protocol_revision": PROTOCOL_REVISION,
        "fingerprint_schema_version": 2,
        "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
        "source_commit_sha": source["head"],
        "user_authorized_production": True,
        "authorization_scope": AUTHORIZATION_SCOPE,
        "topologies": list(TOPOLOGIES),
        "seeds": list(SEEDS),
        "budget_per_cell": BUDGET,
        "population_schedule_terminal_budget": BUDGET,
        "checkpoints": list(CHECKPOINTS),
        "matrix": context["matrix"],
        "total_unique_evaluations": BUDGET * len(TOPOLOGIES) * len(SEEDS),
        "cold_start": True,
        "warm_start": False,
        "parent_transfer": False,
        "topology_transfer": False,
    }
    if any(metadata.get(key) != value for key, value in expected_fields.items()):
        raise RuntimeError("Stage 4B authorization manifest/protocol fingerprint mismatch")
    if not metadata.get("authorized_at"):
        raise RuntimeError("Stage 4B authorization requires its authorization timestamp")
    if manifest.schema_version >= 4:
        if (manifest.continuation_mode != "queue" or manifest.codex_session_id is not None
                or manifest.callback_enabled or not manifest.review_after_completion
                or not manifest.original_thread_id):
            raise RuntimeError("Stage 4B schema-v4 authorization requires exact-thread queue handoff")
        if (manifest.queue_preflight or {}).get("status") != "PASS":
            raise RuntimeError("Stage 4B schema-v4 authorization lacks queue preflight")
    else:
        if not manifest.codex_session_id or not manifest.callback_enabled or not manifest.review_after_completion:
            raise RuntimeError("historical Stage 4B authorization requires its captured-session callback")
        callback_preflight = manifest.callback_preflight or {}
        if (callback_preflight.get("status") != "PASS"
                or callback_preflight.get("session_id") != manifest.codex_session_id
                or callback_preflight.get("validated_target_id") != manifest.codex_session_id):
            raise RuntimeError("historical Stage 4B authorization lacks a passing exact-session callback preflight")
    if manifest.run_id != metadata.get("run_id"):
        raise RuntimeError("Stage 4B authorization run id mismatch")
    if Path(manifest.config_path or "").resolve() != Path(context["config_path"]).resolve():
        raise RuntimeError("Stage 4B authorization config path mismatch")
    if Path(manifest.effective_optimizer_run_dir).resolve() != run:
        raise RuntimeError("Stage 4B authorization output path mismatch")
    if not run.is_relative_to(Path(manifest.run_dir).resolve()):
        raise RuntimeError("Stage 4B optimizer path escapes its orchestration run directory")
    claim_id = authorization_claim_id(metadata)
    claim_path = root / "runs" / ".stage4b_authorization_claims" / f"{claim_id}.json"
    if metadata.get("authorization_claim_id") != claim_id:
        raise RuntimeError("Stage 4B authorization claim identifier mismatch")
    if Path(str(metadata.get("authorization_claim_path", ""))).resolve() != claim_path.resolve():
        raise RuntimeError("Stage 4B authorization claim path mismatch")
    if Path(str(metadata.get("orchestration_run_dir", ""))).resolve() != Path(manifest.run_dir).resolve():
        raise RuntimeError("Stage 4B orchestration output path mismatch")
    if Path(str(metadata.get("optimizer_run_dir", ""))).resolve() != run:
        raise RuntimeError("Stage 4B optimizer output path metadata mismatch")
    if "--stage4b-authorization-manifest" not in manifest.command:
        raise RuntimeError("Stage 4B child command is not bound to its authorization manifest")
    command_index = manifest.command.index("--stage4b-authorization-manifest")
    if (command_index + 1 >= len(manifest.command)
            or Path(manifest.command[command_index + 1]).resolve() != manifest_path):
        raise RuntimeError("Stage 4B child command authorization manifest path mismatch")
    for flag, expected_path in (("--config", str(context["config_path"])), ("--run", str(run))):
        if flag not in manifest.command:
            raise RuntimeError(f"Stage 4B child command is missing {flag}")
        index = manifest.command.index(flag)
        if index + 1 >= len(manifest.command) or Path(manifest.command[index + 1]).resolve() != Path(expected_path).resolve():
            raise RuntimeError(f"Stage 4B child command {flag} path mismatch")
    if not claim_path.is_file():
        raise RuntimeError("Stage 4B one-shot authorization claim is missing")
    claim = _read_json(claim_path)
    if (claim.get("run_id") != manifest.run_id or claim.get("claim_id") != claim_id
            or claim.get("computation_fingerprint") != expected_fields["computation_fingerprint"]
            or claim.get("source_commit_sha") != source["head"]):
        raise RuntimeError("Stage 4B one-shot authorization claim does not match this run")
    return {
        "manifest": manifest,
        "metadata": metadata,
        "manifest_path": manifest_path,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "claim_id": claim_id,
        "claim_path": claim_path,
        "source_state": source,
    }


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
    from ..design.topology import RESONATOR_BOUNDS
    from ..optimization.counters import GeometryGateCounters, evaluation_status
    from ..optimizers.checkpoint_session import LShadeCheckpointSession
    from ..optimizers.lshade import LShadeBackend
    from ..optimizers.selection import GeometryFirstComparator

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


def _initialize_batch_run(run: Path, context: Mapping[str, Any], *, mode: str,
                          source_commit_sha: str, authorization: Mapping[str, Any] | None,
                          resume: bool) -> dict[str, Any]:
    manifest_path = run / "metadata" / "stage4b_run_manifest.json"
    if manifest_path.exists():
        saved = _read_json(manifest_path)
        matrix = context["matrix"] if mode == "production" else _expected_matrix(
            seeds=(SHAKEDOWN_SEED,), budget=SHAKEDOWN_BUDGET,
            checkpoints=SHAKEDOWN_CHECKPOINTS, terminal_budget=SHAKEDOWN_BUDGET,
        )
        expected = {
            "schema_version": 1,
            "protocol_revision": PROTOCOL_REVISION,
            "mode": mode,
            "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
            "reporting_fingerprint": context["fingerprint"]["reporting_fingerprint"],
            "source_commit_sha": source_commit_sha,
            "fingerprint_schema_version": 2,
            "contract": context["contract"],
            "matrix": matrix,
            "budget_per_cell": BUDGET if mode == "production" else SHAKEDOWN_BUDGET,
            "population_schedule_terminal_budget": BUDGET if mode == "production" else SHAKEDOWN_BUDGET,
            "checkpoints": list(CHECKPOINTS if mode == "production" else SHAKEDOWN_CHECKPOINTS),
            "seeds": list(SEEDS if mode == "production" else (SHAKEDOWN_SEED,)),
            "topologies": list(TOPOLOGIES),
            "initial_population_rule": "18 * dimension",
            "cold_start": True,
            "warm_start": False,
            "common_validation_grid_id": context["common_grid_id"],
            "common_validation_grid_sha256": context["grid_metadata"]["sha256"],
            "production_authorized": mode == "production",
            "user_authorized_production": mode == "production",
            "authorization_scope": AUTHORIZATION_SCOPE if mode == "production" else None,
            "user_authorized_at": (
                authorization["metadata"].get("authorized_at") if authorization is not None else None
            ),
            "ranking_eligibility": (
                "only-after-complete-20-cell-integrity-check" if mode == "production" else "never"
            ),
            "authorization_claim_id": authorization["claim_id"] if authorization is not None else None,
            "authorization_claim_path": (
                str(authorization["claim_path"].resolve()) if authorization is not None else None
            ),
            "orchestration_manifest_sha256": (
                authorization["manifest_sha256"] if authorization is not None else None
            ),
            "codex_session_id": (
                authorization["manifest"].codex_session_id if authorization is not None else None
            ),
            "callback_enabled": authorization is not None,
            "review_after_completion": authorization is not None,
        }
        if any(saved.get(key) != value for key, value in expected.items()):
            raise RuntimeError("existing Stage 4B run manifest fingerprint/source mismatch")
        if mode == "production":
            if (saved.get("authorization_claim_id") != authorization.get("claim_id")
                    or saved.get("orchestration_manifest_sha256") != authorization.get("manifest_sha256")):
                raise RuntimeError("existing Stage 4B run is bound to a different authorization manifest")
            snapshot = run / "metadata" / "orchestration_run_manifest.json"
            if (not snapshot.is_file()
                    or hashlib.sha256(snapshot.read_bytes()).hexdigest() != authorization["manifest_sha256"]):
                raise RuntimeError("saved orchestration manifest snapshot is missing or changed")
        return saved
    if resume:
        raise FileNotFoundError("cannot resume Stage 4B without its original run manifest")
    if run.exists() and any(run.iterdir()):
        raise FileExistsError(f"Stage 4B output directory is non-empty without a run manifest: {run}")
    payload = {
        "schema_version": 1,
        "protocol_revision": PROTOCOL_REVISION,
        "mode": mode,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha,
        "fingerprint_schema_version": 2,
        "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
        "reporting_fingerprint": context["fingerprint"]["reporting_fingerprint"],
        "contract": context["contract"],
        "matrix": context["matrix"] if mode == "production" else _expected_matrix(
            seeds=(SHAKEDOWN_SEED,), budget=SHAKEDOWN_BUDGET,
            checkpoints=SHAKEDOWN_CHECKPOINTS, terminal_budget=SHAKEDOWN_BUDGET,
        ),
        "budget_per_cell": BUDGET if mode == "production" else SHAKEDOWN_BUDGET,
        "population_schedule_terminal_budget": BUDGET if mode == "production" else SHAKEDOWN_BUDGET,
        "checkpoints": list(CHECKPOINTS if mode == "production" else SHAKEDOWN_CHECKPOINTS),
        "seeds": list(SEEDS if mode == "production" else (SHAKEDOWN_SEED,)),
        "topologies": list(TOPOLOGIES),
        "initial_population_rule": "18 * dimension",
        "cold_start": True,
        "warm_start": False,
        "common_validation_grid_id": context["common_grid_id"],
        "common_validation_grid_sha256": context["grid_metadata"]["sha256"],
        "production_authorized": mode == "production",
        "user_authorized_production": False if authorization is None else True,
        "authorization_scope": None if authorization is None else AUTHORIZATION_SCOPE,
        "user_authorized_at": None if authorization is None else authorization["metadata"].get("authorized_at"),
        "ranking_eligibility": "only-after-complete-20-cell-integrity-check" if mode == "production" else "never",
        "authorization_claim_id": None if authorization is None else authorization["claim_id"],
        "authorization_claim_path": None if authorization is None else str(authorization["claim_path"].resolve()),
        "orchestration_manifest_sha256": None if authorization is None else authorization["manifest_sha256"],
        "codex_session_id": None if authorization is None else authorization["manifest"].codex_session_id,
        "callback_enabled": False if authorization is None else True,
        "review_after_completion": False if authorization is None else True,
    }
    run.mkdir(parents=True, exist_ok=True)
    _atomic_json(run / "metadata" / "protocol_snapshot.json", context["contract"])
    if authorization is not None:
        authorized_manifest = Path(authorization["manifest_path"])
        if hashlib.sha256(authorized_manifest.read_bytes()).hexdigest() != authorization["manifest_sha256"]:
            raise RuntimeError("orchestration authorization manifest changed after preflight")
        (run / "metadata" / "orchestration_run_manifest.json").write_bytes(authorized_manifest.read_bytes())
    (run / "metadata" / "config_snapshot.yaml").write_text(
        context["config_path"].read_text(encoding="utf-8"), encoding="utf-8",
    )
    _atomic_json(manifest_path, payload)
    return payload


def run_stage4b_shakedown(
    config_path: str | Path, run_path: str | Path, *, resume: bool = False,
) -> dict[str, Any]:
    """Run a separate four-topology, 512-unique dispatch/resume shakedown."""
    context = load_stage4b_context(config_path)
    root = Path(context["root"])
    run = Path(run_path)
    if not run.is_absolute():
        run = root / run
    run = run.resolve()
    if "production" in run.name.casefold():
        raise ValueError("shakedown output path must be clearly separate from production")
    source = _source_state(root)
    run_started = time.perf_counter()
    _initialize_batch_run(run, context, mode="shakedown", source_commit_sha=source["head"],
                          authorization=None, resume=resume)
    results = []
    previously_completed = 0
    for topology in TOPOLOGIES:
        _, _, result_path = _cell_paths(run, topology, SHAKEDOWN_SEED)
        previously_completed += int(result_path.is_file())
        results.append(_run_cell(
            context, run, topology=topology, seed=SHAKEDOWN_SEED,
            budget=SHAKEDOWN_BUDGET, checkpoints=SHAKEDOWN_CHECKPOINTS,
            terminal_budget=SHAKEDOWN_BUDGET, finalist_count=FINALIST_COUNT,
            mode="shakedown", source_commit_sha=source["head"], resume=resume,
        ))
    from ..reporting.hybrid_stage4b import paired_comparisons, summarize_topologies

    topology_summaries = summarize_topologies(results)
    paired_rows = paired_comparisons(results, seed_labels=(SHAKEDOWN_SEED,))
    aggregation_path = run / "metadata" / "shakedown_aggregation.json"
    _atomic_json(aggregation_path, {
        "mode": "shakedown",
        "ranking_eligible": False,
        "topology_summaries": topology_summaries,
        "paired_seed_rows": paired_rows,
    })
    shakedown_manifest = _read_json(run / "metadata" / "stage4b_run_manifest.json")
    output_paths = []
    for topology in TOPOLOGIES:
        cell, cell_manifest, result_path = _cell_paths(run, topology, SHAKEDOWN_SEED)
        required = [
            cell_manifest, result_path, cell / "initializer.json",
            cell / "initialization_checkpoint.json",
            *(cell / f"B{point}.json" for point in SHAKEDOWN_CHECKPOINTS),
        ]
        output_paths.append(all(path.is_file() for path in required))
    checks = {
        "four_topologies": len(results) == 4 and {row["topology"] for row in results} == set(TOPOLOGIES),
        "512_unique_each": all(row.get("unique_evaluations") == SHAKEDOWN_BUDGET for row in results),
        "dimension_scaled_population": all(
            row.get("initial_population") == INITIAL_POPULATION_MULTIPLIER * row.get("dimension")
            for row in results
        ),
        "checkpoints_present": all(row.get("checkpoint_records") == list(SHAKEDOWN_CHECKPOINTS) for row in results),
        "cold_start": all(row.get("cold_start") is True and row.get("warm_start") is False for row in results),
        "common_grid_identical": all(
            row.get("common_validation_grid_id") == context["common_grid_id"] for row in results
        ),
        "resume_manifest_present": shakedown_manifest.get("source_commit_sha") == source["head"]
                                   and shakedown_manifest.get("computation_fingerprint")
                                   == context["fingerprint"]["computation_fingerprint"],
        "production_separation": shakedown_manifest.get("mode") == "shakedown"
                                 and shakedown_manifest.get("ranking_eligibility") == "never",
        "aggregation": len(topology_summaries) == 4 and len(paired_rows) == 6
                       and all(row.get("seed") == SHAKEDOWN_SEED for row in paired_rows),
        "output_paths": all(output_paths) and aggregation_path.is_file()
                        and (run / "metadata" / "protocol_snapshot.json").is_file()
                        and (run / "metadata" / "config_snapshot.yaml").is_file(),
    }
    if not all(checks.values()):
        raise RuntimeError(f"Stage 4B shakedown failed checks: {[key for key, value in checks.items() if not value]}")
    output = {"status": "PASS", "mode": "shakedown", "ranking_eligible": False,
              "checks": checks, "completed_cells_reused": previously_completed,
              "runtime_wall_time_s": float(time.perf_counter() - run_started),
              "resume_metadata": {"source_commit_sha": source["head"],
                                  "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
                                  "same_run_dir": str(run)},
              "topology_summaries": topology_summaries,
              "paired_seed_rows": paired_rows,
              "cells": results, "run_dir": str(run)}
    _atomic_json(run / "metadata" / "shakedown_summary.json", output)
    return output


def run_stage4b_production(
    config_path: str | Path, run_path: str | Path, authorization_manifest_path: str | Path,
) -> dict[str, Any]:
    """Run or resume only the 20 cells authorized by one immutable manifest."""
    context = load_stage4b_context(config_path)
    root = Path(context["root"])
    run = Path(run_path)
    if not run.is_absolute():
        run = root / run
    run = run.resolve()
    authorization = verify_production_manifest(context, run, authorization_manifest_path)
    source_sha = str(authorization["source_state"]["head"])
    _initialize_batch_run(run, context, mode="production", source_commit_sha=source_sha,
                          authorization=authorization, resume=(run / "metadata" / "stage4b_run_manifest.json").exists())
    results = []
    for item in context["matrix"]:
        results.append(_run_cell(
            context, run, topology=item["topology"], seed=item["seed"],
            budget=BUDGET, checkpoints=CHECKPOINTS,
            terminal_budget=BUDGET, finalist_count=FINALIST_COUNT,
            mode="production", source_commit_sha=source_sha, resume=True,
        ))
    from ..reporting.hybrid_stage4b import write_production_reports
    report = write_production_reports(run, context)
    return {"status": report["status"], "run_dir": str(run), "cells": results,
            "integrity": report["integrity"], "decision": report["decision"]}


__all__ = [
    "AUTHORIZATION_SCOPE", "BUDGET", "CHECKPOINTS", "FINALIST_COUNT",
    "INITIAL_POPULATION_MULTIPLIER", "PROTOCOL_REVISION", "SEEDS",
    "SHAKEDOWN_BUDGET", "SHAKEDOWN_CHECKPOINTS", "SHAKEDOWN_SEED",
    "STUDY_TYPE", "TOPOLOGIES", "authorization_claim_id",
    "build_authorization_metadata", "load_stage4b_context",
    "run_stage4b_production", "run_stage4b_shakedown",
    "verify_production_manifest",
    "write_atomic_json", "matched_cell_paths", "read_source_state",
    "run_matched_cell",
]

# Public, unchanged production primitives reused by the confirmatory adapter.
# The Stage 4B entry points and scientific protocol remain unchanged.
write_atomic_json = _atomic_json
matched_cell_paths = _cell_paths
read_source_state = _source_state
run_matched_cell = _run_cell
