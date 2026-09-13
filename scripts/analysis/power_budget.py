"""Inspect saved power-normalized S parameters; no COM re-simulation."""
import json,sys
from pathlib import Path
import numpy as np

out=Path(sys.argv[1])
records=[json.loads(p.read_text(encoding='utf-8')) for p in out.glob('*__*.json') if '.checkpoint.' not in p.name]
groups={}
def key(r): return (not r['feasible'],r['max_violation'] if not r['feasible'] else 0,r['objective'] if not r['feasible'] else r['metrics']['worst_il_db'])
for r in records:
    group=(r['topology'],r['wiring'])
    if group not in groups or key(r)<key(groups[group]): groups[group]=r
summary=[]
for r in sorted(groups.values(),key=key):
    data=np.load(out/r['response_file']); f=data['frequencies_hz']; s=data['s']
    mask=np.flatnonzero((f>=758e6)&(f<=803e6)); ix=mask[np.argmax(data['il'][mask])]
    reflected=abs(s[ix,0,0])**2; transmitted=abs(s[ix,1,0])**2
    summary.append(dict(topology=r['topology'],wiring=r['wiring'],frequency_mhz=float(f[ix]/1e6),
        reflected_percent=float(100*reflected),load_percent=float(100*transmitted),
        dissipated_or_acoustic_radiation_percent=float(100*(1-reflected-transmitted)),
        power_vs_s21_error=float(abs(data['gt']-abs(s[:,1,0])**2).max())))
(out/'power_budget.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary[:4],indent=2))
