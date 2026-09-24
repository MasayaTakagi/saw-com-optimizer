"""Stage 3.5 matched-protocol L-SHADE parity diagnostic.

This is an opt-in orchestration wrapper.  It runs exactly one S1/50-ohm
trajectory to 16,000 unique evaluations while keeping the L-SHADE population
schedule horizon at 64,000.  It deliberately does not modify optimizer,
objective, physics, or search-space behavior.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import yaml

from ..core.models import FilterDesign
from ..io.config import load_experiment_config
from ..io.serialization import save
from ..optimizers.selection import rank
from ..problem.evaluator import dense
from ..reporting.review_bundle import _source_hash, is_checkpoint_artifact
from .convergence import normalize_convergence_config
from .optimizer_ab import lshade_trajectory_worker, run_workers
from .search_efficiency import arm_config, bounds_for_strategy, clean


ROOT = Path(__file__).resolve().parents[3]
SEED = 20260917
PORT_IMPEDANCE_OHM = 50.0
TERMINAL_HORIZON = 64000
DIAGNOSTIC_STOP = 16000
REQUESTED_CHECKPOINTS = [16000]
HISTORICAL_CHECKPOINTS = [16000, 32000, 64000]
EXPECTED_S1_SHA256 = "b4132c8ff4894f946c3ec4d77239d325bf786fd5ae0266649f1bbc22ed28db16"
HISTORICAL_SOURCE_HASH = "bf1d927939c9c9ce99ef7067d469596d240b098914d455a7cd87410cc7ad6caa"
HISTORICAL_RECORD = (
    ROOT / "runs" / "stage3_5_phase_c_revised" / "arms" / "D_S1_LSHADE"
    / "phase_c2" / "trials" / "lshade" / "center_outer_same"
    / f"seed{SEED}" / "B16000.json"
)


def _json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, stderr=subprocess.STDOUT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"unavailable: {exc}"


def _historical_protocol(record: Mapping[str, Any]) -> dict[str, Any]:
    population = list(record.get("population_trace", []))
    archive = list(record.get("archive_trace", []))
    events = list(record.get("frequency_grid_events", []))
    population_last = population[-1] if population else {}
    archive_last = archive[-1] if archive else {}
    event = events[0] if events else {}
    pre_exchange = (
        int(record.get("unique_decoded_evaluations", -1)) == DIAGNOSTIC_STOP
        and int(population_last.get("unique_evaluation", -1)) == DIAGNOSTIC_STOP
        and int(archive_last.get("unique_evaluation", -1)) == DIAGNOSTIC_STOP
        and int(population_last.get("frequency_grid_version", -1)) == 1
        and int(archive_last.get("frequency_grid_version", -1)) == 1
        and int(event.get("frequency_grid_version", -1)) == 2
    )
    return {
        "record_path": str(HISTORICAL_RECORD),
        "seed": record.get("seed"),
        "search_space": "S1",
        "port_impedance_ohm": PORT_IMPEDANCE_OHM,
        "terminal_horizon": record.get("population_schedule_terminal_budget"),
        "hard_max_budget": record.get("hard_max_budget"),
        "checkpoint_sequence": HISTORICAL_CHECKPOINTS,
        "event_count": len(events),
        "event_summary": [
            {
                "event": item.get("event"),
                "added_count": item.get("added_count"),
                "frequency_grid_version": item.get("frequency_grid_version"),
                "has_checkpoint_budget": "checkpoint_budget" in item,
            }
            for item in events
        ],
        "B16000_semantics": "PRE_EXCHANGE" if pre_exchange else "UNKNOWN",
        "overall_historical_semantics": "UNKNOWN",
        "pre_exchange_evidence": {
            "population_trace_last_grid_version": population_last.get("frequency_grid_version"),
            "archive_trace_last_grid_version": archive_last.get("frequency_grid_version"),
            "serialized_event_version": event.get("frequency_grid_version"),
            "serialized_event_has_budget": "checkpoint_budget" in event,
        },
    }


def build_matched_protocol_config(base: Mapping[str, Any], s1: Mapping[str, Any]) -> dict[str, Any]:
    """Build the explicit matched-protocol configuration without changing defaults."""
    state = bounds_for_strategy(base, "S1", s1)
    cfg = arm_config(
        base,
        phase="matched_protocol",
        strategy="S1",
        optimizer="lshade",
        state=state,
        seeds=[SEED],
        budgets=[DIAGNOSTIC_STOP],
        workers=1,
    )
    cfg["convergence"]["impedance_ohm"] = PORT_IMPEDANCE_OHM
    cfg["stage3_5_arm"]["phase"] = "matched_protocol"
    cfg["stage3_5_arm"]["terminal_budget"] = TERMINAL_HORIZON
    cfg["stage3_5_arm"]["diagnostic_stop"] = DIAGNOSTIC_STOP
    cfg["stage3_5_matched_protocol"] = {
        "terminal_horizon": TERMINAL_HORIZON,
        "diagnostic_stop": DIAGNOSTIC_STOP,
        "requested_checkpoints": list(REQUESTED_CHECKPOINTS),
        "adaptive_exchange_schedule": list(REQUESTED_CHECKPOINTS),
        "forbid_checkpoints": [4000, 8000],
    }
    cfg.setdefault("stage3_3", {})["adaptive_frequency_exchange"] = True
    cfg["stage3_3"]["hard_max_budget"] = TERMINAL_HORIZON
    cfg["stage3_3"]["population_schedule_terminal_budget"] = TERMINAL_HORIZON
    cfg["stage3_3"].setdefault("lshade", {})["hard_max_budget"] = TERMINAL_HORIZON
    cfg["stage3_3"]["lshade"]["population_schedule_terminal_budget"] = TERMINAL_HORIZON
    return cfg


def _protocol_manifest(cfg: Mapping[str, Any], s1_path: Path,
                       historical: Mapping[str, Any]) -> dict[str, Any]:
    lshade = cfg.get("stage3_3", {}).get("lshade", {})
    initial = int(lshade.get("initial_population", lshade.get("initial_population_per_dimension", 18) * 7))
    minimum = int(lshade.get("min_population", 4))
    return {
        "schema_version": 1,
        "experiment": "stage3_5_lshade_matched_protocol_16k",
        "optimizer": "L-SHADE",
        "seed": SEED,
        "search_space": "S1",
        "S1_hash": _sha256(s1_path),
        "port_impedance_ohm": PORT_IMPEDANCE_OHM,
        "terminal_horizon": TERMINAL_HORIZON,
        "diagnostic_stop": DIAGNOSTIC_STOP,
        "requested_checkpoints": list(REQUESTED_CHECKPOINTS),
        "adaptive_exchange_schedule": list(REQUESTED_CHECKPOINTS),
        "forbidden_checkpoints": [4000, 8000],
        "adaptive_frequency_exchange": True,
        "initial_population": initial,
        "minimum_population": minimum,
        "population_schedule_identifier": "lshade_linear_population_v1",
        "population_schedule_version": 1,
        "canonicalization": "existing decode/canonicalization; unchanged",
        "historical_checkpoint_sequence": HISTORICAL_CHECKPOINTS,
        "historical_B16000_semantics": historical.get("B16000_semantics"),
        "historical_overall_semantics": historical.get("overall_historical_semantics"),
        "protocol_change_scope": "orchestration/configuration only",
    }


def _provenance_manifest(config_path: Path, s1_path: Path) -> dict[str, Any]:
    config_path = Path(config_path).resolve()
    s1_path = Path(s1_path).resolve()
    relevant = [
        ROOT / "src" / "sawopt" / "optimizers" / "lshade.py",
        ROOT / "src" / "sawopt" / "studies" / "optimizer_ab.py",
        ROOT / "src" / "sawopt" / "studies" / "matched_protocol_parity.py",
        config_path,
        s1_path,
    ]
    return {
        "schema_version": 1,
        "git_head": _git("rev-parse", "HEAD"),
        "git_status": _git("status", "--short"),
        "source_hash": _source_hash(ROOT / "src" / "sawopt"),
        "historical_source_hash": HISTORICAL_SOURCE_HASH,
        "python_version": sys.version,
        "runtime": platform.platform(),
        "libraries": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "matplotlib", "PyYAML")
        },
        "relevant_source_file_hashes": {
            str(path.relative_to(ROOT)): _sha256(path)
            for path in relevant
            if path.is_file()
        },
        "dirty_worktree_preserved": True,
    }


def _preflight(protocol: Mapping[str, Any], provenance: Mapping[str, Any],
               cfg: Mapping[str, Any], s1_path: Path,
               historical_record: Mapping[str, Any]) -> dict[str, Any]:
    matched = cfg.get("stage3_5_matched_protocol", {})
    checks = {
        "seed": int(cfg.get("seeds", [None])[0]) == SEED,
        "S1": _sha256(s1_path) == EXPECTED_S1_SHA256 and protocol.get("S1_hash") == EXPECTED_S1_SHA256,
        "port_impedance": float(cfg.get("convergence", {}).get("impedance_ohm", -1)) == PORT_IMPEDANCE_OHM,
        "terminal_horizon": int(matched.get("terminal_horizon", -1)) == TERMINAL_HORIZON,
        "diagnostic_stop": int(matched.get("diagnostic_stop", -1)) == DIAGNOSTIC_STOP,
        "requested_checkpoints": matched.get("requested_checkpoints") == REQUESTED_CHECKPOINTS,
        "exchange_schedule": matched.get("adaptive_exchange_schedule") == REQUESTED_CHECKPOINTS,
        "4k_exchange_disabled": 4000 not in matched.get("adaptive_exchange_schedule", []),
        "8k_exchange_disabled": 8000 not in matched.get("adaptive_exchange_schedule", []),
        "16k_exchange_enabled": 16000 in matched.get("adaptive_exchange_schedule", []),
        "historical_record_present": HISTORICAL_RECORD.is_file(),
        "historical_B16000_pre_exchange": historical_record.get("B16000_semantics") == "PRE_EXCHANGE",
        "historical_terminal_horizon": historical_record.get("terminal_horizon") == TERMINAL_HORIZON,
        "historical_hard_max_budget": historical_record.get("hard_max_budget") == TERMINAL_HORIZON,
        "source_hash_recorded": bool(provenance.get("source_hash")),
        "dirty_worktree_recorded": provenance.get("dirty_worktree_preserved") is True,
    }
    passed = all(checks.values())
    result = {
        "status": "PASS" if passed else "BLOCKED",
        "checks": checks,
        "optimization_started": False,
        "source_change_scope": "orchestration/configuration only",
    }
    if not passed:
        raise RuntimeError("matched-protocol preflight failed: " + ", ".join(
            name for name, value in checks.items() if not value
        ))
    return result


def _trace_compare(current: list[Any], historical: list[Any]) -> dict[str, Any]:
    if current == historical:
        return {"exact_match": True, "first_difference": None, "current_count": len(current), "historical_count": len(historical)}
    limit = min(len(current), len(historical))
    index = next((i for i in range(limit) if current[i] != historical[i]), limit)
    current_item = current[index] if index < len(current) else None
    historical_item = historical[index] if index < len(historical) else None
    return {
        "exact_match": False,
        "first_difference": {
            "index": index,
            "unique_evaluation": (current_item or historical_item or {}).get("unique_evaluation"),
            "current": current_item,
            "historical": historical_item,
        },
        "current_count": len(current),
        "historical_count": len(historical),
    }


def _pre_exchange_trace(values: list[Any]) -> list[Any]:
    """Remove the post-exchange duplicate observation at the stop budget."""
    return [
        item for item in values
        if int(item.get("frequency_grid_version", 1)) == 1
    ]


def _endpoint_row(record: Mapping[str, Any], cfg: Mapping[str, Any], grid: np.ndarray) -> dict[str, Any]:
    design = FilterDesign(**dict(record["design"]))
    _freq, (validated, _net, _sim) = dense(
        design, cfg, PORT_IMPEDANCE_OHM, PORT_IMPEDANCE_OHM,
        wiring="center_outer_same", base_grid=grid, passes=0, validation=True,
    )
    validated = dict(validated)
    return {
        "design": clean(dict(record["design"])),
        "validated_rank": [float(value) for value in rank(validated)],
        "max_violation": float(validated.get("max_violation", np.inf)),
        "sum_violation": float(sum(validated.get("violations", {}).values())),
        "worst_il_db": float(validated.get("metrics", {}).get("worst_il_db", np.inf)),
        "feasible": bool(validated.get("feasible", False)),
    }


def _endpoint_compare(current: Mapping[str, Any], historical: Mapping[str, Any],
                     cfg: Mapping[str, Any], grid: np.ndarray) -> dict[str, Any]:
    current_pre = current.get("pre_exchange_snapshot")
    if not isinstance(current_pre, Mapping) or not current_pre.get("design"):
        return {"comparable": False, "reason": "current pre-exchange snapshot is missing"}
    current_row = _endpoint_row(current_pre, cfg, grid)
    historical_row = _endpoint_row(historical, cfg, grid)
    fields = {
        "decoded_best_candidate": current_row["design"] == historical_row["design"],
        "validated_rank_tuple": current_row["validated_rank"] == historical_row["validated_rank"],
        "common_validation_metrics": all(
            current_row[key] == historical_row[key]
            for key in ("max_violation", "sum_violation", "worst_il_db")
        ),
        "population_size": current.get("population_size") == historical.get("population_size"),
        "unique_decoded_evaluations": current.get("unique_decoded_evaluations") == historical.get("unique_decoded_evaluations"),
        "pre_exchange_grid_version": current.get("pre_exchange_grid_version") == 1
        and int(historical.get("population_trace", [{}])[-1].get("frequency_grid_version", -1)) == 1,
    }
    return {
        "comparable": True,
        "exact_match": all(fields.values()),
        "fields": fields,
        "current": current_row,
        "historical": historical_row,
    }


def _protocol_compare(current: Mapping[str, Any], historical: Mapping[str, Any]) -> dict[str, Any]:
    current_events = list(current.get("frequency_grid_events", []))
    historical_events = list(historical.get("frequency_grid_events", []))
    current_trace = _pre_exchange_trace(list(current.get("population_trace", [])))
    current_archive = _pre_exchange_trace(list(current.get("archive_trace", [])))
    current_event = current_events[0] if current_events else {}
    historical_event = historical_events[0] if historical_events else {}
    current_version_after = current_event.get(
        "frequency_grid_version_after", current_event.get("frequency_grid_version")
    )
    historical_version_after = historical_event.get(
        "frequency_grid_version_after", historical_event.get("frequency_grid_version")
    )
    checks = {
        "seed": current.get("seed") == historical.get("seed") == SEED,
        "terminal_horizon": current.get("population_schedule_terminal_budget") == historical.get("population_schedule_terminal_budget") == TERMINAL_HORIZON,
        "hard_max_budget": current.get("hard_max_budget") == historical.get("hard_max_budget") == TERMINAL_HORIZON,
        "diagnostic_stop": current.get("unique_decoded_evaluations") == historical.get("unique_decoded_evaluations") == DIAGNOSTIC_STOP,
        "single_exchange_event": len(current_events) == len(historical_events) == 1,
        "exchange_version": bool(current_events and historical_events) and current_version_after == historical_version_after == 2,
        "pre_exchange_population_grid": bool(current_trace) and current_trace[-1].get("frequency_grid_version") == 1,
        "pre_exchange_archive_grid": bool(current_archive) and current_archive[-1].get("frequency_grid_version") == 1,
    }
    event_exact = bool(current_events and historical_events) and all(
        current_event.get(key) == historical_event.get(key)
        for key in ("event", "added_count", "unique_designs_charged", "frequencies_hz")
    ) and current_version_after == historical_version_after
    return {
        "exact_match": all(checks.values()) and event_exact,
        "fields": checks,
        "event_exact_match": event_exact,
        "current_event": current_events[0] if current_events else None,
        "historical_event": historical_events[0] if historical_events else None,
    }


def _first_divergence_report(run: Path, trajectory: Mapping[str, Any],
                             protocol: Mapping[str, Any], endpoint: Mapping[str, Any]) -> None:
    lines = [
        "# First Divergence Trace",
        "",
        "This report is evidence-only. No optimizer change was made.",
        "",
        f"- protocol comparison exact: `{protocol.get('exact_match')}`",
        f"- endpoint comparison exact: `{endpoint.get('exact_match')}`",
    ]
    for name in ("population_trace", "archive_trace", "best_so_far_trace"):
        item = trajectory.get(name, {})
        lines.append(f"- {name}: `{item.get('exact_match')}`; first difference: `{item.get('first_difference')}`")
    lines.append("")
    (run / "reports" / "first_divergence_trace.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _review_text(run: Path, summary: Mapping[str, Any]) -> None:
    report = run / "reports" / "stage3_5_matched_protocol_review.md"
    lines = [
        "# Stage 3.5 Matched-Protocol Parity Review",
        "",
        "## 1. Executive Summary",
        "",
        f"- Status: `{summary['status']}`",
        "- Scope: one L-SHADE S1/50-ohm diagnostic run stopped at 16k.",
        "- Phase D: not started.",
        "",
        "## 2. Historical Protocol Reconstruction",
        "",
        f"- B16000 semantics: `{summary['historical_checkpoint_protocol']['B16000_semantics']}`.",
        "- Broader historical semantics remain `UNKNOWN`; the post-checkpoint event ordering is an evidence-based inference.",
        "",
        "## 3. Current Protocol",
        "",
        "- Requested checkpoints: `[16000]`; 4k/8k exchanges were not requested.",
        "- Terminal population-schedule horizon: `64000`; diagnostic stop: `16000`.",
        "",
        "## 4. Provenance Comparison",
        "",
        f"- Historical source hash: `{summary['provenance']['historical_source_hash']}`.",
        f"- Current source hash: `{summary['provenance']['source_hash']}`.",
        f"- Git status was preserved: `{summary['provenance']['dirty_worktree_preserved']}`.",
        "",
        "## 5. Preflight Verification",
        "",
        f"- Preflight: `{summary['preflight']['status']}`.",
        "",
        "## 6. Run Configuration",
        "",
        "- Optimizer: L-SHADE; seed: 20260917; search space: S1; Zport: 50 ohm.",
        "",
        "## 7. Protocol Parity",
        "",
        f"- Exact protocol parity: `{summary['protocol_parity']['exact_match']}`.",
        "",
        "## 8. Trajectory Parity",
        "",
        f"- Exact trajectory parity through the pre-exchange 16k snapshot: `{summary['trajectory_parity']['exact_match']}`.",
        "",
        "## 9. Endpoint Parity",
        "",
        f"- Endpoint comparable: `{summary['endpoint_parity'].get('comparable')}`; exact: `{summary['endpoint_parity'].get('exact_match')}`.",
        "",
        "## 10. Telemetry Differences",
        "",
        json.dumps(summary.get("telemetry_differences", {}), ensure_ascii=False, indent=2),
        "",
        "## 11. First Divergence",
        "",
        (
            "No pre-exchange divergence was found; a first-divergence trace is not "
            "generated for a parity PASS."
            if summary["status"] == "PARITY_PASS_MATCHED_PROTOCOL"
            else "See `first_divergence_trace.md` for the evidence-only divergence trace."
        ),
        "",
        "## 12. Root-Cause Assessment",
        "",
        f"- Leading root cause: `{summary['leading_root_cause']}`.",
        f"- Source change justified: `{summary['source_change_justified']}`.",
        "",
        "## 13. Sol Escalations",
        "",
        "The matched-protocol configuration gate was reviewed before the run; any parity failure requires a new Sol review.",
        "",
        "## 14. Stage 3.5 Recommendation",
        "",
        f"- `{summary['next_action']}`",
        "",
        "## 15. Phase D Readiness",
        "",
        f"- `{summary['phase_d_readiness']}`; Phase D must not start automatically.",
    ]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_bundle(run: Path) -> Path:
    output = ROOT / "artifacts" / "review_bundles" / "stage3_5_lshade_matched_protocol_16k_review.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as bundle:
        for path in sorted(run.rglob("*")):
            if (not path.is_file() or is_checkpoint_artifact(path.relative_to(run))
                    or "__pycache__" in path.parts):
                continue
            bundle.write(path, path.relative_to(run).as_posix())
    return output


def run_matched_protocol_parity(config_path: str | Path, run: str | Path,
                                *, resume: bool = False) -> dict[str, Any]:
    config_path = Path(config_path).resolve()
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=True)
    (run / "manifests").mkdir(exist_ok=True)
    (run / "results").mkdir(exist_ok=True)
    (run / "reports").mkdir(exist_ok=True)
    base = normalize_convergence_config(load_experiment_config(config_path))
    stage = base.get("stage3_5", {})
    if [int(value) for value in stage.get("seeds", [SEED])] != [SEED]:
        raise ValueError("matched-protocol run requires exactly seed 20260917")
    s1_path = Path(stage.get("s1_path", "artifacts/stage3_5/phase_a_revised/search_space_s1.yaml"))
    if not s1_path.is_absolute():
        s1_path = ROOT / s1_path
    if not s1_path.is_file() or not HISTORICAL_RECORD.is_file():
        raise FileNotFoundError("matched-protocol historical or S1 artifact is missing")
    s1 = yaml.safe_load(s1_path.read_text(encoding="utf-8")) or {}
    historical = _json(HISTORICAL_RECORD)
    historical_protocol = _historical_protocol(historical)
    cfg = build_matched_protocol_config(base, s1)
    protocol = _protocol_manifest(cfg, s1_path, historical_protocol)
    provenance = _provenance_manifest(config_path, s1_path)
    save(run / "manifests" / "protocol_manifest.json", protocol)
    save(run / "manifests" / "provenance_manifest.json", provenance)
    save(run / "results" / "historical_protocol_reconstruction.json", historical_protocol)
    preflight = _preflight(protocol, provenance, cfg, s1_path, historical_protocol)
    save(run / "results" / "preflight.json", preflight)
    if not resume and (run / "results" / "current_record.json").exists():
        raise RuntimeError("matched-protocol run already has a result; use --resume or a new run directory")

    started = time.monotonic()
    tasks = [(str(run / "diagnostics" / "matched_protocol_lshade"), cfg,
              "center_outer_same", SEED, list(REQUESTED_CHECKPOINTS), bool(resume))]
    returned = run_workers(tasks, lshade_trajectory_worker, 1, 1)
    records = [record for group in returned for record in (group if isinstance(group, list) else [group])]
    if len(records) != 1:
        raise RuntimeError(f"expected one matched-protocol record, got {len(records)}")
    current = records[0]
    save(run / "results" / "current_record.json", current)
    save(run / "results" / "historical_record_summary.json", {
        "path": str(HISTORICAL_RECORD),
        "seed": historical.get("seed"),
        "design": clean(dict(historical.get("design", {}))),
        "unique_decoded_evaluations": historical.get("unique_decoded_evaluations"),
        "population_size": historical.get("population_size"),
    })
    trajectory = {
        name: _trace_compare(
            _pre_exchange_trace(list(current.get(name, []))),
            list(historical.get(name, [])),
        )
        for name in ("population_trace", "archive_trace", "best_so_far_trace")
    }
    trajectory["exact_match"] = all(item["exact_match"] for item in trajectory.values())
    protocol_parity = _protocol_compare(current, historical)
    grid_path = ROOT / "runs" / "stage3_5_phase_c_revised" / "common_validation_grid_hz.csv"
    with grid_path.open(encoding="utf-8-sig", newline="") as stream:
        import csv
        grid = np.asarray([float(row["frequency_hz"]) for row in csv.DictReader(stream)], dtype=float)
    endpoint = _endpoint_compare(current, historical, base, grid)
    save(run / "results" / "trajectory_comparison.json", trajectory)
    save(run / "results" / "endpoint_comparison.json", endpoint)
    exchange_exact = protocol_parity.get("event_exact_match", False)
    if not trajectory["exact_match"]:
        status = "PARITY_FAIL_PRE16K"
        readiness = "NEEDS_ROOT_CAUSE_REVIEW"
        root_cause = "RC6_UNRESOLVED_MATCHED_PROTOCOL_DIVERGENCE"
    elif not exchange_exact or not protocol_parity["exact_match"]:
        status = "PARITY_FAIL_AT_EXCHANGE"
        readiness = "NEEDS_ROOT_CAUSE_REVIEW"
        root_cause = "RC6_EXCHANGE_SEMANTICS_OR_PROVENANCE"
    elif not endpoint.get("comparable"):
        status = "TRAJECTORY_PASS_ENDPOINT_INCONCLUSIVE"
        readiness = "READY_FOR_CHAT_SOL_REVIEW"
        root_cause = "RC6_PROTOCOL_MISMATCH_REDUCED_ENDPOINT_PROVENANCE_INCOMPLETE"
    elif not endpoint.get("exact_match"):
        status = "PARITY_FAIL_AT_EXCHANGE"
        readiness = "NEEDS_ROOT_CAUSE_REVIEW"
        root_cause = "RC6_ENDPOINT_OR_SOURCE_LINEAGE_DIVERGENCE"
    else:
        status = "PARITY_PASS_MATCHED_PROTOCOL"
        readiness = "READY_FOR_CHAT_SOL_REVIEW"
        root_cause = "RC6_PROTOCOL_MISMATCH_SUPPORTED"
    telemetry = {
        key: {"current": current.get(key), "historical": historical.get(key)}
        for key in ("objective_calls", "cache_hits", "cache_hit_rate", "duplicate_decoded_attempts", "elapsed_s")
    }
    summary = {
        "status": status,
        "historical_record": str(HISTORICAL_RECORD),
        "current_record": str(run / "results" / "current_record.json"),
        "seed": SEED,
        "S1_hash": protocol["S1_hash"],
        "historical_source_hash": HISTORICAL_SOURCE_HASH,
        "current_source_hash": provenance["source_hash"],
        "terminal_horizon": TERMINAL_HORIZON,
        "diagnostic_stop": DIAGNOSTIC_STOP,
        "historical_checkpoint_protocol": historical_protocol,
        "current_checkpoint_protocol": protocol,
        "exchange_events": {"current": current.get("frequency_grid_events", []), "historical": historical.get("frequency_grid_events", [])},
        "pre_exchange_parity": trajectory,
        "trajectory_parity": trajectory,
        "endpoint_parity": endpoint,
        "protocol_parity": protocol_parity,
        "telemetry_differences": telemetry,
        "leading_root_cause": root_cause,
        "source_change_justified": False,
        "next_action": "STOP_FOR_CHATGPT_SOL_REVIEW",
        "phase_d_readiness": readiness,
        "preflight": preflight,
        "provenance": provenance,
        "runtime_wall_time_s": time.monotonic() - started,
    }
    save(run / "results" / "matched_protocol_parity.json", summary)
    if status in {"PARITY_FAIL_PRE16K", "PARITY_FAIL_AT_EXCHANGE"}:
        _first_divergence_report(run, trajectory, protocol_parity, endpoint)
    else:
        # A prior failed finalization may have left a stale divergence report
        # behind.  A PASS must not retain an artifact that claims divergence.
        (run / "reports" / "first_divergence_trace.md").unlink(missing_ok=True)
    _review_text(run, summary)
    bundle = _write_bundle(run)
    summary["review_bundle"] = str(bundle)
    save(run / "results" / "matched_protocol_parity.json", summary)
    (run / "STOP_FOR_CHATGPT_SOL_REVIEW.txt").write_text(
        "STOP_FOR_CHATGPT_SOL_REVIEW\n", encoding="utf-8"
    )
    return summary


__all__ = ["build_matched_protocol_config", "run_matched_protocol_parity"]
