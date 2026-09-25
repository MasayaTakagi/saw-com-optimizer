from sawopt.optimization import convergence_evidence as canonical


def test_explicit_checkpoint_evidence_and_budget_overrides_have_fixed_output():
    record = {
        "requested_unique_design_budget": 8000,
        "terminal_budget": 16000,
        "grid_converged": False,
        "recovery_pending_confirmation": True,
        "boundary_pending_confirmation": False,
        "hard_bound_unresolved": False,
        "micro_polish_improvement": 0.0,
        "fraction_of_budget_at_last_significant_improvement": 0.75,
    }

    result = canonical.derive_checkpoint_evidence(
        record, current_budget=4000, terminal_budget=16000,
    )

    assert result == {
        "grid_converged": False,
        "recovery_pending_confirmation": True,
        "boundary_pending_confirmation": False,
        "hard_bound_unresolved": False,
        "micro_polish_improvement": 0.0,
        "fraction_of_budget_at_last_significant_improvement": 0.75,
        "current_budget": 4000,
        "terminal_budget": 16000,
        "missing_fields": [],
        "complete": True,
    }


def test_checkpoint_events_and_trace_fallback_have_fixed_output():
    record = {
        "requested_unique_design_budget": 100,
        "terminal_budget": 200,
        "frequency_grid_events": [
            {"checkpoint_budget": 50, "added_count": 1},
            {"checkpoint_budget": 100, "added_count": 0},
        ],
        "recovery_events": [{"budget": 50, "event": "recovery"}],
        "boundary_events": [
            {"budget": 50, "event": "boundary_pressure"},
            {"budget": 100, "event": "hard_bound_limited"},
        ],
        "hard_bound_reached_by_variable": {"reflector_pitch": True},
        "best_candidate_polish": {"improvement": 0.125},
        "best_so_far_trace": [
            {"unique_evaluation": 10, "primary_metric": 2.0},
            {"unique_evaluation": 100, "primary_metric": 1.97},
        ],
    }

    result = canonical.derive_checkpoint_evidence(record, current_budget=50)

    assert result == {
        "grid_converged": False,
        "recovery_pending_confirmation": True,
        "boundary_pending_confirmation": True,
        "hard_bound_unresolved": True,
        "micro_polish_improvement": 0.125,
        "fraction_of_budget_at_last_significant_improvement": 2.0,
        "current_budget": 50,
        "terminal_budget": 200,
        "missing_fields": [],
        "complete": True,
    }


def test_missing_telemetry_stays_unknown_and_missing_field_order_is_stable():
    result = canonical.derive_checkpoint_evidence({
        "requested_unique_design_budget": 64,
        "terminal_budget": 128,
    })

    assert result == {
        "grid_converged": None,
        "recovery_pending_confirmation": None,
        "boundary_pending_confirmation": None,
        "hard_bound_unresolved": None,
        "micro_polish_improvement": None,
        "fraction_of_budget_at_last_significant_improvement": None,
        "current_budget": 64,
        "terminal_budget": 128,
        "missing_fields": list(canonical.EVIDENCE_FIELDS),
        "complete": False,
    }


def test_applied_evidence_augments_record_without_dropping_source_fields():
    source = {
        "source_id": "fixture-17",
        "requested_unique_design_budget": 8,
        "terminal_budget": 16,
        "frequency_grid_events": [{"checkpoint_budget": 8, "grid_fixed": True}],
        "recovery_events": [],
        "boundary_events": [],
        "hard_bound_reached_by_variable": {},
        "micro_polish_improvement": 0.0,
        "fraction_of_budget_at_last_significant_improvement": 1.0,
    }

    result = canonical.apply_checkpoint_evidence(source, current_budget=8)

    assert result["source_id"] == "fixture-17"
    assert result["grid_converged"] is True
    assert result["recovery_pending_confirmation"] is False
    assert result["boundary_pending_confirmation"] is False
    assert result["hard_bound_unresolved"] is False
    assert result["micro_polish_improvement"] == 0.0
    assert result["fraction_of_budget_at_last_significant_improvement"] == 1.0
    assert result["convergence_evidence_complete"] is True
    assert result["convergence_evidence_missing_fields"] == []
