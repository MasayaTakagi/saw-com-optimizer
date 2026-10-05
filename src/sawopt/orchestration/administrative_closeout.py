"""Explicit administrative closeout for dead orphaned production runs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Mapping

from .active_runs import active_runs_for_worktree, release_active_run
from .process_runner import pid_exists
from .run_manager import (
    atomic_write_json,
    load_manifest,
    load_status,
    optimizer_completion_path,
    record_optimizer_completion,
    transition,
    utc_now,
)


EVIDENCE_ROOT = PurePosixPath("reports/administrative_run_closeouts")
AUDIT_NAME = "administrative_failure_closeout.json"


class AdministrativeCloseoutError(RuntimeError):
    """The reviewed administrative closeout contract is not satisfied."""


def _git_bytes(repository_root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=repository_root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise AdministrativeCloseoutError(
            f"Git verification failed for {args[0]}: {detail}"
        )
    return result.stdout


def _path_equal(left: str | Path, right: str | Path) -> bool:
    left_text = os.path.normcase(os.path.abspath(os.fspath(left)))
    right_text = os.path.normcase(os.path.abspath(os.fspath(right)))
    if os.name == "nt":
        return left_text.casefold() == right_text.casefold()
    return left_text == right_text


def _evidence_relative_path(value: str | Path) -> PurePosixPath:
    text = str(value).replace("\\", "/")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise AdministrativeCloseoutError("closeout evidence must be a safe repository-relative path")
    if tuple(path.parts[:2]) != tuple(EVIDENCE_ROOT.parts) or len(path.parts) != 3:
        raise AdministrativeCloseoutError(
            "closeout evidence must be reports/administrative_run_closeouts/<run_id>.json"
        )
    if path.suffix.casefold() != ".json":
        raise AdministrativeCloseoutError("closeout evidence must be JSON")
    return path


def _load_reviewed_evidence(
    repository_root: Path, evidence_path: str | Path,
) -> tuple[dict[str, Any], str, str, str]:
    relative = _evidence_relative_path(evidence_path)
    dirty = _git_bytes(repository_root, "status", "--porcelain")
    if dirty.strip():
        raise AdministrativeCloseoutError(
            "administrative closeout requires a clean committed repository worktree"
        )
    head = _git_bytes(repository_root, "rev-parse", "HEAD").decode("ascii", errors="strict").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", head):
        raise AdministrativeCloseoutError("current Git HEAD is not a commit SHA")
    blob = _git_bytes(repository_root, "show", f"HEAD:{relative.as_posix()}")
    try:
        evidence = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdministrativeCloseoutError("reviewed closeout evidence is not valid UTF-8 JSON") from exc
    if not isinstance(evidence, dict):
        raise AdministrativeCloseoutError("reviewed closeout evidence must be a JSON object")
    digest = hashlib.sha256(blob).hexdigest()
    return evidence, relative.as_posix(), head.lower(), digest


def _validate_evidence(
    evidence: Mapping[str, Any], *, run_dir: Path, manifest, status: Mapping[str, Any],
) -> tuple[int, int, str, str]:
    if evidence.get("schema_version") != 1:
        raise AdministrativeCloseoutError("unsupported administrative closeout schema")
    if evidence.get("action") != "administrative_failure_closeout":
        raise AdministrativeCloseoutError("closeout evidence action is invalid")
    if str(evidence.get("run_id", "")) != manifest.run_id:
        raise AdministrativeCloseoutError("closeout evidence run ID does not match the run manifest")
    if str(evidence.get("source_commit_sha", "")) != str(manifest.source_commit_sha or ""):
        raise AdministrativeCloseoutError("closeout evidence source commit does not match the run manifest")
    if not _path_equal(str(evidence.get("expected_run_dir", "")), run_dir):
        raise AdministrativeCloseoutError("closeout evidence run directory does not match the run manifest")
    if not _path_equal(manifest.run_dir, run_dir):
        raise AdministrativeCloseoutError("requested run directory does not match the immutable manifest")
    if manifest.run_storage_policy != "external_persistent_v1":
        raise AdministrativeCloseoutError("administrative closeout is limited to external production runs")
    try:
        worker_pid = int(evidence["expected_worker_pid"])
        optimizer_pid = int(evidence["expected_optimizer_pid"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AdministrativeCloseoutError("closeout evidence must pin both recorded process IDs") from exc
    if worker_pid <= 0 or optimizer_pid <= 0:
        raise AdministrativeCloseoutError("closeout evidence process IDs must be positive")
    if status.get("worker_pid") != worker_pid or status.get("optimizer_pid") != optimizer_pid:
        raise AdministrativeCloseoutError("recorded process IDs differ from reviewed closeout evidence")
    allowed = evidence.get("allowed_preclose_states")
    if (not isinstance(allowed, list) or not allowed
            or any(str(value) not in {"STARTING", "RUNNING"} for value in allowed)):
        raise AdministrativeCloseoutError(
            "closeout evidence may authorize only STARTING/RUNNING pre-closeout states"
        )
    failure_class = str(evidence.get("failure_class", "")).strip()
    reason = str(evidence.get("reason", "")).strip()
    if not failure_class or len(failure_class) > 128:
        raise AdministrativeCloseoutError("closeout evidence failure_class is missing or too long")
    if not reason or len(reason) > 4096:
        raise AdministrativeCloseoutError("closeout evidence reason is missing or too long")
    scope = str(evidence.get("authorization_scope", "")).casefold()
    if "resume" not in scope or "relaunch" not in scope:
        raise AdministrativeCloseoutError(
            "closeout evidence must explicitly constrain resume and relaunch"
        )
    return worker_pid, optimizer_pid, failure_class, reason


def _matching_active_record(repository_root: Path, manifest, run_dir: Path):
    source_worktree = manifest.source_worktree_at_launch or manifest.project_root
    records = active_runs_for_worktree(repository_root, source_worktree)
    matching = [record for record in records if record.get("run_id") == manifest.run_id]
    if len(matching) > 1:
        raise AdministrativeCloseoutError("multiple active-run records match the same run ID")
    if not matching:
        return None
    record = matching[0]
    if not _path_equal(record.get("run_dir", ""), run_dir):
        raise AdministrativeCloseoutError("active-run registry path differs from the reviewed run")
    if str(record.get("source_head", "")) != str(manifest.source_commit_sha or ""):
        raise AdministrativeCloseoutError("active-run registry source SHA differs from the run manifest")
    return record


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdministrativeCloseoutError(f"invalid {label}") from exc
    if not isinstance(value, dict):
        raise AdministrativeCloseoutError(f"invalid {label}")
    return value


def _audit_matches(
    audit: Mapping[str, Any], *, manifest, evidence_path: str, evidence_sha256: str,
) -> bool:
    return (
        audit.get("schema_version") == 1
        and audit.get("action") == "administrative_failure_closeout"
        and audit.get("run_id") == manifest.run_id
        and audit.get("source_commit_sha") == manifest.source_commit_sha
        and audit.get("evidence_path") == evidence_path
        and audit.get("evidence_sha256") == evidence_sha256
    )


def _ensure_failed_completion(
    run_dir: Path, *, manifest, exit_code: int | None, error: str,
) -> None:
    path = optimizer_completion_path(run_dir)
    if path.exists():
        value = _load_json_object(path, label="optimizer completion evidence")
        if (value.get("run_id") != manifest.run_id
                or value.get("disposition") != "FAILED"):
            raise AdministrativeCloseoutError(
                "existing optimizer completion evidence conflicts with administrative closeout"
            )
        return
    record_optimizer_completion(
        run_dir, disposition="FAILED", exit_code=exit_code, error=error,
    )


def finalize_orphaned_failure(
    run_dir: str | Path,
    evidence_path: str | Path,
    *,
    repository_root: str | Path,
    confirm_abandon: bool,
) -> dict[str, Any]:
    """Close one exact dead production run using reviewed GitHub evidence."""
    if not confirm_abandon:
        raise PermissionError("administrative closeout requires --confirm-abandon")
    root = Path(repository_root).resolve(strict=True)
    requested_run = Path(run_dir)
    if not requested_run.is_absolute():
        raise AdministrativeCloseoutError("administrative closeout requires an absolute run directory")
    run = requested_run.resolve(strict=True)
    manifest = load_manifest(run)
    status = load_status(run)
    evidence, relative_evidence, evidence_head, evidence_sha256 = _load_reviewed_evidence(
        root, evidence_path,
    )
    worker_pid, optimizer_pid, failure_class, reason = _validate_evidence(
        evidence, run_dir=run, manifest=manifest, status=status,
    )
    if PurePosixPath(relative_evidence).name != f"{manifest.run_id}.json":
        raise AdministrativeCloseoutError("closeout evidence filename must equal the run ID")

    worker_alive = pid_exists(worker_pid)
    optimizer_alive = pid_exists(optimizer_pid)
    if worker_alive or optimizer_alive:
        raise AdministrativeCloseoutError(
            "recorded production process is still running; administrative closeout is forbidden"
        )

    audit_path = run / AUDIT_NAME
    existing_audit = None
    if audit_path.exists():
        existing_audit = _load_json_object(audit_path, label="administrative closeout audit")
        if not _audit_matches(
            existing_audit, manifest=manifest,
            evidence_path=relative_evidence, evidence_sha256=evidence_sha256,
        ):
            raise AdministrativeCloseoutError(
                "existing administrative closeout audit conflicts with reviewed evidence"
            )

    active_record = _matching_active_record(root, manifest, run)
    if status["state"] == "FAILED" and existing_audit is not None:
        _ensure_failed_completion(
            run, manifest=manifest, exit_code=status.get("exit_code"),
            error=str(existing_audit.get("reason") or reason),
        )
        released = False
        if active_record is not None:
            released = release_active_run(root, run_id=manifest.run_id)
            if not released:
                raise AdministrativeCloseoutError("failed to release matching active-run registry entry")
        return {
            "status": "ALREADY_CLOSED_FAILED",
            "run_id": manifest.run_id,
            "run_dir": str(run),
            "evidence_path": relative_evidence,
            "evidence_sha256": evidence_sha256,
            "evidence_commit_sha": existing_audit.get("evidence_commit_sha", evidence_head),
            "registry_released": bool(released),
        }

    allowed_states = {str(value) for value in evidence["allowed_preclose_states"]}
    if status["state"] not in allowed_states:
        raise AdministrativeCloseoutError(
            f"current run state {status['state']} is not authorized by reviewed closeout evidence"
        )
    if active_record is None:
        raise AdministrativeCloseoutError(
            "matching active-run registry entry is missing before administrative closeout"
        )
    if audit_path.exists():
        raise AdministrativeCloseoutError(
            "administrative closeout audit already exists without terminal FAILED state"
        )

    prior_status_keys = (
        "state", "worker_pid", "optimizer_pid", "optimizer_state", "exit_code", "error",
        "error_type", "error_message", "error_repr", "error_traceback_path",
        "failing_cell", "last_durable_checkpoint_budget",
    )
    audit = {
        "schema_version": 1,
        "action": "administrative_failure_closeout",
        "run_id": manifest.run_id,
        "source_commit_sha": manifest.source_commit_sha,
        "run_dir": str(run),
        "evidence_path": relative_evidence,
        "evidence_sha256": evidence_sha256,
        "evidence_commit_sha": evidence_head,
        "failure_class": failure_class,
        "reason": reason,
        "closed_at_utc": utc_now(),
        "prior_status": {key: status.get(key) for key in prior_status_keys},
        "process_liveness": {
            "worker_pid": worker_pid,
            "worker_alive": False,
            "optimizer_pid": optimizer_pid,
            "optimizer_alive": False,
        },
        "preservation": {
            "raw_run_preserved": True,
            "checkpoints_preserved": True,
            "queue_continuation_sent": False,
            "scientific_review_completed": False,
            "replacement_production_authorized": False,
        },
    }
    atomic_write_json(audit_path, audit)
    error = status.get("error") or f"administratively closed: {failure_class}: {reason}"
    _ensure_failed_completion(
        run, manifest=manifest, exit_code=status.get("exit_code"), error=str(error),
    )
    transition(
        run, "FAILED", exit_code=status.get("exit_code"), error=str(error),
    )
    released = release_active_run(root, run_id=manifest.run_id)
    if not released:
        raise AdministrativeCloseoutError("failed to release matching active-run registry entry")
    return {
        "status": "CLOSED_FAILED",
        "run_id": manifest.run_id,
        "run_dir": str(run),
        "evidence_path": relative_evidence,
        "evidence_sha256": evidence_sha256,
        "evidence_commit_sha": evidence_head,
        "registry_released": True,
    }


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Administratively close one exact dead production run as failed.",
    )
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--repository-root", default=str(project_root()))
    parser.add_argument("--confirm-abandon", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = finalize_orphaned_failure(
        args.run_dir,
        args.evidence,
        repository_root=args.repository_root,
        confirm_abandon=bool(args.confirm_abandon),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"administrative closeout error: {exc}", file=sys.stderr)
        raise SystemExit(1)
