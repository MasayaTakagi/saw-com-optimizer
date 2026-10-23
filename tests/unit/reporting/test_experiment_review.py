from __future__ import annotations

import binascii
import hashlib
import json
import struct
import zlib
from pathlib import Path

import pytest

from sawopt.io.experiment_store import create_experiment_run
from sawopt.reporting.experiment_review import ReviewPackageError, export_review_package


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE_SHA = "b" * 40
RUN_ID = "20261023T120000Z-deadbeef"


def _png_fixture(*, metadata=b""):
    signature = b"\x89PNG\r\n\x1a\n"

    def chunk(name, data):
        body = name + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)

    return (
        signature
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + (chunk(b"tEXt", metadata) if metadata else b"")
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00\xff"))
        + chunk(b"IEND", b"")
    )


def _create(tmp_path, *, experiment_id="review-schema-test", run_id=RUN_ID, require_comparison=False,
            leave_unrun=False, include_large_raw=False, include_comparison=False, plot_metadata=None):
    expected_cells = [
        {"cell_id": "arm-a-seed-1", "topology": "a", "method": "de", "seed": 1},
        {"cell_id": "arm-b-seed-1", "topology": "b", "method": "de", "seed": 1},
    ]
    if leave_unrun:
        expected_cells.append({"cell_id": "arm-c-seed-1", "topology": "c", "method": "de", "seed": 1})
    data_root = tmp_path / "external-data"
    data_root.parent.mkdir(parents=True, exist_ok=True)
    run = create_experiment_run(
        experiment_id,
        data_root=data_root,
        required_free_bytes=1024 * 1024,
        run_id=run_id,
        source_sha=SOURCE_SHA,
        effective_config={
            "model": {"velocity_m_s": 3480.0},
            "private_input": "/home/alice/private/com.yaml",
            "api_token": "super-secret-value-123456",
        },
        scientific_inputs={
            "model": {"velocity_m_s": 3480.0},
            "search_grid": {"frequencies_hz": [1.0, 2.0]},
            "validation_grid": {"frequencies_hz": [1.0, 1.5, 2.0]},
        },
        expected_cells=expected_cells,
        search_fe_limit=128,
        validation_point_limit=3,
        review_context={
            "purpose": "Synthetic review package test",
            "conditions": "Fixture records only; no optimizer or COM execution",
            "findings": "One completed and one failed fixture cell",
            "limitations": "No scientific result is claimed",
            "review_instructions": "Check the exact roster and hashes",
            "scientific_disposition": "CLAIM_PENDING_REVIEW",
            "requires_comparison": require_comparison,
            "requires_validation": False,
        },
    )
    run.record_cell(
        "arm-a-seed-1", status="COMPLETED", executed=True, search_fes=12,
        validation_points=3,
        result={"feasible": True, "worst_il_db": -18.0},
        design={"x": 0.25}, geometry={"area_um2": 12.0}, feasible=True,
        search_metrics={"worst_il_db": -18.0}, search_violations={"area": 0.0},
        validation_metrics={"worst_il_db": -17.5}, validation_violations={"area": 0.0},
    )
    run.record_cell("arm-b-seed-1", status="FAILED", reason="synthetic injected failure",
                    failure_class="MODEL", search_fes=4, validation_points=0,
                    result={"feasible": None, "worst_il_db": None})
    run.record_checkpoint("arm-a-seed-1", phase="SEARCH", search_fes=8,
                          validation_points=0, metric_name="worst_il_db", metric_value=-17.0,
                          unit="dB", observed_at_utc="2026-10-23T12:01:00Z")
    if include_large_raw:
        run.write_raw_artifact("arrays/search-population.npy", bytes(range(256)) * 4096)
    if include_comparison:
        run.write_artifact("artifacts/comparison.csv", b"cell_id,status,delta\narm-a-seed-1,OBSERVED,0.0\n")
    if plot_metadata is not None:
        run.write_artifact("artifacts/plots/convergence.png", _png_fixture(metadata=plot_metadata))
    run.close(
        status="INCOMPLETE" if leave_unrun else "FAILED",
        errors=[{"classification": "MODEL", "message": "synthetic injected failure"}],
    )
    return run


def _export(run, tmp_path, **kwargs):
    repository = tmp_path / "review-repository"
    repository.mkdir(parents=True, exist_ok=True)
    return export_review_package(
        run.path,
        repository_root=repository,
        **kwargs,
    )


