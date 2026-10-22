"""Build read-only source-compatibility evidence for the repaired Stage 3.9B protocol."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from sawopt.io.config import load_experiment_config
from sawopt.design.topology import T1
from sawopt.studies import dms_topology_screening as study
from sawopt.studies.audits.stage3_9b_overlap_parity import (
    CHECKPOINTS,
    MATERIAL,
    SEEDS,
    TOPOLOGY,
    _config_protocol,
    compare_values,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs/studies/stage3_9b_mlit_t1_50ohm_overlap_parity.yaml"
DEFAULT_EXTENSION_CONFIG = ROOT / "configs/studies/stage3_9b_mlit_t1_50ohm_budget_extension.yaml"
DEFAULT_CANONICAL_RUN = ROOT / "runs/stage3_8c_production_20260924"
DEFAULT_OUTPUT = ROOT / "artifacts/review_bundles/stage3_9b_source_compatibility"
SOURCE_FILES = (
    "src/sawopt/studies/dms_topology_screening.py",
    "src/sawopt/studies/dms_topology_common.py",
    "src/sawopt/studies/audits/stage3_9b_overlap_parity.py",
    "src/sawopt/optimization/selection.py",
    "src/sawopt/optimization/lshade.py",
    "src/sawopt/design/topology.py",
    "src/sawopt/design/space.py",
    "src/sawopt/design/geometry.py",
    "src/sawopt/evaluation.py",
    "src/sawopt/physics/network.py",
    "configs/studies/stage3_9b_mlit_t1_50ohm_overlap_parity.yaml",
    "configs/studies/stage3_9b_mlit_t1_50ohm_budget_extension.yaml",
)
HISTORICAL_SOURCE_REF = "1282699^:src/sawopt/studies/stage3_8c_r1_geometry_gate.py"
REQUIRED_EVALUATOR_FIELDS = (
    "evaluation_status", "geometry_valid", "geometry_violations", "metrics",
    "violations", "feasible", "max_violation", "sum_violation", "design",
)
SAMPLING_COMPARISON_FIELDS = (
    "initial_sampling_seed", "initial_sampling_draws", "initial_sampling_geometry_rejections",
    "initial_sampling_duplicate_rejections", "initial_sampling_rejection_reason_counts",
    "fixed_seed_count", "random_initial_accepts", "unique_population_count",
    "variable_distributions", "geometry_metric_distributions",
    "random_member_variable_distributions", "random_member_geometry_metric_distributions",
)
def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace",
        capture_output=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _tracked_source_comparison(canonical_head: str | None) -> dict[str, Any]:
    comparisons = {}
    source_paths = {
        "src/sawopt/optimization/lshade.py": "src/sawopt/optimizers/lshade.py",
        "src/sawopt/optimization/selection.py": "src/sawopt/optimizers/selection.py",
    }
    for relative, historical_relative in source_paths.items():
        canonical_blob = (
            _git_output("rev-parse", f"{canonical_head}:{historical_relative}")
            if canonical_head else ""
        )
        current_clean_blob = _git_output("hash-object", f"--path={relative}", relative)
        current_path = ROOT / relative
        comparisons[relative] = {
            "canonical_recorded_source_path": historical_relative,
            "canonical_recorded_head_blob_sha": canonical_blob or None,
            "current_worktree_clean_blob_sha": current_clean_blob or None,
            "current_worktree_raw_sha256": _sha256_file(current_path),
            "identical_to_canonical_recorded_head": (
                canonical_blob == current_clean_blob if canonical_blob and current_clean_blob else None
            ),
        }
    return comparisons


def _category(passed: bool, **details: Any) -> dict[str, Any]:
    return {"status": "PASS" if passed else "FAIL", **details}


def _load_checkpoint(canonical_run: Path, seed: int) -> tuple[dict[str, Any], dict[str, Any], Path]:
    seed_dir = canonical_run / "optimization" / MATERIAL / TOPOLOGY / f"seed{seed}"
    checkpoint_path = seed_dir / "optimizer_checkpoint.json"
    trajectory_path = seed_dir / "trajectory_metadata.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
    return checkpoint, trajectory, seed_dir


def _replay_population(cfg: Mapping[str, Any], seed: int, canonical_keys: list[list[float]]) -> dict[str, Any]:
    active, _hard, integer_indices = study.material_bounds(cfg, MATERIAL, TOPOLOGY)
    population, sampling = study.sample_independent_uniform_population(
        cfg, MATERIAL, TOPOLOGY, seed=seed, population_size=180, max_attempts=10_800,
        reference_proposals=0, bootstrap_replicates=0,
    )
    physical = [
        study._canonical_physical(
            active[:, 0] + np.asarray(normalized, dtype=float) * (active[:, 1] - active[:, 0]),
            active, integer_indices,
        ).tolist()
        for normalized in population
    ]
    mismatches = [
        index for index, (expected, actual) in enumerate(zip(canonical_keys, physical))
        if list(expected) != list(actual)
    ]
    return {
        "seed": seed,
        "canonical_initial_cache_entries": len(canonical_keys),
        "replayed_population_entries": len(physical),
        "exact_ordered_match_count": len(physical) - len(mismatches),
        "first_divergence_index_zero_based": mismatches[0] if mismatches else None,
        "initializer_sampling": sampling,
        "canonical_keys": canonical_keys,
        "replayed_keys": physical,
    }


def _compare_sampling(canonical: Mapping[str, Any], replay: Mapping[str, Any]) -> list[str]:
    return [
        field for field in SAMPLING_COMPARISON_FIELDS
        if canonical.get(field) != replay.get(field)
    ]


def _comparator_trace_check(checkpoints: Mapping[int, Mapping[str, Any]]) -> dict[str, Any]:
    seed_results = {}
    for seed, checkpoint in checkpoints.items():
        cache = checkpoint.get("cache", [])
        stored_trace = checkpoint.get("best_so_far_trace", [])
        if len(cache) < 180:
            seed_results[str(seed)] = {"status": "FAIL", "reason": "canonical cache is shorter than the initial population"}
            continue
        records = [entry[1] for entry in cache if isinstance(entry, list) and len(entry) == 2]
        if len(records) != len(cache):
            seed_results[str(seed)] = {"status": "FAIL", "reason": "malformed canonical cache entries"}
            continue
        replayed = []
        initial_best = min(records[:180], key=study.GEOMETRY_FIRST_COMPARATOR.rank_key)
        best_key = study.GEOMETRY_FIRST_COMPARATOR.rank_key(initial_best)
        replayed.append({"unique_evaluation": 180, "rank_key": list(best_key)})
        for index, record in enumerate(records[180:], start=181):
            rank_key = study.GEOMETRY_FIRST_COMPARATOR.rank_key(record)
            if rank_key < best_key:
                best_key = rank_key
                replayed.append({"unique_evaluation": index, "rank_key": list(rank_key)})
        persisted = [
            {"unique_evaluation": event.get("unique_evaluation"), "rank_key": event.get("rank_key")}
            for event in stored_trace
        ]
        differences = compare_values(persisted, replayed, f"seed{seed}.best_so_far_trace")
        seed_results[str(seed)] = {
            "status": "PASS" if not differences else "FAIL",
            "persisted_trace_events": len(persisted),
            "replayed_trace_events": len(replayed),
            "differences": differences[:20],
        }
    return {
        "status": "PASS" if all(row["status"] == "PASS" for row in seed_results.values()) else "FAIL",
        "seeds": seed_results,
    }


def _decode_check(cfg: Mapping[str, Any], replay_rows: Mapping[int, Mapping[str, Any]]) -> dict[str, Any]:
    active, _hard, integer_indices = study.material_bounds(cfg, MATERIAL, TOPOLOGY)
    results = {}
    for seed, row in replay_rows.items():
        mismatches = []
        for index, vector in enumerate(row["canonical_keys"]):
            decoded = study.decode_design(vector, TOPOLOGY, cfg)
            reconstructed = study._design_vector(decoded, TOPOLOGY)
            canonical = study._canonical_physical(reconstructed, active, integer_indices)
            if not np.array_equal(canonical, np.asarray(vector, dtype=float)):
                mismatches.append(index)
        results[str(seed)] = {
            "status": "PASS" if not mismatches else "FAIL",
            "vectors_checked": len(row["canonical_keys"]),
            "exact_round_trip_count": len(row["canonical_keys"]) - len(mismatches),
            "first_divergence_index_zero_based": mismatches[0] if mismatches else None,
        }
    return {
        "status": "PASS" if all(row["status"] == "PASS" for row in results.values()) else "FAIL",
        "seeds": results,
    }


def _optimizer_config_check(
    cfg: Mapping[str, Any], checkpoints: Mapping[int, Mapping[str, Any]], canonical_run: Path,
    tracked_source_comparison: Mapping[str, Any], comparator_check: Mapping[str, Any],
) -> dict[str, Any]:
    active, hard, integer_indices = study.material_bounds(cfg, MATERIAL, TOPOLOGY)
    resolved = study._backend_config(cfg, TOPOLOGY, 8000, hard)
    snapshots = json.loads(
        (canonical_run / "metadata/resolved_search_space_snapshots.json").read_text(encoding="utf-8")
    )
    canonical_search_space = snapshots[MATERIAL][TOPOLOGY]
    current_search_space = {
        "active_search_bounds": active.tolist(),
        "optimizer_hard_bounds": hard.tolist(),
        "integer_indices": list(integer_indices),
    }
    search_space_differences = compare_values(
        {key: canonical_search_space.get(key) for key in current_search_space},
        current_search_space,
        "canonical_search_space",
    )
    effective_initial_population = max(
        int(resolved["initial_population"]), int(resolved.get("min_population", 4)),
    )
    effective_minimum_population = int(resolved.get("min_population", 4))
    configured_memory_batch = int(resolved.get("memory_update_batch_size", 0))
    effective_memory_batch = configured_memory_batch or effective_initial_population
    effective_history_size = int(resolved.get("history_size", 6))
    selection_source = tracked_source_comparison.get("src/sawopt/optimization/selection.py", {})
    selection_same = selection_source.get("identical_to_canonical_recorded_head") is True
    comparator_replay_pass = comparator_check.get("status") == "PASS"
    seed_results = {}
    for seed, checkpoint in checkpoints.items():
        differences = {}
        persisted_expectations = {
            "initial_population_size": effective_initial_population,
            "minimum_population_size": effective_minimum_population,
            "total_budget": int(resolved["total_budget"]),
            "hard_max_budget": int(resolved["hard_max_budget"]),
            "population_schedule_terminal_budget": int(resolved["population_schedule_terminal_budget"]),
            "memory_update_batch_size": effective_memory_batch,
        }
        for persisted, expected in persisted_expectations.items():
            if checkpoint.get(persisted) != expected:
                differences[persisted] = {
                    "resolved_effective_value": expected,
                    "canonical_checkpoint": checkpoint.get(persisted),
                }
        if len(checkpoint.get("m_f", [])) != effective_history_size:
            differences["history_size/m_f"] = {
                "resolved_effective_value": effective_history_size,
                "canonical_checkpoint": len(checkpoint.get("m_f", [])),
            }
        if len(checkpoint.get("m_cr", [])) != effective_history_size:
            differences["history_size/m_cr"] = {
                "resolved_effective_value": effective_history_size,
                "canonical_checkpoint": len(checkpoint.get("m_cr", [])),
            }
        seed_results[str(seed)] = {"status": "PASS" if not differences else "FAIL", "differences": differences}
    lshade_source = tracked_source_comparison.get("src/sawopt/optimization/lshade.py", {})
    source_differences_explained = (
        lshade_source.get("identical_to_canonical_recorded_head") is True
        and (selection_same or comparator_replay_pass)
    )
    return {
        "status": "PASS" if (
            not search_space_differences
            and all(row["status"] == "PASS" for row in seed_results.values())
            and source_differences_explained
        ) else "FAIL",
        "resolved_backend_config": resolved,
        "effective_persisted_controls": {
            "initial_population_size": effective_initial_population,
            "minimum_population_size": effective_minimum_population,
            "total_budget": int(resolved["total_budget"]),
            "hard_max_budget": int(resolved["hard_max_budget"]),
            "population_schedule_terminal_budget": int(resolved["population_schedule_terminal_budget"]),
            "memory_update_batch_size": effective_memory_batch,
            "memory_update_batch_semantics": (
                "LShadeBackend.initialize sets a zero configured batch size to the initialized population size"
            ),
            "history_size": effective_history_size,
            "archive_size_at_canonical_8k": {
                str(seed): len(checkpoint.get("archive", []))
                for seed, checkpoint in checkpoints.items()
            },
            "archive_contents_replayed": False,
        },
        "canonical_vs_current_search_space_differences": search_space_differences,
        "tracked_optimizer_and_comparator_sources": tracked_source_comparison,
        "selection_source_behavioral_explanation": {
            "source_identical_to_canonical_head": selection_same,
            "persisted_best_so_far_trace_replay_status": comparator_check.get("status"),
            "explains_source_difference": selection_same or comparator_replay_pass,
        },
        "tracked_source_differences_explained": source_differences_explained,
        "seeds": seed_results,
    }


def _checkpoint_schedule_check(
    cfg: Mapping[str, Any], trajectories: Mapping[int, Mapping[str, Any]],
    seed_dirs: Mapping[int, Path], expected_search_count: int,
) -> dict[str, Any]:
    configured = [int(value) for value in cfg["dms_topology"]["checkpoints"]]
    canonical_results = {}
    for seed, trajectory in trajectories.items():
        persisted = [int(value) for value in trajectory.get("checkpoints", [])]
        events = trajectory.get("frequency_grid_events", [])
        event_budgets = [int(event.get("checkpoint_budget", -1)) for event in events]
        event_counts = [int(event.get("frequency_grid_count", -1)) for event in events]
        record_budgets = []
        for budget in configured:
            path = seed_dirs[seed] / f"B{budget}.json"
            record = json.loads(path.read_text(encoding="utf-8"))
            record_budgets.append(int(record.get("checkpoint_budget", -1)))
        passed = (
            configured == list(CHECKPOINTS)
            and persisted == configured
            and event_budgets == configured
            and record_budgets == configured
            and all(count == expected_search_count for count in event_counts)
        )
        canonical_results[str(seed)] = {
            "status": "PASS" if passed else "FAIL",
            "configured_checkpoints": configured,
            "canonical_metadata_checkpoints": persisted,
            "canonical_frequency_event_checkpoints": event_budgets,
            "canonical_frequency_event_counts": event_counts,
            "canonical_record_checkpoints": record_budgets,
        }
    return {
        "status": "PASS" if all(row["status"] == "PASS" for row in canonical_results.values()) else "FAIL",
        "seeds": canonical_results,
        "current_checkpoint_scheduler_source_sha256": _sha256_file(
            ROOT / "src/sawopt/studies/dms_topology_screening.py"
        ),
        "scheduler_behavior_evidence": "resolved config lattice compared with persisted checkpoint records and frequency-grid events",
    }


def build_evidence(config_path: Path, extension_config_path: Path, canonical_run: Path, output_dir: Path) -> dict[str, Any]:
    review_root = (ROOT / "artifacts/review_bundles").resolve()
    output_dir = output_dir.resolve()
    try:
        output_dir.relative_to(review_root)
    except ValueError as exc:
        raise ValueError("compatibility evidence must be written under artifacts/review_bundles/") from exc
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output_dir}")

    cfg = load_experiment_config(config_path)
    extension_cfg = load_experiment_config(extension_config_path)
    protocol = _config_protocol(cfg)
    extension_contract = study.resolve_initial_population_seed_contract(extension_cfg)
    contract_ok = (
        extension_contract.identifier == protocol["initial_population_seed_contract"]["identifier"]
        == study.STAGE3_8C_R1_2_INITIAL_POPULATION_SEED_CONTRACT
    )

    canonical_root = json.loads((canonical_run / "metadata/run_source_metadata.json").read_text(encoding="utf-8"))
    canonical_head = canonical_root.get("git", {}).get("head")
    historical_source_at_head = bool(canonical_head and _git_output(
        "ls-tree", canonical_head, "src/sawopt/studies/stage3_8c_r1_geometry_gate.py",
    ))
    historical_blob_sha = _git_output("rev-parse", HISTORICAL_SOURCE_REF)

    tracked_source_comparison = _tracked_source_comparison(canonical_head)
    source_hashes = {
        "canonical_recorded_git_head": canonical_head,
        "canonical_head_contains_stage3_8c_runtime_source_path": historical_source_at_head,
        "retained_historical_source_reference": HISTORICAL_SOURCE_REF,
        "retained_historical_source_git_blob": historical_blob_sha or None,
        "current_source_files": {
            relative: _sha256_file(ROOT / relative) for relative in SOURCE_FILES
        },
        "tracked_optimizer_comparator_source_comparison": tracked_source_comparison,
    }

    checkpoints: dict[int, dict[str, Any]] = {}
    trajectories: dict[int, dict[str, Any]] = {}
    seed_dirs: dict[int, Path] = {}
    replay_rows: dict[int, dict[str, Any]] = {}
    replay_summary = {}
    evaluator_counts = {}
    for seed in SEEDS:
        checkpoint, trajectory, seed_dir = _load_checkpoint(canonical_run, seed)
        checkpoints[seed], trajectories[seed], seed_dirs[seed] = checkpoint, trajectory, seed_dir
        cache = checkpoint.get("cache", [])
        canonical_keys = [entry[0] for entry in cache[:180] if isinstance(entry, list) and len(entry) == 2]
        replay = _replay_population(cfg, seed, canonical_keys)
        replay_rows[seed] = replay
        canonical_sampling = trajectory.get("initial_population_sampling", {})
        stats_differences = _compare_sampling(canonical_sampling, replay["initializer_sampling"])
        population_pass = (
            replay["canonical_initial_cache_entries"] == 180
            and replay["replayed_population_entries"] == 180
            and replay["exact_ordered_match_count"] == 180
            and not stats_differences
        )
        replay_summary[str(seed)] = {
            "status": "PASS" if population_pass else "FAIL",
            "canonical_initial_cache_entries": replay["canonical_initial_cache_entries"],
            "replayed_population_entries": replay["replayed_population_entries"],
            "exact_ordered_match_count": replay["exact_ordered_match_count"],
            "first_divergence_index_zero_based": replay["first_divergence_index_zero_based"],
            "canonical_rng_seed": canonical_sampling.get("initial_sampling_seed"),
            "replayed_rng_seed": replay["initializer_sampling"].get("initial_sampling_seed"),
            "canonical_draws": canonical_sampling.get("initial_sampling_draws"),
            "replayed_draws": replay["initializer_sampling"].get("initial_sampling_draws"),
            "canonical_geometry_rejections": canonical_sampling.get("initial_sampling_geometry_rejections"),
            "replayed_geometry_rejections": replay["initializer_sampling"].get("initial_sampling_geometry_rejections"),
            "sampling_accounting_fields_differing": stats_differences,
        }

        records = [entry[1] for entry in cache if isinstance(entry, list) and len(entry) == 2]
        missing_fields = {
            field: sum(1 for record in records if field not in record)
            for field in REQUIRED_EVALUATOR_FIELDS
        }
        evaluator_counts[str(seed)] = {
            "cache_records": len(records),
            "required_fields_missing_counts": missing_fields,
            "all_records_rankable": all(
                not missing_fields[field] for field in REQUIRED_EVALUATOR_FIELDS
            ) and len(records) == 8000,
        }
    trace_check = _comparator_trace_check(checkpoints)
    evaluator_ok = all(row["all_records_rankable"] for row in evaluator_counts.values())
    replay_ok = all(row["status"] == "PASS" for row in replay_summary.values())
    decode_check = _decode_check(cfg, replay_rows)
    optimizer_detail = _optimizer_config_check(
        cfg, checkpoints, canonical_run, tracked_source_comparison, trace_check,
    )
    schedule_detail = _checkpoint_schedule_check(
        cfg, trajectories, seed_dirs, int(protocol["search_grid_count"]),
    )
    compatibility = {
        "initializer_seed_replay": {
            "status": "PASS" if replay_ok else "FAIL",
            "seeds": replay_summary,
            "physics_or_optimizer_executed": False,
        },
        "comparator_ordering": trace_check,
        "evaluator_payload_and_ranking": {
            "status": "PASS" if evaluator_ok and trace_check["status"] == "PASS" else "FAIL",
            "seeds": evaluator_counts,
            "ranking_trace_replay": trace_check,
        },
        "design_decoding_and_canonicalization": decode_check,
        "optimizer_configuration": optimizer_detail,
        "checkpoint_scheduling": schedule_detail,
        "historical_source_provenance": {
            "status": "PASS_WITH_CAVEAT" if historical_blob_sha else "FAIL",
            "canonical_recorded_git_head": canonical_head,
            "canonical_head_contains_runtime_source_path": historical_source_at_head,
            "retained_source_ref": HISTORICAL_SOURCE_REF,
            "retained_source_blob_sha": historical_blob_sha or None,
            "caveat": (
                "The canonical run's recorded Git head does not contain the exact runtime Stage 3.8C source path. "
                "The retained pre-prune source plus persisted run behavior are corroborating evidence, not a "
                "cryptographically pinned canonical runtime blob."
            ),
        },
        "seed_contract_selection": {
            "status": "PASS" if contract_ok else "FAIL",
            "overlap_contract": protocol["initial_population_seed_contract"],
            "extension_contract": {
                "identifier": extension_contract.identifier,
                "namespace": extension_contract.namespace,
                "derivation_suffix": extension_contract.derivation_suffix,
            },
            "initial_sampling_seeds": protocol["initial_sampling_seeds"],
        },
    }
    required_categories = (
        "comparator_ordering", "evaluator_payload_and_ranking",
        "design_decoding_and_canonicalization", "optimizer_configuration", "checkpoint_scheduling",
    )
    all_required_pass = all(compatibility[name]["status"] == "PASS" for name in required_categories)
    all_pass = all_required_pass and replay_ok and contract_ok and bool(historical_blob_sha)
    summary = {
        "status": "PASS" if all_pass else "FAIL",
        "scope": "read-only post-implementation pre-launch compatibility evidence",
        "optimizer_executed": False,
        "physics_evaluations": 0,
        "initializer_seed_replay": replay_summary,
        "categories": {name: compatibility[name]["status"] for name in required_categories},
        "seed_contract_status": compatibility["seed_contract_selection"]["status"],
        "historical_source_provenance_status": compatibility["historical_source_provenance"]["status"],
        "canonical_source_provenance_caveat": compatibility["historical_source_provenance"]["caveat"],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "compatibility_summary.json", summary)
    _write_json(output_dir / "source_hashes.json", source_hashes)
    _write_json(output_dir / "behavioral_checks.json", compatibility)
    lines = [
        "# Stage 3.9B source compatibility",
        "",
        f"Status: **{summary['status']}**",
        "",
        "This read-only bundle compares the repaired Stage 3.9B implementation and configuration with persisted canonical Stage 3.8C evidence.",
        "No optimizer or RF/COM evaluation was run.",
        "",
        "| Gate | Status |",
        "|---|---|",
    ]
    lines.extend(f"| {name} | {status} |" for name, status in summary["categories"].items())
    lines.extend([
        "| initializer replay | " + ("PASS" if replay_ok else "FAIL") + " |",
        "| shared Stage 3.9B seed contract | " + compatibility["seed_contract_selection"]["status"] + " |",
        "| historical source provenance | " + compatibility["historical_source_provenance"]["status"] + " |",
        "",
        summary["canonical_source_provenance_caveat"],
        "",
    ])
    (output_dir / "compatibility_summary.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--extension-config", type=Path, default=DEFAULT_EXTENSION_CONFIG)
    parser.add_argument("--canonical-run-dir", type=Path, default=DEFAULT_CANONICAL_RUN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    summary = build_evidence(
        args.config.resolve(), args.extension_config.resolve(),
        args.canonical_run_dir.resolve(), args.output_dir.resolve(),
    )
    print(f"{summary['status']}: Stage 3.9B source compatibility evidence")
    print(f"review bundle: {args.output_dir.resolve()}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
