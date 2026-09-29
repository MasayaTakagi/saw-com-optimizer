"""Tiny non-production proof of orchestration -> worker -> run-study dispatch."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

import yaml

from sawopt.orchestration.run_manager import load_status


ROOT = Path(__file__).resolve().parents[2]


def _smoke_config(path: Path) -> Path:
    production = ROOT / "configs/studies/hybrid_stage4b_comparison.yaml"
    cfg = yaml.safe_load(production.read_text(encoding="utf-8"))
    cfg["base_config"] = str((ROOT / "configs/studies/dms_topology_screening.yaml").resolve())
    cfg["study"]["mode"] = "orchestration_smoke"
    cfg["dms_topology"].update({
        "budget": 16, "initial_population": 4,
        "population_schedule_terminal_budget": 16,
        "checkpoints": [8, 16], "seeds": [303],
    })
    cfg["hybrid"]["common_grid_finalists"] = 2
    cfg["hybrid"]["initializer"]["max_attempts"] = 2000
    cfg["hybrid_comparison"].update({
        "topologies": ["D"], "primary_budget": 16,
        "evaluations_per_dimension": 1,
        "population_schedule_terminal_budget": 16,
        "checkpoint_budgets": [8, 16],
        "common_grid_finalists": 2,
        "normalized_targets": {"D": 16},
        "production_launch_authorized": False,
    })
    cfg["hybrid"]["production_launch_authorized"] = False
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path


def test_detached_orchestration_runs_tiny_hybrid_study_and_retains_review_state(tmp_path):
    run_name = f"stage4b-orchestration-smoke-{uuid.uuid4().hex}"
    run_dir = tmp_path / run_name
    config = _smoke_config(tmp_path / "hybrid_smoke.yaml")
    bundle = ROOT / "artifacts" / "review_bundles" / f"{run_name}_review.zip"
    assert not bundle.exists(), "refusing to overwrite an existing review artifact"
    command = [
        sys.executable, "-m", "sawopt.orchestration.cli", "launch",
        "--config", str(config), "--run-dir", str(run_dir), "--no-callback",
    ]
    try:
        launched = subprocess.run(
            command, cwd=ROOT, text=True, encoding="utf-8", capture_output=True,
            timeout=20, check=False,
        )
        assert launched.returncode == 0, launched.stderr or launched.stdout

        deadline = time.monotonic() + 45.0
        latest = None
        while time.monotonic() < deadline:
            latest = load_status(run_dir)
            if latest["state"] in {"REVIEW_WAITING", "COMPLETED", "FAILED", "CALLBACK_FAILED"}:
                break
            time.sleep(0.1)
        assert latest is not None
        assert latest["state"] == "REVIEW_WAITING", latest
        assert latest["optimizer_state"] == "REVIEW_WAITING"
        manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
        assert manifest["callback_enabled"] is False
        optimizer = run_dir / "optimizer"
        completion = json.loads(
            (optimizer / "metadata" / "run_completion.json").read_text(encoding="utf-8")
        )
        assert completion["disposition"] == "REVIEW_WAITING"
        assert json.loads((optimizer / "topology_results.json").read_text(encoding="utf-8"))["stage4b_launched"] is False
        store = optimizer / "optimization" / "D" / "seed303" / "checkpoints"
        assert (store / "latest.json").is_file()
        assert (store / "previous.json").is_file()
        assert not (store / "final.json").exists()
        assert bundle.is_file()
    finally:
        if bundle.is_file():
            bundle.unlink()
