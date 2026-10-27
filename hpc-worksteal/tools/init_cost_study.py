#!/usr/bin/env python3
"""V12 standalone cost diagnosis. Never a candidate acceptance experiment."""
import argparse
import copy
import hashlib
import json
import os
import pathlib
import shutil
import statistics
import subprocess
import threading
import time
import uuid

import confirm_idle as guard
import lab
import memory_tuning_study as oracle

PROTOCOL = 'docs/35-第十二轮初始化成本诊断协议.md'
INPUTS = ((91009, 80), (97001, 128))
APP = '/root/lzuhpc-experiments/ws-20261022-fill-interleaved-release/build-none/worksteal'
APP_SHA = '3992f3db54f07de09e3fd8510463e6fb6458473340a9428e14e33723b6a97caf'


def read(path):
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig'))


def textfile(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(text)


def design(root):
    cases, order, pairs = [], [], []
    for seed, n in INPUTS:
        c = read(root/'configs/verified/memory.json')
        c['workload'].update(seed=seed, elements=n)
        c['layout_seed'] = seed
        c['measurement'].update(mode='diagnostic', initialization_workers=1,
            data_allocation='zeroed', memory_lanes=4, data_identity='separate', data_fill_lanes=1)
        cid = f'app-s{seed}'
        cases.append({'id': cid, 'build': 'app', 'config': c, 'seed': seed, 'words': n*65536})
        order.append(('control', 0, cid))
        pair = []
        for mode in ('zeroed', 'overwrite'):
            cid = f'probe-s{seed}-{mode}'
            cases.append({'id': cid, 'build': 'release', 'seed': seed, 'words': n*65536, 'allocation': mode})
            pair.append(cid)
        pairs.append(pair)
    order += [('warmup', 0, cid) for pair in pairs for cid in pair]
    for rep in range(1, 6):
        order += [('profiling', rep, cid) for pair in pairs for cid in (pair if rep % 2 else pair[::-1])]
    return {'conditions': cases, 'order': order, 'pairs': pairs, 'max_processes': 26,
            'profiling_samples': 20, 'scope': 'diagnostic only; no acceptance or recommendation'}


def check_selftest(result):
    assert result['pass'] and len(result['cases']) == 36
    expected = [(n, seed, mode) for n in (0,1,2,3,17,4097)
                for seed in (0,42,2**64-3) for mode in ('zeroed','overwrite')]
    for row, key in zip(result['cases'], expected):
        n, seed, mode = key
        assert (row['words'], row['seed'], row['allocation']) == key
        data = [oracle.mix((seed+i) & oracle.MASK) for i in range(n)]
        assert row['data'] == data and row['data_hash_fnv1a64'] == oracle.fnv(data)
        assert row['pass'] and row['compared_words'] == n and row['selftest']


def prepare(root):
    origin = lab.ROOT
    root.mkdir(parents=True, exist_ok=False)
    for src in lab.source_files():
        dest = root/src.relative_to(origin)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    lab.ROOT = root
    source = lab.snapshot()
    builds = {}
    for tag in ('release', 'asan'):
        directory = root/'snapshots/probes'/tag
        directory.mkdir(parents=True)
        exe = directory/'init_cost_probe'
        flags = ['-O3', '-DNDEBUG', '-flto=2'] if tag == 'release' else [
            '-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        command = ['g++', '-std=c++20', '-Wall', '-Wextra', '-Wpedantic', '-Wconversion',
                   *flags, str(root/'tools/init_cost_probe.cpp'), '-o', str(exe)]
        p = subprocess.run(command, capture_output=True, text=True, timeout=120)
        lab.write(directory/'compile.json', {'argv': command, 'exit_code': p.returncode,
                  'stdout': p.stdout, 'stderr': p.stderr})
        assert p.returncode == 0 and not p.stderr, 'probe compile failed or warned'
        p = subprocess.run([str(exe), '--selftest'], capture_output=True, text=True, timeout=90)
        textfile(directory/'selftest-stdout.json', p.stdout)
        textfile(directory/'selftest-stderr.log', p.stderr)
        lab.write(directory/'selftest-command.json', {'argv': [str(exe), '--selftest'], 'exit_code': p.returncode})
        assert p.returncode == 0 and not p.stderr
        check_selftest(json.loads(p.stdout))
        builds[tag] = {'exe': str(exe), 'binary_sha256': lab.digest(exe), 'source_id': source,
                       'artifact': directory.relative_to(root).as_posix()}
        lab.seal(directory)
    app = pathlib.Path(APP)
    v = read(app.parent/'validation.json')
    assert v['pass'] and v['binary_sha256'] == lab.digest(app) == APP_SHA
    assert all(r['returncode'] == 0 and not r['stderr'] for r in v['records'])
    for folder, identifier in (('builds', APP_SHA), ('source', v['source_id'])):
        shutil.copytree(app.parent.parent/'snapshots'/folder/identifier, root/'snapshots'/folder/identifier)
    builds['app'] = {'exe': APP, 'binary_sha256': APP_SHA, 'source_id': v['source_id'],
                     'artifact': f'snapshots/builds/{APP_SHA}'}
    disassembly = {}
    for tag in ('release', 'app'):
        argv = ['objdump', '-d', '-C', '--no-show-raw-insn', builds[tag]['exe']]
        p = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=True)
        assert not p.stderr
        path = root/'results'/f'disassembly-{tag}.txt'
        textfile(path, p.stdout)
        disassembly[tag] = {'argv': argv, 'path': path.relative_to(root).as_posix(), 'sha256': lab.digest(path)}
    lab.write(root/'results/frozen-plan.json', {'created': lab.now(), 'collector_source_id': source,
        'protocol': PROTOCOL, 'protocol_sha256': lab.digest(root/PROTOCOL), 'builds': builds,
        'study': design(root), 'disassembly': disassembly})
    lab.write(root/'results/preparation.json', {'created': lab.now(),
        'plan_sha256': lab.digest(root/'results/frozen-plan.json')})
    print(json.dumps({'prepared': str(root), 'source_id': source}), flush=True)


