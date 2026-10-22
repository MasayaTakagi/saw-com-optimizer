"""Runtime conversion for normalized literature COM parameters.

The adapter is intentionally separate from :class:`FixedProvider`.  It keeps
the values reported by a source in their published units and derives the
dimensional parameters for each geometry at call time.  It does not
interpolate, borrow fields from M0, or infer missing phase/geometry data.

This module is research-only until the source/convention gate promotes a
profile.  R1 may use an explicitly labelled signed-real phase assumption for
frequency-only diagnostics; that policy is never an implicit fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np


@dataclass(frozen=True)
class NormalizedLiteratureCOMProfile:
    """One immutable normalized COM profile from one source condition.

    ``alpha_n_value`` and ``capacitance_n_value`` are the numerical values in
    the source table before its displayed scale factors are applied.  The
    source units are retained explicitly so the SI conversion is auditable.
    """

    profile_id: str
    substrate: str
    electrode_material: str | None
    temperature_c: float
    wavelength_um: float
    h_over_lambda: float
    metallization_ratio: float
    velocity_m_s: float
    kappa_p_percent: float
    alpha_n_value: float
    alpha_n_scale: float = 1e-5
    alpha_n_unit: str = "ohm^(-1/2)"
    capacitance_n_value: float = 52.80
    capacitance_n_scale: float = 1e-5
    capacitance_n_unit: str = "pF/um"
    gamma_p: float = 0.002684
    kappa_phase_rad: float | None = None
    alpha_phase_rad: float | None = None
    phase_policy: str = "STRICT_SOURCE_PHASE"
    loss_policy: str = "STRICT_SOURCE_LOSS"
    source_status: str = "BLOCKED"

    def __post_init__(self) -> None:
        for name in (
            "temperature_c", "wavelength_um", "h_over_lambda",
            "metallization_ratio", "velocity_m_s", "kappa_p_percent",
            "alpha_n_value", "alpha_n_scale", "capacitance_n_value",
            "capacitance_n_scale", "gamma_p",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.wavelength_um <= 0 or self.velocity_m_s <= 0:
            raise ValueError("wavelength_um and velocity_m_s must be positive")
        if not 0 < self.h_over_lambda < 1:
            raise ValueError("h_over_lambda must be in (0, 1)")
        if not 0 < self.metallization_ratio < 1:
            raise ValueError("metallization_ratio must be in (0, 1)")
        if self.alpha_n_scale <= 0 or self.capacitance_n_scale <= 0:
            raise ValueError("source scale factors must be positive")
        if self.capacitance_n_value < 0 or self.gamma_p < 0:
            raise ValueError("capacitance and attenuation must be non-negative")
        for name in ("kappa_phase_rad", "alpha_phase_rad"):
            value = getattr(self, name)
            if value is not None and not np.isfinite(float(value)):
                raise ValueError(f"{name} must be finite when supplied")
        if self.phase_policy not in {
            "STRICT_SOURCE_PHASE", "SIGNED_REAL_TABLE_ASSUMPTION"
        }:
            raise ValueError(f"unknown phase_policy: {self.phase_policy}")
        if self.loss_policy not in {
            "STRICT_SOURCE_LOSS", "AMPLITUDE_ATTENUATION_ASSUMPTION"
        }:
            raise ValueError(f"unknown loss_policy: {self.loss_policy}")
        if not self.substrate or not self.profile_id:
            raise ValueError("profile_id and substrate are required")

    @property
    def kappa_p(self) -> float:
        """Dimensionless normalized reflection coefficient."""
        return self.kappa_p_percent / 100.0

    @property
    def alpha_n_sqrt_s(self) -> float:
        """Normalized transduction coefficient in sqrt(Siemens)."""
        return self.alpha_n_value * self.alpha_n_scale

    @property
    def capacitance_n_f_per_m(self) -> float:
        """Normalized capacitance converted from the source unit to SI.

        1 pF/um = 1e-6 F/m.
        """
        return self.capacitance_n_value * self.capacitance_n_scale * 1e-6

    def parameters(
        self,
        region: str,
        geometry: Any,
        frequency: Any = None,
        temperature_c: float | None = None,
    ) -> dict[str, Any]:
        """Convert the profile to the solver's dimensional convention.

        The conversion is valid only at the locked temperature and source
        condition.  ``frequency`` is accepted for provider compatibility and
        is deliberately not interpolated.
        """
        del frequency
        if region not in {"idt", "reflector", "gap"}:
            raise ValueError(f"unknown literature COM region: {region!r}")
        if temperature_c is not None and not np.isclose(
            float(temperature_c), self.temperature_c, rtol=0.0, atol=1e-12
        ):
            raise ValueError(
                f"profile {self.profile_id!r} is locked to {self.temperature_c:g} C"
            )
        try:
            lam_um = float(geometry.wavelength_um)
            aperture_um = float(geometry.aperture_um)
        except AttributeError as exc:
            raise TypeError("geometry requires wavelength_um and aperture_um") from exc
        if not np.isfinite([lam_um, aperture_um]).all() or lam_um <= 0 or aperture_um <= 0:
            raise ValueError("geometry wavelength and aperture must be positive finite values")
        kappa_phase = self.kappa_phase_rad
        alpha_phase = self.alpha_phase_rad
        if kappa_phase is None or (region == "idt" and alpha_phase is None):
            if self.phase_policy != "SIGNED_REAL_TABLE_ASSUMPTION":
                raise ValueError("source phase/reference data is required for conversion")
            # R1's explicit diagnostic policy: retain the signed real table
            # value for kappa and use positive real alpha. This is not a
            # production phase claim and is reported by the caller.
            kappa_phase = 0.0 if kappa_phase is None else kappa_phase
            alpha_phase = 0.0 if alpha_phase is None else alpha_phase
        if self.gamma_p and self.loss_policy != "AMPLITUDE_ATTENUATION_ASSUMPTION":
            raise ValueError(
                "source attenuation convention is required before converting gamma"
            )

        lam = lam_um * 1e-6
        aperture = aperture_um * 1e-6
        aperture_ratio = aperture / lam
        kappa = self.kappa_p / lam
        alpha = self.alpha_n_sqrt_s * np.sqrt(aperture_ratio) / lam
        if kappa_phase is not None:
            kappa *= np.exp(1j * float(kappa_phase))
        if alpha_phase is not None:
            alpha *= np.exp(1j * float(alpha_phase))
        capacitance = self.capacitance_n_f_per_m * aperture_ratio
        gamma = self.gamma_p / lam
        if region == "gap":
            kappa = 0.0j
            alpha = 0.0j
            capacitance = 0.0
        elif region == "reflector":
            alpha = 0.0j
            capacitance = 0.0

        values = {
            "velocity": self.velocity_m_s,
            "kappa": complex(kappa),
            "alpha": complex(alpha),
            "capacitance": float(capacitance),
            "loss": float(gamma),
        }
        if not all(np.isfinite(value).all() if isinstance(value, np.ndarray)
                   else np.isfinite(value) for value in values.values()):
            raise ValueError("non-finite converted COM parameter")
        return values

    def normalized_identities(self, geometry: Any) -> dict[str, float]:
        """Return reverse-normalized values for audit/tests."""
        values = self.parameters("idt", geometry)
        lam = float(geometry.wavelength_um) * 1e-6
        aperture = float(geometry.aperture_um) * 1e-6
        return {
            "kappa_p": values["kappa"].real * lam,
            "alpha_n": values["alpha"].real * lam / np.sqrt(aperture / lam),
            "capacitance_n": values["capacitance"] * lam / aperture,
            "gamma_p": values["loss"] * lam,
        }


def profile_from_mapping(profile: Mapping[str, Any]) -> NormalizedLiteratureCOMProfile:
    """Build a profile from the repository YAML schema without fallbacks."""
    required = {
        "profile_id", "substrate", "temperature_c", "wavelength_um",
        "h_over_lambda", "metallization_ratio", "velocity_m_s",
        "kappa_p_percent", "alpha_n_value", "capacitance_n_value", "gamma_p",
    }
    missing = sorted(required.difference(profile))
    if missing:
        raise ValueError(f"literature profile is missing fields: {missing}")
    return NormalizedLiteratureCOMProfile(
        profile_id=str(profile["profile_id"]),
        substrate=str(profile["substrate"]),
        electrode_material=profile.get("electrode_material"),
        temperature_c=float(profile["temperature_c"]),
        wavelength_um=float(profile["wavelength_um"]),
        h_over_lambda=float(profile["h_over_lambda"]),
        metallization_ratio=float(profile["metallization_ratio"]),
        velocity_m_s=float(profile["velocity_m_s"]),
        kappa_p_percent=float(profile["kappa_p_percent"]),
        alpha_n_value=float(profile["alpha_n_value"]),
        alpha_n_scale=float(profile.get("alpha_n_scale", 1e-5)),
        alpha_n_unit=str(profile.get("alpha_n_unit", "ohm^(-1/2)")),
        capacitance_n_value=float(profile["capacitance_n_value"]),
        capacitance_n_scale=float(profile.get("capacitance_n_scale", 1e-5)),
        capacitance_n_unit=str(profile.get("capacitance_n_unit", "pF/um")),
        gamma_p=float(profile["gamma_p"]),
        kappa_phase_rad=profile.get("kappa_phase_rad"),
        alpha_phase_rad=profile.get("alpha_phase_rad"),
        phase_policy=str(profile.get("phase_policy", "STRICT_SOURCE_PHASE")),
        loss_policy=str(profile.get("loss_policy", "STRICT_SOURCE_LOSS")),
        source_status=str(profile.get("source_status", "BLOCKED")),
    )


__all__ = ["NormalizedLiteratureCOMProfile", "profile_from_mapping"]
