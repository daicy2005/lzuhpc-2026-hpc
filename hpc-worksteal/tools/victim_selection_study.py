#!/usr/bin/env python3
"""V16: original p32 recommendation, one victim change, immutable paired evidence."""
import argparse
import copy
import hashlib
import json
import pathlib
import random
import shutil
import statistics
import subprocess
import threading
import uuid

import confirm_idle as guard
import lab
import stealing_boundary_study as model

PROTOCOL = 'docs/45-第十六轮Victim选择协议.md'
EXE = '/root/lzuhpc-experiments/ws-20261016-verify-full_lanes8/build-none/worksteal'
SHA = 'c52674ba1244813d7d71808298b552042487a8bbeb41b8349a3eb4915027da8c'
SOURCE = 'e85c97b09468b4a3c6a6286bdceac7ffa408d2983cc2a957765e6b3bd9580c86'
INPUTS = ((140009, 229376), (146021, 360448))
VICTIMS = ('round_robin', 'seeded_random')
LAYOUTS = ('concentrated', 'spread', 'shuffled')
read = guard.read
MASK = (1 << 64) - 1


def shuffled_ids(n, seed):
    """libstdc++13 shuffle for mt19937_64, n^2 <= UINT64_MAX; tested against C++."""
    assert 0 <= n <= 1 << 32 and 0 <= seed <= MASK
    state = [seed]
    for i in range(1, 312):
        x = state[-1]
        state.append((6364136223846793005 * (x ^ (x >> 62)) + i) & MASK)
    index = 312

    def next64():
        nonlocal index
        if index == 312:
            for i in range(312):
                x = (state[i] & 0xffffffff80000000) | (state[(i+1) % 312] & 0x7fffffff)
                state[i] = state[(i+156) % 312] ^ (x >> 1) ^ (0xb5026f5aa96619e9 if x & 1 else 0)
            index = 0
        x = state[index]
        index += 1
        x ^= (x >> 29) & 0x5555555555555555
        x ^= (x << 17) & 0x71d67fffeda60000
        x ^= (x << 37) & 0xfff7eee000000000
        return (x ^ (x >> 43)) & MASK

    def uniform(bound):
        threshold = (1 << 64) % bound
        while True:
            product = next64() * bound
            if (product & MASK) >= threshold:
                return product >> 64

    ids = list(range(n))
    if n < 2:
        return ids
    i = 1
    if n % 2 == 0:
        j = uniform(2)
        ids[i], ids[j] = ids[j], ids[i]
        i += 1
    while i != n:
        bound = i + 1
        x = uniform(bound * (bound + 1))
        a, b = divmod(x, bound + 1)
        ids[i], ids[a] = ids[a], ids[i]
        ids[i+1], ids[b] = ids[b], ids[i+1]
        i += 2
    return ids


def item(stage, seed, n, k, layout, victim):
    c = lab.config('on', 32, 256, k, n, seed, 'compute_skewed', layout=layout)
    c['measurement']['reference_workers'] = 32
    c['policies']['victim'] = {'name': victim}
    if victim == 'seeded_random':
        c['policies']['victim']['seed'] = 17
    if stage == 'control':
        c['measurement']['mode'] = 'diagnostic'
    return {'id': f'{stage}-s{seed}-{layout}-{victim}', 'stage': stage, 'config': c}


def design():
    controls = [item('control', 138007, 1031, 7, layout, victim)
                for layout in LAYOUTS for victim in VICTIMS]
    cases, pairs = [], []
    for seed, n in INPUTS:
        for layout in LAYOUTS:
            pair = [item('confirm', seed, n, 1024, layout, v) for v in VICTIMS]
            cases.extend(pair)
            pairs.append([c['id'] for c in pair])
    random.Random(2026102516).shuffle(pairs)
    order = [('control', 0, c['id']) for c in controls]
    order += [(purpose, 0, cid) for purpose in ('diagnostic', 'warmup')
              for pair in pairs for cid in pair]
    for rep in range(1, 8):
        shift = rep - 1
        # Modulo preserves a rotation when rep-1 equals the number of pairs.
        shift %= len(pairs)
        order += [('timing', rep, cid) for pair in pairs[shift:] + pairs[:shift]
                  for cid in (pair if rep % 2 else pair[::-1])]
    return {'stage': 'V16-victim-selection', 'conditions': controls + cases,
            'pairs': pairs, 'order': order, 'processes': 114, 'timing_samples': 84,
            'diagnostic_samples': 18, 'no_adaptation': True}


