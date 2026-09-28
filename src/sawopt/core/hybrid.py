"""COM one-port resonators and electrical nodal interconnection."""
from dataclasses import dataclass, asdict
import numpy as np
from .models import FilterDesign, FixedProvider, decode
from .com import acoustic_admittance, simulate_filter, validate_admittance
from .network import evaluate
from .metrics import measure, geometry


@dataclass
class ResonatorDesign:
    wavelength_um: float = 5.0
    pairs: int = 25
    aperture_um: float = 70.0
    reflector_electrodes: int = 40
    gap_lambda: float = 0.0


RESONATOR_BOUNDS = [(4.5, 5.6), (10, 60), (30, 150)]


def decode_resonator(x):
    return ResonatorDesign(float(x[0]), int(np.floor(x[1] + .5)), float(x[2]))


def resonator_y(d, provider, f):
    geom = FilterDesign(
        wavelength_um=d.wavelength_um,
        io_idt_pairs=d.pairs,
        aperture_um=d.aperture_um,
    )
    regions = [
        ('reflector', d.reflector_electrodes/2, None),
        ('gap', d.gap_lambda, None),
        ('idt', d.pairs, 0),
        ('gap', d.gap_lambda, None),
        ('reflector', d.reflector_electrodes/2, None),
    ]
    y = acoustic_admittance(geom, provider, np.asarray(f), regions, 1)
    validate_admittance(y)
    return y[:, 0, 0]


def circuit_y(dms, branches, ports=(0, 1), dms_nodes=(0, 1), node_count=2):
    """Stamp admittances then eliminate internal nodes. Ground is node -1."""
    n = len(dms)
    Y = np.zeros((n, node_count, node_count), complex)
    for i, ni in enumerate(dms_nodes):
        for j, nj in enumerate(dms_nodes):
            Y[:, ni, nj] += dms[:, i, j]
    for a, b, y in branches:
        if a >= 0:
            Y[:, a, a] += y
        if b >= 0:
            Y[:, b, b] += y
        if a >= 0 and b >= 0:
            Y[:, a, b] -= y
            Y[:, b, a] -= y

    external = list(ports)
    internal = [i for i in range(node_count) if i not in ports]
    out = Y[:, external][:, :, external]
    if internal:
        Yei = Y[:, external][:, :, internal]
        Yii = Y[:, internal][:, :, internal]
        Yie = Y[:, internal][:, :, external]
        try:
            out = out - Yei @ np.linalg.solve(Yii, Yie)
        except np.linalg.LinAlgError as exc:
            raise ValueError('Singular internal-node elimination') from exc
    validate_admittance(out)
    return out


STAGE4A_TOPOLOGIES = ("D", "P_D", "D_P", "P_D_P")


def compose_stage4a_y(dms_y, topology, resonator_ys=()):
    """Compose a current DMS two-port with zero, one, or two shunt resonators.

    ``P_D`` places one one-port resonator at the source-side terminal, ``D_P``
    at the load-side terminal, and ``P_D_P`` places one at each terminal.
    Resonators are independent acoustic tracks and are connected electrically
    in shunt.  A ``D`` call accepts no resonators and returns the DMS Y matrix
    exactly through the same nodal-composition implementation.
    """
    if topology not in STAGE4A_TOPOLOGIES:
        raise ValueError(f"unsupported Stage 4A topology {topology!r}")
    ys = tuple(np.asarray(value, dtype=complex) for value in resonator_ys)
    expected = {"D": 0, "P_D": 1, "D_P": 1, "P_D_P": 2}[topology]
    if len(ys) != expected:
        raise ValueError(f"{topology} requires exactly {expected} resonator admittances")
    if topology == "D":
        nodes, branches = (0, 1), []
    elif topology == "P_D":
        nodes, branches = (0, 1), [(0, -1)]
    elif topology == "D_P":
        nodes, branches = (0, 1), [(1, -1)]
    else:
        nodes, branches = (0, 1), [(0, -1), (1, -1)]
    if ys:
        branches = [(a, b, value) for (a, b), value in zip(branches, ys)]
    return circuit_y(dms_y, branches, dms_nodes=nodes, node_count=2)


