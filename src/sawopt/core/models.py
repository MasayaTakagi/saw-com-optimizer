from dataclasses import dataclass, asdict
from typing import Protocol
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


class ComParameterProvider(Protocol):
    def parameters(self, region, geometry, frequency, temperature_c=25): ...


class FixedProvider:
    """Backward-compatible fixed COM parameter provider.

    Physics represented here is intentionally limited:
    - kappa_lambda is converted to kappa [1/m] using the current wavelength.
    - alpha scales as sqrt(aperture/reference_aperture).
    - capacitance scales linearly with aperture/reference_aperture.
    - loss_db_per_lambda is converted to amplitude attenuation [1/m].

    Region-specific velocity_m_s and loss_db_per_lambda are supported when
    present, falling back to the historical global values. Frequency,
    temperature, metallization ratio and thickness are not interpolated in
    this provider; use a future CalibratedProvider for those dependencies.
    """

    REQUIRED_REGION_KEYS = ('kappa_lambda', 'alpha_sqrtS_per_m', 'capacitance_F_per_m')

    def __init__(self, values):
        self.values = values
        if not isinstance(values, dict):
            raise TypeError('COM values must be a mapping')
        ref_ap = float(values.get('reference_aperture_um', 0.0))
        if not np.isfinite(ref_ap) or ref_ap <= 0:
            raise ValueError('reference_aperture_um must be finite and positive')

    def parameters(self, region, geometry, frequency, temperature_c=25):
        del frequency, temperature_c  # Explicitly unused by FixedProvider.
        p = self.values
        if region not in p:
            raise KeyError(f'Missing COM region {region!r}')
        r = p[region]
        if region != 'gap':
            missing = [k for k in self.REQUIRED_REGION_KEYS if k not in r]
            if missing:
                raise KeyError(f'Missing COM keys for region {region!r}: {missing}')

        lam = float(geometry.wavelength_um)*1e-6
        if not np.isfinite(lam) or lam <= 0:
            raise ValueError('geometry wavelength must be finite and positive')
        aperture_um = float(geometry.aperture_um)
        if not np.isfinite(aperture_um) or aperture_um <= 0:
            raise ValueError('geometry aperture must be finite and positive')
        aperture = aperture_um / float(p['reference_aperture_um'])

        # Permit physically useful region-specific values while keeping old
        # configuration files valid via global fallbacks.
        velocity = r.get('velocity_m_s', p.get('velocity_m_s'))
        loss_db_per_lambda = r.get('loss_db_per_lambda', p.get('loss_db_per_lambda', 0.0))
        if velocity is None:
            raise KeyError(f'No velocity_m_s supplied for region {region!r} or globally')
        velocity = float(velocity)
        loss_db_per_lambda = float(loss_db_per_lambda)
        if not np.isfinite(velocity) or velocity <= 0:
            raise ValueError(f'velocity_m_s for region {region!r} must be finite and positive')
        if not np.isfinite(loss_db_per_lambda) or loss_db_per_lambda < 0:
            raise ValueError(f'loss_db_per_lambda for region {region!r} must be finite and non-negative')

        if region == 'gap':
            # block(..., gap=True) also forces these to zero. Returning zeros
            # here keeps the provider semantically correct on its own.
            kappa = 0.0j
            alpha = 0.0j
            capacitance = 0.0
        else:
            kappa = (
                float(r['kappa_lambda'])/lam
                * np.exp(1j*float(r.get('kappa_phase_rad', 0.0)))
            )
            alpha = (
                float(r['alpha_sqrtS_per_m'])*np.sqrt(aperture)
                * np.exp(1j*float(r.get('alpha_phase_rad', 0.0)))
            )
            capacitance = float(r['capacitance_F_per_m'])*aperture

        return dict(
            velocity=velocity,
            kappa=kappa,
            alpha=alpha,
            capacitance=capacitance,
            loss=loss_db_per_lambda*np.log(10)/20/lam,
        )


class CalibratedProvider:
    """Validated contract for future FEM/measurement-derived COM data.

    No interpolation or extrapolation is implemented until calibrated tables
    are supplied. Calling ``parameters`` therefore fails explicitly.
    """

    REQUIRED_METADATA = (
        'substrate_stack', 'electrode_material', 'metallization_ratio',
        'thickness_over_lambda', 'reference_aperture_um', 'extraction_method',
        'extraction_version', 'validity_domain', 'parameter_units',
        'normalization_convention',
    )

    def __init__(self, metadata, tables=None):
        if not isinstance(metadata, dict):
            raise TypeError('Calibration metadata must be a mapping')
        missing = [key for key in self.REQUIRED_METADATA if key not in metadata]
        if missing:
            raise ValueError(f'Missing calibration metadata: {missing}')
        self.metadata = dict(metadata)
        self.tables = tables

    def parameters(self, region, geometry, frequency, temperature_c=25):
        del region, geometry, frequency, temperature_c
        raise NotImplementedError(
            'CalibratedProvider requires FEM/measurement parameter tables and '
            'a validated interpolation policy; silent extrapolation is disabled'
        )


@dataclass
class SimulationResult:
    frequencies_hz: np.ndarray
    y_parameters: np.ndarray
    diagnostics: dict
