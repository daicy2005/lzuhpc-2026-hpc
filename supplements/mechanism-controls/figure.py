"""Draw the fixed off/on comparison from its audited summary (editable SVG)."""
import argparse
import json
from pathlib import Path


def draw(summary, output):
    groups={g['group']:g for g in summary['groups']}
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="750" height="294" viewBox="0 0 750 294">',
        '<rect width="750" height="294" fill="white"/>',
        '<g font-family="Microsoft YaHei, sans-serif" fill="#233f58">']
    def text(x,y,value,size=14,anchor='start',fill='#233f58'):
        parts.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="{fill}">{value}</text>')
    text(64,23,'epoch 时间比 off / on',17)
    for i,(label,color) in enumerate((('集中布局','#285f86'),('分散布局','#c98140'))):
        x=470+i*125
        parts.append(f'<rect x="{x}" y="10" width="17" height="13" rx="2" fill="{color}"/>')
        text(x+23,22,label)
    x0,y0,plot_h=64,239,180
    for tick in range(7):
        y=y0-plot_h*tick/6
        parts.append(f'<line x1="{x0}" y1="{y}" x2="714" y2="{y}" stroke="#dde5ec" stroke-width="1"/>')
        text(52,y+5,str(tick),14,'end')
    y=y0-plot_h/6
    parts.append(f'<line x1="{x0}" y1="{y}" x2="714" y2="{y}" stroke="#7993a4" stroke-dasharray="5 4"/>')
    for i,(seed,grain) in enumerate(((170021,8),(170021,256),(176023,8),(176023,256))):
        center=146+163*i
        for j,(layout,color) in enumerate((('concentrated','#285f86'),('spread','#c98140'))):
            ratio=groups[f'balance-s{seed}-g{grain}-{layout}']['ratio']
            assert 0<=ratio<=6
            x=center-43+j*46
            h=ratio*plot_h/6
            parts.append(f'<rect x="{x}" y="{y0-h:.3f}" width="38" height="{h:.3f}" rx="2" fill="{color}"/>')
            text(x+19,y0-h-7,f'{ratio:.2f}',14,'middle')
        text(center,262,f'{seed} / {grain}',14,'middle')
    text(389,286,'输入 seed / grain',14,'middle',fill='#596774')
    parts+=['</g>','</svg>']
    Path(output).write_text('\n'.join(parts)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('summary')
    p.add_argument('output')
    a=p.parse_args()
    draw(json.loads(Path(a.summary).read_text(encoding='utf-8')),a.output)
