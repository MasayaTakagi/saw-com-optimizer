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
from urllib.parse import urlsplit


class CodexQueuePreflightError(RuntimeError):
    """The exact-thread queue path is not qualified to run."""


class CodexQueueTimeoutError(TimeoutError):
    """Queue delivery exceeded its finite process timeout."""


QUEUE_PREFLIGHT_TIMEOUT_S = 30.0
QUEUE_SEND_TIMEOUT_S = 120.0
QUEUE_OUTPUT_EXCERPT_MAX_BYTES = 16 * 1024
THREAD_ID_RE = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?i)(?P<label>\b(?:access[_-]?token|refresh[_-]?token|id[_-]?token|token|client[_-]?secret|oauth[_-]?(?:code|token)|password|passwd|pwd|passphrase|api[_-]?key|cookie|set-cookie|session[_-]?(?:id|token)|secret)\b\s*[:=]\s*)(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
)
_AUTHORIZATION_BEARER_RE = re.compile(
    r"(?i)(\bauthorization\s*[:=]\s*bearer\s+|\bbearer\s+)[A-Za-z0-9._~+/-]+={0,2}"
)
_AUTHORIZATION_VALUE_RE = re.compile(
    r"(?i)(\bauthorization\s*[:=]\s*)(?!\s*bearer\b)[^\r\n]+"
)
_COOKIE_HEADER_RE = re.compile(r"(?im)^(\s*(?:cookie|set-cookie)\s*:\s*)[^\r\n]+")
_CREDENTIAL_QUERY_RE = re.compile(
    r"(?i)([?&](?:code|state|access_token|refresh_token|client_secret|password|token|key)=)[^&#\s]+"
)
_URL_RE = re.compile(r"(?i)\bhttps?://[^\s<>\"']+")
_URL_CREDENTIAL_RE = re.compile(r"(?i)(\bhttps?://)[^/\s:@]+:[^@\s/]+@")
_TEMPORARY_TUNNEL_SUFFIXES = (
    "trycloudflare.com", "cfargotunnel.com", "ngrok.io", "ngrok.app",
    "ngrok-free.app", "ngrok-free.dev", "ngrok.dev", "loca.lt",
    "localtunnel.me", "localhost.run", "serveo.net", "tunnelmole.net",
    "tunnelmole.com", "bore.pub", "pinggy.link", "devtunnels.ms",
    "loclx.io", "zrok.io",
)


@dataclass(frozen=True)
class QueueResult:
    exit_code: int | None
    stdout: str
    stderr: str
    stdout_bytes: bytes
    stderr_bytes: bytes
    started_at: str
    finished_at: str
    error: str | None = None


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _captured_bytes(value: Any) -> bytes:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8")
    return str(value).encode("utf-8")


def _redact_sensitive_text(text: str) -> tuple[str, bool]:
    redacted = text
    redacted, cookie_count = _COOKIE_HEADER_RE.subn(r"\1<REDACTED>", redacted)
    redacted, bearer_count = _AUTHORIZATION_BEARER_RE.subn(r"\1<REDACTED>", redacted)
    redacted, authorization_count = _AUTHORIZATION_VALUE_RE.subn(r"\1<REDACTED>", redacted)
    redacted, url_credentials_count = _URL_CREDENTIAL_RE.subn(r"\1<REDACTED>@", redacted)

    url_redacted = False

    def redact_sensitive_url(match: re.Match[str]) -> str:
        nonlocal url_redacted
        candidate = match.group(0)
        trailing = ""
        while candidate and candidate[-1] in ".,;:!?)]}":
            trailing = candidate[-1] + trailing
            candidate = candidate[:-1]
        try:
            parsed = urlsplit(candidate)
            host = (parsed.hostname or "").casefold().rstrip(".")
        except ValueError:
            return match.group(0)
        labels = host.split(".")
        temporary_tunnel = any(
            host == suffix or host.endswith("." + suffix)
            for suffix in _TEMPORARY_TUNNEL_SUFFIXES
        )
        mcp_host = any(
            label == "mcp" or label.startswith("mcp-") or label.endswith("-mcp")
            for label in labels
        )
        mcp_path = any(segment.casefold() == "mcp" for segment in parsed.path.split("/"))
        if temporary_tunnel or mcp_host or mcp_path:
            url_redacted = True
            return "<REDACTED_PUBLIC_MCP_URL>" + trailing
        return match.group(0)

    redacted = _URL_RE.sub(redact_sensitive_url, redacted)
    redacted, assignment_count = _CREDENTIAL_ASSIGNMENT_RE.subn(
        lambda match: match.group("label") + "<REDACTED>", redacted,
    )
    redacted, query_count = _CREDENTIAL_QUERY_RE.subn(r"\1<REDACTED>", redacted)
    return redacted, any((
        cookie_count, bearer_count, authorization_count, assignment_count, query_count,
        url_credentials_count, url_redacted,
    ))


