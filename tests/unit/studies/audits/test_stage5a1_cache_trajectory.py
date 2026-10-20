from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from sawopt.core.metrics import search_grid
from sawopt.io.config import load_experiment_config
from sawopt.studies.audits.stage5a1_cache_trajectory import (
    AuditError,
    _check_terminal_checkpoint_matches_state,
    _geometry_rank_key,
    _stable_top,
    audit_state,
)


ROOT = Path(__file__).resolve().parents[4]
CONFIG = load_experiment_config(ROOT / "configs/studies/hybrid_stage4c_confirmatory.yaml")
SEARCH_GRID = np.unique(search_grid(CONFIG["spec"], CONFIG))
BOUNDS = np.tile([0.0, 1.0], (13, 1))
BOUNDS[0] = [0.0, 256.0]
for _index in (4, 5, 6, 11):
    BOUNDS[_index] = [0.0, 3.0]
INTEGER_INDICES = (4, 5, 6, 11)
FINGERPRINT = "synthetic-computation-fingerprint"


def _result(vector: list[float], index: int) -> dict:
    return {
        "evaluation_status": "PHYSICS_EVALUATED",
        "topology": "P_D",
        "candidate_vector": vector,
        "feasible": True,
        "max_violation": 0.0,
        "sum_violation": 0.0,
        "violations": {},
        "metrics": {"worst_il_db": float(235 - index), "ripple_db": 0.1},
    }


def _fixture_state() -> dict:
    history = []
    results = []
    for index in range(235):
        vector = [
            float(index), 0.25, 0.5, 0.75, 0.0, 0.0, 0.0,
            0.25, 0.5, 0.75, 0.5, 0.0, 0.25,
        ]
        key = list(vector)
        rank = list(_geometry_rank_key(_result(vector, index)))
        history.append([key, 1, rank, vector, index])
        results.append(_result(vector, index))

    population = []
    for index in range(231, 235):
        vector = history[index][3]
        normalized = [vector[d] / BOUNDS[d, 1] for d in range(13)]
        population.append({
            "x": normalized,
            "physical": vector,
            "key": vector,
            "result": results[index],
        })
    top = sorted(history, key=lambda entry: (tuple(entry[2]), entry[4]))[:16]
    retained = [[entry[0], results[entry[4]]] for entry in top]
    counters = {
        "geometry_rejections": 0,
        "geometry_valid_candidates": 235,
        "physics_attempted_evaluations": 235,
        "valid_physics_evaluations": 235,
        "physics_failures": 0,
        "search_frequency_points": 235 * len(SEARCH_GRID),
    }
    return {
        "state_version": 4,
        "backend": "lshade",
        "compact_history_cache": True,
        "historical_finalist_count": 16,
        "bounds": BOUNDS.tolist(),
        "hard_bounds": BOUNDS.tolist(),
        "active_bounds": BOUNDS.tolist(),
        "source_config_fingerprint": FINGERPRINT,
        "active_frequency_grid": SEARCH_GRID.tolist(),
        "frequency_grid_version": 1,
        "design_space_version": 1,
        "compact_history_index": history,
        "cache": [],
        "cache_frequency_versions": [],
        "retained_results": retained,
        "unique_evaluations": 235,
        "actual_unique_budget": 235,
        "requested_unique_budget": 235,
        "initial_population_size": 234,
        "minimum_population_size": 4,
        "current_population_size": 4,
        "population_schedule_terminal_budget": 235,
        "hard_max_budget": 235,
        "total_budget": 235,
        "proposals_total": 235,
        "raw_offspring_count": 1,
        "duplicate_count": 0,
        "cache_hits": 0,
        "duplicate_by_group": {"integer": 0, "continuous": 0},
        "generations": 1,
        "population": population,
        "archive": [],
        "best_so_far_trace": [
            {"unique_evaluation": 234, "frequency_grid_version": 1,
             "rank_key": history[233][2], "comparator": "GeometryFirstComparator"},
            {"unique_evaluation": 235, "frequency_grid_version": 1,
             "rank_key": history[234][2], "comparator": "GeometryFirstComparator"},
        ],
        "population_trace": [
            {"unique_evaluation": 234, "frequency_grid_version": 1, "population_size": 234},
            {"unique_evaluation": 235, "frequency_grid_version": 1, "population_size": 4},
        ],
        "archive_trace": [
            {"unique_evaluation": 234, "frequency_grid_version": 1, "archive_size": 0},
            {"unique_evaluation": 235, "frequency_grid_version": 1, "archive_size": 0},
        ],
        "incumbent": results[234],
        "incumbent_key": history[234][0],
        "m_f": [0.5] * 6,
        "m_cr": [0.5] * 6,
        "history_index": 0,
        "memory_update_batch_size": 234,
        "memory_batch_proposals": 1,
        "successful_f": [],
        "successful_cr": [],
        "successful_weights": [],
        "rng_state": {
            "bit_generator": "PCG64",
            "state": {"state": 17, "inc": 3},
            "has_uint32": 0,
            "uinteger": 0,
        },
        "boundary_repair_counts": {"lower": [0] * 13, "upper": [0] * 13},
        "extra_state": {"geometry_gate_counters": counters},
    }


def _audit(state: dict):
    return audit_state(
        state,
        topology="P_D",
        expected_bounds=BOUNDS,
        expected_hard_bounds=BOUNDS,
        integer_indices=INTEGER_INDICES,
        expected_frequency_grid=SEARCH_GRID,
        expected_fingerprint=FINGERPRINT,
        expected_budget=235,
        expected_memory_size=6,
    )


