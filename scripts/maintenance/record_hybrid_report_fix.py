"""Record a reporting-only import fix without changing numerical result provenance."""
import hashlib,json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
path=root/'runs/hybrid-50ohm/manifest.json'
data=json.loads(path.read_text(encoding='utf-8'))
package_root=root/'src/sawopt'
source=hashlib.sha256(b''.join(
    p.relative_to(package_root).as_posix().encode()+p.read_bytes()
    for p in sorted(package_root.rglob('*.py'))
)).hexdigest()
if data['source_hash']!=source:
    data['numerical_run_initial_source_hash']=data['source_hash']
    data['report_fix_note']='hybrid_report.py: import save for best.json export; exclude cancellation control from overlays (retained in table); draw stopband targets; show optional isolated-resonator plot. No numerical model, objective, search or selection changes. source_snapshot retains initial code.'
    data['source_hash']=source
    data['fingerprint']=hashlib.sha256((json.dumps(data['config'],sort_keys=True)+source).encode()).hexdigest()
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
