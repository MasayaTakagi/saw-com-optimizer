import unittest
from pathlib import Path
import numpy as np
import yaml
from scipy.linalg import expm
from sawopt.physics.network import evaluate
from sawopt.physics.com import FixedProvider, block, simulate_filter
from sawopt.core.models import FilterDesign

class Physics(unittest.TestCase):
    def test_series_resistor_and_rlc(self):
        for z in [25,25+40j,1j*40,1e-6]:
            y=np.array([[[1,-1],[-1,1]]],complex)/z
            for rs,rl in [(50,50),(30,120)]:
                r=evaluate(y,rs,rl)
                self.assertAlmostEqual(r['gt'][0],4*rs*rl/abs(rs+rl+z)**2,places=7)
                self.assertAlmostEqual(abs(r['s'][0,0,0]),abs((rl+z-rs)/(rl+z+rs)),places=7)
                self.assertAlmostEqual(abs(r['s'][0,1,0])**2,r['gt'][0],places=7)

    def test_matched_shunts(self):
        y=np.array([np.diag([1/50,1/100])],complex)
        r=evaluate(y,50,100)
        np.testing.assert_allclose(r['s'],0,atol=1e-15)
        self.assertEqual(r['gt'][0],0)

    def test_uniform_idt_synchronous_known_solution(self):
        f=np.array([780e6]); L=100e-6; alpha=1200; lam=5e-6
        p=dict(velocity=3900,kappa=0,alpha=alpha,capacitance=1e-8,loss=0)
        P=block(f,L,lam,p)[0]
        self.assertAlmostEqual(P[2,2].real,2*alpha**2*L**2,places=12)
        self.assertAlmostEqual(P[2,2].imag,2*np.pi*f[0]*p['capacitance']*L,places=12)
        np.testing.assert_allclose(P[2,:2],-2*P[:2,2],atol=1e-12)

    def test_gap_and_reflector_closed_form(self):
        f=np.array([780e6]); L=100e-6; lam=5e-6
        p=dict(velocity=3900,kappa=4000,alpha=0,capacitance=0,loss=0)
        P=block(f,L,lam,p)[0]
        self.assertAlmostEqual(P[0,0].imag,np.tanh(4000*L),places=12)
        self.assertAlmostEqual(P[0,1].real,1/np.cosh(4000*L),places=12)
        p.update(kappa=0,loss=100)
        P=block(f,L,lam,p,True)[0]
        np.testing.assert_allclose(P[0,1],np.exp((-1j*2*np.pi*f[0]/3900-100)*L),atol=1e-12)

    def test_matrix_exponential_and_partition(self):
        f=np.array([779e6,810e6]); L=120e-6; lam=5e-6
        p=dict(velocity=3900,kappa=4000,alpha=1200,capacitance=1e-8,loss=300)
        P=block(f,L,lam,p)
        for j,freq in enumerate(f):
            delta=2*np.pi*freq/3900-2*np.pi/lam-300j
            M=np.array([[-1j*delta,4000j,1200j,0],[-4000j,1j*delta,-1200j,0],[0,0,0,0],[-2400j,-2400j,1j*2*np.pi*freq*1e-8,0]])
            T=expm(M*L); half=expm(M*L/2)
            np.testing.assert_allclose(T,half@half,atol=1e-10)
            R0=.2+.1j; SL=.3-.2j; V=.8
            S0=(SL-T[1,0]*R0-T[1,2]*V)/T[1,1]
            end=T@np.array([R0,S0,V,0])
            np.testing.assert_allclose(P[j]@np.array([R0,SL,V]),[S0,end[0],end[3]],atol=1e-10)

    def test_filter_passivity_symmetry_floating_and_off(self):
        params=yaml.safe_load((Path(__file__).parents[3]/'configs/models/com_params_hypothetical.yaml').read_text())
        f=np.linspace(10e6,1000e6,1001)
        for center in ['grounded','floating']:
            y=simulate_filter(FilterDesign(),FixedProvider(params),f,center).y_parameters
            np.testing.assert_allclose(y[:,0,1],y[:,1,0],atol=1e-10)
            np.testing.assert_allclose(y[:,0,0],y[:,1,1],atol=1e-10)
            self.assertLessEqual(evaluate(y,50,50)['gt'].max(),1+1e-10)
        params['idt']['alpha_sqrtS_per_m']=0
        y=simulate_filter(FilterDesign(),FixedProvider(params),f).y_parameters
        np.testing.assert_allclose(y[:,0,1],0,atol=1e-15)

if __name__=='__main__': unittest.main()
