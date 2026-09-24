"""Stage 3.5 Phase C supplement runner and offline comparison reports.

The module has two deliberately separate responsibilities:

* run only the required new C64 production arm (S0 + L-SHADE, 64k horizon),
  cold-started on one 64k trajectory per seed; and
* reconstruct B/D crossover evidence and compare C64/D64 without touching the
  historical run artifacts.

No COM equations, specifications, ranking rules, or optimizer parameters are
defined here.  The existing study and evaluator implementations remain the
single source of truth for those concerns.
"""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np

from ..core.models import FilterDesign
from ..io.config import load_experiment_config
from ..io.serialization import save
from ..optimizers.selection import rank
from ..orchestration.run_manager import transition
from ..reporting.review_bundle import _source_hash
from .convergence import normalize_convergence_config
from .convergence_evidence import apply_checkpoint_evidence
from .optimizer_ab import lshade_trajectory_worker, run_workers
from .search_efficiency import (
    arm_config,
    bounds_for_strategy,
    clean,
    sha256,
)


ROOT = Path(__file__).resolve().parents[3]
SEEDS = [20260917, 20260918, 20260919, 20260920]
CROSSOVER_BUDGETS = [4000, 8000, 16000, 32000, 64000]
C64_BUDGETS = [4000, 8000, 16000, 32000, 64000]
TERMINAL_BUDGET = 64000
OLD_PHASE_C_RUN = ROOT / "runs" / "stage3_5_phase_c_revised"
OLD_B_ARM = OLD_PHASE_C_RUN / "arms" / "B_S1_LEGACY" / "phase_c2"
OLD_D_ARM = OLD_PHASE_C_RUN / "arms" / "D_S1_LSHADE" / "phase_c2"


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    values = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(set().union(*(row.keys() for row in values))) if values else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(values)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if np.isfinite(value) else default


def _load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def _record_files(root: Path, optimizer: str) -> list[Path]:
    if optimizer == "scipy_de_legacy":
        return sorted(root.glob("trials/center_outer_same__B*__seed*.json"))
    return sorted(root.glob("trials/lshade/center_outer_same/seed*/B*.json"))


def _load_c64_records(run: Path) -> list[dict[str, Any]]:
    paths = _record_files(run / "production" / "C64_S0_LSHADE", "lshade")
    return [_json(path) for path in paths if path.name != "optimizer_checkpoint.json"]


def _load_reused_checkpoint_rows() -> list[dict[str, Any]]:
    rows = _load_csv(OLD_PHASE_C_RUN / "checkpoint_data.csv")
    result = []
    for row in rows:
        if row.get("arm") not in {"B_S1_LEGACY", "D_S1_LSHADE"}:
            continue
        row["budget"] = int(float(row["budget"]))
        row["seed"] = int(row["seed"])
        for field in (
            "feasible", "max_violation", "sum_violation", "worst_il_db",
            "objective_calls", "unique_decoded_evaluations", "cache_hits",
            "elapsed_s",
        ):
            if field in row and row[field] not in (None, ""):
                if field == "feasible":
                    row[field] = str(row[field]).lower() == "true"
                elif field not in {"objective_calls", "unique_decoded_evaluations", "cache_hits"}:
                    row[field] = _float(row[field])
                else:
                    row[field] = int(float(row[field]))
        if row.get("elapsed_s", 0) in (0, 0.0):
            row["elapsed_s"] = None
        rank_value = row.get("validated_rank_tuple")
        if isinstance(rank_value, str) and rank_value:
            row["validated_rank_tuple"] = json.loads(rank_value)
        result.append(row)
    return result


def _primary(row: Mapping[str, Any]) -> float:
    if bool(row.get("feasible", False)):
        return float(row.get("worst_il_db", np.inf))
    return float(row.get("max_violation", np.inf))


