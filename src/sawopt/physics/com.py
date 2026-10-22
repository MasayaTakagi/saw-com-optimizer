"""Finite uniform COM sections, connected through a global acoustic solve.

COM convention
--------------
exp(+j*w*t), x increasing left to right, peak voltage V, terminal current I
into the transducer. R/S are forward/backward acoustic envelopes and the
average acoustic power flux is |R|^2 - |S|^2.
"""
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import numpy as np


_SERIES_LIMIT = 5e-2


def _broadcast_parameter(value, n, name, *, complex_ok=True):
    """Return a scalar/array COM parameter as a frequency-length vector."""
    dtype = complex if complex_ok else float
    a = np.asarray(value, dtype=dtype)
    try:
        a = np.broadcast_to(a, (n,)).astype(dtype, copy=False)
    except ValueError as exc:
        raise ValueError(f"COM parameter {name!r} must be scalar or shape ({n},)") from exc
    if not np.isfinite(a).all():
        raise ValueError(f"Non-finite COM parameter: {name}")
    return a


def _entire_functions(q):
    """Stable sinh(q)/q and related entire functions.

    Returns
    -------
    sh : sinh(q)/q
    ch : (cosh(q)-1)/q^2
    hh : (sinh(q)/q-1)/q^2

    A Taylor branch avoids cancellation around q=0. No inverse(A) is used.
    """
    q = np.asarray(q, dtype=complex)
    sh = np.empty_like(q)
    ch = np.empty_like(q)
    hh = np.empty_like(q)
    small = np.abs(q) < _SERIES_LIMIT

    z = q[small] ** 2
    # Horner forms through z^5.  At |q| < 0.05, truncation is far below
    # double-precision roundoff for the intended COM calculations.
    sh[small] = 1 + z * (1/6 + z * (1/120 + z * (1/5040 + z * (1/362880 + z/39916800))))
    ch[small] = 1/2 + z * (1/24 + z * (1/720 + z * (1/40320 + z * (1/3628800 + z/479001600))))
    hh[small] = 1/6 + z * (1/120 + z * (1/5040 + z * (1/362880 + z * (1/39916800 + z/6227020800))))

    t = q[~small]
    sh[~small] = np.sinh(t) / t
    # 2*sinh(t/2)^2 is more accurate than cosh(t)-1 for moderately small t.
    ch[~small] = 2 * np.sinh(t / 2) ** 2 / t ** 2
    hh[~small] = (sh[~small] - 1) / t ** 2
    return sh, ch, hh


