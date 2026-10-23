from __future__ import annotations

import fcntl
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from sawopt.io.synthetic_task_ledger import SyntheticTaskError, SyntheticTaskLedger, _read_process_identity


ROOT = Path(__file__).resolve().parents[2]
CLI = [sys.executable, "-m", "sawopt.cli", "synthetic-task"]
_ORIGINAL_OS_KILL = os.kill


def _root(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic-task-root"
    path.mkdir(mode=0o700)
    return path


def _invoke(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [*CLI, *args, "--root", str(root)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def _status(root: Path, run_id: str) -> dict:
    result = _invoke(root, "status", "--run-id", run_id)
    return json.loads(result.stdout)


def _wait_status(root: Path, run_id: str, predicate, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = _status(root, run_id)
        if predicate(last):
            return last
        time.sleep(0.025)
    raise AssertionError(f"task did not reach expected state; last status={last!r}")


def _launch(root: Path, key: str, *, steps: int = 16, interval_ms: int = 100):
    result = _invoke(
        root,
        "launch",
        "--idempotency-key", key,
        "--steps", str(steps),
        "--interval-ms", str(interval_ms),
    )
    return json.loads(result.stdout)


def _kill_only_verified_test_child(snapshot: dict) -> None:
    pid = snapshot.get("owner_pid")
    expected = (snapshot.get("owner_boot_id"), snapshot.get("owner_start_ticks"))
    observed = _read_process_identity(pid) if isinstance(pid, int) else None
    if observed is not None and (observed[0], observed[1]) == expected and observed[2] != "Z":
        _ORIGINAL_OS_KILL(pid, signal.SIGKILL)


def test_detached_synthetic_child_survives_cli_and_fresh_attach_observes_progress(tmp_path):
    root = _root(tmp_path)
    poison_data_root = tmp_path / "must-not-be-opened"
    poison_data_root.mkdir()
    (poison_data_root / "sentinel").write_text("untouched", encoding="utf-8")
    env = dict(os.environ, SAWOPT_DATA_ROOT=str(poison_data_root))

    launch = subprocess.run(
        [
            *CLI, "launch", "--root", str(root), "--idempotency-key", "detached-test",
            "--steps", "20", "--interval-ms", "100",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert launch.returncode == 0, launch.stderr
    issued = json.loads(launch.stdout)
    run_id = issued["run_id"]

    first = _wait_status(root, run_id, lambda value: value["progress_completed"] >= 1)
    assert first["state"] == "RUNNING"
    assert launch.returncode == 0  # the issuing CLI has exited while its child remains active
    time.sleep(0.15)
    second = _status(root, run_id)
    assert second["progress_completed"] > first["progress_completed"]

    attached = _invoke(root, "attach", "--run-id", run_id)
    assert json.loads(attached.stdout)["run_id"] == run_id
    final = _wait_status(root, run_id, lambda value: value["state"] == "COMPLETED")
    assert final["progress_completed"] == 20
    assert final["authorization_test_only"] is True
    assert final["state"] == "COMPLETED"
    assert (poison_data_root / "sentinel").read_text(encoding="utf-8") == "untouched"
    assert sorted(item.name for item in poison_data_root.iterdir()) == ["sentinel"]
    assert (root / "synthetic-tasks.log").stat().st_size <= 16 * 1024


def test_concurrent_same_idempotency_request_has_one_task_and_conflict_on_change(tmp_path):
    root = _root(tmp_path)
    command = [
        *CLI, "launch", "--root", str(root), "--idempotency-key", "one-key",
        "--steps", "18", "--interval-ms", "100",
    ]
    children = [
        subprocess.Popen(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(2)
    ]
    results = [child.communicate(timeout=10) for child in children]
    assert [child.returncode for child in children] == [0, 0], results
    launched = [json.loads(stdout) for stdout, _stderr in results]
    assert launched[0]["run_id"] == launched[1]["run_id"]
    assert launched[0]["attempt_id"] == launched[1]["attempt_id"]

    with sqlite3.connect(root / "synthetic-tasks.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM tasks").fetchone()[0] == 1

    conflict = _invoke(
        root, "launch", "--idempotency-key", "one-key", "--steps", "19",
        "--interval-ms", "100", check=False,
    )
    assert conflict.returncode != 0
    error = json.loads(conflict.stderr)
    assert error["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    _wait_status(root, launched[0]["run_id"], lambda value: value["state"] == "COMPLETED")


def test_stop_is_cooperative_and_is_bound_to_the_exact_attempt(tmp_path):
    root = _root(tmp_path)
    launch = _launch(root, "stop-test", steps=30, interval_ms=100)
    run_id, attempt_id = launch["run_id"], launch["attempt_id"]
    running = _wait_status(root, run_id, lambda value: value["progress_completed"] >= 1)

    wrong_attempt = _invoke(
        root, "stop", "--run-id", run_id, "--attempt-id", "0" * 32, check=False,
    )
    assert wrong_attempt.returncode != 0
    assert _status(root, run_id)["state"] == "RUNNING"

    stopped = _invoke(root, "stop", "--run-id", run_id, "--attempt-id", attempt_id)
    assert json.loads(stopped.stdout)["state"] == "STOP_REQUESTED"
    terminal = _wait_status(root, run_id, lambda value: value["state"] == "STOPPED")
    assert terminal["progress_completed"] >= running["progress_completed"]
    assert terminal["progress_completed"] < 30


def test_worker_death_is_recovery_required_and_duplicate_launch_never_restarts(tmp_path):
    root = _root(tmp_path)
    launched = _launch(root, "crash-test", steps=50, interval_ms=100)
    run_id = launched["run_id"]
    running = _wait_status(root, run_id, lambda value: value["progress_completed"] >= 1)
    identity = _read_process_identity(running["owner_pid"])
    assert identity is not None
    assert identity[0] == running["owner_boot_id"]
    assert identity[1] == running["owner_start_ticks"]
    assert identity[2] != "Z"
    _ORIGINAL_OS_KILL(running["owner_pid"], signal.SIGKILL)  # exact test-owned PID/start/boot identity was just verified

    interrupted = _wait_status(root, run_id, lambda value: value["state"] == "RECOVERY_REQUIRED")
    progress = interrupted["progress_completed"]
    assert interrupted["ledger_state"] == "RUNNING"
    repeated = _launch(root, "crash-test", steps=50, interval_ms=100)
    assert repeated["created"] is False
    assert repeated["run_id"] == run_id
    time.sleep(0.15)
    still_interrupted = _status(root, run_id)
    assert still_interrupted["state"] == "RECOVERY_REQUIRED"
    assert still_interrupted["progress_completed"] == progress


@pytest.mark.parametrize("identity_field", ["owner_start_ticks", "owner_boot_id", "foreign_pid"])
def test_pid_reuse_or_boot_mismatch_fails_closed_and_stop_never_signals_foreign_pid(
    tmp_path, monkeypatch, identity_field,
):
    root = _root(tmp_path)
    launched = _launch(root, f"identity-{identity_field}", steps=40, interval_ms=100)
    run_id, attempt_id = launched["run_id"], launched["attempt_id"]
    running = _wait_status(root, run_id, lambda value: value["progress_completed"] >= 1)
    original_identity = _read_process_identity(running["owner_pid"])
    assert original_identity is not None
    with sqlite3.connect(root / "synthetic-tasks.sqlite3") as connection:
        if identity_field == "owner_start_ticks":
            connection.execute(
                "UPDATE tasks SET owner_start_ticks=owner_start_ticks+100 WHERE run_id=?", (run_id,),
            )
        elif identity_field == "owner_boot_id":
            connection.execute(
                "UPDATE tasks SET owner_boot_id=? WHERE run_id=?", ("0" * 36, run_id),
            )
        else:
            foreign = _read_process_identity(os.getpid())
            assert foreign is not None
            connection.execute(
                "UPDATE tasks SET owner_pid=?,owner_start_ticks=?,owner_boot_id=? WHERE run_id=?",
                (os.getpid(), foreign[1], foreign[0], run_id),
            )

    calls = []
    monkeypatch.setattr(os, "kill", lambda *args, **kwargs: calls.append((args, kwargs)))
    ledger = SyntheticTaskLedger(root)
    assert ledger.get_status(run_id).state == "PROCESS_IDENTITY_UNKNOWN"
    with pytest.raises(SyntheticTaskError) as rejected:
        ledger.request_stop(run_id, attempt_id)
    assert rejected.value.code == "PROCESS_IDENTITY_UNKNOWN"
    assert calls == []
    assert _read_process_identity(os.getpid()) is not None
    # The test owns this worker and only cleans it if its original identity still matches.
    _kill_only_verified_test_child({
        "owner_pid": running["owner_pid"],
        "owner_boot_id": original_identity[0],
        "owner_start_ticks": original_identity[1],
    })


def test_help_invalid_request_and_raw_root_selection_do_not_create_or_move_data(tmp_path, monkeypatch):
    root = _root(tmp_path)
    help_result = subprocess.run(
        [*CLI, "launch", "--help"], cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert help_result.returncode == 0
    assert not list(root.iterdir())

    invalid = _invoke(
        root, "launch", "--idempotency-key", "invalid", "--steps", "0", check=False,
    )
    assert invalid.returncode != 0
    assert json.loads(invalid.stderr)["error"]["code"] == "REQUEST_INVALID"
    assert not list(root.iterdir())

    raw_root = tmp_path / "configured-raw-root"
    raw_root.mkdir(mode=0o700)
    sentinel = raw_root / "sentinel"
    sentinel.write_text("immutable", encoding="utf-8")
    monkeypatch.setenv("SAWOPT_DATA_ROOT", str(raw_root))
    rejected = _invoke(
        raw_root, "launch", "--idempotency-key", "raw", "--steps", "1", check=False,
    )
    assert rejected.returncode != 0
    assert sentinel.read_text(encoding="utf-8") == "immutable"
    assert sorted(item.name for item in raw_root.iterdir()) == ["sentinel"]


def test_raw_root_symlink_alias_is_rejected_without_artifacts_and_unrelated_root_works(tmp_path, monkeypatch):
    raw_root = tmp_path / "raw-real"
    raw_root.mkdir(mode=0o700)
    sentinel = raw_root / "historic-sentinel"
    sentinel.write_text("untouched", encoding="utf-8")
    raw_alias = tmp_path / "raw-alias"
    raw_alias.symlink_to(raw_root, target_is_directory=True)
    forbidden_child = raw_root / "empty-child"
    forbidden_child.mkdir(mode=0o700)
    monkeypatch.setenv("SAWOPT_DATA_ROOT", str(raw_alias))

    rejected = _invoke(
        forbidden_child, "launch", "--idempotency-key", "alias", "--steps", "1", check=False,
    )
    assert rejected.returncode != 0
    assert json.loads(rejected.stderr)["error"]["code"] == "TASK_ROOT_UNSAFE"
    assert not list(forbidden_child.iterdir())
    assert sentinel.read_text(encoding="utf-8") == "untouched"
    assert sorted(item.name for item in raw_root.iterdir()) == ["empty-child", "historic-sentinel"]

    unrelated_parent = tmp_path / "unrelated"
    unrelated_parent.mkdir(mode=0o700)
    unrelated_root = _root(unrelated_parent)
    launched = _launch(unrelated_root, "not-raw", steps=1, interval_ms=10)
    completed = _wait_status(
        unrelated_root, launched["run_id"], lambda value: value["state"] == "COMPLETED",
    )
    assert completed["state"] == "COMPLETED"

    broken_alias = tmp_path / "broken-raw-alias"
    broken_alias.symlink_to(tmp_path / "missing-raw-target", target_is_directory=True)
    monkeypatch.setenv("SAWOPT_DATA_ROOT", str(broken_alias))
    unresolved_root = tmp_path / "unresolved-root"
    unresolved_root.mkdir(mode=0o700)
    rejected = _invoke(
        unresolved_root, "launch", "--idempotency-key", "unresolved", "--steps", "1", check=False,
    )
    assert rejected.returncode != 0
    assert json.loads(rejected.stderr)["error"]["code"] == "TASK_ROOT_UNSAFE"
    assert not list(unresolved_root.iterdir())


def test_held_diagnostic_log_lock_does_not_block_progress_or_cooperative_stop(tmp_path):
    root = _root(tmp_path)
    log_path = root / "synthetic-tasks.log"
    log_path.touch(mode=0o600)
    fd = os.open(log_path, os.O_WRONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        launch = _launch(root, "held-log-lock", steps=40, interval_ms=50)
        running = _wait_status(root, launch["run_id"], lambda value: value["progress_completed"] >= 1)
        stop = _invoke(
            root, "stop", "--run-id", launch["run_id"], "--attempt-id", launch["attempt_id"],
        )
        assert json.loads(stop.stdout)["state"] == "STOP_REQUESTED"
        stopped = _wait_status(root, launch["run_id"], lambda value: value["state"] == "STOPPED")
        assert stopped["progress_completed"] >= running["progress_completed"]
        assert stopped["progress_completed"] < 40
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_invalid_roots_and_missing_explicit_root_do_not_create_task_data(tmp_path):
    target = _root(tmp_path)
    link = tmp_path / "root-link"
    link.symlink_to(target, target_is_directory=True)
    rejected = _invoke(link, "status", "--run-id", "a" * 32, check=False)
    assert rejected.returncode != 0
    assert not list(target.iterdir())

    traversal = str(tmp_path / "unused" / ".." / "synthetic-task-root")
    rejected = _invoke(Path(traversal), "status", "--run-id", "a" * 32, check=False)
    assert rejected.returncode != 0
    assert not list(target.iterdir())

    missing_root = subprocess.run(
        [*CLI, "launch", "--idempotency-key", "missing-root", "--steps", "1"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing_root.returncode != 0
    assert not (ROOT / "runs").exists()
    assert not list(target.iterdir())
