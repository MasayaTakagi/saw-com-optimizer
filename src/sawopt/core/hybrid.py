"""Evidence-only legacy seven-coordinate hybrid evaluation path.

Current design records and reusable geometry live in ``sawopt.design``. The
legacy response path is retained for its existing study/test evidence; current
Stage 4A/B/C and shared DMS evaluation use ``sawopt.evaluation`` directly.
"""
from dataclasses import asdict

import numpy as np

from ..design.geometry import layout
from ..design.space import FilterDesign, decode
from ..design.topology import TOPOLOGIES, decode_resonator
from ..evaluation import compose_stage4a_y, measure, resonator_admittance
from ..physics.com import FixedProvider, simulate_filter, validate_admittance
from ..physics.elements import circuit_y as _circuit_y
from ..physics.network import evaluate


def _termination_from_cfg(cfg, explicit, key, default=50.0):
    value = cfg.get(key, default) if explicit is None else explicit
    value = float(value)
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f'{key} must be a positive finite real impedance')
    return value


def response(x, topology, wiring, cfg, f, rs=None, rl=None, *, measure_result=True):
    """Evaluate one legacy candidate at positive-real source/load impedances.

    This seven-coordinate route is retained as evidence only. Stage-specific
    current evaluation uses the shared DMS/hybrid design-space interface.
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
    ys = [resonator_admittance(r, provider, f) for r in resonators]
    combined = _circuit_y(
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
