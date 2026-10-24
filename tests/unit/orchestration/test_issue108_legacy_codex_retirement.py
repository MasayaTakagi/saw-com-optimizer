from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from sawopt.orchestration.models import RunManifest


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


def test_retired_transport_modules_are_absent_from_active_import_tree():
    assert importlib.util.find_spec("sawopt.orchestration.codex_queue") is None
    assert importlib.util.find_spec("sawopt.orchestration.codex_callback") is None


def test_historical_queue_manifest_remains_parseable_without_transport_import(tmp_path, monkeypatch):
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
