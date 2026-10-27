#!/usr/bin/env python3
"""Confirm frozen V4 choices only in an observed idle window; never stop other jobs."""
import argparse
import collections
import copy
import hashlib
import json
import os
import pathlib
import random
import shutil
import statistics
import subprocess
import threading
import time
import uuid

import lab

KINDS = ('uniform', 'skewed', 'memory')
REFS = {'uniform': 32, 'skewed': 32, 'memory': 4}
INPUTS = ((6619, 221184, 56), (10007, 344064, 88))
PROTOCOL = 'docs/20-第五轮空闲窗口确认协议.md'
PS = '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'


def read(path):
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig'))


def provenance(root):
    builds = read(root/'configs/verified/builds.json')
    for kind in KINDS:
        b = builds[kind]
        assert lab.digest(root/b['config']) == b['config_sha256']
        assert b['reference_workers'] == REFS[kind]
        exe = root.parent/('ws-20261016-verify-'+b['build'])/'build-none/worksteal'
        v = read(exe.parent/'validation.json')
        assert v['pass'] and v['source_id'] == b['source_id']
        assert v['binary_sha256'] == b['binary_sha256'] == lab.digest(exe)
        b['exe'] = str(exe)
        b['validation'] = v
    return {k: builds[k] for k in KINDS}


def prepare(root):
    origin = lab.ROOT
    root.mkdir(parents=True, exist_ok=False)
    for f in lab.source_files():
        d = root/f.relative_to(origin)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, d)
    lab.ROOT = root
    builds = provenance(root)
    cases, pairs = [], []
    for kind in KINDS:
        for seed, n, blocks in INPUTS:
            pair = []
            for label, ref in (('base', 1), ('candidate', REFS[kind])):
                c = read(root/builds[kind]['config'])
                c['workload'].update(seed=seed, elements=blocks if kind == 'memory' else n)
                c['layout_seed'] = seed
                c['measurement']['reference_workers'] = ref
                item = {'id': f'{kind}-s{seed}-{label}', 'kind': kind, 'seed': seed, 'config': c}
                pair.append(item['id'])
                cases.append(item)
            pairs.append(pair)
    random.Random(2026101605).shuffle(pairs)
    order = [('warmup', 0, cid) for pair in pairs for cid in pair]
    for rep in range(1, 8):
        order.extend(('timing', rep, cid) for pair in pairs for cid in (pair if rep % 2 else pair[::-1]))
    plan = {'experiment': 'V5-idle-confirmation', 'created': lab.now(),
            'protocol': PROTOCOL, 'protocol_sha256': lab.digest(root/PROTOCOL),
            'collector_source_id': lab.snapshot(), 'builds': builds, 'conditions': cases,
            'order': order, 'pairs': pairs, 'metric': 'end_to_end_seconds',
            'gate': 'both inputs >=6/7 paired wins and candidate app median <=0.95 base',
            'processes': 96, 'timing_samples': 84, 'no_adaptation': True}
    lab.write(root/'frozen-plan.json', plan)
    lab.write(root/'results/preparation.json', {'created': lab.now(), 'status': 'prepared_not_run',
              'plan_sha256': lab.digest(root/'frozen-plan.json'), 'research_processes': 0})
    print(json.dumps({'prepared': str(root), 'conditions': len(cases), 'planned_processes': len(order)}), flush=True)


def ancestors():
    result = set()
    pid = os.getpid()
    while pid > 0 and pid not in result:
        result.add(pid)
        try:
            data = pathlib.Path(f'/proc/{pid}/status').read_text()
            pid = int(next(s.split(':', 1)[1] for s in data.splitlines() if s.startswith('PPid:')))
        except (OSError, StopIteration):
            break
    return result


