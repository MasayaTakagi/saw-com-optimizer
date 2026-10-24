import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from pathlib import Path
from tempfile import TemporaryDirectory

from sawopt.orchestration.models import RunManifest
from sawopt.orchestration.run_manager import (
    atomic_write_json,
    create_run,
    format_status,
    load_status,
    transition,
    update_status_fields,
)


def _manifest(run_dir: Path, *, callback=False, session_id=None):
    return RunManifest(
        schema_version=1,
        run_id="test-run",
        experiment_name="dummy",
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        project_root=str(run_dir),
        run_dir=str(run_dir),
        command=["dummy"],
        config_path=None,
        codex_session_id=session_id,
        codex_model="test-model" if callback else None,
        callback_enabled=callback,
        review_after_completion=callback,
    )


class RunManagerTests(unittest.TestCase):
    def test_legacy_manifest_defaults_optimizer_output_to_control_root(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "legacy"
            manifest = _manifest(run_dir)
            legacy_data = manifest.to_dict()
            legacy_data.pop("optimizer_run_dir", None)
            legacy_data.pop("callback_preflight", None)
            loaded = RunManifest.from_dict(legacy_data)
            self.assertEqual(loaded.schema_version, 1)
            self.assertIsNone(loaded.optimizer_run_dir)
            self.assertEqual(loaded.effective_optimizer_run_dir, str(run_dir))
            self.assertIsNone(loaded.run_storage_policy)
            self.assertNotIn("persistent_run_root", loaded.to_dict())

    def test_atomic_write_and_validated_state_machine(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            create_run(_manifest(run_dir))
            transition(run_dir, "STARTING")
            update_status_fields(run_dir, worker_pid=123)
            transition(run_dir, "RUNNING")
            transition(run_dir, "COMPLETED", exit_code=0)
            status = load_status(run_dir)
            self.assertEqual(status["state"], "COMPLETED")
            self.assertEqual(status["optimizer_state"], "COMPLETED")
            self.assertEqual(status["worker_pid"], 123)
            self.assertFalse((run_dir / ".status.lock").exists())
            with self.assertRaises(ValueError):
                transition(run_dir, "RUNNING")

    def test_callback_transition_cannot_be_reentered(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            create_run(_manifest(run_dir))
            transition(run_dir, "STARTING")
            transition(run_dir, "RUNNING")
            transition(run_dir, "COMPLETED", exit_code=0)
            before = (run_dir / "status.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "invalid run state transition"):
                transition(run_dir, "CALLBACK_PENDING")
            self.assertEqual((run_dir / "status.json").read_bytes(), before)

    def test_stale_status_lock_is_reclaimed(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            create_run(_manifest(run_dir))
            stale_time = datetime.now(timezone.utc) - timedelta(hours=1)
            atomic_write_json(run_dir / ".status.lock", {
                "pid": 999999,
                "created_at": stale_time.isoformat(),
                "hostname": "dead-host",
            })
            with mock.patch("sawopt.orchestration.run_manager._pid_exists", return_value=False):
                update_status_fields(run_dir, worker_pid=123)
            self.assertEqual(load_status(run_dir)["worker_pid"], 123)
            self.assertFalse((run_dir / ".status.lock").exists())

    def test_historical_callback_status_renders_without_mutation(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "historical"
            run_dir.mkdir()
            atomic_write_json(run_dir / "run_manifest.json", _manifest(
                run_dir, callback=True, session_id="historical-session",
            ).to_dict())
            historical_status = {
                "state": "CALLBACK_RUNNING", "updated_at": "2026-10-24T00:00:00+00:00",
                "worker_pid": 111, "optimizer_pid": 222, "optimizer_state": "RUNNING",
                "callback_attempts": 4, "callback_completed": False, "callback_enabled": True,
            }
            atomic_write_json(run_dir / "status.json", historical_status)
            before = (run_dir / "status.json").read_bytes()
            with mock.patch("sawopt.orchestration.run_manager._pid_exists", side_effect=[True, False]):
                rendered = format_status(run_dir)
            self.assertIn("overall_state: CALLBACK_RUNNING", rendered)
            self.assertIn("callback.state: running", rendered)
            self.assertIn("callback.attempts: 4", rendered)
            self.assertIn("optimizer.state: RUNNING", rendered)
            self.assertIn("worker_pid: 111 (alive)", rendered)
            self.assertIn("optimizer_pid: 222 (dead/unknown)", rendered)
            self.assertEqual((run_dir / "status.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
