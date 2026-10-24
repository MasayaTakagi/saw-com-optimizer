"""Detached worker for supported non-agent optimizer runs."""
from __future__ import annotations

import os
import json
import subprocess
import traceback
from pathlib import Path
from ..io.checkpoints import complete_study_run, finalize_run_checkpoints
from ..io.legacy_lifecycle import legacy_process_disposition
from ..io.lifecycle import RunDisposition
from .run_manager import (
    load_manifest,
    load_status,
    record_optimizer_completion,
    transition,
    update_status_fields,
)


def _append_exception(run_dir: Path, exc: BaseException) -> None:
    with (Path(run_dir) / "stderr.log").open("a", encoding="utf-8") as stream:
        stream.write("\n[orchestration worker exception]\n")
        traceback.print_exception(exc, file=stream)


def durable_cell_failure(optimizer_run_dir: str | Path) -> dict | None:
    """Read the newest durable cell failure without opening optimizer payloads."""
    root = Path(optimizer_run_dir)
    failures = []
    if not root.is_dir():
        return None
    for path in root.rglob("cell_status.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if value.get("status") == "INCOMPLETE" and value.get("error_type"):
            failures.append((str(value.get("updated_at", "")), path, value))
    if not failures:
        return None
    _updated_at, path, value = max(failures, key=lambda item: (item[0], str(item[1])))
    result = dict(value)
    result["error_traceback_path"] = str(path)
    return result


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


def execute_run(run_dir: Path, *, resume: bool = False) -> dict:
    """Execute a non-agent run; retired transport-linked manifests fail closed."""
    run_dir = Path(run_dir).resolve()
    manifest = load_manifest(run_dir)
    if (manifest.uses_retired_agent_transport
            or manifest.study_type in {
                "hybrid_stage4b_topology_comparison", "hybrid_stage4c_confirmatory",
            }
            or "--stage4b-authorization-manifest" in manifest.command
            or "--stage4c-authorization-manifest" in manifest.command):
        raise RuntimeError("legacy Codex-linked and Stage 4B/4C worker execution is retired")
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
        message = str(exc)
        error = f"{type(exc).__name__}: {message}" if message else f"{type(exc).__name__}: (no message)"
        transition(
            run_dir, "FAILED", exit_code=None, error=error,
            error_type=type(exc).__name__, error_message=message, error_repr=repr(exc),
            error_traceback_path="stderr.log",
        )
        complete_study_run(
            Path(manifest.effective_optimizer_run_dir),
            disposition=RunDisposition.FAILED,
        )
        if manifest.schema_version >= 4:
            record_optimizer_completion(
                run_dir, disposition="FAILED", exit_code=None, error=str(exc),
            )
        exit_code = None
    else:
        optimizer_run_dir = Path(manifest.effective_optimizer_run_dir)
        cell_failure = durable_cell_failure(optimizer_run_dir) if exit_code != 0 else None
        if manifest.schema_version >= 4:
            disposition = RunDisposition.COMPLETED if exit_code == 0 else RunDisposition.FAILED
        else:
            disposition = legacy_process_disposition(optimizer_run_dir, return_code=exit_code)
        if exit_code == 0:
            failure_fields = {}
            error = None
        elif cell_failure is not None:
            error_type = str(cell_failure.get("error_type") or "OptimizerChildFailed")
            message = str(cell_failure.get("error_message") or "")
            error = f"{error_type}: {message}" if message else f"{error_type}: (no message)"
            failure_fields = {
                "error_type": error_type,
                "error_message": message,
                "error_repr": str(cell_failure.get("error_repr", "")),
                "error_traceback_path": cell_failure.get("error_traceback_path"),
                "failing_cell": cell_failure.get("failing_cell"),
                "last_durable_checkpoint_budget": cell_failure.get(
                    "last_durable_checkpoint_budget"),
            }
        else:
            error_type = "OptimizerChildExit"
            error = f"optimizer exited with code {exit_code}"
            failure_fields = {
                "error_type": error_type,
                "error_message": error,
                "error_repr": repr(error),
                "error_traceback_path": "stderr.log",
            }
        transition(
            run_dir,
            disposition.value,
            exit_code=exit_code,
            error=error,
            **failure_fields,
        )
        complete_study_run(optimizer_run_dir, disposition=disposition)
        if disposition is RunDisposition.COMPLETED:
            try:
                finalization = finalize_run_checkpoints(optimizer_run_dir)
            except Exception as exc:
                # Optimizer completion remains authoritative. Retain recovery
                # files and make lifecycle failure visible for later repair.
                update_status_fields(run_dir, checkpoint_finalization={
                    "status": "FAILED",
                    "error": f"{type(exc).__name__}: {exc}",
                })
            else:
                update_status_fields(run_dir, checkpoint_finalization=finalization)
        if manifest.schema_version >= 4:
            record_optimizer_completion(
                run_dir,
                disposition="COMPLETED" if disposition is RunDisposition.COMPLETED else "FAILED",
                exit_code=exit_code,
                error=error,
            )

    # Completion and checkpoint-finalization evidence is retained, but there is
    # no automatic queue handoff, callback, or session-resume dispatch.
    return load_status(run_dir)


__all__ = ["execute_run"]
