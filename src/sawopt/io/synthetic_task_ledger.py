"""Private SQLite WAL ledger for isolated synthetic countdown tasks only."""
from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from urllib.parse import quote


DB_NAME = "synthetic-tasks.sqlite3"
LOG_NAME = "synthetic-tasks.log"
SCHEMA_VERSION = 1
MAX_STEPS = 120
MAX_INTERVAL_MS = 1000
MIN_INTERVAL_MS = 10
MAX_LOG_BYTES = 16 * 1024
MAX_ERROR_BYTES = 512
BUSY_TIMEOUT_MS = 5000
REQUEST_KIND = "synthetic-countdown-v1"
_STATES = (
    "CREATED", "STARTING", "RUNNING", "STOP_REQUESTED", "STOPPED",
    "COMPLETED", "FAILED", "LAUNCH_AMBIGUOUS", "PROCESS_IDENTITY_UNKNOWN",
    "RECOVERY_REQUIRED",
)
_ARTIFACTS = {
    DB_NAME, f"{DB_NAME}-wal", f"{DB_NAME}-shm", f"{DB_NAME}-journal", LOG_NAME,
}
_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_TASKS_SCHEMA = """CREATE TABLE tasks (
    run_id TEXT PRIMARY KEY CHECK(length(run_id)=32),
    request_json TEXT NOT NULL CHECK(length(request_json)<=256),
    request_sha256 TEXT NOT NULL CHECK(length(request_sha256)=64),
    idempotency_key TEXT NOT NULL UNIQUE CHECK(length(idempotency_key) BETWEEN 1 AND 128),
    authorization_test_only INTEGER NOT NULL CHECK(authorization_test_only=1),
    attempt_id TEXT NOT NULL CHECK(length(attempt_id)=32),
    state TEXT NOT NULL CHECK(state IN (
        'CREATED','STARTING','RUNNING','STOP_REQUESTED','STOPPED','COMPLETED','FAILED',
        'LAUNCH_AMBIGUOUS','PROCESS_IDENTITY_UNKNOWN','RECOVERY_REQUIRED'
    )),
    progress_completed INTEGER NOT NULL DEFAULT 0 CHECK(progress_completed>=0 AND progress_completed<=120),
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
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class SyntheticTaskError(Exception):
    """A typed, fail-closed task-ledger or process-identity error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_request(steps: int, interval_ms: int) -> tuple[str, str]:
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= MAX_STEPS:
        raise SyntheticTaskError("REQUEST_INVALID", f"steps must be an integer in [1, {MAX_STEPS}]")
    if (
        isinstance(interval_ms, bool) or not isinstance(interval_ms, int)
        or not MIN_INTERVAL_MS <= interval_ms <= MAX_INTERVAL_MS
    ):
        raise SyntheticTaskError(
            "REQUEST_INVALID", f"interval_ms must be an integer in [{MIN_INTERVAL_MS}, {MAX_INTERVAL_MS}]",
        )
    value = {"kind": REQUEST_KIND, "steps": steps, "interval_ms": interval_ms}
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return encoded, hashlib.sha256(encoded.encode("ascii")).hexdigest()


def _validate_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or _ID_RE.fullmatch(run_id) is None:
        raise SyntheticTaskError("REQUEST_INVALID", "run_id must be a 32-character lowercase UUID hex value")


def _validate_attempt_id(attempt_id: str) -> None:
    if not isinstance(attempt_id, str) or _ID_RE.fullmatch(attempt_id) is None:
        raise SyntheticTaskError("REQUEST_INVALID", "attempt_id must be a 32-character lowercase UUID hex value")


def _validate_key(key: str) -> None:
    if not isinstance(key, str) or _KEY_RE.fullmatch(key) is None:
        raise SyntheticTaskError(
            "REQUEST_INVALID", "idempotency key must be 1-128 safe ASCII letters, digits, '.', '_', ':' or '-'",
        )


