import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from sawopt.reporting.review_bundle import (
    BundleValidationError, ReviewBundleSpec, _default_review_bundle_output,
    _git_snapshot, build_review_bundle,
    ignore_checkpoint_entries, is_checkpoint_artifact, write_review_bundle_archive,
)


class ReviewBundle(unittest.TestCase):
    def test_reporting_bundle_module_does_not_import_study_or_optimizer(self):
        repository = Path(__file__).parents[3]
        result = subprocess.run(
            [sys.executable, "-c", (
                "import sys; import sawopt.reporting.review_bundle; "
                "assert not any(name.startswith(('sawopt.studies', 'sawopt.optimizers')) "
                "for name in sys.modules)"
            )],
            cwd=repository,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_checkpoint_artifacts_are_filtered(self):
        self.assertTrue(is_checkpoint_artifact('checkpoints/seed1.json'))
        self.assertTrue(is_checkpoint_artifact('session_checkpoint.json'))
        self.assertFalse(is_checkpoint_artifact('checkpoint_policy.md'))
        self.assertFalse(is_checkpoint_artifact('source/sawopt/io/checkpoints.py'))
        self.assertFalse(is_checkpoint_artifact('checkpoint_accounting.csv'))
        self.assertFalse(is_checkpoint_artifact('results/convergence_summary.json'))
        self.assertEqual(
            ignore_checkpoint_entries('.', ['checkpoints', 'results', 'optimizer_checkpoint.json']),
            ['checkpoints', 'optimizer_checkpoint.json'],
        )

    def test_default_output_is_repository_artifacts_review_bundles(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / 'saw-com-optimizer'
            run = repo / 'runs' / 'example-run'
            self.assertEqual(
                _default_review_bundle_output(run, repo),
                repo / 'artifacts' / 'review_bundles' / 'example-run_review.zip',
            )

    def test_generic_builder_packages_saved_run_without_stage_runner(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / 'repo'
            repo.mkdir()
            (repo / 'numeric.py').write_text('answer = 42\n', encoding='utf-8')
            run = root / 'existing-run'
            (run / 'source_snapshot').mkdir(parents=True)
            (run / 'source_snapshot' / 'old_source.py').write_text('answer = 41\n', encoding='utf-8')
            (run / 'result.csv').write_text('value\n42\n', encoding='utf-8')
            (run / 'input_config.yaml').write_text('value: 42\n', encoding='utf-8')
            (run / 'REVIEW_ME.md').write_text('# Saved result\n', encoding='utf-8')
            (run / 'response.npz').write_bytes(b'large optional response')
            spec = ReviewBundleSpec(
                study_type='small_fixture',
                required_artifacts=('result.csv', 'input_config.yaml', 'REVIEW_ME.md'),
                optional_artifacts=('response.npz',),
                source_paths=('numeric.py',),
            )
            output = root / 'review.zip'
            build_review_bundle(run, output, spec, repo_root=repo)
            with ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn('REVIEW_ME.md', names)
                self.assertIn('run/input_config.yaml', names)
                self.assertIn('optional/response.npz', names)
                self.assertIn('source_snapshot/recorded/old_source.py', names)
                self.assertIn('source_snapshot/current_repository/numeric.py', names)
                manifest = json.loads(archive.read('bundle_manifest.json'))
                self.assertEqual(manifest['study_type'], 'small_fixture')
                self.assertEqual(manifest['snapshot_origin'], 'recorded_run_snapshot')
                self.assertTrue(any(item['path'] == 'run/input_config.yaml' for item in manifest['files']))
                for item in manifest['files']:
                    data = archive.read(item['path'])
                    self.assertEqual(len(data), item['bytes'])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])
                optional = next(item for item in manifest['files'] if item['path'] == 'optional/response.npz')
                self.assertFalse(optional['required'])

    def test_generic_builder_can_omit_large_optional_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / 'existing-run'
            run.mkdir()
            (run / 'REVIEW_ME.md').write_text('review\n', encoding='utf-8')
            (run / 'result.csv').write_text('value\n1\n', encoding='utf-8')
            (run / 'response.npz').write_bytes(b'too large')
            output = root / 'review.zip'
            build_review_bundle(
                run, output,
                ReviewBundleSpec(
                    study_type='fixture', required_artifacts=('result.csv',),
                    optional_artifacts=('response.npz',), max_optional_artifact_bytes=2,
                ),
                repo_root=root,
            )
            with ZipFile(output) as archive:
                manifest = json.loads(archive.read('bundle_manifest.json'))
                self.assertNotIn('optional/response.npz', archive.namelist())
                self.assertEqual(manifest['optional_artifacts_omitted'], ['response.npz'])

    def test_generic_builder_includes_neutral_checkpoint_policy_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / 'completed-run'
            (run / 'metadata').mkdir(parents=True)
            (run / 'checkpoints' / 'seed1').mkdir(parents=True)
            (run / 'REVIEW_ME.md').write_text('review\n', encoding='utf-8')
            (run / 'metadata' / 'recovery_policy.json').write_text(
                '{"checkpoint_policy":"rolling_latest_previous",'
                '"final_checkpoint_present":true}\n', encoding='utf-8',
            )
            (run / 'checkpoints' / 'seed1' / 'final.json').write_text(
                '{"large":"restart state"}\n', encoding='utf-8',
            )
            output = root / 'review.zip'
            build_review_bundle(
                run, output,
                ReviewBundleSpec(
                    study_type='fixture',
                    required_artifacts=('metadata/recovery_policy.json',),
                ),
                repo_root=root,
            )
            with ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn('run/metadata/recovery_policy.json', names)
                self.assertFalse(any(name.endswith('/final.json') for name in names))
                manifest = json.loads(archive.read('bundle_manifest.json'))
                self.assertTrue(any(
                    item['path'] == 'run/metadata/recovery_policy.json'
                    and item['required']
                    for item in manifest['files']
                ))

    def test_staged_archive_supports_legacy_directory_prefix(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            staging = root / 'bundle'
            staging.mkdir()
            (staging / 'REVIEW_ME.md').write_text('review\n', encoding='utf-8')
            output = root / 'review.zip'
            write_review_bundle_archive(
                staging, output, study_type='fixture', run_directory=root,
                required_artifacts=('REVIEW_ME.md',), archive_prefix='bundle_name',
                repository_root=root,
            )
            with ZipFile(output) as archive:
                self.assertIn('bundle_name/REVIEW_ME.md', archive.namelist())
                manifest = json.loads(archive.read('bundle_name/bundle_manifest.json'))
                self.assertTrue(any(
                    item['path'] == 'bundle_name/REVIEW_ME.md'
                    for item in manifest['files']
                ))

    def test_required_checkpoint_validation_report_is_included_but_payloads_are_filtered(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            staging = root / 'bundle'
            staging.mkdir()
            (staging / 'REVIEW_ME.md').write_text('review\n', encoding='utf-8')
            (staging / 'checkpoint_reference_validation.json').write_text(
                '{"status":"PASS"}\n', encoding='utf-8',
            )
            (staging / 'optimizer_checkpoint.json').write_text(
                '{"state":"payload"}\n', encoding='utf-8',
            )
            (staging / 'checkpoints').mkdir()
            (staging / 'checkpoints' / 'checkpoint_reference_validation.json').write_text(
                '{"status":"must stay excluded"}\n', encoding='utf-8',
            )
            output = root / 'review.zip'

            write_review_bundle_archive(
                staging, output, study_type='fixture', run_directory=root,
                required_artifacts=(
                    'REVIEW_ME.md', 'checkpoint_reference_validation.json',
                ),
                repository_root=root,
            )

            with ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn('checkpoint_reference_validation.json', names)
                self.assertNotIn('optimizer_checkpoint.json', names)
                self.assertNotIn(
                    'checkpoints/checkpoint_reference_validation.json', names,
                )

    def test_required_artifact_filtered_from_checkpoint_directory_fails_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            staging = root / 'bundle'
            (staging / 'checkpoints').mkdir(parents=True)
            report = staging / 'checkpoints' / 'required_validation.json'
            report.write_text('{"status":"PASS"}\n', encoding='utf-8')
            with self.assertRaisesRegex(BundleValidationError, 'excluded from the archive'):
                write_review_bundle_archive(
                    staging, root / 'review.zip', study_type='fixture',
                    run_directory=root,
                    required_artifacts=('checkpoints/required_validation.json',),
                    repository_root=root,
                )

    def test_git_snapshot_scopes_patches_but_keeps_full_status(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / 'repo'
            repo.mkdir()
            for name in ('included.py', 'excluded.py', 'staged.py'):
                (repo / name).write_text('value = 1\n', encoding='utf-8')
            commands = (
                ['git', 'init'],
                ['git', 'config', 'user.email', 'review@example.invalid'],
                ['git', 'config', 'user.name', 'Review Fixture'],
                ['git', 'add', 'included.py', 'excluded.py', 'staged.py'],
                ['git', 'commit', '-m', 'fixture'],
            )
            for command in commands:
                subprocess.run(command, cwd=repo, check=True, capture_output=True)

            (repo / 'included.py').write_text('value = 2\n', encoding='utf-8')
            (repo / 'excluded.py').write_text('value = 3\n', encoding='utf-8')
            (repo / 'staged.py').write_text('value = 4\n', encoding='utf-8')
            subprocess.run(['git', 'add', 'staged.py'], cwd=repo, check=True, capture_output=True)

            snapshot = _git_snapshot(repo, ('included.py', 'staged.py'))

            self.assertIn('included.py', snapshot['diff_patch'])
            self.assertNotIn('excluded.py', snapshot['diff_patch'])
            self.assertIn('staged.py', snapshot['staged_diff_patch'])
            self.assertNotIn('excluded.py', snapshot['staged_diff_patch'])
            self.assertIn('excluded.py', snapshot['status_short'])
            self.assertEqual(snapshot['diff_scope'], ['included.py', 'staged.py'])

            staging = repo / 'bundle'
            staging.mkdir()
            (staging / 'REVIEW_ME.md').write_text('review\n', encoding='utf-8')
            output = repo / 'review.zip'
            write_review_bundle_archive(
                staging, output, study_type='fixture', run_directory=repo,
                required_artifacts=('REVIEW_ME.md',), repository_root=repo,
                git_diff_paths=('included.py', 'staged.py'),
            )
            with ZipFile(output) as archive:
                manifest = json.loads(archive.read('bundle_manifest.json'))
                self.assertEqual(manifest['git_diff_scope'], ['included.py', 'staged.py'])
                self.assertIn('excluded.py', manifest['git_status_short'])
                unstaged = archive.read('environment/git/diff_patch.patch').decode()
                self.assertIn('included.py', unstaged)
                self.assertNotIn('excluded.py', unstaged)

    def test_git_diff_scope_rejects_pathspec_patterns(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            staging = root / 'bundle'
            staging.mkdir()
            (staging / 'REVIEW_ME.md').write_text('review\n', encoding='utf-8')
            with self.assertRaisesRegex(BundleValidationError, 'literal repository paths'):
                write_review_bundle_archive(
                    staging, root / 'review.zip', study_type='fixture',
                    run_directory=root, required_artifacts=('REVIEW_ME.md',),
                    repository_root=root, git_diff_paths=('src/*.py',),
                )

    def test_generic_builder_rejects_missing_required_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / 'existing-run'
            run.mkdir()
            with self.assertRaises(BundleValidationError):
                build_review_bundle(
                    run,
                    Path(temp) / 'review.zip',
                    ReviewBundleSpec(study_type='fixture', required_artifacts=('missing.csv',)),
                    repo_root=temp,
                )
