#!/usr/bin/env python3
"""V9 bounded screen/heldout tuning using the already validated V8 binary."""
import argparse
import collections
import copy
import hashlib
import json
import pathlib
import random
import shutil
import statistics
import threading
import uuid

import confirm_idle as guard
import lab

PROTOCOL = 'docs/29-第九轮内存参数优化协议.md'
GRID = tuple((p, g) for p in (4, 8, 16, 32) for g in (4, 8, 16))
BASE = 'p16-g4'
INPUTS = ((59009, 104), (65003, 152))
SHA = '3b98bf25474bfc27a1b3af44cce428cf1a9e16705d940d3df0c1cec32efef275'
MASK = (1 << 64)-1


def read(path):
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig'))


def config(root, p, g, seed, n, diagnostic=False):
    c = read(root/'configs/memory-interleaved/memory.json')
    c['workers'] = p
    c['policies']['partition']['grain'] = g
    c['policies']['affinity']['cpus'] = list(range(p))
    c['workload'].update(seed=seed, elements=n)
    c['layout_seed'] = seed
    if diagnostic:
        c['workload']['bytes_per_element'] = 128
        c['measurement']['mode'] = 'diagnostic'
    return c


def design(root):
    cases, order, branches = [], [], {}
    for p, g in GRID:
        cid = f'control-p{p}-g{g}'
        cases.append({'id': cid, 'config': config(root, p, g, 51001, 37, True)})
        order.append(['control', 0, cid])
    ids = []
    for p, g in GRID:
        cid = f'screen-p{p}-g{g}'
        cases.append({'id': cid, 'config': config(root, p, g, 53003, 112)})
        ids.append(cid)
    random.Random(2026102110).shuffle(ids)
    order.extend(['warmup', 0, cid] for cid in ids)
    for rep in range(1, 4):
        shift = (rep-1)*4
        order.extend(['timing', rep, cid] for cid in ids[shift:]+ids[:shift])
    for p, g in GRID:
        if f'p{p}-g{g}' == BASE:
            continue
        bcases, pairs = [], []
        for seed, n in INPUTS:
            pair = []
            for label, pp, gg in (('base', 16, 4), ('candidate', p, g)):
                cid = f'confirm-s{seed}-{label}'
                bcases.append({'id': cid, 'config': config(root, pp, gg, seed, n)})
                pair.append(cid)
            pairs.append(pair)
        border = [['warmup', 0, cid] for pair in pairs for cid in pair]
        for rep in range(1, 8):
            border.extend(['timing', rep, cid] for pair in pairs
                          for cid in (pair if rep % 2 else pair[::-1]))
        branches[f'p{p}-g{g}'] = {'conditions': bcases, 'order': border}
    return {'stage': 'V9-memory-tuning', 'conditions': cases, 'order': order,
            'confirmation_branches': branches}


def select(timing):
    table = []
    for p, g in GRID:
        samples = [timing[(f'screen-p{p}-g{g}', r)] for r in range(1, 4)]
        table.append({'id': f'p{p}-g{g}', 'workers': p, 'grain': g,
                      **{k: statistics.median(x[k] for x in samples) for k in ('epoch', 'app', 'process')}})
    base = next(x for x in table if x['id'] == BASE)
    for x in table:
        x['eligible'] = x['id'] != BASE and x['epoch'] <= .95*base['epoch'] and x['app'] <= 1.05*base['app']
    eligible = sorted((x for x in table if x['eligible']),
                      key=lambda x: (x['epoch'], x['app'], x['workers'], x['grain']))
    return {'selected': eligible[0]['id'] if eligible else None, 'table': table,
            'rule': 'eligible nonbaseline epoch<=95%, app<=105%; sort epoch,app,workers,grain'}


