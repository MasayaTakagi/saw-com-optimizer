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
    create_run,
    load_manifest,
    load_status,
    transition,
)


ROOT = Path(__file__).resolve().parents[3]


def _clean_git_snapshot(command, **_kwargs):
    if command[:2] == ["git", "branch"]:
        return "codex/test-branch\n"
    if command[:2] == ["git", "rev-parse"]:
        return "a" * 40 + "\n"
    if command[:2] == ["git", "status"]:
        return ""
    raise AssertionError(f"unexpected git command: {command}")


class CliTests(unittest.TestCase):
    def test_launch_creates_manifest_and_returns_without_waiting(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "async-run"
            args = cli.build_parser().parse_args([
                "launch",
                "--config",
                "configs/studies/postrun_workflow_qualification.yaml",
                "--run-dir",
                str(run_dir),
                "--continuation-mode", "disabled",
            ])
            with mock.patch.object(cli.subprocess, "check_output", side_effect=_clean_git_snapshot), \
                    mock.patch.object(cli, "launch_detached", return_value=4242) as launch_mock:
                self.assertEqual(cli.launch(args), 0)
            launch_mock.assert_called_once()
            manifest = load_manifest(run_dir)
            status = load_status(run_dir)
            self.assertEqual(status["state"], "STARTING")
            self.assertEqual(status["worker_pid"], 4242)
            self.assertFalse(manifest.callback_enabled)
            self.assertIn("run-study", manifest.command)
            self.assertEqual(manifest.schema_version, 4)
            self.assertEqual(manifest.continuation_mode, "disabled")
            self.assertIsNone(manifest.codex_session_id)
            self.assertEqual(manifest.review_stage, "qualification")
            self.assertEqual(manifest.effective_optimizer_run_dir, str(run_dir / "optimizer"))
            self.assertEqual(manifest.command[manifest.command.index("--run") + 1], str(run_dir / "optimizer"))

    def test_new_launch_rejects_session_id_instead_of_reinterpreting_as_thread(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "explicit-session"
            with self.assertRaisesRegex(RuntimeError, "retired"):
                cli.main([
                    "launch", "--config", "configs/studies/postrun_workflow_qualification.yaml",
                    "--run-dir", str(run_dir), "--session-id", "session-A",
                ])
            self.assertFalse(run_dir.exists())

    def test_queue_launch_is_rejected_before_run_creation_or_worker_launch(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "blocked-before-launch"
            with mock.patch.object(cli, "launch_detached") as launch_mock:
                with self.assertRaisesRegex(RuntimeError, "queue continuation is retired"):
                    cli.main([
                        "launch", "--config", "configs/studies/postrun_workflow_qualification.yaml",
                        "--run-dir", str(run_dir), "--continuation-mode", "queue",
                    ])
            launch_mock.assert_not_called()
            self.assertFalse(run_dir.exists())

    def test_removed_session_options_are_rejected_before_run_creation(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            with self.assertRaisesRegex(RuntimeError, "retired"):
                cli.main([
                    "launch", "--config", "configs/studies/postrun_workflow_qualification.yaml",
                    "--run-dir", str(run_dir), "--session-id", "session-A",
                ])
            self.assertFalse(run_dir.exists())

    def test_new_v4_launch_does_not_store_a_session_checkpoint(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "checkpointed"
            args = cli.build_parser().parse_args([
                "launch", "--config", "configs/studies/postrun_workflow_qualification.yaml",
                "--run-dir", str(run_dir), "--continuation-mode", "disabled",
            ])
            with mock.patch.object(cli.subprocess, "check_output", side_effect=_clean_git_snapshot), \
                    mock.patch.object(cli, "launch_detached", return_value=4344):
                self.assertEqual(cli.launch(args), 0)
            self.assertFalse((run_dir / "session_checkpoint.json").exists())
            self.assertIsNone(load_status(run_dir)["session_checkpoint_path"])

    def test_authorized_production_launch_records_external_storage_provenance(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {"study": {
                "type": "postrun_workflow_qualification",
                "user_authorized_production": True,
                "comparison_arms": ["fixture"], "seeds": [1],
                "review_spec_id": "postrun_workflow_qualification",
            }}
            args = cli.build_parser().parse_args([
                "launch", "--config", "configs/studies/postrun_workflow_qualification.yaml",
                "--run-root", str(root), "--continuation-mode", "disabled",
            ])
            with mock.patch("sawopt.io.config.load_experiment_config", return_value=payload), \
                    mock.patch.object(cli.subprocess, "check_output", side_effect=_clean_git_snapshot), \
                    mock.patch.object(cli, "register_active_run") as register_mock, \
                    mock.patch.object(cli, "launch_detached", return_value=5656) as launch_mock:
                self.assertEqual(cli.launch(args), 0)
            launch_mock.assert_called_once()
            register_mock.assert_called_once()
            self.assertEqual(register_mock.call_args.kwargs["source_head"], "a" * 40)
            self.assertEqual(register_mock.call_args.kwargs["source_branch"], "codex/test-branch")
            manifest_path = Path(launch_mock.call_args.args[0]) / "run_manifest.json"
            manifest = load_manifest(manifest_path.parent)
            self.assertEqual(manifest.run_storage_policy, "external_persistent_v1")
            self.assertEqual(Path(manifest.persistent_run_root), root.resolve())
            self.assertEqual(Path(manifest.run_dir).parent, root.resolve())
            self.assertEqual(Path(manifest.repository_root_at_launch), ROOT.resolve())
            self.assertEqual(Path(manifest.source_worktree_at_launch), ROOT.resolve())

    def test_authorized_production_inside_worktree_fails_before_launch(self):
        run_dir = ROOT / "runs" / "blocked-production-storage-test"
        args = cli.build_parser().parse_args([
            "launch", "--config", "configs/studies/postrun_workflow_qualification.yaml",
            "--run-dir", str(run_dir), "--continuation-mode", "disabled",
        ])
        payload = {"study": {
            "type": "postrun_workflow_qualification",
            "user_authorized_production": True,
            "comparison_arms": ["fixture"], "seeds": [1],
            "review_spec_id": "postrun_workflow_qualification",
        }}
        with mock.patch("sawopt.io.config.load_experiment_config", return_value=payload), \
                mock.patch.object(cli, "launch_detached") as launch_mock, \
                mock.patch.object(cli, "create_run") as create_mock:
            with self.assertRaisesRegex(ValueError, "FAIL_INSIDE_WORKTREE"):
                cli.launch(args)
        launch_mock.assert_not_called()
        create_mock.assert_not_called()
        self.assertFalse(run_dir.exists())

    def test_authorized_production_registry_failure_prevents_directory_and_worker(self):
        with TemporaryDirectory() as temporary:
            persistent_root = Path(temporary) / "persistent"
            persistent_root.mkdir()
            payload = {"study": {
                "type": "postrun_workflow_qualification",
                "user_authorized_production": True,
                "comparison_arms": ["fixture"], "seeds": [1],
                "review_spec_id": "postrun_workflow_qualification",
            }}
            args = cli.build_parser().parse_args([
                "launch", "--config", "configs/studies/postrun_workflow_qualification.yaml",
                "--run-root", str(persistent_root), "--continuation-mode", "disabled",
            ])
            with mock.patch("sawopt.io.config.load_experiment_config", return_value=payload), \
                    mock.patch.object(cli.subprocess, "check_output", side_effect=_clean_git_snapshot), \
                    mock.patch.object(cli, "register_active_run", side_effect=RuntimeError("registry unavailable")), \
                    mock.patch.object(cli, "create_run") as create_mock, \
                    mock.patch.object(cli, "launch_detached") as launch_mock:
                with self.assertRaisesRegex(RuntimeError, "registry unavailable"):
                    cli.launch(args)
            create_mock.assert_not_called()
            launch_mock.assert_not_called()
            self.assertEqual(list(persistent_root.iterdir()), [])

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
                "--run-dir", str(run_dir), "--resume", "--continuation-mode", "disabled",
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
                "--run-dir", str(run_dir), "--resume", "--continuation-mode", "disabled",
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
                "--run-dir", str(run_dir), "--resume", "--continuation-mode", "disabled",
            ])
            with mock.patch.object(cli, "launch_detached", return_value=7879) as launch_mock:
                self.assertEqual(cli.launch(args), 0)
            command = launch_mock.call_args.kwargs["command"]
            self.assertIn("--resume", command)
            self.assertEqual(load_manifest(run_dir).effective_optimizer_run_dir, str(optimizer_dir))

    def test_session_cli_option_is_rejected_instead_of_ignored(self):
        with self.assertRaisesRegex(RuntimeError, "retired"):
            cli.main([
                "launch", "--config", "configs/base/b28_dms_baseline.yaml",
                "--session-id", "session-A", "--continuation-mode", "disabled",
            ])

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
            status = load_status(run_dir)
            self.assertEqual(status["state"], "ORPHANED")
            self.assertEqual(status["optimizer_state"], "UNKNOWN")

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

if __name__ == "__main__":
    unittest.main()
