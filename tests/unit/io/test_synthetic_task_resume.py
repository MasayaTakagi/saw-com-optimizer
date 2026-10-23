from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest
import sawopt.cli as cli
import sawopt.io.synthetic_task_ledger as ledger_module
from sawopt.cli import build_parser
from sawopt.io.synthetic_task_ledger import (
    DB_NAME, SyntheticTaskError, SyntheticTaskLedger, _TASKS_SCHEMA, _canonical_request,
    _linux_boot_id, _read_process_identity,
)


def test_resume_requires_explicit_root_run_and_predecessor_attempt():
    root = Path("/tmp/synthetic-recovery-test")
    parsed = build_parser().parse_args([
        "synthetic-task", "resume",
        "--root", str(root),
        "--run-id", "a" * 32,
        "--expected-attempt-id", "b" * 32,
    ])

    assert parsed.command == "synthetic-task"
    assert parsed.task_command == "resume"
    assert parsed.root == str(root)
    assert parsed.run_id == "a" * 32
    assert parsed.expected_attempt_id == "b" * 32


def _v1_root(root: Path, *, state: str = "STARTING") -> tuple[str, str]:
    root.mkdir(mode=0o700)
    run_id, attempt_id = uuid.uuid4().hex, uuid.uuid4().hex
    request_json, request_hash = _canonical_request(20, 50)
    now = "2026-10-23T00:00:00.000000Z"
    with sqlite3.connect(root / DB_NAME) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(_TASKS_SCHEMA)
        connection.execute("PRAGMA user_version=1")
        connection.execute(
            """INSERT INTO tasks (
                run_id,request_json,request_sha256,idempotency_key,authorization_test_only,attempt_id,
                state,progress_completed,created_at,updated_at
            ) VALUES (?,?,?,?,1,?,?,0,?,?)""",
            (run_id, request_json, request_hash, "old-v1-task", attempt_id, state, now, now),
        )
    os.chmod(root / DB_NAME, 0o600)
    for sidecar in root.glob(f"{DB_NAME}-*"):
        os.chmod(sidecar, 0o600)
    return run_id, attempt_id


def _claimed_dead_v2_task(root: Path) -> tuple[SyntheticTaskLedger, str, str]:
    root.mkdir(mode=0o700)
    ledger = SyntheticTaskLedger(root)
    task, _created = ledger.create_task("dead-v2", steps=6, interval_ms=10)
    ledger.begin_launch(task.run_id, task.attempt_id)
    dead_pid = 2_000_000_000
    assert _read_process_identity(dead_pid) is None
    boot_id = _linux_boot_id()
    with sqlite3.connect(root / DB_NAME) as connection:
        connection.execute(
            """UPDATE tasks SET state='RUNNING',progress_completed=2,owner_pid=?,owner_start_ticks=1,
               owner_boot_id=?,started_at=created_at WHERE run_id=?""",
            (dead_pid, boot_id, task.run_id),
        )
        connection.execute(
            """UPDATE attempts SET state='RUNNING',progress_end=2,owner_pid=?,owner_start_ticks=1,
               owner_boot_id=?,started_at=created_at WHERE run_id=? AND attempt_id=?""",
            (dead_pid, boot_id, task.run_id, task.attempt_id),
        )
    return ledger, task.run_id, task.attempt_id


def test_restart_intent_without_spawn_is_ambiguous_and_stale_attempt_is_fenced(tmp_path):
    root = tmp_path / "recovery-intent"
    ledger, run_id, old_attempt_id = _claimed_dead_v2_task(root)

    successor = ledger.resume_task(run_id, old_attempt_id)
    assert successor.run_id == run_id
    assert successor.attempt_generation == 2
    assert successor.predecessor_attempt_id == old_attempt_id
    assert successor.progress_completed == 2
    assert successor.state == "LAUNCH_AMBIGUOUS"

    # Simulate process death after durable resume intent but before spawning.
    observed = ledger.get_status(run_id)
    assert observed.ledger_state == "STARTING"
    assert observed.state == "LAUNCH_AMBIGUOUS"
    with pytest.raises(SyntheticTaskError) as stale_resume:
        ledger.resume_task(run_id, old_attempt_id)
    assert stale_resume.value.code == "ATTEMPT_MISMATCH"
    with pytest.raises(SyntheticTaskError) as stale_progress:
        ledger.record_step(run_id, old_attempt_id)
    assert stale_progress.value.code == "PROCESS_IDENTITY_UNKNOWN"
    assert ledger.get_status(run_id).progress_completed == 2
    with sqlite3.connect(root / DB_NAME) as connection:
        assert connection.execute(
            "SELECT count(*) FROM attempts WHERE run_id=?", (run_id,),
        ).fetchone()[0] == 2


