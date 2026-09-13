"""Offline search-space diagnostics for the Stage 3.5 efficiency study.

The module intentionally consumes a completed Stage 3.4b review bundle and
does not run an optimizer.  It produces a deterministic late-elite summary,
fixed-design local sensitivity measurements, and a fail-safe initial-box
proposal.  Hard physical bounds are copied through unchanged; the proposal is
only an initial active box for a continuation run.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zipfile import ZipFile

import numpy as np
import yaml

from ..core.metrics import geometry
from ..core.models import BOUNDS, FilterDesign, NAMES
from ..optimizers.selection import DEFAULT_COMPARATOR, rank
from ..problem.evaluator import dense
from ..io.config import load_experiment_config
from ..studies.convergence import normalize_convergence_config


INTEGER_NAMES = frozenset(NAMES[1:4])
LATE_BUDGETS = (128_000, 192_000, 256_000)
DEFAULT_ELITE_FRACTION = 0.5
MIN_ELITE_EVIDENCE = 4


def _json(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return [_json(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json(value.item())
    if isinstance(value, Mapping):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _read_zip_text(archive: ZipFile, name: str) -> str:
    try:
        return archive.read(name).decode("utf-8")
    except KeyError as exc:
        raise FileNotFoundError(f"Stage 3.4b bundle is missing {name}") from exc


def _read_zip_json(archive: ZipFile, name: str) -> dict[str, Any]:
    return json.loads(_read_zip_text(archive, name))


def load_stage34b_artifact(bundle: str | Path) -> dict[str, Any]:
    """Load the exact Stage 3.4b bundle without extracting or modifying it."""
    bundle = Path(bundle).resolve()
    with ZipFile(bundle) as archive:
        manifest = _read_zip_json(archive, "bundle_manifest.json")
        run_manifest = _read_zip_json(archive, "environment/run_manifest.json")
        summary = _read_zip_json(archive, "results/convergence_summary.json")
        design_space = _read_zip_json(archive, "results/design_space_versions.json")
        budget_rows = list(csv.DictReader(
            _read_zip_text(archive, "results/budget_summary.csv").splitlines()
        ))
        boundary_rows = list(csv.DictReader(
            _read_zip_text(archive, "results/boundary_events.csv").splitlines()
        ))
        stagnation_rows = list(csv.DictReader(
            _read_zip_text(archive, "results/stagnation_events.csv").splitlines()
        ))
        trial_names = [
            name for name in archive.namelist()
            if name.startswith("trials/") and name.endswith(".json")
        ]
        trials = []
        for name in sorted(trial_names):
            record = _read_zip_json(archive, name)
            record["_artifact_path"] = name
            trials.append(record)
    return {
        "path": str(bundle),
        "sha256": _sha256(bundle),
        "manifest": manifest,
        "run_manifest": run_manifest,
        "summary": summary,
        "design_space_versions": design_space,
        "budget_rows": budget_rows,
        "boundary_rows": boundary_rows,
        "stagnation_rows": stagnation_rows,
        "trials": trials,
    }


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validation_record(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the historical dense-validation record when one is present.

    Stage 3.4b exports contain two different rank tuples: the top-level tuple
    describes the search/checkpoint record, while ``validation_record`` is the
    dense validation truth.  The latter is the only source allowed for
    quality, parity, elite, and sensitivity decisions.
    """
    nested = record.get("validation_record")
    return nested if isinstance(nested, Mapping) else record


def _search_key(record: Mapping[str, Any]) -> tuple[float, ...]:
    value = record.get("validated_rank_tuple")
    if value is not None:
        return tuple(float(item) for item in value)
    return tuple(float(item) for item in rank(record))


def _validated_key(record: Mapping[str, Any]) -> tuple[float, ...]:
    """Return the rank used for validation truth, never search provenance."""
    return tuple(float(item) for item in rank(_validation_record(record)))


def _record_budget(record: Mapping[str, Any]) -> int:
    return int(record.get(
        "requested_unique_design_budget",
        record.get("unique_decoded_evaluations", 0),
    ))


def final_seed_records(trials: Iterable[Mapping[str, Any]], *, min_budget: int = 128_000):
    """Return one latest record per seed for the requested wiring."""
    candidates = [
        record for record in trials
        if record.get("wiring") == "center_outer_same"
        and _record_budget(record) >= int(min_budget)
    ]
    by_seed: dict[int, Mapping[str, Any]] = {}
    for record in candidates:
        seed = int(record["seed"])
        previous = by_seed.get(seed)
        if previous is None or _record_budget(record) > _record_budget(previous):
            by_seed[seed] = record
    return [by_seed[key] for key in sorted(by_seed)]