def test_synthetic_terminal_checkpoint_passes_full_read_only_invariants():
    summary, history = _audit(_fixture_state())

    assert summary["compact_history_index_count"] == 235
    assert summary["canonical_keys_unique"] is True
    assert summary["insertion_orders_complete"] is True
    assert summary["search_grid_points"] == 1001
    assert summary["population_size"] == 4
    assert len(history) == 235


def test_duplicate_canonical_key_is_rejected():
    state = _fixture_state()
    state["compact_history_index"][-1] = deepcopy(state["compact_history_index"][0])

    with pytest.raises(AuditError, match="duplicate canonical key"):
        _audit(state)


def test_vector_key_mismatch_is_rejected_exactly():
    state = _fixture_state()
    state["compact_history_index"][10][3][1] = 0.25000000000000006

    with pytest.raises(AuditError, match="canonical identity mismatch"):
        _audit(state)


def test_integer_rounding_mismatch_uses_floor_x_plus_half():
    state = _fixture_state()
    state["compact_history_index"][10][3][4] = 0.51

    with pytest.raises(AuditError, match="canonical identity mismatch"):
        _audit(state)


@pytest.mark.parametrize("replacement, message", [(0, "duplicated"), (235, "complete zero-based")])
def test_insertion_order_duplicate_or_gap_is_rejected(replacement, message):
    state = _fixture_state()
    state["compact_history_index"][-1][4] = replacement

    with pytest.raises(AuditError, match=message):
        _audit(state)


def test_rank_key_corruption_is_rejected_by_incumbent_and_trace_consistency():
    state = _fixture_state()
    state["compact_history_index"][100][2] = [0.0] * 7

    with pytest.raises(AuditError, match="incumbent does not match"):
        _audit(state)


def test_rank_key_with_invalid_comparator_prefix_is_rejected():
    state = _fixture_state()
    state["compact_history_index"][100][2][0] = 2.0

    with pytest.raises(AuditError, match="invalid GeometryFirst rank prefix"):
        _audit(state)


def test_stable_tie_break_uses_insertion_order():
    tied = (0.0, 0.0, 1.0)
    entries = [(tied, (float(i),), order, 1) for i, order in enumerate((9, 2, 5))]

    assert [entry[2] for entry in _stable_top(entries, budget=10, count=3)] == [2, 5, 9]


def test_frequency_grid_version_change_is_rejected():
    state = _fixture_state()
    state["compact_history_index"][0][1] = 2

    with pytest.raises(AuditError, match="changed frequency-grid version"):
        _audit(state)


def test_compact_history_absence_and_partial_history_are_rejected():
    missing = _fixture_state()
    missing["compact_history_index"] = []
    with pytest.raises(AuditError, match="absent or empty"):
        _audit(missing)

    partial = _fixture_state()
    partial["compact_history_index"].pop()
    with pytest.raises(AuditError, match="differs from unique_evaluations"):
        _audit(partial)


def test_counter_inconsistency_is_rejected():
    state = _fixture_state()
    state["proposals_total"] += 1

    with pytest.raises(AuditError, match="proposal count"):
        _audit(state)


def test_frequency_grid_identity_and_checkpoint_terminal_state_must_match():
    state = _fixture_state()
    state["active_frequency_grid"][0] += 1.0
    with pytest.raises(AuditError, match="exactly match"):
        _audit(state)

    state = _fixture_state()
    checkpoint = {"lshade_summary": {
        "best_so_far_trace": state["best_so_far_trace"],
        "population_trace": state["population_trace"],
        "archive_trace": state["archive_trace"],
        "incumbent": state["incumbent"],
        "unique_evaluations": state["unique_evaluations"],
        "proposals_total": state["proposals_total"],
        "raw_offspring_count": state["raw_offspring_count"],
        "duplicate_count": state["duplicate_count"],
        "cache_hits": state["cache_hits"],
        "generations": state["generations"],
        "boundary_repair_counts": state["boundary_repair_counts"],
        "m_f": state["m_f"],
        "m_cr": state["m_cr"],
        "archive_size": len(state["archive"]),
        "current_population": len(state["population"]),
        "population_size": len(state["population"]),
    }}
    _check_terminal_checkpoint_matches_state(checkpoint, state)
    checkpoint["lshade_summary"]["unique_evaluations"] -= 1
    with pytest.raises(AuditError, match="budgets disagree"):
        _check_terminal_checkpoint_matches_state(checkpoint, state)


def test_retained_result_rank_key_corruption_is_rejected():
    state = _fixture_state()
    state["retained_results"][0][1]["metrics"]["worst_il_db"] += 0.25

    with pytest.raises(AuditError, match="rank key is corrupt"):
        _audit(state)


@pytest.mark.parametrize(
    "corrupt, message",
    [
        (lambda state: state.update(rng_state={"bit_generator": "MT19937"}), "PCG64"),
        (lambda state: state["population"][0]["x"].__setitem__(0, 1.2), "outside"),
        (lambda state: state["best_so_far_trace"][1].update(rank_key=[]), "seven GeometryFirst"),
        (lambda state: state["boundary_repair_counts"]["lower"].pop(), "wrong dimension"),
    ],
)
def test_malformed_rng_population_trace_and_repair_state_are_rejected(corrupt, message):
    state = _fixture_state()
    corrupt(state)

    with pytest.raises(AuditError, match=message):
        _audit(state)
