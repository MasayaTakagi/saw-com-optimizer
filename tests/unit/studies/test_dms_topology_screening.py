from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import numpy as np
import pytest

from sawopt.io.config import load_experiment_config
from sawopt.optimization.accounting import validate_checkpoint_lattice
from sawopt.design.topology import T0, T1
from sawopt.studies import dms_topology_screening as study
from sawopt.studies.dms_topology_common import initial_design, provider_for_material


def _config():
    cfg = load_experiment_config("configs/studies/dms_topology_screening.yaml")
    cfg["dms_topology"]["initializer_reference_proposals"] = 0
    cfg["dms_topology"]["distribution_bootstrap_replicates"] = 0
    return cfg


def test_current_config_uses_frozen_inputs_and_has_no_one_time_gates():
    cfg = _config()
    section = cfg["dms_topology"]

    assert cfg["study"]["type"] == "dms_topology_screening"
    assert "stage3_8" not in cfg
    assert "stage3_8c_r1" not in cfg
    assert section["budget"] == 8000
    assert section["seeds"] == [20260917, 20260918]
    assert section["checkpoints"] == [2000, 4000, 6000, 8000]
    assert section["initial_designs"]["M0"].startswith(
        "configs/reference/dms_topology_screening/"
    )
    grid, grid_id, _path, metadata = study._load_common_grid(cfg)
    assert len(grid) == metadata["frequency_count"] == 9113
    assert grid_id == metadata["grid_id"]
    mlit, _metadata = provider_for_material("MLIT", cfg)
    assert mlit.profile_id == "LI2024_42YX_LT_METAL_UNSPECIFIED_T25"


def test_optional_cell_selection_defaults_to_full_protocol_and_accepts_single_cell():
    cfg = _config()
    assert study._selected_study_axes(cfg) == (
        ("M0", "MLIT"), ("T0_CURRENT_3IDT", "T1_SYMMETRIC_5IDT", "T2_PARALLEL_3IDT_X2"),
    )

    cfg["dms_topology"]["selection"] = {
        "materials": ["MLIT"], "topologies": ["T1_SYMMETRIC_5IDT"],
    }
    assert study._selected_study_axes(cfg) == (("MLIT",), ("T1_SYMMETRIC_5IDT",))


def test_optional_cell_selection_rejects_empty_unknown_and_duplicate_axes():
    cfg = _config()
    for selection in (
        {"materials": [], "topologies": ["T1_SYMMETRIC_5IDT"]},
        {"materials": ["MISSING"], "topologies": ["T1_SYMMETRIC_5IDT"]},
        {"materials": ["MLIT"], "topologies": ["T1_SYMMETRIC_5IDT"] * 2},
    ):
        cfg["dms_topology"]["selection"] = selection
        try:
            study._selected_study_axes(cfg)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid selection was accepted: {selection}")


def test_stage3_9b_config_fixes_overlap_population_schedule_and_budget():
    cfg = load_experiment_config(
        "configs/studies/stage3_9b_mlit_t1_50ohm_budget_extension.yaml"
    )
    section = cfg["dms_topology"]
    assert section["budget"] == 16000
    assert section["population_schedule_terminal_budget"] == 8000
    assert section["checkpoints"] == list(range(2000, 16001, 2000))
    assert section["seeds"] == [20260917, 20260918]
    assert section["cold_start"] is True
    assert section["impedance_ohm"] == 50.0
    assert study._selected_study_axes(cfg) == (("MLIT",), ("T1_SYMMETRIC_5IDT",))

    bounds = study.material_bounds(cfg, "MLIT", "T1_SYMMETRIC_5IDT")[1]
    baseline = _config()
    old_settings = study._backend_config(
        baseline, "T1_SYMMETRIC_5IDT", 8000, bounds,
    )
    extended_settings = study._backend_config(
        cfg, "T1_SYMMETRIC_5IDT", 16000, bounds,
    )
    assert old_settings["population_schedule_terminal_budget"] == 8000
    assert extended_settings["population_schedule_terminal_budget"] == 8000
    assert extended_settings["total_budget"] == extended_settings["hard_max_budget"] == 16000

    from sawopt.optimization.lshade import LShadeBackend

    old_backend = LShadeBackend(
        study.material_bounds(baseline, "MLIT", "T1_SYMMETRIC_5IDT")[0],
        seed=20260917, config=old_settings,
        integer_indices=study.material_bounds(baseline, "MLIT", "T1_SYMMETRIC_5IDT")[2],
    )
    extended_backend = LShadeBackend(
        study.material_bounds(cfg, "MLIT", "T1_SYMMETRIC_5IDT")[0],
        seed=20260917, config=extended_settings,
        integer_indices=study.material_bounds(cfg, "MLIT", "T1_SYMMETRIC_5IDT")[2],
    )
    assert [old_backend.population_size_for_budget(b) for b in range(2000, 8001, 2000)] == [
        extended_backend.population_size_for_budget(b) for b in range(2000, 8001, 2000)
    ]


