"""Audited metadata update after non-physics orchestration/report fixes."""
import hashlib
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
manifest_path = Path(sys.argv[1]) / 'manifest.json'
data = json.loads(manifest_path.read_text(encoding='utf-8'))
package_root = root/'src/sawopt'
source_hash = hashlib.sha256(b''.join(
    p.relative_to(package_root).as_posix().encode() + p.read_bytes()
    for p in sorted(package_root.rglob('*.py'))
)).hexdigest()
if data['source_hash'] != source_hash:
    data.setdefault('numerical_run_source_hash', data['source_hash'])
    changes = data.setdefault('post_run_changes', [])
    aggregation_change = (
        'Stage 2 aggregation retains the better of the independent parent '
        'and equal-budget neighbor refinement; numerical trial files are unchanged.'
    )
    debug_change = (
        'Optional COM condition-number diagnostics were added behind '
        'debug_diagnostics=False; numerical trial files are unchanged.'
    )
    report_change = (
        'Hybrid HTML report CSS was moved out of an f-string to prevent brace '
        'interpolation; the numerical model and trial files are unchanged.'
    )
    layout_change = (
        'Python modules were moved into core, optimization, and reporting '
        'packages with imports updated; numerical behavior is unchanged.'
    )
    for change in (aggregation_change, debug_change, report_change, layout_change):
        if change not in changes:
            changes.append(change)
    data.pop('post_run_change', None)
    data['source_hash'] = source_hash
    data['fingerprint'] = hashlib.sha256(
        (json.dumps(data['config'], sort_keys=True) + source_hash).encode()
    ).hexdigest()
    manifest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
