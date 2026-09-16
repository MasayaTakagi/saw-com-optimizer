"""Stage 3.6 Phase C1-C2 DOF release screening at 50/50 ohm.

This study owns its release-space schema and decoder.  The legacy seven
variable ``NAMES``/``BOUNDS`` contract and the L-SHADE backend are unchanged.
The release geometry keeps the mirrored nine-region topology while allowing
only section-class wavelength/aperture overrides selected by the Gate 2A
design review.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import multiprocessing as mp
import shutil
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Mapping
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np

from ..core.com import acoustic_admittance, validate_admittance, block
from ..core.metrics import geometry, search_grid, validation_grid, measure
from ..core.models import BOUNDS, NAMES, FilterDesign, FixedProvider, SimulationResult, decode
from ..core.network import evaluate
from ..io.config import load_experiment_config
from ..io.run_store import initialize
from ..io.serialization import save
from ..optimizers.lshade import LShadeBackend
from ..optimizers.selection import DEFAULT_COMPARATOR, rank
from ..optimization.adaptive_frequency import critical_frequencies, new_frequency_points
from ..optimization.cache import IncrementalFrequencyCache
from ..runtime.parallel import single_blas_thread_environment
from .convergence import normalize_convergence_config
from .convergence_evidence import apply_checkpoint_evidence
from .optimizer_ab import lshade_record


ROOT = Path(__file__).resolve().parents[3]
STUDY_TYPE = "stage3_6_phase_c1_c2_gate2a"
WIRING = "center_outer_same"
ZPORT = 50.0
SCHEMA_VERSION = 1
BASELINE_GROUP = "G0_CURRENT_REDUCED"
INDIVIDUAL_GROUPS = ("G1_CENTER_PITCH", "G2_REFLECTOR_PITCH", "G3_CENTER_APERTURE")
INTERACTION_GROUPS = ("G1_G2", "G1_G3", "G1_G2_G3")


_GROUP_EXTRA_SOURCES = {
    "G1_CENTER_PITCH": ("center_wavelength_um", "wavelength_um"),
    "G2_REFLECTOR_PITCH": ("reflector_wavelength_um", "wavelength_um"),
    "G3_CENTER_APERTURE": ("center_aperture_um", "aperture_um"),
}


@dataclass(frozen=True)
class ReleaseSection:
    region: str
    length_lambda: float
    wavelength_um: float
    aperture_um: float
    electrodes: float
    port: int | None
    metallization_ratio: float


@dataclass(frozen=True)
class ReleasedFilterDesign:
    """Legacy design fields plus optional section-class overrides."""

    wavelength_um: float = 5.0
    io_idt_pairs: int = 24
    center_idt_pairs: int = 16
    reflector_electrodes: int = 40
    idt_gap_lambda: float = 0.5
    reflector_gap_lambda: float = 0.5
    aperture_um: float = 80.0
    metallization_ratio: float = 0.5
    thickness_over_lambda: float = 0.04
    center_wavelength_um: float | None = None
    reflector_wavelength_um: float | None = None
    center_aperture_um: float | None = None

    def section_geometry(self) -> tuple[dict[str, Any], ...]:
        """Return the immutable mirrored R-gap-O-gap-C-gap-O-gap-R profile."""
        center_lambda = self.center_wavelength_um or self.wavelength_um
        reflector_lambda = self.reflector_wavelength_um or self.wavelength_um
        center_aperture = self.center_aperture_um or self.aperture_um
        # Gap lengths intentionally retain the global wavelength reference.
        return (
            asdict(ReleaseSection("reflector", self.reflector_electrodes / 2,
                                  reflector_lambda, self.aperture_um,
                                  self.reflector_electrodes, None,
                                  self.metallization_ratio)),
            asdict(ReleaseSection("gap", self.reflector_gap_lambda,
                                  self.wavelength_um, self.aperture_um,
                                  0.0, None, self.metallization_ratio)),
            asdict(ReleaseSection("idt", self.io_idt_pairs,
                                  self.wavelength_um, self.aperture_um,
                                  2 * self.io_idt_pairs, 0,
                                  self.metallization_ratio)),
            asdict(ReleaseSection("gap", self.idt_gap_lambda,
                                  self.wavelength_um, self.aperture_um,
                                  0.0, None, self.metallization_ratio)),
            asdict(ReleaseSection("idt", self.center_idt_pairs,
                                  center_lambda, center_aperture,
                                  2 * self.center_idt_pairs, 1,
                                  self.metallization_ratio)),
            asdict(ReleaseSection("gap", self.idt_gap_lambda,
                                  self.wavelength_um, self.aperture_um,
                                  0.0, None, self.metallization_ratio)),
            asdict(ReleaseSection("idt", self.io_idt_pairs,
                                  self.wavelength_um, self.aperture_um,
                                  2 * self.io_idt_pairs, 2,
                                  self.metallization_ratio)),
            asdict(ReleaseSection("gap", self.reflector_gap_lambda,
                                  self.wavelength_um, self.aperture_um,
                                  0.0, None, self.metallization_ratio)),
            asdict(ReleaseSection("reflector", self.reflector_electrodes / 2,
                                  reflector_lambda, self.aperture_um,
                                  self.reflector_electrodes, None,
                                  self.metallization_ratio)),
        )


def _clean(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return [_clean(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _clean(value.item())
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(set().union(*(row.keys() for row in rows))) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _extra_names(group: str) -> tuple[str, ...]:
    if group == BASELINE_GROUP:
        return ()
    if group in _GROUP_EXTRA_SOURCES:
        return (_GROUP_EXTRA_SOURCES[group][0],)
    if group == "G1_G2":
        return ("center_wavelength_um", "reflector_wavelength_um")
    if group == "G1_G3":
        return ("center_wavelength_um", "center_aperture_um")
    if group == "G1_G2_G3":
        return ("center_wavelength_um", "reflector_wavelength_um", "center_aperture_um")
    raise ValueError(f"unknown release group: {group}")


def _source_variable(extra_name: str) -> str:
    for name, source in _GROUP_EXTRA_SOURCES.values():
        if name == extra_name:
            return source
    raise ValueError(f"unknown released variable: {extra_name}")


def release_schema(group: str, s1: Mapping[str, Any]) -> dict[str, Any]:
    extras = []
    for name in _extra_names(group):
        source = _source_variable(name)
        item = s1["bounds"][source]
        extras.append({
            "name": name,
            "type": "continuous",
            "source_variable": source,
            "initial": [float(value) for value in item["initial"]],
            "hard": [float(value) for value in item["hard"]],
            "sharing": "center_only" if name.startswith("center_") else "both_reflectors",
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "group": group,
        "base_variable_names": list(NAMES),
        "base_dimension": len(NAMES),
        "extra_variables": extras,
        "dimension": len(NAMES) + len(extras),
        "topology": "reflector-gap-outer-idt-gap-center-idt-gap-outer-idt-gap-reflector",
        "mirrored_outer_sections": True,
        "objective_unchanged": True,
        "validation_protocol_unchanged": True,
    }


def release_bounds(group: str, s1: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, tuple[int, ...]]:
    active = [list(s1["bounds"][name]["initial"]) for name in NAMES]
    hard = [list(s1["bounds"][name]["hard"]) for name in NAMES]
    integer_indices = [1, 2, 3]
    for extra in release_schema(group, s1)["extra_variables"]:
        active.append(list(extra["initial"]))
        hard.append(list(extra["hard"]))
    return np.asarray(active, dtype=float), np.asarray(hard, dtype=float), tuple(integer_indices)


def decode_release(vector: Iterable[float], group: str) -> ReleasedFilterDesign:
    values = np.asarray(list(vector), dtype=float)
    expected = len(NAMES) + len(_extra_names(group))
    if values.shape != (expected,) or not np.isfinite(values).all():
        raise ValueError(f"{group} requires a finite vector with dimension {expected}")
    base = decode(values[:len(NAMES)])
    extra = {
        name: float(values[len(NAMES) + index])
        for index, name in enumerate(_extra_names(group))
    }
    return ReleasedFilterDesign(**asdict(base), **extra)


def _design_from_record(value: Mapping[str, Any]) -> ReleasedFilterDesign:
    allowed = {field.name for field in ReleasedFilterDesign.__dataclass_fields__.values()}
    return ReleasedFilterDesign(**{key: value[key] for key in allowed if key in value})


def _shared_base_design(value: Mapping[str, Any]) -> FilterDesign:
    return FilterDesign(**{key: value[key] for key in asdict(FilterDesign())})


def simulate_released_filter(
    design: ReleasedFilterDesign, com_provider, frequencies_hz, center="grounded",
    wiring=WIRING, debug_diagnostics=False,
) -> SimulationResult:
    if center not in ("grounded", "floating"):
        raise ValueError("Unknown center termination")
    profile = design.section_geometry()
    regions = [(item["region"], item["length_lambda"], item["port"]) for item in profile]
    section_geometries = [SimpleNamespace(
        wavelength_um=float(item["wavelength_um"]),
        aperture_um=float(item["aperture_um"]),
    ) for item in profile]
    frequencies_hz = np.asarray(frequencies_hz, dtype=float)
    y, solve_diagnostics = acoustic_admittance(
        design, com_provider, frequencies_hz, regions, 3,
        return_diagnostics=True, debug_diagnostics=debug_diagnostics,
        section_geometries=section_geometries,
    )
    if wiring in ("center_outer_same", "center_outer_opposite"):
        sign = 1 if wiring == "center_outer_same" else -1
        B = np.array([[0, 1], [1, 0], [0, sign]])
        out = B.T @ y @ B
    elif wiring == "outer_ports":
        out = y[:, [0, 2]][:, :, [0, 2]]
        if center == "floating":
            ycc = y[:, 1, 1]
            if np.any(np.abs(ycc) < np.finfo(float).tiny):
                raise ValueError("Floating-center elimination is singular (Ycc is zero)")
            out -= y[:, [0, 2], 1, None] * y[:, None, 1, [0, 2]] / ycc[:, None, None]
    else:
        raise ValueError("Unknown DMS wiring")
    diagnostics = validate_admittance(out, frequencies_hz=frequencies_hz)
    diagnostics.update(solve_diagnostics)
    return SimulationResult(frequencies_hz, out, diagnostics)


def evaluate_released_design(design, cfg, frequencies, rs, rl, wiring=WIRING):
    sim = simulate_released_filter(design, FixedProvider(cfg["com"]), frequencies,
                                    cfg["center"], wiring=wiring)
    net = evaluate(sim.y_parameters, rs, rl)
    if net["gt"].max() > 1 + 1e-7:
        raise ValueError("Nonpassive power gain")
    result = measure(frequencies, net, design, cfg)
    result["diagnostics"] = sim.diagnostics
    result["search_scalar_objective"] = result["objective"]
    return result, net, sim


def release_evaluator_factory(cfg, z0, wiring, frequencies, group):
    frequency_ref = [np.asarray(frequencies, dtype=float)]

    def evaluator(vector):
        design = decode_release(vector, group)
        _dims, violations = geometry(design, cfg["constraints"])
        try:
            record, _net, _sim = evaluate_released_design(
                design, cfg, frequency_ref[0], z0, z0, wiring=wiring
            )
        except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
            return {
                "design": asdict(design),
                "metrics": {"worst_il_db": float("inf"), "ripple_db": float("inf")},
                "violations": {"geometry": max(violations, default=0.0), "numerical_failure": 1.0},
                "max_violation": 1.0,
                "sum_violation": 1.0 + sum(violations),
                "feasible": False,
                "failure": str(exc),
                "objective": float("inf"),
                "search_scalar_objective": float("inf"),
            }
        record = dict(record)
        record["design"] = asdict(design)
        record.setdefault("violations", {})["geometry"] = max(violations, default=0.0)
        record["sum_violation"] = float(sum(record.get("violations", {}).values()))
        record["max_violation"] = float(max(record.get("violations", {}).values(), default=0.0))
        record["feasible"] = bool(record["max_violation"] <= 1e-10)
        return record

    evaluator.frequency_ref = frequency_ref
    return evaluator


def release_dense(design, cfg, rs, rl, wiring=WIRING, *, base_grid=None,
                  passes=None, validation=False, counters=None):
    frequencies = validation_grid(cfg["spec"], cfg) if base_grid is None else np.unique(np.asarray(base_grid, dtype=float))
    passes = int(cfg.get("validation", {}).get("dense_refinement_passes", 2)) if passes is None else int(passes)
    slope = float(cfg.get("dense_slope_threshold_db", .5))
    tolerance = float(cfg.get("validation", {}).get("adaptive_frequency_tolerance_hz", 1e3))

    def point_evaluate(points):
        sim = simulate_released_filter(design, FixedProvider(cfg["com"]), points,
                                        cfg["center"], wiring=wiring)
        net = evaluate(sim.y_parameters, rs, rl)
        if net["gt"].max() > 1 + 1e-7:
            raise ValueError("Nonpassive power gain")
        payload = dict(net)
        payload["y_parameters"] = sim.y_parameters
        payload["_diagnostics"] = sim.diagnostics
        return payload

    cache = IncrementalFrequencyCache(point_evaluate)
    solved_seen = 0

    def cached_evaluate(points):
        nonlocal solved_seen
        payload = cache.evaluate(points)
        solved_delta = cache.solved_points - solved_seen
        solved_seen = cache.solved_points
        if counters is not None:
            counters.add_solved(solved_delta, validation=validation)
            counters.add_evaluation_time(cache.last_evaluation_wall_time_s, validation=validation)
        net = {key: value for key, value in payload.items()
               if key not in ("frequencies_hz", "y_parameters", "_diagnostics")}
        evaluated = np.asarray(payload["frequencies_hz"], dtype=float)
        sim = SimulationResult(evaluated, np.asarray(payload["y_parameters"]),
                               payload.get("_diagnostics", {}))
        result = measure(evaluated, net, design, cfg)
        result["diagnostics"] = sim.diagnostics
        return result, net, sim

    for _ in range(max(0, passes)):
        result, net, _sim = cached_evaluate(frequencies)
        critical = critical_frequencies(
            frequencies, net, cfg["spec"], slope_threshold_db=slope,
            max_points=int(cfg.get("validation", {}).get("adaptive_max_points_per_round", 64)),
        )
        added = new_frequency_points(frequencies, critical, tolerance)
        if len(added) == 0:
            break
        frequencies = np.unique(np.r_[frequencies, added])
    return frequencies, cached_evaluate(frequencies)


def _backend_config(cfg, terminal, dimension, hard_bounds):
    values = dict(cfg.get("stage3_3", {}).get("lshade", {}))
    values.update({
        "total_budget": int(terminal),
        "hard_max_budget": int(terminal),
        "population_schedule_terminal_budget": int(terminal),
        "initial_population": max(4, 18 * int(dimension)),
        "hard_bounds": np.asarray(hard_bounds, dtype=float).tolist(),
    })
    return values


def _release_exchange(backend, evaluator, cfg, group, wiring, z0, checkpoint_budget):
    event = {
        "event": "adaptive_frequency_check",
        "checkpoint_budget": int(checkpoint_budget),
        "frequency_grid_version_before": int(backend.frequency_grid_version),
        "unique_designs_charged": 0,
        "added_count": 0,
        "grid_fixed": True,
        "frequencies_hz": [],
    }
    if not bool(cfg.get("stage3_3", {}).get("adaptive_frequency_exchange", True)):
        event["disabled"] = True
        event["frequency_grid_version_after"] = int(backend.frequency_grid_version)
        return event
    incumbent = backend.incumbent()
    if not incumbent:
        event["skipped"] = "no_incumbent"
        event["frequency_grid_version_after"] = int(backend.frequency_grid_version)
        return event
    design = _design_from_record(incumbent["design"])
    dense_f, (_dense_result, dense_net, _dense_sim) = release_dense(
        design, cfg, z0, z0, wiring=wiring, passes=0, validation=True,
    )
    critical = critical_frequencies(
        dense_f, dense_net, cfg["spec"],
        slope_threshold_db=float(cfg.get("dense_slope_threshold_db", .5)),
        max_points=int(cfg.get("validation", {}).get("adaptive_max_points_per_round", 64)),
    )
    added = new_frequency_points(
        evaluator.frequency_ref[0], critical,
        float(cfg.get("validation", {}).get("adaptive_frequency_tolerance_hz", 1e3)),
    )
    if len(added):
        evaluator.frequency_ref[0] = np.unique(np.r_[evaluator.frequency_ref[0], added])
        version = int(backend.frequency_grid_version) + 1
        backend.exchange_frequency_grid(evaluator.frequency_ref[0], evaluator, version=version)
        event.update({
            "event": "critical_frequency_exchange",
            "added_count": int(len(added)),
            "grid_fixed": False,
            "frequency_grid_version_after": version,
            "frequencies_hz": [float(value) for value in added],
        })
    else:
        event["frequency_grid_version_after"] = int(backend.frequency_grid_version)
    return event


def _checkpoint_guard(path: Path, group: str, bounds: np.ndarray) -> None:
    state = _json(path)
    saved = np.asarray(state.get("bounds", []), dtype=float)
    if saved.shape != bounds.shape or not np.array_equal(saved, bounds):
        raise ValueError("release checkpoint bounds/schema dimension mismatch; cold start is required")


def _release_worker(payload):
    out, cfg, group, s1, seed, budgets, resume = payload
    out = Path(out)
    budgets = sorted({int(value) for value in budgets})
    if not budgets or any(value <= 0 for value in budgets):
        raise ValueError("release trajectory budgets must be positive")
    schema = release_schema(group, s1)
    active_bounds, hard_bounds, integer_indices = release_bounds(group, s1)
    seed_dir = out / "groups" / group / "trials" / "lshade" / WIRING / f"seed{int(seed)}"
    seed_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = seed_dir / "optimizer_checkpoint.json"
    metadata_path = seed_dir / "trajectory_metadata.json"
    disk_resume_used = False
    if resume and checkpoint_path.exists():
        if not metadata_path.exists():
            raise ValueError("release checkpoint metadata is missing")
        metadata = _json(metadata_path)
        if metadata.get("release_schema") != schema:
            raise ValueError("release checkpoint schema mismatch; cold start is required")
        _checkpoint_guard(checkpoint_path, group, active_bounds)
        disk_resume_used = True
    else:
        metadata = {}
    z0 = float(cfg.get("convergence", {}).get("impedance_ohm", ZPORT))
    frequencies = np.unique(search_grid(cfg["spec"], cfg))
    evaluator = release_evaluator_factory(cfg, z0, WIRING, frequencies, group)
    terminal = int(cfg["stage3_6_gate2a"].get("terminal_budget", max(budgets)))
    lshade_cfg = _backend_config(cfg, terminal, len(active_bounds), hard_bounds)
    fingerprint = hashlib.sha256(json.dumps({
        "cfg": cfg, "schema": schema, "active": active_bounds.tolist(),
        "hard": hard_bounds.tolist(),
    }, sort_keys=True, default=str).encode()).hexdigest()
    backend = LShadeBackend(
        active_bounds, seed=int(seed), config=lshade_cfg,
        integer_indices=integer_indices, comparator=DEFAULT_COMPARATOR,
        source_config_fingerprint=fingerprint,
    )
    if disk_resume_used:
        backend.load_checkpoint(checkpoint_path)
        backend.set_evaluator(evaluator)
        if getattr(backend, "active_frequency_grid", []):
            evaluator.frequency_ref[0] = np.asarray(backend.active_frequency_grid, dtype=float)
    else:
        backend.initialize(evaluator)
        backend.set_frequency_grid(frequencies, version=1)
        metadata = {"last_completed_budget": 0, "frequency_grid_events": []}
    events = list(metadata.get("frequency_grid_events", []))
    last_completed = int(metadata.get("last_completed_budget", 0))
    records = []
    started_wall = time.monotonic()
    started_cpu = time.process_time()
    for index, budget in enumerate(budgets):
        result_path = seed_dir / f"B{budget}.json"
        if disk_resume_used and last_completed >= budget and result_path.exists():
            records.append(_json(result_path))
            continue
        optimizer_started = time.monotonic()
        if backend.unique_evaluations < budget:
            backend.advance_to_unique_budget(budget)
        optimizer_wall = time.monotonic() - optimizer_started
        pre_exchange = copy.deepcopy(backend.incumbent())
        validation_started = time.monotonic()
        event = _release_exchange(backend, evaluator, cfg, group, WIRING, z0, budget)
        validation_wall = time.monotonic() - validation_started
        events.append(event)
        last_completed = budget
        metadata = {
            "last_completed_budget": int(last_completed),
            "frequency_grid_events": events,
            "trajectory_semantics": "one_seed_one_release_trajectory",
            "release_schema": schema,
            "active_bounds": active_bounds.tolist(),
            "hard_bounds": hard_bounds.tolist(),
        }
        record = lshade_record(
            backend, WIRING, seed, budget, checkpoint_path, events,
            started_wall, started_cpu, disk_resume_used=disk_resume_used,
            trajectory_index=index, optimizer_wall_time_s=optimizer_wall,
            validation_wall_time_s=validation_wall,
            total_trial_wall_time_s=time.monotonic() - started_wall,
        )
        record["stage3_6_group"] = group
        record["release_schema"] = schema
        record["release_dimension"] = int(schema["dimension"])
        record["pre_exchange_snapshot"] = _clean(pre_exchange or {})
        record = _clean(record)
        save(result_path, record)
        backend.save_checkpoint(checkpoint_path)
        save(metadata_path, metadata)
        records.append(record)
    return records


def _run_workers(tasks, workers, threads=1):
    with single_blas_thread_environment(threads):
        if int(workers) == 1:
            return [_release_worker(task) for task in tasks]
        context = mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=int(workers), mp_context=context) as pool:
            return list(pool.map(_release_worker, tasks))


def _load_s1(cfg):
    section = cfg.get("stage3_6_gate2a", {})
    raw = Path(section.get("s1_path", "artifacts/stage3_5/phase_a_revised/search_space_s1.yaml"))
    path = raw if raw.is_absolute() else ROOT / raw
    if not path.is_file():
        raise FileNotFoundError(f"frozen S1 config is missing: {path}")
    import yaml
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not document.get("freeze") or not document.get("hard_bounds_unchanged"):
        raise ValueError("S1 config is not marked frozen with unchanged hard bounds")
    return document, path


def _stage_section(cfg):
    section = dict(cfg.get("stage3_6_gate2a", {}))
    seeds = [int(value) for value in section.get("seeds", [20260917, 20260918, 20260919])]
    if seeds != [20260917, 20260918, 20260919]:
        raise ValueError("Gate 2A requires the canonical three paired seeds")
    if int(section.get("screening_budget", 16000)) != 16000:
        raise ValueError("Gate 2A initial screening budget must be 16000")
    if int(section.get("promotion_budget", 32000)) != 32000:
        raise ValueError("Gate 2A promotion budget must be 32000")
    workers = max(1, min(int(section.get("workers", len(seeds))), len(seeds)))
    section.update({"seeds": seeds, "screening_budget": 16000,
                    "promotion_budget": 32000, "workers": workers,
                    "terminal_budget": 32000})
    return section


def _base_record_paths(section, seeds, budgets=(16000, 32000)):
    root = Path(section.get("reduced_baseline_run", "runs/stage3_5_phase_c_revised"))
    if not root.is_absolute():
        root = ROOT / root
    arm = str(section.get("reduced_baseline_arm", "D_S1_LSHADE"))
    segment = str(section.get("reduced_baseline_segment", "phase_c1"))
    source = root / "arms" / arm / segment / "trials" / "lshade" / WIRING
    return [(seed, budget, source / f"seed{seed}" / f"B{budget}.json")
            for seed in seeds for budget in budgets]


def _reuse_baseline(run, section, seeds):
    output = []
    manifest = {"source": [], "reused": True, "group": BASELINE_GROUP}
    for seed, budget, source in _base_record_paths(section, seeds):
        if not source.is_file():
            raise FileNotFoundError(f"reusable Stage 3.5 baseline is missing: {source}")
        target = run / "reused_baseline" / BASELINE_GROUP / f"seed{seed}" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        record = dict(_json(source))
        record.update({
            "stage3_6_group": BASELINE_GROUP,
            "stage3_6_reused": True,
            "stage3_6_source": str(source.relative_to(ROOT)),
        })
        output.append(record)
        manifest["source"].append({"seed": seed, "budget": budget,
                                    "path": str(source.relative_to(ROOT)),
                                    "sha256": _sha256(source)})
    save(run / "reused_baseline_manifest.json", manifest)
    return output


def _group_records(run, group):
    records = []
    for path in sorted((run / "groups" / group / "trials" / "lshade" / WIRING).glob("seed*/B*.json")):
        record = dict(_json(path))
        record["_record_path"] = str(path.relative_to(run))
        records.append(record)
    return records


def _all_records(run, baseline, groups):
    values = {BASELINE_GROUP: list(baseline)}
    for group in groups:
        values[group] = _group_records(run, group)
    return values


def _common_grid(cfg, record_map):
    grid = np.asarray(validation_grid(cfg["spec"], cfg), dtype=float)
    for group, records in record_map.items():
        for record in records:
            try:
                if group == BASELINE_GROUP:
                    design = _shared_base_design(record["design"])
                    from ..problem.evaluator import dense
                    refined, _payload = dense(design, cfg, ZPORT, ZPORT,
                                              wiring=WIRING, validation=True)
                else:
                    design = _design_from_record(record["design"])
                    refined, _payload = release_dense(design, cfg, ZPORT, ZPORT,
                                                      wiring=WIRING, validation=True)
                grid = np.unique(np.r_[grid, refined])
            except (KeyError, TypeError, ValueError, np.linalg.LinAlgError, FloatingPointError):
                continue
    return np.unique(grid)


def _validate_record(cfg, group, record, grid):
    if group == BASELINE_GROUP:
        design = _shared_base_design(record["design"])
        from ..problem.evaluator import dense
        _f, (validated, _net, _sim) = dense(
            design, cfg, ZPORT, ZPORT, wiring=WIRING,
            base_grid=grid, passes=0, validation=True,
        )
    else:
        design = _design_from_record(record["design"])
        _f, (validated, _net, _sim) = release_dense(
            design, cfg, ZPORT, ZPORT, wiring=WIRING,
            base_grid=grid, passes=0, validation=True,
        )
    validated = dict(validated)
    metrics = dict(validated.get("metrics", {}))
    violations = dict(validated.get("violations", {}))
    rank_tuple = tuple(float(value) for value in rank(validated))
    return {
        "group": group,
        "seed": int(record["seed"]),
        "budget": int(record.get("requested_unique_design_budget", record.get("current_budget", 0))),
        "reused": bool(record.get("stage3_6_reused", False)),
        "feasible": bool(validated.get("feasible", False)),
        "max_violation": float(validated.get("max_violation", np.inf)),
        "sum_violation": float(sum(violations.values())),
        "worst_il_db": float(metrics.get("worst_il_db", np.inf)),
        "ripple_db": float(metrics.get("ripple_db", np.inf)),
        "source_return_loss_db_min": float(metrics.get("source_return_loss_db_min", np.inf)),
        "load_return_loss_db_min": float(metrics.get("load_return_loss_db_min", np.inf)),
        "stop_attenuation_db": json.dumps(metrics.get("stop_attenuation_db", [])),
        "objective": float(validated.get("objective", np.inf)),
        "objective_components": json.dumps(_clean(validated.get("objective_parts", {})), sort_keys=True),
        "all_metrics": json.dumps(_clean(metrics), sort_keys=True),
        "all_violations": json.dumps(_clean(violations), sort_keys=True),
        "validated_rank_tuple": json.dumps(list(rank_tuple)),
        "design": json.dumps(_clean(record["design"]), sort_keys=True),
        "unique_decoded_evaluations": int(record.get("unique_decoded_evaluations", 0)),
        "objective_calls": int(record.get("objective_calls", 0)),
        "elapsed_s": float(record.get("elapsed_s", 0.0)),
        "release_dimension": int(record.get("release_dimension", len(NAMES))),
    }


def _released_utilization(group, row):
    design = json.loads(row["design"])
    values = {}
    for name in _extra_names(group):
        source = design.get("wavelength_um" if name.endswith("wavelength_um") else "aperture_um")
        released = design.get(name)
        values[name] = {
            "value": released,
            "base_value": source,
            "delta": None if released is None else float(released) - float(source),
            "normalized_delta": None if released is None else (
                float(released) - float(source)
            ) / max(abs(float(source)), np.finfo(float).tiny),
        }
    return values


def _promotion_decision(rows, section):
    by_group = {}
    for row in rows:
        by_group.setdefault(row["group"], {}).setdefault(int(row["budget"]), {})[int(row["seed"])] = row
    baseline = by_group[BASELINE_GROUP][16000]
    decisions = []
    for group in INDIVIDUAL_GROUPS:
        candidate = by_group.get(group, {}).get(16000, {})
        paired = []
        for seed in section["seeds"]:
            if seed in baseline and seed in candidate:
                paired.append({
                    "seed": seed,
                    "candidate_max_violation": candidate[seed]["max_violation"],
                    "baseline_max_violation": baseline[seed]["max_violation"],
                    "delta_max_violation": candidate[seed]["max_violation"] - baseline[seed]["max_violation"],
                    "candidate_sum_violation": candidate[seed]["sum_violation"],
                    "baseline_sum_violation": baseline[seed]["sum_violation"],
                })
        deltas = [item["delta_max_violation"] for item in paired]
        improvement_count = sum(delta < 0 for delta in deltas)
        median_delta = float(np.median(deltas)) if deltas else float("inf")
        row = {
            "group": group,
            "screening_budget": 16000,
            "paired_seed_count": len(paired),
            "paired": paired,
            "improvement_seed_count": improvement_count,
            "median_delta_max_violation": median_delta,
            "released_dof_utilization": [
                _released_utilization(group, candidate[seed])
                for seed in sorted(candidate)
            ],
            "promote_to_32k": bool(
                improvement_count >= 2 and median_delta < 0
            ),
            "decision_rule": "2_of_3_primary_and_positive_median_improvement",
        }
        decisions.append(row)
    return {
        "screening_budget": 16000,
        "promotion_budget": 32000,
        "individual": decisions,
        "promoted_groups": [row["group"] for row in decisions if row["promote_to_32k"]],
    }


def _plot_summary(rows, out):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    groups = sorted({row["group"] for row in rows})
    for metric, label in (("max_violation", "max violation"), ("sum_violation", "sum violation")):
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for group in groups:
            values = [row for row in rows if row["group"] == group and int(row["budget"]) == 16000]
            ax.plot([int(row["seed"]) for row in values], [row[metric] for row in values], marker="o", label=group)
        ax.set_xlabel("paired seed")
        ax.set_ylabel(label)
        ax.legend(fontsize=7)
        ax.grid(True, alpha=.25)
        path = out / f"{metric}_by_group_seed.png"
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)
    baseline = {
        (int(row["seed"]), int(row["budget"])): float(row["elapsed_s"])
        for row in rows if row["group"] == BASELINE_GROUP
    }
    runtime_rows = [row for row in rows if row["group"] != BASELINE_GROUP]
    if runtime_rows:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for group in sorted({row["group"] for row in runtime_rows}):
            values = [row for row in runtime_rows if row["group"] == group]
            ratios = [row["elapsed_s"] / max(baseline.get((int(row["seed"]), int(row["budget"])), np.nan), np.finfo(float).tiny) for row in values]
            ax.plot([row["release_dimension"] for row in values], ratios, marker="o", linestyle="", label=group)
        ax.set_xlabel("release-space dimension")
        ax.set_ylabel("runtime ratio to G0")
        ax.grid(True, alpha=.25)
        ax.legend(fontsize=7)
        path = out / "runtime_ratio_by_dimension.png"
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for group in sorted({row["group"] for row in runtime_rows}):
            values = [row for row in runtime_rows if row["group"] == group]
            ax.plot([int(row["budget"]) for row in values], [row["max_violation"] for row in values], marker="o", label=group)
        ax.set_xlabel("unique evaluations")
        ax.set_ylabel("best validated max violation")
        ax.grid(True, alpha=.25)
        ax.legend(fontsize=7)
        path = out / "best_so_far_trajectory.png"
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)
    return paths


def run_stage36_gate2a(config_path: str | Path, run: str | Path, *, resume=False):
    config_path = Path(config_path).resolve()
    base = normalize_convergence_config(load_experiment_config(config_path))
    section = _stage_section(base)
    s1, s1_path = _load_s1(base)
    run = initialize(Path(run).resolve(), base)
    save(run / "stage3_6_gate2a_manifest.json", {
        "study_type": STUDY_TYPE,
        "config_path": str(config_path),
        "config_sha256": _sha256(config_path),
        "s1_path": str(s1_path),
        "s1_sha256": _sha256(s1_path),
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                    capture_output=True, text=True, check=True).stdout.strip(),
        "seeds": section["seeds"],
        "screening_budget": section["screening_budget"],
        "promotion_budget": section["promotion_budget"],
        "groups": list(INDIVIDUAL_GROUPS),
        "interactions": list(INTERACTION_GROUPS),
        "optimizer": "L-SHADE",
        "termination": {"source_ohm": ZPORT, "load_ohm": ZPORT},
        "objective_unchanged": True,
        "validation_protocol_unchanged": True,
    })
    (run / "input_config.yaml").write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
    save(run / "release_group_definitions.json", {
        group: release_schema(group, s1) for group in (BASELINE_GROUP, *INDIVIDUAL_GROUPS, *INTERACTION_GROUPS)
    })
    baseline = _reuse_baseline(run, section, section["seeds"])
    requested = list(INDIVIDUAL_GROUPS)
    for group in requested:
        tasks = [(str(run), base, group, s1, seed, [section["screening_budget"]], bool(resume))
                 for seed in section["seeds"]]
        _run_workers(tasks, section["workers"], int(base.get("stage3_3", {}).get("production_parallel", {}).get("blas_threads_per_worker", 1)))
    record_map = _all_records(run, baseline, requested)
    grid = _common_grid(base, record_map)
    grid_id = hashlib.sha256(np.asarray(grid, dtype="<f8").tobytes()).hexdigest()
    rows = [_validate_record(base, group, record, grid)
            for group, records in record_map.items() for record in records]
    _write_csv(run / "screening_checkpoint_data.csv", rows)
    decision = _promotion_decision(rows, section)
    save(run / "promotion_decision.json", decision)
    promoted = list(decision["promoted_groups"])
    for group in promoted:
        tasks = [(str(run), base, group, s1, seed,
                  [section["screening_budget"], section["promotion_budget"]], True)
                 for seed in section["seeds"]]
        _run_workers(tasks, section["workers"], int(base.get("stage3_3", {}).get("production_parallel", {}).get("blas_threads_per_worker", 1)))
    # Interaction runs are explicitly selected from individual evidence.  The
    # first implementation records the selection and only runs interactions
    # when at least two individual groups are promoted, preventing combination
    # explosion while preserving a deterministic policy.
    interaction_candidates = []
    if len(promoted) >= 2:
        if "G1_CENTER_PITCH" in promoted and "G2_REFLECTOR_PITCH" in promoted:
            interaction_candidates.append("G1_G2")
        if "G1_CENTER_PITCH" in promoted and "G3_CENTER_APERTURE" in promoted:
            interaction_candidates.append("G1_G3")
        if len(promoted) == 3:
            interaction_candidates.append("G1_G2_G3")
    save(run / "interaction_selection.json", {
        "candidates": interaction_candidates,
        "rule": "only combinations of promoted individual groups; max three",
    })
    for group in interaction_candidates:
        tasks = [(str(run), base, group, s1, seed, [section["screening_budget"]], False)
                 for seed in section["seeds"]]
        _run_workers(tasks, section["workers"], int(base.get("stage3_3", {}).get("production_parallel", {}).get("blas_threads_per_worker", 1)))
    final_groups = [BASELINE_GROUP, *INDIVIDUAL_GROUPS, *promoted, *interaction_candidates]
    final_groups = list(dict.fromkeys(final_groups))
    record_map = _all_records(run, baseline, [group for group in final_groups if group != BASELINE_GROUP])
    grid = _common_grid(base, record_map)
    grid_id = hashlib.sha256(np.asarray(grid, dtype="<f8").tobytes()).hexdigest()
    rows = [_validate_record(base, group, record, grid)
            for group, records in record_map.items() for record in records]
    _write_csv(run / "results" / "all_seed_results.csv", rows)
    _write_csv(run / "results" / "validation_metrics.csv", rows)
    baseline_runtime = {
        (int(row["seed"]), int(row["budget"])): float(row["elapsed_s"])
        for row in rows if row["group"] == BASELINE_GROUP
    }
    _write_csv(run / "results" / "runtime_comparison.csv", [
        {"group": row["group"], "seed": row["seed"], "budget": row["budget"],
         "elapsed_s": row["elapsed_s"], "dimension": row["release_dimension"],
         "runtime_ratio_to_g0": (
             None if row["group"] == BASELINE_GROUP else row["elapsed_s"] / max(
                 baseline_runtime.get((int(row["seed"]), int(row["budget"])), np.nan),
                 np.finfo(float).tiny,
             )
         )}
        for row in rows
    ])
    _write_csv(run / "results" / "optimized_parameters.csv", [
        {"group": row["group"], "seed": row["seed"], "budget": row["budget"],
         "max_violation": row["max_violation"], **json.loads(row["design"])}
        for row in rows
    ])
    utilization = []
    for row in rows:
        if row["group"] == BASELINE_GROUP:
            continue
        utilization.append({"group": row["group"], "seed": row["seed"],
                            "budget": row["budget"],
                            "utilization": json.dumps(_released_utilization(row["group"], row), sort_keys=True)})
    _write_csv(run / "results" / "released_dof_utilization.csv", utilization)
    raw_map = _all_records(run, baseline, [group for group in final_groups if group != BASELINE_GROUP])
    _write_csv(run / "results" / "boundary_occupancy.csv", [
        {"group": group, "seed": record["seed"],
         "budget": record.get("requested_unique_design_budget", record.get("current_budget", 0)),
         "boundary_repair_counts": json.dumps(record.get("boundary_repair_counts", {}), sort_keys=True),
         "hard_bound_reached_by_variable": json.dumps(record.get("hard_bound_reached_by_variable", {}), sort_keys=True)}
        for group, records in raw_map.items() for record in records
    ])
    _write_csv(run / "results" / "paired_comparison.csv", decision["individual"])
    np.savetxt(run / "results" / "common_validation_grid_hz.csv", grid, header="frequency_hz", comments="")
    trajectory_rows = []
    for group, records in raw_map.items():
        for record in records:
            for item in record.get("best_so_far_trace", []):
                trajectory_rows.append({
                    "group": group, "seed": record["seed"],
                    "checkpoint_budget": record.get("requested_unique_design_budget", 0),
                    "unique_evaluation": item.get("unique_evaluation"),
                    "primary_metric": item.get("primary_metric"),
                    "max_violation": item.get("max_violation"),
                    "sum_violation": item.get("sum_violation"),
                })
    _write_csv(run / "trajectories" / "best_so_far.csv", trajectory_rows)
    save(run / "trajectories" / "best_so_far.json", trajectory_rows)
    plot_paths = _plot_summary(rows, run / "plots")
    save(run / "results" / "common_validation_grid.json", {
        "grid_id": grid_id, "frequency_count": int(len(grid)),
        "grid_source": "Gate 2A aggregate validation grid",
    })
    save(run / "results" / "optimizer_trajectories.json", {
        group: [
            {"seed": row["seed"], "budget": row["budget"],
             "max_violation": row["max_violation"], "objective": row["objective"]}
            for row in rows if row["group"] == group
        ] for group in final_groups
    })
    summary = {
        "study_type": STUDY_TYPE,
        "phase": "C1_C2_complete",
        "decision": "GATE2A_READY",
        "zsource_ohm": ZPORT,
        "zload_ohm": ZPORT,
        "common_validation_grid_id": grid_id,
        "common_validation_frequency_count": int(len(grid)),
        "groups_screened": list(INDIVIDUAL_GROUPS),
        "promoted_groups": promoted,
        "interaction_candidates": interaction_candidates,
        "promotion_decision": decision,
        "reused_reduced_baseline": True,
        "stage4_started": False,
        "asymmetric_terminations_started": False,
        "idt_group_release_64k_rerun": False,
        "review_bundle": None,
        "plot_paths": [str(path.relative_to(run)) for path in plot_paths],
    }
    save(run / "stage3_6_gate2a_summary.json", summary)
    bundle = build_review_bundle(run, base, s1, summary, rows, grid)
    summary["review_bundle"] = str(bundle)
    save(run / "stage3_6_gate2a_summary.json", summary)
    (run / "STAGE3_6_GATE2A_COMPLETE_STOP.txt").write_text(
        f"Review bundle: {bundle}\nNo asymmetric termination or Stage 4 work was started.\n",
        encoding="utf-8",
    )
    return summary


def _write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_review_bundle(run, cfg, s1, summary, rows, grid):
    bundle_root = ROOT / "artifacts" / "review_bundles"
    bundle_root.mkdir(parents=True, exist_ok=True)
    staging = run / "_gate2a_bundle"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    _write_text(staging / "README.md", "# Stage 3.6 Gate 2A DOF release review bundle\n\nThis bundle stops after 50/50 DOF-release screening. No 50/25, 50/100, Phase D, or Stage 4 work was started.\n")
    _write_text(staging / "stage3_6_gate2a_summary.md", _summary_markdown(summary, rows))
    _write_text(staging / "dof_inventory.md", _inventory_markdown(s1))
    _write_csv(staging / "dof_inventory.csv", _inventory_rows(s1))
    _write_text(staging / "constraint_reasoning.md", _constraint_reasoning())
    save(staging / "current_reduced_search_space.json", {
        "schema_version": 1, "source": "artifacts/stage3_5/phase_a_revised/search_space_s1.yaml",
        "variables": [
            {"name": name, "type": "integer" if name in {"io_idt_pairs", "center_idt_pairs", "reflector_electrodes"} else "continuous",
             "initial": s1["bounds"][name]["initial"], "hard": s1["bounds"][name]["hard"],
             "transform": "round_nearest" if name in {"io_idt_pairs", "center_idt_pairs", "reflector_electrodes"} else "identity",
             "sharing": "global"}
            for name in NAMES
        ],
        "constraint_relations": ["outer_left_io_pairs == outer_right_io_pairs", "all_section_wavelengths == wavelength_um", "all_section_apertures == aperture_um"],
    })
    save(staging / "release_group_definitions.json", {group: release_schema(group, s1) for group in (BASELINE_GROUP, *INDIVIDUAL_GROUPS, *INTERACTION_GROUPS)})
    for relative in ("results", "plots", "groups"):
        source = run / relative
        if source.exists():
            shutil.copytree(source, staging / relative, dirs_exist_ok=True)
    for source_name in ("screening_checkpoint_data.csv", "promotion_decision.json", "interaction_selection.json", "reused_baseline_manifest.json", "stage3_6_gate2a_manifest.json"):
        source = run / source_name
        if source.exists():
            shutil.copy2(source, staging / source_name)
    _write_text(staging / "source_diffs" / "README.md", "The release implementation is isolated to `src/sawopt/studies/stage3_6_gate2a.py`; legacy `NAMES`/`BOUNDS` and L-SHADE were not changed for this study.\n")
    _write_text(staging / "tests" / "README.md", "See the targeted Gate 2A unit/regression tests in `tests/unit/studies/test_stage3_6_gate2a.py`.\n")
    _write_text(staging / "logs" / "README.md", "Run metadata, per-seed trajectories, and checkpoint records are under `groups/`.\n")
    output = bundle_root / "stage3_6_gate2a_dof_release_50ohm_review.zip"
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for source in sorted(path for path in staging.rglob("*") if path.is_file()):
            archive.write(source, source.relative_to(staging).as_posix())
    return output


def _inventory_rows(s1):
    integer = {"io_idt_pairs", "center_idt_pairs", "reflector_electrodes"}
    rows = []
    for name in NAMES:
        rows.append({
            "dof": name,
            "current_value_range": json.dumps(s1["bounds"][name]["initial"]),
            "type": "integer" if name in integer else "continuous",
            "free_fixed": "free",
            "shared_scope": "global",
            "left_right_independent": "no",
            "section_independent": "no",
            "physical_reason": "legacy mirrored/global parameterization",
            "implementation_reason": "current FilterDesign/NAMES schema",
            "constraint_reason_class": "C/E",
        })
    rows.extend([
        {"dof": "center_wavelength_um", "current_value_range": "derived from wavelength_um", "type": "derived", "free_fixed": "fixed/shared", "shared_scope": "all sections", "left_right_independent": "not applicable", "section_independent": "no", "physical_reason": "not physically required to equal outer pitch", "implementation_reason": "current model exposes one wavelength", "constraint_reason_class": "E"},
        {"dof": "reflector_wavelength_um", "current_value_range": "derived from wavelength_um", "type": "derived", "free_fixed": "fixed/shared", "shared_scope": "all sections", "left_right_independent": "mirrored reflectors only", "section_independent": "no", "physical_reason": "reflector pitch may be independently detuned", "implementation_reason": "current model exposes one wavelength", "constraint_reason_class": "E"},
        {"dof": "center_aperture_um", "current_value_range": "derived from aperture_um", "type": "derived", "free_fixed": "fixed/shared", "shared_scope": "all sections", "left_right_independent": "not applicable", "section_independent": "no", "physical_reason": "center transduction area can be independently tuned", "implementation_reason": "current model exposes one aperture", "constraint_reason_class": "E"},
        {"dof": "metallization_ratio", "current_value_range": "0.5", "type": "continuous", "free_fixed": "fixed", "shared_scope": "global", "left_right_independent": "no", "section_independent": "no", "physical_reason": "placeholder provider does not model dependence", "implementation_reason": "field not in NAMES", "constraint_reason_class": "F"},
        {"dof": "thickness_over_lambda", "current_value_range": "0.04", "type": "continuous", "free_fixed": "fixed", "shared_scope": "global", "left_right_independent": "no", "section_independent": "no", "physical_reason": "placeholder provider does not model dependence", "implementation_reason": "field not in NAMES", "constraint_reason_class": "F"},
    ])
    return rows


def _inventory_markdown(s1):
    rows = _inventory_rows(s1)
    lines = ["# C1 DOF inventory", "", "The current Reduced S1 is a seven-dimensional global parameterization. The three release candidates below are experiment-owned section-class overrides; left/right asymmetry is not represented.", "", "| DOF | Current range | Type | Free/fixed | Shared scope | L/R independent | Section independent | Physical reason | Implementation reason | Class |", "|---|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row[key]) for key in ("dof", "current_value_range", "type", "free_fixed", "shared_scope", "left_right_independent", "section_independent", "physical_reason", "implementation_reason", "constraint_reason_class")) + " |")
    return "\n".join(lines) + "\n"


def _constraint_reasoning():
    return """# Constraint reasoning

