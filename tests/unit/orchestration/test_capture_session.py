import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "sawopt_capture_session", ROOT / ".codex" / "hooks" / "capture_session.py"
)
capture_session = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture_session)


class CaptureSessionTests(unittest.TestCase):
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

    def test_manual_capture_stores_metadata_without_routing_context(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            stdout = io.StringIO()
            stderr = io.StringIO()
            payload = json.dumps({"session_id": "session-historical", "cwd": temporary})
            with (
                mock.patch.object(capture_session, "_project_root", return_value=root),
                mock.patch.object(sys, "stdin", io.StringIO(payload)),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                result = capture_session.main()

            stored = json.loads((root / ".codex" / "runtime" / "current_session.json").read_text())
            self.assertEqual(result, 0)
            self.assertEqual(stored["session_id"], "session-historical")
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