def prepare(root):
    origin = lab.ROOT
    root.mkdir(parents=True, exist_ok=False)
    for f in lab.source_files():
        dest = root/f.relative_to(origin)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
    lab.ROOT = root
    source = lab.snapshot()
    checkout = root.parent/'ws-20261021-memory-kernel-release'
    bd = checkout/'build-none'
    v = read(bd/'validation.json')
    assert v['pass'] and v['binary_sha256'] == lab.digest(bd/'worksteal') == SHA
    assert all(r['returncode'] == 0 and not r['stderr'] for r in v['records'])
    for folder, identifier in (('builds', SHA), ('source', v['source_id'])):
        shutil.copytree(checkout/'snapshots'/folder/identifier, root/'snapshots'/folder/identifier)
    measured = root/'snapshots/source'/v['source_id']
    for f in lab.source_files():
        rel = f.relative_to(root)
        if rel.parts[0] in ('include', 'src', 'tests') and f.suffix != '.md' or rel.name.startswith('CMake'):
            assert lab.digest(f) == lab.digest(measured/rel), str(rel)
    lab.write(root/'results/frozen-plan.json', {
        'created': lab.now(), 'collector_source_id': source, 'protocol': PROTOCOL,
        'protocol_sha256': lab.digest(root/PROTOCOL), 'study': design(root),
        'build': {'exe': str(bd/'worksteal'), 'binary_sha256': SHA, 'source_id': v['source_id']},
        'max_processes': 92, 'max_timing_samples': 64, 'screen_processes': 60})
    lab.write(root/'results/preparation.json', {'created': lab.now(),
              'plan_sha256': lab.digest(root/'results/frozen-plan.json')})
    print(json.dumps({'prepared': str(root), 'collector_source_id': source}), flush=True)


def load(root):
    path = root/'results/frozen-plan.json'
    assert lab.digest(path) == read(root/'results/preparation.json')['plan_sha256']
    p = read(path)
    source = root/'snapshots/source'/p['collector_source_id']
    assert lab.digest(source/PROTOCOL) == p['protocol_sha256']
    assert p['study'] == design(source)
    return p


def metric(result, row, path):
    return {'epoch': result['timing']['epoch_seconds'], 'app': result['timing']['end_to_end_seconds'],
            'process': row['elapsed_process_seconds'], 'phases': result['phase_seconds'], 'run_path': path}


def run(root, wait_seconds):
    p = load(root)
    assert not list((root/'runs').glob('*')), 'no retry after batch starts'
    assert len(list((root/'results').glob('availability-*.json'))) < 2
    b = p['build']
    assert lab.digest(pathlib.Path(b['exe'])) == b['binary_sha256']
    status, receipt = guard.availability(root, wait_seconds)
    if status != 'ready':
        return 3
    stage = p['study']
    batch = lab.Batch(stage['stage'], {**stage, 'build': b,
                      'availability_receipt': receipt.relative_to(root).as_posix(),
                      'frozen_plan_sha256': lab.digest(root/'results/frozen-plan.json')},
                      pathlib.Path(b['exe']), budget=600)
    batch.source, batch.binary = b['source_id'], b['binary_sha256']
    own, stop, samples, lock = guard.ancestors(), threading.Event(), [], threading.Lock()

    def check():
        with lock:
            sample = guard.observe(own)
            samples.append(sample)
        return sample['clear'] and all(s['clear'] for s in samples)

    def monitor():
        while not stop.wait(.5):
            if not check():
                break

    def execute(conditions, order):
        cases = {c['id']: c for c in conditions}
        for purpose, repeat, cid in order:
            if not check():
                raise RuntimeError('resource_contamination')
            result = batch.run(cases[cid]['config'], cid, purpose, repeat, timeout=90)
            if not check():
                raise RuntimeError('resource_contamination')
            if purpose == 'timing':
                row = batch.records[-1]
                timing[(cid, repeat)] = metric(result, row, (batch.path/row['run_id']).relative_to(root).as_posix())

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    state, reason, timing = 'completed', None, {}
    try:
        execute(stage['conditions'], stage['order'])
        selection = select(timing)
        lab.write(batch.path/'selection.json', selection)
        print(json.dumps({'selection': selection}), flush=True)
        if selection['selected']:
            branch = stage['confirmation_branches'][selection['selected']]
            execute(branch['conditions'], branch['order'])
    except Exception as e:
        reason = str(e)
        state = 'contaminated' if reason == 'resource_contamination' else 'failed'
    finally:
        stop.set()
        thread.join(timeout=15)
        if thread.is_alive():
            state, reason = 'failed', 'monitor_did_not_stop'
        lab.write(batch.path/'resource-observations.json', {
            'samples': samples, 'clean': all(s['clear'] for s in samples), 'interval_seconds': .5,
            'scope': 'WSL known-process observation; not physical exclusivity'})
        batch.finish(state, reason)
    print(json.dumps({'status': state, 'batch': str(batch.path), 'processes': len(batch.records)}), flush=True)
    return 0 if state == 'completed' else 4


