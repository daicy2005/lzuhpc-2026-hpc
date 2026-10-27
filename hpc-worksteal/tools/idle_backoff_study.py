#!/usr/bin/env python3
"""V15: fixed immediate/backoff comparison with immutable paired evidence."""
import argparse
import copy
import hashlib
import json
import pathlib
import random
import shutil
import statistics
import threading
import uuid

import batch_migration_study as shared
import confirm_idle as guard
import lab

PROTOCOL = 'docs/43-第十五轮采集修正与恢复协议.md'
EXE, SHA = shared.EXE, shared.SHA
INPUTS = ((128021, 73728), (134033, 106496))
POLICIES = ('immediate', 'bounded_backoff')
GRAINS = (8, 256)
LAYOUTS = ('concentrated', 'spread')
read = shared.read


def item(stage, seed, n, k, grain, layout, policy):
    c = lab.config('on', 16, grain, k, n, seed, 'compute_skewed', layout=layout)
    c['measurement']['reference_workers'] = 16
    c['policies']['steal_timing'] = {'name': policy}
    if stage == 'control':
        c['measurement']['mode'] = 'diagnostic'
    return {'id': f'{stage}-s{seed}-g{grain}-{layout}-{policy}',
            'stage': stage, 'grain': grain, 'policy': policy, 'config': c}


def design():
    controls = [item('control', 126007, 1031, 7, g, l, t)
                for g in GRAINS for l in LAYOUTS for t in POLICIES]
    cases, pairs = [], []
    for seed, n in INPUTS:
        for g in GRAINS:
            for layout in LAYOUTS:
                pair = [item('confirm', seed, n, 256, g, layout, t) for t in POLICIES]
                cases.extend(pair)
                pairs.append([c['id'] for c in pair])
    random.Random(2026102515).shuffle(pairs)
    order = [('control', 0, c['id']) for c in controls]
    order += [(purpose, 0, cid) for purpose in ('diagnostic', 'warmup')
              for pair in pairs for cid in pair]
    for rep in range(1, 8):
        shift = rep - 1
        order += [('timing', rep, cid) for pair in pairs[shift:] + pairs[:shift]
                  for cid in (pair if rep % 2 else pair[::-1])]
    return {'stage': 'V15-idle-backoff', 'conditions': controls + cases, 'pairs': pairs,
            'order': order, 'processes': 152, 'timing_samples': 112, 'no_adaptation': True}


def confirmation(timing, plan):
    cases = {c['id']: c for c in plan['conditions']}
    groups = []
    for base, candidate in plan['pairs']:
        c = cases[base]['config']
        pairs = [{'repeat': r, 'base': timing[(base, r)],
                  'candidate': timing[(candidate, r)]} for r in range(1, 8)]
        medians = {mode: {metric: statistics.median(p[mode][metric] for p in pairs)
                         for metric in ('epoch', 'app', 'process')}
                   for mode in ('base', 'candidate')}
        a, b = medians['base'], medians['candidate']
        wins = sum(p['candidate']['epoch'] < p['base']['epoch'] for p in pairs)
        target = c['layout'] == 'concentrated' and cases[base]['grain'] == 8
        passed = b['app'] <= 1.05 * a['app'] and (
            wins >= 6 and b['epoch'] <= .95 * a['epoch'] if target
            else b['epoch'] <= 1.10 * a['epoch'])
        groups.append({'seed': c['workload']['seed'], 'elements': c['workload']['elements'],
                       'grain': cases[base]['grain'], 'layout': c['layout'], 'target': target,
                       'epoch_wins': wins, 'medians': medians, 'epoch_speedup': a['epoch']/b['epoch'],
                       'app_speedup': a['app']/b['app'], 'pass': passed, 'pairs': pairs})
    return {'accepted': all(g['pass'] for g in groups), 'groups': groups}


