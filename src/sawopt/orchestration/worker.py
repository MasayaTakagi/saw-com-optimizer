"""Detached worker: run an existing optimizer entry point, then callback."""
from __future__ import annotations

import os
import subprocess
import traceback
from pathlib import Path
from typing import Callable

from .codex_callback import run_codex_callback
from .run_manager import (
    callback_lock_path,
    exclusive_lock,
    finish_callback,
    load_manifest,
    load_status,
    prepare_callback,
    transition,
    update_status_fields,
)


def _append_exception(run_dir: Path, exc: BaseException) -> None:
    with (Path(run_dir) / "stderr.log").open("a", encoding="utf-8") as stream:
        stream.write("\n[orchestration worker exception]\n")
        traceback.print_exception(exc, file=stream)


def _run_optimizer(manifest, run_dir: Path, *, resume: bool = False) -> int:
    """Run the configured production entry point as a subprocess."""
    command = list(manifest.command)
    if resume and "--resume" not in command:
        command.append("--resume")
    with (run_dir / "stdout.log").open("a", encoding="utf-8") as stdout, \
            (run_dir / "stderr.log").open("a", encoding="utf-8") as stderr:
        kwargs = {
            "cwd": manifest.project_root,
            "env": dict(os.environ, PYTHONUNBUFFERED="1"),
            "stdin": subprocess.DEVNULL,
            "stdout": stdout,
            "stderr": stderr,
        }
        # The detached orchestration worker has no interactive console, but a
        # child Python process launched without this flag can still create a
        # transient console window on Windows.  Keep all long-running worker
        # processes headless while retaining stdout/stderr log capture.
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        process = subprocess.Popen(command, **kwargs)
        update_status_fields(
            run_dir,
            optimizer_pid=int(process.pid),
            optimizer_state="RUNNING",
        )
        return int(process.wait())


def execute_run(run_dir: Path, *, callback_runner: Callable[..., int] | None = None,
                codex_executable: str | None = None, resume: bool = False) -> dict:
    """Execute one durable run and return its final status dictionary."""
    run_dir = Path(run_dir).resolve()
    manifest = load_manifest(run_dir)
    status = load_status(run_dir)
    if status["state"] == "CREATED":
        transition(run_dir, "STARTING")
        transition(run_dir, "RUNNING", worker_pid=os.getpid())
    elif status["state"] == "STARTING":
        transition(run_dir, "RUNNING", worker_pid=os.getpid())
    elif status["state"] != "RUNNING":
        raise ValueError(f"worker cannot start from state {status['state']}")

    try:
        exit_code = _run_optimizer(manifest, run_dir, resume=resume)
    except BaseException as exc:
        _append_exception(run_dir, exc)
        transition(run_dir, "FAILED", exit_code=None, error=str(exc))
        exit_code = None
    else:
        review_waiting = bool(
            exit_code == 0
            and any(
                (run_dir / marker).is_file()
                for marker in (
                "PHASE_C_SUPPLEMENT_COMPLETE_WAITING_FOR_REVIEW.txt",
                "PHASE_C_FINAL_CONFIRMATION_COMPLETE_WAITING_FOR_REVIEW.txt",
                "STAGE3_6_GATE2B_A_COMPLETE_WAITING_FOR_REVIEW.txt",
                )
            )
        )
        transition(
            run_dir,
            "REVIEW_WAITING" if review_waiting else ("COMPLETED" if exit_code == 0 else "FAILED"),
            exit_code=exit_code,
            error=None if exit_code == 0 else f"optimizer exited with code {exit_code}",
        )

    if manifest.callback_enabled and manifest.review_after_completion:
        claimed = False
        lock_path = Path(callback_lock_path(run_dir))
        try:
            with exclusive_lock(lock_path):
                claimed = prepare_callback(run_dir, automatic=True)
                if claimed:
                    failed = exit_code != 0 or load_status(run_dir).get("optimizer_state") == "FAILED"
                    try:
                        if callback_runner is None:
                            callback_exit = run_codex_callback(
                                manifest,
                                exit_code=exit_code,
                                optimizer_failed=failed,
                                codex_executable=codex_executable,
                                timeout_s=(
                                    None if manifest.callback_timeout_minutes is None
                                    else manifest.callback_timeout_minutes * 60.0
                                ),
                            )
                        else:
                            callback_exit = int(callback_runner(
                                manifest,
                                exit_code=exit_code,
                                optimizer_failed=failed,
                            ))
                    except BaseException as exc:
                        _append_exception(run_dir, exc)
                        finish_callback(run_dir, success=False, exit_code=None, error=str(exc))
                    else:
                        finish_callback(
                            run_dir,
                            success=callback_exit == 0,
                            exit_code=callback_exit,
                            error=None if callback_exit == 0 else f"callback exited with code {callback_exit}",
                        )
        except (FileExistsError, TimeoutError):
            # Another worker/manual review owns the callback.  The durable
            # status remains authoritative and no duplicate resume is issued.
            pass
    return load_status(run_dir)


__all__ = ["execute_run"]
