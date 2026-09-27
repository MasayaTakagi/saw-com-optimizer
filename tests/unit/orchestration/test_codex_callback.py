import subprocess
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from sawopt.orchestration.codex_callback import (
    CodexCallbackPreflightError,
    CodexCallbackTimeoutError,
    CodexCallbackTargetMismatchError,
    build_resume_command,
    run_codex_callback,
    run_codex_callback_preflight,
)
from sawopt.orchestration.models import RunManifest


class CallbackTests(unittest.TestCase):
    def test_resume_uses_explicit_session_and_workspace_write(self):
        command = build_resume_command("session-123", "review", codex_executable="codex-test")
        self.assertEqual(command[:6], ["codex-test", "exec", "--sandbox", "workspace-write", "resume", "session-123"])
        self.assertNotIn("--last", command)

    def test_callback_runner_receives_manifest_session_and_keeps_prompt_out_of_shell(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            run_dir.mkdir()
            manifest = RunManifest(
                schema_version=1,
                run_id="run-1",
                experiment_name="dummy",
                created_at=datetime.now(timezone.utc).isoformat(),
                project_root=str(run_dir),
                run_dir=str(run_dir),
                command=["dummy"],
                config_path=None,
                codex_session_id="session-123",
                codex_model="test",
                callback_enabled=True,
                review_after_completion=True,
            )
            calls = []

            def fake_runner(command, **kwargs):
                calls.append((command, kwargs))
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        '{"type":"thread.started","thread_id":"session-123"}\n'
                    ),
                )

            code = run_codex_callback(
                manifest,
                exit_code=0,
                optimizer_failed=False,
                codex_executable="codex-test",
                runner=fake_runner,
            )
            self.assertEqual(code, 0)
            self.assertEqual(calls[0][0][6], "session-123")
            self.assertIn("--json", calls[0][0])
            self.assertEqual(calls[0][1]["cwd"], str(run_dir))
            self.assertEqual(calls[0][1]["timeout"], 1800.0)
            self.assertEqual(calls[0][1]["encoding"], "utf-8")
            self.assertEqual(calls[0][1]["errors"], "replace")
            self.assertTrue((run_dir / "callback.log").exists())

    def test_callback_prompt_names_control_and_optimizer_directories(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            optimizer = root / "optimizer"
            root.mkdir()
            manifest = RunManifest(
                schema_version=2,
                run_id="run-separated",
                experiment_name="dummy",
                created_at=datetime.now(timezone.utc).isoformat(),
                project_root=str(root),
                run_dir=str(root),
                optimizer_run_dir=str(optimizer),
                command=["dummy"],
                config_path=None,
                codex_session_id="session-123",
                codex_model="test",
                callback_enabled=True,
                review_after_completion=True,
            )
            calls = []

            def fake_runner(command, **kwargs):
                calls.append((command, kwargs))
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        '{"type":"thread.started","thread_id":"session-123"}\n'
                    ),
                )

            run_codex_callback(
                manifest,
                exit_code=0,
                optimizer_failed=False,
                runner=fake_runner,
            )
            prompt = calls[0][0][-1]
            self.assertIn(f"orchestration_root: {root}", prompt)
            self.assertIn(f"optimizer_output_dir: {optimizer}", prompt)

    def test_callback_preflight_requires_exact_target_and_acknowledgement(self):
        with TemporaryDirectory() as temporary:
            calls = []

            def fake_runner(command, **kwargs):
                calls.append((command, kwargs))
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        '{"type":"thread.started","thread_id":"session-123"}\n'
                        '{"type":"item.completed","item":{"type":"agent_message",'
                        '"text":"CALLBACK_PREFLIGHT_OK"}}\n'
                    ),
                )

            result = run_codex_callback_preflight(
                "session-123",
                project_root=temporary,
                codex_executable=sys.executable,
                runner=fake_runner,
            )

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["validated_target_id"], "session-123")
            self.assertIn("--json", calls[0][0])
            self.assertEqual(calls[0][0][6], "session-123")
            self.assertEqual(calls[0][1]["cwd"], temporary)
            self.assertIn("CALLBACK_PREFLIGHT_OK", calls[0][0][-1])

    def test_callback_preflight_fails_closed_on_missing_target(self):
        with TemporaryDirectory() as temporary:
            def missing_target_runner(command, **kwargs):
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        '{"type":"item.completed","item":{"type":"agent_message",'
                        '"text":"CALLBACK_PREFLIGHT_OK"}}\n'
                    ),
                )

            with self.assertRaises(CodexCallbackPreflightError):
                run_codex_callback_preflight(
                    "session-123",
                    project_root=temporary,
                    codex_executable=sys.executable,
                    runner=missing_target_runner,
                )

    def test_callback_preflight_fails_closed_on_target_mismatch_and_nonzero(self):
        with TemporaryDirectory() as temporary:
            responses = (
                SimpleNamespace(
                    returncode=0,
                    stdout=(
                        '{"type":"thread.started","thread_id":"session-other"}\n'
                        '{"type":"item.completed","item":{"type":"agent_message",'
                        '"text":"CALLBACK_PREFLIGHT_OK"}}\n'
                    ),
                ),
                SimpleNamespace(
                    returncode=17,
                    stdout=(
                        '{"type":"thread.started","thread_id":"session-123"}\n'
                        '{"type":"item.completed","item":{"type":"agent_message",'
                        '"text":"CALLBACK_PREFLIGHT_OK"}}\n'
                    ),
                ),
            )
            for response in responses:
                with self.subTest(returncode=response.returncode):
                    with self.assertRaises(CodexCallbackPreflightError):
                        run_codex_callback_preflight(
                            "session-123",
                            project_root=temporary,
                            codex_executable=sys.executable,
                            runner=lambda command, **kwargs: response,
                        )

    def test_callback_preflight_fails_closed_on_access_denied_and_timeout(self):
        with TemporaryDirectory() as temporary:
            def access_denied_runner(command, **kwargs):
                raise PermissionError("state database access denied")

            with self.assertRaises(CodexCallbackPreflightError):
                run_codex_callback_preflight(
                    "session-123",
                    project_root=temporary,
                    codex_executable=sys.executable,
                    runner=access_denied_runner,
                )

    def test_callback_preflight_rejects_acknowledgement_substrings(self):
        with TemporaryDirectory() as temporary:
            acknowledgements = (
                "NOT_CALLBACK_PREFLIGHT_OK",
                "CALLBACK_PREFLIGHT_OK trailing",
                "prefix CALLBACK_PREFLIGHT_OK",
                "CALLBACK_PREFLIGHT_OK or another response",
            )
            for acknowledgement in acknowledgements:
                with self.subTest(acknowledgement=acknowledgement):
                    response = SimpleNamespace(
                        returncode=0,
                        stdout=(
                            json.dumps({
                                "type": "thread.started",
                                "thread_id": "session-123",
                            }) + "\n" + json.dumps({
                                "type": "item.completed",
                                "item": {
                                    "type": "agent_message",
                                    "text": acknowledgement,
                                },
                            }) + "\n"
                        ),
                    )
                    with self.assertRaises(CodexCallbackPreflightError):
                        run_codex_callback_preflight(
                            "session-123",
                            project_root=temporary,
                            codex_executable=sys.executable,
                            runner=lambda command, **kwargs: response,
                        )

    def test_callback_preflight_ignores_echo_and_non_agent_acknowledgements(self):
        with TemporaryDirectory() as temporary:
            outputs = (
                '{"type":"item.completed","item":{"type":"user_message",'
                '"text":"CALLBACK_PREFLIGHT_OK"}}\n',
                '{"type":"item.started","item":{"type":"agent_message",'
                '"text":"CALLBACK_PREFLIGHT_OK"}}\n',
                '{"type":"item.completed","item":{"type":"agent_message",'
                '"text":"CALLBACK_PREFLIGHT_OK in echoed prompt"}}\n',
            )
            for output in outputs:
                with self.subTest(output=output):
                    response = SimpleNamespace(
                        returncode=0,
                        stdout=(
                            '{"type":"thread.started","thread_id":"session-123"}\n'
                            + output
                        ),
                    )
                    with self.assertRaises(CodexCallbackPreflightError):
                        run_codex_callback_preflight(
                            "session-123",
                            project_root=temporary,
                            codex_executable=sys.executable,
                            runner=lambda command, **kwargs: response,
                        )

    def test_callback_preflight_rejects_requested_and_foreign_target_ids(self):
        with TemporaryDirectory() as temporary:
            response = SimpleNamespace(
                returncode=0,
                stdout=(
                    '{"type":"thread.started","thread_id":"session-123"}\n'
                    '{"type":"turn.started","session_id":"session-other"}\n'
                    '{"type":"item.completed","item":{"type":"agent_message",'
                    '"text":"CALLBACK_PREFLIGHT_OK"}}\n'
                ),
            )
            with self.assertRaises(CodexCallbackPreflightError):
                run_codex_callback_preflight(
                    "session-123",
                    project_root=temporary,
                    codex_executable=sys.executable,
                    runner=lambda command, **kwargs: response,
                )

            def timeout_runner(command, **kwargs):
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])

            with self.assertRaises(CodexCallbackPreflightError):
                run_codex_callback_preflight(
                    "session-123",
                    project_root=temporary,
                    codex_executable=sys.executable,
                    runner=timeout_runner,
                )

    def test_callback_preflight_fails_when_executable_is_unavailable(self):
        with TemporaryDirectory() as temporary:
            with mock.patch(
                "sawopt.orchestration.codex_callback.shutil.which",
                return_value=None,
            ):
                with self.assertRaisesRegex(
                    CodexCallbackPreflightError,
                    "executable is not resolvable",
                ):
                    run_codex_callback_preflight(
                        "session-123",
                        project_root=temporary,
                    )

    def test_structured_callback_rejects_a_different_target(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            run_dir.mkdir()
            manifest = RunManifest(
                schema_version=1,
                run_id="run-mismatch",
                experiment_name="dummy",
                created_at=datetime.now(timezone.utc).isoformat(),
                project_root=str(run_dir),
                run_dir=str(run_dir),
                command=["dummy"],
                config_path=None,
                codex_session_id="session-requested",
                codex_model="test",
                callback_enabled=True,
                review_after_completion=True,
            )

            def mismatch_runner(command, **kwargs):
                return SimpleNamespace(
                    returncode=0,
                    stdout='{"type":"thread.started","thread_id":"session-other"}\n',
                )

            with self.assertRaises(CodexCallbackTargetMismatchError):
                run_codex_callback(
                    manifest,
                    exit_code=0,
                    optimizer_failed=False,
                    codex_executable="codex-test",
                    runner=mismatch_runner,
                )
            self.assertIn("target validation: mismatch", (run_dir / "callback.log").read_text(encoding="utf-8"))

    def test_timeout_is_recorded_and_raised_for_manual_recovery(self):
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            run_dir.mkdir()
            manifest = RunManifest(
                schema_version=1,
                run_id="run-timeout",
                experiment_name="dummy",
                created_at=datetime.now(timezone.utc).isoformat(),
                project_root=str(run_dir),
                run_dir=str(run_dir),
                command=["dummy"],
                config_path=None,
                codex_session_id="session-timeout",
                codex_model="test",
                callback_enabled=True,
                review_after_completion=True,
            )

            def timeout_runner(command, **kwargs):
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])

            with self.assertRaises(CodexCallbackTimeoutError):
                run_codex_callback(
                    manifest,
                    exit_code=0,
                    optimizer_failed=False,
                    codex_executable="codex-test",
                    timeout_s=0.5,
                    runner=timeout_runner,
                )
            self.assertIn("timed out after 0.5s", (run_dir / "callback.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
