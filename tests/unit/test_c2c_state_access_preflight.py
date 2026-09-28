"""Behavioral checks for the least-privilege C2C state preflight."""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest


HOOK_PATH = Path(__file__).resolve().parents[2] / ".codex" / "hooks" / "c2c_state_access_preflight.py"
SPEC = importlib.util.spec_from_file_location("c2c_state_access_preflight", HOOK_PATH)
assert SPEC is not None and SPEC.loader is not None
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)


def _environment(local_app_data: Path, **extra: str) -> dict[str, str]:
    return {"LOCALAPPDATA": str(local_app_data), **extra}


def _make_state_root(local_app_data: Path) -> Path:
    root = local_app_data / "codex-with-chatgpt"
    root.mkdir(parents=True)
    return root


def test_canonical_temporary_root_passes_and_leaves_no_canary(tmp_path: Path) -> None:
    state_root = _make_state_root(tmp_path)

    result = PREFLIGHT.probe_state_access(_environment(tmp_path))

    assert result["status"] == "PASS"
    assert list(state_root.glob(".c2c-access-probe-*.tmp")) == []


def test_resolved_alias_samefile_passes_but_canary_uses_lexical_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _make_state_root(tmp_path)
    resolved_alias = tmp_path / "resolved-alias"
    resolved_alias.mkdir()
    original_resolve = Path.resolve
    original_open = os.open
    opened_paths: list[Path] = []

    def resolve_with_alias(path: Path, *args: object, **kwargs: object) -> Path:
        if path == state_root:
            return resolved_alias
        return original_resolve(path, *args, **kwargs)

    def record_open(path: str | os.PathLike[str], *args: object, **kwargs: object) -> int:
        opened_paths.append(Path(path))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve_with_alias)
    monkeypatch.setattr(PREFLIGHT.os.path, "samefile", lambda left, right: True)
    monkeypatch.setattr(PREFLIGHT.os, "open", record_open)

    result = PREFLIGHT.probe_state_access(_environment(tmp_path))

    assert result["status"] == "PASS"
    assert len(opened_paths) == 1
    assert opened_paths[0].parent == state_root
    assert list(state_root.glob(".c2c-access-probe-*.tmp")) == []
    assert list(resolved_alias.glob(".c2c-access-probe-*.tmp")) == []


def test_resolved_alias_with_different_object_fails_before_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _make_state_root(tmp_path)
    resolved_alias = tmp_path / "resolved-alias"
    resolved_alias.mkdir()
    original_resolve = Path.resolve
    create_calls: list[Path] = []

    def resolve_with_alias(path: Path, *args: object, **kwargs: object) -> Path:
        if path == state_root:
            return resolved_alias
        return original_resolve(path, *args, **kwargs)

    def record_create(path: str | os.PathLike[str], *args: object, **kwargs: object) -> int:
        create_calls.append(Path(path))
        raise AssertionError("canary creation must not run after identity failure")

    monkeypatch.setattr(Path, "resolve", resolve_with_alias)
    monkeypatch.setattr(PREFLIGHT.os.path, "samefile", lambda left, right: False)
    monkeypatch.setattr(PREFLIGHT.os, "open", record_create)

    result = PREFLIGHT.probe_state_access(_environment(tmp_path))

    assert result["status"] == "STATE_PATH_MISMATCH"
    assert create_calls == []
    assert list(state_root.glob(".c2c-access-probe-*.tmp")) == []


def test_samefile_error_fails_closed_before_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _make_state_root(tmp_path)
    resolved_alias = tmp_path / "resolved-alias"
    resolved_alias.mkdir()
    original_resolve = Path.resolve

    def resolve_with_alias(path: Path, *args: object, **kwargs: object) -> Path:
        if path == state_root:
            return resolved_alias
        return original_resolve(path, *args, **kwargs)

    def fail_samefile(_left: Path, _right: Path) -> bool:
        raise OSError("simulated identity inspection error")

    monkeypatch.setattr(Path, "resolve", resolve_with_alias)
    monkeypatch.setattr(PREFLIGHT.os.path, "samefile", fail_samefile)

    result = PREFLIGHT.probe_state_access(_environment(tmp_path))

    assert result["status"] == "STATE_PATH_MISMATCH"
    assert list(state_root.glob(".c2c-access-probe-*.tmp")) == []


def test_noncanonical_override_is_rejected_even_if_samefile_would_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _make_state_root(tmp_path)
    alternate_path = tmp_path / "alternate-state"
    alternate_path.mkdir()
    samefile_calls: list[tuple[Path, Path]] = []

    def report_samefile(left: Path, right: Path) -> bool:
        samefile_calls.append((Path(left), Path(right)))
        return True

    monkeypatch.setattr(PREFLIGHT.os.path, "samefile", report_samefile)

    result = PREFLIGHT.probe_state_access(
        _environment(tmp_path, C2C_STATE_DIR=str(alternate_path))
    )

    assert result["status"] == "STATE_PATH_MISMATCH"
    assert samefile_calls == []
    assert list(state_root.glob(".c2c-access-probe-*.tmp")) == []


