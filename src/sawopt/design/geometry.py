"""Pure geometry measurement and modeled constraint inputs."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping, Sequence

import numpy as np

from .topology import RESONATOR_BOUNDS
from .space import T1_DIMENSION


def geometry(d, c):
    """Return manufacturing dimensions and normalized violations.

    Legacy ``FilterDesign`` objects follow the historical scalar calculation
    exactly. Stage 3.6 release-space objects may expose ``section_geometry``;
    that method supplies the mirrored nine-region chain with local wavelength
    and aperture values. Parallel tracks own device-level width/length
    accounting rather than being treated as one serial acoustic chain.
    """
    topology_geometry = getattr(d, "topology_geometry", None)
    if callable(topology_geometry):
        return topology_geometry(c)
    profile_fn = getattr(d, "section_geometry", None)
    if callable(profile_fn):
        profile = list(profile_fn())
        if not profile:
            raise ValueError("section_geometry() must return at least one section")
        active = [item for item in profile if item["region"] != "gap"]
        length = float(sum(
            float(item["length_lambda"]) * float(item["wavelength_um"])
            for item in profile
        ))
        electrodes = float(sum(
            float(item.get("electrodes", 0.0)) for item in profile
        ))
        width = float(max(float(item["aperture_um"]) for item in active))
        feature_wavelengths = [float(item["wavelength_um"]) for item in active]
        if any(value <= 0 or not np.isfinite(value) for value in feature_wavelengths):
            raise ValueError("section wavelengths must be finite and positive")
        ratios = [float(item.get("metallization_ratio", d.metallization_ratio)) for item in active]
        widths = [lam * ratio / 2 for lam, ratio in zip(feature_wavelengths, ratios)]
        gaps = [lam * (1 - ratio) / 2 for lam, ratio in zip(feature_wavelengths, ratios)]
        min_width = min(widths)
        min_gap = min(gaps)
    else:
        length = d.wavelength_um * (
            2 * d.io_idt_pairs + d.center_idt_pairs + d.reflector_electrodes
            + 2 * d.idt_gap_lambda + 2 * d.reflector_gap_lambda
        )
        electrodes = 4 * d.io_idt_pairs + 2 * d.center_idt_pairs + 2 * d.reflector_electrodes
        width = d.aperture_um
        min_width = d.wavelength_um * d.metallization_ratio / 2
        min_gap = d.wavelength_um * (1 - d.metallization_ratio) / 2
    violations = [
        max(0, length / c["max_length_um"] - 1),
        max(0, width / c["max_width_um"] - 1),
        max(0, c["min_electrode_width_um"] / min_width - 1),
        max(0, c["min_electrode_gap_um"] / min_gap - 1),
        max(0, electrodes / c["max_electrodes"] - 1),
    ]
    return dict(length_um=length, width_um=width, electrodes=electrodes), violations


def layout(d, resonators, cfg):
    dims, violations = geometry(d, cfg["constraints"])
    tracks = [(
        dims["length_um"] + cfg["layout"]["length_margin_um"],
        d.aperture_um + cfg["layout"]["width_margin_um"],
    )]
    total = dims["electrodes"]
    for resonator in resonators:
        tracks.append((
            resonator.wavelength_um * (
                resonator.pairs + resonator.reflector_electrodes + 2 * resonator.gap_lambda
            ) + cfg["layout"]["length_margin_um"],
            resonator.aperture_um + cfg["layout"]["width_margin_um"],
        ))
        total += 2 * resonator.pairs + 2 * resonator.reflector_electrodes
    width = max(track[0] for track in tracks)
    height = sum(track[1] for track in tracks)
    die = cfg["layout"]["die_um"]
    violations += [
        max(0, width / die[0] - 1),
        max(0, height / die[1] - 1),
        max(0, total / cfg["layout"]["max_total_electrodes"] - 1),
    ]
    return dict(
        footprint_width_um=width,
        footprint_height_um=height,
        footprint_mm2=width * height / 1e6,
        total_electrodes=total,
    ), max(violations)


def hybrid_geometry(
    candidate,
    cfg: Mapping[str, Any],
    *,
    resonator_bounds: Sequence[Sequence[float]] = RESONATOR_BOUNDS,
) -> dict[str, Any]:
    """Return separate DMS, resonator, and combined hypothetical-layout checks.

    The combined layout retains the historical conservative row-placement
    approximation: each resonator occupies a row below the DMS, with the
    configured margins applied to every row. It is a qualification constraint,
    not a foundry layout or a calibrated die estimate.
    """
    settings = cfg["hybrid"]
    dms_dims, dms_values = geometry(candidate.dms_design, cfg["constraints"])
    dms_names = (
        "max_total_acoustic_length", "max_aperture_width", "minimum_electrode_width",
        "minimum_electrode_gap", "max_total_electrode_count",
    )
    dms_violations = {name: float(value) for name, value in zip(dms_names, dms_values)}
    r_bounds = np.asarray(resonator_bounds, dtype=float)
    aperture_bounds = np.asarray(settings["resonator_aperture_bounds_um"], dtype=float)
    min_width = float(cfg["constraints"]["min_electrode_width_um"])
    min_gap = float(cfg["constraints"]["min_electrode_gap_um"])
    resonator_rows = []
    resonator_violations: dict[str, float] = {}
    rows = [(float(dms_dims["length_um"]), float(candidate.dms_design.aperture_um))]
    total_electrodes = float(dms_dims["electrodes"])
    for index, design in enumerate(candidate.resonator_designs):
        vector = candidate.vector[T1_DIMENSION + index * 3:
                                  T1_DIMENSION + (index + 1) * 3]
        local = np.asarray(vector, dtype=float)
        wavelength, pairs, aperture = map(float, local)
        feature_width = wavelength * 0.25  # fixed FilterDesign metallization_ratio = 0.5
        feature_gap = wavelength * 0.25
        length = wavelength * (pairs + design.reflector_electrodes + 2.0 * design.gap_lambda)
        values = {
            "wavelength_lower": max(0.0, r_bounds[0, 0] / wavelength - 1.0),
            "wavelength_upper": max(0.0, wavelength / r_bounds[0, 1] - 1.0),
            "pairs_lower": max(0.0, r_bounds[1, 0] / pairs - 1.0),
            "pairs_upper": max(0.0, pairs / r_bounds[1, 1] - 1.0),
            "aperture_lower": max(0.0, aperture_bounds[0] / aperture - 1.0),
            "aperture_upper": max(0.0, aperture / aperture_bounds[1] - 1.0),
            "minimum_electrode_width": max(0.0, min_width / feature_width - 1.0),
            "minimum_electrode_gap": max(0.0, min_gap / feature_gap - 1.0),
            "max_acoustic_length": max(0.0, length / float(cfg["constraints"]["max_length_um"]) - 1.0),
            "max_aperture_width": max(0.0, aperture / float(cfg["constraints"]["max_width_um"]) - 1.0),
        }
        resonator_violations.update({f"resonator_{index}_{name}": value
                                     for name, value in values.items()})
        resonator_rows.append({
            "design": asdict(design), "length_um": length, "aperture_um": aperture,
            "electrodes": float(2 * design.pairs + 2 * design.reflector_electrodes),
            "feature_width_um": feature_width, "feature_gap_um": feature_gap,
            "violations": values, "max_violation": max(values.values(), default=0.0),
        })
        rows.append((length, aperture))
        total_electrodes += float(2 * design.pairs + 2 * design.reflector_electrodes)

    settings_layout = settings["layout"]
    margin_length = float(settings_layout["length_margin_um"])
    margin_width = float(settings_layout["width_margin_um"])
    footprint_width = max(length + margin_length for length, _ in rows)
    footprint_height = sum(aperture + margin_width for _, aperture in rows)
    die_length, die_width = map(float, settings_layout["die_um"])
    combined_violations = {
        "die_length": max(0.0, footprint_width / die_length - 1.0),
        "die_width": max(0.0, footprint_height / die_width - 1.0),
        "max_total_electrodes": max(
            0.0, total_electrodes / float(settings_layout["max_total_electrodes"]) - 1.0,
        ),
    }
    return {
        "dms": {"dimensions": {key: float(value) for key, value in dms_dims.items()},
                "violations": dms_violations,
                "max_violation": max(dms_violations.values(), default=0.0)},
        "resonators": resonator_rows,
        "resonator_violations": resonator_violations,
        "combined": {
            "footprint_width_um": footprint_width,
            "footprint_height_um": footprint_height,
            "footprint_mm2": footprint_width * footprint_height / 1e6,
            "total_electrodes": total_electrodes,
            "violations": combined_violations,
            "max_violation": max(combined_violations.values(), default=0.0),
        },
        "max_violation": max(
            [*dms_violations.values(), *resonator_violations.values(),
             *combined_violations.values()], default=0.0,
        ),
    }


def assumptions() -> dict[str, Any]:
    """Document fixed one-port model settings already used by resonator_y."""
    return {
        "reflector_electrodes": 40,
        "gap_lambda": 0.0,
        "metallization_ratio": 0.5,
        "thickness_over_lambda": 0.04,
        "source": "existing design.topology.ResonatorDesign and design.space.FilterDesign defaults",
    }


__all__ = ["assumptions", "geometry", "hybrid_geometry", "layout"]