def _safe_root(root: str | os.PathLike[str], *, require_ledger: bool) -> Path:
    raw = os.fspath(root)
    if not raw or not os.path.isabs(raw):
        raise SyntheticTaskError("TASK_ROOT_REQUIRED", "--root must be an explicit absolute path")
    path = Path(raw)
    if ".." in path.parts:
        raise SyntheticTaskError("TASK_ROOT_UNSAFE", "task root must not contain path traversal")
    candidate = Path(os.path.abspath(raw))
    repository_root = Path(__file__).resolve().parents[3]
    try:
        if os.path.commonpath((str(candidate), str(repository_root))) == str(repository_root):
            raise SyntheticTaskError("TASK_ROOT_UNSAFE", "synthetic task roots may not be inside a repository")
    except ValueError:
        pass
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError as exc:
            raise SyntheticTaskError("TASK_ROOT_UNSAFE", "task root and its parents must already exist") from exc
        if stat.S_ISLNK(info.st_mode):
            raise SyntheticTaskError("TASK_ROOT_UNSAFE", "symlinked task-root path components are forbidden")
    info = os.lstat(path)
    if not stat.S_ISDIR(info.st_mode):
        raise SyntheticTaskError("TASK_ROOT_UNSAFE", "task root must be an existing directory")
    if not hasattr(os, "getuid") or info.st_uid != os.getuid():
        raise SyntheticTaskError("TASK_ROOT_UNSAFE", "task root must be owned by the current user")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise SyntheticTaskError("TASK_ROOT_UNSAFE", "task root permissions must exclude group and other users")
    try:
        resolved_candidate = path.resolve(strict=True)
        if resolved_candidate != candidate:
            raise SyntheticTaskError("TASK_ROOT_UNSAFE", "task-root canonical path changed during validation")
    except (OSError, RuntimeError) as exc:
        raise SyntheticTaskError("TASK_ROOT_UNSAFE", "cannot resolve explicit task root safely") from exc

    configured_raw_root = os.environ.get("SAWOPT_DATA_ROOT")
    if configured_raw_root:
        if not os.path.isabs(configured_raw_root):
            raise SyntheticTaskError("TASK_ROOT_UNSAFE", "configured SAWOPT_DATA_ROOT must be absolute")
        try:
            configured_root = Path(configured_raw_root).resolve(strict=True)
            if not configured_root.is_dir():
                raise SyntheticTaskError("TASK_ROOT_UNSAFE", "configured SAWOPT_DATA_ROOT is not a directory")
        except SyntheticTaskError:
            raise
        except (OSError, RuntimeError) as exc:
            raise SyntheticTaskError(
                "TASK_ROOT_UNSAFE", "configured SAWOPT_DATA_ROOT cannot be resolved safely",
            ) from exc
        try:
            if os.path.commonpath((str(resolved_candidate), str(configured_root))) == str(configured_root):
                raise SyntheticTaskError(
                    "TASK_ROOT_UNSAFE", "synthetic task roots may not use SAWOPT_DATA_ROOT or its descendants",
                )
        except ValueError:
            pass

    try:
        entries = {entry.name for entry in os.scandir(path)}
    except OSError as exc:
        raise SyntheticTaskError("TASK_ROOT_UNSAFE", "cannot inspect the explicit task root") from exc
    unexpected = entries - _ARTIFACTS
    if unexpected:
        raise SyntheticTaskError(
            "TASK_ROOT_UNSAFE", "task root contains non-ledger data; use an empty synthetic-only directory",
        )
    db_path = path / DB_NAME
    if require_ledger and DB_NAME not in entries:
        raise SyntheticTaskError("LEDGER_NOT_FOUND", "no synthetic task ledger exists in this root")
    for name in entries:
        artifact = path / name
        try:
            artifact_info = os.lstat(artifact)
        except FileNotFoundError:
            # SQLite may unlink/recreate WAL/SHM sidecars while another
            # cooperating process opens or closes a connection.
            if name in {f"{DB_NAME}-wal", f"{DB_NAME}-shm", f"{DB_NAME}-journal"}:
                continue
            raise SyntheticTaskError("TASK_ROOT_UNSAFE", "cannot inspect a ledger artifact")
        except OSError as exc:
            raise SyntheticTaskError("TASK_ROOT_UNSAFE", "cannot inspect a ledger artifact") from exc
        if not stat.S_ISREG(artifact_info.st_mode) or artifact_info.st_uid != os.getuid():
            raise SyntheticTaskError("TASK_ROOT_UNSAFE", "ledger artifacts must be regular files owned by this user")
        if stat.S_IMODE(artifact_info.st_mode) & 0o077:
            raise SyntheticTaskError("TASK_ROOT_UNSAFE", "ledger artifact permissions must exclude group and others")
    return path


