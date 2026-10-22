"""COM response, RF metrics, modeled constraints, and frequency-grid evaluation."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Sequence

import numpy as np

from .design.geometry import geometry
from .design.space import FilterDesign
from .design.topology import (
    DesignSection,
    T0,
    T0_PORT_MATRIX,
    T1,
    T1_PORT_MATRIX,
    T2,
    STAGE4A_TOPOLOGIES,
    TOPOLOGIES,
    t0_sections,
)
from .physics.com import FixedProvider, SimulationResult, simulate_filter, validate_admittance
from .physics.elements import (
    AcousticSection,
    circuit_y,
    parallel_two_port_admittance,
    resonator_y as _calculate_resonator_y,
    simulate_section_chain,
)
from .physics.network import evaluate as evaluate_network


def feasibility_objective(metrics, violations):
    """Scalar search surrogate for the authoritative feasibility-first rank.

    Feasible candidates minimize worst passband IL. Infeasible candidates are
    placed above the feasible range and ordered first by maximum normalized
    violation, then by total violation and IL as deterministic tie-breakers.
    The separated scales preserve that order for the finite normalized-
    violation range used by this model; final reports always retain the
    lexicographic ``validated_rank_tuple`` rather than treating this scalar as
    an exact proof of rank equivalence.
    """
    values = np.asarray(list(violations.values()), dtype=float)
    if not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError('Violations must be finite and non-negative')
    worst = float(values.max(initial=0.0))
    il = float(metrics['worst_il_db'])
    if not np.isfinite(il):
        raise ValueError('Worst insertion loss must be finite')
    if worst <= 1e-10:
        return il, dict(policy='feasible_worst_il', primary=il, secondary=0.0)
    secondary = float(values.sum())
    max_scale = 1e9
    sum_scale = 1e3
    il_scale = 1e-3
    score = (max_scale * (1.0 + worst) +
             sum_scale * min(secondary, 1e6) +
             il_scale * min(max(il, 0.0), 1e6))
    return score, dict(
        policy='infeasible_max_violation', primary=worst, secondary=secondary,
        scales={'max_violation': max_scale, 'sum_violation': sum_scale, 'il': il_scale},
        intended_normalized_violation_range=[0.0, 1e6],
    )


def _band_grid(band, max_step_mhz=None, fallback_points=181):
    """Build a deterministic grid for one band.

    ``max_step_mhz`` is deliberately a configuration value rather than a
    physics constant. The fallback point count keeps old configurations
    numerically compatible when no spacing policy is supplied.
    """
    lo, hi = map(float, band[:2])
    if not np.isfinite([lo, hi]).all() or hi <= lo:
        raise ValueError(f'Invalid frequency band: {band!r}')
    if max_step_mhz is not None:
        step = float(max_step_mhz)
        if not np.isfinite(step) or step <= 0:
            raise ValueError('Frequency max_step_mhz must be finite and positive')
        count = max(2, int(np.ceil((hi - lo) / step)) + 1)
    else:
        count = int(fallback_points)
    return np.linspace(lo, hi, count)


def _grid(spec, *, max_step_mhz=None, band_max_steps=None,
          broad_points=101, band_points=181):
    bands = [spec['passband']] + [b[:2] for b in spec['stopbands']]
    broad = np.linspace(10.0, 1000.0, int(broad_points))
    if band_max_steps is None:
        band_max_steps = [max_step_mhz] * len(bands)
    if len(band_max_steps) != len(bands):
        raise ValueError('band_max_steps must match passband plus stopbands')
    return np.unique(np.concatenate([
        broad,
        *[_band_grid(b, step, band_points) for b, step in zip(bands, band_max_steps)],
    ])) * 1e6


def search_grid(spec, cfg=None):
    """Return the grid used by optimizer objective evaluations."""
    cfg = cfg or {}
    validation = cfg.get('validation', {})
    pass_step = validation.get('search_passband_max_step_mhz',
                               cfg.get('search_passband_max_step_mhz'))
    stop_step = validation.get('search_stopband_max_step_mhz',
                               cfg.get('search_stopband_max_step_mhz'))
    if pass_step is not None or stop_step is not None:
        pass_step = pass_step if pass_step is not None else validation.get('search_max_step_mhz')
        stop_step = stop_step if stop_step is not None else pass_step
        steps = [pass_step] + [stop_step] * len(spec['stopbands'])
    else:
        step = validation.get('search_max_step_mhz')
        if step is None:
            step = cfg.get('search_max_step_mhz')
        steps = None
    # The broad legacy grid remains intentionally sparse; explicit pass/stop
    # bands receive the configured maximum spacing.
    return _grid(spec, max_step_mhz=None if steps else step,
                 band_max_steps=steps, broad_points=101, band_points=181)


def validation_grid(spec, cfg=None):
    """Return the base dense-validation grid before adaptive critical points."""
    cfg = cfg or {}
    step = cfg.get('validation', {}).get('max_step_mhz')
    if step is None:
        step = cfg.get('validation', {}).get('validation_max_step_mhz')
    if step is None:
        step = cfg.get('validation_max_step_mhz', 0.25)
    broad_points = cfg.get('validation', {}).get('broad_points', 5001)
    band_points = cfg.get('validation', {}).get('band_points', 501)
    return _grid(spec, max_step_mhz=step, broad_points=broad_points, band_points=band_points)


def report_grid(spec, cfg=None):
    """Return the broad grid reserved for report plots."""
    del cfg
    return _grid(spec, max_step_mhz=None, broad_points=5001, band_points=501)


def grid(spec, final=False, cfg=None):
    """Backward-compatible grid API.

    Existing callers used ``grid(spec, True)`` for dense validation. New code
    should call :func:`search_grid` or :func:`validation_grid` explicitly.
    """
    return validation_grid(spec, cfg) if final else search_grid(spec, cfg)


def measure(f, response, d, cfg):
    s = cfg['spec']
    mhz = f / 1e6
    il = response['il']
    vs = response['vswr']
    mask = (mhz >= s['passband'][0]) & (mhz <= s['passband'][1])
    stops = [float(il[(mhz >= a) & (mhz <= b)].min()) for a, b, _ in s['stopbands']]
    return_loss = response.get('return_loss_db')
    if return_loss is None:
        gamma = np.abs(np.diagonal(response['s'], axis1=1, axis2=2))
        with np.errstate(divide='ignore'):
            return_loss = -20 * np.log10(gamma)
    metrics = dict(
        worst_il_db=float(il[mask].max()),
        ripple_db=float(np.ptp(il[mask])),
        input_vswr=float(vs[mask, 0].max()),
        output_vswr=float(vs[mask, 1].max()),
        source_return_loss_db_min=float(np.min(return_loss[mask, 0])),
        load_return_loss_db_min=float(np.min(return_loss[mask, 1])),
        stop_attenuation_db=stops,
    )
    dims, geometry_violations = geometry(d, cfg['constraints'])
    metrics.update(dims)
    violations = dict(
        il=max(0, metrics['worst_il_db'] / s['il'] - 1),
        ripple=max(0, metrics['ripple_db'] / s['ripple'] - 1),
        input_vswr=max(0, metrics['input_vswr'] / s['vswr'] - 1),
        output_vswr=max(0, metrics['output_vswr'] / s['vswr'] - 1),
    )
    violations.update({
        f'stop_{i}': max(0, (b[2] - stops[i]) / b[2])
        for i, b in enumerate(s['stopbands'])
    })
    violations['geometry'] = max(geometry_violations)
    objective, parts = feasibility_objective(metrics, violations)
    return dict(
        metrics=metrics,
        violations=violations,
        feasible=max(violations.values()) <= 1e-10,
        max_violation=max(violations.values()),
        objective=objective,
        search_scalar_objective=objective,
        objective_parts=parts,
    )


def evaluate_response(d, cfg, f, rs, rl, wiring="outer_ports"):
    """Return the physical simulation and network response on a supplied grid."""
    simulation = simulate_filter(d, FixedProvider(cfg["com"]), f, cfg["center"], wiring=wiring)
    network = evaluate_network(simulation.y_parameters, rs, rl)
    if network["gt"].max() > 1 + 1e-7:
        raise ValueError("Nonpassive power gain")
    return network, simulation


def evaluate_design(d, cfg, f, rs, rl, wiring="outer_ports"):
    """Evaluate one decoded filter design on a supplied frequency grid."""
    network, simulation = evaluate_response(d, cfg, f, rs, rl, wiring=wiring)
    result = measure(f, network, d, cfg)
    result["diagnostics"] = simulation.diagnostics
    result["search_scalar_objective"] = result["objective"]
    return result, network, simulation


def resonator_admittance(d, provider, frequencies_hz):
    """Adapt a resonator design to the full provider-visible geometry record."""
    geometry_record = FilterDesign(
        wavelength_um=d.wavelength_um,
        io_idt_pairs=d.pairs,
        aperture_um=d.aperture_um,
    )
    return _calculate_resonator_y(
        geometry_record,
        provider,
        frequencies_hz,
        pairs=d.pairs,
        reflector_electrodes=d.reflector_electrodes,
        gap_lambda=d.gap_lambda,
    )


def compose_stage4a_y(dms_y, topology, resonator_ys=()):
    """Compose a current DMS two-port with zero, one, or two shunt resonators.

    ``P_D`` places one one-port resonator at the source-side terminal, ``D_P``
    at the load-side terminal, and ``P_D_P`` places one at each terminal.
    Resonators are independent acoustic tracks and are connected electrically
    in shunt. A ``D`` call accepts no resonators and returns the DMS Y matrix
    exactly through the same nodal-composition implementation.
    """
    if topology not in STAGE4A_TOPOLOGIES:
        raise ValueError(f"unsupported Stage 4A topology {topology!r}")
    ys = tuple(np.asarray(value, dtype=complex) for value in resonator_ys)
    nodes, branches, node_count = TOPOLOGIES[topology]
    expected = {"D": 0, "P_D": 1, "D_P": 1, "P_D_P": 2}[topology]
    if len(ys) != expected:
        raise ValueError(f"{topology} requires exactly {expected} resonator admittances")
    if ys:
        branches = [(a, b, value) for (a, b), value in zip(branches, ys)]
    return circuit_y(dms_y, branches, dms_nodes=nodes, node_count=node_count)


def _physics_sections(sections: Sequence[DesignSection]) -> tuple[AcousticSection, ...]:
    return tuple(AcousticSection(
        section.label, section.region, section.length_lambda, section.wavelength_um,
        section.aperture_um, section.port, section.electrodes,
    ) for section in sections)


def simulate_topology(design: Any, provider: Any, frequencies_hz: Any, topology: str):
    """Return an unterminated two-port simulation for T0, T1, or T2."""
    if topology == T0:
        return simulate_section_chain(
            _physics_sections(t0_sections(design)), provider, frequencies_hz, T0_PORT_MATRIX,
            topology_id=T0,
        )
    if topology == T1:
        return simulate_section_chain(
            _physics_sections(design.sections()), provider, frequencies_hz,
            T1_PORT_MATRIX, topology_id=T1,
        )
    if topology == T2:
        tracks = [
            simulate_section_chain(
                _physics_sections(design.track_sections(design.track_A_main_wavelength_um)),
                provider, frequencies_hz, T0_PORT_MATRIX, topology_id=f"{T2}:A",
            ),
            simulate_section_chain(
                _physics_sections(design.track_sections(design.track_B_main_wavelength_um)),
                provider, frequencies_hz, T0_PORT_MATRIX, topology_id=f"{T2}:B",
            ),
        ]
        return parallel_two_port_admittance(tracks, topology_id=T2)
    raise ValueError(f"unknown topology {topology!r}")


def evaluate_topology_response(
    design, provider, cfg, frequencies_hz, topology: str, *,
    rs: float = 50.0, rl: float = 50.0, require_finite_gain: bool = False,
):
    """Return metrics, network response, and simulation for one topology."""
    simulation = simulate_topology(design, provider, frequencies_hz, topology)
    network = evaluate_network(simulation.y_parameters, rs, rl)
    gain = np.asarray(network["gt"], dtype=float)
    if require_finite_gain and not np.isfinite(gain).all():
        raise ValueError("non-finite transducer power gain")
    if gain.max() > 1.0 + 1e-7:
        raise ValueError("Nonpassive power gain")
    record = measure(np.asarray(frequencies_hz), network, design, cfg)
    return record, network, simulation


def evaluate_topology_design(
    design, provider, cfg, frequencies_hz, topology: str, *, rs: float = 50.0, rl: float = 50.0,
) -> dict[str, Any]:
    """Evaluate one topology while preserving the existing metrics/objective."""
    _dims, geometry_violations = geometry(design, cfg["constraints"])
    if max(geometry_violations, default=0.0) > 0:
        return invalid_topology_record(design, geometry_violations, "manufacturing constraint")
    record, _network, simulation = evaluate_topology_response(
        design, provider, cfg, frequencies_hz, topology, rs=rs, rl=rl,
    )
    record = dict(record)
    record.update({
        "design": asdict(design),
        "topology": topology,
        "source_impedance_ohm": float(rs),
        "load_impedance_ohm": float(rl),
        "diagnostics": simulation.diagnostics,
        "search_scalar_objective": record["objective"],
    })
    return record


def invalid_topology_record(design, geometry_violations: Sequence[float], failure: str):
    violations = {
        "geometry": float(max(geometry_violations, default=0.0)),
        "numerical_failure": 1.0 if failure != "manufacturing constraint" else 0.0,
    }
    return {
        "design": asdict(design),
        "metrics": {"worst_il_db": float("inf"), "ripple_db": float("inf")},
        "violations": violations,
        "max_violation": float(max(violations.values(), default=1.0)),
        "sum_violation": float(sum(violations.values())),
        "feasible": False,
        "failure": failure,
        "objective": float("inf"),
        "search_scalar_objective": float("inf"),
        "topology": None,
    }


__all__ = [
    "compose_stage4a_y", "evaluate_design", "evaluate_response", "evaluate_topology_design",
    "evaluate_topology_response",
    "feasibility_objective", "grid", "measure", "report_grid", "resonator_admittance",
    "invalid_topology_record", "search_grid", "simulate_topology", "validation_grid",
]
