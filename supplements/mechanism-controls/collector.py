#!/usr/bin/env python3
"""Fixed controls for idle behavior, task overhead and memory prereading."""
import argparse
import copy
import json
import pathlib
import random
import shutil
import statistics
import subprocess
import time
import traceback

import confirm_idle as guard
import lab

PROTOCOL = 'docs/52-机制补充实验协议.md'


def read(path):
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig'))


def design():
    cases, groups = [], []
    def add(group, variants):
        ids = []
        for label, c in variants:
            cid = group + '-' + label
            cases.append({'id': cid, 'group': group, 'label': label, 'config': c})
            ids.append(cid)
        groups.append(ids)

    for seed, n in ((170021, 65536), (176023, 98304)):
        for grain in (8, 256):
            for layout in ('concentrated', 'spread'):
                pair = []
                for mode in ('off', 'on'):
                    c = lab.config(mode, 16, grain, 256, n, seed, 'compute_skewed', layout=layout)
                    c['measurement']['reference_workers'] = 16
                    if mode == 'off':
                        c['policies']['steal_timing']['name'] = 'disabled_yield'
                    pair.append((mode, c))
                add(f'balance-s{seed}-g{grain}-{layout}', pair)

    overhead = []
    for grain in (8, 64, 4096):
        c = lab.config('off', 1, grain, 16, 262144, 182027)
        c['policies']['steal_timing']['name'] = 'disabled_yield'
        overhead.append(('g' + str(grain), c))
    overhead.append(('serial', lab.config('serial', 1, 4096, 16, 262144, 182027)))
    add('overhead', overhead)

    for size, per_element in (('512KiB', 8192), ('4.5MiB', 73728), ('288MiB', 4718592)):
        def memory(workers, home):
            c = lab.config('on', workers, 1, 1, 64, 188029, 'memory_reuse')
            c['workload'].update(bytes_per_element=per_element, passes=4)
            c['policies']['placement']['name'] = 'home'
            c['measurement'].update(home_worker=home, reference_workers=4)
            return c
        for target in (0, 1):
            pair = []
            for label, home in (('same', target), ('other', 1-target)):
                c = memory(2, home)
                c['measurement']['controlled_worker'] = target
                pair.append((label, c))
            add(f'preread-{size}-target{target}', pair)
        add(f'dynamic-{size}', [('on', memory(4, 0))])

    random.Random(2026102717).shuffle(groups)
    order = [(purpose, 0, cid) for purpose in ('diagnostic', 'warmup') for g in groups for cid in g]
    for rep in range(1, 6):
        shift = (rep-1) * len(groups) // 5
        rotated = groups[shift:] + groups[:shift]
        order.extend(('timing', rep, cid) for g in rotated for cid in (g if rep % 2 else g[::-1]))
    assert len(cases) == 35 and len(order) == 245
    return {'experiment': 'mechanism-controls', 'conditions': cases, 'groups': groups,
            'order': order, 'processes': 245, 'timing_samples': 175,
            'protocol': PROTOCOL, 'budget_seconds': 900, 'no_adaptation': True}


