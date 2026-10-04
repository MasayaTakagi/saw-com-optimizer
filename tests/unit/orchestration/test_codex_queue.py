import hashlib
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from sawopt.orchestration import cli, codex_queue
from sawopt.orchestration.models import RunManifest
from sawopt.orchestration.run_manager import (
    claim_queue_delivery,
    confirm_queue_delivery,
    create_run,
    load_continuation_delivery,
    load_status,
    mark_queue_command_started,
    optimizer_completion_path,
    record_optimizer_completion,
    record_queue_sender_result,
    transition,
)
from sawopt.io.lifecycle import RunDisposition
from sawopt.io.checkpoints import complete_study_run


ROOT = Path(__file__).resolve().parents[3]
THREAD = "01a0e89c-1c65-72a3-beb6-489f0cf01b30"
SENTINEL = "a" * 32
DELIVERY = "b" * 32


def _queue_preflight():
    return {
        "status": "PASS", "thread_id": THREAD,
        "effective_user": "test-user", "user_profile": "C:/Users/test-user",
        "windows_user_profile": "C:/Users/test-user",
        "codex_executable": "C:/Codex/codex.exe", "codex_version": "codex-test 1.0",
        "queue_help_sha256": "c" * 64, "explicit_thread": True, "explicit_message": True,
    }


def _manifest(run_dir: Path, *, schema=4, mode="queue"):
    from sawopt.reporting.github_review import _canonical_json_sha256, load_review_spec

    spec = load_review_spec("postrun_workflow_qualification", ROOT)
    return RunManifest(
        schema_version=schema,
        run_id="queue-test-run",
        experiment_name="postrun_workflow_qualification",
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        project_root=str(ROOT), run_dir=str(run_dir.resolve()),
        optimizer_run_dir=str((run_dir / "optimizer").resolve()),
        command=[sys.executable, "-c", "pass"],
        config_path=str(ROOT / "configs/studies/postrun_workflow_qualification.yaml"),
        codex_session_id=None, codex_model=None, callback_enabled=False,
        review_after_completion=(mode == "queue"), continuation_mode=mode,
        original_thread_id=THREAD if mode == "queue" else None,
        c2c_task_id="historical-task" if schema == 3 and mode == "queue" else None,
        plan_iteration=0 if schema == 3 and mode == "queue" else None,
        next_expected_step="publish_review_evidence" if mode == "queue" else None,
        delivery_sentinel=SENTINEL if mode == "queue" else None,
        queue_preflight=_queue_preflight() if mode == "queue" else None,
        queue_timeout_seconds=12.0 if mode == "queue" else None,
        review_stage="qualification", review_contract_version="1",
        review_output_dir=f"reports/experiment_reviews/qualification/queue-test-run",
        review_spec_id="postrun_workflow_qualification",
        review_spec_sha256=_canonical_json_sha256(spec), review_spec=spec,
        source_commit_sha="d" * 40, source_branch="codex/test",
        study_type="postrun_workflow_qualification",
        experiment_metadata={
            "study_type": "postrun_workflow_qualification",
            "comparison_arms": ["fixture"], "seeds": ["qualification"],
            "expected_cell_count": 1, "computation_fingerprint": "e" * 64,
        },
    )


def _completed_run(run_dir: Path, *, schema=4):
    create_run(_manifest(run_dir, schema=schema))
    transition(run_dir, "STARTING")
    transition(run_dir, "RUNNING")
    transition(run_dir, "COMPLETED", exit_code=0)
    record_optimizer_completion(run_dir, disposition="COMPLETED", exit_code=0)
    return run_dir


