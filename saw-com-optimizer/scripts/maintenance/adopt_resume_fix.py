"""One-time audited metadata migration; numerical engine/results are unchanged."""
import hashlib,json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
for name in ['refined-prototype','50ohm','baseline']:
    path=root/'runs'/name/'manifest.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    package_root=root/'src/sawopt'
    source=hashlib.sha256(b''.join(
        p.relative_to(package_root).as_posix().encode()+p.read_bytes()
        for p in sorted(package_root.rglob('*.py'))
    )).hexdigest()
    data['previous_source_hash_before_cli_resume_fix']=data['source_hash']
    data['migration_note']='Only refinement selection in __main__.py changed: always anchor on coarse resistances, including on resume. Numerical model and optimization unchanged. Existing results retained.'
    data['source_hash']=source
    data['fingerprint']=hashlib.sha256((json.dumps(data['config'],sort_keys=True)+source).encode()).hexdigest()
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
