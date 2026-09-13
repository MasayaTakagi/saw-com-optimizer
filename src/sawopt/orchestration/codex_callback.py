"""Explicit-ID Codex review callback for completed asynchronous runs."""
from __future__ import annotations

import shutil
import subprocess
import json
import os
from pathlib import Path
from typing import Callable

from .models import RunManifest


class CodexCallbackTimeoutError(TimeoutError):
    """Raised when a Codex callback exceeds its finite execution timeout."""


class CodexCallbackTargetMismatchError(RuntimeError):
    """Raised when structured Codex output names a different session/thread."""


COMPLETED_PROMPT = """The production optimization run has completed.

run_id: {run_id}
run_dir: {run_dir}
status: COMPLETED
exit_code: 0

Review this run now.

Required actions:
1. Read run_manifest.json and status.json.
2. Inspect the generated summary/results/logs.
3. If result.json exists, report its run_id and result value explicitly.
4. Validate that the run completed correctly.
5. Compare the result with the experiment objective and previous relevant runs.
6. Identify convergence, stability, seed dependence, and any suspicious behavior.
7. Recommend the next experiment or stopping criterion.
8. Do NOT automatically launch another production optimization run.
"""

FAILED_PROMPT = """The production optimization run failed.

run_id: {run_id}
run_dir: {run_dir}
status: FAILED
exit_code: {exit_code}

Investigate the failure now.

Required actions:
1. Read run_manifest.json and status.json.
2. Inspect stdout.log and stderr.log.
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


def run_codex_callback(manifest: RunManifest, *, exit_code: int | None,
                       optimizer_failed: bool,
                       codex_executable: str | None = None,
                       timeout_s: float | None = 1800.0,
                       runner: Callable[..., object] = subprocess.run) -> int:
    """Resume the exact captured session and write all callback output to a log."""
    if not manifest.codex_session_id:
        raise ValueError("callback is enabled but run manifest has no Codex session ID")
    executable = codex_executable or shutil.which("codex") or "codex"
    prompt = callback_prompt(manifest, exit_code=exit_code, optimizer_failed=optimizer_failed)
    command = build_resume_command(
        manifest.codex_session_id,
        prompt,
        codex_executable=executable,
        structured_output=True,
    )
    callback_log = Path(manifest.run_dir) / "callback.log"
    if timeout_s is not None and float(timeout_s) <= 0:
        raise ValueError("callback timeout must be positive or None")
    with callback_log.open("a", encoding="utf-8") as stream:
        stream.write(f"$ {executable} exec resume {manifest.codex_session_id} <review-prompt>\n")
        try:
            callback_env = dict(os.environ)
            # Detached Windows workers may inherit USERPROFILE without HOME.
            # Codex CLI uses HOME to resolve its global state/session store;
            # fill only the missing compatibility variable and preserve any
            # explicitly configured environment.
            if not callback_env.get("HOME") and callback_env.get("USERPROFILE"):
                callback_env["HOME"] = callback_env["USERPROFILE"]
            if not callback_env.get("CODEX_HOME") and callback_env.get("USERPROFILE"):
                callback_env["CODEX_HOME"] = str(
                    Path(callback_env["USERPROFILE"]) / ".codex"
                )
            result = runner(
                command,
                cwd=manifest.project_root,
                env=callback_env,
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
        output = getattr(result, "stdout", "") or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        stream.write(output)
        observed = _observed_target_ids(output)
        target = manifest.codex_session_id
        all_observed = observed["session_id"] | observed["thread_id"]
        if all_observed and target not in all_observed:
            stream.write(
                "callback target validation: mismatch; "
                f"requested={target}; observed={sorted(all_observed)}\n"
            )
            raise CodexCallbackTargetMismatchError(
                f"Codex callback resumed a different session/thread: "
                f"requested={target}; observed={sorted(all_observed)}"
            )
        if all_observed:
            stream.write(f"callback target validation: matched {target}\n")
        else:
            stream.write(
                "callback target validation: unavailable; "
                "Codex emitted no session_id/thread_id JSON event\n"
            )
    return int(getattr(result, "returncode", 0))


__all__ = [
    "CodexCallbackTimeoutError",
    "CodexCallbackTargetMismatchError",
    "build_resume_command",
    "callback_prompt",
    "run_codex_callback",
]
