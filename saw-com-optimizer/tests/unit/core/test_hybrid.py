import unittest
from pathlib import Path
import numpy as np,yaml
from sawopt.core.hybrid import circuit_y,resonator_y,ResonatorDesign,layout,TOPOLOGIES,response
from sawopt.core.models import FixedProvider,FilterDesign,NAMES
from sawopt.core.com import simulate_filter,acoustic_admittance

class Hybrid(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).parents[3]/'configs'
        self.cfg=yaml.safe_load((root/'base/b28_dms_baseline.yaml').read_text())
        self.cfg.update(yaml.safe_load((root/'studies/hybrid_50ohm.yaml').read_text()))
        self.cfg['com']=yaml.safe_load((root/'models/com_params_hypothetical.yaml').read_text())
        self.provider=FixedProvider(self.cfg['com'])

    def test_series_and_shunt_analytic(self):
        y=np.array([[[1,-1],[-1,1]]],complex)/25
        np.testing.assert_allclose(circuit_y(y,[(0,2,np.array([1/30]))],dms_nodes=(2,1),node_count=3),y*25/55,atol=1e-12)
        expected=y.copy(); expected[:,0,0]+=1/80
        np.testing.assert_allclose(circuit_y(y,[(0,-1,np.array([1/80]))]),expected)
        np.testing.assert_allclose(circuit_y(y,[]),y)

    def test_resonator_static_limit(self):
        f=np.linspace(750e6,810e6,10)
        self.cfg['com']['idt']['alpha_sqrtS_per_m']=0
        y=resonator_y(ResonatorDesign(),FixedProvider(self.cfg['com']),f)
        C=1e-8*(70/80)*25*5e-6
        np.testing.assert_allclose(y,1j*2*np.pi*f*C,atol=1e-12)

    def test_wiring_transform_against_three_port(self):
        f=np.linspace(730e6,830e6,101); d=FilterDesign()
        regions=[('reflector',20,None),('gap',.5,None),('idt',24,0),('gap',.5,None),('idt',16,1),('gap',.5,None),('idt',24,2),('gap',.5,None),('reflector',20,None)]
        full=acoustic_admittance(d,self.provider,f,regions,3)
        for wiring,sign in [('center_outer_same',1),('center_outer_opposite',-1)]:
            B=np.array([[0,1],[1,0],[0,sign]])
            out=simulate_filter(d,self.provider,f,wiring=wiring).y_parameters
            np.testing.assert_allclose(out,B.T@full@B,atol=1e-12)
        # Mirror-symmetric single-mode model cancels the odd outer combination.
        odd=simulate_filter(d,self.provider,f,wiring='center_outer_opposite').y_parameters
        np.testing.assert_allclose(odd[:,0,1],0,atol=1e-12)

    def test_all_topologies_passive_and_layout(self):
        f=np.unique(np.r_[np.linspace(10e6,1000e6,301),[758e6,803e6]])
        x=[5,24,16,40,.5,.5,80]
        for topology,(_,terminals,_) in TOPOLOGIES.items():
            r,net,y=response(x+[5.1,15,60]*len(terminals),topology,'center_outer_same',self.cfg,f)
            self.assertLessEqual(net['gt'].max(),1+1e-10)
            self.assertLessEqual(r['layout']['total_electrodes'],500)
        _,v=layout(FilterDesign(),[ResonatorDesign(pairs=60)]*2,self.cfg)
        self.assertGreater(v,0)
