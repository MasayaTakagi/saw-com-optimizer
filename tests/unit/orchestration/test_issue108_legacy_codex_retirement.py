from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from sawopt import __main__ as legacy_main
from sawopt.orchestration import cli as orchestration_cli
from sawopt.orchestration import worker as orchestration_worker
from sawopt.orchestration.models import RunManifest
from sawopt.orchestration.run_manager import create_run
from sawopt.studies import hybrid_stage4b, hybrid_stage4c


def _queue_manifest(run_dir: Path) -> dict:
    run_id = "legacy-queue-fixture"
    thread_id = "01a0e89c-1c65-72a3-beb6-489f0cf01b30"
    review_spec = {"spec_id": "fixture"}
    return {
        "schema_version": 4,
        "run_id": run_id,
        "experiment_name": "legacy queue fixture",
        "created_at": "2026-10-24T00:00:00+00:00",
        "project_root": str(run_dir),
        "run_dir": str(run_dir),
        "command": [sys.executable, "-c", "raise SystemExit(0)"],
        "config_path": None,
        "codex_session_id": None,
        "codex_model": None,
        "callback_enabled": False,
        "review_after_completion": True,
        "optimizer_run_dir": str(run_dir / "optimizer"),
        "continuation_mode": "queue",
        "original_thread_id": thread_id,
        "next_expected_step": "publish_review_evidence",
        "delivery_sentinel": "a" * 32,
        "queue_preflight": {
            "status": "PASS",
            "thread_id": thread_id,
            "codex_executable": "codex",
            "codex_version": "fixture",
            "explicit_thread": True,
            "explicit_message": True,
        },
        "queue_timeout_seconds": 120.0,
        "review_stage": "fixture",
        "review_contract_version": "1",
        "review_output_dir": f"reports/experiment_reviews/fixture/{run_id}",
        "review_spec_id": "fixture",
        "review_spec_sha256": hashlib.sha256(
            json.dumps(review_spec, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "review_spec": review_spec,
    }


def _write_queue_run(root: Path) -> Path:
    run_dir = root / "queue-run"
    run_dir.mkdir()
    (run_dir / "run_manifest.json").write_text(
        json.dumps(_queue_manifest(run_dir)), encoding="utf-8",
    )
    (run_dir / "status.json").write_text(
        json.dumps({"state": "CREATED", "updated_at": "2026-10-24T00:00:00+00:00"}),
        encoding="utf-8",
    )
    return run_dir


def test_retired_transport_modules_are_absent_from_active_import_tree():
    assert importlib.util.find_spec("sawopt.orchestration.codex_queue") is None
    assert importlib.util.find_spec("sawopt.orchestration.codex_callback") is None


def test_historical_queue_manifest_remains_parseable_without_transport_import(monkeypatch, tmp_path):
    manifest_value = _queue_manifest(tmp_path / "legacy")
    manifest_path = tmp_path / "manifest.json"
    original_bytes = json.dumps(manifest_value).encode("utf-8")
    manifest_path.write_bytes(original_bytes)
    real_import = __import__

    def no_transport_import(name, *args, **kwargs):
        if name.endswith(("codex_queue", "codex_callback")):
            raise AssertionError(f"historical parsing imported retired transport: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", no_transport_import)
    manifest = RunManifest.from_dict(json.loads(manifest_path.read_bytes()))
    assert manifest.continuation_mode == "queue"
    assert manifest.original_thread_id == manifest_value["original_thread_id"]
    assert manifest.queue_preflight == manifest_value["queue_preflight"]
    assert manifest_path.read_bytes() == original_bytes


def test_create_run_rejects_old_queue_manifest_before_directory_creation(tmp_path):
    manifest_value = _queue_manifest(tmp_path / "new-queue")
    manifest = RunManifest.from_dict(manifest_value)
    with pytest.raises(RuntimeError, match="retired"):
        create_run(manifest)
    assert not Path(manifest.run_dir).exists()


def test_worker_rejects_old_queue_run_before_process_or_status_mutation(monkeypatch, tmp_path):
    run_dir = _write_queue_run(tmp_path)
    status_path = run_dir / "status.json"
    original_status = status_path.read_bytes()
    optimizer_calls = []
    monkeypatch.setattr(
        orchestration_worker, "_run_optimizer",
        lambda *args, **kwargs: optimizer_calls.append((args, kwargs)) or 0,
    )

    with pytest.raises(RuntimeError, match="retired|unsupported"):
        orchestration_worker.execute_run(run_dir)

    assert optimizer_calls == []
    assert status_path.read_bytes() == original_status


def test_resume_rejects_old_queue_run_before_checkpoint_or_status_mutation(tmp_path):
    run_dir = _write_queue_run(tmp_path)
    status_path = run_dir / "status.json"
    original_status = status_path.read_bytes()
    args = type("Args", (), {"run_dir": str(run_dir)})()

    with pytest.raises(RuntimeError, match="retired|unsupported"):
        orchestration_cli._resume_launch(args, tmp_path)

    assert status_path.read_bytes() == original_status
    assert not (run_dir / "resume_checkpoint.json").exists()


def test_recovery_rejects_old_queue_run_before_status_mutation(monkeypatch, tmp_path):
    run_dir = _write_queue_run(tmp_path)
    original_status = (run_dir / "status.json").read_bytes()
    monkeypatch.setattr(orchestration_cli, "resolve_run_dir", lambda *_args, **_kwargs: run_dir)

    with pytest.raises(RuntimeError, match="retired|unsupported"):
        orchestration_cli.recover(type("Args", (), {"run_id": "legacy-queue-fixture"})())

    assert (run_dir / "status.json").read_bytes() == original_status


def test_queue_confirmation_and_callback_review_are_explicitly_retired():
    for command in ("confirm-queue", "review"):
        with pytest.raises(RuntimeError, match="retired|unsupported"):
            orchestration_cli.main([command, "fixture"])


@pytest.mark.parametrize(
    "study_type",
    ["hybrid_stage4b_topology_comparison", "hybrid_stage4c_confirmatory"],
)
def test_direct_legacy_stage_production_dispatch_is_rejected_before_output(
    monkeypatch, tmp_path, study_type,
):
    monkeypatch.setattr(
        legacy_main, "load_experiment_config",
        lambda _path: {"study": {"type": study_type}},
    )
    output = tmp_path / "must-not-be-created"
    with pytest.raises(RuntimeError, match="retired|unsupported"):
        legacy_main._run_study("fixture.yaml", output)

    assert not output.exists()


def test_stage4b_live_runtime_entrypoints_reject_before_read_or_write(tmp_path):
    output = tmp_path / "must-not-be-created"
    missing_config = tmp_path / "missing.yaml"

    with pytest.raises(RuntimeError, match="retired|unsupported"):
        hybrid_stage4b.load_stage4b_context(missing_config)
    with pytest.raises(RuntimeError, match="retired|unsupported"):
        hybrid_stage4b.run_stage4b_shakedown(missing_config, output)
    with pytest.raises(RuntimeError, match="retired|unsupported"):
        hybrid_stage4b.run_stage4b_production(missing_config, output, tmp_path / "auth.json")

    assert not output.exists()


@pytest.mark.parametrize(
    "config_name",
    ["hybrid_stage4b_topology_comparison.yaml", "hybrid_stage4c_confirmatory.yaml"],
)
def test_orchestration_stage_launch_rejects_before_run_creation(monkeypatch, tmp_path, config_name):
    project_root = Path(__file__).resolve().parents[3]
    monkeypatch.setattr(orchestration_cli, "project_root", lambda: project_root)
    config = project_root / "configs" / "studies" / config_name
    run_root = tmp_path / "external-runs"
    args = orchestration_cli.build_parser().parse_args([
        "launch", "--config", str(config), "--run-root", str(run_root),
        "--continuation-mode", "disabled",
    ])

    with pytest.raises(RuntimeError, match="retired"):
        orchestration_cli.launch(args)

    assert not run_root.exists()


def test_stage4c_production_entrypoint_rejects_before_read_or_write(tmp_path):
    output = tmp_path / "must-not-be-created"
    with pytest.raises(RuntimeError, match="retired|unsupported"):
        hybrid_stage4c.run_stage4c_production(
            tmp_path / "missing.yaml", output, tmp_path / "auth.json",
        )
    assert not output.exists()


def test_retired_cli_commands_fail_before_dispatch():
    with pytest.raises(RuntimeError, match="retired|unsupported"):
        orchestration_cli.main(["launch", "--config", "fixture.yaml", "--continuation-mode", "queue"])


def test_legacy_stage_authorization_flags_are_rejected_before_dispatch():
    with pytest.raises(RuntimeError, match="retired|unsupported"):
        legacy_main.main(["run-study", "--stage4b-authorization-manifest", "fixture.json"])