def late_seed_records(trials: Iterable[Mapping[str, Any]], *,
                      budgets: Sequence[int] = LATE_BUDGETS) -> list[Mapping[str, Any]]:
    """Return at most one record per (seed, requested late checkpoint)."""
    wanted = {int(value) for value in budgets}
    selected: dict[tuple[int, int], Mapping[str, Any]] = {}
    for record in trials:
        if record.get("wiring") != "center_outer_same":
            continue
        budget = _record_budget(record)
        if budget not in wanted:
            continue
        key = (int(record["seed"]), budget)
        # Deterministic in case a review bundle contains duplicate exports.
        previous = selected.get(key)
        if previous is None or str(record.get("_artifact_path", "")) < str(previous.get("_artifact_path", "")):
            selected[key] = record
    return [selected[key] for key in sorted(selected)]


def elite_records(records: Sequence[Mapping[str, Any]], *, fraction: float = DEFAULT_ELITE_FRACTION,
                  minimum: int = MIN_ELITE_EVIDENCE):
    """Select a deterministic late elite envelope without fitting a surrogate."""
    ordered = sorted(records, key=lambda record: (_validated_key(record), int(record["seed"])))
    if not ordered:
        return []
    count = max(int(minimum), int(math.ceil(len(ordered) * float(fraction))))
    return ordered[:min(count, len(ordered))]


