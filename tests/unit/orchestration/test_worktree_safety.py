import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from sawopt.orchestration import worktree_safety


class WorktreeSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repository = self.base / "repo"
        self.worktree = self.base / "disposable"
        self.repository.mkdir()
        self.git(self.repository, "init", "-b", "main")
        self.git(self.repository, "config", "user.name", "Safety Test")
        self.git(self.repository, "config", "user.email", "safety@example.invalid")
        (self.repository / ".gitignore").write_text(
            "runs/\n.pytest-tmp/\n.pytest_cache/\nignored.dat\n", encoding="utf-8",
        )
        (self.repository / "tracked.txt").write_text("baseline\n", encoding="utf-8")
        self.git(self.repository, "add", ".gitignore", "tracked.txt")
        self.git(self.repository, "commit", "-m", "baseline")
        self.git(self.repository, "worktree", "add", "--detach", str(self.worktree), "HEAD")
        worktree_safety.initialize_active_run_registry(
            self.repository, confirm_no_unregistered_active_runs=True,
        )

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def git(cwd: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=cwd, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False,
        )
        if result.returncode:
            raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
        return result.stdout.decode("utf-8", errors="replace").strip()

    def audit(self):
        return worktree_safety.audit_worktree(self.worktree, repository_root=self.repository)

    def test_clean_registered_disposable_worktree_is_allowed(self):
        audit = self.audit()
        self.assertTrue(audit.registered)
        self.assertTrue(audit.filesystem_inventory_complete)
        self.assertEqual(audit.classification, "WORKTREE_REMOVE_ALLOWED")
        self.assertTrue(audit.deletion_allowed)

    def test_uninitialized_registry_fails_closed(self):
        registry = worktree_safety.registry_directory(self.repository)
        for entry in registry.iterdir():
            entry.unlink()
        registry.rmdir()
        audit = self.audit()
        self.assertFalse(audit.deletion_allowed)
        self.assertEqual(audit.classification, "FAIL_ACTIVE_RUN_REGISTRY_UNINITIALIZED")

    def test_active_run_blocks_worktree_until_explicit_release(self):
        identity = next(
            item for item in worktree_safety._worktree_identities(self.repository)
            if worktree_safety._path_equal(item.path, self.worktree)
        )
        worktree_safety.register_active_run(
            self.repository, run_id="20261004_test001", run_dir=self.base / "runs" / "external",
            source_worktree=self.worktree, source_head=identity.head,
            source_branch=identity.branch,
        )
        audit = self.audit()
        self.assertFalse(audit.deletion_allowed)
        self.assertEqual(audit.classification, "WORKTREE_REMOVE_BLOCKED_ACTIVE_RUN")
        self.assertEqual(audit.active_runs, ("20261004_test001",))
        self.assertTrue(worktree_safety.release_active_run(self.repository, run_id="20261004_test001"))
        self.assertTrue(self.audit().deletion_allowed)

    def test_corrupt_active_run_registry_fails_closed(self):
        registry = worktree_safety.registry_directory(self.repository)
        (registry / "broken.json").write_text("{broken", encoding="utf-8")
        audit = self.audit()
        self.assertFalse(audit.deletion_allowed)
        self.assertEqual(audit.classification, "FAIL_ACTIVE_RUN_REGISTRY_INVALID")

    def test_clean_removal_uses_git_and_verifies_both_postconditions(self):
        result = worktree_safety.remove_worktree(self.worktree, repository_root=self.repository)
        self.assertEqual(result.classification, "WORKTREE_REMOVED")
        self.assertTrue(result.deletion_allowed)
        self.assertTrue(result.remove_invoked)
        self.assertFalse(result.path_exists_after)
        self.assertFalse(result.registered_after)

    def test_tracked_modification_blocks_removal(self):
        (self.worktree / "tracked.txt").write_text("changed\n", encoding="utf-8")
        audit = self.audit()
        self.assertFalse(audit.deletion_allowed)
        self.assertEqual(audit.classification, "WORKTREE_REMOVE_BLOCKED_TRACKED_CHANGES")

    def test_untracked_file_blocks_removal(self):
        (self.worktree / "new.txt").write_text("untracked\n", encoding="utf-8")
        audit = self.audit()
        self.assertTrue(audit.untracked_files)
        self.assertEqual(audit.classification, "WORKTREE_REMOVE_BLOCKED_NONTRACKED_DATA")

    def test_ignored_file_blocks_removal(self):
        (self.worktree / "ignored.dat").write_text("ignored\n", encoding="utf-8")
        self.assertEqual(self.git(self.worktree, "status", "--short"), "")
        audit = self.audit()
        self.assertTrue(audit.ignored_files)
        self.assertFalse(audit.deletion_allowed)

    def test_ignored_pytest_tmp_blocks_removal(self):
        protected = self.worktree / ".pytest-tmp" / "attempt" / "state.bin"
        protected.parent.mkdir(parents=True)
        protected.write_bytes(b"temporary state")
        self.assertEqual(self.git(self.worktree, "status", "--short"), "")
        audit = self.audit()
        self.assertIn(".pytest-tmp/attempt/state.bin", audit.ignored_files)
        self.assertIn(".pytest-tmp/attempt/state.bin", audit.protected_paths)
        self.assertEqual(audit.classification, "WORKTREE_REMOVE_BLOCKED_NONTRACKED_DATA")

    def test_runs_directory_blocks_removal_even_with_clean_git_status(self):
        result = self.worktree / "runs" / "protected" / "result.json"
        result.parent.mkdir(parents=True)
        result.write_text("{}\n", encoding="utf-8")
        self.assertEqual(self.git(self.worktree, "status", "--short"), "")
        audit = self.audit()
        self.assertIn("runs/protected/result.json", audit.ignored_files)
        self.assertIn("runs/protected/result.json", audit.protected_paths)
        self.assertEqual(audit.classification, "WORKTREE_REMOVE_BLOCKED_NONTRACKED_DATA")

    def test_exact_incident_regression_blocks_ignored_run_and_never_calls_remove(self):
        result = self.worktree / "runs" / "protected" / "result.json"
        result.parent.mkdir(parents=True)
        result.write_text('{"valuable":true}\n', encoding="utf-8")
        self.assertEqual(self.git(self.worktree, "status", "--short"), "")
        actual_run = worktree_safety.subprocess.run
        remove_calls = []

        def spy(command, *args, **kwargs):
            if command[:3] == ["git", "worktree", "remove"]:
                remove_calls.append(command)
            return actual_run(command, *args, **kwargs)

        with mock.patch.object(worktree_safety.subprocess, "run", side_effect=spy):
            result_state = worktree_safety.remove_worktree(
                self.worktree, repository_root=self.repository,
            )
        self.assertFalse(result_state.deletion_allowed)
        self.assertFalse(result_state.remove_invoked)
        self.assertEqual(result_state.classification, "WORKTREE_REMOVE_BLOCKED_NONTRACKED_DATA")
        self.assertEqual(remove_calls, [])
        self.assertTrue(result.exists())

    def test_filesystem_inventory_error_blocks_removal(self):
        with mock.patch.object(worktree_safety, "_filesystem_inventory", side_effect=PermissionError("denied")):
            audit = self.audit()
        self.assertFalse(audit.deletion_allowed)
        self.assertFalse(audit.filesystem_inventory_complete)
        self.assertEqual(audit.classification, "FAIL_INCOMPLETE_FILESYSTEM_INVENTORY")

    def test_reparse_point_blocks_removal(self):
        inventory = {
            "file_count": 1, "total_bytes": 0, "protected_paths": (),
            "reparse_points": ("linked-output",), "inaccessible_paths": (),
            "complete": True,
        }
        with mock.patch.object(worktree_safety, "_filesystem_inventory", return_value=inventory):
            audit = self.audit()
        self.assertFalse(audit.deletion_allowed)
        self.assertEqual(audit.classification, "WORKTREE_REMOVE_BLOCKED_REPARSE_POINT")

    def test_unregistered_residual_is_never_removed(self):
        residual = self.base / "residual"
        residual.mkdir()
        marker = residual / "keep.txt"
        marker.write_text("leave", encoding="utf-8")
        removal = worktree_safety.remove_worktree(residual, repository_root=self.repository)
        self.assertEqual(removal.classification, "FAIL_UNREGISTERED_WORKTREE")
        self.assertFalse(removal.remove_invoked)
        self.assertTrue(marker.exists())

    def test_windows_path_identity_is_case_insensitive_and_component_aware(self):
        self.assertTrue(worktree_safety._path_equal(r"C:\Repo\Tree", r"c:\repo\tree", windows=True))
        self.assertFalse(worktree_safety._path_equal(r"C:\Repository", r"C:\Repo", windows=True))

    def test_identity_change_between_audit_and_remove_blocks_mutation(self):
        identity = worktree_safety._worktree_identities(self.repository)
        target = next(item for item in identity if worktree_safety._path_equal(item.path, self.worktree))
        first = worktree_safety.WorktreeAudit(
            str(self.worktree), "WORKTREE_REMOVE_ALLOWED", True, True, False, target,
            filesystem_inventory_complete=True,
        )
        changed = worktree_safety.WorktreeIdentity(target.path, "f" * 40, target.branch)
        second = worktree_safety.WorktreeAudit(
            str(self.worktree), "WORKTREE_REMOVE_ALLOWED", True, True, False, changed,
            filesystem_inventory_complete=True,
        )
        actual_run = worktree_safety.subprocess.run
        remove_calls = []

        def spy(command, *args, **kwargs):
            if command[:3] == ["git", "worktree", "remove"]:
                remove_calls.append(command)
            return actual_run(command, *args, **kwargs)

        with mock.patch.object(worktree_safety, "audit_worktree", side_effect=[first, second]), \
                mock.patch.object(worktree_safety.subprocess, "run", side_effect=spy):
            result = worktree_safety.remove_worktree(self.worktree, repository_root=self.repository)
        self.assertEqual(result.classification, "WORKTREE_REMOVE_BLOCKED_IDENTITY_CHANGED")
        self.assertFalse(result.remove_invoked)
        self.assertEqual(remove_calls, [])
        self.assertTrue(self.worktree.exists())

    def test_git_remove_error_never_falls_back_to_filesystem_delete(self):
        actual_run = worktree_safety.subprocess.run
        remove_calls = []

        def fail_remove(command, *args, **kwargs):
            if command[:3] == ["git", "worktree", "remove"]:
                remove_calls.append(command)
                return subprocess.CompletedProcess(command, 1, b"", b"simulated failure")
            return actual_run(command, *args, **kwargs)

        with mock.patch.object(worktree_safety.subprocess, "run", side_effect=fail_remove):
            result = worktree_safety.remove_worktree(self.worktree, repository_root=self.repository)
        self.assertEqual(result.classification, "WORKTREE_REMOVE_FAILED")
        self.assertTrue(result.remove_invoked)
        self.assertEqual(len(remove_calls), 1)
        self.assertTrue(self.worktree.exists())

    def test_deregistered_directory_is_preserved_and_reported(self):
        actual_identities = worktree_safety._worktree_identities
        calls = 0

        def identities_after_simulated_remove(root):
            nonlocal calls
            calls += 1
            values = actual_identities(root)
            if calls >= 4:
                return tuple(item for item in values if not worktree_safety._path_equal(item.path, self.worktree))
            return values

        actual_run = worktree_safety.subprocess.run

        def simulated_remove(command, *args, **kwargs):
            if command[:3] == ["git", "worktree", "remove"]:
                return subprocess.CompletedProcess(command, 0, b"", b"")
            return actual_run(command, *args, **kwargs)

        with mock.patch.object(worktree_safety, "_worktree_identities", side_effect=identities_after_simulated_remove), \
                mock.patch.object(worktree_safety.subprocess, "run", side_effect=simulated_remove):
            result = worktree_safety.remove_worktree(self.worktree, repository_root=self.repository)
        self.assertEqual(result.classification, "WORKTREE_DEREGISTERED_RESIDUAL_DIRECTORY_REMAINS")
        self.assertTrue(result.path_exists_after)
        self.assertFalse(result.registered_after)
        self.assertTrue(self.worktree.exists())


if __name__ == "__main__":
    unittest.main()
