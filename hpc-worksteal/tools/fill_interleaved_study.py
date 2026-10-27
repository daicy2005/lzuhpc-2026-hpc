#!/usr/bin/env python3
"""Frozen V11 independent data-fill lanes confirmation, audit and export."""
import argparse
import collections
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
import memory_tuning_study as oracle

PROTOCOL = 'docs/33-第十一轮数据生成交错协议.md'
INPUTS = ((80021, 96), (86011, 144))


def read(path):
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig'))


def config(root, kind, seed, n, mode=None):
    c = read(root/f'configs/verified/{kind}.json')
    c['workload'].update(seed=seed, elements=n)
    c['layout_seed'] = seed
    c['measurement'].update(initialization_workers=1, data_allocation='zeroed', memory_lanes=4, data_identity='separate')
    if mode is not None:
        c['measurement']['data_fill_lanes'] = mode
    return c


def design(root):
    cases, order, pairs = [], [], []
    for kind in ('light', 'uniform', 'skewed', 'memory'):
        for label, mode in (('old', None), ('fill1', 1), ('fill4', 4)):
            cid = f'control-{kind}-{label}'
            c = config(root, kind, 79001, 37 if kind == 'memory' else 4096, mode)
            c['measurement']['mode'] = 'diagnostic'
            if kind == 'memory':
                c['workload']['bytes_per_element'] = 136
            cases.append({'id': cid, 'kind': kind, 'build': 'old' if label == 'old' else 'release', 'config': c})
            order.append(('control', 0, cid))
    for seed, n in INPUTS:
        pair = []
        for label, mode in (('base', 1), ('candidate', 4)):
            cid = f'memory-s{seed}-{label}'
            cases.append({'id': cid, 'kind': 'memory', 'build': 'release',
                          'config': config(root, 'memory', seed, n, mode)})
            pair.append(cid)
        pairs.append(pair)
    order += [('warmup', 0, cid) for pair in pairs for cid in pair]
    for rep in range(1, 8):
        order += [('timing', rep, cid) for pair in pairs
                  for cid in (pair if rep % 2 else pair[::-1])]
    return {'stage': 'V11-fill-interleaved', 'conditions': cases, 'pairs': pairs, 'order': order}


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
        checkout = root.parent/('ws-20261021-blocked-identity-release' if tag == 'old'
                                else f'ws-20261022-fill-interleaved-{tag}')
        bd = checkout/('build-'+(tag if tag in ('asan', 'tsan') else 'none'))
        v = read(bd/'validation.json')
        assert v['pass'] and v['binary_sha256'] == lab.digest(bd/'worksteal')
        assert all(r['returncode'] == 0 and not r['stderr'] for r in v['records'])
        if tag != 'old':
            assert v['source_id'] == source, 'build and collector source differ'
        else:
            assert v['binary_sha256'] == 'ce017c475c947044b3e32070951f01cb24f43ba29a44f3b8dbfb4bb0ea90f3ed'
        assert 'warning:' not in (bd/'build-1.log').read_text().lower()
        builds[tag] = {'exe': str(bd/'worksteal'), 'binary_sha256': v['binary_sha256'],
                       'source_id': v['source_id']}
        for folder, identifier in (('builds', v['binary_sha256']), ('source', v['source_id'])):
            dest = root/'snapshots'/folder/identifier
            if not dest.exists():
                shutil.copytree(checkout/'snapshots'/folder/identifier, dest)
    disassembly = {}
    for tag in ('old', 'release'):
        b = builds[tag]
        command = ['objdump', '-d', '-C', '--no-show-raw-insn', b['exe']]
        process = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
        assert not process.stderr
        path = root/'results'/f'disassembly-{tag}.txt'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as f:
            f.write(process.stdout)
        disassembly[tag] = {'command': command, 'file': path.relative_to(root).as_posix(), 'sha256': lab.digest(path)}
    lab.write(root/'results/frozen-plan.json', {
        'created': lab.now(), 'collector_source_id': source, 'protocol': PROTOCOL,
        'protocol_sha256': lab.digest(root/PROTOCOL), 'builds': builds, 'study': design(root), 'disassembly': disassembly,
        'gate': 'both inputs >=6/7 paired app wins, candidate app median <=0.95 base and epoch median <=1.10 base',
        'max_processes': 44, 'timing_samples': 28})
    lab.write(root/'results/preparation.json', {
        'plan_sha256': lab.digest(root/'results/frozen-plan.json'), 'created': lab.now()})
    print(json.dumps({'prepared': str(root), 'source_id': source}), flush=True)


