"""Aggregate fixed-family, topology-envelope and loading-control reports."""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from ..optimization.study import rank, save


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def report(out):
    out = Path(out)
    manifest = _read(out / 'manifest.json')
    cfg = manifest['config']
    summary = _read(out / 'stage2_summary.json')
    impedances = [float(z) for z in summary['impedances_ohm']]
    pairs = [tuple(pair) for pair in summary['final_pairs']]
    control = {float(r['rs']): r for r in _read(out / 'loading_control.json')}

    family = {}
    seed_spread = {}
    for z0 in impedances:
        for topology, wiring in pairs:
            pattern = f'Z{z0:g}_*__R{z0:g}_L{z0:g}__{topology}__{wiring}__*.json'
            records = [_read(p) for p in out.glob(pattern) if '.checkpoint.' not in p.name]
            if not records:
                raise ValueError(f'Missing neighbor results for {z0:g} ohm {topology}/{wiring}')
            winner = min(records, key=rank)
            family[z0, topology, wiring] = winner
            same_phase = [r for r in records if r['phase'] == winner['phase']]
            seed_spread[z0, topology, wiring] = float(np.ptp([r['metrics']['worst_il_db'] for r in same_phase]))

    envelope = {z: min((family[z, *pair] for pair in pairs), key=rank) for z in impedances}
    rows = []
    for z in impedances:
        winner = envelope[z]
        row = {
            'z0_ohm': z, 'topology': winner['topology'], 'wiring': winner['wiring'],
            'feasible': winner['feasible'], 'max_violation': winner['max_violation'],
            'worst_il_db': winner['metrics']['worst_il_db'],
            'ripple_db': winner['metrics']['ripple_db'],
            'input_vswr': winner['metrics']['input_vswr'],
            'output_vswr': winner['metrics']['output_vswr'],
            'footprint_mm2': winner['layout']['footprint_mm2'],
            'total_electrodes': winner['layout']['total_electrodes'],
            'seed_il_range_db': seed_spread[z, winner['topology'], winner['wiring']],
            'dimensions': winner['dimensions'], 'population': winner['population'],
            'evaluations': winner['evaluations'],
            'adaptive_rounds': winner['adaptive_rounds_completed'],
            'search_frequency_count': winner['search_frequency_count'],
            'response_file': winner['response_file'],
            'loading_only_worst_il_db': control[z]['metrics']['worst_il_db'],
        }
        row.update({f'stop_{i}_db': value for i, value in enumerate(winner['metrics']['stop_attenuation_db'])})
        rows.append(row)
    with (out / 'impedance_envelope.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)

    fixed_rows = []
    for z in impedances:
        for topology, wiring in pairs:
            r = family[z, topology, wiring]
            fixed_rows.append({
                'z0_ohm': z, 'topology': topology, 'wiring': wiring,
                'feasible': r['feasible'], 'max_violation': r['max_violation'],
                'worst_il_db': r['metrics']['worst_il_db'],
                'ripple_db': r['metrics']['ripple_db'],
                'input_vswr': r['metrics']['input_vswr'],
                'output_vswr': r['metrics']['output_vswr'],
                'footprint_mm2': r['layout']['footprint_mm2'],
                'total_electrodes': r['layout']['total_electrodes'],
                'seed_il_range_db': seed_spread[z, topology, wiring],
            })
    with (out / 'fixed_family.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fixed_rows[0].keys())
        writer.writeheader(); writer.writerows(fixed_rows)

    fig, axes = plt.subplots(3, 3, figsize=(16, 13))
    x = np.asarray(impedances)
    for pair in pairs:
        label = '/'.join(pair)
        axes[0, 0].plot(x, [family[z, *pair]['metrics']['worst_il_db'] for z in x], 'o--', alpha=.55, label=label)
    axes[0, 0].plot(x, [envelope[z]['metrics']['worst_il_db'] for z in x], 'ko-', lw=2.5, label='free-topology envelope')
    axes[0, 0].plot(x, [control[z]['metrics']['worst_il_db'] for z in x], 's:', lw=2, label='50-ohm geometry loading-only')
    axes[0, 0].set_ylabel('Worst passband IL (dB)'); axes[0, 0].legend(fontsize=7)
    series = [
        ('max_violation', lambda r: r['max_violation']),
        ('ripple_db', lambda r: r['metrics']['ripple_db']),
        ('input_vswr', lambda r: r['metrics']['input_vswr']),
        ('output_vswr', lambda r: r['metrics']['output_vswr']),
        ('footprint_mm2', lambda r: r['layout']['footprint_mm2']),
        ('total_electrodes', lambda r: r['layout']['total_electrodes']),
        ('seed_il_range_db', lambda r: seed_spread[r['rs'], r['topology'], r['wiring']]),
    ]
    for ax, (label, getter) in zip(axes.flat[1:8], series):
        ax.plot(x, [getter(envelope[z]) for z in x], 'o-'); ax.set_ylabel(label)
    labels = [f"{envelope[z]['topology']}\n{envelope[z]['wiring']}" for z in x]
    axes[2, 2].scatter(x, np.arange(len(x)))
    axes[2, 2].set_yticks(np.arange(len(x)), labels=labels, fontsize=7)
    axes[2, 2].set_ylabel('Selected topology / wiring')
    for ax in axes.flat:
        ax.set_xlabel('Z0 (ohm)'); ax.grid(alpha=.25)
    fig.tight_layout(); fig.savefig(out / 'impedance_summary.png', dpi=150); plt.close(fig)

    fig, stop_axes = plt.subplots(len(cfg['spec']['stopbands']), 1, figsize=(10, 3*len(cfg['spec']['stopbands'])), sharex=True)
    stop_axes = np.atleast_1d(stop_axes)
    for index, (ax, band) in enumerate(zip(stop_axes, cfg['spec']['stopbands'])):
        ax.plot(x, [envelope[z]['metrics']['stop_attenuation_db'][index] for z in x], 'o-')
        ax.axhline(band[2], color='gray', ls='--'); ax.set_ylabel(f'{band[0]:g}-{band[1]:g} MHz (dB)'); ax.grid(alpha=.25)
    stop_axes[-1].set_xlabel('Z0 (ohm)'); fig.tight_layout(); fig.savefig(out / 'stopbands.png', dpi=150); plt.close(fig)

    headers = ['z0_ohm', 'topology', 'wiring', 'worst_il_db', 'max_violation', 'ripple_db', 'input_vswr', 'output_vswr', 'loading_only_worst_il_db']
    table = '<tr>' + ''.join(f'<th>{h}</th>' for h in headers) + '</tr>'
    for row in rows:
        table += '<tr>' + ''.join(f'<td>{html.escape(f"{row[h]:.4g}" if isinstance(row[h], float) else str(row[h]))}</td>' for h in headers) + '</tr>'
    page = f'''<!doctype html><html lang="ja"><meta charset="utf-8"><title>Stage 2 impedance study</title><style>body{{font:16px system-ui;max-width:1300px;margin:32px auto;padding:20px;background:#f4f6fa;color:#182b3d}}p{{line-height:1.8}}img{{width:100%}}table{{border-collapse:collapse;background:white;width:100%}}td,th{{padding:8px;border-bottom:1px solid #ddd}}.table{{overflow:auto}}</style><h1>Stage 2：構成とインピーダンスの共同探索</h1><p><b>COM parameters: {html.escape(str(cfg['com'].get('provenance','unknown')))}</b>。各Z0で独立に構成×結線を段階選抜し、その後だけ隣接Z0の設計を等予算のwarm startとして使用しています。</p>'''
    page += '<p>太線が構成自由の包絡、破線が構成固定、点線が50 Ω最適形状を固定したloading-only対照です。候補は密・適応グリッドで順位付けされています。</p>'
    page += '<div class="table"><table>' + table + '</table></div><img src="impedance_summary.png"><img src="stopbands.png">'
    page += '<p><a href="impedance_envelope.csv">包絡CSV</a> / <a href="fixed_family.csv">構成固定CSV</a>。仮COM定数による探索であり、実デバイスの最適インピーダンスを示しません。</p></html>'
    (out / 'report.html').write_text(page, encoding='utf-8')
    save(out / 'envelope.json', [envelope[z] for z in impedances])
    return str(out / 'report.html')
