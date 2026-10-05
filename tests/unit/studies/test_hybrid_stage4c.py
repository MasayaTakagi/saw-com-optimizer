from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sawopt.orchestration import cli as orchestration_cli
from sawopt.orchestration.persistent_storage import validate_persistent_run_location
from sawopt.reporting.github_review import ReviewExportError, _canonical_json_sha256, export_review, load_review_spec
from sawopt.reporting.hybrid_stage4c import (
    STAGE4C_REQUIRED_ARTIFACTS,
    export_stage4c_review,
    paired_comparisons,
    primary_summary,
    stopband_rows,
    validate_stage4c_review_contract,
    write_stage4c_reports,
)
from sawopt.studies.hybrid import stage4a_load_context
from sawopt.studies.hybrid_stage4c import (
    BUDGET,
    CHECKPOINTS,
    COMMON_GRID_ID,
    COMMON_GRID_SHA256,
    PROTOCOL_REVISION,
    PRODUCTION_RUN_ROOT,
    SEARCH_GRID_SHA256,
    SEEDS,
    STAGE4B_SEEDS,
    STUDY_TYPE,
    TOPOLOGIES,
    build_authorization_metadata,
    build_stage4c_run_manifest,
    expected_matrix,
    load_stage4c_context,
    validate_frozen_config,
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


def test_stage4c_manifest_and_authorization_contract_have_no_legacy_fields(tmp_path):
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
    assert metadata["authorization_scope"] == "stage4c-confirmatory-production-v1"
    assert not ({"codex_session_id", "callback_enabled"} & set(metadata))
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
    assert report["classification"] == "STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED"
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


def test_stage4c_orchestration_requires_separate_production_authorization(monkeypatch):
    monkeypatch.setattr(orchestration_cli, "project_root", lambda: Path.cwd())
    args = type("Args", (), {
        "resume": False, "no_callback": False, "session_id": None,
        "continuation_mode": "disabled", "config": CONFIG,
        "authorize_stage4c_production": False,
    })()
    with pytest.raises(PermissionError, match="--authorize-stage4c-production"):
        orchestration_cli.launch(args)