def fnv(words):
    h = 14695981039346656037
    for x in words:
        for b in int(x).to_bytes(8, 'little'):
            h = ((h ^ b)*1099511628211) & MASK
    return f'{h:016x}'


def mix(x):
    x = ((x ^ (x >> 30))*0xbf58476d1ce4e5b9) & MASK
    x = ((x ^ (x >> 27))*0x94d049bb133111eb) & MASK
    return x ^ (x >> 31)


def identity(c):
    w, p = c['workload'], c['workers']
    n, g = w['elements'], c['policies']['partition']['grain']
    unit = w['bytes_per_element']//8*w['passes']
    tasks = [(i, b, min(n, b+g), i % p) for i, b in enumerate(range(0, n, g))]
    costs = [(e-b)*unit for _, b, e, _ in tasks]
    lists = [[i for i in range(len(tasks)) if i % p == worker] for worker in range(p)]
    queue = [word for worker, ids in enumerate(lists) for word in (worker, len(ids), *ids)]
    return {'task_hash_fnv1a64': fnv(word for t in tasks for word in t),
            'queue_hash_fnv1a64': fnv(queue), 'initial_cost_units': [sum(costs[i] for i in ids) for ids in lists],
            'total_cost_units': n*unit, 'max_task_cost_units': max(costs), 'task_count': len(tasks),
            'per_element_bytes': w['bytes_per_element'], 'total_data_bytes': n*w['bytes_per_element'],
            'input_hash_fnv1a64': fnv(mix(w['seed'] ^ ((i*0x9e3779b97f4a7c15) & MASK)) for i in range(n)),
            'cost_hash_fnv1a64': fnv(w['iterations'] for _ in range(n))}


def diagnostic_oracle(c, e):
    w = c['workload']
    n, words = w['elements'], w['bytes_per_element']//8
    data = [mix((w['seed']+i) & MASK) for i in range(n*words)]
    output = []
    for i in range(n):
        x = mix(w['seed'] ^ ((i*0x9e3779b97f4a7c15) & MASK))
        for r in range(w['passes']):
            for d in data[i*words:(i+1)*words]:
                x = ((x+d+r) & MASK) ^ (x >> 7)
        output.append(x)
    assert e['identity']['data_hash_fnv1a64'] == fnv(data)
    assert e['correctness']['output_hash_fnv1a64'] == fnv(output)
    assert e['pretouch_hash_fnv1a64'] == fnv(sum(data[i*words:(i+1)*words]) & MASK for i in range(n))
    assert e['correctness']['exact_once'] is True
    ex, p, g = e['execution'], c['workers'], c['policies']['partition']['grain']
    elements = [0]*p
    assert len(ex['task_executor']) == (n+g-1)//g
    for i, worker in enumerate(ex['task_executor']):
        assert 0 <= worker < p
        elements[worker] += min(g, n-i*g)
    assert ex['worker_elements'] == elements
    assert ex['worker_cost_units'] == [v*words*w['passes'] for v in elements]


def confirm(timing):
    heldout = []
    for seed, n in INPUTS:
        pairs = [{'repeat': r, **{label: timing[(f'confirm-s{seed}-{label}', r)]
                                  for label in ('base', 'candidate')}} for r in range(1, 8)]
        medians = {}
        for label in ('base', 'candidate'):
            medians[label] = {k: statistics.median(x[label][k] for x in pairs) for k in ('epoch', 'app', 'process')}
            medians[label]['phases'] = {k: statistics.median(x[label]['phases'][k] for x in pairs)
                                        for k in pairs[0][label]['phases']}
        wins = sum(x['candidate']['epoch'] < x['base']['epoch'] for x in pairs)
        m = medians
        heldout.append({'seed': seed, 'elements': n, 'pairs': pairs, 'medians': m, 'epoch_wins': wins,
                        'app_wins': sum(x['candidate']['app'] < x['base']['app'] for x in pairs),
                        'epoch_speedup': m['base']['epoch']/m['candidate']['epoch'],
                        'app_speedup': m['base']['app']/m['candidate']['app'],
                        'passed': wins >= 6 and m['candidate']['epoch'] <= .90*m['base']['epoch']
                                  and m['candidate']['app'] <= 1.05*m['base']['app']})
    return heldout