def _crossover_rows(reused: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_key = {
        (str(row["arm"]), int(row["seed"]), int(row["budget"])): row
        for row in reused
    }
    rows = []
    for optimizer, arm in (("Legacy-DE", "B_S1_LEGACY"), ("L-SHADE", "D_S1_LSHADE")):
        for budget in CROSSOVER_BUDGETS:
            for seed in SEEDS:
                source = by_key.get((arm, seed, budget))
                if source is None:
                    rows.append({
                        "seed": seed, "optimizer": optimizer, "search_space": "S1",
                        "terminal_budget": TERMINAL_BUDGET, "checkpoint_budget": budget,
                        "feasible": None, "max_violation": None, "sum_violation": None,
                        "worst_il_db": None, "validated_rank": None,
                        "objective_calls": None, "unique_decoded_evaluations": None,
                        "cache_hits": None, "optimizer_wall_time_s": None,
                        "missing_checkpoint_evidence": True,
                    })
                    continue
                rows.append({
                    "seed": seed, "optimizer": optimizer, "search_space": "S1",
                    "terminal_budget": TERMINAL_BUDGET, "checkpoint_budget": budget,
                    "feasible": bool(source.get("feasible", False)),
                    "max_violation": source.get("max_violation"),
                    "sum_violation": source.get("sum_violation"),
                    "worst_il_db": source.get("worst_il_db"),
                    "validated_rank": json.dumps(source.get("validated_rank_tuple")),
                    "objective_calls": source.get("objective_calls"),
                    "unique_decoded_evaluations": source.get("unique_decoded_evaluations"),
                    "cache_hits": source.get("cache_hits"),
                    "optimizer_wall_time_s": None,
                    "missing_checkpoint_evidence": False,
                })
    return rows


def _aggregate_crossover(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    medians: dict[str, dict[str, float | None]] = {}
    paired: list[dict[str, Any]] = []
    for budget in CROSSOVER_BUDGETS:
        medians[str(budget)] = {}
        for optimizer in ("Legacy-DE", "L-SHADE"):
            values = [
                _primary(row) for row in rows
                if row["optimizer"] == optimizer
                and int(row["checkpoint_budget"]) == budget
                and row.get("max_violation") is not None
            ]
            medians[str(budget)][optimizer] = float(np.median(values)) if values else None
        legacy = {
            int(row["seed"]): row for row in rows
            if row["optimizer"] == "Legacy-DE" and int(row["checkpoint_budget"]) == budget
        }
        lshade = {
            int(row["seed"]): row for row in rows
            if row["optimizer"] == "L-SHADE" and int(row["checkpoint_budget"]) == budget
        }
        deltas = []
        for seed in sorted(set(legacy) & set(lshade)):
            if legacy[seed].get("max_violation") is None or lshade[seed].get("max_violation") is None:
                continue
            delta = _primary(lshade[seed]) - _primary(legacy[seed])
            deltas.append(float(delta))
            paired.append({"seed": seed, "checkpoint_budget": budget, "delta_primary_lshade_minus_legacy": float(delta)})
        medians[str(budget)]["paired_delta_median"] = float(np.median(deltas)) if deltas else None
        medians[str(budget)]["paired_seed_count"] = len(deltas)
    first_observed_better = next(
        (int(budget) for budget in CROSSOVER_BUDGETS
         if medians[str(budget)]["paired_delta_median"] is not None
         and medians[str(budget)]["paired_delta_median"] < 0),
        None,
    )
    missing = [
        budget for budget in CROSSOVER_BUDGETS
        if medians[str(budget)]["paired_seed_count"] < len(SEEDS)
    ]
    return {
        "budgets": CROSSOVER_BUDGETS,
        "median_by_budget": medians,
        "paired_deltas": paired,
        "first_observed_lshade_better_budget": first_observed_better,
        "first_crossover_budget": (
            first_observed_better
            if first_observed_better is not None
            and all(
                medians[str(budget)]["paired_seed_count"] == len(SEEDS)
                for budget in CROSSOVER_BUDGETS
                if budget < first_observed_better
            )
            else None
        ),
        "crossover_criterion": "median validated primary delta L-SHADE - Legacy-DE < 0",
        "missing_checkpoint_evidence": missing,
        "evidence_complete": not missing,
        "crossover_identifiable": not missing,
    }


def _validation_grid() -> np.ndarray:
    path = OLD_PHASE_C_RUN / "common_validation_grid_hz.csv"
    rows = _load_csv(path)
    return np.asarray([float(row["frequency_hz"]) for row in rows], dtype=float)


def _validate_c64_records(cfg: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    from ..problem.evaluator import dense

    grid = _validation_grid()
    z0 = float(cfg.get("convergence", {}).get("impedance_ohm", 50.0))
    rows = []
    for record in records:
        design = FilterDesign(**dict(record["design"]))
        _freq, (validated, _net, _sim) = dense(
            design, cfg, z0, z0, wiring="center_outer_same",
            base_grid=grid, passes=0, validation=True,
        )
        validated = dict(validated)
        rank_tuple = tuple(float(value) for value in rank(validated))
        enriched = apply_checkpoint_evidence(
            record,
            current_budget=int(record.get("requested_unique_design_budget", record.get("checkpoint_budget", 0))),
            terminal_budget=TERMINAL_BUDGET,
        )
        enriched["micro_polish_improvement"] = record.get("micro_polish_improvement")
        rows.append({
            "arm": "C64_S0_LSHADE", "seed": int(record["seed"]),
            "budget": int(record.get("requested_unique_design_budget", 0)),
            "feasible": bool(validated.get("feasible", False)),
            "max_violation": float(validated.get("max_violation", np.inf)),
            "sum_violation": float(sum(validated.get("violations", {}).values())),
            "worst_il_db": float(validated.get("metrics", {}).get("worst_il_db", np.inf)),
            "ripple_db": float(validated.get("metrics", {}).get("ripple_db", np.inf)),
            "validated_rank_tuple": list(rank_tuple),
            "common_validation_grid_id": "34eb7177ea863e031fb6a5e620e00dee6a37bee00cc1bd7a58a489165a923534",
            "common_validation_frequency_count": int(len(grid)),
            "objective_calls": record.get("objective_calls"),
            "unique_decoded_evaluations": record.get("unique_decoded_evaluations"),
            "cache_hits": record.get("cache_hits"),
            "cache_hit_rate": record.get("cache_hit_rate"),
            "duplicate_decoded_attempts": record.get("duplicate_decoded_attempts"),
            "duplicate_decoded_rate": record.get("duplicate_decoded_rate"),
            "optimizer_wall_time_s": record.get("optimizer_wall_time_s"),
            "validation_wall_time_s": record.get("validation_wall_time_s"),
            "total_trial_wall_time_s": record.get("total_trial_wall_time_s"),
            "terminal_budget": TERMINAL_BUDGET,
            "current_budget": int(record.get("current_budget", record.get("requested_unique_design_budget", 0))),
            **{field: enriched.get(field) for field in (
                "grid_converged", "recovery_pending_confirmation",
                "boundary_pending_confirmation", "hard_bound_unresolved",
                "micro_polish_improvement",
                "fraction_of_budget_at_last_significant_improvement",
            )},
            "convergence_evidence_missing_fields": enriched.get("convergence_evidence_missing_fields", []),
            "design": json.dumps(clean(dict(record["design"])), sort_keys=True),
        })
    return rows


def _target_tuple() -> tuple[float, ...]:
    target = _json(OLD_PHASE_C_RUN / "common_validation_targets.json")
    return tuple(float(value) for value in target["T_median_common"])


def _space_summary(rows: Sequence[Mapping[str, Any]], target: tuple[float, ...]) -> dict[str, Any]:
    final = [row for row in rows if int(row["budget"]) == TERMINAL_BUDGET]
    by_arm = {arm: [row for row in final if row["arm"] == arm] for arm in ("C64_S0_LSHADE", "D64_S1_LSHADE")}
    result: dict[str, Any] = {}
    for arm, values in by_arm.items():
        primary = [_primary(row) for row in values]
        result[arm] = {
            "seed_count": len(values),
            "feasible_fraction": float(np.mean([bool(row["feasible"]) for row in values])) if values else None,
            "median_primary": float(np.median(primary)) if primary else None,
            "p75_primary": float(np.percentile(primary, 75)) if primary else None,
            "worst_primary": float(max(primary)) if primary else None,
            "iqr_primary": float(np.percentile(primary, 75) - np.percentile(primary, 25)) if primary else None,
            "target_hit_count": sum(tuple(row["validated_rank_tuple"]) <= target for row in values),
            "rank_tuple": [row["validated_rank_tuple"] for row in sorted(values, key=lambda item: item["seed"])],
        }
    evidence_rows = [row for row in final if row.get("convergence_evidence_missing_fields")]
    result["convergence_evidence_complete"] = not evidence_rows
    result["convergence_evidence_missing_rows"] = [
        {"arm": row["arm"], "seed": row["seed"], "budget": row["budget"],
         "fields": row.get("convergence_evidence_missing_fields", [])}
        for row in evidence_rows
    ]
    c = {int(row["seed"]): row for row in by_arm["C64_S0_LSHADE"]}
    d = {int(row["seed"]): row for row in by_arm["D64_S1_LSHADE"]}
    paired = []
    for seed in sorted(set(c) & set(d)):
        paired.append({
            "seed": seed,
            "delta_primary_s0_minus_s1": _primary(c[seed]) - _primary(d[seed]),
            "s0_rank_tuple": c[seed]["validated_rank_tuple"],
            "s1_rank_tuple": d[seed]["validated_rank_tuple"],
        })
    result["paired"] = paired
    return result


def select_stage35_decisions(crossover: Mapping[str, Any], space: Mapping[str, Any], *, tolerance: float = .02) -> dict[str, Any]:
    """Return independent optimizer and search-space decisions."""
    optimizer_decision = "OPTIMIZER_UNRESOLVED"
    d64 = crossover.get("median_by_budget", {}).get("64000", {})
    legacy = d64.get("Legacy-DE")
    lshade = d64.get("L-SHADE")
    if legacy is not None and lshade is not None:
        if lshade <= legacy * (1.0 - tolerance):
            optimizer_decision = "PROMOTE_LSHADE"
        elif legacy <= lshade * (1.0 - tolerance):
            optimizer_decision = "PROMOTE_LEGACY_DE"

    search_decision = "SEARCH_SPACE_UNRESOLVED"
    s0 = space.get("C64_S0_LSHADE", {})
    s1 = space.get("D64_S1_LSHADE", {})
    s0_median, s1_median = s0.get("median_primary"), s1.get("median_primary")
    if s0_median is not None and s1_median is not None:
        if s0_median <= s1_median * (1.0 - tolerance):
            search_decision = "PROMOTE_S0"
        elif s1_median <= s0_median * (1.0 - tolerance):
            search_decision = "PROMOTE_S1"
        elif all(abs(float(row["delta_primary_s0_minus_s1"])) <= tolerance * max(abs(s1_median), 1.0)
                 for row in space.get("paired", [])):
            search_decision = "PROMOTE_S0"
    evidence_status = "COMPLETE" if (
        bool(crossover.get("evidence_complete"))
        and bool(space.get("convergence_evidence_complete", True))
    ) else "INCOMPLETE"
    return {
        "optimizer_decision": optimizer_decision,
        "search_space_decision": search_decision,
        "evidence_status": evidence_status,
        "equivalence_tolerance_fraction": tolerance,
    }


def _make_plots(out: Path, crossover: Mapping[str, Any], space: Mapping[str, Any]) -> None:
    import matplotlib
    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    out.mkdir(parents=True, exist_ok=True)
    budgets = np.asarray(CROSSOVER_BUDGETS, dtype=float)
    plt.figure(figsize=(7, 4))
    for name, color in (("Legacy-DE", "tab:blue"), ("L-SHADE", "tab:orange")):
        values = [crossover["median_by_budget"][str(int(b))].get(name) for b in budgets]
        plt.plot(budgets, [np.nan if value is None else value for value in values], "o-", label=name, color=color)
    plt.xscale("log", base=2)
    plt.xlabel("Unique decoded evaluations")
    plt.ylabel("Median validated primary")
    plt.grid(alpha=.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out / "optimizer_budget_curve.png", dpi=150)
    plt.close()

    plt.figure(figsize=(7, 4))
    delta = [crossover["median_by_budget"][str(int(b))].get("paired_delta_median") for b in budgets]
    plt.axhline(0.0, color="black", linewidth=.8)
    plt.plot(budgets, [np.nan if value is None else value for value in delta], "o-", color="tab:purple")
    plt.xscale("log", base=2)
    plt.xlabel("Unique decoded evaluations")
    plt.ylabel("L-SHADE - Legacy-DE primary")
    plt.grid(alpha=.25)
    plt.tight_layout()
    plt.savefig(out / "optimizer_paired_delta.png", dpi=150)
    plt.close()

    paired = space.get("paired", [])
    plt.figure(figsize=(7, 4))
    if paired:
        plt.bar([str(row["seed"]) for row in paired], [row["delta_primary_s0_minus_s1"] for row in paired], color="tab:green")
    plt.axhline(0.0, color="black", linewidth=.8)
    plt.xlabel("Seed")
    plt.ylabel("S0 - S1 primary")
    plt.grid(axis="y", alpha=.25)
    plt.tight_layout()
    plt.savefig(out / "search_space_seed_comparison.png", dpi=150)
    plt.close()


def _run_targeted_tests(out: Path) -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", "-q", "tests/unit/optimization/test_stage33.py",
               "tests/unit/optimization/test_stage331.py", "tests/unit/optimization/test_stage34b_convergence.py",
               "tests/unit/studies/test_search_efficiency.py", "tests/unit/orchestration/test_worker.py"]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (out / "tests").mkdir(parents=True, exist_ok=True)
    (out / "tests" / "pytest.txt").write_text(
        completed.stdout + "\n" + completed.stderr, encoding="utf-8"
    )
    summary = {"command": command, "passed": completed.returncode == 0, "exit_code": completed.returncode}
    save(out / "tests" / "test_summary.json", summary)
    return summary


def _write_review_bundle(run: Path, summary: Mapping[str, Any]) -> Path:
    bundle_root = ROOT / "artifacts" / "review_bundles"
    bundle_root.mkdir(parents=True, exist_ok=True)
    output = bundle_root / "stage3_5_phase_c_supplement_review.zip"
    staging = run / "_review_bundle"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for directory in ("config", "results", "plots", "tests", "environment"):
        (staging / directory).mkdir()
    config_source = run / "config" / "stage3_5_phase_c_supplement.yaml"
    if config_source.is_file():
        shutil.copy2(config_source, staging / "config" / config_source.name)
    for source in (run / "results").glob("*"):
        if source.is_file():
            shutil.copy2(source, staging / "results" / source.name)
    for name in ("status.json", "supplement_manifest.json"):
        source = run / name
        if source.is_file():
            shutil.copy2(source, staging / "results" / name)
    for source in (run / "plots").glob("*"):
        if source.is_file():
            shutil.copy2(source, staging / "plots" / source.name)
    for source in (run / "tests").glob("*"):
        if source.is_file():
            shutil.copy2(source, staging / "tests" / source.name)
    runtime = {
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "source_hash": _source_hash(ROOT / "src" / "sawopt"),
    }
    save(staging / "environment" / "local_runtime.json", runtime)
    (staging / "environment" / "git_status.txt").write_text(
        subprocess.run(["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True, check=True).stdout,
        encoding="utf-8",
    )
    (staging / "REVIEW_ME.md").write_text((run / "REVIEW_ME.md").read_text(encoding="utf-8"), encoding="utf-8")
    (staging / "PHASE_C_SUPPLEMENT_COMPLETE_WAITING_FOR_REVIEW.txt").write_text(
        "PHASE_C_SUPPLEMENT_COMPLETE_WAITING_FOR_REVIEW\n", encoding="utf-8"
    )
    files = []
    for source in sorted(staging.rglob("*")):
        if source.is_file():
            files.append({"path": source.relative_to(staging).as_posix(), "sha256": sha256(source), "bytes": source.stat().st_size})
    save(staging / "bundle_manifest.json", {"bundle_format_version": 1, "files": files, "summary": summary})
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for source in sorted(staging.rglob("*")):
            if source.is_file():
                archive.write(source, source.relative_to(staging).as_posix())
    with ZipFile(output) as archive:
        manifest = _json(staging / "bundle_manifest.json")
        for item in manifest["files"]:
            if hashlib.sha256(archive.read(item["path"])).hexdigest() != item["sha256"]:
                raise RuntimeError(f"review bundle hash mismatch: {item['path']}")
    return output


def _write_review_text(run: Path, summary: Mapping[str, Any]) -> None:
    decisions = summary["decisions"]
    crossover = summary["crossover"]
    space = summary["search_space"]
    lines = [
        "# Stage 3.5 Phase C supplement review",
        "",
        f"- optimizer decision: `{decisions['optimizer_decision']}`",
        f"- search-space decision: `{decisions['search_space_decision']}`",
        f"- convergence status: `{summary['convergence_status']}`",
        f"- evidence completeness: `{decisions['evidence_status']}`",
        f"- new run wall time: `{summary.get('new_run_wall_time_s')}` s",
        f"- reused runs: `{summary['reused_runs']}`",
        f"- new runs: `{summary['new_runs']}`",
        f"- test result: `{summary['tests']}`",
        "",
        "## Optimizer crossover",
        "",
        f"- first observed L-SHADE-better budget: `{crossover.get('first_observed_lshade_better_budget')}`",
        f"- exact first crossover budget: `{crossover['first_crossover_budget']}`",
        f"- crossover identifiable: `{crossover.get('crossover_identifiable')}`",
        f"- missing checkpoint evidence: `{crossover['missing_checkpoint_evidence']}`",
        "",
        "| budget | Legacy-DE median | L-SHADE median | paired delta (L-SHADE - Legacy) | paired seeds |",
        "|---:|---:|---:|---:|---:|",
    ]
    for budget in CROSSOVER_BUDGETS:
        value = crossover["median_by_budget"][str(budget)]
        lines.append(f"| {budget} | {value.get('Legacy-DE')} | {value.get('L-SHADE')} | {value.get('paired_delta_median')} | {value.get('paired_seed_count')} |")
    lines += [
        "",
        "## S0 vs S1 at the same L-SHADE 64k horizon",
        "",
        f"- S0: `{json.dumps(space.get('C64_S0_LSHADE'), ensure_ascii=False)}`",
        f"- S1: `{json.dumps(space.get('D64_S1_LSHADE'), ensure_ascii=False)}`",
        f"- paired deltas: `{json.dumps(space.get('paired'), ensure_ascii=False)}`",
        "",
        "## Gate and limitations",
        "",
        f"- convergence evidence: `{json.dumps(summary['convergence_evidence'], ensure_ascii=False)}`",
        "- Existing B/D/C artifacts were read only; no historical artifact was rewritten.",
        "- Phase D was not started.",
        "",
        "PHASE_C_SUPPLEMENT_COMPLETE_WAITING_FOR_REVIEW",
        "",
    ]
    (run / "REVIEW_ME.md").write_text("\n".join(lines), encoding="utf-8")


def run_phase_c_supplement(
    config_path: str | Path,
    run: str | Path,
    *,
    resume: bool = False,
    refresh_only: bool = False,
) -> dict[str, Any]:
    """Execute the required C64 arm and produce the review bundle.

    ``refresh_only`` is an offline reporting path for a completed production
    run. It revalidates and repackages existing artifacts without rerunning
    the 64k optimization.
    """
    if resume and not refresh_only:
        raise ValueError("Phase C supplement requires a cold start; resume is forbidden")
    config_path = Path(config_path).resolve()
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=True)
    (run / "config").mkdir(exist_ok=True)
    shutil.copy2(config_path, run / "config" / config_path.name)
    base = normalize_convergence_config(load_experiment_config(config_path))
    stage = base.get("stage3_5", {})
    seeds = [int(value) for value in stage.get("seeds", SEEDS)]
    if seeds != SEEDS:
        raise ValueError("supplement seed set must match the existing Stage 3.5 four seeds")
    s1_path = Path(stage.get("s1_path", "artifacts/stage3_5/phase_a_revised/search_space_s1.yaml"))
    if not s1_path.is_absolute():
        s1_path = ROOT / s1_path
    import yaml
    s1 = yaml.safe_load(s1_path.read_text(encoding="utf-8")) or {}
    state = bounds_for_strategy(base, "S0", s1)
    cfg = arm_config(
        base, phase="supplement", strategy="S0", optimizer="lshade",
        state=state, seeds=seeds, budgets=C64_BUDGETS, workers=int(stage.get("workers", 4)),
    )
    cfg["stage3_5_arm"]["terminal_budget"] = TERMINAL_BUDGET
    cfg["stage3_5_arm"]["cold_start"] = True
    cfg["stage3_5_arm"]["source_population_injected"] = False
    production = run / "production" / "C64_S0_LSHADE"
    production.mkdir(parents=True, exist_ok=True)
    if refresh_only:
        prior_summary = run / "results" / "phase_c_supplement_summary.json"
        prior = _json(prior_summary) if prior_summary.is_file() else {}
        new_wall = prior.get("new_run_wall_time_s")
    else:
        tasks = [(str(production), cfg, "center_outer_same", seed, C64_BUDGETS, False) for seed in seeds]
        started = time.monotonic()
        run_workers(tasks, lshade_trajectory_worker, min(int(stage.get("workers", 4)), len(seeds)), 1)
        new_wall = time.monotonic() - started
    records = _load_c64_records(run)
    if len(records) != len(seeds) * len(C64_BUDGETS):
        raise RuntimeError(f"C64 record count mismatch: {len(records)}")
    manifest = {
        "study_type": "stage3_5_phase_c_supplement",
        "phase": "C_supplement",
        "config_path": str(config_path), "config_sha256": sha256(config_path),
        "source_hash": _source_hash(ROOT / "src" / "sawopt"),
        "seeds": seeds, "checkpoints": C64_BUDGETS,
        "terminal_budget": TERMINAL_BUDGET, "cold_start": True,
        "source_population_injected": False,
        "population_schedule_identifier": "lshade_linear_population_v1",
        "reused_runs": [str(OLD_B_ARM), str(OLD_D_ARM)],
        "new_run": str(production),
    }
    save(run / "supplement_manifest.json", manifest)
    c64_rows = _validate_c64_records(base, records)
    reused = _load_reused_checkpoint_rows()
    crossover_rows = _crossover_rows(reused)
    crossover = _aggregate_crossover(crossover_rows)
    d64_rows = []
    for row in reused:
        if row["arm"] == "D_S1_LSHADE" and row["budget"] == TERMINAL_BUDGET:
            d64_rows.append({
                "arm": "D64_S1_LSHADE", "seed": row["seed"], "budget": TERMINAL_BUDGET,
                "feasible": row.get("feasible", False), "max_violation": row.get("max_violation"),
                "sum_violation": row.get("sum_violation"), "worst_il_db": row.get("worst_il_db"),
                "ripple_db": row.get("ripple_db"), "validated_rank_tuple": row.get("validated_rank_tuple"),
                "convergence_evidence_missing_fields": ["micro_polish_improvement"],
            })
    space_rows = c64_rows + d64_rows
    space = _space_summary(space_rows, _target_tuple())
    convergence_evidence = {
        "C64_S0_LSHADE": {
            "missing_fields_by_checkpoint": {
                str(row["budget"]): row.get("convergence_evidence_missing_fields", [])
                for row in c64_rows
            },
            "complete": all(not row.get("convergence_evidence_missing_fields") for row in c64_rows),
        },
        "D64_S1_LSHADE": {
            "complete": False,
            "missing_fields": ["micro_polish_improvement"],
            "source": "reused historical run; no artifact rewrite",
        },
    }
    decisions = select_stage35_decisions(crossover, space)
    convergence_status = "inconclusive" if decisions["evidence_status"] != "COMPLETE" else "likely_underoptimized"
    results = run / "results"
    results.mkdir(exist_ok=True)
    _write_csv(results / "optimizer_crossover.csv", crossover_rows)
    save(results / "optimizer_crossover_summary.json", crossover)
    _write_csv(results / "search_space_comparison.csv", space_rows)
    save(results / "search_space_decision.json", decisions | {"paired": space.get("paired", [])})
    save(results / "convergence_evidence.json", convergence_evidence)
    telemetry = [
        {"arm": "C64_S0_LSHADE", **{key: row.get(key) for key in (
            "seed", "budget", "objective_calls", "unique_decoded_evaluations", "cache_hits",
            "cache_hit_rate", "duplicate_decoded_attempts", "duplicate_decoded_rate",
            "optimizer_wall_time_s", "validation_wall_time_s", "total_trial_wall_time_s",
        )}}
        for row in c64_rows
    ]
    telemetry += [
        {"arm": row["arm"], "seed": row["seed"], "budget": row["budget"],
         "objective_calls": reused_row.get("objective_calls"),
         "unique_decoded_evaluations": reused_row.get("unique_decoded_evaluations"),
         "cache_hits": reused_row.get("cache_hits"), "cache_hit_rate": None,
         "duplicate_decoded_attempts": None, "duplicate_decoded_rate": None,
         "optimizer_wall_time_s": None, "validation_wall_time_s": None,
         "total_trial_wall_time_s": reused_row.get("elapsed_s")}
        for row in d64_rows
        for reused_row in reused
        if reused_row["arm"] == "D_S1_LSHADE" and reused_row["seed"] == row["seed"] and reused_row["budget"] == row["budget"]
    ]
    _write_csv(results / "telemetry_comparison.csv", telemetry)
    plots = run / "plots"
    _make_plots(plots, crossover, space)
    tests = _run_targeted_tests(run)
    summary = {
        "study_type": "stage3_5_phase_c_supplement",
        "optimizer_decision": decisions["optimizer_decision"],
        "search_space_decision": decisions["search_space_decision"],
        "decisions": decisions,
        "convergence_status": convergence_status,
        "evidence_completeness": decisions["evidence_status"],
        "convergence_evidence": convergence_evidence,
        "crossover": crossover,
        "search_space": space,
        "new_run_wall_time_s": new_wall,
        "reused_runs": [str(OLD_B_ARM), str(OLD_D_ARM)],
        "new_runs": [str(production)],
        "tests": tests,
        "phase_d_started": False,
    }
    save(results / "phase_c_supplement_summary.json", summary)
    _write_review_text(run, summary)
    (run / "PHASE_C_SUPPLEMENT_COMPLETE_WAITING_FOR_REVIEW.txt").write_text(
        "PHASE_C_SUPPLEMENT_COMPLETE_WAITING_FOR_REVIEW\n", encoding="utf-8"
    )
    if (run / "status.json").is_file():
        transition(run, "REVIEW_WAITING", exit_code=0, error=None)
    bundle = _write_review_bundle(run, summary)
    summary["review_bundle"] = str(bundle)
    save(results / "phase_c_supplement_summary.json", summary)
    return summary


__all__ = ["run_phase_c_supplement", "select_stage35_decisions"]
