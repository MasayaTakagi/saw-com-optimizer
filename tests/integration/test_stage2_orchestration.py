import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sawopt.__main__ import _refinement_points
from sawopt.reporting.hybrid_report import diagram
from sawopt.optimization.stage2_study import successive_halving, neighbor_refinement


def fake_result(topology, wiring, seed, phase, rs, score):
    return {
        'topology': topology, 'wiring': wiring, 'seed': seed, 'phase': phase,
        'rs': rs, 'rl': rs, 'feasible': False, 'max_violation': score,
        'violations': {'test': score}, 'objective': 1e6*(1+score),
        'metrics': {'worst_il_db': 5+score}, 'design': {}, 'resonators': [],
        'x': [score], 'result_file': f'{phase}-{topology}-{wiring}-{seed}.json',
    }


class Stage2Orchestration(unittest.TestCase):
    def test_joint_screening_keeps_cross_wiring_candidate(self):
        calls = []
        scores = {('D','a'):.2, ('D','b'):.8, ('P_D','a'):.7, ('P_D','b'):.1}
        def fake(_out, _cfg, topology, wiring, seed, phase, _iterations, parent=None, rs=None, rl=None, warm_starts=None):
            calls.append((topology,wiring,phase))
            return fake_result(topology,wiring,seed,phase,rs,scores[topology,wiring])
        cfg = {'screening': {'low_iterations':0,'keep_fraction':.5,'medium_iterations':0,'medium_keep':1,'refine_iterations':0},
               'topologies':['D','P_D'],'wirings':['a','b'],'seeds':[1]}
        with tempfile.TemporaryDirectory() as tmp, patch('sawopt.optimization.stage2_study.optimize_case', side_effect=fake):
            _latest, finalists = successive_halving(Path(tmp), cfg, 50.)
        self.assertTrue(all((t,w,'Z50_low') in calls for t in ('D','P_D') for w in ('a','b')))
        self.assertEqual(finalists, [('P_D','b')])
        self.assertEqual('a', min(('a','b'), key=lambda w: scores['D',w]))

    def test_neighbor_warm_starts_are_adjacent_and_equal_budget(self):
        calls=[]
        def fake(_out,_cfg,topology,wiring,seed,phase,iterations,parent=None,rs=None,rl=None,warm_starts=None):
            calls.append((rs,iterations,len(warm_starts or [])))
            return fake_result(topology,wiring,seed,phase,rs,.1)
        pair=('D','a'); coarse={z:{pair:fake_result(*pair,1,'coarse',z,.2)} for z in (20.,50.,100.)}
        cfg={'screening':{'neighbor_iterations':3},'seeds':[1]}
        with tempfile.TemporaryDirectory() as tmp, patch('sawopt.optimization.stage2_study.optimize_case',side_effect=fake):
            neighbor_refinement(Path(tmp),cfg,[20.,50.,100.],coarse,[pair])
        self.assertEqual(calls,[(20.,3,1),(50.,3,2),(100.,3,1)])

    def test_refine_semantics_and_dynamic_diagram(self):
        with self.assertRaisesRegex(ValueError, 'only defined for symmetric'):
            _refinement_points('optimize', 5, [], [50])
        with self.assertRaisesRegex(ValueError, 'No completed'):
            _refinement_points('sweep', 5, [], [50])
        svg=diagram('D',33,77)
        self.assertIn('IN 33 Ω',svg); self.assertIn('OUT 77 Ω',svg)


if __name__=='__main__': unittest.main()