def prepare(root):
    origin = lab.ROOT
    root.mkdir(parents=True, exist_ok=False)
    for f in lab.source_files():
        dest = root / f.relative_to(origin)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        assert lab.digest(f) == lab.digest(dest)
    lab.ROOT = root
    build = root / 'build-mechanism'
    commands = [
        ['cmake', '-S', str(root), '-B', str(build), '-DCMAKE_BUILD_TYPE=Release',
         '-DWS_ENABLE_IPO=ON', '-DWS_COMPLETION_BATCH=32', '-DWS_STEAL_SCRATCH=ON', '-DWS_COMPUTE_LANES=8'],
        ['cmake', '--build', str(build), '-j2'],
        ['ctest', '--test-dir', str(build), '--output-on-failure'],
        ['python3', str(root/'tests/cli_checks.py'), str(build/'worksteal_mechanism'), str(build/'worksteal_extension')],
    ]
    logs = []
    for i, command in enumerate(commands):
        p = subprocess.run(command, capture_output=True, text=True, timeout=300)
        entry = {'command': command, 'exit_code': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
        logs.append(entry)
        lab.write(root/f'results/build-{i}.json', entry)
        if p.returncode:
            raise RuntimeError('build or correctness check failed: ' + str(i))
    exe = build/'worksteal_mechanism'
    lab.write(build/'validation.json', {'pass': True, 'records': logs, 'binary_sha256': lab.digest(exe)})
    lab.write(root/'results/build-evidence.json', {
        'binary_sha256': lab.digest(exe), 'source_id': lab.snapshot(),
        'cmake_cache_sha256': lab.digest(build/'CMakeCache.txt'), 'checks_pass': True,
        'runtime_unchanged': lab.digest(root/'src/runtime/worker_pool.cpp') == lab.digest(origin/'src/runtime/worker_pool.cpp')})
    shutil.copy2(build/'CMakeCache.txt', root/'results/CMakeCache.txt')
    plan = design()
    plan['source_id'] = lab.snapshot()
    plan['binary_sha256'] = lab.digest(exe)
    plan['protocol_sha256'] = lab.digest(root/PROTOCOL)
    lab.write(root/'results/frozen-plan.json', plan)
    print(json.dumps({'prepared': str(root), 'checks': 'pass', 'processes': len(plan['order'])}), flush=True)


def validate(config, r, purpose):
    assert r['correctness']['pass'] and r['metrics_mode'] == ('diagnostic' if purpose == 'diagnostic' else 'timing')
    e = r['epochs'][0]
    assert e['correctness']['compared_elements'] == config['workload']['elements']
    assert r['affinity']['actual_workers'] == [[cpu] for cpu in config['policies']['affinity']['cpus']]
    if purpose != 'diagnostic':
        assert e['worker_stats'] is None and e['execution'] is None
        return
    # Serial executes one contiguous range without the pool's per-task counters.
    # Full element verification still applies; exact_once is deliberately null.
    if config['executor'] == 'serial':
        assert e['correctness']['exact_once'] is None
    else:
        assert e['correctness']['exact_once'] is True
    assert sum(e['execution']['worker_cost_units']) == e['identity']['total_cost_units']
    stats = e['worker_stats'] or []
    if config['policies']['steal_timing']['name'] == 'disabled_yield':
        assert sum(s['steals'] for s in stats) == 0
    if 'controlled_worker' in config['measurement']:
        assert e['local_only']
        assert set(e['execution']['task_executor']) == {config['measurement']['controlled_worker']}
        assert sum(s['steals'] for s in stats) == 0
    elif config['workload']['name'] == 'memory_reuse':
        assert not e['local_only'] and sum(s['steals'] for s in stats) > 0
        assert e['execution']['element_home_mismatches'] > 0


def run(root):
    lab.ROOT = root
    plan = read(root/'results/frozen-plan.json')
    exe = root/'build-mechanism/worksteal_mechanism'
    assert lab.digest(exe) == plan['binary_sha256']
    assert lab.snapshot() == plan['source_id']
    assert not list((root/'runs').glob('*')), 'new directory required for each attempt'
    own = guard.ancestors()
    status, receipt = guard.availability(root, 300)
    if status != 'ready':
        raise RuntimeError('resource window busy; no experiment started')
    batch = lab.Batch('mechanism-controls', {**plan,
        'availability_receipt':receipt.relative_to(root).as_posix()}, exe, budget=900)
    cases = {c['id']: c for c in plan['conditions']}
    samples, identities = [], {}
    state, reason = 'completed', None
    try:
        for purpose, rep, cid in plan['order']:
            sample = guard.observe(own)
            samples.append(sample)
            if not sample['clear']:
                raise RuntimeError('competing Linux task detected')
            config = copy.deepcopy(cases[cid]['config'])
            if purpose == 'diagnostic':
                config['measurement']['mode'] = 'diagnostic'
            result = batch.run(config, cid, purpose, rep, timeout=60)
            validate(config, result, purpose)
            e = result['epochs'][0]
            # Every repeated process must reproduce all identity and output hashes.
            identity = (e['identity'], e['correctness']['output_hash_fnv1a64'], e['pretouch_hash_fnv1a64'])
            if cid in identities:
                assert identity == identities[cid]
            identities[cid] = identity
    except Exception as error:
        state, reason = 'failed', repr(error)
        lab.write(batch.path/'collector-error.json', {'error':repr(error), 'traceback':traceback.format_exc()})
    finally:
        lab.write(batch.path/'resource-samples.json', samples)
        batch.finish(state, reason)
    print(json.dumps({'batch': str(batch.path), 'status': state, 'reason': reason}), flush=True)
    if state != 'completed':
        raise RuntimeError(reason)


def audit(root):
    lab.ROOT = root
    plan = read(root/'results/frozen-plan.json')
    batches = list((root/'runs').glob('*'))
    assert len(batches) == 1
    batch = batches[0]
    assert read(batch/'completion.json')['status'] == 'completed'
    checked = 0
    for directory in (batch, *[x for x in batch.iterdir() if x.is_dir()]):
        for name, sha in read(directory/'checksums.json').items():
            assert lab.digest(directory/name) == sha
            checked += 1
    records = read(batch/'records.json')
    assert len(records) == len(plan['order'])
    assert [(r['purpose'], r['repeat'], r['condition']) for r in records] == [tuple(x) for x in plan['order']]
    cases = {c['id']: c for c in plan['conditions']}
    times, diagnostics, first = {}, {}, {}
    for r in records:
        assert r['status'] == 'completed' and r['binary_sha256'] == plan['binary_sha256']
        cid, purpose = r['condition'], r['purpose']
        rd = batch/r['run_id']
        c, result = read(rd/'config.json'), read(rd/'result.json')
        validate(c, result, purpose)
        e = result['epochs'][0]
        key = json.dumps(c['workload'], sort_keys=True)
        hashes = {k: e['identity'][k] for k in ('input_hash_fnv1a64','cost_hash_fnv1a64','data_hash_fnv1a64')}
        hashes['output'] = e['correctness']['output_hash_fnv1a64']
        hashes['pretouch'] = e['pretouch_hash_fnv1a64']
        assert first.setdefault(key, hashes) == hashes
        if purpose == 'timing':
            times[(cid,r['repeat'])] = {'epoch':e['epoch_seconds'], 'app':result['timing']['end_to_end_seconds'],
                'run_path': (rd/'result.json').relative_to(root).as_posix()}
        elif purpose == 'diagnostic':
            stats = e['worker_stats'] or []
            diagnostics[cid] = {'steals':sum(s['steals'] for s in stats),
                'moved':sum(s['moved'] for s in stats), 'execution':e['execution'],
                'identity':e['identity'], 'run_path':(rd/'result.json').relative_to(root).as_posix()}
    groups = []
    for ids in plan['groups']:
        rows = []
        for cid in ids:
            samples = [times[(cid, rep)] for rep in range(1,6)]
            rows.append({'condition':cid, 'label':cases[cid]['label'],
                'epoch_median':statistics.median(x['epoch'] for x in samples),
                'app_median':statistics.median(x['app'] for x in samples), 'samples':samples})
        group = {'group':cases[ids[0]]['group'], 'conditions':rows}
        if len(ids) == 2:
            a,b = rows
            group.update(ratio=a['epoch_median']/b['epoch_median'],
                second_faster_pairs=sum(y['epoch']<x['epoch'] for x,y in zip(a['samples'],b['samples'])))
        groups.append(group)
    summary = {'batch':batch.name, 'source_id':plan['source_id'], 'binary_sha256':plan['binary_sha256'],
               'processes':len(records), 'timing_samples':len(times), 'hash_checks':checked,
               'groups':groups, 'diagnostics':diagnostics, 'all_correct':True}
    assert len(times) == 175
    lab.write(root/'results/summary.json', summary)
    lines = ['# WorkSteal 机制补测', '', '35 个条件各测五次，预热和诊断另存。epoch 不含初始化、建队列和完整核验。', '',
             '|对照|配置|epoch 中位数（ms）|', '|---|---|---|']
    for g in groups:
        for r in g['conditions']:
            lines.append(f"|{g['group']}|{r['label']}|{r['epoch_median']*1000:.4f}|")
    lines += ['', '动态窃取诊断：', '']
    for cid,d in diagnostics.items():
        if cid.startswith('dynamic-'):
            lines.append(f"- {cid}: {d['steals']} 次成功窃取，{d['execution']['element_home_mismatches']}/64 个元素由非 home 执行。")
    lines += ['', '固定执行线程的预读差异仍不能等同于纯缓存损失；WSL1 下物理缓存映射和 PMU 未确认。', '',
              '逐次结果与 run_id 见 summary.json，每个原始目录保留命令、配置、标准输出及散列。']
    (root/'results/report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps({'audit':'pass','processes':len(records),'timing_samples':len(times),'hash_checks':checked}),flush=True)


def export(root, target):
    assert read(root/'results/summary.json')['all_correct']
    target.mkdir(parents=True, exist_ok=False)
    entries = {}
    for folder in ('runs','snapshots','results'):
        for f in sorted((root/folder).rglob('*')):
            if f.is_file():
                dest = target/f.relative_to(root)
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(f,dest)
                assert lab.digest(f) == lab.digest(dest)
                entries[f.relative_to(root).as_posix()] = lab.digest(dest)
    lab.write(target/'export-manifest.json', {'source_root':str(root),'files':entries,'time':lab.now()})
    print(json.dumps({'exported_files':len(entries),'sha256_verified':True}),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('prepare','run','audit','export'))
    p.add_argument('--root',required=True)
    p.add_argument('--target')
    a=p.parse_args();root=pathlib.Path(a.root).resolve()
    if a.action=='export': export(root,pathlib.Path(a.target).resolve())
    else: {'prepare':prepare,'run':run,'audit':audit}[a.action](root)


if __name__=='__main__':
    main()