def block(f, length, lam, p, gap=False):
    """Build the finite-section 3x3 acoustic/electrical P matrix."""
    f = np.asarray(f, dtype=float)
    if f.ndim != 1 or len(f) == 0 or not np.isfinite(f).all() or np.any(f <= 0):
        raise ValueError("frequencies must be a non-empty finite 1-D array of positive Hz values")
    if not np.isfinite(length) or length < 0:
        raise ValueError("section length must be finite and non-negative")
    if not np.isfinite(lam) or lam <= 0:
        raise ValueError("wavelength must be finite and positive")

    n = len(f)
    velocity = _broadcast_parameter(p['velocity'], n, 'velocity', complex_ok=False)
    loss = _broadcast_parameter(p['loss'], n, 'loss', complex_ok=False)
    if np.any(velocity <= 0):
        raise ValueError("COM velocity must be positive")
    if np.any(loss < 0):
        raise ValueError("COM amplitude attenuation must be non-negative")

    delta = 2*np.pi*f/velocity - (0 if gap else 2*np.pi/lam) - 1j*loss

    # A true free gap has no distributed reflection, transduction or static C.
    # Enforce this here so a malformed provider cannot silently create an IDT
    # inside a gap. Gap velocity/loss still come from the provider.
    if gap:
        k = np.zeros(n, dtype=complex)
        alpha = np.zeros(n, dtype=complex)
        c = np.zeros(n, dtype=float)
    else:
        k = _broadcast_parameter(p['kappa'], n, 'kappa')
        alpha = _broadcast_parameter(p['alpha'], n, 'alpha')
        c = _broadcast_parameter(p['capacitance'], n, 'capacitance', complex_ok=False)
        if np.any(c < 0):
            raise ValueError("COM capacitance per metre must be non-negative")

    a = np.zeros((n, 2, 2), complex)
    a[:, 0, 0] = -1j*delta
    a[:, 1, 1] = 1j*delta
    a[:, 0, 1] = 1j*k
    a[:, 1, 0] = -1j*np.conj(k)

    q = np.sqrt(np.abs(k)**2 - delta**2 + 0j) * length
    sh, ch, hh = _entire_functions(q)
    eye = np.eye(2)[None]
    T = np.cosh(q)[:, None, None]*eye + length*sh[:, None, None]*a
    F = length*sh[:, None, None]*eye + length**2*ch[:, None, None]*a
    H = length**2*ch[:, None, None]*eye + length**3*hh[:, None, None]*a

    b = np.stack((1j*alpha, -1j*np.conj(alpha)), axis=1)              # (n,2)
    row = np.stack((-2j*np.conj(alpha), -2j*alpha), axis=1)          # (n,2)
    u = np.einsum('nij,nj->ni', F, b)

    denom = T[:, 1, 1]
    P = np.zeros((n, 3, 3), complex)
    with np.errstate(divide='ignore', invalid='ignore', over='ignore'):
        P[:, 0, 0] = -T[:, 1, 0] / denom
        P[:, 0, 1] = 1 / denom
        P[:, 0, 2] = -u[:, 1] / denom
        P[:, 1, 0] = T[:, 0, 0] + T[:, 0, 1]*P[:, 0, 0]
        P[:, 1, 1] = T[:, 0, 1]*P[:, 0, 1]
        P[:, 1, 2] = u[:, 0] + T[:, 0, 1]*P[:, 0, 2]

        r = np.einsum('ni,nij->nj', row, F)
        row_H_b = np.einsum('ni,nij,nj->n', row, H, b)
        P[:, 2, 0] = r[:, 0] + r[:, 1]*P[:, 0, 0]
        P[:, 2, 1] = r[:, 1]*P[:, 0, 1]
        P[:, 2, 2] = (
            r[:, 1]*P[:, 0, 2]
            + row_H_b
            + 1j*2*np.pi*f*c*length
        )

    if not np.isfinite(P).all():
        bad = np.flatnonzero(~np.isfinite(P).all(axis=(1, 2)))
        raise ValueError(
            "Non-finite COM P matrix. The section may be singular or have "
            f"excessive |kappa*L|; first bad frequency index: {int(bad[0]) if len(bad) else 'unknown'}"
        )
    return P


def simulate_filter(
    design, com_provider, frequencies_hz, center='grounded', wiring='outer_ports',
    debug_diagnostics=False,
):
    if center not in ('grounded', 'floating'):
        raise ValueError('Unknown center termination')
    d = design
    f = np.asarray(frequencies_hz, dtype=float)
    lam = d.wavelength_um*1e-6
    regions = [
        ('reflector', d.reflector_electrodes/2, None),
        ('gap', d.reflector_gap_lambda, None),
        ('idt', d.io_idt_pairs, 0),
        ('gap', d.idt_gap_lambda, None),
        ('idt', d.center_idt_pairs, 1),
        ('gap', d.idt_gap_lambda, None),
        ('idt', d.io_idt_pairs, 2),
        ('gap', d.reflector_gap_lambda, None),
        ('reflector', d.reflector_electrodes/2, None),
    ]
    y, solve_diagnostics = acoustic_admittance(
        d, com_provider, f, regions, 3, return_diagnostics=True,
        debug_diagnostics=debug_diagnostics,
    )

    if wiring in ('center_outer_same', 'center_outer_opposite'):
        # V_IDT = B V_external, I_external = B^T I_IDT.
        sign = 1 if wiring == 'center_outer_same' else -1
        B = np.array([[0, 1], [1, 0], [0, sign]])
        out = B.T @ y @ B
    elif wiring == 'outer_ports':
        out = y[:, [0, 2]][:, :, [0, 2]]
        if center == 'floating':
            ycc = y[:, 1, 1]
            if np.any(np.abs(ycc) < np.finfo(float).tiny):
                raise ValueError('Floating-center elimination is singular (Ycc is zero)')
            out -= y[:, [0, 2], 1, None] * y[:, None, 1, [0, 2]] / ycc[:, None, None]
    else:
        raise ValueError('Unknown DMS wiring')

    diagnostics = validate_admittance(out, frequencies_hz=f)
    diagnostics.update(solve_diagnostics)
    return SimulationResult(f, out, diagnostics)