def test_cold_start_protocol_rejects_resume_before_creating_output(tmp_path):
    config_path = "configs/studies/stage3_9b_mlit_t1_50ohm_budget_extension.yaml"
    output = tmp_path / "must-not-be-created"
    try:
        study.run_dms_topology_screening(config_path, output, resume=True)
    except ValueError as exc:
        assert "requires a cold start" in str(exc)
    else:
        raise AssertionError("cold-start config accepted resume=True")
    assert not output.exists()


def test_independent_uniform_initializer_is_seeded_and_geometry_valid():
    cfg = _config()
    options = {
        "seed": 20260917,
        "population_size": 12,
        "max_attempts": 720,
        "reference_proposals": 0,
        "bootstrap_replicates": 0,
    }
    first, first_stats = study.sample_independent_uniform_population(
        cfg, "M0", T0, **options,
    )
    second, second_stats = study.sample_independent_uniform_population(
        cfg, "M0", T0, **options,
    )

    np.testing.assert_array_equal(first, second)
    assert first_stats["initial_sampling_seed"] == second_stats["initial_sampling_seed"]
    assert first_stats["initial_sampling_draws"] == (
        first_stats["initial_sampling_geometry_rejections"]
        + first_stats["initial_sampling_duplicate_rejections"]
        + first_stats["random_initial_accepts"]
    )
    active, _hard, integers = study.material_bounds(cfg, "M0", T0)
    physical = active[:, 0] + first * (active[:, 1] - active[:, 0])
    for vector in physical:
        design = study.decode_design(vector, T0, cfg)
        assert study._geometry_status(design, cfg)[2] == 0.0
        np.testing.assert_array_equal(
            study._canonical_physical(vector, active, integers), vector,
        )


def test_initial_population_seed_contracts_are_explicit_and_scoped():
    cfg = _config()
    assert study.resolve_initial_population_seed_contract(cfg).identifier == (
        study.DEFAULT_INITIAL_POPULATION_SEED_CONTRACT
    )
    assert study.initial_population_sampling_seed(cfg, 20260917, "MLIT", T1) == 3688039291
    cfg["study"]["revision"] = "renamed_without_science_change"
    assert study.initial_population_sampling_seed(cfg, 20260917, "MLIT", T1) == 3688039291

    cfg["dms_topology"]["initial_population_seed_contract"] = (
        study.STAGE3_8C_R1_2_INITIAL_POPULATION_SEED_CONTRACT
    )
    contract = study.resolve_initial_population_seed_contract(cfg)
    assert contract.namespace == "stage3_8c_r1_geometry_first_v1"
    assert contract.derivation_suffix == "r1_2_independent_rejection"
    assert study.initial_population_sampling_seed(cfg, 20260917, "MLIT", T1) == 3938065196
    assert study.initial_population_sampling_seed(cfg, 20260918, "MLIT", T1) == 1982837181

    cfg["dms_topology"]["initial_population_seed_contract"] = "unknown"
    with pytest.raises(ValueError, match="unknown initial population seed contract"):
        study.initial_population_sampling_seed(cfg, 20260917, "MLIT", T1)


