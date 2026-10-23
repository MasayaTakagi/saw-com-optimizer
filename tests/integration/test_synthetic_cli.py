from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sawopt.cli import build_parser, main, run_experiment
from sawopt.io.cli_config import CliConfigError, load_synthetic_config, validate_synthetic_config
from sawopt.io.experiment_store import RunValidationError, read_experiment_manifest


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs/examples/r6_synthetic_smoke.yaml"
TEST_SOURCE_SHA = "a" * 40
TEST_RUN_ID = "20261023T000000Z-00000071"


def _fixture_paths(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "external-data"
    repository = tmp_path / "mock-repository"
    repository.mkdir()
    return data_root, repository


def test_import_and_help_have_no_physics_or_run_side_effects(tmp_path):
    env = dict(os.environ)
    env.pop("SAWOPT_DATA_ROOT", None)
    result = subprocess.run(
        [sys.executable, "-c", (
            "import sys; import sawopt.cli; "
            "assert not any(name.startswith('sawopt.physics') for name in sys.modules)"
        )],
        cwd=ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr

    parser = build_parser()
    with pytest.raises(SystemExit) as raised:
        parser.parse_args(["--help"])
    assert raised.value.code == 0
    help_result = subprocess.run(
        [sys.executable, "-m", "sawopt.cli", "--help"],
        cwd=ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert help_result.returncode == 0
    assert "validate" in help_result.stdout
    assert "run" in help_result.stdout
    assert "COM/FE" in help_result.stdout
    assert not (ROOT / "runs").exists()


def test_synthetic_config_is_explicit_and_strict():
    config = load_synthetic_config(CONFIG_PATH)
    assert validate_synthetic_config(config) == config

    invalid = {**config, "unexpected": True}
    with pytest.raises(CliConfigError, match="unknown"):
        validate_synthetic_config(invalid)

    invalid_optimizer = {**config, "optimizer": {**config["optimizer"], "name": "unknown"}}
    with pytest.raises(CliConfigError, match="optimizer.name"):
        validate_synthetic_config(invalid_optimizer)

    invalid_version = {**config, "schema_version": True}
    with pytest.raises(CliConfigError, match="schema_version"):
        validate_synthetic_config(invalid_version)


def test_synthetic_cli_vertical_slice_persists_reviewable_separate_accounting(tmp_path, capsys):
    config = load_synthetic_config(CONFIG_PATH)
    data_root, repository = _fixture_paths(tmp_path)

    exit_code = main(
        ["run", "--config", str(CONFIG_PATH)],
        source_sha=TEST_SOURCE_SHA,
        data_root=data_root,
        repository_root=repository,
        run_id=TEST_RUN_ID,
    )
    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "COMPLETED"

    raw_directory = Path(result["raw_run_directory"])
    review_directory = Path(result["review_directory"])
    raw = read_experiment_manifest(raw_directory)
    review = json.loads((review_directory / "manifest.json").read_text(encoding="utf-8"))
    cells = json.loads((review_directory / "cells.json").read_text(encoding="utf-8"))

    assert raw["execution_source_sha"] == TEST_SOURCE_SHA  # injected test identity only
    assert set(raw["scientific_input_sha256"]) == {"model", "search_grid", "validation_grid"}
    assert raw["status"] == "COMPLETED"
    assert raw["search_fe_count"] == config["search_fe_limit"]
    assert raw["validation_point_count"] == len(config["validation_grid"]["points"])
    assert raw["cells"][0]["status"] == "COMPLETED"
    assert raw["cells"][0]["search_fes"] == config["search_fe_limit"]
    assert raw["cells"][0]["validation_points"] == len(config["validation_grid"]["points"])
    assert raw["cells"][0]["search_metrics"]["synthetic_peak_error"] >= 0.0
    assert raw["cells"][0]["validation_metrics"]["synthetic_peak_error"] >= 0.0
    assert raw["observed_checkpoints"] and len(raw["observed_checkpoints"]) == 2
    assert review["package_status"] == "READY_FOR_REVIEW"
    assert review["raw_run_status"] == "COMPLETED"
    assert review["execution_source_sha"] == TEST_SOURCE_SHA
    assert cells[0]["status"] == "COMPLETED"
    assert (review_directory / "validation.csv").is_file()
    with (review_directory / "convergence.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [(row["phase"], int(row["search_fes"]), int(row["validation_points"])) for row in rows] == [
        ("SEARCH", config["search_fe_limit"], 0),
        ("VALIDATION", config["search_fe_limit"], len(config["validation_grid"]["points"])),
    ]
    assert "synthetic" in (review_directory / "README.md").read_text(encoding="utf-8").lower()
    assert not (ROOT / "runs").exists()


def test_injected_evaluator_failure_closes_and_exports_every_cell_honestly(tmp_path):
    config = load_synthetic_config(CONFIG_PATH)
    data_root, repository = _fixture_paths(tmp_path)

    def fail_evaluation(_design, _model, _points):
        raise RuntimeError("synthetic injected evaluator failure")

    result = run_experiment(
        config,
        source_sha=TEST_SOURCE_SHA,
        data_root=data_root,
        repository_root=repository,
        run_id=TEST_RUN_ID,
        response_evaluator=fail_evaluation,
    )
    raw = read_experiment_manifest(result["raw_run_directory"])
    review = json.loads((Path(result["review_directory"]) / "manifest.json").read_text(encoding="utf-8"))
    cells = json.loads((Path(result["review_directory"]) / "cells.json").read_text(encoding="utf-8"))

    assert result["status"] == "FAILED"
    assert raw["status"] == "FAILED"
    assert raw["cells"][0]["status"] == "FAILED"
    assert raw["cells"][0]["search_fes"] == 0
    assert len(raw["expected_cells"]) == len(raw["cells"]) == len(cells) == 1
    assert review["raw_run_status"] == "FAILED"
    assert review["package_status"] == "READY_FOR_REVIEW"
    assert cells[0]["status"] == "FAILED"


def test_missing_data_root_fails_before_any_repository_local_run_write(tmp_path, monkeypatch):
    config = load_synthetic_config(CONFIG_PATH)
    monkeypatch.delenv("SAWOPT_DATA_ROOT", raising=False)
    repository = tmp_path / "mock-repository"
    repository.mkdir()

    with pytest.raises(RunValidationError, match="SAWOPT_DATA_ROOT is required"):
        run_experiment(
            config,
            source_sha=TEST_SOURCE_SHA,
            repository_root=repository,
            run_id=TEST_RUN_ID,
        )

    assert not (ROOT / "runs").exists()
    assert not (tmp_path / "runs").exists()
