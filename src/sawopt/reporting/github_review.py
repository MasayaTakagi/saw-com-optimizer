"""Deterministic, allowlist-based directory exports for GitHub run review."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

import yaml


EXPORTER_VERSION = "sawopt.github_review_export/1"
REVIEW_CONTRACT_VERSION = "1"
ARTIFACT_COLUMNS = (
    "category", "source_path_sanitized", "source_size_bytes", "source_mtime_utc",
    "source_sha256", "destination_path", "destination_size_bytes",
    "destination_sha256", "included", "reason",
)
TEXT_SUFFIXES = {".csv", ".json", ".jsonl", ".md", ".txt", ".toml", ".ini", ".yaml", ".yml"}
REDACTION_PATTERNS = (
    re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/-]{8,}"),
    re.compile(r"(?i)[\"']?\b(?:access_token|refresh_token|client_secret|admin_token)\b[\"']?\s*[:=]\s*[\"']?(?!<REDACTED>)[A-Za-z0-9._~+/-]{8,}"),
    re.compile(r"(?i)[\"']?\b(?:api[_-]?key|password|secret|token)\b[\"']?\s*[:=]\s*[\"']?(?!<REDACTED>)[A-Za-z0-9._~+/-]{12,}"),
    re.compile(r"(?i)https?://[^\s\"']*(?:trycloudflare\.com|/mcp(?:/|\b))[^\s\"']*"),
    re.compile(r"(?i)https?://[^\s\"']*(?:oauth|authorize|callback)[^\s\"']*"),
    re.compile(r"(?i)\b(?:pairing[_ ]code|cookie)\s*[:=]\s*\S+"),
)
FORBIDDEN_NAMES = {"stdout.log", "stderr.log", "callback.log"}
B_CHECKPOINT_RE = re.compile(r"^B\d+\.json$", re.IGNORECASE)


class ReviewExportError(ValueError):
    """Review package failed path, integrity, redaction, or completeness gates."""


@dataclass(frozen=True)
class _Artifact:
    source: Path
    source_relative: str
    destination_relative: str
    category: str
    required: bool


def _safe_relative(value: str, *, label: str) -> str:
    normalized = str(value).replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ReviewExportError(f"{label} must be a safe relative path: {value!r}")
    if re.match(r"^[A-Za-z]:", normalized):
        raise ReviewExportError(f"{label} must not be drive-qualified: {value!r}")
    return path.as_posix()


def _canonical_json_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_review_spec(spec_id: str, repository_root: str | Path) -> dict[str, Any]:
    """Load the repository's declarative, versioned review allowlist."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", spec_id):
        raise ReviewExportError("invalid review spec identifier")
    path = Path(repository_root).resolve() / "configs" / "review_specs" / f"{spec_id}.yaml"
    if not path.is_file():
        raise ReviewExportError(f"review spec does not exist: {spec_id}")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("spec_id") is None:
        raise ReviewExportError("review spec must be a YAML mapping with spec_id")
    if value["spec_id"] != spec_id and not value["spec_id"].startswith(spec_id + "_"):
        raise ReviewExportError("review spec filename and spec_id do not match")
    _validate_spec(value)
    return value


def _validate_spec(spec: Mapping[str, Any]) -> None:
    for key in ("stage", "study_types", "required_artifacts", "required_globs", "target_size_bytes", "hard_size_bytes"):
        if key not in spec:
            raise ReviewExportError(f"review spec missing {key}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", str(spec["stage"])):
        raise ReviewExportError("review spec stage is invalid")
    if int(spec["target_size_bytes"]) <= 0 or int(spec["hard_size_bytes"]) <= int(spec["target_size_bytes"]):
        raise ReviewExportError("review spec size limits are invalid")
    for group in ("required_artifacts", "optional_artifacts"):
        for entry in spec.get(group, ()):
            _safe_relative(entry["source"], label="artifact source")
            _safe_relative(entry["destination"], label="artifact destination")
            if not entry.get("category"):
                raise ReviewExportError("artifact specification requires a category")
    for group in ("required_globs", "optional_globs"):
        for entry in spec.get(group, ()):
            pattern = _safe_relative(entry["source_pattern"], label="glob source")
            if ".." in pattern.split("/") or not entry.get("destination") or not entry.get("category"):
                raise ReviewExportError("glob specification is invalid")
            try:
                re.compile(entry["capture_regex"])
            except re.error as exc:
                raise ReviewExportError("glob capture_regex is invalid") from exc
            _safe_relative(str(entry["destination"]).replace("{arm}", "arm").replace("{seed}", "seed"), label="glob destination")


