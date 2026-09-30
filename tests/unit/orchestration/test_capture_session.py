import importlib.util
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "sawopt_capture_session", ROOT / ".codex" / "hooks" / "capture_session.py"
)
capture_session = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture_session)


class CaptureSessionTests(unittest.TestCase):
    def test_main_persists_session_without_runtime_context(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / ".codex" / "runtime" / "current_session.json"
            stdout = io.StringIO()
            stderr = io.StringIO()
            payload = {
                "session_id": "session-from-hook",
                "cwd": temporary,
                "model": "test-model",
                "source": "startup",
                "hook_event_name": "SessionStart",
            }

            with (
                patch.object(capture_session, "_project_root", return_value=root),
                patch.object(capture_session.sys, "stdin", io.StringIO(json.dumps(payload))),
                patch.object(capture_session.sys, "stdout", stdout),
                patch.object(capture_session.sys, "stderr", stderr),
            ):
                self.assertEqual(capture_session.main(), 0)

            self.assertEqual(stdout.getvalue(), "")
            self.assertTrue(destination.is_file())
            stored = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(
                set(stored),
                {
                    "session_id",
                    "session_cwd",
                    "project_root",
                    "model",
                    "captured_at",
                    "hook_event_name",
                    "source",
                },
            )
            self.assertEqual(
                stored["session_id"], "session-from-hook"
            )
            self.assertEqual(stored["session_cwd"], str(Path(temporary).resolve()))
            self.assertEqual(stored["project_root"], str(root.resolve()))
            self.assertEqual(stored["model"], "test-model")
            self.assertTrue(stored["captured_at"])
            self.assertEqual(stored["hook_event_name"], "SessionStart")
            self.assertEqual(stored["source"], "startup")
            self.assertFalse(list(destination.parent.glob("*.tmp")))

    def test_main_capture_failure_is_fail_open_without_runtime_context(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                patch.object(capture_session, "_project_root", return_value=root),
                patch.object(capture_session.sys, "stdin", io.StringIO('{"session_id": ""}')),
                patch.object(capture_session.sys, "stdout", stdout),
                patch.object(capture_session.sys, "stderr", stderr),
            ):
                self.assertEqual(capture_session.main(), 0)

            error_log = root / ".codex" / "runtime" / "hook_errors.log"
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("capture_session hook failed:", stderr.getvalue())
            self.assertTrue(error_log.is_file())
            self.assertIn("ValueError", error_log.read_text(encoding="utf-8"))

    def test_hook_capture_is_atomic_and_keeps_explicit_session_fields(self):
        with TemporaryDirectory() as temporary:
            destination = Path(temporary) / "runtime" / "current_session.json"
            result = capture_session.capture_payload({
                "session_id": "session-123",
                "cwd": temporary,
                "model": "test-model",
                "source": "resume",
            }, destination)
            stored = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(stored, result)
            self.assertEqual(stored["session_id"], "session-123")
            self.assertEqual(stored["source"], "resume")
            self.assertEqual(stored["hook_event_name"], "SessionStart")
            self.assertEqual(stored["session_cwd"], str(Path(temporary).resolve()))
            self.assertEqual(stored["project_root"], str(capture_session._project_root()))
            self.assertFalse(list(destination.parent.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