def _bounded_redacted_excerpt(raw: bytes, *, limit: int = QUEUE_OUTPUT_EXCERPT_MAX_BYTES) -> tuple[str, bool, bool]:
    text, redacted = _redact_sensitive_text(raw.decode("utf-8", errors="replace"))
    encoded = text.encode("utf-8")
    truncated = len(raw) > limit or len(encoded) > limit
    if not truncated:
        return text, False, redacted

    marker = b"\n...[excerpt truncated; beginning and end retained]...\n"
    budget = max(0, limit - len(marker))
    head_size = (budget + 1) // 2
    tail_size = budget - head_size
    head = encoded[:head_size].decode("utf-8", errors="ignore")
    tail = encoded[-tail_size:].decode("utf-8", errors="ignore") if tail_size else ""
    excerpt = head + marker.decode("ascii") + tail
    while len(excerpt.encode("utf-8")) > limit:
        tail = tail[1:]
        excerpt = head + marker.decode("ascii") + tail
    return excerpt, True, redacted


def _sender_diagnostics(result: QueueResult, *, codex_executable: str,
                        codex_version: str) -> dict[str, Any]:
    stdout_excerpt, stdout_truncated, stdout_redacted = _bounded_redacted_excerpt(result.stdout_bytes)
    stderr_excerpt, stderr_truncated, stderr_redacted = _bounded_redacted_excerpt(result.stderr_bytes)
    safe_executable, executable_redacted = _redact_sensitive_text(codex_executable)
    return {
        "schema_version": 1,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "codex_executable": safe_executable,
        "codex_version": codex_version,
        "exit_code": result.exit_code,
        "stdout_sha256": hashlib.sha256(result.stdout_bytes).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr_bytes).hexdigest(),
        "stdout_excerpt": stdout_excerpt,
        "stderr_excerpt": stderr_excerpt,
        "stdout_original_bytes": len(result.stdout_bytes),
        "stderr_original_bytes": len(result.stderr_bytes),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "redaction_status": "PASS",
        "redaction_applied": any((stdout_redacted, stderr_redacted, executable_redacted)),
    }


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
    command = build_queue_command(thread_id, message, codex_executable=codex_executable)
    started_at = _utc_timestamp()
    stdout_bytes = b""
    stderr_bytes = b""
    exit_code: int | None
    error: str | None
    try:
        result = runner(
            command,
            cwd=str(Path(project_root).resolve()), env=dict(os.environ),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout_s, check=False,
        )
        stdout_bytes = _captured_bytes(result.stdout)
        stderr_bytes = _captured_bytes(result.stderr)
        exit_code = int(result.returncode)
        error = None if exit_code == 0 else "codex queue returned a non-zero exit"
    except subprocess.TimeoutExpired as exc:
        stdout_bytes = _captured_bytes(exc.stdout if exc.stdout is not None else exc.output)
        stderr_bytes = _captured_bytes(exc.stderr)
        exit_code = None
        error = f"{CodexQueueTimeoutError.__name__}: codex queue exceeded finite process timeout"
    except OSError as exc:
        exit_code = None
        error = f"{type(exc).__name__}: {exc}"

    return QueueResult(
        exit_code=exit_code,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        started_at=started_at,
        finished_at=_utc_timestamp(),
        error=error,
    )


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
    diagnostics = _sender_diagnostics(
        result,
        codex_executable=executable,
        codex_version=str(actual["codex_version"]),
    )
    safe_error = None if result.error is None else _redact_sensitive_text(result.error)[0]
    return record_queue_sender_result(
        root, exit_code=result.exit_code, error=safe_error,
        stdout_sha256=diagnostics["stdout_sha256"],
        stderr_sha256=diagnostics["stderr_sha256"],
        sender_diagnostics=diagnostics,
    )


__all__ = [
    "CodexQueuePreflightError", "CodexQueueTimeoutError", "QueueResult",
    "assert_preflight_compatible", "build_queue_command", "build_queue_message",
    "current_codex_thread_id", "run_codex_queue", "run_codex_queue_preflight",
    "send_queue_continuation", "validate_thread_id",
]
