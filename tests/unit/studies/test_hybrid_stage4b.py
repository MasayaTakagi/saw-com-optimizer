import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from sawopt.orchestration import cli as orchestration_cli
from sawopt.reporting.hybrid_stage4b import (
    _classify,
    paired_comparisons,
    summarize_topologies,
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
    _expected_matrix,
    _run_cell,
    authorization_claim_id,
    build_authorization_metadata,
    load_stage4b_context,
    verify_production_manifest,
)
from sawopt.reporting.hybrid_stage4b import symmetry_sanity


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


def test_stage4b_config_and_population_contract():
    context = load_stage4b_context(CONFIG)
    assert tuple(context["contract"]["topologies"]) == TOPOLOGIES
    assert tuple(context["contract"]["seeds"]) == SEEDS
    assert context["contract"]["budget_per_cell"] == BUDGET == 24000
    assert context["contract"]["population_schedule_terminal_budget"] == BUDGET
    assert tuple(context["contract"]["checkpoints"]) == CHECKPOINTS
    assert context["initial_populations"] == {"D": 180, "P_D": 234, "D_P": 234, "P_D_P": 288}
    assert context["fingerprint"]["fingerprint_schema_version"] == 2
    assert len(context["search_frequencies"]) == 1001
    assert len(context["common_frequencies"]) == 9113


def test_exact_20_cell_matrix_seed_mapping_and_checkpoint_policy():
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
    assert all(row["budget"] == row["population_schedule_terminal_budget"] == 24000 for row in matrix)
    assert all(row["checkpoints"] == [4000, 8000, 16000, 24000] for row in matrix)
    assert all(row["cold_start"] and not row["warm_start"] and not row["parent_transfer"]
               and not row["topology_transfer"] for row in matrix)
    assert SHAKEDOWN_SEED not in SEEDS
    assert SHAKEDOWN_BUDGET == 512
    assert SHAKEDOWN_CHECKPOINTS == (400, 512)
    assert FINALIST_COUNT == 16


def test_stage4b_production_authorization_gate(monkeypatch):
    monkeypatch.setattr(orchestration_cli, "project_root", lambda: Path.cwd())
    args = Namespace(
        resume=False, no_callback=False, session_id=None,
        config=CONFIG, authorize_stage4b_production=False,
    )
    with pytest.raises(PermissionError, match="--authorize-stage4b-production"):
        orchestration_cli.launch(args)


def test_authorized_stage4b_launch_records_preflight_and_one_shot_claim(tmp_path, monkeypatch):
    source_sha = "e57332bdb6a65fceff36364dd5eb086a0b2cc36d"
    run_id = "stage4b-cli-test"
    context = {
        "fingerprint": {"computation_fingerprint": "stage4b-test-fingerprint"},
        "matrix": _expected_matrix(),
        "authorization_scope": "stage4b-hybrid-topology-production-exact-protocol-v1",
    }
    monkeypatch.setattr(orchestration_cli, "project_root", lambda: tmp_path)
    monkeypatch.setattr(orchestration_cli, "_new_run_id", lambda: run_id)
    monkeypatch.setattr(
        "sawopt.studies.hybrid_stage4b.load_stage4b_context",
        lambda _config: context,
    )
    monkeypatch.setattr(
        orchestration_cli,
        "resolve_session",
        lambda **_kwargs: {"session_id": "captured-session", "source": "explicit"},
    )
    monkeypatch.setattr(
        orchestration_cli,
        "run_codex_callback_preflight",
        lambda session_id, **_kwargs: {
            "status": "PASS",
            "session_id": session_id,
            "validated_target_id": session_id,
            "executable": "codex-test",
        },
    )

    def git_output(command, **_kwargs):
        return {
            "branch": "codex/stage4b-hybrid-production-20261003\n",
            "rev-parse": source_sha + "\n",
            "status": "",
        }[command[1]]

    monkeypatch.setattr(orchestration_cli.subprocess, "check_output", git_output)
    monkeypatch.setattr(orchestration_cli, "launch_detached", lambda *_args, **_kwargs: 8192)
    run_dir = tmp_path / "runs" / "stage4b-hybrid-topology-production-20261003"
    args = orchestration_cli.build_parser().parse_args([
        "launch", "--config", str((Path.cwd() / CONFIG).resolve()),
        "--run-dir", "runs/stage4b-hybrid-topology-production-20261003",
        "--session-id", "captured-session", "--authorize-stage4b-production",
    ])

    assert orchestration_cli.launch(args) == 0
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    metadata = manifest["experiment_metadata"]
    assert manifest["codex_session_id"] == "captured-session"
    assert manifest["callback_enabled"] is True
    assert manifest["review_after_completion"] is True
    assert manifest["callback_preflight"]["status"] == "PASS"
    assert metadata["source_commit_sha"] == source_sha
    assert metadata["user_authorized_production"] is True
    claim_path = Path(metadata["authorization_claim_path"])
    assert claim_path.is_file()
    assert json.loads(claim_path.read_text(encoding="utf-8"))["claim_id"] == metadata["authorization_claim_id"]


