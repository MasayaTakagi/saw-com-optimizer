"""Stage 3.8C-R1 geometry-gated dual-material topology screen.

This module keeps the Stage 3.8 topology/COM implementation and L-SHADE
backend intact. It changes only the study-level candidate gate, comparator,
population initialization, accounting, and validation/reporting path.
"""
from __future__ import annotations

import csv
import ast
import hashlib
import json
import math
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from ..core.literature_com import profile_from_mapping
from ..core.metrics import geometry, measure, search_grid
from ..core.models import FixedProvider
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
from ..reporting.material_metadata import material_profile_metadata
from ..reporting.review_bundle import write_review_bundle_archive
from .optimizer_ab import lshade_record
from .stage3_8_dual_material_dms_topology_fast_screen import (
    MATERIALS,
    T0,
    T1,
    T2,
    TOPOLOGIES,
    decode_design,
    fixed_design_sanity,
    implementation_validation,
    initial_design,
    simulate_topology,
)


ROOT = Path(__file__).resolve().parents[3]
STUDY_TYPE = "stage3_8c_r1_geometry_gate"
SEMANTICS_VERSION = "stage3_8c_r1_geometry_first_v1"
GEOMETRY_CONSTRAINT_NAMES = (
    "max_total_acoustic_length",
    "max_aperture_width",
    "minimum_electrode_width",
    "minimum_electrode_gap",
    "max_total_electrode_count",
)
RF_METRIC_KEYS = (
    "worst_il_db",
    "ripple_db",
    "input_vswr",
    "output_vswr",
    "source_return_loss_db_min",
    "load_return_loss_db_min",
    "stop_attenuation_db",
)
EXPECTED_PHYSICS_ERRORS = (ValueError, np.linalg.LinAlgError, FloatingPointError, OverflowError)
PILOT_FAIL = "STAGE3_8C_R1_PILOT_FAIL_STOP"
MAIN_COMPLETE = "STAGE3_8C_R1_VALID_TOPOLOGY_SCREEN_COMPLETE_STOP"
SEARCH_REDESIGN = "STAGE3_8C_R1_SEARCH_SPACE_REDESIGN_REQUIRED_STOP"
R1_INITIAL_REJECTION_REFERENCE = {
    "M0": {T0: (1176, 1337), T1: (8, 187), T2: (2483, 2662)},
    "MLIT": {T0: (997, 1158), T1: (14, 193), T2: (2056, 2235)},
}


def _finite(value: Any, default: float = math.inf) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    return number if math.isfinite(number) else float(default)


R1_COMPARATOR = GeometryFirstComparator()


def _provider(material: str, cfg: Mapping[str, Any]):
    section = cfg["stage3_8"]["materials"][material]
    if material == "M0":
        values = yaml.safe_load((ROOT / section["com_file"]).read_text(encoding="utf-8"))
        return FixedProvider(values), material_profile_metadata(profile_id="M0")
    profile_path = ROOT / section["profile_file"]
    profile_data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    provider = profile_from_mapping(profile_data)
    return provider, material_profile_metadata(
        profile_data, profile_id=provider.profile_id,
        com_parameter_source=str(profile_path),
    )


def _backend_config(cfg: Mapping[str, Any], topology: str, budget: int,
                    hard_bounds: np.ndarray) -> dict[str, Any]:
    section = cfg["stage3_8"]["topologies"][topology]
    values = dict(cfg.get("stage3_3", {}).get("lshade", {}))
    values.update({
        "total_budget": int(budget),
        "hard_max_budget": int(budget),
        "population_schedule_terminal_budget": int(budget),
        "initial_population": max(4, 18 * int(len(hard_bounds))),
        "hard_bounds": np.asarray(hard_bounds, dtype=float).tolist(),
    })
    values.update(section.get("lshade", {}))
    return values


