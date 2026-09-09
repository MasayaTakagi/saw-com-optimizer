import csv,json,html
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ..optimization.study import rank
from ..core.models import NAMES

def report(out):
    out=Path(out); records=[json.loads(p.read_text(encoding='utf-8')) for p in out.glob('R*_seed*.json') if '.checkpoint.' not in p.name]
    if not records: raise ValueError('No completed optimization results')
    groups={}
    for r in records: groups.setdefault((r['rs'],r['rl']),[]).append(r)
    best=[min(groups[k],key=rank) for k in sorted(groups)]
    rows=[]
    for r in best:
        row=dict(rs=r['rs'],rl=r['rl'],seed=r['seed'],feasible=r['feasible'],objective=r['objective'],max_violation=r['max_violation'])
        row.update({k:v for k,v in r['metrics'].items() if k!='stop_attenuation_db'})
        row.update({f'stop_{i}_db':v for i,v in enumerate(r['metrics']['stop_attenuation_db'])})
        row.update(r['design']); row['seed_il_range_db']=float(np.ptp([v['metrics']['worst_il_db'] for v in groups[r['rs'],r['rl']]])); rows.append(row)
    with (out/'comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    fig,axes=plt.subplots(3,3,figsize=(15,11)); x=[r['rs'] for r in best]
    keys=['worst_il_db','ripple_db','input_vswr','output_vswr','length_um','objective','stop_0_db','stop_1_db','seed_il_range_db']
    for ax,key in zip(axes.flat,keys):
        ax.plot(x,[r[key] for r in rows],'o-'); ax.set(xlabel='Common resistance (ohm)',ylabel=key); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(out/'comparison.png',dpi=140); plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(15,4))
    for r in sorted(best,key=rank)[:3]:
        data=np.load(out/r['response_file']); f=data['frequencies_hz']/1e6
        for ax,(i,j) in zip(axes,[(1,0),(0,0),(1,1)]): ax.plot(f,20*np.log10(np.maximum(abs(data['s'][:,i,j]),1e-15)),label=f"{r['rs']:g} ohm")
    for ax,label in zip(axes,['S21','S11','S22']): ax.set(xlim=(700,920),ylim=(-100,1),xlabel='MHz',ylabel=label+' (dB)'); ax.grid(alpha=.3); ax.legend()
    fig.tight_layout(); fig.savefig(out/'responses.png',dpi=140); plt.close(fig)
    fig,axes=plt.subplots(2,4,figsize=(15,7))
    for ax,key in zip(axes.flat,NAMES): ax.plot(x,[r['design'][key] for r in best],'o-'); ax.set(xlabel='ohm',ylabel=key); ax.grid(alpha=.3)
    axes.flat[-1].axis('off'); fig.tight_layout(); fig.savefig(out/'geometry.png',dpi=140); plt.close(fig)
    winner=min(best,key=rank)
    intro=f"仮モデル内の暫定上位: {winner['rs']:g} Ω。全仕様達成: {sum(r['feasible'] for r in best)}/{len(best)}条件。"
    columns=['rs','worst_il_db','ripple_db','input_vswr','max_violation','seed_il_range_db','feasible']
    table='<tr>'+''.join('<th>'+k+'</th>' for k in columns)+'</tr>'
    for row in rows: table+='<tr>'+''.join('<td>'+html.escape(f'{row[k]:.4g}' if isinstance(row[k],float) else str(row[k]))+'</td>' for k in columns)+'</tr>'
    page='''<!doctype html><html lang="ja"><meta charset="utf-8"><title>SAW COM impedance study</title><style>body{font:16px system-ui;max-width:1200px;margin:40px auto;padding:20px;background:#f5f7fa;color:#18253a}img{width:100%;background:white}table{border-collapse:collapse;width:100%;background:white}td,th{padding:10px;border-bottom:1px solid #ddd}p{line-height:1.8}</style><h1>SAW 入出力インピーダンス探索</h1><p><b>COM parameters: hypothetical</b> — 実デバイスの推奨抵抗ではありません。小規模探索の動作確認結果です。広帯域外挿・中央IDT結線・実測校正は未検証です。</p>'''
    page+='<p>'+intro+'</p><p>未達条件は最大正規化制約違反、目的関数の順で比較。シード間の損失幅が大きい条件は探索不足です。周波数の適応細分化も全共振捕捉を保証しません。</p><table>'+table+'</table>'
    page+=''.join(f'<img src="{name}.png" alt="{name}">' for name in ['comparison','responses','geometry'])
    page+='<p><a href="comparison.csv">全阻止帯域・寸法を含むCSV</a></p></html>'
    (out/'report.html').write_text(page,encoding='utf-8'); return str(out/'report.html')
