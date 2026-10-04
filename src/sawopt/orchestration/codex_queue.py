"""Exact-thread Codex queue transport for detached run continuations."""
from __future__ import annotations

import ctypes
import hashlib
import os
import re
import secrets
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


class CodexQueuePreflightError(RuntimeError):
    """The exact-thread queue path is not qualified to run."""


class CodexQueueTimeoutError(TimeoutError):
    """Queue delivery exceeded its finite process timeout."""


QUEUE_PREFLIGHT_TIMEOUT_S = 30.0
QUEUE_SEND_TIMEOUT_S = 120.0
THREAD_ID_RE = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


@dataclass(frozen=True)
class QueueResult:
    exit_code: int
    stdout: str
    stderr: str


def validate_thread_id(thread_id: str) -> str:
    value = str(thread_id).strip()
    if not THREAD_ID_RE.fullmatch(value):
        raise ValueError("original Codex thread ID must be a UUID")
    return value.lower()


def current_codex_thread_id() -> str:
    """Use only the thread identity supplied by the Codex runtime environment."""
    value = str(os.environ.get("CODEX_THREAD_ID") or "").strip()
    if not value:
        raise CodexQueuePreflightError("Codex runtime did not provide CODEX_THREAD_ID")
    return validate_thread_id(value)


def _windows_profile_folder() -> str:
    if os.name != "nt":
        return str(Path.home())
    buffer = ctypes.create_unicode_buffer(32768)
    result = ctypes.windll.shell32.SHGetFolderPathW(None, 40, None, 0, buffer)
    if result != 0 or not buffer.value:
        raise CodexQueuePreflightError("Windows UserProfile special folder is unavailable")
    return buffer.value


