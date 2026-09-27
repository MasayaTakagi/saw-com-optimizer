"""Explicit-ID Codex review callback for completed asynchronous runs."""
from __future__ import annotations

import shutil
import subprocess
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from .models import RunManifest


class CodexCallbackTimeoutError(TimeoutError):
    """Raised when a Codex callback exceeds its finite execution timeout."""


class CodexCallbackTargetMismatchError(RuntimeError):
    """Raised when structured Codex output names a different session/thread."""


class CodexCallbackTargetUnavailableError(RuntimeError):
    """Raised when structured Codex output does not identify a target."""


class CodexCallbackPreflightError(RuntimeError):
    """Raised when callback access or exact-session validation fails pre-launch."""


CALLBACK_PREFLIGHT_TIMEOUT_S = 120.0
CALLBACK_PREFLIGHT_PROMPT = (
    "This is a callback connectivity preflight only. Do not inspect, read, or "
    "modify repository files; do not run commands, use connectors, or launch "
    "any work. Reply with exactly CALLBACK_PREFLIGHT_OK."
)


COMPLETED_PROMPT = """The production optimization run has completed.

run_id: {run_id}
orchestration_root: {run_dir}
optimizer_output_dir: {optimizer_run_dir}
status: COMPLETED
exit_code: 0

Review this run now.

Required actions:
1. Read run_manifest.json and status.json from orchestration_root.
2. Inspect generated summary/results/logs under optimizer_output_dir.
3. If result.json exists, report its run_id and result value explicitly.
4. Validate that the run completed correctly.
5. Compare the result with the experiment objective and previous relevant runs.
6. Identify convergence, stability, seed dependence, and any suspicious behavior.
7. Recommend the next experiment or stopping criterion.
8. Do NOT automatically launch another production optimization run.
"""

FAILED_PROMPT = """The production optimization run failed.

run_id: {run_id}
orchestration_root: {run_dir}
optimizer_output_dir: {optimizer_run_dir}
status: FAILED
exit_code: {exit_code}

Investigate the failure now.

Required actions:
1. Read run_manifest.json and status.json from orchestration_root.
2. Inspect optimizer output and the captured stdout.log/stderr.log under orchestration_root.
3. Identify the root cause.
4. Determine whether results are usable.
5. Propose a fix/retry plan if appropriate.
6. Do NOT automatically launch another production optimization run.
"""


def callback_prompt(manifest: RunManifest, *, exit_code: int | None,
                    optimizer_failed: bool) -> str:
    template = FAILED_PROMPT if optimizer_failed else COMPLETED_PROMPT
    return template.format(
        run_id=manifest.run_id,
        run_dir=manifest.run_dir,
        optimizer_run_dir=manifest.effective_optimizer_run_dir,
        exit_code="unknown" if exit_code is None else exit_code,
    )


def build_resume_command(
    session_id: str,
    prompt: str,
    *,
    codex_executable: str = "codex",
    structured_output: bool = False,
) -> list[str]:
    """Build a callback command that cannot accidentally select ``--last``."""
    if not session_id.strip():
        raise ValueError("session_id must not be empty")
    command = [
        codex_executable,
        "exec",
        "--sandbox",
        "workspace-write",
    ]
    if structured_output:
        command.append("--json")
    command.extend(["resume", session_id, prompt])
    return command


def _observed_target_ids(output: str) -> dict[str, set[str]]:
    """Extract only session/thread identifiers from Codex JSONL events."""
    observed: dict[str, set[str]] = {"session_id": set(), "thread_id": set()}
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        stack = [value]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                for key, child in item.items():
                    if key in observed and isinstance(child, (str, int)):
                        observed[key].add(str(child))
                    elif isinstance(child, (dict, list)):
                        stack.append(child)
            elif isinstance(item, list):
                stack.extend(item)
    return observed


def _completed_agent_messages(output: str) -> list[str]:
    """Return only completed agent-message text from Codex JSONL events."""
    messages: list[str] = []
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(event, dict) or event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if isinstance(text, str):
            messages.append(text.replace("\r\n", "\n").strip())
    return messages


def _callback_environment() -> dict[str, str]:
    """Build the same Codex state environment for preflight and callbacks."""
    callback_env = dict(os.environ)
    # Detached Windows workers may inherit USERPROFILE without HOME. Codex
    # resolves its global state/session store through these variables.
    if not callback_env.get("HOME") and callback_env.get("USERPROFILE"):
        callback_env["HOME"] = callback_env["USERPROFILE"]
    if not callback_env.get("CODEX_HOME") and callback_env.get("USERPROFILE"):
        callback_env["CODEX_HOME"] = str(Path(callback_env["USERPROFILE"]) / ".codex")
    return callback_env


