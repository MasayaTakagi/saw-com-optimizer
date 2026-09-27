"""Current DMS topology screening protocol for T0, T1, and T2."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml

from ..core.metrics import geometry, measure, search_grid
from ..core.network import evaluate
from ..io.config import load_experiment_config
from ..io.serialization import save
from ..optimization.accounting import validate_checkpoint_lattice
from ..optimization.counters import GeometryGateCounters as EvaluationCounters
from ..optimization.counters import evaluation_status as _status
from ..optimization.population import (
    independent_uniform_candidate as _independent_uniform_candidate_primitive,
    sample_independent_uniform_population as _sample_independent_uniform_rejection_population,
)
from ..optimizers.lshade import LShadeBackend
from ..optimizers.selection import GeometryFirstComparator
from ..problem.dms_topologies import T0, T1, T2, TOPOLOGIES, simulate_topology
from ..reporting.review_bundle import write_review_bundle_archive
from .dms_topology_common import (
    MATERIALS, decode_design, fixed_design_sanity, implementation_validation,
    initial_design, provider_for_material,
)
from .lshade_records import lshade_record

ROOT = Path(__file__).resolve().parents[3]
STUDY_TYPE = "dms_topology_screening"
SEMANTICS_VERSION = "dms_topology_geometry_first_independent_rejection_v1"
DEFAULT_INITIAL_POPULATION_SEED_CONTRACT = "dms_topology_current_v1"
STAGE3_8C_R1_2_INITIAL_POPULATION_SEED_CONTRACT = "stage3_8c_r1_2_independent_rejection"
GEOMETRY_CONSTRAINT_NAMES = (
    "max_total_acoustic_length", "max_aperture_width", "minimum_electrode_width",
    "minimum_electrode_gap", "max_total_electrode_count",
)
RF_METRIC_KEYS = (
    "worst_il_db", "ripple_db", "input_vswr", "output_vswr",
    "source_return_loss_db_min", "load_return_loss_db_min", "stop_attenuation_db",
)
EXPECTED_PHYSICS_ERRORS = (ValueError, np.linalg.LinAlgError, FloatingPointError, OverflowError)
GEOMETRY_FIRST_COMPARATOR = GeometryFirstComparator()


@dataclass(frozen=True)
class InitialPopulationSeedContract:
    identifier: str
    namespace: str
    derivation_suffix: str


_INITIAL_POPULATION_SEED_CONTRACTS = {
    DEFAULT_INITIAL_POPULATION_SEED_CONTRACT: InitialPopulationSeedContract(
        DEFAULT_INITIAL_POPULATION_SEED_CONTRACT,
        SEMANTICS_VERSION,
        "independent_rejection",
    ),
    STAGE3_8C_R1_2_INITIAL_POPULATION_SEED_CONTRACT: InitialPopulationSeedContract(
        STAGE3_8C_R1_2_INITIAL_POPULATION_SEED_CONTRACT,
        "stage3_8c_r1_geometry_first_v1",
        "r1_2_independent_rejection",
    ),
}


def resolve_initial_population_seed_contract(
    cfg: Mapping[str, Any],
) -> InitialPopulationSeedContract:
    """Resolve a named, explicit initializer RNG contract; absent means current behavior."""
    identifier = cfg.get("dms_topology", {}).get(
        "initial_population_seed_contract", DEFAULT_INITIAL_POPULATION_SEED_CONTRACT,
    )
    try:
        return _INITIAL_POPULATION_SEED_CONTRACTS[identifier]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"unknown initial population seed contract: {identifier!r}") from exc


def initial_population_sampling_seed(
    cfg: Mapping[str, Any], seed: int, material: str, topology: str,
) -> int:
    """Derive the initializer-only RNG seed from the configured immutable contract."""
    contract = resolve_initial_population_seed_contract(cfg)
    payload = (
        f"{contract.namespace}/{contract.derivation_suffix}/{seed}/{material}/{topology}/initial_population"
    )
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big") % (2**32)


def _backend_config(cfg: Mapping[str, Any], topology: str, budget: int,
                    hard_bounds: np.ndarray) -> dict[str, Any]:
    section = cfg["dms_topology"]["topologies"][topology]
    values = dict(cfg.get("dms_topology", {}).get("lshade", {}))
    schedule_horizon = int(cfg["dms_topology"].get(
        "population_schedule_terminal_budget", budget,
    ))
    if schedule_horizon <= 0 or schedule_horizon > int(budget):
        raise ValueError("population schedule horizon must be positive and no greater than budget")
    configured_population = cfg["dms_topology"].get("initial_population")
    if configured_population is None:
        configured_population = (
            int(cfg["dms_topology"].get("initial_population_per_dimension", 18))
            * int(len(hard_bounds))
        )
    values.update({
        "total_budget": int(budget),
        "hard_max_budget": int(budget),
        "population_schedule_terminal_budget": schedule_horizon,
        "initial_population": max(4, int(configured_population)),
        "hard_bounds": np.asarray(hard_bounds, dtype=float).tolist(),
    })
    values.update(section.get("lshade", {}))
    effective_horizon = int(values["population_schedule_terminal_budget"])
    if effective_horizon <= 0 or effective_horizon > int(budget):
        raise ValueError("effective L-SHADE schedule horizon must be positive and no greater than budget")
    return values


def _selected_study_axes(cfg: Mapping[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Resolve an optional validated material/topology subset for this run."""
    settings = cfg["dms_topology"]
    selection = settings.get("selection", {})
    if not isinstance(selection, Mapping):
        raise ValueError("dms_topology.selection must be a mapping")
    unknown_axes = set(selection) - {"materials", "topologies"}
    if unknown_axes:
        raise ValueError(f"unknown dms_topology.selection keys: {sorted(unknown_axes)}")

    def resolve(name: str, configured: Sequence[str], available: Sequence[str],
                configured_map: Mapping[str, Any]) -> tuple[str, ...]:
        requested = selection.get(name)
        if requested is None:
            selected = tuple(configured)
        else:
            if isinstance(requested, (str, bytes)) or not isinstance(requested, Sequence):
                raise ValueError(f"dms_topology.selection.{name} must be a non-empty list")
            selected = tuple(str(value) for value in requested)
        if not selected:
            raise ValueError(f"dms_topology.selection.{name} must not be empty")
        if len(selected) != len(set(selected)):
            raise ValueError(f"dms_topology.selection.{name} contains duplicates")
        unknown = [value for value in selected if value not in available]
        if unknown:
            raise ValueError(f"unknown {name}: {unknown}")
        missing = [value for value in selected if value not in configured_map]
        if missing:
            raise ValueError(f"selected {name} missing from dms_topology configuration: {missing}")
        return selected

    materials = resolve("materials", MATERIALS, MATERIALS, settings.get("materials", {}))
    topologies = resolve("topologies", TOPOLOGIES, TOPOLOGIES, settings.get("topologies", {}))
    return materials, topologies


def _load_common_grid(cfg: Mapping[str, Any]) -> tuple[np.ndarray, str, str, dict[str, Any]]:
    metadata_path = ROOT / cfg["dms_topology"]["common_validation_grid_metadata"]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    grid_path = Path(metadata["source"])
    if not grid_path.is_absolute():
        grid_path = ROOT / grid_path
    # Git stores this reference CSV with LF endings; normalize CRLF worktrees
    # before checking the content hash so Windows and Linux validate the same
    # immutable bytes.
    grid_bytes = grid_path.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(grid_bytes).hexdigest() != metadata["sha256"]:
        raise ValueError("common validation grid file hash does not match its metadata")
    grid = np.loadtxt(grid_path, delimiter=",", skiprows=1).astype(float)
    grid_id = hashlib.sha256(np.asarray(grid, dtype="<f8").tobytes()).hexdigest()
    if grid_id != metadata["grid_id"]:
        raise ValueError(f"validation-grid identity mismatch: {grid_id} != {metadata['grid_id']}")
    return grid, grid_id, str(metadata_path), metadata