def test_historical_seed_contract_replays_canonical_ordered_population():
    cfg = load_experiment_config(
        "configs/studies/stage3_9b_mlit_t1_50ohm_overlap_parity.yaml"
    )
    expected_hashes = {
        20260917: "699703dcfec14fc3691ca0c728dccc787469d82903728cc0bcff8e84e4f13770",
        20260918: "8c5c42b5bc4214ac88220593ef58ba98b2fd341e4bc81c1d9cabd97eea293e4a",
    }
    expected_rejections = {20260917: 3, 20260918: 6}
    for seed in (20260917, 20260918):
        population, sampling = study.sample_independent_uniform_population(
            cfg, "MLIT", T1, seed=seed, population_size=180, max_attempts=10_800,
            reference_proposals=0, bootstrap_replicates=0,
        )
        active, _hard, integer_indices = study.material_bounds(cfg, "MLIT", T1)
        physical = [
            study._canonical_physical(
                active[:, 0] + vector * (active[:, 1] - active[:, 0]),
                active,
                integer_indices,
            ).tolist()
            for vector in population
        ]
        digest = hashlib.sha256(
            json.dumps(physical, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest()
        assert len(physical) == 180
        assert digest == expected_hashes[seed]
        assert sampling["initial_sampling_geometry_rejections"] == expected_rejections[seed]
        assert sampling["initial_sampling_duplicate_rejections"] == 0
        assert sampling["initial_sampling_seed_contract_id"] == (
            study.STAGE3_8C_R1_2_INITIAL_POPULATION_SEED_CONTRACT
        )


def test_geometry_gate_skips_com_evaluation_for_invalid_design(monkeypatch):
    cfg = _config()
    design = replace(initial_design("M0", T0, cfg), aperture_um=1000.0)
    provider, _ = provider_for_material("M0", cfg)

    def unexpected_physics(*_args, **_kwargs):
        raise AssertionError("physics must not run after geometry rejection")

    monkeypatch.setattr(study, "simulate_topology", unexpected_physics)
    result = study.evaluate_dms_design(design, provider, cfg, np.asarray([780e6]), T0)
    assert result["evaluation_status"] == "GEOMETRY_REJECTED"
    assert result["geometry_valid"] is False


def test_checkpoint_rows_preserve_counter_partition_and_lattice():
    record = {
        "material": "M0", "topology": T0, "seed": 7, "checkpoint_budget": 10,
        "evaluation_status": "PHYSICS_EVALUATED", "geometry_valid": True,
        "metrics": {}, "violations": {}, "design": {},
        "geometry_violations": {}, "geometry_dimensions": {},
    }
    counters = {
        "unique_decoded_evaluations": 10, "geometry_rejections": 2,
        "geometry_valid_candidates": 8, "valid_physics_evaluations": 7,
        "physics_failures": 1, "physics_attempted_evaluations": 8,
    }
    row = study._checkpoint_row(record, counters, {}, np.empty((0, 2)), np.empty((0, 2)))
    audit = validate_checkpoint_lattice(
        [row], materials=["M0"], topologies=[T0], seeds=[7], checkpoints=[10],
    )

    assert audit["passed"] is True
    assert row["counter_identity_pass"] is True
    assert row["physics_partition_pass"] is True
    assert row["physics_attempt_identity_pass"] is True


def test_short_seeded_optimizer_run_writes_a_reusable_checkpoint(tmp_path):
    cfg = _config()
    cfg["dms_topology"]["initial_population_per_dimension"] = 1
    provider, _ = provider_for_material("M0", cfg)
    outcomes = []

    for label in ("first", "repeat"):
        records, backend, _counters, sampling = study._optimize_cell(
            tmp_path / label, cfg, "M0", T0, 20260917, provider,
            np.linspace(775e6, 785e6, 5), budget=10, checkpoints=(10,),
            fingerprint="short-seeded-characterization", sampling_seed_data={},
            max_attempts=100,
        )
        assert records[-1]["checkpoint_budget"] == 10
        assert backend.unique_evaluations >= 10
        assert (tmp_path / label / "optimization" / "M0" / T0 / "seed20260917" / "B10.json").is_file()
        outcomes.append((records[-1]["design"], records[-1]["objective"], sampling["initial_sampling_seed"]))

    assert outcomes[0] == outcomes[1]
