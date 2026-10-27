"""Editable, data-driven plots following the reviewed paper-figure design."""
import html
import argparse
import json
import math
import statistics
from pathlib import Path

INK = '#253744'
MUTED = '#63717B'
GRID = '#E1E6E9'
BLUE = '#31566E'
TEAL = '#27858A'
RUST = '#B66C47'


class SVG:
    def __init__(self, width, height, title, metadata):
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            f'<title>{html.escape(title)}</title>',
            '<metadata>' + html.escape(json.dumps(metadata, ensure_ascii=False)) + '</metadata>',
            f'<rect width="{width}" height="{height}" fill="white"/>',
            '<g font-family="Microsoft YaHei" fill="' + INK + '">',
        ]

    def text(self, x, y, value, size=16, anchor='start', fill=INK):
        self.parts.append(f'<text x="{x:.3f}" y="{y:.3f}" font-size="{size}" text-anchor="{anchor}" fill="{fill}">{html.escape(str(value))}</text>')

    def line(self, x1, y1, x2, y2, stroke=GRID, width=1, dash=None):
        extra = f' stroke-dasharray="{dash}"' if dash else ''
        self.parts.append(f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" stroke="{stroke}" stroke-width="{width}"{extra}/>')

    def rect(self, x, y, width, height, fill, stroke='none', sw=1):
        self.parts.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{width:.3f}" height="{height:.3f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def circle(self, x, y, radius=4, stroke=BLUE):
        self.parts.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{radius}" fill="white" stroke="{stroke}" stroke-width="1.5"/>')

    def diamond(self, x, y, radius=6, fill=BLUE):
        self.parts.append(f'<polygon points="{x:.3f},{y-radius:.3f} {x+radius:.3f},{y:.3f} {x:.3f},{y+radius:.3f} {x-radius:.3f},{y:.3f}" fill="{fill}"/>')

    def hatched_bar(self, x, y, width, height, color=RUST):
        self.rect(x, y, width, height, '#FCF8F5')
        # Bounded segments work in PDF renderers without SVG pattern support.
        for k in range(0, math.ceil(width + height), 12):
            low, high = max(0, k-height), min(width, k)
            if high > low:
                self.line(x+low, y+height-k+low, x+high, y+height-k+high, color, .9)
        self.rect(x, y, width, height, 'none', color, 1.3)

    def save(self, path):
        Path(path).write_text('\n'.join(self.parts + ['</g>', '</svg>'])+'\n', encoding='utf-8')


def draw_raytracing(upstream, final, output):
    assert len(upstream) == len(final) == 3
    median_ratio = statistics.median(upstream) / statistics.median(final)
    metadata = {'chart': 'raytracing', 'x_scale': 'log', 'x_domain': [50, 2500],
                'upstream_seconds': upstream, 'final_seconds': final,
                'median_ratio': median_ratio, 'range_definition': 'observed min and max, not a confidence interval'}
    svg = SVG(900, 245, '光线追踪：三次渲染耗时与中位数', metadata)
    left, right, top, bottom = 125, 735, 42, 184
    def x(value):
        assert 50 <= value <= 2500
        return left + (right-left) * math.log(value/50) / math.log(2500/50)
    svg.text(left, 21, f'中位数耗时比 {median_ratio:.2f}×', 17)
    svg.circle(604, 15, 3.5)
    svg.text(617, 21, '单次运行', 14)
    svg.diamond(724, 15, 5)
    svg.text(737, 21, '中位数', 14)
    for tick in (50, 100, 200, 500, 1000, 2000):
        xx = x(tick)
        svg.line(xx, top, xx, bottom, GRID, .8)
        svg.line(xx, bottom, xx, bottom+5, MUTED, 1)
        svg.text(xx, bottom+24, tick, 14, 'middle', MUTED)
    svg.line(left, bottom, right, bottom, MUTED, 1.1)
    for row, label, values, color in ((76, '原版 O2', upstream, BLUE), (137, '最终版', final, TEAL)):
        svg.text(left-17, row+5, label, 17, 'end')
        lo, hi, med = min(values), max(values), statistics.median(values)
        svg.line(x(lo), row+5, x(hi), row+5, color, 1.5)
        for edge in (lo, hi):
            svg.line(x(edge), row, x(edge), row+10, color, 1.2)
        # Vertical offsets distinguish nearly identical samples; only x encodes time.
        for offset, value in zip((-16, -5, 15), values):
            svg.circle(x(value), row+offset, 4, color)
        svg.diamond(x(med), row+5, 5.8, color)
        svg.text(891, row+10, f'{med:.3f} s', 17, 'end', color)
    svg.text((left+right)/2, 235, 'Render time / s（对数刻度）', 15, 'middle')
    svg.save(output)


def draw_worksteal(summary, output):
    groups = {g['group']: g for g in summary['groups']}
    rows = []
    for seed in (170021, 176023):
        for grain in (8, 256):
            for layout in ('concentrated', 'spread'):
                group = groups[f'balance-s{seed}-g{grain}-{layout}']
                medians = {c['label']: c['epoch_median'] for c in group['conditions']}
                assert all(len(c['samples']) == 5 for c in group['conditions'])
                assert math.isclose(group['ratio'], medians['off']/medians['on'], rel_tol=1e-12)
                rows.append({'seed': seed, 'grain': grain, 'layout': layout, 'ratio': group['ratio']})
    svg = SVG(900, 330, '相同空闲策略下的工作窃取收益',
              {'chart': 'worksteal', 'y_domain': [0, 6], 'quantity': 'median epoch off / median epoch on', 'rows': rows})
    svg.text(58, 22, 'epoch 时间比 off / on', 17)
    svg.rect(574, 8, 22, 13, BLUE)
    svg.text(605, 21, '集中布局', 15)
    svg.hatched_bar(728, 8, 22, 13)
    svg.text(759, 21, '分散布局', 15)
    top, bottom = 70, 270
    def y(value):
        assert 0 <= value <= 6
        return bottom - value*(bottom-top)/6
    for panel, seed in enumerate((170021, 176023)):
        left, right = 64+panel*436, 424+panel*436
        svg.text((left+right)/2, 53, f'({"ab"[panel]}) seed = {seed}', 16, 'middle')
        for tick in (0, 2, 4, 6):
            yy = y(tick)
            svg.line(left, yy, right, yy, GRID, .8)
            svg.line(left-4, yy, left, yy, MUTED, 1)
            svg.text(left-11, yy+5, tick, 14, 'end', MUTED)
        svg.line(left, top, left, bottom, MUTED, 1.1)
        svg.line(left, bottom, right, bottom, MUTED, 1.1)
        svg.line(left, y(1), right, y(1), BLUE, 1, '5 4')
        svg.text(right-3, y(1)-5, 'off = on', 11, 'end', BLUE)
        for index, grain in enumerate((8, 256)):
            center = left+103+154*index
            for j, layout in enumerate(('concentrated', 'spread')):
                value = groups[f'balance-s{seed}-g{grain}-{layout}']['ratio']
                xx, width = center-43+48*j, 38
                if layout == 'concentrated':
                    svg.rect(xx, y(value), width, bottom-y(value), BLUE)
                else:
                    svg.hatched_bar(xx, y(value), width, bottom-y(value))
                svg.text(xx+width/2, y(value)-8, f'{value:.2f}', 16, 'middle', BLUE if j == 0 else RUST)
            svg.line(center, bottom, center, bottom+4, MUTED, 1)
            svg.text(center, 295, grain, 16, 'middle')
        svg.text((left+right)/2, 320, 'grain', 15, 'middle')
    svg.save(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Rebuild both performance SVGs from the report figure data.')
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding='utf-8'))
    args.outdir.mkdir(parents=True, exist_ok=True)
    rt = data['raytracing']
    draw_raytracing(rt['upstream_seconds'], rt['final_seconds'], args.outdir/'raytracing-comparison.svg')
    draw_worksteal(data['mechanism_controls'], args.outdir/'worksteal-matched.svg')
