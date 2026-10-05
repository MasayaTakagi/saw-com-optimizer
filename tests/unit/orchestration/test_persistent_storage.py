import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sawopt.orchestration import persistent_storage


class PersistentStorageTests(unittest.TestCase):
    def test_absolute_destination_outside_all_worktrees_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository = base / "repo"
            worktree = base / "linked"
            external = base / "persistent" / "run-001"
            repository.mkdir()
            worktree.mkdir()
            external.parent.mkdir()
            result = persistent_storage.validate_persistent_run_location(
                external, repository, worktree_roots=(repository, worktree),
            )
            self.assertEqual(result.classification, "PASS_EXTERNAL_PERSISTENT")
            self.assertTrue(result.passed)

    def test_primary_and_linked_worktree_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repo"
            linked = Path(temporary) / "linked"
            repository.mkdir()
            linked.mkdir()
            for candidate in (repository / "runs" / "new", linked / "runs" / "new"):
                result = persistent_storage.validate_persistent_run_location(
                    candidate, repository, worktree_roots=(repository, linked),
                )
                self.assertEqual(result.classification, "FAIL_INSIDE_WORKTREE")

    def test_relative_path_is_rejected(self):
        result = persistent_storage.validate_persistent_run_location(
            Path("runs/new"), Path.cwd(), worktree_roots=(Path.cwd(),),
        )
        self.assertEqual(result.classification, "FAIL_RELATIVE_PATH")

    def test_exact_worktree_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            result = persistent_storage.validate_persistent_run_location(
                root, root, worktree_roots=(root,),
            )
            self.assertEqual(result.classification, "FAIL_INSIDE_WORKTREE")

    def test_git_worktree_discovery_failure_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(persistent_storage, "discover_worktree_roots", side_effect=RuntimeError("git unavailable")):
                result = persistent_storage.validate_persistent_run_location(
                    root / "outside" / "run", root, worktree_roots=None,
                )
            self.assertEqual(result.classification, "FAIL_WORKTREE_DISCOVERY")
            self.assertFalse(result.passed)

    def test_existing_destination_is_a_conflict_even_when_empty(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "persistent" / "run"
            destination.mkdir(parents=True)
            result = persistent_storage.validate_persistent_run_location(
                destination, root, worktree_roots=(root / "repo",),
            )
            self.assertEqual(result.classification, "FAIL_DESTINATION_CONFLICT")

    def test_git_and_review_publication_roots_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            for candidate in (root / ".git" / "objects", root / "reports" / "experiment_reviews" / "stage" / "run"):
                result = persistent_storage.validate_persistent_run_location(
                    candidate, root, worktree_roots=(),
                )
                self.assertEqual(result.classification, "FAIL_INSIDE_WORKTREE")

    def test_reparse_point_path_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "outside").mkdir()
            with mock.patch.object(persistent_storage, "_has_reparse_component", return_value=True):
                result = persistent_storage.validate_persistent_run_location(
                    root / "outside" / "run", root, worktree_roots=(root / "repo",),
                )
            self.assertEqual(result.classification, "FAIL_REPARSE_POINT")

    def test_unwritable_parent_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(persistent_storage, "_probe_writable", side_effect=PermissionError("denied")):
                result = persistent_storage.validate_persistent_run_location(
                    root / "run", root, worktree_roots=(root / "repo",),
                )
            self.assertEqual(result.classification, "FAIL_DESTINATION_CONFLICT")

    def test_windows_paths_compare_case_insensitively_by_components(self):
        self.assertTrue(persistent_storage._same_or_below(
            r"C:\Repo\runs\result", r"c:\repo",
        ))
        self.assertFalse(persistent_storage._same_or_below(
            r"C:\Repository\runs", r"C:\Repo",
        ))

    def test_porcelain_zero_parser_preserves_paths_with_spaces(self):
        parsed = persistent_storage.parse_worktree_list(
            b"worktree C:/repo with spaces\0HEAD abc123\0branch refs/heads/main\0\0"
        )
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0], Path("C:/repo with spaces"))


if __name__ == "__main__":
    unittest.main()
