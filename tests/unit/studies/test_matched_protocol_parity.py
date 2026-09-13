from sawopt.io.config import load_experiment_config
from sawopt.studies.convergence import normalize_convergence_config
from sawopt.studies.matched_protocol_parity import (
    DIAGNOSTIC_STOP,
    EXPECTED_S1_SHA256,
    TERMINAL_HORIZON,
    _historical_protocol,
    _pre_exchange_trace,
    _trace_compare,
    build_matched_protocol_config,
)


def test_matched_protocol_separates_terminal_horizon_from_stop():
    base = normalize_convergence_config(load_experiment_config(
        "configs/studies/stage3_5_lshade_matched_protocol_parity.yaml"
    ))
    import yaml
    with open("artifacts/stage3_5/phase_a_revised/search_space_s1.yaml", encoding="utf-8") as stream:
        s1 = yaml.safe_load(stream)
    cfg = build_matched_protocol_config(base, s1)
    matched = cfg["stage3_5_matched_protocol"]
    assert matched["terminal_horizon"] == TERMINAL_HORIZON
    assert matched["diagnostic_stop"] == DIAGNOSTIC_STOP
    assert matched["requested_checkpoints"] == [DIAGNOSTIC_STOP]
    assert matched["forbid_checkpoints"] == [4000, 8000]
    assert cfg["stage3_3"]["lshade"]["population_schedule_terminal_budget"] == TERMINAL_HORIZON
    assert cfg["stage3_3"]["lshade"]["hard_max_budget"] == TERMINAL_HORIZON


def test_matched_protocol_uses_frozen_s1_identity():
    import hashlib
    from pathlib import Path
    path = Path("artifacts/stage3_5/phase_a_revised/search_space_s1.yaml")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == EXPECTED_S1_SHA256


def test_post_exchange_snapshot_is_excluded_from_pre_exchange_comparison():
    historical = [
        {"unique_evaluation": 1, "frequency_grid_version": 1},
        {"unique_evaluation": DIAGNOSTIC_STOP, "frequency_grid_version": 1},
    ]
    current = historical + [
        {"unique_evaluation": DIAGNOSTIC_STOP, "frequency_grid_version": 2},
    ]

    comparison = _trace_compare(_pre_exchange_trace(current), historical)

    assert comparison["exact_match"] is True


def test_historical_protocol_optional_or_malformed_event_is_safe():
    base = {
        "unique_decoded_evaluations": DIAGNOSTIC_STOP,
        "population_trace": [
            {"unique_evaluation": DIAGNOSTIC_STOP, "frequency_grid_version": 1}
        ],
        "archive_trace": [
            {"unique_evaluation": DIAGNOSTIC_STOP, "frequency_grid_version": 1}
        ],
    }

    absent = _historical_protocol(base)
    malformed = _historical_protocol({**base, "frequency_grid_events": [{"event": "unknown"}]})

    assert absent["B16000_semantics"] == "UNKNOWN"
    assert malformed["B16000_semantics"] == "UNKNOWN"
