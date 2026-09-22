import numpy as np

from sawopt.studies.stage3_7b_r1_normalized_literature_com_validation import (
    _extract_native_features,
)


def test_antiresonance_excludes_resonance_zero_and_selects_post_resonance_minimum():
    frequencies = np.linspace(1.75e9, 1.95e9, 401)
    resonance_hz = 1.814e9
    anti_hz = 1.8786e9
    conductance = (
        0.001
        + 0.8 * np.exp(-((frequencies - resonance_hz) / 2.0e6) ** 2)
    )
    admittance_abs = 0.1 - 0.099 * np.exp(-((frequencies - anti_hz) / 2.0e6) ** 2)
    susceptance = (frequencies - resonance_hz) * (frequencies - anti_hz)
    y = conductance + 1j * susceptance
    # The synthetic |Y| minimum is independent of the real part; this is
    # sufficient to exercise the selection rule and its separation gate.
    y = np.real(y) + 1j * susceptance
    y[np.argmin(np.abs(frequencies - anti_hz))] = (
        np.real(y[np.argmin(np.abs(frequencies - anti_hz))])
        + 1j * susceptance[np.argmin(np.abs(frequencies - anti_hz))]
    )

    resonance_index = int(np.argmin(np.abs(frequencies - resonance_hz)))
    extracted = _extract_native_features(frequencies, y, resonance_index, 1.872685e9)

    selected = extracted["selected_antiresonance_frequency_hz"]
    assert selected is not None
    assert selected > resonance_hz + extracted["minimum_separation_hz"]
    assert abs(selected - anti_hz) < 2.0e6
    assert extracted["selection_reason"].startswith("POST_RESONANCE")


def test_feature_candidates_include_all_three_feature_families():
    frequencies = np.linspace(1.7e9, 2.0e9, 601)
    resonance_hz = 1.82e9
    anti_hz = 1.88e9
    g = 0.01 + np.exp(-((frequencies - resonance_hz) / 3e6) ** 2)
    b = (frequencies - resonance_hz) * (frequencies - anti_hz)
    # A deep post-resonance admittance minimum at the B zero crossing.
    magnitude = 0.2 - 0.19 * np.exp(-((frequencies - anti_hz) / 4e6) ** 2)
    y = magnitude * np.exp(1j * np.arctan2(b, g))
    resonance_index = int(np.argmax(np.real(y)))
    extracted = _extract_native_features(frequencies, y, resonance_index, 1.87e9)

    kinds = {row["feature_type"] for row in extracted["candidate_rows"]}
    assert kinds == {
        "conductance_local_maximum",
        "admittance_abs_local_minimum",
        "susceptance_zero_crossing",
    }
