import numpy as np


def evaluate(y, rs, rl):
    """Evaluate a reciprocal/passive two-port for positive real terminations.

    Phasor convention: peak voltage. The source is a 1 V peak Thevenin source,
    so Pavs=1/(8*Rs), while PL=|Vl|^2/(2*Rl). For these real references,
    gt equals |S21|^2 up to numerical roundoff.
    """
    y = np.asarray(y, dtype=complex)
    if y.ndim != 3 or y.shape[1:] != (2, 2):
        raise ValueError('y must have shape (frequency, 2, 2)')
    if not np.isfinite(y).all():
        raise ValueError('Non-finite two-port admittance')
    if not np.isscalar(rs) or not np.isscalar(rl) or np.iscomplexobj(rs) or np.iscomplexobj(rl):
        raise ValueError('Only positive real scalar terminations are supported')
    rs = float(rs)
    rl = float(rl)
    if not np.isfinite(rs) or not np.isfinite(rl) or rs <= 0 or rl <= 0:
        raise ValueError('Positive finite real terminations required')

    a = y.copy()
    a[:, 0, 0] += 1/rs
    a[:, 1, 1] += 1/rl
    b = np.zeros((len(y), 2, 1), complex)
    b[:, 0, 0] = 1/rs
    try:
        v = np.linalg.solve(a, b)[..., 0]
    except np.linalg.LinAlgError as exc:
        raise ValueError('Singular terminated two-port solve') from exc

    gt = 4*rs/rl*np.abs(v[:, 1])**2

    root = np.sqrt([rs, rl])
    yn = y*root[None, :, None]*root[None, None, :]
    eye = np.broadcast_to(np.eye(2), yn.shape)
    try:
        s = np.linalg.solve(eye + yn, eye - yn)
    except np.linalg.LinAlgError as exc:
        raise ValueError('Singular Y-to-S conversion') from exc

    gamma = np.abs(np.diagonal(s, axis1=1, axis2=2))
    vswr = (1 + gamma)/np.maximum(1 - gamma, 1e-14)
    return dict(
        gt=gt,
        il=-10*np.log10(np.maximum(gt, 1e-300)),
        s=s,
        vswr=vswr,
        source_impedance_ohm=rs,
        load_impedance_ohm=rl,
    )

