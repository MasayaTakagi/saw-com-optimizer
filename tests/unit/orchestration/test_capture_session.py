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
    def test_additional_context_is_continuation_mode_aware(self):
        context = capture_session.build_additional_context("session-123")

        self.assertIn("Current Codex session ID: session-123", context)
        self.assertIn("legacy_resume", context)
        self.assertIn("--thread-id", context)
        self.assertIn("queue mode", context)
        self.assertIn("--session-id", context)
        self.assertIn("--session-file", context)
        self.assertIn("exact original Desktop thread ID", context)
        self.assertIn("do not pass --session-id or --session-file", context)
        self.assertIn("continuation_mode=disabled", context)
        self.assertIn("session ID and Desktop thread ID are distinct", context)
        self.assertLess(len(context), 1000)
        old_instruction = (
            "For async "
            "production launch, pass "
            "this exact ID "
            "explicitly using --session-id."
        )
        self.assertNotIn(old_instruction, context)

    def test_main_emits_mode_aware_context_and_writes_only_to_test_root(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / ".codex" / "runtime" / "current_session.json"
            stdout = io.StringIO()
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
            ):
                self.assertEqual(capture_session.main(), 0)

            emitted = json.loads(stdout.getvalue())
            context = emitted["hookSpecificOutput"]["additionalContext"]
            self.assertEqual(
                context,
                capture_session.build_additional_context("session-from-hook"),
            )
            self.assertTrue(destination.is_file())
            self.assertEqual(
                json.loads(destination.read_text(encoding="utf-8"))["session_id"],
                "session-from-hook",
            )

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
