import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from sawopt.reporting.review_bundle import (
    BundleValidationError, _source_hash, create_review_bundle,
)


class ReviewBundle(unittest.TestCase):
    def _make_run(self, root):
        run = Path(root)
        (run / 'trials').mkdir(parents=True)
        (run / 'tests').mkdir()
        trial = 'trials/outer_ports__B10__seed1.json'
        (run / trial).write_text(json.dumps({
            'design': {}, 'seed': 1, 'requested_unique_design_budget': 10,
            'objective_calls': 1, 'unique_decoded_evaluations': 1,
            'metrics': {}, 'violations': {}, 'validated_rank_tuple': [],
            'selected_adaptive_round': 0, 'validation_gap_primary': 0.0,
            'best_so_far_trace': [], 'polish': {},
            'global_search_wall_time_s': 0.0, 'validation_wall_time_s': 0.0,
            'polish_wall_time_s': 0.0, 'diagnostics': {},
        }), encoding='utf-8')
        summary = {
            'study_type': 'stage3_1_dms_convergence',
            'impedance_ohm': 50.0,
            'wirings': ['outer_ports'],
            'budgets_run_by_wiring': {'outer_ports': [10]},
            'cold_seeds': [1],
            'trial_files': [trial],
            'expected_trial_count': 1,
            'unique_design_budgets': [10],
            'statuses': {'outer_ports': {'status': 'inconclusive', 'evidence': {}}},
            'budget_summary': {}, 'performance_gate': {},
            'elapsed_s': 0.1,
        }
        (run / 'convergence_summary.json').write_text(json.dumps(summary), encoding='utf-8')
        (run / 'manifest.json').write_text(json.dumps({
            'source_hash': _source_hash(Path(__file__).parents[3] / 'src' / 'sawopt'),
            'git_commit': 'unknown', 'python': 'test', 'versions': {},
            'config': {'inputs': {'study.yaml': 'value: 1\n', 'com.yaml': 'value: 2\n'}},
        }), encoding='utf-8')
        for name in ('convergence_trials.csv', 'convergence_report.html',
                     'best_candidates.json', 'budget_summary.csv',
                     'paired_budget_deltas.csv', 'performance_gate.json'):
            (run / name).write_text('{}\n', encoding='utf-8')
        (run / 'tests' / 'pytest.txt').write_text('1 passed\n', encoding='utf-8')
        (run / 'tests' / 'pytest_summary.json').write_text(
            json.dumps({'passed': 1, 'failed': 0, 'exit_code': 0}), encoding='utf-8')
        return run

    def test_bundle_hashes_and_optional_payloads(self):
        with tempfile.TemporaryDirectory() as temp:
            run = self._make_run(Path(temp) / 'run')
            (run / 'history.jsonl').write_text('{}\n', encoding='utf-8')
            (run / 'response.npz').write_bytes(b'npz')
            output = Path(temp) / 'review.zip'
            create_review_bundle(run, output, include_history=True, include_npz=True)
            with ZipFile(output) as archive:
                manifest = json.loads(archive.read('bundle_manifest.json'))
                self.assertTrue(manifest['included_history'])
                self.assertTrue(manifest['included_npz'])
                self.assertTrue(any(item['path'] == 'REVIEW_ME.md' for item in manifest['files']))
                for item in manifest['files']:
                    self.assertEqual(len(archive.read(item['path'])), item['bytes'])

    def test_missing_required_artifact_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            run = self._make_run(Path(temp) / 'run')
            (run / 'performance_gate.json').unlink()
            with self.assertRaises(BundleValidationError):
                create_review_bundle(run, Path(temp) / 'review.zip')