def observe(own, windows=False):
    sample = {'time': lab.now(), 'windows_sampled': windows}
    try:
        p = subprocess.run(['ps', '-eo', 'pid,ppid,comm,args'], capture_output=True, text=True, timeout=10, check=True)
        sample['processes'] = p.stdout
        rows = []
        for line in p.stdout.splitlines()[1:]:
            parts = line.split(None, 3)
            if len(parts) == 4:
                rows.append((int(parts[0]), int(parts[1]), parts[2], parts[3]))
        # Only our direct measured executable and our transient observation programs.
        allowed = own | {pid for pid, parent, comm, args in rows
                         if parent == os.getpid() and
                         (comm in ('worksteal', 'ps', 'powershell.exe') or
                          (comm == 'python3' and args == 'ps -eo pid,ppid,comm,args'))}
        names = {'RayTracing', 'worksteal', 'runtime_checks', 'cc1plus', 'cc1', 'g++', 'gcc',
                 'clang', 'clang++', 'cmake', 'ninja', 'make', 'ctest', 'python', 'python3'}
        markers = ('hpc-raytracing', 'remaining.py', 'run_variant.py', 'sdar-setup', 'torchrun')
        sample['blockers'] = [{'pid': pid, 'comm': comm, 'args': args} for pid, _, comm, args in rows
                              if pid not in allowed and (comm in names or any(m in args for m in markers))]
        if windows:
            p = subprocess.run([PS, '-NoProfile', '-NonInteractive', '-Command',
                                '@(Get-CimInstance Win32_Processor | ForEach-Object { $_.LoadPercentage }) | ConvertTo-Json -Compress'],
                               capture_output=True, text=True, timeout=20, check=True)
            values = json.loads(p.stdout.strip().lstrip('\ufeff'))
            values = values if isinstance(values, list) else [values]
            assert values and all(isinstance(x, (int, float)) and 0 <= x <= 100 for x in values)
            sample['windows_load_percent'] = values
            if max(values) > 15:
                sample['blockers'].append({'reason': 'windows_load_above_15_percent'})
        sample['clear'] = not sample['blockers']
    except Exception as e:
        sample.update(clear=False, error=str(e), blockers=[{'reason': 'observation_failed'}])
    return sample


def availability(root, wait_seconds):
    own = ancestors()
    observations = []
    started = time.monotonic()
    consecutive = 0
    while True:
        sample = observe(own, windows=True)
        observations.append(sample)
        consecutive = consecutive + 1 if sample['clear'] else 0
        print(json.dumps({'availability': sample['clear'], 'consecutive': consecutive,
                          'load': sample.get('windows_load_percent'), 'blockers': sample['blockers']}), flush=True)
        if consecutive == 3:
            status = 'ready'
            break
        delay = 3 if sample['clear'] else 20
        if time.monotonic() - started + delay > wait_seconds:
            status = 'deferred_busy'
            break
        time.sleep(delay)
    path = root/'results'/('availability-'+uuid.uuid4().hex+'.json')
    lab.write(path, {'status': status, 'created': lab.now(), 'observations': observations,
                    'wait_budget_seconds': wait_seconds, 'elapsed_seconds': time.monotonic()-started})
    return status, path


