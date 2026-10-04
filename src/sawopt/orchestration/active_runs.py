"""Durable active-production registry shared by Git-linked worktrees."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Iterator

from .run_manager import atomic_write_json, exclusive_lock


REGISTRY_NAME = "sawopt-active-runs"
REGISTRY_SCHEMA_VERSION = 1
_RUN_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


class ActiveRunRegistryError(RuntimeError):
    """The active-run registry is absent, corrupt, or inconsistent."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_common_dir(repository_root: str | Path) -> Path:
    root = Path(repository_root).resolve(strict=True)
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"], cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ActiveRunRegistryError(f"cannot resolve Git common directory: {detail}")
    value = result.stdout.decode("utf-8", errors="strict").strip()
    common = Path(value)
    if not common.is_absolute():
        common = root / common
    return common.resolve(strict=True)


def registry_directory(repository_root: str | Path) -> Path:
    return git_common_dir(repository_root) / REGISTRY_NAME


@contextmanager
def worktree_safety_lock(repository_root: str | Path) -> Iterator[Path]:
    """Serialize launch registration with the final audit/removal transaction."""
    common = git_common_dir(repository_root)
    with exclusive_lock(common / ".sawopt-worktree-safety.lock", timeout_s=30.0):
        yield common


def _read_registry(directory: Path) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    if not directory.exists():
        raise ActiveRunRegistryError("FAIL_ACTIVE_RUN_REGISTRY_UNINITIALIZED")
    try:
        directory_info = directory.lstat()
    except OSError as exc:
        raise ActiveRunRegistryError(f"FAIL_ACTIVE_RUN_REGISTRY_INVALID: {exc}") from exc
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if (not stat.S_ISDIR(directory_info.st_mode)
            or stat.S_ISLNK(directory_info.st_mode)
            or bool(getattr(directory_info, "st_file_attributes", 0) & reparse_flag)):
        raise ActiveRunRegistryError("FAIL_ACTIVE_RUN_REGISTRY_INVALID: registry is not a directory")
    metadata_path = directory / "registry.json"
    try:
        metadata_info = metadata_path.lstat()
        if (not stat.S_ISREG(metadata_info.st_mode)
                or stat.S_ISLNK(metadata_info.st_mode)
                or bool(getattr(metadata_info, "st_file_attributes", 0) & reparse_flag)):
            raise ActiveRunRegistryError(
                "FAIL_ACTIVE_RUN_REGISTRY_INVALID: initialization metadata is not a regular file"
            )
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except ActiveRunRegistryError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ActiveRunRegistryError(f"FAIL_ACTIVE_RUN_REGISTRY_INVALID: {exc}") from exc
    if (not isinstance(metadata, dict)
            or metadata.get("schema_version") != REGISTRY_SCHEMA_VERSION
            or metadata.get("initialized") is not True
            or metadata.get("acknowledged_no_unregistered_active_runs") is not True):
        raise ActiveRunRegistryError("FAIL_ACTIVE_RUN_REGISTRY_INVALID: initialization metadata is invalid")
    records: list[dict[str, Any]] = []
    try:
        entries = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
    except OSError as exc:
        raise ActiveRunRegistryError(f"FAIL_ACTIVE_RUN_REGISTRY_INVALID: {exc}") from exc
    for path in entries:
        if path.name == "registry.json":
            continue
        try:
            entry_info = path.lstat()
        except OSError as exc:
            raise ActiveRunRegistryError(f"FAIL_ACTIVE_RUN_REGISTRY_INVALID: {path.name}: {exc}") from exc
        if (path.suffix.casefold() != ".json" or not stat.S_ISREG(entry_info.st_mode)
                or stat.S_ISLNK(entry_info.st_mode)
                or bool(getattr(entry_info, "st_file_attributes", 0) & reparse_flag)):
            raise ActiveRunRegistryError(
                f"FAIL_ACTIVE_RUN_REGISTRY_INVALID: unexpected registry entry {path.name}"
            )
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ActiveRunRegistryError(
                f"FAIL_ACTIVE_RUN_REGISTRY_INVALID: {path.name}: {exc}"
            ) from exc
        if (not isinstance(record, dict)
                or record.get("schema_version") != REGISTRY_SCHEMA_VERSION
                or record.get("run_id") != path.stem
                or record.get("state") != "ACTIVE"
                or not isinstance(record.get("source_worktree"), str)
                or not Path(record["source_worktree"]).is_absolute()
                or not isinstance(record.get("run_dir"), str)
                or not Path(record["run_dir"]).is_absolute()
                or not isinstance(record.get("source_head"), str)
                or not record["source_head"]):
            raise ActiveRunRegistryError(
                f"FAIL_ACTIVE_RUN_REGISTRY_INVALID: malformed active record {path.name}"
            )
        records.append(record)
    return metadata, tuple(records)


