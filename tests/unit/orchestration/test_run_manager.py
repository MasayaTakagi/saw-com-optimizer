import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from pathlib import Path
from tempfile import TemporaryDirectory

from sawopt.orchestration.models import RunManifest
from sawopt.orchestration.run_manager import (
    SessionValidationError,
    atomic_write_json,
    create_run,
    format_status,
    load_status,
    prepare_callback,
    read_current_session,
    resolve_session,
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
        codex_model="test-model",
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

    def test_callback_claim_is_idempotent_for_automatic_attempts(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            create_run(_manifest(run_dir, callback=True, session_id="session-1"))
            transition(run_dir, "STARTING")
            transition(run_dir, "RUNNING")
            transition(run_dir, "COMPLETED", exit_code=0)
            self.assertTrue(prepare_callback(run_dir, automatic=True))
            transition(run_dir, "CALLBACK_FAILED", callback_completed=False)
            self.assertFalse(prepare_callback(run_dir, automatic=True))
            self.assertTrue(prepare_callback(run_dir, automatic=False))

    def test_callback_claim_accepts_review_waiting(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            create_run(_manifest(run_dir, callback=True, session_id="session-review-waiting"))
            transition(run_dir, "STARTING")
            transition(run_dir, "RUNNING")
            transition(run_dir, "REVIEW_WAITING", exit_code=0)
            self.assertTrue(prepare_callback(run_dir, automatic=True))
            self.assertEqual(load_status(run_dir)["state"], "CALLBACK_RUNNING")

    def test_session_validation_rejects_stale_or_wrong_project(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            root.mkdir()
            capture = root / "current_session.json"
            now = datetime.now(timezone.utc)
            atomic_write_json(capture, {
                "session_id": "session-1",
                "cwd": str(root),
                "captured_at": (now - timedelta(days=2)).isoformat(),
            })
            with self.assertRaises(SessionValidationError):
                read_current_session(capture, root, max_age_s=60, now=now)
            atomic_write_json(capture, {
                "session_id": "session-1",
                "cwd": str(root / "other"),
                "captured_at": now.isoformat(),
            })
            with self.assertRaises(SessionValidationError):
                read_current_session(capture, root, now=now)

            atomic_write_json(capture, {
                "session_id": "session-1",
                "cwd": str(root),
                "hook_event": "OtherEvent",
                "captured_at": now.isoformat(),
            })
            with self.assertRaises(SessionValidationError):
                read_current_session(capture, root, now=now)

    def test_explicit_session_id_takes_precedence_over_hook_capture(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            root.mkdir()
            session = resolve_session(
                explicit_session_id="session-explicit",
                session_path=root / "missing.json",
                project_root=root,
                max_age_s=60,
            )
            self.assertEqual(session["session_id"], "session-explicit")
            self.assertEqual(session["source"], "explicit")

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

    def test_status_includes_optimizer_callback_and_pid_details(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            create_run(_manifest(run_dir, callback=True, session_id="session-1"))
            transition(run_dir, "STARTING", worker_pid=111, optimizer_pid=222)
            transition(run_dir, "RUNNING")
            update_status_fields(run_dir, optimizer_state="RUNNING")
            with mock.patch("sawopt.orchestration.run_manager._pid_exists", side_effect=[True, False]):
                rendered = format_status(run_dir)
            self.assertIn("overall_state: RUNNING", rendered)
            self.assertIn("optimizer.state: RUNNING", rendered)
            self.assertIn("worker_pid: 111 (alive)", rendered)
            self.assertIn("optimizer_pid: 222 (dead/unknown)", rendered)


if __name__ == "__main__":
    unittest.main()
