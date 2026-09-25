"""Create and validate compact saved-run review bundles."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZipFile


class BundleValidationError(ValueError):
    """Raised when a run is not complete enough to be reviewed."""


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _write_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _copy_file(source, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def is_checkpoint_artifact(path):
    """Return whether a run artifact is a checkpoint payload.

    Review bundles keep summaries and source code, but omit potentially large
    restart/progress payloads. Dedicated ``checkpoints`` directories are
    always omitted. Checkpoint-named files are omitted only for payload formats;
    source code, documentation, and CSV accounting remain reviewable.
    """
    path = Path(path)
    if any(part.casefold() == 'checkpoints' for part in path.parts):
        return True
    payload_suffixes = {'.json', '.jsonl', '.npz', '.npy', '.pkl', '.pickle', '.bin', '.chk'}
    return path.suffix.casefold() in payload_suffixes and any(
        'checkpoint' in part.casefold() for part in path.parts
    )


def ignore_checkpoint_entries(_directory, names):
    """``shutil.copytree`` ignore callback for checkpoint payloads."""
    return [name for name in names if is_checkpoint_artifact(name)]


def _repository_root(module_path=None):
    """Resolve both the checkout layout and an extracted bundle layout."""
    module_path = Path(module_path or __file__).resolve()
    for candidate in (module_path.parents[3], module_path.parents[2], module_path.parents[1]):
        if (candidate / 'src' / 'sawopt').is_dir():
            return candidate
    raise BundleValidationError(f'Cannot resolve repository root from {module_path}')


def _workspace_root(repo=None):
    """Return the repository root that owns the external review artifacts."""
    return Path(repo or _repository_root()).resolve()


def _default_review_bundle_output(run, repo=None):
    """Return the fixed repository-level output path for ``run``."""
    run = Path(run).resolve()
    return _workspace_root(repo) / 'artifacts' / 'review_bundles' / f'{run.name}_review.zip'


def _git(repo, args):
    try:
        # Git emits repository text as UTF-8 even when the Windows process
        # locale is a legacy code page.  Decode explicitly so review bundles
        # remain reproducible on Japanese Windows hosts.
        return subprocess.check_output(
            ['git', *args], cwd=repo, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace',
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return f'git unavailable: {exc}\n'


@dataclass(frozen=True)
class ReviewBundleSpec:
    """Declarative inputs for packaging an already completed study run."""

    study_type: str
    required_artifacts: tuple[str, ...]
    optional_artifacts: tuple[str, ...] = ()
    source_paths: tuple[str, ...] = ()
    review_me_path: str = "REVIEW_ME.md"
    source_snapshot_dir: str = "source_snapshot"
    max_optional_artifact_bytes: int | None = None
    git_diff_paths: tuple[str, ...] | None = None


def _bundle_relative_path(value: str) -> Path:
    normalized = str(value).replace("\\", "/")
    path = Path(normalized)
    parts = normalized.split("/")
    if path.is_absolute() or any(part in ("", ".", "..") for part in parts):
        raise BundleValidationError(f"Bundle artifact path must be relative and contained: {value!r}")
    return Path(*parts)


def _git_diff_scope(values: Sequence[str] | None) -> tuple[str, ...] | None:
    if values is None:
        return None
    if isinstance(values, (str, bytes)):
        raise BundleValidationError("Git diff scope must be a sequence of literal repository paths")
    scope = []
    for value in values:
        if not isinstance(value, str):
            raise BundleValidationError("Git diff scope entries must be strings")
        normalized = value.replace("\\", "/")
        _bundle_relative_path(normalized)
        if any(char in normalized for char in "*?[]:") or "\0" in normalized:
            raise BundleValidationError(
                f"Git diff scope must use literal repository paths: {value!r}"
            )
        scope.append(normalized)
    return tuple(dict.fromkeys(scope))


def _git_snapshot(
    repo: Path, diff_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    scope = _git_diff_scope(diff_paths)
    if scope is None:
        unstaged = _git(repo, ["diff", "--binary"])
        staged = _git(repo, ["diff", "--cached", "--binary"])
    elif scope:
        unstaged = _git(repo, ["--literal-pathspecs", "diff", "--binary", "--", *scope])
        staged = _git(repo, ["--literal-pathspecs", "diff", "--cached", "--binary", "--", *scope])
    else:
        unstaged = staged = ""
    return {
        "head": _git(repo, ["rev-parse", "HEAD"]).strip(),
        "branch": _git(repo, ["branch", "--show-current"]).strip(),
        "status_short": _git(repo, ["status", "--short"]),
        "diff_patch": unstaged,
        "staged_diff_patch": staged,
        "diff_scope": list(scope) if scope is not None else None,
    }


def _write_environment_snapshot(
    destination: Path, repo: Path, *, git_diff_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    import importlib.metadata

    git = _git_snapshot(repo, git_diff_paths)
    for name, value in git.items():
        if name == "diff_scope":
            suffix = ".json"
            contents = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        else:
            suffix = ".patch" if name.endswith("patch") else ".txt"
            contents = value + ("\n" if suffix == ".txt" and value else "")
        _write_text(destination / "git" / f"{name}{suffix}", contents)
    packages = {}
    for name in ("numpy", "scipy", "matplotlib", "PyYAML", "pytest"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    environment = {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "packages": packages,
    }
    _write_text(destination / "environment.json", json.dumps(environment, ensure_ascii=False, indent=2) + "\n")
    return {"git": git, "environment": environment}


def write_review_bundle_archive(
    bundle_directory: str | Path,
    output_zip: str | Path,
    *,
    study_type: str,
    run_directory: str | Path,
    required_artifacts: Sequence[str] = (),
    optional_artifacts: Sequence[str] = (),
    metadata: Mapping[str, Any] | None = None,
    archive_prefix: str | None = None,
    repository_root: str | Path | None = None,
    git_diff_paths: Sequence[str] | None = None,
) -> Path:
    """Hash and archive a stage-prepared bundle directory.

    Stage-specific reporting code may prepare review text and derived files;
    this shared layer validates the required paths, creates a SHA-256 manifest,
    writes the ZIP, and checks every archived byte against the manifest.
    """
    bundle = Path(bundle_directory).resolve()
    output = Path(output_zip).resolve()
    if not bundle.is_dir():
        raise BundleValidationError(f"Staged bundle directory does not exist: {bundle}")
    required = [_bundle_relative_path(value) for value in required_artifacts]
    optional = [_bundle_relative_path(value) for value in optional_artifacts]
    missing = [path.as_posix() for path in required if not (bundle / path).is_file()]
    if missing:
        raise BundleValidationError("Missing required bundle artifacts: " + ", ".join(missing))
    prefix = _bundle_relative_path(archive_prefix).as_posix() if archive_prefix else ""
    optional_set = set(optional)
    repository = Path(repository_root).resolve() if repository_root else _repository_root()
    diff_scope = _git_diff_scope(git_diff_paths)
    environment_snapshot = _write_environment_snapshot(
        bundle / "environment", repository, git_diff_paths=diff_scope,
    )

    files = []
    for source in sorted(path for path in bundle.rglob("*") if path.is_file()):
        relative = source.relative_to(bundle)
        if relative.name == "bundle_manifest.json":
            continue
        # Checkpoint stores are always excluded, even if a caller mistakenly
        # lists a file below one as required. Other checkpoint-named JSON files
        # may be required lifecycle validation reports, so explicit required
        # artifacts take precedence over the filename-based payload filter.
        if any(part.casefold() == "checkpoints" for part in relative.parts):
            continue
        if relative not in required and is_checkpoint_artifact(relative):
            continue
        archive_name = "/".join(part for part in (prefix, relative.as_posix()) if part)
        files.append({
            "path": archive_name,
            "sha256": _sha256(source),
            "bytes": source.stat().st_size,
            "required": relative in required or relative not in optional_set,
        })
    required_archive_names = {
        "/".join(part for part in (prefix, path.as_posix()) if part)
        for path in required
    }
    archived_names = {entry["path"] for entry in files}
    omitted_required = sorted(required_archive_names - archived_names)
    if omitted_required:
        raise BundleValidationError(
            "Required artifacts were excluded from the archive: "
            + ", ".join(omitted_required)
        )
    manifest = {
        "bundle_format_version": 2,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "study_type": study_type,
        "run_directory": str(Path(run_directory).resolve()),
        "optional_artifacts": [path.as_posix() for path in optional],
        "files": files,
        "environment": environment_snapshot["environment"],
        "git_head": environment_snapshot["git"]["head"],
        "git_status_short": environment_snapshot["git"]["status_short"],
        "git_diff_scope": environment_snapshot["git"]["diff_scope"],
    }
    if metadata:
        protected = set(manifest)
        overlap = protected & set(metadata)
        if overlap:
            raise BundleValidationError("Bundle metadata overrides reserved keys: " + ", ".join(sorted(overlap)))
        manifest.update(metadata)
    manifest_path = bundle / "bundle_manifest.json"
    _write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_archive_path = "/".join(part for part in (prefix, "bundle_manifest.json") if part)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(manifest_path, manifest_archive_path)
        for entry in files:
            archive_parts = entry["path"].split("/")
            prefix_parts = prefix.split("/") if prefix else []
            source_parts = archive_parts[len(prefix_parts):]
            source = bundle / Path(*source_parts)
            archive.write(source, entry["path"])

    with ZipFile(output) as archive:
        names = set(archive.namelist())
        if manifest_archive_path not in names:
            raise BundleValidationError("ZIP is missing bundle_manifest.json")
        bundled_manifest = json.loads(archive.read(manifest_archive_path).decode("utf-8"))
        expected_names = {entry["path"] for entry in bundled_manifest["files"]}
        if names != expected_names | {manifest_archive_path}:
            raise BundleValidationError("ZIP contents do not match bundle manifest")
        for entry in bundled_manifest["files"]:
            data = archive.read(entry["path"])
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise BundleValidationError(f"ZIP hash mismatch: {entry['path']}")
            if len(data) != int(entry["bytes"]):
                raise BundleValidationError(f"ZIP byte-size mismatch: {entry['path']}")
    return output


def build_review_bundle(
    run_dir: str | Path,
    output_zip: str | Path,
    spec: ReviewBundleSpec,
    *,
    repo_root: str | Path | None = None,
    include_optional: bool = True,
) -> Path:
    """Build a review ZIP from saved run files without loading a study runner."""
    run = Path(run_dir).resolve()
    output = Path(output_zip).resolve()
    if not run.is_dir():
        raise BundleValidationError(f"Run directory does not exist: {run}")
    required = [_bundle_relative_path(value) for value in spec.required_artifacts]
    review_path = _bundle_relative_path(spec.review_me_path)
    if review_path not in required:
        required.append(review_path)
    optional = [_bundle_relative_path(value) for value in spec.optional_artifacts]
    missing = [path.as_posix() for path in required if not (run / path).is_file()]
    if missing:
        raise BundleValidationError("Missing required run artifacts: " + ", ".join(missing))

    repo = Path(repo_root).resolve() if repo_root else _repository_root()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="review_bundle_", dir=str(output.parent)) as temp_name:
        staging = Path(temp_name) / "bundle"
        staging.mkdir()
        _copy_file(run / review_path, staging / "REVIEW_ME.md")
        for relative in required:
            _copy_file(run / relative, staging / "run" / relative)
        omitted_optional = []
        for relative in optional:
            source = run / relative
            if not include_optional or not source.is_file():
                omitted_optional.append(relative.as_posix())
                continue
            if (spec.max_optional_artifact_bytes is not None
                    and source.stat().st_size > spec.max_optional_artifact_bytes):
                omitted_optional.append(relative.as_posix())
                continue
            _copy_file(source, staging / "optional" / relative)

        saved_snapshot = run / _bundle_relative_path(spec.source_snapshot_dir)
        snapshot_origin = "not_available"
        if saved_snapshot.is_dir():
            shutil.copytree(saved_snapshot, staging / "source_snapshot" / "recorded")
            snapshot_origin = "recorded_run_snapshot"
        if spec.source_paths:
            current = staging / "source_snapshot" / "current_repository"
            for value in spec.source_paths:
                relative = _bundle_relative_path(value)
                source = repo / relative
                if not source.is_file():
                    raise BundleValidationError(f"Missing current source snapshot file: {value}")
                _copy_file(source, current / relative)
            if snapshot_origin == "not_available":
                snapshot_origin = "current_repository_at_bundle_time"
        _write_text(staging / "source_snapshot" / "origin.txt", snapshot_origin + "\n")
        optional_outputs = [Path("optional") / path for path in optional if (staging / "optional" / path).is_file()]
        archive = write_review_bundle_archive(
            staging,
            output,
            study_type=spec.study_type,
            run_directory=run,
            required_artifacts=(
                "REVIEW_ME.md",
                *(Path("run") / relative for relative in required),
            ),
            optional_artifacts=[path.as_posix() for path in optional_outputs],
            metadata={
                "snapshot_origin": snapshot_origin,
                "optional_artifacts_omitted": omitted_optional,
            },
            repository_root=repo,
            git_diff_paths=spec.git_diff_paths,
        )
    return archive


def main(argv=None):
    parser = argparse.ArgumentParser(description="Package a saved run using a ReviewBundleSpec")
    parser.add_argument("--run", required=True)
    parser.add_argument("--spec", required=True, help="JSON file containing a ReviewBundleSpec")
    parser.add_argument("--output", help="Optional filename inside artifacts/review_bundles")
    args = parser.parse_args(argv)
    repo = _repository_root()
    default_output = _default_review_bundle_output(args.run, repo)
    output = default_output if args.output is None else Path(args.output).resolve()
    if output.parent != default_output.parent.resolve():
        parser.error(
            "Review bundles must be written directly under the repository-root "
            f"artifacts/review_bundles directory: {default_output.parent}"
        )
    try:
        payload = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        spec = ReviewBundleSpec(
            study_type=str(payload["study_type"]),
            required_artifacts=tuple(payload["required_artifacts"]),
            optional_artifacts=tuple(payload.get("optional_artifacts", ())),
            source_paths=tuple(payload.get("source_paths", ())),
            review_me_path=str(payload.get("review_me_path", "REVIEW_ME.md")),
            source_snapshot_dir=str(payload.get("source_snapshot_dir", "source_snapshot")),
            max_optional_artifact_bytes=payload.get("max_optional_artifact_bytes"),
            git_diff_paths=(
                tuple(payload["git_diff_paths"])
                if payload.get("git_diff_paths") is not None else None
            ),
        )
        archive = build_review_bundle(args.run, output, spec)
    except (BundleValidationError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(archive)


if __name__ == '__main__':
    main()
