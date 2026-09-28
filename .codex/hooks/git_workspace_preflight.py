"""Read-only Git/worktree diagnostics plus a removable metadata write probe.

The probe creates one exclusive temporary file in each distinct Git metadata
directory, writes and flushes it, closes it, and removes it. It never changes
refs, the index, the object database, the working tree, or FETCH_HEAD.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
import subprocess
from pathlib import Path
from typing import Any


EXIT_CODES = {
    "PASS": 0,
    "PASS_WITH_LIMITATIONS": 0,
    "MISSING_REPOSITORY": 2,
    "REPO_TRUST_BLOCKED": 3,
    "PREFLIGHT_ERROR": 4,
    "METADATA_PROBE_CLEANUP_FAILED": 5,
}


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", str(repo), *args]
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        return subprocess.CompletedProcess(command, 127, "", f"{type(exc).__name__}: {exc}")


def _failure_class(stderr: str) -> str:
    message = stderr.casefold()
    if "detected dubious ownership" in message or "safe.directory" in message:
        return "REPO_TRUST_BLOCKED"
    if any(token in message for token in ("permission denied", "access is denied", "could not lock", "unable to create")):
        return "GIT_METADATA_WRITE_BLOCKED"
    return "UNEXPECTED_GIT_FAILURE"


def _is_reparse_point(path: Path) -> bool:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", None)
    if attributes is not None:
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(attributes & reparse_flag)
    return False


def _probe_one_directory(directory: Path) -> dict[str, str]:
    """Prove create/write/flush/remove access without touching Git-owned files."""
    try:
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or _is_reparse_point(directory):
            return {"status": "UNVERIFIED", "detail": "Git metadata path is not a plain directory."}
    except OSError as exc:
        return {"status": "UNVERIFIED", "detail": f"Cannot inspect metadata directory ({type(exc).__name__})."}

    canary = directory / f".codex-git-write-probe-{secrets.token_hex(16)}.tmp"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    descriptor: int | None = None
    created = False
    failure: str | None = None
    failure_status = "ERROR"
    try:
        descriptor = os.open(canary, flags, 0o600)
        created = True
        payload = b"temporary Codex Git metadata write probe\n"
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("Metadata probe write made no progress.")
            offset += written
        os.fsync(descriptor)
    except FileExistsError:
        failure = "Unique probe path unexpectedly already exists."
        failure_status = "UNVERIFIED"
    except PermissionError:
        failure = "The active process cannot write to this Git metadata directory."
        failure_status = "FAIL"
    except OSError as exc:
        failure = f"Metadata probe failed ({type(exc).__name__})."
        failure_status = "ERROR"
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as exc:
                failure = f"Metadata probe close failed ({type(exc).__name__})."
                failure_status = "ERROR"

    if created:
        try:
            canary.unlink()
        except OSError as exc:
            return {
                "status": "CLEANUP_FAILED",
                "detail": f"Could not remove the temporary probe ({type(exc).__name__}).",
                "probe_path": str(canary),
            }

    if failure:
        return {"status": failure_status, "detail": failure}
    return {"status": "PASS", "detail": "Created, wrote, flushed, closed, and removed one temporary file."}


def probe_git_metadata_write(git_dir: Path, common_dir: Path) -> dict[str, Any]:
    """Check both per-worktree and shared metadata directories, without Git mutations."""
    paths: list[Path] = []
    for candidate in (git_dir, common_dir):
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            return {"status": "UNVERIFIED", "detail": f"Cannot resolve Git metadata directory ({type(exc).__name__}).", "checks": []}
        if not resolved.is_dir():
            return {"status": "UNVERIFIED", "detail": "Git metadata path is not a directory.", "checks": []}
        if all(os.path.normcase(str(resolved)) != os.path.normcase(str(existing)) for existing in paths):
            paths.append(resolved)

    checks: list[dict[str, str]] = []
    for path in paths:
        check = _probe_one_directory(path)
        checks.append({"path": str(path), **check})
        if check["status"] == "CLEANUP_FAILED":
            return {"status": "CLEANUP_FAILED", "detail": check["detail"], "checks": checks}
        if check["status"] == "FAIL":
            return {"status": "FAIL", "detail": check["detail"], "checks": checks}
        if check["status"] != "PASS":
            return {"status": "UNVERIFIED", "detail": check["detail"], "checks": checks}
    return {"status": "PASS", "detail": "All distinct Git metadata directories passed the temporary write probe.", "checks": checks}


def _safe_directory_entries(repo: Path) -> dict[str, Any]:
    result = _run_git(repo, "config", "--show-origin", "--get-all", "safe.directory")
    entries: list[dict[str, str]] = []
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            origin, separator, value = line.partition("\t")
            if separator:
                entries.append({"origin": origin, "value": value})
            elif line:
                entries.append({"origin": "unknown", "value": line})
    target = os.path.normcase(os.path.normpath(str(repo.resolve())))
    matching: list[dict[str, str]] = []
    broad_wildcard = False
    for entry in entries:
        value = os.path.normcase(os.path.normpath(entry["value"]))
        if value == "*":
            broad_wildcard = True
            matching.append(entry)
        elif value == target:
            matching.append(entry)
        elif value.endswith(os.sep + "*"):
            parent = value[:-2]
            if target == parent or target.startswith(parent.rstrip(os.sep) + os.sep):
                matching.append(entry)
    status = "MATCH" if matching else ("UNAVAILABLE" if result.returncode not in (0, 1) else "NO_MATCH")
    return {"status": status, "entries": entries, "matching_entries": matching, "broad_wildcard_present": broad_wildcard}


def _parse_worktree_records(output: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for block in output.strip().split("\n\n"):
        if not block.strip():
            continue
        record: dict[str, Any] = {"locked": False, "detached": False}
        for line in block.splitlines():
            key, separator, value = line.partition(" ")
            if key == "worktree" and separator:
                record["path"] = value
            elif key == "HEAD" and separator:
                record["head"] = value
            elif key == "branch" and separator:
                record["branch"] = value
            elif key == "detached":
                record["detached"] = True
            elif key == "locked":
                record["locked"] = True
                record["lock_reason"] = value if separator else ""
            elif key == "prunable":
                record["prunable"] = True
        records.append(record)
    return records


def _matching_worktree_record(records: list[dict[str, Any]], top_level: str) -> dict[str, Any] | None:
    target = os.path.normcase(os.path.normpath(top_level))
    for record in records:
        path = record.get("path")
        if path and os.path.normcase(os.path.normpath(path)) == target:
            return record
    return None


def _verify_remote_freshness(repo: Path) -> dict[str, str]:
    upstream = _run_git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if upstream.returncode != 0:
        return {"remote_access": "UNVERIFIED", "remote_freshness": "UNVERIFIED", "detail": "Current branch has no readable upstream reference."}
    upstream_name = upstream.stdout.strip()
    remote, separator, branch = upstream_name.partition("/")
    if not separator or not remote or not branch:
        return {"remote_access": "UNVERIFIED", "remote_freshness": "UNVERIFIED", "detail": "Upstream reference is not in remote/branch form."}

    local = _run_git(repo, "rev-parse", "--verify", f"refs/remotes/{remote}/{branch}")
    remote_result = _run_git(repo, "ls-remote", "--heads", remote, f"refs/heads/{branch}")
    if remote_result.returncode != 0:
        return {"remote_access": "FAIL", "remote_freshness": "UNVERIFIED", "detail": "Read-only ls-remote failed; local refs were not updated."}
    remote_head = ""
    expected_ref = f"refs/heads/{branch}"
    for line in remote_result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] == expected_ref:
            remote_head = fields[0]
            break
    if local.returncode != 0 or not remote_head:
        return {"remote_access": "PASS", "remote_freshness": "UNVERIFIED", "detail": "Remote was reachable but no comparable tracking ref was available."}
    freshness = "FRESH" if local.stdout.strip() == remote_head else "STALE"
    return {"remote_access": "PASS", "remote_freshness": freshness, "detail": "Compared upstream tracking SHA with read-only ls-remote."}


def inspect_workspace(
    repo_path: str | os.PathLike[str], *, verify_remote: bool = False, metadata_probe: bool = True
) -> dict[str, Any]:
    repo = Path(repo_path).expanduser()
    if not repo.exists() or not repo.is_dir():
        return {
            "status": "MISSING_REPOSITORY",
            "repository": str(repo),
            "repo_exists": False,
            "repo_trust": "UNVERIFIED",
            "git_metadata_write": "UNVERIFIED",
            "remote_access": "UNVERIFIED",
            "remote_freshness": "UNVERIFIED",
            "errors": [],
        }

    repo = repo.resolve()
    trust = _run_git(repo, "rev-parse", "--show-toplevel")
    if trust.returncode != 0:
        classification = _failure_class(trust.stderr)
        status = "REPO_TRUST_BLOCKED" if classification == "REPO_TRUST_BLOCKED" else "PREFLIGHT_ERROR"
        return {
            "status": status,
            "repository": str(repo),
            "repo_exists": True,
            "repo_trust": "BLOCKED" if classification == "REPO_TRUST_BLOCKED" else "ERROR",
            "trust_error_class": classification,
            "safe_directory": _safe_directory_entries(repo),
            "git_metadata_read": "UNVERIFIED",
            "git_metadata_write": "UNVERIFIED",
            "remote_access": "UNVERIFIED",
            "remote_freshness": "UNVERIFIED",
            "errors": ["git rev-parse --show-toplevel failed"],
        }

    top_level = trust.stdout.strip()
    errors: list[str] = []
    status_result = _run_git(repo, "status", "--porcelain=v1", "--branch")
    branch_result = _run_git(repo, "branch", "--show-current")
    head_result = _run_git(repo, "rev-parse", "HEAD")
    git_dir_result = _run_git(repo, "rev-parse", "--path-format=absolute", "--git-dir")
    common_dir_result = _run_git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
    worktrees_result = _run_git(repo, "worktree", "list", "--porcelain")

    for label, result in (
        ("git status", status_result),
        ("git branch --show-current", branch_result),
        ("git rev-parse HEAD", head_result),
        ("git rev-parse --git-dir", git_dir_result),
        ("git rev-parse --git-common-dir", common_dir_result),
        ("git worktree list", worktrees_result),
    ):
        if result.returncode != 0:
            errors.append(f"{label}: {_failure_class(result.stderr)}")

    status_lines = status_result.stdout.splitlines() if status_result.returncode == 0 else []
    changes = [line for line in status_lines if line and not line.startswith("##")]
    working_tree = "UNKNOWN" if status_result.returncode != 0 else ("DIRTY" if changes else "CLEAN")
    git_dir = Path(git_dir_result.stdout.strip()) if git_dir_result.returncode == 0 else None
    common_dir = Path(common_dir_result.stdout.strip()) if common_dir_result.returncode == 0 else None
    worktree_records = _parse_worktree_records(worktrees_result.stdout) if worktrees_result.returncode == 0 else []
    current_record = _matching_worktree_record(worktree_records, top_level)
    identity = "UNKNOWN"
    if git_dir is not None and common_dir is not None:
        identity = "PRIMARY" if os.path.normcase(str(git_dir)) == os.path.normcase(str(common_dir)) else "LINKED"

    metadata = {"status": "UNVERIFIED", "detail": "Metadata probe disabled or Git directories unavailable.", "checks": []}
    if metadata_probe and git_dir is not None and common_dir is not None:
        metadata = probe_git_metadata_write(git_dir, common_dir)

    safe_dirs = _safe_directory_entries(repo)
    remote = (
        _verify_remote_freshness(repo)
        if verify_remote
        else {"remote_access": "UNVERIFIED", "remote_freshness": "UNVERIFIED", "detail": "Remote probe not requested; no network call was made."}
    )

    if metadata["status"] == "FAIL":
        write_dependent = "BLOCKED_BY_GIT_METADATA_WRITE"
    elif metadata["status"] == "PASS":
        write_dependent = "NOT_TESTED_METADATA_PROBE_PASSED"
    else:
        write_dependent = "UNVERIFIED"

    status = "PASS"
    if metadata["status"] == "CLEANUP_FAILED":
        status = "METADATA_PROBE_CLEANUP_FAILED"
    elif errors or metadata["status"] == "ERROR":
        status = "PREFLIGHT_ERROR"
    elif metadata["status"] != "PASS" or remote["remote_freshness"] != "FRESH":
        status = "PASS_WITH_LIMITATIONS"

    return {
        "status": status,
        "repository": str(repo),
        "repo_exists": True,
        "repo_trust": "PASS",
        "current_branch": branch_result.stdout.strip() if branch_result.returncode == 0 else "",
        "head": head_result.stdout.strip() if head_result.returncode == 0 else "",
        "working_tree": working_tree,
        "git_dir": str(git_dir) if git_dir is not None else None,
        "git_common_dir": str(common_dir) if common_dir is not None else None,
        "git_metadata_read": "PASS" if not errors and current_record is not None else "UNVERIFIED",
        "worktree_identity": identity,
        "worktree_registered": current_record is not None,
        "worktree_locked": current_record.get("locked") if current_record else None,
        "worktree_readiness": "READ_ONLY_READY" if current_record is not None and not errors else "UNVERIFIED",
        "git_metadata_write": metadata["status"],
        "metadata_probe": metadata,
        "write_dependent_capabilities": {
            "branch_create": write_dependent,
            "commit": write_dependent,
            "worktree_create": write_dependent,
        },
        "safe_directory": safe_dirs,
        "remote_access": remote["remote_access"],
        "remote_freshness": remote["remote_freshness"],
        "remote_detail": remote["detail"],
        "errors": errors,
    }


def _hook_message(result: dict[str, Any]) -> str:
    return (
        f"Git/worktree preflight: {result['status']}; "
        f"REPO_TRUST={result['repo_trust']}; "
        f"GIT_METADATA_WRITE={result['git_metadata_write']}; "
        f"WORKTREE={result.get('worktree_readiness', 'UNVERIFIED')} "
        f"({result.get('worktree_identity', 'UNKNOWN')}); "
        f"REMOTE_ACCESS={result['remote_access']}; "
        f"REMOTE_FRESHNESS={result['remote_freshness']}. "
        "Informational only. The default performs no network request; the temporary metadata probe "
        "does not change refs, the index, FETCH_HEAD, branches, or working-tree files."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2], help="Repository directory (defaults to this project).")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--hook-output", action="store_true", help="Emit Codex SessionStart hook context and always return success.")
    parser.add_argument("--verify-remote", action="store_true", help="Use read-only ls-remote to compare the current upstream; does not update refs.")
    parser.add_argument("--skip-metadata-probe", action="store_true", help="Do not create the temporary exclusive Git metadata canary.")
    args = parser.parse_args()

    result = inspect_workspace(args.repo, verify_remote=args.verify_remote, metadata_probe=not args.skip_metadata_probe)
    if args.hook_output:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": _hook_message(result),
        }}, ensure_ascii=False))
        return 0
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(_hook_message(result))
    return EXIT_CODES.get(result["status"], 4)


if __name__ == "__main__":
    raise SystemExit(main())
