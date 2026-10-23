"""Deterministic, fail-closed review-schema-v1 export for synthetic future runs."""
from __future__ import annotations

import binascii
import csv
import hashlib
import io
import json
import os
import re
import shutil
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import yaml

from ..io import experiment_store as store


REVIEW_SCHEMA_ID = "sawopt.review/1"
REVIEW_SCHEMA_VERSION = 1
TARGET_BYTES = 2 * 1024 * 1024
HARD_LIMIT_BYTES = 10 * 1024 * 1024
REQUIRED_FILES = {
    "README.md", "manifest.json", "config.yaml", "cells.json", "convergence.csv", "checks.json",
}
SECRET_PATTERN = re.compile(
    r"(?i)(?:authorization\s*:\s*bearer\s+\S+|(?:api[_-]?key|access_token|refresh_token|client_secret|admin_token|password|secret|token)\s*[:=]\s*(?![\"']?<REDACTED(?:_PATH)?[\"']?)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+))"
)
UNIX_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9:])/(?:[^\s\"'<>|]+/)*[^\s\"'<>|]+")
WINDOWS_PATH_PATTERN = re.compile(r"(?i)(?<![A-Za-z0-9])[A-Z]:[\\/][^\s\"'<>|]+")
SENSITIVE_KEY_PATTERN = re.compile(r"(?i)(password|secret|token|api[_-]?key|credential|authorization|private[_-]?key)")
CONVERGENCE_COLUMNS = (
    "cell_id", "phase", "search_fes", "validation_points", "metric_name",
    "metric_value", "metric_status", "unit", "observed_at_utc",
)


class ReviewPackageError(ValueError):
    """Required evidence, provenance, redaction, or publication check failed."""


@dataclass(frozen=True)
class ReviewExportResult:
    status: str
    package_status: str
    experiment_id: str
    run_id: str
    path: str
    files: int
    package_bytes: int
    target_size_exceeded: bool


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReviewPackageError(f"review record is not finite JSON data: {exc}") from exc


def _json_bytes(value: Any) -> bytes:
    _canonical_json(value)
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _yaml_bytes(value: Any) -> bytes:
    _canonical_json(value)
    try:
        return yaml.safe_dump(value, sort_keys=True, allow_unicode=True, default_flow_style=False).encode("utf-8")
    except (yaml.YAMLError, TypeError, ValueError) as exc:
        raise ReviewPackageError(f"review config cannot be serialized: {exc}") from exc


def _sanitize_text(text: str, redactions: list[str], location: str) -> str:
    original = text
    text = SECRET_PATTERN.sub("<REDACTED>", text)
    text = UNIX_PATH_PATTERN.sub("<REDACTED_PATH>", text)
    text = WINDOWS_PATH_PATTERN.sub("<REDACTED_PATH>", text)
    if text != original:
        redactions.append(location)
    return text


def _sanitize(value: Any, redactions: list[str], location: str = "$", key: str | None = None) -> Any:
    if key is not None and SENSITIVE_KEY_PATTERN.search(key):
        if value is not None:
            redactions.append(location)
        return "<REDACTED>" if value is not None else None
    if isinstance(value, Mapping):
        if any(not isinstance(name, str) for name in value):
            raise ReviewPackageError(f"review mapping keys must be strings at {location}")
        return {
            name: _sanitize(item, redactions, f"{location}.{name}", name)
            for name, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, redactions, f"{location}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, str):
        return _sanitize_text(value, redactions, location)
    if value is None or isinstance(value, (bool, int, float)):
        try:
            _canonical_json(value)
        except ReviewPackageError as exc:
            raise ReviewPackageError(f"nonfinite review value at {location}; use explicit null and status") from exc
        return value
    raise ReviewPackageError(f"unsupported review value at {location}: {type(value).__name__}")


def _valid_png(payload: bytes) -> bool:
    signature = b"\x89PNG\r\n\x1a\n"
    if not payload.startswith(signature):
        return False
    offset = len(signature)
    chunks = []
    while offset < len(payload):
        if offset + 12 > len(payload):
            return False
        length = int.from_bytes(payload[offset:offset + 4], "big")
        chunk_type = payload[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(payload) or any(
            not (65 <= byte <= 90 or 97 <= byte <= 122) for byte in chunk_type
        ):
            return False
        chunk_data = payload[offset + 8:offset + 8 + length]
        expected_crc = int.from_bytes(payload[offset + 8 + length:end], "big")
        if binascii.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != expected_crc:
            return False
        name = chunk_type.decode("ascii", errors="strict")
        if not chunks and (name != "IHDR" or length != 13):
            return False
        if name[0].isupper() and name not in {"IHDR", "PLTE", "IDAT", "IEND"}:
            return False
        chunks.append(name)
        offset = end
        if name == "IEND":
            return length == 0 and offset == len(payload) and "IDAT" in chunks and chunks.count("IHDR") == 1
    return False


def _strip_png_metadata(payload: bytes) -> tuple[bytes, bool]:
    if not _valid_png(payload):
        raise ReviewPackageError("optional PNG plot is malformed")
    signature = b"\x89PNG\r\n\x1a\n"
    safe_chunks = {"IHDR", "PLTE", "IDAT", "IEND", "tRNS"}
    output = bytearray(signature)
    offset = len(signature)
    stripped = False
    while offset < len(payload):
        length = int.from_bytes(payload[offset:offset + 4], "big")
        end = offset + 12 + length
        chunk = payload[offset:end]
        name = payload[offset + 4:offset + 8].decode("ascii")
        if name in safe_chunks:
            output.extend(chunk)
        else:
            stripped = True
        offset = end
    return bytes(output), stripped


def _scan_redaction(directory: Path) -> list[str]:
    findings = []
    for path in sorted(directory.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            findings.append(f"symlink:{path.relative_to(directory).as_posix()}")
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() == ".png":
            payload = path.read_bytes()
            if not _valid_png(payload):
                findings.append(f"invalid-png:{path.relative_to(directory).as_posix()}")
                continue
            # Inspect literal metadata/text bytes as a conservative backstop.
            text = payload.decode("latin-1")
        else:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeError:
                findings.append(f"non-text:{path.relative_to(directory).as_posix()}")
                continue
        if SECRET_PATTERN.search(text):
            findings.append(f"secret:{path.relative_to(directory).as_posix()}")
        if UNIX_PATH_PATTERN.search(text) or WINDOWS_PATH_PATTERN.search(text):
            findings.append(f"absolute-path:{path.relative_to(directory).as_posix()}")
    return findings


def _open_raw_file(run_path: Path, relative: str) -> int:
    if not isinstance(relative, str) or "\\" in relative:
        raise ReviewPackageError(f"raw artifact path is unsafe: {relative!r}")
    pure = PurePosixPath(relative)
    if (pure.is_absolute() or not pure.parts or pure.as_posix() != relative
            or any(part in ("", ".", "..") for part in pure.parts)):
        raise ReviewPackageError(f"raw artifact path is unsafe: {relative!r}")
    parent_fd = None
    try:
        parent_fd = store._open_directory_chain(run_path)
        for part in pure.parts[:-1]:
            child_fd = os.open(
                part, os.O_RDONLY | store._O_DIRECTORY | store._O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            os.close(parent_fd)
            parent_fd = child_fd
        descriptor = os.open(
            pure.parts[-1],
            os.O_RDONLY | store._O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_fd,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise ReviewPackageError(f"raw artifact is not a regular file: {relative}")
        return descriptor
    except ReviewPackageError:
        raise
    except (OSError, ValueError) as exc:
        raise ReviewPackageError(f"raw artifact cannot be opened safely: {relative}") from exc
    finally:
        if parent_fd is not None:
            os.close(parent_fd)


def _read_raw_file(run_path: Path, relative: str) -> bytes:
    descriptor = _open_raw_file(run_path, relative)
    try:
        chunks = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                return b"".join(chunks)
            chunks.append(block)
    except OSError as exc:
        raise ReviewPackageError(f"raw artifact cannot be read: {relative}") from exc
    finally:
        os.close(descriptor)


def _read_verified_raw_file(run_path: Path, relative: str, expected: Mapping[str, Any]) -> bytes:
    data = _read_raw_file(run_path, relative)
    if len(data) != expected.get("bytes") or _sha256(data) != expected.get("sha256"):
        raise ReviewPackageError(f"raw artifact changed between integrity check and read: {relative}")
    return data


def _hash_raw_file(run_path: Path, relative: str) -> dict[str, Any]:
    descriptor = _open_raw_file(run_path, relative)
    digest = hashlib.sha256()
    size = 0
    try:
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            size += len(block)
    except OSError as exc:
        raise ReviewPackageError(f"raw artifact cannot be hashed: {relative}") from exc
    finally:
        os.close(descriptor)
    return {"sha256": digest.hexdigest(), "bytes": size}


def _read_and_hash_raw_file(run_path: Path, relative: str, *, max_bytes: int) -> tuple[dict[str, Any], bytes]:
    descriptor = _open_raw_file(run_path, relative)
    digest = hashlib.sha256()
    chunks = []
    size = 0
    try:
        if os.fstat(descriptor).st_size > max_bytes:
            raise ReviewPackageError(f"review artifact exceeds the 10 MiB package cap: {relative}")
        while True:
            block = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - size))
            if not block:
                break
            chunks.append(block)
            digest.update(block)
            size += len(block)
            if size > max_bytes:
                raise ReviewPackageError(f"review artifact exceeds the 10 MiB package cap: {relative}")
    except ReviewPackageError:
        raise
    except OSError as exc:
        raise ReviewPackageError(f"raw artifact cannot be read and hashed: {relative}") from exc
    finally:
        os.close(descriptor)
    return {"sha256": digest.hexdigest(), "bytes": size}, b"".join(chunks)


def _verify_checkpoint_state(run_path: Path, checkpoint_state: Mapping[str, Any], run_id: str) -> bool:
    root = run_path / "checkpoints"
    streams = checkpoint_state.get("streams")
    if not isinstance(streams, list):
        raise ReviewPackageError("checkpoint state has no stream roster")
    if not root.exists() and not root.is_symlink():
        if streams:
            raise ReviewPackageError("checkpoint manifest references an absent checkpoint directory")
        metadata_dir = run_path / "metadata"
        if (metadata_dir.exists() or metadata_dir.is_symlink()) and any(
            (metadata_dir / name).exists() or (metadata_dir / name).is_symlink()
            for name in ("recovery_policy.json", "run_completion.json")
        ):
            raise ReviewPackageError("checkpoint recovery metadata exists without checkpoint streams")
        if checkpoint_state.get("recovery_artifacts", {}):
            raise ReviewPackageError("checkpoint recovery metadata exists without checkpoint streams")
        return True
    if root.is_symlink() or not root.is_dir():
        raise ReviewPackageError("checkpoint root is unsafe")
    actual_names = sorted(path.name for path in root.iterdir())
    declared_names = sorted(item.get("name") for item in streams if isinstance(item, Mapping))
    if actual_names != declared_names:
        raise ReviewPackageError("checkpoint stream roster differs from raw manifest")
    for stream in streams:
        name = stream.get("name")
        if (not isinstance(name, str) or store.CHECKPOINT_STREAM_RE.fullmatch(name) is None
                or stream.get("run_id") != run_id):
            raise ReviewPackageError("checkpoint stream is not bound to this run identity")
        stream_path = root / name
        if stream_path.is_symlink() or not stream_path.is_dir():
            raise ReviewPackageError("checkpoint stream path is unsafe")
        actual = {}
        for path in stream_path.rglob("*"):
            if path.is_symlink():
                raise ReviewPackageError("checkpoint tree contains a symlink")
            if path.is_file():
                relative = path.relative_to(stream_path).as_posix()
                raw_relative = path.relative_to(run_path).as_posix()
                actual[relative] = _hash_raw_file(run_path, raw_relative)
        if actual != stream.get("files"):
            raise ReviewPackageError(f"checkpoint hashes or recovery state changed: {name}")
        retention = actual.get("retention.json")
        if retention is None:
            raise ReviewPackageError(f"checkpoint stream lacks retention policy: {name}")
        try:
            policy = json.loads(_read_verified_raw_file(
                run_path, f"checkpoints/{name}/retention.json", retention,
            ))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ReviewPackageError("checkpoint retention metadata is invalid") from exc
        expected_files = {"latest": "latest.json", "previous": "previous.json", "final": "final.json"}
        if (policy.get("format_version") != 1 or policy.get("policy") != "rolling_latest_previous"
                or policy.get("state") != stream.get("status")
                or any(policy.get(key) != filename for key, filename in expected_files.items())):
            raise ReviewPackageError("checkpoint retention policy and manifest state disagree")

    metadata_dir = run_path / "metadata"
    recovery = checkpoint_state.get("recovery_artifacts", {})
    if not isinstance(recovery, Mapping):
        raise ReviewPackageError("checkpoint recovery artifact map is invalid")
    actual_recovery = {}
    if metadata_dir.exists() or metadata_dir.is_symlink():
        if metadata_dir.is_symlink() or not metadata_dir.is_dir():
            raise ReviewPackageError("checkpoint recovery metadata path is unsafe")
        for filename in ("recovery_policy.json", "run_completion.json"):
            artifact = metadata_dir / filename
            if artifact.exists() or artifact.is_symlink():
                if artifact.is_symlink() or not artifact.is_file():
                    raise ReviewPackageError("checkpoint recovery metadata file is unsafe")
                actual_recovery[filename] = _hash_raw_file(run_path, f"metadata/{filename}")
    if actual_recovery != dict(recovery):
        raise ReviewPackageError("checkpoint recovery metadata hash mismatch")
    if "recovery_policy.json" in actual_recovery:
        policy = json.loads(_read_verified_raw_file(
            run_path, "metadata/recovery_policy.json", actual_recovery["recovery_policy.json"],
        ))
        final_present = any("final.json" in stream.get("files", {}) for stream in streams)
        pinned_count = sum(
            relative.startswith("pinned/") and relative.endswith(".json")
            for stream in streams for relative in stream.get("files", {})
        )
        if (policy.get("checkpoint_retention_count") != 2
                or policy.get("final_checkpoint_present") is not final_present
                or policy.get("pinned_checkpoint_count") != pinned_count):
            raise ReviewPackageError("checkpoint recovery policy disagrees with retained stream state")
    return True


def _verify_manifest_and_raw(run_path: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    # Validate the path-derived root before opening any run file. This prevents
    # an export attempt from reading a historical/repository-local raw manifest.
    if run_path.parent.parent.name != "runs":
        raise ReviewPackageError("raw run path must be <external-root>/runs/<experiment_id>/<run_id>")
    try:
        store._validate_experiment_id(run_path.parent.name)
        store._validate_run_id(run_path.name)
        store.validate_data_root(run_path.parent.parent.parent, required_free_bytes=0, read_only=True)
    except (OSError, ValueError) as exc:
        raise ReviewPackageError(f"raw run is not in a trusted external root: {exc}") from exc
    try:
        manifest = store.read_experiment_manifest(run_path)
    except (OSError, ValueError) as exc:
        raise ReviewPackageError(f"raw run identity/provenance is invalid: {exc}") from exc
    experiment_id = manifest.get("experiment_id")
    run_id = manifest.get("run_id")
    if run_path.name != run_id or run_path.parent.name != experiment_id:
        raise ReviewPackageError("raw run path and manifest experiment/run IDs do not match")
    if manifest.get("status") not in {"COMPLETED", "FAILED", "INCOMPLETE"}:
        raise ReviewPackageError("review export requires a durably closed raw run")
    if manifest.get("execution_source_sha") is None:
        raise ReviewPackageError("raw run has no frozen execution source SHA")
    if manifest.get("frozen_provenance_sha256") != store._sha256(store._canonical_json(store._frozen_provenance_payload(manifest))):
        raise ReviewPackageError("frozen source/config/grid/runtime provenance hash mismatch")

    expected = manifest.get("expected_cells")
    cells = manifest.get("cells")
    if not isinstance(expected, list) or not isinstance(cells, list) or not expected:
        raise ReviewPackageError("raw run has no full expected cell roster")
    if [item.get("cell_id") for item in expected] != [item.get("cell_id") for item in cells]:
        raise ReviewPackageError("expected cell roster and persisted cell records differ")
    if store._sha256(store._canonical_json(cells)) != manifest.get("cell_roster_sha256"):
        raise ReviewPackageError("raw cell roster hash mismatch")
    for identity, cell in zip(expected, cells, strict=True):
        for key, value in identity.items():
            if cell.get(key) != value:
                raise ReviewPackageError(f"cell identity changed for {identity.get('cell_id')}: {key}")
        if cell.get("status") not in store.CELL_STATUSES:
            raise ReviewPackageError("cell has an unknown status")
        if cell.get("status") in {"RUNNING", "COMPLETED"} and cell.get("executed") is not True:
            raise ReviewPackageError("running/completed cell lacks an explicit execution record")
        if cell.get("status") == "COMPLETED" and (
            isinstance(cell.get("search_fes"), bool) or not isinstance(cell.get("search_fes"), int)
            or cell["search_fes"] <= 0
        ):
            raise ReviewPackageError("completed cell lacks an observed unique search FE")
        if cell.get("status") == "NOT_STARTED" and (
            cell.get("executed") is not False or cell.get("search_fes") != 0 or cell.get("validation_points") != 0
        ):
            raise ReviewPackageError("not-started cell contains an execution or counter record")
        if cell.get("status") == "NOT_RUN" and (
            cell.get("executed") is True or cell.get("search_fes") != 0 or cell.get("validation_points") != 0
        ):
            raise ReviewPackageError("not-run cell contains an execution or counter record")
        if cell.get("status") == "FAILED" and (not cell.get("reason") or cell.get("failure_class") not in store.FAILURE_CLASSES):
            raise ReviewPackageError("failed cell lacks an explicit failure reason/class")
        if (isinstance(cell.get("search_fes"), bool) or not isinstance(cell.get("search_fes"), int)
                or cell["search_fes"] < 0 or cell["search_fes"] > manifest.get("search_fe_limit_per_cell", 0)):
            raise ReviewPackageError("cell search FE count is outside its frozen per-cell limit")
        if (isinstance(cell.get("validation_points"), bool) or not isinstance(cell.get("validation_points"), int)
                or cell["validation_points"] < 0
                or cell["validation_points"] > manifest.get("validation_point_limit_per_cell", 0)):
            raise ReviewPackageError("cell validation count is outside its frozen per-cell limit")
    run_status = manifest.get("status")
    if run_status == "COMPLETED" and any(cell["status"] != "COMPLETED" for cell in cells):
        raise ReviewPackageError("completed run contains a non-completed expected cell")
    if run_status == "FAILED" and not (
        any(cell["status"] in {"FAILED", "NOT_RUN"} for cell in cells) or manifest.get("errors")
    ):
        raise ReviewPackageError("failed run lacks a failed cell or recorded run error")
    if run_status == "INCOMPLETE" and not any(
        cell["status"] in {"NOT_STARTED", "RUNNING", "INCOMPLETE"} for cell in cells
    ):
        raise ReviewPackageError("incomplete run has no incomplete expected cell")
    if manifest.get("search_fe_count") != sum(cell["search_fes"] for cell in cells):
        raise ReviewPackageError("search FE totals do not reconcile to the cell roster")
    if manifest.get("validation_point_count") != sum(cell["validation_points"] for cell in cells):
        raise ReviewPackageError("validation point totals do not reconcile to the cell roster")
    if manifest["search_fe_count"] > manifest["search_fe_limit_per_cell"] * len(cells):
        raise ReviewPackageError("search FE total exceeds frozen per-cell limits")
    if manifest["validation_point_count"] > manifest["validation_point_limit_per_cell"] * len(cells):
        raise ReviewPackageError("validation total exceeds frozen per-cell limits")

    raw_hashes = manifest.get("raw_artifact_sha256")
    if not isinstance(raw_hashes, dict):
        raise ReviewPackageError("raw artifact hash map is missing")
    required_raw = {"config.yaml", "convergence.csv", "inputs/model.yaml", "inputs/search_grid.yaml", "inputs/validation_grid.yaml"}
    reviewable_raw = required_raw | {"artifacts/comparison.csv", "artifacts/validation.csv"}
    raw_bytes = {}
    cell_ids = {cell["cell_id"] for cell in expected}
    for relative, record in raw_hashes.items():
        if (not isinstance(relative, str) or not isinstance(record, Mapping)
                or not isinstance(record.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None
                or isinstance(record.get("bytes"), bool) or not isinstance(record.get("bytes"), int)
                or record["bytes"] < 0):
            raise ReviewPackageError(f"raw artifact hash record is invalid: {relative}")
        if relative not in required_raw:
            try:
                store._validate_raw_relative(relative, cell_ids=cell_ids)
            except ValueError as exc:
                raise ReviewPackageError(f"raw artifact path is invalid: {relative}: {exc}") from exc
        if relative.startswith("artifacts/plots/"):
            reviewable_raw.add(relative)
        if relative in reviewable_raw:
            actual_hash, data = _read_and_hash_raw_file(
                run_path, relative, max_bytes=HARD_LIMIT_BYTES,
            )
        else:
            actual_hash = _hash_raw_file(run_path, relative)
            data = None
        if actual_hash != {"sha256": record["sha256"], "bytes": record["bytes"]}:
            raise ReviewPackageError(f"raw artifact hash mismatch: {relative}")
        if data is not None:
            raw_bytes[relative] = data
    if not required_raw.issubset(raw_bytes):
        raise ReviewPackageError("raw run is missing frozen config/model/grid artifacts")
    try:
        store._validate_checkpoint_observations(manifest)
    except (KeyError, TypeError, ValueError) as exc:
        raise ReviewPackageError(f"checkpoint observations do not reconcile to executed cell work: {exc}") from exc
    if raw_bytes["convergence.csv"] != store._convergence_csv_bytes(manifest["observed_checkpoints"]):
        raise ReviewPackageError("raw convergence.csv does not match observed checkpoint records")
    try:
        raw_config = yaml.safe_load(raw_bytes["config.yaml"])
        scientific_config_sha = store._sha256(store._canonical_json(raw_config))
    except (yaml.YAMLError, ValueError, TypeError) as exc:
        raise ReviewPackageError(f"raw config is not canonical scientific input: {exc}") from exc
    if scientific_config_sha != manifest.get("scientific_config_sha256"):
        raise ReviewPackageError("scientific config hash mismatch")
    for name in ("model", "search_grid", "validation_grid"):
        try:
            value = yaml.safe_load(raw_bytes[f"inputs/{name}.yaml"])
            digest = store._sha256(store._canonical_json(value))
        except (yaml.YAMLError, ValueError, TypeError) as exc:
            raise ReviewPackageError(f"scientific {name} input is invalid: {exc}") from exc
        if digest != manifest.get("scientific_input_sha256", {}).get(name):
            raise ReviewPackageError(f"scientific {name} grid/model hash mismatch")
    checkpoint_state = manifest.get("checkpoint_state", {})
    _verify_checkpoint_state(run_path, checkpoint_state, run_id)
    registered_files = set(raw_hashes) | {"manifest.json", ".manifest.lock"}
    for stream in checkpoint_state.get("streams", []):
        registered_files.update(
            f"checkpoints/{stream['name']}/{relative}"
            for relative in stream.get("files", {})
        )
    registered_files.update(
        f"metadata/{relative}" for relative in checkpoint_state.get("recovery_artifacts", {})
    )
    for path in run_path.rglob("*"):
        relative = path.relative_to(run_path).as_posix()
        if path.is_symlink():
            raise ReviewPackageError(f"raw run contains a symlink: {relative}")
        if path.is_file() and relative not in registered_files:
            raise ReviewPackageError(f"raw run file is missing its manifest hash: {relative}")
        if not path.is_file() and not path.is_dir():
            raise ReviewPackageError(f"raw run contains a non-regular entry: {relative}")
    return manifest, raw_bytes


def _cell_review_record(cell: Mapping[str, Any]) -> dict[str, Any]:
    result = cell.get("result") or {}
    if not isinstance(result, Mapping):
        raise ReviewPackageError("cell result must be an object or null")
    search_metrics = cell.get("search_metrics", result.get("metrics"))
    search_violations = cell.get("search_violations", result.get("violations"))
    design = cell.get("design", result.get("design"))
    geometry = cell.get("geometry", result.get("geometry"))
    validation_metrics = cell.get("validation_metrics")
    validation_violations = cell.get("validation_violations")
    feasible = cell.get("feasible", result.get("feasible"))
    if cell["status"] == "COMPLETED":
        required = {
            "design": design,
            "geometry": geometry,
            "search_metrics": search_metrics,
            "search_violations": search_violations,
            "feasible": feasible,
        }
        if cell["validation_points"] > 0:
            required["validation_metrics"] = validation_metrics
            required["validation_violations"] = validation_violations
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ReviewPackageError(
                f"completed cell {cell['cell_id']} lacks required review evidence: {', '.join(missing)}"
            )
    return {
        **{key: value for key, value in cell.items() if key not in {"result", "search_metrics", "search_violations", "design", "geometry", "validation_metrics", "validation_violations", "feasible"}},
        "design": design,
        "geometry": geometry,
        "search_metrics": search_metrics,
        "search_violations": search_violations,
        "validation_metrics": validation_metrics,
        "validation_violations": validation_violations,
        "feasible": feasible,
        "result": dict(result),
        "missing_evidence": [
            field for field, value in {
                "design": design, "geometry": geometry, "search_metrics": search_metrics,
                "search_violations": search_violations,
                "validation_metrics": validation_metrics,
                "validation_violations": validation_violations,
            }.items() if value is None
        ],
    }


def _convergence_bytes(manifest: Mapping[str, Any]) -> bytes:
    observations = manifest.get("observed_checkpoints")
    if not isinstance(observations, list):
        raise ReviewPackageError("observed checkpoint records are missing")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CONVERGENCE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    seen = set()
    for item in observations:
        if not isinstance(item, Mapping) or item.get("metric_status") not in {"OBSERVED", "NOT_AVAILABLE"}:
            raise ReviewPackageError("convergence row is not an explicit observed checkpoint")
        key = (item.get("cell_id"), item.get("phase"), item.get("search_fes"), item.get("validation_points"))
        if key in seen:
            raise ReviewPackageError("duplicate convergence checkpoint observation")
        seen.add(key)
        if item.get("phase") not in {"SEARCH", "VALIDATION"}:
            raise ReviewPackageError("convergence checkpoint phase is invalid")
        writer.writerow({column: item.get(column, "") for column in CONVERGENCE_COLUMNS})
    return output.getvalue().encode("utf-8")


def _safe_package_files(stage: Path, expected_files: set[str]) -> set[str]:
    names = set()
    directories = set()
    for path in stage.rglob("*"):
        relative = path.relative_to(stage).as_posix()
        if path.is_symlink():
            raise ReviewPackageError(f"review staging tree contains a symlink: {relative}")
        if path.is_file():
            names.add(relative)
        elif path.is_dir():
            directories.add(relative)
        else:
            raise ReviewPackageError(f"review staging tree contains a non-regular entry: {relative}")
    expected_directories = {
        parent.as_posix()
        for filename in expected_files
        for parent in PurePosixPath(filename).parents
        if parent.as_posix() != "."
    }
    if directories != expected_directories:
        raise ReviewPackageError("review package contains unexpected or missing directories")
    return names


def _atomic_publish(stage: Path, destination: Path) -> None:
    parent_fd = store._open_directory_chain(destination.parent)
    try:
        _stage_parent = stage.parent
        if _stage_parent != destination.parent:
            raise ReviewPackageError("staging package must share the destination filesystem directory")
        store._rename_noreplace_at(parent_fd, stage.name, destination.name)
    finally:
        os.close(parent_fd)


def _verify_existing_package(existing: Path, expected: Mapping[str, bytes], *, experiment_id: str, run_id: str) -> ReviewExportResult:
    if existing.is_symlink() or not existing.is_dir():
        raise ReviewPackageError("existing review destination is not a regular directory")
    if sum(path.stat().st_size for path in existing.rglob("*") if path.is_file()) > HARD_LIMIT_BYTES:
        raise ReviewPackageError("existing review package exceeds the 10 MiB hard limit")
    actual_files = {
        path.relative_to(existing).as_posix(): path.read_bytes()
        for path in existing.rglob("*") if path.is_file() and not path.is_symlink()
    }
    if {path.relative_to(existing).as_posix() for path in existing.rglob("*") if path.is_symlink()}:
        raise ReviewPackageError("existing review package contains a symlink")
    expected_directories = {
        parent.as_posix()
        for filename in expected
        for parent in PurePosixPath(filename).parents
        if parent.as_posix() != "."
    }
    actual_directories = {
        path.relative_to(existing).as_posix()
        for path in existing.rglob("*") if path.is_dir() and not path.is_symlink()
    }
    if actual_directories != expected_directories or actual_files != dict(expected):
        raise ReviewPackageError("existing review package differs from deterministic export; refusing overwrite")
    manifest = json.loads(actual_files["manifest.json"])
    total = sum(len(data) for data in actual_files.values())
    return ReviewExportResult(
        "ALREADY_VALID", manifest["package_status"], experiment_id, run_id,
        str(existing), len(actual_files), total, manifest["target_size_exceeded"],
    )


def _create_destination_parents(destination: Path, repository_root: Path) -> None:
    try:
        relative = destination.parent.relative_to(repository_root)
    except ValueError as exc:
        raise ReviewPackageError("review output path must remain within the repository root") from exc
    try:
        descriptor = store._open_directory_chain(repository_root)
        try:
            for part in relative.parts:
                child, _created = store._mkdir_at(descriptor, part)
                os.close(descriptor)
                descriptor = child
        finally:
            os.close(descriptor)
    except (OSError, ValueError) as exc:
        raise ReviewPackageError(f"review destination parent is not a trusted directory: {exc}") from exc


def export_review_package(
    raw_run_directory: str | os.PathLike[str],
    *,
    repository_root: str | os.PathLike[str],
    destination: str | os.PathLike[str] | None = None,
) -> ReviewExportResult:
    """Build and atomically publish a compact, hash-correlated schema-v1 package."""
    raw_path = Path(raw_run_directory).absolute()
    repository_input = Path(repository_root).absolute()
    try:
        store._assert_no_symlink_components(repository_input, allow_missing_leaf=False)
    except (OSError, ValueError) as exc:
        raise ReviewPackageError(f"repository root path is not trusted: {exc}") from exc
    repository = repository_input.resolve(strict=True)
    if not repository.is_dir():
        raise ReviewPackageError("repository_root must be a directory")
    try:
        manifest, raw_bytes = _verify_manifest_and_raw(raw_path)
    except ReviewPackageError:
        raise
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ReviewPackageError(f"raw run schema is malformed: {exc}") from exc
    experiment_id = store._validate_experiment_id(manifest["experiment_id"])
    run_id = store._validate_run_id(manifest["run_id"])
    canonical = repository / "reports" / "experiments" / experiment_id / run_id
    final = Path(destination).absolute() if destination is not None else canonical
    if final != canonical:
        raise ReviewPackageError("destination must use the exact reports/experiments/<experiment_id>/<run_id> identity path")
    if final == repository or repository not in final.parents:
        raise ReviewPackageError("review package destination escapes repository root")
    if final.exists() or final.is_symlink():
        # Build an exact candidate package first, then compare without overwriting.
        existing = final
    else:
        existing = None

    context = manifest.get("review_context")
    if not isinstance(context, Mapping):
        raise ReviewPackageError("frozen review context is missing")
    if context.get("requires_comparison") and "artifacts/comparison.csv" not in raw_bytes:
        raise ReviewPackageError("comparison review requires artifacts/comparison.csv")
    if context.get("requires_validation") and "artifacts/validation.csv" not in raw_bytes:
        raise ReviewPackageError("physical-response review requires artifacts/validation.csv")
    redactions: list[str] = []
    optional_raw = {}
    if "artifacts/comparison.csv" in raw_bytes:
        optional_raw["comparison.csv"] = raw_bytes["artifacts/comparison.csv"]
    if "artifacts/validation.csv" in raw_bytes:
        optional_raw["validation.csv"] = raw_bytes["artifacts/validation.csv"]
    for name, data in raw_bytes.items():
        if name.startswith("artifacts/plots/"):
            package_name = f"plots/{PurePosixPath(name).name}"
            if package_name in optional_raw:
                raise ReviewPackageError(f"multiple raw plots map to the same review filename: {package_name}")
            if package_name.lower().endswith(".png"):
                data, metadata_removed = _strip_png_metadata(data)
                if metadata_removed:
                    redactions.append(f"{package_name}:png-metadata")
            optional_raw[package_name] = data

    review_config = _sanitize(yaml.safe_load(raw_bytes["config.yaml"]), redactions, "config")
    review_cells = [_cell_review_record(cell) for cell in manifest["cells"]]
    review_cells = _sanitize(review_cells, redactions, "cells")
    review_runtime = _sanitize(manifest["runtime"], redactions, "runtime")
    review_context = _sanitize(context, redactions, "review_context")
    review_errors = _sanitize(manifest["errors"], redactions, "errors")
    convergence = _convergence_bytes(manifest)
    readme = (
        f"# Experiment review: {experiment_id} / {run_id}\n\n"
        f"- Purpose: {review_context['purpose']}\n"
        f"- Conditions: {review_context['conditions']}\n"
        f"- Observed findings: {review_context['findings']}\n"
        f"- Limitations: {review_context['limitations']}\n"
        f"- Review instructions: {review_context['review_instructions']}\n"
        f"- Scientific disposition: `{review_context['scientific_disposition']}`\n\n"
        "This is a claim and compact evidence package awaiting independent review. "
        "Package integrity is not scientific acceptance or authorization for further execution.\n"
    )
    readme = _sanitize_text(readme, redactions, "README.md").encode("utf-8")
    files: dict[str, bytes] = {
        "README.md": readme,
        "config.yaml": _yaml_bytes(review_config),
        "cells.json": _json_bytes(review_cells),
        "convergence.csv": convergence,
        **optional_raw,
    }
    if context["requires_comparison"] and "comparison.csv" not in files:
        raise ReviewPackageError("required comparison evidence is absent")
    if context["requires_validation"] and "validation.csv" not in files:
        raise ReviewPackageError("required validation evidence is absent")

    raw_artifact_hashes = manifest["raw_artifact_sha256"]
    review_hashes_without_checks = {name: _sha256(data) for name, data in files.items()}
    statuses = [cell["status"] for cell in manifest["cells"]]
    status_counts = {status: statuses.count(status) for status in sorted(store.CELL_STATUSES)}
    expected_ids = [cell["cell_id"] for cell in manifest["expected_cells"]]
    present_ids = [cell["cell_id"] for cell in manifest["cells"]]
    checkpoint_consistency = _verify_checkpoint_state(raw_path, manifest["checkpoint_state"], run_id)
    dispatch = manifest["runtime"].get("dispatch_identity", {})
    if not isinstance(dispatch, Mapping) or dispatch.get("status") != "CAPTURED" or not dispatch.get("report"):
        raise ReviewPackageError("numerical dispatch provenance is not captured; package cannot claim READY_FOR_REVIEW")
    checks = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "run_id": run_id,
        "raw_review_ids_match": True,
        "execution_source_sha_valid": bool(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", manifest["execution_source_sha"])),
        "frozen_provenance_sha256": manifest["frozen_provenance_sha256"],
        "config_sha256": manifest["scientific_config_sha256"],
        "scientific_input_sha256": manifest["scientific_input_sha256"],
        "raw_artifact_hashes_valid": True,
        "checkpoint_recovery_consistent": checkpoint_consistency,
        "expected_cell_ids": expected_ids,
        "present_cell_ids": present_ids,
        "missing_cell_ids": [],
        "expected_cell_count": len(expected_ids),
        "present_cell_count": len(present_ids),
        "cell_status_counts": status_counts,
        "all_expected_cells_included": expected_ids == present_ids,
        "all_cells_terminal": all(status in store.TERMINAL_CELL_STATUSES for status in statuses),
        "search_fe_count": manifest["search_fe_count"],
        "validation_point_count": manifest["validation_point_count"],
        "search_and_validation_counts_separate": True,
        "observed_checkpoint_rows_only": True,
        "redacted_fields": sorted(set(redactions)),
        "redaction_status": "PASS",
        "checks_run": ["raw SHA-256", "frozen provenance", "config/model/grid identity", "cell roster", "checkpoint hashes", "redaction", "package size"],
        "checks_not_run": ["COM/FE recalculation", "scientific acceptance", "optimizer qualification"],
        "review_artifact_sha256": review_hashes_without_checks,
        "package_status": "READY_FOR_REVIEW",
    }
    if expected_ids != present_ids or not checks["all_expected_cells_included"]:
        raise ReviewPackageError("review package does not contain the exact frozen cell roster")
    if not checks["execution_source_sha_valid"]:
        raise ReviewPackageError("execution source SHA is invalid")
    files["checks.json"] = _json_bytes(checks)
    review_hashes = {name: _sha256(data) for name, data in files.items()}

    manifest_out = {
        "review_schema_id": REVIEW_SCHEMA_ID,
        "review_schema_version": REVIEW_SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "run_id": run_id,
        "package_status": "READY_FOR_REVIEW",
        "raw_run_status": manifest["status"],
        "created_at_utc": manifest["created_at_utc"],
        "finished_at_utc": manifest["finished_at_utc"],
        "execution_source_sha": manifest["execution_source_sha"],
        "frozen_provenance_sha256": manifest["frozen_provenance_sha256"],
        "runtime": review_runtime,
        "method": manifest["method"],
        "topology": manifest["topology"],
        "seeds": manifest["seeds"],
        "search_fe_limit_per_cell": manifest["search_fe_limit_per_cell"],
        "validation_point_limit_per_cell": manifest["validation_point_limit_per_cell"],
        "search_fe_count": manifest["search_fe_count"],
        "validation_point_count": manifest["validation_point_count"],
        "expected_cells": review_cells,
        "cell_status_counts": status_counts,
        "scientific_config_sha256": manifest["scientific_config_sha256"],
        "raw_config_file_sha256": manifest["config_file_sha256"],
        "review_config_file_sha256": review_hashes["config.yaml"],
        "scientific_input_sha256": manifest["scientific_input_sha256"],
        "raw_artifact_sha256": raw_artifact_hashes,
        "checkpoint_state": _sanitize(manifest["checkpoint_state"], redactions, "checkpoint_state"),
        "errors": review_errors,
        "completeness": {
            "expected_cells": len(expected_ids),
            "present_cells": len(present_ids),
            "terminal_cells": sum(status in store.TERMINAL_CELL_STATUSES for status in statuses),
            "scientifically_completed_cells": status_counts["COMPLETED"],
        },
        "redaction_status": "PASS",
        "review_artifact_sha256": review_hashes,
        "package_artifact_count_excluding_manifest": len(files),
        "package_total_bytes": 0,
        "target_size_bytes": TARGET_BYTES,
        "hard_size_bytes": HARD_LIMIT_BYTES,
        "target_size_exceeded": False,
        "self_hash_excluded": True,
    }
    _canonical_json(manifest_out)

    _create_destination_parents(final, repository)
    stage_name = f".r5-{uuid.uuid4().hex}.tmp"
    stage = final.parent / stage_name
    try:
        stage.mkdir(mode=0o700)
        for name, data in files.items():
            target = stage / Path(*PurePosixPath(name).parts)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not target.parent.resolve(strict=True).is_relative_to(stage.resolve(strict=True)):
                raise ReviewPackageError("review artifact path escapes staging directory")
            target.write_bytes(data)
        (stage / "manifest.json").write_bytes(_json_bytes(manifest_out))
        expected_names = REQUIRED_FILES | set(optional_raw)
        actual_names = _safe_package_files(stage, expected_names)
        if actual_names != expected_names:
            raise ReviewPackageError("review package contains missing or unexpected files")
        redaction_findings = _scan_redaction(stage)
        if redaction_findings:
            raise ReviewPackageError("review package redaction scan failed: " + ", ".join(redaction_findings[:5]))
        total = sum(path.stat().st_size for path in stage.rglob("*") if path.is_file())
        if total > HARD_LIMIT_BYTES:
            raise ReviewPackageError(f"review package exceeds the strict 10 MiB hard size limit ({total} bytes)")
        manifest_out["package_total_bytes"] = total
        manifest_out["target_size_exceeded"] = total > TARGET_BYTES
        # The manifest includes its own final byte count; resolve the small JSON-size fixed point.
        for _ in range(8):
            (stage / "manifest.json").write_bytes(_json_bytes(manifest_out))
            new_total = sum(path.stat().st_size for path in stage.rglob("*") if path.is_file())
            if new_total == manifest_out["package_total_bytes"]:
                break
            manifest_out["package_total_bytes"] = new_total
        (stage / "manifest.json").write_bytes(_json_bytes(manifest_out))
        total = sum(path.stat().st_size for path in stage.rglob("*") if path.is_file())
        if total > HARD_LIMIT_BYTES:
            raise ReviewPackageError(f"review package exceeds the strict 10 MiB hard size limit ({total} bytes)")
        if total != manifest_out["package_total_bytes"]:
            raise ReviewPackageError("review package size did not stabilize during manifest serialization")
        final_files = {
            path.relative_to(stage).as_posix(): path.read_bytes()
            for path in stage.rglob("*") if path.is_file()
        }
        # If a prior output exists, validate byte-for-byte and refuse all overwrites.
        if existing is not None:
            shutil.rmtree(stage)
            stage = None
            return _verify_existing_package(existing, final_files, experiment_id=experiment_id, run_id=run_id)
        _atomic_publish(stage, final)
        stage = None
        return ReviewExportResult(
            "EXPORTED", "READY_FOR_REVIEW", experiment_id, run_id, str(final),
            len(final_files), total, manifest_out["target_size_exceeded"],
        )
    except ReviewPackageError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise ReviewPackageError(f"review package could not be safely published: {exc}") from exc
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)


__all__ = [
    "HARD_LIMIT_BYTES", "REVIEW_SCHEMA_VERSION", "TARGET_BYTES", "ReviewExportResult",
    "ReviewPackageError", "export_review_package",
]