def run(root, wait_seconds):
    plan = read(root/'frozen-plan.json')
    assert lab.digest(root/'frozen-plan.json') == read(root/'results/preparation.json')['plan_sha256']
    assert lab.digest(root/PROTOCOL) == plan['protocol_sha256']
    assert provenance(root) == plan['builds']
    if any((root/'runs').glob('*')):
        raise RuntimeError('this collector already has a batch; use a fresh prepared collector')
    status, receipt = availability(root, wait_seconds)
    if status != 'ready':
        return 3
    cases = {c['id']: c for c in plan['conditions']}
    exe = pathlib.Path(plan['builds']['skewed']['exe'])
    batch = lab.Batch('V5-idle-confirmation', {**plan, 'availability_receipt': str(receipt.relative_to(root)),
                      'frozen_plan_sha256': lab.digest(root/'frozen-plan.json')}, exe, budget=600)
    own, stop, samples, lock = ancestors(), threading.Event(), [], threading.Lock()

    def check():
        with lock:
            # WSL1 may expose a second concurrent ps child before exec with its
            # parent's comm=python3. Serialize probes to remove that race.
            s = observe(own)
            samples.append(s)
        return s['clear']

    def monitor():
        while not stop.wait(.5):
            if not check():
                break

    worker = threading.Thread(target=monitor, daemon=True)
    worker.start()
    state, reason = 'completed', None
    try:
        for purpose, repeat, cid in plan['order']:
            if not check() or any(not s['clear'] for s in samples):
                state, reason = 'contaminated', 'external_work_or_observation_failure'
                break
            c = cases[cid]
            b = plan['builds'][c['kind']]
            batch.exe, batch.source, batch.binary = pathlib.Path(b['exe']), b['source_id'], b['binary_sha256']
            batch.run(c['config'], cid, purpose, repeat, timeout=90)
            if not check() or any(not s['clear'] for s in samples):
                state, reason = 'contaminated', 'external_work_or_observation_failure'
                break
    except Exception as e:
        state, reason = 'failed', str(e)
    finally:
        stop.set()
        worker.join(timeout=15)
        if worker.is_alive():
            state, reason = 'failed', 'monitor_did_not_stop'
        lab.write(batch.path/'resource-observations.json', {'samples': samples, 'interval_seconds': .5,
                  'clean': all(s['clear'] for s in samples), 'scope': 'known WSL programs; not exclusive reservation'})
        batch.finish(state, reason)
    print(json.dumps({'status': state, 'batch': str(batch.path), 'processes': len(batch.records)}), flush=True)
    return 0 if state == 'completed' else 4