def audit(root):
    p = load(root)
    checks, sources = 0, 0
    for manifest in (root/'snapshots/source').glob('*/manifest.json'):
        m = read(manifest)
        assert hashlib.sha256(json.dumps(m['files'], sort_keys=True).encode()).hexdigest() == m['source_id'] == manifest.parent.name
        for rel, sha in m['files'].items():
            assert lab.digest(manifest.parent/rel) == sha
            sources += 1
    b = p['build']
    bd = root/'snapshots/builds'/b['binary_sha256']
    v = read(bd/'validation.json')
    assert v['pass'] and v['source_id'] == b['source_id'] and v['binary_sha256'] == b['binary_sha256'] == lab.digest(bd/'worksteal')
    assert all(r['returncode'] == 0 and not r['stderr'] for r in v['records'])
    assert 'warning:' not in (bd/'build-1.log').read_text().lower()
    for rel, sha in read(bd/'checksums.json').items():
        assert lab.digest(bd/rel) == sha
        checks += 1
    availability = []
    for path in sorted((root/'results').glob('availability-*.json')):
        a, consecutive = read(path), 0
        for s in a['observations']:
            assert s['windows_sampled'] and s['clear'] == (not s['blockers'])
            if s['clear']:
                assert max(s['windows_load_percent']) <= 15
            consecutive = consecutive+1 if s['clear'] else 0
        assert (consecutive == 3) == (a['status'] == 'ready')
        availability.append({'file': path.name, 'status': a['status'], 'observations': len(a['observations'])})
    assert len(availability) <= 2
    timing, batches, identities, selection, heldout = {}, [], collections.defaultdict(set), None, []
    for directory in sorted((root/'runs').glob('*')):
        assert not batches, 'only one batch'
        plan, done, rows = (read(directory/name) for name in ('plan.json', 'completion.json', 'records.json'))
        stage = p['study']
        assert all(plan[k] == val for k, val in stage.items())
        assert plan['source_id'] == p['collector_source_id']
        assert plan['build'] == b and done['processes'] == len(rows)
        assert plan['frozen_plan_sha256'] == lab.digest(root/'results/frozen-plan.json')
        order = list(stage['order'])
        cases = {c['id']: c for c in stage['conditions']}
        if (directory/'selection.json').exists():
            selection = read(directory/'selection.json')
            assert len(rows) >= 60
            if selection['selected']:
                branch = stage['confirmation_branches'][selection['selected']]
                order += branch['order']
                cases.update({c['id']: c for c in branch['conditions']})
        assert [[r['purpose'], r['repeat'], r['condition']] for r in rows] == order[:len(rows)]
        assert len(rows) <= len(order) <= 92
        assert {d.name for d in directory.iterdir() if d.is_dir()} == {r['run_id'] for r in rows}
        for manifest in [directory/'checksums.json']+list(directory.glob('*/checksums.json')):
            hashes = read(manifest)
            assert set(hashes) == {f.relative_to(manifest.parent).as_posix() for f in manifest.parent.rglob('*')
                                   if f.is_file() and f.name != 'checksums.json'}
            for rel, sha in hashes.items():
                assert lab.digest(manifest.parent/rel) == sha
                checks += 1
        for row in rows:
            c, d = cases[row['condition']]['config'], directory/row['run_id']
            assert read(d/'metadata.json') == row and read(d/'config.json') == c
            assert read(d/'command.txt')['argv'] == [b['exe'], '--config',
                    str(pathlib.PurePosixPath(read(d/'command.txt')['cwd'])/'runs'/directory.name/row['run_id']/'config.json'),
                    '--output', str(pathlib.PurePosixPath(read(d/'command.txt')['cwd'])/'runs'/directory.name/row['run_id']/'result.json')]
            assert row['source_id'] == b['source_id'] and row['binary_sha256'] == b['binary_sha256']
            assert row['collector_sha256'] == lab.digest(root/'snapshots/source'/p['collector_source_id']/'tools/lab.py')
            if row['status'] != 'completed':
                assert done['status'] == 'failed' and not row['included']
                continue
            assert (d/'stderr.log').stat().st_size == 0 and row['exit_code'] == 0
            r = read(d/'result.json')
            resolved = copy.deepcopy(c)
            resolved['steal_enabled'] = True
            assert r['resolved_config'] == resolved and r['correctness']['pass']
            assert row['timing'] == r['timing'] and len(r['epochs']) == 1
            assert row['included'] == (row['purpose'] == 'timing')
            n, workers = c['workload']['elements'], c['workers']
            e = r['epochs'][0]
            cc = e['correctness']
            assert cc['pass'] and cc['mismatches'] == 0 and cc['compared_elements'] == n
            assert cc['reference_tile_elements'] == 1 and cc['reference_workers_used'] == 4
            assert cc['exact_once'] == (True if row['purpose'] == 'control' else None)
            assert all(e['identity'][k] == val for k, val in identity(c).items())
            if row['purpose'] == 'control':
                diagnostic_oracle(c, e)
            assert r['affinity']['requested'] == list(range(workers))
            assert r['affinity']['actual_workers'] == [[cpu] for cpu in range(workers)]
            assert r['execution_kernel']['memory_lanes_requested'] == r['execution_kernel']['memory_lanes_used'] == 4
            init = r['initialization']
            assert init['requested_workers'] == init['workers_used'] == 1
            assert init['data_allocation_requested'] == init['data_allocation_used'] == 'zeroed'
            assert all(val >= 0 for val in r['phase_seconds'].values())
            assert sum(r['phase_seconds'].values()) <= r['timing']['end_to_end_seconds']+1e-9
            identities[(c['workload']['seed'], n)].add(tuple(e['identity'][k] for k in
                ('input_hash_fnv1a64', 'cost_hash_fnv1a64', 'data_hash_fnv1a64', 'total_cost_units'))+
                (cc['output_hash_fnv1a64'], e['pretouch_hash_fnv1a64']))
            if row['included']:
                timing[(row['condition'], row['repeat'])] = metric(r, row, d.relative_to(root).as_posix())
        if selection:
            assert selection == select(timing), 'selection recomputation'
        resource = read(directory/'resource-observations.json')
        assert resource['samples'] and resource['clean'] == all(s['clear'] for s in resource['samples'])
        a = read(root/plan['availability_receipt'])
        assert a['status'] == 'ready' and all(s['clear'] for s in a['observations'][-3:])
        clean = done['status'] == 'completed' and resource['clean']
        if clean:
            assert len(rows) == len(order) and selection is not None
            assert sum(r['included'] for r in rows) == (64 if selection['selected'] else 36)
            if selection['selected']:
                heldout = confirm(timing)
        batches.append({'batch': directory.name, 'status': done['status'], 'confirmable': clean,
                        'processes': len(rows), 'timing_samples': sum(r['included'] for r in rows),
                        'resource_samples': len(resource['samples'])})
    assert all(len(v) == 1 for v in identities.values()), 'input/output/pretouch mismatch'
    result = {'created': lab.now(), 'audit_pass': True, 'source_hash_checks': sources, 'hash_checks': checks,
              'availability': availability, 'batches': batches, 'selection': selection, 'heldout': heldout,
              'screen_samples': [{'condition': cid, 'repeat': rep, **value} for (cid, rep), value in timing.items()
                                 if cid.startswith('screen-')],
              'accepted': len(heldout) == 2 and all(h['passed'] for h in heldout),
              'scope': 'joint worker/grain tuning; epoch primary with app guard; not pure stealing or cache cause'}
    output = root/'results'/('audit-'+uuid.uuid4().hex+'.json')
    lab.write(output, result)
    print(json.dumps({'audit': str(output), 'accepted': result['accepted'], 'batches': batches}), flush=True)
    return result


