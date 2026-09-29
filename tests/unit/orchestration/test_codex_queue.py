import json
import os
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from sawopt.orchestration import cli, codex_queue
from sawopt.orchestration.models import RunManifest
from sawopt.orchestration.process_runner import launch_detached, pid_exists
from sawopt.orchestration.run_manager import (
    claim_queue_delivery,
    confirm_queue_delivery,
    continuation_delivery_path,
    create_run,
    load_continuation_delivery,
    load_manifest,
    load_status,
    mark_queue_command_started,
    optimizer_completion_path,
    record_optimizer_completion,
    record_queue_sender_result,
    transition,
)


THREAD_ID = "01a0e89c-1c65-72a3-beb6-489f0cf01b30"
TASK_ID = "c2c_test_queue"
SENTINEL = "a" * 32


def _preflight(executable: str | None = None) -> dict:
    return {
        "status": "PASS",
        "thread_id": THREAD_ID,
        "effective_user": "test-user",
        "user_profile": "C:/Users/test-user",
        "windows_user_profile": "C:/Users/test-user",
        "codex_executable": executable or str(Path(sys.executable).resolve()),
        "codex_version": "codex-test 1.0",
        "explicit_thread": True,
        "explicit_message": True,
    }


def _create_queue_run(run_dir: Path, *, command: list[str] | None = None) -> Path:
    manifest = RunManifest(
        schema_version=3,
        run_id="queue-test-run",
        experiment_name="synthetic-queue-fixture",
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        project_root=str(run_dir.parent.resolve()),
        run_dir=str(run_dir.resolve()),
        optimizer_run_dir=str((run_dir / "optimizer").resolve()),
        command=command or [sys.executable, "-c", "pass"],
        config_path=None,
        codex_session_id=None,
        codex_model=None,
        callback_enabled=False,
        review_after_completion=True,
        continuation_mode="queue",
        original_thread_id=THREAD_ID,
        c2c_task_id=TASK_ID,
        plan_iteration=2,
        next_expected_step="validate the detached fixture receipt",
        delivery_sentinel=SENTINEL,
        queue_preflight=_preflight(),
        queue_timeout_seconds=10.0,
    )
    create_run(manifest)
    return run_dir


def _mark_review_waiting(run_dir: Path) -> None:
    transition(run_dir, "STARTING")
    transition(run_dir, "RUNNING")
    transition(run_dir, "REVIEW_WAITING", exit_code=0)
    record_optimizer_completion(run_dir, disposition="REVIEW_WAITING", exit_code=0)