def acoustic_admittance(
    d, com_provider, f, regions, ports, return_diagnostics=False,
    debug_diagnostics=False, section_geometries=None,
):
    """Connect finite sections with radiating external acoustic boundaries.

    ``debug_diagnostics`` enables a per-frequency matrix condition number.
    It remains off during optimization because the SVD is expensive.
    """
    f = np.asarray(f, dtype=float)
    lam = d.wavelength_um*1e-6
    n = len(f)
    m = len(regions)
    if section_geometries is not None:
        if len(section_geometries) != m:
            raise ValueError('section_geometries must match regions length')
    mat = np.broadcast_to(np.eye(2*m), (n, 2*m, 2*m)).astype(complex).copy()
    rhs = np.zeros((n, 2*m, ports), complex)
    blocks = []

    for j, (region, l, port) in enumerate(regions):
        local_geometry = d if section_geometries is None else section_geometries[j]
        local_lam = float(local_geometry.wavelength_um)*1e-6
        p = com_provider.parameters(region, local_geometry, f)
        P = block(f, l*local_lam, local_lam, p, region == 'gap')
        blocks.append(P)
        if j > 0:
            mat[:, 2*j:2*j+2, 2*j-1] -= P[:, :2, 0]
        if j < m-1:
            mat[:, 2*j:2*j+2, 2*j+2] -= P[:, :2, 1]
        if port is not None:
            rhs[:, 2*j:2*j+2, port] = P[:, :2, 2]

    try:
        waves = np.linalg.solve(mat, rhs)
    except np.linalg.LinAlgError as exc:
        raise ValueError('Singular global acoustic solve') from exc

    # Cheap backward-error diagnostic. This is intentionally not a condition
    # number because an SVD per frequency is too expensive in an optimizer.
    residual = mat @ waves - rhs
    residual_norm = np.linalg.norm(residual, axis=(1, 2))
    scale = (
        np.linalg.norm(mat, axis=(1, 2))*np.linalg.norm(waves, axis=(1, 2))
        + np.linalg.norm(rhs, axis=(1, 2))
        + np.finfo(float).tiny
    )
    rel_residual = residual_norm / scale
    worst_residual_index = int(np.argmax(rel_residual))
    if not np.isfinite(rel_residual).all() or np.max(rel_residual) > 1e-8:
        raise ValueError(f'Unreliable global acoustic solve: max relative residual={np.max(rel_residual):.3e}')

    y = np.zeros((n, ports, ports), complex)
    for j, (_, _, port) in enumerate(regions):
        if port is None:
            continue
        P = blocks[j]
        if j > 0:
            y[:, port, :] += P[:, 2, 0, None]*waves[:, 2*j-1, :]
        if j < m-1:
            y[:, port, :] += P[:, 2, 1, None]*waves[:, 2*j+2, :]
        y[:, port, port] += P[:, 2, 2]
    diagnostics = {
        'max_acoustic_solve_residual': float(rel_residual[worst_residual_index]),
        'worst_acoustic_residual_frequency_hz': float(f[worst_residual_index]),
    }
    if debug_diagnostics:
        condition_number = np.linalg.cond(mat)
        worst_condition_index = int(np.argmax(condition_number))
        diagnostics.update({
            'max_acoustic_condition_number': float(condition_number[worst_condition_index]),
            'worst_acoustic_condition_frequency_hz': float(f[worst_condition_index]),
        })
    return (y, diagnostics) if return_diagnostics else y


def validate_admittance(out, frequencies_hz=None, *, passivity_atol=1e-8,
                        reciprocity_atol=1e-7, rtol=1e-10):
    """Validate finite, passive and reciprocal electrical admittance matrices."""
    out = np.asarray(out, dtype=complex)
    if out.ndim != 3 or out.shape[1] != out.shape[2]:
        raise ValueError('Admittance must have shape (frequency, port, port)')
    if not np.isfinite(out).all():
        raise ValueError('Non-finite admittance')

    hermitian_g = (out + out.conj().transpose(0, 2, 1))/2
    eig = np.linalg.eigvalsh(hermitian_g)
    reciprocity_error = float(np.abs(out - out.transpose(0, 2, 1)).max())
    scale = max(1.0, float(np.abs(out).max()))
    passivity_tol = passivity_atol + rtol*scale
    reciprocity_tol = reciprocity_atol + rtol*scale
    conductance_by_frequency = eig.min(axis=1)
    min_index = int(np.argmin(conductance_by_frequency))
    reciprocity_by_frequency = np.abs(
        out - out.transpose(0, 2, 1)
    ).max(axis=(1, 2))
    reciprocity_index = int(np.argmax(reciprocity_by_frequency))
    diagnostics = dict(
        min_conductance_eigenvalue=float(conductance_by_frequency[min_index]),
        reciprocity_error=reciprocity_error,
        admittance_scale=scale,
        passivity_tolerance=passivity_tol,
        reciprocity_tolerance=reciprocity_tol,
    )
    if frequencies_hz is not None:
        frequencies_hz = np.asarray(frequencies_hz, dtype=float)
        if frequencies_hz.ndim != 1 or len(frequencies_hz) != len(out):
            raise ValueError('frequencies_hz must match the admittance frequency axis')
        diagnostics.update({
            'worst_conductance_frequency_hz': float(frequencies_hz[min_index]),
            'worst_reciprocity_frequency_hz': float(frequencies_hz[reciprocity_index]),
        })
    if eig.min() < -passivity_tol or reciprocity_error > reciprocity_tol:
        raise ValueError(f'Invalid COM result: {diagnostics}')
    return diagnostics


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