def test_state_root_reparse_point_is_rejected_before_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _make_state_root(tmp_path)
    original_lstat = Path.lstat
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

    def lstat_with_reparse_point(path: Path, *args: object, **kwargs: object) -> os.stat_result:
        if path == state_root:
            return SimpleNamespace(
                st_mode=stat.S_IFDIR | 0o755,
                st_file_attributes=reparse_flag,
            )  # type: ignore[return-value]
        return original_lstat(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", lstat_with_reparse_point)
        result = PREFLIGHT.probe_state_access(_environment(tmp_path))

    assert result["status"] == "STATE_PATH_MISMATCH"
    assert list(state_root.glob(".c2c-access-probe-*.tmp")) == []


def test_reparse_metadata_inspection_error_fails_closed_before_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _make_state_root(tmp_path)

    def fail_reparse_inspection(_info: os.stat_result) -> bool:
        raise OSError("simulated reparse metadata failure")

    monkeypatch.setattr(PREFLIGHT, "_is_reparse_point", fail_reparse_inspection)

    result = PREFLIGHT.probe_state_access(_environment(tmp_path))

    assert result["status"] == "STATE_PATH_MISMATCH"
    assert list(state_root.glob(".c2c-access-probe-*.tmp")) == []


@pytest.mark.parametrize("environment", [{}, {"LOCALAPPDATA": "missing-local-app-data"}])
def test_missing_local_app_data_or_root_is_reported(environment: dict[str, str]) -> None:
    assert PREFLIGHT.probe_state_access(environment)["status"] == "STATE_ROOT_MISSING"


def test_conflicting_state_override_fails_without_creating_canary(tmp_path: Path) -> None:
    state_root = _make_state_root(tmp_path)
    other_root = tmp_path / "other-c2c-state"
    other_root.mkdir()

    result = PREFLIGHT.probe_state_access(
        _environment(tmp_path, C2C_STATE_DIR=str(other_root))
    )

    assert result["status"] == "STATE_PATH_MISMATCH"
    assert list(state_root.glob(".c2c-access-probe-*.tmp")) == []


def test_permission_error_on_create_is_active_sandbox_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _make_state_root(tmp_path)

    def deny_create(*args: object, **kwargs: object) -> int:
        raise PermissionError("simulated denial")

    monkeypatch.setattr(PREFLIGHT.os, "open", deny_create)
    result = PREFLIGHT.probe_state_access(_environment(tmp_path))

    assert result["status"] == "ACTIVE_SANDBOX_DENIED"
    assert list(state_root.glob(".c2c-access-probe-*.tmp")) == []


def test_other_create_error_is_reported_without_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _make_state_root(tmp_path)

    def fail_create(*args: object, **kwargs: object) -> int:
        raise OSError("simulated I/O failure")

    monkeypatch.setattr(PREFLIGHT.os, "open", fail_create)
    result = PREFLIGHT.probe_state_access(_environment(tmp_path))

    assert result["status"] == "OTHER_IO_FAILURE"
    assert list(state_root.glob(".c2c-access-probe-*.tmp")) == []


def test_fsync_error_removes_the_created_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _make_state_root(tmp_path)

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("simulated flush failure")

    monkeypatch.setattr(PREFLIGHT.os, "fsync", fail_fsync)
    result = PREFLIGHT.probe_state_access(_environment(tmp_path))

    assert result["status"] == "OTHER_IO_FAILURE"
    assert list(state_root.glob(".c2c-access-probe-*.tmp")) == []


def test_unlink_error_is_reported_and_temporary_canary_is_cleaned_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _make_state_root(tmp_path)
    original_unlink = Path.unlink

    def fail_canary_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.name.startswith(".c2c-access-probe-"):
            raise PermissionError("simulated cleanup failure")
        original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_canary_unlink)
        result = PREFLIGHT.probe_state_access(_environment(tmp_path))

    assert result["status"] == "PROBE_CLEANUP_FAILED"
    leftovers = list(state_root.glob(".c2c-access-probe-*.tmp"))
    assert len(leftovers) == 1
    original_unlink(leftovers[0])
    assert list(state_root.glob(".c2c-access-probe-*.tmp")) == []


def test_session_start_output_is_informational_even_on_denial(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", [str(HOOK_PATH), "--hook-output"])
    monkeypatch.setattr(
        PREFLIGHT,
        "probe_state_access",
        lambda: {"status": "ACTIVE_SANDBOX_DENIED", "detail": "simulated denial"},
    )

    exit_code = PREFLIGHT.main()
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "ACTIVE_SANDBOX_DENIED" in context
    assert "informational only" in context