def test_resume_transaction_failure_rolls_back_attempt_lineage_and_progress(tmp_path, monkeypatch):
    root = tmp_path / "resume-rollback"
    ledger, run_id, attempt_id = _claimed_dead_v2_task(root)

    def fail_before_commit(*_args, **_kwargs):
        raise RuntimeError("injected failure after transition writes, before commit")

    with monkeypatch.context() as patch:
        patch.setattr("sawopt.io.synthetic_task_recovery.SyntheticTaskRecoveryLedger._snapshot_v2", fail_before_commit)
        with pytest.raises(RuntimeError, match="injected failure"):
            ledger.resume_task(run_id, attempt_id)

    with sqlite3.connect(root / DB_NAME) as connection:
        task = connection.execute(
            "SELECT current_attempt_id,attempt_generation,state,progress_completed FROM tasks WHERE run_id=?",
            (run_id,),
        ).fetchone()
        attempts = connection.execute(
            "SELECT attempt_id,generation,state,progress_start,progress_end FROM attempts WHERE run_id=?",
            (run_id,),
        ).fetchall()
    assert task == (attempt_id, 1, "RUNNING", 2)
    assert attempts == [(attempt_id, 1, "RUNNING", 0, 2)]


def test_resume_spawn_without_claim_stays_ambiguous_and_cannot_be_retried(tmp_path, monkeypatch, capsys):
    root = tmp_path / "spawn-no-claim"
    ledger, run_id, old_attempt_id = _claimed_dead_v2_task(root)
    calls = []
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *args, **kwargs: calls.append(args) or object())

    assert cli.main([
        "synthetic-task", "resume", "--root", str(root), "--run-id", run_id,
        "--expected-attempt-id", old_attempt_id,
    ]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["state"] == "LAUNCH_AMBIGUOUS"
    assert response["ledger_state"] == "STARTING"
    assert response["attempt_generation"] == 2
    assert len(calls) == 1
    assert ledger.get_status(run_id).ledger_state == "STARTING"

    assert cli.main([
        "synthetic-task", "resume", "--root", str(root), "--run-id", run_id,
        "--expected-attempt-id", old_attempt_id,
    ]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "ATTEMPT_MISMATCH"
    assert len(calls) == 1


def test_resume_spawn_failure_stays_ambiguous_and_cannot_be_retried(tmp_path, monkeypatch, capsys):
    root = tmp_path / "spawn-failure"
    ledger, run_id, old_attempt_id = _claimed_dead_v2_task(root)
    calls = []

    def fail_spawn(*_args, **_kwargs):
        calls.append(True)
        raise OSError("injected process-creation failure")

    monkeypatch.setattr(cli.subprocess, "Popen", fail_spawn)
    assert cli.main([
        "synthetic-task", "resume", "--root", str(root), "--run-id", run_id,
        "--expected-attempt-id", old_attempt_id,
    ]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "LAUNCH_AMBIGUOUS"
    status = ledger.get_status(run_id)
    assert status.ledger_state == "LAUNCH_AMBIGUOUS"
    assert status.attempt_generation == 2
    assert status.progress_completed == 2

    assert cli.main([
        "synthetic-task", "resume", "--root", str(root), "--run-id", run_id,
        "--expected-attempt-id", old_attempt_id,
    ]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "ATTEMPT_MISMATCH"
    assert calls == [True]


def test_reboot_recovery_requires_absent_pid_and_all_other_identity_checks(tmp_path):
    absent_root = tmp_path / "reboot-absent"
    absent_ledger, absent_run, absent_attempt = _claimed_dead_v2_task(absent_root)
    with sqlite3.connect(absent_root / DB_NAME) as connection:
        connection.execute("UPDATE tasks SET owner_boot_id=? WHERE run_id=?", ("old-boot-id", absent_run))
        connection.execute("UPDATE attempts SET owner_boot_id=? WHERE run_id=?", ("old-boot-id", absent_run))
    resumed = absent_ledger.resume_task(absent_run, absent_attempt)
    assert resumed.attempt_generation == 2
    assert resumed.predecessor_attempt_id == absent_attempt

    present_root = tmp_path / "reboot-present-pid"
    present_ledger, present_run, present_attempt = _claimed_dead_v2_task(present_root)
    from sawopt.io.synthetic_task_ledger import current_process_identity

    pid, start_ticks, _boot = current_process_identity()
    with sqlite3.connect(present_root / DB_NAME) as connection:
        connection.execute(
            "UPDATE tasks SET owner_pid=?,owner_start_ticks=?,owner_boot_id=? WHERE run_id=?",
            (pid, start_ticks, "old-boot-id", present_run),
        )
        connection.execute(
            "UPDATE attempts SET owner_pid=?,owner_start_ticks=?,owner_boot_id=? WHERE run_id=?",
            (pid, start_ticks, "old-boot-id", present_run),
        )
    with pytest.raises(SyntheticTaskError) as ambiguous:
        present_ledger.resume_task(present_run, present_attempt)
    assert ambiguous.value.code == "RECOVERY_AMBIGUOUS"
    with sqlite3.connect(present_root / DB_NAME) as connection:
        assert connection.execute(
            "SELECT count(*) FROM attempts WHERE run_id=?", (present_run,),
        ).fetchone()[0] == 1


def test_matching_zombie_identity_is_recoverable_without_signalling(tmp_path, monkeypatch):
    root = tmp_path / "zombie-process"
    ledger, run_id, attempt_id = _claimed_dead_v2_task(root)
    pid = os.getpid()
    start_ticks = 123456
    boot_id = _linux_boot_id()
    with sqlite3.connect(root / DB_NAME) as connection:
        connection.execute(
            "UPDATE tasks SET owner_pid=?,owner_start_ticks=?,owner_boot_id=? WHERE run_id=?",
            (pid, start_ticks, boot_id, run_id),
        )
        connection.execute(
            "UPDATE attempts SET owner_pid=?,owner_start_ticks=?,owner_boot_id=? WHERE run_id=?",
            (pid, start_ticks, boot_id, run_id),
        )
    monkeypatch.setattr(
        "sawopt.io.synthetic_task_recovery._proc_stat",
        lambda observed_pid: (start_ticks, "Z") if observed_pid == pid else None,
    )
    monkeypatch.setattr("sawopt.io.synthetic_task_recovery._proc_argv", lambda _pid: ())

    resumed = ledger.resume_task(run_id, attempt_id)
    assert resumed.attempt_generation == 2
    assert resumed.predecessor_attempt_id == attempt_id
    assert resumed.progress_completed == 2


def test_missing_argv_for_live_pid_is_ambiguous_not_proof_of_death(tmp_path, monkeypatch):
    root = tmp_path / "missing-argv"
    ledger, run_id, attempt_id = _claimed_dead_v2_task(root)
    pid = os.getpid()
    start_ticks = 123456
    boot_id = _linux_boot_id()
    with sqlite3.connect(root / DB_NAME) as connection:
        connection.execute(
            "UPDATE tasks SET owner_pid=?,owner_start_ticks=?,owner_boot_id=? WHERE run_id=?",
            (pid, start_ticks, boot_id, run_id),
        )
        connection.execute(
            "UPDATE attempts SET owner_pid=?,owner_start_ticks=?,owner_boot_id=? WHERE run_id=?",
            (pid, start_ticks, boot_id, run_id),
        )
    monkeypatch.setattr(
        "sawopt.io.synthetic_task_recovery._proc_stat",
        lambda observed_pid: (start_ticks, "S") if observed_pid == pid else None,
    )
    monkeypatch.setattr("sawopt.io.synthetic_task_recovery._proc_argv", lambda _pid: None)

    with pytest.raises(SyntheticTaskError) as ambiguous:
        ledger.resume_task(run_id, attempt_id)
    assert ambiguous.value.code == "RECOVERY_AMBIGUOUS"
    with sqlite3.connect(root / DB_NAME) as connection:
        assert connection.execute(
            "SELECT count(*) FROM attempts WHERE run_id=?", (run_id,),
        ).fetchone()[0] == 1


def test_foreign_live_argv_is_not_accepted_as_dead_or_owned_worker(tmp_path):
    root = tmp_path / "foreign-process"
    ledger, run_id, attempt_id = _claimed_dead_v2_task(root)
    from sawopt.io.synthetic_task_ledger import current_process_identity

    pid, start_ticks, boot_id = current_process_identity()
    with sqlite3.connect(root / DB_NAME) as connection:
        connection.execute(
            "UPDATE tasks SET owner_pid=?,owner_start_ticks=?,owner_boot_id=? WHERE run_id=?",
            (pid, start_ticks, boot_id, run_id),
        )
        connection.execute(
            "UPDATE attempts SET owner_pid=?,owner_start_ticks=?,owner_boot_id=? WHERE run_id=?",
            (pid, start_ticks, boot_id, run_id),
        )

    with pytest.raises(SyntheticTaskError) as ambiguous:
        ledger.resume_task(run_id, attempt_id)
    assert ambiguous.value.code == "RECOVERY_AMBIGUOUS"
    with sqlite3.connect(root / DB_NAME) as connection:
        assert connection.execute(
            "SELECT count(*) FROM attempts WHERE run_id=?", (run_id,),
        ).fetchone()[0] == 1


def test_v2_status_and_attach_are_read_only_and_never_spawn(tmp_path, monkeypatch, capsys):
    root = tmp_path / "read-only-views"
    ledger, run_id, _attempt_id = _claimed_dead_v2_task(root)
    spawn_calls = []
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *args, **kwargs: spawn_calls.append(args))
    with sqlite3.connect(root / DB_NAME) as connection:
        before = (
            connection.execute("SELECT * FROM tasks WHERE run_id=?", (run_id,)).fetchone(),
            connection.execute("SELECT * FROM attempts WHERE run_id=?", (run_id,)).fetchall(),
        )

    status = ledger.get_status(run_id)
    assert status.state == "RECOVERY_REQUIRED"
    assert cli.main(["synthetic-task", "attach", "--root", str(root), "--run-id", run_id]) == 0
    assert json.loads(capsys.readouterr().out)["attached"] is True
    with sqlite3.connect(root / DB_NAME) as connection:
        after = (
            connection.execute("SELECT * FROM tasks WHERE run_id=?", (run_id,)).fetchone(),
            connection.execute("SELECT * FROM attempts WHERE run_id=?", (run_id,)).fetchall(),
        )
    assert after == before
    assert spawn_calls == []


def test_unreadable_process_identity_is_not_treated_as_death(tmp_path, monkeypatch):
    root = tmp_path / "unknown-process"
    ledger, run_id, attempt_id = _claimed_dead_v2_task(root)

    def unreadable(_pid):
        raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "injected unreadable proc state")

    monkeypatch.setattr("sawopt.io.synthetic_task_recovery._proc_stat", unreadable)
    with pytest.raises(SyntheticTaskError) as ambiguous:
        ledger.resume_task(run_id, attempt_id)
    assert ambiguous.value.code == "RECOVERY_AMBIGUOUS"
    with sqlite3.connect(root / DB_NAME) as connection:
        assert connection.execute(
            "SELECT count(*) FROM attempts WHERE run_id=?", (run_id,),
        ).fetchone()[0] == 1


@pytest.mark.parametrize(
    "state", ["CREATED", "STARTING", "STOP_REQUESTED", "STOPPED", "COMPLETED", "FAILED", "LAUNCH_AMBIGUOUS"],
)
def test_unclaimed_cancelled_and_terminal_states_cannot_resume(tmp_path, state):
    root = tmp_path / f"blocked-{state.lower()}"
    if state == "CREATED":
        root.mkdir(mode=0o700)
        ledger = SyntheticTaskLedger(root)
        task, _created = ledger.create_task("blocked", steps=6, interval_ms=10)
        run_id, attempt_id = task.run_id, task.attempt_id
    else:
        ledger, run_id, attempt_id = _claimed_dead_v2_task(root)
        no_owner = state in ("STARTING", "LAUNCH_AMBIGUOUS")
        terminal = state in ("STOPPED", "COMPLETED", "FAILED", "LAUNCH_AMBIGUOUS")
        progress = 6 if state == "COMPLETED" else 0 if no_owner else 2
        with sqlite3.connect(root / DB_NAME) as connection:
            created_at = connection.execute(
                "SELECT created_at FROM tasks WHERE run_id=?", (run_id,),
            ).fetchone()[0]
            connection.execute(
                "UPDATE tasks SET state=?,progress_completed=?,stop_requested_at=?,finished_at=?,"
                "owner_pid=CASE WHEN ? THEN NULL ELSE owner_pid END,"
                "owner_start_ticks=CASE WHEN ? THEN NULL ELSE owner_start_ticks END,"
                "owner_boot_id=CASE WHEN ? THEN NULL ELSE owner_boot_id END WHERE run_id=?",
                (state, progress, created_at if state in ("STOP_REQUESTED", "STOPPED") else None,
                 created_at if terminal else None, no_owner, no_owner, no_owner, run_id),
            )
            connection.execute(
                "UPDATE attempts SET state=?,progress_end=?,finished_at=?,"
                "owner_pid=CASE WHEN ? THEN NULL ELSE owner_pid END,"
                "owner_start_ticks=CASE WHEN ? THEN NULL ELSE owner_start_ticks END,"
                "owner_boot_id=CASE WHEN ? THEN NULL ELSE owner_boot_id END WHERE run_id=?",
                (state, progress, created_at if terminal else None,
                 no_owner, no_owner, no_owner, run_id),
            )
    with sqlite3.connect(root / DB_NAME) as connection:
        before = connection.execute(
            "SELECT state,current_attempt_id,attempt_generation,progress_completed FROM tasks WHERE run_id=?",
            (run_id,),
        ).fetchone()
    with pytest.raises(SyntheticTaskError) as rejected:
        ledger.resume_task(run_id, attempt_id)
    assert rejected.value.code == "RECOVERY_UNSUPPORTED"
    with sqlite3.connect(root / DB_NAME) as connection:
        after = connection.execute(
            "SELECT state,current_attempt_id,attempt_generation,progress_completed FROM tasks WHERE run_id=?",
            (run_id,),
        ).fetchone()
        assert after == before
        assert connection.execute(
            "SELECT count(*) FROM attempts WHERE run_id=?", (run_id,),
        ).fetchone()[0] == 1


def test_root_swap_after_validation_cannot_redirect_v2_ledger_to_raw_root(tmp_path, monkeypatch):
    root = tmp_path / "validated-root"
    root.mkdir(mode=0o700)
    raw_root = tmp_path / "raw-root"
    raw_root.mkdir(mode=0o700)
    sentinel = raw_root / "historic-sentinel"
    sentinel.write_text("immutable", encoding="utf-8")
    monkeypatch.setenv("SAWOPT_DATA_ROOT", str(raw_root))
    original_safe_root = ledger_module._safe_root
    swapped = False

    def swap_after_validation(candidate, *, require_ledger):
        nonlocal swapped
        validated = original_safe_root(candidate, require_ledger=require_ledger)
        if not swapped:
            root.rmdir()
            root.symlink_to(raw_root, target_is_directory=True)
            swapped = True
        return validated

    monkeypatch.setattr("sawopt.io.synthetic_task_ledger._safe_root", swap_after_validation)
    with pytest.raises(SyntheticTaskError) as unsafe:
        SyntheticTaskLedger(root).create_task("unsafe-swap", steps=2, interval_ms=10)
    assert unsafe.value.code == "TASK_ROOT_UNSAFE"
    assert sentinel.read_text(encoding="utf-8") == "immutable"
    assert sorted(item.name for item in raw_root.iterdir()) == ["historic-sentinel"]


@pytest.mark.parametrize("identity_kind", ["source", "runtime"])
def test_current_source_or_runtime_identity_mismatch_blocks_resume(tmp_path, monkeypatch, identity_kind):
    root = tmp_path / f"current-{identity_kind}-mismatch"
    ledger, run_id, attempt_id = _claimed_dead_v2_task(root)
    from sawopt.io.synthetic_task_recovery import _source_and_runtime_identity

    source_sha, runtime_sha = _source_and_runtime_identity()
    if identity_kind == "source":
        observed_identity = ("1" * 64, runtime_sha)
    else:
        observed_identity = (source_sha, "2" * 64)
    monkeypatch.setattr(
        "sawopt.io.synthetic_task_recovery._source_and_runtime_identity",
        lambda: observed_identity,
    )
    with pytest.raises(SyntheticTaskError) as mismatch:
        ledger.resume_task(run_id, attempt_id)
    assert mismatch.value.code == "SOURCE_IDENTITY_MISMATCH"
    with sqlite3.connect(root / DB_NAME) as connection:
        assert connection.execute(
            "SELECT count(*) FROM attempts WHERE run_id=?", (run_id,),
        ).fetchone()[0] == 1


def test_runtime_identity_changes_when_interpreter_binary_digest_changes(monkeypatch):
    import sawopt.io.synthetic_task_recovery as recovery_module

    original_hash = recovery_module._hash_regular_file
    source_sha, runtime_sha = recovery_module._source_and_runtime_identity()
    executable = Path(sys.executable).resolve(strict=True)

    def altered_executable_digest(path):
        digest, size = original_hash(path)
        if Path(path).resolve(strict=True) == executable:
            return "f" * 64, size
        return digest, size

    monkeypatch.setattr(recovery_module, "_hash_regular_file", altered_executable_digest)
    changed_source_sha, changed_runtime_sha = recovery_module._source_and_runtime_identity()
    assert changed_source_sha == source_sha
    assert changed_runtime_sha != runtime_sha


def test_source_identity_mismatch_and_unknown_schema_fail_without_successor(tmp_path):
    root = tmp_path / "identity-mismatch"
    ledger, run_id, attempt_id = _claimed_dead_v2_task(root)
    with sqlite3.connect(root / DB_NAME) as connection:
        connection.execute("UPDATE tasks SET source_contract_sha256=? WHERE run_id=?", ("0" * 64, run_id))
        connection.execute("UPDATE attempts SET source_contract_sha256=? WHERE run_id=?", ("0" * 64, run_id))
    status = ledger.get_status(run_id)
    assert status.state == "SOURCE_IDENTITY_MISMATCH"
    assert status.as_dict()["error"]["code"] == "SOURCE_IDENTITY_MISMATCH"
    with pytest.raises(SyntheticTaskError) as mismatch:
        ledger.resume_task(run_id, attempt_id)
    assert mismatch.value.code == "SOURCE_IDENTITY_MISMATCH"
    with sqlite3.connect(root / DB_NAME) as connection:
        assert connection.execute(
            "SELECT count(*) FROM attempts WHERE run_id=?", (run_id,),
        ).fetchone()[0] == 1

    with sqlite3.connect(root / DB_NAME) as connection:
        connection.execute("PRAGMA user_version=999")
    with pytest.raises(SyntheticTaskError) as unknown:
        ledger.resume_task(run_id, attempt_id)
    assert unknown.value.code == "LEDGER_SCHEMA_UNKNOWN"


def test_unrecognized_v2_schema_objects_block_resume_without_successor(tmp_path):
    root = tmp_path / "malformed-v2"
    ledger, run_id, attempt_id = _claimed_dead_v2_task(root)
    with sqlite3.connect(root / DB_NAME) as connection:
        connection.execute(
            "CREATE TRIGGER unexpected_task_trigger AFTER UPDATE ON tasks BEGIN SELECT 1; END",
        )

    with pytest.raises(SyntheticTaskError) as unknown:
        ledger.resume_task(run_id, attempt_id)
    assert unknown.value.code == "LEDGER_SCHEMA_UNKNOWN"
    with sqlite3.connect(root / DB_NAME) as connection:
        assert connection.execute(
            "SELECT count(*) FROM attempts WHERE run_id=?", (run_id,),
        ).fetchone()[0] == 1


def test_v1_root_operations_remain_and_resume_rejects_without_mutation(tmp_path, monkeypatch, capsys):
    root = tmp_path / "old-v1"
    run_id, attempt_id = _v1_root(root)
    spawn_calls = []
    with monkeypatch.context() as patch:
        patch.setattr(cli.subprocess, "Popen", lambda *args, **kwargs: spawn_calls.append(args))
        assert cli.main([
            "synthetic-task", "launch", "--root", str(root), "--idempotency-key", "old-v1-task",
            "--steps", "20", "--interval-ms", "50",
        ]) == 0
        launched = json.loads(capsys.readouterr().out)
        assert launched["created"] is False
        assert launched["run_id"] == run_id
        assert launched["attempt_id"] == attempt_id
        assert spawn_calls == []

    before = sqlite3.connect(root / DB_NAME).execute(
        "SELECT state,progress_completed,attempt_id,request_sha256 FROM tasks WHERE run_id=?", (run_id,),
    ).fetchone()
    assert cli.main(["synthetic-task", "status", "--root", str(root), "--run-id", run_id]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["state"] == "LAUNCH_AMBIGUOUS"
    assert status["ledger_state"] == "STARTING"
    assert cli.main(["synthetic-task", "attach", "--root", str(root), "--run-id", run_id]) == 0
    assert json.loads(capsys.readouterr().out)["attached"] is True

    assert cli.main([
        "synthetic-task", "resume", "--root", str(root), "--run-id", run_id,
        "--expected-attempt-id", attempt_id,
    ]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "RECOVERY_UNSUPPORTED"
    after = sqlite3.connect(root / DB_NAME).execute(
        "SELECT state,progress_completed,attempt_id,request_sha256 FROM tasks WHERE run_id=?", (run_id,),
    ).fetchone()
    assert after == before
    assert spawn_calls == []

    # Exercise original v1 exact-attempt stop semantics with a synthetic
    # process-identity fixture; no process is signalled or v1 data migrated.
    fake_pid, fake_start, fake_boot = 2_000_000_000, 17, "test-boot-id"
    with sqlite3.connect(root / DB_NAME) as connection:
        connection.execute(
            """UPDATE tasks SET state='RUNNING',owner_pid=?,owner_start_ticks=?,owner_boot_id=?
               WHERE run_id=?""",
            (fake_pid, fake_start, fake_boot, run_id),
        )
    with monkeypatch.context() as patch:
        patch.setattr(
            "sawopt.io.synthetic_task_ledger._read_process_identity",
            lambda pid: (fake_boot, fake_start, "S") if pid == fake_pid else None,
        )
        patch.setattr("sawopt.io.synthetic_task_ledger._is_expected_worker", lambda *args: True)
        assert cli.main([
            "synthetic-task", "stop", "--root", str(root), "--run-id", run_id,
            "--attempt-id", attempt_id,
        ]) == 0
        assert json.loads(capsys.readouterr().out)["state"] == "STOP_REQUESTED"
        assert cli.main([
            "synthetic-task", "stop", "--root", str(root), "--run-id", run_id,
            "--attempt-id", "0" * 32,
        ]) == 2
        assert json.loads(capsys.readouterr().err)["error"]["code"] == "ATTEMPT_MISMATCH"
    stopped = sqlite3.connect(root / DB_NAME).execute(
        "SELECT state,progress_completed,attempt_id FROM tasks WHERE run_id=?", (run_id,),
    ).fetchone()
    assert stopped == ("STOP_REQUESTED", 0, attempt_id)


def test_resume_help_is_explicitly_synthetic_and_requires_operator_action():
    parser = build_parser()
    task_parser = next(action for action in parser._actions if action.dest == "command")
    synthetic_action = next(action for action in task_parser.choices["synthetic-task"]._actions if action.dest == "task_command")
    resume_help = next(action.help for action in synthetic_action._choices_actions if action.dest == "resume")

    assert "synthetic" in resume_help.lower()
    assert "explicit" in resume_help.lower() or "operator" in resume_help.lower()
