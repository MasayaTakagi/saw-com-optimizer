import hashlib
import json
import subprocess
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from sawopt.orchestration.administrative_closeout import (
    AdministrativeCloseoutError,
    finalize_orphaned_failure,
)
from sawopt.orchestration.models import RunManifest, RunStatus
from sawopt.orchestration.run_manager import (
    atomic_write_json,
    load_status,
    optimizer_completion_path,
    transition,
)


def _review_spec():
    return {
        "spec_id": "fixture",
        "stage": "stage4c",
        "study_types": ["fixture"],
        "required_artifacts": [],
        "required_globs": [],
        "target_size_bytes": 1,
        "hard_size_bytes": 2,
    }


def _manifest(repo: Path, run_dir: Path, run_id: str, source_sha: str) -> RunManifest:
    spec = _review_spec()
    spec_sha = hashlib.sha256(json.dumps(
        spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    return RunManifest(
        schema_version=4,
        run_id=run_id,
        experiment_name="orphan-closeout-fixture",
        created_at=datetime.now(timezone.utc).isoformat(),
        project_root=str(repo),
        run_dir=str(run_dir),
        optimizer_run_dir=str(run_dir / "optimizer"),
        command=["python", "-m", "sawopt"],
        config_path=None,
        codex_session_id=None,
        codex_model=None,
        callback_enabled=False,
        review_after_completion=False,
        continuation_mode="disabled",
        review_stage="stage4c",
        review_contract_version="1",
        review_output_dir=f"reports/experiment_reviews/stage4c/{run_id}",
        review_spec_id="fixture",
        review_spec_sha256=spec_sha,
        review_spec=spec,
        source_commit_sha=source_sha,
        source_branch="fixture",
        study_type="fixture",
        run_storage_policy="external_persistent_v1",
        persistent_run_root=str(run_dir.parent),
        repository_root_at_launch=str(repo),
        source_worktree_at_launch=str(repo),
    )


def _init_repo(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=repo, check=True)


def _commit_evidence(repo: Path, payload: dict) -> Path:
    path = repo / "reports" / "administrative_run_closeouts" / f"{payload['run_id']}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    subprocess.run(["git", "add", path.relative_to(repo).as_posix()], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "closeout evidence"], cwd=repo, check=True, capture_output=True)
    return path


class AdministrativeCloseoutTests(unittest.TestCase):
    def _fixture(self, *, source_sha="a" * 40):
        temporary = TemporaryDirectory()
        root = Path(temporary.name)
        repo = root / "repo"
        repo.mkdir()
        _init_repo(repo)
        run_dir = root / "production" / "run-1"
        run_dir.parent.mkdir()
        manifest = _manifest(repo, run_dir, "run-1", source_sha)
        run_dir.mkdir(parents=True)
        atomic_write_json(run_dir / "run_manifest.json", manifest.to_dict())
        atomic_write_json(run_dir / "status.json", RunStatus(
            state="CREATED", updated_at=manifest.created_at,
            callback_enabled=False, continuation_mode="disabled",
            continuation_state="DISABLED", review_output_dir=manifest.review_output_dir,
        ).to_dict())
        transition(run_dir, "STARTING", worker_pid=111, optimizer_pid=222)
        transition(run_dir, "RUNNING")
        (run_dir / "optimizer" / "checkpoints").mkdir(parents=True)
        sentinel = run_dir / "optimizer" / "checkpoints" / "latest.json"
        sentinel.write_text('{"keep": true}\n', encoding="utf-8")
        evidence = {
            "schema_version": 1,
            "action": "administrative_failure_closeout",
            "run_id": "run-1",
            "source_commit_sha": source_sha,
            "expected_run_dir": str(run_dir.resolve()),
            "expected_worker_pid": 111,
            "expected_optimizer_pid": 222,
            "allowed_preclose_states": ["RUNNING"],
            "failure_class": "MemoryError",
            "reason": "fixture orphan failure",
            "authorization_scope": "close only this run; no resume or relaunch",
        }
        evidence_path = _commit_evidence(repo, evidence)
        return temporary, repo, run_dir, sentinel, evidence_path

    @staticmethod
    def _active(run_dir: Path):
        return ({
            "run_id": "run-1",
            "run_dir": str(run_dir.resolve()),
            "source_head": "a" * 40,
        },)

    def test_closeout_marks_failed_writes_audit_and_releases_registry(self):
        temporary, repo, run_dir, sentinel, evidence_path = self._fixture()
        self.addCleanup(temporary.cleanup)
        with mock.patch("sawopt.orchestration.administrative_closeout.pid_exists", return_value=False), \
                mock.patch("sawopt.orchestration.administrative_closeout.active_runs_for_worktree", return_value=self._active(run_dir)), \
                mock.patch("sawopt.orchestration.administrative_closeout.release_active_run", return_value=True) as release:
            result = finalize_orphaned_failure(
                run_dir, evidence_path.relative_to(repo), repository_root=repo,
                confirm_abandon=True,
            )
        self.assertEqual(result["status"], "CLOSED_FAILED")
        self.assertTrue(result["registry_released"])
        release.assert_called_once_with(repo.resolve(), run_id="run-1")
        status = load_status(run_dir)
        self.assertEqual(status["state"], "FAILED")
        self.assertEqual(status["optimizer_state"], "FAILED")
        self.assertIsNone(status["exit_code"])
        completion = json.loads(optimizer_completion_path(run_dir).read_text(encoding="utf-8"))
        self.assertEqual(completion["disposition"], "FAILED")
        self.assertIsNone(completion["exit_code"])
        audit = json.loads((run_dir / "administrative_failure_closeout.json").read_text(encoding="utf-8"))
        self.assertEqual(audit["run_id"], "run-1")
        self.assertEqual(audit["prior_status"]["state"], "RUNNING")
        self.assertFalse(audit["process_liveness"]["worker_alive"])
        self.assertFalse(audit["process_liveness"]["optimizer_alive"])
        self.assertTrue(sentinel.is_file())

    def test_live_optimizer_fails_before_mutating_run_or_registry(self):
        temporary, repo, run_dir, _sentinel, evidence_path = self._fixture()
        self.addCleanup(temporary.cleanup)
        with mock.patch("sawopt.orchestration.administrative_closeout.pid_exists", side_effect=[False, True]), \
                mock.patch("sawopt.orchestration.administrative_closeout.active_runs_for_worktree") as active, \
                mock.patch("sawopt.orchestration.administrative_closeout.release_active_run") as release:
            with self.assertRaisesRegex(AdministrativeCloseoutError, "still running"):
                finalize_orphaned_failure(
                    run_dir, evidence_path.relative_to(repo), repository_root=repo,
                    confirm_abandon=True,
                )
        self.assertEqual(load_status(run_dir)["state"], "RUNNING")
        self.assertFalse((run_dir / "administrative_failure_closeout.json").exists())
        self.assertFalse(optimizer_completion_path(run_dir).exists())
        active.assert_not_called()
        release.assert_not_called()

    def test_source_sha_mismatch_fails_closed(self):
        temporary, repo, run_dir, _sentinel, evidence_path = self._fixture()
        self.addCleanup(temporary.cleanup)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        payload["source_commit_sha"] = "b" * 40
        evidence_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "add", evidence_path.relative_to(repo).as_posix()], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "mismatched evidence"], cwd=repo, check=True, capture_output=True)
        with mock.patch("sawopt.orchestration.administrative_closeout.pid_exists", return_value=False), \
                mock.patch("sawopt.orchestration.administrative_closeout.release_active_run") as release:
            with self.assertRaisesRegex(AdministrativeCloseoutError, "source commit"):
                finalize_orphaned_failure(
                    run_dir, evidence_path.relative_to(repo), repository_root=repo,
                    confirm_abandon=True,
                )
        self.assertEqual(load_status(run_dir)["state"], "RUNNING")
        release.assert_not_called()

    def test_matching_audit_allows_retry_after_interrupted_closeout(self):
        temporary, repo, run_dir, _sentinel, evidence_path = self._fixture()
        self.addCleanup(temporary.cleanup)
        with mock.patch("sawopt.orchestration.administrative_closeout.pid_exists", return_value=False), \
                mock.patch("sawopt.orchestration.administrative_closeout.active_runs_for_worktree", return_value=self._active(run_dir)), \
                mock.patch("sawopt.orchestration.administrative_closeout.record_optimizer_completion", side_effect=OSError("fixture interruption")), \
                mock.patch("sawopt.orchestration.administrative_closeout.release_active_run") as release:
            with self.assertRaisesRegex(OSError, "fixture interruption"):
                finalize_orphaned_failure(
                    run_dir, evidence_path.relative_to(repo), repository_root=repo,
                    confirm_abandon=True,
                )
            release.assert_not_called()
        self.assertEqual(load_status(run_dir)["state"], "RUNNING")
        self.assertTrue((run_dir / "administrative_failure_closeout.json").is_file())
        with mock.patch("sawopt.orchestration.administrative_closeout.pid_exists", return_value=False), \
                mock.patch("sawopt.orchestration.administrative_closeout.active_runs_for_worktree", return_value=self._active(run_dir)), \
                mock.patch("sawopt.orchestration.administrative_closeout.release_active_run", return_value=True):
            result = finalize_orphaned_failure(
                run_dir, evidence_path.relative_to(repo), repository_root=repo,
                confirm_abandon=True,
            )
        self.assertEqual(result["status"], "CLOSED_FAILED")
        self.assertEqual(load_status(run_dir)["state"], "FAILED")

    def test_same_reviewed_evidence_is_idempotent_after_success(self):
        temporary, repo, run_dir, _sentinel, evidence_path = self._fixture()
        self.addCleanup(temporary.cleanup)
        with mock.patch("sawopt.orchestration.administrative_closeout.pid_exists", return_value=False), \
                mock.patch("sawopt.orchestration.administrative_closeout.active_runs_for_worktree", side_effect=[self._active(run_dir), ()]), \
                mock.patch("sawopt.orchestration.administrative_closeout.release_active_run", return_value=True):
            first = finalize_orphaned_failure(
                run_dir, evidence_path.relative_to(repo), repository_root=repo,
                confirm_abandon=True,
            )
            second = finalize_orphaned_failure(
                run_dir, evidence_path.relative_to(repo), repository_root=repo,
                confirm_abandon=True,
            )
        self.assertEqual(first["status"], "CLOSED_FAILED")
        self.assertEqual(second["status"], "ALREADY_CLOSED_FAILED")

    def test_explicit_confirmation_is_required(self):
        temporary, repo, run_dir, _sentinel, evidence_path = self._fixture()
        self.addCleanup(temporary.cleanup)
        with self.assertRaisesRegex(PermissionError, "confirm-abandon"):
            finalize_orphaned_failure(
                run_dir, evidence_path.relative_to(repo), repository_root=repo,
                confirm_abandon=False,
            )
        self.assertEqual(load_status(run_dir)["state"], "RUNNING")


if __name__ == "__main__":
    unittest.main()
