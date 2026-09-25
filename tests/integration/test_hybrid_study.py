import json,tempfile,unittest
from pathlib import Path
import yaml
import numpy as np
from sawopt.studies.hybrid import optimize_case

class HybridStudy(unittest.TestCase):
    def test_hybrid_seed_reproducibility_and_reuse(self):
        root=Path(__file__).parents[2]/'configs'
        cfg=yaml.safe_load((root/'base/b28_dms_baseline.yaml').read_text())
        cfg.update(yaml.safe_load((root/'studies/hybrid_50ohm.yaml').read_text()))
        cfg['com']=yaml.safe_load((root/'models/com_params_hypothetical.yaml').read_text()); cfg['population']=5
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            left=optimize_case(Path(a),cfg,'SP_D','center_outer_same',123,'test',0)
            right=optimize_case(Path(b),cfg,'SP_D','center_outer_same',123,'test',0)
            self.assertEqual(left['x'],right['x']); self.assertEqual(left['objective'],right['objective'])
            files={p.name:p.stat().st_mtime_ns for p in Path(a).iterdir()}
            self.assertEqual(left,optimize_case(Path(a),cfg,'SP_D','center_outer_same',123,'test',0))
            self.assertEqual(files,{p.name:p.stat().st_mtime_ns for p in Path(a).iterdir()})

    def test_termination_values_propagate_to_result_and_filenames(self):
        root=Path(__file__).parents[2]/'configs'
        cfg=yaml.safe_load((root/'base/b28_dms_baseline.yaml').read_text())
        cfg.update(yaml.safe_load((root/'studies/hybrid_50ohm.yaml').read_text()))
        cfg['com']=yaml.safe_load((root/'models/com_params_hypothetical.yaml').read_text())
        cfg.update(population=5,adaptive_frequency_rounds=0,dense_refinement_passes=0)
        with tempfile.TemporaryDirectory() as tmp:
            result=optimize_case(Path(tmp),cfg,'D','outer_ports',7,'termination',0,rs=33,rl=77)
            self.assertEqual((result['rs'],result['rl']),(33,77))
            self.assertIn('R33_L77',result['response_file'])
            with np.load(Path(tmp)/result['response_file']) as data:
                self.assertEqual(float(data['source_impedance_ohm']),33)
                self.assertEqual(float(data['load_impedance_ohm']),77)