def test_export_has_exact_schema_ids_all_cells_hashes_and_observed_checkpoints(tmp_path):
    run = _create(tmp_path)
    result = _export(run, tmp_path)
    package = Path(result.path)
    assert package == tmp_path / "review-repository/reports/experiments/review-schema-test" / RUN_ID
    assert {path.name for path in package.iterdir()} == {
        "README.md", "manifest.json", "config.yaml", "cells.json", "convergence.csv", "checks.json",
    }
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    checks = json.loads((package / "checks.json").read_text(encoding="utf-8"))
    cells = json.loads((package / "cells.json").read_text(encoding="utf-8"))
    assert manifest["review_schema_id"] == "sawopt.review/1"
    assert manifest["review_schema_version"] == 1
    assert manifest["experiment_id"] == "review-schema-test"
    assert manifest["run_id"] == RUN_ID
    assert manifest["execution_source_sha"] == SOURCE_SHA
    assert manifest["package_status"] == "READY_FOR_REVIEW"
    assert [cell["status"] for cell in cells] == ["COMPLETED", "FAILED"]
    assert checks["expected_cell_count"] == checks["present_cell_count"] == 2
    assert checks["raw_review_ids_match"] is True
    convergence = (package / "convergence.csv").read_text(encoding="utf-8")
    assert (run.path / "convergence.csv").read_bytes() == convergence.encode("utf-8")
    assert convergence.count("OBSERVED") == 1
    assert "2026-10-23T12:01:00Z" in convergence
    assert "FAILED" not in convergence
    for name, digest in manifest["review_artifact_sha256"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == digest
    assert result.package_bytes <= 10 * 1024 * 1024
    assert not list(package.rglob("latest.json"))


def test_large_raw_arrays_are_verified_but_never_copied_into_compact_review(tmp_path):
    run = _create(tmp_path, include_large_raw=True)
    result = _export(run, tmp_path)
    package = Path(result.path)
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["raw_artifact_sha256"]["arrays/search-population.npy"]["bytes"] == 1024 * 1024
    assert not (package / "arrays").exists()
    assert result.package_bytes < 2 * 1024 * 1024


def test_optional_png_plot_metadata_is_stripped_before_review_export(tmp_path):
    run = _create(tmp_path, plot_metadata=b"Comment\x00synthetic plot")
    result = _export(run, tmp_path)
    plot = Path(result.path) / "plots/convergence.png"
    assert plot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    leaking = _create(
        tmp_path / "leaking", run_id="20261023T120000Z-1234abcd",
        plot_metadata=b"Comment\x00api_token=super-secret-value-123",
    )
    leaking_result = _export(leaking, tmp_path / "leaking")
    safe_plot = Path(leaking_result.path) / "plots/convergence.png"
    assert b"super-secret-value-123" not in safe_plot.read_bytes()
    leaking_checks = json.loads((Path(leaking_result.path) / "checks.json").read_text(encoding="utf-8"))
    assert "plots/convergence.png:png-metadata" in leaking_checks["redacted_fields"]


def test_expected_cell_that_never_ran_is_included_as_not_started(tmp_path):
    run = _create(tmp_path, leave_unrun=True)
    result = _export(run, tmp_path)
    package = Path(result.path)
    cells = json.loads((package / "cells.json").read_text(encoding="utf-8"))
    assert len(cells) == 3
    assert cells[2]["cell_id"] == "arm-c-seed-1"
    assert cells[2]["status"] == "NOT_STARTED"
    assert cells[2]["executed"] is False
    checks = json.loads((package / "checks.json").read_text(encoding="utf-8"))
    assert checks["all_expected_cells_included"] is True
    assert checks["all_cells_terminal"] is False


def test_review_export_redacts_secrets_and_private_paths_without_touching_raw(tmp_path):
    run = _create(tmp_path)
    raw_before = (run.path / "config.yaml").read_bytes()
    raw_inventory_before = {path.relative_to(run.path).as_posix() for path in run.path.rglob("*")}
    result = _export(run, tmp_path)
    package = Path(result.path)
    exported_config = (package / "config.yaml").read_text(encoding="utf-8")
    all_text = "\n".join(path.read_text(encoding="utf-8") for path in package.rglob("*") if path.is_file())
    assert "super-secret-value-123456" not in all_text
    assert "/home/alice/private/com.yaml" not in all_text
    assert "<REDACTED>" in exported_config
    assert "<REDACTED_PATH>" in exported_config
    assert (run.path / "config.yaml").read_bytes() == raw_before
    assert {path.relative_to(run.path).as_posix() for path in run.path.rglob("*")} == raw_inventory_before
    checks = json.loads((package / "checks.json").read_text(encoding="utf-8"))
    assert checks["redaction_status"] == "PASS"


def test_short_credentials_in_free_text_are_redacted_before_review(tmp_path):
    run = _create(tmp_path)
    run.update_review_context(findings="fixture leaked password=abc123 and token:'x'")
    result = _export(run, tmp_path)
    package = Path(result.path)
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in package.rglob("*")
        if path.is_file() and path.suffix.lower() != ".png"
    )
    assert "abc123" not in text
    assert "token:'x'" not in text
    checks = json.loads((package / "checks.json").read_text(encoding="utf-8"))
    assert "review_context.findings" in checks["redacted_fields"]
    assert checks["redaction_status"] == "PASS"


