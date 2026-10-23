"""Future-only v2 ledger contract for explicit synthetic countdown recovery.

Existing schema-v1 roots continue through ``_SyntheticTaskLedgerV1`` and are
never migrated. This module adds no scientific or external side effects.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
import uuid
from pathlib import Path
from typing import Any

from .synthetic_task_ledger import (
    DB_NAME,
    MAX_ERROR_BYTES,
    MAX_INTERVAL_MS,
    MAX_STEPS,
    MIN_INTERVAL_MS,
    SyntheticTaskError,
    TaskSnapshot,
    current_process_identity,
    _SyntheticTaskLedgerV1,
    _linux_boot_id,
    _validate_attempt_id,
    _validate_key,
    _validate_run_id,
)

V2_SCHEMA_VERSION = 2
V2_REQUEST_KIND = "synthetic-countdown-v2"
_V2_TASKS_SCHEMA = """CREATE TABLE tasks (
    run_id TEXT PRIMARY KEY CHECK(length(run_id)=32),
    task_kind TEXT NOT NULL CHECK(task_kind='synthetic-countdown-v2'),
    request_json TEXT NOT NULL CHECK(length(request_json)<=256),
    request_sha256 TEXT NOT NULL CHECK(length(request_sha256)=64),
    idempotency_key TEXT NOT NULL UNIQUE CHECK(length(idempotency_key) BETWEEN 1 AND 128),
    authorization_test_only INTEGER NOT NULL CHECK(authorization_test_only=1),
    current_attempt_id TEXT NOT NULL CHECK(length(current_attempt_id)=32),
    attempt_generation INTEGER NOT NULL CHECK(attempt_generation>=1),
    state TEXT NOT NULL CHECK(state IN (
        'CREATED','STARTING','RUNNING','STOP_REQUESTED','STOPPED','COMPLETED','FAILED','LAUNCH_AMBIGUOUS'
    )),
    progress_completed INTEGER NOT NULL DEFAULT 0 CHECK(progress_completed>=0 AND progress_completed<=120),
    source_contract_sha256 TEXT NOT NULL CHECK(length(source_contract_sha256)=64),
    runtime_identity_sha256 TEXT NOT NULL CHECK(length(runtime_identity_sha256)=64),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    last_progress_at TEXT,
    stop_requested_at TEXT,
    owner_pid INTEGER,
    owner_start_ticks INTEGER,
    owner_boot_id TEXT,
    error_code TEXT,
    error_message TEXT CHECK(error_message IS NULL OR length(error_message)<=512),
    CHECK((owner_pid IS NULL AND owner_start_ticks IS NULL AND owner_boot_id IS NULL)
       OR (owner_pid>0 AND owner_start_ticks>=0 AND length(owner_boot_id) BETWEEN 1 AND 64))
)"""
_V2_ATTEMPTS_SCHEMA = """CREATE TABLE attempts (
    attempt_id TEXT PRIMARY KEY CHECK(length(attempt_id)=32),
    run_id TEXT NOT NULL REFERENCES tasks(run_id),
    generation INTEGER NOT NULL CHECK(generation>=1),
    predecessor_attempt_id TEXT,
    state TEXT NOT NULL CHECK(state IN (
        'CREATED','STARTING','RUNNING','STOP_REQUESTED','STOPPED','COMPLETED','FAILED','LAUNCH_AMBIGUOUS','SUPERSEDED'
    )),
    progress_start INTEGER NOT NULL CHECK(progress_start>=0 AND progress_start<=120),
    progress_end INTEGER NOT NULL CHECK(progress_end>=progress_start AND progress_end<=120),
    source_contract_sha256 TEXT NOT NULL CHECK(length(source_contract_sha256)=64),
    runtime_identity_sha256 TEXT NOT NULL CHECK(length(runtime_identity_sha256)=64),
    expected_argv_json TEXT NOT NULL CHECK(length(expected_argv_json)<=2048),
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    owner_pid INTEGER,
    owner_start_ticks INTEGER,
    owner_boot_id TEXT,
    UNIQUE(run_id,generation),
    CHECK((owner_pid IS NULL AND owner_start_ticks IS NULL AND owner_boot_id IS NULL)
       OR (owner_pid>0 AND owner_start_ticks>=0 AND length(owner_boot_id) BETWEEN 1 AND 64))
)"""


def _initialize_v2(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("BEGIN IMMEDIATE")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
            )
        }
        if version != 0 or tables:
            raise SyntheticTaskError("LEDGER_SCHEMA_UNKNOWN", "new v2 ledger file is not empty")
        conn.execute(_V2_TASKS_SCHEMA)
        conn.execute(_V2_ATTEMPTS_SCHEMA)
        conn.execute(f"PRAGMA user_version={V2_SCHEMA_VERSION}")
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise


def _validate_schema_v2(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version != V2_SCHEMA_VERSION:
        raise SyntheticTaskError("LEDGER_SCHEMA_UNKNOWN", f"unsupported SQLite task-ledger schema version {version}")
    objects = {
        (row[0], row[1]) for row in conn.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'",
        )
    }
    if objects != {("table", "tasks"), ("table", "attempts")}:
        raise SyntheticTaskError("LEDGER_SCHEMA_UNKNOWN", "SQLite v2 task-ledger object set is unknown")
    for table, expected_sql, expected_columns in (
        (
            "tasks", _V2_TASKS_SCHEMA,
            (
                "run_id", "task_kind", "request_json", "request_sha256", "idempotency_key",
                "authorization_test_only", "current_attempt_id", "attempt_generation", "state",
                "progress_completed", "source_contract_sha256", "runtime_identity_sha256", "created_at",
                "updated_at", "started_at", "finished_at", "last_progress_at", "stop_requested_at",
                "owner_pid", "owner_start_ticks", "owner_boot_id", "error_code", "error_message",
            ),
        ),
        (
            "attempts", _V2_ATTEMPTS_SCHEMA,
            (
                "attempt_id", "run_id", "generation", "predecessor_attempt_id", "state", "progress_start",
                "progress_end", "source_contract_sha256", "runtime_identity_sha256", "expected_argv_json",
                "created_at", "started_at", "finished_at", "owner_pid", "owner_start_ticks", "owner_boot_id",
            ),
        ),
    ):
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,),
        ).fetchone()
        if row is None or not isinstance(row[0], str):
            raise SyntheticTaskError("LEDGER_SCHEMA_UNKNOWN", f"SQLite v2 {table} definition is missing")
        if " ".join(row[0].split()) != " ".join(expected_sql.split()):
            raise SyntheticTaskError("LEDGER_SCHEMA_UNKNOWN", f"SQLite v2 {table} constraints do not match")
        columns = tuple(item[1] for item in conn.execute(f"PRAGMA table_info({table})"))
        if columns != expected_columns:
            raise SyntheticTaskError("LEDGER_SCHEMA_UNKNOWN", f"SQLite v2 {table} columns do not match")


def _hash_regular_file(path: Path) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise SyntheticTaskError("SOURCE_IDENTITY_UNKNOWN", "cannot open an identity-bound implementation file") from exc
    digest = hashlib.sha256()
    size = 0
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise SyntheticTaskError("SOURCE_IDENTITY_UNKNOWN", "identity-bound implementation is not a regular file")
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
        after = os.fstat(fd)
        if (
            before.st_dev != after.st_dev or before.st_ino != after.st_ino
            or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns or size != after.st_size
        ):
            raise SyntheticTaskError("SOURCE_IDENTITY_UNKNOWN", "identity-bound implementation changed while hashing")
        return digest.hexdigest(), size
    except OSError as exc:
        raise SyntheticTaskError("SOURCE_IDENTITY_UNKNOWN", "cannot hash identity-bound implementation") from exc
    finally:
        os.close(fd)


def _source_and_runtime_identity() -> tuple[str, str]:
    """Hash the exact allowlisted implementation and interpreter identity."""
    package_root = Path(__file__).resolve().parents[1]
    relative_files = (
        "cli.py", "io/synthetic_task_ledger.py", "io/synthetic_task_recovery.py", "synthetic_worker.py",
    )
    source = hashlib.sha256()
    for relative in relative_files:
        path = package_root / relative
        try:
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise SyntheticTaskError("SOURCE_IDENTITY_UNKNOWN", "synthetic implementation source is not a regular file")
            content_sha, content_size = _hash_regular_file(path)
        except SyntheticTaskError:
            raise
        except OSError as exc:
            raise SyntheticTaskError("SOURCE_IDENTITY_UNKNOWN", "cannot read synthetic implementation source") from exc
        encoded_name = relative.encode("ascii")
        source.update(len(encoded_name).to_bytes(4, "big"))
        source.update(encoded_name)
        source.update(content_size.to_bytes(8, "big"))
        source.update(bytes.fromhex(content_sha))

    try:
        executable = Path(sys.executable).resolve(strict=True)
        executable_info = os.stat(executable)
        if not stat.S_ISREG(executable_info.st_mode) or not os.access(executable, os.X_OK):
            raise OSError("interpreter is not an executable regular file")
        executable_sha, executable_size = _hash_regular_file(executable)
        runtime = {
            "implementation": sys.implementation.name,
            "python_version": list(sys.version_info[:3]),
            "executable": str(executable),
            "executable_size": executable_size,
            "executable_sha256": executable_sha,
        }
    except (OSError, RuntimeError) as exc:
        raise SyntheticTaskError("SOURCE_IDENTITY_UNKNOWN", "cannot establish Python executable identity") from exc
    runtime_json = json.dumps(runtime, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return source.hexdigest(), hashlib.sha256(runtime_json.encode("ascii")).hexdigest()


def _canonical_v2_request(steps: int, interval_ms: int) -> tuple[str, str]:
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= MAX_STEPS:
        raise SyntheticTaskError("REQUEST_INVALID", f"steps must be an integer in [1, {MAX_STEPS}]")
    if (
        isinstance(interval_ms, bool) or not isinstance(interval_ms, int)
        or not MIN_INTERVAL_MS <= interval_ms <= MAX_INTERVAL_MS
    ):
        raise SyntheticTaskError(
            "REQUEST_INVALID", f"interval_ms must be an integer in [{MIN_INTERVAL_MS}, {MAX_INTERVAL_MS}]",
        )
    value = {"kind": V2_REQUEST_KIND, "steps": steps, "interval_ms": interval_ms}
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return encoded, hashlib.sha256(encoded.encode("ascii")).hexdigest()


def _expected_worker_argv(root: str | os.PathLike[str], run_id: str, attempt_id: str) -> list[str]:
    return [
        "-m", "sawopt.synthetic_worker", "--root", str(Path(root).resolve(strict=True)),
        "--run-id", run_id, "--attempt-id", attempt_id,
    ]


def _validate_procfs() -> None:
    try:
        if not stat.S_ISDIR(os.stat("/proc").st_mode):
            raise OSError("/proc is not a directory")
        text = Path("/proc/self/stat").read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "Linux procfs is unavailable or unreadable") from exc
    close = text.rfind(")")
    fields = text[close + 1 :].strip().split() if close >= 0 else ()
    if len(fields) <= 19:
        raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "Linux procfs self identity is incomplete")
    try:
        if int(text[: text.find(" ")]) != os.getpid() or int(fields[19]) < 0:
            raise ValueError("self process identity mismatch")
    except ValueError as exc:
        raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "Linux procfs self identity is invalid") from exc


def _proc_stat(pid: int) -> tuple[int, str] | None:
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except FileNotFoundError:
        try:
            os.stat(f"/proc/{pid}")
        except FileNotFoundError:
            _validate_procfs()
            _linux_boot_id()
            return None
        except OSError as exc:
            raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "cannot establish whether the recorded PID exists") from exc
        raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "PID proc directory exists without a readable stat record")
    except (OSError, UnicodeError) as exc:
        raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "cannot read the recorded process identity") from exc
    close = text.rfind(")")
    if close < 0:
        raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "Linux process stat is malformed")
    fields = text[close + 1 :].strip().split()
    if len(fields) <= 19:
        raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "Linux process stat is incomplete")
    try:
        start_ticks = int(fields[19])
    except ValueError as exc:
        raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "Linux process start time is invalid") from exc
    if start_ticks < 0:
        raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "Linux process start time is invalid")
    return start_ticks, fields[0]


def _proc_argv(pid: int) -> tuple[bytes, ...] | None:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "cannot read the recorded process argv") from exc
    return tuple(part for part in raw.split(b"\0") if part)


def _process_state(row: sqlite3.Row, expected_argv: list[str]) -> str:
    """Return LIVE, DEAD, or UNKNOWN; never infer death from an identity mismatch."""
    pid = row["owner_pid"]
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return "UNKNOWN"
    try:
        _validate_procfs()
        current_boot = _linux_boot_id()
        process = _proc_stat(pid)
    except SyntheticTaskError:
        return "UNKNOWN"
    if process is None:
        return "DEAD"
    start_ticks, state = process
    if current_boot != row["owner_boot_id"] or start_ticks != row["owner_start_ticks"]:
        return "UNKNOWN"
    actual_argv = _proc_argv(pid)
    if actual_argv is None:
        try:
            os.stat(f"/proc/{pid}")
        except FileNotFoundError:
            try:
                _validate_procfs()
                _linux_boot_id()
            except SyntheticTaskError:
                return "UNKNOWN"
            return "DEAD"
        except OSError:
            return "UNKNOWN"
        return "UNKNOWN"
    try:
        actual_executable = Path(f"/proc/{pid}/exe").resolve(strict=True)
        expected_executable = Path(sys.executable).resolve(strict=True)
    except (OSError, RuntimeError):
        return "UNKNOWN"
    if actual_executable != expected_executable:
        return "UNKNOWN"
    expected = tuple(os.fsencode(value) for value in expected_argv)
    # The claimed worker recorded this complete argv before it could progress.
    # Linux may hide a zombie's argv after the process has exited; its matching
    # start ticks and boot ID still identify that already-claimed process.
    if state == "Z" and not actual_argv:
        return "DEAD"
    if len(actual_argv) < 2 or actual_argv[1:] != expected:
        return "UNKNOWN"
    if state == "Z":
        return "DEAD"
    return "LIVE"


class SyntheticTaskRecoveryLedger(_SyntheticTaskLedgerV1):
    """V2 same-ledger schema with attempt lineage and explicit safe recovery."""

    def _request_v2(self, row: sqlite3.Row) -> dict[str, Any]:
        try:
            request = json.loads(row["request_json"])
            if not isinstance(request, dict) or set(request) != {"kind", "steps", "interval_ms"}:
                raise ValueError("task request field set is invalid")
            encoded = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            digest = hashlib.sha256(encoded.encode("ascii")).hexdigest()
            if (
                digest != row["request_sha256"]
                or row["task_kind"] != V2_REQUEST_KIND
                or request["kind"] != V2_REQUEST_KIND
                or isinstance(request["steps"], bool)
                or not isinstance(request["steps"], int)
                or not 1 <= request["steps"] <= MAX_STEPS
                or isinstance(request["interval_ms"], bool)
                or not isinstance(request["interval_ms"], int)
                or not MIN_INTERVAL_MS <= request["interval_ms"] <= MAX_INTERVAL_MS
                or row["authorization_test_only"] != 1
            ):
                raise ValueError("task request fields are inconsistent")
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise SyntheticTaskError("LEDGER_CORRUPT", "v2 task request or immutable hash is invalid") from exc
        return request

    def _fetch_v2(self, conn: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        _validate_run_id(run_id)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise SyntheticTaskError("TASK_NOT_FOUND", "synthetic task run_id was not found")
        return row

    def _attempts_v2(self, conn: sqlite3.Connection, row: sqlite3.Row, request: dict[str, Any]) -> list[sqlite3.Row]:
        attempts = conn.execute(
            "SELECT * FROM attempts WHERE run_id=? ORDER BY generation", (row["run_id"],),
        ).fetchall()
        if (
            isinstance(row["attempt_generation"], bool)
            or not isinstance(row["attempt_generation"], int)
            or len(attempts) != row["attempt_generation"] or not attempts
            or isinstance(row["progress_completed"], bool)
            or not isinstance(row["progress_completed"], int)
            or not 0 <= row["progress_completed"] <= request["steps"]
        ):
            raise SyntheticTaskError("LEDGER_CORRUPT", "v2 attempt generation or progress history is invalid")
        previous = None
        for index, attempt in enumerate(attempts, start=1):
            if any(
                isinstance(attempt[field], bool) or not isinstance(attempt[field], int)
                for field in ("generation", "progress_start", "progress_end")
            ):
                raise SyntheticTaskError("LEDGER_CORRUPT", "v2 attempt counters are not integers")
            try:
                expected_argv = json.loads(attempt["expected_argv_json"])
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise SyntheticTaskError("LEDGER_CORRUPT", "v2 worker argv identity is invalid") from exc
            if (
                not isinstance(expected_argv, list)
                or any(not isinstance(value, str) for value in expected_argv)
                or attempt["generation"] != index
                or (attempt["predecessor_attempt_id"] != (None if previous is None else previous["attempt_id"]))
                or attempt["source_contract_sha256"] != row["source_contract_sha256"]
                or attempt["runtime_identity_sha256"] != row["runtime_identity_sha256"]
                or not 0 <= attempt["progress_start"] <= attempt["progress_end"] <= request["steps"]
                or expected_argv != _expected_worker_argv(self.root, row["run_id"], attempt["attempt_id"])
            ):
                raise SyntheticTaskError("LEDGER_CORRUPT", "v2 attempt lineage or frozen identity is inconsistent")
            if previous is not None and previous["progress_end"] != attempt["progress_start"]:
                raise SyntheticTaskError("LEDGER_CORRUPT", "v2 attempt progress lineage is discontinuous")
            if index < len(attempts) and attempt["state"] != "SUPERSEDED":
                raise SyntheticTaskError("LEDGER_CORRUPT", "non-current v2 attempt was not fenced")
            previous = attempt
        current = attempts[-1]
        if (
            current["attempt_id"] != row["current_attempt_id"]
            or current["generation"] != row["attempt_generation"]
            or current["progress_end"] != row["progress_completed"]
            or current["state"] != row["state"]
        ):
            raise SyntheticTaskError("LEDGER_CORRUPT", "v2 current task state does not match its attempt")
        return attempts

    def _snapshot_v2(
        self, conn: sqlite3.Connection, row: sqlite3.Row, *, inspect_process: bool,
    ) -> TaskSnapshot:
        request = self._request_v2(row)
        attempts = self._attempts_v2(conn, row, request)
        current = attempts[-1]
        state = row["state"]
        error_code = row["error_code"]
        error_message = row["error_message"]
        if state == "CREATED":
            state = "RECOVERY_REQUIRED"
        elif state == "STARTING":
            state = "LAUNCH_AMBIGUOUS"
        if inspect_process and row["state"] in ("STARTING", "RUNNING", "STOP_REQUESTED"):
            try:
                source_sha, runtime_sha = _source_and_runtime_identity()
            except SyntheticTaskError as exc:
                state = "SOURCE_IDENTITY_UNKNOWN"
                error_code, error_message = exc.code, exc.message
            else:
                if source_sha != row["source_contract_sha256"] or runtime_sha != row["runtime_identity_sha256"]:
                    state = "SOURCE_IDENTITY_MISMATCH"
                    error_code = "SOURCE_IDENTITY_MISMATCH"
                    error_message = "synthetic worker source/runtime identity changed"
                elif row["state"] in ("RUNNING", "STOP_REQUESTED"):
                    if (
                        current["owner_pid"] != row["owner_pid"]
                        or current["owner_start_ticks"] != row["owner_start_ticks"]
                        or current["owner_boot_id"] != row["owner_boot_id"]
                        or row["owner_pid"] is None or row["owner_start_ticks"] is None or row["owner_boot_id"] is None
                    ):
                        state = "PROCESS_IDENTITY_UNKNOWN"
                    else:
                        process_state = _process_state(row, json.loads(current["expected_argv_json"]))
                        if process_state == "DEAD":
                            state = "RECOVERY_REQUIRED"
                        elif process_state == "UNKNOWN":
                            state = "PROCESS_IDENTITY_UNKNOWN"
        return TaskSnapshot(
            run_id=row["run_id"],
            attempt_id=row["current_attempt_id"],
            request_sha256=row["request_sha256"],
            idempotency_key=row["idempotency_key"],
            authorization_test_only=bool(row["authorization_test_only"]),
            state=state,
            ledger_state=row["state"],
            progress_completed=row["progress_completed"],
            progress_total=request["steps"],
            interval_ms=request["interval_ms"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            last_progress_at=row["last_progress_at"],
            stop_requested_at=row["stop_requested_at"],
            owner_pid=row["owner_pid"],
            owner_start_ticks=row["owner_start_ticks"],
            owner_boot_id=row["owner_boot_id"],
            error_code=error_code,
            error_message=error_message,
            attempt_generation=row["attempt_generation"],
            predecessor_attempt_id=current["predecessor_attempt_id"],
        )

    def create_task(self, idempotency_key: str, *, steps: int, interval_ms: int) -> tuple[TaskSnapshot, bool]:
        _validate_key(idempotency_key)
        request_json, digest = _canonical_v2_request(steps, interval_ms)
        source_sha, runtime_sha = _source_and_runtime_identity()
        with self._connection(writable=True, create=True, schema_version=2) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT * FROM tasks WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if existing is not None:
                if existing["request_sha256"] != digest:
                    conn.rollback()
                    raise SyntheticTaskError(
                        "IDEMPOTENCY_CONFLICT", "idempotency key already names a different immutable request",
                    )
                if existing["source_contract_sha256"] != source_sha or existing["runtime_identity_sha256"] != runtime_sha:
                    conn.rollback()
                    raise SyntheticTaskError("SOURCE_IDENTITY_MISMATCH", "task implementation/runtime identity changed")
                row = self._fetch_v2(conn, existing["run_id"])
                snapshot = self._snapshot_v2(conn, row, inspect_process=True)
                conn.commit()
                return snapshot, False

            run_id, attempt_id = uuid.uuid4().hex, uuid.uuid4().hex
            now = _utc_now()
            expected_argv = _expected_worker_argv(self.root, run_id, attempt_id)
            conn.execute(
                """INSERT INTO tasks (
                    run_id,task_kind,request_json,request_sha256,idempotency_key,authorization_test_only,
                    current_attempt_id,attempt_generation,state,progress_completed,source_contract_sha256,
                    runtime_identity_sha256,created_at,updated_at
                ) VALUES (?,?,?,?,?,1,?,1,'CREATED',0,?,?,?,?)""",
                (run_id, V2_REQUEST_KIND, request_json, digest, idempotency_key, attempt_id,
                 source_sha, runtime_sha, now, now),
            )
            conn.execute(
                """INSERT INTO attempts (
                    attempt_id,run_id,generation,predecessor_attempt_id,state,progress_start,progress_end,
                    source_contract_sha256,runtime_identity_sha256,expected_argv_json,created_at
                ) VALUES (?,?,1,NULL,'CREATED',0,0,?,?,?,?)""",
                (attempt_id, run_id, source_sha, runtime_sha,
                 json.dumps(expected_argv, separators=(",", ":")), now),
            )
            row = self._fetch_v2(conn, run_id)
            snapshot = self._snapshot_v2(conn, row, inspect_process=False)
            conn.commit()
            return snapshot, True

    def begin_launch(self, run_id: str, attempt_id: str) -> None:
        self._transition_starting(run_id, attempt_id)

    def _transition_starting(self, run_id: str, attempt_id: str) -> None:
        _validate_run_id(run_id)
        _validate_attempt_id(attempt_id)
        with self._connection(writable=True, schema_version=2) as conn:
            conn.execute("BEGIN IMMEDIATE")
            now = _utc_now()
            task = conn.execute(
                "UPDATE tasks SET state='STARTING',updated_at=? WHERE run_id=? AND current_attempt_id=? AND state='CREATED'",
                (now, run_id, attempt_id),
            )
            attempt = conn.execute(
                "UPDATE attempts SET state='STARTING' WHERE run_id=? AND attempt_id=? AND state='CREATED'",
                (run_id, attempt_id),
            )
            if task.rowcount != 1 or attempt.rowcount != 1:
                conn.rollback()
                raise SyntheticTaskError("RECOVERY_REQUIRED", "task cannot start from its persisted state")
            conn.commit()

    def mark_launch_ambiguous(self, run_id: str, attempt_id: str, message: str) -> None:
        _validate_run_id(run_id)
        _validate_attempt_id(attempt_id)
        bounded = str(message).encode("utf-8", "replace")[:MAX_ERROR_BYTES].decode("utf-8", "ignore")
        with self._connection(writable=True, schema_version=2) as conn:
            conn.execute("BEGIN IMMEDIATE")
            now = _utc_now()
            attempt = conn.execute(
                """UPDATE attempts SET state='LAUNCH_AMBIGUOUS',finished_at=?
                   WHERE run_id=? AND attempt_id=? AND state='STARTING' AND owner_pid IS NULL""",
                (now, run_id, attempt_id),
            )
            task = conn.execute(
                """UPDATE tasks SET state='LAUNCH_AMBIGUOUS',updated_at=?,finished_at=?,
                   error_code='LAUNCH_AMBIGUOUS',error_message=?
                   WHERE run_id=? AND current_attempt_id=? AND state='STARTING' AND owner_pid IS NULL""",
                (now, now, bounded, run_id, attempt_id),
            )
            if attempt.rowcount != task.rowcount:
                conn.rollback()
                raise SyntheticTaskError("RECOVERY_AMBIGUOUS", "launch ambiguity could not be recorded atomically")
            conn.commit()

    def claim_attempt(self, run_id: str, attempt_id: str) -> bool:
        _validate_run_id(run_id)
        _validate_attempt_id(attempt_id)
        identity = current_process_identity()
        source_sha, runtime_sha = _source_and_runtime_identity()
        with self._connection(writable=True, schema_version=2) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            row = self._fetch_v2(conn, run_id)
            request = self._request_v2(row)
            attempts = self._attempts_v2(conn, row, request)
            current = attempts[-1]
            expected_argv = json.loads(current["expected_argv_json"])
            if (
                row["current_attempt_id"] != attempt_id or row["state"] != "STARTING"
                or current["state"] != "STARTING" or current["owner_pid"] is not None
                or row["authorization_test_only"] != 1
            ):
                conn.rollback()
                return False
            if source_sha != row["source_contract_sha256"] or runtime_sha != row["runtime_identity_sha256"]:
                conn.rollback()
                return False
            if not _matches_current_process_argv(expected_argv):
                conn.rollback()
                return False
            now = _utc_now()
            task = conn.execute(
                """UPDATE tasks SET state='RUNNING',owner_pid=?,owner_start_ticks=?,owner_boot_id=?,
                   started_at=COALESCE(started_at,?),updated_at=?,error_code=NULL,error_message=NULL
                   WHERE run_id=? AND current_attempt_id=? AND state='STARTING' AND owner_pid IS NULL""",
                (*identity, now, now, run_id, attempt_id),
            )
            attempt = conn.execute(
                """UPDATE attempts SET state='RUNNING',owner_pid=?,owner_start_ticks=?,owner_boot_id=?,started_at=?
                   WHERE run_id=? AND attempt_id=? AND state='STARTING' AND owner_pid IS NULL""",
                (*identity, now, run_id, attempt_id),
            )
            if task.rowcount != 1 or attempt.rowcount != 1:
                conn.rollback()
                return False
            conn.commit()
            return True

    def record_step(self, run_id: str, attempt_id: str) -> tuple[str, int]:
        _validate_run_id(run_id)
        _validate_attempt_id(attempt_id)
        identity = current_process_identity()
        with self._connection(writable=True, schema_version=2) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            row = self._fetch_v2(conn, run_id)
            request = self._request_v2(row)
            self._attempts_v2(conn, row, request)
            if (
                row["current_attempt_id"] != attempt_id or row["owner_pid"] != identity[0]
                or row["owner_start_ticks"] != identity[1] or row["owner_boot_id"] != identity[2]
            ):
                conn.rollback()
                raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "worker is fenced from this task attempt")
            now = _utc_now()
            if row["state"] == "STOP_REQUESTED":
                task = conn.execute(
                    "UPDATE tasks SET state='STOPPED',finished_at=?,updated_at=? WHERE run_id=? AND current_attempt_id=? AND state='STOP_REQUESTED'",
                    (now, now, run_id, attempt_id),
                )
                attempt = conn.execute(
                    "UPDATE attempts SET state='STOPPED',finished_at=?,progress_end=? WHERE run_id=? AND attempt_id=? AND state='STOP_REQUESTED'",
                    (now, row["progress_completed"], run_id, attempt_id),
                )
                if task.rowcount != 1 or attempt.rowcount != 1:
                    conn.rollback()
                    raise SyntheticTaskError("RECOVERY_AMBIGUOUS", "stop transition did not reconcile atomically")
                conn.commit()
                return "STOPPED", row["progress_completed"]
            if row["state"] != "RUNNING":
                conn.rollback()
                raise SyntheticTaskError("RECOVERY_REQUIRED", "task is not in a worker-progress state")
            progress = row["progress_completed"]
            if progress >= request["steps"]:
                conn.rollback()
                raise SyntheticTaskError("LEDGER_CORRUPT", "task progress exceeds its immutable total")
            progress += 1
            terminal = progress == request["steps"]
            state = "COMPLETED" if terminal else "RUNNING"
            task = conn.execute(
                """UPDATE tasks SET state=?,progress_completed=?,last_progress_at=?,updated_at=?,finished_at=?
                   WHERE run_id=? AND current_attempt_id=? AND state='RUNNING'""",
                (state, progress, now, now, now if terminal else None, run_id, attempt_id),
            )
            attempt = conn.execute(
                "UPDATE attempts SET state=?,progress_end=?,finished_at=? WHERE run_id=? AND attempt_id=? AND state='RUNNING'",
                (state, progress, now if terminal else None, run_id, attempt_id),
            )
            if task.rowcount != 1 or attempt.rowcount != 1:
                conn.rollback()
                raise SyntheticTaskError("RECOVERY_AMBIGUOUS", "progress transaction did not reconcile atomically")
            conn.commit()
            return state, progress

    def fail_attempt(self, run_id: str, attempt_id: str, error_code: str, message: str) -> None:
        _validate_run_id(run_id)
        _validate_attempt_id(attempt_id)
        identity = current_process_identity()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", error_code):
            error_code = "WORKER_FAILED"
        bounded = str(message).encode("utf-8", "replace")[:MAX_ERROR_BYTES].decode("utf-8", "ignore")
        with self._connection(writable=True, schema_version=2) as conn:
            conn.execute("BEGIN IMMEDIATE")
            now = _utc_now()
            task = conn.execute(
                """UPDATE tasks SET state='FAILED',error_code=?,error_message=?,finished_at=?,updated_at=?
                   WHERE run_id=? AND current_attempt_id=? AND owner_pid=? AND owner_start_ticks=? AND owner_boot_id=?
                     AND state IN ('RUNNING','STOP_REQUESTED')""",
                (error_code, bounded, now, now, run_id, attempt_id, *identity),
            )
            attempt = conn.execute(
                """UPDATE attempts SET state='FAILED',finished_at=?,progress_end=?
                   WHERE run_id=? AND attempt_id=? AND owner_pid=? AND owner_start_ticks=? AND owner_boot_id=?
                     AND state IN ('RUNNING','STOP_REQUESTED')""",
                (now, _progress_for_attempt(conn, run_id, attempt_id), run_id, attempt_id, *identity),
            )
            if task.rowcount != 1 or attempt.rowcount != 1:
                conn.rollback()
                raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "worker cannot fail a superseded attempt")
            conn.commit()

    def get_status(self, run_id: str) -> TaskSnapshot:
        with self._connection(writable=False, schema_version=2) as conn:
            conn.row_factory = sqlite3.Row
            row = self._fetch_v2(conn, run_id)
            return self._snapshot_v2(conn, row, inspect_process=True)

    def request_stop(self, run_id: str, attempt_id: str) -> TaskSnapshot:
        _validate_run_id(run_id)
        _validate_attempt_id(attempt_id)
        with self._connection(writable=True, schema_version=2) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            row = self._fetch_v2(conn, run_id)
            request = self._request_v2(row)
            attempts = self._attempts_v2(conn, row, request)
            current = attempts[-1]
            if row["current_attempt_id"] != attempt_id:
                conn.rollback()
                raise SyntheticTaskError("ATTEMPT_MISMATCH", "stop requires the exact current attempt_id")
            if row["state"] != "RUNNING":
                conn.rollback()
                raise SyntheticTaskError("STOP_NOT_ALLOWED", "only a running synthetic task can be stopped")
            process_state = _process_state(row, json.loads(current["expected_argv_json"]))
            if process_state != "LIVE":
                conn.rollback()
                code = "PROCESS_IDENTITY_UNKNOWN" if process_state == "UNKNOWN" else "RECOVERY_REQUIRED"
                raise SyntheticTaskError(code, "refusing stop because the exact worker is not verified live")
            now = _utc_now()
            task = conn.execute(
                """UPDATE tasks SET state='STOP_REQUESTED',stop_requested_at=?,updated_at=?
                   WHERE run_id=? AND current_attempt_id=? AND state='RUNNING'""",
                (now, now, run_id, attempt_id),
            )
            attempt = conn.execute(
                """UPDATE attempts SET state='STOP_REQUESTED' WHERE run_id=? AND attempt_id=? AND state='RUNNING'""",
                (run_id, attempt_id),
            )
            if task.rowcount != 1 or attempt.rowcount != 1:
                conn.rollback()
                raise SyntheticTaskError("STOP_NOT_ALLOWED", "task state changed before stop was committed")
            row = self._fetch_v2(conn, run_id)
            snapshot = self._snapshot_v2(conn, row, inspect_process=True)
            conn.commit()
            return snapshot

    def resume_task(self, run_id: str, expected_attempt_id: str) -> TaskSnapshot:
        """Commit one successor only when all recovery evidence is positive."""
        _validate_run_id(run_id)
        _validate_attempt_id(expected_attempt_id)
        source_sha, runtime_sha = _source_and_runtime_identity()
        with self._connection(writable=True, schema_version=2) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            row = self._fetch_v2(conn, run_id)
            request = self._request_v2(row)
            attempts = self._attempts_v2(conn, row, request)
            current = attempts[-1]
            if row["current_attempt_id"] != expected_attempt_id:
                conn.rollback()
                raise SyntheticTaskError("ATTEMPT_MISMATCH", "resume requires the exact current predecessor attempt_id")
            if row["state"] != "RUNNING" or current["state"] != "RUNNING":
                conn.rollback()
                raise SyntheticTaskError("RECOVERY_UNSUPPORTED", "only a claimed, nonterminal RUNNING attempt is resumable")
            if row["authorization_test_only"] != 1 or row["progress_completed"] >= request["steps"]:
                conn.rollback()
                raise SyntheticTaskError("RECOVERY_AMBIGUOUS", "task authorization or progress bounds are invalid")
            if source_sha != row["source_contract_sha256"] or runtime_sha != row["runtime_identity_sha256"]:
                conn.rollback()
                raise SyntheticTaskError("SOURCE_IDENTITY_MISMATCH", "synthetic worker source/runtime identity changed")
            if (
                current["owner_pid"] != row["owner_pid"]
                or current["owner_start_ticks"] != row["owner_start_ticks"]
                or current["owner_boot_id"] != row["owner_boot_id"]
                or row["owner_pid"] is None
            ):
                conn.rollback()
                raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "claimed process identity is incomplete or inconsistent")
            process_state = _process_state(row, json.loads(current["expected_argv_json"]))
            if process_state == "LIVE":
                conn.rollback()
                raise SyntheticTaskError("WORKER_ACTIVE", "the recorded synthetic worker is still alive")
            if process_state != "DEAD":
                conn.rollback()
                raise SyntheticTaskError("RECOVERY_AMBIGUOUS", "previous worker death cannot be proven")
            # Re-read source identity under the transaction immediately before
            # advancing the fence. The new worker independently verifies it.
            if _source_and_runtime_identity() != (source_sha, runtime_sha):
                conn.rollback()
                raise SyntheticTaskError("SOURCE_IDENTITY_MISMATCH", "synthetic source changed during resume validation")

            now = _utc_now()
            new_attempt_id = uuid.uuid4().hex
            generation = row["attempt_generation"] + 1
            progress = row["progress_completed"]
            expected_argv = _expected_worker_argv(self.root, run_id, new_attempt_id)
            superseded = conn.execute(
                """UPDATE attempts SET state='SUPERSEDED',finished_at=?,progress_end=?
                   WHERE run_id=? AND attempt_id=? AND state='RUNNING'""",
                (now, progress, run_id, expected_attempt_id),
            )
            if superseded.rowcount != 1:
                conn.rollback()
                raise SyntheticTaskError("RECOVERY_AMBIGUOUS", "predecessor attempt could not be fenced")
            conn.execute(
                """INSERT INTO attempts (
                    attempt_id,run_id,generation,predecessor_attempt_id,state,progress_start,progress_end,
                    source_contract_sha256,runtime_identity_sha256,expected_argv_json,created_at
                ) VALUES (?,?,?,?, 'STARTING',?,?,?,?,?,?)""",
                (new_attempt_id, run_id, generation, expected_attempt_id, progress, progress,
                 source_sha, runtime_sha, json.dumps(expected_argv, separators=(",", ":")), now),
            )
            updated = conn.execute(
                """UPDATE tasks SET current_attempt_id=?,attempt_generation=?,state='STARTING',
                   updated_at=?,finished_at=NULL,owner_pid=NULL,owner_start_ticks=NULL,owner_boot_id=NULL,
                   error_code=NULL,error_message=NULL WHERE run_id=? AND current_attempt_id=? AND state='RUNNING'""",
                (new_attempt_id, generation, now, run_id, expected_attempt_id),
            )
            if updated.rowcount != 1:
                conn.rollback()
                raise SyntheticTaskError("ATTEMPT_MISMATCH", "predecessor attempt changed before resume committed")
            row = self._fetch_v2(conn, run_id)
            snapshot = self._snapshot_v2(conn, row, inspect_process=False)
            conn.commit()
            return snapshot


def _progress_for_attempt(conn: sqlite3.Connection, run_id: str, attempt_id: str) -> int:
    row = conn.execute(
        "SELECT progress_completed FROM tasks WHERE run_id=? AND current_attempt_id=?",
        (run_id, attempt_id),
    ).fetchone()
    return -1 if row is None else int(row[0])


def _matches_current_process_argv(expected_argv: list[str]) -> bool:
    try:
        actual = _proc_argv(os.getpid())
        executable = Path(f"/proc/{os.getpid()}/exe").resolve(strict=True)
        expected_executable = Path(sys.executable).resolve(strict=True)
    except (OSError, RuntimeError, SyntheticTaskError):
        return False
    return (
        actual is not None
        and len(actual) >= 2
        and actual[1:] == tuple(os.fsencode(value) for value in expected_argv)
        and executable == expected_executable
    )


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
