from __future__ import annotations

import fcntl
import os
import sqlite3
import time
from pathlib import Path

import pytest

from sawopt.io.synthetic_task_ledger import SyntheticTaskError, SyntheticTaskLedger


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "ledger"
    root.mkdir(mode=0o700, parents=True)
    return root


def test_request_identity_and_interrupted_launch_intent_fail_closed(tmp_path):
    root = _root(tmp_path)
    ledger = SyntheticTaskLedger(root)
    created, is_new = ledger.create_task("once", steps=3, interval_ms=10)
    assert is_new is True
    assert created.ledger_state == "CREATED"
    assert created.authorization_test_only is True

    same, is_new = ledger.create_task("once", steps=3, interval_ms=10)
    assert is_new is False
    assert same.run_id == created.run_id
    assert same.attempt_id == created.attempt_id
    with pytest.raises(SyntheticTaskError) as conflict:
        ledger.create_task("once", steps=4, interval_ms=10)
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"

    # Crash after the durable launch intent, before a child claims the attempt.
    ledger.begin_launch(created.run_id, created.attempt_id)
    observed = ledger.get_status(created.run_id)
    assert observed.state == "LAUNCH_AMBIGUOUS"
    assert observed.ledger_state == "STARTING"
    assert observed.owner_pid is None

    repeated, is_new = ledger.create_task("once", steps=3, interval_ms=10)
    assert is_new is False
    assert repeated.run_id == created.run_id
    assert repeated.state == "LAUNCH_AMBIGUOUS"
    assert repeated.owner_pid is None


def test_unsupported_schema_and_corrupt_database_fail_closed(tmp_path):
    root = _root(tmp_path)
    ledger = SyntheticTaskLedger(root)
    ledger.create_task("schema", steps=1, interval_ms=10)
    with sqlite3.connect(root / "synthetic-tasks.sqlite3") as connection:
        connection.execute("PRAGMA user_version=999")

    with pytest.raises(SyntheticTaskError) as unknown:
        ledger.get_status("0" * 32)
    assert unknown.value.code == "LEDGER_SCHEMA_UNKNOWN"

    altered_root = _root(tmp_path / "altered")
    altered = SyntheticTaskLedger(altered_root)
    altered.create_task("altered", steps=1, interval_ms=10)
    with sqlite3.connect(altered_root / "synthetic-tasks.sqlite3") as connection:
        sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'",
        ).fetchone()[0]
        assert "CHECK(length(run_id)=32)" in sql
        connection.execute("PRAGMA writable_schema=ON")
        connection.execute(
            "UPDATE sqlite_master SET sql=? WHERE type='table' AND name='tasks'",
            (sql.replace("CHECK(length(run_id)=32)", "CHECK(length(run_id)>0)", 1),),
        )
        connection.execute("PRAGMA schema_version=100")
    with pytest.raises(SyntheticTaskError) as altered_schema:
        altered.get_status("0" * 32)
    assert altered_schema.value.code == "LEDGER_SCHEMA_UNKNOWN"

    corrupt_root = _root(tmp_path / "other")
    corrupt = SyntheticTaskLedger(corrupt_root)
    corrupt.create_task("corrupt", steps=1, interval_ms=10)
    (corrupt_root / "synthetic-tasks.sqlite3").write_bytes(b"not sqlite data")
    with pytest.raises(SyntheticTaskError) as damaged:
        corrupt.get_status("0" * 32)
    assert damaged.value.code in {"LEDGER_CORRUPT", "LEDGER_SCHEMA_UNKNOWN"}


def test_task_ledger_file_lock_has_a_bounded_timeout(tmp_path, monkeypatch):
    root = _root(tmp_path)
    ledger = SyntheticTaskLedger(root)
    ledger.create_task("file-lock", steps=1, interval_ms=10)
    fd = os.open(root / "synthetic-tasks.sqlite3", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        monkeypatch.setattr("sawopt.io.synthetic_task_ledger.BUSY_TIMEOUT_MS", 50)
        started = time.monotonic()
        with pytest.raises(SyntheticTaskError) as locked:
            ledger.get_status("0" * 32)
        assert locked.value.code == "LEDGER_LOCKED"
        assert time.monotonic() - started < 0.5
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_task_log_is_private_and_hard_bounded(tmp_path):
    root = _root(tmp_path)
    ledger = SyntheticTaskLedger(root)
    ledger.create_task("log", steps=1, interval_ms=10)
    for _ in range(100):
        ledger.append_log("x" * 1000)
    log = root / "synthetic-tasks.log"
    assert log.stat().st_size == 16 * 1024
    assert log.stat().st_mode & 0o077 == 0


def test_diagnostic_log_lock_contention_is_bounded_and_best_effort(tmp_path):
    root = _root(tmp_path)
    ledger = SyntheticTaskLedger(root)
    task, _created = ledger.create_task("held-log", steps=1, interval_ms=10)
    assert ledger.append_log("initial") is True
    fd = os.open(root / "synthetic-tasks.log", os.O_WRONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        started = time.monotonic()
        assert ledger.append_log("must be skipped") is False
        assert time.monotonic() - started < 0.5
        status = ledger.get_status(task.run_id)
        assert status.ledger_state == "CREATED"
        assert status.state == "RECOVERY_REQUIRED"
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_sqlite_writer_lock_is_reported_without_repair_or_reset(tmp_path, monkeypatch):
    root = _root(tmp_path)
    ledger = SyntheticTaskLedger(root)
    ledger.create_task("locked", steps=1, interval_ms=10)
    external = sqlite3.connect(root / "synthetic-tasks.sqlite3", timeout=0.1, isolation_level=None)
    try:
        external.execute("BEGIN IMMEDIATE")
        monkeypatch.setattr("sawopt.io.synthetic_task_ledger.BUSY_TIMEOUT_MS", 50)
        with pytest.raises(SyntheticTaskError) as locked:
            ledger.create_task("blocked", steps=1, interval_ms=10)
        assert locked.value.code == "LEDGER_LOCKED"
        external.rollback()
        status, created = ledger.create_task("blocked", steps=1, interval_ms=10)
        assert created is True
        assert status.state == "RECOVERY_REQUIRED"
    finally:
        if external.in_transaction:
            external.rollback()
        external.close()