def load(root):
    p = read(root/'results/frozen-plan.json')
    assert lab.digest(root/'results/frozen-plan.json') == read(root/'results/preparation.json')['plan_sha256']
    source = root/'snapshots/source'/p['collector_source_id']
    assert lab.digest(source/PROTOCOL) == p['protocol_sha256']
    assert p['study'] == json.loads(json.dumps(design(source)))
    for item in p['disassembly'].values():
        assert lab.digest(root/item['path']) == item['sha256']
    return p


def run(root, wait_seconds):
    p = load(root)
    assert not list((root/'runs').glob('*')), 'no retry of a started batch'
    assert len(list((root/'results').glob('availability-*.json'))) < 2
    for b in p['builds'].values():
        assert lab.digest(pathlib.Path(b['exe'])) == b['binary_sha256']
    status, receipt = guard.availability(root, wait_seconds)
    if status != 'ready':
        return 3
    identifier = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())+'-V12-init-cost-'+uuid.uuid4().hex[:6]
    directory = root/'runs'/identifier
    directory.mkdir(parents=True)
    lab.write(directory/'plan.json', {**p['study'], 'builds': p['builds'],
        'availability_receipt': receipt.relative_to(root).as_posix(),
        'frozen_plan_sha256': lab.digest(root/'results/frozen-plan.json'), 'budget_seconds': 600})
    lab.write(directory/'environment.json', lab.environment(pathlib.Path(APP)))
    own, stop, samples, lock = guard.ancestors(), threading.Event(), [], threading.Lock()

    def check():
        with lock:
            sample = guard.observe(own)
            # Also recognize unrelated copies of this new probe; the historical
            # observer predates its name. Do not change that frozen observer.
            for line in sample.get('processes', '').splitlines()[1:]:
                parts = line.split(None, 3)
                if len(parts) == 4 and parts[2] == 'init_cost_probe' and int(parts[1]) != os.getpid():
                    sample['blockers'].append({'reason': 'external_init_cost_probe', 'row': line})
                    sample['clear'] = False
            samples.append(sample)
        return all(s['clear'] for s in samples)

    def monitor():
        while not stop.wait(.5):
            if not check(): break

    worker = threading.Thread(target=monitor, daemon=True)
    worker.start()
    started, records, state, reason = time.monotonic(), [], 'completed', None
    cases = {c['id']: c for c in p['study']['conditions']}
    try:
        for purpose, rep, cid in p['study']['order']:
            if not check(): raise RuntimeError('resource_contamination')
            c = cases[cid]
            b = p['builds'][c['build']]
            rid = f'{len(records):04d}-{purpose}-{cid}-r{rep}-{uuid.uuid4().hex[:6]}'
            rd = directory/rid
            rd.mkdir()
            lab.write(rd/'condition.json', c)
            if c['build'] == 'app':
                lab.write(rd/'config.json', c['config'])
                command = [b['exe'], '--config', str(rd/'config.json'), '--output', str(rd/'result.json')]
            else:
                command = [b['exe'], str(c['words']), str(c['seed']), c['allocation']]
            lab.write(rd/'command.json', {'argv': command, 'cwd': str(root), 'explicit_environment': {}})
            begin, stamp = time.monotonic(), lab.now()
            code, error, out, err = None, None, b'', b''
            try:
                remaining = 600-(time.monotonic()-started)
                if remaining <= 0: raise RuntimeError('budget_exhausted')
                process = subprocess.run(command, cwd=root, capture_output=True, timeout=min(90,remaining))
                code, out, err = process.returncode, process.stdout, process.stderr
                if code or err: raise RuntimeError('nonzero_exit_or_stderr')
                if c['build'] != 'app':
                    lab.write(rd/'result.json', json.loads(out))
                result = read(rd/'result.json')
                assert result['correctness']['pass'] if c['build'] == 'app' else result['pass']
            except subprocess.TimeoutExpired as exc:
                out, err, error = exc.stdout or b'', exc.stderr or b'', 'timeout'
            except Exception as exc:
                error = str(exc)
            with (rd/'stdout.log').open('xb') as f: f.write(out)
            with (rd/'stderr.log').open('xb') as f: f.write(err)
            row = {'run_id': rid, 'condition': cid, 'purpose': purpose, 'repeat': rep,
                   'binary_sha256': b['binary_sha256'], 'source_id': b['source_id'],
                   'collector_sha256': lab.digest(root/'tools/init_cost_study.py'),
                   'started': stamp, 'ended': lab.now(), 'elapsed_process_seconds': time.monotonic()-begin,
                   'exit_code': code, 'status': 'failed' if error else 'completed', 'failure_reason': error,
                   'included_in_performance_selection': False}
            lab.write(rd/'metadata.json', row)
            lab.seal(rd)
            records.append(row)
            print(json.dumps({'run': rid, 'status': row['status']}), flush=True)
            if error: raise RuntimeError(error)
            if not check(): raise RuntimeError('resource_contamination')
    except Exception as exc:
        reason = str(exc)
        state = 'contaminated' if reason == 'resource_contamination' else 'failed'
    finally:
        stop.set()
        worker.join(timeout=15)
        if worker.is_alive(): state, reason = 'failed', 'monitor_did_not_stop'
        lab.write(directory/'resource-observations.json', {'samples': samples, 'clean': all(s['clear'] for s in samples)})
        lab.write(directory/'records.json', records)
        lab.write(directory/'completion.json', {'status': state, 'reason': reason, 'processes': len(records),
            'elapsed_seconds': time.monotonic()-started, 'ended': lab.now()})
        lab.seal(directory)
    print(json.dumps({'batch': identifier, 'status': state, 'processes': len(records)}), flush=True)
    return 0 if state == 'completed' else 4


