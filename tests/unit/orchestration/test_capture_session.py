import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


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


if __name__ == "__main__":
    unittest.main()