def _configured_bounds(cfg: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    configured = cfg.get("optimizer_validation", {}).get("bounds", {})
    result: dict[str, dict[str, Any]] = {}
    for index, name in enumerate(NAMES):
        hard = [float(value) for value in BOUNDS[index]]
        initial = list(hard)
        item = configured.get(name, {})
        if item.get("hard") is not None:
            hard = [float(value) for value in item["hard"]]
        if item.get("initial") is not None:
            initial = [float(value) for value in item["initial"]]
        result[name] = {
            "hard": hard,
            "initial": initial,
            "expandable": bool(item.get("expandable", False)),
            "lower_steps": [int(value) for value in item.get("lower_steps", [])],
            "upper_steps": [int(value) for value in item.get("upper_steps", [])],
        }
    return result


def _boundary_sides(rows: Sequence[Mapping[str, Any]], name: str) -> set[str]:
    return {
        str(row.get("direction")) for row in rows
        if row.get("variable") == name
        and str(row.get("event", "")).lower() in {
            "boundary_pressure", "hard_bound_limited", "boundary_probe",
        }
    }


def _rank_values(values: Sequence[float]) -> np.ndarray:
    order = np.argsort(np.asarray(values, dtype=float), kind="mergesort")
    ranks = np.empty(len(order), dtype=float)
    ranks[order] = np.arange(len(order), dtype=float)
    return ranks


def pairwise_diagnostics(records: Sequence[Mapping[str, Any]], *, maximum: int = 3):
    """Return at most three diagnostic pairs; no two-dimensional sweep occurs."""
    designs = [_validation_record(record).get("design", {}) for record in records]
    rows = []
    for left_index, left in enumerate(NAMES):
        for right in NAMES[left_index + 1:]:
            x = [float(design[left]) for design in designs if left in design and right in design]
            y = [float(design[right]) for design in designs if left in design and right in design]
            if len(x) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
                correlation = 0.0
            else:
                correlation = float(np.corrcoef(_rank_values(x), _rank_values(y))[0, 1])
            rows.append({
                "variable_a": left,
                "variable_b": right,
                "sample_count": len(x),
                "spearman_rank_correlation": correlation,
                "absolute_correlation": abs(correlation),
                "selected": False,
                "selection_reason": "",
            })
    rows.sort(key=lambda row: (-row["absolute_correlation"], row["variable_a"], row["variable_b"]))
    selected = 0
    for row in rows:
        if selected >= int(maximum):
            break
        if row["sample_count"] >= 3 and row["absolute_correlation"] >= 0.5:
            row["selected"] = True
            row["selection_reason"] = "elite_rank_correlation"
            selected += 1
    return rows[:max(int(maximum), selected)]


def cross_version_parity(records: Sequence[Mapping[str, Any]], cfg: Mapping[str, Any], *,
                         wiring: str = "center_outer_same", rtol: float = 1e-9,
                         atol: float = 1e-10) -> list[dict[str, Any]]:
    """Re-evaluate historical final designs on their exact saved validation grids.

    This is a refactor-safety gate, not an optimizer experiment.  Missing saved
    validation frequencies fail closed because a different grid would not be a
    like-for-like numerical parity test.
    """
    impedance = float(cfg.get("convergence", {}).get("impedance_ohm", 50.0))
    rows: list[dict[str, Any]] = []
    for record in records:
        validation_record = record.get("validation_record")
        row = {
            "seed": int(record.get("seed", 0)),
            "budget": _record_budget(record),
            "historical_search_rank": list(_search_key(record)),
            "historical_validation_rank": None,
            "current_validation_rank": None,
            "max_abs_validation_rank_diff": None,
            "validation_parity_pass": False,
            "error": "",
        }
        if not isinstance(validation_record, Mapping):
            row["error"] = "missing_validation_record"
            rows.append(row)
            continue
        try:
            frequencies = validation_record.get("validation_frequencies_hz")
            if not frequencies:
                row["error"] = "missing_validation_record.validation_frequencies_hz"
                rows.append(row)
                continue
            design = FilterDesign(**dict(validation_record["design"]))
            _f, (evaluated, _net, _sim) = dense(
                design, cfg, impedance, impedance, wiring=wiring,
                base_grid=np.asarray(frequencies, dtype=float), passes=0, validation=True,
            )
            current = tuple(float(value) for value in rank(evaluated))
            saved = tuple(float(value) for value in rank(validation_record))
            diff = np.abs(np.asarray(current, dtype=float) - np.asarray(saved, dtype=float))
            row["historical_validation_rank"] = list(saved)
            row["current_validation_rank"] = list(current)
            row["max_abs_validation_rank_diff"] = float(np.max(diff)) if len(diff) else 0.0
            row["validation_parity_pass"] = bool(np.allclose(current, saved, rtol=rtol, atol=atol))
        except (KeyError, TypeError, ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
    return rows


def _metric_snapshot(record: Mapping[str, Any]) -> dict[str, Any]:
    validation_record = _validation_record(record)
    metrics = validation_record.get("metrics", {})
    return {
        "feasible": bool(validation_record.get("feasible", False)),
        "max_violation": float(validation_record.get("max_violation", np.inf)),
        "sum_violation": float(validation_record.get(
            "sum_violation", sum(float(value) for value in validation_record.get("violations", {}).values())
        )),
        "worst_passband_il_db": float(metrics.get("worst_il_db", np.inf)),
        "validated_rank_tuple": list(_validated_key(record)),
        "per_spec_normalized_violations": {
            str(key): float(value) for key, value in validation_record.get("violations", {}).items()
        },
    }


def run_local_sensitivity(records: Sequence[Mapping[str, Any]], cfg: Mapping[str, Any], *,
                          wiring: str = "center_outer_same") -> list[dict[str, Any]]:
    """Evaluate fixed-design perturbations using the common dense validator."""
    bounds = _configured_bounds(cfg)
    results: list[dict[str, Any]] = []
    impedance = float(cfg.get("convergence", {}).get("impedance_ohm", 50.0))
    scales = (0.01, 0.025, 0.05)
    for base in records:
        validation_record = _validation_record(base)
        design_values = dict(validation_record.get("design", {}))
        validation_grid = validation_record.get("validation_frequencies_hz")
        seed = int(base.get("seed", 0))
        base_snapshot = _metric_snapshot(base)
        for name in NAMES:
            lo, hi = bounds[name]["hard"]
            value = float(design_values[name])
            if name in INTEGER_NAMES:
                perturbations = [("lower", value - 1.0, 1.0), ("upper", value + 1.0, 1.0),
                                  ("lower", value - 2.0, 2.0), ("upper", value + 2.0, 2.0)]
            else:
                span = hi - lo
                perturbations = [
                    (direction, value + sign * fraction * span, fraction)
                    for fraction in scales
                    for direction, sign in (("lower", -1.0), ("upper", 1.0))
                ]
            for direction, proposed, magnitude in perturbations:
                row = {
                    "seed": seed,
                    "variable": name,
                    "direction": direction,
                    "perturbation": magnitude,
                    "base_value": value,
                    "perturbed_value": proposed,
                    "within_hard_bounds": bool(lo <= proposed <= hi),
                    "valid_geometry": False,
                    "error": "",
                    "improves_validated_rank": False,
                    "outside_improvement_suggested": False,
                    **{f"base_{key}": value for key, value in base_snapshot.items()},
                }
                if name in INTEGER_NAMES:
                    proposed = float(round(proposed))
                    row["perturbed_value"] = proposed
                if not row["within_hard_bounds"]:
                    # An unevaluated point beyond the hard bound is not evidence
                    # of outward improvement.  Keep it as an explicit diagnostic
                    # rather than blocking S1 with a false positive.
                    row["error"] = "outside_hard_bounds_not_evaluated"
                    results.append(row)
                    continue
                candidate = dict(design_values)
                candidate[name] = int(proposed) if name in INTEGER_NAMES else float(proposed)
                d = FilterDesign(**candidate)
                _dims, violations = geometry(d, cfg["constraints"])
                row["valid_geometry"] = not bool(max(violations, default=0.0) > 1e-10)
                if not row["valid_geometry"]:
                    row["error"] = "geometry_invalid"
                    results.append(row)
                    continue
                try:
                    _frequencies, (evaluated, _net, _sim) = dense(
                        d, cfg, impedance, impedance, wiring=wiring, counters=None,
                        base_grid=np.asarray(validation_grid, dtype=float), passes=0, validation=True,
                    )
                    evaluated = dict(evaluated)
                    evaluated["design"] = dict(candidate)
                    evaluated["validated_rank_tuple"] = list(rank(evaluated))
                    row.update({
                        "feasible": bool(evaluated.get("feasible", False)),
                        "max_violation": float(evaluated.get("max_violation", np.inf)),
                        "sum_violation": float(evaluated.get(
                            "sum_violation",
                            sum(float(value) for value in evaluated.get("violations", {}).values()),
                        )),
                        "worst_passband_il_db": float(evaluated.get("metrics", {}).get("worst_il_db", np.inf)),
                        "validated_rank_tuple": list(evaluated["validated_rank_tuple"]),
                        "per_spec_normalized_violations": json.dumps(
                            _json(evaluated.get("violations", {})), sort_keys=True,
                        ),
                    })
                    row["improves_validated_rank"] = tuple(evaluated["validated_rank_tuple"]) < tuple(base_snapshot["validated_rank_tuple"])
                    row["outside_improvement_suggested"] = bool(row["improves_validated_rank"] and (
                        direction == "lower" and value <= lo + 2 or direction == "upper" and value >= hi - 2
                    ))
                except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                    row["error"] = f"{type(exc).__name__}: {exc}"
                results.append(row)
    return results


def _sensitivity_summary(rows: Sequence[Mapping[str, Any]], name: str) -> dict[str, Any]:
    selected = [row for row in rows if row.get("variable") == name]
    return {
        "evaluated_count": len(selected),
        "valid_count": sum(bool(row.get("valid_geometry")) and not row.get("error") for row in selected),
        "outside_improvement_suggested": any(bool(row.get("outside_improvement_suggested")) for row in selected),
        "improvement_count": sum(bool(row.get("improves_validated_rank")) for row in selected),
    }


def propose_s1(artifact: Mapping[str, Any], cfg: Mapping[str, Any], sensitivity: Sequence[Mapping[str, Any]], *,
               elite_fraction: float = DEFAULT_ELITE_FRACTION) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build S1 by mechanical guards; fail-safe means retain S0 bounds."""
    baseline = _configured_bounds(cfg)
    finals = final_seed_records(artifact["trials"])
    late = late_seed_records(artifact["trials"])
    elites = elite_records(late, fraction=elite_fraction)
    rows = []
    s1: dict[str, dict[str, Any]] = {}
    boundary_rows = artifact.get("boundary_rows", [])
    for name in NAMES:
        hard_lo, hard_hi = baseline[name]["hard"]
        initial_lo, initial_hi = baseline[name]["initial"]
        values = [float(_validation_record(record)["design"][name]) for record in elites]
        hard_span = hard_hi - hard_lo
        evidence = len(values) >= MIN_ELITE_EVIDENCE
        elo = min(values) if values else initial_lo
        ehi = max(values) if values else initial_hi
        iqr = float(np.percentile(values, 75) - np.percentile(values, 25)) if values else 0.0
        guard = max(0.10 * hard_span, 1.5 * iqr,
                    3.0 if name in INTEGER_NAMES else 0.0)
        candidate_lo = max(hard_lo, elo - guard)
        candidate_hi = min(hard_hi, ehi + guard)
        if name in INTEGER_NAMES:
            candidate_lo = float(math.floor(candidate_lo))
            candidate_hi = float(math.ceil(candidate_hi))
        candidate_width = candidate_hi - candidate_lo
        baseline_width = initial_hi - initial_lo
        sides = _boundary_sides(boundary_rows, name)
        sensitivity_summary = _sensitivity_summary(sensitivity, name)
        edge_pressure = bool(
            values and (min((value - hard_lo) / hard_span for value in values) <= 0.05
                        or min((hard_hi - value) / hard_span for value in values) <= 0.05)
        )
        spread_large = bool(values and ((ehi - elo) / hard_span > 0.80 or iqr / hard_span > 0.25))
        multimodal = bool(values and len(values) >= 5 and max(np.diff(sorted(values)), default=0.0) > 0.35 * hard_span)
        reasons = []
        if not evidence:
            reasons.append("insufficient_evidence")
        if edge_pressure:
            reasons.append("elite_near_hard_edge")
        if sides:
            reasons.append("boundary_pressure:" + ",".join(sorted(sides)))
        if sensitivity_summary["outside_improvement_suggested"]:
            reasons.append("local_sensitivity_outward_improvement")
        if multimodal:
            reasons.append("multimodal_elite_distribution")
        if spread_large:
            reasons.append("large_normalized_elite_spread")
        if not baseline[name]["expandable"]:
            reasons.append("no_existing_expansion_support")
        if name == "io_idt_pairs" and candidate_lo > 8:
            reasons.append("io_lower_must_remain_8")
            candidate_lo = 8.0
        narrow = (
            not reasons
            and baseline[name]["expandable"]
            and candidate_width <= 0.70 * hard_span
            and candidate_width < baseline_width
        )
        if not narrow:
            candidate_lo, candidate_hi = initial_lo, initial_hi
            if not reasons and candidate_width > 0.70 * hard_span:
                reasons.append("candidate_not_narrow_enough")
            if not reasons:
                reasons.append("retain_production_initial_bounds")
        if name == "io_idt_pairs":
            candidate_lo = 8.0
        s1[name] = {
            "initial": [int(candidate_lo) if name in INTEGER_NAMES else float(candidate_lo),
                        int(candidate_hi) if name in INTEGER_NAMES else float(candidate_hi)],
            "hard": [int(hard_lo) if name in INTEGER_NAMES else float(hard_lo),
                     int(hard_hi) if name in INTEGER_NAMES else float(hard_hi)],
            "expandable": bool(baseline[name]["expandable"]),
            "lower_steps": list(baseline[name]["lower_steps"]),
            "upper_steps": list(baseline[name]["upper_steps"]),
        }
        if narrow and baseline[name]["expandable"] and candidate_hi < hard_hi and not s1[name]["upper_steps"]:
            # The existing continuation policy already supports an explicit
            # expansion schedule.  Supply a conservative final hard-bound
            # step when the historical config had no upper schedule, so S1
            # never makes the upper side permanent.
            s1[name]["upper_steps"] = [int(hard_hi) if name in INTEGER_NAMES else float(hard_hi)]
        rows.append({
            "variable": name,
            "hard_lower": hard_lo,
            "hard_upper": hard_hi,
            "baseline_initial_lower": initial_lo,
            "baseline_initial_upper": initial_hi,
            "elite_count": len(values),
            "elite_lower": elo,
            "elite_upper": ehi,
            "elite_iqr": iqr,
            "normalized_elite_spread": (ehi - elo) / hard_span if hard_span else 0.0,
            "normalized_distance_to_lower_median": float(np.median([(value - hard_lo) / hard_span for value in values])) if values else None,
            "normalized_distance_to_upper_median": float(np.median([(hard_hi - value) / hard_span for value in values])) if values else None,
            "boundary_sides": ",".join(sorted(sides)),
            "edge_pressure": edge_pressure,
            "multimodal": multimodal,
            "local_sensitivity": json.dumps(sensitivity_summary, sort_keys=True),
            "guard_band": guard,
            "candidate_lower": candidate_lo,
            "candidate_upper": candidate_hi,
            "candidate_width": candidate_width,
            "narrowing_applied": narrow,
            "s1_initial_lower": s1[name]["initial"][0],
            "s1_initial_upper": s1[name]["initial"][1],
            "decision": "narrow" if narrow else "retain_s0",
            "rationale": ";".join(reasons),
        })
    return s1, rows, pairwise_diagnostics(late)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(set().union(*(row.keys() for row in rows))) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def build_diagnostics(artifact: Mapping[str, Any], cfg: Mapping[str, Any], *, config_path: str | Path,
                      elite_fraction: float = DEFAULT_ELITE_FRACTION, sensitivity: bool = True):
    finals = final_seed_records(artifact["trials"])
    if len(finals) != 8:
        raise ValueError(f"Stage 3.4b artifact has {len(finals)} final seed records; required exactly 8")
    parity_rows = cross_version_parity(finals, cfg)
    failed_parity = [row for row in parity_rows if not row.get("validation_parity_pass")]
    if failed_parity:
        raise ValueError(
            "Stage 3.4b -> current-source numerical parity failed for seeds: "
            + ",".join(str(row["seed"]) for row in failed_parity)
        )
    sensitivity_rows = run_local_sensitivity(finals, cfg) if sensitivity else []
    s1, variable_rows, pair_rows = propose_s1(
        artifact, cfg, sensitivity_rows, elite_fraction=elite_fraction,
    )
    summary = artifact["summary"]
    status = summary.get("statuses", {}).get("center_outer_same", {})
    evidence = status.get("evidence", {})
    if status.get("status") != "converged" or evidence.get("budgets", [])[-1:] != [256_000]:
        raise ValueError("Stage 3.4b artifact does not certify convergence at 256k")
    return {
        "artifact": {
            "path": artifact["path"],
            "sha256": artifact["sha256"],
            "bundle_source_hash": artifact["manifest"].get("source_hash"),
            "bundle_git_commit": artifact["manifest"].get("git_commit"),
            "review_scope": artifact["manifest"].get("review_scope"),
        },
        "current_config_path": str(Path(config_path).resolve()),
        "current_config_sha256": _sha256(config_path),
        "wiring": "center_outer_same",
        "impedance_ohm": float(cfg.get("convergence", {}).get("impedance_ohm", 50.0)),
        "cold_seeds": [int(record["seed"]) for record in finals],
        "late_budgets": sorted({_record_budget(record) for record in artifact["trials"] if _record_budget(record) >= 128_000}),
        "final_seed_records": [
            {"seed": int(record["seed"]), "budget": _record_budget(record),
             "design": _json(_validation_record(record).get("design", {})),
             "historical_search_rank": _json(_search_key(record)),
             "historical_validation_rank": _json(_validated_key(record)),
             "metrics": _metric_snapshot(record),
             "artifact_path": record.get("_artifact_path")}
            for record in finals
        ],
        "certificate": {
            "status": status.get("status"),
            "checkpoint": 256_000,
            "grid_converged_seed_fraction": evidence.get("stage34b_gates", {}).get("grid_converged_seed_fraction"),
            "validation_primary_gap": evidence.get("validation_primary_gap"),
            "final_seed_primary_iqr": evidence.get("final_seed_primary_iqr"),
            "worst_minus_median": evidence.get("final_seed_primary_worst_minus_median"),
            "recovery_pending": evidence.get("recovery_pending_confirmation"),
            "boundary_pending": evidence.get("boundary_pending_confirmation"),
            "hard_bound_unresolved": evidence.get("hard_bound_unresolved"),
        },
        "rules": {
            "elite_fraction": elite_fraction,
            "minimum_elite_evidence": MIN_ELITE_EVIDENCE,
            "guard_band": "max(0.10*hard_span, 1.5*elite_IQR, minimum_canonical_margin)",
            "minimum_integer_margin_steps": 3,
            "narrowing_width_ratio_max": 0.70,
            "hard_bounds_changed": False,
            "io_idt_pairs_initial_lower": 8,
        },
        "variables": variable_rows,
        "s1": s1,
        "pairwise": pair_rows,
        "cross_version_parity": parity_rows,
        "cross_version_parity_pass": True,
        "sensitivity_row_count": len(sensitivity_rows),
    }, sensitivity_rows


def _markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Stage 3.5 search-space diagnostics",
        "",
        "This report is offline analysis of the exact Stage 3.4b bundle. No optimizer was run by Phase A.",
        "",
        f"- Artifact: `{summary['artifact']['path']}`",
        f"- Artifact SHA-256: `{summary['artifact']['sha256']}`",
        f"- Bundle source hash: `{summary['artifact']['bundle_source_hash']}`",
        f"- Bundle Git commit: `{summary['artifact']['bundle_git_commit']}`",
        f"- Current config SHA-256: `{summary['current_config_sha256']}`",
        f"- Certificate: `{summary['certificate']['status']}` at `{summary['certificate']['checkpoint']}` unique evaluations/seed",
        f"- Cross-version numerical parity: `{summary.get('cross_version_parity_pass', False)}`",
        "",
        "## S1 decisions",
        "",
        "| variable | hard bounds | S0 initial | late elite range | IQR | S1 initial | decision | rationale |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in summary["variables"]:
        lines.append(
            f"| {row['variable']} | [{row['hard_lower']}, {row['hard_upper']}] | "
            f"[{row['baseline_initial_lower']}, {row['baseline_initial_upper']}] | "
            f"[{row['elite_lower']}, {row['elite_upper']}] | {row['elite_iqr']:.6g} | "
            f"[{row['s1_initial_lower']}, {row['s1_initial_upper']}] | {row['decision']} | {row['rationale'] or '—'} |"
        )
    lines += [
        "",
        "## Safety rules",
        "",
        "- Hard bounds are unchanged and remain the expansion target.",
        "- `io_idt_pairs` initial lower bound is 8.",
        "- Variables are never fixed/eliminated.",
        "- Any boundary pressure, outward local improvement, multimodality, large spread, or insufficient evidence retains S0 initial bounds.",
        "",
        "## Pairwise diagnostics",
        "",
        "Only the top three rank-correlation candidates are listed; no 2-D optimizer sweep was performed.",
        "",
        "| variable A | variable B | samples | Spearman | selected |",
        "|---|---|---:|---:|---|",
    ]
    for row in summary["pairwise"]:
        lines.append(f"| {row['variable_a']} | {row['variable_b']} | {row['sample_count']} | {row['spearman_rank_correlation']:.4f} | {row['selected']} |")
    lines.append("")
    return "\n".join(lines)


def write_outputs(summary: Mapping[str, Any], sensitivity_rows: Sequence[Mapping[str, Any]], out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": out / "search_space_diagnostics.json",
        "md": out / "search_space_diagnostics.md",
        "elites": out / "search_space_elites.csv",
        "sensitivity": out / "local_sensitivity.csv",
        "pairwise": out / "pairwise_diagnostics.csv",
        "parity": out / "cross_version_parity.csv",
        "s1": out / "search_space_s1.yaml",
        "rationale": out / "search_space_s1_rationale.md",
    }
    paths["json"].write_text(json.dumps(_json(summary), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths["md"].write_text(_markdown(summary), encoding="utf-8")
    _write_csv(paths["sensitivity"], list(sensitivity_rows))
    _write_csv(paths["pairwise"], summary["pairwise"])
    _write_csv(paths["parity"], summary.get("cross_version_parity", []))
    _write_csv(paths["elites"], [
        {"seed": item["seed"], "budget": item["budget"], **item["design"],
         "validated_rank_tuple": json.dumps(item["metrics"]["validated_rank_tuple"])}
        for item in summary["final_seed_records"]
    ])
    s1_document = {
        "strategy": "S1_adaptive_initial_box",
        "source_artifact_sha256": summary["artifact"]["sha256"],
        "source_bundle_hash": summary["artifact"]["bundle_source_hash"],
        "source_config_sha256": summary["current_config_sha256"],
        "freeze": True,
        "hard_bounds_unchanged": True,
        "bounds": summary["s1"],
    }
    paths["s1"].write_text(yaml.safe_dump(s1_document, sort_keys=False), encoding="utf-8")
    paths["rationale"].write_text(_markdown(summary), encoding="utf-8")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 3.5 offline search-space diagnostics")
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--no-sensitivity", action="store_true")
    args = parser.parse_args()
    # Use the same historical/default normalization as the canonical study
    # entry points so parity evaluates the real model, including layout data.
    cfg = normalize_convergence_config(load_experiment_config(args.config))
    artifact = load_stage34b_artifact(args.artifact)
    summary, sensitivity_rows = build_diagnostics(
        artifact, cfg, config_path=args.config, sensitivity=not args.no_sensitivity,
    )
    paths = write_outputs(summary, sensitivity_rows, args.out_dir)
    print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