def _source_fingerprint(raw_config: str, grid_id: str) -> str:
    digest = hashlib.sha256()
    digest.update(raw_config.encode("utf-8"))
    digest.update(SEMANTICS_VERSION.encode("utf-8"))
    digest.update(grid_id.encode("ascii"))
    for path in (
        Path(__file__),
        Path(__file__).with_name("dms_topology_common.py"),
        ROOT / "src" / "sawopt" / "problem" / "dms_topologies.py",
        ROOT / "src" / "sawopt" / "problem" / "released_dms.py",
        ROOT / "src" / "sawopt" / "studies" / "lshade_records.py",
    ):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _git_state() -> dict[str, str]:
    def run(*args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False,
        )
        return result.stdout.strip()

    return {
        "branch": run("branch", "--show-current"),
        "head": run("rev-parse", "HEAD"),
        "status": run("status", "--short"),
    }



def _finite(value: Any, default: float = math.inf) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    return number if math.isfinite(number) else float(default)

def _clean(value: Any):
    if isinstance(value, np.ndarray):
        return [_clean(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _clean(value.item())
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_clean(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value

def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clean(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    columns = list(dict.fromkeys(key for row in rows for key in row))
    if not columns:
        columns = {
            "dms_topology_geometry_rejections.csv": [
                "material", "topology", "seed", "evaluation_status", "failure_stage",
                "design", "geometry_dimensions", "violated_hard_constraints",
                "normalized_geometry_violations",
            ],
            "dms_topology_validated_responses.csv": [
                "material", "topology", "seed", "frequency_hz", "s11_db", "s21_db",
            ],
        }.get(path.name, ["status"])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns or ["status"])
        writer.writeheader()
        writer.writerows([{key: _clean(value) for key, value in row.items()} for row in rows])

def _design_vector(design: Any, topology: str) -> np.ndarray:
    names = {
        T0: ("wavelength_um", "io_idt_pairs", "center_idt_pairs", "reflector_electrodes",
             "idt_gap_lambda", "reflector_gap_lambda", "aperture_um", "center_wavelength_um",
             "reflector_wavelength_um"),
        T1: ("wavelength_A_um", "wavelength_B_um", "wavelength_C_um",
             "reflector_wavelength_um", "pairs_A", "pairs_B", "pairs_C",
             "common_idt_gap_lambda", "reflector_gap_lambda", "aperture_um"),
        T2: ("track_A_main_wavelength_um", "track_B_main_wavelength_um", "io_idt_pairs",
             "center_idt_pairs", "reflector_electrodes", "idt_gap_lambda",
             "reflector_gap_lambda", "center_wavelength_ratio", "reflector_wavelength_ratio",
             "total_aperture_um"),
    }[topology]
    values = [getattr(design, name) for name in names]
    if topology == T0:
        values[7] = design.center_wavelength_um or design.wavelength_um
        values[8] = design.reflector_wavelength_um or design.wavelength_um
    return np.asarray(values, dtype=float)

def _aperture_index(topology: str) -> int:
    return {T0: 6, T1: 9, T2: 9}[topology]

def material_bounds(cfg: Mapping[str, Any], material: str, topology: str):
    """Resolve topology search bounds with the declared material aperture range."""
    section = cfg["dms_topology"]["topologies"][topology]
    active = np.asarray(section["bounds"]["active"], dtype=float).copy()
    hard = np.asarray(section["bounds"].get("hard", section["bounds"]["active"]), dtype=float).copy()
    low, high = map(float, cfg["dms_topology"]["materials"][material]["aperture_bounds_um"])
    index = _aperture_index(topology)
    active[index] = (low, high)
    if high > hard[index, 1]:
        raise ValueError(f"{material}/{topology} aperture active bound exceeds optimizer hard bound")
    if np.any(active[:, 0] < hard[:, 0]) or np.any(active[:, 1] > hard[:, 1]):
        raise ValueError(f"active bounds for {material}/{topology} exceed optimizer hard bounds")
    integer_indices = tuple(int(value) for value in section.get("integer_indices", []))
    return active, hard, integer_indices

def _canonical_physical(vector: Sequence[float], active: np.ndarray,
                        integer_indices: Sequence[int]) -> np.ndarray:
    physical = np.asarray(vector, dtype=float).copy()
    for index in integer_indices:
        physical[index] = np.floor(physical[index] + 0.5)
    return np.clip(physical, active[:, 0], active[:, 1])

def _variable_names(topology: str) -> tuple[str, ...]:
    return {
        T0: ("wavelength_um", "io_idt_pairs", "center_idt_pairs", "reflector_electrodes",
             "idt_gap_lambda", "reflector_gap_lambda", "aperture_um", "center_wavelength_um",
             "reflector_wavelength_um"),
        T1: ("wavelength_A_um", "wavelength_B_um", "wavelength_C_um",
             "reflector_wavelength_um", "pairs_A", "pairs_B", "pairs_C",
             "common_idt_gap_lambda", "reflector_gap_lambda", "aperture_um"),
        T2: ("track_A_main_wavelength_um", "track_B_main_wavelength_um", "io_idt_pairs",
             "center_idt_pairs", "reflector_electrodes", "idt_gap_lambda",
             "reflector_gap_lambda", "center_wavelength_ratio", "reflector_wavelength_ratio",
             "total_aperture_um"),
    }[topology]

def _distribution_summary(values: Sequence[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    quantiles = np.quantile(array, [0.05, 0.25, 0.5, 0.75, 0.95])
    return {
        "count": int(len(array)),
        "min": float(np.min(array)),
        "q05": float(quantiles[0]),
        "q25": float(quantiles[1]),
        "median": float(quantiles[2]),
        "q75": float(quantiles[3]),
        "q95": float(quantiles[4]),
        "max": float(np.max(array)),
        "mean": float(np.mean(array)),
        "std": float(np.std(array, ddof=0)),
    }

def _independent_uniform_candidate(
    rng: np.random.Generator, low: np.ndarray, high: np.ndarray,
    integer_indices: Sequence[int],
) -> np.ndarray:
    """Make one current-compatible independent real-uniform proposal and canonicalize it."""
    return _independent_uniform_candidate_primitive(
        rng, low, high, integer_indices, _canonical_physical,
    )

def _geometry_population_metrics(
    physical_population: np.ndarray, cfg: Mapping[str, Any], topology: str,
) -> dict[str, np.ndarray]:
    dimensions = []
    for vector in physical_population:
        design = decode_design(vector, topology, cfg)
        dims, violations = geometry(design, cfg["constraints"])
        if not np.isfinite(list(dims.values())).all() or max(violations, default=0.0) > 0.0:
            raise AssertionError("initializer distribution contains invalid geometry")
        dimensions.append(dims)
    return {
        "length_um": np.asarray([row["length_um"] for row in dimensions], dtype=float),
        "width_um": np.asarray([row["width_um"] for row in dimensions], dtype=float),
        "electrodes": np.asarray([row["electrodes"] for row in dimensions], dtype=float),
    }

def _ks_distance(left: Sequence[float], right: Sequence[float]) -> float:
    a = np.sort(np.asarray(left, dtype=float))
    b = np.sort(np.asarray(right, dtype=float))
    support = np.unique(np.concatenate((a, b)))
    return float(np.max(np.abs(np.searchsorted(a, support, side="right") / len(a)
                               - np.searchsorted(b, support, side="right") / len(b))))

def _uniform_geometry_reference(
    cfg: Mapping[str, Any], material: str, topology: str, *, active: np.ndarray,
    integer_indices: Sequence[int], seed: int, proposals: int,
) -> tuple[dict[str, Any], np.ndarray, dict[str, np.ndarray]]:
    """Draw a separate COM-free iid proposal stream for distribution validation."""
    if proposals < 1:
        raise ValueError("initializer reference proposal count must be positive")
    rng = np.random.default_rng(seed)
    low, high = active[:, 0], active[:, 1]
    reasons = {name: 0 for name in GEOMETRY_CONSTRAINT_NAMES}
    accepted: list[np.ndarray] = []
    started = time.perf_counter()
    for _ in range(proposals):
        candidate = _independent_uniform_candidate(rng, low, high, integer_indices)
        dims, violations, maximum = _geometry_status(decode_design(candidate, topology, cfg), cfg)
        if math.isfinite(maximum) and maximum <= 0.0:
            accepted.append(candidate)
        else:
            for name, value in violations.items():
                if value > 0.0:
                    reasons[name] += 1
    if not accepted:
        raise RuntimeError(f"independent-uniform reference accepted no designs for {material}/{topology}")
    physical = np.asarray(accepted, dtype=float)
    metrics = _geometry_population_metrics(physical, cfg, topology)
    names = _variable_names(topology)
    distributions = {
        name: _distribution_summary(physical[:, index])
        for index, name in enumerate(names)
    }
    distributions.update({name: _distribution_summary(values) for name, values in metrics.items()})
    rejected = proposals - len(accepted)
    return ({
        "method": "independent_uniform_geometry_rejection_mc",
        "seed": int(seed),
        "candidate_draws": int(proposals),
        "geometry_valid_candidates": int(len(accepted)),
        "geometry_rejections": int(rejected),
        "geometry_rejection_fraction": float(rejected / proposals),
        "attempts_per_geometry_valid_candidate": float(proposals / len(accepted)),
        "rejection_reason_counts": reasons,
        "population_generation_time_s": float(time.perf_counter() - started),
        "variable_and_geometry_distributions": distributions,
    }, physical, metrics)

def _distribution_validation(
    sample: np.ndarray, reference: np.ndarray, sample_metrics: Mapping[str, np.ndarray],
    reference_metrics: Mapping[str, np.ndarray], integer_indices: Sequence[int],
    *, seed: int, bootstrap_replicates: int = 256,
) -> dict[str, Any]:
    """Check marginal ECDF distances against a reference-derived max-KS envelope."""
    if len(sample) < 2 or len(reference) < len(sample):
        raise ValueError("distribution validation requires >=2 sample points and a larger reference")
    actual_columns: dict[str, np.ndarray] = {
        f"variable_{index}": sample[:, index] for index in range(sample.shape[1])
    }
    reference_columns: dict[str, np.ndarray] = {
        f"variable_{index}": reference[:, index] for index in range(reference.shape[1])
    }
    actual_columns.update({f"geometry_{name}": np.asarray(values) for name, values in sample_metrics.items()
                           if name in {"length_um", "electrodes"}})
    reference_columns.update({f"geometry_{name}": np.asarray(values) for name, values in reference_metrics.items()
                              if name in {"length_um", "electrodes"}})
    distances = {
        name: _ks_distance(actual_columns[name], reference_columns[name])
        for name in actual_columns
    }
    observed_max = max(distances.values())
    rng = np.random.default_rng(seed)
    reference_max_distances = []
    n_reference = len(reference)
    sample_size = len(sample)
    for _ in range(bootstrap_replicates):
        indices = rng.integers(0, n_reference, size=sample_size)
        reference_max_distances.append(max(
            _ks_distance(reference_columns[name][indices], reference_columns[name])
            for name in reference_columns
        ))
    q99 = float(np.quantile(reference_max_distances, 0.99))

    # Distinct count tuples and marginal support are checked against the lower
    # 1% reference-bootstrap envelope; this is a gate, not candidate repair.
    def count_diversity(vectors: np.ndarray) -> dict[str, int]:
        if not integer_indices:
            return {"unique_integer_tuples": 0}
        tuples = {tuple(int(round(vector[index])) for index in integer_indices) for vector in vectors}
        result = {"unique_integer_tuples": len(tuples)}
        result.update({f"unique_integer_values_{index}": int(np.unique(vectors[:, index]).size)
                       for index in integer_indices})
        return result

    sample_diversity = count_diversity(sample)
    ref_diversity = count_diversity(reference)
    diversity_rng = np.random.default_rng((seed ^ 0xA11CE55) % (2**32))
    bootstrap_diversity: dict[str, list[int]] = {name: [] for name in ref_diversity}
    for _ in range(bootstrap_replicates):
        indices = diversity_rng.integers(0, n_reference, size=sample_size)
        stats = count_diversity(reference[indices])
        for name, value in stats.items():
            bootstrap_diversity[name].append(value)
    diversity_minimums = {
        name: int(math.floor(np.quantile(values, 0.01)))
        for name, values in bootstrap_diversity.items()
    }
    diversity_pass = all(sample_diversity[name] >= minimum
                         for name, minimum in diversity_minimums.items())
    return {
        "method": "independent_geometry_reference_max_marginal_ks_bootstrap",
        "seed": int(seed),
        "bootstrap_replicates": int(bootstrap_replicates),
        "reference_sample_count": int(n_reference),
        "initializer_random_sample_count": int(sample_size),
        "marginal_ks_distances": distances,
        "max_marginal_ks_distance": float(observed_max),
        "max_marginal_ks_reference_q99": q99,
        "distribution_match_passed": bool(observed_max <= q99),
        "initializer_integer_diversity": sample_diversity,
        "reference_integer_diversity": ref_diversity,
        "integer_diversity_q01_minimums": diversity_minimums,
        "integer_diversity_passed": bool(diversity_pass),
    }

def sample_independent_uniform_population(
    cfg: Mapping[str, Any], material: str, topology: str, *, seed: int,
    population_size: int, max_attempts: int, reference_proposals: int = 10000,
    bootstrap_replicates: int = 256, rng_seed_override: int | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Build a unique geometry-valid population by current independent rejection sampling."""
    if population_size < 1 or max_attempts < 0:
        raise ValueError("population_size must be positive and max_attempts non-negative")
    active, hard, integer_indices = material_bounds(cfg, material, topology)
    low, high = active[:, 0], active[:, 1]
    fixed = initial_design(material, topology, cfg)
    fixed_physical = _design_vector(fixed, topology)
    fixed_canonical = _canonical_physical(fixed_physical, active, integer_indices)
    if not np.allclose(fixed_physical, fixed_canonical, rtol=0.0, atol=1e-10):
        raise ValueError(f"known fixed seed for {material}/{topology} is not canonical")
    if np.any(fixed_canonical < hard[:, 0]) or np.any(fixed_canonical > hard[:, 1]):
        raise ValueError(f"known fixed seed for {material}/{topology} is outside optimizer hard bounds")
    if not np.allclose(_design_vector(decode_design(fixed_canonical, topology, cfg), topology),
                       fixed_physical, rtol=0.0, atol=1e-10):
        raise ValueError(f"known fixed seed for {material}/{topology} fails canonical round-trip")
    if max(geometry(fixed, cfg["constraints"])[1], default=0.0) > 0.0:
        raise ValueError(f"known fixed seed for {material}/{topology} violates geometry")

    seed_contract = resolve_initial_population_seed_contract(cfg)
    rng_seed = (
        int(rng_seed_override) if rng_seed_override is not None
        else initial_population_sampling_seed(cfg, seed, material, topology)
    )
    rng = np.random.default_rng(rng_seed)
    started = time.perf_counter()
    (
        physical_population,
        random_population,
        draws,
        geometry_rejections,
        duplicate_rejections,
        reasons,
    ) = _sample_independent_uniform_rejection_population(
        rng=rng,
        low=low,
        high=high,
        integer_indices=integer_indices,
        first_candidate=fixed_canonical,
        population_size=population_size,
        max_attempts=max_attempts,
        reason_names=GEOMETRY_CONSTRAINT_NAMES,
        candidate_proposer=_independent_uniform_candidate,
        geometry_check=lambda candidate: _geometry_status(
            decode_design(candidate, topology, cfg), cfg,
        ),
    )
    generation_time = float(time.perf_counter() - started)
    accepted_random = len(random_population)
    base_stats: dict[str, Any] = {
        "initializer_method": "independent_uniform_rejection_v1",
        "requested_population_size": int(population_size),
        "max_attempts": int(max_attempts),
        "max_attempts_exceeded": bool(len(physical_population) != population_size),
        "total_candidate_draws": int(draws),
        "valid_accepted_candidates": int(len(physical_population)),
        "geometry_valid_members": int(len(physical_population)),
        "rejected_candidates": int(geometry_rejections + duplicate_rejections),
        "geometry_rejection_fraction": float(geometry_rejections / draws) if draws else 0.0,
        "total_candidate_rejection_fraction": float((geometry_rejections + duplicate_rejections) / draws) if draws else 0.0,
        "attempts_per_random_accept": float(draws / accepted_random) if accepted_random else math.inf,
        "fixed_seed_count": 1,
        "initial_sampling_seed": int(rng_seed),
        "initial_sampling_seed_contract_id": seed_contract.identifier,
        "initial_sampling_seed_namespace": seed_contract.namespace,
        "initial_sampling_seed_derivation_suffix": seed_contract.derivation_suffix,
        "initial_sampling_draws": int(draws),
        "initial_sampling_geometry_rejections": int(geometry_rejections),
        "initial_sampling_duplicate_rejections": int(duplicate_rejections),
        "initial_sampling_rejection_reason_counts": reasons,
        "random_initial_accepts": int(accepted_random),
        "unique_population_count": len(physical_population),
        "population_generation_time_s": generation_time,
        "geometry_rejection_fraction_is_diagnostic_only": True,
    }
    if draws != geometry_rejections + duplicate_rejections + accepted_random:
        raise AssertionError("current initializer attempt accounting identity failed")
    if len(physical_population) != population_size:
        base_stats["failure_code"] = "INITIALIZER_EXHAUSTED"
        raise InitializerExhausted(base_stats)

    physical_array = np.asarray(physical_population, dtype=float)
    random_array = np.asarray(random_population, dtype=float)
    if np.any(physical_array < low) or np.any(physical_array > high):
        raise AssertionError("current initializer emitted a design outside the declared bounds")
    unique_count = len({tuple(float(value) for value in row) for row in physical_array})
    if unique_count != population_size:
        raise AssertionError("current initializer emitted duplicate canonical designs")
    full_metrics = _geometry_population_metrics(physical_array, cfg, topology)
    random_metrics = _geometry_population_metrics(random_array, cfg, topology)
    names = _variable_names(topology)
    base_stats["variable_distributions"] = {
        name: _distribution_summary(physical_array[:, index])
        for index, name in enumerate(names)
    }
    base_stats["geometry_metric_distributions"] = {
        name: _distribution_summary(values) for name, values in full_metrics.items()
    }
    base_stats["random_member_variable_distributions"] = {
        name: _distribution_summary(random_array[:, index])
        for index, name in enumerate(names)
    }
    base_stats["random_member_geometry_metric_distributions"] = {
        name: _distribution_summary(values) for name, values in random_metrics.items()
    }

    if reference_proposals > 0:
        reference_seed = (rng_seed ^ 0x6D2B79F5) % (2**32)
        reference, reference_array, reference_metrics = _uniform_geometry_reference(
            cfg, material, topology, active=active, integer_indices=integer_indices,
            seed=reference_seed, proposals=reference_proposals,
        )
        validation_seed = (rng_seed ^ 0x35A1C7E9) % (2**32)
        validation = _distribution_validation(
            random_array, reference_array, random_metrics, reference_metrics,
            integer_indices, seed=validation_seed, bootstrap_replicates=bootstrap_replicates,
        )
        base_stats["independent_uniform_reference"] = reference
        base_stats["distribution_validation"] = validation
        base_stats["integer_diversity_diagnostic_passed"] = validation["integer_diversity_passed"]
        base_stats["distribution_reference_check_passed"] = validation["distribution_match_passed"]
    else:
        base_stats["integer_diversity_diagnostic_passed"] = True
        base_stats["distribution_reference_check_passed"] = True
    if draws != geometry_rejections + duplicate_rejections + accepted_random:
        raise AssertionError("current initializer attempt accounting identity failed")
    normalized = (physical_array - low) / (high - low)
    if not np.isfinite(normalized).all() or np.any(normalized < 0.0) or np.any(normalized > 1.0):
        raise AssertionError("current initializer emitted a normalized vector outside [0, 1]")
    return normalized, base_stats

def _geometry_status(design: Any, cfg: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, float], float]:
    dims, values = geometry(design, cfg["constraints"])
    values = [float(value) for value in values]
    if len(values) != len(GEOMETRY_CONSTRAINT_NAMES):
        raise ValueError(f"expected five geometry constraints, received {len(values)}")
    detail = {name: value for name, value in zip(GEOMETRY_CONSTRAINT_NAMES, values)}
    return {key: float(value) for key, value in dims.items()}, detail, max(values, default=0.0)

def _finite_filter_outputs(record: Mapping[str, Any]) -> bool:
    metrics = record.get("metrics", {})
    violations = record.get("violations", {})
    if not all(key in metrics for key in RF_METRIC_KEYS):
        return False
    metric_values = [metrics[key] for key in RF_METRIC_KEYS]
    flattened = [float(item) for value in metric_values
                 for item in (value if isinstance(value, (list, tuple, np.ndarray)) else [value])]
    violation_values = [float(value) for value in violations.values()]
    return bool(
        flattened and np.isfinite(flattened).all()
        and violation_values and np.isfinite(violation_values).all()
        and math.isfinite(float(record.get("objective", math.inf)))
        and math.isfinite(float(record.get("max_violation", math.inf)))
        and math.isfinite(float(record.get("sum_violation", math.inf)))
    )

def evaluate_dms_design(
    design: Any, provider: Any, cfg: Mapping[str, Any], frequencies_hz: np.ndarray,
    topology: str, *, rs: float = 50.0, rl: float = 50.0, include_spectrum: bool = False,
) -> dict[str, Any]:
    """Gate geometry before running the DMS COM, network, and metric evaluation."""
    try:
        dims, geometry_violations, maximum = _geometry_status(design, cfg)
    except (ValueError, FloatingPointError, OverflowError) as exc:
        dims = {}
        geometry_violations = {"geometry_evaluation_failure": math.inf}
        maximum = math.inf
        return {
            "evaluation_status": "GEOMETRY_REJECTED",
            "failure_stage": "geometry_evaluation",
            "failure": str(exc),
            "geometry_valid": False,
            "geometry_dimensions": dims,
            "geometry_violations": geometry_violations,
            "geometry_max_violation": maximum,
            "metrics": {},
            "violations": {},
            "filter_metrics_available": False,
            "feasible": False,
            "max_violation": None,
            "sum_violation": None,
            "objective": None,
            "design": asdict(design),
            "topology": topology,
        }
    if not math.isfinite(maximum) or maximum > 0:
        return {
            "evaluation_status": "GEOMETRY_REJECTED",
            "failure_stage": "hard_geometry_gate",
            "geometry_valid": False,
            "geometry_dimensions": dims,
            "geometry_violations": geometry_violations,
            "geometry_max_violation": maximum,
            "metrics": {},
            "violations": {},
            "filter_metrics_available": False,
            "feasible": False,
            "max_violation": None,
            "sum_violation": None,
            "objective": None,
            "design": asdict(design),
            "topology": topology,
        }

    try:
        simulation = simulate_topology(design, provider, frequencies_hz, topology)
        network = evaluate(simulation.y_parameters, rs, rl)
        if not np.isfinite(np.asarray(network["gt"], dtype=float)).all():
            raise ValueError("non-finite transducer power gain")
        if np.asarray(network["gt"], dtype=float).max() > 1.0 + 1e-7:
            raise ValueError("Nonpassive power gain")
        raw = dict(measure(np.asarray(frequencies_hz), network, design, cfg))
        all_violations = dict(raw.get("violations", {}))
        filter_violations = {
            str(key): float(value) for key, value in all_violations.items() if key != "geometry"
        }
        metrics = dict(raw.get("metrics", {}))
        for key in ("length_um", "width_um", "electrodes"):
            metrics.pop(key, None)
        result = {
            "evaluation_status": "PHYSICS_EVALUATED",
            "failure_stage": None,
            "geometry_valid": True,
            "geometry_dimensions": dims,
            "geometry_violations": geometry_violations,
            "geometry_max_violation": 0.0,
            "metrics": metrics,
            "violations": filter_violations,
            "filter_metrics_available": True,
            "filter_feasible": max(filter_violations.values(), default=math.inf) <= 1e-10,
            "feasible": max(filter_violations.values(), default=math.inf) <= 1e-10,
            "max_violation": max(filter_violations.values(), default=math.inf),
            "sum_violation": sum(filter_violations.values()),
            "objective": float(raw["objective"]),
            "objective_parts": raw.get("objective_parts", {}),
            "design": asdict(design),
            "topology": topology,
            "source_impedance_ohm": float(rs),
            "load_impedance_ohm": float(rl),
            "diagnostics": simulation.diagnostics,
        }
        if not _finite_filter_outputs(result):
            raise ValueError("non-finite or incomplete filter metrics/violations")
        if include_spectrum:
            scattering = np.asarray(network["s"])
            with np.errstate(divide="ignore", invalid="ignore"):
                result["spectrum"] = {
                    "frequency_hz": np.asarray(frequencies_hz, dtype=float).tolist(),
                    "s11_db": (20 * np.log10(np.maximum(np.abs(scattering[:, 0, 0]), 1e-300))).tolist(),
                    "s21_db": (20 * np.log10(np.maximum(np.abs(scattering[:, 1, 0]), 1e-300))).tolist(),
                }
        return result
    except EXPECTED_PHYSICS_ERRORS as exc:
        return {
            "evaluation_status": "PHYSICS_FAILED",
            "failure_stage": "com_network_or_metrics",
            "failure": f"{type(exc).__name__}: {exc}",
            "geometry_valid": True,
            "geometry_dimensions": dims,
            "geometry_violations": geometry_violations,
            "geometry_max_violation": 0.0,
            "metrics": {},
            "violations": {},
            "filter_metrics_available": False,
            "filter_feasible": False,
            "feasible": False,
            "max_violation": None,
            "sum_violation": None,
            "objective": None,
            "design": asdict(design),
            "topology": topology,
        }

def _assert_counter_invariants(counters: EvaluationCounters, unique: int, search_frequency_count: int):
    if unique != counters.geometry_rejections + counters.geometry_valid_candidates:
        raise AssertionError("unique evaluation geometry partition failed")
    if counters.geometry_valid_candidates != (
        counters.valid_physics_evaluations + counters.physics_failures
    ):
        raise AssertionError("geometry-valid candidate counter partition failed")
    if counters.valid_physics_evaluations > counters.geometry_valid_candidates:
        raise AssertionError("valid physics count exceeds geometry-valid candidate count")
    if counters.physics_attempted_evaluations != (
        counters.valid_physics_evaluations + counters.physics_failures
    ):
        raise AssertionError("physics attempted counter partition failed")
    expected_points = counters.valid_physics_evaluations * int(search_frequency_count)
    if counters.search_frequency_points != expected_points:
        raise AssertionError("search frequency point counter does not match completed physics sweeps")

def _counter_snapshot(backend: LShadeBackend, counters: EvaluationCounters,
                      search_frequency_count: int, elapsed_s: float) -> dict[str, Any]:
    summary = backend.summary()
    unique = int(summary["unique_evaluations"])
    _assert_counter_invariants(counters, unique, search_frequency_count)
    validation_points = counters.validation_solved_frequency_points
    return {
        "objective_calls": int(summary["proposals_total"]),
        "canonical_candidates_seen": int(summary["proposals_total"]),
        "unique_decoded_evaluations": unique,
        "geometry_rejections": counters.geometry_rejections,
        "geometry_valid_candidates": counters.geometry_valid_candidates,
        "valid_physics_evaluations": counters.valid_physics_evaluations,
        "physics_attempted_evaluations": counters.physics_attempted_evaluations,
        "physics_failures": counters.physics_failures,
        "cache_hits": int(summary["cache_hits"]),
        "solved_frequency_points": counters.search_frequency_points + validation_points,
        "search_frequency_points": counters.search_frequency_points,
        "validation_evaluations": counters.validation_evaluations,
        "validation_physics_failures": counters.validation_physics_failures,
        "validation_frequency_points": validation_points,
        "search_frequency_count": int(search_frequency_count),
        "elapsed_s": float(elapsed_s),
        "initial_population_sampling": dict(counters.initial_sampling),
    }

def _population_size(cfg: Mapping[str, Any], topology: str, budget: int,
                     hard_bounds: np.ndarray) -> int:
    lcfg = _backend_config(cfg, topology, budget, hard_bounds)
    dimension = len(cfg["dms_topology"]["topologies"][topology]["bounds"]["active"])
    requested = int(lcfg.get("initial_population", lcfg.get("initial_population_per_dimension", 18) * dimension))
    return max(requested, int(lcfg.get("min_population", 4)))

def _evaluator(cfg, provider, topology: str, frequencies: np.ndarray,
               counters: EvaluationCounters):
    def evaluate_vector(vector):
        design = decode_design(vector, topology, cfg)
        result = evaluate_dms_design(design, provider, cfg, frequencies, topology)
        counters.observe_search(result, len(frequencies))
        return result
    return evaluate_vector

def select_common_grid_candidate(records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    eligible = [record for record in records if _status(record) == "PHYSICS_EVALUATED"
                and _finite_filter_outputs(record)]
    return min(eligible, key=GEOMETRY_FIRST_COMPARATOR.rank_key) if eligible else None

def _design_vector_from_record(payload: Mapping[str, Any], topology: str) -> np.ndarray:
    """Inverse of the topology decoders for serialized fixed-dimensional designs."""
    names = {
        T0: ("wavelength_um", "io_idt_pairs", "center_idt_pairs", "reflector_electrodes",
             "idt_gap_lambda", "reflector_gap_lambda", "aperture_um", "center_wavelength_um",
             "reflector_wavelength_um"),
        T1: ("wavelength_A_um", "wavelength_B_um", "wavelength_C_um",
             "reflector_wavelength_um", "pairs_A", "pairs_B", "pairs_C",
             "common_idt_gap_lambda", "reflector_gap_lambda", "aperture_um"),
        T2: ("track_A_main_wavelength_um", "track_B_main_wavelength_um", "io_idt_pairs",
             "center_idt_pairs", "reflector_electrodes", "idt_gap_lambda",
             "reflector_gap_lambda", "center_wavelength_ratio", "reflector_wavelength_ratio",
             "total_aperture_um"),
    }[topology]
    values = [payload.get(name) for name in names]
    if topology == T0:
        values[7] = payload.get("center_wavelength_um") or payload["wavelength_um"]
        values[8] = payload.get("reflector_wavelength_um") or payload["wavelength_um"]
    if any(value is None for value in values):
        raise ValueError(f"serialized design is incomplete for {topology}")
    return np.asarray(values, dtype=float)

def _cache_key_records(backend: LShadeBackend) -> list[Mapping[str, Any]]:
    return [dict(value) for value in backend._cache.values()]

def _checkpoint_row(record: Mapping[str, Any], counters: Mapping[str, Any],
                    sampling: Mapping[str, Any], active: np.ndarray, hard: np.ndarray):
    incumbent = record
    metrics = incumbent.get("metrics", {})
    violations = incumbent.get("violations", {})
    unique = int(counters.get("unique_decoded_evaluations", 0))
    rejected = int(counters.get("geometry_rejections", 0))
    geometry_valid = int(counters.get("geometry_valid_candidates", 0))
    valid_physics = int(counters.get("valid_physics_evaluations", 0))
    physics_failures = int(counters.get("physics_failures", 0))
    physics_attempted = int(counters.get("physics_attempted_evaluations", 0))
    return {
        "material": record.get("material"),
        "topology": record.get("topology"),
        "seed": record.get("seed"),
        "checkpoint_budget": record.get("checkpoint_budget"),
        "evaluation_status": record.get("evaluation_status"),
        "geometry_valid": record.get("geometry_valid"),
        "geometry_max_violation": record.get("geometry_max_violation"),
        "max_violation": record.get("max_violation"),
        "sum_violation": record.get("sum_violation"),
        "feasible": record.get("feasible"),
        "worst_il_db": metrics.get("worst_il_db"),
        "ripple_db": metrics.get("ripple_db"),
        "input_vswr": metrics.get("input_vswr"),
        "output_vswr": metrics.get("output_vswr"),
        "stop_1_attenuation_db": metrics.get("stop_attenuation_db", [None] * 4)[1],
        "stop_2_attenuation_db": metrics.get("stop_attenuation_db", [None] * 4)[2],
        "active_filter_constraint": max(violations, key=violations.get) if violations else None,
        "design": json.dumps(_clean(record.get("design", {})), sort_keys=True),
        "geometry_violations": json.dumps(
            _clean(record.get("geometry_violations", {})), sort_keys=True
        ),
        "hard_geometry_dimensions": json.dumps(
            _clean(record.get("geometry_dimensions", {})), sort_keys=True
        ),
        **{key: counters.get(key) for key in (
            "objective_calls", "canonical_candidates_seen", "unique_decoded_evaluations",
            "geometry_rejections", "geometry_valid_candidates", "valid_physics_evaluations",
            "physics_attempted_evaluations", "physics_failures", "cache_hits",
            "solved_frequency_points", "search_frequency_points",
            "validation_frequency_points", "elapsed_s",
        )},
        "counter_identity_pass": unique == rejected + geometry_valid,
        "physics_partition_pass": geometry_valid == valid_physics + physics_failures,
        "valid_physics_within_geometry_valid": valid_physics <= geometry_valid,
        "physics_attempt_identity_pass": physics_attempted == valid_physics + physics_failures,
        "initial_sampling": json.dumps(_clean(sampling), sort_keys=True),
        "search_bound_hit_variables": json.dumps(
            _clean(_search_bound_hits(record.get("design", {}), record["topology"], active)),
            sort_keys=True,
        ),
        "optimizer_hard_bounds": json.dumps(hard.tolist()),
    }

def _search_bound_hits(design: Mapping[str, Any], topology: str, active: np.ndarray):
    names = {
        T0: ("wavelength_um", "io_idt_pairs", "center_idt_pairs", "reflector_electrodes",
             "idt_gap_lambda", "reflector_gap_lambda", "aperture_um", "center_wavelength_um",
             "reflector_wavelength_um"),
        T1: ("wavelength_A_um", "wavelength_B_um", "wavelength_C_um",
             "reflector_wavelength_um", "pairs_A", "pairs_B", "pairs_C",
             "common_idt_gap_lambda", "reflector_gap_lambda", "aperture_um"),
        T2: ("track_A_main_wavelength_um", "track_B_main_wavelength_um", "io_idt_pairs",
             "center_idt_pairs", "reflector_electrodes", "idt_gap_lambda",
             "reflector_gap_lambda", "center_wavelength_ratio", "reflector_wavelength_ratio",
             "total_aperture_um"),
    }[topology]
    hits = {}
    for index, name in enumerate(names):
        if name not in design or index >= len(active):
            continue
        value = float(design[name])
        hits[name] = {
            "lower": abs(value - active[index, 0]) <= 1e-9,
            "upper": abs(value - active[index, 1]) <= 1e-9,
        }
    return hits

def _optimize_cell(
    out: Path, cfg: Mapping[str, Any], material: str, topology: str, seed: int,
    provider: Any, search_frequencies: np.ndarray, *, budget: int,
    checkpoints: Sequence[int], fingerprint: str, sampling_seed_data: Mapping[str, Any],
    max_attempts: int, resume: bool = False,
) -> tuple[list[dict[str, Any]], LShadeBackend, EvaluationCounters, dict[str, int]]:
    active, hard, integer_indices = material_bounds(cfg, material, topology)
    seed_dir = out / "optimization" / material / topology / f"seed{int(seed)}"
    seed_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = seed_dir / "optimizer_checkpoint.json"
    metadata_path = seed_dir / "trajectory_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if resume and metadata_path.exists() else {}
    counters = EvaluationCounters(initial_sampling=dict(
        metadata.get("initial_population_sampling", sampling_seed_data)
    ))
    evaluator = _evaluator(cfg, provider, topology, search_frequencies, counters)
    backend = LShadeBackend(
        active,
        seed=int(seed),
        config=_backend_config(cfg, topology, budget, hard),
        integer_indices=integer_indices,
        comparator=GEOMETRY_FIRST_COMPARATOR,
        source_config_fingerprint=fingerprint,
    )
    if resume and checkpoint_path.exists():
        backend.load_checkpoint(checkpoint_path)
        backend.set_evaluator(evaluator)
        if getattr(backend, "active_frequency_grid", None) is None or len(backend.active_frequency_grid) == 0:
            backend.set_frequency_grid(search_frequencies, version=1)
        counters.restore_from_cache(_cache_key_records(backend), len(search_frequencies))
    else:
        population, sampling, _preflight = _population_preflight(
            cfg, material, topology, seed, budget, max_attempts,
        )
        counters.initial_sampling = dict(sampling)
        backend.set_frequency_grid(search_frequencies, version=1)
        backend.initialize(evaluator, population=population)
        metadata = {"last_completed_budget": 0, "initial_population_sampling": sampling}

    started = time.monotonic()
    started_cpu = time.process_time()
    elapsed_before_run = float(metadata.get("cumulative_wall_time_s", 0.0))
    records: list[dict[str, Any]] = []
    events = list(metadata.get("frequency_grid_events", []))
    if not checkpoints or any(int(point) < backend.initial_population_size for point in checkpoints):
        raise ValueError("every checkpoint must be at least the initial population size")
    for index, point_value in enumerate(checkpoints):
        point = int(point_value)
        result_path = seed_dir / f"B{point}.json"
        if resume and result_path.exists() and backend.unique_evaluations >= point:
            records.append(json.loads(result_path.read_text(encoding="utf-8")))
            continue
        optimizer_started = time.monotonic()
        if backend.unique_evaluations < point:
            backend.advance_to_unique_budget(point)
        optimizer_elapsed = time.monotonic() - optimizer_started
        elapsed = elapsed_before_run + time.monotonic() - started
        snapshot = _counter_snapshot(backend, counters, len(search_frequencies), elapsed)
        event = {
            "event": "fixed_search_grid_checkpoint",
            "checkpoint_budget": point,
            "frequency_grid_version": int(backend.frequency_grid_version),
            "frequency_grid_count": len(search_frequencies),
            "unique_decoded_evaluations": int(backend.unique_evaluations),
        }
        events.append(event)
        record = lshade_record(
            backend, topology, seed, point, checkpoint_path, events,
            started, started_cpu, disk_resume_used=bool(resume),
            trajectory_index=index, optimizer_wall_time_s=optimizer_elapsed,
            validation_wall_time_s=0.0, total_trial_wall_time_s=elapsed,
        )
        record.update({
            "study_type": STUDY_TYPE,
            "material": material,
            "topology": topology,
            "seed": int(seed),
            "evaluation_status": _status(backend.incumbent() or {}),
            "geometry_valid": bool((backend.incumbent() or {}).get("geometry_valid", False)),
            "geometry_max_violation": (backend.incumbent() or {}).get("geometry_max_violation"),
            "geometry_dimensions": (backend.incumbent() or {}).get("geometry_dimensions", {}),
            "geometry_violations": (backend.incumbent() or {}).get("geometry_violations", {}),
            "evaluation_counters": snapshot,
            "initial_population_sampling": dict(counters.initial_sampling),
            "active_bounds": active.tolist(),
            "optimizer_hard_bounds": hard.tolist(),
            "search_bounds_are_not_manufacturing_limits": True,
            "cold_start": not bool(resume),
            "warm_start": False,
            "parent_transfer": False,
            "neighbor_warm_start": False,
        })
        save(result_path, _clean(record))
        backend.save_checkpoint(checkpoint_path)
        metadata = {
            "last_completed_budget": point,
            "material": material,
            "topology": topology,
            "seed": int(seed),
            "source_config_fingerprint": fingerprint,
            "active_bounds": active.tolist(),
            "optimizer_hard_bounds": hard.tolist(),
            "initial_population_sampling": dict(counters.initial_sampling),
            "frequency_grid_count": int(len(search_frequencies)),
            "frequency_grid_hash": hashlib.sha256(search_frequencies.tobytes()).hexdigest(),
            "cumulative_wall_time_s": elapsed,
            "evaluation_counters": snapshot,
            "frequency_grid_events": events,
            "checkpoints": list(map(int, checkpoints)),
            "budget": int(budget),
        }
        _write_json(metadata_path, metadata)
        records.append(_clean(record))
    return records, backend, counters, dict(counters.initial_sampling)

def _finite_required_metrics(record: Mapping[str, Any] | None) -> bool:
    return bool(record is not None and _status(record) == "PHYSICS_EVALUATED"
                and _finite_filter_outputs(record))

def _valid_physics_fraction(counters: Mapping[str, Any]) -> float:
    unique = int(counters.get("unique_decoded_evaluations", 0))
    return float(counters.get("valid_physics_evaluations", 0) / unique) if unique else 0.0

def _geometry_rejection_fraction(counters: Mapping[str, Any]) -> float:
    unique = int(counters.get("unique_decoded_evaluations", 0))
    return float(counters.get("geometry_rejections", 0) / unique) if unique else 0.0

class InitializerExhausted(RuntimeError):
    """Finite rejection-sampling cap reached before filling the population."""

    def __init__(self, diagnostics: Mapping[str, Any]):
        self.diagnostics = dict(diagnostics)
        super().__init__("INITIALIZER_EXHAUSTED: rejection-sampling attempt cap reached")


def _common_grid_select(
    search_records: Sequence[Mapping[str, Any]], provider: Any, cfg: Mapping[str, Any],
    frequencies: np.ndarray, topology: str, counters: EvaluationCounters, finalist_count: int,
) -> tuple[Mapping[str, Any] | None, list[Mapping[str, Any]]]:
    eligible = [record for record in search_records
                if _status(record) == "PHYSICS_EVALUATED" and _finite_filter_outputs(record)]
    finalists = sorted(eligible, key=GEOMETRY_FIRST_COMPARATOR.rank_key)[:max(1, int(finalist_count))]
    validated = []
    for source in finalists:
        design = decode_design(_design_vector_from_record(source["design"], topology), topology, cfg)
        counters.validation_evaluations += 1
        result = evaluate_dms_design(design, provider, cfg, frequencies, topology, include_spectrum=True)
        result = dict(result)
        result["design"] = asdict(design)
        result["search_source_rank_key"] = list(GEOMETRY_FIRST_COMPARATOR.rank_key(source))
        if _status(result) == "PHYSICS_EVALUATED":
            counters.validation_solved_frequency_points += len(frequencies)
        else:
            counters.validation_physics_failures += 1
        validated.append(result)
    return select_common_grid_candidate(validated), validated


def _population_preflight(
    cfg: Mapping[str, Any], material: str, topology: str, seed: int, budget: int,
    max_attempts: int,
) -> tuple[np.ndarray, dict[str, Any], dict[str, Any]]:
    active, hard, integer_indices = material_bounds(cfg, material, topology)
    population_size = _population_size(cfg, topology, budget, hard)
    if budget < population_size:
        raise ValueError(f"budget {budget} is below initial population {population_size}")
    settings = cfg["dms_topology"]
    max_attempts = max(int(max_attempts),
                       int(settings.get("initial_population_attempt_multiplier", 60)) * population_size)
    population, sampling = sample_independent_uniform_population(
        cfg, material, topology, seed=seed, population_size=population_size,
        max_attempts=max_attempts,
        reference_proposals=int(settings.get("initializer_reference_proposals", 0)),
        bootstrap_replicates=int(settings.get("distribution_bootstrap_replicates", 0)),
    )
    low, high = active[:, 0], active[:, 1]
    canonical_keys = set()
    for normalized in population:
        physical = low + np.asarray(normalized, dtype=float) * (high - low)
        canonical = _canonical_physical(physical, active, integer_indices)
        if not np.allclose(physical, canonical, rtol=0.0, atol=1e-10):
            raise AssertionError("initializer vector changes under optimizer canonicalization")
        key = tuple(float(value) for value in canonical)
        if key in canonical_keys:
            raise AssertionError("initializer emitted duplicate canonical designs")
        canonical_keys.add(key)
        design = decode_design(canonical, topology, cfg)
        if _geometry_status(design, cfg)[2] > 0.0:
            raise AssertionError("initializer emitted a geometry-invalid design")
    row = {
        "material": material,
        "topology": topology,
        "seed": int(seed),
        "population_size": population_size,
        "active_bounds": active.tolist(),
        "optimizer_hard_bounds": hard.tolist(),
        "initial_population_sampling": sampling,
        "unique_canonical_members": len(canonical_keys),
    }
    return population, sampling, row


def _known_design_preflight(
    cfg: Mapping[str, Any], search_frequencies: np.ndarray, common_frequencies: np.ndarray,
    *, materials: Sequence[str] | None = None, topologies: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    rows = []
    selected_materials = tuple(materials) if materials is not None else _selected_study_axes(cfg)[0]
    selected_topologies = tuple(topologies) if topologies is not None else _selected_study_axes(cfg)[1]
    for material in selected_materials:
        provider, _metadata = provider_for_material(material, cfg)
        for topology in selected_topologies:
            design = initial_design(material, topology, cfg)
            search_result = evaluate_dms_design(design, provider, cfg, search_frequencies, topology)
            common_result = evaluate_dms_design(design, provider, cfg, common_frequencies, topology)
            rows.append({
                "material": material,
                "topology": topology,
                "search_status": _status(search_result),
                "common_grid_status": _status(common_result),
                "search_frequency_count": len(search_frequencies),
                "common_frequency_count": len(common_frequencies),
                "search_metrics_finite": _finite_required_metrics(search_result),
                "common_metrics_finite": _finite_required_metrics(common_result),
                "geometry_valid": bool(search_result.get("geometry_valid", False)),
                "design": _clean(asdict(design)),
            })
    return rows


def run_dms_topology_screening(
    config_path: str | Path, run_path: str | Path, *, resume: bool = False,
) -> dict[str, Any]:
    """Optimize each configured material/topology/seed cell independently."""
    cfg = load_experiment_config(config_path)
    cfg = dict(cfg)
    cfg["_source_config_path"] = str(Path(config_path).resolve())
    settings = cfg["dms_topology"]
    out = Path(run_path).resolve()
    if bool(settings.get("cold_start", False)) and resume:
        raise ValueError("this study config requires a cold start and forbids resume")
    if out.exists() and not resume and any(out.iterdir()):
        raise FileExistsError(f"study output directory is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)

    raw_config = Path(config_path).read_text(encoding="utf-8")
    common_frequencies, common_grid_id, metadata_path, grid_metadata = _load_common_grid(cfg)
    search_frequencies = np.unique(search_grid(cfg["spec"], cfg))
    fingerprint = _source_fingerprint(raw_config, common_grid_id)
    budget = int(settings["budget"])
    seeds = tuple(int(seed) for seed in settings["seeds"])
    checkpoints = tuple(int(point) for point in settings.get("checkpoints", [budget]))
    materials, topologies = _selected_study_axes(cfg)
    if not seeds or not checkpoints or max(checkpoints) != budget:
        raise ValueError("checkpoints must be non-empty and end at the configured budget")
    seed_contract = resolve_initial_population_seed_contract(cfg)
    initial_sampling_seeds = {
        f"{material}/{topology}/{seed}": initial_population_sampling_seed(
            cfg, seed, material, topology,
        )
        for material in materials for topology in topologies for seed in seeds
    }

    metadata_dir = out / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (out / "input_config.yaml").write_text(raw_config, encoding="utf-8")
    (metadata_dir / "common_validation_grid.csv").write_bytes(
        (ROOT / grid_metadata["source"]).read_bytes()
    )
    _write_json(metadata_dir / "run_source_metadata.json", {
        "study_type": STUDY_TYPE,
        "semantics_version": SEMANTICS_VERSION,
        "source_config_fingerprint": fingerprint,
        "git": _git_state(),
        "search_frequency_count": len(search_frequencies),
        "search_frequency_sha256": hashlib.sha256(search_frequencies.tobytes()).hexdigest(),
        "common_validation_grid_id": common_grid_id,
        "common_validation_grid_count": len(common_frequencies),
        "common_validation_grid_metadata_path": metadata_path,
        "common_validation_grid_sha256": grid_metadata["sha256"],
        "common_validation_grid_origin": grid_metadata.get("historical_origin"),
        "initial_design_origins": json.loads(
            (ROOT / "configs/reference/dms_topology_screening/initial_design_origins.json")
            .read_text(encoding="utf-8")
        ),
        "source_impedance_ohm": float(settings.get("impedance_ohm", 50.0)),
        "load_impedance_ohm": float(settings.get("impedance_ohm", 50.0)),
        "budget": budget,
        "checkpoints": list(checkpoints),
        "seeds": list(seeds),
        "selected_materials": list(materials),
        "selected_topologies": list(topologies),
        "selection": {"materials": list(materials), "topologies": list(topologies)},
        "cold_start": not resume,
        "warm_start": bool(resume),
        "parent_transfer": False,
        "neighbor_warm_start": False,
        "initializer_method": "independent_uniform_rejection_v1",
        "initial_population_seed_contract": {
            "identifier": seed_contract.identifier,
            "namespace": seed_contract.namespace,
            "derivation_suffix": seed_contract.derivation_suffix,
        },
        "initial_sampling_seeds": initial_sampling_seeds,
    })

    implementation = implementation_validation(cfg)
    _write_json(metadata_dir / "implementation_validation.json", implementation)
    if implementation.get("status") != "PASS":
        return {"status": "IMPLEMENTATION_VALIDATION_FAILED", "run": str(out)}
    fixed_rows = fixed_design_sanity(
        out, cfg, common_frequencies, materials=materials, topologies=topologies,
    )
    known_rows = _known_design_preflight(
        cfg, search_frequencies, common_frequencies,
        materials=materials, topologies=topologies,
    )
    _write_csv(out / "known_design_preflight.csv", known_rows)
    failed_known = [row for row in known_rows if not row["search_metrics_finite"]
                    or not row["common_metrics_finite"] or not row["geometry_valid"]]
    if failed_known:
        return {"status": "KNOWN_DESIGN_PREFLIGHT_FAILED", "run": str(out),
                "failures": failed_known}

    search_rows = []
    checkpoint_rows = []
    rejection_rows = []
    response_rows = []
    initializer_rows = []
    for material in materials:
        provider, _profile_metadata = provider_for_material(material, cfg)
        for topology in topologies:
            active, hard, _integer_indices = material_bounds(cfg, material, topology)
            for seed in seeds:
                initial_population_size = _population_size(cfg, topology, budget, hard)
                records, backend, counters, sampling = _optimize_cell(
                    out, cfg, material, topology, seed, provider, search_frequencies,
                    budget=budget, checkpoints=checkpoints, fingerprint=fingerprint,
                    sampling_seed_data={},
                    max_attempts=max(int(settings.get("max_initial_population_attempts", 10000)),
                                     int(settings.get("initial_population_attempt_multiplier", 60))
                                     * initial_population_size),
                    resume=resume,
                )
                initializer_rows.append({
                    "material": material, "topology": topology, "seed": seed,
                    "population_size": initial_population_size,
                    "initial_population_sampling": sampling,
                })
                if not records:
                    raise RuntimeError(f"optimizer produced no checkpoints for {material}/{topology}/{seed}")
                final = dict(records[-1])
                selected, validated = _common_grid_select(
                    _cache_key_records(backend), provider, cfg, common_frequencies,
                    topology, counters, int(settings.get("common_grid_finalists", 16)),
                )
                snapshot = _counter_snapshot(
                    backend, counters, len(search_frequencies),
                    float(final.get("total_trial_wall_time_s", 0.0)),
                )
                final.update({
                    "evaluation_counters": snapshot,
                    "common_validation_grid_id": common_grid_id,
                    "common_grid_status": _status(selected) if selected else "NO_VALID_FINALIST",
                    "common_grid_selected_design": _clean(selected.get("design", {})) if selected else None,
                    "common_grid_metrics": _clean(selected.get("metrics", {})) if selected else {},
                    "common_grid_spectrum": _clean(selected.get("spectrum", {})) if selected else {},
                })
                seed_dir = out / "optimization" / material / topology / f"seed{seed}"
                _write_json(seed_dir / "common_grid_selection.json", {
                    "source_config_fingerprint": fingerprint,
                    "common_validation_grid_id": common_grid_id,
                    "selected": _clean(selected),
                    "validated_finalists": _clean(validated),
                })
                save(seed_dir / f"B{budget}.json", _clean(final))
                for record in records:
                    counters_at_checkpoint = record.get("evaluation_counters", {})
                    checkpoint_rows.append(_checkpoint_row(
                        record, counters_at_checkpoint, sampling, active, hard,
                    ))
                rejection_rows.extend({
                    "material": material,
                    "topology": topology,
                    "seed": seed,
                    "evaluation_status": _status(row),
                    "failure_stage": row.get("failure_stage"),
                    "design": row.get("design", {}),
                    "geometry_dimensions": row.get("geometry_dimensions", {}),
                    "geometry_violations": row.get("geometry_violations", {}),
                } for row in _cache_key_records(backend)
                  if _status(row) == "GEOMETRY_REJECTED")
                for candidate in validated:
                    spectrum = candidate.get("spectrum", {})
                    frequencies = spectrum.get("frequency_hz", [])
                    s11 = spectrum.get("s11_db", [])
                    s21 = spectrum.get("s21_db", [])
                    response_rows.extend({
                        "material": material, "topology": topology, "seed": seed,
                        "frequency_hz": frequency,
                        "s11_db": s11[index] if index < len(s11) else None,
                        "s21_db": s21[index] if index < len(s21) else None,
                    } for index, frequency in enumerate(frequencies))
                search_rows.append({
                    "material": material,
                    "topology": topology,
                    "seed": seed,
                    "checkpoint_budget": budget,
                    "evaluation_status": final.get("evaluation_status"),
                    "geometry_valid": final.get("geometry_valid"),
                    "max_violation": final.get("max_violation"),
                    "sum_violation": final.get("sum_violation"),
                    "feasible": final.get("feasible"),
                    "metrics": final.get("metrics", {}),
                    "objective": final.get("objective"),
                    "design": final.get("design", {}),
                    "common_grid_status": final["common_grid_status"],
                    "common_grid_metrics": final["common_grid_metrics"],
                    "common_grid_design": final["common_grid_selected_design"],
                    "evaluation_counters": snapshot,
                })

    _write_json(out / "study_summary.json", {
        "study_type": STUDY_TYPE,
        "status": "COMPLETE",
        "source_config_fingerprint": fingerprint,
        "common_validation_grid_id": common_grid_id,
        "materials": list(materials),
        "topologies": list(topologies),
        "seeds": list(seeds),
        "budget": budget,
        "checkpoint_count": len(checkpoint_rows),
        "cell_results": search_rows,
    })
    _write_csv(out / "seed_results.csv", search_rows)
    _write_csv(out / "checkpoint_accounting.csv", checkpoint_rows)
    _write_csv(out / "initializer_accounting.csv", initializer_rows)
    _write_csv(out / "geometry_rejections.csv", rejection_rows)
    _write_csv(out / "common_grid_responses.csv", response_rows)
    checkpoint_audit = validate_checkpoint_lattice(
        checkpoint_rows, materials=materials, topologies=topologies,
        seeds=seeds, checkpoints=checkpoints,
    )
    _write_json(out / "checkpoint_accounting_audit.json", checkpoint_audit)
    if not checkpoint_audit["passed"]:
        raise RuntimeError("checkpoint accounting does not cover the configured evaluation lattice")

    review_dir = out / "review_bundle"
    review_dir.mkdir(parents=True, exist_ok=True)
    bundle_files = [
        "input_config.yaml", "study_summary.json", "seed_results.csv",
        "checkpoint_accounting.csv", "initializer_accounting.csv",
        "geometry_rejections.csv", "common_grid_responses.csv",
        "known_design_preflight.csv", "dms_topology_fixed_design_sanity.csv",
        "common_validation_grid.csv", "checkpoint_accounting_audit.json",
    ]
    for relative in bundle_files:
        source_path = (metadata_dir / relative.removeprefix("metadata/")) if relative == "common_validation_grid.csv" else out / relative
        shutil.copy2(source_path, review_dir / relative)
    shutil.copy2(metadata_dir / "run_source_metadata.json", review_dir / "run_source_metadata.json")
    review_output = ROOT / "artifacts" / "review_bundles" / f"{out.name}_review.zip"
    write_review_bundle_archive(
        review_dir, review_output, study_type=STUDY_TYPE,
        run_directory=out, required_artifacts=bundle_files + ["run_source_metadata.json"],
        metadata={
            "source_config_fingerprint": fingerprint,
            "common_validation_grid_id": common_grid_id,
        },
        repository_root=ROOT,
        git_diff_paths=[
            "src/sawopt/studies/dms_topology_screening.py",
            "src/sawopt/studies/dms_topology_common.py",
            "configs/studies/dms_topology_screening.yaml",
        ],
    )
    return {
        "status": "DMS_TOPOLOGY_SCREENING_COMPLETE",
        "run": str(out),
        "review_bundle": str(review_output),
        "source_config_fingerprint": fingerprint,
        "common_validation_grid_id": common_grid_id,
        "cell_count": len(search_rows),
    }
