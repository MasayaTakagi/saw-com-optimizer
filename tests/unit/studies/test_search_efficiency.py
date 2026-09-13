import unittest

from sawopt.core.models import BOUNDS, NAMES
from sawopt.studies.search_efficiency import (
    _arm_config, _bounds_for_strategy, _missing_certificate_evidence,
)


class SearchEfficiencyConfigTests(unittest.TestCase):
    def setUp(self):
        self.base = {
            "convergence": {"impedance_ohm": 50.0},
            "optimizer": {"population": 14},
            "optimizer_validation": {
                "bounds": {
                    "io_idt_pairs": {"initial": [8, 100], "hard": [8, 120], "expandable": True},
                    "center_idt_pairs": {"initial": [10, 80], "hard": [5, 100], "expandable": True, "lower_steps": [8, 5]},
                },
                "boundary_detection": {},
                "parallel": {},
            },
        }
        self.s1 = {"bounds": {name: {
            "initial": list(BOUNDS[index]), "hard": list(BOUNDS[index]),
            "expandable": False, "lower_steps": [], "upper_steps": [],
        } for index, name in enumerate(NAMES)}}
        self.s1["bounds"]["center_idt_pairs"] = {
            "initial": [5, 24], "hard": [5, 100], "expandable": True,
            "lower_steps": [8, 5], "upper_steps": [100],
        }
        self.s1["bounds"]["io_idt_pairs"] = {
            "initial": [8, 100], "hard": [8, 120], "expandable": True,
            "lower_steps": [], "upper_steps": [],
        }

    def test_s1_preserves_hard_bounds_and_does_not_freeze_variables(self):
        state = _bounds_for_strategy(self.base, "S1", self.s1)
        self.assertEqual(state["center_idt_pairs"]["active"], [5.0, 24.0])
        self.assertEqual(state["center_idt_pairs"]["hard"], [5.0, 100.0])
        for name in NAMES:
            self.assertLess(state[name]["active"][0], state[name]["active"][1])

    def test_arm_config_is_cold_and_phase_c_uses_fixed_screening_horizon(self):
        state = _bounds_for_strategy(self.base, "S1", self.s1)
        cfg = _arm_config(
            self.base, phase="screening", strategy="S1", optimizer="lshade",
            state=state, seeds=[20260917, 20260918, 20260919, 20260920],
            budgets=[16000, 32000, 64000], workers=4,
        )
        self.assertEqual(cfg["stage3_5_arm"]["cold_start"], True)
        self.assertFalse(cfg["stage3_5_arm"]["source_population_injected"])
        self.assertEqual(cfg["optimizer_validation"]["budgets"], [16000, 32000, 64000])
        self.assertEqual(cfg["optimizer_validation"]["minimum_convergence_budget"], 64000)
        self.assertEqual(cfg["stage3_5_active_bounds"][2], [5.0, 24.0])
        self.assertEqual(cfg["optimizer_validation"]["bounds"]["center_idt_pairs"]["initial"], [5.0, 24.0])

    def test_certificate_evidence_is_fail_closed(self):
        rows = [{
            "grid_converged": True,
            "recovery_pending_confirmation": False,
            "boundary_pending_confirmation": False,
            "hard_bound_unresolved": False,
            "micro_polish_improvement": 0.0,
            "fraction_of_budget_at_last_significant_improvement": None,
            "validation_gap_primary": 0.0,
        }]
        self.assertEqual(
            _missing_certificate_evidence(rows),
            ["fraction_of_budget_at_last_significant_improvement"],
        )


if __name__ == "__main__":
    unittest.main()
