from __future__ import annotations

from dataclasses import replace

import numpy as np

from sawopt.io.config import load_experiment_config
from sawopt.optimization.accounting import validate_checkpoint_lattice
from sawopt.problem.dms_topologies import T0
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