def audit(root):
    p = load(root)
    checked = 0
    for manifest in (root/'snapshots/source').glob('*/manifest.json'):
        m = read(manifest)
        assert hashlib.sha256(json.dumps(m['files'],sort_keys=True).encode()).hexdigest() == m['source_id'] == manifest.parent.name
        for rel, sha in m['files'].items():
            assert lab.digest(manifest.parent/rel) == sha
            checked += 1
    for manifest in list((root/'snapshots').glob('builds/*/checksums.json'))+list((root/'snapshots').glob('probes/*/checksums.json')):
        hashes = read(manifest)
        assert set(hashes) == {f.relative_to(manifest.parent).as_posix() for f in manifest.parent.rglob('*')
                              if f.is_file() and f.name != 'checksums.json'}
        for rel, sha in hashes.items():
            assert lab.digest(manifest.parent/rel) == sha
            checked += 1
    for tag in ('release','asan'):
        d = root/p['builds'][tag]['artifact']
        assert lab.digest(d/'init_cost_probe') == p['builds'][tag]['binary_sha256']
        assert read(d/'compile.json')['exit_code'] == 0 and not read(d/'compile.json')['stderr']
        assert read(d/'selftest-command.json')['exit_code'] == 0 and not (d/'selftest-stderr.log').read_bytes()
        check_selftest(read(d/'selftest-stdout.json'))
    assert lab.digest(root/p['builds']['app']['artifact']/'worksteal') == APP_SHA
    batches = list((root/'runs').iterdir())
    assert len(batches) == 1
    directory = batches[0]
    plan, rows, done = read(directory/'plan.json'), read(directory/'records.json'), read(directory/'completion.json')
    assert plan['frozen_plan_sha256'] == lab.digest(root/'results/frozen-plan.json')
    assert {k: plan[k] for k in p['study']} == p['study'] and plan['builds'] == p['builds']
    assert len(rows) == done['processes']
    assert [(r['purpose'],r['repeat'],r['condition']) for r in rows] == [tuple(s) for s in p['study']['order'][:len(rows)]]
    assert {d.name for d in directory.iterdir() if d.is_dir()} == {r['run_id'] for r in rows}
    for manifest in [directory/'checksums.json']+list(directory.glob('*/checksums.json')):
        hashes = read(manifest)
        assert set(hashes) == {f.relative_to(manifest.parent).as_posix() for f in manifest.parent.rglob('*')
                              if f.is_file() and f.name != 'checksums.json'}
        for rel, sha in hashes.items():
            assert lab.digest(manifest.parent/rel) == sha
            checked += 1
    cases = {c['id']: c for c in p['study']['conditions']}
    data_hashes, observations = {}, {}
    for row in rows:
        rd, c = directory/row['run_id'], cases[row['condition']]
        b = p['builds'][c['build']]
        assert read(rd/'metadata.json') == row and read(rd/'condition.json') == c
        assert row['binary_sha256'] == b['binary_sha256'] and row['source_id'] == b['source_id']
        assert row['collector_sha256'] == lab.digest(root/'snapshots/source'/p['collector_source_id']/'tools/init_cost_study.py')
        assert row['included_in_performance_selection'] is False
        cmd = read(rd/'command.json')
        original = pathlib.PurePosixPath(cmd['cwd'])/'runs'/directory.name/row['run_id']
        expected = [b['exe'], '--config', str(original/'config.json'), '--output', str(original/'result.json')] if c['build'] == 'app' else [b['exe'],str(c['words']),str(c['seed']),c['allocation']]
        assert cmd['argv'] == expected and not cmd['explicit_environment']
        if row['status'] != 'completed':
            assert done['status'] != 'completed'
            continue
        assert row['exit_code'] == 0 and not (rd/'stderr.log').read_bytes()
        r = read(rd/'result.json')
        if c['build'] == 'app':
            assert read(rd/'config.json') == c['config']
            resolved = copy.deepcopy(c['config']); resolved['steal_enabled'] = True
            assert r['resolved_config'] == resolved and r['correctness']['pass'] and len(r['epochs']) == 1
            e, n = r['epochs'][0], c['config']['workload']['elements']
            cc = e['correctness']
            assert cc['pass'] and cc['exact_once'] and cc['mismatches'] == 0 and cc['compared_elements'] == n
            assert cc['reference_workers_used'] == 4 and cc['reference_tile_elements'] == 1
            assert all(e['identity'][key] == value for key,value in oracle.identity(c['config']).items())
            cpus = c['config']['policies']['affinity']['cpus']
            assert r['affinity']['requested'] == cpus and r['affinity']['actual_workers'] == [[cpu] for cpu in cpus]
            data_hashes[c['seed']] = e['identity']['data_hash_fnv1a64']
        else:
            assert json.loads((rd/'stdout.log').read_bytes()) == r
            assert r['pass'] and not r['selftest'] and r['compared_words'] == r['words'] == c['words']
            assert r['seed'] == c['seed'] and r['allocation'] == c['allocation']
            assert r['data_hash_fnv1a64'] == data_hashes[c['seed']]
            assert set(r['phases']) == {'allocation','fill','fnv'}
            for key in ('seconds','minor_faults','major_faults'):
                assert all(stage[key] >= 0 for stage in r['phases'].values())
                assert abs(sum(stage[key] for stage in r['phases'].values())-r['combined'][key]) < 1e-8
            if row['purpose'] == 'profiling':
                observations[(c['seed'],c['allocation'],row['repeat'])] = {**r,
                    'run_path': rd.relative_to(root).as_posix()}
    resource = read(directory/'resource-observations.json')
    assert resource['samples'] and resource['clean'] == all(s['clear'] for s in resource['samples'])
    available = read(root/plan['availability_receipt'])
    assert available['status'] == 'ready' and all(s['clear'] for s in available['observations'][-3:])
    clean = done['status'] == 'completed' and resource['clean']
    summary = []
    if clean:
        assert len(rows) == 26 and len(observations) == 20
        for seed, n in INPUTS:
            for mode in ('zeroed','overwrite'):
                data = [observations[(seed,mode,rep)] for rep in range(1,6)]
                medians = {phase: {key: statistics.median(r['phases'][phase][key] for r in data)
                           for key in ('seconds','minor_faults','major_faults')} for phase in ('allocation','fill','fnv')}
                summary.append({'seed': seed, 'mib': n//2, 'allocation': mode, 'medians': medians,
                    'combined_median_seconds': statistics.median(r['combined']['seconds'] for r in data),
                    'allocation_plus_fill_median_seconds': statistics.median(r['phases']['allocation']['seconds']+r['phases']['fill']['seconds'] for r in data),
                    'fnv_fraction_median': statistics.median(r['phases']['fnv']['seconds']/r['combined']['seconds'] for r in data),
                    'samples': data})
    result = {'audit_pass': True, 'diagnostic_complete': clean, 'accepted': None,
              'scope': 'standalone diagnosis only; no acceptance decision', 'batch': directory.name,
              'processes': len(rows), 'profiling_samples': len(observations), 'hash_checks': checked,
              'resource_samples': len(resource['samples']), 'summary': summary, 'created': lab.now()}
    path = root/'results'/('audit-'+uuid.uuid4().hex+'.json')
    lab.write(path,result)
    print(json.dumps({'audit': str(path), 'complete': clean, 'hash_checks': checked}), flush=True)
    return result, path


