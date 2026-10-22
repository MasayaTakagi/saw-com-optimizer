"""Current filter-design record and its legacy vector decoder.

COM parameter providers and simulation results live in ``sawopt.physics``.
Design-space ownership is scheduled for the R3 migration.
"""
from dataclasses import dataclass, asdict
import numpy as np


@dataclass
class FilterDesign:
    wavelength_um: float = 5.0
    io_idt_pairs: int = 24
    center_idt_pairs: int = 16
    reflector_electrodes: int = 40
    idt_gap_lambda: float = 0.5
    reflector_gap_lambda: float = 0.5
    aperture_um: float = 80.0
    metallization_ratio: float = 0.5
    thickness_over_lambda: float = 0.04


NAMES = list(asdict(FilterDesign()))[:7]
BOUNDS = [(4.6, 5.4), (20, 100), (10, 80), (40, 160), (0, 3), (0, 3), (30, 150)]


def decode(x):
    v = dict(zip(NAMES, map(float, x)))
    for k in NAMES[1:4]:
        v[k] = int(np.floor(v[k] + 0.5))
    return FilterDesign(**v)
