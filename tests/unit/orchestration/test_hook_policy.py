import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _session_start_commands() -> list[str]:
    config = json.loads((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    commands = []
    for event in config.get("hooks", {}).get("SessionStart", []):
        for hook in event.get("hooks", []):
            for key in ("command", "commandWindows"):
                if key in hook:
                    commands.append(hook[key])
    return commands


class ActiveHookPolicyTests(unittest.TestCase):
    def test_session_start_does_not_run_session_capture_as_routing_instruction(self):
        commands = _session_start_commands()
        self.assertFalse(any("capture_session" in command for command in commands))

    def test_session_start_does_not_run_c2c_preflight_for_saw_operations(self):
        commands = _session_start_commands()
        self.assertFalse(any("c2c_state_access_preflight" in command for command in commands))

    def test_active_hook_and_guides_do_not_direct_new_production_to_session_id(self):
        paths = (
            ROOT / ".codex" / "hooks.json",
            ROOT / ".codex" / "hooks" / "capture_session.py",
            ROOT / "docs" / "c2c" / "FROZEN.md",
            ROOT / "docs" / "guides" / "async_orchestration.md",
        )
        active_text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        # Join adjacent Python string literals in the historical hook wording.
        active_text = active_text.replace('"', "").replace("'", "")
        active_text = re.sub(r"\s+", " ", active_text)
        stale_instruction = re.compile(
            r"for\s+async\s+production\s+launch.{0,120}"
            r"(?:pass|use|provide).{0,50}--session-id",
            re.IGNORECASE | re.DOTALL,
        )
        self.assertIsNone(stale_instruction.search(active_text))

        guide = (ROOT / "docs" / "guides" / "async_orchestration.md").read_text(encoding="utf-8")
        frozen = (ROOT / "docs" / "c2c" / "FROZEN.md").read_text(encoding="utf-8")
        self.assertIn("`CODEX_THREAD_ID`", guide)
        self.assertIn("`--thread-id`", guide)
        self.assertIn("codex queue --thread", guide)
        self.assertIn("SessionStart hookからproduction routing identityを注入しません", guide)
        self.assertIn("historical recovery/compatibility", frozen)


if __name__ == "__main__":
    unittest.main()
