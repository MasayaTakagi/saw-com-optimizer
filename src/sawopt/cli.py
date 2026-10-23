"""Thin R6 CLI for a strictly synthetic/injected-evaluator vertical slice.

This entry point does not expose COM/FE evaluation, historical study runners,
agent sessions, or repository-local run storage. New user-facing scientific
execution remains separately gated.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io.cli_config import CliConfigError, load_synthetic_config, validate_synthetic_config


class _SyntheticComparator:
    """Toy-only order for the injected synthetic loss; not a SAW comparator."""

    @staticmethod
    def rank_key(record: Mapping[str, Any]) -> tuple[float]:
        return (float(record["metrics"]["synthetic_peak_error"]),)

    def better(self, left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        return self.rank_key(left) < self.rank_key(right)

    def quality(self, record: Mapping[str, Any]) -> float:
        return self.rank_key(record)[0]

    def improvement(self, old: Mapping[str, Any], new: Mapping[str, Any]) -> float:
        improvement = self.quality(old) - self.quality(new)
        return max(improvement, sys.float_info.epsilon) if self.better(new, old) else 0.0

    def primary_metric(self, record: Mapping[str, Any]) -> float:
        return self.quality(record)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _source_sha(repository: Path) -> str:
    """Resolve an immutable source identity only from a clean committed tree."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=repository,
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=repository,
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("cannot establish the committed execution source identity") from exc
    if dirty:
        raise RuntimeError("refusing to create a run from a dirty source tree")
    if len(head) != 40 or any(character not in "0123456789abcdef" for character in head):
        raise RuntimeError("Git returned an invalid full execution source SHA")
    return head


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sawopt",
        description="Synthetic-only R6 software CLI; no COM/FE or production evaluation is available.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate a strict synthetic experiment config without running it")
    validate.add_argument("--config", required=True, help="explicit YAML config path")
    run = commands.add_parser("run", help="run one explicit synthetic software fixture")
    run.add_argument("--config", required=True, help="explicit YAML config path")
    run.add_argument("--data-root", help="explicit external raw root; otherwise SAWOPT_DATA_ROOT is required")
    run.add_argument("--repository-root", help="review-package repository root; defaults to this source repository")
    return parser


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _synthetic_response(
    design: Mapping[str, Any], model: Mapping[str, Any], points: Sequence[float],
) -> list[float]:
    center = float(model["offset"])
    value = float(design["value"])
    return [(value - (center + float(point))) ** 2 for point in points]


def _response_metrics(
    evaluator: Callable[[Mapping[str, Any], Mapping[str, Any], Sequence[float]], Sequence[float]],
    design: Mapping[str, Any], model: Mapping[str, Any], grid: Mapping[str, Any],
) -> tuple[list[float], dict[str, float]]:
    response = evaluator(design, model, grid["points"])
    if isinstance(response, (str, bytes, Mapping)):
        raise ValueError("synthetic response evaluator must return a sequence")
    try:
        response = list(response)
    except TypeError as exc:
        raise ValueError("synthetic response evaluator must return an iterable sequence") from exc
    if len(response) != len(grid["points"]):
        raise ValueError("synthetic response length must match its frozen point set")
    values = []
    for index, raw in enumerate(response):
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
            raise ValueError(f"synthetic response value {index} must be finite")
        value = float(raw)
        if value < 0.0:
            raise ValueError(f"synthetic response value {index} must be non-negative")
        values.append(value)
    return values, {
        "synthetic_peak_error": max(values),
        "synthetic_mean_error": sum(values) / len(values),
    }