def _load_common_grid(cfg: Mapping[str, Any]) -> tuple[np.ndarray, str, str]:
    metadata_path = ROOT / cfg["stage3_8"]["common_validation_grid_metadata"]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    grid_path = Path(metadata["source"])
    if not grid_path.is_absolute():
        grid_path = ROOT / grid_path
    grid = np.loadtxt(grid_path, delimiter=",", skiprows=1).astype(float)
    grid_id = hashlib.sha256(np.asarray(grid, dtype="<f8").tobytes()).hexdigest()
    if grid_id != metadata["grid_id"]:
        raise ValueError(f"validation-grid identity mismatch: {grid_id} != {metadata['grid_id']}")
    return grid, grid_id, str(metadata_path)


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
            "stage3_8c_r1_geometry_rejections.csv": [
                "material", "topology", "seed", "evaluation_status", "failure_stage",
                "design", "geometry_dimensions", "violated_hard_constraints",
                "normalized_geometry_violations",
            ],
            "stage3_8c_r1_validated_responses.csv": [
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
    section = cfg["stage3_8"]["topologies"][topology]
    active = np.asarray(section["bounds"]["active"], dtype=float).copy()
    hard = np.asarray(section["bounds"].get("hard", section["bounds"]["active"]), dtype=float).copy()
    low, high = map(float, cfg["stage3_8"]["materials"][material]["aperture_bounds_um"])
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


def _sample_seed(seed: int, material: str, topology: str) -> int:
    payload = (
        f"{SEMANTICS_VERSION}/r1_1_conditional_geometry/{seed}/"
        f"{material}/{topology}/initial_population"
    ).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % (2**32)


def _geometry_sampling_model(
    cfg: Mapping[str, Any], topology: str, vector: np.ndarray,
) -> dict[str, Any]:
    """Return exact positive count contributions for the current decoders."""
    if topology == T0:
        wavelength, _io, _center, _reflector, idt_gap, reflector_gap, *_rest = vector
        center_wavelength, reflector_wavelength = vector[7], vector[8]
        return {
            "base_electrodes": 0.0,
            "electrode_coefficients": {1: 4.0, 2: 2.0, 3: 2.0},
            "base_lengths_um": (2.0 * wavelength * (idt_gap + reflector_gap),),
            "length_coefficients_um": {
                1: (2.0 * wavelength,),
                2: (center_wavelength,),
                3: (reflector_wavelength,),
            },
        }
    if topology == T1:
        wavelength_a, wavelength_b, wavelength_c, reflector_wavelength = vector[:4]
        gap, reflector_gap = vector[7:9]
        reflector_electrodes = float(cfg["stage3_8"]["t1_reflector_electrodes"])
        return {
            "base_electrodes": 2.0 * reflector_electrodes,
            "electrode_coefficients": {4: 4.0, 5: 4.0, 6: 2.0},
            "base_lengths_um": (
                reflector_electrodes * reflector_wavelength
                + (2.0 * reflector_gap + gap) * wavelength_a
                + 2.0 * gap * wavelength_b
                + gap * wavelength_c,
            ),
            "length_coefficients_um": {
                4: (2.0 * wavelength_a,),
                5: (2.0 * wavelength_b,),
                6: (wavelength_c,),
            },
        }
    if topology == T2:
        wavelength_a, wavelength_b = vector[:2]
        center_ratio, reflector_ratio = vector[7:9]
        idt_gap, reflector_gap = vector[5:7]
        base_a = 2.0 * wavelength_a * (idt_gap + reflector_gap)
        base_b = 2.0 * wavelength_b * (idt_gap + reflector_gap)
        return {
            "base_electrodes": 0.0,
            "electrode_coefficients": {2: 8.0, 3: 4.0, 4: 4.0},
            # Both track lengths must fit; geometry() reports their maximum.
            "base_lengths_um": (base_a, base_b),
            "length_coefficients_um": {
                2: (2.0 * wavelength_a, 2.0 * wavelength_b),
                3: (wavelength_a * center_ratio, wavelength_b * center_ratio),
                4: (wavelength_a * reflector_ratio, wavelength_b * reflector_ratio),
            },
        }
    raise ValueError(f"unsupported topology for conditional sampling: {topology}")


def _integer_search_support(
    active: np.ndarray, integer_indices: Sequence[int],
) -> dict[int, tuple[int, int]]:
    support = {}
    for index in integer_indices:
        low, high = map(float, active[index])
        minimum, maximum = math.ceil(low), math.floor(high)
        if minimum > maximum:
            raise ValueError(f"integer variable {index} has no integer value inside active bounds")
        support[int(index)] = (int(minimum), int(maximum))
    return support


def _count_upper_bound(
    index: int, *, model: Mapping[str, Any], selected: Mapping[int, int],
    remaining: Sequence[int], support: Mapping[int, tuple[int, int]],
    constraints: Mapping[str, Any],
) -> int:
    """Maximum current count while reserving minimum values for later counts."""
    maximum = support[index][1]
    electrode_coefficients = model["electrode_coefficients"]
    current_electrodes = float(model["base_electrodes"])
    current_electrodes += sum(
        electrode_coefficients[key] * value for key, value in selected.items()
    )
    current_electrodes += sum(
        electrode_coefficients[key] * support[key][0] for key in remaining
    )
    coefficient = float(electrode_coefficients[index])
    electrode_room = (float(constraints["max_electrodes"]) - current_electrodes) / coefficient
    maximum = min(maximum, math.floor(electrode_room + 1e-10))

    base_lengths = model["base_lengths_um"]
    length_coefficients = model["length_coefficients_um"]
    for track_index, base_length in enumerate(base_lengths):
        used_length = float(base_length)
        used_length += sum(
            length_coefficients[key][track_index] * value
            for key, value in selected.items()
        )
        used_length += sum(
            length_coefficients[key][track_index] * support[key][0]
            for key in remaining
        )
        coefficient = float(length_coefficients[index][track_index])
        length_room = (float(constraints["max_length_um"]) - used_length) / coefficient
        maximum = min(maximum, math.floor(length_room + 1e-10))
    return int(maximum)


def _quantile_summary(values: Sequence[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    quantiles = np.quantile(array, [0.05, 0.25, 0.5, 0.75, 0.95])
    return {
        "min": float(np.min(array)),
        "q05": float(quantiles[0]),
        "q25": float(quantiles[1]),
        "median": float(quantiles[2]),
        "q75": float(quantiles[3]),
        "q95": float(quantiles[4]),
        "max": float(np.max(array)),
    }


def _independent_uniform_reference(
    cfg: Mapping[str, Any], material: str, topology: str, *,
    active: np.ndarray, integer_indices: Sequence[int], seed: int, draws: int,
) -> dict[str, Any]:
    """Estimate the old independent-uniform geometry acceptance for comparison."""
    rng = np.random.default_rng(seed)
    low, high = active[:, 0], active[:, 1]
    reasons = {name: 0 for name in GEOMETRY_CONSTRAINT_NAMES}
    accepted = 0
    for _ in range(draws):
        proposed = low + rng.uniform(0.0, 1.0, len(active)) * (high - low)
        canonical = _canonical_physical(proposed, active, integer_indices)
        design = decode_design(canonical, topology, cfg)
        _, details, maximum = _geometry_status(design, cfg)
        if math.isfinite(maximum) and maximum <= 0.0:
            accepted += 1
        else:
            for name, value in details.items():
                if value > 0.0:
                    reasons[name] += 1
    rejected = draws - accepted
    return {
        "method": "independent_uniform_rejection_reference",
        "seed": int(seed),
        "candidate_draws": int(draws),
        "geometry_valid_candidates": int(accepted),
        "geometry_rejections": int(rejected),
        "geometry_rejection_fraction": float(rejected / draws) if draws else 0.0,
        "rejection_reason_counts": reasons,
    }


def sample_geometry_valid_population(
    cfg: Mapping[str, Any], material: str, topology: str, *, seed: int,
    population_size: int, max_attempts: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Build unique feasible members by conditionally sampling discrete counts."""
    if population_size < 1 or max_attempts < 0:
        raise ValueError("population_size must be positive and max_attempts non-negative")
    active, hard, integer_indices = material_bounds(cfg, material, topology)
    support = _integer_search_support(active, integer_indices)
    fixed = initial_design(material, topology, cfg)
    fixed_physical = _design_vector(fixed, topology)
    fixed_canonical = _canonical_physical(fixed_physical, active, integer_indices)
    if not np.allclose(fixed_physical, fixed_canonical, rtol=0.0, atol=1e-10):
        raise ValueError(f"known fixed seed for {material}/{topology} would be clipped or rounded")
    if np.any(fixed_canonical < hard[:, 0]) or np.any(fixed_canonical > hard[:, 1]):
        raise ValueError(f"known fixed seed for {material}/{topology} is outside optimizer hard bounds")
    roundtrip = _design_vector(decode_design(fixed_canonical, topology, cfg), topology)
    if not np.allclose(fixed_physical, roundtrip, rtol=0.0, atol=1e-10):
        raise ValueError(f"known fixed seed for {material}/{topology} fails canonical round-trip")
    if max(geometry(fixed, cfg["constraints"])[1], default=0.0) > 0:
        raise ValueError(f"known fixed seed for {material}/{topology} violates geometry")

    low, high = active[:, 0], active[:, 1]
    physical_population = [fixed_canonical.copy()]
    seen = {tuple(float(value) for value in fixed_canonical)}
    rng_seed = _sample_seed(seed, material, topology)
    rng = np.random.default_rng(rng_seed)
    draws = geometry_rejections = duplicate_rejections = 0
    rejection_reasons = {name: 0 for name in GEOMETRY_CONSTRAINT_NAMES}
    started = time.perf_counter()
    constraints = cfg["constraints"]
    model = None
    while len(physical_population) < population_size and draws < max_attempts:
        draws += 1
        candidate = low + rng.uniform(0.0, 1.0, len(active)) * (high - low)
        for index, (minimum, _maximum) in support.items():
            candidate[index] = float(minimum)
        model = _geometry_sampling_model(cfg, topology, candidate)
        minimum_design = decode_design(candidate, topology, cfg)
        _, minimum_violations, minimum_maximum = _geometry_status(minimum_design, cfg)
        if not math.isfinite(minimum_maximum) or minimum_maximum > 0.0:
            geometry_rejections += 1
            for name, value in minimum_violations.items():
                if value > 0.0:
                    rejection_reasons[name] += 1
            continue

        selected: dict[int, int] = {}
        for position, index in enumerate(integer_indices):
            remaining = integer_indices[position + 1:]
            maximum = _count_upper_bound(
                index, model=model, selected=selected, remaining=remaining,
                support=support, constraints=constraints,
            )
            minimum = support[index][0]
            if maximum < minimum:
                raise AssertionError(
                    f"conditional feasible set is empty for {material}/{topology} "
                    f"variable {index}; minimum-count geometry passed"
                )
            selected[index] = int(rng.integers(minimum, maximum + 1))
            candidate[index] = float(selected[index])

        design = decode_design(candidate, topology, cfg)
        _, violations, maximum_violation = _geometry_status(design, cfg)
        if not math.isfinite(maximum_violation) or maximum_violation > 0.0:
            raise AssertionError(
                f"conditional geometry constraints disagreed with decoder for "
                f"{material}/{topology}: {violations}"
            )
        canonical = _canonical_physical(candidate, active, integer_indices)
        if not np.array_equal(candidate, canonical):
            raise AssertionError("conditional initializer generated a value requiring clipping or rounding")
        key = tuple(float(value) for value in canonical)
        if key in seen:
            duplicate_rejections += 1
            continue
        seen.add(key)
        physical_population.append(canonical)

    accepted = len(physical_population) - 1
    stats = {
        "initializer_method": "conditional_integer_feasible_set_v1",
        "requested_population_size": int(population_size),
        "total_candidate_draws": int(draws),
        "valid_accepted_candidates": int(len(physical_population)),
        "rejected_candidates": int(geometry_rejections + duplicate_rejections),
        "geometry_rejection_fraction": float(geometry_rejections / draws) if draws else 0.0,
        "total_candidate_rejection_fraction": float(
            (geometry_rejections + duplicate_rejections) / draws
        ) if draws else 0.0,
        "fixed_seed_count": 1,
        "initial_sampling_seed": rng_seed,
        "initial_sampling_draws": draws,
        "initial_sampling_geometry_rejections": geometry_rejections,
        "initial_sampling_duplicate_rejections": duplicate_rejections,
        "initial_sampling_rejection_reason_counts": rejection_reasons,
        "random_initial_accepts": accepted,
        "unique_population_count": len(seen),
        "population_generation_time_s": float(time.perf_counter() - started),
    }
    if draws != geometry_rejections + duplicate_rejections + accepted:
        raise AssertionError("initial population sampling accounting identity failed")
    if len(physical_population) != population_size:
        raise RuntimeError(
            f"population initialization failed for {material}/{topology}: "
            f"accepted {len(physical_population)}/{population_size} after {draws} draws"
        )

    physical_array = np.asarray(physical_population, dtype=float)
    normalized = (physical_array - low) / (high - low)
    if not np.isfinite(normalized).all() or np.any(normalized < 0.0) or np.any(normalized > 1.0):
        raise AssertionError("conditional initializer produced a vector outside active search bounds")
    variable_names = {
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
    dimensions = []
    for vector in physical_array:
        design = decode_design(vector, topology, cfg)
        dims, violations = geometry(design, constraints)
        if not np.isfinite(list(dims.values())).all() or max(violations, default=0.0) > 0.0:
            raise AssertionError("diagnostic population geometry validation failed")
        dimensions.append(dims)
    stats["variable_distributions"] = {
        name: _quantile_summary(physical_array[:, index])
        for index, name in enumerate(variable_names)
    }
    stats["geometry_metric_distributions"] = {
        name: _quantile_summary([row[name] for row in dimensions])
        for name in ("length_um", "width_um", "electrodes")
    }
    stats["geometry_margin_distributions"] = {
        "max_total_acoustic_length_um": _quantile_summary(
            [float(constraints["max_length_um"]) - row["length_um"] for row in dimensions]
        ),
        "max_total_electrode_count": _quantile_summary(
            [float(constraints["max_electrodes"]) - row["electrodes"] for row in dimensions]
        ),
    }
    reference_draws = max(2048, min(10000, population_size * 32))
    reference_seed = (rng_seed ^ 0x5A17C3D1) % (2**32)
    stats["independent_uniform_reference"] = _independent_uniform_reference(
        cfg, material, topology, active=active, integer_indices=integer_indices,
        seed=reference_seed, draws=reference_draws,
    )
    return normalized, stats


class InitializerExhausted(RuntimeError):
    """Finite rejection-sampling cap reached before filling the population."""

    def __init__(self, diagnostics: Mapping[str, Any]):
        self.diagnostics = dict(diagnostics)
        super().__init__("INITIALIZER_EXHAUSTED: rejection-sampling attempt cap reached")


def _r1_variable_names(topology: str) -> tuple[str, ...]:
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
    """Make one R1-compatible independent real-uniform proposal and canonicalize it."""
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
    names = _r1_variable_names(topology)
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
    bootstrap_replicates: int = 256, study_revision: str = "R1.2",
    rng_seed_override: int | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Build a unique geometry-valid population by R1 independent rejection sampling."""
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

    rng_seed = int(rng_seed_override) if rng_seed_override is not None else int.from_bytes(hashlib.sha256(
        f"{SEMANTICS_VERSION}/r1_2_independent_rejection/{seed}/{material}/{topology}/initial_population".encode()
    ).digest()[:8], "big") % (2**32)
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
        "study_revision": str(study_revision).upper(),
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
        raise AssertionError("R1.2 initializer attempt accounting identity failed")
    if len(physical_population) != population_size:
        base_stats["failure_code"] = "INITIALIZER_EXHAUSTED"
        raise InitializerExhausted(base_stats)

    physical_array = np.asarray(physical_population, dtype=float)
    random_array = np.asarray(random_population, dtype=float)
    if np.any(physical_array < low) or np.any(physical_array > high):
        raise AssertionError("R1.2 initializer emitted a design outside the declared bounds")
    unique_count = len({tuple(float(value) for value in row) for row in physical_array})
    if unique_count != population_size:
        raise AssertionError("R1.2 initializer emitted duplicate canonical designs")
    full_metrics = _geometry_population_metrics(physical_array, cfg, topology)
    random_metrics = _geometry_population_metrics(random_array, cfg, topology)
    names = _r1_variable_names(topology)
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
        base_stats["initializer_diversity_gate_passed"] = validation["integer_diversity_passed"]
        base_stats["distribution_regression_passed"] = validation["distribution_match_passed"]
    else:
        base_stats["initializer_diversity_gate_passed"] = True
        base_stats["distribution_regression_passed"] = True
    if draws != geometry_rejections + duplicate_rejections + accepted_random:
        raise AssertionError("R1.2 initializer attempt accounting identity failed")
    normalized = (physical_array - low) / (high - low)
    if not np.isfinite(normalized).all() or np.any(normalized < 0.0) or np.any(normalized > 1.0):
        raise AssertionError("R1.2 initializer emitted a normalized vector outside [0, 1]")
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


def evaluate_r1_design(
    design: Any, provider: Any, cfg: Mapping[str, Any], frequencies_hz: np.ndarray,
    topology: str, *, rs: float = 50.0, rl: float = 50.0, include_spectrum: bool = False,
) -> dict[str, Any]:
    """Hard-gate geometry, then run unchanged Stage 3.8 COM/network/metric code."""
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


def _source_fingerprint(raw_config: str) -> str:
    hasher = hashlib.sha256()
    normalized_config = yaml.safe_load(raw_config)
    r1_settings = normalized_config.get("stage3_8c_r1", {})
    for run_specific in ("mode", "budget", "checkpoints", "seeds", "pilot_run_dir"):
        r1_settings.pop(run_specific, None)
    hasher.update(yaml.safe_dump(normalized_config, sort_keys=True).encode("utf-8"))
    hasher.update(SEMANTICS_VERSION.encode("utf-8"))
    for path in (
        Path(__file__),
        Path(__file__).with_name("stage3_8_dual_material_dms_topology_fast_screen.py"),
    ):
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def _git_state() -> dict[str, Any]:
    def run(*args: str) -> str:
        completed = subprocess.run(
            ["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False,
        )
        return completed.stdout.strip()
    return {
        "branch": run("branch", "--show-current"),
        "head": run("rev-parse", "HEAD"),
        "status": run("status", "--short"),
        "diff_summary": run("diff", "--stat"),
        "staged_diff_summary": run("diff", "--cached", "--stat"),
        "pre_r1_baseline": {
            "branch": "main",
            "head": "f2babf340f7143e44db6af83f28e2324e724f6ed",
            "status_summary": "36 tracked paths changed plus pre-existing untracked additions; 69 insertions and 16,322 deletions in git diff --stat.",
            "note": "Pre-existing user changes were present before R1 work and were preserved.",
        },
    }


def _population_size(cfg: Mapping[str, Any], topology: str, budget: int,
                     hard_bounds: np.ndarray) -> int:
    lcfg = _backend_config(cfg, topology, budget, hard_bounds)
    dimension = len(cfg["stage3_8"]["topologies"][topology]["bounds"]["active"])
    requested = int(lcfg.get("initial_population", lcfg.get("initial_population_per_dimension", 18) * dimension))
    return max(requested, int(lcfg.get("min_population", 4)))


def _evaluator(cfg, provider, topology: str, frequencies: np.ndarray,
               counters: EvaluationCounters):
    def evaluate_vector(vector):
        design = decode_design(vector, topology, cfg)
        result = evaluate_r1_design(design, provider, cfg, frequencies, topology)
        counters.observe_search(result, len(frequencies))
        return result
    return evaluate_vector


def _extract_rejection_rows(records: Sequence[Mapping[str, Any]], *, material: str,
                            topology: str, seed: int) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        if _status(record) != "GEOMETRY_REJECTED":
            continue
        rows.append({
            "material": material,
            "topology": topology,
            "seed": int(seed),
            "evaluation_status": _status(record),
            "failure_stage": record.get("failure_stage"),
            "design": json.dumps(_clean(record.get("design", {})), sort_keys=True),
            "geometry_dimensions": json.dumps(_clean(record.get("geometry_dimensions", {})), sort_keys=True),
            "violated_hard_constraints": json.dumps(_clean({
                key: value for key, value in record.get("geometry_violations", {}).items()
                if _finite(value, 0.0) > 0
            }), sort_keys=True),
            "normalized_geometry_violations": json.dumps(
                _clean(record.get("geometry_violations", {})), sort_keys=True
            ),
        })
    return rows


def select_common_grid_candidate(records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    eligible = [record for record in records if _status(record) == "PHYSICS_EVALUATED"
                and _finite_filter_outputs(record)]
    return min(eligible, key=R1_COMPARATOR.rank_key) if eligible else None


def _common_grid_select(
    search_records: Sequence[Mapping[str, Any]], provider: Any, cfg: Mapping[str, Any],
    frequencies: np.ndarray, topology: str, counters: EvaluationCounters, finalist_count: int,
) -> tuple[Mapping[str, Any] | None, list[Mapping[str, Any]]]:
    valid = [record for record in search_records if _status(record) == "PHYSICS_EVALUATED"]
    finalists = sorted(valid, key=R1_COMPARATOR.rank_key)[:max(1, int(finalist_count))]
    validated = []
    for source in finalists:
        design = decode_design(_design_vector_from_record(source["design"], topology), topology, cfg)
        counters.validation_evaluations += 1
        result = evaluate_r1_design(
            design, provider, cfg, frequencies, topology, include_spectrum=True,
        )
        result = dict(result)
        result["design"] = asdict(design)
        result["search_source_rank_key"] = list(R1_COMPARATOR.rank_key(source))
        if _status(result) == "PHYSICS_EVALUATED":
            counters.validation_solved_frequency_points += len(frequencies)
        else:
            counters.validation_physics_failures += 1
        validated.append(result)
    selected = select_common_grid_candidate(validated)
    return selected, validated


def _load_saved_common_grid_selection(
    path: Path, search_records: Sequence[Mapping[str, Any]], counters: EvaluationCounters,
    *, fingerprint: str, common_grid_id: str, finalist_count: int,
) -> tuple[Mapping[str, Any] | None, list[Mapping[str, Any]]] | None:
    if not path.is_file():
        return None
    saved = json.loads(path.read_text(encoding="utf-8"))
    if (saved.get("source_config_fingerprint") != fingerprint
            or saved.get("common_validation_grid_id") != common_grid_id):
        raise RuntimeError("saved common-grid selection fingerprint/grid does not match resumed run")
    validated = list(saved.get("validated_finalists", []))
    expected_designs = [
        json.dumps(_clean(record.get("design", {})), sort_keys=True)
        for record in sorted(
            (record for record in search_records if _status(record) == "PHYSICS_EVALUATED"),
            key=R1_COMPARATOR.rank_key,
        )[:max(1, int(finalist_count))]
    ]
    restored_designs = [
        json.dumps(_clean(record.get("design", {})), sort_keys=True) for record in validated
    ]
    if not expected_designs or sorted(restored_designs) != sorted(expected_designs):
        return None
    counters.restore_validation(saved.get("r1_counters", {}))
    selected = saved.get("selected")
    return selected, validated


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


def _population_preflight(cfg: Mapping[str, Any], material: str, topology: str,
                          seed: int, budget: int, max_attempts: int):
    active, hard, integer_indices = material_bounds(cfg, material, topology)
    population_size = _population_size(cfg, topology, budget, hard)
    if budget < population_size:
        raise ValueError(
            f"budget {budget} is below required initial population {population_size} "
            f"for {material}/{topology}"
        )
    r1_settings = cfg.get("stage3_8c_r1", {})
    revision = str(r1_settings.get("revision", "R1")).upper()
    final_confirmation = revision == "R1.2" and bool(
        r1_settings.get("final_confirmation", False)
    )
    if revision == "R1.1":
        population, sampling = sample_geometry_valid_population(
            cfg, material, topology, seed=seed, population_size=population_size,
            max_attempts=max_attempts,
        )
    else:
        effective_max_attempts = int(max_attempts)
        reference_proposals = 0
        bootstrap_replicates = 0
        if revision == "R1.2":
            effective_max_attempts = max(
                effective_max_attempts,
                int(r1_settings.get("initial_population_attempt_multiplier", 60)) * population_size,
            )
            if not final_confirmation:
                reference_proposals = int(r1_settings.get("initializer_reference_proposals", 10000))
                bootstrap_replicates = int(r1_settings.get("distribution_bootstrap_replicates", 256))
        population, sampling = sample_independent_uniform_population(
            cfg, material, topology, seed=seed, population_size=population_size,
            max_attempts=effective_max_attempts,
            reference_proposals=reference_proposals,
            bootstrap_replicates=bootstrap_replicates,
            study_revision=revision,
        )
        if final_confirmation:
            sampling["distribution_validation_status"] = "SKIPPED_FINAL_CONFIRMATION"
            sampling["initializer_diversity_validation_status"] = "SKIPPED_FINAL_CONFIRMATION"
    # Check the actual vectors submitted to initialize against the same physical
    # decoding and geometry gate used by objective evaluations.
    low, high = active[:, 0], active[:, 1]
    geometries = []
    keys = set()
    for normalized in population:
        physical = low + np.clip(normalized, 0.0, 1.0) * (high - low)
        canonical = _canonical_physical(physical, active, integer_indices)
        if not np.allclose(physical, canonical, rtol=0.0, atol=1e-10):
            raise AssertionError("initial population member changes under backend canonicalization")
        key = tuple(float(value) for value in canonical)
        if key in keys:
            raise AssertionError("initial population contains duplicate canonical designs")
        keys.add(key)
        design = decode_design(canonical, topology, cfg)
        _, violations, maximum = _geometry_status(design, cfg)
        if not math.isfinite(maximum) or maximum > 0:
            raise AssertionError("geometry-invalid design reached initial population")
        geometries.append(asdict(design))
    row = {
        "material": material,
        "topology": topology,
        "seed": int(seed),
        "population_size": population_size,
        "active_bounds": active.tolist(),
        "optimizer_hard_bounds": hard.tolist(),
        "initial_population_sampling": sampling,
        "unique_canonical_members": len(keys),
        "geometry_valid_members": len(geometries),
    }
    if revision == "R1.2":
        gate_failures = []
        if len(population) != population_size:
            gate_failures.append("accepted population does not equal requested population")
        if len(geometries) != population_size:
            gate_failures.append("accepted population is not 100% geometry-valid")
        if sampling.get("max_attempts_exceeded"):
            gate_failures.append("INITIALIZER_EXHAUSTED")
        if len(keys) != population_size:
            gate_failures.append("canonical population is not unique")
        if not final_confirmation:
            if not sampling.get("initializer_diversity_gate_passed", False):
                gate_failures.append("integer-count diversity is below the reference envelope")
            if not sampling.get("distribution_regression_passed", False):
                gate_failures.append("initializer distribution is outside the Monte Carlo reference envelope")
        runtime_limit = float(r1_settings.get("initializer_runtime_limit_s", 60.0))
        if float(sampling.get("population_generation_time_s", math.inf)) > runtime_limit:
            gate_failures.append(
                f"initializer runtime exceeded {runtime_limit:g} seconds"
            )
        row["initializer_gate_failures"] = gate_failures
        row["initializer_runtime_limit_s"] = runtime_limit
    return population, sampling, row


def _cache_key_records(backend: LShadeBackend) -> list[Mapping[str, Any]]:
    return [dict(value) for value in backend._cache.values()]


def _checkpoint_row(record: Mapping[str, Any], counters: Mapping[str, Any],
                    sampling: Mapping[str, Any], active: np.ndarray, hard: np.ndarray):
    incumbent = record
    metrics = incumbent.get("metrics", {})
    violations = incumbent.get("violations", {})
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
        comparator=R1_COMPARATOR,
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
            "event": "r1_fixed_search_grid_checkpoint",
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
            "r1_counters": snapshot,
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
            "r1_counters": snapshot,
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _material_metadata_snapshot(cfg: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = {}
    for material in MATERIALS:
        _provider_instance, metadata = _provider(material, cfg)
        snapshot[material] = {
            "profile": _clean(metadata),
            "profile_id": cfg["stage3_8"]["materials"][material]["profile_id"],
            "aperture_bounds_um": list(map(
                float, cfg["stage3_8"]["materials"][material]["aperture_bounds_um"]
            )),
            "aperture_bound_provenance": (
                "R1 user-directed bound override; Stage 3.7D archived record was 30-150 um"
                if material == "MLIT" else "Stage 3.8 continuity bound retained"
            ),
        }
    return snapshot


def _preflight_known_designs(cfg: Mapping[str, Any], search_frequencies: np.ndarray,
                             common_frequencies: np.ndarray):
    rows = []
    failures = []
    for material in MATERIALS:
        provider, _metadata = _provider(material, cfg)
        for topology in TOPOLOGIES:
            design = initial_design(material, topology, cfg)
            search_result = evaluate_r1_design(
                design, provider, cfg, search_frequencies, topology,
            )
            common_result = evaluate_r1_design(
                design, provider, cfg, common_frequencies, topology,
            )
            search_pass = _finite_required_metrics(search_result)
            common_pass = _finite_required_metrics(common_result)
            row = {
                "material": material,
                "topology": topology,
                "search_status": _status(search_result),
                "common_grid_status": _status(common_result),
                "search_frequency_count": len(search_frequencies),
                "common_frequency_count": len(common_frequencies),
                "search_metrics_finite": search_pass,
                "common_metrics_finite": common_pass,
                "geometry_valid": bool(search_result.get("geometry_valid", False)),
                "design": json.dumps(_clean(asdict(design)), sort_keys=True),
                "search_max_violation": search_result.get("max_violation"),
                "search_worst_il_db": search_result.get("metrics", {}).get("worst_il_db"),
                "common_worst_il_db": common_result.get("metrics", {}).get("worst_il_db"),
            }
            rows.append(row)
            if not search_pass or not common_pass or not row["geometry_valid"]:
                failures.append(row)
    return rows, failures


def _write_source_snapshots(out: Path, cfg: Mapping[str, Any], raw_config: str,
                            grid: np.ndarray, grid_id: str, grid_metadata_path: str,
                            fingerprint: str) -> None:
    metadata_dir = out / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (out / "input_config.yaml").write_text(raw_config, encoding="utf-8")
    revision = str(cfg.get("stage3_8c_r1", {}).get("revision", "R1")).upper()
    git_metadata = _git_state()
    if revision == "R1.1":
        baseline_path = ROOT / "reports" / "stage3_8c_r1_1_pre_work_git_state.json"
        if not baseline_path.is_file():
            raise FileNotFoundError("R1.1 pre-work Git state snapshot is required")
        git_metadata["pre_r1_1_work_baseline"] = json.loads(
            baseline_path.read_text(encoding="utf-8")
        )
    _write_json(metadata_dir / "run_source_metadata.json", {
        "study_type": STUDY_TYPE,
        "study_revision": revision,
        "semantics_version": SEMANTICS_VERSION,
        "source_config_fingerprint": fingerprint,
        "git": git_metadata,
        "initialization_policy": (
            "conditional_integer_feasible_set_v1; changes initializer distribution; diagnostic-only pilot"
            if revision == "R1.1" else "independent_uniform_rejection_v1"
        ),
        "source_config_path": str(cfg.get("_source_config_path", "")),
        "resolved_search_frequency_count": None,
        "common_validation_grid_id": grid_id,
        "common_validation_grid_count": int(len(grid)),
        "common_validation_grid_metadata_path": grid_metadata_path,
        "common_validation_grid_sha256": hashlib.sha256(grid.tobytes()).hexdigest(),
        "topology_definitions": {
            "T0": "existing generalized 3-IDT topology and port map; unchanged",
            "T1": "symmetric 5-IDT R-A-B-C-B-A-R; unchanged",
            "T2": "parallel 3-IDT x2 with unterminated Y summation and total aperture split; unchanged",
        },
        "input_output_impedance_ohm": [50.0, 50.0],
        "search_bounds_are_not_manufacturing_limits": True,
        "manufacturing_geometry_limits": cfg["constraints"],
        "material_aperture_bounds_um": {
            material: cfg["stage3_8"]["materials"][material]["aperture_bounds_um"]
            for material in MATERIALS
        },
        "mlit_aperture_provenance": {
            "r1_bound_um": cfg["stage3_8"]["materials"]["MLIT"]["aperture_bounds_um"],
            "classification": "R1 user-directed bound override",
            "archived_stage3_7d_recommendation": "30-150 um; STAGE3_8_READY_APERTURE_150",
            "archived_recommendation_csv": "runs/stage3_7d_mlit_aperture_boundary_and_metadata_final/stage3_8_aperture_bound_recommendation.csv",
            "archived_recommendation_sha256": _sha256(ROOT / "runs/stage3_7d_mlit_aperture_boundary_and_metadata_final/stage3_8_aperture_bound_recommendation.csv"),
            "r1_handoff": "docs/handoff/stage3_8c_r1_geometry_gate_correction_topology_rerun_codex_task.md",
            "r1_handoff_sha256": _sha256(ROOT / "docs/handoff/stage3_8c_r1_geometry_gate_correction_topology_rerun_codex_task.md"),
            "prior_review": "reports/escalation_log.md; Stage 3.8 decision recorded 30-150 um",
            "cross_material_comparison_limitation": "M0/MLIT results have unequal aperture search spaces and cannot isolate material-only effects.",
        },
    })
    _write_json(metadata_dir / "material_profile_snapshots.json", _material_metadata_snapshot(cfg))
    search_snapshots = {}
    for material in MATERIALS:
        search_snapshots[material] = {}
        for topology in TOPOLOGIES:
            active, hard, integers = material_bounds(cfg, material, topology)
            search_snapshots[material][topology] = {
                "active_search_bounds": active.tolist(),
                "optimizer_hard_bounds": hard.tolist(),
                "integer_indices": list(integers),
                "manufacturing_hard_limits": cfg["constraints"],
            }
    _write_json(metadata_dir / "resolved_search_space_snapshots.json", search_snapshots)
    grid_metadata = json.loads(
        (ROOT / cfg["stage3_8"]["common_validation_grid_metadata"]).read_text(encoding="utf-8")
    )
    grid_path = Path(grid_metadata["source"])
    if not grid_path.is_absolute():
        grid_path = ROOT / grid_path
    (metadata_dir / "common_validation_grid.csv").write_bytes(grid_path.read_bytes())


def _pilot_gate_status(rows: Sequence[Mapping[str, Any]]) -> tuple[bool, list[str]]:
    failures = []
    for row in rows:
        counters = row.get("r1_counters", {})
        cell = f"{row.get('material')}/{row.get('topology')}"
        if not row.get("optimizer_incumbent_geometry_valid", False):
            failures.append(f"{cell}: best search incumbent is not geometry-valid")
        if int(counters.get("geometry_valid_candidates", 0)) <= 0:
            failures.append(f"{cell}: no geometry-valid candidates")
        if int(counters.get("valid_physics_evaluations", 0)) <= 0:
            failures.append(f"{cell}: no successful physics evaluations")
        if int(counters.get("solved_frequency_points", 0)) <= 0:
            failures.append(f"{cell}: no solved frequency points")
        if not row.get("finite_search_metrics", False):
            failures.append(f"{cell}: no finite search metrics")
        if not row.get("finite_common_metrics", False):
            failures.append(f"{cell}: no finite common-grid metrics")
        if not row.get("population_initialization_passed", False):
            failures.append(f"{cell}: geometry-valid population initialization failed")
        rejection_fraction = float(row.get("geometry_rejection_fraction", 0.0))
        if rejection_fraction > 0.90:
            failures.append(f"{cell}: geometry rejection fraction exceeds 90%")
        sampling = row.get("initial_population_sampling", {})
        draws = int(sampling.get("initial_sampling_draws", 0))
        rejection = int(sampling.get("initial_sampling_geometry_rejections", 0))
        if draws and sampling.get("study_revision") == "R1.2":
            if int(sampling.get("requested_population_size", 0)) != int(
                sampling.get("valid_accepted_candidates", 0)
            ):
                failures.append(f"{cell}: initializer did not fill the requested population")
            if int(sampling.get("geometry_valid_members", 0)) != int(
                sampling.get("requested_population_size", 0)
            ):
                failures.append(f"{cell}: initializer population is not 100% geometry-valid")
            if sampling.get("max_attempts_exceeded"):
                failures.append(f"{cell}: INITIALIZER_EXHAUSTED")
            if int(sampling.get("unique_population_count", 0)) != int(
                sampling.get("requested_population_size", 0)
            ):
                failures.append(f"{cell}: canonical population contains duplicates")
            if sampling.get("initializer_diversity_validation_status") != "SKIPPED_FINAL_CONFIRMATION" and not sampling.get("initializer_diversity_gate_passed", False):
                failures.append(f"{cell}: integer-count diversity gate failed")
            if sampling.get("distribution_validation_status") != "SKIPPED_FINAL_CONFIRMATION" and not sampling.get("distribution_regression_passed", False):
                failures.append(f"{cell}: initializer distribution reference gate failed")
            if float(sampling.get("population_generation_time_s", math.inf)) > float(
                row.get("initializer_runtime_limit_s", 60.0)
            ):
                failures.append(f"{cell}: initializer runtime gate failed")
        elif draws and sampling.get("initializer_method") == "conditional_integer_feasible_set_v1":
            if rejection / draws >= 0.50:
                failures.append(f"{cell}: initial sampling geometry rejection is not below 50%")
        elif draws and rejection / draws > 0.90:
            failures.append(f"{cell}: initial sampling geometry rejection exceeds 90%")
    return not failures and len(rows) == len(TOPOLOGIES) * len(MATERIALS), failures


def _write_initializer_diagnostics(
    out: Path, population_preflight: Sequence[Mapping[str, Any]],
) -> None:
    """Write flat R1.1 initializer diagnostics without changing R1 counters."""
    summary_rows = []
    rejection_rows = []
    distribution_rows = []
    geometry_rows = []
    preflight_rows = []
    for row in population_preflight:
        sampling = row.get("initial_population_sampling", {})
        reference = sampling.get("independent_uniform_reference", {})
        preflight_rows.append({
            "material": row.get("material"),
            "topology": row.get("topology"),
            "seed": row.get("seed"),
            "status": row.get("status"),
            "failure": row.get("failure"),
            "population_size": row.get("population_size"),
            "unique_canonical_members": row.get("unique_canonical_members"),
            "geometry_valid_members": row.get("geometry_valid_members"),
            "active_bounds": json.dumps(_clean(row.get("active_bounds")), sort_keys=True),
            "optimizer_hard_bounds": json.dumps(_clean(row.get("optimizer_hard_bounds")), sort_keys=True),
            "initializer_method": sampling.get("initializer_method"),
            "initializer_diagnostics": json.dumps(_clean(sampling), sort_keys=True),
        })
        if row.get("status") != "PASS":
            continue
        common = {
            "material": row.get("material"),
            "topology": row.get("topology"),
            "seed": row.get("seed"),
        }
        summary_rows.append({
            **common,
            "initializer_method": sampling.get("initializer_method"),
            "requested_population_size": sampling.get("requested_population_size"),
            "total_candidate_draws": sampling.get("total_candidate_draws"),
            "valid_accepted_candidates": sampling.get("valid_accepted_candidates"),
            "rejected_candidates": sampling.get("rejected_candidates"),
            "geometry_rejection_fraction": sampling.get("geometry_rejection_fraction"),
            "total_candidate_rejection_fraction": sampling.get("total_candidate_rejection_fraction"),
            "geometry_rejection_count": sampling.get("initial_sampling_geometry_rejections"),
            "duplicate_count": sampling.get("initial_sampling_duplicate_rejections"),
            "unique_population_count": sampling.get("unique_population_count"),
            "population_generation_time_s": sampling.get("population_generation_time_s"),
            "random_seed": sampling.get("initial_sampling_seed"),
            "reference_candidate_draws": reference.get("candidate_draws"),
            "reference_geometry_rejection_fraction": reference.get("geometry_rejection_fraction"),
        })
        geometry_rows.append({
            **common,
            "r1_initial_geometry_rejections": R1_INITIAL_REJECTION_REFERENCE[
                str(row.get("material"))
            ][str(row.get("topology"))][0],
            "r1_initial_candidate_draws": R1_INITIAL_REJECTION_REFERENCE[
                str(row.get("material"))
            ][str(row.get("topology"))][1],
            "r1_initial_geometry_rejection_fraction": (
                R1_INITIAL_REJECTION_REFERENCE[str(row.get("material"))]
                [str(row.get("topology"))][0]
                / R1_INITIAL_REJECTION_REFERENCE[str(row.get("material"))]
                [str(row.get("topology"))][1]
            ),
            "r1_1_initializer_geometry_rejection_fraction": sampling.get("geometry_rejection_fraction"),
            "r1_1_initializer_geometry_rejections": sampling.get("initial_sampling_geometry_rejections"),
            "r1_1_initializer_candidate_draws": sampling.get("total_candidate_draws"),
            "independent_uniform_reference_rejection_fraction": reference.get("geometry_rejection_fraction"),
            "independent_uniform_reference_rejections": reference.get("geometry_rejections"),
            "independent_uniform_reference_draws": reference.get("candidate_draws"),
            "acoustic_length_margin_um": json.dumps(
                _clean(sampling.get("geometry_margin_distributions", {}).get("max_total_acoustic_length_um")),
                sort_keys=True,
            ),
            "electrode_count_margin": json.dumps(
                _clean(sampling.get("geometry_margin_distributions", {}).get("max_total_electrode_count")),
                sort_keys=True,
            ),
        })
        reason_counts = sampling.get("initial_sampling_rejection_reason_counts", {})
        for reason, count in reason_counts.items():
            rejection_rows.append({**common, "method": "conditional_initializer", "reason": reason,
                                   "rejected_candidates": int(count)})
        rejection_rows.append({
            **common, "method": "conditional_initializer", "reason": "duplicate",
            "rejected_candidates": int(sampling.get("initial_sampling_duplicate_rejections", 0)),
        })
        for reason, count in reference.get("rejection_reason_counts", {}).items():
            rejection_rows.append({**common, "method": "independent_uniform_reference",
                                   "reason": reason, "rejected_candidates": int(count)})
        for category, values in (
            ("variable", sampling.get("variable_distributions", {})),
            ("geometry_metric", sampling.get("geometry_metric_distributions", {})),
            ("geometry_margin", sampling.get("geometry_margin_distributions", {})),
        ):
            for name, quantiles in values.items():
                distribution_rows.append({**common, "category": category, "parameter": name,
                                          **quantiles})

    _write_csv(out / "stage3_8c_r1_1_initializer_summary.csv", summary_rows)
    _write_csv(out / "stage3_8c_r1_1_initializer_rejections.csv", rejection_rows)
    _write_csv(out / "stage3_8c_r1_1_initializer_distribution.csv", distribution_rows)
    _write_csv(out / "stage3_8c_r1_1_geometry_rejection_summary.csv", geometry_rows)
    _write_csv(out / "stage3_8c_r1_1_population_preflight.csv", preflight_rows)


def _comparison_rows_from_r1_run(cfg: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    comparison_runs = cfg["stage3_8c_r1"].get("comparison_runs", {})
    run_value = comparison_runs.get("R1")
    if not run_value:
        return {}
    run_dir = Path(run_value)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    source = run_dir / "stage3_8c_r1_population_preflight.csv"
    if not source.is_file():
        return {}
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    with source.open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            try:
                row["initial_population_sampling"] = ast.literal_eval(
                    row.get("initial_population_sampling") or "{}"
                )
            except (ValueError, SyntaxError):
                row["initial_population_sampling"] = {}
            rows[(str(row.get("material")), str(row.get("topology")))] = row
    return rows


def _r1_1_comparison_rows(cfg: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    comparison_runs = cfg["stage3_8c_r1"].get("comparison_runs", {})
    run_value = comparison_runs.get("R1.1")
    if not run_value:
        return {}
    run_dir = Path(run_value)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    source = run_dir / "stage3_8c_r1_1_population_preflight.csv"
    if not source.is_file():
        return {}
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    with source.open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            try:
                row["initializer_diagnostics"] = json.loads(
                    row.get("initializer_diagnostics") or "{}"
                )
            except json.JSONDecodeError:
                row["initializer_diagnostics"] = {}
            rows[(str(row.get("material")), str(row.get("topology")))] = row
    return rows


def _write_r1_2_final_confirmation_diagnostics(
    out: Path, population_preflight: Sequence[Mapping[str, Any]],
) -> None:
    """Write only the population checks needed for Final Confirmation."""
    rows = []
    for row in population_preflight:
        sampling = row.get("initial_population_sampling", {})
        rows.append({
            "material": row.get("material"),
            "topology": row.get("topology"),
            "seed": row.get("seed"),
            "status": row.get("status"),
            "requested_population_size": row.get("population_size"),
            "accepted_population_size": sampling.get("valid_accepted_candidates"),
            "geometry_valid_members": row.get("geometry_valid_members"),
            "total_attempts": sampling.get("total_candidate_draws"),
            "geometry_rejections": sampling.get("initial_sampling_geometry_rejections"),
            "duplicate_rejections": sampling.get("initial_sampling_duplicate_rejections"),
            "rejection_fraction_diagnostic_only": sampling.get("geometry_rejection_fraction"),
            "population_generation_time_s": sampling.get("population_generation_time_s"),
            "max_attempts": sampling.get("max_attempts"),
            "max_attempts_exceeded": sampling.get("max_attempts_exceeded"),
            "unique_population_count": sampling.get("unique_population_count"),
        })
    _write_csv(out / "stage3_8c_r1_2_final_confirmation_initializer_summary.csv", rows)


def _write_r1_2_initializer_diagnostics(
    out: Path, population_preflight: Sequence[Mapping[str, Any]],
    cfg: Mapping[str, Any],
) -> None:
    """Write R1.2 gate data and R1/R1.1/R1.2 initializer comparisons."""
    summary_rows = []
    attempt_rows = []
    rejection_rows = []
    distribution_rows = []
    reference_rows = []
    preflight_rows = []
    generation_comparison = []
    distribution_comparison = []
    r1_rows = _comparison_rows_from_r1_run(cfg)
    r1_1_rows = _r1_1_comparison_rows(cfg)

    for row in population_preflight:
        material = str(row.get("material"))
        topology = str(row.get("topology"))
        cell = (material, topology)
        sampling = row.get("initial_population_sampling", {})
        preflight_rows.append({
            "material": material,
            "topology": topology,
            "seed": row.get("seed"),
            "status": row.get("status"),
            "failure": row.get("failure"),
            "failure_code": row.get("failure_code"),
            "population_size": row.get("population_size"),
            "unique_canonical_members": row.get("unique_canonical_members"),
            "geometry_valid_members": row.get("geometry_valid_members"),
            "active_bounds": json.dumps(_clean(row.get("active_bounds")), sort_keys=True),
            "optimizer_hard_bounds": json.dumps(_clean(row.get("optimizer_hard_bounds")), sort_keys=True),
            "initializer_gate_failures": json.dumps(_clean(row.get("initializer_gate_failures", []))),
            "initializer_diagnostics": json.dumps(_clean(sampling), sort_keys=True),
        })
        if row.get("status") != "PASS":
            continue

        reference = sampling.get("independent_uniform_reference", {})
        summary_rows.append({
            "material": material,
            "topology": topology,
            "seed": row.get("seed"),
            "initializer_method": sampling.get("initializer_method"),
            "requested_population_size": sampling.get("requested_population_size"),
            "accepted_population_size": sampling.get("valid_accepted_candidates"),
            "geometry_valid_members": sampling.get("geometry_valid_members"),
            "total_attempts": sampling.get("total_candidate_draws"),
            "geometry_rejections": sampling.get("initial_sampling_geometry_rejections"),
            "duplicate_rejections": sampling.get("initial_sampling_duplicate_rejections"),
            "rejection_fraction": sampling.get("geometry_rejection_fraction"),
            "total_rejection_fraction_including_duplicates": sampling.get("total_candidate_rejection_fraction"),
            "attempts_per_random_accept": sampling.get("attempts_per_random_accept"),
            "population_generation_time_s": sampling.get("population_generation_time_s"),
            "max_attempts": sampling.get("max_attempts"),
            "unique_population_count": sampling.get("unique_population_count"),
            "initializer_diversity_gate_passed": sampling.get("initializer_diversity_gate_passed"),
            "distribution_regression_passed": sampling.get("distribution_regression_passed"),
            "mc_candidate_draws": reference.get("candidate_draws"),
            "mc_geometry_valid_candidates": reference.get("geometry_valid_candidates"),
            "mc_geometry_rejection_fraction": reference.get("geometry_rejection_fraction"),
            "mc_runtime_s": reference.get("population_generation_time_s"),
        })
        for outcome, count in (
            ("attempted", sampling.get("total_candidate_draws", 0)),
            ("geometry_rejected", sampling.get("initial_sampling_geometry_rejections", 0)),
            ("duplicate_rejected", sampling.get("initial_sampling_duplicate_rejections", 0)),
            ("random_accepted", sampling.get("random_initial_accepts", 0)),
        ):
            attempt_rows.append({"material": material, "topology": topology,
                                 "outcome": outcome, "count": count})
        for reason, count in sampling.get("initial_sampling_rejection_reason_counts", {}).items():
            rejection_rows.append({"material": material, "topology": topology,
                                   "method": "r1_2_initializer", "reason": reason,
                                   "rejected_candidates": count})
        rejection_rows.append({
            "material": material, "topology": topology, "method": "r1_2_initializer",
            "reason": "duplicate", "rejected_candidates": sampling.get("initial_sampling_duplicate_rejections", 0),
        })
        for category, source_name in (
            ("variable", "variable_distributions"),
            ("geometry_metric", "geometry_metric_distributions"),
            ("random_member_variable", "random_member_variable_distributions"),
            ("random_member_geometry_metric", "random_member_geometry_metric_distributions"),
        ):
            for name, values in sampling.get(source_name, {}).items():
                distribution_rows.append({"material": material, "topology": topology,
                                          "revision": "R1.2", "sample": category,
                                          "parameter": name, **values})
        for name, values in reference.get("variable_and_geometry_distributions", {}).items():
            distribution_rows.append({"material": material, "topology": topology,
                                      "revision": "R1.2_MC_reference", "sample": "mc_accepted",
                                      "parameter": name, **values})
            reference_rows.append({"material": material, "topology": topology,
                                   "parameter": name, **values,
                                   "candidate_draws": reference.get("candidate_draws"),
                                   "geometry_valid_candidates": reference.get("geometry_valid_candidates"),
                                   "geometry_rejection_fraction": reference.get("geometry_rejection_fraction"),
                                   "seed": reference.get("seed")})

        r1_comparison = r1_rows.get(cell, {})
        r1_old_sampling = r1_comparison.get("initial_population_sampling", {})
        r1_seed = r1_old_sampling.get("initial_sampling_seed")
        r1_replay_stats = None
        if r1_seed is not None:
            active, _hard, integer_indices = material_bounds(cfg, material, topology)
            replay_population, r1_replay_stats = sample_independent_uniform_population(
                cfg, material, topology, seed=int(r1_comparison.get("seed", 20260917)),
                population_size=int(r1_comparison.get("population_size", row.get("population_size", 0))),
                max_attempts=max(1, int(r1_old_sampling.get("initial_sampling_draws", 1))),
                reference_proposals=0, bootstrap_replicates=0, study_revision="R1",
                rng_seed_override=int(r1_seed),
            )
            expected_draws = int(r1_old_sampling.get("initial_sampling_draws", -1))
            expected_rejects = int(r1_old_sampling.get("initial_sampling_geometry_rejections", -1))
            r1_replay_stats["historical_replay_matches_saved_accounting"] = bool(
                r1_replay_stats.get("initial_sampling_draws") == expected_draws
                and r1_replay_stats.get("initial_sampling_geometry_rejections") == expected_rejects
            )
            physical = active[:, 0] + replay_population * (active[:, 1] - active[:, 0])
            replay_metrics = _geometry_population_metrics(physical, cfg, topology)
            for index, name in enumerate(_r1_variable_names(topology)):
                distribution_comparison.append({
                    "material": material, "topology": topology, "revision": "R1",
                    "parameter": name, **_distribution_summary(physical[:, index]),
                    "historical_replay_matches_saved_accounting": r1_replay_stats[
                        "historical_replay_matches_saved_accounting"
                    ],
                })
            for name, values in replay_metrics.items():
                distribution_comparison.append({
                    "material": material, "topology": topology, "revision": "R1",
                    "parameter": name, **_distribution_summary(values),
                    "historical_replay_matches_saved_accounting": r1_replay_stats[
                        "historical_replay_matches_saved_accounting"
                    ],
                })
        for revision, old_stats in (
            ("R1.1", r1_1_rows.get(cell, {}).get("initializer_diagnostics", {})),
            ("R1.2", sampling),
        ):
            for name, values in old_stats.get("variable_distributions", {}).items():
                distribution_comparison.append({
                    "material": material, "topology": topology, "revision": revision,
                    "parameter": name, **values,
                })
            for name, values in old_stats.get("geometry_metric_distributions", {}).items():
                distribution_comparison.append({
                    "material": material, "topology": topology, "revision": revision,
                    "parameter": name, **values,
                })
        for name, values in reference.get("variable_and_geometry_distributions", {}).items():
            distribution_comparison.append({
                "material": material, "topology": topology,
                "revision": "R1.2_MC_reference", "parameter": name, **values,
            })

        for revision, old_row, old_stats in (
            ("R1", r1_comparison, r1_replay_stats or r1_old_sampling),
            ("R1.1", r1_1_rows.get(cell, {}), r1_1_rows.get(cell, {}).get("initializer_diagnostics", {})),
            ("R1.2", row, sampling),
        ):
            generation_comparison.append({
                "material": material,
                "topology": topology,
                "revision": revision,
                "population_size": old_row.get("population_size") or old_stats.get("requested_population_size"),
                "candidate_attempts": old_stats.get("initial_sampling_draws", old_stats.get("total_candidate_draws")),
                "accepted_random": old_stats.get("random_initial_accepts"),
                "geometry_rejections": old_stats.get("initial_sampling_geometry_rejections"),
                "duplicate_rejections": old_stats.get("initial_sampling_duplicate_rejections"),
                "rejection_fraction": old_stats.get("geometry_rejection_fraction"),
                "generation_time_s": old_stats.get("population_generation_time_s"),
                "time_provenance": "historical_saved" if revision == "R1.1" else
                    "current_deterministic_replay" if revision == "R1" else "pilot_run",
                "historical_replay_matches_saved_accounting": old_stats.get(
                    "historical_replay_matches_saved_accounting"
                ),
            })

    _write_csv(out / "stage3_8c_r1_2_initializer_summary.csv", summary_rows)
    _write_csv(out / "stage3_8c_r1_2_initializer_attempts.csv", attempt_rows)
    _write_csv(out / "stage3_8c_r1_2_initializer_distribution.csv", distribution_rows)
    _write_csv(out / "stage3_8c_r1_2_geometry_rejections.csv", rejection_rows)
    _write_csv(out / "stage3_8c_r1_2_population_preflight.csv", preflight_rows)
    _write_csv(out / "stage3_8c_r1_2_initializer_reference_mc.csv", reference_rows)
    _write_csv(out / "stage3_8c_initializer_generation_comparison.csv", generation_comparison)
    _write_csv(out / "stage3_8c_initializer_distribution_comparison.csv", distribution_comparison)


def _pilot_path(cfg: Mapping[str, Any]) -> Path:
    value = cfg["stage3_8c_r1"].get("pilot_run_dir")
    if not value:
        raise ValueError("production config must name the passing R1 pilot run directory")
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _check_pilot_gate(cfg: Mapping[str, Any], source_fingerprint: str,
                      common_grid_id: str) -> None:
    pilot_dir = _pilot_path(cfg)
    revision = str(cfg.get("stage3_8c_r1", {}).get("revision", "R1")).upper()
    gate_name = {
        "R1.1": "stage3_8c_r1_1_pilot_gate.json",
        "R1.2": "stage3_8c_r1_2_pilot_gate.json",
    }.get(revision, "stage3_8c_r1_pilot_gate.json")
    gate_path = pilot_dir / gate_name
    if not gate_path.is_file():
        raise RuntimeError(f"passing pilot gate not found: {gate_path}")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if gate.get("status") != "PASS" or int(gate.get("passed_cells", 0)) != 6:
        raise RuntimeError(f"R1 pilot gate did not PASS all six cells: {gate}")
    if gate.get("source_config_fingerprint") != source_fingerprint:
        raise RuntimeError("pilot fingerprint differs from production code/search-space fingerprint")
    if gate.get("common_validation_grid_id") != common_grid_id:
        raise RuntimeError("pilot and production common validation grids differ")


def _production_candidate_fingerprint(cfg: Mapping[str, Any]) -> str:
    value = cfg.get("stage3_8c_r1", {}).get("production_candidate_config")
    if not value:
        raise RuntimeError("Final Confirmation requires production_candidate_config")
    path = Path(str(value))
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise FileNotFoundError(f"production candidate config not found: {path}")
    return _source_fingerprint(path.read_text(encoding="utf-8"))


def _audit_counter_accounting_rows(
    rows: Sequence[Mapping[str, Any]], *, materials: Sequence[str],
    topologies: Sequence[str], seeds: Sequence[int], checkpoints: Sequence[int],
) -> dict[str, Any]:
    """Compatibility wrapper for the shared checkpoint accounting validator."""
    return validate_checkpoint_lattice(
        rows, materials=materials, topologies=topologies,
        seeds=seeds, checkpoints=checkpoints,
    )


def _record_flag_is_true(value: Any) -> bool:
    return value is True or str(value).strip().lower() == "true"


def _finite_at_most(value: Any, maximum: float) -> bool:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(parsed) and parsed <= maximum


def _production_metrics_are_finite(row: Mapping[str, Any]) -> bool:
    names = (
        "search_max_violation", "search_sum_violation", "search_worst_il_db",
        "search_ripple_db", "search_input_vswr", "search_output_vswr",
        "common_grid_max_violation", "common_grid_sum_violation",
        "common_grid_worst_il_db", "common_grid_ripple_db",
        "common_grid_input_vswr", "common_grid_output_vswr",
    )
    if not _record_flag_is_true(row.get("finite_search_metrics")) or not _record_flag_is_true(
        row.get("finite_common_metrics")
    ):
        return False
    try:
        return all(math.isfinite(float(row[name])) for name in names)
    except (KeyError, TypeError, ValueError):
        return False


def _check_final_confirmation_gate(cfg: Mapping[str, Any], fingerprint: str,
                                   common_grid_id: str) -> None:
    confirmation_dir = _pilot_path(cfg)
    gate_path = confirmation_dir / "stage3_8c_r1_2_final_confirmation_gate.json"
    marker = confirmation_dir / "STAGE3_8C_R1_2_FINAL_CONFIRMATION_PASS.txt"
    if not gate_path.is_file() or not marker.is_file():
        raise RuntimeError("R1.2 Final Confirmation PASS gate/marker is missing")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    candidate_fingerprint = _production_candidate_fingerprint(cfg)
    if (gate.get("status") != "PASS"
            or gate.get("final_confirmation_fingerprint") != fingerprint
            or gate.get("production_candidate_fingerprint") != candidate_fingerprint
            or fingerprint != candidate_fingerprint
            or gate.get("common_validation_grid_id") != common_grid_id):
        raise RuntimeError("Final Confirmation gate does not match this production fingerprint/grid")
    if not all(gate.get("gates", {}).values()):
        raise RuntimeError("Final Confirmation contains a failed mandatory gate")


def _write_r1_2_final_confirmation_gate(
    out: Path, cfg: Mapping[str, Any], *, fingerprint: str,
    common_grid_id: str, pilot_gate: Mapping[str, Any],
    cell_rows: Sequence[Mapping[str, Any]],
    population_rows: Sequence[Mapping[str, Any]],
    fixed_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    r1_settings = cfg.get("stage3_8c_r1", {})
    failures: list[str] = []
    candidate_fingerprint = None
    try:
        candidate_fingerprint = _production_candidate_fingerprint(cfg)
    except (OSError, RuntimeError, ValueError) as exc:
        failures.append(f"production candidate fingerprint unavailable: {exc}")

    tests_value = r1_settings.get("final_confirmation_test_gate")
    tests_path = Path(str(tests_value)) if tests_value else Path()
    if tests_value and not tests_path.is_absolute():
        tests_path = ROOT / tests_path
    test_gate = {}
    if tests_value and tests_path.is_file():
        try:
            test_gate = json.loads(tests_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            failures.append("Final Confirmation test gate is invalid JSON")
    else:
        failures.append("Final Confirmation test gate is missing")

    source_match = bool(candidate_fingerprint and fingerprint == candidate_fingerprint)
    if not source_match:
        failures.append("final pilot and production candidate fingerprints differ")
    pilot_complete = (
        pilot_gate.get("status") == "PASS"
        and len(cell_rows) == len(MATERIALS) * len(TOPOLOGIES)
        and all(row.get("run_status") == "VALID_RUN" for row in cell_rows)
    )
    if not pilot_complete:
        failures.append("Final Confirmation pilot did not complete all six cells")

    populations_by_cell = {
        (str(row.get("material")), str(row.get("topology"))): row
        for row in population_rows
    }
    population_valid = len(populations_by_cell) == 6 and all(
        row.get("status") == "PASS"
        and int(row.get("population_size", 0)) > 0
        and int(row.get("unique_canonical_members", 0)) == int(row.get("population_size", 0))
        and int(row.get("geometry_valid_members", 0)) == int(row.get("population_size", 0))
        and not row.get("initial_population_sampling", {}).get("max_attempts_exceeded", False)
        for row in populations_by_cell.values()
    )
    if not population_valid:
        failures.append("one or more initial populations were incomplete or not geometry-valid")

    physics_valid = True
    finite_results = True
    physics_failure_count = 0
    for row in cell_rows:
        counters = row.get("r1_counters", {})
        attempted = int(counters.get("physics_attempted_evaluations", 0))
        valid = int(counters.get("valid_physics_evaluations", 0))
        solved = int(counters.get("solved_frequency_points", 0))
        physics_failures = int(counters.get("physics_failures", 0))
        physics_failure_count += physics_failures
        if attempted <= 0 or valid <= 0 or solved <= 0 or physics_failures > max(1, math.floor(attempted * 0.01)):
            physics_valid = False
        if not row.get("finite_search_metrics") or not row.get("finite_common_metrics"):
            finite_results = False
    if not physics_valid:
        failures.append("physics evaluations failed or had a non-negligible failure rate")
    if not finite_results:
        failures.append("search-grid or common-grid metrics are non-finite")

    accounting_path = out / "stage3_8c_r1_2_counter_accounting.csv"
    accounting_rows = []
    if accounting_path.is_file():
        with accounting_path.open("r", encoding="utf-8", newline="") as stream:
            accounting_rows = list(csv.DictReader(stream))
    counter_pass = len(accounting_rows) == 6 and all(
        str(row.get("counter_identity_pass", "")).lower() == "true"
        and str(row.get("physics_partition_pass", "")).lower() == "true"
        and str(row.get("valid_physics_within_geometry_valid", "")).lower() == "true"
        and str(row.get("physics_attempt_identity_pass", "")).lower() == "true"
        for row in accounting_rows
    )
    if not counter_pass:
        failures.append("counter accounting did not pass for all six cells")

    fixed_pass = len(fixed_rows) == 6 and all(
        bool(row.get("passivity"))
        and float(row.get("reciprocity_error", math.inf)) <= 1e-7
        for row in fixed_rows
    )
    if not fixed_pass:
        failures.append("fixed-design sanity did not pass 6/6")

    tests_pass = (
        test_gate.get("status") == "PASS"
        and test_gate.get("source_config_fingerprint") == fingerprint
        and test_gate.get("production_candidate_fingerprint") == candidate_fingerprint
        and test_gate.get("targeted_tests_status") == "PASS"
        and test_gate.get("full_suite_status") == "PASS"
        and test_gate.get("routing_policy_status") == "PASS"
    )
    if not tests_pass:
        failures.append("targeted/full test or GPT-6 Sol routing regression gate failed")

    gates = {
        "source_config_identity": source_match,
        "pilot_completion_6_of_6": pilot_complete,
        "initial_population_100_percent_geometry_valid": population_valid,
        "physics_evaluations_valid": physics_valid,
        "finite_search_and_common_metrics": finite_results,
        "counter_accounting": counter_pass,
        "fixed_design_sanity_6_of_6": fixed_pass,
        "targeted_full_and_routing_tests": tests_pass,
    }
    status = "PASS" if all(gates.values()) and not failures else "FAIL"
    gate = {
        "schema_version": 1,
        "study_revision": "R1.2",
        "confirmation_type": "final_confirmation",
        "status": status,
        "run_dir": str(out),
        "final_confirmation_fingerprint": fingerprint,
        "production_candidate_fingerprint": candidate_fingerprint,
        "common_validation_grid_id": common_grid_id,
        "pilot_cells_completed": sum(row.get("run_status") == "VALID_RUN" for row in cell_rows),
        "pilot_cells_total": 6,
        "population_cells_passed": sum(
            row.get("status") == "PASS" and int(row.get("population_size", 0)) == int(row.get("geometry_valid_members", -1))
            for row in population_rows
        ),
        "physics_failure_count": physics_failure_count,
        "counter_accounting_cells_passed": sum(
            str(row.get("counter_identity_pass", "")).lower() == "true"
            and str(row.get("physics_partition_pass", "")).lower() == "true"
            and str(row.get("valid_physics_within_geometry_valid", "")).lower() == "true"
            and str(row.get("physics_attempt_identity_pass", "")).lower() == "true"
            for row in accounting_rows
        ),
        "fixed_design_cells_passed": sum(
            bool(row.get("passivity")) and float(row.get("reciprocity_error", math.inf)) <= 1e-7
            for row in fixed_rows
        ),
        "tests": test_gate,
        "gates": gates,
        "failures": failures,
        "production_started": False,
    }
    gate_path = out / "stage3_8c_r1_2_final_confirmation_gate.json"
    _write_json(gate_path, gate)
    pass_marker = out / "STAGE3_8C_R1_2_FINAL_CONFIRMATION_PASS.txt"
    fail_marker = out / "STAGE3_8C_R1_2_FINAL_CONFIRMATION_FAIL_STOP.txt"
    if status == "PASS":
        pass_marker.write_text(pass_marker.stem + "\n", encoding="utf-8")
        fail_marker.unlink(missing_ok=True)
    else:
        fail_marker.write_text(fail_marker.stem + "\n", encoding="utf-8")
        pass_marker.unlink(missing_ok=True)
    summary_lines = [
        "# Stage 3.8C-R1.2 Final Confirmation Summary", "",
        f"- Status: **{status}**", f"- Fingerprint: **{'MATCH' if source_match else 'MISMATCH'}**",
        f"- Final pilot fingerprint: `{fingerprint}`",
        f"- Production candidate fingerprint: `{candidate_fingerprint}`",
        f"- Pilot cells: {gate['pilot_cells_completed']} / 6 PASS",
        f"- Initial populations: {gate['population_cells_passed']} / 6 geometry-valid",
        f"- Physics-valid cells: {sum(bool(row.get('r1_counters', {}).get('valid_physics_evaluations', 0)) and bool(row.get('r1_counters', {}).get('solved_frequency_points', 0)) for row in cell_rows)} / 6",
        f"- Finite search/common metrics: {sum(bool(row.get('finite_search_metrics')) and bool(row.get('finite_common_metrics')) for row in cell_rows)} / 6",
        f"- Counter accounting: {gate['counter_accounting_cells_passed']} / 6 PASS",
        f"- Fixed-design sanity: {gate['fixed_design_cells_passed']} / 6 PASS",
        f"- Tests: {'PASS' if tests_pass else 'FAIL'}",
        "- Production transition is authorized only after this PASS marker and fingerprint gate are recorded.",
        "",
    ]
    if failures:
        summary_lines.extend(["## Failures", "", *[f"- {item}" for item in failures], ""])
    (out / "stage3_8c_r1_2_final_confirmation_summary.md").write_text(
        "\n".join(summary_lines), encoding="utf-8",
    )
    return gate


def run_stage38c_r1(config_path: str | Path, run_path: str | Path, *, resume: bool = False):
    """Run a gated pilot or an explicitly confirmed R1.2 production screen."""
    cfg = load_experiment_config(config_path)
    cfg = dict(cfg)
    cfg["_source_config_path"] = str(Path(config_path).resolve())
    r1 = cfg["stage3_8c_r1"]
    revision = str(r1.get("revision", "R1")).upper()
    if revision not in {"R1", "R1.1", "R1.2"}:
        raise ValueError("stage3_8c_r1.revision must be R1, R1.1, or R1.2")
    mode = str(r1.get("mode", "")).lower()
    if mode not in {"pilot", "production"}:
        raise ValueError("stage3_8c_r1.mode must be pilot or production")
    final_confirmation = bool(r1.get("final_confirmation", False))
    if revision == "R1.1" and mode != "pilot":
        raise ValueError("R1.1 is a pilot-only revision; production is not authorized")
    if revision == "R1.2" and mode != "pilot" and not final_confirmation:
        raise ValueError("R1.2 production requires Final Confirmation authorization")
    if final_confirmation and revision != "R1.2":
        raise ValueError("Final Confirmation authorization is valid only for R1.2")
    pilot_fail_marker = {
        "R1.1": "STAGE3_8C_R1_1_PILOT_FAIL_STOP",
        "R1.2": "STAGE3_8C_R1_2_PILOT_FAIL_STOP",
    }.get(revision, PILOT_FAIL)
    pilot_pass_marker = {
        "R1.1": "STAGE3_8C_R1_1_PILOT_PASS_AWAITING_REVIEW",
        "R1.2": "STAGE3_8C_R1_2_PILOT_PASS_AWAITING_REVIEW",
    }.get(revision, "STAGE3_8C_R1_PILOT_PASS_WAITING_FOR_PRODUCTION_LAUNCH")
    out = Path(run_path).resolve()
    orchestration_files = {
        "run_manifest.json", "status.json", "session_checkpoint.json",
        "stdout.log", "stderr.log", "callback.log",
    }
    if out.exists() and not resume:
        unexpected = [item.name for item in out.iterdir() if item.name not in orchestration_files]
        if unexpected:
            raise FileExistsError(f"R1 run directory is not fresh: {out}; found {unexpected}")
    out.mkdir(parents=True, exist_ok=True)
    raw_config = Path(config_path).read_text(encoding="utf-8")
    fingerprint = _source_fingerprint(raw_config)
    common_frequencies, common_grid_id, grid_metadata_path = _load_common_grid(cfg)
    if mode == "production":
        _check_pilot_gate(cfg, fingerprint, common_grid_id)
        if revision == "R1.2":
            _check_final_confirmation_gate(cfg, fingerprint, common_grid_id)
    search_frequencies = np.unique(search_grid(cfg["spec"], cfg))
    _write_source_snapshots(
        out, cfg, raw_config, common_frequencies, common_grid_id,
        grid_metadata_path, fingerprint,
    )
    source_metadata_path = out / "metadata" / "run_source_metadata.json"
    source_metadata = json.loads(source_metadata_path.read_text(encoding="utf-8"))
    source_metadata["resolved_search_frequency_count"] = int(len(search_frequencies))
    source_metadata["resolved_search_frequency_sha256"] = hashlib.sha256(search_frequencies.tobytes()).hexdigest()
    source_metadata["mode"] = mode
    source_metadata["study_revision"] = revision
    source_metadata["initializer_method"] = (
        "conditional_integer_feasible_set_v1" if revision == "R1.1"
        else "independent_uniform_rejection_v1"
    )
    source_metadata["budget"] = int(r1["budget"])
    source_metadata["seeds"] = list(map(int, r1["seeds"]))
    _write_json(source_metadata_path, source_metadata)

    def stop_preflight(details: Mapping[str, Any], *,
                       population_rows: Sequence[Mapping[str, Any]] = (),
                       known: Sequence[Mapping[str, Any]] = (),
                       fixed: Sequence[Mapping[str, Any]] = ()):
        result = _stop_run(out, pilot_fail_marker if mode == "pilot" else SEARCH_REDESIGN, details)
        if revision == "R1.2" and mode == "pilot":
            if final_confirmation:
                _write_r1_2_final_confirmation_diagnostics(out, population_rows)
            else:
                _write_r1_2_initializer_diagnostics(out, population_rows, cfg)
            fail_gate = {
                "status": "FAIL",
                "mode": "pilot",
                "study_revision": revision,
                "passed_cells": 0,
                "total_cells": len(MATERIALS) * len(TOPOLOGIES),
                "failures": [details.get("reason", "R1.2 preflight failed")],
                "run_dir": str(out),
                "source_config_fingerprint": fingerprint,
                "common_validation_grid_id": common_grid_id,
                "performance_interpretation": "diagnostic_only",
                "promotion_eligible": False,
                "seed_consistency": "N/A_single_seed",
                "production_started": False,
                "initializer_method": "independent_uniform_rejection_v1",
            }
            _write_json(out / "stage3_8c_r1_2_pilot_gate.json", fail_gate)
            if final_confirmation:
                confirmation_gate = _write_r1_2_final_confirmation_gate(
                    out, cfg, fingerprint=fingerprint,
                    common_grid_id=common_grid_id, pilot_gate=fail_gate,
                    cell_rows=(), population_rows=population_rows,
                    fixed_rows=fixed,
                )
                result["status"] = (
                    "STAGE3_8C_R1_2_FINAL_CONFIRMATION_FAIL_STOP"
                    if confirmation_gate.get("status") != "PASS" else result["status"]
                )
            else:
                _write_pilot_summary_report(out, fail_gate, ())
                _write_r1_review_bundle(
                    out, cfg, "pilot", (), (), population_rows, known, fixed, (), fail_gate,
                )
        return result

    implementation = implementation_validation(cfg)
    _write_json(out / "stage3_8c_r1_implementation_validation.json", implementation)
    if implementation.get("status") != "PASS":
        return stop_preflight({"reason": "Stage 3.8 topology implementation validation failed"})

    fixed_rows = fixed_design_sanity(out, cfg, common_frequencies)
    if revision == "R1.1":
        _write_csv(out / "stage3_8c_r1_1_fixed_design_sanity.csv", fixed_rows)
    elif revision == "R1.2":
        _write_csv(out / "stage3_8c_r1_2_fixed_design_sanity.csv", fixed_rows)
    fixed_failures = [row for row in fixed_rows if not row.get("passivity", False)
                      or float(row.get("reciprocity_error", math.inf)) > 1e-7]
    known_rows, known_failures = _preflight_known_designs(cfg, search_frequencies, common_frequencies)
    _write_csv(out / "stage3_8c_r1_known_seed_preflight.csv", known_rows)
    if fixed_failures or known_failures or len(known_rows) != 6:
        return stop_preflight({
            "reason": "fixed-design sanity or known seed did not pass on search/common grids",
            "fixed_design_failures": fixed_failures,
            "known_seed_failures": known_failures,
        }, known=known_rows, fixed=fixed_rows)

    budget = int(r1["budget"])
    seeds = tuple(int(value) for value in r1["seeds"])
    checkpoints = tuple(int(value) for value in r1.get("checkpoints", [budget]))
    if not seeds or max(checkpoints) != budget:
        raise ValueError("R1 checkpoints must end at the configured unique-evaluation budget")
    max_attempts = int(r1.get("max_initial_population_attempts", 10000))
    population_preflight = []
    preflight_sampling = {}
    preflight_errors = []
    for material in MATERIALS:
        for topology in TOPOLOGIES:
            for seed in seeds:
                try:
                    _population, sampling, row = _population_preflight(
                        cfg, material, topology, seed, budget, max_attempts,
                    )
                    row["status"] = "FAIL" if row.get("initializer_gate_failures") else "PASS"
                    population_preflight.append(row)
                    if row["status"] == "FAIL":
                        row["failure"] = "; ".join(row["initializer_gate_failures"])
                        preflight_errors.append(row)
                    else:
                        preflight_sampling[(material, topology, seed)] = sampling
                except InitializerExhausted as exc:
                    row = {
                        "material": material, "topology": topology, "seed": seed,
                        "status": "FAIL", "failure_code": "INITIALIZER_EXHAUSTED",
                        "failure": str(exc), "initial_population_sampling": exc.diagnostics,
                        "population_size": exc.diagnostics.get("requested_population_size"),
                    }
                    population_preflight.append(row)
                    preflight_errors.append(row)
                except (ValueError, RuntimeError, AssertionError) as exc:
                    row = {"material": material, "topology": topology, "seed": seed,
                           "status": "FAIL", "failure": f"{type(exc).__name__}: {exc}"}
                    population_preflight.append(row)
                    preflight_errors.append(row)
    _write_csv(out / "stage3_8c_r1_population_preflight.csv", population_preflight)
    if revision == "R1.1":
        _write_initializer_diagnostics(out, population_preflight)
    elif revision == "R1.2" and final_confirmation:
        _write_r1_2_final_confirmation_diagnostics(out, population_preflight)
    elif revision == "R1.2":
        _write_r1_2_initializer_diagnostics(out, population_preflight, cfg)
    if preflight_errors:
        return stop_preflight({
            "reason": "not all geometry-valid initial populations could be constructed",
            "failures": preflight_errors,
        }, population_rows=population_preflight, known=known_rows, fixed=fixed_rows)

    cell_rows = []
    checkpoint_rows = []
    rejection_rows = []
    response_rows = []
    for material in MATERIALS:
        provider, _profile = _provider(material, cfg)
        for topology in TOPOLOGIES:
            for seed in seeds:
                sampling = preflight_sampling[(material, topology, seed)]
                records, backend, counters, _sampling = _optimize_cell(
                    out, cfg, material, topology, seed, provider, search_frequencies,
                    budget=budget, checkpoints=checkpoints, fingerprint=fingerprint,
                    sampling_seed_data=sampling, max_attempts=max_attempts, resume=resume,
                )
                last = dict(records[-1])
                cache_records = _cache_key_records(backend)
                rejection_rows.extend(_extract_rejection_rows(
                    cache_records, material=material, topology=topology, seed=seed,
                ))
                cell_dir = out / "optimization" / material / topology / f"seed{seed}"
                selection_path = cell_dir / "final_common_grid_selection.json"
                finalist_count = int(r1.get("common_grid_finalists", 16))
                restored_selection = (
                    _load_saved_common_grid_selection(
                        selection_path, cache_records, counters,
                        fingerprint=fingerprint, common_grid_id=common_grid_id,
                        finalist_count=finalist_count,
                    ) if resume else None
                )
                if restored_selection is not None:
                    selected, validated_finalists = restored_selection
                    validation_elapsed = 0.0
                    persisted_validation_elapsed = float(
                        json.loads(selection_path.read_text(encoding="utf-8")).get(
                            "validation_wall_time_s", 0.0
                        )
                    )
                else:
                    validation_started = time.monotonic()
                    selected, validated_finalists = _common_grid_select(
                        cache_records, provider, cfg, common_frequencies, topology,
                        counters, finalist_count,
                    )
                    validation_elapsed = time.monotonic() - validation_started
                    persisted_validation_elapsed = validation_elapsed
                elapsed_total = float(last.get("elapsed_s", 0.0)) + validation_elapsed
                snapshot = _counter_snapshot(
                    backend, counters, len(search_frequencies),
                    elapsed_total,
                )
                search_best = backend.incumbent() or {}
                is_final_valid = (
                    _status(search_best) == "PHYSICS_EVALUATED"
                    and bool(search_best.get("geometry_valid", False))
                    and _finite_required_metrics(search_best)
                )
                common_valid = selected is not None and _finite_required_metrics(selected)
                rejection_fraction = _geometry_rejection_fraction(snapshot)
                valid_fraction = _valid_physics_fraction(snapshot)
                run_valid = is_final_valid and common_valid and (
                    snapshot["valid_physics_evaluations"] > 0
                    and snapshot["solved_frequency_points"] > 0
                )
                final_metrics = selected.get("metrics", {}) if selected else {}
                best_metrics = search_best.get("metrics", {})
                row = {
                    "material": material,
                    "topology": topology,
                    "seed": int(seed),
                    "mode": mode,
                    "run_status": "VALID_RUN" if run_valid else "INVALID_RUN",
                    "optimizer_incumbent_status": _status(search_best),
                    "optimizer_incumbent_geometry_valid": bool(search_best.get("geometry_valid", False)),
                    "optimizer_incumbent_max_violation": search_best.get("max_violation"),
                    "optimizer_incumbent_sum_violation": search_best.get("sum_violation"),
                    "optimizer_incumbent_metrics": best_metrics,
                    "common_grid_status": _status(selected or {}),
                    "common_grid_geometry_valid": bool((selected or {}).get("geometry_valid", False)),
                    "common_grid_max_violation": (selected or {}).get("max_violation"),
                    "common_grid_sum_violation": (selected or {}).get("sum_violation"),
                    "common_grid_metrics": final_metrics,
                    "common_grid_violations": (selected or {}).get("violations", {}),
                    "common_grid_filter_feasible": bool((selected or {}).get("filter_feasible", False)),
                    "selected_design": (selected or {}).get("design", search_best.get("design", {})),
                    "optimizer_geometry_violations": search_best.get("geometry_violations", {}),
                    "optimizer_geometry_dimensions": search_best.get("geometry_dimensions", {}),
                    "active_bounds": last.get("active_bounds"),
                    "optimizer_hard_bounds": last.get("optimizer_hard_bounds"),
                    "initial_population_sampling": sampling,
                    "r1_counters": snapshot,
                    "valid_physics_fraction": valid_fraction,
                    "geometry_rejection_fraction": rejection_fraction,
                    "finite_search_metrics": _finite_required_metrics(search_best),
                    "finite_common_metrics": common_valid,
                    "population_initialization_passed": True,
                    "search_frequency_count": len(search_frequencies),
                    "common_validation_grid_count": len(common_frequencies),
                    "common_validation_grid_id": common_grid_id,
                    "wall_time_s": snapshot["elapsed_s"],
                    "source_config_fingerprint": fingerprint,
                }
                cell_rows.append(row)
                for checkpoint_record in records:
                    snapshot_at_checkpoint = checkpoint_record.get("r1_counters", {})
                    checkpoint_rows.append(_checkpoint_row(
                        checkpoint_record, snapshot_at_checkpoint, sampling,
                        np.asarray(checkpoint_record.get("active_bounds"), dtype=float),
                        np.asarray(checkpoint_record.get("optimizer_hard_bounds"), dtype=float),
                    ))
                if selected and selected.get("spectrum"):
                    for frequency, s11_db, s21_db in zip(
                        selected["spectrum"]["frequency_hz"],
                        selected["spectrum"]["s11_db"],
                        selected["spectrum"]["s21_db"],
                    ):
                        response_rows.append({
                            "material": material,
                            "topology": topology,
                            "seed": seed,
                            "frequency_hz": frequency,
                            "s11_db": s11_db,
                            "s21_db": s21_db,
                        })
                last["r1_counters"] = snapshot
                last["common_grid_selection"] = {
                    "evaluation_status": _status(selected or {}),
                    "selected_design": (selected or {}).get("design"),
                    "metrics": final_metrics,
                    "finalist_count": len(validated_finalists),
                    "common_validation_grid_id": common_grid_id,
                }
                last["validation_wall_time_s"] = float(
                    last.get("validation_wall_time_s", 0.0) + validation_elapsed
                )
                last["elapsed_s"] = elapsed_total
                last["total_trial_wall_time_s"] = elapsed_total
                save(cell_dir / f"B{budget}.json", _clean(last))
                _write_json(selection_path, {
                    "selected": _clean(selected) if selected else None,
                    "validated_finalists": [
                        {key: value for key, value in candidate.items() if key != "spectrum"}
                        for candidate in validated_finalists
                    ],
                    "common_validation_grid_id": common_grid_id,
                    "source_config_fingerprint": fingerprint,
                    "search_unique_evaluations": int(snapshot["unique_decoded_evaluations"]),
                    "validation_wall_time_s": persisted_validation_elapsed,
                    "r1_counters": snapshot,
                })
                metadata_path = cell_dir / "trajectory_metadata.json"
                if metadata_path.is_file():
                    trajectory_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    trajectory_metadata["cumulative_wall_time_s"] = elapsed_total
                    trajectory_metadata["r1_counters"] = snapshot
                    trajectory_metadata["common_validation_grid_id"] = common_grid_id
                    trajectory_metadata["validation_wall_time_s"] = persisted_validation_elapsed
                    _write_json(metadata_path, trajectory_metadata)

    _write_csv(out / "stage3_8c_r1_all_seed_results.csv", [
        _flat_cell_row(row) for row in cell_rows
    ])
    if mode == "pilot":
        _copy_if_exists(out / "stage3_8c_r1_all_seed_results.csv",
                        out / "stage3_8c_r1_pilot_results.csv")
    else:
        _copy_if_exists(_pilot_path(cfg) / "stage3_8c_r1_pilot_results.csv",
                        out / "stage3_8c_r1_pilot_results.csv")
    _write_csv(out / "stage3_8c_r1_checkpoint_results.csv", checkpoint_rows)
    _write_csv(out / "stage3_8c_r1_geometry_rejections.csv", rejection_rows)
    _write_csv(out / "stage3_8c_r1_validated_responses.csv", response_rows)
    _write_derived_csvs(out, cell_rows, checkpoint_rows)
    if revision == "R1.1":
        aliases = {
            "stage3_8c_r1_1_all_seed_results.csv": "stage3_8c_r1_all_seed_results.csv",
            "stage3_8c_r1_1_pilot_results.csv": "stage3_8c_r1_pilot_results.csv",
            "stage3_8c_r1_1_checkpoint_results.csv": "stage3_8c_r1_checkpoint_results.csv",
            "stage3_8c_r1_1_geometry_rejections.csv": "stage3_8c_r1_geometry_rejections.csv",
            "stage3_8c_r1_1_counter_accounting.csv": "stage3_8c_r1_counter_accounting.csv",
            "stage3_8c_r1_1_boundary_diagnostics.csv": "stage3_8c_r1_boundary_diagnostics.csv",
            "stage3_8c_r1_1_constraint_bottlenecks.csv": "stage3_8c_r1_constraint_bottlenecks.csv",
            "stage3_8c_r1_1_compute_cost.csv": "stage3_8c_r1_compute_cost.csv",
            "stage3_8c_r1_1_topology_summary_by_material.csv": "stage3_8c_r1_topology_summary_by_material.csv",
            "stage3_8c_r1_1_cross_material_ranking.csv": "stage3_8c_r1_cross_material_ranking.csv",
            "stage3_8c_r1_1_validated_responses.csv": "stage3_8c_r1_validated_responses.csv",
        }
        for destination_name, source_name in aliases.items():
            source = out / source_name
            if source.is_file():
                (out / destination_name).write_bytes(source.read_bytes())
        if len(seeds) == 1:
            ranking_path = out / "stage3_8c_r1_cross_material_ranking.csv"
            if ranking_path.is_file():
                ranking_rows = list(csv.DictReader(ranking_path.open(encoding="utf-8", newline="")))
                for ranking_row in ranking_rows:
                    ranking_row["promotion_eligible"] = "false"
                    ranking_row["seed_consistency"] = "N/A_single_seed"
                    ranking_row["performance_interpretation"] = "diagnostic_only"
                _write_csv(out / "stage3_8c_r1_cross_material_ranking.csv", ranking_rows)
                _write_csv(out / "stage3_8c_r1_1_cross_material_ranking.csv", ranking_rows)

    if revision == "R1.2":
        aliases = {
            "stage3_8c_r1_2_all_seed_results.csv": "stage3_8c_r1_all_seed_results.csv",
            "stage3_8c_r1_2_pilot_results.csv": "stage3_8c_r1_pilot_results.csv",
            "stage3_8c_r1_2_checkpoint_results.csv": "stage3_8c_r1_checkpoint_results.csv",
            "stage3_8c_r1_2_geometry_rejections.csv": "stage3_8c_r1_geometry_rejections.csv",
            "stage3_8c_r1_2_counter_accounting.csv": "stage3_8c_r1_counter_accounting.csv",
            "stage3_8c_r1_2_boundary_diagnostics.csv": "stage3_8c_r1_boundary_diagnostics.csv",
            "stage3_8c_r1_2_constraint_bottlenecks.csv": "stage3_8c_r1_constraint_bottlenecks.csv",
            "stage3_8c_r1_2_compute_cost.csv": "stage3_8c_r1_compute_cost.csv",
            "stage3_8c_r1_2_topology_summary_by_material.csv": "stage3_8c_r1_topology_summary_by_material.csv",
            "stage3_8c_r1_2_cross_material_ranking.csv": "stage3_8c_r1_cross_material_ranking.csv",
            "stage3_8c_r1_2_validated_responses.csv": "stage3_8c_r1_validated_responses.csv",
            "stage3_8c_r1_2_fixed_design_sanity.csv": "stage3_8c_r1_2_fixed_design_sanity.csv",
        }
        for destination_name, source_name in aliases.items():
            source = out / source_name
            if source.is_file():
                (out / destination_name).write_bytes(source.read_bytes())
        if len(seeds) == 1:
            ranking_path = out / "stage3_8c_r1_cross_material_ranking.csv"
            if ranking_path.is_file():
                ranking_rows = list(csv.DictReader(ranking_path.open(encoding="utf-8", newline="")))
                for ranking_row in ranking_rows:
                    ranking_row["promotion_eligible"] = "false"
                    ranking_row["seed_consistency"] = "N/A_single_seed"
                    ranking_row["performance_interpretation"] = "diagnostic_only"
                _write_csv(ranking_path, ranking_rows)
                _write_csv(out / "stage3_8c_r1_2_cross_material_ranking.csv", ranking_rows)

    gate_pass = False
    gate_failures = []
    if mode == "pilot":
        gate_pass, gate_failures = _pilot_gate_status(cell_rows)
        gate = {
            "status": "PASS" if gate_pass else "FAIL",
            "mode": "pilot",
            "study_revision": revision,
            "passed_cells": sum(1 for row in cell_rows if row.get("run_status") == "VALID_RUN"),
            "total_cells": len(MATERIALS) * len(TOPOLOGIES),
            "failures": gate_failures,
            "run_dir": str(out),
            "source_config_fingerprint": fingerprint,
            "common_validation_grid_id": common_grid_id,
            "performance_interpretation": "diagnostic_only",
            "promotion_eligible": False,
            "seed_consistency": "N/A_single_seed" if len(seeds) == 1 else "not_applicable",
            "production_started": False,
            "initializer_method": (
                "conditional_integer_feasible_set_v1" if revision == "R1.1"
                else "independent_uniform_rejection_v1"
            ),
            "initializer_gates": (
                "R1.2_final_confirmation_population_geometry_runtime"
                if revision == "R1.2" and final_confirmation else
                "R1.2_population_geometry_diversity_runtime_distribution"
                if revision == "R1.2" else None
            ),
        }
        _write_json(out / "stage3_8c_r1_pilot_gate.json", gate)
        gate_path = out / "stage3_8c_r1_pilot_gate.json"
        if revision == "R1.1":
            gate_path = out / "stage3_8c_r1_1_pilot_gate.json"
            gate_path.write_text(json.dumps(_clean(gate), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        elif revision == "R1.2":
            gate_path = out / "stage3_8c_r1_2_pilot_gate.json"
            gate_path.write_text(json.dumps(_clean(gate), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if not gate_pass:
            (out / f"{pilot_fail_marker}.txt").write_text(pilot_fail_marker + "\n", encoding="utf-8")
            if final_confirmation:
                confirmation_gate = _write_r1_2_final_confirmation_gate(
                    out, cfg, fingerprint=fingerprint,
                    common_grid_id=common_grid_id, pilot_gate=gate,
                    cell_rows=cell_rows, population_rows=population_preflight,
                    fixed_rows=fixed_rows,
                )
                return {
                    "status": "STAGE3_8C_R1_2_FINAL_CONFIRMATION_FAIL_STOP",
                    "run": str(out),
                    "gate": confirmation_gate,
                }
            _write_pilot_summary_report(out, gate, cell_rows)
            _write_r1_review_bundle(out, cfg, mode, cell_rows, checkpoint_rows,
                                    population_preflight, known_rows, fixed_rows,
                                    response_rows, gate)
            return {"status": pilot_fail_marker, "run": str(out), "gate": gate}
        summary_path = gate_path
        (out / f"{pilot_pass_marker}.txt").write_text(
            pilot_pass_marker + "\n", encoding="utf-8"
        )
        if final_confirmation:
            confirmation_gate = _write_r1_2_final_confirmation_gate(
                out, cfg, fingerprint=fingerprint,
                common_grid_id=common_grid_id, pilot_gate=gate,
                cell_rows=cell_rows, population_rows=population_preflight,
                fixed_rows=fixed_rows,
            )
            return {
                "status": (
                    "STAGE3_8C_R1_2_FINAL_CONFIRMATION_PASS"
                    if confirmation_gate.get("status") == "PASS"
                    else "STAGE3_8C_R1_2_FINAL_CONFIRMATION_FAIL_STOP"
                ),
                "run": str(out),
                "gate": str(out / "stage3_8c_r1_2_final_confirmation_gate.json"),
            }
        _write_pilot_summary_report(out, gate, cell_rows)
        _write_r1_review_bundle(out, cfg, mode, cell_rows, checkpoint_rows,
                                population_preflight, known_rows, fixed_rows,
                                response_rows, gate)
        return {"status": pilot_pass_marker, "run": str(out), "gate": str(summary_path)}

    (out / f"{MAIN_COMPLETE}.txt").write_text(MAIN_COMPLETE + "\n", encoding="utf-8")
    if revision == "R1.2":
        production_rows = len(MATERIALS) * len(TOPOLOGIES) * len(seeds)
        valid_rows = [row for row in cell_rows if row.get("run_status") == "VALID_RUN"]
        expected_evaluations = budget * production_rows
        completed_evaluations = sum(
            int(row.get("r1_counters", {}).get("unique_decoded_evaluations", 0))
            for row in cell_rows
        )
        accounting_path = out / "stage3_8c_r1_2_counter_accounting.csv"
        accounting_rows = []
        if accounting_path.is_file():
            with accounting_path.open("r", encoding="utf-8", newline="") as stream:
                accounting_rows = list(csv.DictReader(stream))
        counter_audit = _audit_counter_accounting_rows(
            accounting_rows, materials=MATERIALS, topologies=TOPOLOGIES,
            seeds=seeds, checkpoints=checkpoints,
        )
        counter_pass = bool(counter_audit["passed"])
        by_cell: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
        for row in cell_rows:
            by_cell.setdefault((str(row.get("material")), str(row.get("topology"))), []).append(row)
        cells_completed = sum(
            len(rows) == len(seeds) and all(row.get("run_status") == "VALID_RUN" for row in rows)
            for rows in by_cell.values()
        )
        physics_failures = sum(
            int(row.get("r1_counters", {}).get("physics_failures", 0))
            for row in cell_rows
        )
        finite_production_metrics = len(cell_rows) == production_rows and all(
            _production_metrics_are_finite(row) for row in cell_rows
        )
        common_grid_validation_pass = len(cell_rows) == production_rows and all(
            row.get("common_grid_status") == "PHYSICS_EVALUATED"
            and _record_flag_is_true(row.get("common_grid_geometry_valid"))
            and row.get("common_validation_grid_id") == common_grid_id
            for row in cell_rows
        )
        final_gate_path = _pilot_path(cfg) / "stage3_8c_r1_2_final_confirmation_gate.json"
        production_fingerprint_match = final_gate_path.is_file()
        final_gate = json.loads(final_gate_path.read_text(encoding="utf-8")) if production_fingerprint_match else {}
        production_fingerprint_match = (
            production_fingerprint_match
            and final_gate.get("status") == "PASS"
            and final_gate.get("final_confirmation_fingerprint") == fingerprint
            and final_gate.get("production_candidate_fingerprint") == fingerprint
            and all(row.get("source_config_fingerprint") == fingerprint for row in cell_rows)
        )
        fixed_sanity_path = out / "stage3_8c_r1_2_fixed_design_sanity.csv"
        fixed_sanity_rows = []
        if fixed_sanity_path.is_file():
            with fixed_sanity_path.open("r", encoding="utf-8", newline="") as stream:
                fixed_sanity_rows = list(csv.DictReader(stream))
        fixed_design_sanity_pass = len(fixed_sanity_rows) == len(MATERIALS) * len(TOPOLOGIES) and all(
            row.get("status") == "PASS"
            and _record_flag_is_true(row.get("passivity"))
            and _finite_at_most(row.get("reciprocity_error"), 1e-7)
            for row in fixed_sanity_rows
        )
        failures = []
        if len(cell_rows) != production_rows:
            failures.append(f"completed seed runs {len(cell_rows)}/{production_rows}")
        if len(valid_rows) != production_rows:
            failures.append(f"valid seed runs {len(valid_rows)}/{production_rows}")
        if completed_evaluations != expected_evaluations:
            failures.append(f"unique evaluations {completed_evaluations}/{expected_evaluations}")
        if not counter_pass:
            failures.append(
                "production counter accounting failed "
                f"({counter_audit['actual_rows']}/{counter_audit['expected_rows']} checkpoint rows)"
            )
        if physics_failures != 0:
            failures.append(f"physics failures {physics_failures}/0")
        if not finite_production_metrics:
            failures.append("production search/common-grid metrics are missing or non-finite")
        if not common_grid_validation_pass:
            failures.append("common-grid validation did not PASS for all seed runs")
        if not production_fingerprint_match:
            failures.append("production source/config fingerprint does not match Final Confirmation")
        if not fixed_design_sanity_pass:
            failures.append("fixed-design sanity did not PASS all six cells")
        if cells_completed != len(MATERIALS) * len(TOPOLOGIES):
            failures.append(f"completed cells {cells_completed}/{len(MATERIALS) * len(TOPOLOGIES)}")
        production_gate = {
            "schema_version": 1,
            "study_revision": "R1.2",
            "mode": "production",
            "status": "COMPLETED" if not failures else "FAILED",
            "run_dir": str(out),
            "source_config_fingerprint": fingerprint,
            "final_confirmation_fingerprint": final_gate.get("final_confirmation_fingerprint"),
            "common_validation_grid_id": common_grid_id,
            "expected_evaluations": expected_evaluations,
            "completed_evaluations": completed_evaluations,
            "counter_accounting_expected_rows": counter_audit["expected_rows"],
            "counter_accounting_actual_rows": counter_audit["actual_rows"],
            "counter_accounting": counter_audit,
            "cells_completed": cells_completed,
            "seed_runs_completed": len(valid_rows),
            "seed_runs_total": production_rows,
            "physics_failures": physics_failures,
            "finite_production_metrics_passed": finite_production_metrics,
            "common_grid_validation_passed": common_grid_validation_pass,
            "source_config_fingerprint_match": production_fingerprint_match,
            "fixed_design_sanity_passed": fixed_design_sanity_pass,
            "counter_accounting_rows_passed": len(accounting_rows) if counter_pass else 0,
            "final_confirmation_passed": final_gate.get("status") == "PASS",
            "stage3_9_started": False,
            "failures": failures,
        }
        _write_json(out / "stage3_8c_production_gate.json", production_gate)
        production_marker = (
            "STAGE3_8C_PRODUCTION_COMPLETED.txt"
            if production_gate["status"] == "COMPLETED"
            else "STAGE3_8C_PRODUCTION_FAILED.txt"
        )
        (out / production_marker).write_text(production_marker + "\n", encoding="utf-8")
        _write_csv(out / "stage3_8c_seed_comparison.csv", _r1_2_seed_comparison_rows(cell_rows))
        _write_r1_2_production_summary(out, production_gate, cell_rows)
        _write_r1_review_bundle(out, cfg, mode, cell_rows, checkpoint_rows,
                                population_preflight, known_rows, fixed_rows,
                                response_rows, production_gate)
        return {
            "status": "STAGE3_8C_PRODUCTION_COMPLETED" if not failures else "STAGE3_8C_PRODUCTION_FAILED",
            "run": str(out),
            "gate": str(out / "stage3_8c_production_gate.json"),
        }
    gate = {
        "status": "COMPLETE",
        "mode": "production",
        "valid_runs": sum(1 for row in cell_rows if row.get("run_status") == "VALID_RUN"),
        "invalid_runs": sum(1 for row in cell_rows if row.get("run_status") != "VALID_RUN"),
        "total_runs": len(cell_rows),
        "run_dir": str(out),
        "source_config_fingerprint": fingerprint,
        "common_validation_grid_id": common_grid_id,
        "pilot_run_dir": str(_pilot_path(cfg)),
        "pilot_all_cells_passed": True,
    }
    _write_main_summary_report(out, gate, cell_rows)
    _write_r1_review_bundle(out, cfg, mode, cell_rows, checkpoint_rows,
                            population_preflight, known_rows, fixed_rows,
                            response_rows, gate)
    return {"status": MAIN_COMPLETE, "run": str(out), "gate": gate}


def _stop_run(out: Path, marker: str, details: Mapping[str, Any]):
    (out / f"{marker}.txt").write_text(marker + "\n", encoding="utf-8")
    revision = "r1_2" if "_R1_2_" in marker else "r1_1" if "_R1_1_" in marker else "r1"
    _write_json(out / f"stage3_8c_{revision}_preflight_failure.json", {"marker": marker, **details})
    return {"status": marker, "run": str(out), "details": details}


def _flat_cell_row(row: Mapping[str, Any]) -> dict[str, Any]:
    counters = row.get("r1_counters", {})
    search_metrics = row.get("optimizer_incumbent_metrics", {})
    common_metrics = row.get("common_grid_metrics", {})
    return {
        "material": row.get("material"),
        "topology": row.get("topology"),
        "seed": row.get("seed"),
        "mode": row.get("mode"),
        "run_status": row.get("run_status"),
        "optimizer_incumbent_status": row.get("optimizer_incumbent_status"),
        "optimizer_incumbent_geometry_valid": row.get("optimizer_incumbent_geometry_valid"),
        "search_max_violation": row.get("optimizer_incumbent_max_violation"),
        "search_sum_violation": row.get("optimizer_incumbent_sum_violation"),
        "search_worst_il_db": search_metrics.get("worst_il_db"),
        "search_ripple_db": search_metrics.get("ripple_db"),
        "search_input_vswr": search_metrics.get("input_vswr"),
        "search_output_vswr": search_metrics.get("output_vswr"),
        "common_grid_status": row.get("common_grid_status"),
        "common_grid_geometry_valid": row.get("common_grid_geometry_valid"),
        "common_grid_max_violation": row.get("common_grid_max_violation"),
        "common_grid_sum_violation": row.get("common_grid_sum_violation"),
        "common_grid_worst_il_db": common_metrics.get("worst_il_db"),
        "common_grid_ripple_db": common_metrics.get("ripple_db"),
        "common_grid_input_vswr": common_metrics.get("input_vswr"),
        "common_grid_output_vswr": common_metrics.get("output_vswr"),
        "common_grid_stop_attenuation_db": json.dumps(_clean(common_metrics.get("stop_attenuation_db"))),
        "selected_design": json.dumps(_clean(row.get("selected_design", {})), sort_keys=True),
        "valid_physics_fraction": row.get("valid_physics_fraction"),
        "geometry_rejection_fraction": row.get("geometry_rejection_fraction"),
        "finite_search_metrics": row.get("finite_search_metrics"),
        "finite_common_metrics": row.get("finite_common_metrics"),
        "objective_calls": counters.get("objective_calls"),
        "canonical_candidates_seen": counters.get("canonical_candidates_seen"),
        "unique_decoded_evaluations": counters.get("unique_decoded_evaluations"),
        "geometry_rejections": counters.get("geometry_rejections"),
        "geometry_valid_candidates": counters.get("geometry_valid_candidates"),
        "valid_physics_evaluations": counters.get("valid_physics_evaluations"),
        "physics_attempted_evaluations": counters.get("physics_attempted_evaluations"),
        "physics_failures": counters.get("physics_failures"),
        "cache_hits": counters.get("cache_hits"),
        "solved_frequency_points": counters.get("solved_frequency_points"),
        "search_frequency_points": counters.get("search_frequency_points"),
        "validation_evaluations": counters.get("validation_evaluations"),
        "validation_frequency_points": counters.get("validation_frequency_points"),
        "elapsed_s": row.get("wall_time_s"),
        "initial_population_sampling": json.dumps(
            _clean(row.get("initial_population_sampling", {})), sort_keys=True
        ),
        "active_bounds": json.dumps(_clean(row.get("active_bounds"))),
        "optimizer_hard_bounds": json.dumps(_clean(row.get("optimizer_hard_bounds"))),
        "common_validation_grid_id": row.get("common_validation_grid_id"),
        "source_config_fingerprint": row.get("source_config_fingerprint"),
    }


def _material_topology_summaries(
    cell_rows: Sequence[Mapping[str, Any]], material: str,
) -> list[dict[str, Any]]:
    summaries = []
    for topology in TOPOLOGIES:
        group = [row for row in cell_rows
                 if row.get("material") == material and row.get("topology") == topology]
        valid = [row for row in group if row.get("run_status") == "VALID_RUN"]
        max_values = [float(row["common_grid_max_violation"]) for row in valid
                      if row.get("common_grid_max_violation") is not None]
        sum_values = [float(row["common_grid_sum_violation"]) for row in valid
                      if row.get("common_grid_sum_violation") is not None]
        il_values = [float(row["common_grid_metrics"]["worst_il_db"]) for row in valid]
        ripple_values = [float(row["common_grid_metrics"]["ripple_db"]) for row in valid]
        feasible_fraction = (
            sum(bool(row.get("common_grid_filter_feasible", False)) for row in valid)
            / len(valid) if valid else 0.0
        )
        seed_consistent = (
            len(valid) < 2
            or len({bool(row.get("common_grid_filter_feasible", False)) for row in valid}) == 1
        )
        best = min(valid, key=lambda row: (
            int(not row.get("common_grid_filter_feasible", False)),
            _finite(row.get("common_grid_max_violation")),
            _finite(row.get("common_grid_sum_violation")),
            _finite(row.get("common_grid_metrics", {}).get("worst_il_db")),
        )) if valid else None
        summaries.append({
            "material": material,
            "topology": topology,
            "valid_run_count": len(valid),
            "total_run_count": len(group),
            "feasible_fraction": feasible_fraction,
            "median_max_violation": float(np.median(max_values)) if max_values else None,
            "p75_max_violation": float(np.percentile(max_values, 75)) if max_values else None,
            "median_sum_violation": float(np.median(sum_values)) if sum_values else None,
            "median_worst_il_db": float(np.median(il_values)) if il_values else None,
            "median_ripple_db": float(np.median(ripple_values)) if ripple_values else None,
            "seed_consistent": seed_consistent,
            "seed_max_violation_spread": (
                float(max(max_values) - min(max_values)) if len(max_values) >= 2 else 0.0
            ),
            "best_seed": best.get("seed") if best else None,
            "best_seed_max_violation": best.get("common_grid_max_violation") if best else None,
            "best_seed_sum_violation": best.get("common_grid_sum_violation") if best else None,
            "best_seed_worst_il_db": best.get("common_grid_metrics", {}).get("worst_il_db") if best else None,
            "cross_material_search_space_warning": (
                "MLIT 30-180 um vs M0 30-150 um; cross-material ranking is descriptive only"
            ),
        })
    return summaries


def _topology_summary_rank_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        -float(row["feasible_fraction"]),
        _finite(row.get("median_max_violation")),
        _finite(row.get("p75_max_violation")),
        _finite(row.get("median_sum_violation")),
        _finite(row.get("median_worst_il_db")),
        int(not bool(row.get("seed_consistent", False))),
        _finite(row.get("seed_max_violation_spread")),
        _finite(row.get("best_seed_max_violation")),
        _finite(row.get("best_seed_sum_violation")),
        _finite(row.get("best_seed_worst_il_db")),
    )


def _aggregate_topology_order(cell_rows: Sequence[Mapping[str, Any]], material: str) -> list[str]:
    summaries = _material_topology_summaries(cell_rows, material)
    return [row["topology"] for row in sorted(summaries, key=_topology_summary_rank_key)
            if int(row["valid_run_count"]) > 0]


def _write_derived_csvs(out: Path, cell_rows: Sequence[Mapping[str, Any]],
                        checkpoint_rows: Sequence[Mapping[str, Any]]) -> None:
    rejection_rows = []
    for row in cell_rows:
        counters = row.get("r1_counters", {})
        rejection_rows.append({
            "material": row.get("material"),
            "topology": row.get("topology"),
            "seed": row.get("seed"),
            "geometry_rejections": counters.get("geometry_rejections"),
            "unique_decoded_evaluations": counters.get("unique_decoded_evaluations"),
            "geometry_rejection_fraction": row.get("geometry_rejection_fraction"),
            "initial_sampling_draws": row.get("initial_population_sampling", {}).get("initial_sampling_draws"),
            "initial_sampling_geometry_rejections": row.get("initial_population_sampling", {}).get("initial_sampling_geometry_rejections"),
            "initial_sampling_duplicate_rejections": row.get("initial_population_sampling", {}).get("initial_sampling_duplicate_rejections"),
        })
    _write_csv(out / "stage3_8c_r1_geometry_rejection_summary.csv", rejection_rows)

    accounting = []
    for row in checkpoint_rows:
        unique = row.get("unique_decoded_evaluations")
        rejected = row.get("geometry_rejections")
        valid = row.get("valid_physics_evaluations")
        failed = row.get("physics_failures")
        accounting.append({
            "material": row.get("material"),
            "topology": row.get("topology"),
            "seed": row.get("seed"),
            "checkpoint_budget": row.get("checkpoint_budget"),
            "unique_decoded_evaluations": unique,
            "geometry_rejections": rejected,
            "geometry_valid_candidates": row.get("geometry_valid_candidates"),
            "valid_physics_evaluations": valid,
            "physics_failures": failed,
            "counter_identity_lhs": unique,
            "counter_identity_rhs": (rejected or 0) + (row.get("geometry_valid_candidates") or 0),
            "counter_identity_pass": unique == (rejected or 0) + (row.get("geometry_valid_candidates") or 0),
            "physics_partition_pass": (row.get("geometry_valid_candidates") or 0) == (valid or 0) + (failed or 0),
            "valid_physics_within_geometry_valid": (valid or 0) <= (row.get("geometry_valid_candidates") or 0),
            "physics_attempted_evaluations": row.get("physics_attempted_evaluations"),
            "physics_attempt_identity_pass": row.get("physics_attempted_evaluations") == (valid or 0) + (failed or 0),
            "solved_frequency_points": row.get("solved_frequency_points"),
            "search_frequency_points": row.get("search_frequency_points"),
            "cache_hits": row.get("cache_hits"),
        })
    _write_csv(out / "stage3_8c_r1_counter_accounting.csv", accounting)

    boundaries = []
    bottlenecks = []
    costs = []
    for row in cell_rows:
        design = row.get("selected_design", {})
        hits = {}
        active_bounds = row.get("active_bounds") or []
        for name, value in _search_bound_hits(design, row["topology"], np.asarray(active_bounds, dtype=float)).items() if active_bounds else []:
            hits[name] = value
        boundaries.append({
            "material": row.get("material"),
            "topology": row.get("topology"),
            "seed": row.get("seed"),
            "search_bound_hits": json.dumps(_clean(hits), sort_keys=True),
            "hard_geometry_status": "HARD_GEOMETRY_REJECTION" if row.get("run_status") == "INVALID_RUN" and not row.get("optimizer_incumbent_geometry_valid") else "PASS",
            "hard_geometry_violations": json.dumps(_clean(row.get("optimizer_geometry_violations", {})), sort_keys=True),
            "manufacturing_dimensions": json.dumps(_clean(row.get("optimizer_geometry_dimensions", {})), sort_keys=True),
            "active_search_bounds": json.dumps(_clean(row.get("active_bounds"))),
            "optimizer_hard_bounds": json.dumps(_clean(row.get("optimizer_hard_bounds"))),
        })
        costs.append({
            "material": row.get("material"),
            "topology": row.get("topology"),
            "seed": row.get("seed"),
            "run_status": row.get("run_status"),
            "elapsed_s": row.get("wall_time_s"),
            "unique_decoded_evaluations": row.get("r1_counters", {}).get("unique_decoded_evaluations"),
            "valid_physics_evaluations": row.get("r1_counters", {}).get("valid_physics_evaluations"),
            "solved_frequency_points": row.get("r1_counters", {}).get("solved_frequency_points"),
            "seconds_per_unique": (
                row.get("wall_time_s", 0.0) / max(row.get("r1_counters", {}).get("unique_decoded_evaluations", 1), 1)
            ),
        })
        metrics = row.get("common_grid_metrics", {})
        violations = row.get("common_grid_violations", {})
        active_filter = max(violations, key=violations.get) if violations else None
        bottlenecks.append({
            "material": row.get("material"),
            "topology": row.get("topology"),
            "seed": row.get("seed"),
            "run_status": row.get("run_status"),
            "active_filter_constraint": active_filter,
            "max_violation": row.get("common_grid_max_violation"),
            "sum_violation": row.get("common_grid_sum_violation"),
            "worst_il_db": metrics.get("worst_il_db"),
            "ripple_db": metrics.get("ripple_db"),
            "stop_attenuation_db": json.dumps(_clean(metrics.get("stop_attenuation_db"))),
        })
    _write_csv(out / "stage3_8c_r1_boundary_diagnostics.csv", boundaries)
    _write_csv(out / "stage3_8c_r1_constraint_bottlenecks.csv", bottlenecks)
    _write_csv(out / "stage3_8c_r1_compute_cost.csv", costs)

    material_summaries = []
    rankings = []
    for material in MATERIALS:
        group = _material_topology_summaries(cell_rows, material)
        material_summaries.extend(group)
        ordered = sorted(group, key=_topology_summary_rank_key)
        for rank, summary in enumerate(ordered, 1):
            rankings.append({"material": material, "rank": rank, **summary})
    _write_csv(out / "stage3_8c_r1_topology_summary_by_material.csv", material_summaries)
    _write_csv(out / "stage3_8c_r1_cross_material_ranking.csv", rankings)


def _leaders(rows: Sequence[Mapping[str, Any]], material: str, *, seed: int | None = None):
    group = [row for row in rows if row.get("material") == material
             and row.get("run_status") == "VALID_RUN"
             and (seed is None or int(row.get("seed")) == int(seed))]
    if not group:
        return []
    return [row["topology"] for row in sorted(group, key=lambda row: (
        int(not row.get("common_grid_filter_feasible", False)),
        _finite(row.get("common_grid_max_violation")),
        _finite(row.get("common_grid_sum_violation")),
        _finite(row.get("common_grid_metrics", {}).get("worst_il_db")),
    ))]


def _third_seed_candidates(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    recommended = []
    valid = [row for row in rows if row.get("run_status") == "VALID_RUN"]
    materials = sorted({row["material"] for row in valid})
    for material in materials:
        material_rows = [row for row in valid if row["material"] == material]
        seeds = sorted({int(row["seed"]) for row in material_rows})
        if len(seeds) < 2:
            continue
        leaders = [_leaders(material_rows, material, seed=seed) for seed in seeds[:2]]
        if leaders[0] and leaders[1] and leaders[0][0] != leaders[1][0]:
            for topology in {leaders[0][0], leaders[1][0]}:
                recommended.append({
                    "material": material,
                    "topology": topology,
                    "reason": "seed_winner_reversed",
                    "third_seed": 20260919,
                    "status": "CONDITIONAL_RECOMMENDATION_ONLY",
                })
        topology_groups: dict[str, list[Mapping[str, Any]]] = {}
        for row in material_rows:
            topology_groups.setdefault(str(row["topology"]), []).append(row)
        medians = []
        for topology, group in topology_groups.items():
            vals = [_finite(row.get("common_grid_max_violation")) for row in group]
            if vals:
                medians.append((topology, float(np.median(vals))))
        medians.sort(key=lambda item: item[1])
        if len(medians) > 1:
            first, second = medians[:2]
            relative = abs(second[1] - first[1]) / max(abs(first[1]), 1e-12)
            if relative < 0.10:
                for topology in (first[0], second[0]):
                    recommended.append({
                        "material": material,
                        "topology": topology,
                        "reason": "top_two_difference_below_10_percent",
                        "third_seed": 20260919,
                        "status": "CONDITIONAL_RECOMMENDATION_ONLY",
                    })
        for topology, group in topology_groups.items():
            physics_counts = [int(row.get("r1_counters", {}).get("valid_physics_evaluations", 0))
                              for row in group]
            if len(physics_counts) >= 2 and min(physics_counts) > 0:
                imbalance = max(physics_counts) / min(physics_counts)
                if imbalance >= 1.25:
                    recommended.append({
                        "material": material,
                        "topology": topology,
                        "reason": "valid_physics_count_imbalance",
                        "third_seed": 20260919,
                        "status": "CONDITIONAL_RECOMMENDATION_ONLY",
                    })
    deduplicated = {}
    for row in recommended:
        deduplicated[(row["material"], row["topology"], row["reason"])] = row
    return list(deduplicated.values())[:4]


def _write_pilot_summary_report(out: Path, gate: Mapping[str, Any],
    cell_rows: Sequence[Mapping[str, Any]]) -> Path:
    revision = str(gate.get("study_revision", "R1")).upper()
    suffix = {"R1.1": "r1_1", "R1.2": "r1_2"}.get(revision, "r1")
    lines = [
        f"# Stage 3.8C-{revision} pilot summary",
        "",
        f"- Gate status: **{gate.get('status')}**",
        f"- Cells passing the gate: {gate.get('passed_cells', 0)}/{gate.get('total_cells', 6)}",
        f"- Run directory: `{out}`",
        f"- Source fingerprint: `{gate.get('source_config_fingerprint')}`",
        f"- Common validation grid: `{gate.get('common_validation_grid_id')}`",
        "- Performance interpretation: diagnostic only; one seed is not a topology ranking.",
        "",
    ]
    if revision == "R1.1":
        lines.extend([
            "| Material | Topology | Status | Unique | Physics valid | Solved points | R1 initial rejection | R1.1 conditional rejection | Uniform reference rejection | Optimizer rejection |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
    elif revision == "R1.2":
        lines.extend([
            "| Material | Topology | Status | Population | Attempts | Initial geometry rejection | Init time (s) | Physics valid | Solved points |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
    else:
        lines.extend([
            "| Material | Topology | Status | Unique | Geometry rejected | Valid physics | Solved points | Valid fraction | Rejection fraction |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
    for row in cell_rows:
        counters = row.get("r1_counters", {})
        if revision == "R1.1":
            sampling = row.get("initial_population_sampling", {})
            reference = sampling.get("independent_uniform_reference", {})
            r1_rejections, r1_draws = R1_INITIAL_REJECTION_REFERENCE[
                str(row.get("material"))
            ][str(row.get("topology"))]
            lines.append(
                f"| {row.get('material')} | {row.get('topology')} | {row.get('run_status')} | "
                f"{counters.get('unique_decoded_evaluations')} | "
                f"{counters.get('valid_physics_evaluations')} | {counters.get('solved_frequency_points')} | "
                f"{r1_rejections / r1_draws:.2%} | "
                f"{sampling.get('geometry_rejection_fraction', 0):.2%} | "
                f"{reference.get('geometry_rejection_fraction', 0):.2%} | "
                f"{row.get('geometry_rejection_fraction', 0):.2%} |"
            )
        elif revision == "R1.2":
            sampling = row.get("initial_population_sampling", {})
            lines.append(
                f"| {row.get('material')} | {row.get('topology')} | {row.get('run_status')} | "
                f"{sampling.get('valid_accepted_candidates', 'n/a')}/{sampling.get('requested_population_size', 'n/a')} | "
                f"{sampling.get('total_candidate_draws', 'n/a')} | "
                f"{sampling.get('geometry_rejection_fraction', 0):.2%} | "
                f"{sampling.get('population_generation_time_s', 0):.3f} | "
                f"{counters.get('valid_physics_evaluations')} | {counters.get('solved_frequency_points')} |"
            )
        else:
            lines.append(
                f"| {row.get('material')} | {row.get('topology')} | {row.get('run_status')} | "
                f"{counters.get('unique_decoded_evaluations')} | {counters.get('geometry_rejections')} | "
                f"{counters.get('valid_physics_evaluations')} | {counters.get('solved_frequency_points')} | "
                f"{row.get('valid_physics_fraction', 0):.3f} | {row.get('geometry_rejection_fraction', 0):.3f} |"
            )
    lines.extend(["", "## Gate failures", ""])
    failures = gate.get("failures", [])
    lines.extend([f"- {value}" for value in failures] if failures else ["- None."])
    lines.extend([
        "",
        "The pilot uses 256 unique decoded evaluations per cell, one seed (20260917), "
        "geometry-valid initial populations, and a separate common-grid re-evaluation "
        "of search finalists. R1.1/R1.2 pilots stop for review; no pilot authorizes or "
        "starts production automatically.",
        "",
    ])
    if revision == "R1.1":
        lines.extend([
            "M0 and MLIT use different aperture search ranges (30–150 um and 30–180 um); "
            "cross-material differences therefore do not isolate material effects.",
            "The conditional initializer changes population sampling distribution; the independent-uniform column is a geometry-only reference estimate, not the R1.1 population.",
            "Production was not started. Review is required before any production run.",
        ])
    elif revision == "R1.2":
        initializer_rows = [row.get("initial_population_sampling", {}) for row in cell_rows]
        runtimes = [float(item.get("population_generation_time_s", 0.0)) for item in initializer_rows]
        lines.extend([
            "R1.2 uses independent real-uniform proposals, existing integer canonicalization, and geometry rejection/resampling; rejected designs are never repaired. Rejection fraction is diagnostic only.",
            f"Initializer runtime median/max: {float(np.median(runtimes)):.3f}/{max(runtimes, default=0.0):.3f} s.",
            "R1.1's conditional initializer is not the R1.2 default. Production was not started; review is required before any production run.",
            "M0 and MLIT retain 30–150 um and 30–180 um aperture ranges respectively; cross-material differences do not isolate material effects.",
        ])
    report_path = ROOT / "reports" / f"stage3_8c_{suffix}_pilot_summary.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    out_path = out / f"stage3_8c_{suffix}_pilot_summary.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _r1_2_seed_comparison_rows(
    cell_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_cell: dict[tuple[str, str], dict[int, Mapping[str, Any]]] = {}
    for row in cell_rows:
        key = (str(row.get("material")), str(row.get("topology")))
        by_cell.setdefault(key, {})[int(row.get("seed", -1))] = row
    metrics = (
        ("valid_physics_evaluations", lambda row: row.get("r1_counters", {}).get("valid_physics_evaluations")),
        ("solved_frequency_points", lambda row: row.get("r1_counters", {}).get("solved_frequency_points")),
        ("search_max_violation", lambda row: row.get("optimizer_incumbent_max_violation")),
        ("common_grid_max_violation", lambda row: row.get("common_grid_max_violation")),
        ("common_grid_worst_il_db", lambda row: row.get("common_grid_metrics", {}).get("worst_il_db")),
        ("common_grid_ripple_db", lambda row: row.get("common_grid_metrics", {}).get("ripple_db")),
    )
    output = []
    for (material, topology), seeds in sorted(by_cell.items()):
        seed_values = sorted(seeds)
        if len(seed_values) != 2:
            continue
        seed_a, seed_b = seed_values
        row_a, row_b = seeds[seed_a], seeds[seed_b]
        for metric, getter in metrics:
            value_a, value_b = getter(row_a), getter(row_b)
            delta = None
            if value_a is not None and value_b is not None:
                delta = float(value_b) - float(value_a)
            output.append({
                "material": material,
                "topology": topology,
                "metric": metric,
                "seed_a": seed_a,
                "seed_a_status": row_a.get("run_status"),
                "seed_a_value": value_a,
                "seed_b": seed_b,
                "seed_b_status": row_b.get("run_status"),
                "seed_b_value": value_b,
                "seed_b_minus_seed_a": delta,
            })
    return output


def _write_r1_2_production_summary(out: Path, gate: Mapping[str, Any],
                                   cell_rows: Sequence[Mapping[str, Any]]) -> Path:
    report = [
        "# Stage 3.8C Production Summary", "",
        f"- Status: **{gate.get('status')}**",
        f"- Evaluations: {gate.get('completed_evaluations', 0)} / {gate.get('expected_evaluations', 0)}",
        f"- Cells completed: {gate.get('cells_completed', 0)} / 6",
        f"- Seed runs completed: {gate.get('seed_runs_completed', 0)} / 12",
        f"- Physics failures: {gate.get('physics_failures', 0)}",
        f"- Source/config fingerprint: `{gate.get('source_config_fingerprint')}`",
        f"- Final Confirmation fingerprint: `{gate.get('final_confirmation_fingerprint')}`",
        f"- Common validation grid: `{gate.get('common_validation_grid_id')}`",
        "- Stage 3.9: NOT STARTED; review is required before any next-stage decision.",
        "",
        "| Material | Topology | Seed | Status | Unique evaluations | Valid physics | Solved points | Physics failures |",
        "|---|---|---:|---|---:|---:|---:|---:|",
    ]
    for row in sorted(cell_rows, key=lambda item: (
        str(item.get("material")), str(item.get("topology")), int(item.get("seed", -1))
    )):
        counters = row.get("r1_counters", {})
        report.append(
            f"| {row.get('material')} | {row.get('topology')} | {row.get('seed')} | "
            f"{row.get('run_status')} | {counters.get('unique_decoded_evaluations', 0)} | "
            f"{counters.get('valid_physics_evaluations', 0)} | "
            f"{counters.get('solved_frequency_points', 0)} | {counters.get('physics_failures', 0)} |"
        )
    if gate.get("failures"):
        report.extend(["", "## Failures", "", *[f"- {failure}" for failure in gate["failures"]]])
    path = out / "stage3_8c_production_summary.md"
    path.write_text("\n".join(report) + "\n", encoding="utf-8")
    return path


def _write_main_summary_report(out: Path, gate: Mapping[str, Any],
                               rows: Sequence[Mapping[str, Any]]) -> Path:
    valid_rows = [row for row in rows if row.get("run_status") == "VALID_RUN"]
    m0 = _aggregate_topology_order(valid_rows, "M0")
    mlit = _aggregate_topology_order(valid_rows, "MLIT")
    same_leader = bool(m0 and mlit and m0[0] == mlit[0])
    rejection = {
        topology: float(np.mean([
            row.get("geometry_rejection_fraction", 0.0)
            for row in rows if row.get("topology") == topology
        ])) for topology in TOPOLOGIES
    }
    t1_beats_t0 = any(
        ranks and T1 in ranks and T0 in ranks and ranks.index(T1) < ranks.index(T0)
        for ranks in (m0, mlit)
    )
    stop1_rows = [row for row in valid_rows if row.get("common_grid_violations", {}).get("stop_1", 0) > 0]
    stop2_rows = [row for row in valid_rows if row.get("common_grid_violations", {}).get("stop_2", 0) > 0]
    t2_rows = [row for row in rows if row.get("topology") == T2]

    def median_metric(material: str, topology: str, metric: str, stop_index: int | None = None):
        values = []
        for row in valid_rows:
            if row.get("material") != material or row.get("topology") != topology:
                continue
            metrics = row.get("common_grid_metrics", {})
            value = (metrics.get("stop_attenuation_db", [])[stop_index]
                     if stop_index is not None else metrics.get(metric))
            if value is not None and math.isfinite(float(value)):
                values.append(float(value))
        return float(np.median(values)) if values else None

    t2_comparisons = []
    for material in MATERIALS:
        t2_il = median_metric(material, T2, "worst_il_db")
        t2_ripple = median_metric(material, T2, "ripple_db")
        t2_stop1 = median_metric(material, T2, "stop_attenuation_db", stop_index=1)
        baseline_il = [median_metric(material, topology, "worst_il_db") for topology in (T0, T1)]
        baseline_ripple = [median_metric(material, topology, "ripple_db") for topology in (T0, T1)]
        baseline_stop1 = [median_metric(material, topology, "stop_attenuation_db", stop_index=1)
                          for topology in (T0, T1)]
        il_better = (t2_il is not None and any(value is not None and t2_il < value
                                                for value in baseline_il))
        ripple_better = (t2_ripple is not None and any(value is not None and t2_ripple < value
                                                        for value in baseline_ripple))
        stop1_better = (t2_stop1 is not None and any(value is not None and t2_stop1 > value
                                                      for value in baseline_stop1))
        t2_comparisons.append(
            f"{material}: median worst IL={t2_il if t2_il is not None else 'n/a'} dB, "
            f"ripple={t2_ripple if t2_ripple is not None else 'n/a'} dB, "
            f"stop_1 attenuation={t2_stop1 if t2_stop1 is not None else 'n/a'} dB; "
            f"better than at least one T0/T1 median: IL={'yes' if il_better else 'no'}, "
            f"ripple={'yes' if ripple_better else 'no'}, stop_1={'yes' if stop1_better else 'no'}"
        )
    third_seed = _third_seed_candidates(valid_rows)
    third_seed_text = (
        "conditional review recommended for " + ", ".join(
            f"{item['material']}/{item['topology']}" for item in third_seed
        ) if third_seed else "not indicated by the configured diagnostics"
    )
    any_boundary_hits = False
    for row in valid_rows:
        hits = _search_bound_hits(
            row.get("selected_design", {}), row["topology"],
            np.asarray(row.get("active_bounds", []), dtype=float),
        )
        if any(value["lower"] or value["upper"] for value in hits.values()):
            any_boundary_hits = True
            break
    if any(float(row.get("geometry_rejection_fraction", 0.0)) > 0.90 for row in rows):
        classification = "SEARCH_SPACE_INVALID"
    elif len(valid_rows) != len(rows):
        classification = "BOUNDARY_LIMITED"
    elif any_boundary_hits:
        classification = "BOUNDARY_LIMITED"
    elif same_leader:
        classification = "ROBUST_TOPOLOGY_LEADER"
    elif m0[:2] and mlit[:2] and set(m0[:2]) == set(mlit[:2]):
        classification = "ROBUST_SHORTLIST"
    else:
        classification = "MATERIAL_DEPENDENT_TOPOLOGY"
    lines = [
        "# Stage 3.8C-R1 topology fast-screen summary",
        "",
        f"- Run status: `{gate.get('status')}`",
        f"- Final valid runs: {gate.get('valid_runs', len(valid_rows))}/{gate.get('total_runs', len(rows))}",
        f"- Classification: **`{classification}`**",
        f"- Run directory: `{out}`",
        f"- Common validation grid: `{gate.get('common_validation_grid_id')}`",
        "- Previous Stage 3.8 ordering: `INVALIDATED_BY_GEOMETRY_RANKING_BUG`",
        "",
        "## Pilot and geometry gate",
        "",
        f"- Physics evaluator reached in all six pilot cells: {gate.get('pilot_all_cells_passed', 'recorded in pilot gate')}.",
        "- Topology COM/network implementation was retained; the R1 change is limited to geometry/objective integration and accounting.",
        "- Geometry rejection fraction by topology: " + ", ".join(f"{t}={rejection[t]:.3f}" for t in TOPOLOGIES) + ".",
        "- Any invalid production seed is marked `INVALID_RUN` and excluded from topology ranking.",
        "",
        "## Within-material ranking",
        "",
        f"- M0 order: {', '.join(m0) if m0 else 'no valid run'}.",
        f"- MLIT order: {', '.join(mlit) if mlit else 'no valid run'}.",
        f"- Same leader: {'yes' if same_leader else 'no or insufficient valid runs'}.",
        f"- T1 5-IDT shows an advantage over T0: {'yes' if t1_beats_t0 else 'no clear signal'}.",
        f"- T2 stop_1 active in {sum(row.get('common_grid_violations', {}).get('stop_1', 0) > 0 for row in t2_rows)}/{len(t2_rows)} T2 runs; across all valid runs stop_1 is active in {len(stop1_rows)}/{len(valid_rows)} and stop_2 in {len(stop2_rows)}/{len(valid_rows)}.",
        f"- stop_1 dominance appears weaker than stop_2: {'yes' if len(stop1_rows) < len(stop2_rows) else 'no clear signal'}.",
        "- T2 median passband and stop_1 comparison versus T0/T1: " + "; ".join(t2_comparisons) + ".",
        "",
        "## Cross-material interpretation and promotion",
        "",
        "M0 uses a 30–150 um aperture search range and MLIT uses 30–180 um. "
        "The latter is an **R1 user-directed bound override**. Stage 3.7D's archived "
        "recommendation remains 30–150 um. Cross-material differences are confounded "
        "by unequal search spaces, so the topology orders below are descriptive and "
        "cannot isolate a material-only effect.",
        f"- Topology order changes by material: {'yes (descriptive only)' if m0 and mlit and m0[0] != mlit[0] else 'no clear change'}.",
        f"- Stage 3.9 shortlist (maximum two): {', '.join((m0[:2] if same_leader else list(dict.fromkeys(m0[:1] + mlit[:1]))[:2])) if m0 or mlit else 'none'}.",
        f"- Third seed 20260919: {third_seed_text}; no third seed was run.",
        "- FEM extraction: this screen ranks topology responses under the frozen M0/MLIT COM profiles; production-qualified device conclusions still need measured or FEM-derived parameters.",
        "",
        "## Metric priority used",
        "",
        "Valid runs are ranked within each material by feasible fraction, median maximum filter violation, 75th-percentile maximum violation, median sum violation, median worst insertion loss, then seed consistency (same feasibility class, then smaller cross-seed max-violation spread); best single seed metrics are tie-breakers only. Geometry status was applied before all filter metrics.",
        "FEM extraction is not needed to interpret this frozen-profile topology screen; it is needed before production-qualified device claims.",
        "",
    ]
    report_path = ROOT / "reports" / "stage3_8c_r1_topology_fast_screen_summary.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    out_path = out / "stage3_8c_r1_topology_fast_screen_summary.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _write_r1_plots(bundle: Path, cell_rows: Sequence[Mapping[str, Any]],
                    responses: Sequence[Mapping[str, Any]]) -> None:
    plots = bundle / "plots"
    plots.mkdir(parents=True, exist_ok=True)

    def bar_plot(filename: str, title: str, ylabel: str, values: Sequence[float], labels: Sequence[str]):
        fig, ax = plt.subplots(figsize=(10, 5))
        x = np.arange(len(values))
        ax.bar(x, values)
        ax.set_xticks(x, labels, rotation=35, ha="right")
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(plots / filename, dpi=160)
        plt.close(fig)

    labels = [f"{row['material']}\n{row['topology']}\n{row['seed']}" for row in cell_rows]
    bar_plot("stage3_8c_r1_valid_physics_fraction.png", "Valid physics fraction", "fraction",
             [float(row.get("valid_physics_fraction", 0.0)) for row in cell_rows], labels)
    bar_plot("stage3_8c_r1_geometry_rejection_fraction.png", "Geometry rejection fraction", "fraction",
             [float(row.get("geometry_rejection_fraction", 0.0)) for row in cell_rows], labels)
    bar_plot("stage3_8c_r1_median_max_violation.png", "Common-grid maximum filter violation", "max violation",
             [_finite(row.get("common_grid_max_violation"), 0.0) for row in cell_rows], labels)
    bar_plot("stage3_8c_r1_seed_level_max_violation.png", "Seed-level common-grid maximum violation", "max violation",
             [_finite(row.get("common_grid_max_violation"), 0.0) for row in cell_rows], labels)

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(cell_rows))
    stops1 = [float(row.get("common_grid_metrics", {}).get("stop_attenuation_db", [0, 0, 0, 0])[1])
              for row in cell_rows]
    stops2 = [float(row.get("common_grid_metrics", {}).get("stop_attenuation_db", [0, 0, 0, 0])[2])
              for row in cell_rows]
    ax.bar(x - 0.2, stops1, width=0.4, label="stop_1")
    ax.bar(x + 0.2, stops2, width=0.4, label="stop_2")
    ax.set_xticks(x, labels, rotation=35, ha="right")
    ax.set_ylabel("attenuation (dB)")
    ax.set_title("Stopband attenuation comparison")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(plots / "stage3_8c_r1_stopband_comparison.png", dpi=160)
    plt.close(fig)

    boundary_hits = []
    for row in cell_rows:
        bounds = np.asarray(row.get("active_bounds", []), dtype=float)
        hits = _search_bound_hits(row.get("selected_design", {}), row["topology"], bounds) if bounds.size else {}
        boundary_hits.append(sum(int(value["lower"] or value["upper"]) for value in hits.values()))
    bar_plot("stage3_8c_r1_boundary_diagnostics.png", "Active search-bound hits by selected design", "hit count",
             boundary_hits, labels)

    fig, ax = plt.subplots(figsize=(12, 6))
    selected = []
    seen = set()
    for row in responses:
        key = (row["material"], row["topology"])
        if key not in seen:
            selected.append(key)
            seen.add(key)
    for material, topology in selected:
        spectrum = [row for row in responses if row["material"] == material and row["topology"] == topology]
        if not spectrum:
            continue
        seed = min(int(row["seed"]) for row in spectrum)
        spectrum = sorted([row for row in spectrum if int(row["seed"]) == seed], key=lambda row: row["frequency_hz"])
        frequency_mhz = np.asarray([row["frequency_hz"] for row in spectrum], dtype=float) / 1e6
        ax.plot(frequency_mhz, [row["s21_db"] for row in spectrum], label=f"{material}/{topology} S21")
    ax.set_xlabel("frequency (MHz)")
    ax.set_ylabel("S21 (dB)")
    ax.set_title("Representative common-grid validated responses")
    ax.legend(fontsize=7, ncol=2)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(plots / "stage3_8c_r1_representative_validated_s21.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(12, 6))
    for material, topology in selected:
        spectrum = [row for row in responses if row["material"] == material and row["topology"] == topology]
        if not spectrum:
            continue
        seed = min(int(row["seed"]) for row in spectrum)
        spectrum = sorted([row for row in spectrum if int(row["seed"]) == seed], key=lambda row: row["frequency_hz"])
        frequency_mhz = np.asarray([row["frequency_hz"] for row in spectrum], dtype=float) / 1e6
        ax.plot(frequency_mhz, [row["s11_db"] for row in spectrum], label=f"{material}/{topology} S11")
    ax.set_xlabel("frequency (MHz)")
    ax.set_ylabel("S11 (dB)")
    ax.set_title("Representative common-grid validated responses")
    ax.legend(fontsize=7, ncol=2)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(plots / "stage3_8c_r1_representative_validated_s11.png", dpi=160)
    plt.close(fig)

    bar_plot("stage3_8c_r1_compute_cost.png", "Compute cost by cell", "wall time (s)",
             [float(row.get("wall_time_s", 0.0)) for row in cell_rows], labels)


def _copy_if_exists(source: Path, destination: Path) -> None:
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())


def _write_r1_review_bundle(
    out: Path, cfg: Mapping[str, Any], mode: str,
    cell_rows: Sequence[Mapping[str, Any]], checkpoint_rows: Sequence[Mapping[str, Any]],
    population_preflight: Sequence[Mapping[str, Any]], known_rows: Sequence[Mapping[str, Any]],
    fixed_rows: Sequence[Mapping[str, Any]], response_rows: Sequence[Mapping[str, Any]],
    gate: Mapping[str, Any],
) -> Path:
    artifact_root = ROOT / "artifacts" / "review_bundles"
    artifact_root.mkdir(parents=True, exist_ok=True)
    revision = str(cfg.get("stage3_8c_r1", {}).get("revision", "R1")).upper()
    revision_suffix = {"R1.1": "r1_1", "R1.2": "r1_2"}.get(revision, "r1")
    if revision == "R1.2" and mode == "production":
        name = "stage3_8c_production_review"
    else:
        name = (f"stage3_8c_{revision_suffix}_pilot_review" if mode == "pilot" else
                f"stage3_8c_{revision_suffix}_geometry_gate_correction_topology_rerun_review")
    bundle = artifact_root / name
    if bundle.exists():
        bundle = artifact_root / f"{name}_{out.name}"
    bundle.mkdir(parents=True, exist_ok=True)

    for filename in (
        "stage3_8c_r1_1_all_seed_results.csv",
        "stage3_8c_r1_1_pilot_results.csv",
        "stage3_8c_r1_1_checkpoint_results.csv",
        "stage3_8c_r1_1_geometry_rejections.csv",
        "stage3_8c_r1_1_counter_accounting.csv",
        "stage3_8c_r1_1_boundary_diagnostics.csv",
        "stage3_8c_r1_1_constraint_bottlenecks.csv",
        "stage3_8c_r1_1_compute_cost.csv",
        "stage3_8c_r1_1_topology_summary_by_material.csv",
        "stage3_8c_r1_1_cross_material_ranking.csv",
        "stage3_8c_r1_1_validated_responses.csv",
        "stage3_8c_r1_1_initializer_summary.csv",
        "stage3_8c_r1_1_initializer_rejections.csv",
        "stage3_8c_r1_1_initializer_distribution.csv",
        "stage3_8c_r1_1_geometry_rejection_summary.csv",
        "stage3_8c_r1_1_population_preflight.csv",
        "stage3_8c_r1_1_fixed_design_sanity.csv",
        "stage3_8c_r1_1_pilot_gate.json",
        "stage3_8c_r1_1_pilot_summary.md",
        "stage3_8c_r1_2_initializer_summary.csv",
        "stage3_8c_r1_2_initializer_attempts.csv",
        "stage3_8c_r1_2_initializer_distribution.csv",
        "stage3_8c_r1_2_geometry_rejections.csv",
        "stage3_8c_r1_2_population_preflight.csv",
        "stage3_8c_r1_2_initializer_reference_mc.csv",
        "stage3_8c_initializer_generation_comparison.csv",
        "stage3_8c_initializer_distribution_comparison.csv",
        "stage3_8c_r1_2_fixed_design_sanity.csv",
        "stage3_8c_r1_2_pilot_gate.json",
        "stage3_8c_r1_2_pilot_summary.md",
        "stage3_8c_r1_2_all_seed_results.csv",
        "stage3_8c_r1_2_pilot_results.csv",
        "stage3_8c_r1_2_checkpoint_results.csv",
        "stage3_8c_r1_2_counter_accounting.csv",
        "stage3_8c_r1_2_boundary_diagnostics.csv",
        "stage3_8c_r1_2_validated_responses.csv",
        "stage3_8c_r1_all_seed_results.csv",
        "stage3_8c_r1_checkpoint_results.csv",
        "stage3_8c_r1_geometry_rejections.csv",
        "stage3_8c_r1_geometry_rejection_summary.csv",
        "stage3_8c_r1_counter_accounting.csv",
        "stage3_8c_r1_boundary_diagnostics.csv",
        "stage3_8c_r1_constraint_bottlenecks.csv",
        "stage3_8c_r1_compute_cost.csv",
        "stage3_8c_r1_topology_summary_by_material.csv",
        "stage3_8c_r1_cross_material_ranking.csv",
        "stage3_8c_r1_validated_responses.csv",
        "stage3_8c_r1_known_seed_preflight.csv",
    ):
        _copy_if_exists(out / filename, bundle / filename)
    if revision == "R1.2" and mode == "production":
        aliases = {
            "stage3_8c_production_results.csv": "stage3_8c_r1_2_all_seed_results.csv",
            "stage3_8c_all_seed_results.csv": "stage3_8c_r1_2_all_seed_results.csv",
            "stage3_8c_counter_accounting.csv": "stage3_8c_r1_2_counter_accounting.csv",
            "stage3_8c_validated_responses.csv": "stage3_8c_r1_2_validated_responses.csv",
            "stage3_8c_boundary_diagnostics.csv": "stage3_8c_r1_2_boundary_diagnostics.csv",
            "stage3_8c_production_gate.json": "stage3_8c_production_gate.json",
            "stage3_8c_production_summary.md": "stage3_8c_production_summary.md",
        }
        for destination_name, source_name in aliases.items():
            _copy_if_exists(out / source_name, bundle / destination_name)
        confirmation_dir = _pilot_path(cfg)
        _copy_if_exists(
            confirmation_dir / "stage3_8c_r1_2_final_confirmation_gate.json",
            bundle / "stage3_8c_r1_2_final_confirmation_gate.json",
        )
        _copy_if_exists(
            confirmation_dir / "stage3_8c_r1_2_final_confirmation_summary.md",
            bundle / "stage3_8c_r1_2_final_confirmation_summary.md",
        )
        _copy_if_exists(
            confirmation_dir / "STAGE3_8C_R1_2_FINAL_CONFIRMATION_PASS.txt",
            bundle / "run" / "STAGE3_8C_R1_2_FINAL_CONFIRMATION_PASS.txt",
        )
    _write_csv(bundle / "stage3_8c_r1_population_preflight.csv", population_preflight)
    _write_csv(bundle / "stage3_8c_r1_fixed_design_sanity.csv", fixed_rows)
    if mode == "pilot":
        _copy_if_exists(out / "stage3_8c_r1_all_seed_results.csv",
                        bundle / "stage3_8c_r1_pilot_results.csv")
        pilot_gate = gate
        if revision == "R1.1":
            _write_json(bundle / "stage3_8c_r1_1_pilot_gate.json", pilot_gate)
            _copy_if_exists(out / "stage3_8c_r1_1_pilot_summary.md",
                            bundle / "stage3_8c_r1_1_pilot_summary.md")
        elif revision == "R1.2":
            _write_json(bundle / "stage3_8c_r1_2_pilot_gate.json", pilot_gate)
            _copy_if_exists(out / "stage3_8c_r1_2_pilot_summary.md",
                            bundle / "stage3_8c_r1_2_pilot_summary.md")
        else:
            _write_json(bundle / "stage3_8c_r1_pilot_gate.json", pilot_gate)
            _copy_if_exists(out / "stage3_8c_r1_pilot_summary.md",
                            bundle / "stage3_8c_r1_pilot_summary.md")
    elif not (revision == "R1.2" and mode == "production"):
        pilot_dir = _pilot_path(cfg)
        _copy_if_exists(pilot_dir / "stage3_8c_r1_all_seed_results.csv",
                        bundle / "stage3_8c_r1_pilot_results.csv")
        _copy_if_exists(pilot_dir / "stage3_8c_r1_pilot_gate.json",
                        bundle / "stage3_8c_r1_pilot_gate.json")
        _copy_if_exists(pilot_dir / "stage3_8c_r1_pilot_summary.md",
                        bundle / "stage3_8c_r1_pilot_summary.md")
    source_summary = (ROOT / "reports" / "stage3_8c_r1_topology_fast_screen_summary.md")
    if mode == "production" and source_summary.is_file():
        _copy_if_exists(source_summary, bundle / "stage3_8c_r1_topology_fast_screen_summary.md")
    _copy_if_exists(ROOT / "reports" / "stage3_8c_r1_geometry_gate_root_cause.md",
                    bundle / "stage3_8c_r1_geometry_gate_root_cause.md")
    _copy_if_exists(ROOT / "reports" / "stage3_8c_r1_geometry_ranking_tests.md",
                    bundle / "stage3_8c_r1_geometry_ranking_tests.md")
    test_summary_source = {
        "R1.1": ROOT / "reports" / "stage3_8c_r1_1_test_summary.md",
        "R1.2": ROOT / "reports" / "stage3_8c_r1_2_test_summary.md",
    }.get(revision, ROOT / "reports" / "test_summary.md")
    _copy_if_exists(test_summary_source, bundle / "test_summary.md")
    if not (bundle / "test_summary.md").exists():
        (bundle / "test_summary.md").write_text("Test summary will be populated after the R1 regression gates.\n", encoding="utf-8")

    metadata_out = bundle / "metadata"
    metadata_out.mkdir(exist_ok=True)
    metadata_src = out / "metadata"
    for item in metadata_src.rglob("*"):
        if item.is_file():
            _copy_if_exists(item, metadata_out / item.relative_to(metadata_src))
    _copy_if_exists(out / "input_config.yaml", bundle / "metadata" / "input_config.yaml")
    _copy_if_exists(out / "run_manifest.json", bundle / "run" / "run_manifest.json")
    _copy_if_exists(out / "status.json", bundle / "run" / "status.json")
    _copy_if_exists(out / "stdout.log", bundle / "run" / "stdout.log")
    _copy_if_exists(out / "stderr.log", bundle / "run" / "stderr.log")
    marker_names = (
        ("STAGE3_8C_PRODUCTION_COMPLETED.txt", "STAGE3_8C_PRODUCTION_FAILED.txt")
        if revision == "R1.2" and mode == "production" else {
        "R1.1": ("STAGE3_8C_R1_1_PILOT_PASS_AWAITING_REVIEW.txt",
                 "STAGE3_8C_R1_1_PILOT_FAIL_STOP.txt"),
        "R1.2": ("STAGE3_8C_R1_2_PILOT_PASS_AWAITING_REVIEW.txt",
                 "STAGE3_8C_R1_2_PILOT_FAIL_STOP.txt"),
    }.get(revision, ("STAGE3_8C_R1_PILOT_PASS_WAITING_FOR_PRODUCTION_LAUNCH.txt",
                    f"{PILOT_FAIL}.txt"))
    )
    for marker_name in marker_names:
        _copy_if_exists(out / marker_name, bundle / "run" / marker_name)
    _copy_if_exists(out / f"{MAIN_COMPLETE}.txt", bundle / "run" / f"{MAIN_COMPLETE}.txt")
    (bundle / "run" / "run_directory.txt").parent.mkdir(parents=True, exist_ok=True)
    (bundle / "run" / "run_directory.txt").write_text(str(out) + "\n", encoding="utf-8")
    _write_r1_plots(bundle, cell_rows, response_rows)
    for report_name in ("gpt6sol_migration_report.md", "gpt6sol_routing_test_results.json"):
        _copy_if_exists(ROOT / "reports" / report_name, bundle / report_name)
    if revision == "R1.2":
        _copy_if_exists(
            ROOT / "reports" / "stage3_8c_r1_2_gpt6sol_routing_test_results.json",
            bundle / "gpt6sol_routing_test_results.json",
        )

    if mode == "pilot":
        summary_path = bundle / f"stage3_8c_{revision_suffix}_pilot_summary.md"
        if not summary_path.exists():
            _copy_if_exists(out / f"stage3_8c_{revision_suffix}_pilot_summary.md", summary_path)
    if revision == "R1.2" and mode == "production":
        status = str(gate.get("status", "FAILED"))
        readme = (
            f"Stage 3.8C Production: {status}\n\n"
            "# Review bundle\n\n"
            f"Run directory: `{out}`. Source/config fingerprint: `{gate.get('source_config_fingerprint')}`.\n\n"
            f"1. Evaluations: {gate.get('completed_evaluations', 0)} / {gate.get('expected_evaluations', 96000)}.\n"
            f"2. Cells completed: {gate.get('cells_completed', 0)} / 6.\n"
            f"3. Seed runs completed: {gate.get('seed_runs_completed', 0)} / {gate.get('seed_runs_total', 12)}.\n"
            f"4. Physics failures: {gate.get('physics_failures', 0)}.\n"
            f"5. Final Confirmation fingerprint: `{gate.get('final_confirmation_fingerprint')}`; production config was gated against that fingerprint.\n"
            "6. Counter accounting, per-seed results, paired seed comparison, validated responses, and boundary diagnostics are included.\n"
            "7. Final Confirmation summary/gate and tests are included.\n"
            "8. Topology/material ranking is not promoted by this run; Stage 3.9 is NOT STARTED.\n"
            "9. Production conditions retain the approved R1.2 search space, COM profiles, geometry constraints, topology, objective, optimizer, 8,000-evaluation budget, and two configured seeds.\n"
        )
    elif revision == "R1.1":
        result_label = "PASS_AWAITING_REVIEW" if gate.get("status") == "PASS" else "FAIL_STOP"
        physics_cells = sum(
            1 for row in cell_rows
            if row.get("optimizer_incumbent_geometry_valid")
            and int(row.get("r1_counters", {}).get("valid_physics_evaluations", 0)) > 0
            and int(row.get("r1_counters", {}).get("solved_frequency_points", 0)) > 0
            and row.get("finite_search_metrics") and row.get("finite_common_metrics")
        )
        fixed_passes = sum(
            1 for row in fixed_rows
            if row.get("passivity") and float(row.get("reciprocity_error", math.inf)) <= 1e-7
        )
        summary_rows = {
            (str(row.get("material")), str(row.get("topology"))): row
            for row in population_preflight if row.get("status") == "PASS"
        }
        rejection_lines = []
        for material in MATERIALS:
            for topology in TOPOLOGIES:
                row = summary_rows.get((material, topology), {})
                sampling = row.get("initial_population_sampling", {})
                r1_rejections, r1_draws = R1_INITIAL_REJECTION_REFERENCE[material][topology]
                rejection_lines.append(
                    f"| {material} | {topology} | {r1_rejections / r1_draws:.2%} | "
                    f"{sampling.get('geometry_rejection_fraction', 'n/a')} | "
                    f"{sampling.get('independent_uniform_reference', {}).get('geometry_rejection_fraction', 'n/a')} |"
                )
        readme = (
            f"Stage 3.8C-R1.1 Pilot result: {result_label}\n\n"
            f"# Review bundle\n\nMode: `{mode}`. Run directory: `{out}`.\n\n"
            "## Required review summary\n\n"
            "1. Initializer: continuous coordinates are sampled within the unchanged active bounds; integer counts are sampled from topology-specific feasible discrete sets with downstream minima reserved. Every candidate is rechecked with the existing decoder and geometry evaluator.\n"
            "2. Initial geometry rejection comparison:\n\n"
            "| Material | Topology | R1 observed | R1.1 conditional sampler | Independent-uniform reference |\n"
            "|---|---|---:|---:|---:|\n"
            + "\n".join(rejection_lines) + "\n\n"
            f"3. Physics-valid cells: {physics_cells}/6; search/common-grid finite metrics are recorded per cell.\n"
            f"4. Fixed-design sanity: {fixed_passes}/6 PASS.\n"
            "5. Full test suite results are in `test_summary.md`.\n"
            "6. Sol review target: `gpt-6-sol`; routing details are in `gpt6sol_migration_report.md`.\n"
            "7. GPT-6 Sol routing smoke: see `gpt6sol_routing_test_results.json`; requested model was accepted, resolved backend identity is not exposed.\n"
            "8. Production: NOT STARTED. This R1.1 config is pilot-only.\n"
            "9. Limitations: one seed is diagnostic only; M0 uses 30–150 um aperture and MLIT uses 30–180 um, so cross-material comparisons do not isolate material effects. The conditional sampler changes initializer distribution.\n\n"
            "Geometry hard feasibility remains ahead of filter feasibility. No COM, network, measurement, specification, objective, constraints, topology, optimizer update rule, evaluation budget, impedance, material profile, search bound, or common validation grid was changed.\n"
        )
    elif revision == "R1.2":
        result_label = "PASS_AWAITING_REVIEW" if gate.get("status") == "PASS" else "FAIL_STOP"
        physics_cells = sum(
            1 for row in cell_rows
            if row.get("optimizer_incumbent_geometry_valid")
            and int(row.get("r1_counters", {}).get("valid_physics_evaluations", 0)) > 0
            and int(row.get("r1_counters", {}).get("solved_frequency_points", 0)) > 0
            and row.get("finite_search_metrics") and row.get("finite_common_metrics")
        )
        fixed_passes = sum(
            1 for row in fixed_rows
            if row.get("passivity") and float(row.get("reciprocity_error", math.inf)) <= 1e-7
        )
        preflight_by_cell = {
            (str(row.get("material")), str(row.get("topology"))): row
            for row in population_preflight
        }
        generation_records = {}
        generation_path = out / "stage3_8c_initializer_generation_comparison.csv"
        if generation_path.is_file():
            with generation_path.open("r", encoding="utf-8", newline="") as stream:
                for generation_row in csv.DictReader(stream):
                    generation_records[(generation_row.get("material"),
                                        generation_row.get("topology"),
                                        generation_row.get("revision"))] = generation_row

        def _generation_value(record: Mapping[str, Any], key: str,
                              precision: int = 0) -> str:
            value = record.get(key)
            if value in (None, ""):
                return "n/a"
            number = float(value)
            return f"{number:.{precision}f}"

        generation_lines = []
        for material in MATERIALS:
            for topology in TOPOLOGIES:
                r1 = generation_records.get((material, topology, "R1"), {})
                r1_1 = generation_records.get((material, topology, "R1.1"), {})
                r1_2 = generation_records.get((material, topology, "R1.2"), {})
                generation_lines.append(
                    f"| {material} | {topology} | "
                    f"{_generation_value(r1, 'candidate_attempts')} | "
                    f"{_generation_value(r1, 'geometry_rejections')} | "
                    f"{_generation_value(r1, 'rejection_fraction', 2)} | "
                    f"{_generation_value(r1, 'generation_time_s', 3)} | "
                    f"{_generation_value(r1_1, 'candidate_attempts')} | "
                    f"{_generation_value(r1_1, 'rejection_fraction', 2)} | "
                    f"{_generation_value(r1_1, 'generation_time_s', 3)} | "
                    f"{_generation_value(r1_2, 'candidate_attempts')} | "
                    f"{_generation_value(r1_2, 'rejection_fraction', 2)} | "
                    f"{_generation_value(r1_2, 'generation_time_s', 3)} |"
                )
        distribution_records = {}
        distribution_path = out / "stage3_8c_initializer_distribution_comparison.csv"
        if distribution_path.is_file():
            with distribution_path.open("r", encoding="utf-8", newline="") as stream:
                for distribution_row in csv.DictReader(stream):
                    if distribution_row.get("parameter") in {"electrodes", "length_um"}:
                        distribution_records[(distribution_row.get("material"),
                                               distribution_row.get("topology"),
                                               distribution_row.get("revision"),
                                               distribution_row.get("parameter"))] = distribution_row
        distribution_lines = []
        for material in MATERIALS:
            for topology in TOPOLOGIES:
                for metric in ("electrodes", "length_um"):
                    medians = {
                        revision_name: distribution_records.get(
                            (material, topology, revision_name, metric), {}
                        ).get("median", "n/a")
                        for revision_name in ("R1", "R1.1", "R1.2", "R1.2_MC_reference")
                    }
                    distribution_lines.append(
                        f"| {material} | {topology} | {metric} | {medians['R1']} | "
                        f"{medians['R1.1']} | {medians['R1.2']} | {medians['R1.2_MC_reference']} |"
                    )
        readme = (
            f"Stage 3.8C-R1.2 Pilot: {result_label}\n\n"
            f"# Review bundle\n\nRun directory: `{out}`. Source/config fingerprint: `{gate.get('source_config_fingerprint')}`.\n\n"
            "## Required review summary\n\n"
            "1. R1.2 uses independent real-uniform proposals, existing integer canonicalization, hard geometry validation, and rejection/resampling. Invalid candidates are not repaired.\n"
            "2. R1.1 conditional integer sampling remains available for historical pilot reproduction; it is not the R1.2/default initializer.\n"
            "3. Initializer generation comparison (historical R1 attempt/rejection counts; saved R1.1/R1.2 diagnostics):\n\n"
            "| Material | Topology | R1 attempts | R1 rejects | R1 rejection fraction | R1 time (s) | R1.1 attempts | R1.1 rejection fraction | R1.1 time (s) | R1.2 attempts | R1.2 rejection fraction | R1.2 time (s) |\n"
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n"
            + "\n".join(generation_lines) + "\n\n"
            "4. Distribution medians for total electrodes and total acoustic length (additional variable quantiles and means/std are in the comparison CSV):\n\n"
            "| Material | Topology | Metric | R1 median | R1.1 median | R1.2 median | R1.2 MC reference median |\n|---|---|---|---:|---:|---:|---:|\n"
            + "\n".join(distribution_lines) + "\n\n"
            f"5. Geometry-valid initial populations: {sum(int(row.get('geometry_valid_members', 0)) == int(row.get('population_size', 0)) for row in population_preflight)}/6.\n"
            f"6. Physics-valid cells with finite search/common metrics: {physics_cells}/6.\n"
            f"7. Fixed-design sanity: {fixed_passes}/6 PASS.\n"
            "8. Full repository test results are in `test_summary.md`.\n"
            "9. GPT-6 Sol route: see `gpt6sol_routing_test_results.json`; the request was accepted, hidden backend identity is NOT VERIFIED.\n"
            "10. Production: NOT STARTED. R1.2 is pilot-only and stops for review.\n"
            "11. Limitations: one seed and 256 evaluations are diagnostic only; `promotion_eligible=false`, `seed_consistency=N/A_single_seed`. M0 aperture is 30–150 um and MLIT aperture is 30–180 um, so cross-material differences are confounded. R1.1 and R1.2 use different initial distributions, so performance changes are not optimizer regressions.\n\n"
            "Rejection fraction is diagnostic, not a PASS/FAIL gate. The hard geometry and all other study conditions remain unchanged.\n"
        )
    else:
        readme = (
            f"# Stage 3.8C-{revision} review bundle\n\n"
            f"Mode: `{mode}`. Run directory: `{out}`.\n\n"
            "Geometry hard feasibility is ranked before filter feasibility. The legacy Stage 3.8 rankings are invalidated. "
            "MLIT's 30–180 um aperture range is recorded as an R1 user-directed override; Stage 3.7D's archived recommendation is 30–150 um. "
            "Cross-material comparisons are confounded by the different aperture search ranges.\n"
        )
    (bundle / "REVIEW_ME.md").write_text(readme, encoding="utf-8")

    if revision == "R1.1":
        reproducibility = bundle / "reproducibility"
        reproducibility.mkdir(parents=True, exist_ok=True)
        _copy_if_exists(
            ROOT / "reports" / "stage3_8c_r1_1_pre_work_git_state.json",
            reproducibility / "pre_work_git_state.json",
        )
        def git_output(*args: str) -> str:
            completed = subprocess.run(
                ["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace",
                capture_output=True, check=False,
            )
            return completed.stdout.strip()
        _write_json(reproducibility / "post_work_git_state.json", {
            "head": git_output("rev-parse", "HEAD"),
            "branch": git_output("branch", "--show-current"),
            "status_short": git_output("status", "--short"),
            "diff_stat": git_output("diff", "--stat"),
            "cached_diff_stat": git_output("diff", "--cached", "--stat"),
        })
        snapshot_files = (
            "AGENTS.md",
            "configs/studies/stage3_8c_r1_1_pilot.yaml",
            "src/sawopt/studies/stage3_8c_r1_geometry_gate.py",
            "src/sawopt/studies/stage3_8_dual_material_dms_topology_fast_screen.py",
            "tests/unit/studies/test_stage3_8c_r1_geometry_gate.py",
            "tests/unit/test_sol_review_routing_policy.py",
            "reports/escalation_log.md",
        )
        source_snapshot = bundle / "source_snapshot"
        for relative in snapshot_files:
            _copy_if_exists(ROOT / relative, source_snapshot / relative)
        scoped = subprocess.run(
            ["git", "diff", "--", "AGENTS.md", "reports/escalation_log.md"],
            cwd=ROOT, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False,
        )
        (reproducibility / "scoped_tracked_diff.patch").write_text(
            scoped.stdout or "", encoding="utf-8",
        )

    if revision == "R1.2":
        reproducibility = bundle / "reproducibility"
        reproducibility.mkdir(parents=True, exist_ok=True)
        if mode == "production":
            _copy_if_exists(
                ROOT / "reports" / "stage3_8c_r1_2_final_confirmation_source_freeze.json",
                reproducibility / "final_confirmation_source_freeze.json",
            )
        else:
            _copy_if_exists(
                ROOT / "reports" / "stage3_8c_r1_2_pre_work_git_state.json",
                reproducibility / "pre_work_git_state.json",
            )
        def git_output(*args: str) -> str:
            completed = subprocess.run(
                ["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace",
                capture_output=True, check=False,
            )
            return completed.stdout.strip()
        _write_json(reproducibility / "post_work_git_state.json", {
            "head": git_output("rev-parse", "HEAD"),
            "branch": git_output("branch", "--show-current"),
            "status_short": git_output("status", "--short"),
            "diff_stat": git_output("diff", "--stat"),
            "cached_diff_stat": git_output("diff", "--cached", "--stat"),
        })
        snapshot_files = (
            "AGENTS.md",
            "configs/studies/stage3_8c_r1_2_pilot.yaml",
            "configs/studies/stage3_8c_r1_2_final_confirmation.yaml",
            "configs/studies/stage3_8c_r1_2_production.yaml",
            "src/sawopt/studies/stage3_8c_r1_geometry_gate.py",
            "src/sawopt/studies/stage3_8_dual_material_dms_topology_fast_screen.py",
            "tests/unit/studies/test_stage3_8c_r1_geometry_gate.py",
            "tests/unit/test_sol_review_routing_policy.py",
            "reports/stage3_8c_r1_2_initializer_escalation.md",
            "reports/stage3_8c_r1_2_test_summary.md",
            "reports/stage3_8c_r1_2_final_confirmation_test_gate.json",
            "reports/stage3_8c_r1_2_final_confirmation_source_freeze.json",
            "reports/stage3_8c_r1_2_gpt6sol_routing_test_results.json",
            "reports/escalation_log.md",
        )
        source_snapshot = bundle / "source_snapshot"
        for relative in snapshot_files:
            _copy_if_exists(ROOT / relative, source_snapshot / relative)
        scoped = subprocess.run(
            ["git", "diff", "--", "configs/studies/stage3_8c_r1_2_pilot.yaml",
             "configs/studies/stage3_8c_r1_2_final_confirmation.yaml",
             "configs/studies/stage3_8c_r1_2_production.yaml",
             "src/sawopt/studies/stage3_8c_r1_geometry_gate.py",
             "tests/unit/studies/test_stage3_8c_r1_geometry_gate.py",
             "reports/escalation_log.md"],
            cwd=ROOT, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False,
        )
        (reproducibility / "scoped_source_diff.patch").write_text(
            scoped.stdout or "", encoding="utf-8",
        )

    run_source_path = out / "metadata" / "run_source_metadata.json"
    run_source = json.loads(run_source_path.read_text(encoding="utf-8")) if run_source_path.is_file() else {}
    zip_path = artifact_root / f"{bundle.name}.zip"
    write_review_bundle_archive(
        bundle,
        zip_path,
        study_type=STUDY_TYPE,
        run_directory=out,
        required_artifacts=("REVIEW_ME.md",),
        metadata={
            "schema_version": 1,
            "mode": mode,
            "source_config_fingerprint": run_source.get("source_config_fingerprint"),
            "gate": _clean(gate),
        },
        archive_prefix=bundle.name,
        repository_root=ROOT,
    )
    return bundle