def load(root):
    path = root/'results/frozen-plan.json'
    assert lab.digest(path) == read(root/'results/preparation.json')['plan_sha256']
    p = read(path)
    source = root/'snapshots/source'/p['collector_source_id']
    assert lab.digest(source/PROTOCOL) == p['protocol_sha256']
    assert p['study'] == json.loads(json.dumps(design(source)))
    for item in p['disassembly'].values():
        assert lab.digest(root/item['file']) == item['sha256']
    return p


def run(root, wait_seconds):
    p = load(root)
    assert not list((root/'runs').glob('*')), 'never append/retry an already started batch'
    assert len(list((root/'results').glob('availability-*.json'))) < 2, 'availability retry budget'
    for b in p['builds'].values():
        assert lab.digest(pathlib.Path(b['exe'])) == b['binary_sha256']
    status, receipt = guard.availability(root, wait_seconds)
    if status != 'ready':
        return 3
    stage = p['study']
    batch = lab.Batch(stage['stage'], {**stage, 'builds': p['builds'],
                      'availability_receipt': receipt.relative_to(root).as_posix(),
                      'frozen_plan_sha256': lab.digest(root/'results/frozen-plan.json')},
                      pathlib.Path(p['builds']['release']['exe']), budget=600)
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
            b = p['builds'][c['build']]
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
        lab.write(batch.path/'resource-observations.json', {
            'samples': samples, 'clean': all(s['clear'] for s in samples),
            'interval_seconds': .5, 'scope': 'observed window; no physical exclusivity proof'})
        batch.finish(state, reason)
    print(json.dumps({'status': state, 'batch': str(batch.path), 'processes': len(batch.records)}), flush=True)
    return 0 if state == 'completed' else 4