def initialize_active_run_registry(
    repository_root: str | Path, *, confirm_no_unregistered_active_runs: bool,
) -> dict[str, Any]:
    """Explicitly initialize only after existing external runs were reconciled."""
    if not confirm_no_unregistered_active_runs:
        raise ActiveRunRegistryError(
            "initialization requires explicit reconciliation of all existing external run roots"
        )
    with worktree_safety_lock(repository_root) as common:
        directory = common / REGISTRY_NAME
        if directory.exists():
            metadata, records = _read_registry(directory)
            return {"status": "ALREADY_INITIALIZED", "active_runs": len(records), **metadata}
        directory.mkdir()
        metadata = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "initialized": True,
            "initialized_at": _utc_now(),
            "acknowledged_no_unregistered_active_runs": True,
        }
        atomic_write_json(directory / "registry.json", metadata)
        return {"status": "INITIALIZED", "active_runs": 0, **metadata}


def _path_equal(left: str | Path, right: str | Path) -> bool:
    left_text = os.path.normcase(os.path.abspath(os.fspath(left)))
    right_text = os.path.normcase(os.path.abspath(os.fspath(right)))
    if os.name == "nt":
        return left_text.casefold() == right_text.casefold()
    return left_text == right_text


def _verify_source_worktree(
    repository_root: Path, source_worktree: Path, *, source_head: str,
    source_branch: str | None,
) -> None:
    from .worktree_safety import _path_equal, _worktree_identities

    identities = _worktree_identities(repository_root)
    identity = next((item for item in identities if _path_equal(item.path, source_worktree)), None)
    if identity is None:
        raise ActiveRunRegistryError("source worktree is no longer registered with Git")
    registered_branch = identity.branch
    if registered_branch and registered_branch.startswith("refs/heads/"):
        registered_branch = registered_branch[len("refs/heads/"):]
    if identity.head != source_head or registered_branch != source_branch:
        raise ActiveRunRegistryError("source worktree identity changed before active-run registration")


def register_active_run(
    repository_root: str | Path, *, run_id: str, run_dir: str | Path,
    source_worktree: str | Path, source_head: str, source_branch: str | None,
) -> Path:
    if not _RUN_ID.fullmatch(run_id):
        raise ActiveRunRegistryError("run ID is unsafe for active-run registry")
    root = Path(repository_root).resolve(strict=True)
    source = Path(source_worktree).resolve(strict=True)
    run = Path(run_dir).resolve(strict=False)
    with worktree_safety_lock(root) as common:
        directory = common / REGISTRY_NAME
        _metadata, records = _read_registry(directory)
        _verify_source_worktree(root, source, source_head=source_head, source_branch=source_branch)
        if any(item["run_id"].casefold() == run_id.casefold() for item in records):
            raise ActiveRunRegistryError(f"active run ID is already registered: {run_id}")
        record = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "state": "ACTIVE",
            "run_id": run_id,
            "run_dir": str(run),
            "source_worktree": str(source),
            "source_head": source_head,
            "source_branch": source_branch,
            "registered_at": _utc_now(),
        }
        path = directory / f"{run_id}.json"
        if path.exists():
            raise ActiveRunRegistryError(f"active run registry entry already exists: {path.name}")
        atomic_write_json(path, record)
        return path


def active_runs_for_worktree(
    repository_root: str | Path, worktree: str | Path, *, lock_held: bool = False,
) -> tuple[dict[str, Any], ...]:
    target = Path(worktree).resolve(strict=False)

    def read(common: Path) -> tuple[dict[str, Any], ...]:
        _metadata, records = _read_registry(common / REGISTRY_NAME)
        return tuple(item for item in records if _path_equal(item["source_worktree"], target))

    if lock_held:
        return read(git_common_dir(repository_root))
    with worktree_safety_lock(repository_root) as common:
        return read(common)


def release_active_run(repository_root: str | Path, *, run_id: str) -> bool:
    if not _RUN_ID.fullmatch(run_id):
        raise ActiveRunRegistryError("run ID is unsafe for active-run registry")
    with worktree_safety_lock(repository_root) as common:
        directory = common / REGISTRY_NAME
        _metadata, records = _read_registry(directory)
        path = directory / f"{run_id}.json"
        if not any(item["run_id"] == run_id for item in records):
            return False
        path.unlink()
        return True


__all__ = [
    "ActiveRunRegistryError", "active_runs_for_worktree", "git_common_dir",
    "initialize_active_run_registry", "register_active_run", "release_active_run",
    "registry_directory", "worktree_safety_lock",
]
