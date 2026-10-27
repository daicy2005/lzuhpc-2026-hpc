#!/usr/bin/env python3
"""Observe app phases using separate, validated instrumentation builds."""
import argparse, collections, json, pathlib, statistics
import lab
from refine import OLD, condition

PHASES = {'configuration_and_policies', 'workload_initialization', 'partition_and_placement',
          'identity_hashes', 'pool_creation', 'output_and_counts_preparation', 'home_preread',
          'dispatch_and_execution_wall', 'full_reference_verification', 'result_summary', 'pool_shutdown'}
def read(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))

def run():
    root = lab.ROOT; versions = {}; cases = []; controls = []
    for k, (build, p, g) in OLD.items():
        for prefix in ('opt', 'phase'):
            name = prefix+'-'+build
            exe = root.parent/('ws-20261016-'+name)/'build-none/worksteal'
            validation = read(exe.parent/'validation.json')
            assert validation['pass'] and validation['binary_sha256'] == lab.digest(exe)
            versions[name] = {'exe': str(exe), 'binary_sha256': lab.digest(exe), 'source_id': validation['source_id'], 'validation': validation}
        c = condition(k, 'phase-'+build, p, g, seed=911)
        if k == 'memory': c['config']['workload']['elements'] = 64
        cases.append(c)
        ctrl = json.loads(json.dumps(c)); ctrl['id'] += '-control'; ctrl['build'] = 'opt-'+build; controls.append(ctrl)
    steps = [('control', 0, c) for c in controls] + [('warmup', 0, c) for c in cases]
    for rep in range(1, 4):
        rotated = cases[rep-1:]+cases[:rep-1]
        steps += [('profiling', rep, c) for c in rotated]
    plan = {'experiment': 'R3C-phase-observation', 'conditions': controls+cases, 'builds': versions,
            'order': [(purpose, rep, c['id']) for purpose, rep, c in steps],
            'scope': 'instrumented observations excluded from all performance selection',
            'protocol': 'docs/16-第三轮补充实验协议.md'}
    batch = lab.Batch('R3C-phase-observation', plan, pathlib.Path(versions['phase-runtime']['exe']), budget=180)
    try:
        for purpose, rep, c in steps:
            v = versions[c['build']]; batch.exe = pathlib.Path(v['exe']); batch.binary = v['binary_sha256']; batch.source = v['source_id']
            batch.run(c['config'], c['id'], purpose, rep, timeout=60)
        result = batch.finish()
    except Exception as e: batch.finish('failed', str(e)); raise
    analyze(result)

def analyze(directory):
    plan = read(directory/'plan.json'); done = read(directory/'completion.json'); records = read(directory/'records.json')
    assert done['status'] == 'completed' and len(records) == done['processes'] == 20
    assert [(r['purpose'], r['repeat'], r['condition']) for r in records] == [tuple(x) for x in plan['order']]
    assert len({r['run_id'] for r in records}) == len(records)
    assert {p.name for p in directory.iterdir() if p.is_dir()} == {r['run_id'] for r in records}
    hashes_checked = 0
    for manifest in [directory/'checksums.json']+list(directory.glob('*/checksums.json')):
        hashes = read(manifest)
        assert set(hashes) == {str(p.relative_to(manifest.parent)).replace('\\', '/') for p in manifest.parent.rglob('*') if p.is_file() and p.name != 'checksums.json'}
        for name, h in hashes.items(): assert lab.digest(manifest.parent/name) == h; hashes_checked += 1
    conditions = {c['id']: c for c in plan['conditions']}; signatures = collections.defaultdict(set); observed = collections.defaultdict(list)
    for r in records:
        d = directory/r['run_id']; c = conditions[r['condition']]; b = plan['builds'][c['build']]; result = read(d/'result.json')
        assert read(d/'metadata.json') == r and read(d/'config.json') == c['config']
        assert r['binary_sha256'] == b['binary_sha256'] and r['source_id'] == b['source_id'] and b['validation']['pass']
        assert read(d/'command.txt')['argv'][0] == b['exe'] and r['status'] == 'completed' and not r['included']
        assert r['timing'] == result['timing'] and result['correctness']['pass'] and len(result['epochs']) == 1
        expected = json.loads(json.dumps(c['config'])); expected['steal_enabled'] = True
        assert result['resolved_config'] == expected
        epoch = result['epochs'][0]; assert epoch['correctness']['pass']
        signatures[c['kind']].add((json.dumps(epoch['identity'], sort_keys=True), epoch['correctness']['output_hash_fnv1a64']))
        if r['purpose'] != 'control':
            ph = result['phase_seconds']; total = result['timing']['end_to_end_seconds']
            assert set(ph) == PHASES and all(v >= 0 for v in ph.values())
            assert sum(ph.values()) <= total+1e-9
            assert ph['dispatch_and_execution_wall']+1e-9 >= epoch['epoch_seconds']
        if r['purpose'] == 'profiling': observed[c['kind']].append({'path': str(d.relative_to(lab.ROOT)), 'repeat': r['repeat'], 'phase_seconds': ph, 'end_to_end_seconds': total, 'epoch_seconds': epoch['epoch_seconds']})
    assert all(len(v) == 1 for v in signatures.values())
    summary = {}
    for k, rows in observed.items():
        assert sorted(r['repeat'] for r in rows) == [1, 2, 3]
        summary[k] = {'samples': rows, 'phase_medians': {p: statistics.median(r['phase_seconds'][p] for r in rows) for p in sorted(PHASES)},
                      'app_median': statistics.median(r['end_to_end_seconds'] for r in rows),
                      'epoch_median': statistics.median(r['epoch_seconds'] for r in rows),
                      'verification_fraction_median': statistics.median(r['phase_seconds']['full_reference_verification']/r['end_to_end_seconds'] for r in rows)}
    lab.write(lab.ROOT/'results/phase-summary.json', {'pass': True, 'batch': str(directory.relative_to(lab.ROOT)), 'processes': 20,
              'profiling_samples': 12, 'hash_checks': hashes_checked, 'groups': summary,
              'scope': 'observations only; not formal performance samples or causal decomposition'})
    print(json.dumps({'phase_summary': summary}, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); a = ap.parse_args(); lab.ROOT = pathlib.Path(a.root).resolve(); run()
