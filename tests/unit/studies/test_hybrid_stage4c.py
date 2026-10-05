from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess

import pytest

from sawopt.orchestration import cli as orchestration_cli
from sawopt.orchestration.persistent_storage import validate_persistent_run_location
from sawopt.reporting.github_review import ReviewExportError, _canonical_json_sha256, export_review, load_review_spec
from sawopt.reporting.hybrid_stage4c import (
    MODEL_LEVEL_MATERIALITY_THRESHOLD,
    STAGE4C_REQUIRED_ARTIFACTS,
    _boundary_rows,
    _checkpoint_rows,
    classify_stage4c,
    export_stage4c_review,
    paired_comparisons,
    primary_summary,
    stopband_rows,
    validate_stage4c_review_contract,
    write_stage4c_reports,
    write_stage4c_shakedown_reports,
)
from sawopt.studies.hybrid import stage4a_load_context
from sawopt.studies.hybrid_stage4c import (
    AUTHORIZATION_SCOPE,
    BUDGET,
    CHECKPOINTS,
    COMMON_GRID_ID,
    COMMON_GRID_SHA256,
    PROTOCOL_REVISION,
    PRODUCTION_RUN_ROOT,
    SEARCH_GRID_SHA256,
    SHAKEDOWN_BUDGET,
    SHAKEDOWN_CHECKPOINTS,
    SHAKEDOWN_SEED,
    SEEDS,
    STAGE4B_SEEDS,
    STUDY_TYPE,
    TOPOLOGIES,
    authorization_claim_id,
    build_authorization_metadata,
    build_stage4c_run_manifest,
    ensure_stage4c_run_manifest,
    expected_matrix,
    expected_shakedown_matrix,
    load_stage4c_context,
    run_stage4c_shakedown,
    validate_frozen_config,
    validate_stage4c_run_manifest,
    verify_stage4c_authorization,
)


CONFIG = "configs/studies/hybrid_stage4c_confirmatory.yaml"
BASELINE_CONFIG = "configs/studies/hybrid_stage4a_qualification.yaml"


def _baseline_contract():
    context = stage4a_load_context(BASELINE_CONFIG)
    baseline = dict(context["cfg"])
    baseline["_stage4c_t1_active_bounds"] = context["contract"]["dms_active_bounds"]
    baseline["_stage4c_t1_hard_bounds"] = context["contract"]["dms_hard_bounds"]
    baseline["_stage4c_profile_metadata"] = context["profile_metadata"]
    return baseline


def test_stage4c_exact_frozen_protocol_and_matrix():
    context = load_stage4c_context(CONFIG)
    matrix = expected_matrix()
    assert context["contract"]["study_type"] == STUDY_TYPE
    assert context["contract"]["protocol_revision"] == PROTOCOL_REVISION
    assert tuple(context["contract"]["topologies"]) == TOPOLOGIES == ("P_D", "D_P")
    assert tuple(context["contract"]["seeds"]) == SEEDS == (20261007, 20261008, 20261009, 20261010, 20261011)
    assert set(SEEDS).isdisjoint(STAGE4B_SEEDS)
    assert len(matrix) == 10
    assert {(row["topology"], row["seed"]) for row in matrix} == {
        (topology, seed) for topology in TOPOLOGIES for seed in SEEDS
    }
    assert {row["dimension"] for row in matrix} == {13}
    assert {row["initial_population"] for row in matrix} == {234}
    assert all(row["budget"] == row["population_schedule_terminal_budget"] == BUDGET for row in matrix)
    assert all(row["checkpoints"] == list(CHECKPOINTS) for row in matrix)
    assert all(row["cold_start"] and not row["warm_start"] and not row["parent_transfer"]
               and not row["topology_transfer"] and not row["historical_population_injection"] for row in matrix)
    assert len(context["search_frequencies"]) == 1001
    assert len(context["common_frequencies"]) == 9113
    assert context["contract"]["search_frequency_sha256"] == SEARCH_GRID_SHA256
    assert context["contract"]["common_validation_grid_id"] == COMMON_GRID_ID
    assert context["contract"]["common_validation_grid_sha256"] == COMMON_GRID_SHA256
    assert context["initial_populations"] == {"P_D": 234, "D_P": 234}
    shakedown = expected_shakedown_matrix()
    assert {(row["topology"], row["seed"]) for row in shakedown} == {
        (topology, SHAKEDOWN_SEED) for topology in TOPOLOGIES
    }
    assert all(row["budget"] == row["population_schedule_terminal_budget"] == SHAKEDOWN_BUDGET
               and row["checkpoints"] == list(SHAKEDOWN_CHECKPOINTS) for row in shakedown)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("study", "seeds"), [20261002, 20261003, 20261004, 20261005, 20261006]),
        (("study", "topologies"), ["P_D"]),
        (("stage4c", "budget_per_cell"), 24000),
        (("stage4c", "population_schedule_terminal_budget"), 64000),
        (("stage4c", "checkpoints"), [8000, 16000, 24000]),
        (("hybrid", "source_impedance_ohm"), 45.0),
        (("hybrid", "common_grid_finalists"), 8),
        (("stage4c", "warm_start"), True),
    ],
)
def test_stage4c_fails_closed_on_protocol_drift(path, value):
    context = load_stage4c_context(CONFIG)
    altered = copy.deepcopy(context["cfg"])
    target = altered
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError, match="Stage 4C protected/frozen input mismatch"):
        validate_frozen_config(altered, _baseline_contract())


