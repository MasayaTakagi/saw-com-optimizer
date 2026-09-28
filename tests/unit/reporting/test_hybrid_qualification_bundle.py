import tempfile
import zipfile
from pathlib import Path

from sawopt.reporting.hybrid_qualification import (
    STAGE4A_REQUIRED_ARTIFACTS,
    build_stage4a_review_bundle,
    write_stage4a_reports,
)


def test_stage4a_bundle_includes_lifecycle_evidence_and_excludes_checkpoints():
    repository_root = Path(__file__).resolve().parents[3]
    with tempfile.TemporaryDirectory(prefix="stage4a_bundle_case_") as temp:
        run = Path(temp) / Path(temp).name
        run.mkdir()
        for relative in (*STAGE4A_REQUIRED_ARTIFACTS, "REVIEW_ME.md"):
            path = run / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        checkpoint = run / "optimization" / "P_D" / "seed0" / "checkpoints" / "latest.json"
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text('{"payload":"must stay out of review bundle"}\n', encoding="utf-8")
        context = {
            "root": repository_root,
            "computation_paths": (),
            "reporting_paths": (),
        }
        bundle = repository_root / "artifacts" / "review_bundles" / f"{run.name}_review.zip"
        try:
            result = build_stage4a_review_bundle(run, context)
            assert result == bundle
            with zipfile.ZipFile(result) as archive:
                names = set(archive.namelist())
            assert "run/metadata/run_completion.json" in names
            assert "run/metadata/recovery_policy.json" in names
            assert not any(name.startswith("run/optimization/") for name in names)
            assert not any(name.endswith("latest.json") for name in names)
        finally:
            bundle.unlink(missing_ok=True)


def test_review_request_distinguishes_focused_and_full_suite_counts(tmp_path):
    context = {
        "source_impedance_ohm": 50.0,
        "load_impedance_ohm": 50.0,
        "common_grid_id": "fixture-grid",
        "common_frequencies": [1.0],
        "fingerprint": {
            "computation_fingerprint": "fixture-computation",
            "fingerprint_schema_version": 2,
        },
    }
    result = {
        "status": "STAGE4A_SMOKE_COMPLETE",
        "topologies": [],
        "stage4b_runtime_estimate": {
            "low_hours": 0.4, "high_hours": 0.8, "central_hours": 0.6,
        },
    }
    parity = {
        "grids": {"search": {"frequency_count": 1001}, "common": {"frequency_count": 9113}},
        "rtol": 1e-10, "atol": 1e-12,
        "overall_maximum_absolute_difference": 0.0,
    }
    tests = {
        "focused_regressions": {"passed": 29, "failed": 0},
        "full_suite": {"passed": 237, "failed": 0, "subtests_passed": 20},
    }
    write_stage4a_reports(tmp_path, result, context, [], parity, tests)
    report = (tmp_path / "REVIEW_ME.md").read_text(encoding="utf-8")
    assert "Focused regressions: 29 passed, 0 failed." in report
    assert "Full suite: 237 passed, 0 failed, 20 subtests passed." in report
