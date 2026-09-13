import unittest

from sawopt.core.models import BOUNDS, NAMES
from sawopt.reporting.search_space_diagnostics import late_seed_records, propose_s1


def _artifact(values_by_seed):
    trials = []
    for seed, values in enumerate(values_by_seed, 1):
        trials.append({
            "wiring": "center_outer_same",
            "seed": seed,
            "requested_unique_design_budget": 256000,
            "design": dict(zip(NAMES, values)),
            "validated_rank_tuple": [1.0, float(seed), 0.0, 0.0, 0.0],
        })
    return {
        "trials": trials,
        "boundary_rows": [],
    }


class SearchSpaceDiagnostics(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "constraints": {
                "max_length_um": 750,
                "max_width_um": 250,
                "min_electrode_width_um": 0.8,
                "min_electrode_gap_um": 0.8,
                "max_electrodes": 500,
            },
            "optimizer_validation": {
                "bounds": {
                    "io_idt_pairs": {
                        "initial": [8, 100], "hard": [8, 120], "expandable": True,
                    },
                    "center_idt_pairs": {
                        "initial": [10, 80], "hard": [5, 100], "expandable": True,
                        "lower_steps": [8, 5],
                    },
                },
            },
        }

    def test_narrowing_requires_existing_expansion_and_keeps_hard_bounds(self):
        values = [5.0, 9, 14, 40, .5, .5, 80.0]
        artifact = _artifact([values, values, values, values, values])
        s1, rows, _pairs = propose_s1(artifact, self.cfg, [])
        self.assertEqual(s1["io_idt_pairs"]["initial"][0], 8)
        self.assertEqual(s1["center_idt_pairs"]["hard"], [5, 100])
        self.assertEqual(s1["wavelength_um"]["initial"], list(BOUNDS[0]))
        self.assertEqual(s1["aperture_um"]["initial"], list(BOUNDS[6]))
        self.assertEqual(len(rows), len(NAMES))
        for name in NAMES:
            expected = self.cfg["optimizer_validation"]["bounds"].get(name, {}).get(
                "hard", list(BOUNDS[NAMES.index(name)])
            )
            self.assertEqual(s1[name]["hard"], expected)

    def test_boundary_pressure_retains_s0_initial_bounds(self):
        values = [5.0, 9, 14, 40, .5, .5, 80.0]
        artifact = _artifact([values, values, values, values, values])
        artifact["boundary_rows"] = [{"variable": "center_idt_pairs", "direction": "lower", "event": "boundary_pressure"}]
        s1, rows, _pairs = propose_s1(artifact, self.cfg, [])
        self.assertEqual(s1["center_idt_pairs"]["initial"], [10, 80])
        row = next(item for item in rows if item["variable"] == "center_idt_pairs")
        self.assertIn("boundary_pressure:lower", row["rationale"])

    def test_late_seed_records_uses_128_192_256k_checkpoints(self):
        values = [5.0, 9, 14, 40, .5, .5, 80.0]
        artifact = _artifact([values, values, values, values])
        trials = []
        for record in artifact["trials"]:
            for budget in (128000, 192000, 256000):
                copy = dict(record)
                copy["requested_unique_design_budget"] = budget
                trials.append(copy)
        rows = late_seed_records(trials)
        self.assertEqual(len(rows), 12)
        self.assertEqual(sorted({row["requested_unique_design_budget"] for row in rows}), [128000, 192000, 256000])


if __name__ == "__main__":
    unittest.main()