def test_stage4c_protected_science_inputs_and_grids_are_pinned():
    context = load_stage4c_context(CONFIG)
    altered = copy.deepcopy(context["cfg"])
    altered["stage4c"]["protected_inputs"]["specification"]["il"] = 2.9
    with pytest.raises(ValueError, match="protected specification"):
        validate_frozen_config(altered, _baseline_contract())
    altered = copy.deepcopy(context["cfg"])
    altered["stage4c"]["protected_inputs"]["common_validation_grid_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="common grid SHA"):
        validate_frozen_config(altered, _baseline_contract())
    altered = copy.deepcopy(context["cfg"])
    altered["dms_topology"]["seeds"] = list(STAGE4B_SEEDS)
    with pytest.raises(ValueError, match="DMS seeds"):
        validate_frozen_config(altered, _baseline_contract())


def test_stage4c_fingerprint_separates_computation_from_reporting():
    context = load_stage4c_context(CONFIG)
    dependency_manifest = context["fingerprint"]["dependency_manifest"]
    computation = {row["path"] for row in dependency_manifest["computation"]}
    reporting = {row["path"] for row in dependency_manifest["reporting"]}
    assert "src/sawopt/studies/hybrid_stage4c.py" in computation
    assert "src/sawopt/studies/hybrid_stage4b.py" in computation
    assert "src/sawopt/optimizers/lshade.py" in computation
    assert CONFIG in computation
    assert "src/sawopt/reporting/hybrid_stage4c.py" in reporting
    assert "src/sawopt/reporting/hybrid_stage4c.py" not in computation


def test_stage4c_manifest_and_authorization_contract_have_no_legacy_fields(tmp_path, monkeypatch):
    context = load_stage4c_context(CONFIG)
    manifest = build_stage4c_run_manifest(
        context, run_id="stage4c-fixture", source_commit_sha="a" * 40,
    )
    assert manifest["study_type"] == STUDY_TYPE
    assert manifest["protocol_revision"] == PROTOCOL_REVISION
    assert manifest["budget_per_cell"] == manifest["population_schedule_terminal_budget"] == BUDGET
    assert manifest["checkpoints"] == list(CHECKPOINTS)
    assert manifest["topologies"] == list(TOPOLOGIES)
    assert manifest["seeds"] == list(SEEDS)
    assert manifest["run_storage_policy"] == "external_persistent_v1"
    assert not ({"codex_session_id", "callback_enabled"} & set(manifest))
    metadata = build_authorization_metadata(
        context, source_commit_sha="a" * 40, run_id="stage4c-fixture",
        authorized_at="2026-10-05T00:00:00+00:00",
    )
    assert metadata["authorization_scope"] == AUTHORIZATION_SCOPE
    assert not ({"codex_session_id", "callback_enabled"} & set(metadata))
    git_common = tmp_path / "git-common"
    claim_dir = git_common / "sawopt-stage4c-authorization-claims"
    claim_dir.mkdir(parents=True)
    monkeypatch.setattr("sawopt.orchestration.active_runs.git_common_dir", lambda _root: git_common)
    claim_id = authorization_claim_id(metadata)
    claim_path = claim_dir / f"{claim_id}.json"
    claim_payload = {
        "schema_version": 1,
        "claim_id": claim_id,
        "authorization_scope": metadata["authorization_scope"],
        "computation_fingerprint": metadata["computation_fingerprint"],
        "source_commit_sha": metadata["source_commit_sha"],
        "run_id": metadata["run_id"],
        "claimed_at_utc": "2026-10-05T00:00:01+00:00",
    }
    claim_path.write_text(json.dumps(claim_payload), encoding="utf-8")
    metadata["authorization_claim_id"] = claim_id
    metadata["authorization_claim_path"] = str(claim_path.resolve())
    orchestration_manifest = {
        "run_id": "stage4c-fixture", "source_commit_sha": "a" * 40,
        "study_type": STUDY_TYPE, "run_storage_policy": "external_persistent_v1",
        "persistent_run_root": PRODUCTION_RUN_ROOT,
        "run_dir": f"{PRODUCTION_RUN_ROOT}/stage4c-fixture",
        "optimizer_run_dir": f"{PRODUCTION_RUN_ROOT}/stage4c-fixture/optimizer",
        "continuation_mode": "queue", "review_after_completion": True,
        "original_thread_id": "01a0e89c-1c65-72a3-beb6-489f0cf01b30",
        "queue_preflight": {
            "status": "PASS",
            "thread_id": "01a0e89c-1c65-72a3-beb6-489f0cf01b30",
        },
        "review_spec_id": "hybrid_stage4c", "review_stage": "stage4c",
        "review_contract_version": "1",
        "review_output_dir": "reports/experiment_reviews/stage4c/stage4c-fixture",
        "review_spec": load_review_spec("hybrid_stage4c", Path.cwd()),
        "review_spec_sha256": _canonical_json_sha256(
            load_review_spec("hybrid_stage4c", Path.cwd())
        ),
        "experiment_metadata": {
            **metadata,
            "orchestration_run_dir": f"{PRODUCTION_RUN_ROOT}/stage4c-fixture",
            "optimizer_run_dir": f"{PRODUCTION_RUN_ROOT}/stage4c-fixture/optimizer",
        },
    }
    path = tmp_path / "authorization.json"
    path.write_text(json.dumps(orchestration_manifest), encoding="utf-8")
    assert verify_stage4c_authorization(context, path)["authorization"]["study_type"] == STUDY_TYPE
    orchestration_manifest["persistent_run_root"] = "relative/run-root"
    path.write_text(json.dumps(orchestration_manifest), encoding="utf-8")
    with pytest.raises(PermissionError, match="absolute external persistent run root"):
        verify_stage4c_authorization(context, path)

    orchestration_manifest["persistent_run_root"] = PRODUCTION_RUN_ROOT
    path.write_text(json.dumps(orchestration_manifest), encoding="utf-8")
    claim_path.unlink()
    with pytest.raises(PermissionError, match="one-shot authorization claim is missing"):
        verify_stage4c_authorization(context, path)

    claim_path.write_text(json.dumps({**claim_payload, "run_id": "different-run"}), encoding="utf-8")
    with pytest.raises(PermissionError, match="one-shot authorization claim does not match this run"):
        verify_stage4c_authorization(context, path)

    claim_path.write_text(json.dumps(claim_payload), encoding="utf-8")
    orchestration_manifest["experiment_metadata"]["authorization_claim_path"] = str(tmp_path / "wrong-claim.json")
    path.write_text(json.dumps(orchestration_manifest), encoding="utf-8")
    with pytest.raises(PermissionError, match="authorization claim path mismatch"):
        verify_stage4c_authorization(context, path)


def test_stage4c_resume_manifest_preserves_creation_time_and_rejects_protocol_drift(tmp_path):
    context = load_stage4c_context(CONFIG)
    path = tmp_path / "metadata" / "stage4c_run_manifest.json"
    expected = build_stage4c_run_manifest(
        context, run_id="stage4c-resume-fixture", source_commit_sha="a" * 40,
    )
    first, created = ensure_stage4c_run_manifest(path, expected)
    assert created
    timestamp = first["created_at_utc"]
    later_expected = build_stage4c_run_manifest(
        context, run_id="stage4c-resume-fixture", source_commit_sha="a" * 40,
    )
    resumed, created = ensure_stage4c_run_manifest(path, later_expected)
    assert not created
    assert resumed["created_at_utc"] == timestamp
    assert json.loads(path.read_text(encoding="utf-8"))["created_at_utc"] == timestamp

    original = json.loads(path.read_text(encoding="utf-8"))
    for key, value in (
        ("budget_per_cell", 512),
        ("search_grid_sha256", "0" * 64),
        ("seeds", [20261012]),
        ("source_commit_sha", "b" * 40),
    ):
        changed = {**original, key: value}
        path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(RuntimeError, match=f"immutable run manifest mismatch: {key}"):
            ensure_stage4c_run_manifest(path, expected)
    path.write_text(json.dumps(original), encoding="utf-8")


def test_stage4c_external_storage_gate_rejects_repository_local_output(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    external = tmp_path / "persistent"
    external.mkdir()
    accepted = validate_persistent_run_location(
        external / "run-1", repository, worktree_roots=[repository],
    )
    rejected = validate_persistent_run_location(
        repository / "runs" / "run-2", repository, worktree_roots=[repository],
    )
    assert accepted.passed
    assert not rejected.passed


def test_stage4c_authorization_claim_uses_git_common_state_not_repo_runs(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    metadata = {
        "authorization_scope": AUTHORIZATION_SCOPE,
        "computation_fingerprint": "c" * 64,
        "source_commit_sha": "a" * 40,
        "run_id": "stage4c-claim-fixture",
    }
    _claim_id, claim_path = orchestration_cli._claim_stage4c_authorization(repository, metadata)
    assert claim_path == repository / ".git" / "sawopt-stage4c-authorization-claims" / f"{claim_path.stem}.json"
    assert claim_path.is_file()
    assert not (repository / "runs").exists()


def test_stage4c_claim_is_source_protocol_scoped_and_duplicate_run_id_is_rejected(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    metadata_a = {
        "authorization_scope": AUTHORIZATION_SCOPE,
        "computation_fingerprint": "c" * 64,
        "source_commit_sha": "a" * 40,
        "run_id": "stage4c-run-a",
    }
    metadata_b = {**metadata_a, "run_id": "stage4c-run-b"}
    assert authorization_claim_id(metadata_a) == authorization_claim_id(metadata_b)
    claim_id, claim_path = orchestration_cli._claim_stage4c_authorization(repository, metadata_a)
    assert claim_id == authorization_claim_id(metadata_a)
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    assert claim["run_id"] == "stage4c-run-a"
    with pytest.raises(RuntimeError, match="already been claimed"):
        orchestration_cli._claim_stage4c_authorization(repository, metadata_b)
    assert not (repository / "runs").exists()


def test_stage4c_claim_is_consumed_before_active_run_registration():
    import inspect

    source = inspect.getsource(orchestration_cli.launch)
    claim_marker = "claim_id, claim_path = _claim_stage4c_authorization"
    registry_marker = "register_active_run("
    assert source.index(claim_marker) < source.index(registry_marker)


def _synthetic_review_run(tmp_path, *, repository_root, context):
    run_id = "stage4c-fixture"
    run = tmp_path / "raw" / run_id
    optimizer = run / "optimizer"
    (optimizer / "metadata").mkdir(parents=True)
    (optimizer / "summary").mkdir()
    source_sha = "a" * 40
    stage_manifest = build_stage4c_run_manifest(
        context, run_id=run_id, source_commit_sha=source_sha,
    )
    metadata = {
        "study_type": STUDY_TYPE,
        "protocol_revision": PROTOCOL_REVISION,
        "protocol_fingerprint": PROTOCOL_REVISION,
        "computation_fingerprint": context["fingerprint"]["computation_fingerprint"],
        "topologies": list(TOPOLOGIES), "comparison_arms": list(TOPOLOGIES),
        "seeds": list(SEEDS), "expected_cell_count": 10,
        "budget_per_cell": BUDGET, "population_schedule_terminal_budget": BUDGET,
        "checkpoints": list(CHECKPOINTS), "search_grid_sha256": SEARCH_GRID_SHA256,
        "common_validation_grid_id": COMMON_GRID_ID,
        "common_validation_grid_sha256": COMMON_GRID_SHA256,
        "source_impedance_ohm": 50.0, "load_impedance_ohm": 50.0,
        "cold_start": True, "warm_start": False,
        "parent_transfer": False, "topology_transfer": False,
        "initial_population_rule": "18 * topology_dimension",
        "initial_populations": {"P_D": 234, "D_P": 234},
        "production_early_stop": False,
        "historical_population_injection": False,
    }
    spec = load_review_spec("hybrid_stage4c", repository_root)
    root_manifest = {
        "schema_version": 4,
        "run_id": run_id,
        "study_type": STUDY_TYPE,
        "source_commit_sha": source_sha,
        "source_branch": "codex/stage4c-confirmatory-protocol",
        "project_root": str(Path(repository_root).resolve()),
        "run_storage_policy": "external_persistent_v1",
        "persistent_run_root": PRODUCTION_RUN_ROOT,
        "review_stage": "stage4c",
        "review_output_dir": f"reports/experiment_reviews/stage4c/{run_id}",
        "review_spec_id": "hybrid_stage4c",
        "review_spec": spec,
        "review_spec_sha256": _canonical_json_sha256(spec),
        "experiment_metadata": metadata,
    }
    (run / "run_manifest.json").write_text(json.dumps(root_manifest), encoding="utf-8")
    (run / "status.json").write_text(json.dumps({"optimizer_state": "COMPLETED", "exit_code": 0}), encoding="utf-8")
    for relpath, value in {
        "run_completion.json": {"status": "COMPLETED", "run_id": run_id, "computation_fingerprint": metadata["computation_fingerprint"]},
        "protocol_snapshot.json": {"study_type": STUDY_TYPE, "run_id": run_id, "computation_fingerprint": metadata["computation_fingerprint"], "common_validation_grid_id": COMMON_GRID_ID},
        "integrity_check.json": {"status": "PASS", "complete": True, "cells_expected": 10, "cells_present": 10,
                                 "cells_completed": 10, "topologies_present": list(TOPOLOGIES), "seeds_present": list(SEEDS)},
        "stage4c_run_manifest.json": stage_manifest,
    }.items():
        (optimizer / "metadata" / relpath).write_text(json.dumps(value), encoding="utf-8")
    (optimizer / "metadata" / "config_snapshot.yaml").write_text("study:\n  type: hybrid_stage4c_confirmatory\n", encoding="utf-8")
    for name in STAGE4C_REQUIRED_ARTIFACTS:
        if name.startswith("summary/"):
            (optimizer / name).write_text("key,value\nfixture,1\n", encoding="utf-8")
    for item in expected_matrix():
        cell_dir = optimizer / "optimization" / item["topology"] / f"seed{item['seed']}"
        cell_dir.mkdir(parents=True)
        for filename in ("cell_result.json", "cell_status.json"):
            payload = {
                "status": "COMPLETED", "run_id": run_id,
                "source_commit_sha": source_sha,
                "computation_fingerprint": metadata["computation_fingerprint"],
                "topology": item["topology"], "seed": item["seed"],
                "budget": BUDGET, "population_schedule_terminal_budget": BUDGET,
                "common_validation_grid_id": COMMON_GRID_ID,
                "cold_start": True, "warm_start": False,
                "parent_transfer": False, "topology_transfer": False,
            }
            (cell_dir / filename).write_text(json.dumps(payload), encoding="utf-8")
    return run, root_manifest, stage_manifest


def test_stage4c_dedicated_review_spec_and_export(tmp_path):
    context = load_stage4c_context(CONFIG)
    spec = load_review_spec("hybrid_stage4c", Path.cwd())
    destinations = {item["destination"] for item in spec["required_artifacts"]}
    assert set(STAGE4C_REQUIRED_ARTIFACTS) <= destinations | {"run_manifest.json", "status.json"}
    assert spec["stage"] == "stage4c"
    assert spec["target_size_bytes"] == 2 * 1024 * 1024
    assert spec["hard_size_bytes"] == 10 * 1024 * 1024
    run, _root_manifest, _stage_manifest = _synthetic_review_run(
        tmp_path, repository_root=Path.cwd(), context=context,
    )
    validated = validate_stage4c_review_contract(run, Path.cwd())
    assert validated["status"] == "PASS"
    assert validated["canonical_path"] == "reports/experiment_reviews/stage4c/stage4c-fixture"
    result = export_stage4c_review(
        run, repository_root=Path.cwd(), destination=tmp_path / "review-package",
    )
    assert result["status"] == "EXPORTED"
    assert result["bytes"] < 2 * 1024 * 1024
    assert (tmp_path / "review-package" / "cells" / "P_D" / f"{SEEDS[0]}_result.json").is_file()


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("stage", "review stage mismatch"),
        ("study_type", "study type mismatch"),
        ("seeds", "seeds mismatch"),
        ("topologies", "topologies mismatch"),
        ("budget", "budget_per_cell mismatch"),
        ("grid", "common_validation_grid_id mismatch"),
        ("mode", "production mode"),
    ],
)
def test_stage4c_exporter_fails_closed_on_contract_mismatch(tmp_path, mutation, match):
    context = load_stage4c_context(CONFIG)
    run, root_manifest, stage_manifest = _synthetic_review_run(
        tmp_path, repository_root=Path.cwd(), context=context,
    )
    if mutation == "stage":
        root_manifest["review_stage"] = "stage4b"
        root_manifest["review_output_dir"] = "reports/experiment_reviews/stage4b/stage4c-fixture"
    elif mutation == "study_type":
        root_manifest["study_type"] = "hybrid_stage4b_topology_comparison"
    elif mutation == "seeds":
        root_manifest["experiment_metadata"]["seeds"] = list(SEEDS[:-1])
    elif mutation == "topologies":
        stage_manifest["topologies"] = ["P_D"]
        (run / "optimizer" / "metadata" / "stage4c_run_manifest.json").write_text(
            json.dumps(stage_manifest), encoding="utf-8",
        )
    elif mutation == "budget":
        stage_manifest["budget_per_cell"] = 24000
        (run / "optimizer" / "metadata" / "stage4c_run_manifest.json").write_text(
            json.dumps(stage_manifest), encoding="utf-8",
        )
    elif mutation == "grid":
        root_manifest["experiment_metadata"]["common_validation_grid_id"] = "wrong-grid"
    elif mutation == "mode":
        stage_manifest["mode"] = "shakedown"
        (run / "optimizer" / "metadata" / "stage4c_run_manifest.json").write_text(
            json.dumps(stage_manifest), encoding="utf-8",
        )
    (run / "run_manifest.json").write_text(json.dumps(root_manifest), encoding="utf-8")
    with pytest.raises(ReviewExportError, match=match):
        export_review(
            run, repository_root=Path.cwd(), destination=tmp_path / "must-not-export",
        )


def test_stage4c_report_summaries_cover_convergence_boundary_runtime_and_stopband(tmp_path):
    context = load_stage4c_context(CONFIG)
    cells = []
    for topology in TOPOLOGIES:
        for index, seed in enumerate(SEEDS):
            score = 0.40 + (0.01 if topology == "D_P" else 0.0) + index * 0.001
            selected = {
                "feasible": False, "max_violation": score,
                "sum_violation": 1.0 + score,
                "metrics": {"worst_il_db": 4.0 + score, "ripple_db": 1.0 + score / 2},
                "violations": {"stop_1": 0.1, "stop_2": 0.2, "passband_il": 0.3},
            }
            cells.append({
                "topology": topology, "seed": seed, "status": "COMPLETED",
                "budget": BUDGET, "population_schedule_terminal_budget": BUDGET,
                "initial_population": 234, "unique_evaluations": BUDGET,
                "common_grid_selected_finalist": selected,
                "active_bound_diagnostics": ([{"variable": "resonator_0_pairs", "at_upper_bound": True}]
                                             if topology == "D_P" and seed == SEEDS[0] else []),
                "counters": {"geometry_rejections": 10, "objective_proposals": 1000,
                             "physics_failures": 0, "physics_attempted_evaluations": BUDGET,
                             "validation_evaluations": 16, "validation_frequency_points": 145808,
                             "search_frequency_points": 1001000},
                "initialization": {"geometry_rejections": 2, "candidate_draws": 20},
                "cache_statistics": {"cache_hits": 30},
                "runtime": {"cell_wall_time_s": 100.0, "search_evaluation_wall_time_s": 80.0,
                            "common_validation_wall_time_s": 20.0},
                "checkpoint_records": list(CHECKPOINTS),
            })
    run = tmp_path / "synthetic-optimizer-run"
    for cell in cells:
        cell_dir = run / "optimization" / cell["topology"] / f"seed{cell['seed']}"
        cell_dir.mkdir(parents=True, exist_ok=True)
        bounds = context["spaces"][cell["topology"]].bounds
        vector = ((bounds[:, 0] + bounds[:, 1]) / 2).tolist()
        for checkpoint in CHECKPOINTS:
            selected = {
                "feasible": False, "max_violation": 0.40,
                "sum_violation": 1.4,
                "metrics": {"worst_il_db": 4.4, "ripple_db": 1.2},
                "candidate_vector": vector,
            }
            trace = [
                {"unique_evaluation": 1000, "rank_key": [0, 0.60]},
                {"unique_evaluation": int(checkpoint * 0.70), "rank_key": [0, 0.40]},
            ]
            (cell_dir / f"B{checkpoint}.json").write_text(json.dumps({
                "common_grid_selected_finalist": selected,
                "lshade_summary": {"best_so_far_trace": trace},
            }), encoding="utf-8")
    report = write_stage4c_reports(run, context, cells)
    convergence = (run / "summary" / "convergence.csv").read_text(encoding="utf-8-sig")
    assert "fraction_of_budget_at_last_significant_improvement" in convergence
    assert "convergence_evidence_complete" in convergence
    assert report["integrity"]["status"] == "PASS"
    assert report["classification"] == "STAGE4C_PRACTICALLY_EQUIVALENT"
    primary = primary_summary(cells)
    assert all(row["feasible_count"] == 0 for row in primary)
    pairs = paired_comparisons(cells)
    assert len(pairs) == 5
    stopbands = stopband_rows(cells)
    assert stopbands[-1]["stop_2_band_mhz"] == "832-862"
    assert stopbands[-1]["stop_2_violation_median"] == pytest.approx(0.2)
    assert len(json.loads(stopbands[-1]["paired_stop_2_difference_by_seed_P_D_minus_D_P"])) == 5
    bound_report = (run / "summary" / "bound_pressure_summary.csv").read_text(encoding="utf-8-sig")
    assert "resonator_0_pairs" in bound_report
    runtime_report = (run / "summary" / "runtime_accounting_summary.csv").read_text(encoding="utf-8-sig")
    assert "runtime_geometry_rejection_rate" in runtime_report
    assert "duplicate_proposals" in runtime_report


def _write_boundary_checkpoint_fixture(tmp_path, context, *, early_hit, terminal_hit):
    run = tmp_path / "raw-checkpoint-run"
    topology, seed = "P_D", SEEDS[0]
    cell_dir = run / "optimization" / topology / f"seed{seed}"
    cell_dir.mkdir(parents=True)
    bounds = context["spaces"][topology].bounds
    center = ((bounds[:, 0] + bounds[:, 1]) / 2).tolist()
    on_bound = list(center)
    on_bound[0] = float(bounds[0, 0])
    for checkpoint in CHECKPOINTS:
        vector = list(center)
        if early_hit and checkpoint == 32000:
            vector = list(on_bound)
        if terminal_hit and checkpoint == BUDGET:
            vector = list(on_bound)
        (cell_dir / f"B{checkpoint}.json").write_text(json.dumps({
            "common_grid_selected_finalist": {
                "candidate_vector": vector,
                "feasible": False,
                "max_violation": 0.40,
                "sum_violation": 1.2,
                "metrics": {"worst_il_db": 4.0, "ripple_db": 1.0},
            },
            "lshade_summary": {
                "best_so_far_trace": [
                    {"unique_evaluation": 1000, "rank_key": [0, 0.60]},
                    {"unique_evaluation": int(checkpoint * 0.70), "rank_key": [0, 0.40]},
                ],
            },
        }), encoding="utf-8")
    cell = {"topology": topology, "seed": seed}
    return run, cell


def test_stage4c_early_boundary_hit_is_historical_but_does_not_block_maturity(tmp_path):
    context = load_stage4c_context(CONFIG)
    run, cell = _write_boundary_checkpoint_fixture(
        tmp_path, context, early_hit=True, terminal_hit=False,
    )
    rows = _checkpoint_rows(run, [cell], context)
    by_budget = {row["checkpoint_budget"]: row for row in rows}
    assert by_budget[32000]["historical_bound_hit"] is True
    assert by_budget[BUDGET]["historical_bound_hit"] is False
    assert by_budget[BUDGET]["hard_bound_unresolved"] is False
    assert by_budget[BUDGET]["boundary_pending_confirmation"] is False
    assert by_budget[BUDGET]["maturity_classification"] == "MATURE"

    boundary = _boundary_rows([cell], rows)
    cell_row = next(row for row in boundary if row.get("scope") == "cell")
    variable_row = next(row for row in boundary if row.get("scope") == "variable"
                        and row.get("variable") == "wavelength_A_um" and row.get("side") == "lower")
    assert cell_row["historical_bound_hit"] is True
    assert cell_row["hard_bound_unresolved"] is False
    assert variable_row["historical_bound_hits"] == 1
    assert variable_row["terminal_bound_hits"] == 0


def test_stage4c_terminal_boundary_hit_blocks_maturity(tmp_path):
    context = load_stage4c_context(CONFIG)
    run, cell = _write_boundary_checkpoint_fixture(
        tmp_path, context, early_hit=False, terminal_hit=True,
    )
    rows = _checkpoint_rows(run, [cell], context)
    terminal = next(row for row in rows if row["checkpoint_budget"] == BUDGET)
    assert terminal["historical_bound_hit"] is True
    assert terminal["hard_bound_unresolved"] is True
    assert terminal["boundary_pending_confirmation"] is True
    assert terminal["maturity_classification"] == "IMMATURE_OR_INCOMPLETE"


def test_stage4c_shakedown_report_is_explicitly_non_scientific(tmp_path):
    context = load_stage4c_context(CONFIG)
    run = tmp_path / "qualification-run"
    cells = []
    for topology in TOPOLOGIES:
        cell_dir = run / "optimization" / topology / f"seed{SHAKEDOWN_SEED}"
        cell_dir.mkdir(parents=True)
        cell = {
            "topology": topology, "seed": SHAKEDOWN_SEED,
            "status": "COMPLETED", "mode": "shakedown",
            "unique_evaluations": SHAKEDOWN_BUDGET,
            "budget": SHAKEDOWN_BUDGET,
            "population_schedule_terminal_budget": SHAKEDOWN_BUDGET,
            "initial_population": 234,
            "checkpoint_records": list(SHAKEDOWN_CHECKPOINTS),
            "common_validation_grid_id": COMMON_GRID_ID,
            "cold_start": True, "warm_start": False,
            "parent_transfer": False, "topology_transfer": False,
            "historical_population_injection": False,
            "checkpoint_summaries": [], "physics_failures": 0,
            "runtime": {},
        }
        cells.append(cell)
        (cell_dir / "cell_result.json").write_text("{}", encoding="utf-8")
        for checkpoint in SHAKEDOWN_CHECKPOINTS:
            (cell_dir / f"B{checkpoint}.json").write_text("{}", encoding="utf-8")
    manifest = build_stage4c_run_manifest(
        context, run_id=run.name, source_commit_sha="a" * 40,
        mode="shakedown", run_storage_policy="external_qualification_v1",
    )
    report = write_stage4c_shakedown_reports(run, context, cells, manifest)
    assert report["status"] == "PASS"
    assert report["classification"] == "NON_SCIENTIFIC_STAGE4C_SHAKEDOWN_PASS"
    assert report["ranking_eligible"] is False
    assert report["scientific_evidence"] == "NO"
    assert (run / "summary" / "shakedown_cells.csv").is_file()
    assert (run / "metadata" / "shakedown_status.json").is_file()


def _mature_classification_fixture(*, winner_component="max_violation", max_delta=0.05, ripple_delta=0.0):
    cells = []
    checkpoints = []
    for seed_index, seed in enumerate(SEEDS):
        for topology in TOPOLOGIES:
            base = {
                "feasible": False,
                "max_violation": 0.10,
                "sum_violation": 1.0,
                "metrics": {"worst_il_db": 4.0, "ripple_db": 1.0},
                "violations": {"stop_1": 0.1, "stop_2": 0.2},
            }
            p_d_wins = seed_index < 4
            if winner_component == "max_violation":
                if topology == "P_D":
                    base["max_violation"] += 0.0 if p_d_wins else max_delta
                else:
                    base["max_violation"] += max_delta if p_d_wins else 0.0
            elif winner_component == "worst_il_db":
                base["metrics"]["worst_il_db"] += (0.0 if p_d_wins else 1.0) if topology == "P_D" else (1.0 if p_d_wins else 0.0)
            else:
                base["metrics"]["ripple_db"] += ripple_delta if topology == "P_D" else 0.0
            cells.append({
                "topology": topology, "seed": seed, "status": "COMPLETED",
                "common_grid_selected_finalist": base,
            })
            for budget in (64000, 80000, 96000):
                checkpoints.append({
                    "topology": topology, "seed": seed, "checkpoint_budget": budget,
                    "selected_feasible": base["feasible"],
                    "selected_max_violation": base["max_violation"],
                    "selected_sum_violation": base["sum_violation"],
                    "selected_worst_il_db": base["metrics"]["worst_il_db"],
                    "significant_improvement_80k_to_96k": False,
                    "maturity_classification": "MATURE" if budget == 96000 else "NOT_TERMINAL",
                })
    return cells, checkpoints, paired_comparisons(cells)


def test_stage4c_model_materiality_threshold_and_feasibility_equivalence_rules():
    assert MODEL_LEVEL_MATERIALITY_THRESHOLD == 0.02
    clear_cells, clear_checkpoints, clear_pairs = _mature_classification_fixture(
        winner_component="max_violation", max_delta=0.02,
    )
    clear = classify_stage4c(clear_cells, clear_checkpoints, clear_pairs)
    assert clear["classification"] == "STAGE4C_CLEAR_CONFIRMATORY_WINNER"
    assert clear["material_terminal_winning_pairs"] == 4

    il_cells, il_checkpoints, il_pairs = _mature_classification_fixture(
        winner_component="worst_il_db",
    )
    il_only = classify_stage4c(il_cells, il_checkpoints, il_pairs)
    assert il_only["classification"] == "STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED"
    assert il_only["material_terminal_winning_pairs"] == 0

    ripple_cells, ripple_checkpoints, ripple_pairs = _mature_classification_fixture(
        winner_component="ripple", ripple_delta=5.0,
    )
    ripple_only = classify_stage4c(ripple_cells, ripple_checkpoints, ripple_pairs)
    assert ripple_only["classification"] == "STAGE4C_PRACTICALLY_EQUIVALENT"

    feasibility_cells, feasibility_checkpoints, _ = _mature_classification_fixture(
        winner_component="max_violation", max_delta=0.0,
    )
    for cell in feasibility_cells:
        if cell["seed"] in SEEDS[:4]:
            cell["common_grid_selected_finalist"]["feasible"] = cell["topology"] == "P_D"
    for row in feasibility_checkpoints:
        if row["seed"] in SEEDS[:4]:
            row["selected_feasible"] = row["topology"] == "P_D"
    feasibility_pairs = paired_comparisons(feasibility_cells)
    feasibility_wins = classify_stage4c(
        feasibility_cells, feasibility_checkpoints, feasibility_pairs,
    )
    assert feasibility_wins["classification"] == "STAGE4C_CLEAR_CONFIRMATORY_WINNER"


def test_stage4c_orchestration_requires_separate_production_authorization(monkeypatch):
    monkeypatch.setattr(orchestration_cli, "project_root", lambda: Path.cwd())
    args = type("Args", (), {
        "resume": False, "no_callback": False, "session_id": None,
        "continuation_mode": "disabled", "config": CONFIG,
        "authorize_stage4c_production": False,
    })()
    with pytest.raises(PermissionError, match="--authorize-stage4c-production"):
        orchestration_cli.launch(args)
