import unittest
from dataclasses import fields

import numpy as np

from sawopt.design.geometry import geometry
from sawopt.evaluation import measure, search_grid, simulate_topology
from sawopt.physics.network import evaluate
from sawopt.io.config import load_experiment_config
from sawopt.design import topology as canonical
from sawopt.design.topology import ThreeIdtDesign
from sawopt.problem.released_dms import ReleasedFilterDesign, simulate_released_filter
from sawopt.studies.dms_topology_common import decode_design, initial_design, provider_for_material


def _current_config():
    return load_experiment_config("configs/studies/dms_topology_screening.yaml")


class DmsTopologyParity(unittest.TestCase):
    def test_t0_decoder_uses_design_owned_record_with_legacy_geometry(self):
        cfg = _current_config()
        vector = [5.0, 24.0, 16.0, 40.0, .5, .5, 80.0, 5.2, 4.9]
        design = decode_design(vector, canonical.T0, cfg)
        self.assertIsInstance(design, ThreeIdtDesign)
        self.assertEqual(design.wavelength_um, vector[0])
        self.assertEqual(design.center_wavelength_um, vector[7])
        self.assertEqual(design.reflector_wavelength_um, vector[8])
        released_reference = ReleasedFilterDesign(**{
            field.name: getattr(design, field.name) for field in fields(ReleasedFilterDesign)
        })
        self.assertEqual(design.section_geometry(), released_reference.section_geometry())

    def test_generalized_t0_response_matches_released_parity_reference(self):
        cfg = _current_config()
        provider, _metadata = provider_for_material("M0", cfg)
        design = initial_design("M0", canonical.T0, cfg)
        released = ReleasedFilterDesign(**{
            field.name: getattr(design, field.name) for field in fields(ReleasedFilterDesign)
        })
        frequencies = np.linspace(758e6, 803e6, 13)

        generalized = simulate_topology(design, provider, frequencies, canonical.T0)
        parity_reference = simulate_released_filter(
            released, provider, frequencies, cfg["center"], wiring="center_outer_same",
        )

        np.testing.assert_allclose(
            generalized.y_parameters, parity_reference.y_parameters, rtol=1e-10, atol=1e-12,
        )

    def test_current_topology_exports_are_canonical(self):
        from sawopt.studies import dms_topology_screening as study

        self.assertIs(study.T0, canonical.T0)
        self.assertIs(study.T1, canonical.T1)
        self.assertIs(study.T2, canonical.T2)
        self.assertIs(study.simulate_topology, simulate_topology)

    def test_mlit_reference_design_metrics_regression(self):
        cfg = _current_config()
        frequencies = search_grid(cfg["spec"], cfg)
        provider, _metadata = provider_for_material("MLIT", cfg)
        reference = {
            canonical.T0: {
                "worst_il_db": 5.54717729290152,
                "ripple_db": 3.5907944846189386,
                "geometry": (392.5298944619181, 148.41366049691598, 162.0),
            },
            canonical.T1: {
                "worst_il_db": 10.066838837687019,
                "ripple_db": 4.242504728282849,
                "geometry": (344.3654494280638, 148.41366049691598, 140.0),
            },
            canonical.T2: {
                "worst_il_db": 23.770954726443527,
                "ripple_db": 20.392420217822114,
                "geometry": (396.45519340653726, 148.41366049691598, 324.0),
            },
        }
        for topology, expected in reference.items():
            design = initial_design("MLIT", topology, cfg)
            if topology == canonical.T0:
                self.assertIsInstance(design, ThreeIdtDesign)
            simulation = simulate_topology(design, provider, frequencies, topology)
            network = evaluate(simulation.y_parameters, 50.0, 50.0)
            record = measure(frequencies, network, design, cfg)
            self.assertAlmostEqual(record["metrics"]["worst_il_db"], expected["worst_il_db"], places=8)
            self.assertAlmostEqual(record["metrics"]["ripple_db"], expected["ripple_db"], places=8)
            dimensions, violations = geometry(design, cfg["constraints"])
            self.assertEqual(max(violations, default=0.0), 0.0)
            for name, target in zip(("length_um", "width_um", "electrodes"), expected["geometry"]):
                self.assertAlmostEqual(dimensions[name], target, places=8)
            self.assertTrue(np.isfinite(simulation.y_parameters).all())


if __name__ == "__main__":
    unittest.main()