def selfcheck():
    p = design()
    assert len(p['conditions']) == 24 and len(p['order']) == 152
    assert sum(x[0] == 'timing' for x in p['order']) == 112
    assert len({(x[0], x[1], x[2]) for x in p['order']}) == 152
    for base, cand in p['pairs']:
        cases = {c['id']: c for c in p['conditions']}
        a, b = (copy.deepcopy(cases[c]['config']) for c in (base, cand))
        assert a['policies'].pop('steal_timing') == {'name': 'immediate'}
        assert b['policies'].pop('steal_timing') == {'name': 'bounded_backoff'}
        assert a == b
    timing = {(cid, r): {'epoch': 1. if cid.endswith('-immediate') else .9,
                         'app': 1., 'process': 1., 'run_path': 'synthetic'}
              for purpose, r, cid in p['order'] if purpose == 'timing'}
    assert confirmation(timing, p)['accepted']
    target = next(pair for pair in p['pairs'] if '-g8-concentrated-' in pair[0])
    for rep in (1, 2):
        timing[(target[1], rep)]['epoch'] = 1.01
    assert not confirmation(timing, p)['accepted']  # only five wins despite good median
    for rep in (1, 2):
        timing[(target[1], rep)]['epoch'] = .9
    timing[(target[1], 4)]['app'] = 1.06
    assert confirmation(timing, p)['accepted']  # one slow success is retained, median unchanged
    for rep in range(1, 8):
        timing[(target[1], rep)]['app'] = 1.06
    assert not confirmation(timing, p)['accepted']
    for rep in range(1, 8):
        timing[(target[1], rep)]['app'] = 1.
    other = next(pair for pair in p['pairs'] if '-g256-spread-' in pair[0])
    for rep in range(1, 8):
        timing[(other[1], rep)]['epoch'] = 1.11
    assert not confirmation(timing, p)['accepted']
    print(json.dumps({'selfcheck': 'pass', 'processes': 152, 'timing_samples': 112}), flush=True)


def check(c, result, small, cache, outputs):
    # The reused V14 checker varied migration only. V15 also varies grain, so
    # task/queue identity caches must be separate even when outputs are equal.
    grain_cache = cache.setdefault(('grain', c['policies']['partition']['grain']), {})
    d = shared.check(c, result, 1, small, grain_cache, outputs)
    if d is not None:
        stats = result['epochs'][0]['worker_stats']
        d['probe_counts'] = {name: sum(s[name] for s in stats)
                             for name in ('attempts', 'busy', 'empty', 'steals', 'moved')}
    return d


def prepare(root):
    selfcheck()
    origin = lab.ROOT
    root.mkdir(parents=True, exist_ok=False)
    for src in lab.source_files():
        dest = root/src.relative_to(origin)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    lab.ROOT = root
    source = lab.snapshot()
    exe = pathlib.Path(EXE)
    v = read(exe.parent/'validation.json')
    assert v['pass'] and v['binary_sha256'] == lab.digest(exe) == SHA
    assert all(r['returncode'] == 0 and not r['stderr'] for r in v['records'])
    assert 'warning:' not in (exe.parent/'build-1.log').read_text().lower()
    old = read(exe.parent.parent/'snapshots/source'/v['source_id']/'manifest.json')
    for rel, sha in old['files'].items():
        if rel.startswith(('src/', 'include/')) or rel.startswith(('tests/', 'configs/')) and rel.endswith(('.cpp', '.hpp', '.py', '.json')) or rel in ('CMakeLists.txt', 'CMakePresets.json'):
            assert lab.digest(root/rel) == sha
    for folder, identifier in (('source', v['source_id']), ('builds', SHA)):
        shutil.copytree(exe.parent.parent/'snapshots'/folder/identifier, root/'snapshots'/folder/identifier)
    lab.write(root/'results/frozen-plan.json', {'created': lab.now(), 'collector_source_id': source,
        'protocol': PROTOCOL, 'protocol_sha256': lab.digest(root/PROTOCOL), 'study': design(),
        'build': {'exe': EXE, 'binary_sha256': SHA, 'source_id': v['source_id']}})
    lab.write(root/'results/preparation.json', {'created': lab.now(),
        'plan_sha256': lab.digest(root/'results/frozen-plan.json')})
    print(json.dumps({'prepared': str(root), 'source_id': source}), flush=True)