def _effective_user() -> str:
    if os.name != "nt":
        return str(os.environ.get("USER") or os.environ.get("USERNAME") or "")
    try:
        result = subprocess.run(
            ["whoami.exe"], capture_output=True, text=True, timeout=10.0, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CodexQueuePreflightError("effective Windows user could not be resolved") from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise CodexQueuePreflightError("effective Windows user could not be resolved")
    return result.stdout.strip()


def _identity_snapshot() -> dict[str, str]:
    user_profile = str(os.environ.get("USERPROFILE") or "").strip()
    special_profile = str(_windows_profile_folder()).strip()
    effective_user = _effective_user()
    if not user_profile or not special_profile:
        raise CodexQueuePreflightError("user profile path is unavailable")
    if os.path.normcase(os.path.abspath(user_profile)) != os.path.normcase(os.path.abspath(special_profile)):
        raise CodexQueuePreflightError("USERPROFILE differs from Windows UserProfile")
    if os.name == "nt":
        account = effective_user.rsplit("\\", 1)[-1].strip()
        if not account or account.casefold() != Path(user_profile).name.casefold():
            raise CodexQueuePreflightError("effective Windows account is not the normal profile user")
    return {
        "effective_user": effective_user,
        "user_profile": str(Path(user_profile).resolve()),
        "windows_user_profile": str(Path(special_profile).resolve()),
    }


def _resolve_executable(codex_executable: str | None) -> str:
    resolved = codex_executable or shutil.which("codex")
    if not resolved:
        raise CodexQueuePreflightError("Codex executable is not resolvable")
    path = Path(resolved).expanduser()
    if not path.is_absolute() and (located := shutil.which(str(path))):
        path = Path(located)
    try:
        path = path.resolve(strict=True)
    except OSError as exc:
        raise CodexQueuePreflightError("Codex executable is unavailable") from exc
    if not path.is_file() or (os.name == "nt" and path.suffix.casefold() not in {".exe", ".com"}):
        raise CodexQueuePreflightError("Codex executable must be a native executable file")
    return str(path)


def _run_cli(command: list[str], *, cwd: str | Path, timeout_s: float,
             runner: Callable[..., Any]) -> Any:
    try:
        return runner(
            command, cwd=str(cwd), env=dict(os.environ), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CodexQueuePreflightError("Codex queue preflight command timed out") from exc
    except OSError as exc:
        raise CodexQueuePreflightError(f"Codex preflight command could not start: {type(exc).__name__}") from exc


def run_codex_queue_preflight(thread_id: str, *, project_root: str | Path,
                              codex_executable: str | None = None,
                              runner: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    exact_thread = validate_thread_id(thread_id)
    identity = _identity_snapshot()
    executable = _resolve_executable(codex_executable)
    root = Path(project_root).resolve()
    version = _run_cli([executable, "--version"], cwd=root,
                       timeout_s=QUEUE_PREFLIGHT_TIMEOUT_S, runner=runner)
    version_output = (version.stdout or "").strip()
    version_line = next((
        line.strip() for line in version_output.splitlines()
        if re.search(r"(?i)\bcodex\b", line) and re.search(r"\d+\.\d+", line)
    ), None)
    if version.returncode != 0 or version_line is None:
        raise CodexQueuePreflightError("Codex version preflight failed")
    help_result = _run_cli([executable, "queue", "--help"], cwd=root,
                           timeout_s=QUEUE_PREFLIGHT_TIMEOUT_S, runner=runner)
    help_output = "\n".join((help_result.stdout or "", help_result.stderr or ""))
    if help_result.returncode != 0 or "--thread" not in help_output or "--message" not in help_output:
        raise CodexQueuePreflightError("codex queue help must pass and support --thread and --message")
    help_identity = help_result.stdout or help_output
    return {
        "status": "PASS", "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "thread_id": exact_thread, **identity, "codex_executable": executable,
        "codex_version": version_line,
        "queue_help_sha256": hashlib.sha256(help_identity.encode("utf-8")).hexdigest(),
        "explicit_thread": True, "explicit_message": True,
    }


def assert_preflight_compatible(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    for key in ("thread_id", "effective_user", "user_profile", "windows_user_profile",
                "codex_executable", "codex_version", "queue_help_sha256"):
        if str(actual.get(key, "")).casefold() != str(expected.get(key, "")).casefold():
            raise CodexQueuePreflightError(f"queue sender {key} differs from launch preflight")


def build_queue_message(manifest: Any, *, delivery_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", str(delivery_id)):
        raise ValueError("delivery ID must be 32 lowercase hexadecimal characters")
    required = {
        "RUN_ID": manifest.run_id,
        "RESULT": manifest.run_dir,
        "NEXT_EXPECTED_STEP": manifest.next_expected_step,
        "REVIEW_OUTPUT": manifest.review_output_dir,
        "DELIVERY_ID": delivery_id,
        "DELIVERY_SENTINEL": manifest.delivery_sentinel,
    }
    if any(value in (None, "") for value in required.values()):
        raise ValueError("queue manifest is missing handoff fields")
    message = (
        "[SAW ASYNC COMPLETE]\n" + "\n".join(f"{key}: {value}" for key, value in required.items())
        + "\nUse runtime CODEX_THREAD_ID to run orchestration.cli confirm-queue with RUN_ID, DELIVERY_ID, and DELIVERY_SENTINEL above; stop if identity fails. Use run_manifest.project_root as Git cwd and manifest.command[0] with PYTHONPATH=<project_root>/src for project commands. Verify terminal state, run sawopt export-review --run RESULT, commit only REVIEW_OUTPUT, push the same branch, then run mark-review-published with the pushed branch and commit. Stop; do no scientific review or new run."
    )
    if len(message.encode("utf-8")) > 1024:
        raise ValueError("queue continuation message exceeds 1 KiB")
    return message


def build_queue_command(thread_id: str, message: str, *, codex_executable: str) -> list[str]:
    exact = validate_thread_id(thread_id)
    if not message or len(message.encode("utf-8")) > 1024:
        raise ValueError("queue message must be non-empty and no more than 1 KiB")
    return [codex_executable, "queue", "--thread", exact, "--message", message]


def run_codex_queue(thread_id: str, message: str, *, codex_executable: str,
                    project_root: str | Path, timeout_s: float = QUEUE_SEND_TIMEOUT_S,
                    runner: Callable[..., Any] = subprocess.run) -> QueueResult:
    if timeout_s <= 0:
        raise ValueError("queue timeout must be positive")
    try:
        result = runner(
            build_queue_command(thread_id, message, codex_executable=codex_executable),
            cwd=str(Path(project_root).resolve()), env=dict(os.environ),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CodexQueueTimeoutError("codex queue exceeded finite timeout") from exc
    return QueueResult(int(result.returncode), str(result.stdout or ""), str(result.stderr or ""))


def send_queue_continuation(run_dir: str | Path, *, codex_executable: str | None = None,
                            preflight_runner: Callable[..., Any] = subprocess.run,
                            queue_runner: Callable[..., Any] = subprocess.run,
                            timeout_s: float = QUEUE_SEND_TIMEOUT_S) -> dict[str, Any]:
    from .run_manager import (
        claim_queue_delivery, load_manifest, mark_queue_command_started,
        record_continuation_preflight_failure, record_queue_sender_result,
    )
    root = Path(run_dir).resolve()
    manifest = load_manifest(root)
    if manifest.schema_version != 4 or manifest.continuation_mode != "queue":
        raise ValueError("only schema-v4 queue manifests use project-neutral continuation")
    expected = manifest.queue_preflight or {}
    executable = codex_executable or str(expected.get("codex_executable") or "")
    if not executable:
        raise CodexQueuePreflightError("manifest has no pinned Codex executable")
    try:
        actual = run_codex_queue_preflight(
            manifest.original_thread_id or "", project_root=manifest.project_root,
            codex_executable=executable, runner=preflight_runner,
        )
        assert_preflight_compatible(actual, expected)
    except BaseException as exc:
        record_continuation_preflight_failure(root, f"{type(exc).__name__}: {exc}")
        return {"state": "PENDING", "attempt_count": 0, "preflight_error": str(exc)}

    # Validate all deterministic payload fields before the irreversible claim.
    delivery_id = secrets.token_hex(16)
    message = build_queue_message(manifest, delivery_id=delivery_id)
    claim_queue_delivery(root, delivery_id=delivery_id)
    try:
        mark_queue_command_started(root)
        result = run_codex_queue(
            manifest.original_thread_id or "", message, codex_executable=executable,
            project_root=manifest.project_root, timeout_s=timeout_s, runner=queue_runner,
        )
    except BaseException as exc:
        return record_queue_sender_result(
            root, exit_code=None, error=f"{type(exc).__name__}: {exc}",
        )
    return record_queue_sender_result(
        root, exit_code=result.exit_code,
        error=None if result.exit_code == 0 else "codex queue returned a non-zero exit",
        stdout_sha256=hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
        stderr_sha256=hashlib.sha256(result.stderr.encode("utf-8")).hexdigest(),
    )


__all__ = [
    "CodexQueuePreflightError", "CodexQueueTimeoutError", "QueueResult",
    "assert_preflight_compatible", "build_queue_command", "build_queue_message",
    "current_codex_thread_id", "run_codex_queue", "run_codex_queue_preflight",
    "send_queue_continuation", "validate_thread_id",
]
