"""Render student-report charts from frozen measurements, without running experiments."""
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / '.cache/report-python').is_dir():
    sys.path.insert(0, str(ROOT / '.cache/report-python'))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

OUT = ROOT / 'report/student/figures'
OUT.mkdir(parents=True, exist_ok=True)


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8-sig'))


def sha(relative):
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


frozen = read('report/final/input-data.json')
first_path = 'results/study-summary.json'
boundary_path = 'stealing-boundary/results/audit-6508b2892aa3457087dda02bd6d45825.json'
for rel in (first_path, boundary_path):
    assert sha(rel) == frozen['source_sha256'][rel]
first, boundary = read(first_path), read(boundary_path)
# SVG exports the family declaration, while PNG rendering can use fname directly.
# Specify both so the editable SVG keeps the same Chinese font as the PNG.
font = FontProperties(family='Microsoft YaHei', fname='C:/Windows/Fonts/msyh.ttc', size=10)
small = FontProperties(family='Microsoft YaHei', fname='C:/Windows/Fonts/msyh.ttc', size=9)
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                     'axes.edgecolor': '#CBD5E1', 'axes.labelcolor': '#263D55',
                     'xtick.color': '#526477', 'ytick.color': '#526477',
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'figure.facecolor': 'white', 'axes.facecolor': 'white',
                     'savefig.facecolor': 'white', 'svg.fonttype': 'none'})
navy, teal, amber, blue = '#263D55', '#168C91', '#C48A42', '#748FA8'
records = {'scope': 'Existing frozen timing samples; stylistic redraw only.',
           'source_sha256': {p: sha(p) for p in (first_path, boundary_path)},
           'new_performance_samples': 0, 'charts': {}}


def finish(fig, name):
    for ext in ('png', 'svg'):
        fig.savefig(OUT / f'{name}.{ext}', dpi=240, bbox_inches='tight', pad_inches=.14)
    plt.close(fig)


fig, ax = plt.subplots(figsize=(7.6, 3.15), layout='constrained')
ax.grid(axis='y', color='#E8EDF2', linewidth=.8)
ax.set_axisbelow(True)
chart = []
grains = (1, 64, 4096)
for mode, label, color, marker in [('static', '静态队列', navy, 's'),
                                   ('central', '集中队列', amber, 'D'),
                                   ('off', '禁止窃取', blue, '^'),
                                   ('on', '允许窃取', teal, 'o')]:
    medians = []
    for grain in grains:
        group = next(g for g in first['groups'] if g['experiment'] == 'W00_W01'
                     and g['condition'] == f'{mode}-p4-g{grain}')
        paths = [p.replace('\\', '/') for p in group['run_paths']]
        seconds = [frozen['verified_raw_runs'][p]['epoch'] for p in paths]
        assert len(seconds) == 3 and statistics.median(seconds) == group['epoch_seconds']['median']
        medians.append(statistics.median(seconds) * 1000)
        chart.append({'mode': mode, 'grain': grain, 'run_paths': paths,
                      'epoch_seconds': seconds, 'median_ms': medians[-1]})
    ax.plot(grains, medians, color=color, marker=marker, lw=1.8, ms=5.5, label=label)
ax.set_xscale('log', base=2)
ax.set_xticks(grains, labels=['1', '64', '4096'])
ax.set_ylim(205, 213.3)
ax.set_yticks([206, 208, 210, 212])
ax.set_xlabel('每任务元素数 grain', fontproperties=font, labelpad=9)
ax.set_ylabel('epoch 中位数 / ms', fontproperties=font, labelpad=9)
legend = ax.legend(prop=small, loc='upper right', ncol=2, frameon=True,
                   facecolor='white', edgecolor='#E8EDF2', columnspacing=1.2)
legend.get_frame().set_alpha(.97)
records['charts']['w01-overhead-styled'] = chart
finish(fig, 'w01-overhead-styled')

fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.15), sharey=True, layout='constrained')
chart = []
for ax, seed in zip(axes, (100003, 106013)):
    ax.grid(axis='y', color='#E8EDF2', linewidth=.8)
    ax.set_axisbelow(True)
    for layout, label, color, marker in [('concentrated', '集中', teal, 'o'),
                                        ('spread', '分散', navy, 's')]:
        groups = sorted([g for g in boundary['groups'] if g['seed'] == seed
                         and g['layout'] == layout], key=lambda g: g['grain'])
        assert [g['grain'] for g in groups] == [8, 256, 16384]
        ratios = []
        for group in groups:
            modes = {}
            for mode in ('off', 'on'):
                paths = ['stealing-boundary/' + p[mode]['run_path'].replace('\\', '/')
                         for p in group['pairs']]
                seconds = [frozen['verified_raw_runs'][p]['epoch'] for p in paths]
                assert len(seconds) == 5
                assert statistics.median(seconds) == group['medians'][mode]['epoch']
                modes[mode] = {'run_paths': paths, 'epoch_seconds': seconds,
                               'median_seconds': statistics.median(seconds)}
            ratio = modes['off']['median_seconds'] / modes['on']['median_seconds']
            assert ratio == group['epoch_speedup']
            ratios.append(ratio)
            chart.append({'seed': seed, 'layout': layout, 'grain': group['grain'],
                          'modes': modes, 'off_over_on': ratio})
        ax.plot(range(3), ratios, color=color, marker=marker, lw=1.9, ms=5.5, label=label)
    ax.axhline(1, color=amber, ls='--', lw=1.1, zorder=1.8)
    ax.set_xticks(range(3), labels=['8', '256', '16384'])
    ax.set_xlabel('grain', labelpad=8)
    ax.set_title(f'seed {seed}', loc='left', color=navy, pad=12, fontweight='bold')
    ax.set_ylim(.65, 3.4)
    ax.legend(prop=small, frameon=False, loc='upper right')
axes[0].set_ylabel('epoch 时间比 off / on', fontproperties=font, labelpad=9)
records['charts']['v13-boundary-styled'] = chart
finish(fig, 'v13-boundary-styled')
(OUT / 'chart-data.json').write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'pass': True, 'new_performance_samples': 0,
                  'figures': ['w01-overhead-styled', 'v13-boundary-styled']}, ensure_ascii=False))
