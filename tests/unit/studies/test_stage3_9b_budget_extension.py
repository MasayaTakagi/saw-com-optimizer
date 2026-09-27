import json
from pathlib import Path

from sawopt.studies.audits import stage3_9b_budget_extension as extension
from sawopt.studies.audits import stage3_9b_overlap_parity as parity


def test_prefix_projection_excludes_only_approved_total_budget_fields():
    control = {
        "hard_max_budget": 8000,
        "terminal_budget": 8000,
        "population_schedule_terminal_budget": 8000,
        "objective": 1.25,
        "best_so_far_trace": [{"unique_evaluation": 2000, "rank_key": [0.0, 1.0]}],
    }
    extended = {
        **control,
        "hard_max_budget": 16000,
    }

    assert extension._without_expansion_limits(control) == extension._without_expansion_limits(extended)
    wrong_schedule = {**extended, "terminal_budget": 16000}
    assert extension._without_expansion_limits(control) != extension._without_expansion_limits(wrong_schedule)
    changed_trajectory = {**extended, "objective": 1.5}
    assert extension._without_expansion_limits(control) != extension._without_expansion_limits(changed_trajectory)


def test_extension_checkpoint_terminal_budget_is_8k_schedule_horizon():
    checkpoint = {
        "hard_max_budget": 16000,
        "terminal_budget": 8000,
        "population_schedule_terminal_budget": 8000,
    }
    assert extension._checkpoint_budget_metadata_errors(checkpoint, "extension", 16000) == []
    errors = extension._checkpoint_budget_metadata_errors(
        {**checkpoint, "terminal_budget": 16000}, "extension", 16000,
    )
    assert any("terminal_budget" in error and "expected 8000" in error for error in errors)


def test_prefix_search_counters_ignore_only_finalization_validation_work():
    control = {name: 0 for name in parity.COUNTER_FIELDS}
    control.update({
        "search_frequency_points": 7_994_987,
        "search_frequency_count": 9_113,
        "solved_frequency_points": 8_140_795,
        "validation_evaluations": 16,
        "validation_frequency_points": 145_808,
    })
    extension_checkpoint = {
        **control,
        "solved_frequency_points": 7_994_987,
        "validation_evaluations": 0,
        "validation_frequency_points": 0,
    }

    assert extension._prefix_search_counter_projection({"evaluation_counters": control}) == (
        extension._prefix_search_counter_projection({"evaluation_counters": extension_checkpoint})
    )
    observations = extension._prefix_finalization_counter_observations(
        {"evaluation_counters": control}, {"evaluation_counters": extension_checkpoint},
    )
    assert observations["validation_evaluations"] == {"control": 16, "extension": 0}
    assert observations["validation_frequency_points"] == {
        "control": 145_808, "extension": 0,
    }
    changed_search_work = {**extension_checkpoint, "search_frequency_points": 7_994_986}
    assert extension._prefix_search_counter_projection({"evaluation_counters": control}) != (
        extension._prefix_search_counter_projection({"evaluation_counters": changed_search_work})
    )


def test_prefix_does_not_require_post_run_common_grid_fields(monkeypatch):
    monkeypatch.setattr(parity, "_validate_checkpoint_accounting", lambda *_args: [])
    monkeypatch.setattr(
        parity,
        "_record_projection",
        lambda record: {
            key: record[key] for key in (
                "hard_max_budget", "terminal_budget", "population_schedule_terminal_budget",
                "objective", "evaluation_counters",
            )
        },
    )
    monkeypatch.setattr(parity, "_normalized_counters", lambda record: record["evaluation_counters"])
    control = {
        "hard_max_budget": 8000,
        "terminal_budget": 8000,
        "population_schedule_terminal_budget": 8000,
        "objective": 1.0,
        "evaluation_counters": {name: 0 for name in parity.COUNTER_FIELDS},
    }
    extension_checkpoint = {**control, "hard_max_budget": 16000}

    assert not any("common_grid" in error for error in extension._prefix_record_mismatches(
        control, extension_checkpoint, seed=20260917, budget=2000,
    ))


def test_final_common_grid_gate_still_fails_when_b16000_fields_are_missing(tmp_path, monkeypatch):
    seed = extension.SEEDS[0]
    seed_dir = tmp_path / "optimization" / extension.MATERIAL / extension.TOPOLOGY / f"seed{seed}"
    seed_dir.mkdir(parents=True)
    (seed_dir / "final_common_grid_selection.json").write_text(json.dumps({
        "common_validation_grid_id": "grid-v1",
        "selected": {"rank": 1},
        "validated_finalists": [{"rank": 1}],
    }))

    projection = {
        "evaluation_status": "PHYSICS_EVALUATED",
        "geometry_valid": True,
        "search_source_rank_key": [1],
        "design": {"x": 1.0},
        "metrics": {"worst_il_db": 2.0},
        "feasible": False,
        "filter_feasible": False,
        "max_violation": 0.4,
        "objective": 1.0,
    }
    monkeypatch.setattr(extension.parity, "_final_selection_projection", lambda _row: projection)
    errors, _outcomes = extension._common_grid_errors(
        tmp_path,
        {"common_grid_id": "grid-v1"},
        {(seed, 16000): (seed_dir / "B16000.json", {})},
    )

    assert any("B16000.common_grid_selected_design" in error for error in errors)
    assert any("B16000.metrics.common_grid" in error for error in errors)


