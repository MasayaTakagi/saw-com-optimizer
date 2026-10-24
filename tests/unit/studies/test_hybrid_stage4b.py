import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sawopt.studies import hybrid_stage4b
from sawopt.reporting.hybrid_stage4b import (
    _classify,
    paired_comparisons,
    summarize_topologies,
    symmetry_sanity,
)
from sawopt.studies.hybrid_stage4b import (
    BUDGET,
    CHECKPOINTS,
    FINALIST_COUNT,
    INITIAL_POPULATION_MULTIPLIER,
    SEEDS,
    SHAKEDOWN_BUDGET,
    SHAKEDOWN_CHECKPOINTS,
    SHAKEDOWN_SEED,
    TOPOLOGIES,
    _cell_paths,
    _cell_failure_payload,
    _expected_matrix,
    _run_cell,
    load_stage4b_context,
    run_stage4b_production,
    run_stage4b_shakedown,
)


CONFIG = "configs/studies/hybrid_stage4b_topology_comparison.yaml"


def _synthetic_cells():
    rows = []
    for topology_index, topology in enumerate(TOPOLOGIES):
        for seed in SEEDS:
            score = topology_index + 1.0
            selected = {
                "max_violation": score,
                "sum_violation": score * 2,
                "metrics": {"worst_il_db": score * 3, "ripple_db": score / 2},
                "violations": {"passband_il": score},
                "feasible": False,
            }
            rows.append({
                "topology": topology,
                "seed": seed,
                "status": "COMPLETED",
                "common_grid_selected_finalist": selected,
                "physics_failures": 1,
                "validation_physics_failures": 0,
                "geometry_rejections": 2,
                "cache_statistics": {"cache_hits": 3},
                "active_bound_diagnostics": [],
                "checkpoint_summaries": [],
            })
    return rows


def test_stage4b_live_context_and_fingerprint_regeneration_are_retired():
    with pytest.raises(RuntimeError, match="retired"):
        load_stage4b_context(CONFIG)


def test_stage4b_manifest_verification_rejects_before_file_or_source_access(monkeypatch, tmp_path):
    def unexpected_access(*args, **kwargs):
        raise AssertionError("retired manifest verification attempted external access")

    monkeypatch.setattr(hybrid_stage4b, "_read_json", unexpected_access)
    monkeypatch.setattr(hybrid_stage4b, "_source_state", unexpected_access)
    context = {
        "root": tmp_path,
        "fingerprint": {"computation_fingerprint": "unused"},
        "matrix": [],
        "config_path": tmp_path / "missing-config.yaml",
    }

    with pytest.raises(RuntimeError, match="legacy Stage 4B production authorization is retired"):
        hybrid_stage4b.verify_production_manifest(
            context, tmp_path / "missing-run", tmp_path / "missing-authorization.json",
        )

    assert not (tmp_path / "missing-run").exists()


def test_stage4b_production_and_shakedown_reject_before_read_or_write(tmp_path):
    output = tmp_path / "must-not-be-created"
    missing_config = tmp_path / "missing.yaml"
    with pytest.raises(RuntimeError, match="retired"):
        run_stage4b_shakedown(missing_config, output)
    with pytest.raises(RuntimeError, match="retired"):
        run_stage4b_production(missing_config, output, tmp_path / "authorization.json")
    assert not output.exists()


def test_memoryerror_cell_failure_keeps_traceback_and_last_durable_budget():
    identity = {"topology": "P_D", "seed": 20261007}
    try:
        raise MemoryError()
    except MemoryError as exc:
        record = _cell_failure_payload(
            identity, exc, phase="search_advance",
            backend=SimpleNamespace(unique_evaluations=80000),
            last_durable_budget=64000,
            checkpoint_reference={"checkpoint_stream": "cells/P_D/seed/checkpoints"},
            elapsed_wall_time_s=12.0,
        )
    assert record["error_type"] == "MemoryError"
    assert record["error_message"] == ""
    assert record["error_repr"] == "MemoryError()"
    assert "MemoryError" in record["traceback"]
    assert record["failing_stage"] == "search_advance"
    assert record["failing_cell"] == identity
    assert record["last_durable_checkpoint_budget"] == 64000
    assert record["checkpoint_reference"]["checkpoint_stream"].endswith("checkpoints")


def test_stage4b_historical_matrix_and_population_contract_remain_recorded():
    matrix = _expected_matrix()
    assert len(matrix) == 20
    assert {row["topology"] for row in matrix} == set(TOPOLOGIES)
    assert {row["seed"] for row in matrix} == set(SEEDS)
    assert {(row["topology"], row["seed"]) for row in matrix} == {
        (topology, seed) for topology in TOPOLOGIES for seed in SEEDS
    }
    assert {row["initial_population"] for row in matrix if row["topology"] == "D"} == {180}
    assert {row["initial_population"] for row in matrix if row["topology"] == "P_D"} == {234}
    assert {row["initial_population"] for row in matrix if row["topology"] == "D_P"} == {234}
    assert {row["initial_population"] for row in matrix if row["topology"] == "P_D_P"} == {288}
    assert all(row["initial_population"] == INITIAL_POPULATION_MULTIPLIER * row["dimension"] for row in matrix)
    assert all(row["budget"] == row["population_schedule_terminal_budget"] == BUDGET for row in matrix)
    assert all(row["checkpoints"] == list(CHECKPOINTS) for row in matrix)
    assert all(row["cold_start"] and not row["warm_start"] and not row["parent_transfer"]
               and not row["topology_transfer"] for row in matrix)
    assert SHAKEDOWN_SEED not in SEEDS
    assert SHAKEDOWN_BUDGET == 512
    assert SHAKEDOWN_CHECKPOINTS == (400, 512)
    assert FINALIST_COUNT == 16