def report(root):
    receipt = read(sorted((root/'results').glob('export-*.json'))[-1])
    for rel, sha in receipt['files'].items():
        assert lab.digest(root/rel) == sha
    result = audit(root)
    project = pathlib.Path(__file__).resolve().parents[1]
    data = root.relative_to(project).as_posix()
    lines = ['# 第九轮内存线程数与任务粒度报告', '', f"通过采用门槛：{result['accepted']}。复用V8 Release，无C++或构建改动。",
             '12诊断control验证尾部/完整参考/独立Python oracle；筛选和新输入确认分开。', '',
             '|批次|状态|进程|计时|资源观察|', '|---|---|---:|---:|---:|']
    for b in result['batches']:
        lines.append(f"|{b['batch']}|{b['status']}|{b['processes']}|{b['timing_samples']}|{b['resource_samples']}|")
    if result['selection']:
        s = result['selection']
        lines += ['', f"筛选唯一入选：{s['selected']}。非对照epoch≤95%、app≤105%先过滤，再按epoch/app/p/g排序。", '',
                  '|配置|epoch中位(ms)|app中位(ms)|process中位(ms)|合格|原件|', '|---|---:|---:|---:|---:|---|']
        for x in s['table']:
            links = ' / '.join(f"[r{sample['repeat']}](../../{data}/{sample['run_path']}/result.json)"
                               for sample in result['screen_samples'] if sample['condition'] == 'screen-'+x['id'])
            lines.append(f"|{x['id']}|{x['epoch']*1000:.3f}|{x['app']*1000:.3f}|{x['process']*1000:.3f}|{x['eligible']}|{links}|")
    lines += ['', '|seed/N|base epoch(ms)|candidate epoch(ms)|epoch加速|epoch胜对|app比(候选/对照)|通过|',
              '|---|---:|---:|---:|---:|---:|---|']
    for h in result['heldout']:
        m = h['medians']
        lines.append(f"|{h['seed']}/{h['elements']}|{m['base']['epoch']*1000:.3f}|{m['candidate']['epoch']*1000:.3f}|{h['epoch_speedup']:.3f}×|{h['epoch_wins']}/7|{1/h['app_speedup']:.3f}|{h['passed']}|")
    for h in result['heldout']:
        m = h['medians']
        lines += ['', f"## seed{h['seed']}所有配对", '',
                  '|对|base epoch(ms)|candidate epoch(ms)|base app(ms)|candidate app(ms)|原件|', '|---:|---:|---:|---:|---:|---|']
        for pair in h['pairs']:
            links = ' / '.join(f"[{label}](../../{data}/{pair[label]['run_path']}/result.json)" for label in ('base', 'candidate'))
            lines.append(f"|{pair['repeat']}|{pair['base']['epoch']*1000:.3f}|{pair['candidate']['epoch']*1000:.3f}|{pair['base']['app']*1000:.3f}|{pair['candidate']['app']*1000:.3f}|{links}|")
        lines += ['', '|区间中位数(ms)|base|candidate|', '|---|---:|---:|']
        for k in ('epoch', 'app', 'process'):
            lines.append(f"|{k}|{m['base'][k]*1000:.3f}|{m['candidate'][k]*1000:.3f}|")
        for k in m['base']['phases']:
            lines.append(f"|{k}|{m['base']['phases'][k]*1000:.3f}|{m['candidate']['phases'][k]*1000:.3f}|")
    lines += ['', f"Windows逐文件核对{len(receipt['files'])}个导出文件；独立复核{result['source_hash_checks']}个源码项、{result['hash_checks']}个构建/批次/运行散列项。",
              'task/queue/初始工作量由Python独立重建；跨组合输入/data/output/pretouch一致，完整核验N个元素；所有慢成功样本保留。',
              '确认门槛：每输入epoch至少6/7胜、epoch中位数≤90%、app中位数≤105%。不是显著性检验。未通过不重选，不追加样本。',
              '这是线程数/粒度的联合参数收益，home/队列/预读并发也改变；不声称纯窃取收益、物理独占、NUMA或cache因果，不乘历史倍数，阶段中位数不可相加。',
              '默认及历史推荐保留；仅双输入通过才新增configs/memory-tuned。最终PDF、容器实建及连续Session仍为独立待办。', '',
              f'冻结协议：[29](../../{PROTOCOL})；原件：`{data}/runs`。', '']
    output = project/'report/memory-tuning'/('第九轮内存参数优化报告-'+uuid.uuid4().hex[:8]+'.md')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(json.dumps({'report': str(output), 'export_checks': len(receipt['files'])}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=('prepare', 'run', 'audit', 'export', 'report'))
    ap.add_argument('--root', required=True)
    ap.add_argument('--wait-seconds', type=int, default=0)
    ap.add_argument('--target')
    a = ap.parse_args()
    if not 0 <= a.wait_seconds <= 600:
        ap.error('wait-seconds must be in [0,600]')
    root = pathlib.Path(a.root).resolve()
    if a.action == 'prepare':
        prepare(root)
        return 0
    lab.ROOT = root
    if a.action == 'run':
        return run(root, a.wait_seconds)
    if a.action == 'audit':
        audit(root)
    if a.action == 'export':
        assert a.target
        lab.export(argparse.Namespace(target=a.target))
    if a.action == 'report':
        report(root)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
