#!/usr/bin/env python3
"""Frozen memory initialization screening and independent paired holdouts."""
import argparse
import collections
import copy
import json
import pathlib
import random
import shutil
import statistics
import threading
import uuid

import confirm_idle as guard
import lab

PROTOCOL = 'docs/23-第六轮初始化优化协议.md'
INPUTS = ((19001, 72), (23003, 112))
COUNTS = (1, 2, 4, 8)


def read(p):
    return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))


def config(root, kind, seed, n, count=None):
    c = read(root/f'configs/verified/{kind}.json')
    c['workload'].update(seed=seed, elements=n)
    c['layout_seed'] = seed
    if count is not None:
        c['measurement']['initialization_workers'] = count
    return c


def screen_plan(root):
    cases = []
    for kind in ('light', 'uniform', 'skewed', 'memory'):
        for build in ('old', 'release'):
            cases.append({'id': f'control-{kind}-{build}', 'kind': kind, 'build': build,
                          'config': config(root, kind, 13007, 64 if kind == 'memory' else 4096)})
    screen = [{'id': f'memory-init{p}', 'kind': 'memory', 'build': 'release',
               'config': config(root, 'memory', 13007, 64, p)} for p in COUNTS]
    order = [('control', 0, c['id']) for c in cases]
    cases += screen
    random.Random(2026102106).shuffle(screen)
    order += [('warmup', 0, c['id']) for c in screen]
    for rep in range(1, 4):
        rotation = (rep-1) % len(screen)
        order += [('timing', rep, c['id']) for c in screen[rotation:]+screen[:rotation]]
    return {'stage': 'V6A-initialization-screen', 'conditions': cases, 'order': order}


def heldout_plan(root, selected):
    cases, pairs = [], []
    for seed, n in INPUTS:
        pair = []
        for label, count in (('base', 1), ('candidate', selected)):
            c = {'id': f'memory-s{seed}-{label}', 'kind': 'memory', 'build': 'release',
                 'config': config(root, 'memory', seed, n, count)}
            cases.append(c)
            pair.append(c['id'])
        pairs.append(pair)
    random.Random(2026102107).shuffle(pairs)
    order = [('warmup', 0, cid) for pair in pairs for cid in pair]
    for rep in range(1, 8):
        order += [('timing', rep, cid) for pair in pairs for cid in (pair if rep % 2 else pair[::-1])]
    return {'stage': 'V6B-initialization-heldout', 'selected': selected, 'conditions': cases,
            'pairs': pairs, 'order': order}


def prepare(root):
    origin = lab.ROOT
    root.mkdir(parents=True, exist_ok=False)
    for f in lab.source_files():
        dest = root/f.relative_to(origin)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
    lab.ROOT = root
    source = lab.snapshot()
    builds = {}
    for tag in ('old', 'release', 'asan', 'tsan'):
        checkout = root.parent/('ws-20261016-verify-full_lanes8' if tag == 'old' else f'ws-20261021-init-{tag}')
        directory = checkout/('build-'+(tag if tag in ('asan', 'tsan') else 'none'))
        v = read(directory/'validation.json')
        assert v['pass'] and v['binary_sha256'] == lab.digest(directory/'worksteal')
        if tag != 'old':
            assert v['source_id'] == source, 'build and collector sources differ'
        else:
            assert v['binary_sha256'] == read(root/'configs/verified/builds.json')['memory']['binary_sha256']
        builds[tag] = {'exe': str(directory/'worksteal'), 'binary_sha256': v['binary_sha256'], 'source_id': v['source_id']}
        for folder, identifier in (('builds', v['binary_sha256']), ('source', v['source_id'])):
            dest = root/'snapshots'/folder/identifier
            if not dest.exists():
                shutil.copytree(checkout/'snapshots'/folder/identifier, dest)
    plan = {'created': lab.now(), 'collector_source_id': source, 'protocol': PROTOCOL,
            'protocol_sha256': lab.digest(root/PROTOCOL), 'builds': builds, 'screen': screen_plan(root),
            'heldout_inputs': INPUTS, 'gate': 'both inputs >=6/7 paired app wins and candidate app median <=0.95 base',
            'max_processes': 56, 'max_timing_samples': 40}
    lab.write(root/'results/frozen-plan.json', plan)
    lab.write(root/'results/preparation.json', {'created': lab.now(), 'plan_sha256': lab.digest(root/'results/frozen-plan.json')})
    print(json.dumps({'prepared': str(root), 'source_id': source}), flush=True)


