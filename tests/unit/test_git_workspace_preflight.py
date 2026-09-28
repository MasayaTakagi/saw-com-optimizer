"""Behavioral tests for Git/worktree sandbox diagnostics."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".codex" / "hooks" / "git_workspace_preflight.py"
SPEC = importlib.util.spec_from_file_location("git_workspace_preflight", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return result


def _make_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git("init", "-b", "main", cwd=path)
    _git("config", "user.name", "Preflight Test", cwd=path)
    _git("config", "user.email", "preflight@example.invalid", cwd=path)
    (path / "README.md").write_text("temporary repository\n", encoding="utf-8")
    _git("add", "README.md", cwd=path)
    _git("commit", "-m", "initial", cwd=path)
    return path


def test_clean_trusted_repository_reports_limited_remote_freshness(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")

    result = PREFLIGHT.inspect_workspace(repo)

    assert result["repo_exists"] is True
    assert result["repo_trust"] == "PASS"
    assert result["working_tree"] == "CLEAN"
    assert result["worktree_identity"] == "PRIMARY"
    assert result["worktree_registered"] is True
    assert result["git_metadata_write"] == "PASS"
    assert result["remote_access"] == "UNVERIFIED"
    assert result["remote_freshness"] == "UNVERIFIED"
    assert result["status"] == "PASS_WITH_LIMITATIONS"
    assert list((repo / ".git").glob(".codex-git-write-probe-*.tmp")) == []


def test_dirty_working_tree_is_reported_without_changing_it(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    (repo / "README.md").write_text("changed\n", encoding="utf-8")

    result = PREFLIGHT.inspect_workspace(repo)

    assert result["working_tree"] == "DIRTY"
    assert (repo / "README.md").read_text(encoding="utf-8") == "changed\n"


def test_linked_worktree_reports_git_common_directory(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    linked = tmp_path / "linked"
    _git("worktree", "add", "--detach", str(linked), "HEAD", cwd=repo)

    result = PREFLIGHT.inspect_workspace(linked)

    assert result["repo_trust"] == "PASS"
    assert result["worktree_identity"] == "LINKED"
    assert result["worktree_registered"] is True
    assert Path(result["git_common_dir"]) == repo / ".git"
    assert Path(result["git_dir"]) != Path(result["git_common_dir"])
    assert result["git_metadata_write"] == "PASS"


def test_missing_repository_is_reported(tmp_path: Path) -> None:
    result = PREFLIGHT.inspect_workspace(tmp_path / "missing")

    assert result["status"] == "MISSING_REPOSITORY"
    assert result["repo_exists"] is False
    assert result["repo_trust"] == "UNVERIFIED"


def test_dubious_ownership_is_classified_as_repository_trust(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path / "repo")
    original = PREFLIGHT._run_git

    def deny_trust(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
        if args == ("rev-parse", "--show-toplevel"):
            return subprocess.CompletedProcess(["git"], 128, "", "fatal: detected dubious ownership in repository")
        return original(path, *args)

    monkeypatch.setattr(PREFLIGHT, "_run_git", deny_trust)
    result = PREFLIGHT.inspect_workspace(repo)

    assert result["status"] == "REPO_TRUST_BLOCKED"
    assert result["repo_trust"] == "BLOCKED"
    assert result["trust_error_class"] == "REPO_TRUST_BLOCKED"
    assert result["git_metadata_write"] == "UNVERIFIED"


def test_metadata_write_denial_is_not_repository_trust_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path / "repo")
    monkeypatch.setattr(
        PREFLIGHT,
        "_probe_one_directory",
        lambda _path: {"status": "FAIL", "detail": "simulated metadata write denial"},
    )

    result = PREFLIGHT.inspect_workspace(repo)

    assert result["repo_trust"] == "PASS"
    assert result["git_metadata_write"] == "FAIL"
    assert result["write_dependent_capabilities"]["worktree_create"] == "BLOCKED_BY_GIT_METADATA_WRITE"
    assert result["status"] == "PASS_WITH_LIMITATIONS"


def test_remote_freshness_is_unverified_without_a_remote_probe(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")

    result = PREFLIGHT.inspect_workspace(repo, verify_remote=False)

    assert result["remote_access"] == "UNVERIFIED"
    assert result["remote_freshness"] == "UNVERIFIED"
    assert "no network call" in result["remote_detail"]


def test_read_only_remote_check_reports_fresh_tracking_ref(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    bare = tmp_path / "remote.git"
    _git("init", "--bare", str(bare), cwd=tmp_path)
    _git("remote", "add", "origin", str(bare), cwd=repo)
    _git("push", "--set-upstream", "origin", "main", cwd=repo)

    result = PREFLIGHT.inspect_workspace(repo, verify_remote=True)

    assert result["remote_access"] == "PASS"
    assert result["remote_freshness"] == "FRESH"
    assert result["status"] == "PASS"


def test_remote_network_failure_does_not_claim_stale_or_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path / "repo")
    bare = tmp_path / "remote.git"
    _git("init", "--bare", str(bare), cwd=tmp_path)
    _git("remote", "add", "origin", str(bare), cwd=repo)
    _git("push", "--set-upstream", "origin", "main", cwd=repo)
    original = PREFLIGHT._run_git

    def deny_remote(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "ls-remote":
            return subprocess.CompletedProcess(["git"], 128, "", "fatal: unable to access remote")
        return original(path, *args)

    monkeypatch.setattr(PREFLIGHT, "_run_git", deny_remote)
    result = PREFLIGHT.inspect_workspace(repo, verify_remote=True)

    assert result["remote_access"] == "FAIL"
    assert result["remote_freshness"] == "UNVERIFIED"


def test_unexpected_git_failure_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path / "repo")
    original = PREFLIGHT._run_git

    def fail_trust(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
        if args == ("rev-parse", "--show-toplevel"):
            return subprocess.CompletedProcess(["git"], 128, "", "fatal: simulated internal error")
        return original(path, *args)

    monkeypatch.setattr(PREFLIGHT, "_run_git", fail_trust)
    result = PREFLIGHT.inspect_workspace(repo)

    assert result["status"] == "PREFLIGHT_ERROR"
    assert result["repo_trust"] == "ERROR"
    assert result["trust_error_class"] == "UNEXPECTED_GIT_FAILURE"


def test_hook_output_is_json_and_never_blocks_session_start(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    repo = _make_repo(tmp_path / "repo")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--repo", str(repo), "--hook-output"])

    exit_code = PREFLIGHT.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    message = payload["hookSpecificOutput"]["additionalContext"]
    assert "REPO_TRUST=PASS" in message
    assert "REMOTE_FRESHNESS=UNVERIFIED" in message


def test_safe_directory_configuration_is_visible_and_flags_broad_wildcard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path / "repo")
    original = PREFLIGHT._run_git

    def report_safe_directories(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
        if args == ("config", "--show-origin", "--get-all", "safe.directory"):
            configured = str(repo.resolve())
            output = f"file:C:/Users/test/.gitconfig\t{configured}\nfile:C:/Users/test/.gitconfig\t*\n"
            return subprocess.CompletedProcess(["git"], 0, output, "")
        return original(path, *args)

    monkeypatch.setattr(PREFLIGHT, "_run_git", report_safe_directories)
    result = PREFLIGHT.inspect_workspace(repo)

    assert result["safe_directory"]["status"] == "MATCH"
    assert result["safe_directory"]["broad_wildcard_present"] is True
    assert len(result["safe_directory"]["matching_entries"]) == 2


def test_probe_cleanup_failure_is_reported_and_test_removes_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path / "repo")
    original_unlink = Path.unlink

    def fail_probe_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        if path.name.startswith(".codex-git-write-probe-"):
            raise PermissionError("simulated cleanup denial")
        original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_probe_cleanup)
        result = PREFLIGHT.inspect_workspace(repo)

    leftovers = list((repo / ".git").glob(".codex-git-write-probe-*.tmp"))
    assert result["git_metadata_write"] == "CLEANUP_FAILED"
    assert result["status"] == "METADATA_PROBE_CLEANUP_FAILED"
    assert len(leftovers) == 1
    original_unlink(leftovers[0])
    assert list((repo / ".git").glob(".codex-git-write-probe-*.tmp")) == []


def test_os_permission_denial_is_metadata_write_failure_without_leftover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    def deny_create(*args: object, **kwargs: object) -> int:
        raise PermissionError("simulated sandbox write denial")

    monkeypatch.setattr(PREFLIGHT.os, "open", deny_create)
    result = PREFLIGHT._probe_one_directory(git_dir)

    assert result["status"] == "FAIL"
    assert "cannot write" in result["detail"]
    assert list(git_dir.iterdir()) == []