def load(root):
    path = root/'results/frozen-plan.json'
    assert lab.digest(path) == read(root/'results/preparation.json')['plan_sha256']
    p = read(path)
    assert p['study'] == json.loads(json.dumps(design()))
    assert lab.digest(root/'snapshots/source'/p['collector_source_id']/p['protocol']) == p['protocol_sha256']
    return p


def run(root, wait_seconds):
    p = load(root)
    assert not list((root/'runs').glob('*')), 'no retry of a started batch'
    assert len(list((root/'results').glob('availability-*.json'))) < 2
    assert lab.digest(pathlib.Path(EXE)) == SHA
    status, receipt = guard.availability(root, wait_seconds)
    if status != 'ready':
        return 3
    stage, b = p['study'], p['build']
    batch = lab.Batch(stage['stage'], {**stage, 'build': b,
        'availability_receipt': receipt.relative_to(root).as_posix(),
        'frozen_plan_sha256': lab.digest(root/'results/frozen-plan.json')}, pathlib.Path(EXE), budget=600)
    batch.source, batch.binary = b['source_id'], b['binary_sha256']
    own, stop, samples, lock = guard.ancestors(), threading.Event(), [], threading.Lock()
    def clean():
        with lock:
            samples.append(guard.observe(own))
        return all(s['clear'] for s in samples)
    def monitor():
        while not stop.wait(.5):
            if not clean():
                break
    cache, outputs, diags = {}, {}, []
    cases = {c['id']: c for c in stage['conditions']}
    worker = threading.Thread(target=monitor, daemon=True)
    worker.start()
    state, reason = 'completed', None
    try:
        for purpose, rep, cid in stage['order']:
            if not clean():
                raise RuntimeError('resource_contamination')
            it = cases[cid]
            c = copy.deepcopy(it['config'])
            if purpose == 'diagnostic':
                c['measurement']['mode'] = 'diagnostic'
            r = batch.run(c, cid, purpose, rep, timeout=90)
            d = check(c, r, it['stage'] == 'control', cache, outputs)
            if d is not None:
                diags.append({'condition': cid, 'purpose': purpose, **d})
            if not clean():
                raise RuntimeError('resource_contamination')
        lab.write(batch.path/'diagnostic-reconstruction.json', diags)
    except Exception as exc:
        reason = str(exc) or repr(exc)
        state = 'contaminated' if str(exc) == 'resource_contamination' else 'failed'
    finally:
        stop.set()
        worker.join(timeout=15)
        if worker.is_alive():
            state, reason = 'failed', 'monitor_did_not_stop'
        lab.write(batch.path/'resource-observations.json', {'samples': samples,
            'clean': all(s['clear'] for s in samples), 'interval_seconds': .5})
        batch.finish(state, reason)
    print(json.dumps({'batch': str(batch.path), 'status': state, 'processes': len(batch.records)}), flush=True)
    return 0 if state == 'completed' else 4


