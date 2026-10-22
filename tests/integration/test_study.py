import copy,json,tempfile,unittest
from pathlib import Path
import yaml,numpy as np
from sawopt.optimization.runner import initialize,optimize_one
from sawopt.design.geometry import geometry
from sawopt.design.space import FilterDesign

class Study(unittest.TestCase):
    def test_reproducibility_resume_and_constraints(self):
        root=Path(__file__).parents[2]/'configs'
        cfg=yaml.safe_load((root/'base/b28_dms_baseline.yaml').read_text())
        cfg['com']=yaml.safe_load((root/'models/com_params_hypothetical.yaml').read_text())
        cfg['optimizer'].update(maxiter=0,population=5)
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            pa=initialize(a,cfg); pb=initialize(b,cfg)
            r=optimize_one(pa,cfg,50,50,12); s=optimize_one(pb,cfg,50,50,12)
            self.assertEqual(r['design'],s['design']); self.assertEqual(r['objective'],s['objective'])
            history=pa/'R50_L50_seed12.jsonl'; before=history.read_bytes()
            self.assertEqual(r,optimize_one(pa,cfg,50,50,12))
            self.assertEqual(before,history.read_bytes())
            d=FilterDesign(**r['design']); self.assertEqual(max(geometry(d,cfg['constraints'])[1]),0)
            self.assertIsInstance(d.io_idt_pairs,int)
            # A completed seed can be deleted to emulate interruption; restart is deterministic.
            (pa/'R50_L50_seed12.json').unlink()
            restarted=optimize_one(pa,cfg,50,50,12)
            self.assertEqual(restarted['objective'],r['objective'])
            bad=copy.deepcopy(cfg); bad['center']='floating'
            with self.assertRaises(ValueError): initialize(a,bad)
