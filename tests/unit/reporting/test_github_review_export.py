import csv
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import yaml

from sawopt.reporting.github_review import (
    ARTIFACT_COLUMNS,
    ReviewExportError,
    _canonical_json_sha256,
    _validate_spec,
    export_review,
)


ROOT = Path(__file__).resolve().parents[3]
RUN_ID = "qualification-test-001"


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _repo_with_spec(root: Path) -> None:
    spec_dir = root / "configs" / "review_specs"
    spec_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        ROOT / "configs" / "review_specs" / "postrun_workflow_qualification.yaml",
        spec_dir / "postrun_workflow_qualification.yaml",
    )


def _fixture(root: Path, *, schema=2, oversized=False, run_directory: Path | None = None) -> Path:
    _repo_with_spec(root)
    run = Path(run_directory) if run_directory is not None else root / "runs" / RUN_ID
    run.mkdir(parents=True, exist_ok=True)
    study_type = "postrun_workflow_qualification"
    spec = yaml.safe_load((root / "configs/review_specs/postrun_workflow_qualification.yaml").read_text(encoding="utf-8"))
    metadata = {
        "study_type": study_type, "comparison_arms": ["fixture"],
        "seeds": ["qualification"], "expected_cell_count": 1,
        "computation_fingerprint": "e" * 64,
    }
    manifest = {
        "schema_version": schema, "run_id": RUN_ID,
        "experiment_name": study_type,
        "created_at": "2026-10-04T00:00:00+00:00",
        "project_root": str(root), "run_dir": str(run),
        "optimizer_run_dir": str(run / "optimizer"),
        "command": ["synthetic"], "config_path": None,
        "codex_session_id": None, "callback_enabled": False,
        "review_after_completion": False, "experiment_metadata": metadata,
        "study_type": study_type, "source_commit_sha": "f" * 40,
        "source_branch": "codex/test-fixture",
    }
    if schema == 4:
        spec["hard_size_bytes"] = 1000 if oversized else 10 * 1024 * 1024
        spec["target_size_bytes"] = 500 if oversized else 2 * 1024 * 1024
        manifest.update({
            "continuation_mode": "disabled", "codex_session_id": None,
            "original_thread_id": None, "callback_enabled": False,
            "review_after_completion": False, "queue_timeout_seconds": None,
            "review_stage": "qualification", "review_contract_version": "1",
            "review_output_dir": f"reports/experiment_reviews/qualification/{RUN_ID}",
            "review_spec_id": "postrun_workflow_qualification",
            "review_spec": spec, "review_spec_sha256": _canonical_json_sha256(spec),
        })
    _write_json(run / "run_manifest.json", manifest)
    _write_json(run / "status.json", {
        "state": "COMPLETED", "optimizer_state": "COMPLETED", "exit_code": 0,
        "updated_at": "2026-10-04T00:00:02+00:00", "finished_at": "2026-10-04T00:00:02+00:00",
    })
    optimizer = run / "optimizer"
    metadata_dir = optimizer / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    _write_json(metadata_dir / "run_completion.json", {"status": "COMPLETED", "disposition": "COMPLETED"})
    (metadata_dir / "config_snapshot.yaml").write_text("study: synthetic\n", encoding="utf-8")
    _write_json(metadata_dir / "protocol_snapshot.json", {"study_type": study_type, "ranking_eligible": False})
    _write_json(metadata_dir / "integrity_check.json", {
        "status": "PASS", "complete": True, "cells_expected": 1,
        "cells_present": 1, "cells_completed": 1,
        "arms_present": ["fixture"], "seeds_present": ["qualification"],
    })
    summary = optimizer / "summary"
    summary.mkdir(parents=True)
    summary_path = summary / "primary_summary.csv"
    summary_path.write_text(
        "arm,seed,status,ranking_eligible\nfixture,qualification,COMPLETED,false\n",
        encoding="utf-8",
    )
    if oversized:
        summary_path.write_text("x" * 2048, encoding="utf-8")
    (summary / "scientific_limitations.md").write_text("Synthetic only.\n", encoding="utf-8")
    cell = optimizer / "cells" / "fixture"
    _write_json(cell / "qualification_result.json", {
        "arm": "fixture", "seed": "qualification", "status": "COMPLETED",
        "ranking_eligible": False, "source_commit_sha": "f" * 40,
        "computation_fingerprint": "e" * 64,
    })
    _write_json(cell / "qualification_status.json", {
        "arm": "fixture", "seed": "qualification", "status": "COMPLETED",
        "source_commit_sha": "f" * 40, "computation_fingerprint": "e" * 64,
    })
    excluded = optimizer / "cells" / "fixture" / "checkpoints"
    excluded.mkdir()
    (excluded / "B4000.json").write_text("{}", encoding="utf-8")
    (run / "stdout.log").write_text("large logs stay local\n", encoding="utf-8")
    return run


