import numpy as np


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

def geometry(d,c):
    length=d.wavelength_um*(2*d.io_idt_pairs+d.center_idt_pairs+d.reflector_electrodes+2*d.idt_gap_lambda+2*d.reflector_gap_lambda)
    electrodes=4*d.io_idt_pairs+2*d.center_idt_pairs+2*d.reflector_electrodes
    width=d.wavelength_um*d.metallization_ratio/2
    gap=d.wavelength_um*(1-d.metallization_ratio)/2
    v=[max(0,length/c['max_length_um']-1),max(0,d.aperture_um/c['max_width_um']-1),
       max(0,c['min_electrode_width_um']/width-1),max(0,c['min_electrode_gap_um']/gap-1),max(0,electrodes/c['max_electrodes']-1)]
    return dict(length_um=length,width_um=d.aperture_um,electrodes=electrodes),v

def _band_grid(band, max_step_mhz=None, fallback_points=181):
    """Build a deterministic grid for one band.

    ``max_step_mhz`` is deliberately a configuration value rather than a
    physics constant.  The fallback point count keeps old configurations
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

    Existing callers used ``grid(spec, True)`` for dense validation.  New code
    should call :func:`search_grid` or :func:`validation_grid` explicitly.
    """
    return validation_grid(spec, cfg) if final else search_grid(spec, cfg)

def measure(f,response,d,cfg):
    s=cfg['spec']; mhz=f/1e6; il=response['il']; vs=response['vswr']
    mask=(mhz>=s['passband'][0])&(mhz<=s['passband'][1])
    stops=[float(il[(mhz>=a)&(mhz<=b)].min()) for a,b,_ in s['stopbands']]
    metrics=dict(worst_il_db=float(il[mask].max()),ripple_db=float(np.ptp(il[mask])),input_vswr=float(vs[mask,0].max()),output_vswr=float(vs[mask,1].max()),stop_attenuation_db=stops)
    dims,gv=geometry(d,cfg['constraints']); metrics.update(dims)
    violations=dict(il=max(0,metrics['worst_il_db']/s['il']-1),ripple=max(0,metrics['ripple_db']/s['ripple']-1),
        input_vswr=max(0,metrics['input_vswr']/s['vswr']-1),output_vswr=max(0,metrics['output_vswr']/s['vswr']-1))
    violations.update({f'stop_{i}':max(0,(b[2]-stops[i])/b[2]) for i,b in enumerate(s['stopbands'])})
    violations['geometry']=max(gv)
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
