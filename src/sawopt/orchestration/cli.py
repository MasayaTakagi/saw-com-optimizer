"""CLI for asynchronous production runs and human-readable recovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .codex_callback import run_codex_callback
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
    confirm_queue_delivery,
    mark_review_published,
    lock_owner_pid,
    reclaim_stale_lock,
    resolve_session,
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
    stage4b_authorization_manifest: Path | None = None,
    stage4c_authorization_manifest: Path | None = None,
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
    if stage4b_authorization_manifest is not None:
        command.extend(["--stage4b-authorization-manifest", str(stage4b_authorization_manifest)])
    if stage4c_authorization_manifest is not None:
        command.extend(["--stage4c-authorization-manifest", str(stage4c_authorization_manifest)])
    return command


def _claim_stage4b_authorization(root: Path, metadata: dict) -> tuple[str, Path]:
    """Persist an exclusive one-shot claim for one source/protocol fingerprint."""
    from ..studies.hybrid_stage4b import authorization_claim_id

    claim_id = authorization_claim_id(metadata)
    claim_directory = root / "runs" / ".stage4b_authorization_claims"
    claim_path = claim_directory / f"{claim_id}.json"
    lock_path = claim_directory / ".claim.lock"
    claim_directory.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(lock_path):
        if claim_path.exists():
            raise RuntimeError("Stage 4B one-shot production authorization has already been claimed")
        claim = {
            "schema_version": 1,
            "claim_id": claim_id,
            "authorization_scope": metadata["authorization_scope"],
            "computation_fingerprint": metadata["computation_fingerprint"],
            "source_commit_sha": metadata["source_commit_sha"],
            "run_id": metadata["run_id"],
            "claimed_at_utc": utc_now(),
        }
        with claim_path.open("x", encoding="utf-8") as stream:
            json.dump(claim, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    return claim_id, claim_path


def _claim_stage4c_authorization(root: Path, metadata: dict) -> tuple[str, Path]:
    """Persist an exclusive one-shot claim for the frozen Stage 4C protocol."""
    identity = {
        "authorization_scope": "stage4c-confirmatory-production-v1",
        "computation_fingerprint": metadata["computation_fingerprint"],
        "source_commit_sha": metadata["source_commit_sha"],
        "run_id": metadata["run_id"],
    }
    claim_id = hashlib.sha256(json.dumps(
        identity, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    claim_directory = root / "runs" / ".stage4c_authorization_claims"
    claim_path = claim_directory / f"{claim_id}.json"
    claim_directory.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(claim_directory / ".claim.lock"):
        if claim_path.exists():
            raise RuntimeError("Stage 4C one-shot production authorization has already been claimed")
        claim = {
            "schema_version": 1,
            "claim_id": claim_id,
            **identity,
            "claimed_at_utc": utc_now(),
        }
        with claim_path.open("x", encoding="utf-8") as stream:
            json.dump(claim, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    return claim_id, claim_path


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
    if args.no_callback and (getattr(args, "session_id", None) or getattr(args, "session_file", None)):
        raise ValueError("--session-id/--session-file cannot be combined with --no-callback")
    requested_mode = getattr(args, "continuation_mode", None)
    if args.no_callback:
        if requested_mode not in (None, "disabled"):
            raise ValueError("--no-callback conflicts with --continuation-mode")
        continuation_mode = "disabled"
    else:
        continuation_mode = requested_mode or "queue"
    if continuation_mode == "legacy_resume":
        raise ValueError("legacy_resume is historical read/recovery only; new launches support queue or disabled")
    if continuation_mode not in {"queue", "disabled"}:
        raise ValueError(f"unsupported new launch continuation mode: {continuation_mode}")
    if continuation_mode == "disabled" and (getattr(args, "session_id", None) or getattr(args, "session_file", None)):
        raise ValueError("session identity cannot be used when continuation is disabled")
    config = Path(args.config)
    if not config.is_absolute():
        config = (root / config).resolve()
    if not config.exists():
        raise FileNotFoundError(f"config does not exist: {config}")
    from ..io.config import load_experiment_config

    config_payload = load_experiment_config(config)
    configured_study = config_payload.get("study", {})
    stage4b_launch = configured_study.get("type") == "hybrid_stage4b_topology_comparison"
    stage4c_launch = configured_study.get("type") == "hybrid_stage4c_confirmatory"
    if stage4b_launch and not getattr(args, "authorize_stage4b_production", False):
        raise PermissionError("Stage 4B production requires --authorize-stage4b-production")
    if not stage4b_launch and getattr(args, "authorize_stage4b_production", False):
        raise ValueError("--authorize-stage4b-production is valid only for Stage 4B")
    if stage4c_launch and not getattr(args, "authorize_stage4c_production", False):
        raise PermissionError("Stage 4C production requires --authorize-stage4c-production")
    if not stage4c_launch and getattr(args, "authorize_stage4c_production", False):
        raise ValueError("--authorize-stage4c-production is valid only for Stage 4C")
    production_launch = stage4b_launch or stage4c_launch or any(
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
    if stage4c_launch:
        required_production_root = Path(
            config_payload.get("storage_contract", {}).get("production_root", "")
        ).resolve(strict=False)
        try:
            run_dir.resolve(strict=False).relative_to(required_production_root)
        except ValueError as exc:
            raise ValueError(
                "Stage 4C production destination must be below the frozen external production root"
            ) from exc
    if storage_provenance:
        storage_validation = validate_persistent_run_location(run_dir, root)
        if not storage_validation.passed:
            raise ValueError(
                f"production run storage rejected: {storage_validation.classification}: "
                f"{storage_validation.reason}"
            )
    stage4b_context = None
    stage4b_source = None
    stage4c_context = None
    stage4c_source = None
    if stage4b_launch:
        if continuation_mode != "queue":
            raise ValueError("Stage 4B production requires exact-thread queue continuation")
        from ..studies.hybrid_stage4b import load_stage4b_context

        stage4b_context = load_stage4b_context(config)
        stage4b_source = {
            "branch": subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=root, text=True,
                encoding="utf-8", errors="replace",
            ).strip(),
            "head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True,
                encoding="utf-8", errors="replace",
            ).strip(),
            "status_short": subprocess.check_output(
                ["git", "status", "--short"], cwd=root, text=True,
                encoding="utf-8", errors="replace",
            ).strip(),
        }
        if stage4b_source["branch"] != "codex/stage4b-hybrid-production-20261003":
            raise RuntimeError("Stage 4B production must launch from the named Stage 4B branch")
        if stage4b_source["status_short"]:
            raise RuntimeError("Stage 4B production requires a clean committed source tree")
    if stage4c_launch:
        if continuation_mode != "queue":
            raise ValueError("Stage 4C production requires exact-thread queue continuation")
        from ..studies.hybrid_stage4c import load_stage4c_context

        stage4c_context = load_stage4c_context(config)
        stage4c_source = {
            "branch": subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=root, text=True,
                encoding="utf-8", errors="replace",
            ).strip(),
            "head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True,
                encoding="utf-8", errors="replace",
            ).strip(),
            "status_short": subprocess.check_output(
                ["git", "status", "--short"], cwd=root, text=True,
                encoding="utf-8", errors="replace",
            ).strip(),
        }
        if stage4c_source["status_short"]:
            raise RuntimeError("Stage 4C production requires a clean committed source tree")
    optimizer_run_dir = run_dir / "optimizer"
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"orchestration directory is not empty: {run_dir}")
    if optimizer_run_dir.exists() and any(optimizer_run_dir.iterdir()):
        raise FileExistsError(f"optimizer output directory is not empty: {optimizer_run_dir}")
    callback_enabled = False
    queue_preflight = None
    original_thread_id = None
    queue_timeout_seconds = float(getattr(args, "queue_timeout_seconds", 120.0))
    if continuation_mode == "queue":
        if getattr(args, "session_id", None) or getattr(args, "session_file", None):
            raise ValueError("queue routing rejects --session-id/--session-file; use --thread-id")
        from .codex_queue import current_codex_thread_id, run_codex_queue_preflight, validate_thread_id
        runtime_thread_id = current_codex_thread_id()
        requested_thread_id = getattr(args, "thread_id", None) or runtime_thread_id
        if validate_thread_id(requested_thread_id) != runtime_thread_id:
            raise ValueError("--thread-id must exactly match current runtime CODEX_THREAD_ID")
        original_thread_id = runtime_thread_id
        queue_preflight = run_codex_queue_preflight(
            original_thread_id, project_root=str(root),
            codex_executable=getattr(args, "codex_executable", None),
        )
        original_thread_id = queue_preflight["thread_id"]

    from ..reporting.github_review import load_review_spec, _canonical_json_sha256
    study_type = str(configured_study.get("type", ""))
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
        config,
        optimizer_run_dir,
        workers=args.workers,
        stage4b_authorization_manifest=(run_dir / "run_manifest.json") if stage4b_launch else None,
        stage4c_authorization_manifest=(run_dir / "run_manifest.json") if stage4c_launch else None,
    )
    experiment_metadata = None
    if stage4b_launch:
        from ..studies.hybrid_stage4b import build_authorization_metadata

        experiment_metadata = build_authorization_metadata(
            stage4b_context,
            source_commit_sha=stage4b_source["head"],
            run_id=run_id,
            authorized_at=utc_now(),
        )
        experiment_metadata.update({
            "orchestration_run_dir": str(run_dir.resolve()),
            "optimizer_run_dir": str(optimizer_run_dir.resolve()),
        })
    elif stage4c_launch:
        from ..studies.hybrid_stage4c import build_authorization_metadata

        experiment_metadata = build_authorization_metadata(
            stage4c_context,
            source_commit_sha=stage4c_source["head"],
            run_id=run_id,
            authorized_at=utc_now(),
        )
        experiment_metadata.update({
            "orchestration_run_dir": str(run_dir.resolve()),
            "optimizer_run_dir": str(optimizer_run_dir.resolve()),
        })
    else:
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
        review_after_completion=continuation_mode == "queue",
        callback_timeout_minutes=None,
        optimizer_run_dir=str(optimizer_run_dir),
        callback_preflight=None,
        experiment_metadata=experiment_metadata,
        continuation_mode=continuation_mode,
        original_thread_id=original_thread_id,
        next_expected_step="publish_review_evidence" if continuation_mode == "queue" else None,
        delivery_sentinel=secrets.token_hex(16) if continuation_mode == "queue" else None,
        queue_preflight=queue_preflight,
        queue_timeout_seconds=queue_timeout_seconds if continuation_mode == "queue" else None,
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
    if stage4b_launch:
        claim_id, claim_path = _claim_stage4b_authorization(root, experiment_metadata)
        experiment_metadata["authorization_claim_id"] = claim_id
        experiment_metadata["authorization_claim_path"] = str(claim_path.resolve())
        # The manifest is frozen, so build the final object after the exclusive
        # claim is persisted and include its durable identity.
        manifest = RunManifest(
            **{**manifest.to_dict(), "experiment_metadata": experiment_metadata}
        )
    elif stage4c_launch:
        claim_id, claim_path = _claim_stage4c_authorization(root, experiment_metadata)
        experiment_metadata["authorization_claim_id"] = claim_id
        experiment_metadata["authorization_claim_path"] = str(claim_path.resolve())
        manifest = RunManifest(
            **{**manifest.to_dict(), "experiment_metadata": experiment_metadata}
        )
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
    print(f"Original thread: {original_thread_id or 'none'}")
    return 0


def review(args: argparse.Namespace) -> int:
    run_dir = resolve_run_dir(args.run_id)
    manifest = load_manifest(run_dir)
    status = load_status(run_dir)
    if manifest.schema_version >= 4:
        raise ValueError("schema-v4 runs use queue publication; legacy callback review is disabled")
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


def confirm_queue(args: argparse.Namespace) -> int:
    delivery = confirm_queue_delivery(
        resolve_run_dir(args.run_dir), run_id=args.run_id,
        delivery_id=args.delivery_id, delivery_sentinel=args.delivery_sentinel,
    )
    print(json.dumps({
        "state": delivery["state"], "run_id": delivery["run_id"],
        "delivery_id": delivery["delivery_id"],
        "receiver_thread_id": delivery["receiver_thread_id"],
        "receiver_confirmed_at": delivery["receiver_confirmed_at"],
    }, ensure_ascii=False, indent=2))
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
    status = load_status(run_dir)
    if (manifest.schema_version == 4 and manifest.continuation_mode == "queue"
            and status.get("optimizer_state") in {"COMPLETED", "FAILED"}
            and not pid_exists(status.get("worker_pid"))):
        from .run_manager import continuation_delivery_path, mark_stranded_queue_attempt_ambiguous
        if continuation_delivery_path(run_dir).exists():
            try:
                mark_stranded_queue_attempt_ambiguous(run_dir)
            except (OSError, ValueError):
                # Existing but unreadable ledger is an ambiguous consumed slot.
                pass
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
    launch_parser.add_argument("--continuation-mode", choices=("queue", "disabled", "legacy_resume"))
    launch_parser.add_argument("--thread-id", help="exact original Codex thread ID, never a session ID")
    launch_parser.add_argument("--queue-timeout-seconds", type=float, default=120.0)
    launch_parser.add_argument("--review-spec", help="frozen review artifact spec identifier")
    launch_parser.add_argument("--review-stage", help="canonical review stage identifier")
    launch_parser.add_argument("--codex-executable", help="optional native Codex executable for queue preflight")
    launch_parser.add_argument("--session-id", help=argparse.SUPPRESS)
    launch_parser.add_argument("--no-callback", action="store_true", help="explicitly disable new continuation")
    launch_parser.add_argument(
        "--authorize-stage4b-production", action="store_true",
        help="consume the current task's one-shot authorization for the exact Stage 4B protocol",
    )
    launch_parser.add_argument(
        "--authorize-stage4c-production", action="store_true",
        help="consume the current task's one-shot authorization for the exact Stage 4C protocol",
    )
    launch_parser.add_argument("--session-file", help=argparse.SUPPRESS)
    launch_parser.set_defaults(handler=launch)

    for name in ("status", "review", "recover"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("run_id")
        if name == "status":
            subparser.set_defaults(handler=lambda args: print(format_status(resolve_run_dir(args.run_id))) or 0)
        else:
            subparser.set_defaults(handler=review if name == "review" else recover)
    subparsers.choices["review"].add_argument("--codex-executable")

    confirm_parser = subparsers.add_parser("confirm-queue", help="confirm a queued turn in its runtime thread")
    confirm_parser.add_argument("--run-dir", required=True)
    confirm_parser.add_argument("--run-id", required=True)
    confirm_parser.add_argument("--delivery-id", required=True)
    confirm_parser.add_argument("--delivery-sentinel", required=True)
    confirm_parser.set_defaults(handler=confirm_queue)

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
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"orchestration error: {exc}", file=sys.stderr)
        raise SystemExit(1)