def audit(root):
    p = load(root)
    checked = 0
    for manifest in (root/'snapshots/source').glob('*/manifest.json'):
        m = read(manifest)
        assert hashlib.sha256(json.dumps(m['files'], sort_keys=True).encode()).hexdigest() == m['source_id'] == manifest.parent.name
        for rel, sha in m['files'].items():
            assert lab.digest(manifest.parent/rel) == sha
            checked += 1
    build = root/'snapshots/builds'/SHA
    v = read(build/'validation.json')
    assert v['pass'] and v['source_id'] == p['build']['source_id'] and v['binary_sha256'] == lab.digest(build/'worksteal') == SHA
    assert all(r['returncode'] == 0 and not r['stderr'] for r in v['records'])
    directories = list((root/'runs').iterdir())
    assert len(directories) == 1
    directory = directories[0]
    rows, done, plan = (read(directory/name) for name in ('records.json', 'completion.json', 'plan.json'))
    assert plan['source_id'] == p['collector_source_id'] and plan['build'] == p['build']
    assert {k: plan[k] for k in p['study']} == p['study']
    assert plan['frozen_plan_sha256'] == lab.digest(root/'results/frozen-plan.json')
    manifests = list((root/'snapshots/builds').glob('*/checksums.json')) + [directory/'checksums.json'] + list(directory.glob('*/checksums.json'))
    for manifest in manifests:
        hashes = read(manifest)
        assert set(hashes) == {f.relative_to(manifest.parent).as_posix() for f in manifest.parent.rglob('*') if f.is_file() and f.name != 'checksums.json'}
        for rel, sha in hashes.items():
            assert lab.digest(manifest.parent/rel) == sha
            checked += 1
    assert len(rows) == done['processes'] and len({r['run_id'] for r in rows}) == len(rows)
    assert {d.name for d in directory.iterdir() if d.is_dir()} == {r['run_id'] for r in rows}
    assert [(r['purpose'], r['repeat'], r['condition']) for r in rows] == [tuple(x) for x in p['study']['order'][:len(rows)]]
    cases = {c['id']: c for c in p['study']['conditions']}
    cache, outputs, timing, diags = {}, {}, {}, []
    for row in rows:
        rd = directory/row['run_id']
        it = cases[row['condition']]
        c = copy.deepcopy(it['config'])
        if row['purpose'] == 'diagnostic':
            c['measurement']['mode'] = 'diagnostic'
        assert read(rd/'metadata.json') == row and read(rd/'config.json') == c
        assert row['source_id'] == p['build']['source_id'] and row['binary_sha256'] == SHA
        assert row['collector_sha256'] == lab.digest(root/'snapshots/source'/p['collector_source_id']/'tools/lab.py')
        cmd = read(rd/'command.txt')
        original = pathlib.PurePosixPath(cmd['cwd'])/'runs'/directory.name/row['run_id']
        assert cmd['argv'] == [EXE, '--config', str(original/'config.json'), '--output', str(original/'result.json')] and not cmd['explicit_environment']
        if row['status'] != 'completed':
            assert done['status'] != 'completed' and not row['included']
            continue
        assert row['exit_code'] == 0 and not (rd/'stderr.log').read_bytes()
        r = read(rd/'result.json')
        assert json.loads((rd/'stdout.log').read_bytes()) == r
        assert row['timing'] == r['timing'] and row['included'] == (row['purpose'] == 'timing')
        d = check(c, r, it['stage'] == 'control', cache, outputs)
        if d is not None:
            diags.append({'condition': row['condition'], 'purpose': row['purpose'], **d})
        if row['included']:
            timing[(row['condition'], row['repeat'])] = {'epoch': r['timing']['epoch_seconds'],
                'app': r['timing']['end_to_end_seconds'], 'process': row['elapsed_process_seconds'],
                'run_path': rd.relative_to(root).as_posix()}
    resource = read(directory/'resource-observations.json')
    assert resource['samples'] and resource['clean'] == all(s['clear'] for s in resource['samples'])
    av = read(root/plan['availability_receipt'])
    assert av['status'] == 'ready' and len(av['observations']) >= 3 and all(s['clear'] for s in av['observations'][-3:])
    complete = done['status'] == 'completed' and resource['clean']
    result = None
    if complete:
        assert len(rows) == 152 and len(timing) == 112 and len(diags) == 24
        assert read(directory/'diagnostic-reconstruction.json') == diags
        result = confirmation(timing, p['study'])
    a = {'created': lab.now(), 'audit_pass': True, 'complete': complete,
         'accepted': result['accepted'] if result else False, 'confirmation': result,
         'batch': directory.name, 'processes': len(rows), 'timing_samples': len(timing),
         'diagnostic_samples': len(diags), 'resource_samples': len(resource['samples']),
         'hash_checks': checked, 'diagnostics': diags}
    path = root/'results'/('audit-' + uuid.uuid4().hex + '.json')
    lab.write(path, a)
    print(json.dumps({'audit': str(path), 'complete': complete, 'accepted': a['accepted'],
                      'processes': len(rows), 'hash_checks': checked}), flush=True)
    return a, path


