import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_project_codex_hooks_do_not_enable_retired_callback_or_queue_behavior():
    config = json.loads((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    assert config.get("hooks", {}) == {}
    assert not (ROOT / ".codex" / "hooks" / "capture_session.py").exists()
    assert not (ROOT / ".codex" / "hooks" / "capture_session.cmd").exists()
    # The standalone C2C path-access preflight is safety tooling, not a session
    # capture, queue sender, or callback substitute.
    assert (ROOT / ".codex" / "hooks" / "c2c_state_access_preflight.py").is_file()


def test_legacy_orchestration_guides_are_explicitly_non_operational():
    for relative_path in (
        "docs/guides/async_orchestration.md",
        "docs/guides/github_review_workflow.md",
        "docs/c2c/OPERATIONS.md",
    ):
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "Issue #108" in text
        assert "retire" in text.casefold() or "廃止" in text
