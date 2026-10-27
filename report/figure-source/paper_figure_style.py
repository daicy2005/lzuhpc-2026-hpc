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

    def text(self, x, y, value, size=16, anchor='start', fill=INK, rotation=None):
        transform = f' transform="rotate({rotation} {x:.3f} {y:.3f})"' if rotation is not None else ''
        self.parts.append(f'<text x="{x:.3f}" y="{y:.3f}" font-size="{size}" text-anchor="{anchor}" fill="{fill}"{transform}>{html.escape(str(value))}</text>')

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
    paired_ratios = [a/b for a, b in zip(upstream, final)]
    metadata = {'chart': 'raytracing', 'panels': ['median runtime', 'paired runtime ratio'],
                'y_scales': ['linear', 'linear'], 'y_domains': [[0, 2200], [0, 25]],
                'upstream_seconds': upstream, 'final_seconds': final,
                'median_ratio': median_ratio, 'paired_ratios': paired_ratios}
    svg = SVG(900, 340, '光线追踪：渲染耗时与逐次耗时比', metadata)
    svg.text(450, 22, f'两组中位数耗时比 {median_ratio:.2f}×', 18, 'middle')
    top, bottom = 84, 276
    left, right = 76, 414
    svg.text((left+right)/2, 54, '(a) 渲染耗时', 17, 'middle')
    svg.text(18, 180, 'Render time / s', 14, 'middle', rotation=-90)
    for tick in (0, 500, 1000, 1500, 2000, 2200):
        yy = bottom-tick*(bottom-top)/2200
        if tick < 2200:
            svg.line(left, yy, right, yy, GRID, .8)
        svg.line(left-4, yy, left, yy, MUTED, 1)
        svg.text(left-10, yy+5, tick, 14, 'end', MUTED)
    svg.line(left, top, left, bottom, MUTED, 1.1)
    svg.line(left, bottom, right, bottom, MUTED, 1.1)
    for center, label, values, color in ((174, '原版 O2', upstream, BLUE), (327, '最终版', final, TEAL)):
        median = statistics.median(values)
        assert 0 <= median <= 2200
        yy = bottom-median*(bottom-top)/2200
        svg.rect(center-37, yy, 74, bottom-yy, color)
        svg.text(center, yy-8, f'{median:.3f}', 16, 'middle', color)
        svg.text(center, 302, label, 16, 'middle')
    svg.text((left+right)/2, 329, '三次运行的中位数', 13, 'middle', MUTED)
    left, right = 520, 878
    svg.text((left+right)/2, 54, '(b) 逐次耗时比', 17, 'middle')
    svg.text(462, 180, '原版 / 最终版', 14, 'middle', rotation=-90)
    for tick in (0, 5, 10, 15, 20, 25):
        yy = bottom-tick*(bottom-top)/25
        if tick < 25:
            svg.line(left, yy, right, yy, GRID, .8)
        svg.line(left-4, yy, left, yy, MUTED, 1)
        svg.text(left-10, yy+5, tick, 14, 'end', MUTED)
    svg.line(left, top, left, bottom, MUTED, 1.1)
    svg.line(left, bottom, right, bottom, MUTED, 1.1)
    for index, ratio in enumerate(paired_ratios):
        assert 0 <= ratio <= 25
        center = 587+111*index
        yy = bottom-ratio*(bottom-top)/25
        svg.rect(center-32, yy, 64, bottom-yy, TEAL)
        svg.text(center, yy-8, f'{ratio:.2f}×', 16, 'middle', TEAL)
        svg.text(center, 302, f'第{index+1}对', 16, 'middle')
    reference = bottom-(bottom-top)/25
    svg.line(left, reference, right, reference, MUTED, 1, '5 4')
    svg.text(right-3, reference-5, '1×', 12, 'end', MUTED)
    svg.text((left+right)/2, 329, '配对运行', 13, 'middle', MUTED)
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
