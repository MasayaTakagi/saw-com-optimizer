"""CLI for asynchronous production runs and human-readable recovery."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .codex_callback import run_codex_callback, run_codex_callback_preflight
from .models import RunManifest
from .process_runner import build_worker_command, launch_detached, pid_exists
from .run_manager import (
    SessionValidationError,
    callback_lock_path,
    create_run,
    atomic_write_json,
    exclusive_lock,
    finish_callback,
    format_status,
    load_manifest,
    load_status,
    prepare_callback,
    lock_owner_pid,
    reclaim_stale_lock,
    resolve_session,
    transition,
    update_status_fields,
    utc_now,
)
from .worker import execute_run


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_run_dir(value: str, root: Path | None = None) -> Path:
    root = (root or project_root()).resolve()
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    if len(candidate.parts) == 1:
        return (root / "runs" / candidate).resolve()
    return (root / candidate).resolve()


def _build_optimizer_command(
    config: Path, optimizer_run_dir: Path, *, workers: int | None,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "sawopt",
        "run-study",
        "--config",
        str(config),
        "--run",
        str(optimizer_run_dir),
    ]
    if workers is not None:
        command.extend(["--workers", str(workers)])
    return command


def _write_session_checkpoint(run_dir: Path, *, mode: str, resume_count: int,
                               session_id: str | None = None) -> Path:
    path = Path(run_dir) / "session_checkpoint.json"
    atomic_write_json(path, {
        "schema_version": 1,
        "run_id": load_manifest(Path(run_dir)).run_id,
        "run_dir": str(Path(run_dir).resolve()),
        "mode": mode,
        "resume_count": int(resume_count),
        "session_id": session_id,
        "updated_at": utc_now(),
    })
    return path


def _resume_launch(args: argparse.Namespace, root: Path) -> int:
    if not args.run_dir:
        raise ValueError("--resume requires --run-dir pointing to an existing run")
    run_dir = resolve_run_dir(args.run_dir, root)
    manifest = load_manifest(run_dir)
    status = load_status(run_dir)
    current_count = int(status.get("resume_count", 0))
    state = status["state"]
    if state in {"STARTING", "RUNNING"}:
        worker_alive = pid_exists(status.get("worker_pid"))
        optimizer_alive = pid_exists(status.get("optimizer_pid"))
        if worker_alive or optimizer_alive:
            checkpoint = _write_session_checkpoint(
                run_dir, mode="reattach", resume_count=current_count + 1,
                session_id=getattr(args, "session_id", None),
            )
            update_status_fields(
                run_dir,
                resume_count=current_count + 1,
                last_attached_at=utc_now(),
                session_checkpoint_path=str(checkpoint),
            )
            print(f"Run is still active; reattached to {run_dir}")
            print(f"run_id: {manifest.run_id}")
            print(f"worker_alive: {worker_alive}")
            print(f"optimizer_alive: {optimizer_alive}")
            return 0
        transition(run_dir, "ORPHANED", error="resume requested after detached process exit")
        state = "ORPHANED"
    if state not in {"FAILED", "ORPHANED", "ORPHANED_CHILD"}:
        raise ValueError(f"run cannot be resumed from state {state}")
    checkpoint = _write_session_checkpoint(
        run_dir, mode="resume", resume_count=current_count + 1,
        session_id=getattr(args, "session_id", None),
    )
    transition(
        run_dir, "STARTING", resume_requested=True,
        resume_count=current_count + 1,
        last_attached_at=utc_now(),
        session_checkpoint_path=str(checkpoint),
        error=None,
    )
    worker_pid = launch_detached(
        run_dir, project_root=root,
        command=build_worker_command(run_dir, resume=True),
    )
    update_status_fields(run_dir, worker_pid=worker_pid)
    print("Production run resumed asynchronously.")
    print(f"run_id: {manifest.run_id}")
    print(f"pid: {worker_pid}")
    print(f"run_dir: {run_dir}")
    return 0


def launch(args: argparse.Namespace) -> int:
    root = project_root()
    if getattr(args, "resume", False):
        return _resume_launch(args, root)
    if args.no_callback and getattr(args, "session_id", None):
        raise ValueError("--session-id cannot be combined with --no-callback")
    config = Path(args.config)
    if not config.is_absolute():
        config = (root / config).resolve()
    if not config.exists():
        raise FileNotFoundError(f"config does not exist: {config}")
    run_id = _new_run_id()
    run_dir = resolve_run_dir(args.run_dir, root) if args.run_dir else root / "runs" / run_id
    optimizer_run_dir = run_dir / "optimizer"
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"orchestration directory is not empty: {run_dir}")
    if optimizer_run_dir.exists() and any(optimizer_run_dir.iterdir()):
        raise FileExistsError(f"optimizer output directory is not empty: {optimizer_run_dir}")
    callback_enabled = not args.no_callback
    session = None
    callback_preflight = None
    if callback_enabled:
        session_path = Path(args.session_file) if args.session_file else root / ".codex" / "runtime" / "current_session.json"
        if not session_path.is_absolute():
            session_path = (root / session_path).resolve()
        session = resolve_session(
            explicit_session_id=getattr(args, "session_id", None),
            session_path=session_path,
            project_root=root,
            max_age_s=float(args.session_max_age_hours) * 3600,
        )
        callback_preflight = run_codex_callback_preflight(
            str(session["session_id"]),
            project_root=str(root),
        )
    command = _build_optimizer_command(
        config,
        optimizer_run_dir,
        workers=args.workers,
    )
    manifest = RunManifest(
        schema_version=2,
        run_id=run_id,
        experiment_name=args.experiment_name or config.stem,
        created_at=utc_now(),
        project_root=str(root),
        run_dir=str(run_dir),
        command=command,
        config_path=str(config),
        codex_session_id=None if session is None else str(session["session_id"]),
        codex_model=None if session is None else session.get("model"),
        callback_enabled=callback_enabled,
        review_after_completion=callback_enabled,
        callback_timeout_minutes=(
            None if args.callback_timeout_minutes is None
            else float(args.callback_timeout_minutes)
        ),
        codex_session_source=None if session is None else str(session.get("source", "unknown")),
        optimizer_run_dir=str(optimizer_run_dir),
        callback_preflight=callback_preflight,
    )
    create_run(manifest)
    checkpoint = _write_session_checkpoint(
        run_dir, mode="launch", resume_count=0,
        session_id=None if session is None else str(session["session_id"]),
    )
    update_status_fields(run_dir, session_checkpoint_path=str(checkpoint))
    transition(run_dir, "STARTING")
    try:
        worker_pid = launch_detached(run_dir, project_root=root)
        update_status_fields(run_dir, worker_pid=worker_pid)
    except BaseException as exc:
        transition(run_dir, "FAILED", error=f"worker launch failed: {exc}")
        raise
    print("Production run started asynchronously.")
    print(f"run_id: {run_id}")
    print(f"pid: {worker_pid}")
    print(f"run_dir: {Path(run_dir).resolve()}")
    print(f"Codex callback: {'enabled' if callback_enabled else 'disabled'}")
    return 0


def review(args: argparse.Namespace) -> int:
    run_dir = resolve_run_dir(args.run_id)
    manifest = load_manifest(run_dir)
    status = load_status(run_dir)
    if not manifest.codex_session_id:
        raise SessionValidationError("run manifest has no captured Codex session ID")
    if status["state"] in {"RUNNING", "STARTING", "CREATED"}:
        raise ValueError(f"run is not ready for review: {status['state']}")
    lock_path = callback_lock_path(run_dir)
    with exclusive_lock(lock_path):
        if not prepare_callback(run_dir, automatic=False):
            print("Callback already completed; nothing to do.")
            return 0
        current = load_status(run_dir)
        failed = current.get("optimizer_state") == "FAILED"
        try:
            code = run_codex_callback(
                manifest,
                exit_code=current.get("exit_code"),
                optimizer_failed=failed,
                codex_executable=args.codex_executable,
                timeout_s=(
                    None if manifest.callback_timeout_minutes is None
                    else manifest.callback_timeout_minutes * 60.0
                ),
            )
        except BaseException as exc:
            finish_callback(run_dir, success=False, exit_code=None, error=str(exc))
            raise
        finish_callback(
            run_dir,
            success=code == 0,
            exit_code=code,
            error=None if code == 0 else f"callback exited with code {code}",
        )
        print(f"callback: {'reviewed' if code == 0 else 'failed'}")
        return 0 if code == 0 else code


def recover(args: argparse.Namespace) -> int:
    run_dir = resolve_run_dir(args.run_id)
    status = load_status(run_dir)
    if status["state"] in {"STARTING", "RUNNING"}:
        pid = status.get("worker_pid")
        optimizer_pid = status.get("optimizer_pid")
        worker_alive = pid_exists(pid)
        optimizer_alive = pid_exists(optimizer_pid)
        if not worker_alive and optimizer_alive:
            transition(
                run_dir,
                "ORPHANED_CHILD",
                error=(
                    f"worker PID {pid} is no longer running while optimizer PID "
                    f"{optimizer_pid} is still running; automatic rerun is forbidden"
                ),
            )
            print(f"run marked ORPHANED_CHILD: {run_dir}")
            return 0
        if not worker_alive:
            transition(run_dir, "ORPHANED", error=f"worker PID {pid} is no longer running")
            print(f"run marked ORPHANED: {run_dir}")
            return 0
    if status["state"] == "CALLBACK_RUNNING":
        lock_path = callback_lock_path(run_dir)
        owner_pid = lock_owner_pid(lock_path)
        if not pid_exists(owner_pid):
            transition(run_dir, "CALLBACK_FAILED", error="callback owner process is no longer running")
            reclaim_stale_lock(lock_path, stale_after_s=0.0)
            print(f"callback marked CALLBACK_FAILED: {run_dir}")
            return 0
    if status["state"] == "CALLBACK_PENDING":
        lock_path = callback_lock_path(run_dir)
        if lock_path.exists():
            owner_pid = lock_owner_pid(lock_path)
            if not pid_exists(owner_pid):
                reclaim_stale_lock(lock_path, stale_after_s=0.0)
    print(format_status(run_dir))
    return 0


def _new_run_id() -> str:
    import secrets
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(3)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Asynchronous SAW optimizer orchestration")
    subparsers = parser.add_subparsers(dest="command", required=True)

    launch_parser = subparsers.add_parser("launch", help="start a detached optimizer run")
    launch_parser.add_argument("--config", required=True)
    launch_parser.add_argument("--run-dir")
    launch_parser.add_argument("--experiment-name")
    launch_parser.add_argument("--workers", type=int)
    launch_parser.add_argument(
        "--resume",
        action="store_true",
        help="reattach to an active run or restart an orphaned run from checkpoints",
    )
    launch_parser.add_argument("--session-id", help="explicit Codex callback session ID")
    launch_parser.add_argument("--no-callback", action="store_true")
    launch_parser.add_argument("--session-file")
    launch_parser.add_argument("--session-max-age-hours", type=float, default=24.0)
    launch_parser.add_argument("--callback-timeout-minutes", type=float, default=30.0)
    launch_parser.set_defaults(handler=launch)

    for name in ("status", "review", "recover"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("run_id")
        if name == "status":
            subparser.set_defaults(handler=lambda args: print(format_status(resolve_run_dir(args.run_id))) or 0)
        else:
            subparser.set_defaults(handler=review if name == "review" else recover)
    subparsers.choices["review"].add_argument("--codex-executable")

    worker_parser = subparsers.add_parser("worker", help="internal detached worker")
    worker_parser.add_argument("--run-dir", required=True)
    worker_parser.add_argument("--resume", action="store_true")
    worker_parser.set_defaults(handler=lambda args: (
        execute_run(Path(args.run_dir), resume=args.resume), 0
    )[1])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"orchestration error: {exc}", file=sys.stderr)
        raise SystemExit(1)
