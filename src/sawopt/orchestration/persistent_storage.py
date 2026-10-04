"""Fail-closed validation for durable production run locations."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PureWindowsPath
import subprocess
import tempfile
from typing import Iterable


@dataclass(frozen=True)
class PersistentRunValidation:
    classification: str
    candidate: str
    reason: str
    worktree_roots: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.classification == "PASS_EXTERNAL_PERSISTENT"


def _windows_parts(value: str | Path) -> tuple[str, ...] | None:
    path = PureWindowsPath(str(value))
    if not path.drive:
        return None
    return tuple(part.casefold() for part in path.parts)


def _same_or_below(candidate: str | Path, parent: str | Path) -> bool:
    child_windows = _windows_parts(candidate)
    parent_windows = _windows_parts(parent)
    if child_windows is not None or parent_windows is not None:
        if child_windows is None or parent_windows is None:
            return False
        return (len(child_windows) >= len(parent_windows)
                and child_windows[:len(parent_windows)] == parent_windows)
    child = Path(os.path.normpath(os.path.abspath(os.fspath(candidate))))
    base = Path(os.path.normpath(os.path.abspath(os.fspath(parent))))
    try:
        child.relative_to(base)
        return True
    except ValueError:
        return False


def _windows_identity_uncertain(candidate: Path, roots: Iterable[Path]) -> str | None:
    """Reject UNC destinations and unresolved aliases for Windows drive roots."""
    if os.name != "nt":
        return None
    candidate_path = PureWindowsPath(str(candidate))
    if candidate_path.drive.startswith("\\\\"):
        return "UNC persistent run paths are not supported because worktree identity cannot be proven"
    for root in roots:
        root_path = PureWindowsPath(str(root))
        if root_path.drive.startswith("\\\\"):
            return f"registered UNC worktree identity is uncertain: {root}"
        if not candidate_path.drive or not root_path.drive or candidate_path.drive.casefold() == root_path.drive.casefold():
            continue
        try:
            candidate_device = os.stat(candidate_path.anchor).st_dev
            root_device = os.stat(root_path.anchor).st_dev
        except OSError as exc:
            return f"cannot compare Windows drive identities: {exc}"
        if candidate_device == root_device:
            return f"different drive letters may alias the same volume: {candidate_path.drive} and {root_path.drive}"
    return None


def parse_worktree_list(output: bytes | str) -> tuple[Path, ...]:
    """Parse `git worktree list --porcelain -z` without line-based path parsing."""
    text = output.decode("utf-8", errors="strict") if isinstance(output, bytes) else output
    roots = []
    for record in text.split("\0"):
        if record.startswith("worktree "):
            value = record[len("worktree "):]
            if not value:
                raise ValueError("Git returned an empty worktree path")
            roots.append(Path(value))
    if not roots:
        raise ValueError("Git returned no registered worktrees")
    return tuple(roots)


def discover_worktree_roots(repository_root: str | Path) -> tuple[Path, ...]:
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain", "-z"],
        cwd=Path(repository_root), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace") if isinstance(result.stderr, bytes) else str(result.stderr)
        raise RuntimeError(f"git worktree discovery failed ({result.returncode}): {detail.strip()}")
    return parse_worktree_list(result.stdout)


def _has_reparse_component(path: Path) -> bool:
    """Detect symlinks, junctions, and Windows reparse points in existing components."""
    import stat

    absolute = Path(os.path.abspath(os.fspath(path)))
    components = list(reversed(absolute.parents)) + [absolute]
    for component in components:
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise RuntimeError(f"cannot inspect path component {component}: {exc}") from exc
        if stat.S_ISLNK(info.st_mode):
            return True
        attributes = getattr(info, "st_file_attributes", 0)
        if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            return True
        is_junction = getattr(component, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
    return False


def _probe_writable(directory: Path) -> None:
    descriptor, probe = tempfile.mkstemp(prefix=".sawopt-storage-probe-", dir=directory)
    os.close(descriptor)
    Path(probe).unlink()


def validate_persistent_run_location(
    candidate_run_dir: str | Path,
    repository_root: str | Path,
    *,
    worktree_roots: Iterable[str | Path] | None = None,
) -> PersistentRunValidation:
    """Validate an absolute, unique output path outside all known worktrees.

    Supplying ``worktree_roots`` is intended for isolated tests. Production
    callers omit it so Git discovery is mandatory and failures are fail-closed.
    """
    candidate_input = Path(candidate_run_dir)
    if not candidate_input.is_absolute():
        return PersistentRunValidation("FAIL_RELATIVE_PATH", str(candidate_input), "run path must be absolute")
    try:
        candidate_lexical = Path(os.path.abspath(os.fspath(candidate_input)))
        candidate_resolved = candidate_input.resolve(strict=False)
        repository = Path(repository_root).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        return PersistentRunValidation("FAIL_REPARSE_POINT", str(candidate_input), f"path resolution failed: {exc}")

    try:
        roots = tuple(Path(p) for p in worktree_roots) if worktree_roots is not None else discover_worktree_roots(repository)
        canonical_roots = tuple(Path(p).resolve(strict=False) for p in roots)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        return PersistentRunValidation("FAIL_WORKTREE_DISCOVERY", str(candidate_resolved), str(exc))

    uncertain_identity = _windows_identity_uncertain(candidate_lexical, canonical_roots)
    if uncertain_identity:
        return PersistentRunValidation(
            "FAIL_WORKTREE_DISCOVERY", str(candidate_resolved), uncertain_identity,
            tuple(str(p) for p in canonical_roots),
        )

    candidate_forms = (candidate_lexical, candidate_resolved)
    for root in canonical_roots:
        if any(_same_or_below(candidate, root) for candidate in candidate_forms):
            return PersistentRunValidation(
                "FAIL_INSIDE_WORKTREE", str(candidate_resolved),
                f"run path is equal to or below registered worktree {root}",
                tuple(str(p) for p in canonical_roots),
            )

    protected_roots = (repository / ".git", repository / "reports" / "experiment_reviews")
    for protected in protected_roots:
        protected_resolved = protected.resolve(strict=False)
        if any(_same_or_below(candidate, protected_resolved) for candidate in candidate_forms):
            return PersistentRunValidation(
                "FAIL_INSIDE_WORKTREE", str(candidate_resolved),
                f"run path is below protected repository path {protected_resolved}",
                tuple(str(p) for p in canonical_roots),
            )

    try:
        if _has_reparse_component(candidate_lexical):
            return PersistentRunValidation(
                "FAIL_REPARSE_POINT", str(candidate_resolved),
                "run path contains a symlink, junction, or other reparse point",
                tuple(str(p) for p in canonical_roots),
            )
    except RuntimeError as exc:
        return PersistentRunValidation("FAIL_REPARSE_POINT", str(candidate_resolved), str(exc), tuple(map(str, canonical_roots)))

    try:
        if candidate_lexical.exists():
            return PersistentRunValidation(
                "FAIL_DESTINATION_CONFLICT", str(candidate_resolved),
                "run destination already exists; production destinations must be unique",
                tuple(str(p) for p in canonical_roots),
            )
        parent = candidate_lexical.parent
        if not parent.is_dir():
            return PersistentRunValidation(
                "FAIL_DESTINATION_CONFLICT", str(candidate_resolved),
                f"run destination parent does not exist: {parent}",
                tuple(str(p) for p in canonical_roots),
            )
        _probe_writable(parent)
    except OSError as exc:
        return PersistentRunValidation(
            "FAIL_DESTINATION_CONFLICT", str(candidate_resolved),
            f"run destination parent is not writable or could not be checked: {exc}",
            tuple(str(p) for p in canonical_roots),
        )

    return PersistentRunValidation(
        "PASS_EXTERNAL_PERSISTENT", str(candidate_resolved),
        "absolute unique destination is outside registered worktrees and writable",
        tuple(str(p) for p in canonical_roots),
    )


__all__ = [
    "PersistentRunValidation", "discover_worktree_roots", "parse_worktree_list",
    "validate_persistent_run_location",
]