# (DMS nodes, resonator terminals, node count). Added resonators are independent.
TOPOLOGIES = {
    'D': ((0, 1), [], 2),
    'S_D': ((2, 1), [(0, 2)], 3),
    'D_S': ((0, 2), [(2, 1)], 3),
    'P_D': ((0, 1), [(0, -1)], 2),
    'D_P': ((0, 1), [(1, -1)], 2),
    'S_D_S': ((2, 3), [(0, 2), (3, 1)], 4),
    'P_D_P': ((0, 1), [(0, -1), (1, -1)], 2),
    'SP_D': ((2, 1), [(0, 2), (2, -1)], 3),
    'PS_D': ((2, 1), [(0, 2), (0, -1)], 3),
    'D_SP': ((0, 2), [(2, 1), (1, -1)], 3),
    'D_PS': ((0, 2), [(2, 1), (2, -1)], 3),
    'S_D_P': ((2, 1), [(0, 2), (1, -1)], 3),
    'P_D_S': ((0, 2), [(2, 1), (0, -1)], 3),
}


def layout(d, resonators, cfg):
    dims, v = geometry(d, cfg['constraints'])
    # Conservative row placement: each acoustic track gets a pad/wiring margin.
    tracks = [(
        dims['length_um'] + cfg['layout']['length_margin_um'],
        d.aperture_um + cfg['layout']['width_margin_um'],
    )]
    total = dims['electrodes']
    for r in resonators:
        tracks.append((
            r.wavelength_um*(r.pairs + r.reflector_electrodes + 2*r.gap_lambda)
            + cfg['layout']['length_margin_um'],
            r.aperture_um + cfg['layout']['width_margin_um'],
        ))
        total += 2*r.pairs + 2*r.reflector_electrodes
    width = max(t[0] for t in tracks)
    height = sum(t[1] for t in tracks)
    die = cfg['layout']['die_um']
    v += [
        max(0, width/die[0] - 1),
        max(0, height/die[1] - 1),
        max(0, total/cfg['layout']['max_total_electrodes'] - 1),
    ]
    return dict(
        footprint_width_um=width,
        footprint_height_um=height,
        footprint_mm2=width*height/1e6,
        total_electrodes=total,
    ), max(v)


def _termination_from_cfg(cfg, explicit, key, default=50.0):
    value = cfg.get(key, default) if explicit is None else explicit
    value = float(value)
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f'{key} must be a positive finite real impedance')
    return value


def response(x, topology, wiring, cfg, f, rs=None, rl=None, *, measure_result=True):
    """Evaluate one candidate at arbitrary positive-real source/load impedances.

    Backward compatibility: if rs/rl are omitted, read
    cfg['source_impedance_ohm'] / cfg['load_impedance_ohm']; if those keys are
    absent, fall back to the historical 50-ohm behavior.
    """
    rs = _termination_from_cfg(cfg, rs, 'source_impedance_ohm')
    rl = _termination_from_cfg(cfg, rl, 'load_impedance_ohm')

    d = decode(x[:7])
    resonators = [decode_resonator(x[i:i+3]) for i in range(7, len(x), 3)]
    dims, violation = layout(d, resonators, cfg)
    if violation > 0:
        raise ValueError('Layout/manufacturing constraint violation')

    provider = FixedProvider(cfg['com'])
    dms = simulate_filter(d, provider, f, cfg['center'], wiring).y_parameters
    nodes, terminals, node_count = TOPOLOGIES[topology]
    ys = [resonator_y(r, provider, f) for r in resonators]
    combined = circuit_y(
        dms,
        [(a, b, y) for (a, b), y in zip(terminals, ys)],
        dms_nodes=nodes,
        node_count=node_count,
    )
    net = evaluate(combined, rs, rl)
    if net['gt'].max() > 1 + 1e-7:
        raise ValueError('Nonpassive gain')

    if not measure_result:
        return None, net, combined
    result = measure(f, net, d, cfg)
    result.update(
        design=asdict(d),
        resonators=[asdict(r) for r in resonators],
        layout=dims,
        source_impedance_ohm=rs,
        load_impedance_ohm=rl,
        diagnostics=validate_admittance(combined),
    )
    return result, net, combined