def _linux_boot_id() -> str:
    if sys.platform != "linux":
        raise SyntheticTaskError("PLATFORM_UNSUPPORTED", "synthetic detached tasks are supported only on Linux/WSL2")
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except OSError as exc:
        raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "Linux boot identity is unavailable") from exc
    if not value or len(value) > 64:
        raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "Linux boot identity is invalid")
    return value


def _read_process_identity(pid: int) -> tuple[str, int, str] | None:
    if sys.platform != "linux" or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return None
    try:
        boot_id = _linux_boot_id()
        text = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except (OSError, SyntheticTaskError):
        return None
    close = text.rfind(")")
    if close < 0:
        return None
    fields = text[close + 1 :].strip().split()
    # fields[0] is proc stat field 3; starttime is field 22.
    if len(fields) <= 19:
        return None
    try:
        start_ticks = int(fields[19])
    except ValueError:
        return None
    if start_ticks < 0:
        return None
    return boot_id, start_ticks, fields[0]


def _is_expected_worker(pid: int, root: str | os.PathLike[str], run_id: str, attempt_id: str) -> bool:
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    expected = [
        b"-m", b"sawopt.synthetic_worker", b"--root", os.fsencode(os.fspath(root)),
        b"--run-id", os.fsencode(run_id), b"--attempt-id", os.fsencode(attempt_id),
    ]
    return any(command[index : index + len(expected)] == expected for index in range(len(command) - len(expected) + 1))


def _acquire_ledger_file_lock(fd: int, *, writable: bool) -> None:
    import fcntl

    operation = fcntl.LOCK_EX if writable else fcntl.LOCK_SH
    deadline = time.monotonic() + BUSY_TIMEOUT_MS / 1000
    while True:
        try:
            fcntl.flock(fd, operation | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN):
                raise SyntheticTaskError("LEDGER_UNAVAILABLE", "cannot acquire task-ledger file lock") from exc
            if time.monotonic() >= deadline:
                raise SyntheticTaskError("LEDGER_LOCKED", "task-ledger file lock timed out") from exc
            time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))


def current_process_identity() -> tuple[int, int, str]:
    identity = _read_process_identity(os.getpid())
    if identity is None:
        raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "cannot establish this worker's Linux process identity")
    boot_id, start_ticks, _state = identity
    return os.getpid(), start_ticks, boot_id


@dataclass(frozen=True)
class TaskSnapshot:
    run_id: str
    attempt_id: str
    request_sha256: str
    idempotency_key: str
    authorization_test_only: bool
    state: str
    ledger_state: str
    progress_completed: int
    progress_total: int
    interval_ms: int
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
    last_progress_at: str | None
    stop_requested_at: str | None
    owner_pid: int | None
    owner_start_ticks: int | None
    owner_boot_id: str | None
    error_code: str | None
    error_message: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "attempt_id": self.attempt_id,
            "request_sha256": self.request_sha256,
            "idempotency_key": self.idempotency_key,
            "authorization_test_only": self.authorization_test_only,
            "state": self.state,
            "ledger_state": self.ledger_state,
            "progress_completed": self.progress_completed,
            "progress_total": self.progress_total,
            "progress_fraction": self.progress_completed / self.progress_total,
            "interval_ms": self.interval_ms,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "last_progress_at": self.last_progress_at,
            "stop_requested_at": self.stop_requested_at,
            "owner_pid": self.owner_pid,
            "owner_start_ticks": self.owner_start_ticks,
            "owner_boot_id": self.owner_boot_id,
            "error": None if self.error_code is None else {
                "code": self.error_code,
                "message": self.error_message,
            },
        }