def load_plan(root):
    path = root/'results/frozen-plan.json'
    assert lab.digest(path) == read(root/'results/preparation.json')['plan_sha256']
    p = read(path)
    snapshot = root/'snapshots/source'/p['collector_source_id']
    assert lab.digest(snapshot/PROTOCOL) == p['protocol_sha256']
    return p


def run(root, wait_seconds):
    plan = load_plan(root)
    previous = audit(root)
    if any(not b['confirmable'] for b in previous['batches']):
        raise RuntimeError('sealed incomplete/contaminated batch; use a fresh collector, never append')
    if not previous['batches']:
        stage = plan['screen']
    elif len(previous['batches']) == 1 and previous['selected'] != 1:
        stage = heldout_plan(root, previous['selected'])
        frozen = root/'results/heldout-plan.json'
        if frozen.exists():
            assert read(frozen) == json.loads(json.dumps(stage))
        else:
            lab.write(frozen, stage)
    else:
        raise RuntimeError('study already finished; no extra samples allowed')
    for b in plan['builds'].values():
        assert lab.digest(pathlib.Path(b['exe'])) == b['binary_sha256']
    status, receipt = guard.availability(root, wait_seconds)
    if status != 'ready':
        return 3
    batch = lab.Batch(stage['stage'], {**stage, 'builds': plan['builds'],
                      'availability_receipt': str(receipt.relative_to(root)),
                      'frozen_plan_sha256': lab.digest(root/'results/frozen-plan.json')},
                      pathlib.Path(plan['builds']['release']['exe']), budget=600)
    own, stop, samples, lock = guard.ancestors(), threading.Event(), [], threading.Lock()

    def check():
        with lock:
            sample = guard.observe(own)
            samples.append(sample)
        return sample['clear']

    def monitor():
        while not stop.wait(.5):
            if not check():
                break

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    state, reason = 'completed', None
    try:
        cases = {c['id']: c for c in stage['conditions']}
        for purpose, repeat, cid in stage['order']:
            if not check() or any(not s['clear'] for s in samples):
                state, reason = 'contaminated', 'external_work_or_observation_failure'
                break
            c = cases[cid]
            b = plan['builds'][c['build']]
            batch.exe, batch.source, batch.binary = pathlib.Path(b['exe']), b['source_id'], b['binary_sha256']
            batch.run(c['config'], cid, purpose, repeat, timeout=90)
            if not check() or any(not s['clear'] for s in samples):
                state, reason = 'contaminated', 'external_work_or_observation_failure'
                break
    except Exception as e:
        state, reason = 'failed', str(e)
    finally:
        stop.set()
        thread.join(timeout=15)
        if thread.is_alive():
            state, reason = 'failed', 'monitor_did_not_stop'
        lab.write(batch.path/'resource-observations.json', {'samples': samples, 'clean': all(s['clear'] for s in samples),
                  'interval_seconds': .5, 'scope': 'observed window; no exclusive reservation proof'})
        batch.finish(state, reason)
    print(json.dumps({'status': state, 'batch': str(batch.path), 'processes': len(batch.records)}), flush=True)
    return 0 if state == 'completed' else 4