def confirmation(timing, plan):
    cases = {c['id']: c for c in plan['conditions']}
    groups = []
    for base, candidate in plan['pairs']:
        c = cases[base]['config']
        pairs = [{'repeat': r, 'base': timing[(base, r)], 'candidate': timing[(candidate, r)]}
                 for r in range(1, 8)]
        medians = {mode: {metric: statistics.median(p[mode][metric] for p in pairs)
                         for metric in ('epoch', 'app', 'process')}
                   for mode in ('base', 'candidate')}
        a, b = medians['base'], medians['candidate']
        wins = sum(p['candidate']['epoch'] < p['base']['epoch'] for p in pairs)
        target = c['layout'] == 'concentrated'
        passed = b['app'] <= 1.05 * a['app'] and (
            wins >= 6 and b['epoch'] <= .95 * a['epoch'] if target
            else b['epoch'] <= 1.10 * a['epoch'])
        groups.append({'seed': c['workload']['seed'], 'elements': c['workload']['elements'],
                       'layout': c['layout'], 'target': target, 'epoch_wins': wins,
                       'medians': medians, 'epoch_speedup': a['epoch']/b['epoch'],
                       'app_speedup': a['app']/b['app'], 'pass': passed, 'pairs': pairs})
    return {'accepted': all(g['pass'] for g in groups), 'groups': groups}


def selfcheck():
    p = design()
    assert len(p['conditions']) == 18 and len(p['order']) == p['processes'] == 114
    assert len({tuple(x) for x in p['order']}) == 114
    assert sum(x[0] == 'timing' for x in p['order']) == 84
    cases = {c['id']: c for c in p['conditions']}
    for base, candidate in p['pairs']:
        a, b = (copy.deepcopy(cases[c]['config']) for c in (base, candidate))
        assert a['policies'].pop('victim') == {'name': 'round_robin'}
        assert b['policies'].pop('victim') == {'name': 'seeded_random', 'seed': 17}
        assert a == b
    good = {(cid, r): {'epoch': 1. if cid.endswith('round_robin') else .9,
                       'app': 1., 'process': 1., 'run_path': 'synthetic'}
            for purpose, r, cid in p['order'] if purpose == 'timing'}
    assert confirmation(good, p)['accepted']
    target = next(pair for pair in p['pairs'] if '-concentrated-' in pair[0])
    bad = copy.deepcopy(good)
    for rep in (1, 2):
        bad[(target[1], rep)]['epoch'] = 1.01
    assert not confirmation(bad, p)['accepted']
    bad = copy.deepcopy(good)
    for rep in range(1, 8):
        bad[(target[1], rep)]['epoch'] = .96
    assert not confirmation(bad, p)['accepted']
    for layout, metric, value in (('spread', 'epoch', 1.11), ('shuffled', 'epoch', 1.11),
                                  ('concentrated', 'app', 1.06)):
        bad = copy.deepcopy(good)
        pair = next(x for x in p['pairs'] if f'-{layout}-' in x[0])
        for rep in range(1, 8):
            bad[(pair[1], rep)][metric] = value
        assert not confirmation(bad, p)['accepted']
    # A single slow success is retained; it does not replace the median.
    slow = copy.deepcopy(good)
    slow[(target[1], 1)]['app'] = 100.
    assert confirmation(slow, p)['accepted']
    print(json.dumps({'selfcheck': 'pass', 'processes': 114, 'timing_samples': 84}), flush=True)