def test_package_export_is_deterministic_and_existing_output_is_not_overwritten(tmp_path):
    run = _create(tmp_path)
    first = _export(run, tmp_path / "first")
    second = _export(run, tmp_path / "first")
    assert first.package_status == second.package_status == "READY_FOR_REVIEW"
    package = Path(first.path)
    before = {path.relative_to(package).as_posix(): path.read_bytes() for path in package.rglob("*") if path.is_file()}
    assert second.status == "ALREADY_VALID"
    assert before == {path.relative_to(package).as_posix(): path.read_bytes() for path in package.rglob("*") if path.is_file()}


def test_required_comparison_artifact_and_run_review_ids_are_fail_closed(tmp_path):
    incomplete = _create(tmp_path, require_comparison=True)
    destination_repo = tmp_path / "review-repository"
    destination_repo.mkdir()
    with pytest.raises(ReviewPackageError, match="comparison"):
        export_review_package(incomplete.path, repository_root=destination_repo)

    run = _create(
        tmp_path / "with-comparison", require_comparison=True,
        run_id="20261023T120000Z-beadbead", include_comparison=True,
    )
    with pytest.raises(ReviewPackageError, match="destination|identity|ID"):
        export_review_package(
            run.path,
            repository_root=destination_repo,
            destination=destination_repo / "reports/experiments/other-id" / run.run_id,
        )
    result = export_review_package(run.path, repository_root=destination_repo)
    assert (Path(result.path) / "comparison.csv").is_file()


def test_raw_artifact_parent_symlink_is_rejected_during_descriptor_open(tmp_path):
    run = _create(tmp_path)
    outside = tmp_path / "outside-inputs"
    outside.mkdir()
    (outside / "model.yaml").write_text("velocity_m_s: 1", encoding="utf-8")
    (run.path / "inputs").rename(run.path / "inputs-original")
    (run.path / "inputs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ReviewPackageError, match="safely|symlink"):
        _export(run, tmp_path)


def test_unregistered_raw_output_file_blocks_review_package(tmp_path):
    run = _create(tmp_path)
    orphan = run.path / "logs" / "orphan.log"
    orphan.parent.mkdir()
    orphan.write_text("synthetic orphan", encoding="utf-8")
    with pytest.raises(ReviewPackageError, match="missing its manifest hash"):
        _export(run, tmp_path)


def test_raw_artifact_hash_mismatch_blocks_review_package(tmp_path):
    run = _create(tmp_path)
    (run.path / "config.yaml").write_text("model: tampered\n", encoding="utf-8")
    with pytest.raises(ReviewPackageError, match="hash|integrity"):
        _export(run, tmp_path)
    assert not (tmp_path / "review-repository/reports/experiments" / run.experiment_id / RUN_ID).exists()


def test_failed_or_incomplete_roster_is_never_dropped_and_missing_observations_are_not_filled(tmp_path):
    run = _create(tmp_path)
    # The fixture intentionally has no checkpoint for the second expected cell.
    result = _export(run, tmp_path)
    package = Path(result.path)
    cells = json.loads((package / "cells.json").read_text(encoding="utf-8"))
    assert {cell["cell_id"] for cell in cells} == {"arm-a-seed-1", "arm-b-seed-1"}
    assert (package / "convergence.csv").read_text(encoding="utf-8").count("\n") == 2
    # No saved optimizer checkpoint is copied into the review package.
    assert not any("checkpoint" in path.name.lower() for path in package.rglob("*"))


def test_review_hard_size_limit_is_enforced_including_metadata(tmp_path):
    run = _create(tmp_path)
    too_large = "x" * (10 * 1024 * 1024 + 1)
    run.update_review_context(findings=too_large)
    with pytest.raises(ReviewPackageError, match="10 MiB|size|limit"):
        _export(run, tmp_path)
    assert not (tmp_path / "review-repository/reports/experiments" / run.experiment_id / RUN_ID).exists()


def test_review_package_does_not_claim_ready_when_runtime_provenance_is_incomplete(tmp_path):
    run = _create(tmp_path)
    manifest_path = run.path / "manifest.json"
    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_manifest["runtime"]["dispatch_identity"] = {"status": "UNAVAILABLE"}
    manifest_path.write_text(json.dumps(raw_manifest), encoding="utf-8")
    with pytest.raises(ReviewPackageError, match="dispatch|provenance"):
        _export(run, tmp_path)