def audit(root):
    p = load(root)
    checked, sources = 0, 0
    for manifest in (root/'snapshots/source').glob('*/manifest.json'):
        m = read(manifest)
        assert hashlib.sha256(json.dumps(m['files'], sort_keys=True).encode()).hexdigest() == m['source_id'] == manifest.parent.name
        for rel, sha in m['files'].items():
            assert lab.digest(manifest.parent/rel) == sha
            sources += 1
    for b in p['builds'].values():
        bd = root/'snapshots/builds'/b['binary_sha256']
        v = read(bd/'validation.json')
        assert v['pass'] and v['source_id'] == b['source_id'] and v['binary_sha256'] == b['binary_sha256']
        assert all(r['returncode'] == 0 and not r['stderr'] for r in v['records'])
        assert lab.digest(bd/'worksteal') == b['binary_sha256']
        for rel, sha in read(bd/'checksums.json').items():
            assert lab.digest(bd/rel) == sha
            checked += 1
    availability = []
    for path in sorted((root/'results').glob('availability-*.json')):
        a = read(path)
        consecutive = 0
        for s in a['observations']:
            assert s['windows_sampled'] and s['clear'] == (not s['blockers'])
            if s['clear']:
                assert max(s['windows_load_percent']) <= 15
            consecutive = consecutive+1 if s['clear'] else 0
        assert (consecutive == 3) == (a['status'] == 'ready')
        availability.append({'file': path.name, 'status': a['status'], 'observations': len(a['observations'])})
    identities, timing, batches = collections.defaultdict(set), {}, []
    for directory in sorted((root/'runs').glob('*')):
        assert not batches, 'only one batch authorized'
        plan, done, rows = (read(directory/name) for name in ('plan.json', 'completion.json', 'records.json'))
        for key, value in p['study'].items():
            assert plan[key] == value
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
            command = read(d/'command.txt')
            original = pathlib.PurePosixPath(command['cwd'])/'runs'/directory.name/row['run_id']
            assert command['argv'] == [b['exe'], '--config', str(original/'config.json'), '--output', str(original/'result.json')]
            collector = root/'snapshots/source'/p['collector_source_id']
            assert row['collector_sha256'] == lab.digest(collector/'tools/lab.py')
            assert row['source_id'] == b['source_id'] and row['binary_sha256'] == b['binary_sha256']
            if row['status'] != 'completed':
                assert done['status'] == 'failed' and not row['included']
                continue
            assert (d/'stderr.log').stat().st_size == 0
            r = read(d/'result.json')
            resolved = copy.deepcopy(c['config'])
            resolved['steal_enabled'] = True
            assert r['resolved_config'] == resolved and r['correctness']['pass'] and row['exit_code'] == 0
            assert row['timing'] == r['timing'] and len(r['epochs']) == 1
            assert row['included'] == (row['purpose'] == 'timing')
            e, n = r['epochs'][0], c['config']['workload']['elements']
            cc, tile = e['correctness'], 1 if c['kind'] == 'memory' else 256
            assert cc['pass'] and cc['mismatches'] == 0 and cc['compared_elements'] == n
            assert cc['reference_tile_elements'] == tile
            assert cc['reference_workers_used'] == min(c['config']['measurement']['reference_workers'], (n+tile-1)//tile)
            if c['kind'] == 'memory':
                assert all(e['identity'][key] == value for key, value in oracle.identity(c['config']).items())
                if row['purpose'] == 'control':
                    oracle.diagnostic_oracle(c['config'], e)
            assert r['initialization']['data_allocation_requested'] == 'zeroed'
            assert r['initialization']['data_allocation_used'] == ('zeroed' if c['kind'] == 'memory' and n else 'none')
            diagnostic = c['config']['measurement']['mode'] == 'diagnostic'
            assert cc['exact_once'] == (True if diagnostic and c['config']['executor'] != 'serial' else None)
            cpus = c['config']['policies']['affinity']['cpus']
            assert r['affinity']['requested'] == cpus
            assert r['affinity']['actual_workers'] == [[cpu] for cpu in cpus]
            if c['build'] != 'old':
                fill = c['config']['measurement']['data_fill_lanes']
                assert r['data_fill']['lanes_requested'] == fill
                assert r['data_fill']['lanes_used'] == (fill if c['kind'] == 'memory' and n else 0)
                mode = c['config']['measurement']['data_identity']
                meta = r['data_identity']
                used = mode if c['kind'] == 'memory' and n else 'none'
                assert meta['requested'] == mode and meta['used'] == used
                assert meta['block_bytes'] == (262144 if used == 'blocked' else 0)
                lanes = c['config']['measurement']['memory_lanes']
                assert r['execution_kernel']['memory_lanes_requested'] == lanes
                assert r['execution_kernel']['memory_lanes_used'] == (lanes if c['kind'] == 'memory' and n else 0)
            assert r['initialization']['requested_workers'] == 1
            assert r['initialization']['workers_used'] == (1 if c['kind'] == 'memory' and n else 0)
            assert all(v >= 0 for v in r['phase_seconds'].values())
            assert sum(r['phase_seconds'].values()) <= r['timing']['end_to_end_seconds']+1e-9
            identities[(c['kind'], c['config']['workload']['seed'], n)].add(
                (json.dumps(e['identity'], sort_keys=True), cc['output_hash_fnv1a64'], e['pretouch_hash_fnv1a64']))
            if row['included']:
                timing[(row['condition'], row['repeat'])] = {
                    'app': r['timing']['end_to_end_seconds'], 'epoch': r['timing']['epoch_seconds'],
                    'process': row['elapsed_process_seconds'], 'phases': r['phase_seconds'],
                    'initialization_plus_identity': (r['phase_seconds']['workload_initialization']+
                                                     r['phase_seconds']['identity_hashes']),
                    'run_path': d.relative_to(root).as_posix()}
        resource = read(directory/'resource-observations.json')
        assert resource['samples'] and resource['clean'] == all(s['clear'] for s in resource['samples'])
        a = read(root/plan['availability_receipt'])
        assert a['status'] == 'ready' and all(s['clear'] for s in a['observations'][-3:])
        clean = done['status'] == 'completed' and resource['clean']
        if clean:
            assert len(rows) == 44 and sum(r['included'] for r in rows) == 28
        batches.append({'batch': directory.name, 'status': done['status'], 'confirmable': clean,
                        'processes': len(rows), 'timing_samples': sum(r['included'] for r in rows),
                        'resource_samples': len(resource['samples'])})
    assert all(len(v) == 1 for v in identities.values()), 'full input/output/pretouch mismatch'
    heldout = []
    if batches and batches[0]['confirmable']:
        for seed, n in INPUTS:
            pairs = [{'repeat': rep, **{label: timing[(f'memory-s{seed}-{label}', rep)]
                                       for label in ('base', 'candidate')}} for rep in range(1, 8)]
            medians = {}
            for label in ('base', 'candidate'):
                medians[label] = {key: statistics.median(pair[label][key] for pair in pairs)
                                  for key in ('app', 'epoch', 'process', 'initialization_plus_identity')}
                medians[label]['phases'] = {key: statistics.median(pair[label]['phases'][key] for pair in pairs)
                                            for key in pairs[0][label]['phases']}
            wins = sum(pair['candidate']['app'] < pair['base']['app'] for pair in pairs)
            heldout.append({'seed': seed, 'elements': n, 'wins': wins, 'epoch_wins': sum(pair['candidate']['epoch'] < pair['base']['epoch'] for pair in pairs), 'medians': medians,
                            'app_speedup': medians['base']['app']/medians['candidate']['app'],
                            'epoch_speedup': medians['base']['epoch']/medians['candidate']['epoch'],
                            'passed': (wins >= 6 and medians['candidate']['app'] <= .95*medians['base']['app']
                                       and medians['candidate']['epoch'] <= 1.10*medians['base']['epoch']),
                            'pairs': pairs})
    result = {'created': lab.now(), 'audit_pass': True, 'hash_checks': checked, 'source_hash_checks': sources,
              'batches': batches, 'availability': availability, 'heldout': heldout,
              'accepted': len(heldout) == 2 and all(h['passed'] for h in heldout),
              'status': batches[0]['status'] if batches else 'not_run',
              'scope': 'independent data generation interleaved; app primary, epoch guard; original separate full FNV unchanged'}
    output = root/'results'/('audit-'+uuid.uuid4().hex+'.json')
    lab.write(output, result)
    print(json.dumps({'audit': str(output), 'batches': batches, 'accepted': result['accepted']}, ensure_ascii=False), flush=True)
    return result


def report(root):
    receipt = read(sorted((root/'results').glob('export-*.json'))[-1])
    for rel, sha in receipt['files'].items():
        assert lab.digest(root/rel) == sha
    result = audit(root)
    project = pathlib.Path(__file__).resolve().parents[1]
    data = root.relative_to(project).as_posix()
    lines = ['# 第十一轮数据生成交错报告', '', f"采用data_fill_lanes=4：{result['accepted']}。固定候选，无筛选或追加样本。",
             '同一新二进制仅改变data_fill_lanes=1/4；memory_lanes4、separate完整FNV、zeroed、填充线程1、参考线程4。旧/新四类诊断control不进入性能统计。', '',
             '|批次|状态|进程|正式计时|资源观测|', '|---|---|---:|---:|---:|']
    for b in result['batches']:
        lines.append(f"|{b['batch']}|{b['status']}|{b['processes']}|{b['timing_samples']}|{b['resource_samples']}|")
    lines += ['', '|seed|块数|fill1 app(ms)|fill4 app(ms)|app加速|app胜对|epoch比(候选/对照)|过门槛|',
              '|---|---:|---:|---:|---:|---:|---:|---|']
    for h in result['heldout']:
        m = h['medians']
        lines.append(f"|{h['seed']}|{h['elements']}|{m['base']['app']*1000:.3f}|{m['candidate']['app']*1000:.3f}|{h['app_speedup']:.3f}×|{h['wins']}/7|{1/h['epoch_speedup']:.3f}|{h['passed']}|")
    for h in result['heldout']:
        m = h['medians']
        lines += ['', f"## seed{h['seed']}区间中位数（ms）", '', '|区间|fill1|fill4|', '|---|---:|---:|']
        for metric in ('epoch', 'app', 'process', 'initialization_plus_identity'):
            lines.append(f"|{metric}|{m['base'][metric]*1000:.3f}|{m['candidate'][metric]*1000:.3f}|")
        for phase in m['base']['phases']:
            lines.append(f"|{phase}|{m['base']['phases'][phase]*1000:.3f}|{m['candidate']['phases'][phase]*1000:.3f}|")
        lines += ['', '|对|fill1 epoch(ms)|fill4 epoch(ms)|fill1 app(ms)|fill4 app(ms)|原始记录|',
                  '|---:|---:|---:|---:|---:|---|']
        for pair in h['pairs']:
            links = ' / '.join(f"[{label}](../../{data}/{pair[label]['run_path']}/result.json)" for label in ('base', 'candidate'))
            lines.append(f"|{pair['repeat']}|{pair['base']['epoch']*1000:.3f}|{pair['candidate']['epoch']*1000:.3f}|{pair['base']['app']*1000:.3f}|{pair['candidate']['app']*1000:.3f}|{links}|")
    lines += ['', f"Windows核对{len(receipt['files'])}个导出文件；独立审计{result['source_hash_checks']}个源码项、{result['hash_checks']}个构建/批次/运行散列项。",
              '完整身份、输出和预读散列一致，核验元素数等于N，所有成功慢样本保留。',
              '主要门槛：两个输入各需≥6/7对app更快，app中位数下降≥5%；epoch护栏：每输入候选epoch中位数≤对照110%。这不是显著性检验。',
              '阶段中位数不能相加；initialization_plus_identity为每run两阶段之和再取中位数。填充交错未移动data散列，仍用完整原FNV读取实际存储。只通过资源观察，不证明物理独占、NUMA或缓存因果；不归为窃取收益，不乘历史倍数。',
              '默认fill1和历史推荐保留；通过才另存configs/fill-interleaved。原FNV、任务执行和完整参考核验未改，不省略生成工作。', '',
              f'冻结协议：[33](../../{PROTOCOL})；原件：`{data}/runs`。', '']
    output = project/'report/fill-interleaved'/('第十一轮数据生成交错报告-'+uuid.uuid4().hex[:8]+'.md')
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
