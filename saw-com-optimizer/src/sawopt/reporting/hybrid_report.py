import csv,json,html
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ..optimization.study import rank,save
from ..core.hybrid import TOPOLOGIES

def diagram(topology, rs=50, rl=50):
    nodes,branches,_=TOPOLOGIES[topology]
    positions={0:65,1:835}
    if nodes[0]>=2: positions[nodes[0]]=300
    if nodes[1]>=2: positions[nodes[1]]=600
    parts=['<svg viewBox="0 0 900 240" role="img" aria-label="Circuit topology" style="width:100%;background:white">']
    def line(x1,y1,x2,y2): parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#213b53" stroke-width="3"/>')
    def label(x,y,t): parts.append(f'<text x="{x}" y="{y}" text-anchor="middle" font-size="18">{t}</text>')
    a,b=map(positions.get,nodes); mid=(a+b)/2
    line(a,70,mid-75,70); line(mid+75,70,b,70)
    parts.append(f'<rect x="{mid-75}" y="40" width="150" height="60" rx="8" fill="#deecfc" stroke="#213b53"/>'); label(mid,77,'DMS')
    for i,(n1,n2) in enumerate(branches):
        x=positions[n1]
        if n2==-1:
            line(x,70,x,115); parts.append(f'<rect x="{x-23}" y="115" width="46" height="55" fill="#fcdfb5" stroke="#213b53"/>')
            label(x,147,f'P{i+1}'); line(x,170,x,195); line(x-20,195,x+20,195); line(x-12,203,x+12,203); line(x-5,211,x+5,211)
        else:
            end=positions[n2]; m=(x+end)/2
            line(x,70,m-28,70); line(m+28,70,end,70)
            parts.append(f'<rect x="{m-28}" y="47" width="56" height="46" fill="#fcdfb5" stroke="#213b53"/>'); label(m,77,f'S{i+1}')
    label(65,30,f'IN {rs:g} Ω'); label(835,30,f'OUT {rl:g} Ω'); parts.append('</svg>')
    return ''.join(parts)

