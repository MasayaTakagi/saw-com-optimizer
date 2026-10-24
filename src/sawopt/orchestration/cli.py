"""CLI for asynchronous production runs and human-readable recovery."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .models import RunManifest
from .process_runner import build_worker_command, launch_detached, pid_exists
from .run_manager import (
    create_run,
    format_status,
    load_manifest,
    load_status,
    mark_review_published,
    transition,
    update_status_fields,
    utc_now,
)
from .persistent_storage import validate_persistent_run_location
from .active_runs import register_active_run
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


def _write_resume_checkpoint(run_dir: Path, *, mode: str, resume_count: int) -> Path:
    path = Path(run_dir) / "resume_checkpoint.json"
    manifest = load_manifest(Path(run_dir))
    from .run_manager import atomic_write_json

    atomic_write_json(path, {
        "schema_version": 1,
        "run_id": manifest.run_id,
        "run_dir": str(Path(run_dir).resolve()),
        "mode": mode,
        "resume_count": int(resume_count),
        "updated_at": utc_now(),
    })
    return path


def _resume_launch(args: argparse.Namespace, root: Path) -> int:
    if not args.run_dir:
        raise ValueError("--resume requires --run-dir pointing to an existing run")
    run_dir = resolve_run_dir(args.run_dir, root)
    manifest = load_manifest(run_dir)
    if manifest.uses_retired_agent_transport or manifest.study_type in {
        "hybrid_stage4b_topology_comparison", "hybrid_stage4c_confirmatory",
    }:
        raise RuntimeError("legacy Codex-linked and Stage 4B/4C resume is retired")
    status = load_status(run_dir)
    current_count = int(status.get("resume_count", 0))
    state = status["state"]
    if state in {"STARTING", "RUNNING"}:
        worker_alive = pid_exists(status.get("worker_pid"))
        optimizer_alive = pid_exists(status.get("optimizer_pid"))
        if worker_alive or optimizer_alive:
            checkpoint = _write_resume_checkpoint(
                run_dir, mode="reattach", resume_count=current_count + 1,
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
    checkpoint = _write_resume_checkpoint(
        run_dir, mode="resume", resume_count=current_count + 1,
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
    continuation_mode = getattr(args, "continuation_mode", None)
    if continuation_mode == "queue":
        raise RuntimeError("legacy Codex queue continuation is retired")
    if continuation_mode != "disabled":
        raise ValueError("new legacy-orchestration launches require explicit --continuation-mode disabled")
    config = Path(args.config)
    if not config.is_absolute():
        config = (root / config).resolve()
    if not config.exists():
        raise FileNotFoundError(f"config does not exist: {config}")
    from ..io.config import load_experiment_config

    config_payload = load_experiment_config(config)
    configured_study = config_payload.get("study", {})
    study_type = str(configured_study.get("type", ""))
    if study_type in {
        "hybrid_stage4b_topology_comparison", "hybrid_stage4c_confirmatory",
    }:
        raise RuntimeError(f"legacy {study_type} production launch is retired")
    production_launch = any(
        configured_study.get(key) is True
        for key in ("user_authorized_production", "production_launch_authorized", "ranking_eligible")
    ) or bool(configured_study.get("ranking_eligibility") not in (None, "", "never", False))
    if getattr(args, "run_dir", None) and getattr(args, "run_root", None):
        raise ValueError("--run-dir and --run-root are mutually exclusive")
    run_id = _new_run_id()
    persistent_run_root = None
    storage_provenance = False
    if production_launch and not (getattr(args, "run_dir", None) or getattr(args, "run_root", None)):
        raise ValueError("authorized/ranking-eligible production requires an explicit external --run-root or --run-dir")
    if getattr(args, "run_root", None):
        requested_root = Path(args.run_root)
        if not requested_root.is_absolute():
            raise ValueError("production run root must be an absolute path")
        persistent_run_root = requested_root.resolve(strict=False)
        run_dir = persistent_run_root / run_id
        storage_provenance = True
    elif production_launch:
        requested_run_dir = Path(args.run_dir)
        if not requested_run_dir.is_absolute():
            raise ValueError("production run directory must be an absolute path")
        run_dir = requested_run_dir.resolve(strict=False)
        persistent_run_root = run_dir.parent
        storage_provenance = True
    else:
        run_dir = resolve_run_dir(args.run_dir, root) if args.run_dir else root / "runs" / run_id
    if storage_provenance:
        storage_validation = validate_persistent_run_location(run_dir, root)
        if not storage_validation.passed:
            raise ValueError(
                f"production run storage rejected: {storage_validation.classification}: "
                f"{storage_validation.reason}"
            )
    optimizer_run_dir = run_dir / "optimizer"
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"orchestration directory is not empty: {run_dir}")
    if optimizer_run_dir.exists() and any(optimizer_run_dir.iterdir()):
        raise FileExistsError(f"optimizer output directory is not empty: {optimizer_run_dir}")
    from ..reporting.github_review import load_review_spec, _canonical_json_sha256
    spec_id = getattr(args, "review_spec", None) or configured_study.get("review_spec_id")
    if not spec_id:
        if study_type.startswith("hybrid_stage4"):
            spec_id = "hybrid_production"
        elif study_type == "postrun_workflow_qualification":
            spec_id = "postrun_workflow_qualification"
    if not spec_id:
        raise ValueError("new launches must identify a frozen --review-spec")
    review_spec = load_review_spec(str(spec_id), root)
    review_stage = str(getattr(args, "review_stage", None) or configured_study.get("review_stage") or review_spec["stage"])
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", review_stage):
        raise ValueError("review stage must be a safe lowercase identifier")
    review_output_dir = f"reports/experiment_reviews/{review_stage}/{run_id}"

    source_branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=root, text=True,
        encoding="utf-8", errors="replace",
    ).strip()
    source_commit_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True,
        encoding="utf-8", errors="replace",
    ).strip()
    source_status = subprocess.check_output(
        ["git", "status", "--short"], cwd=root, text=True,
        encoding="utf-8", errors="replace",
    ).strip()
    if source_status:
        raise RuntimeError("new v4 runs require a clean committed source tree")
    command = _build_optimizer_command(
        config, optimizer_run_dir, workers=args.workers,
    )
    arms = (configured_study.get("comparison_arms") or configured_study.get("topologies")
            or configured_study.get("arms"))
    seeds = configured_study.get("seeds")
    if not arms or not seeds:
        raise ValueError("new v4 runs must declare comparison_arms/topologies and seeds")
    experiment_metadata = {
        "study_type": study_type,
        "comparison_arms": list(arms),
        "seeds": list(seeds),
        "expected_cell_count": int(configured_study.get("expected_cell_count", len(arms) * len(seeds))),
        "computation_fingerprint": configured_study.get("computation_fingerprint"),
        "protocol_fingerprint": configured_study.get("protocol_fingerprint"),
    }
    manifest = RunManifest(
        schema_version=4,
        run_id=run_id,
        experiment_name=args.experiment_name or config.stem,
        created_at=utc_now(),
        project_root=str(root),
        run_dir=str(run_dir),
        command=command,
        config_path=str(config),
        codex_session_id=None,
        codex_model=None,
        callback_enabled=False,
        review_after_completion=False,
        callback_timeout_minutes=None,
        optimizer_run_dir=str(optimizer_run_dir),
        callback_preflight=None,
        experiment_metadata=experiment_metadata,
        continuation_mode=continuation_mode,
        review_stage=review_stage,
        review_contract_version="1",
        review_output_dir=review_output_dir,
        review_spec_id=str(spec_id),
        review_spec_sha256=_canonical_json_sha256(review_spec),
        review_spec=review_spec,
        source_commit_sha=source_commit_sha,
        source_branch=source_branch,
        study_type=study_type,
        run_storage_policy="external_persistent_v1" if storage_provenance else None,
        persistent_run_root=str(persistent_run_root) if storage_provenance else None,
        repository_root_at_launch=str(root) if storage_provenance else None,
        source_worktree_at_launch=str(root) if storage_provenance else None,
    )
    if storage_provenance:
        # Final recheck plus exclusive directory reservation closes the gap
        # between validation and create_run for an explicitly reused --run-dir.
        storage_validation = validate_persistent_run_location(run_dir, root)
        if not storage_validation.passed:
            raise ValueError(
                f"production run storage changed before run creation: "
                f"{storage_validation.classification}: {storage_validation.reason}"
            )
        register_active_run(
            root, run_id=run_id, run_dir=run_dir, source_worktree=root,
            source_head=source_commit_sha,
            source_branch=source_branch or None,
        )
        run_dir.mkdir(exist_ok=False)
    create_run(manifest)
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
    print(f"Continuation mode: {continuation_mode}")
    return 0


def mark_published(args: argparse.Namespace) -> int:
    status = mark_review_published(
        resolve_run_dir(args.run_dir), review_path=args.review_path,
        branch=args.branch, commit=args.commit,
    )
    print(json.dumps({
        "state": status["state"],
        "review_evidence_state": status["review_evidence_state"],
        "review_output_dir": status["review_output_dir"],
        "review_publication_branch": status["review_publication_branch"],
        "review_publication_commit": status["review_publication_commit"],
        "review_published_at": status["review_published_at"],
    }, ensure_ascii=False, indent=2))
    return 0


def recover(args: argparse.Namespace) -> int:
    run_dir = resolve_run_dir(args.run_id)
    manifest = load_manifest(run_dir)
    if manifest.uses_retired_agent_transport or manifest.study_type in {
        "hybrid_stage4b_topology_comparison", "hybrid_stage4c_confirmatory",
    }:
        raise RuntimeError("legacy Codex-linked and Stage 4B/4C recovery is retired")
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
    launch_parser.add_argument(
        "--run-root",
        help="absolute persistent root outside all Git worktrees; run ID becomes a child directory",
    )
    launch_parser.add_argument("--experiment-name")
    launch_parser.add_argument("--workers", type=int)
    launch_parser.add_argument(
        "--resume",
        action="store_true",
        help="reattach to an active run or restart an orphaned run from checkpoints",
    )
    launch_parser.add_argument("--continuation-mode", choices=("disabled",), required=True)
    launch_parser.add_argument("--review-spec", help="frozen review artifact spec identifier")
    launch_parser.add_argument("--review-stage", help="canonical review stage identifier")
    launch_parser.set_defaults(handler=launch)

    status_parser = subparsers.add_parser("status", help="display recorded run status")
    status_parser.add_argument("run_id")
    status_parser.set_defaults(handler=lambda args: print(format_status(resolve_run_dir(args.run_id))) or 0)

    recover_parser = subparsers.add_parser("recover", help="recover non-agent process state")
    recover_parser.add_argument("run_id")
    recover_parser.set_defaults(handler=recover)

    published_parser = subparsers.add_parser("mark-review-published", help="record pushed review evidence")
    published_parser.add_argument("--run-dir", required=True)
    published_parser.add_argument("--review-path", required=True)
    published_parser.add_argument("--branch", required=True)
    published_parser.add_argument("--commit", required=True)
    published_parser.set_defaults(handler=mark_published)

    worker_parser = subparsers.add_parser("worker", help="internal detached worker")
    worker_parser.add_argument("--run-dir", required=True)
    worker_parser.add_argument("--resume", action="store_true")
    worker_parser.set_defaults(handler=lambda args: (
        execute_run(Path(args.run_dir), resume=args.resume), 0
    )[1])
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    retired_commands = {"review", "confirm-queue"}
    retired_options = {
        "--thread-id", "--queue-timeout-seconds", "--codex-executable",
        "--session-id", "--session-file", "--no-callback",
        "--authorize-stage4b-production", "--authorize-stage4c-production",
    }
    if arguments and arguments[0] in retired_commands:
        raise RuntimeError(f"legacy {arguments[0]} command is retired")
    if any(option in retired_options for option in arguments):
        raise RuntimeError("legacy Codex/session/Stage 4B/4C orchestration options are retired")
    if (arguments[:1] == ["launch"] and "--continuation-mode" in arguments
            and arguments[arguments.index("--continuation-mode") + 1:][:1] == ["queue"]):
        raise RuntimeError("legacy Codex queue continuation is retired")
    args = build_parser().parse_args(arguments)
    return int(args.handler(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"orchestration error: {exc}", file=sys.stderr)
        raise SystemExit(1)