class CodexQueueTests(unittest.TestCase):
    def test_queue_command_uses_only_the_exact_thread_and_small_message(self):
        with TemporaryDirectory() as temporary:
            run_dir = _create_queue_run(Path(temporary) / "run")
            manifest = load_manifest(run_dir)
            message = codex_queue.build_queue_message(
                manifest, delivery_id="f" * 32,
            )
            command = codex_queue.build_queue_command(
                THREAD_ID, message, codex_executable="codex.exe",
            )

        self.assertEqual(command[:4], ["codex.exe", "queue", "--thread", THREAD_ID])
        self.assertEqual(command[4], "--message")
        self.assertEqual(command[5], message)
        self.assertNotIn("--last", command)
        self.assertLessEqual(len(message.encode("utf-8")), 1024)
        self.assertIn("TASK_ID: c2c_test_queue", message)
        self.assertIn("NEXT_EXPECTED_STEP: validate the detached fixture receipt", message)
        self.assertIn(f"DELIVERY_ID: {'f' * 32}", message)
        self.assertIn(f"DELIVERY_SENTINEL: {SENTINEL}", message)

    def test_runtime_thread_identity_fails_closed_without_runtime_environment(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                codex_queue.CodexQueuePreflightError, "CODEX_THREAD_ID",
            ):
                codex_queue.current_codex_thread_id()

    def test_queue_preflight_checks_cli_version_and_explicit_help_flags(self):
        calls = []

        def runner(command, **_kwargs):
            calls.append(command)
            if command[1:] == ["--version"]:
                return SimpleNamespace(returncode=0, stdout="codex-test 1.2\n", stderr="")
            return SimpleNamespace(
                returncode=0, stdout="queue --thread THREAD --message MESSAGE", stderr="",
            )

        with mock.patch.object(codex_queue, "_identity_snapshot", return_value={
            "effective_user": "test-user",
            "user_profile": "C:/Users/test-user",
            "windows_user_profile": "C:/Users/test-user",
        }), mock.patch.object(codex_queue, "_resolve_executable", return_value="codex.exe"):
            result = codex_queue.run_codex_queue_preflight(
                THREAD_ID, project_root=".", runner=runner,
            )

        self.assertEqual([item[1:] for item in calls], [["--version"], ["queue", "--help"]])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["thread_id"], THREAD_ID)
        self.assertTrue(result["explicit_thread"])
        self.assertTrue(result["explicit_message"])
        self.assertEqual(result["codex_version"], "codex-test 1.2")

    def test_queue_preflight_fails_closed_when_normal_profile_check_fails(self):
        runner = mock.Mock()
        with mock.patch.object(
            codex_queue, "_identity_snapshot",
            side_effect=codex_queue.CodexQueuePreflightError("unqualified user profile"),
        ):
            with self.assertRaisesRegex(codex_queue.CodexQueuePreflightError, "unqualified"):
                codex_queue.run_codex_queue_preflight(
                    THREAD_ID, project_root=".", codex_executable="codex.exe", runner=runner,
                )
        runner.assert_not_called()

    def test_legacy_manifest_without_queue_fields_remains_readable(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "legacy"
            manifest = RunManifest(
                schema_version=2, run_id="legacy", experiment_name="old",
                created_at=datetime.now(timezone.utc).isoformat(),
                project_root=str(run_dir), run_dir=str(run_dir),
                optimizer_run_dir=str(run_dir / "optimizer"), command=["dummy"],
                config_path=None, codex_session_id="session-old", codex_model=None,
                callback_enabled=True, review_after_completion=True,
            )
            old_data = manifest.to_dict()
            for key in (
                "continuation_mode", "original_thread_id", "c2c_task_id", "plan_iteration",
                "next_expected_step", "delivery_sentinel", "queue_preflight",
                "queue_timeout_seconds",
            ):
                old_data.pop(key, None)
            loaded = RunManifest.from_dict(old_data)

        self.assertEqual(loaded.continuation_mode, "legacy_resume")
        self.assertEqual(loaded.codex_session_id, "session-old")
        self.assertTrue(loaded.callback_enabled)

    def test_schema_three_requires_explicit_continuation_mode_and_queue_version(self):
        with TemporaryDirectory() as temporary:
            run_dir = _create_queue_run(Path(temporary) / "schema-validation")
            manifest_data = load_manifest(run_dir).to_dict()

        missing_mode = dict(manifest_data)
        missing_mode.pop("continuation_mode")
        with self.assertRaisesRegex(ValueError, "requires an explicit continuation_mode"):
            RunManifest.from_dict(missing_mode)

        unsupported_queue_version = dict(manifest_data)
        unsupported_queue_version["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "requires schema version 3"):
            RunManifest.from_dict(unsupported_queue_version)

        invalid_mode = dict(manifest_data)
        invalid_mode["continuation_mode"] = "unknown"
        with self.assertRaisesRegex(ValueError, "unknown continuation mode"):
            RunManifest.from_dict(invalid_mode)

    def test_queue_manifest_persists_exact_receiver_and_c2c_checkpoint(self):
        with TemporaryDirectory() as temporary:
            run_dir = _create_queue_run(Path(temporary) / "queue")
            manifest = load_manifest(run_dir)

        self.assertEqual(manifest.schema_version, 3)
        self.assertEqual(manifest.original_thread_id, THREAD_ID)
        self.assertEqual(manifest.c2c_task_id, TASK_ID)
        self.assertEqual(manifest.plan_iteration, 2)
        self.assertEqual(manifest.next_expected_step, "validate the detached fixture receipt")
        self.assertEqual(manifest.delivery_sentinel, SENTINEL)
        self.assertFalse(manifest.callback_enabled)
        self.assertTrue(manifest.review_after_completion)

    def test_atomic_claim_allows_only_one_concurrent_sender(self):
        with TemporaryDirectory() as temporary:
            run_dir = _create_queue_run(Path(temporary) / "race")
            _mark_review_waiting(run_dir)

            def attempt():
                try:
                    claim_queue_delivery(run_dir)
                    return "claimed"
                except ValueError:
                    return "rejected"

            with ThreadPoolExecutor(max_workers=8) as pool:
                outcomes = list(pool.map(lambda _index: attempt(), range(8)))

            self.assertEqual(outcomes.count("claimed"), 1)
            self.assertEqual(outcomes.count("rejected"), 7)
            self.assertTrue(continuation_delivery_path(run_dir).is_file())
            self.assertEqual(load_continuation_delivery(run_dir)["attempt_count"], 1)

    def test_sender_acceptance_and_receiver_confirmation_are_idempotent(self):
        with TemporaryDirectory() as temporary:
            run_dir = _create_queue_run(Path(temporary) / "delivered")
            _mark_review_waiting(run_dir)
            claim = claim_queue_delivery(run_dir)
            mark_queue_command_started(run_dir)
            record_queue_sender_result(run_dir, exit_code=0)

            with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": THREAD_ID}):
                receipt = confirm_queue_delivery(
                    run_dir,
                    task_id=TASK_ID,
                    run_id="queue-test-run",
                    delivery_id=claim["delivery_id"],
                    delivery_sentinel=SENTINEL,
                )
                repeated = confirm_queue_delivery(
                    run_dir,
                    task_id=TASK_ID,
                    run_id="queue-test-run",
                    delivery_id=claim["delivery_id"],
                    delivery_sentinel=SENTINEL,
                )
            status = load_status(run_dir)

        self.assertEqual(receipt["state"], "RECEIVER_CONFIRMED")
        self.assertEqual(repeated["delivery_id"], receipt["delivery_id"])
        self.assertEqual(status["state"], "REVIEW_WAITING")
        self.assertEqual(status["optimizer_state"], "REVIEW_WAITING")
        self.assertEqual(status["continuation_state"], "RECEIVER_CONFIRMED")

    def test_receiver_rejects_wrong_thread_task_or_sentinel(self):
        with TemporaryDirectory() as temporary:
            run_dir = _create_queue_run(Path(temporary) / "wrong-receiver")
            _mark_review_waiting(run_dir)
            claim = claim_queue_delivery(run_dir)
            mark_queue_command_started(run_dir)
            cases = (
                ("01a0e89c-1c65-72a3-beb6-489f0cf01b31", TASK_ID,
                 claim["delivery_id"], SENTINEL),
                (THREAD_ID, "other-task", claim["delivery_id"], SENTINEL),
                (THREAD_ID, TASK_ID, claim["delivery_id"], "b" * 32),
                (THREAD_ID, TASK_ID, "0" * 32, SENTINEL),
            )
            for fields in cases:
                runtime_thread, task_id, delivery_id, sentinel = fields
                with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": runtime_thread}):
                    with self.assertRaises(ValueError):
                        confirm_queue_delivery(
                            run_dir, task_id=task_id, run_id="queue-test-run",
                            delivery_id=delivery_id, delivery_sentinel=sentinel,
                        )

    def test_verify_queue_ignores_caller_thread_id_and_requires_runtime_identity(self):
        with TemporaryDirectory() as temporary:
            run_dir = _create_queue_run(Path(temporary) / "untrusted-thread")
            _mark_review_waiting(run_dir)
            claim = claim_queue_delivery(run_dir)
            mark_queue_command_started(run_dir)
            record_queue_sender_result(run_dir, exit_code=0)
            args = SimpleNamespace(
                run_ref=str(run_dir), run_id="queue-test-run", task_id=TASK_ID,
                delivery_id=claim["delivery_id"], delivery_sentinel=SENTINEL,
                # Even a caller-provided correct UUID is not accepted as proof.
                thread_id=THREAD_ID,
            )
            for runtime_thread in (None, "01a0e89c-1c65-72a3-beb6-489f0cf01b31"):
                environment = {} if runtime_thread is None else {
                    "CODEX_THREAD_ID": runtime_thread,
                }
                with mock.patch.dict(os.environ, environment, clear=True):
                    expected = (
                        codex_queue.CodexQueuePreflightError
                        if runtime_thread is None else ValueError
                    )
                    with self.assertRaises(expected):
                        cli.verify_queue(args)
            delivery = load_continuation_delivery(run_dir)

        self.assertEqual(delivery["state"], "SENDER_ACCEPTED")
        self.assertIsNone(delivery["receiver_confirmed_at"])

    def test_verify_queue_separates_custom_run_path_from_manifest_run_id(self):
        with TemporaryDirectory() as temporary:
            run_dir = _create_queue_run(Path(temporary) / "custom-directory-name")
            _mark_review_waiting(run_dir)
            claim = claim_queue_delivery(run_dir)
            mark_queue_command_started(run_dir)
            record_queue_sender_result(run_dir, exit_code=0)

            common_args = [
                "verify-queue", str(run_dir), "--run-id", "queue-test-run",
                "--task-id", TASK_ID, "--delivery-id", claim["delivery_id"],
                "--delivery-sentinel", SENTINEL,
            ]
            wrong_id_args = cli.build_parser().parse_args([
                *common_args[:2], "--run-id", "different-manifest-id", *common_args[4:],
            ])
            with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": THREAD_ID}):
                with self.assertRaisesRegex(ValueError, "task/run identity"):
                    cli.verify_queue(wrong_id_args)
                self.assertEqual(load_continuation_delivery(run_dir)["state"], "SENDER_ACCEPTED")

                correct_args = cli.build_parser().parse_args(common_args)
                self.assertEqual(cli.verify_queue(correct_args), 0)
            delivery = load_continuation_delivery(run_dir)

        self.assertNotEqual(run_dir.name, "queue-test-run")
        self.assertEqual(delivery["state"], "RECEIVER_CONFIRMED")
        self.assertEqual(delivery["delivery_id"], claim["delivery_id"])

    def test_ambiguous_queue_attempt_is_durable_and_never_retried(self):
        with TemporaryDirectory() as temporary:
            run_dir = _create_queue_run(Path(temporary) / "ambiguous")
            _mark_review_waiting(run_dir)
            queue_calls = []

            def queue_runner(command, **_kwargs):
                queue_calls.append(command)
                ledger = load_continuation_delivery(run_dir)
                self.assertEqual(ledger["state"], "CLAIMED")
                self.assertIn(f"DELIVERY_ID: {ledger['delivery_id']}", command[-1])
                raise subprocess.TimeoutExpired("codex queue", 1)

            with mock.patch.object(
                codex_queue, "run_codex_queue_preflight", return_value=_preflight(),
            ):
                result = codex_queue.send_queue_continuation(
                    run_dir,
                    queue_runner=queue_runner,
                    timeout_s=1,
                )
                with self.assertRaisesRegex(ValueError, "resend is forbidden"):
                    codex_queue.send_queue_continuation(
                        run_dir, queue_runner=queue_runner, timeout_s=1,
                    )
            status = load_status(run_dir)
            completion = json.loads(optimizer_completion_path(run_dir).read_text())

        self.assertEqual(result["state"], "AMBIGUOUS")
        self.assertEqual(result["attempt_count"], 1)
        self.assertEqual(len(queue_calls), 1)
        self.assertIn("queue", queue_calls[0])
        self.assertEqual(status["state"], "REVIEW_WAITING")
        self.assertEqual(status["optimizer_state"], "REVIEW_WAITING")
        self.assertEqual(completion["disposition"], "REVIEW_WAITING")

    def test_post_claim_message_failure_consumes_attempt_without_spawning_sender(self):
        with TemporaryDirectory() as temporary:
            run_dir = _create_queue_run(Path(temporary) / "message-failure")
            _mark_review_waiting(run_dir)
            queue_runner = mock.Mock()
            with mock.patch.object(
                codex_queue, "run_codex_queue_preflight", return_value=_preflight(),
            ), mock.patch.object(
                codex_queue, "build_queue_message", side_effect=ValueError("bad message"),
            ):
                result = codex_queue.send_queue_continuation(
                    run_dir, queue_runner=queue_runner,
                )
            delivery = load_continuation_delivery(run_dir)

        self.assertEqual(result["state"], "AMBIGUOUS")
        self.assertEqual(result["attempt_count"], 1)
        self.assertIsNone(delivery["command_started_at"])
        self.assertEqual(delivery["state"], "AMBIGUOUS")
        queue_runner.assert_not_called()

    def test_worker_queue_success_and_failure_preserve_review_waiting_checkpoints(self):
        from sawopt.orchestration.worker import execute_run

        for queue_exit in (0, 7):
            with self.subTest(queue_exit=queue_exit), TemporaryDirectory() as temporary:
                root = Path(temporary)
                run_dir = root / "worker-run"
                script = (
                    "import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); "
                    "p.mkdir(parents=True,exist_ok=True); "
                    "(p/'run_completion.json').write_text(json.dumps({'status':'REVIEW_WAITING',"
                    "'disposition':'REVIEW_WAITING'}),encoding='utf-8')"
                )
                _create_queue_run(
                    run_dir,
                    command=[sys.executable, "-c", script, str(run_dir / "optimizer" / "metadata")],
                )
                from sawopt.io.checkpoints import CheckpointStore
                store = CheckpointStore(
                    run_dir / "optimizer" / "checkpoints",
                    run_directory=run_dir / "optimizer",
                )
                store.write(lambda path: path.write_text('{"n":1}', encoding="utf-8"))
                store.write(lambda path: path.write_text('{"n":2}', encoding="utf-8"))

                fake_queue = lambda *_args, **_kwargs: SimpleNamespace(
                    returncode=queue_exit, stdout="", stderr="simulated",
                )
                with mock.patch.object(
                    codex_queue, "run_codex_queue_preflight", return_value=_preflight(),
                ):
                    status = execute_run(run_dir, queue_runner=fake_queue)

                delivery = load_continuation_delivery(run_dir)
                self.assertEqual(status["state"], "REVIEW_WAITING")
                self.assertEqual(status["optimizer_state"], "REVIEW_WAITING")
                self.assertTrue(store.latest_path.is_file())
                self.assertTrue(store.previous_path.is_file())
                self.assertFalse(store.final_path.exists())
                self.assertEqual(delivery["state"], "SENDER_ACCEPTED" if queue_exit == 0 else "AMBIGUOUS")

    @unittest.skipIf(os.name != "nt", "detached Windows identity shim qualifies the queue fixture")
    def test_detached_tiny_worker_persists_completion_before_one_fake_queue(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            run_dir = root / "detached-run"
            trace_path = root / "queue-invocation.json"
            fake_queue = root / "queue"
            fake_queue.write_text(
                "import json,os,sys\n"
                "if '--help' in sys.argv:\n"
                " print('queue --thread THREAD --message MESSAGE'); raise SystemExit(0)\n"
                "path=os.environ['QUEUE_TEST_TRACE']\n"
                "with open(path,'w',encoding='utf-8') as stream: json.dump(sys.argv[1:],stream)\n"
                "print('queued')\n",
                encoding="utf-8",
            )
            optimizer_script = (
                "import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); "
                "p.mkdir(parents=True,exist_ok=True); "
                "(p/'run_completion.json').write_text(json.dumps({'status':'REVIEW_WAITING',"
                "'disposition':'REVIEW_WAITING'}),encoding='utf-8')"
            )
            _create_queue_run(
                run_dir,
                command=[sys.executable, "-c", optimizer_script, str(run_dir / "optimizer" / "metadata")],
            )
            manifest_path = run_dir / "run_manifest.json"
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_data["project_root"] = str(root)
            pinned_version = subprocess.run(
                [sys.executable, "--version"], capture_output=True, text=True, check=True,
            )
            manifest_data["queue_preflight"] = _preflight(str(Path(sys.executable).resolve()))
            manifest_data["queue_preflight"]["codex_version"] = (
                (pinned_version.stdout or pinned_version.stderr).strip()
            )
            manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")
            helper = root / "detached_worker.py"
            helper.write_text(
                "import sys\n"
                "from sawopt.orchestration import codex_queue\n"
                "root=sys.argv[1]\n"
                "codex_queue._identity_snapshot=lambda: {'effective_user':'test-user',"
                "'user_profile':'C:/Users/test-user','windows_user_profile':'C:/Users/test-user'}\n"
                "from sawopt.orchestration.worker import execute_run\n"
                "execute_run(sys.argv[2])\n",
                encoding="utf-8",
            )
            pid = launch_detached(
                run_dir,
                project_root=root,
                command=[sys.executable, str(helper), str(root), str(run_dir)],
                env={
                    "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src"),
                    "QUEUE_TEST_TRACE": str(trace_path),
                },
            )
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if trace_path.exists() and continuation_delivery_path(run_dir).exists():
                    try:
                        current_delivery = load_continuation_delivery(run_dir)
                    except (OSError, ValueError, json.JSONDecodeError):
                        current_delivery = None
                    status = load_status(run_dir)
                    if (
                        current_delivery is not None
                        and current_delivery.get("state") == "SENDER_ACCEPTED"
                        and not pid_exists(status.get("worker_pid"))
                    ):
                        break
                time.sleep(0.1)

            if not trace_path.exists():
                status_path = run_dir / "status.json"
                status = status_path.read_text(encoding="utf-8") if status_path.exists() else "missing status"
                stderr = (run_dir / "stderr.log").read_text(encoding="utf-8")
                stdout = (run_dir / "stdout.log").read_text(encoding="utf-8")
                self.fail(
                    f"detached worker PID {pid} did not queue; status={status}; "
                    f"stdout={stdout}; stderr={stderr}"
                )
            args = json.loads(trace_path.read_text(encoding="utf-8"))
            completion = json.loads(optimizer_completion_path(run_dir).read_text(encoding="utf-8"))
            delivery = load_continuation_delivery(run_dir)
            self.assertEqual(args[0], "--thread")
            self.assertEqual(args[1], THREAD_ID)
            self.assertEqual(args[2], "--message")
            self.assertIn("RUN_ID: queue-test-run", args[3])
            self.assertEqual(completion["disposition"], "REVIEW_WAITING")
            self.assertEqual(delivery["attempt_count"], 1)
            self.assertEqual(delivery["state"], "SENDER_ACCEPTED")


if __name__ == "__main__":
    unittest.main()