def _git(root: Path, *args: str, check: bool = True) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", check=False,
        )
    except OSError as exc:
        raise ReviewExportError("Git provenance could not be read") from exc
    if check and result.returncode != 0:
        raise ReviewExportError(f"Git command failed: {args[0]}")
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_forbidden(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if any(part.casefold() in {"checkpoints", "checkpoint"} for part in parts):
        return True
    name = parts[-1] if parts else ""
    return name.casefold() in FORBIDDEN_NAMES or bool(B_CHECKPOINT_RE.fullmatch(name)) or "rollout" in name.casefold()


def _resolve_source(root: Path, relative: str) -> Path:
    safe = _safe_relative(relative, label="source path")
    path = root / Path(*safe.split("/"))
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ReviewExportError(f"source path escapes run root: {relative}") from exc
    if path.is_symlink():
        raise ReviewExportError(f"symlinked source artifacts are not accepted: {relative}")
    return path


def _expand_glob(root: Path, entry: Mapping[str, Any], *, required: bool) -> list[_Artifact]:
    pattern = _safe_relative(str(entry["source_pattern"]), label="glob pattern")
    regex = re.compile(str(entry["capture_regex"]))
    found: list[_Artifact] = []
    for candidate in sorted(root.glob(pattern)):
        relative = candidate.relative_to(root).as_posix()
        if not candidate.is_file():
            continue
        if _is_forbidden(relative):
            continue
        try:
            candidate.resolve(strict=True).relative_to(root.resolve())
        except (ValueError, OSError) as exc:
            raise ReviewExportError(f"glob result escapes or is unavailable: {relative}") from exc
        if candidate.is_symlink():
            raise ReviewExportError(f"symlinked glob result is not accepted: {relative}")
        match = regex.fullmatch(relative)
        if not match:
            raise ReviewExportError(f"glob result does not match capture contract: {relative}")
        values = match.groupdict()
        try:
            destination = str(entry["destination"]).format(**values)
        except (KeyError, IndexError) as exc:
            raise ReviewExportError("glob destination references an unknown capture") from exc
        destination = _safe_relative(destination, label="glob destination")
        found.append(_Artifact(candidate, relative, destination, str(entry["category"]), required))
    if required and not found:
        raise ReviewExportError(f"required glob matched no terminal artifacts: {pattern}")
    return found


def _nested_values(value: Any, wanted: set[str]) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in wanted and item not in (None, ""):
                found.append(item)
            found.extend(_nested_values(item, wanted))
    elif isinstance(value, list):
        for item in value:
            found.extend(_nested_values(item, wanted))
    return found


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewExportError(f"invalid required JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ReviewExportError(f"required JSON must be an object: {path.name}")
    return value


def _manifest_info(run_root: Path, raw: dict[str, Any], status: dict[str, Any],
                   spec: Mapping[str, Any], review_stage: str) -> dict[str, Any]:
    metadata = raw.get("experiment_metadata") or {}
    stage_manifest_path = run_root / "optimizer" / "metadata" / "stage4b_run_manifest.json"
    stage_manifest = _load_json(stage_manifest_path) if stage_manifest_path.is_file() else {}
    source_sha = raw.get("source_commit_sha") or metadata.get("source_commit_sha") or stage_manifest.get("source_commit_sha")
    fingerprint = metadata.get("computation_fingerprint") or stage_manifest.get("computation_fingerprint")
    protocol_fingerprint = metadata.get("protocol_fingerprint") or stage_manifest.get("protocol_revision")
    study_type = raw.get("study_type") or metadata.get("study_type") or stage_manifest.get("study_type")
    arms = metadata.get("comparison_arms") or metadata.get("topologies")
    seeds = metadata.get("seeds")
    if not arms or not seeds:
        contract = stage_manifest.get("contract", {})
        arms = arms or contract.get("topologies")
        seeds = seeds or contract.get("seeds")
    if not arms or not seeds:
        raise ReviewExportError("run manifest does not declare comparison arms and seeds")
    expected_count = int(metadata.get("expected_cell_count", len(arms) * len(seeds)))
    if expected_count != len(arms) * len(seeds):
        raise ReviewExportError("declared expected cell count does not equal the arm/seed matrix")
    completion = status.get("optimizer_state") or status.get("state")
    exit_code = status.get("exit_code")
    if completion not in {"COMPLETED", "FAILED"}:
        raise ReviewExportError(f"optimizer is not terminal: {completion}")
    if completion == "COMPLETED" and exit_code not in (0, None):
        raise ReviewExportError("optimizer completion and exit code disagree")
    spec_studies = spec.get("study_types", ())
    if study_type and spec_studies and study_type not in spec_studies:
        raise ReviewExportError(f"review spec {spec.get('spec_id')} does not apply to {study_type}")
    return {
        "run_id": str(raw.get("run_id", "")), "stage": review_stage,
        "study_type": study_type, "source_sha": source_sha, "fingerprint": fingerprint,
        "protocol_fingerprint": protocol_fingerprint,
        "arms": list(arms), "seeds": list(seeds), "expected_cell_count": expected_count,
        "optimizer_completion_state": completion, "exit_code": exit_code,
        "experiment_metadata": metadata,
    }


def _collect_artifacts(run_root: Path, spec: Mapping[str, Any]) -> tuple[list[_Artifact], list[dict[str, Any]]]:
    artifacts: list[_Artifact] = []
    rows: list[dict[str, Any]] = []
    for required, group in ((True, "required_artifacts"), (False, "optional_artifacts")):
        for entry in spec.get(group, ()):
            relative = _safe_relative(str(entry["source"]), label="artifact source")
            source = _resolve_source(run_root, relative)
            destination = _safe_relative(str(entry["destination"]), label="artifact destination")
            if not source.is_file():
                if required:
                    raise ReviewExportError(f"required artifact is missing: {relative}")
                rows.append({
                    "category": entry["category"], "source_path_sanitized": relative,
                    "source_size_bytes": "", "source_mtime_utc": "", "source_sha256": "",
                    "destination_path": destination, "destination_size_bytes": "",
                    "destination_sha256": "", "included": "false", "reason": "optional artifact absent",
                })
                continue
            artifacts.append(_Artifact(source, relative, destination, str(entry["category"]), required))
    for required, group in ((True, "required_globs"), (False, "optional_globs")):
        for entry in spec.get(group, ()):
            expanded = _expand_glob(run_root, entry, required=required)
            if required:
                artifacts.extend(expanded)
            else:
                artifacts.extend(expanded)
    destinations = [item.destination_relative.casefold() for item in artifacts]
    if len(destinations) != len(set(destinations)):
        raise ReviewExportError("two review artifacts map to the same destination")
    return artifacts, rows


def _cell_key(item: _Artifact) -> tuple[str, str] | None:
    match = re.match(r"^cells/([^/]+)/([^/]+)_(?:result|status)\.json$", item.destination_relative)
    return (match.group(1), match.group(2)) if match else None


def _validate_matrix(run_root: Path, info: Mapping[str, Any], artifacts: Iterable[_Artifact]) -> int:
    items = list(artifacts)
    integrity_artifact = next((item for item in items if item.category == "integrity"), None)
    if integrity_artifact is None:
        raise ReviewExportError("review spec did not include an integrity artifact")
    integrity = _load_json(integrity_artifact.source)
    if (integrity.get("status") != "PASS" or integrity.get("complete") is not True
            or int(integrity.get("cells_expected", -1)) != int(info["expected_cell_count"])
            or int(integrity.get("cells_present", -1)) != int(info["expected_cell_count"])
            or int(integrity.get("cells_completed", -1)) != int(info["expected_cell_count"])):
        raise ReviewExportError("saved run integrity artifact does not prove a complete matrix")
    integrity_arms = integrity.get("topologies_present") or integrity.get("arms_present")
    integrity_seeds = integrity.get("seeds_present")
    if integrity_arms and {str(x) for x in integrity_arms} != {str(x) for x in info["arms"]}:
        raise ReviewExportError("integrity artifact arm/topology set differs from run manifest")
    if integrity_seeds and {str(x) for x in integrity_seeds} != {str(x) for x in info["seeds"]}:
        raise ReviewExportError("integrity artifact seed set differs from run manifest")
    result_pairs: set[tuple[str, str]] = set()
    status_pairs: set[tuple[str, str]] = set()
    completion_states = {"COMPLETED", "COMPLETE", "SUCCEEDED"}
    for item in items:
        key = _cell_key(item)
        if not key:
            continue
        is_result = item.destination_relative.endswith("_result.json")
        payload = _load_json(item.source)
        if str(payload.get("status", "")).upper() not in completion_states:
            raise ReviewExportError(f"terminal cell artifact is not complete: {item.source_relative}")
        observed_arm = payload.get("arm", payload.get("topology"))
        observed_seed = payload.get("seed")
        if observed_arm is not None and str(observed_arm) != key[0]:
            raise ReviewExportError(f"cell arm/topology disagrees with its path: {item.source_relative}")
        if observed_seed is not None and str(observed_seed) != key[1]:
            raise ReviewExportError(f"cell seed disagrees with its path: {item.source_relative}")
        if is_result:
            result_pairs.add(key)
        else:
            status_pairs.add(key)
    expected = {(str(arm), str(seed)) for arm in info["arms"] for seed in info["seeds"]}
    if result_pairs != expected or status_pairs != expected:
        raise ReviewExportError(
            f"terminal cell matrix incomplete: results={len(result_pairs)}/{len(expected)}, "
            f"statuses={len(status_pairs)}/{len(expected)}"
        )
    return len(result_pairs)


def _check_consistency(artifacts: Iterable[_Artifact], info: Mapping[str, Any]) -> None:
    source_values: set[str] = set()
    fingerprints: set[str] = set()
    run_ids: set[str] = set()
    grid_ids: set[str] = set()
    for item in artifacts:
        if item.source.suffix.casefold() != ".json":
            continue
        value = _load_json(item.source)
        source_values.update(str(v) for v in _nested_values(value, {"source_commit_sha"}))
        fingerprints.update(str(v) for v in _nested_values(value, {"computation_fingerprint"}))
        run_ids.update(str(v) for v in _nested_values(value, {"run_id"}))
        grid_ids.update(str(v) for v in _nested_values(value, {"common_validation_grid_id", "common_grid_id"}))
    expected_source = info.get("source_sha")
    expected_fp = info.get("fingerprint")
    if expected_source and source_values and source_values != {str(expected_source)}:
        raise ReviewExportError("source commit SHA differs across frozen run artifacts")
    if expected_fp and fingerprints and fingerprints != {str(expected_fp)}:
        raise ReviewExportError("computation fingerprint differs across frozen run artifacts")
    if run_ids and run_ids != {str(info["run_id"])}:
        raise ReviewExportError("run ID differs across frozen run artifacts")
    if len(grid_ids) > 1:
        raise ReviewExportError("common grid identity differs across frozen run artifacts")


def _scan_redaction(root: Path) -> list[str]:
    findings: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.casefold() not in TEXT_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(f"non-UTF8 text-like file: {path.relative_to(root).as_posix()}")
            continue
        for pattern in REDACTION_PATTERNS:
            match = pattern.search(content)
            if match:
                findings.append(f"{path.relative_to(root).as_posix()}: {pattern.pattern}")
                break
    return findings


def _verify_existing_package(final: Path, *, run_id: str, source_sha: str | None,
                             fingerprint: str | None, protocol_fingerprint: str | None,
                             spec: Mapping[str, Any],
                             artifacts: Iterable[_Artifact]) -> dict[str, Any]:
    try:
        review_manifest = _load_json(final / "review_manifest.json")
        artifact_manifest_sha = _sha256(final / "artifact_manifest.csv")
        if review_manifest.get("artifact_manifest_sha256") != artifact_manifest_sha:
            raise ReviewExportError("existing package artifact manifest hash mismatch")
        if (review_manifest.get("run_id") != run_id
                or review_manifest.get("production_execution_source_sha") != source_sha
                or review_manifest.get("computation_fingerprint") != fingerprint
                or review_manifest.get("protocol_fingerprint") != protocol_fingerprint
                or review_manifest.get("review_spec_sha256") != _canonical_json_sha256(spec)
                or review_manifest.get("package_complete") is not True
                or review_manifest.get("redaction_scan") != "PASS"):
            raise ReviewExportError("existing review manifest does not match this immutable run/spec")
        if _sha256(final / "README.md") != review_manifest.get("readme_sha256"):
            raise ReviewExportError("existing package README hash mismatch")
        included_rows = {}
        with (final / "artifact_manifest.csv").open("r", encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                if row.get("included", "").casefold() == "true":
                    included_rows[row["destination_path"]] = row
        artifacts_by_destination = {a.destination_relative: a for a in artifacts}
        if set(included_rows) != set(artifacts_by_destination):
            raise ReviewExportError("existing package artifact coverage differs from the frozen spec")
        for destination, row in included_rows.items():
            path = final / Path(*destination.split("/"))
            digest = _sha256(path)
            if digest != row["destination_sha256"] or digest != row["source_sha256"]:
                raise ReviewExportError(f"existing package byte-copy hash mismatch: {destination}")
            # status.json is intentionally a point-in-time artifact: exporter
            # state advances after the first atomic publication.
            if destination != "status.json":
                artifact = artifacts_by_destination[destination]
                if _sha256(artifact.source) != row["source_sha256"]:
                    raise ReviewExportError(f"saved source artifact changed since export: {artifact.source_relative}")
        actual_files = {path.relative_to(final).as_posix() for path in final.rglob("*") if path.is_file()}
        expected_files = set(included_rows) | {"README.md", "review_manifest.json", "artifact_manifest.csv"}
        if actual_files != expected_files:
            raise ReviewExportError("existing review package contains missing or unexpected files")
        if sum(path.stat().st_size for path in final.rglob("*") if path.is_file()) != review_manifest.get("package_total_bytes"):
            raise ReviewExportError("existing package size does not match review manifest")
        if review_manifest["package_total_bytes"] >= int(spec["hard_size_bytes"]):
            raise ReviewExportError("existing package exceeds hard size gate")
        findings = _scan_redaction(final)
        if findings:
            raise ReviewExportError("existing package fails redaction scan")
        return {
            "status": "ALREADY_VALID", "run_id": run_id, "path": str(final),
            "files": len(actual_files), "bytes": review_manifest["package_total_bytes"],
            "cell_count": review_manifest["completed_cell_count"],
            "redaction": "PASS", "completeness": "PASS",
        }
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ReviewExportError("existing destination is not a valid deterministic review package") from exc


def _safe_stage(stage: str, run_id: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", stage):
        raise ReviewExportError("review stage is unsafe")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run_id):
        raise ReviewExportError("run ID is unsafe for a canonical review path")


def _record_review_export_if_supported(run_root: Path) -> None:
    """Keep report export available without writing retired run lifecycle state."""
    from ..orchestration.run_manager import load_manifest, mark_review_exported

    manifest = load_manifest(run_root)
    if (manifest.uses_retired_agent_transport or manifest.study_type in {
        "hybrid_stage4b_topology_comparison", "hybrid_stage4c_confirmatory",
    }):
        return
    mark_review_exported(run_root)


def export_review(run_directory: str | Path, *, destination: str | Path | None = None,
                  repository_root: str | Path | None = None) -> dict[str, Any]:
    """Export deterministic, hashed evidence without modifying run artifacts."""
    run_root = Path(run_directory).resolve()
    if not run_root.is_dir():
        raise ReviewExportError(f"run directory does not exist: {run_root}")
    raw_path, status_path = run_root / "run_manifest.json", run_root / "status.json"
    raw, status = _load_json(raw_path), _load_json(status_path)
    repo = Path(repository_root or raw.get("project_root") or run_root.parent).resolve()
    metadata = raw.get("experiment_metadata") or {}
    stage_manifest_path = run_root / "optimizer" / "metadata" / "stage4b_run_manifest.json"
    stage_manifest = _load_json(stage_manifest_path) if stage_manifest_path.is_file() else {}
    study_type = raw.get("study_type") or metadata.get("study_type") or stage_manifest.get("study_type")

    if int(raw.get("schema_version", 1)) >= 4:
        spec = raw.get("review_spec")
        if not isinstance(spec, dict):
            raise ReviewExportError("schema-v4 manifest has no frozen review spec")
        if _canonical_json_sha256(spec) != raw.get("review_spec_sha256"):
            raise ReviewExportError("frozen review spec hash mismatch")
        stage = str(raw.get("review_stage") or "")
        canonical = str(raw.get("review_output_dir") or "")
    else:
        study_type = raw.get("study_type") or metadata.get("study_type") or stage_manifest.get("study_type")
        spec_id = metadata.get("review_spec_id")
        if not spec_id:
            if study_type == "postrun_workflow_qualification":
                spec_id = "postrun_workflow_qualification"
            elif str(study_type or "").startswith("hybrid_stage4"):
                spec_id = "hybrid_production"
        if not spec_id:
            raise ReviewExportError("historical run has no resolvable review spec")
        spec = load_review_spec(spec_id, repo)
        stage = str(spec["stage"])
        canonical = f"reports/experiment_reviews/{stage}/{raw.get('run_id', '')}"
    if spec.get("spec_id") == "hybrid_stage4c":
        from .hybrid_stage4c import validate_stage4c_review_contract

        validate_stage4c_review_contract(run_root, repo)
    _validate_spec(spec)
    run_id = str(raw.get("run_id", ""))
    _safe_stage(stage, run_id)
    expected_canonical = f"reports/experiment_reviews/{stage}/{run_id}"
    if canonical.replace("\\", "/").strip("/") != expected_canonical:
        raise ReviewExportError("manifest review path is not canonical")
    canonical_path = (repo / expected_canonical).resolve()
    try:
        canonical_path.relative_to(repo)
    except ValueError as exc:
        raise ReviewExportError("canonical review path escapes repository") from exc
    final = Path(destination).resolve() if destination else canonical_path
    try:
        final.relative_to(repo)
    except ValueError:
        if destination is None:
            raise ReviewExportError("canonical destination escapes repository")
        # A caller-supplied test destination may be in a temp root, but must
        # never point into the immutable source run.
        try:
            final.relative_to(run_root)
        except ValueError:
            pass
        else:
            raise ReviewExportError("test destination may not be inside the source run")
    if final == run_root or run_root in final.parents:
        raise ReviewExportError("review output must be separate from source run")

    info = _manifest_info(run_root, raw, status, spec, stage)
    if not info["run_id"]:
        raise ReviewExportError("run manifest has no run ID")
    artifacts, rows = _collect_artifacts(run_root, spec)
    completed_count = _validate_matrix(run_root, info, artifacts)
    _check_consistency(artifacts, info)

    if final.exists():
        result = _verify_existing_package(
            final, run_id=run_id, source_sha=info["source_sha"],
            fingerprint=info["fingerprint"], protocol_fingerprint=info["protocol_fingerprint"],
            spec=spec, artifacts=artifacts,
        )
        if int(raw.get("schema_version", 1)) >= 4 and final == canonical_path:
            _record_review_export_if_supported(run_root)
        return result

    before_hashes = {a.source_relative: _sha256(a.source) for a in artifacts}
    final.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = final.parent / f".r-{secrets.token_hex(6)}"
    stage_dir.mkdir()
    try:
        for artifact in artifacts:
            if _is_forbidden(artifact.source_relative):
                raise ReviewExportError(f"default-excluded artifact selected by spec: {artifact.source_relative}")
            target = stage_dir / Path(*artifact.destination_relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(artifact.source, target)
            source_hash = before_hashes[artifact.source_relative]
            destination_hash = _sha256(target)
            if source_hash != destination_hash:
                raise ReviewExportError(f"byte-copy SHA256 mismatch: {artifact.source_relative}")
            stat = artifact.source.stat()
            rows.append({
                "category": artifact.category,
                "source_path_sanitized": artifact.source_relative,
                "source_size_bytes": stat.st_size,
                "source_mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
                "source_sha256": source_hash,
                "destination_path": artifact.destination_relative,
                "destination_size_bytes": target.stat().st_size,
                "destination_sha256": destination_hash,
                "included": "true", "reason": "required allowlisted copy" if artifact.required else "optional allowlisted copy",
            })

        created_at = status.get("finished_at") or status.get("updated_at") or raw.get("created_at")
        readme = (
            f"# Experiment review evidence: {run_id}\n\n"
            f"- Stage: `{stage}`\n- Study: `{info['study_type'] or 'unspecified'}`\n"
            f"- Optimizer state: `{info['optimizer_completion_state']}` (exit {info['exit_code']})\n"
            f"- Cells: {completed_count}/{info['expected_cell_count']}\n"
            "- This directory is a deterministic compact export from the saved run.\n"
            "- Checkpoint bodies, populations, caches, and process logs are excluded.\n"
        )
        (stage_dir / "README.md").write_text(readme, encoding="utf-8", newline="\n")
        readme_sha256 = _sha256(stage_dir / "README.md")
        with (stage_dir / "artifact_manifest.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=ARTIFACT_COLUMNS, lineterminator="\n")
            writer.writeheader()
            for row in sorted(rows, key=lambda item: str(item["destination_path"])):
                writer.writerow(row)

        branch = raw.get("source_branch") or metadata.get("source_branch")
        if not branch and int(raw.get("schema_version", 1)) >= 4:
            try:
                branch = _git(repo, "branch", "--show-current")
            except ReviewExportError:
                branch = None
        protocol_values = []
        for item in artifacts:
            if item.source.suffix.casefold() == ".json":
                try:
                    protocol_values.extend(_nested_values(_load_json(item.source), {"common_validation_grid_id", "common_grid_id", "grid_identity"}))
                except ReviewExportError:
                    pass
        grids = sorted({str(value) for value in protocol_values})
        review_manifest = {
            "review_schema_version": 1,
            "run_id": run_id,
            "stage": stage,
            "study_type": info["study_type"],
            "production_execution_source_sha": info["source_sha"],
            "computation_fingerprint": info["fingerprint"],
            "protocol_fingerprint": info["protocol_fingerprint"],
            "source_branch": branch,
            "review_branch": _git(repo, "branch", "--show-current", check=False) or None,
            "canonical_review_directory": expected_canonical,
            "optimizer_completion_state": info["optimizer_completion_state"],
            "exit_code": info["exit_code"],
            "expected_cell_count": info["expected_cell_count"],
            "completed_cell_count": completed_count,
            "seeds": info["seeds"], "comparison_arms": info["arms"],
            "evaluation_budget_per_cell": metadata.get("budget_per_cell"),
            "terminal_horizon": metadata.get("population_schedule_terminal_budget"),
            "grid_identity": grids,
            "review_spec_id": spec.get("spec_id"),
            "review_spec_sha256": _canonical_json_sha256(spec),
            "exporter_identity": EXPORTER_VERSION,
            "created_at_utc": created_at,
            "package_complete": True,
            "redaction_scan": "PASS",
            "target_size_bytes": int(spec["target_size_bytes"]),
            "hard_size_bytes": int(spec["hard_size_bytes"]),
            "target_size_exceeded": False,
            "package_total_bytes": 0,
            "artifact_manifest_sha256": _sha256(stage_dir / "artifact_manifest.csv"),
            "readme_sha256": readme_sha256,
        }
        manifest_file = stage_dir / "review_manifest.json"
        for _ in range(3):
            manifest_file.write_text(json.dumps(review_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
            total = sum(path.stat().st_size for path in stage_dir.rglob("*") if path.is_file())
            if total == review_manifest["package_total_bytes"]:
                break
            review_manifest["package_total_bytes"] = total
        manifest_file.write_text(json.dumps(review_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        total_bytes = sum(path.stat().st_size for path in stage_dir.rglob("*") if path.is_file())
        if total_bytes >= int(spec["hard_size_bytes"]):
            raise ReviewExportError(f"review package is {total_bytes} bytes, exceeding the strict hard size gate")
        review_manifest["package_total_bytes"] = total_bytes
        review_manifest["target_size_exceeded"] = total_bytes >= int(spec["target_size_bytes"])
        for _ in range(6):
            manifest_file.write_text(json.dumps(review_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
            actual_bytes = sum(path.stat().st_size for path in stage_dir.rglob("*") if path.is_file())
            if actual_bytes == review_manifest["package_total_bytes"]:
                break
            review_manifest["package_total_bytes"] = actual_bytes
        manifest_file.write_text(json.dumps(review_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        if sum(path.stat().st_size for path in stage_dir.rglob("*") if path.is_file()) >= int(spec["hard_size_bytes"]):
            raise ReviewExportError("review manifest exceeded hard size gate")
        findings = _scan_redaction(stage_dir)
        if findings:
            raise ReviewExportError("redaction scan failed: " + "; ".join(findings[:5]))
        for artifact in artifacts:
            if _sha256(artifact.source) != before_hashes[artifact.source_relative]:
                raise ReviewExportError(f"source run artifact changed during export: {artifact.source_relative}")
        package_index = {
            path.relative_to(stage_dir).as_posix(): _sha256(path)
            for path in stage_dir.rglob("*") if path.is_file()
        }
        os.replace(stage_dir, final)
        stage_dir = None
        if int(raw.get("schema_version", 1)) >= 4 and final == canonical_path:
            _record_review_export_if_supported(run_root)
        return {"status": "EXPORTED", "run_id": run_id, "path": str(final),
                "canonical_path": expected_canonical, "files": len(package_index),
                "bytes": total_bytes, "cell_count": completed_count,
                "redaction": "PASS", "completeness": "PASS",
                "target_size_exceeded": review_manifest["target_size_exceeded"]}
    finally:
        if stage_dir is not None:
            shutil.rmtree(stage_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Export deterministic experiment review evidence")
    parser.add_argument("--run", required=True, help="orchestration run directory")
    parser.add_argument("--destination", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        result = export_review(args.run, destination=args.destination)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
