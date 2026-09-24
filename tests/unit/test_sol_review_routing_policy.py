from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_active_sol_review_policy_requests_gpt6_sol_without_legacy_fallback():
    instructions = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    policy = instructions.split("## Sol Escalation Policy", 1)[1].split("---", 1)[0]

    assert "Active Sol review target: `gpt-6-sol`." in policy
    assert "Explicitly request `gpt-6-sol`." in policy
    assert "gpt-5.6-sol" not in policy
