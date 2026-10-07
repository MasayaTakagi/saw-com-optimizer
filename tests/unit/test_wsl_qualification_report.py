from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COLLECT_REPORT = ROOT / "tools" / "wsl" / "collect-report.sh"


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_report_uses_qualification_head_not_bootstrap_head(tmp_path: Path) -> None:
    tested_head = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True,
    ).strip()
    source_status = subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
        text=True,
    ).splitlines()
    bootstrap_head = "a" * 40
    assert tested_head != bootstrap_head

    results = tmp_path / "results"
    report = tmp_path / "review"
    results.mkdir()
    _write_json(results / "environment.json", {
        "git_head": {"output": bootstrap_head},
        "wsl_distro": "Ubuntu-24.04",
        "kernel": "test-kernel",
        "python": "3.12.3",
        "numpy": "2.5.3",
        "scipy": "1.18.1",
    })
    for name in (
        "filesystem.json",
        "git.json",
        "worktree-identity.json",
        "worktree-cleanup.json",
        "codex-sandbox.json",
        "optimizer-checkpoint.json",
        "regression.json",
    ):
        _write_json(results / name, {"status": "PASS", "detail": "test fixture"})
    _write_json(results / "numerical.json", {
        "evaluator_parity": {"status": "PASS"},
        "optimizer": {"status": "PASS", "checkpoint": {"state_version": 4}},
    })

    subprocess.run(
        ["bash", str(COLLECT_REPORT), str(results), str(report)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    markdown = (report / "report.md").read_text(encoding="utf-8")
    payload = json.loads((report / "report.json").read_text(encoding="utf-8"))
    assert f"- Source commit: {tested_head}" in markdown
    assert f"- Source commit: {bootstrap_head}" not in markdown
    assert f"- Bootstrap source commit: {bootstrap_head}" in markdown
    assert payload["source_commit_sha"] == tested_head
    assert payload["bootstrap_source_commit_sha"] == bootstrap_head
    assert payload["source_working_tree"] == {
        "clean": not source_status,
        "status": source_status,
    }
    dirty_blocker_present = any(
        item["category"] == "SOURCE_WORKTREE_DIRTY" for item in payload["blockers"]
    )
    if source_status:
        assert payload["final_status"] == "WSL2_CORE_BLOCKED"
        assert dirty_blocker_present
    else:
        assert payload["final_status"] == "WSL2_CORE_QUALIFIED"
        assert not dirty_blocker_present