- A: The mirrored outer sections are retained because the current DMS topology and 50/50 screening protocol are symmetric.
- B: No manufacturing necessity was introduced in this phase.
- C: The frozen S1 ranges and existing global geometry are inherited from prior stages.
- D: No new D-class constraint was added.
- E: Global wavelength/aperture sharing is an implementation limitation of the current seven-variable `FilterDesign` contract; C2 tests only three small section-class releases.
- F: `metallization_ratio` and `thickness_over_lambda` are fixed fields whose placeholder provider has no electrical dependence. They are deferred rather than released as artificial dimensions.

Left/right independent variables, COM coefficient releases, and material-dependent releases are deferred because they need separate physics/model judgment and would not be valid evidence under the current placeholder model.
"""


def _summary_markdown(summary, rows):
    lines = [
        "# Stage 3.6 Gate 2A — DOF release screening at 50/50 ohm", "",
        f"- Decision: `{summary['decision']}`", f"- Validation grid: `{summary['common_validation_grid_id']}` ({summary['common_validation_frequency_count']} points)",
        f"- Groups screened: `{', '.join(summary['groups_screened'])}`", f"- Promoted: `{', '.join(summary['promoted_groups']) or 'none'}`", f"- Interactions: `{', '.join(summary['interaction_candidates']) or 'none'}`", "",
        "## Scope guard", "",
        "This bundle stops after C1/C2. No 50/25, 50/100, asymmetric termination, Phase D, Stage 4, topology exploration, or IDT_GROUP_RELEASE 64k rerun was started.", "",
        "## 50/50 results", "", "| group | seed | budget | max violation | sum violation | worst IL dB | ripple dB | feasible | runtime s |", "|---|---:|---:|---:|---:|---:|---:|---|---:|"]
    for row in rows:
        lines.append(f"| {row['group']} | {row['seed']} | {row['budget']} | {row['max_violation']:.9g} | {row['sum_violation']:.9g} | {row['worst_il_db']:.9g} | {row['ripple_db']:.9g} | {row['feasible']} | {row['elapsed_s']:.3f} |")
    lines += ["", "## Interpretation", "", "The current surrogate uses placeholder region-type COM parameters. Any section pitch/aperture gain is evidence about this numerical model and must not be treated as calibrated fabrication evidence. Center-aperture release also omits transverse diffraction/mode mismatch.", "", "## Gate 2A questions", "", "1. The current Reduced S1 inventory is seven global variables; three additional section-class DOFs were tested.", "2. Non-physical shared/fixed constraints are the global wavelength/aperture implementation limits and the unused fixed material fields.", "3. The selected releases are G1 center pitch, G2 mirrored reflector pitch, and G3 center aperture.", "4. Improvement and utilization are recorded per paired seed in `results/`.", "5. The max-violation wall is assessed against the reused G0 baseline on one common validation grid.", "6. Interactions are selected only after individual evidence and are capped at three combinations.", "7. Released DOF values and normalized deltas are in `released_dof_utilization.csv`.", "8. Unused groups are documented in `constraint_reasoning.md`.", "9. Runtime and dimension counts are in `runtime_comparison.csv`.", "10. Stage 4 candidate space is the best promoted individual/interaction group, subject to review.", "11. Asymmetric candidate spaces are not selected by this symmetric 50/50 gate.", "12. 32k promotion is limited to the deterministic paired rule in `promotion_decision.json`.", "13. Deferred fixed/shared DOFs are listed in the inventory.", "14. Placeholder-physics limitations are recorded above.", ""]
    return "\n".join(lines)


# Public adapters for the final-confirmation study.  They preserve the
# existing implementation while keeping cross-study imports within the
# architecture's public-interface contract.
def release_worker(payload):
    return _release_worker(payload)


def run_release_workers(tasks, workers, threads=1):
    return _run_workers(tasks, workers, threads)


def load_frozen_s1(cfg):
    return _load_s1(cfg)


def reuse_gate2a_baseline(run, section, seeds):
    return _reuse_baseline(run, section, seeds)


def gate2a_group_records(run, group):
    return _group_records(run, group)


def common_validation_grid(cfg, record_map):
    return _common_grid(cfg, record_map)


def validate_gate2a_record(cfg, group, record, grid):
    return _validate_record(cfg, group, record, grid)


def write_gate2a_csv(path, rows):
    return _write_csv(path, rows)


def main():
    parser = argparse.ArgumentParser(description="Stage 3.6 Phase C1-C2 Gate 2A DOF release screening")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_stage36_gate2a(args.config, args.run, resume=args.resume), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