class LiteratureProfileProvider:
    """Select one complete, indivisible COM material profile.

    This provider deliberately has no interpolation or fallback behavior.  A
    production profile must carry its own metadata and all COM values required
    by :class:`FixedProvider`; missing ``alpha``, capacitance, loss, or phase
    information therefore fails at construction instead of being silently
    borrowed from the hypothetical M0 profile.
    """

    REQUIRED_METADATA = (
        'substrate', 'electrode_material', 'h_over_lambda',
        'metallization_ratio', 'frequency_context', 'phasor_convention',
        'x_direction', 'acoustic_normalization', 'electrical_normalization',
        'parameter_definitions', 'normalization_convention',
        'source_citation', 'source_publication_metadata',
    )
    ALLOWED_CLASSIFICATIONS = {
        'CURRENT_BASELINE', 'DIRECT_COMPATIBLE', 'CONVERTIBLE_WITH_DERIVATION',
    }
    PROFILE_REGIONS = ('idt', 'reflector', 'gap')

    def __init__(self, profiles: Mapping[str, Mapping[str, Any]], profile_id: str):
        if not isinstance(profiles, Mapping):
            raise TypeError('profiles must be a mapping of profile id to profile')
        if profile_id not in profiles:
            raise KeyError(f'Unknown COM profile {profile_id!r}')
        profile = profiles[profile_id]
        if not isinstance(profile, Mapping):
            raise TypeError(f'COM profile {profile_id!r} must be a mapping')

        metadata = profile.get('metadata')
        missing = [key for key in self.REQUIRED_METADATA
                   if not isinstance(metadata, Mapping) or not metadata.get(key)]
        if missing:
            raise ValueError(
                f'Profile {profile_id!r} is missing required metadata: {missing}'
            )
        classification = str(profile.get('classification', ''))
        if classification not in self.ALLOWED_CLASSIFICATIONS:
            raise ValueError(
                f'Profile {profile_id!r} is not production-eligible: '
                f'{classification or "missing classification"}'
            )
        com = profile.get('com')
        self._validate_com(profile_id, com)

        self.profile_id = str(profile_id)
        self.classification = classification
        self.metadata = dict(metadata)
        self.source = profile.get('source')
        self._provider = FixedProvider(dict(com))

    @classmethod
    def _validate_com(cls, profile_id: str, com: Any) -> None:
        if not isinstance(com, Mapping):
            raise ValueError(f'Profile {profile_id!r} must contain a COM mapping')
        if not np.isfinite(float(com.get('reference_aperture_um', np.nan))) or \
                float(com.get('reference_aperture_um', 0.0)) <= 0:
            raise ValueError(
                f'Profile {profile_id!r} requires a positive reference_aperture_um'
            )
        if 'velocity_m_s' not in com and any(
                'velocity_m_s' not in com.get(region, {})
                for region in cls.PROFILE_REGIONS
        ):
            raise ValueError(
                f'Profile {profile_id!r} requires velocity_m_s globally or per region'
            )
        if 'loss_db_per_lambda' not in com and any(
                'loss_db_per_lambda' not in com.get(region, {})
                for region in cls.PROFILE_REGIONS
        ):
            raise ValueError(
                f'Profile {profile_id!r} requires explicit loss_db_per_lambda '
                'globally or for every region'
            )
        for region in cls.PROFILE_REGIONS:
            values = com.get(region)
            if not isinstance(values, Mapping):
                raise ValueError(f'Profile {profile_id!r} is missing region {region!r}')
            if region != 'gap':
                missing = [key for key in FixedProvider.REQUIRED_REGION_KEYS
                           if key not in values]
                if missing:
                    raise ValueError(
                        f'Profile {profile_id!r} region {region!r} is missing {missing}'
                    )

    def parameters(self, region, geometry, frequency, temperature_c=25):
        return self._provider.parameters(region, geometry, frequency, temperature_c)


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
