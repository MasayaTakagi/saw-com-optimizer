"""Filesystem-backed run manifests, status transitions, and session capture."""
from __future__ import annotations

import json
import os
import secrets
import socket
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .models import RUN_STATES, RunManifest, RunStatus
from .pid_utils import pid_exists as _pid_exists


TRANSITIONS = {
    "CREATED": {"STARTING", "FAILED"},
    "STARTING": {"RUNNING", "FAILED", "ORPHANED", "ORPHANED_CHILD"},
    "RUNNING": {"COMPLETED", "REVIEW_WAITING", "FAILED", "ORPHANED", "ORPHANED_CHILD"},
    "COMPLETED": {"CALLBACK_PENDING", "REVIEW_WAITING"},
    "FAILED": {"CALLBACK_PENDING", "STARTING"},
    "CALLBACK_PENDING": {"CALLBACK_RUNNING"},
    "CALLBACK_RUNNING": {"REVIEWED", "CALLBACK_FAILED"},
    "CALLBACK_FAILED": {"CALLBACK_PENDING"},
    "REVIEW_WAITING": {"CALLBACK_PENDING", "REVIEWED"},
    "REVIEWED": set(),
    "ORPHANED": {"STARTING"},
    "ORPHANED_CHILD": {"STARTING"},
}

LOCK_STALE_AFTER_S = 300.0


class SessionValidationError(ValueError):
    """Raised when an automatically captured Codex session is unsafe to use."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    """Write JSON with flush/fsync/replace so readers never see partial JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _read_lock_metadata(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def read_lock_metadata(path: Path) -> dict[str, Any] | None:
    """Read owner metadata for a durable orchestration lock."""
    return _read_lock_metadata(Path(path))


def lock_owner_pid(path: Path) -> int | None:
    """Return a lock owner's PID, including legacy text-PID locks."""
    metadata = _read_lock_metadata(Path(path))
    if metadata is not None:
        try:
            return int(metadata.get("pid"))
        except (TypeError, ValueError):
            return None
    try:
        return int(Path(path).read_text(encoding="ascii").strip())
    except (OSError, TypeError, ValueError):
        return None


def _lock_age_s(path: Path, metadata: dict[str, Any] | None) -> float:
    created_at = metadata.get("created_at") if metadata else None
    if created_at:
        try:
            created = datetime.fromisoformat(str(created_at))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - created).total_seconds())
        except ValueError:
            pass
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return 0.0


def _reclaim_stale_lock(path: Path, *, stale_after_s: float) -> bool:
    """Atomically quarantine a dead, old lock without deleting a new owner."""
    metadata = _read_lock_metadata(path)
    owner_pid = lock_owner_pid(path)
    if _lock_age_s(path, metadata) < stale_after_s or _pid_exists(owner_pid):
        return False
    quarantine = path.with_name(
        f".{path.name}.stale.{os.getpid()}.{time.monotonic_ns()}"
    )
    try:
        os.replace(path, quarantine)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    else:
        quarantine.unlink(missing_ok=True)
        return True


def reclaim_stale_lock(path: Path, *, stale_after_s: float = LOCK_STALE_AFTER_S) -> bool:
    """Atomically remove a dead, sufficiently old lock if still present."""
    return _reclaim_stale_lock(Path(path), stale_after_s=stale_after_s)