def test_production_manifest_fingerprint_mismatch_rejected(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    run = root / "runs" / "stage4b"
    manifest_path = run / "run_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    monkeypatch.setattr(
        "sawopt.studies.hybrid_stage4b._source_state",
        lambda _: {"branch": "codex/stage4b-hybrid-production-20261003", "head": "abc", "status_short": ""},
    )
    context = {
        "root": root,
        "config_path": (Path.cwd() / CONFIG).resolve(),
        "common_grid_id": "grid-id",
        "matrix": _expected_matrix(),
        "fingerprint": {"computation_fingerprint": "expected-fingerprint"},
    }
    manifest = {
        "schema_version": 2,
        "run_id": "run-1",
        "experiment_name": "stage4b",
        "created_at": "2026-10-03T00:00:00Z",
        "project_root": str(root),
        "run_dir": str(run),
        "command": [],
        "config_path": str(context["config_path"]),
        "codex_session_id": "session-id",
        "codex_model": None,
        "callback_enabled": True,
        "review_after_completion": True,
        "optimizer_run_dir": str(run / "optimizer"),
        "experiment_metadata": {"computation_fingerprint": "different-fingerprint"},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="fingerprint mismatch"):
        verify_production_manifest(context, run / "optimizer", manifest_path)


def test_production_manifest_requires_exact_session_callback_preflight(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    run = root / "runs" / "stage4b"
    optimizer = run / "optimizer"
    manifest_path = run / "run_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    monkeypatch.setattr(
        "sawopt.studies.hybrid_stage4b._source_state",
        lambda _: {"branch": "codex/stage4b-hybrid-production-20261003", "head": "abc", "status_short": ""},
    )
    context = {
        "root": root,
        "config_path": (Path.cwd() / CONFIG).resolve(),
        "common_grid_id": "grid-id",
        "grid_metadata": {"sha256": "grid-sha"},
        "matrix": _expected_matrix(),
        "fingerprint": {"computation_fingerprint": "fingerprint"},
    }
    metadata = build_authorization_metadata(
        context, source_commit_sha="abc", run_id="run-1", authorized_at="2026-10-03T00:00:00Z",
    )
    claim_id = authorization_claim_id(metadata)
    metadata.update({
        "authorization_claim_id": claim_id,
        "authorization_claim_path": str((root / "runs" / ".stage4b_authorization_claims" / f"{claim_id}.json").resolve()),
        "orchestration_run_dir": str(run.resolve()),
        "optimizer_run_dir": str(optimizer.resolve()),
    })
    manifest = {
        "schema_version": 2,
        "run_id": "run-1",
        "experiment_name": "stage4b",
        "created_at": "2026-10-03T00:00:00Z",
        "project_root": str(root),
        "run_dir": str(run),
        "command": [
            "python", "-m", "sawopt", "run-study", "--config", str(context["config_path"]),
            "--run", str(optimizer), "--stage4b-authorization-manifest", str(manifest_path),
        ],
        "config_path": str(context["config_path"]),
        "codex_session_id": "session-id",
        "codex_model": None,
        "callback_enabled": True,
        "review_after_completion": True,
        "callback_preflight": {"status": "FAIL", "session_id": "session-id", "validated_target_id": "session-id"},
        "optimizer_run_dir": str(optimizer),
        "experiment_metadata": metadata,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="passing exact-session callback preflight"):
        verify_production_manifest(context, optimizer, manifest_path)


def test_completed_cell_is_skipped_on_resume(tmp_path):
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
        "mode": "production",
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
        mode="production", source_commit_sha="source-sha", resume=True,
    ) == payload


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
    # Make one pair exactly equal for every seed; this cannot count as a win.
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
