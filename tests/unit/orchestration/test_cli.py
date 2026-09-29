import json
import unittest
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from sawopt.orchestration import cli
from sawopt.orchestration.models import RunManifest
from sawopt.orchestration.run_manager import (
    atomic_write_json,
    callback_lock_path,
    create_run,
    load_manifest,
    load_status,
    transition,
)


ROOT = Path(__file__).resolve().parents[3]


class CliTests(unittest.TestCase):
    def test_queue_launch_uses_thread_preflight_not_legacy_resume_preflight(self):
        thread_id = "01a0e89c-1c65-72a3-beb6-489f0cf01b30"
        preflight = {
            "status": "PASS", "thread_id": thread_id,
            "effective_user": "test-user", "user_profile": "C:/Users/test-user",
            "windows_user_profile": "C:/Users/test-user",
            "codex_executable": "C:/tools/codex.exe", "codex_version": "codex-test 1.0",
            "explicit_thread": True, "explicit_message": True,
        }
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "queue-launch"
            args = cli.build_parser().parse_args([
                "launch", "--config", "configs/base/b28_dms_baseline.yaml",
                "--run-dir", str(run_dir), "--continuation-mode", "queue",
                "--thread-id", thread_id, "--c2c-task-id", "c2c_test",
                "--plan-iteration", "4", "--next-expected-step", "inspect saved results",
            ])
            with mock.patch.object(cli, "run_codex_queue_preflight", return_value=preflight) as queue_gate, \
                    mock.patch.object(cli, "run_codex_callback_preflight") as legacy_gate, \
                    mock.patch.object(cli, "launch_detached", return_value=4345):
                self.assertEqual(cli.launch(args), 0)

            manifest = load_manifest(run_dir)
            checkpoint = json.loads((run_dir / "session_checkpoint.json").read_text(encoding="utf-8"))
            status = load_status(run_dir)

        queue_gate.assert_called_once_with(thread_id, project_root=ROOT, codex_executable=None)
        legacy_gate.assert_not_called()
        self.assertEqual(manifest.schema_version, 3)
        self.assertEqual(manifest.continuation_mode, "queue")
        self.assertEqual(manifest.original_thread_id, thread_id)
        self.assertEqual(manifest.c2c_task_id, "c2c_test")
        self.assertEqual(manifest.plan_iteration, 4)
        self.assertEqual(checkpoint["next_expected_step"], "inspect saved results")
        self.assertEqual(status["continuation_state"], "PENDING")

    def test_queue_storage_probe_cleans_its_canary_and_temporary_directory(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "future-run"
            cli._probe_queue_storage(run_dir)
            self.assertFalse(run_dir.exists())

    def test_launch_creates_manifest_and_returns_without_waiting(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "async-run"
            args = cli.build_parser().parse_args([
                "launch",
                "--config",
                "configs/studies/hybrid_stage4b_comparison.yaml",
                "--run-dir",
                str(run_dir),
                "--no-callback",
            ])
            with mock.patch.object(cli, "launch_detached", return_value=4242) as launch_mock:
                self.assertEqual(cli.launch(args), 0)
            launch_mock.assert_called_once()
            manifest = load_manifest(run_dir)
            status = load_status(run_dir)
            self.assertEqual(status["state"], "STARTING")
            self.assertEqual(status["worker_pid"], 4242)
            self.assertFalse(manifest.callback_enabled)
            self.assertIn("run-study", manifest.command)
            self.assertEqual(manifest.schema_version, 2)
            self.assertEqual(manifest.effective_optimizer_run_dir, str(run_dir / "optimizer"))
            self.assertEqual(manifest.command[manifest.command.index("--run") + 1], str(run_dir / "optimizer"))

    def test_explicit_session_id_is_used_without_reading_hook_capture(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "explicit-session"
            args = cli.build_parser().parse_args([
                "launch",
                "--config",
                "configs/studies/hybrid_stage4b_comparison.yaml",
                "--run-dir",
                str(run_dir),
                "--session-id",
                "session-A",
                "--continuation-mode",
                "legacy_resume",
                "--callback-timeout-minutes",
                "12",
            ])
            with mock.patch.object(cli, "run_codex_callback_preflight", return_value={
                "status": "PASS",
                "session_id": "session-A",
                "validated_target_id": "session-A",
                "executable": "codex-test",
            }) as preflight_mock, mock.patch.object(cli, "launch_detached", return_value=4343):
                self.assertEqual(cli.launch(args), 0)
            preflight_mock.assert_called_once_with("session-A", project_root=str(ROOT))
            manifest = load_manifest(run_dir)
            self.assertEqual(manifest.codex_session_id, "session-A")
            self.assertEqual(manifest.codex_session_source, "explicit")
            self.assertEqual(manifest.callback_timeout_minutes, 12.0)
            self.assertEqual(manifest.callback_preflight["status"], "PASS")
            self.assertTrue(manifest.callback_enabled)
            self.assertTrue(manifest.review_after_completion)
            self.assertEqual(
                manifest.command[manifest.command.index("--config") + 1],
                str((ROOT / "configs/studies/hybrid_stage4b_comparison.yaml").resolve()),
            )

    def test_preflight_failure_prevents_run_creation_and_worker_launch(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "blocked-before-launch"
            args = cli.build_parser().parse_args([
                "launch", "--config", "configs/base/b28_dms_baseline.yaml",
                "--run-dir", str(run_dir), "--session-id", "session-A",
                "--continuation-mode", "legacy_resume",
            ])
            with mock.patch.object(
                cli, "run_codex_callback_preflight", side_effect=RuntimeError("preflight denied"),
            ), mock.patch.object(cli, "launch_detached") as launch_mock:
                with self.assertRaisesRegex(RuntimeError, "preflight denied"):
                    cli.launch(args)
            launch_mock.assert_not_called()
            self.assertFalse(run_dir.exists())

    def test_two_explicit_sessions_are_fixed_to_separate_manifests(self):
        with TemporaryDirectory() as temporary:
            run_a = Path(temporary) / "run-a"
            run_b = Path(temporary) / "run-b"
            args_a = cli.build_parser().parse_args([
                "launch", "--config", "configs/base/b28_dms_baseline.yaml",
                "--run-dir", str(run_a), "--session-id", "session-A",
                "--continuation-mode", "legacy_resume",
            ])
            args_b = cli.build_parser().parse_args([
                "launch", "--config", "configs/base/b28_dms_baseline.yaml",
                "--run-dir", str(run_b), "--session-id", "session-B",
                "--continuation-mode", "legacy_resume",
            ])
            with mock.patch.object(
                cli,
                "run_codex_callback_preflight",
                side_effect=lambda session_id, **kwargs: {
                    "status": "PASS",
                    "session_id": session_id,
                    "validated_target_id": session_id,
                    "executable": "codex-test",
                },
            ), mock.patch.object(cli, "launch_detached", side_effect=[5001, 5002]):
                self.assertEqual(cli.launch(args_a), 0)
                self.assertEqual(cli.launch(args_b), 0)
            self.assertEqual(load_manifest(run_a).codex_session_id, "session-A")
            self.assertEqual(load_manifest(run_b).codex_session_id, "session-B")

    def test_launch_records_durable_session_checkpoint(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "checkpointed"
            args = cli.build_parser().parse_args([
                "launch", "--config", "configs/base/b28_dms_baseline.yaml",
                "--run-dir", str(run_dir), "--no-callback",
            ])
            with mock.patch.object(cli, "launch_detached", return_value=4344):
                self.assertEqual(cli.launch(args), 0)
            checkpoint = json.loads((run_dir / "session_checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["mode"], "launch")
            self.assertEqual(checkpoint["resume_count"], 0)
            self.assertEqual(load_status(run_dir)["session_checkpoint_path"], str(run_dir / "session_checkpoint.json"))

    def test_resume_active_run_reattaches_without_starting_duplicate_worker(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "active"
            create_run(RunManifest(
                schema_version=1, run_id="active", experiment_name="dummy",
                created_at=datetime.now(timezone.utc).isoformat(),
                project_root=str(run_dir), run_dir=str(run_dir), command=["dummy"],
                config_path=None, codex_session_id=None, codex_model=None,
                callback_enabled=False, review_after_completion=False,
            ))
            transition(run_dir, "STARTING", worker_pid=123)
            transition(run_dir, "RUNNING", optimizer_pid=456)
            args = cli.build_parser().parse_args([
                "launch", "--config", "configs/base/b28_dms_baseline.yaml",
                "--run-dir", str(run_dir), "--resume", "--no-callback",
            ])
            with mock.patch.object(cli, "pid_exists", side_effect=lambda pid: pid in {123, 456}), \
                    mock.patch.object(cli, "launch_detached") as launch_mock:
                self.assertEqual(cli.launch(args), 0)
            launch_mock.assert_not_called()
            self.assertEqual(load_status(run_dir)["resume_count"], 1)

    def test_resume_orphan_restarts_worker_with_resume_flag(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "orphan"
            create_run(RunManifest(
                schema_version=1, run_id="orphan", experiment_name="dummy",
                created_at=datetime.now(timezone.utc).isoformat(),
                project_root=str(run_dir), run_dir=str(run_dir), command=["dummy"],
                config_path=None, codex_session_id=None, codex_model=None,
                callback_enabled=False, review_after_completion=False,
            ))
            transition(run_dir, "STARTING", worker_pid=999999)
            transition(run_dir, "ORPHANED", error="test")
            args = cli.build_parser().parse_args([
                "launch", "--config", "configs/base/b28_dms_baseline.yaml",
                "--run-dir", str(run_dir), "--resume", "--no-callback",
            ])
            with mock.patch.object(cli, "launch_detached", return_value=7878) as launch_mock:
                self.assertEqual(cli.launch(args), 0)
            command = launch_mock.call_args.kwargs["command"]
            self.assertIn("--resume", command)
            self.assertEqual(load_status(run_dir)["state"], "STARTING")

    def test_resume_keeps_the_manifest_optimizer_output_directory(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "orphan-v2"
            optimizer_dir = run_dir / "optimizer"
            create_run(RunManifest(
                schema_version=2, run_id="orphan-v2", experiment_name="dummy",
                created_at=datetime.now(timezone.utc).isoformat(),
                project_root=str(run_dir), run_dir=str(run_dir),
                optimizer_run_dir=str(optimizer_dir),
                command=["study", "--run", str(optimizer_dir)],
                config_path=None, codex_session_id=None, codex_model=None,
                callback_enabled=False, review_after_completion=False,
            ))
            transition(run_dir, "STARTING", worker_pid=999999)
            transition(run_dir, "ORPHANED", error="test")
            args = cli.build_parser().parse_args([
                "launch", "--config", "configs/base/b28_dms_baseline.yaml",
                "--run-dir", str(run_dir), "--resume", "--no-callback",
            ])
            with mock.patch.object(cli, "launch_detached", return_value=7879) as launch_mock:
                self.assertEqual(cli.launch(args), 0)
            command = launch_mock.call_args.kwargs["command"]
            self.assertIn("--resume", command)
            self.assertEqual(load_manifest(run_dir).effective_optimizer_run_dir, str(optimizer_dir))

    def test_resume_refuses_completed_review_waiting_run_without_mutating_it(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "review-waiting"
            create_run(RunManifest(
                schema_version=2, run_id="review-waiting", experiment_name="dummy",
                created_at=datetime.now(timezone.utc).isoformat(),
                project_root=str(run_dir), run_dir=str(run_dir),
                optimizer_run_dir=str(run_dir / "optimizer"), command=["dummy"],
                config_path=None, codex_session_id=None, codex_model=None,
                callback_enabled=False, review_after_completion=False,
            ))
            transition(run_dir, "STARTING")
            transition(run_dir, "RUNNING")
            transition(run_dir, "REVIEW_WAITING", exit_code=0)
            args = cli.build_parser().parse_args([
                "launch", "--config", "unused.yaml", "--run-dir", str(run_dir),
                "--resume", "--no-callback",
            ])
            before = load_status(run_dir)
            with mock.patch.object(cli, "launch_detached") as launch_mock:
                with self.assertRaisesRegex(ValueError, "cannot be resumed from state REVIEW_WAITING"):
                    cli.launch(args)
            launch_mock.assert_not_called()
            self.assertEqual(load_status(run_dir), before)

    def test_session_id_cannot_be_silently_ignored_when_callback_is_disabled(self):
        args = cli.build_parser().parse_args([
            "launch",
            "--config",
            "configs/base/b28_dms_baseline.yaml",
            "--session-id",
            "session-A",
            "--no-callback",
        ])
        with self.assertRaisesRegex(ValueError, "--session-id.*--no-callback"):
            cli.launch(args)

    def test_recover_marks_dead_worker_as_orphaned(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "orphaned"
            create_run(RunManifest(
                schema_version=1,
                run_id="orphaned",
                experiment_name="dummy",
                created_at=datetime.now(timezone.utc).isoformat(),
                project_root=str(run_dir),
                run_dir=str(run_dir),
                command=["dummy"],
                config_path=None,
                codex_session_id=None,
                codex_model=None,
                callback_enabled=False,
                review_after_completion=False,
            ))
            transition(run_dir, "STARTING", worker_pid=999999)
            with mock.patch.object(cli, "pid_exists", return_value=False):
                self.assertEqual(cli.recover(Namespace(run_id=str(run_dir))), 0)
            self.assertEqual(load_status(run_dir)["state"], "ORPHANED")

    def test_recover_detects_live_optimizer_with_dead_worker(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "orphaned-child"
            create_run(RunManifest(
                schema_version=1,
                run_id="orphaned-child",
                experiment_name="dummy",
                created_at=datetime.now(timezone.utc).isoformat(),
                project_root=str(run_dir),
                run_dir=str(run_dir),
                command=["dummy"],
                config_path=None,
                codex_session_id=None,
                codex_model=None,
                callback_enabled=False,
                review_after_completion=False,
            ))
            transition(run_dir, "STARTING", worker_pid=111, optimizer_pid=222)
            with mock.patch.object(cli, "pid_exists", side_effect=[False, True]):
                self.assertEqual(cli.recover(Namespace(run_id=str(run_dir))), 0)
            status = load_status(run_dir)
            self.assertEqual(status["state"], "ORPHANED_CHILD")
            self.assertIn("automatic rerun is forbidden", status["error"])

    def test_review_manually_retries_callback_without_rerunning_optimizer(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "manual-review"
            create_run(RunManifest(
                schema_version=1,
                run_id="manual-review",
                experiment_name="dummy",
                created_at=datetime.now(timezone.utc).isoformat(),
                project_root=str(run_dir),
                run_dir=str(run_dir),
                command=["dummy"],
                config_path=None,
                codex_session_id="session-review",
                codex_model=None,
                callback_enabled=True,
                review_after_completion=True,
            ))
            transition(run_dir, "STARTING", worker_pid=123)
            transition(run_dir, "RUNNING")
            transition(run_dir, "COMPLETED", exit_code=0)
            self.assertTrue(cli.prepare_callback(run_dir, automatic=True))
            cli.finish_callback(run_dir, success=False, exit_code=9, error="smoke failure")
            args = Namespace(run_id=str(run_dir), codex_executable="codex-test")
            with mock.patch.object(cli, "run_codex_callback", return_value=0) as callback_mock:
                self.assertEqual(cli.review(args), 0)
            callback_mock.assert_called_once()
            status = load_status(run_dir)
            self.assertEqual(status["state"], "REVIEWED")
            self.assertEqual(status["optimizer_state"], "COMPLETED")
            self.assertEqual(status["callback_attempts"], 2)

    def test_recover_reclaims_stale_callback_lock_without_rerunning_optimizer(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "stale-callback"
            create_run(RunManifest(
                schema_version=1,
                run_id="stale-callback",
                experiment_name="dummy",
                created_at=datetime.now(timezone.utc).isoformat(),
                project_root=str(run_dir),
                run_dir=str(run_dir),
                command=["dummy"],
                config_path=None,
                codex_session_id="session-stale",
                codex_model=None,
                callback_enabled=True,
                review_after_completion=True,
            ))
            transition(run_dir, "STARTING", worker_pid=123)
            transition(run_dir, "RUNNING")
            transition(run_dir, "COMPLETED", exit_code=0)
            self.assertTrue(cli.prepare_callback(run_dir, automatic=True))
            atomic_write_json(callback_lock_path(run_dir), {
                "pid": 99999999,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "hostname": "dead-host",
            })

            self.assertEqual(cli.recover(Namespace(run_id=str(run_dir))), 0)
            status = load_status(run_dir)
            self.assertEqual(status["state"], "CALLBACK_FAILED")
            self.assertFalse(callback_lock_path(run_dir).exists())


if __name__ == "__main__":
    unittest.main()
