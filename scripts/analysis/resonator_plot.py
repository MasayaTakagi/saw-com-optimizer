"""Plot the saved winner's isolated added resonators using its saved COM config."""
import json,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sawopt.core.hybrid import ResonatorDesign, resonator_admittance
from sawopt.physics.com import FixedProvider

out=Path(sys.argv[1]); best=json.loads((out/'best.json').read_text(encoding='utf-8'))
cfg=json.loads((out/'manifest.json').read_text(encoding='utf-8'))['config']
f=np.linspace(700e6,880e6,3601)
fig,axes=plt.subplots(2,1,figsize=(10,7),sharex=True)
for i,values in enumerate(best['resonators']):
    y=resonator_admittance(ResonatorDesign(**values),FixedProvider(cfg['com']),f)
    axes[0].plot(f/1e6,20*np.log10(np.maximum(abs(y),1e-15)),label=f'Resonator {i+1}')
    axes[1].plot(f/1e6,np.angle(y,deg=True),label=f'Resonator {i+1}')
for ax in axes: ax.axvspan(758,803,color='green',alpha=.06); ax.grid(alpha=.3); ax.legend()
axes[0].set_ylabel('Admittance (dB relative to 1 S)'); axes[1].set(ylabel='Admittance phase (deg)',xlabel='MHz')
fig.suptitle('Isolated added COM resonators / hypothetical')
fig.tight_layout(); fig.savefig(out/'resonators.png',dpi=150)
