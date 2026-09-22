import numpy as np

from sawopt.core.models import NAMES
from sawopt.io.config import load_experiment_config
from sawopt.studies.convergence import normalize_convergence_config
from sawopt.studies.stage3_6_gate2a import decode_release, release_bounds, release_schema
from sawopt.studies.stage3_6_gate2c import (
    CONDITIONS,
    CHECKPOINTS,
    S0_GROUP,
    S1_GROUP,
    SEEDS,
    _promotion_decisions,
    _space_comparison,
    _stage_section,
)


def _cfg():
    return normalize_convergence_config(load_experiment_config(
        "configs/studies/stage3_6_gate2c_joint_impedance_dof_fast_screening.yaml"
    ))


def _s1():
    import yaml
    return yaml.safe_load(open("artifacts/stage3_5/phase_a_revised/search_space_s1.yaml", encoding="utf-8"))


def _row(cid, group, seed, value):
    return {
        "condition_id": cid, "search_space": group, "seed": seed,
        "max_violation": value, "sum_violation": value, "objective": value,
        "worst_il_db": value, "ripple_db": value, "input_vswr": value,
        "output_vswr": value, "stopband_violation": value, "feasible": False,
    }


def test_gate2c_protocol_is_fixed_and_s1_adds_one_existing_dof():
    section = _stage_section(_cfg())
    assert tuple(section["seeds"]) == SEEDS
    assert tuple(section["checkpoints"]) == CHECKPOINTS
    assert [item["id"] for item in section["conditions"]] == [item[0] for item in CONDITIONS]
    s1 = _s1()
    assert release_schema(S0_GROUP, s1)["dimension"] == len(NAMES) + 2
    assert release_schema(S1_GROUP, s1)["dimension"] == len(NAMES) + 3
    assert release_schema(S1_GROUP, s1)["extra_variables"][-1]["name"] == "center_aperture_um"
    _active, hard, _integer = release_bounds(S1_GROUP, s1)
    assert hard[1, 0] == 8


def test_existing_center_aperture_decode_changes_only_s1_extra_dimension():
    s1 = _s1()
    active, _hard, _integer = release_bounds(S1_GROUP, s1)
    vector = np.mean(active, axis=1)
    design = decode_release(vector, S1_GROUP)
    assert design.center_aperture_um == np.mean(active[-1])
    assert design.metallization_ratio == .5
    assert design.thickness_over_lambda == .04


def test_space_comparison_is_paired_and_promotion_is_capped():
    rows = []
    for cid, _zin, _zout in CONDITIONS:
        for seed in SEEDS:
            rows.append(_row(cid, S0_GROUP, seed, 1.0 + seed / 1e9))
            rows.append(_row(cid, S1_GROUP, seed, .9 + seed / 1e9))
    detail, aggregate = _space_comparison(rows)
    assert len(detail) == len(CONDITIONS) * len(SEEDS)
    assert all(row["s1_better"] for row in detail)
    decisions, selected = _promotion_decisions(rows, 4)
    assert len(decisions) == len(CONDITIONS)
    assert len(selected) <= 4
