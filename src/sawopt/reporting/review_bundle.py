"""Create and validate a compact Stage 3.1 review bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


class BundleValidationError(ValueError):
    """Raised when a run is not complete enough to be reviewed."""


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _source_hash(package_root):
    package_root = Path(package_root)
    digest = hashlib.sha256()
    for path in sorted(package_root.rglob('*.py')):
        digest.update(path.relative_to(package_root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _copy_file(source, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _repository_root(module_path=None):
    """Resolve both the checkout layout and an extracted bundle layout."""
    module_path = Path(module_path or __file__).resolve()
    for candidate in (module_path.parents[3], module_path.parents[2], module_path.parents[1]):
        if (candidate / 'src' / 'sawopt').is_dir():
            return candidate
    raise BundleValidationError(f'Cannot resolve repository root from {module_path}')


def _workspace_root(repo=None):
    """Return the repository root that owns the external review artifacts."""
    return Path(repo or _repository_root()).resolve()


def _default_review_bundle_output(run, repo=None):
    """Return the fixed repository-level output path for ``run``."""
    run = Path(run).resolve()
    return _workspace_root(repo) / 'artifacts' / 'review_bundles' / f'{run.name}_review.zip'


def _git(repo, args):
    try:
        # Git emits repository text as UTF-8 even when the Windows process
        # locale is a legacy code page.  Decode explicitly so review bundles
        # remain reproducible on Japanese Windows hosts.
        return subprocess.check_output(
            ['git', *args], cwd=repo, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace',
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return f'git unavailable: {exc}\n'


def _required_run_artifacts(run, summary):
    names = [
        'manifest.json', 'convergence_summary.json', 'convergence_trials.csv',
        'convergence_report.html', 'best_candidates.json', 'budget_summary.csv',
        'paired_budget_deltas.csv', 'performance_gate.json',
    ]
    stage32 = summary.get('study_type') == 'stage3_2_dms_convergence'
    if stage32:
        names.extend([
            'boundary_events.csv', 'design_space_versions.json',
            'stagnation_events.csv', 'parallel_benchmark.json',
            'benchmark_decision.json', 'environment/local_runtime.json',
            'checkpoints/checkpoint_summary.json',
            'smoke/smoke_test.json',
        ])
    missing = [name for name in names if not (run / name).is_file()]
    trial_files = list(summary.get('trial_files', []))
    expected = sum(
        len(summary.get('budgets_run_by_wiring', {}).get(wiring, [])) *
        len(summary.get('cold_seeds', []))
        for wiring in summary.get('wirings', [])
    )
    if expected and len(trial_files) != expected:
        raise BundleValidationError(
            f'trial count mismatch: expected {expected}, found {len(trial_files)}'
        )
    declared = summary.get('expected_trial_count')
    if declared is not None and int(declared) != len(trial_files):
        raise BundleValidationError(
            f'declared trial count mismatch: expected {declared}, found {len(trial_files)}'
        )
    for relative in trial_files:
        if not (run / relative).is_file():
            missing.append(relative)
        else:
            try:
                trial = json.loads((run / relative).read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as exc:
                raise BundleValidationError(f'Invalid trial JSON {relative}: {exc}') from exc
            required_trial_fields = {
                'design', 'seed', 'requested_unique_design_budget',
                'objective_calls', 'unique_decoded_evaluations',
                'metrics', 'violations', 'validated_rank_tuple',
                'selected_adaptive_round', 'validation_gap_primary',
                'best_so_far_trace', 'polish', 'global_search_wall_time_s',
                'validation_wall_time_s', 'polish_wall_time_s', 'diagnostics',
            }
            if stage32:
                required_trial_fields = {
                    'design', 'seed', 'requested_unique_design_budget',
                    'actual_unique_design_evaluations', 'objective_calls',
                    'metrics', 'violations', 'design_space_version',
                    'active_bounds', 'grid_converged', 'optimizer_converged',
                    'best_candidate_polish_improvement',
                    'median_candidate_polish_improvement',
                    'last_significant_improvement_unique_eval',
                    'best_so_far_trace', 'grid_extension_events',
                    'validation_frequencies_hz', 'diagnostics',
                    'validated_rank_tuple',
                    'recovery_fired_at_current_checkpoint',
                    'recovery_pending_confirmation',
                    'boundary_pressure_first_seen_at_current_checkpoint',
                    'boundary_pending_confirmation',
                    'hard_bound_reached_by_variable',
                }
            missing_fields = sorted(required_trial_fields - set(trial))
            if missing_fields:
                raise BundleValidationError(
                    f'Trial {relative} is missing fields: {", ".join(missing_fields)}'
                )
    if missing:
        raise BundleValidationError('Missing required run artifacts: ' + ', '.join(missing))
    return trial_files


def _test_artifact(run, name):
    candidates = [run / 'tests' / name, run / name]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise BundleValidationError(f'Missing required test artifact: {name}')


def _test_artifact_any(run, names):
    for name in names:
        try:
            return _test_artifact(run, name), name
        except BundleValidationError:
            continue
    raise BundleValidationError(
        'Missing required test artifact: ' + ' or '.join(names)
    )


def _run_bundle_self_test(staging, expected_source_hash):
    """Run discovery from the extracted bundle payload before packaging it."""
    staging = Path(staging)
    source_root = staging / 'source'
    python_root = source_root / 'src' if (source_root / 'src').is_dir() else source_root
    config_root = source_root / 'configs'
    if not config_root.is_dir():
        raise BundleValidationError('Self-contained bundle is missing source/configs')
    actual = _source_hash(python_root / 'sawopt')
    if actual != expected_source_hash:
        raise BundleValidationError('Self-contained source hash verification failed')
    environment = dict(os.environ)
    environment['PYTHONPATH'] = str(python_root)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    process = subprocess.run(
        [sys.executable, '-m', 'unittest', 'discover', '-s', '../tests', '-q'],
        cwd=python_root, env=environment, capture_output=True, text=True,
    )
    output = (process.stdout or '') + (process.stderr or '')
    match = re.search(r'Ran\s+(\d+)\s+tests?', output)
    result = {
        'runner': 'unittest',
        'passed': int(match.group(1)) if match and process.returncode == 0 else 0,
        'failed': 0 if process.returncode == 0 else 1,
        'exit_code': int(process.returncode),
        'source_hash_verified': True,
        'configs_present': True,
        'output_tail': output[-4000:],
    }
    _write_text(staging / 'tests/bundle_self_test.json', json.dumps(
        result, ensure_ascii=False, indent=2
    ) + '\n')
    if process.returncode != 0:
        raise BundleValidationError(
            'Bundle-only unittest discovery failed: ' + output[-2500:]
        )
    return result


def _review_text(summary, manifest, run, pytest_result=None):
    command = summary.get(
        'command',
        f'python -m sawopt.optimization.convergence_study --run {run.as_posix()}',
    )
    test_log_path = 'tests/unittest.txt' if summary.get('study_type') == 'stage3_2_dms_convergence' else 'tests/pytest.txt'
    experiment_name = summary.get('experiment_name') or summary.get(
        'study_type', 'convergence'
    )
    lines = [
        f'# {experiment_name} review summary',
        '',
        'This bundle contains finite cold-seed evidence only; it does not claim a global optimum.',
        '',
        f'- Command: `{command}`',
        f'- Impedance: {summary.get("impedance_ohm")} ohm',
        f'- Budgets (unique decoded designs): {summary.get("budgets", summary.get("unique_design_budgets"))}',
        f'- Wirings: {summary.get("wirings")}',
        f'- Cold seeds: {summary.get("cold_seeds")}',
        '',
        '## Convergence',
        '',
    ]
    statuses = summary.get('statuses', {})
    for wiring, value in statuses.items():
        lines.append(f'- `{wiring}` status: `{value.get("status")}`')
        evidence = value.get('evidence', {})
        lines.append(f'  - final seed IQR: {evidence.get("final_seed_primary_iqr", evidence.get("final_seed_iqr_db"))}')
        lines.append(f'  - worst-minus-median: {evidence.get("final_seed_primary_worst_minus_median", evidence.get("final_seed_il_worst_minus_median_db"))}')
        lines.append(f'  - grid-converged fraction: {evidence.get("stage34b_gates", {}).get("grid_converged_seed_fraction")}')
        lines.append(f'  - recovery pending: {evidence.get("stage34b_gates", {}).get("recovery_pending_confirmation")}')
        lines.append(f'  - boundary pending: {evidence.get("stage34b_gates", {}).get("boundary_pending_confirmation")}')
        lines.append(f'  - common validation gap: {evidence.get("validation_primary_gap", evidence.get("validation_il_gap_db"))}')
        lines.append(f'  - best-candidate polish improvement: {evidence.get("best_polish_primary_improvement", evidence.get("best_polish_il_improvement_db"))}')
        intervals = evidence.get('paired_budget_deltas', [])
        if intervals:
            lines.append(f'  - last paired median improvement: {intervals[-1].get("median_improvement")}')
        last_positions = summary.get('last_significant_improvement', {}).get(wiring, {})
        if last_positions:
            lines.append(f'  - last significant improvement positions: {json.dumps(last_positions, ensure_ascii=False)}')
    lines.extend(['', '## Budget summaries', ''])
    for wiring, budgets in summary.get('budget_summary', {}).items():
        for budget, values in budgets.items():
            lines.append(
                f'- `{wiring}` / {budget}: best primary={values.get("best_primary_metric")}, '
                f'median primary={values.get("median_primary_metric")}'
            )
    lines.extend([
        '', '## Runtime and validation', '',
        f'- Last significant improvement location is recorded in every trial JSON.',
        f'- Performance-gate speedup: `{json.dumps({wiring: value.get("speedup") for wiring, value in summary.get("performance_gate", {}).items()}, ensure_ascii=False)}`',
        f'- Wall time: {summary.get("elapsed_s")} s',
        '- Solved frequency point counts and logging I/O time are in `convergence_trials.csv`.',
        f'- Test status: `{json.dumps(pytest_result or {}, ensure_ascii=False)}`; exact output is `{test_log_path}`.',
        '', '## Known limitations', '',
    ])
    for limitation in summary.get('known_limitations', []):
        lines.append(f'- {limitation}')
    lines.extend([
        '- The benchmark does not establish a global optimum.',
        '- Production impedance/topology sweeps require review of this certificate first.',
        f'- Source hash from the run manifest: `{manifest.get("source_hash", "unknown")}`',
    ])
    return '\n'.join(lines) + '\n'


def create_review_bundle(run, output, *, include_history=False, include_npz=False):
    """Validate ``run`` and create a self-contained review ZIP."""
    run = Path(run).resolve()
    output = Path(output).resolve()
    if not run.is_dir():
        raise BundleValidationError(f'Run directory does not exist: {run}')
    summary_path = run / 'convergence_summary.json'
    manifest_path = run / 'manifest.json'
    if not summary_path.is_file() or not manifest_path.is_file():
        raise BundleValidationError('Run manifest and convergence summary are required')
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    run_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    stage32 = summary.get('study_type') == 'stage3_2_dms_convergence'
    trial_files = _required_run_artifacts(run, summary)
    if stage32:
        test_log, test_log_name = _test_artifact_any(run, ('unittest.txt', 'pytest.txt'))
        test_summary, test_summary_name = _test_artifact_any(
            run, ('test_summary.json', 'pytest_summary.json')
        )
    else:
        test_log, test_log_name = _test_artifact(run, 'pytest.txt'), 'pytest.txt'
        test_summary, test_summary_name = _test_artifact(run, 'pytest_summary.json'), 'pytest_summary.json'
    pytest_result = json.loads(test_summary.read_text(encoding='utf-8'))
    if not isinstance(pytest_result, dict) or any(
        key not in pytest_result for key in ('passed', 'failed', 'exit_code')
    ):
        raise BundleValidationError(
            f'{test_summary_name} must contain passed, failed, and exit_code'
        )

    repo = _repository_root()
    package_root = repo / 'src' / 'sawopt'
    expected_source_hash = run_manifest.get('source_hash')
    if not expected_source_hash:
        raise BundleValidationError('Run manifest source_hash is required')
    actual_source_hash = _source_hash(package_root)
    if expected_source_hash and expected_source_hash != actual_source_hash:
        raise BundleValidationError(
            'Source hash mismatch between run manifest and current source snapshot'
        )
    if run_manifest.get('fingerprint') and run_manifest.get('config') is not None:
        fingerprint = hashlib.sha256((
            json.dumps(run_manifest['config'], sort_keys=True) + actual_source_hash
        ).encode()).hexdigest()
        if fingerprint != run_manifest['fingerprint']:
            raise BundleValidationError('Run manifest config fingerprint does not validate')

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='stage3_1_bundle_', dir=str(output.parent)) as temp_name:
        staging = Path(temp_name) / 'review_bundle'
        staging.mkdir()
        required_paths = set()

        def copy_required(source, relative):
            _copy_file(source, staging / relative)
            required_paths.add(Path(relative).as_posix())

        copy_required(summary_path, 'results/convergence_summary.json')
        copy_required(run / 'convergence_trials.csv', 'results/convergence_trials.csv')
        copy_required(run / 'convergence_report.html', 'results/convergence_report.html')
        copy_required(run / 'best_candidates.json', 'results/best_candidates.json')
        copy_required(run / 'budget_summary.csv', 'results/budget_summary.csv')
        copy_required(run / 'paired_budget_deltas.csv', 'results/paired_budget_deltas.csv')
        copy_required(run / 'performance_gate.json', 'results/performance_gate.json')
        if stage32:
            copy_required(run / 'boundary_events.csv', 'results/boundary_events.csv')
            copy_required(run / 'stagnation_events.csv', 'results/stagnation_events.csv')
            copy_required(run / 'design_space_versions.json', 'results/design_space_versions.json')
            copy_required(run / 'parallel_benchmark.json', 'results/parallel_benchmark.json')
            copy_required(run / 'benchmark_decision.json', 'benchmark/benchmark_decision.json')
            copy_required(run / 'environment/local_runtime.json', 'environment/local_runtime.json')
            copy_required(run / 'smoke/smoke_test.json', 'results/smoke_test.json')
            copy_required(run / 'checkpoints/checkpoint_summary.json', 'checkpoints/checkpoint_summary.json')
        for relative in trial_files:
            copy_required(run / relative, Path('trials') / Path(relative).name)
        copy_required(test_log, 'tests/unittest.txt' if stage32 else 'tests/pytest.txt')
        copy_required(test_summary, 'tests/test_summary.json' if stage32 else 'tests/pytest_summary.json')
        if stage32:
            copy_required(run / 'parallel_benchmark.json', 'tests/parallel_benchmark.json')
            copy_required(run / 'benchmark_decision.json', 'tests/benchmark_decision.json')
            copy_required(run / 'smoke/smoke_test.json', 'tests/smoke_test.json')

        inputs = run_manifest.get('config', {}).get('inputs', {})
        if not isinstance(inputs, dict) or not inputs:
            raise BundleValidationError('Exact input text is missing from run manifest config.inputs')
        for name, text in inputs.items():
            destination = Path('inputs') / Path(name).name
            _write_text(staging / destination, text)
            required_paths.add(destination.as_posix())

        for source in sorted(package_root.rglob('*.py')):
            relative = source.relative_to(repo / 'src').as_posix()
            destination = Path('source') / relative
            copy_required(source, destination)
            if stage32:
                copy_required(source, Path('source') / 'src' / relative)
        tests_root = repo / 'tests'
        for source in sorted(tests_root.rglob('*.py')):
            destination = Path('source') / 'tests' / source.relative_to(tests_root)
            copy_required(source, destination)
        if stage32:
            configs_root = repo / 'configs'
            for source in sorted(configs_root.rglob('*')):
                if source.is_file():
                    destination = Path('source') / 'configs' / source.relative_to(configs_root)
                    copy_required(source, destination)
            experiments_root = repo / 'experiments'
            for source in sorted(experiments_root.rglob('*')):
                if source.is_file():
                    destination = Path('source') / 'experiments' / source.relative_to(experiments_root)
                    copy_required(source, destination)
        copy_required(repo / 'pyproject.toml', 'source/pyproject.toml')
        if _source_hash(staging / 'source' / 'sawopt') != expected_source_hash:
            raise BundleValidationError('Bundled source snapshot hash does not match run manifest')

        _write_text(staging / 'environment/git_status.txt', _git(repo, ['status', '--short']))
        _write_text(staging / 'environment/git_diff.patch', _git(repo, ['diff', '--binary']))
        _write_text(staging / 'environment/pip_versions.json', json.dumps(
            run_manifest.get('versions', {}), ensure_ascii=False, indent=2
        ) + '\n')
        _write_text(staging / 'environment/manifest.json', json.dumps(
            run_manifest, ensure_ascii=False, indent=2
        ) + '\n')
        if stage32:
            _write_text(staging / 'environment/run_manifest.json', json.dumps(
                run_manifest, ensure_ascii=False, indent=2
            ) + '\n')
        for path in (staging / 'environment').iterdir():
            required_paths.add(path.relative_to(staging).as_posix())

        if include_history:
            for source in sorted(run.rglob('*.jsonl')):
                destination = staging / 'optional/history' / source.relative_to(run)
                _copy_file(source, destination)
        if include_npz:
            for source in sorted(run.rglob('*.npz')):
                destination = staging / 'optional/responses' / source.relative_to(run)
                _copy_file(source, destination)

        if stage32:
            self_test = _run_bundle_self_test(staging, expected_source_hash)
            required_paths.add('tests/bundle_self_test.json')
        else:
            self_test = None
        _write_text(staging / 'REVIEW_ME.md', _review_text(summary, run_manifest, run, pytest_result))
        required_paths.add('REVIEW_ME.md')

        files = []
        for source in sorted(path for path in staging.rglob('*') if path.is_file()):
            relative = source.relative_to(staging).as_posix()
            files.append({
                'path': relative,
                'sha256': _sha256(source),
                'bytes': source.stat().st_size,
                'required': relative in required_paths or not relative.startswith('optional/'),
            })
        bundle_manifest = {
            'bundle_format_version': 1,
            'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'study_type': summary.get('study_type', 'stage3_1_dms_convergence'),
            'run_directory': str(run),
            'source_hash': expected_source_hash or actual_source_hash,
            'git_commit': run_manifest.get('git_commit', 'unknown'),
            'git_dirty': bool(_git(repo, ['status', '--short']).strip()),
            'python_version': run_manifest.get('python', sys.version),
            'platform': platform.platform(),
            'review_scope': summary.get('experiment_name', '50 ohm DMS convergence'),
            'included_history': bool(include_history),
            'included_npz': bool(include_npz),
            'test_log_name': test_log_name,
            'test_summary_name': test_summary_name,
            'bundle_self_test': self_test,
            'files': files,
        }
        _write_text(staging / 'bundle_manifest.json', json.dumps(
            bundle_manifest, ensure_ascii=False, indent=2
        ) + '\n')

        with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
            for source in sorted(path for path in staging.rglob('*') if path.is_file()):
                archive.write(source, source.relative_to(staging).as_posix())

    with ZipFile(output) as archive:
        names = set(archive.namelist())
        bundled_manifest = json.loads(archive.read('bundle_manifest.json').decode('utf-8'))
        listed = {entry['path'] for entry in bundled_manifest['files']}
        extra = sorted(names - listed - {'bundle_manifest.json'})
        if extra:
            raise BundleValidationError(
                'ZIP contains files absent from bundle_manifest.json: ' + ', '.join(extra)
            )
        for entry in bundled_manifest['files']:
            if entry['path'] not in names:
                raise BundleValidationError(f'ZIP is missing manifest file: {entry["path"]}')
            data = archive.read(entry['path'])
            if hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise BundleValidationError(f'ZIP hash mismatch: {entry["path"]}')
            if len(data) != int(entry['bytes']):
                raise BundleValidationError(f'ZIP byte-size mismatch: {entry["path"]}')
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description='Create a Stage 3.1 review bundle ZIP')
    parser.add_argument('--run', required=True)
    parser.add_argument(
        '--output',
        help='Optional filename inside the repository-root artifacts/review_bundles directory; '
             'defaults to <run-name>_review.zip',
    )
    parser.add_argument('--include-history', action='store_true')
    parser.add_argument('--include-npz', action='store_true')
    args = parser.parse_args(argv)
    repo = _repository_root()
    default_output = _default_review_bundle_output(args.run, repo)
    output = default_output if args.output is None else Path(args.output).resolve()
    if output.parent != default_output.parent.resolve():
        parser.error(
            'Review bundles must be written directly under the repository-root '
            f'artifacts/review_bundles directory: {default_output.parent}'
        )
    try:
        path = create_review_bundle(args.run, output,
                                    include_history=args.include_history,
                                    include_npz=args.include_npz)
    except BundleValidationError as exc:
        parser.error(str(exc))
    print(path)


if __name__ == '__main__':
    main()