def report(root):
    receipts = list((root/'results').glob('export-*.json'))
    assert len(receipts) == 1
    receipt = read(receipts[0])
    for rel, sha in receipt['files'].items():
        assert lab.digest(root/rel) == sha
    a, path = audit(root)
    area = root.relative_to(lab.ROOT).as_posix()
    protocol = load(root)['protocol']
    target = lab.ROOT/'report/idle-backoff'/('第十五轮空闲退避报告-' + uuid.uuid4().hex[:8] + '.md')
    lines = ['# 第十五轮：空闲退避', '',
        f"批次`{a['batch']}`，{a['processes']}进程/{a['timing_samples']}计时，complete={a['complete']}、accepted={a['accepted']}。", '',
        '原Release/16worker/K256/round_robin/single不变，只比较immediate与bounded_backoff；后者连续失败第32次起请求固定50微秒等待。全部慢成功样本保留。', '',
        '## 独立输入对照', '', '|seed/N|grain|布局|epoch base→candidate ms|胜对|app base→candidate ms|通过|',
        '|---|---:|---|---:|---:|---:|---|']
    groups = a['confirmation']['groups'] if a['confirmation'] else []
    for g in groups:
        b, c = g['medians']['base'], g['medians']['candidate']
        lines.append(f"|{g['seed']}/{g['elements']}|{g['grain']}|{g['layout']}|{b['epoch']*1000:.4f}→{c['epoch']*1000:.4f}|{g['epoch_wins']}/7|{b['app']*1000:.4f}→{c['app']*1000:.4f}|{g['pass']}|")
    lines += ['', '两个输入g8/concentrated各至少6/7胜且epoch中位数≤95%；其余epoch≤110%；全部app≤105%。工程门槛不是显著性检验。范围仅限本轮条件，不直接替换p32推荐。', '',
        f"[独立审计](../../{area}/{path.relative_to(root).as_posix()})；[冻结协议](../../{protocol})；[冻结计划](../../{area}/results/frozen-plan.json)；[全部run索引](../../{area}/runs/{a['batch']}/records.json)。", '',
        '## 独立诊断计数', '', '|condition|attempts|busy|empty|steals|', '|---|---:|---:|---:|---:|']
    for d in a['diagnostics']:
        if d['purpose'] == 'control':
            continue
        s = d['probe_counts']
        lines.append(f"|{d['condition']}|{s['attempts']}|{s['busy']}|{s['empty']}|{s['steals']}|")
    lines += ['', '计数来自额外诊断进程，不证明正式计时瓶颈；attempts不覆盖第一处锁失败，busy/attempts不是总体失败率。未测实际睡眠时长、上下文切换、功耗或物理核占用。', '', '## 全部配对与阶段原件', '']
    for g in groups:
        lines += [f"### seed{g['seed']} grain{g['grain']} {g['layout']}", '']
        for pair in g['pairs']:
            b, c = pair['base'], pair['candidate']
            lines.append(f"- 第{pair['repeat']}对：[immediate](../../{area}/{b['run_path']}/result.json) {b['epoch']*1000:.4f}ms → [backoff](../../{area}/{c['run_path']}/result.json) {c['epoch']*1000:.4f}ms；process {b['process']*1000:.4f}→{c['process']*1000:.4f}ms。")
        lines.append('')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(json.dumps({'report': str(target), 'exported_files_verified': len(receipt['files'])}, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('selfcheck', 'prepare', 'run', 'audit', 'export', 'report'))
    parser.add_argument('--root')
    parser.add_argument('--target')
    parser.add_argument('--wait-seconds', type=int, default=600)
    args = parser.parse_args()
    if args.action == 'selfcheck':
        selfcheck()
        return 0
    assert args.root
    root = pathlib.Path(args.root).resolve()
    if args.action == 'prepare':
        prepare(root)
    else:
        if args.action != 'report':
            lab.ROOT = root
        if args.action == 'run':
            return run(root, args.wait_seconds)
        if args.action == 'audit':
            audit(root)
        if args.action == 'export':
            lab.export(argparse.Namespace(target=args.target))
        if args.action == 'report':
            report(root)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
