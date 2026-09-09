import unittest
import numpy as np

from sawopt.core.com import block


def legacy_scalar_block(f, length, lam, p, gap=False):
    n=len(f); delta=2*np.pi*f/p['velocity']-(0 if gap else 2*np.pi/lam)-1j*p['loss']
    k=p['kappa']; alpha=p['alpha']; c=p['capacitance']
    a=np.zeros((n,2,2),complex); a[:,0,0]=-1j*delta; a[:,1,1]=1j*delta
    a[:,0,1]=1j*k; a[:,1,0]=-1j*np.conj(k)
    q=np.sqrt(abs(k)**2-delta**2+0j)*length
    small=abs(q)<1e-3; sh=np.empty(n,complex); ch=np.empty(n,complex); hh=np.empty(n,complex)
    z=q[small]**2; sh[small]=1+z/6+z*z/120+z*z*z/5040
    ch[small]=.5+z/24+z*z/720+z*z*z/40320; hh[small]=1/6+z/120+z*z/5040+z*z*z/362880
    t=q[~small]; sh[~small]=np.sinh(t)/t; ch[~small]=(np.cosh(t)-1)/t**2; hh[~small]=(np.sinh(t)/t-1)/t**2
    eye=np.eye(2)[None]; T=np.cosh(q)[:,None,None]*eye+length*sh[:,None,None]*a
    F=length*sh[:,None,None]*eye+length**2*ch[:,None,None]*a; H=length**2*ch[:,None,None]*eye+length**3*hh[:,None,None]*a
    b=np.array([1j*alpha,-1j*np.conj(alpha)]); row=np.array([-2j*np.conj(alpha),-2j*alpha]); u=F@b
    P=np.zeros((n,3,3),complex); P[:,0,0]=-T[:,1,0]/T[:,1,1]; P[:,0,1]=1/T[:,1,1]; P[:,0,2]=-u[:,1]/T[:,1,1]
    P[:,1,0]=T[:,0,0]+T[:,0,1]*P[:,0,0]; P[:,1,1]=T[:,0,1]*P[:,0,1]; P[:,1,2]=u[:,0]+T[:,0,1]*P[:,0,2]
    r=row@F; P[:,2,0]=r[:,0]+r[:,1]*P[:,0,0]; P[:,2,1]=r[:,1]*P[:,0,1]
    P[:,2,2]=r[:,1]*P[:,0,2]+row@H@b+1j*2*np.pi*f*c*length
    return P


class ScalarRegression(unittest.TestCase):
    def test_hardened_solver_matches_prepatch_scalar_solver(self):
        f=np.linspace(700e6,900e6,401); p=dict(velocity=3900.,kappa=4000+300j,alpha=1000-50j,capacitance=1e-8,loss=350.)
        old=legacy_scalar_block(f,100e-6,5e-6,p); new=block(f,100e-6,5e-6,p)
        delta=np.max(np.abs(old-new)); scale=np.max(np.abs(old))
        self.assertLessEqual(delta,2e-14+2e-12*scale)


if __name__=='__main__': unittest.main()
