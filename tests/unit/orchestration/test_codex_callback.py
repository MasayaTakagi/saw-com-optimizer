import subprocess
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from sawopt.orchestration.codex_callback import (
    CodexCallbackTimeoutError,
    CodexCallbackTargetMismatchError,
    build_resume_command,
    run_codex_callback,
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
                return SimpleNamespace(returncode=0)

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