def audit(root):
    p = load_plan(root)
    checked, source_checks = 0, 0
    for manifest in (root/'snapshots/source').glob('*/manifest.json'):
        m = read(manifest)
        import hashlib
        assert hashlib.sha256(json.dumps(m['files'], sort_keys=True).encode()).hexdigest() == m['source_id']
        assert manifest.parent.name == m['source_id']
        for rel, sha in m['files'].items():
            assert lab.digest(manifest.parent/rel) == sha
            source_checks += 1
    for b in p['builds'].values():
        directory = root/'snapshots/builds'/b['binary_sha256']
        v = read(directory/'validation.json')
        assert v['pass'] and v['source_id'] == b['source_id'] and v['binary_sha256'] == b['binary_sha256']
        assert all(r['returncode'] == 0 for r in v['records'])
        assert lab.digest(directory/'worksteal') == b['binary_sha256']
        for rel, sha in read(directory/'checksums.json').items():
            assert lab.digest(directory/rel) == sha
            checked += 1
    observations = []
    for path in (root/'results').glob('availability-*.json'):
        a = read(path)
        consecutive = 0
        for s in a['observations']:
            assert s['windows_sampled'] and s['clear'] == (not s['blockers'])
            if s['clear']:
                assert max(s['windows_load_percent']) <= 15
            consecutive = consecutive+1 if s['clear'] else 0
        assert (consecutive == 3) == (a['status'] == 'ready')
        observations.append({'file': path.name, 'status': a['status'], 'observations': len(a['observations'])})
    identities, timing, batches = collections.defaultdict(set), {}, []
    selected = None
    for directory in sorted((root/'runs').glob('*')):
        plan, done, rows = (read(directory/name) for name in ('plan.json', 'completion.json', 'records.json'))
        if not batches:
            expected = p['screen']
        else:
            assert len(batches) == 1 and selected not in (None, 1)
            # Use the frozen collector's configs even when auditing an export.
            snapshot = root/'snapshots/source'/p['collector_source_id']
            expected = heldout_plan(snapshot, selected)
            assert read(root/'results/heldout-plan.json') == json.loads(json.dumps(expected))
        for key, value in expected.items():
            assert plan[key] == json.loads(json.dumps(value))
        assert plan['builds'] == p['builds'] and done['processes'] == len(rows)
        assert plan['frozen_plan_sha256'] == lab.digest(root/'results/frozen-plan.json')
        assert [(r['purpose'], r['repeat'], r['condition']) for r in rows] == [tuple(x) for x in plan['order'][:len(rows)]]
        assert {d.name for d in directory.iterdir() if d.is_dir()} == {r['run_id'] for r in rows}
        for manifest in [directory/'checksums.json']+list(directory.glob('*/checksums.json')):
            hashes = read(manifest)
            assert set(hashes) == {f.relative_to(manifest.parent).as_posix() for f in manifest.parent.rglob('*')
                                   if f.is_file() and f.name != 'checksums.json'}
            for rel, sha in hashes.items():
                assert lab.digest(manifest.parent/rel) == sha
                checked += 1
        cases = {c['id']: c for c in plan['conditions']}
        for row in rows:
            c, d = cases[row['condition']], directory/row['run_id']
            b = p['builds'][c['build']]
            assert read(d/'metadata.json') == row and read(d/'config.json') == c['config']
            assert read(d/'command.txt')['argv'][0] == b['exe']
            assert row['source_id'] == b['source_id'] and row['binary_sha256'] == b['binary_sha256']
            if row['status'] != 'completed':
                assert done['status'] == 'failed' and not row['included']
                continue
            r = read(d/'result.json')
            resolved = copy.deepcopy(c['config'])
            resolved['steal_enabled'] = True
            assert r['resolved_config'] == resolved and r['correctness']['pass']
            assert row['timing'] == r['timing'] and len(r['epochs']) == 1
            assert row['included'] == (row['purpose'] == 'timing')
            e, n = r['epochs'][0], c['config']['workload']['elements']
            cc = e['correctness']
            tile = 1 if c['kind'] == 'memory' else 256
            assert cc['pass'] and cc['mismatches'] == 0 and cc['compared_elements'] == n
            assert cc['reference_tile_elements'] == tile
            assert cc['reference_workers_used'] == min(c['config']['measurement']['reference_workers'], (n+tile-1)//tile)
            if c['build'] != 'old':
                count = c['config']['measurement'].get('initialization_workers', 1)
                assert r['initialization']['requested_workers'] == count
                assert r['initialization']['workers_used'] == (min(n, count) if c['kind'] == 'memory' else 0)
            assert all(v >= 0 for v in r['phase_seconds'].values())
            assert sum(r['phase_seconds'].values()) <= r['timing']['end_to_end_seconds']+1e-9
            key = (c['kind'], c['config']['workload']['seed'], n)
            identities[key].add((json.dumps(e['identity'], sort_keys=True), cc['output_hash_fnv1a64'], e['pretouch_hash_fnv1a64']))
            if row['included']:
                timing[(row['condition'], row['repeat'])] = {
                    'app': r['timing']['end_to_end_seconds'], 'epoch': r['timing']['epoch_seconds'],
                    'process': row['elapsed_process_seconds'], 'phases': r['phase_seconds'],
                    'run_path': (d.relative_to(root)).as_posix()}
        resource = read(directory/'resource-observations.json')
        assert resource['samples'] and resource['clean'] == all(s['clear'] for s in resource['samples'])
        a = read(root/plan['availability_receipt'])
        assert a['status'] == 'ready'
        assert len(a['observations']) >= 3 and all(s['clear'] for s in a['observations'][-3:])
        clean = done['status'] == 'completed' and resource['clean']
        if clean:
            assert len(rows) == len(plan['order'])
            if not batches:
                selected = min(COUNTS, key=lambda count: (statistics.median(timing[(f'memory-init{count}', r)]['app'] for r in range(1, 4)), count))
        batches.append({'batch': directory.name, 'stage': plan['stage'], 'status': done['status'],
                        'processes': len(rows), 'timing_samples': sum(r['included'] for r in rows),
                        'confirmable': clean, 'resource_samples': len(resource['samples'])})
    assert all(len(v) == 1 for v in identities.values()), 'input/output/pretouch identity changed'
    heldout = []
    if len(batches) == 2 and all(b['confirmable'] for b in batches):
        for seed, n in INPUTS:
            pairs = [{'repeat': rep, **{label: timing[(f'memory-s{seed}-{label}', rep)] for label in ('base', 'candidate')}} for rep in range(1, 8)]
            medians = {}
            for label in ('base', 'candidate'):
                medians[label] = {key: statistics.median(pair[label][key] for pair in pairs) for key in ('app', 'epoch', 'process')}
                medians[label]['phases'] = {key: statistics.median(pair[label]['phases'][key] for pair in pairs) for key in pairs[0][label]['phases']}
            wins = sum(pair['candidate']['app'] < pair['base']['app'] for pair in pairs)
            heldout.append({'seed': seed, 'elements': n, 'wins': wins, 'medians': medians,
                            'app_speedup': medians['base']['app']/medians['candidate']['app'],
                            'passed': wins >= 6 and medians['candidate']['app'] <= .95*medians['base']['app'], 'pairs': pairs})
    screening = {count: statistics.median(timing[(f'memory-init{count}', r)]['app'] for r in range(1, 4)) for count in COUNTS} if selected else {}
    summary = {'created': lab.now(), 'audit_pass': True, 'hash_checks': checked, 'source_hash_checks': source_checks,
               'availability': observations, 'batches': batches, 'selected': selected, 'screen_app_medians': screening,
               'heldout': heldout, 'accepted': bool(heldout) and all(h['passed'] for h in heldout),
               'status': 'not_run' if not batches else ('completed' if selected == 1 or heldout else batches[-1]['status']),
               'scope': 'observed resource window; application initialization, not scheduler speedup'}
    out = root/'results'/('audit-'+uuid.uuid4().hex+'.json')
    lab.write(out, summary)
    print(json.dumps({'audit': str(out), 'batches': batches, 'selected': selected, 'accepted': summary['accepted']}, ensure_ascii=False), flush=True)
    return summary


def report(root):
    receipt = read(sorted((root/'results').glob('export-*.json'))[-1])
    for rel, sha in receipt['files'].items():
        assert lab.digest(root/rel) == sha
    result = audit(root)
    project = pathlib.Path(__file__).resolve().parents[1]
    data = root.relative_to(project).as_posix()
    lines = ['# 第六轮内存初始化优化报告', '', f"筛选候选：{result['selected']}线程；最终采用：{result['accepted']}。",
             '新同一二进制仅改变初始化填充线程数，核验4线程及执行配置不变。', '',
             '|阶段|批次|状态|进程|计时|资源观测|', '|---|---|---|---:|---:|---:|']
    for b in result['batches']:
        lines.append(f"|{b['stage']}|{b['batch']}|{b['status']}|{b['processes']}|{b['timing_samples']}|{b['resource_samples']}|")
    lines += ['', '筛选app中位数：'+ '；'.join(f'{k}线程={v*1000:.3f}ms' for k, v in result['screen_app_medians'].items())+'。', '',
              '|seed|块数|对照app(ms)|候选app(ms)|加速|胜对|过门槛|', '|---|---:|---:|---:|---:|---:|---|']
    for h in result['heldout']:
        m = h['medians']
        lines.append(f"|{h['seed']}|{h['elements']}|{m['base']['app']*1000:.3f}|{m['candidate']['app']*1000:.3f}|{h['app_speedup']:.3f}×|{h['wins']}/7|{h['passed']}|")
    for h in result['heldout']:
        lines += ['', f"## seed{h['seed']}各区间中位数（ms）", '', '|区间|init1|候选|', '|---|---:|---:|']
        for metric in ('app', 'epoch', 'process'):
            lines.append(f"|{metric}|{h['medians']['base'][metric]*1000:.3f}|{h['medians']['candidate'][metric]*1000:.3f}|")
        for phase in h['medians']['base']['phases']:
            lines.append(f"|{phase}|{h['medians']['base']['phases'][phase]*1000:.3f}|{h['medians']['candidate']['phases'][phase]*1000:.3f}|")
        lines += ['', '|重复|对照app(ms)|候选app(ms)|原始记录|', '|---:|---:|---:|---|']
        for pair in h['pairs']:
            links = ' / '.join(f"[{label}](../../{data}/{pair[label]['run_path']}/result.json)" for label in ('base', 'candidate'))
            lines.append(f"|{pair['repeat']}|{pair['base']['app']*1000:.3f}|{pair['candidate']['app']*1000:.3f}|{links}|")
    lines += ['', f"Windows核对{len(receipt['files'])}个导出文件；重审计源码{result['source_hash_checks']}项、构建/批次/运行散列{result['hash_checks']}项。",
              '所有成功慢样本保留，完整输入/输出/预读身份一致。仅通过已定义观测门禁，不证明物理独占或缓存因果。初始化仍包含在app中，应用收益不等于epoch/工作窃取收益。',
              '筛选未完成或任何批次干扰时不能认定优化通过；确认未过门槛保留init1，不追跑求通过。', '',
              f'协议：[23](../../{PROTOCOL})；原件：`{data}/runs`。', '']
    output = project/'report/initialization'/('第六轮内存初始化报告-'+uuid.uuid4().hex[:8]+'.md')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(json.dumps({'report': str(output), 'export_checks': len(receipt['files'])}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run', 'audit', 'export', 'report'))
    parser.add_argument('--root', required=True)
    parser.add_argument('--wait-seconds', type=int, default=0)
    parser.add_argument('--target')
    a = parser.parse_args()
    if not 0 <= a.wait_seconds <= 1800:
        parser.error('wait-seconds must be in [0,1800]')
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