def report(out):
    out=Path(out)
    records=[json.loads(p.read_text(encoding='utf-8')) for p in out.glob('*__*.json') if '.checkpoint.' not in p.name]
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8')) if (out/'manifest.json').exists() else {}
    cfg=manifest.get('config',{})
    spec=cfg.get('spec',{})
    if not records: raise ValueError('No completed trials')
    groups={}
    for r in records: groups.setdefault((r['topology'],r['wiring']),[]).append(r)
    best=sorted([min(v,key=rank) for v in groups.values()],key=rank)
    rows=[]
    for r in best:
        phases=groups[r['topology'],r['wiring']]; phase='refine' if any(v['phase']=='refine' for v in phases) else r['phase']
        selected=[v for v in phases if v['phase']==phase]
        row=dict(topology=r['topology'],wiring=r['wiring'],phase=r['phase'],seed=r['seed'],feasible=r['feasible'],max_violation=r['max_violation'],objective=r['objective'],resonator_count=len(r['resonators']))
        row.update({k:v for k,v in r['metrics'].items() if k!='stop_attenuation_db'})
        row.update({f'stop_{i}_db':v for i,v in enumerate(r['metrics']['stop_attenuation_db'])}); row.update(r['layout'])
        row['seed_il_range_db']=float(np.ptp([v['metrics']['worst_il_db'] for v in selected]))
        row['total_evaluations']=sum(v['evaluations'] for v in phases); rows.append(row)
    with (out/'comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
    with (out/'all_trials.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['topology','wiring','phase','seed','evaluations','failures','elapsed_s','max_violation','objective']
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows({k:r[k] for k in fields} for r in records)
    controls=[r for r in best if r['topology']=='D' and r['metrics']['worst_il_db']<100]; top=best[:3]
    shown={r['result_file']:r for r in top+controls}
    fig,axes=plt.subplots(2,2,figsize=(13,8))
    for r in shown.values():
        data=np.load(out/r['response_file']); f=data['frequencies_hz']/1e6
        label=r['topology']+' / '+r['wiring']
        for ax in axes[0]: ax.plot(f,data['il'],label=label)
        axes[1,0].plot(f,data['vswr'][:,0],label=label); axes[1,1].plot(f,data['vswr'][:,1],label=label)
    p_lo,p_hi=spec.get('passband',(758,803)); p_w=p_hi-p_lo
    axes[0,0].set(xlim=(p_lo-.6*p_w,p_hi+.6*p_w),ylim=(0,30),ylabel='Insertion loss (dB)')
    axes[0,1].set(xlim=(10,1000),ylim=(0,100),ylabel='Attenuation (dB)')
    for lo,hi,target in spec.get('stopbands',[]):
        axes[0,1].plot([lo,hi],[target,target],color='black',ls='--',lw=1)
    vswr_target=spec.get('vswr',2.5)
    for ax in axes[1]: ax.set(xlim=(p_lo,p_hi),ylim=(1,max(15,vswr_target*2))); ax.axhline(vswr_target,c='gray',ls='--')
    axes[1,0].set_ylabel('Input VSWR'); axes[1,1].set_ylabel('Output VSWR')
    axes[0,0].axhline(spec.get('il',3),c='gray',ls='--'); axes[0,0].axvspan(p_lo,p_hi,color='green',alpha=.05)
    for ax in axes.flat: ax.grid(alpha=.25); ax.set_xlabel('MHz')
    axes[0,1].legend(fontsize=7); fig.tight_layout(); fig.savefig(out/'responses.png',dpi=150); plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,6))
    for row in rows:
        if row['worst_il_db']>100: continue
        ax.scatter(row['footprint_mm2'],row['worst_il_db'],s=50+row['resonator_count']*35)
        ax.annotate(row['topology']+' / '+row['wiring'].replace('center_outer_',''),(row['footprint_mm2'],row['worst_il_db']),fontsize=7,xytext=(3,4),textcoords='offset points')
    ax.set(xlabel='Estimated footprint (mm²)',ylabel='Worst passband IL (dB)'); ax.grid(alpha=.25)
    fig.tight_layout(); fig.savefig(out/'tradeoffs.png',dpi=150); plt.close(fig)
    columns=['topology','wiring','worst_il_db','ripple_db','input_vswr','output_vswr','max_violation','total_electrodes','seed_il_range_db']
    table='<tr>'+''.join('<th>'+k+'</th>' for k in columns)+'</tr>'
    for row in rows:
        table+='<tr>'+''.join('<td>'+html.escape(f'{row[k]:.3f}' if isinstance(row[k],float) else str(row[k]))+'</td>' for k in columns)+'</tr>'
    winner=best[0]
    rs=float(winner.get('rs',winner.get('source_impedance_ohm',50))); rl=float(winner.get('rl',winner.get('load_impedance_ohm',rs)))
    style = '''<style>body{font:16px system-ui;max-width:1300px;margin:32px auto;padding:20px;background:#f4f6fa;color:#182b3d}p{line-height:1.9}img{width:100%}table{border-collapse:collapse;background:white;font-size:13px;width:100%}td,th{padding:9px;border-bottom:1px solid #ddd}pre{overflow:auto;background:white;padding:20px}.table{overflow:auto}</style>'''
    page=f'''<!doctype html><html lang="ja"><meta charset="utf-8"><title>{rs:g}Ω/{rl:g}Ω DMS + Ladder</title>{style}<h1>{rs:g} Ω / {rl:g} Ω：DMS＋ラダー共振子</h1><p><b>COM parameters: hypothetical</b>。仮モデル内の探索結果です。実デバイス性能・最適構成の保証ではありません。</p>'''
    page+=f"<p>暫定上位：<b>{winner['topology']} / {winner['wiring']}</b>。最悪帯域内損失 {winner['metrics']['worst_il_db']:.3f} dB。仕様達成：{sum(r['feasible'] for r in best)}/{len(best)}構成・結線。</p>"
    page+=diagram(winner['topology'],rs,rl)
    page+='<p>Sは直列共振子、Pは接地する並列共振子。中心IDT入力・外側IDT同相出力はcenter_outer_same、旧結線はouter_ports。中心入力・外側逆相出力は対称モデルでは伝達が打ち消されます。結線・電極位相の実レイアウト校正は未実施です。</p>'
    page+='<p>未達候補は最大正規化違反、目的関数の順で比較。DMS単独3結線を評価後、単独で最良だった結線だけで12追加構成を探索し、上位3構成とDMS単独を追加探索します。他の結線との組合せ、全トポロジーの大域最適性は未確認です。幅・長さの余白各60 µmによる行配置推定であり、詳細レイアウトではありません。総電極上限500を全素子に適用しています。</p>'
    page+='<div class="table"><table>'+table+'</table></div><p>シード幅は各構成の最新段階内で算出。共通親候補を含むため、幅が小さくても収束の保証ではありません。</p>'
    page+='<img src="responses.png" alt="Frequency response"><img src="tradeoffs.png" alt="Area and loss tradeoff">'
    if (out/'resonators.png').exists():
        page+='<h2>追加共振子の単体特性</h2><img src="resonators.png" alt="Isolated resonator admittance">'
    page+='<h2>上位候補の寸法</h2><pre>'+html.escape(json.dumps({k:winner[k] for k in ['topology','wiring','design','resonators','layout','metrics','violations']},ensure_ascii=False,indent=2))+'</pre>'
    page+='<p><a href="comparison.csv">構成比較CSV</a> / <a href="all_trials.csv">全試行CSV</a>。NPZに周波数・Y行列・S行列・電力利得を保存しています。</p></html>'
    (out/'report.html').write_text(page,encoding='utf-8')
    save(out/'best.json',winner)
    return str(out/'report.html')