class CodexQueueTests(unittest.TestCase):
    def test_valid_and_invalid_exact_thread_uuid(self):
        self.assertEqual(codex_queue.validate_thread_id(THREAD.upper()), THREAD)
        with self.assertRaises(ValueError):
            codex_queue.validate_thread_id("not-a-thread")

    def test_receiver_identity_comes_from_runtime_not_cli_argument(self):
        with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": THREAD}):
            self.assertEqual(codex_queue.current_codex_thread_id(), THREAD)
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(codex_queue.CodexQueuePreflightError, "CODEX_THREAD_ID"):
                codex_queue.current_codex_thread_id()

    def test_queue_preflight_requires_explicit_flags_and_pins_executable_version(self):
        calls = []

        def runner(command, **_kwargs):
            calls.append(command)
            self.assertEqual(_kwargs["encoding"], "utf-8")
            self.assertEqual(_kwargs["errors"], "replace")
            if command[1:] == ["--version"]:
                return SimpleNamespace(returncode=0, stdout="codex-test 4.2\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="queue --thread ID --message TEXT", stderr="")

        with mock.patch.object(codex_queue, "_identity_snapshot", return_value={
            "effective_user": "test-user", "user_profile": "C:/Users/test-user",
            "windows_user_profile": "C:/Users/test-user",
        }), mock.patch.object(codex_queue, "_resolve_executable", return_value="C:/Codex/codex.exe"):
            result = codex_queue.run_codex_queue_preflight(THREAD, project_root=ROOT, runner=runner)
        self.assertEqual(result["codex_executable"], "C:/Codex/codex.exe")
        self.assertEqual(result["codex_version"], "codex-test 4.2")
        self.assertTrue(result["explicit_thread"] and result["explicit_message"])
        self.assertEqual(calls[1][1:], ["queue", "--help"])

    def test_queue_preflight_fails_when_help_lacks_exact_flags(self):
        def runner(command, **_kwargs):
            if command[1:] == ["--version"]:
                return SimpleNamespace(returncode=0, stdout="codex 1.0", stderr="")
            return SimpleNamespace(returncode=0, stdout="queue", stderr="")

        with mock.patch.object(codex_queue, "_identity_snapshot", return_value={}), \
                mock.patch.object(codex_queue, "_resolve_executable", return_value="codex.exe"):
            with self.assertRaisesRegex(codex_queue.CodexQueuePreflightError, "--thread"):
                codex_queue.run_codex_queue_preflight(THREAD, project_root=ROOT, runner=runner)

    def test_preflight_ignores_transient_cli_stderr_for_pinned_identity(self):
        warnings = iter(("warning path one", "warning path two", "help warning one", "help warning two"))

        def runner(command, **_kwargs):
            if command[1:] == ["--version"]:
                return SimpleNamespace(returncode=0, stdout="codex-cli 1.2.3\n", stderr=next(warnings))
            return SimpleNamespace(returncode=0, stdout="queue --thread ID --message TEXT", stderr=next(warnings))

        with mock.patch.object(codex_queue, "_identity_snapshot", return_value={
            "effective_user": "test-user", "user_profile": "C:/Users/test-user",
            "windows_user_profile": "C:/Users/test-user",
        }), mock.patch.object(codex_queue, "_resolve_executable", return_value="C:/Codex/codex.exe"):
            first = codex_queue.run_codex_queue_preflight(THREAD, project_root=ROOT, runner=runner)
            second = codex_queue.run_codex_queue_preflight(THREAD, project_root=ROOT, runner=runner)
        self.assertEqual(first["codex_version"], "codex-cli 1.2.3")
        self.assertEqual(second["codex_version"], first["codex_version"])
        self.assertEqual(second["queue_help_sha256"], first["queue_help_sha256"])

    @unittest.skipUnless(os.name == "nt", "Windows identity contract")
    def test_windows_userprofile_identity_mismatch_fails(self):
        with mock.patch.dict(os.environ, {"USERPROFILE": r"C:\Users\test-user"}), \
                mock.patch.object(codex_queue, "_windows_profile_folder", return_value=r"C:\Users\test-user"), \
                mock.patch.object(codex_queue, "_effective_user", return_value=r"DOMAIN\other"):
            with self.assertRaisesRegex(codex_queue.CodexQueuePreflightError, "normal profile"):
                codex_queue._identity_snapshot()

    def test_new_v4_manifest_has_no_c2c_fields_but_schema3_queue_remains_readable(self):
        with TemporaryDirectory() as temporary:
            v4 = _manifest(Path(temporary) / "v4")
            self.assertNotIn("c2c_task_id", v4.to_dict())
            self.assertNotIn("plan_iteration", v4.to_dict())
            v3_data = _manifest(Path(temporary) / "v3", schema=3).to_dict()
            loaded = RunManifest.from_dict(v3_data)
            self.assertEqual(loaded.c2c_task_id, "historical-task")
            self.assertEqual(loaded.plan_iteration, 0)

    def test_schema_v4_rejects_legacy_resume_and_session_routing(self):
        with TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "legacy_resume"):
                _manifest(Path(temporary) / "legacy", mode="legacy_resume")
            run_dir = Path(temporary) / "not-created"
            args = cli.build_parser().parse_args([
                "launch", "--config", "configs/studies/postrun_workflow_qualification.yaml",
                "--run-dir", str(run_dir), "--session-id", "session-not-thread",
            ])
            with self.assertRaisesRegex(ValueError, "session-id"):
                cli.launch(args)
            self.assertFalse(run_dir.exists())

    def test_durable_claim_exists_before_queue_process_and_exit_zero_is_sender_only(self):
        with TemporaryDirectory() as temporary:
            run_dir = _completed_run(Path(temporary) / "run")
            message_seen = []

            def queue_runner(command, **_kwargs):
                self.assertEqual(_kwargs["stdout"], subprocess.PIPE)
                self.assertEqual(_kwargs["stderr"], subprocess.PIPE)
                self.assertEqual(_kwargs["stdin"], subprocess.DEVNULL)
                self.assertNotIn("text", _kwargs)
                ledger = load_continuation_delivery(run_dir)
                self.assertEqual(ledger["state"], "CLAIMED")
                self.assertIsNotNone(ledger["command_started_at"])
                message_seen.append(command)
                return SimpleNamespace(returncode=0, stdout="accepted", stderr="")

            with mock.patch.object(codex_queue, "run_codex_queue_preflight", return_value=_queue_preflight()):
                result = codex_queue.send_queue_continuation(
                    run_dir, queue_runner=queue_runner, timeout_s=5,
                )
            self.assertEqual(result["state"], "SENDER_ACCEPTED")
            self.assertEqual(result["attempt_count"], 1)
            diagnostics = result["sender_diagnostics"]
            self.assertEqual(diagnostics["schema_version"], 1)
            self.assertEqual(diagnostics["codex_executable"], _queue_preflight()["codex_executable"])
            self.assertEqual(diagnostics["codex_version"], _queue_preflight()["codex_version"])
            self.assertEqual(diagnostics["stdout_excerpt"], "accepted")
            self.assertEqual(diagnostics["stdout_original_bytes"], len(b"accepted"))
            self.assertEqual(diagnostics["stdout_sha256"], hashlib.sha256(b"accepted").hexdigest())
            self.assertEqual(diagnostics["stderr_sha256"], hashlib.sha256(b"").hexdigest())
            self.assertFalse(diagnostics["stdout_truncated"])
            self.assertFalse(diagnostics["stderr_truncated"])
            self.assertEqual(diagnostics["redaction_status"], "PASS")
            self.assertLessEqual(len(diagnostics["stdout_excerpt"].encode("utf-8")), 16 * 1024)
            self.assertLessEqual(len(diagnostics["stderr_excerpt"].encode("utf-8")), 16 * 1024)
            datetime.fromisoformat(diagnostics["started_at"])
            datetime.fromisoformat(diagnostics["finished_at"])
            self.assertEqual(message_seen[0][1:4], ["queue", "--thread", THREAD])
            self.assertIn("[SAW ASYNC COMPLETE]", message_seen[0][-1])
            self.assertIn("run_manifest.project_root as Git cwd", message_seen[0][-1])
            self.assertNotIn("TASK_ID", message_seen[0][-1])
            self.assertLessEqual(len(message_seen[0][-1].encode("utf-8")), 1024)
            status = load_status(run_dir)
            self.assertEqual(status["state"], "COMPLETED")
            self.assertFalse(status["callback_completed"])
            self.assertNotEqual(status["state"], "REVIEWED")
            with self.assertRaisesRegex(ValueError, "already claimed"):
                with mock.patch.object(codex_queue, "run_codex_queue_preflight", return_value=_queue_preflight()):
                    codex_queue.send_queue_continuation(run_dir, queue_runner=queue_runner)
            self.assertEqual(len(message_seen), 1)

    def test_nonzero_sender_persists_stderr_and_remains_ambiguous_without_resend(self):
        with TemporaryDirectory() as temporary:
            run_dir = _completed_run(Path(temporary) / "nonzero")
            calls = []

            def queue_runner(*_args, **_kwargs):
                calls.append(True)
                return SimpleNamespace(returncode=1, stdout=b"started", stderr=b"queue failed: policy denied")

            with mock.patch.object(codex_queue, "run_codex_queue_preflight", return_value=_queue_preflight()):
                result = codex_queue.send_queue_continuation(run_dir, queue_runner=queue_runner, timeout_s=5)
                self.assertEqual(result["state"], "AMBIGUOUS")
                self.assertEqual(result["attempt_count"], 1)
                self.assertEqual(result["sender_diagnostics"]["exit_code"], 1)
                self.assertEqual(result["sender_diagnostics"]["stderr_excerpt"], "queue failed: policy denied")
                self.assertEqual(result["sender_diagnostics"]["stderr_sha256"], hashlib.sha256(b"queue failed: policy denied").hexdigest())
                with self.assertRaisesRegex(ValueError, "already claimed"):
                    codex_queue.send_queue_continuation(run_dir, queue_runner=queue_runner, timeout_s=5)
            self.assertEqual(len(calls), 1)

    def test_sender_diagnostic_excerpts_bound_both_streams_and_keep_edges(self):
        with TemporaryDirectory() as temporary:
            run_dir = _completed_run(Path(temporary) / "large")
            stdout = b"stdout-begin\n" + b"o" * (20 * 1024) + b"\nstdout-end"
            stderr = b"stderr-begin\n" + b"e" * (20 * 1024) + b"\nstderr-end"
            with mock.patch.object(codex_queue, "run_codex_queue_preflight", return_value=_queue_preflight()):
                result = codex_queue.send_queue_continuation(
                    run_dir,
                    queue_runner=lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr),
                    timeout_s=5,
                )
            diagnostics = result["sender_diagnostics"]
            self.assertLessEqual(len(diagnostics["stdout_excerpt"].encode("utf-8")), 16 * 1024)
            self.assertLessEqual(len(diagnostics["stderr_excerpt"].encode("utf-8")), 16 * 1024)
            self.assertTrue(diagnostics["stdout_truncated"])
            self.assertTrue(diagnostics["stderr_truncated"])
            self.assertIn("stdout-begin", diagnostics["stdout_excerpt"])
            self.assertIn("stdout-end", diagnostics["stdout_excerpt"])
            self.assertIn("stderr-begin", diagnostics["stderr_excerpt"])
            self.assertIn("stderr-end", diagnostics["stderr_excerpt"])
            self.assertEqual(diagnostics["stdout_original_bytes"], len(stdout))
            self.assertEqual(diagnostics["stderr_original_bytes"], len(stderr))

    def test_sender_diagnostic_redacts_credentials_and_hashes_raw_bytes(self):
        with TemporaryDirectory() as temporary:
            run_dir = _completed_run(Path(temporary) / "secrets")
            stdout = (
                b"Authorization: Bearer bearer-secret-123\n"
                b"access_token=access-secret refresh_token=refresh-secret "
                b"client_secret=client-secret oauth_code=oauth-secret "
                b"password=hunter2\nCookie: session=cookie-secret; other=also-secret\n"
                b"https://abc123.trycloudflare.com/mcp?token=tunnel-secret\n"
            )
            stderr = b"https://temporary.mcp.example.org/mcp/sse\n"
            with mock.patch.object(codex_queue, "run_codex_queue_preflight", return_value=_queue_preflight()):
                result = codex_queue.send_queue_continuation(
                    run_dir,
                    queue_runner=lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr),
                    timeout_s=5,
                )
            diagnostics = result["sender_diagnostics"]
            self.assertEqual(diagnostics["stdout_sha256"], hashlib.sha256(stdout).hexdigest())
            self.assertEqual(diagnostics["stderr_sha256"], hashlib.sha256(stderr).hexdigest())
            self.assertEqual(diagnostics["redaction_status"], "PASS")
            self.assertTrue(diagnostics["redaction_applied"])
            persisted = diagnostics["stdout_excerpt"] + diagnostics["stderr_excerpt"]
            for secret in (
                "bearer-secret-123", "access-secret", "refresh-secret", "client-secret",
                "oauth-secret", "hunter2", "cookie-secret", "also-secret",
                "abc123.trycloudflare.com", "temporary.mcp.example.org", "tunnel-secret",
            ):
                self.assertNotIn(secret, persisted)
            self.assertIn("Authorization: Bearer <REDACTED>", diagnostics["stdout_excerpt"])
            self.assertIn("<REDACTED_PUBLIC_MCP_URL>", diagnostics["stdout_excerpt"])
            self.assertIn("<REDACTED_PUBLIC_MCP_URL>", diagnostics["stderr_excerpt"])

    def test_empty_sender_output_has_empty_excerpt_and_raw_empty_hashes(self):
        with TemporaryDirectory() as temporary:
            run_dir = _completed_run(Path(temporary) / "empty")
            with mock.patch.object(codex_queue, "run_codex_queue_preflight", return_value=_queue_preflight()):
                result = codex_queue.send_queue_continuation(
                    run_dir,
                    queue_runner=lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=b"", stderr=b""),
                    timeout_s=5,
                )
            diagnostics = result["sender_diagnostics"]
            self.assertEqual(diagnostics["stdout_excerpt"], "")
            self.assertEqual(diagnostics["stderr_excerpt"], "")
            self.assertEqual(diagnostics["stdout_original_bytes"], 0)
            self.assertEqual(diagnostics["stderr_original_bytes"], 0)
            self.assertEqual(diagnostics["stdout_sha256"], hashlib.sha256(b"").hexdigest())
            self.assertFalse(diagnostics["stdout_truncated"])
            self.assertFalse(diagnostics["stderr_truncated"])

    def test_old_continuation_ledger_without_sender_diagnostics_remains_readable(self):
        with TemporaryDirectory() as temporary:
            run_dir = _completed_run(Path(temporary) / "historical")
            claim_queue_delivery(run_dir, delivery_id=DELIVERY)
            delivery_path = run_dir / "continuation_delivery.json"
            historical = json.loads(delivery_path.read_text(encoding="utf-8"))
            historical.update({
                "state": "AMBIGUOUS",
                "exit_code": 1,
                "sender_accepted": False,
                "stdout_sha256": "a" * 64,
                "stderr_sha256": "b" * 64,
                "error": "codex queue returned a non-zero exit",
                "sender_finished_at": "2026-10-04T00:00:00+00:00",
            })
            historical.pop("sender_diagnostics", None)
            delivery_path.write_text(json.dumps(historical), encoding="utf-8")
            loaded = load_continuation_delivery(run_dir)
            self.assertEqual(loaded["state"], "AMBIGUOUS")
            self.assertEqual(loaded["stderr_sha256"], "b" * 64)
            self.assertNotIn("sender_diagnostics", loaded)

    def test_queue_timeout_becomes_ambiguous_and_never_resends(self):
        with TemporaryDirectory() as temporary:
            run_dir = _completed_run(Path(temporary) / "timeout")
            with mock.patch.object(codex_queue, "run_codex_queue_preflight", return_value=_queue_preflight()):
                result = codex_queue.send_queue_continuation(
                    run_dir,
                    queue_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired(
                        "codex", 1, output=b"partial stdout", stderr=b"partial stderr",
                    )),
                    timeout_s=1,
                )
            self.assertEqual(result["state"], "AMBIGUOUS")
            self.assertEqual(result["attempt_count"], 1)
            self.assertEqual(result["sender_diagnostics"]["stdout_excerpt"], "partial stdout")
            self.assertEqual(result["sender_diagnostics"]["stderr_excerpt"], "partial stderr")

    def test_receiver_confirms_exact_runtime_thread_and_delivery_tuple_only(self):
        with TemporaryDirectory() as temporary:
            run_dir = _completed_run(Path(temporary) / "receiver")
            claim_queue_delivery(run_dir, delivery_id=DELIVERY)
            mark_queue_command_started(run_dir)
            record_queue_sender_result(run_dir, exit_code=0)
            with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": THREAD}):
                result = confirm_queue_delivery(
                    run_dir, run_id="queue-test-run", delivery_id=DELIVERY,
                    delivery_sentinel=SENTINEL,
                )
            self.assertEqual(result["state"], "RECEIVER_CONFIRMED")
            self.assertEqual(result["receiver_thread_id"], THREAD)
            self.assertEqual(load_status(run_dir)["state"], "COMPLETED")
            with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "01a0e89c-1c65-72a3-beb6-489f0cf01b31"}):
                with self.assertRaisesRegex(ValueError, "does not match"):
                    confirm_queue_delivery(
                        run_dir, run_id="queue-test-run", delivery_id=DELIVERY,
                        delivery_sentinel=SENTINEL,
                    )
            with self.assertRaisesRegex(ValueError, "sentinel"):
                with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": THREAD}):
                    confirm_queue_delivery(
                        run_dir, run_id="queue-test-run", delivery_id=DELIVERY,
                        delivery_sentinel="f" * 32,
                    )


if __name__ == "__main__":
    unittest.main()