def _run_codex_prompt(
    session_id: str,
    prompt: str,
    *,
    cwd: str,
    callback_log: Path,
    codex_executable: str | None,
    timeout_s: float | None,
    runner: Callable[..., object],
) -> tuple[int, str, str]:
    if not session_id.strip():
        raise ValueError("session_id must not be empty")
    executable = codex_executable or shutil.which("codex") or "codex"
    command = build_resume_command(
        session_id,
        prompt,
        codex_executable=executable,
        structured_output=True,
    )
    if timeout_s is not None and float(timeout_s) <= 0:
        raise ValueError("callback timeout must be positive or None")
    callback_log = Path(callback_log)
    with callback_log.open("a", encoding="utf-8") as stream:
        stream.write(f"$ {executable} exec resume {session_id} <review-prompt>\n")
        try:
            result = runner(
                command,
                cwd=cwd,
                env=_callback_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            stream.write(f"callback timed out after {float(timeout_s):.1f}s\n")
            raise CodexCallbackTimeoutError(
                f"Codex callback timed out after {float(timeout_s):.1f}s"
            ) from exc
        except BaseException as exc:
            stream.write(f"callback process failed: {type(exc).__name__}: {exc}\n")
            raise
        output = getattr(result, "stdout", "") or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        stream.write(output)
        observed = _observed_target_ids(output)
        target = session_id
        all_observed = observed["session_id"] | observed["thread_id"]
        if not all_observed:
            stream.write(
                "callback target validation: unavailable; "
                "Codex emitted no session_id/thread_id JSON event\n"
            )
            raise CodexCallbackTargetUnavailableError(
                "Codex emitted no session_id/thread_id JSON event"
            )
        if all_observed != {target}:
            stream.write(
                "callback target validation: mismatch; "
                f"requested={target}; observed={sorted(all_observed)}\n"
            )
            raise CodexCallbackTargetMismatchError(
                f"Codex callback resumed a different session/thread: "
                f"requested={target}; observed={sorted(all_observed)}"
            )
        stream.write(f"callback target validation: matched {target}\n")
    return int(getattr(result, "returncode", 0)), output, executable


def run_codex_callback_preflight(
    session_id: str,
    *,
    project_root: str,
    codex_executable: str | None = None,
    timeout_s: float = CALLBACK_PREFLIGHT_TIMEOUT_S,
    runner: Callable[..., object] = subprocess.run,
) -> dict[str, str]:
    """Prove the exact session and callback state are usable before launch."""
    executable = codex_executable or shutil.which("codex")
    if not executable:
        raise CodexCallbackPreflightError("Codex callback executable is not resolvable")
    if codex_executable and not Path(codex_executable).is_file():
        resolved = shutil.which(codex_executable)
        if not resolved:
            raise CodexCallbackPreflightError(
                f"Codex callback executable is not resolvable: {codex_executable}"
            )
        executable = resolved
    with tempfile.TemporaryDirectory(prefix="sawopt-callback-preflight-") as temporary:
        callback_log = Path(temporary) / "callback.log"
        try:
            exit_code, output, resolved_executable = _run_codex_prompt(
                session_id,
                CALLBACK_PREFLIGHT_PROMPT,
                cwd=project_root,
                callback_log=callback_log,
                codex_executable=executable,
                timeout_s=timeout_s,
                runner=runner,
            )
        except Exception as exc:
            raise CodexCallbackPreflightError(
                f"Codex callback preflight failed: {type(exc).__name__}: {exc}"
            ) from exc
    if exit_code != 0:
        raise CodexCallbackPreflightError(
            f"Codex callback preflight exited with code {exit_code}"
        )
    if "CALLBACK_PREFLIGHT_OK" not in _completed_agent_messages(output):
        raise CodexCallbackPreflightError(
            "Codex callback preflight did not return an exact completed agent-message acknowledgement"
        )
    return {
        "status": "PASS",
        "session_id": session_id,
        "validated_target_id": session_id,
        "executable": resolved_executable,
    }


def run_codex_callback(manifest: RunManifest, *, exit_code: int | None,
                       optimizer_failed: bool,
                       codex_executable: str | None = None,
                       timeout_s: float | None = 1800.0,
                       runner: Callable[..., object] = subprocess.run) -> int:
    """Resume the exact captured session and write all callback output to a log."""
    if not manifest.codex_session_id:
        raise ValueError("callback is enabled but run manifest has no Codex session ID")
    prompt = callback_prompt(manifest, exit_code=exit_code, optimizer_failed=optimizer_failed)
    callback_log = Path(manifest.run_dir) / "callback.log"
    if timeout_s is not None and float(timeout_s) <= 0:
        raise ValueError("callback timeout must be positive or None")
    result_code, _output, _executable = _run_codex_prompt(
        manifest.codex_session_id,
        prompt,
        cwd=manifest.project_root,
        callback_log=callback_log,
        codex_executable=codex_executable,
        timeout_s=timeout_s,
        runner=runner,
    )
    return result_code


__all__ = [
    "CodexCallbackTimeoutError",
    "CodexCallbackTargetMismatchError",
    "CodexCallbackTargetUnavailableError",
    "CodexCallbackPreflightError",
    "build_resume_command",
    "callback_prompt",
    "run_codex_callback_preflight",
    "run_codex_callback",
]