class SyntheticTaskLedger:
    """One SQLite lifecycle ledger; no scientific/raw-store integration."""

    def __init__(self, root: str | os.PathLike[str]):
        self.root = root

    @contextlib.contextmanager
    def _connection(self, *, writable: bool, create: bool = False) -> Iterator[sqlite3.Connection]:
        path = _safe_root(self.root, require_ledger=not create)
        db_path = path / DB_NAME
        created = False
        flags = os.O_RDWR
        if writable:
            flags |= os.O_CREAT
        else:
            flags = os.O_RDONLY
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        if create and writable:
            try:
                fd = os.open(db_path, flags | os.O_EXCL, 0o600)
                created = True
            except FileExistsError:
                fd = os.open(db_path, flags)
        else:
            try:
                fd = os.open(db_path, flags)
            except FileNotFoundError as exc:
                raise SyntheticTaskError("LEDGER_NOT_FOUND", "no synthetic task ledger exists in this root") from exc
        try:
            file_info = os.fstat(fd)
            path_info = os.lstat(db_path)
            if (
                not stat.S_ISREG(file_info.st_mode) or stat.S_ISLNK(path_info.st_mode)
                or file_info.st_ino != path_info.st_ino or file_info.st_dev != path_info.st_dev
                or file_info.st_uid != os.getuid()
                or stat.S_IMODE(file_info.st_mode) & 0o077
            ):
                raise SyntheticTaskError("TASK_ROOT_UNSAFE", "ledger file identity or permissions are unsafe")
            import fcntl

            _acquire_ledger_file_lock(fd, writable=writable)
        except Exception:
            os.close(fd)
            raise

        conn: sqlite3.Connection | None = None
        old_umask = os.umask(0o077) if writable else None
        try:
            if writable:
                conn = sqlite3.connect(str(db_path), timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
                conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
                mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                if str(mode).lower() != "wal":
                    raise SyntheticTaskError("LEDGER_UNAVAILABLE", "SQLite refused WAL mode")
                conn.execute("PRAGMA synchronous=FULL")
                conn.execute("PRAGMA foreign_keys=ON")
            else:
                uri = db_path.as_uri() + "?mode=ro"
                conn = sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
                conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
                conn.execute("PRAGMA query_only=ON")
                mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                if str(mode).lower() != "wal":
                    raise SyntheticTaskError("LEDGER_SCHEMA_UNKNOWN", "task ledger is not in required WAL mode")

            if created:
                self._initialize(conn)
            self._validate_schema(conn)
            if writable:
                os.chmod(db_path, 0o600)
            integrity = conn.execute("PRAGMA quick_check(1)").fetchone()
            if not integrity or integrity[0] != "ok":
                raise SyntheticTaskError("LEDGER_CORRUPT", "SQLite ledger integrity check failed")
            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = Path(f"{db_path}{suffix}")
                try:
                    sidecar_info = os.lstat(sidecar)
                except FileNotFoundError:
                    continue
                if (
                    not stat.S_ISREG(sidecar_info.st_mode) or sidecar_info.st_uid != os.getuid()
                    or stat.S_IMODE(sidecar_info.st_mode) & 0o077
                ):
                    raise SyntheticTaskError("TASK_ROOT_UNSAFE", "SQLite sidecar identity or permissions are unsafe")
            yield conn
        except SyntheticTaskError:
            raise
        except sqlite3.DatabaseError as exc:
            code = "LEDGER_LOCKED" if "locked" in str(exc).lower() or "busy" in str(exc).lower() else "LEDGER_CORRUPT"
            raise SyntheticTaskError(code, "SQLite task ledger is unavailable or invalid") from exc
        except OSError as exc:
            raise SyntheticTaskError("LEDGER_UNAVAILABLE", "cannot safely access the SQLite task ledger") from exc
        finally:
            if conn is not None:
                conn.close()
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
            if old_umask is not None:
                os.umask(old_umask)

    @staticmethod
    def _initialize(conn: sqlite3.Connection) -> None:
        try:
            conn.execute("BEGIN IMMEDIATE")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
                )
            }
            if version != 0 or tables:
                raise SyntheticTaskError("LEDGER_SCHEMA_UNKNOWN", "new ledger file is not empty")
            conn.execute(_TASKS_SCHEMA)
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            conn.commit()
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise

    @staticmethod
    def _validate_schema(conn: sqlite3.Connection) -> None:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise SyntheticTaskError("LEDGER_SCHEMA_UNKNOWN", f"unsupported SQLite task-ledger schema version {version}")
        objects = {
            (row[0], row[1]) for row in conn.execute(
                "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'",
            )
        }
        if objects != {("table", "tasks")}:
            raise SyntheticTaskError("LEDGER_SCHEMA_UNKNOWN", "SQLite task-ledger object set is unknown")
        schema_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'",
        ).fetchone()
        if schema_row is None or not isinstance(schema_row[0], str):
            raise SyntheticTaskError("LEDGER_SCHEMA_UNKNOWN", "SQLite task-ledger table definition is missing")
        if " ".join(schema_row[0].split()) != " ".join(_TASKS_SCHEMA.split()):
            raise SyntheticTaskError("LEDGER_SCHEMA_UNKNOWN", "SQLite task-ledger constraints do not match schema v1")
        columns = tuple(row[1] for row in conn.execute("PRAGMA table_info(tasks)"))
        expected = (
            "run_id", "request_json", "request_sha256", "idempotency_key", "authorization_test_only",
            "attempt_id", "state", "progress_completed", "created_at", "updated_at", "started_at",
            "finished_at", "last_progress_at", "stop_requested_at", "owner_pid", "owner_start_ticks",
            "owner_boot_id", "error_code", "error_message",
        )
        if columns != expected:
            raise SyntheticTaskError("LEDGER_SCHEMA_UNKNOWN", "SQLite task-ledger columns do not match schema v1")

    @staticmethod
    def _request_from_row(row: sqlite3.Row) -> dict[str, object]:
        try:
            request = json.loads(row["request_json"])
            encoded = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            digest = hashlib.sha256(encoded.encode("ascii")).hexdigest()
            if digest != row["request_sha256"]:
                raise ValueError("request hash mismatch")
            if (
                set(request) != {"kind", "steps", "interval_ms"}
                or request["kind"] != REQUEST_KIND
                or isinstance(request["steps"], bool)
                or not isinstance(request["steps"], int)
                or not 1 <= request["steps"] <= MAX_STEPS
                or isinstance(request["interval_ms"], bool)
                or not isinstance(request["interval_ms"], int)
                or not MIN_INTERVAL_MS <= request["interval_ms"] <= MAX_INTERVAL_MS
                or row["authorization_test_only"] != 1
            ):
                raise ValueError("request fields invalid")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SyntheticTaskError("LEDGER_CORRUPT", "task request or immutable hash is invalid") from exc
        return request

    @staticmethod
    def _fetch(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        _validate_run_id(run_id)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise SyntheticTaskError("TASK_NOT_FOUND", "synthetic task run_id was not found")
        return row

    @staticmethod
    def _owner_matches(row: sqlite3.Row, identity: tuple[int, int, str]) -> bool:
        pid, start_ticks, boot_id = identity
        return (
            row["owner_pid"] == pid
            and row["owner_start_ticks"] == start_ticks
            and row["owner_boot_id"] == boot_id
        )

    def _snapshot(self, row: sqlite3.Row, *, inspect_process: bool) -> TaskSnapshot:
        request = self._request_from_row(row)
        ledger_state = row["state"]
        state = ledger_state
        if ledger_state == "CREATED":
            state = "RECOVERY_REQUIRED"
        elif ledger_state == "STARTING":
            state = "LAUNCH_AMBIGUOUS"
        elif ledger_state in ("RUNNING", "STOP_REQUESTED") and inspect_process:
            if row["owner_pid"] is None:
                state = "PROCESS_IDENTITY_UNKNOWN"
            else:
                observed = _read_process_identity(row["owner_pid"])
                if observed is None:
                    state = "RECOVERY_REQUIRED"
                elif observed[0] != row["owner_boot_id"] or observed[1] != row["owner_start_ticks"]:
                    state = "PROCESS_IDENTITY_UNKNOWN"
                elif observed[2] == "Z":
                    state = "RECOVERY_REQUIRED"
                elif not _is_expected_worker(
                    row["owner_pid"], self.root, row["run_id"], row["attempt_id"],
                ):
                    state = "PROCESS_IDENTITY_UNKNOWN"
        elif ledger_state in ("RUNNING", "STOP_REQUESTED") and not inspect_process and row["owner_pid"] is None:
            state = "PROCESS_IDENTITY_UNKNOWN"
        return TaskSnapshot(
            run_id=row["run_id"],
            attempt_id=row["attempt_id"],
            request_sha256=row["request_sha256"],
            idempotency_key=row["idempotency_key"],
            authorization_test_only=bool(row["authorization_test_only"]),
            state=state,
            ledger_state=ledger_state,
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
            error_code=row["error_code"],
            error_message=row["error_message"],
        )

    def create_task(self, idempotency_key: str, *, steps: int, interval_ms: int) -> tuple[TaskSnapshot, bool]:
        _validate_key(idempotency_key)
        request_json, digest = _canonical_request(steps, interval_ms)
        with self._connection(writable=True, create=True) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            now = _utc_now()
            existing = conn.execute(
                "SELECT * FROM tasks WHERE idempotency_key=?", (idempotency_key,),
            ).fetchone()
            if existing is not None:
                if existing["request_sha256"] != digest:
                    conn.rollback()
                    raise SyntheticTaskError(
                        "IDEMPOTENCY_CONFLICT", "idempotency key already names a different immutable request",
                    )
                conn.commit()
                return self._snapshot(existing, inspect_process=True), False
            run_id, attempt_id = uuid.uuid4().hex, uuid.uuid4().hex
            conn.execute(
                """INSERT INTO tasks (
                    run_id,request_json,request_sha256,idempotency_key,authorization_test_only,attempt_id,
                    state,progress_completed,created_at,updated_at
                ) VALUES (?,?,?,?,1,?,'CREATED',0,?,?)""",
                (run_id, request_json, digest, idempotency_key, attempt_id, now, now),
            )
            row = self._fetch(conn, run_id)
            conn.commit()
            return self._snapshot(row, inspect_process=False), True

    def begin_launch(self, run_id: str, attempt_id: str) -> None:
        _validate_run_id(run_id)
        _validate_attempt_id(attempt_id)
        with self._connection(writable=True) as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "UPDATE tasks SET state='STARTING',updated_at=? WHERE run_id=? AND attempt_id=? AND state='CREATED'",
                (_utc_now(), run_id, attempt_id),
            )
            if cur.rowcount != 1:
                conn.rollback()
                raise SyntheticTaskError("RECOVERY_REQUIRED", "task cannot be launched from its persisted state")
            conn.commit()

    def mark_launch_ambiguous(self, run_id: str, attempt_id: str, message: str) -> None:
        _validate_run_id(run_id)
        _validate_attempt_id(attempt_id)
        bounded = str(message).encode("utf-8", "replace")[:MAX_ERROR_BYTES].decode("utf-8", "ignore")
        with self._connection(writable=True) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """UPDATE tasks SET state='LAUNCH_AMBIGUOUS',updated_at=?,error_code='LAUNCH_AMBIGUOUS',
                   error_message=? WHERE run_id=? AND attempt_id=? AND state='STARTING' AND owner_pid IS NULL""",
                (_utc_now(), bounded, run_id, attempt_id),
            )
            conn.commit()

    def claim_attempt(self, run_id: str, attempt_id: str) -> bool:
        _validate_run_id(run_id)
        _validate_attempt_id(attempt_id)
        identity = current_process_identity()
        with self._connection(writable=True) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            row = self._fetch(conn, run_id)
            self._request_from_row(row)
            if (
                row["attempt_id"] != attempt_id or row["authorization_test_only"] != 1
                or row["state"] not in ("STARTING", "LAUNCH_AMBIGUOUS") or row["owner_pid"] is not None
            ):
                conn.rollback()
                return False
            now = _utc_now()
            cur = conn.execute(
                """UPDATE tasks SET state='RUNNING',owner_pid=?,owner_start_ticks=?,owner_boot_id=?,
                   started_at=?,updated_at=?,error_code=NULL,error_message=NULL
                   WHERE run_id=? AND attempt_id=? AND state IN ('STARTING','LAUNCH_AMBIGUOUS')
                     AND owner_pid IS NULL AND authorization_test_only=1""",
                (*identity, now, now, run_id, attempt_id),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return False
            conn.commit()
            return True

    def record_step(self, run_id: str, attempt_id: str) -> tuple[str, int]:
        _validate_run_id(run_id)
        _validate_attempt_id(attempt_id)
        identity = current_process_identity()
        with self._connection(writable=True) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            row = self._fetch(conn, run_id)
            self._request_from_row(row)
            if row["attempt_id"] != attempt_id or not self._owner_matches(row, identity):
                conn.rollback()
                raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "worker does not own this exact task attempt")
            now = _utc_now()
            if row["state"] == "STOP_REQUESTED":
                conn.execute(
                    "UPDATE tasks SET state='STOPPED',finished_at=?,updated_at=? WHERE run_id=? AND state='STOP_REQUESTED'",
                    (now, now, run_id),
                )
                conn.commit()
                return "STOPPED", row["progress_completed"]
            if row["state"] != "RUNNING":
                conn.rollback()
                raise SyntheticTaskError("RECOVERY_REQUIRED", "task is not in a worker-progress state")
            request = json.loads(row["request_json"])
            progress = row["progress_completed"]
            if progress >= request["steps"]:
                conn.rollback()
                raise SyntheticTaskError("LEDGER_CORRUPT", "task progress exceeds the permitted transition")
            progress += 1
            terminal = progress == request["steps"]
            state = "COMPLETED" if terminal else "RUNNING"
            conn.execute(
                """UPDATE tasks SET state=?,progress_completed=?,last_progress_at=?,updated_at=?,
                   finished_at=? WHERE run_id=? AND attempt_id=? AND state='RUNNING'""",
                (state, progress, now, now, now if terminal else None, run_id, attempt_id),
            )
            conn.commit()
            return state, progress

    def fail_attempt(self, run_id: str, attempt_id: str, error_code: str, message: str) -> None:
        _validate_run_id(run_id)
        _validate_attempt_id(attempt_id)
        identity = current_process_identity()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", error_code):
            error_code = "WORKER_FAILED"
        bounded = str(message).encode("utf-8", "replace")[:MAX_ERROR_BYTES].decode("utf-8", "ignore")
        with self._connection(writable=True) as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                """UPDATE tasks SET state='FAILED',error_code=?,error_message=?,finished_at=?,updated_at=?
                   WHERE run_id=? AND attempt_id=? AND owner_pid=? AND owner_start_ticks=? AND owner_boot_id=?
                     AND state IN ('RUNNING','STOP_REQUESTED')""",
                (error_code, bounded, _utc_now(), _utc_now(), run_id, attempt_id, *identity),
            )
            conn.commit()
            if cur.rowcount != 1:
                raise SyntheticTaskError("PROCESS_IDENTITY_UNKNOWN", "worker could not fail only its claimed attempt")

    def get_status(self, run_id: str) -> TaskSnapshot:
        _validate_run_id(run_id)
        with self._connection(writable=False) as conn:
            conn.row_factory = sqlite3.Row
            row = self._fetch(conn, run_id)
            return self._snapshot(row, inspect_process=True)

    def request_stop(self, run_id: str, attempt_id: str) -> TaskSnapshot:
        _validate_run_id(run_id)
        _validate_attempt_id(attempt_id)
        with self._connection(writable=True) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            row = self._fetch(conn, run_id)
            if row["attempt_id"] != attempt_id:
                conn.rollback()
                raise SyntheticTaskError("ATTEMPT_MISMATCH", "stop requires the exact current attempt_id")
            if row["state"] != "RUNNING":
                conn.rollback()
                raise SyntheticTaskError("STOP_NOT_ALLOWED", "only a verified running synthetic task can be stopped")
            observed = _read_process_identity(row["owner_pid"])
            if (
                observed is None or observed[0] != row["owner_boot_id"]
                or observed[1] != row["owner_start_ticks"] or observed[2] == "Z"
                or not _is_expected_worker(row["owner_pid"], self.root, run_id, attempt_id)
            ):
                conn.rollback()
                raise SyntheticTaskError(
                    "PROCESS_IDENTITY_UNKNOWN", "refusing stop because the recorded worker identity is not verified",
                )
            now = _utc_now()
            cur = conn.execute(
                """UPDATE tasks SET state='STOP_REQUESTED',stop_requested_at=?,updated_at=?
                   WHERE run_id=? AND attempt_id=? AND state='RUNNING' AND owner_pid=?
                     AND owner_start_ticks=? AND owner_boot_id=?""",
                (now, now, run_id, attempt_id, row["owner_pid"], row["owner_start_ticks"], row["owner_boot_id"]),
            )
            if cur.rowcount != 1:
                conn.rollback()
                raise SyntheticTaskError("STOP_NOT_ALLOWED", "task state changed before stop could be committed")
            row = self._fetch(conn, run_id)
            conn.commit()
            return self._snapshot(row, inspect_process=True)

    def append_log(self, message: str) -> bool:
        """Best-effort bounded diagnostics; contention never blocks task progress."""
        try:
            path = _safe_root(self.root, require_ledger=True)
        except SyntheticTaskError:
            return False
        log_path = path / LOG_NAME
        message_bytes = (str(message).replace("\n", " ").replace("\r", " ")[:400] + "\n").encode("utf-8", "replace")
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(log_path, flags, 0o600)
        except OSError:
            return False
        import fcntl

        locked = False
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                return False
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                return False
            size = os.fstat(fd).st_size
            remaining = MAX_LOG_BYTES - size
            if remaining <= 0:
                return True
            os.write(fd, message_bytes[:remaining])
            return True
        except OSError:
            return False
        finally:
            if locked:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            try:
                os.close(fd)
            except OSError:
                pass
