"""Filesystem-backed run manifests, status transitions, and session capture."""
from __future__ import annotations

import json
import os
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
    "RUNNING": {"COMPLETED", "FAILED", "ORPHANED", "ORPHANED_CHILD"},
    "COMPLETED": {"CALLBACK_PENDING"},
    "FAILED": {"CALLBACK_PENDING"},
    "CALLBACK_PENDING": {"CALLBACK_RUNNING"},
    "CALLBACK_RUNNING": {"REVIEWED", "CALLBACK_FAILED"},
    "CALLBACK_FAILED": {"CALLBACK_PENDING"},
    "REVIEWED": set(),
    "ORPHANED": set(),
    "ORPHANED_CHILD": set(),
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
    run_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(manifest_path(run_dir), manifest.to_dict())
    atomic_write_json(status_path(run_dir), RunStatus(
        state="CREATED",
        updated_at=manifest.created_at,
        callback_enabled=manifest.callback_enabled,
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
        if new_state in {"COMPLETED", "FAILED", "ORPHANED", "ORPHANED_CHILD"}:
            value["finished_at"] = value.get("finished_at") or now
            if new_state in {"COMPLETED", "FAILED"}:
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
    if current_state in {"COMPLETED", "FAILED", "CALLBACK_FAILED"}:
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
    started = parse_timestamp(status.get("started_at")) or parse_timestamp(manifest.created_at)
    elapsed = max(0.0, (datetime.now(timezone.utc) - started).total_seconds()) if started else 0.0
    callback = (
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
        f"worker_pid: {worker_pid} ({worker_liveness})",
        f"optimizer_pid: {optimizer_pid} ({optimizer_liveness})",
        f"elapsed: {elapsed:.1f}s",
        f"run_dir: {run_dir}",
    ])


__all__ = [
    "SessionValidationError", "atomic_write_json", "callback_lock_path",
    "create_run", "exclusive_lock", "finish_callback", "format_status",
    "load_manifest", "load_status", "lock_owner_pid", "manifest_path",
    "prepare_callback", "read_current_session", "read_lock_metadata",
    "reclaim_stale_lock", "resolve_session", "status_path", "transition",
    "update_status_fields", "utc_now",
]
