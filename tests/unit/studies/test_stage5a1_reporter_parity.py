"""Stage 5A-1 regression for Stage 4C reporter/optimizer rank parity."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sawopt.optimizers.selection import DEFAULT_COMPARATOR, GeometryFirstComparator
from sawopt.reporting.hybrid_stage4c import _score, _winner, paired_comparisons
from sawopt.studies.hybrid_stage4c import SEEDS, TOPOLOGIES


def _candidate(
    feasible: bool, max_violation: float, sum_violation: float,
    worst_il_db: float, ripple_db: float,
) -> dict:
    constraint_names = (
        "il", "ripple", "input_vswr", "output_vswr",
        "stop_0", "stop_1", "stop_2", "stop_3",
    )
    remaining = sum_violation
    violations = {}
    for name in constraint_names:
        value = min(max_violation, max(0.0, remaining))
        violations[name] = value
        remaining -= value
    assert remaining <= 1e-12
    return {
        "evaluation_status": "PHYSICS_EVALUATED",
        "failure_stage": None,
        "geometry_max_violation": 0.0,
        "geometry_violations": {"synthetic_geometry": 0.0},
        "violations": violations,
        "feasible": feasible,
        "max_violation": max_violation,
        "sum_violation": sum_violation,
        "metrics": {"worst_il_db": worst_il_db, "ripple_db": ripple_db},
    }


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        pytest.param(
            _candidate(True, 0.0, 0.0, 3.0, 1.0),
            _candidate(True, 5e-11, 5e-11, 2.0, 1.0),
            "D_P", id="feasible-il-before-violation",
        ),
        pytest.param(
            _candidate(True, 5e-11, 5e-11, 2.0, 0.5),
            _candidate(True, 0.0, 0.0, 2.0, 1.5),
            "P_D", id="feasible-ripple-before-violation",
        ),
        pytest.param(
            _candidate(True, 0.0, 0.0, 2.0, 0.5),
            _candidate(True, 5e-11, 5e-11, 2.0, 0.5),
            "P_D", id="feasible-violation-tiebreak",
        ),
        pytest.param(
            _candidate(False, 0.20, 1.5, 9.0, 1.0),
            _candidate(False, 0.21, 0.5, 2.0, 0.2),
            "P_D", id="infeasible-max-violation-first",
        ),
        pytest.param(
            _candidate(False, 0.20, 1.0, 9.0, 1.0),
            _candidate(False, 0.20, 1.5, 2.0, 0.2),
            "P_D", id="infeasible-sum-violation-second",
        ),
        pytest.param(
            _candidate(False, 0.20, 1.0, 4.0, 1.5),
            _candidate(False, 0.20, 1.0, 5.0, 0.2),
            "P_D", id="infeasible-il-tiebreak",
        ),
        pytest.param(
            _candidate(False, 0.20, 1.0, 4.0, 0.5),
            _candidate(False, 0.20, 1.0, 4.0, 1.5),
            "P_D", id="infeasible-ripple-tiebreak",
        ),
        pytest.param(
            _candidate(True, 0.0, 0.0, 3.0, 1.0),
            _candidate(False, 0.01, 0.01, 1.0, 0.2),
            "P_D", id="feasibility-before-performance",
        ),
        pytest.param(
            _candidate(False, 0.20, 1.0, 4.0, 0.5),
            _candidate(False, 0.20, 1.0, 4.0, 0.5),
            "TIE", id="identical-keys-tie",
        ),
    ],
)
def test_reporter_matches_canonical_optimizer_key(left, right, expected):
    geometry = GeometryFirstComparator()
    for record in (left, right):
        assert _score(record) == DEFAULT_COMPARATOR.rank_key(record)
        assert _score(record) == geometry.rank_key(record)[2:]
    comparison = geometry.compare(left, right)
    canonical_winner = "P_D" if comparison < 0 else ("D_P" if comparison > 0 else "TIE")
    assert _winner(left, right) == canonical_winner == expected


@pytest.mark.parametrize(
    "invalidity",
    ["absent", "non_bool_feasible", "missing_ripple", "nonfinite_ripple",
     "missing_metrics", "physics_failed", "nonfinite_max"],
)
def test_reporter_returns_indeterminate_for_incomplete_ranking_evidence(invalidity):
    good = _candidate(False, 0.20, 1.0, 4.0, 1.0)
    record = _candidate(False, 0.21, 1.1, 4.5, 1.2)
    if invalidity == "absent":
        record = None
    elif invalidity == "non_bool_feasible":
        record["feasible"] = "false"
    elif invalidity == "missing_ripple":
        del record["metrics"]["ripple_db"]
    elif invalidity == "nonfinite_ripple":
        record["metrics"]["ripple_db"] = float("nan")
    elif invalidity == "missing_metrics":
        record["metrics"] = None
    elif invalidity == "physics_failed":
        record["evaluation_status"] = "PHYSICS_FAILED"
    elif invalidity == "nonfinite_max":
        record["max_violation"] = float("inf")

    assert _score(record) is None
    assert _winner(record, good) == "INDETERMINATE"
    assert _winner(good, record) == "INDETERMINATE"


def test_frozen_stage4c_matched_seed_winners_unchanged_on_each_grid():
    """Read-only regression over committed, distinct search/common-grid records."""
    root = Path(__file__).resolve().parents[3]
    saved = root / "reports/experiment_reviews/stage4c/20261006_124153_ed50ba/cells"
    records = {}
    for topology in TOPOLOGIES:
        for seed in SEEDS:
            path = saved / topology / f"{seed}_result.json"
            records[(topology, seed)] = json.loads(path.read_text(encoding="utf-8"))

    expected = ("D_P", "P_D", "P_D", "D_P", "P_D")
    assert tuple(SEEDS) == (20261007, 20261008, 20261009, 20261010, 20261011)
    for field in ("search_incumbent", "common_grid_selected_finalist"):
        winners = []
        for seed in SEEDS:
            left = records[("P_D", seed)][field]
            right = records[("D_P", seed)][field]
            for row in (left, right):
                assert row["evaluation_status"] == "PHYSICS_EVALUATED"
                assert row["feasible"] is False
                assert _score(row) == DEFAULT_COMPARATOR.rank_key(row)
                assert _score(row) == GeometryFirstComparator().rank_key(row)[2:]
            winners.append(_winner(left, right))
        assert tuple(winners) == expected
        assert winners.count("P_D") == 3
        assert winners.count("D_P") == 2

    common_grid_report = paired_comparisons(list(records.values()))
    assert tuple(row["lexicographic_winner"] for row in common_grid_report) == expected


def test_checkpoint_ranking_uses_feasible_ripple_tiebreak():
    """Checkpoint ranking must carry the same fields as terminal comparison."""
    from sawopt.reporting.hybrid_stage4c import _paired_at_checkpoint

    checkpoint_rows = []
    for seed in SEEDS:
        for topology in TOPOLOGIES:
            checkpoint_rows.append({
                "seed": seed, "topology": topology, "checkpoint_budget": 96000,
                "selected_feasible": True,
                "selected_max_violation": 0.0,
                "selected_sum_violation": 0.0,
                "selected_worst_il_db": 2.0,
                "selected_ripple_db": 0.5 if topology == "P_D" else 1.0,
            })
    result = _paired_at_checkpoint(checkpoint_rows, 96000)
    assert result == {seed: "P_D" for seed in SEEDS}

    checkpoint_rows[0].pop("selected_ripple_db")
    assert _paired_at_checkpoint(checkpoint_rows, 96000)[SEEDS[0]] == "INDETERMINATE"
