import sys
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sawopt.io.checkpoints import CheckpointStore
from sawopt.io.legacy_lifecycle import LEGACY_REVIEW_WAITING_MARKERS
from sawopt.orchestration.models import RunManifest
from sawopt.orchestration.run_manager import create_run
from sawopt.orchestration.worker import execute_run


def _create_manifest(run_dir: Path, code: int) -> None:
    marker = run_dir / "result.txt"
    command = [
        sys.executable,
        "-c",
        "import pathlib, sys; pathlib.Path(sys.argv[1]).write_text('result', encoding='utf-8'); sys.exit(int(sys.argv[2]))",
        str(marker),
        str(code),
    ]
    create_run(RunManifest(
        schema_version=1,
        run_id="dummy",
        experiment_name="dummy",
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        project_root=str(run_dir),
        run_dir=str(run_dir),
        command=command,
        config_path=None,
        codex_session_id=None,
        codex_model=None,
        callback_enabled=False,
        review_after_completion=False,
    ))


class WorkerTests(unittest.TestCase):
    def test_successful_dummy_optimizer(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            _create_manifest(run_dir, 0)
            status = execute_run(run_dir)
            self.assertEqual(status["state"], "COMPLETED")
            self.assertEqual(status["exit_code"], 0)
            self.assertEqual((run_dir / "result.txt").read_text(encoding="utf-8"), "result")
            self.assertTrue((run_dir / "stdout.log").exists())
            self.assertTrue((run_dir / "stderr.log").exists())

    def test_nonzero_optimizer_is_failed_but_does_not_raise(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            _create_manifest(run_dir, 3)
            status = execute_run(run_dir)
            self.assertEqual(status["state"], "FAILED")
            self.assertEqual(status["exit_code"], 3)
            self.assertEqual(status["optimizer_state"], "FAILED")

    def test_failed_optimizer_preserves_runtime_checkpoint_generations(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "failed"
            _create_manifest(run_dir, 3)
            store = CheckpointStore(run_dir / "checkpoints", run_directory=run_dir)
            store.write(lambda path: path.write_text('{"value":1}', encoding="utf-8"))
            store.write(lambda path: path.write_text('{"value":2}', encoding="utf-8"))

            status = execute_run(run_dir)

            self.assertEqual(status["state"], "FAILED")
            self.assertTrue(store.latest_path.is_file())
            self.assertTrue(store.previous_path.is_file())
            self.assertFalse(store.final_path.exists())
            disposition = json.loads(
                (run_dir / "metadata" / "run_completion.json").read_text(encoding="utf-8")
            )
            self.assertEqual(disposition["disposition"], "FAILED")

    def test_historical_review_marker_keeps_worker_run_waiting(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "review"
            _create_manifest(run_dir, 0)
            store = CheckpointStore(run_dir / "checkpoints", run_directory=run_dir)
            store.write(lambda path: path.write_text('{"value":1}', encoding="utf-8"))
            store.write(lambda path: path.write_text('{"value":2}', encoding="utf-8"))
            (run_dir / LEGACY_REVIEW_WAITING_MARKERS[0]).write_text(
                "awaiting review\n", encoding="utf-8",
            )

            status = execute_run(run_dir)

            self.assertEqual(status["state"], "REVIEW_WAITING")
            self.assertTrue(store.latest_path.is_file())
            self.assertTrue(store.previous_path.is_file())
            self.assertFalse(store.final_path.exists())
            disposition = json.loads(
                (run_dir / "metadata" / "run_completion.json").read_text(encoding="utf-8")
            )
            self.assertEqual(disposition["disposition"], "REVIEW_WAITING")

    def test_successful_worker_records_explicit_disposition_then_finalizes(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            _create_manifest(run_dir, 0)
            store = CheckpointStore(run_dir / "checkpoints", run_directory=run_dir)
            store.write(lambda path: path.write_text('{"value":1}', encoding="utf-8"))
            store.write(lambda path: path.write_text('{"value":2}', encoding="utf-8"))

            def complete_study(_manifest, current_run_dir, *, resume=False):
                metadata = current_run_dir / "metadata"
                metadata.mkdir(exist_ok=True)
                (metadata / "run_completion.json").write_text(
                    json.dumps({"status": "COMPLETED"}), encoding="utf-8",
                )
                return 0

            with patch("sawopt.orchestration.worker._run_optimizer", side_effect=complete_study):
                status = execute_run(run_dir)

            self.assertEqual(status["state"], "COMPLETED")
            self.assertEqual(status["checkpoint_finalization"]["status"], "FINALIZED")
            self.assertTrue(store.final_path.is_file())
            self.assertFalse(store.latest_path.exists())
            self.assertFalse(store.previous_path.exists())

    def test_callback_failure_preserves_optimizer_result(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            _create_manifest(run_dir, 0)
            manifest_path = run_dir / "run_manifest.json"
            import json
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["callback_enabled"] = True
            manifest["review_after_completion"] = True
            manifest["codex_session_id"] = "session-1"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            calls = []

            def failed_callback(manifest, **kwargs):
                calls.append((manifest.codex_session_id, kwargs))
                return 9

            status = execute_run(run_dir, callback_runner=failed_callback)
            self.assertEqual(calls[0][0], "session-1")
            self.assertEqual(status["state"], "CALLBACK_FAILED")
            self.assertEqual(status["optimizer_state"], "COMPLETED")
            self.assertEqual(status["callback_exit_code"], 9)
            self.assertTrue((run_dir / "result.txt").exists())

    def test_optimizer_failure_is_reviewed_without_hiding_failure(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "failed-review"
            _create_manifest(run_dir, 3)
            manifest_path = run_dir / "run_manifest.json"
            import json
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["callback_enabled"] = True
            manifest["review_after_completion"] = True
            manifest["codex_session_id"] = "session-1"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            status = execute_run(run_dir, callback_runner=lambda manifest, **kwargs: 0)
            self.assertEqual(status["state"], "REVIEWED")
            self.assertEqual(status["optimizer_state"], "FAILED")
            self.assertEqual(status["exit_code"], 3)
            self.assertTrue(status["callback_completed"])


if __name__ == "__main__":
    unittest.main()