def task_model(c):
    n, k, p = c['workload']['elements'], c['workload']['iterations'], c['workers']
    grain = c['policies']['partition']['grain']
    tasks = [(i, b, min(n, b+grain), i % p) for i, b in enumerate(range(0, n, grain))]
    costs = [(e-b+8*max(0, min(e, n//8)-b))*k for _, b, e, _ in tasks]
    ids = (shuffled_ids(len(tasks), c['layout_seed']) if c['layout'] == 'shuffled'
           else sorted(range(len(tasks)), key=lambda i: -costs[i]))
    capacity = (len(tasks)+p-1)//p if tasks else 1
    lists = [[] for _ in range(p)]
    for rank, tid in enumerate(ids):
        owner = min(p-1, rank//capacity) if c['layout'] == 'concentrated' else rank % p
        lists[owner].append(tid)
    return tasks, costs, lists


def identities(c, cache):
    w = c['workload']
    key = (w['seed'], w['elements'], w['iterations'])
    if key not in cache:
        cache[key] = {
            'input_hash_fnv1a64': model.numeric.fnv(model.numeric.mix(w['seed'] ^ ((i*0x9e3779b97f4a7c15)&MASK)) for i in range(w['elements'])),
            'cost_hash_fnv1a64': model.numeric.fnv(w['iterations']*(9 if i<w['elements']//8 else 1) for i in range(w['elements']))}
    tasks, costs, lists = task_model(c)
    return {**cache[key], 'task_hash_fnv1a64': model.numeric.fnv(x for t in tasks for x in t),
            'queue_hash_fnv1a64': model.numeric.fnv(x for worker, q in enumerate(lists) for x in (worker, len(q), *q)),
            'data_hash_fnv1a64': None, 'initial_cost_units': [sum(costs[i] for i in q) for q in lists],
            'total_cost_units': sum(costs), 'max_task_cost_units': max(costs), 'task_count': len(tasks),
            'per_element_bytes': 8, 'total_data_bytes': 0}


def check(c, result, small, cache, outputs):
    resolved = copy.deepcopy(c)
    resolved['steal_enabled'] = True
    assert result['resolved_config'] == resolved and result['correctness']['pass']
    assert result['status'] == 'completed' and len(result['epochs']) == 1
    e, w, p = result['epochs'][0], c['workload'], c['workers']
    key = (w['seed'], w['elements'], w['iterations'])
    ikey = ('identity', *key, p, c['policies']['partition']['grain'], c['layout'], c['layout_seed'])
    if ikey not in cache:
        cache[ikey] = identities(c, cache)
    assert e['identity'] == cache[ikey]
    cc = e['correctness']
    assert cc['pass'] and cc['mismatches'] == 0 and cc['compared_elements'] == w['elements']
    assert cc['reference_tile_elements'] == 256
    assert cc['reference_workers_used'] == min(p, (w['elements']+255)//256)
    if key not in outputs:
        outputs[key] = model.small_output(c) if small else cc['output_hash_fnv1a64']
    assert cc['output_hash_fnv1a64'] == outputs[key]
    assert e['pretouch_hash_fnv1a64'] is None and not e['local_only']
    cpus = c['policies']['affinity']['cpus']
    assert result['affinity']['requested'] == cpus
    assert result['affinity']['actual_workers'] == [[cpu] for cpu in cpus]
    assert all(v >= 0 for v in result['phase_seconds'].values())
    assert sum(result['phase_seconds'].values()) <= result['timing']['end_to_end_seconds']+1e-9
    diagnostic = c['measurement']['mode'] == 'diagnostic'
    assert cc['exact_once'] == (True if diagnostic else None)
    if not diagnostic:
        assert e['execution'] is None and e['worker_stats'] is None
        return None
    tasks, costs, lists = task_model(c)
    initial_owner = {tid: worker for worker, q in enumerate(lists) for tid in q}
    owners, stats = e['execution']['task_executor'], e['worker_stats']
    assert len(owners) == len(tasks) and len(stats) == p
    work, elements, count = [0]*p, [0]*p, [0]*p
    mismatch = relocated = 0
    for (tid, begin, end, home), cost, owner in zip(tasks, costs, owners):
        assert type(owner) is int and 0 <= owner < p
        work[owner] += cost
        elements[owner] += end-begin
        count[owner] += 1
        mismatch += (end-begin)*(owner != home)
        relocated += owner != initial_owner[tid]
    assert e['execution'] == {'worker_cost_units': work, 'worker_elements': elements,
        'task_executor': owners, 'element_home_mismatches': mismatch, 'cost_unit': 'mix_iterations'}
    assert [s['tasks'] for s in stats] == count
    for s in stats:
        assert 0 <= s['steals'] == s['moved'] <= s['tasks']
    probes = {name: sum(s[name] for s in stats) for name in ('attempts', 'busy', 'empty', 'steals', 'moved')}
    assert probes['steals'] == probes['moved'] == relocated
    initial = cache[ikey]['initial_cost_units']
    return {'initial_cost_units': initial, 'actual_cost_units': work, 'task_count': len(tasks),
            'total_cost_units': sum(costs), 'initial_cost_balance': sum(initial)/(p*max(initial)),
            'actual_cost_balance': sum(work)/(p*max(work)), 'final_owner_changed_tasks': relocated,
            'probe_counts': probes, 'home_mismatched_elements': mismatch}


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
    recommended = read(root/'configs/verified/builds.json')['skewed']
    assert recommended['binary_sha256'] == v['binary_sha256'] == lab.digest(exe) == SHA
    assert recommended['source_id'] == v['source_id'] == SOURCE and v['pass']
    assert lab.digest(root/recommended['config']) == recommended['config_sha256']
    assert all(r['returncode'] == 0 and not r['stderr'] for r in v['records'])
    assert 'warning:' not in (exe.parent/'build-1.log').read_text().lower()
    for folder, identifier in (('source', SOURCE), ('builds', SHA)):
        shutil.copytree(exe.parent.parent/'snapshots'/folder/identifier, root/'snapshots'/folder/identifier)
    # Validate the independent Python model with the actual standard library.
    oracle = root/'results/shuffle-oracle'
    oracle.mkdir(parents=True)
    command = ['g++', '-std=c++20', '-O2', '-Wall', '-Wextra', '-Wpedantic', '-Wconversion',
               str(root/'tools/shuffle_oracle.cpp'), '-o', str(oracle/'probe')]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
    proof = {'command': command, 'returncode': compiled.returncode,
             'stdout': compiled.stdout, 'stderr': compiled.stderr}
    lab.write(oracle/'compile.json', proof)
    assert compiled.returncode == 0 and not compiled.stderr
    probe = subprocess.run([str(oracle/'probe')], capture_output=True, text=True, timeout=10)
    lab.write(oracle/'probe.json', {'returncode': probe.returncode, 'stdout': probe.stdout, 'stderr': probe.stderr})
    assert probe.returncode == 0 and not probe.stderr
    vectors = json.loads(probe.stdout)
    assert len(vectors) == 50
    for case in vectors:
        assert shuffled_ids(case['count'], case['seed']) == case['ids']
    lab.write(oracle/'verification.json', {'pass': True, 'cases': len(vectors),
        'source_sha256': lab.digest(root/'tools/shuffle_oracle.cpp'),
        'binary_sha256': lab.digest(oracle/'probe'),
        'headers': {str(path): lab.digest(path) for path in (
            pathlib.Path('/usr/include/c++/13/bits/stl_algo.h'),
            pathlib.Path('/usr/include/c++/13/bits/uniform_int_dist.h'))}})
    lab.seal(oracle)
    lab.write(root/'results/frozen-plan.json', {'created': lab.now(), 'collector_source_id': source,
        'protocol': PROTOCOL, 'protocol_sha256': lab.digest(root/PROTOCOL), 'study': design(),
        'oracle_checksums_sha256': lab.digest(oracle/'checksums.json'),
        'build': {'exe': EXE, 'binary_sha256': SHA, 'source_id': SOURCE}})
    lab.write(root/'results/preparation.json', {'created': lab.now(),
        'plan_sha256': lab.digest(root/'results/frozen-plan.json')})
    print(json.dumps({'prepared': str(root), 'source_id': source, 'shuffle_model_checks': 50}), flush=True)


def load(root):
    path = root/'results/frozen-plan.json'
    assert lab.digest(path) == read(root/'results/preparation.json')['plan_sha256']
    p = read(path)
    assert p['study'] == json.loads(json.dumps(design()))
    assert lab.digest(root/'snapshots/source'/p['collector_source_id']/p['protocol']) == p['protocol_sha256']
    assert lab.digest(root/'results/shuffle-oracle/checksums.json') == p['oracle_checksums_sha256']
    for rel, sha in read(root/'results/shuffle-oracle/checksums.json').items():
        assert lab.digest(root/'results/shuffle-oracle'/rel) == sha
    vectors = json.loads(read(root/'results/shuffle-oracle/probe.json')['stdout'])
    assert len(vectors) == 50
    for case in vectors:
        assert shuffled_ids(case['count'], case['seed']) == case['ids']
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
            result = batch.run(c, cid, purpose, rep, timeout=90)
            d = check(c, result, it['stage'] == 'control', cache, outputs)
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
    assert v['pass'] and v['source_id'] == SOURCE and v['binary_sha256'] == lab.digest(build/'worksteal') == SHA
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
        assert row['source_id'] == SOURCE and row['binary_sha256'] == SHA
        assert row['collector_sha256'] == lab.digest(root/'snapshots/source'/p['collector_source_id']/'tools/lab.py')
        cmd = read(rd/'command.txt')
        original = pathlib.PurePosixPath(cmd['cwd'])/'runs'/directory.name/row['run_id']
        assert cmd['argv'] == [EXE, '--config', str(original/'config.json'), '--output', str(original/'result.json')] and not cmd['explicit_environment']
        if row['status'] != 'completed':
            assert done['status'] != 'completed' and not row['included']
            continue
        assert row['exit_code'] == 0 and not (rd/'stderr.log').read_bytes()
        result = read(rd/'result.json')
        assert json.loads((rd/'stdout.log').read_bytes()) == result
        assert row['timing'] == result['timing'] and row['included'] == (row['purpose'] == 'timing')
        d = check(c, result, it['stage'] == 'control', cache, outputs)
        if d is not None:
            diags.append({'condition': row['condition'], 'purpose': row['purpose'], **d})
        if row['included']:
            timing[(row['condition'], row['repeat'])] = {'epoch': result['timing']['epoch_seconds'],
                'app': result['timing']['end_to_end_seconds'], 'process': row['elapsed_process_seconds'],
                'run_path': rd.relative_to(root).as_posix()}
    resource = read(directory/'resource-observations.json')
    assert resource['samples'] and resource['clean'] == all(s['clear'] for s in resource['samples'])
    av = read(root/plan['availability_receipt'])
    assert av['status'] == 'ready' and len(av['observations']) >= 3 and all(s['clear'] for s in av['observations'][-3:])
    complete = done['status'] == 'completed' and resource['clean']
    result = None
    if complete:
        assert len(rows) == p['study']['processes'] and len(timing) == p['study']['timing_samples']
        assert len(diags) == p['study']['diagnostic_samples']
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
    target = lab.ROOT/'report/victim-selection'/('第十六轮Victim选择报告-' + uuid.uuid4().hex[:8] + '.md')
    lines = ['# 第十六轮：优化后p32的victim选择', '',
        f"批次`{a['batch']}`，{a['processes']}进程/{a['timing_samples']}计时，complete={a['complete']}、accepted={a['accepted']}。", '',
        '原第四轮full_lanes8 Release/p32/g256/K1024/immediate/single/ref32固定，只比较round_robin与seeded_random(seed17)。诊断/预热排除于正式中位数，全部慢成功样本保留。', '',
        '|seed/N|布局|epoch RR→random ms|random胜对|app RR→random ms|通过|',
        '|---|---|---:|---:|---:|---|']
    groups = a['confirmation']['groups'] if a['confirmation'] else []
    for g in groups:
        b, c = g['medians']['base'], g['medians']['candidate']
        lines.append(f"|{g['seed']}/{g['elements']}|{g['layout']}|{b['epoch']*1000:.4f}→{c['epoch']*1000:.4f}|{g['epoch_wins']}/7|{b['app']*1000:.4f}→{c['app']*1000:.4f}|{g['pass']}|")
    lines += ['', '两个输入concentrated各至少6/7胜且epoch中位数≤95%；其余epoch≤110%；全部app≤105%。工程门槛不是显著性检验。结论限本轮p32偏斜输入，不推及其他workload。', '',
        f"[审计](../../{area}/{path.relative_to(root).as_posix()})；[冻结协议](../../{PROTOCOL})；[冻结计划](../../{area}/results/frozen-plan.json)；[全部run索引](../../{area}/runs/{a['batch']}/records.json)。", '',
        '## 独立诊断', '', '|condition|attempts|busy|empty|steals|实际单位均衡度|', '|---|---:|---:|---:|---:|---:|']
    for d in a['diagnostics']:
        if d['purpose'] == 'control':
            continue
        s = d['probe_counts']
        lines.append(f"|{d['condition']}|{s['attempts']}|{s['busy']}|{s['empty']}|{s['steals']}|{d['actual_cost_balance']:.4f}|")
    lines += ['', '计数来自额外诊断，不证明正式计时瓶颈。attempts不含第一处victim锁失败，busy/attempts不是总体失败率。单位均衡度不是CPU利用率；WSL掩码不证明物理驻留。', '', '## 全部配对和原件', '']
    for g in groups:
        lines += [f"### seed{g['seed']} {g['layout']}", '']
        for pair in g['pairs']:
            b, c = pair['base'], pair['candidate']
            lines.append(f"- 第{pair['repeat']}对：[RR](../../{area}/{b['run_path']}/result.json) {b['epoch']*1000:.4f}ms → [random](../../{area}/{c['run_path']}/result.json) {c['epoch']*1000:.4f}ms；process {b['process']*1000:.4f}→{c['process']*1000:.4f}ms。")
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