def test_completed_qualification_cell_is_skipped_on_resume(tmp_path):
    run = tmp_path / "production"
    topology, seed = "D", SEEDS[0]
    _, _, result_path = _cell_paths(run, topology, seed)
    result_path.parent.mkdir(parents=True)
    identity = {
        "schema_version": 1,
        "topology": topology,
        "seed": seed,
        "dimension": 10,
        "budget": BUDGET,
        "population_schedule_terminal_budget": BUDGET,
        "checkpoints": list(CHECKPOINTS),
        "initial_population": 180,
        "initial_population_rule": "18 * dimension",
        "cold_start": True,
        "warm_start": False,
        "parent_transfer": False,
        "topology_transfer": False,
        "historical_population_injection": False,
        "mode": "wsl2_qualification",
        "computation_fingerprint": "fingerprint",
        "source_commit_sha": "source-sha",
        "common_validation_grid_id": "grid-id",
    }
    payload = {**identity, "status": "COMPLETED", "unique_evaluations": BUDGET, "sentinel": "keep"}
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    context = {
        "cfg": {},
        "spaces": {topology: SimpleNamespace(dimension=10)},
        "fingerprint": {"computation_fingerprint": "fingerprint"},
        "common_grid_id": "grid-id",
    }
    assert _run_cell(
        context, run, topology=topology, seed=seed, budget=BUDGET,
        checkpoints=CHECKPOINTS, terminal_budget=BUDGET, finalist_count=16,
        mode="wsl2_qualification", source_commit_sha="source-sha", resume=True,
    ) == payload


def test_stage4b_production_cell_rejects_before_filesystem_access(tmp_path):
    run = tmp_path / "must-not-be-created"
    with pytest.raises(RuntimeError, match="production cell execution is retired"):
        _run_cell(
            {}, run, topology="D", seed=SEEDS[0], budget=BUDGET,
            checkpoints=CHECKPOINTS, terminal_budget=BUDGET, finalist_count=16,
            mode="production", source_commit_sha="source-sha", resume=False,
        )
    assert not run.exists()


def test_paired_comparison_and_aggregation_use_all_matched_seeds():
    cells = _synthetic_cells()
    summary = summarize_topologies(cells)
    paired = paired_comparisons(cells)
    assert len(summary) == 4
    assert all(row["completed_seeds"] == row["valid_finalist_seeds"] == 5 for row in summary)
    assert len(paired) == 30
    shakedown_pairs = paired_comparisons(cells, seed_labels=(SHAKEDOWN_SEED,))
    assert len(shakedown_pairs) == 6
    assert {row["seed"] for row in shakedown_pairs} == {SHAKEDOWN_SEED}
    assert all(row["lexicographic_winner"] == "D" for row in paired if row["topology_left"] == "D")
    decision = _classify(summary, paired, integrity_complete=True)
    assert decision["classification"] == "STAGE4B_PRIMARY_AND_FALLBACK_IDENTIFIED"
    assert decision["primary"] == "D"
    assert decision["fallback"] == "P_D"


def test_exact_paired_ties_do_not_count_as_wins_and_incomplete_matrix_is_inconclusive():
    cells = _synthetic_cells()
    d = [row for row in cells if row["topology"] == "D"]
    pd = [row for row in cells if row["topology"] == "P_D"]
    for left, right in zip(d, pd):
        right["common_grid_selected_finalist"] = dict(left["common_grid_selected_finalist"])
    paired = paired_comparisons(cells)
    assert all(row["lexicographic_winner"] == "TIE" for row in paired
               if row["topology_left"] == "D" and row["topology_right"] == "P_D")
    summary = summarize_topologies(cells)
    assert _classify(summary, paired, integrity_complete=False)["classification"] == "STAGE4B_INCONCLUSIVE"


def test_p_d_d_p_symmetry_warning_requires_consistent_seed_direction_and_span():
    cells = _synthetic_cells()
    by_key = {(row["topology"], row["seed"]): row for row in cells}
    for seed in SEEDS:
        by_key[("P_D", seed)]["common_grid_selected_finalist"]["metrics"]["worst_il_db"] = 4.0
        by_key[("D_P", seed)]["common_grid_selected_finalist"]["metrics"]["worst_il_db"] = 1.0
    report = symmetry_sanity(cells)
    assert report["status"] == "SYMMETRY_SANITY_WARNING"
    assert report["warning"] is True