def run_experiment(
    config: Mapping[str, Any],
    *,
    source_sha: str,
    data_root: str | os.PathLike[str] | None = None,
    repository_root: str | os.PathLike[str] | None = None,
    run_id: str | None = None,
    response_evaluator: Callable[
        [Mapping[str, Any], Mapping[str, Any], Sequence[float]], Sequence[float]
    ] | None = None,
) -> dict[str, Any]:
    """Run the one-cell synthetic slice through R5 storage and review export.

    ``source_sha`` is required and deliberately injectable by tests; a test SHA
    records only fixture identity and must not be interpreted as a scientific
    execution. Normal CLI use resolves a clean committed Git source itself.
    """
    frozen = load_synthetic_config(config) if isinstance(config, (str, Path)) else config
    if not isinstance(frozen, Mapping):
        raise CliConfigError("configuration must be a validated mapping or YAML path")
    frozen = validate_synthetic_config(frozen)

    from .io.experiment_store import create_experiment_run
    from .optimization.lshade import LShadeBackend
    evaluator = _synthetic_response if response_evaluator is None else response_evaluator
    design_config = frozen["design"]
    model = frozen["model"]
    search_grid = frozen["search_grid"]
    validation_grid = frozen["validation_grid"]
    lower, upper = (float(value) for value in design_config["bounds"])
    budget = int(frozen["search_fe_limit"])
    seed = int(frozen["seed"])
    population = int(frozen["optimizer"]["initial_population"])
    backend = LShadeBackend(
        [(lower, upper)], seed=seed, integer_indices=(), comparator=_SyntheticComparator(),
        config={
            "initial_population": population,
            "min_population": int(frozen["optimizer"]["min_population"]),
            "history_size": int(frozen["optimizer"]["history_size"]),
            "total_budget": budget,
            "hard_max_budget": budget,
            "population_schedule_terminal_budget": budget,
            "requested_unique_budget": budget,
        },
    )

    cell_id = "synthetic"
    raw_run = create_experiment_run(
        frozen["experiment_id"],
        effective_config=frozen,
        scientific_inputs={
            "model": model,
            "search_grid": search_grid,
            "validation_grid": validation_grid,
        },
        expected_cells=[{
            "cell_id": cell_id,
            "topology": design_config["name"],
            "method": frozen["optimizer"]["name"],
            "seed": seed,
        }],
        source_sha=source_sha,
        search_fe_limit=budget,
        validation_point_limit=len(validation_grid["points"]),
        required_free_bytes=int(frozen["required_free_bytes"]),
        review_context=frozen["review_context"],
        run_id=run_id,
        data_root=data_root,
        method=frozen["optimizer"]["name"],
        topology=design_config["name"],
    )
    raw_run.record_cell(cell_id, status="RUNNING", executed=True, search_fes=0, validation_points=0)
    calls = 0

    def search_evaluator(vector):
        nonlocal calls
        value = float(vector[0])
        design = {"name": design_config["name"], "value": value, "unit": "dimensionless"}
        _response, metrics = _response_metrics(evaluator, design, model, search_grid)
        calls += 1
        return {
            "candidate_vector": [value],
            "metrics": metrics,
            "violations": {},
            "feasible": True,
            "max_violation": 0.0,
            "sum_violation": 0.0,
        }

    search_fes = 0
    search_summary: Mapping[str, Any] = {}
    incumbent = None
    best_design = None
    validation_response: list[float] = []
    validation_metrics: dict[str, float] = {}
    failure_message = None
    try:
        backend.initialize(search_evaluator)
        search_summary = backend.advance_to_unique_budget(budget)
        search_fes = int(search_summary["unique_evaluations"])
        incumbent = backend.incumbent()
        if incumbent is None:
            raise RuntimeError("synthetic optimizer produced no observed incumbent")
        if search_fes != calls:
            raise RuntimeError("synthetic search evaluator calls do not reconcile to unique FEs")
        if search_fes > budget:
            raise RuntimeError("synthetic optimizer exceeded its declared unique-FE budget")
        if search_fes == budget:
            best_value = float(incumbent["candidate_vector"][0])
            best_design = {"name": design_config["name"], "value": best_value, "unit": "dimensionless"}
            validation_response, validation_metrics = _response_metrics(
                evaluator, best_design, model, validation_grid,
            )
    except Exception as exc:
        failure_message = (
            f"synthetic evaluation failed ({type(exc).__name__}); no scientific result is claimed"
        )

    if failure_message is not None:
        raw_run.record_cell(
            cell_id,
            status="FAILED",
            executed=True,
            search_fes=int(backend.unique_evaluations),
            validation_points=0,
            reason=failure_message,
            failure_class="MODEL",
            search_proposals=int(backend.proposals_total),
            duplicate_proposals=int(backend.duplicate_count),
        )
        raw_run.record_error(classification="MODEL", message=failure_message, cell_id=cell_id)
        run_manifest = raw_run.close(status="FAILED")
    elif search_fes < budget:
        raw_run.record_cell(
            cell_id, status="INCOMPLETE", executed=True, search_fes=search_fes,
            validation_points=0, reason="synthetic search space exhausted before the declared budget",
            search_proposals=int(search_summary["proposals_total"]),
            duplicate_proposals=int(search_summary["duplicate_count"]),
        )
        if search_fes > 0 and incumbent is not None:
            raw_run.record_checkpoint(
                cell_id, phase="SEARCH", search_fes=search_fes, validation_points=0,
                metric_name="synthetic_peak_error",
                metric_value=float(incumbent["metrics"]["synthetic_peak_error"]),
                unit="dimensionless", observed_at_utc=_utc_now(),
            )
        run_manifest = raw_run.close(status="INCOMPLETE")
    else:
        validation_points = len(validation_response)
        validation_csv = io.StringIO(newline="")
        writer = csv.writer(validation_csv, lineterminator="\n")
        writer.writerow(["design_value", "grid_coordinate", "synthetic_error", "unit"])
        for coordinate, response_value in zip(validation_grid["points"], validation_response, strict=True):
            writer.writerow([best_design["value"], float(coordinate), response_value, "dimensionless"])
        raw_run.write_artifact("artifacts/validation.csv", validation_csv.getvalue().encode("utf-8"))
        geometry = {"status": "NOT_APPLICABLE", "unit": "dimensionless"}
        violations: dict[str, float] = {}
        raw_run.record_cell(
            cell_id,
            status="COMPLETED",
            executed=True,
            search_fes=search_fes,
            validation_points=validation_points,
            result={
                "design": best_design,
                "geometry": geometry,
                "metrics": dict(incumbent["metrics"]),
                "violations": violations,
                "feasible": True,
                "synthetic_only": True,
            },
            design=best_design,
            geometry=geometry,
            search_metrics=dict(incumbent["metrics"]),
            search_violations=violations,
            validation_metrics=validation_metrics,
            validation_violations=violations,
            feasible=True,
            search_proposals=int(search_summary["proposals_total"]),
            duplicate_proposals=int(search_summary["duplicate_count"]),
            cache_hits=int(search_summary["cache_hits"]),
        )
        raw_run.record_checkpoint(
            cell_id, phase="SEARCH", search_fes=search_fes, validation_points=0,
            metric_name="synthetic_peak_error",
            metric_value=float(incumbent["metrics"]["synthetic_peak_error"]),
            unit="dimensionless", observed_at_utc=_utc_now(),
        )
        raw_run.record_checkpoint(
            cell_id, phase="VALIDATION", search_fes=search_fes,
            validation_points=validation_points, metric_name="synthetic_peak_error",
            metric_value=validation_metrics["synthetic_peak_error"],
            unit="dimensionless", observed_at_utc=_utc_now(),
        )
        run_manifest = raw_run.close(status="COMPLETED")

    from .reporting.experiment_review import export_review_package

    exported = export_review_package(raw_run.path, repository_root=repository_root or _project_root())
    return {
        "status": run_manifest["status"],
        "package_status": exported.package_status,
        "experiment_id": raw_run.experiment_id,
        "run_id": raw_run.run_id,
        "raw_run_directory": str(raw_run.path),
        "review_directory": exported.path,
        "search_fes": run_manifest["search_fe_count"],
        "validation_points": run_manifest["validation_point_count"],
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    source_sha: str | None = None,
    data_root: str | os.PathLike[str] | None = None,
    repository_root: str | os.PathLike[str] | None = None,
    run_id: str | None = None,
    response_evaluator: Callable[
        [Mapping[str, Any], Mapping[str, Any], Sequence[float]], Sequence[float]
    ] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_synthetic_config(args.config)
        if args.command == "validate":
            print(json.dumps({
                "status": "VALID",
                "experiment_id": config["experiment_id"],
                "method": config["optimizer"]["name"],
                "search_fe_limit": config["search_fe_limit"],
                "validation_points": len(config["validation_grid"]["points"]),
                "synthetic_only": True,
            }, sort_keys=True))
            return 0
        source_root = _project_root()
        identity = source_sha if source_sha is not None else _source_sha(source_root)
        result = run_experiment(
            config,
            source_sha=identity,
            data_root=args.data_root if args.data_root is not None else data_root,
            repository_root=args.repository_root or repository_root or source_root,
            run_id=run_id,
            response_evaluator=response_evaluator,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "COMPLETED" else 1
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main", "run_experiment"]