def report(root):
    receipts = sorted((root/'results').glob('export-*.json'))
    assert receipts, 'export receipt required for Windows independent review'
    receipt = read(receipts[-1])
    for rel, sha in receipt['files'].items(): assert lab.digest(root/rel) == sha
    result, audit_path = audit(root)
    target = lab.ROOT/'report/init-cost'/('第十二轮初始化成本诊断报告-'+uuid.uuid4().hex[:8]+'.md')
    lines = ['# 第十二轮初始化成本诊断', '',
        '独立顺序探针；不作应用、窃取或候选采用结论。全部阶段保留原mix与完整逐字节FNV，末尾逐word核验。', '',
        f"批次`{result['batch']}`；{result['processes']}进程，{result['profiling_samples']}条profiling；audit_pass=true，diagnostic_complete={result['diagnostic_complete']}。", '',
        '|输入|分配|分配ms|填充ms|FNV ms|分配+填充ms（逐run求和）|全区间ms|FNV占比（逐run）|minor faults：分配/填充/FNV|',
        '|---|---|---:|---:|---:|---:|---:|---:|---|']
    for s in result['summary']:
        m = s['medians']
        lines.append(f"|seed{s['seed']}/{s['mib']}MiB|{s['allocation']}|{m['allocation']['seconds']*1000:.4f}|{m['fill']['seconds']*1000:.4f}|{m['fnv']['seconds']*1000:.4f}|{s['allocation_plus_fill_median_seconds']*1000:.4f}|{s['combined_median_seconds']*1000:.4f}|{s['fnv_fraction_median']*100:.2f}%|{m['allocation']['minor_faults']}/{m['fill']['minor_faults']}/{m['fnv']['minor_faults']}|")
    lines += ['', '各列分别取中位数；阶段中位数不可相加。noinline边界、rusage与独立进程状态会改变代码布局和页状态；不直接投射到生产应用。overwrite不是零成本获得数据，首次写入可能承担延迟页建立。无PMU证据，不据此断言缓存或带宽因果。', '',
        'Release与ASan/UBSan各36例自检，由Python逐word和FNV独立重算；大数组完整FNV与两次原应用控制一致。所有成功慢样本保留；本轮不改变第八轮推荐。', '',
        f"[Windows审计](../../init-cost/{audit_path.relative_to(root).as_posix()})；[冻结计划](../../init-cost/results/frozen-plan.json)；[批次记录](../../init-cost/runs/{result['batch']}/records.json)。", '', '## 全部诊断样本', '']
    for s in result['summary']:
        for row in s['samples']:
            lines.append(f"- [{row['run_path']}](../../init-cost/{row['run_path']}/result.json)：全区间{row['combined']['seconds']*1000:.4f}ms。")
    textfile(target, '\n'.join(lines)+'\n')
    print(json.dumps({'report': str(target), 'verified_export_files': len(receipt['files'])},ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare','run','audit','export','report'))
    parser.add_argument('--root', required=True)
    parser.add_argument('--target')
    parser.add_argument('--wait-seconds', type=int, default=600)
    args = parser.parse_args()
    root = pathlib.Path(args.root).resolve()
    if args.action == 'prepare': prepare(root)
    else:
        if args.action != 'report': lab.ROOT = root
        if args.action == 'run': return run(root,args.wait_seconds)
        if args.action == 'audit': audit(root)
        if args.action == 'export': lab.export(argparse.Namespace(target=args.target))
        if args.action == 'report': report(root)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