@contextmanager
def exclusive_lock(path: Path, timeout_s: float = 10.0,
                   stale_after_s: float = LOCK_STALE_AFTER_S):
    """Cross-platform lock with owner metadata and stale-lock recovery."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_s
    fd = None
    while time.monotonic() < deadline:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            metadata = {
                "pid": os.getpid(),
                "created_at": utc_now(),
                "hostname": socket.gethostname(),
            }
            os.write(fd, json.dumps(metadata, ensure_ascii=True).encode("utf-8"))
            os.fsync(fd)
            break
        except FileExistsError:
            if not _reclaim_stale_lock(path, stale_after_s=stale_after_s):
                time.sleep(0.01)
        except BaseException:
            if fd is not None:
                os.close(fd)
                path.unlink(missing_ok=True)
                fd = None
            raise
    if fd is None:
        raise TimeoutError(f"timed out acquiring lock: {path}")
    try:
        yield
    finally:
        os.close(fd)
        path.unlink(missing_ok=True)


_exclusive_lock = exclusive_lock


def manifest_path(run_dir: Path) -> Path:
    return Path(run_dir) / "run_manifest.json"


def status_path(run_dir: Path) -> Path:
    return Path(run_dir) / "status.json"


def callback_lock_path(run_dir: Path) -> Path:
    return Path(run_dir) / "callback.lock"


def continuation_lock_path(run_dir: Path) -> Path:
    return Path(run_dir) / ".continuation.lock"


def continuation_delivery_path(run_dir: Path) -> Path:
    return Path(run_dir) / "continuation_delivery.json"


def optimizer_completion_path(run_dir: Path) -> Path:
    return Path(run_dir) / "optimizer_completion.json"


def load_manifest(run_dir: Path) -> RunManifest:
    path = manifest_path(Path(run_dir))
    return RunManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_status(run_dir: Path) -> dict[str, Any]:
    path = status_path(Path(run_dir))
    value = json.loads(path.read_text(encoding="utf-8"))
    RunStatus.from_dict(value)
    return value


def create_run(manifest: RunManifest) -> None:
    """Create a new run directory without overwriting an existing run."""
    run_dir = Path(manifest.run_dir)
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"run directory is not empty: {run_dir}")
    optimizer_run_dir = Path(manifest.effective_optimizer_run_dir)
    if optimizer_run_dir.exists() and any(optimizer_run_dir.iterdir()):
        raise FileExistsError(
            f"optimizer output directory is not empty: {optimizer_run_dir}"
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(manifest_path(run_dir), manifest.to_dict())
    atomic_write_json(status_path(run_dir), RunStatus(
        state="CREATED",
        updated_at=manifest.created_at,
        callback_enabled=manifest.callback_enabled,
        continuation_mode=manifest.continuation_mode or "disabled",
        continuation_state=(
            "PENDING" if manifest.continuation_mode == "queue" else
            "DISABLED" if manifest.continuation_mode == "disabled" else "PENDING"
        ),
    ).to_dict())


def _mutate_status(run_dir: Path, mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    run_dir = Path(run_dir)
    with exclusive_lock(run_dir / ".status.lock"):
        value = load_status(run_dir)
        mutator(value)
        value["updated_at"] = utc_now()
        RunStatus.from_dict(value)
        atomic_write_json(
            status_path(run_dir),
            {key: item for key, item in value.items() if not key.startswith("_")},
        )
        return value


def update_status_fields(run_dir: Path, **updates: Any) -> dict[str, Any]:
    """Update non-state fields while retaining the state-machine authority."""
    return _mutate_status(Path(run_dir), lambda value: value.update(updates))


def transition(run_dir: Path, new_state: str, **updates: Any) -> dict[str, Any]:
    """Apply one validated state transition and persist it atomically."""
    if new_state not in RUN_STATES:
        raise ValueError(f"unknown run state: {new_state}")

    def mutate(value: dict[str, Any]) -> None:
        old_state = value["state"]
        if old_state != new_state and new_state not in TRANSITIONS[old_state]:
            raise ValueError(f"invalid run state transition: {old_state} -> {new_state}")
        value.update(updates)
        value["state"] = new_state
        now = utc_now()
        if new_state == "RUNNING" and value.get("started_at") is None:
            value["started_at"] = now
        if new_state in {"COMPLETED", "FAILED", "ORPHANED", "ORPHANED_CHILD", "REVIEW_WAITING"}:
            value["finished_at"] = value.get("finished_at") or now
            if new_state in {"COMPLETED", "FAILED", "REVIEW_WAITING"}:
                value["optimizer_state"] = new_state
        if new_state == "CALLBACK_RUNNING" and value.get("callback_started_at") is None:
            value["callback_started_at"] = now
        if new_state in {"REVIEWED", "CALLBACK_FAILED"}:
            value["callback_finished_at"] = now

    return _mutate_status(Path(run_dir), mutate)


def prepare_callback(run_dir: Path, *, automatic: bool) -> bool:
    """Claim one callback attempt; return False for an already handled run."""
    run_dir = Path(run_dir)
    current = load_status(run_dir)
    current_state = current["state"]
    if current.get("callback_completed") or current_state == "REVIEWED":
        return False
    if automatic and int(current.get("callback_attempts", 0)) >= 1:
        return False
    if current_state in {"COMPLETED", "FAILED", "REVIEW_WAITING", "CALLBACK_FAILED"}:
        transition(run_dir, "CALLBACK_PENDING")

    def mutate(value: dict[str, Any]) -> None:
        state = value["state"]
        if value.get("callback_completed") or state == "REVIEWED":
            value["_skip_callback"] = True
            return
        if automatic and int(value.get("callback_attempts", 0)) >= 1:
            value["_skip_callback"] = True
            return
        if state != "CALLBACK_PENDING":
            raise ValueError(f"callback cannot start from {state}")
        if "CALLBACK_RUNNING" not in TRANSITIONS[state]:
            raise ValueError(f"callback cannot start from {state}")
        value["callback_attempts"] = int(value.get("callback_attempts", 0)) + 1
        value["state"] = "CALLBACK_RUNNING"
        value["callback_started_at"] = utc_now()
        value["callback_exit_code"] = None
        value["error"] = None
        value.pop("_skip_callback", None)

    value = _mutate_status(run_dir, mutate)
    return not value.pop("_skip_callback", False)


def finish_callback(run_dir: Path, *, success: bool, exit_code: int | None,
                    error: str | None = None) -> dict[str, Any]:
    """Record callback completion without changing optimizer success/failure."""
    return transition(
        Path(run_dir),
        "REVIEWED" if success else "CALLBACK_FAILED",
        callback_completed=bool(success),
        callback_exit_code=exit_code,
        error=error,
    )


def record_optimizer_completion(
    run_dir: Path,
    *,
    disposition: str,
    exit_code: int | None,
    error: str | None = None,
) -> dict[str, Any]:
    """Persist a durable orchestration completion marker before notification."""
    run_dir = Path(run_dir).resolve()
    manifest = load_manifest(run_dir)
    if disposition not in {"COMPLETED", "FAILED", "REVIEW_WAITING"}:
        raise ValueError(f"invalid optimizer completion disposition: {disposition}")
    result = {
        "schema_version": 1,
        "run_id": manifest.run_id,
        "disposition": disposition,
        "exit_code": exit_code,
        "error": error,
        "result_reference": str(run_dir),
        "optimizer_run_dir": manifest.effective_optimizer_run_dir,
        "completed_at": utc_now(),
    }
    atomic_write_json(optimizer_completion_path(run_dir), result)
    return result


def _read_delivery(run_dir: Path) -> dict[str, Any] | None:
    path = continuation_delivery_path(Path(run_dir))
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("invalid continuation delivery ledger")
    if value.get("attempt_count") != 1:
        raise ValueError("continuation delivery ledger violates one-attempt contract")
    return value


def load_continuation_delivery(run_dir: Path) -> dict[str, Any] | None:
    """Read the authoritative per-run delivery claim and state ledger."""
    return _read_delivery(Path(run_dir))


def _write_delivery_locked(run_dir: Path, delivery: dict[str, Any]) -> None:
    atomic_write_json(continuation_delivery_path(run_dir), delivery)
    _mirror_delivery_status(run_dir, delivery)


def _mirror_delivery_status(run_dir: Path, delivery: dict[str, Any]) -> None:
    update_status_fields(
        run_dir,
        continuation_mode="queue",
        continuation_state=str(delivery["state"]),
        continuation_attempt_count=1,
        continuation_delivery_id=str(delivery["delivery_id"]),
        continuation_claimed_at=str(delivery["claimed_at"]),
        continuation_command_started_at=delivery.get("command_started_at"),
        continuation_exit_code=delivery.get("exit_code"),
        continuation_acknowledged=delivery.get("queue_acknowledged"),
        continuation_error=delivery.get("error"),
        continuation_receiver_confirmed_at=delivery.get("receiver_confirmed_at"),
        continuation_receiver_thread_id=delivery.get("receiver_thread_id"),
    )


def record_continuation_preflight_failure(run_dir: Path, error: str) -> None:
    """Record a sender preflight failure without consuming the one-shot claim."""
    if continuation_delivery_path(Path(run_dir)).exists():
        raise ValueError("queue claim already exists; cannot alter preflight outcome")
    update_status_fields(
        run_dir,
        continuation_mode="queue",
        continuation_state="PENDING",
        continuation_error=str(error),
    )


def claim_queue_delivery(run_dir: Path) -> dict[str, Any]:
    """Durably claim the sole sender attempt before spawning ``codex queue``."""
    run_dir = Path(run_dir).resolve()
    manifest = load_manifest(run_dir)
    if manifest.continuation_mode != "queue":
        raise ValueError("run manifest is not queue-native")
    status = load_status(run_dir)
    if status.get("state") not in {"COMPLETED", "FAILED", "REVIEW_WAITING"}:
        raise ValueError("queue delivery requires a durable terminal optimizer state")
    completion_path = optimizer_completion_path(run_dir)
    if not completion_path.is_file():
        raise ValueError("durable optimizer completion marker is missing")
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    if completion.get("run_id") != manifest.run_id:
        raise ValueError("optimizer completion marker run_id does not match manifest")
    if completion.get("disposition") != status.get("optimizer_state"):
        raise ValueError("optimizer completion marker disposition does not match status")
    if completion.get("result_reference") != str(run_dir):
        raise ValueError("optimizer completion result reference does not match run directory")

    # The exclusive create is the cross-process compare-and-set. A process
    # crash while writing still leaves the path claimed, so recovery fails
    # closed instead of creating a second delivery attempt.
    ledger_path = continuation_delivery_path(run_dir)
    now = utc_now()
    delivery = {
        "schema_version": 1,
        "state": "CLAIMED",
        "attempt_count": 1,
        "delivery_id": secrets.token_hex(16),
        "run_id": manifest.run_id,
        "c2c_task_id": manifest.c2c_task_id,
        "plan_iteration": manifest.plan_iteration,
        "original_thread_id": manifest.original_thread_id,
        "delivery_sentinel": manifest.delivery_sentinel,
        "next_expected_step": manifest.next_expected_step,
        "result_reference": completion["result_reference"],
        "claimed_at": now,
        "command_started_at": None,
        "exit_code": None,
        "queue_acknowledged": None,
        "error": None,
        "receiver_confirmed_at": None,
        "receiver_thread_id": None,
    }
    encoded = (json.dumps(delivery, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    try:
        fd = os.open(ledger_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError(
            "queue delivery attempt is already claimed; automatic resend is forbidden"
        ) from exc
    try:
        payload = memoryview(encoded.encode("utf-8"))
        while payload:
            written = os.write(fd, payload)
            if written <= 0:
                raise OSError("short write while persisting queue delivery claim")
            payload = payload[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    _mirror_delivery_status(run_dir, delivery)
    return delivery


def mark_queue_command_started(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    with exclusive_lock(continuation_lock_path(run_dir)):
        delivery = _read_delivery(run_dir)
        if delivery is None or delivery.get("state") != "CLAIMED":
            raise ValueError("queue command requires the one-shot CLAIMED delivery")
        if delivery.get("command_started_at") is not None:
            raise ValueError("queue command has already been started")
        delivery["command_started_at"] = utc_now()
        _write_delivery_locked(run_dir, delivery)
        return delivery


def record_queue_sender_result(
    run_dir: Path,
    *,
    exit_code: int | None,
    error: str | None = None,
    stdout_sha256: str | None = None,
    stderr_sha256: str | None = None,
) -> dict[str, Any]:
    """Persist sender acknowledgement; every non-clean result stays ambiguous."""
    run_dir = Path(run_dir).resolve()
    with exclusive_lock(continuation_lock_path(run_dir)):
        delivery = _read_delivery(run_dir)
        if delivery is None:
            raise ValueError("queue sender has no durable one-shot claim")
        if delivery.get("state") == "RECEIVER_CONFIRMED":
            return delivery
        if delivery.get("state") != "CLAIMED":
            raise ValueError(f"queue sender result cannot update {delivery.get('state')}")
        delivery["exit_code"] = exit_code
        clean_ack = exit_code == 0 and error is None
        delivery["queue_acknowledged"] = True if clean_ack else None
        delivery["state"] = "SENDER_ACCEPTED" if clean_ack else "AMBIGUOUS"
        delivery["stdout_sha256"] = stdout_sha256
        delivery["stderr_sha256"] = stderr_sha256
        delivery["error"] = error if error is not None else (
            None if clean_ack else f"codex queue exited with code {exit_code}"
        )
        delivery["sender_finished_at"] = utc_now()
        _write_delivery_locked(run_dir, delivery)
        return delivery


def mark_stranded_queue_attempt_ambiguous(run_dir: Path) -> dict[str, Any] | None:
    """Fail closed when a claimed sender disappeared before reporting outcome."""
    run_dir = Path(run_dir).resolve()
    if not continuation_delivery_path(run_dir).exists():
        return None
    with exclusive_lock(continuation_lock_path(run_dir)):
        delivery = _read_delivery(run_dir)
        if delivery is None or delivery.get("state") != "CLAIMED":
            return delivery
        delivery["state"] = "AMBIGUOUS"
        delivery["error"] = "queue sender ended without a durable outcome; resend forbidden"
        delivery["sender_finished_at"] = utc_now()
        _write_delivery_locked(run_dir, delivery)
        return delivery


def confirm_queue_delivery(
    run_dir: Path,
    *,
    task_id: str,
    run_id: str,
    delivery_id: str,
    delivery_sentinel: str,
) -> dict[str, Any]:
    """Idempotently confirm arrival in the exact original Desktop thread."""
    from .codex_queue import current_codex_thread_id

    run_dir = Path(run_dir).resolve()
    thread_id = current_codex_thread_id()
    manifest = load_manifest(run_dir)
    if manifest.continuation_mode != "queue":
        raise ValueError("run manifest is not queue-native")
    if thread_id != (manifest.original_thread_id or "").lower():
        raise ValueError("current thread does not match the immutable queue target")
    if task_id != manifest.c2c_task_id or run_id != manifest.run_id:
        raise ValueError("queued task/run identity does not match the manifest")
    if not delivery_id:
        raise ValueError("queued delivery ID is required")
    if delivery_sentinel != manifest.delivery_sentinel:
        raise ValueError("queued delivery sentinel does not match the manifest")
    status = load_status(run_dir)
    if status.get("optimizer_state") not in {"COMPLETED", "FAILED", "REVIEW_WAITING"}:
        raise ValueError("optimizer has not reached a durable terminal state")
    completion_path = optimizer_completion_path(run_dir)
    if not completion_path.is_file():
        raise ValueError("durable optimizer completion marker is missing")
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    if completion.get("run_id") != manifest.run_id or completion.get("disposition") != status.get("optimizer_state"):
        raise ValueError("optimizer completion evidence does not match current status")
    if completion.get("result_reference") != str(run_dir) or not Path(completion["result_reference"]).exists():
        raise ValueError("durable result reference is missing or mismatched")

    with exclusive_lock(continuation_lock_path(run_dir)):
        delivery = _read_delivery(run_dir)
        if delivery is None or delivery.get("attempt_count") != 1:
            raise ValueError("queued turn has no single durable delivery claim")
        if delivery.get("original_thread_id") != thread_id:
            raise ValueError("delivery claim target does not match current thread")
        if delivery.get("c2c_task_id") != task_id or delivery.get("run_id") != run_id:
            raise ValueError("delivery claim task/run identity does not match")
        if delivery.get("delivery_id") != delivery_id:
            raise ValueError("queued delivery ID does not match the one-shot claim")
        if delivery.get("delivery_sentinel") != delivery_sentinel:
            raise ValueError("delivery claim sentinel does not match")
        if not delivery.get("command_started_at"):
            raise ValueError("queue command start was not durably recorded")
        if delivery.get("state") == "RECEIVER_CONFIRMED":
            if delivery.get("receiver_thread_id") != thread_id:
                raise ValueError("previous receipt was recorded for a different thread")
            return delivery
        if delivery.get("state") not in {"CLAIMED", "SENDER_ACCEPTED", "AMBIGUOUS"}:
            raise ValueError(f"delivery cannot be confirmed from {delivery.get('state')}")
        delivery["state"] = "RECEIVER_CONFIRMED"
        delivery["receiver_confirmed_at"] = utc_now()
        delivery["receiver_thread_id"] = thread_id
        delivery["error"] = None
        _write_delivery_locked(run_dir, delivery)
        return delivery


def read_current_session(path: Path, project_root: Path, *, max_age_s: float = 86400.0,
                         now: datetime | None = None) -> dict[str, Any]:
    """Load and validate the Hook-captured session bound to this project root."""
    path = Path(path)
    if not path.exists():
        raise SessionValidationError(f"Codex session capture is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionValidationError(f"invalid Codex session capture: {path}") from exc
    session_id = str(value.get("session_id", "")).strip()
    if not session_id:
        raise SessionValidationError("Codex session capture contains an empty session_id")
    hook_event = value.get("hook_event_name") or value.get("hook_event")
    if hook_event is not None and str(hook_event) != "SessionStart":
        raise SessionValidationError(
            f"Codex session capture has unexpected hook event: {hook_event}"
        )
    expected = Path(project_root).resolve()
    captured_project_root = value.get("project_root")
    if captured_project_root:
        actual_project_root = Path(str(captured_project_root)).resolve()
        if os.path.normcase(str(actual_project_root)) != os.path.normcase(str(expected)):
            raise SessionValidationError(
                "Codex session capture project_root does not match project root: "
                f"{actual_project_root} != {expected}"
            )
    captured_cwd = value.get("session_cwd") or value.get("cwd")
    if not captured_cwd:
        raise SessionValidationError("Codex session capture contains no session_cwd")
    actual = Path(str(captured_cwd)).resolve()
    if not actual.is_dir():
        raise SessionValidationError(f"Codex session cwd does not exist: {actual}")
    try:
        common = os.path.commonpath([os.path.normcase(str(actual)), os.path.normcase(str(expected))])
    except ValueError:
        common = ""
    if common != os.path.normcase(str(expected)):
        raise SessionValidationError(
            f"Codex session cwd is outside project root: {actual} not under {expected}"
        )
    captured_at = value.get("captured_at")
    if not captured_at:
        raise SessionValidationError("Codex session capture contains no captured_at")
    try:
        timestamp = datetime.fromisoformat(str(captured_at))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise SessionValidationError("Codex session capture has invalid captured_at") from exc
    reference = now or datetime.now(timezone.utc)
    age = (reference - timestamp).total_seconds()
    if age < -60 or age > float(max_age_s):
        raise SessionValidationError(
            f"Codex session capture is stale or from the future (age={age:.0f}s)"
        )
    return value


def resolve_session(
    *,
    explicit_session_id: str | None,
    session_path: Path,
    project_root: Path,
    max_age_s: float,
) -> dict[str, Any]:
    """Resolve a callback target with explicit IDs taking precedence."""
    if explicit_session_id is not None:
        session_id = str(explicit_session_id).strip()
        if not session_id:
            raise SessionValidationError("explicit Codex session ID must not be empty")
        return {"session_id": session_id, "source": "explicit"}
    return read_current_session(session_path, project_root, max_age_s=max_age_s)


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_status(run_dir: Path) -> str:
    """Return concise human-readable status for PowerShell and CI logs."""
    run_dir = Path(run_dir).resolve()
    manifest = load_manifest(run_dir)
    status = load_status(run_dir)
    delivery = None
    try:
        delivery = load_continuation_delivery(run_dir)
    except (OSError, ValueError, json.JSONDecodeError):
        delivery = {"state": "AMBIGUOUS", "attempt_count": 1}
    started = parse_timestamp(status.get("started_at")) or parse_timestamp(manifest.created_at)
    elapsed = max(0.0, (datetime.now(timezone.utc) - started).total_seconds()) if started else 0.0
    callback = (
        "queue" if manifest.continuation_mode == "queue" else
        "review-waiting" if status.get("state") == "REVIEW_WAITING" else
        "completed" if status.get("callback_completed") else
        "failed" if status.get("state") == "CALLBACK_FAILED" else
        "running" if status.get("state") == "CALLBACK_RUNNING" else
        "pending" if manifest.callback_enabled else "disabled"
    )
    worker_pid = status.get("worker_pid")
    optimizer_pid = status.get("optimizer_pid")
    worker_liveness = "alive" if _pid_exists(worker_pid) else "dead/unknown"
    optimizer_liveness = "alive" if _pid_exists(optimizer_pid) else "dead/unknown"
    return "\n".join([
        f"run_id: {manifest.run_id}",
        f"overall_state: {status['state']}",
        f"optimizer.state: {status.get('optimizer_state') or 'UNKNOWN'}",
        f"optimizer.exit_code: {status.get('exit_code')}",
        f"callback.state: {callback}",
        f"callback.attempts: {status.get('callback_attempts', 0)}",
        f"continuation.mode: {manifest.continuation_mode or 'legacy_resume'}",
        f"continuation.state: {delivery.get('state') if delivery else status.get('continuation_state', 'DISABLED')}",
        f"continuation.attempt_count: {delivery.get('attempt_count', 0) if delivery else status.get('continuation_attempt_count', 0)}",
        f"continuation.delivery_id: {delivery.get('delivery_id') if delivery else status.get('continuation_delivery_id')}",
        f"continuation.target_thread: {manifest.original_thread_id or 'n/a'}",
        f"continuation.exit_code: {delivery.get('exit_code') if delivery else status.get('continuation_exit_code')}",
        f"continuation.error: {delivery.get('error') if delivery else status.get('continuation_error')}",
        f"worker_pid: {worker_pid} ({worker_liveness})",
        f"optimizer_pid: {optimizer_pid} ({optimizer_liveness})",
        f"elapsed: {elapsed:.1f}s",
        f"run_dir: {run_dir}",
    ])


__all__ = [
    "SessionValidationError", "atomic_write_json", "callback_lock_path",
    "claim_queue_delivery", "confirm_queue_delivery", "continuation_delivery_path",
    "continuation_lock_path", "create_run", "exclusive_lock", "finish_callback",
    "format_status", "load_continuation_delivery", "load_manifest", "load_status",
    "lock_owner_pid", "manifest_path", "mark_queue_command_started",
    "mark_stranded_queue_attempt_ambiguous", "optimizer_completion_path",
    "prepare_callback", "read_current_session", "read_lock_metadata",
    "record_continuation_preflight_failure", "record_optimizer_completion",
    "record_queue_sender_result", "reclaim_stale_lock", "resolve_session",
    "status_path", "transition", "update_status_fields", "utc_now",
]