class GitHubReviewExportTests(unittest.TestCase):
    def test_default_destination_uses_manifest_stage_and_run_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = _fixture(root)
            result = export_review(run, repository_root=root)
            self.assertEqual(
                Path(result["path"]),
                root / "reports/experiment_reviews/qualification" / RUN_ID,
            )

    def test_byte_copies_hashes_and_manifest_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            run = _fixture(root)
            destination = base / "export"
            result = export_review(run, destination=destination, repository_root=root)
            self.assertEqual(result["status"], "EXPORTED")
            with (destination / "artifact_manifest.csv").open("r", encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(tuple(rows[0].keys()), ARTIFACT_COLUMNS)
            for row in rows:
                if row["included"] == "true":
                    copied = destination / Path(*row["destination_path"].split("/"))
                    self.assertEqual(row["source_sha256"], row["destination_sha256"])
                    self.assertEqual(hashlib.sha256(copied.read_bytes()).hexdigest(), row["source_sha256"])
            review = json.loads((destination / "review_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(review["run_id"], RUN_ID)
            self.assertEqual(review["expected_cell_count"], 1)
            self.assertEqual(review["completed_cell_count"], 1)
            self.assertEqual(review["redaction_scan"], "PASS")
            self.assertEqual(review["package_complete"], True)
            self.assertFalse(any(
                "checkpoints" in path.relative_to(destination).as_posix().casefold()
                for path in destination.rglob("*")
            ))
            self.assertFalse(any(path.name == "B4000.json" for path in destination.rglob("*")))
            self.assertFalse((destination / "stdout.log").exists())

    def test_external_raw_run_exports_to_repository_canonical_path_without_changing_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository = base / "source-repository"
            external_raw = base / "persistent-runs" / RUN_ID
            run = _fixture(repository, run_directory=external_raw)
            before = {
                path.relative_to(run).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in run.rglob("*") if path.is_file()
            }
            result = export_review(run, repository_root=repository)
            self.assertEqual(result["status"], "EXPORTED")
            expected = repository / "reports/experiment_reviews/qualification" / RUN_ID
            self.assertEqual(Path(result["path"]), expected)
            self.assertFalse(Path(result["path"]).is_relative_to(run))
            review = json.loads((expected / "review_manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(review["package_complete"])
            self.assertEqual(review["redaction_scan"], "PASS")
            with (expected / "artifact_manifest.csv").open("r", encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertTrue(rows)
            self.assertTrue(all(row["source_sha256"] == row["destination_sha256"]
                                for row in rows if row["included"] == "true"))
            after = {
                path.relative_to(run).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in run.rglob("*") if path.is_file()
            }
            self.assertEqual(before, after)

    def test_retired_queue_review_export_preserves_run_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = _fixture(root, schema=4)
            manifest_path = run / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            thread_id = "01a0e89c-1c65-72a3-beb6-489f0cf01b30"
            manifest.update({
                "continuation_mode": "queue", "review_after_completion": True,
                "original_thread_id": thread_id, "next_expected_step": "publish_review_evidence",
                "delivery_sentinel": "a" * 32, "queue_timeout_seconds": 120.0,
                "queue_preflight": {
                    "status": "PASS", "thread_id": thread_id,
                    "codex_executable": "historical-codex", "codex_version": "historical",
                    "explicit_thread": True, "explicit_message": True,
                },
            })
            _write_json(manifest_path, manifest)
            status_path = run / "status.json"
            before = status_path.read_bytes()

            result = export_review(run, repository_root=root)

            self.assertEqual(result["status"], "EXPORTED")
            self.assertTrue(Path(result["path"]).is_dir())
            self.assertEqual(status_path.read_bytes(), before)

    def test_required_missing_artifact_and_traversal_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = _fixture(root)
            (run / "optimizer/metadata/integrity_check.json").unlink()
            with self.assertRaisesRegex(ReviewExportError, "required artifact is missing"):
                export_review(run, destination=root / "out", repository_root=root)
        with self.assertRaises(ReviewExportError):
            _validate_spec({
                "stage": "test", "study_types": [], "target_size_bytes": 10,
                "hard_size_bytes": 20,
                "required_artifacts": [{"source": "../secret", "destination": "secret", "category": "x"}],
                "required_globs": [],
            })

    def test_required_globs_and_incomplete_cell_matrix_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = _fixture(root)
            (run / "optimizer/cells/fixture/qualification_status.json").unlink()
            with self.assertRaisesRegex(ReviewExportError, "terminal cell matrix incomplete|required glob matched no terminal artifacts"):
                export_review(run, destination=root / "out", repository_root=root)

    def test_identical_export_is_idempotent_and_conflicting_destination_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = _fixture(root)
            destination = root / "export"
            first = export_review(run, destination=destination, repository_root=root)
            second = export_review(run, destination=destination, repository_root=root)
            self.assertEqual(first["status"], "EXPORTED")
            self.assertEqual(second["status"], "ALREADY_VALID")
            (destination / "README.md").write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ReviewExportError, "README hash"):
                export_review(run, destination=destination, repository_root=root)

    def test_export_does_not_wait_review_and_publication_requires_pushed_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            root = temporary_root / "repo"
            root.mkdir()
            persistent_root = temporary_root / "persistent-runs"
            persistent_root.mkdir()
            run = _fixture(root, schema=4, run_directory=persistent_root / RUN_ID)
            manifest_path = run / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update({
                "run_storage_policy": "external_persistent_v1",
                "persistent_run_root": str(persistent_root),
                "repository_root_at_launch": str(root),
                "source_worktree_at_launch": str(root),
            })
            _write_json(manifest_path, manifest)
            def git(*args):
                result = subprocess.run(
                    ["git", *args], cwd=root, check=False, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True,
                )
                if result.returncode:
                    raise AssertionError(result.stderr)
                return result.stdout.strip()
            git("init", "-b", "codex/test-review-publication")
            git("config", "user.name", "Test User")
            git("config", "user.email", "test@example.invalid")
            git("commit", "--allow-empty", "-m", "source baseline")

            from sawopt.orchestration.active_runs import (
                active_runs_for_worktree,
                initialize_active_run_registry,
                register_active_run,
            )

            initialize_active_run_registry(
                root, confirm_no_unregistered_active_runs=True,
            )
            register_active_run(
                root, run_id=RUN_ID, run_dir=run, source_worktree=root,
                source_head=git("rev-parse", "HEAD"),
                source_branch="codex/test-review-publication",
            )

            result = export_review(run, repository_root=root)
            self.assertEqual(result["status"], "EXPORTED")
            status = json.loads((run / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "COMPLETED")
            self.assertEqual(status["review_evidence_state"], "EXPORTED")

            from sawopt.orchestration.run_manager import mark_review_published

            review_path = f"reports/experiment_reviews/qualification/{RUN_ID}"
            with self.assertRaises(subprocess.CalledProcessError):
                mark_review_published(
                    run, review_path=review_path,
                    branch="codex/test-review-publication", commit="missing-commit",
                )
            self.assertEqual(
                json.loads((run / "status.json").read_text(encoding="utf-8"))["state"],
                "COMPLETED",
            )

            git("add", review_path)
            git("commit", "-m", "publish synthetic review evidence")
            commit = git("rev-parse", "HEAD")
            # Model the local remote-tracking state produced by a successful
            # push without spawning Git's network/remote shell helper.
            git("config", "remote.origin.url", str(root / "remote.git"))
            git("config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
            git("update-ref", "refs/remotes/origin/codex/test-review-publication", commit)
            git("branch", "--set-upstream-to=origin/codex/test-review-publication")
            status = mark_review_published(
                run, review_path=review_path,
                branch="codex/test-review-publication", commit=commit,
            )
            self.assertEqual(status["state"], "REVIEW_WAITING")
            self.assertEqual(status["review_evidence_state"], "PUBLISHED")
            self.assertEqual(status["optimizer_state"], "COMPLETED")
            self.assertEqual(active_runs_for_worktree(root, root), ())
            repeated = mark_review_published(
                run, review_path=review_path,
                branch="codex/test-review-publication", commit=commit,
            )
            self.assertEqual(repeated["state"], "REVIEW_WAITING")
            self.assertEqual(active_runs_for_worktree(root, root), ())

    def test_redaction_hit_blocks_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = _fixture(root)
            result_path = run / "optimizer/cells/fixture/qualification_result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["access_token"] = "abcdefghijklmno"
            _write_json(result_path, result)
            with self.assertRaisesRegex(ReviewExportError, "redaction scan failed"):
                export_review(run, destination=root / "out", repository_root=root)

    def test_configured_hard_size_gate_blocks_oversize_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = _fixture(root, schema=4, oversized=True)
            with self.assertRaisesRegex(ReviewExportError, "hard size gate"):
                export_review(run, destination=root / "out", repository_root=root)


if __name__ == "__main__":
    unittest.main()