def audit(root):
    plan_path = root/'frozen-plan.json'
    if not plan_path.exists():
        plan_path = root/'results/frozen-plan.json'
    frozen = read(plan_path)
    assert lab.digest(plan_path) == read(root/'results/preparation.json')['plan_sha256']
    protocol_path = root/PROTOCOL
    if not protocol_path.exists():
        protocol_path = root/'snapshots/source'/frozen['collector_source_id']/PROTOCOL
    assert lab.digest(protocol_path) == frozen['protocol_sha256']
    snapshot = root/'snapshots/source'/frozen['collector_source_id']
    source_manifest = read(snapshot/'manifest.json')
    assert source_manifest['source_id'] == frozen['collector_source_id']
    assert hashlib.sha256(json.dumps(source_manifest['files'], sort_keys=True).encode()).hexdigest() == source_manifest['source_id']
    for rel, sha in source_manifest['files'].items():
        assert lab.digest(snapshot/rel) == sha
    availability_checks = []
    for receipt in sorted((root/'results').glob('availability-*.json'), key=lambda p: read(p)['created']):
        a = read(receipt)
        assert a['observations'] and a['status'] in ('ready', 'deferred_busy')
        consecutive = 0
        for s in a['observations']:
            assert s['windows_sampled'] and s['clear'] == (not s['blockers'])
            if s['clear']:
                assert max(s['windows_load_percent']) <= 15
            consecutive = consecutive + 1 if s['clear'] else 0
        assert (consecutive == 3) == (a['status'] == 'ready')
        availability_checks.append({'file': receipt.name, 'status': a['status'],
                                    'observations': len(a['observations']), 'elapsed_seconds': a['elapsed_seconds']})
    checked = 0
    results = []
    for directory in sorted((root/'runs').glob('*')):
        plan, done, rows = (read(directory/n) for n in ('plan.json', 'completion.json', 'records.json'))
        assert plan['conditions'] == frozen['conditions'] and plan['order'] == frozen['order']
        assert plan['builds'] == frozen['builds']
        assert plan['frozen_plan_sha256'] == lab.digest(plan_path)
        assert done['processes'] == len(rows)
        assert [(r['purpose'], r['repeat'], r['condition']) for r in rows] == [tuple(x) for x in frozen['order'][:len(rows)]]
        for manifest in [directory/'checksums.json'] + list(directory.glob('*/checksums.json')):
            m = read(manifest)
            assert set(m) == {str(p.relative_to(manifest.parent)).replace('\\', '/') for p in manifest.parent.rglob('*')
                              if p.is_file() and p.name != 'checksums.json'}
            for rel, sha in m.items():
                assert lab.digest(manifest.parent/rel) == sha
                checked += 1
        cs = {c['id']: c for c in frozen['conditions']}
        assert {p.name for p in directory.iterdir() if p.is_dir()} == {r['run_id'] for r in rows}
        identities, timing = collections.defaultdict(set), collections.defaultdict(dict)
        for r in rows:
            rd, c = directory/r['run_id'], cs[r['condition']]
            b = frozen['builds'][c['kind']]
            assert read(rd/'metadata.json') == r and read(rd/'config.json') == c['config']
            assert r['binary_sha256'] == b['binary_sha256'] and r['source_id'] == b['source_id']
            assert read(rd/'command.txt')['argv'][0] == b['exe']
            if r['status'] != 'completed':
                assert done['status'] == 'failed' and not r['included']
                continue
            result = read(rd/'result.json')
            expected = copy.deepcopy(c['config'])
            expected['steal_enabled'] = True
            assert result['resolved_config'] == expected and len(result['epochs']) == 1
            assert result['correctness']['pass'] and result['timing'] == r['timing']
            assert r['included'] == (r['purpose'] == 'timing')
            e, n = result['epochs'][0], c['config']['workload']['elements']
            cc = e['correctness']
            tile = 1 if c['kind'] == 'memory' else 256
            assert cc['pass'] and cc['mismatches'] == 0 and cc['compared_elements'] == n
            assert cc['reference_workers_used'] == min(c['config']['measurement']['reference_workers'], (n+tile-1)//tile)
            assert cc['reference_tile_elements'] == tile
            assert all(v >= 0 for v in result['phase_seconds'].values())
            assert sum(result['phase_seconds'].values()) <= r['timing']['end_to_end_seconds'] + 1e-9
            identities[(c['kind'], c['seed'])].add((json.dumps(e['identity'], sort_keys=True), cc['output_hash_fnv1a64']))
            if r['included']:
                assert r['repeat'] not in timing[r['condition']]
                timing[r['condition']][r['repeat']] = {'app': r['timing']['end_to_end_seconds'],
                    'epoch': r['timing']['epoch_seconds'], 'reference': result['phase_seconds']['full_reference_verification'],
                    'process': r['elapsed_process_seconds'], 'run_id': r['run_id']}
        assert all(len(v) == 1 for v in identities.values())
        observations = read(directory/'resource-observations.json')
        assert observations['clean'] == all(s['clear'] for s in observations['samples'])
        availability_receipt = read(root/plan['availability_receipt'])
        assert availability_receipt['status'] == 'ready'
        last = availability_receipt['observations'][-3:]
        assert len(last) == 3 and all(s['clear'] and s['windows_sampled'] and max(s['windows_load_percent']) <= 15 for s in last)
        confirmable = done['status'] == 'completed' and observations['clean']
        selection = {}
        if confirmable:
            assert len(rows) == 96 and sum(r['included'] for r in rows) == 84
            assert set(timing) == set(cs)
            assert all(set(v) == set(range(1, 8)) for v in timing.values())
            for kind in KINDS:
                inputs = []
                for seed, _, _ in INPUTS:
                    base, candidate = (timing[f'{kind}-s{seed}-{label}'] for label in ('base', 'candidate'))
                    pairs = [{'repeat': rep, 'base': base[rep], 'candidate': candidate[rep]} for rep in range(1, 8)]
                    wins = sum(p['candidate']['app'] < p['base']['app'] for p in pairs)
                    medians = {label: {metric: statistics.median(row[metric] for row in values.values())
                               for metric in ('app', 'epoch', 'reference', 'process')}
                               for label, values in (('base', base), ('candidate', candidate))}
                    ratio = medians['base']['app']/medians['candidate']['app']
                    inputs.append({'seed': seed, 'wins': wins, 'medians': medians, 'app_speedup': ratio,
                                   'passed': wins >= 6 and medians['candidate']['app'] <= .95*medians['base']['app'], 'pairs': pairs})
                selection[kind] = {'confirmed': all(h['passed'] for h in inputs), 'reference_workers': REFS[kind], 'inputs': inputs}
        results.append({'batch': directory.name, 'status': done['status'], 'processes': len(rows),
                        'timing_samples': sum(r['included'] for r in rows), 'confirmable': confirmable, 'selection': selection})
    summary = {'created': lab.now(), 'audit_pass': True, 'hash_checks': checked, 'batches': results,
               'source_hash_checks': len(source_manifest['files']), 'availability': availability_checks,
               'status': 'not_run' if not results else results[-1]['status'],
               'scope': 'observed idle window; no physical placement or exclusive reservation proof'}
    path = root/'results'/('audit-'+uuid.uuid4().hex+'.json')
    lab.write(path, summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return path


def report(root):
    """Re-audit exported raw data on Windows; write a new report without overwrites."""
    exports = sorted((root/'results').glob('export-*.json'))
    assert exports, 'no verified Linux export receipt'
    export = read(exports[-1])
    for rel, sha in export['files'].items():
        assert lab.digest(root/rel) == sha
    audit_path = audit(root)
    summary = read(audit_path)
    frozen = read(root/'results/frozen-plan.json')
    # The unchanged measured binaries are in the fourth-round archive.
    project = pathlib.Path(__file__).resolve().parents[1]
    data_dir = root.relative_to(project).as_posix()
    for b in frozen['builds'].values():
        assert lab.digest(project/b['snapshot']/'worksteal') == b['binary_sha256']
    lines = ['# 第五轮空闲窗口确认记录', '',
             '本轮固定第四轮候选及原二进制，仅换新输入；不重新筛选参数。', '',
             f"计划96研究进程、84计时样本；实际批次状态：{summary['status']}。",
             'uniform/skewed核验32线程、memory核验4线程，各与同二进制串行核验比较；light保留串行。', '']
    if not summary['batches']:
        probes = sorted((root/'results').glob('availability-*.json'), key=lambda p: read(p)['created'])
        assert probes
        probe = read(probes[-1])
        count = sum(v['observations'] for v in summary['availability'])
        lines += ['## 尚未启动正式计时', '',
                  f"资源检查：{probe['status']}，{len(probes)}段有界等待、共{count}次观测；研究进程0个、计时样本0个。",
                  '检测到其他计算/编排任务或主机负载未过门禁。没有停止其他项目、没有混跑并宣称空闲收益。', '',
                  '各段证据：', '']
        for v in summary['availability']:
            lines.append(f"- `{data_dir}/results/{v['file']}`：{v['status']}，{v['observations']}次观测、等待{v['elapsed_seconds']:.1f}秒。")
        lines += ['', '本轮没有应用运行结果，不能据此确认性能收益。', '']
    else:
        for b in summary['batches']:
            lines += [f"## 批次 {b['batch']}", '',
                      f"状态{b['status']}；{b['processes']}进程、{b['timing_samples']}计时。", '']
            if b['confirmable']:
                lines += ['|任务|seed|串行app中位数(ms)|候选app中位数(ms)|比值|胜对|输入过门槛|',
                          '|---|---:|---:|---:|---:|---:|---|']
                for kind, v in b['selection'].items():
                    for h in v['inputs']:
                        m = h['medians']
                        lines.append(f"|{kind}|{h['seed']}|{m['base']['app']*1000:.3f}|{m['candidate']['app']*1000:.3f}|{h['app_speedup']:.3f}×|{h['wins']}/7|{'是' if h['passed'] else '否'}|")
                lines += ['', '双输入确认：'+ '；'.join(k+('通过' if v['confirmed'] else '未通过') for k,v in b['selection'].items())+'。', '']
                lines += ['各计时区间中位数（ms），每格为串行核验对照→固定候选：', '',
                          '|任务|seed|执行epoch|完整参考核验|外层进程|',
                          '|---|---:|---:|---:|---:|']
                for kind, v in b['selection'].items():
                    for h in v['inputs']:
                        m = h['medians']
                        values = [f"{m['base'][metric]*1000:.3f}→{m['candidate'][metric]*1000:.3f}"
                                  for metric in ('epoch', 'reference', 'process')]
                        lines.append(f"|{kind}|{h['seed']}|"+'|'.join(values)+'|')
                lines += ['', '逐对app时间及运行记录（ms，慢成功样本全部保留）：', '',
                          '|任务|seed|重复|对照app|候选app|候选更快|原始记录|',
                          '|---|---:|---:|---:|---:|---|---|']
                for kind, v in b['selection'].items():
                    for h in v['inputs']:
                        for pair in h['pairs']:
                            base, candidate = pair['base'], pair['candidate']
                            links = ' / '.join(f"[{label}](../../{data_dir}/runs/{b['batch']}/{row['run_id']}/result.json)"
                                               for label, row in (('对照', base), ('候选', candidate)))
                            lines.append(f"|{kind}|{h['seed']}|{pair['repeat']}|{base['app']*1000:.3f}|{candidate['app']*1000:.3f}|"
                                         +('是' if candidate['app'] < base['app'] else '否')+'|'+links+'|')
                lines.append('')
            else:
                lines += ['此批次不作空闲确认；原始成功/慢样本/失败均保留，不能选择性补齐。', '']
            lines += [f"原件：`{data_dir}/runs/{b['batch']}`；完整逐对app/epoch/reference/process在本次audit JSON。", '']
    lines += ['## 核验与解释边界', '',
              f"Windows重新逐文件核对Linux导出{len(export['files'])}个文件、冻结源码{summary['source_hash_checks']}个SHA256项、批次/运行清单{summary['hash_checks']}项；核对所有资源等待记录。若存在已完成批次，另从原始结果重算配置、全量核验、身份、逐对结果与门槛。第四轮原二进制散列也已核对。",
              '应用计时包含初始化、调度和完整参考核验；epoch只包含执行区间。核验收益不是调度内核收益，不能与历史倍数相乘。',
              '资源门禁只证明已定义观测窗口，不能证明物理绑核或排除所有短暂/未知Windows负载；原始数据及慢成功样本保留。',
              '历史四轮结果不覆盖。同盘双副本不等于故障备份；题面DevContainer实建与完整连续Session导出仍待完成。', '',
              f'复现协议：[docs/20](../../docs/20-第五轮空闲窗口确认协议.md)。实验计划及顺序：`{data_dir}/results/frozen-plan.json`。',
              f"本次审计：[完整统计和来源](../../{data_dir}/results/{audit_path.name})。", '']
    title = '第五轮空闲窗口确认报告' if summary['batches'] else '第五轮准备与资源检查'
    out = project/'report/confirmation'/(title+'.md')
    if out.exists():
        out = out.with_name(out.stem+'-'+uuid.uuid4().hex[:8]+out.suffix)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(json.dumps({'report': str(out), 'export_checks': len(export['files'])}, ensure_ascii=False), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=('prepare', 'probe', 'run', 'audit', 'export', 'report'))
    ap.add_argument('--root', required=True)
    ap.add_argument('--wait-seconds', type=int, default=0)
    ap.add_argument('--target')
    a = ap.parse_args()
    if not 0 <= a.wait_seconds <= 1800:
        ap.error('--wait-seconds must be in 0..1800')
    root = pathlib.Path(a.root).resolve()
    if a.action == 'prepare':
        prepare(root)
        return 0
    lab.ROOT = root
    if a.action == 'probe':
        return 0 if availability(root, a.wait_seconds)[0] == 'ready' else 3
    if a.action == 'run':
        return run(root, a.wait_seconds)
    if a.action == 'audit':
        audit(root)
    if a.action == 'report':
        report(root)
    if a.action == 'export':
        if not a.target:
            ap.error('--target required')
        plan_copy = root/'results/frozen-plan.json'
        if not plan_copy.exists():
            shutil.copy2(root/'frozen-plan.json', plan_copy)
        assert lab.digest(plan_copy) == read(root/'results/preparation.json')['plan_sha256']
        lab.export(argparse.Namespace(target=a.target))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