def test_retained_input_config_hash_is_line_ending_independent_and_detects_mutation(tmp_path):
    approved = tmp_path / "approved.yaml"
    optimizer_dir = tmp_path / "optimizer"
    optimizer_dir.mkdir()
    retained = optimizer_dir / "input_config.yaml"
    approved.write_bytes(b"budget: 16000\nschedule: 8000\n")
    retained.write_bytes(b"budget: 16000\r\nschedule: 8000\r\n")

    errors, report = extension._retained_input_config_provenance(optimizer_dir, approved, {})
    assert errors == []
    assert report["normalized_content_matches"] is True
    assert report["approved_normalized_content_sha256"] == report["retained_normalized_content_sha256"]
    assert report["run_source_path_field_present"] is False

    retained.write_text("budget: 8000\nschedule: 8000\n", encoding="utf-8")
    errors, report = extension._retained_input_config_provenance(optimizer_dir, approved, {})
    assert report["normalized_content_matches"] is False
    assert any("input_config.yaml content differs" in error for error in errors)


def test_effective_backend_requires_16k_limits_and_8k_schedule_horizon():
    protocol = {"hard_bounds": [[0.0, 1.0], [2.0, 3.0]]}
    backend = {
        "total_budget": 16000,
        "hard_max_budget": 16000,
        "population_schedule_terminal_budget": 8000,
        "initial_population": 180,
        "hard_bounds": protocol["hard_bounds"],
    }
    assert extension._effective_backend_config_errors(backend, protocol) == []
    assert extension._effective_backend_config_errors(
        {**backend, "hard_max_budget": 8000}, protocol,
    )
    assert extension._effective_backend_config_errors(
        {**backend, "population_schedule_terminal_budget": 16000}, protocol,
    )


def test_cache_prefix_compares_ordered_keys_and_metric_payload_but_ignores_tail():
    def row(index, insertion_loss):
        return [
            [float(index)],
            {
                "evaluation_status": "PHYSICS_EVALUATED",
                "metrics": {"worst_il_db": insertion_loss},
                "objective": 1.0,
            },
        ]

    control = [row(1, 2.0), row(2, 3.0)]
    extended_cache = [row(1, 2.0), row(2, 3.0), row(3, 99.0)]
    errors, versions_checked = extension._compare_cache_sequence_prefix(
        control, extended_cache, expected_count=2,
    )
    assert errors == []
    assert versions_checked is False


def test_cache_prefix_rejects_changed_key_and_cached_result():
    def row(index, insertion_loss):
        return [
            [float(index)],
            {
                "evaluation_status": "PHYSICS_EVALUATED",
                "metrics": {"worst_il_db": insertion_loss},
                "objective": 1.0,
            },
        ]

    control = [row(1, 2.0), row(2, 3.0)]
    changed_key = [row(1, 2.0), row(3, 3.0)]
    key_errors, _ = extension._compare_cache_sequence_prefix(control, changed_key, expected_count=2)
    assert any("cache prefix key 1 differs" in error for error in key_errors)

    changed_value = [row(1, 2.0), row(2, 3.1)]
    value_errors, _ = extension._compare_cache_sequence_prefix(control, changed_value, expected_count=2)
    assert any("metrics.worst_il_db" in error for error in value_errors)


def test_extension_lattice_has_two_seeds_and_eight_checkpoints():
    expected = {
        (seed, budget)
        for seed in (20260917, 20260918)
        for budget in (2000, 4000, 6000, 8000, 10000, 12000, 14000, 16000)
    }
    assert extension._expected_lattice(extension.EXTENSION_CHECKPOINTS) == expected


def test_review_bundle_path_is_confined_to_artifact_directory():
    valid = extension.ROOT / "artifacts/review_bundles/example"
    assert extension._review_bundle_path(valid).is_relative_to(
        extension.ROOT / "artifacts/review_bundles"
    )

    try:
        extension._review_bundle_path(extension.ROOT / "runs/example")
    except ValueError as exc:
        assert "review bundle must stay under" in str(exc)
    else:
        raise AssertionError("review bundle path outside artifacts/review_bundles was accepted")


def test_outcome_report_keeps_feasibility_separate_from_objective_delta():
    def cells(seed, budget, objective, feasible):
        return {(seed, budget): (Path(f"B{budget}.json"), {
            "objective": objective,
            "max_violation": 0.4 if feasible else 0.6,
            "filter_feasible": feasible,
            "feasible": feasible,
            "geometry_valid": True,
            "metrics": {"worst_il_db": 3.0},
            "objective_parts": {"primary": 0.4, "secondary": 1.0},
        })}

    control = {}
    extended = {}
    for seed in extension.SEEDS:
        control.update(cells(seed, 8000, 10.0, False))
        extended.update(cells(seed, 16000, 9.0, True))

    report = extension._outcome_summary(control, extended)
    assert report["20260917"]["objective"]["delta_16000_minus_8000"] == -1.0
    assert report["20260917"]["feasibility"]["at_8000"]["filter_feasible"] is False
    assert report["20260917"]["feasibility"]["at_16000"]["filter_feasible"] is True
    assert "success_rate" not in report
