#!/usr/bin/env python3
"""Frozen app-level reference-verification study with fresh paired holdouts."""
import argparse, collections, copy, json, pathlib, random, shutil, statistics, sys
import lab
from analyze_opt import stats

KINDS = ('light', 'uniform', 'skewed', 'memory')
def read(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))
def versions():
    result = {}
    for prefix in ('opt', 'verify'):
        for name in ('lanes8', 'full_lanes8'):
            exe = lab.ROOT.parent/('ws-20261016-'+prefix+'-'+name)/'build-none/worksteal'
            v = read(exe.parent/'validation.json')
            assert v['pass'] and v['binary_sha256'] == lab.digest(exe)
            result[prefix+'-'+name] = {'exe': str(exe), 'source_id': v['source_id'], 'binary_sha256': v['binary_sha256'], 'validation': v}
    for name in ('asan', 'tsan'):
        directory = lab.ROOT.parent/('ws-20261016-verify-'+name)/('build-'+name)
        v = read(directory/'validation.json'); assert v['pass'] and v['binary_sha256'] == lab.digest(directory/'worksteal')
        result[name] = {'exe': str(directory/'worksteal'), 'source_id': v['source_id'], 'binary_sha256': v['binary_sha256'], 'validation': v}
    return result

def case(kind, ref, seed=1237, n=262144, old=False, suffix=''):
    info = read(lab.ROOT/'configs/refined/builds.json')[kind]
    c = read(lab.ROOT/info['config']); c['workload']['seed'] = seed; c['layout_seed'] = seed
    c['workload']['elements'] = ({1237:64,1709:48,4001:96}[seed] if kind == 'memory' else n)
    if not old: c['measurement']['reference_workers'] = ref
    return {'id': f'{kind}-ref{ref}{suffix}', 'kind': kind, 'build': ('opt-' if old else 'verify-')+info['build'], 'config': c}

def run_batch(stage, cases, steps, extra):
    builds = versions(); exe = pathlib.Path(builds['verify-full_lanes8']['exe'])
    plan = {'experiment': stage, 'builds': builds, 'conditions': cases,
            'order': [(p, r, c['id']) for p, r, c in steps], 'metric': 'end_to_end_seconds',
            'protocol': 'docs/18-第四轮并行核验协议.md', **extra}
    batch = lab.Batch(stage, plan, exe, budget=600)
    try:
        for purpose, repeat, c in steps:
            b = builds[c['build']]; batch.exe = pathlib.Path(b['exe']); batch.source = b['source_id']; batch.binary = b['binary_sha256']
            batch.run(c['config'], c['id'], purpose, repeat, timeout=90)
        path = batch.finish()
    except Exception as e: batch.finish('failed', str(e)); raise
    print(json.dumps({'completed': stage, 'path': str(path)}), flush=True); return path

def screen():
    cases = [case(k, ref) for k in KINDS for ref in (1,4,8,16,32)]
    controls = [case(k, 1, old=True, suffix='-old-control') for k in KINDS]
    indexes = list(range(len(cases))); random.Random(2026101604).shuffle(indexes)
    steps = [('control',0,c) for c in controls]+[('warmup',0,cases[i]) for i in indexes]
    for rep in range(1,4):
        offset = (rep-1)*len(indexes)//3
        steps += [('timing',rep,cases[i]) for i in indexes[offset:]+indexes[:offset]]
    return run_batch('V4A-reference-screen', controls+cases, steps,
                     {'heldout_inputs': [[1709,196608],[4001,393216]], 'selection': 'minimum app median by kind; id tie break'})

def winners(path):
    plan = read(path/'plan.json'); rows = read(path/'records.json'); timing = collections.defaultdict(list)
    assert read(path/'completion.json')['status'] == 'completed'
    for r in rows:
        if r['included']: timing[r['condition']].append(r['timing']['end_to_end_seconds'])
    assert all(len(v) == 3 for v in timing.values())
    return {k: min((c for c in plan['conditions'] if c['kind'] == k and c['id'] in timing),
                   key=lambda c:(statistics.median(timing[c['id']]),c['id'])) for k in KINDS}

def confirm(path):
    selected = winners(path); cases = []; pairs = []
    for kind, chosen in selected.items():
        ref = chosen['config']['measurement']['reference_workers']
        if ref == 1: continue
        for seed, n in ((1709,196608),(4001,393216)):
            pair = (case(kind,1,seed,n,suffix=f'-s{seed}-base'), case(kind,ref,seed,n,suffix=f'-s{seed}-candidate'))
            cases.extend(pair); pairs.append(pair)
    if not cases: return
    steps = [('warmup',0,c) for c in cases]
    for rep in range(1,6):
        for pair in pairs: steps += [('timing',rep,c) for c in (pair if rep%2 else pair[::-1])]
    run_batch('V4B-heldout', cases, steps, {'selected': selected, 'screen_path': str(path),
              'gate': 'both inputs app >=4/5 paired wins and candidate app median <=0.95 baseline', 'no_adaptation': True})

def analyze(root):
    batches = {}; groups = {}; rows_all = []; identities = collections.defaultdict(set); checked = 0; ids = set()
    for directory in sorted((root/'runs').iterdir()):
        plan = read(directory/'plan.json'); done = read(directory/'completion.json'); rows = read(directory/'records.json')
        assert done['status'] == 'completed' and done['processes'] == len(rows)
        assert [(r['purpose'],r['repeat'],r['condition']) for r in rows] == [tuple(x) for x in plan['order']]
        assert len({tuple(x) for x in plan['order']}) == len(rows)
        assert {p.name for p in directory.iterdir() if p.is_dir()} == {r['run_id'] for r in rows}
        for manifest in [directory/'checksums.json']+list(directory.glob('*/checksums.json')):
            m = read(manifest)
            assert set(m) == {str(p.relative_to(manifest.parent)).replace('\\','/') for p in manifest.parent.rglob('*') if p.is_file() and p.name != 'checksums.json'}
            for rel,h in m.items(): assert lab.digest(manifest.parent/rel) == h; checked += 1
        cs = {c['id']:c for c in plan['conditions']}; assert len(cs) == len(plan['conditions'])
        timing = collections.defaultdict(list)
        for r in rows:
            assert r['run_id'] not in ids; ids.add(r['run_id'])
            d = directory/r['run_id']; c = cs[r['condition']]; b = plan['builds'][c['build']]
            assert read(d/'metadata.json') == r and read(d/'config.json') == c['config']
            assert r['status'] == 'completed' and r['included'] == (r['purpose'] == 'timing')
            assert r['source_id'] == b['source_id'] and r['binary_sha256'] == b['binary_sha256'] and b['validation']['pass']
            assert read(d/'command.txt')['argv'][0] == b['exe']
            result = read(d/'result.json'); assert result['correctness']['pass'] and result['timing'] == r['timing']
            expected = copy.deepcopy(c['config']); expected['steal_enabled'] = True
            assert result['resolved_config'] == expected and len(result['epochs']) == 1
            e = result['epochs'][0]; correctness = e['correctness']; n = c['config']['workload']['elements']
            assert correctness['pass'] and correctness['compared_elements'] == n and correctness['mismatches'] == 0
            identities[(c['kind'],c['config']['workload']['seed'])].add((json.dumps(e['identity'],sort_keys=True),correctness['output_hash_fnv1a64']))
            if r['purpose'] != 'control':
                tile = 1 if c['kind'] == 'memory' else 256; ref = c['config']['measurement']['reference_workers']
                assert correctness['reference_workers_used'] == min(ref,(n+tile-1)//tile)
                assert correctness['reference_tile_elements'] == tile
                assert all(v >= 0 for v in result['phase_seconds'].values())
                assert sum(result['phase_seconds'].values()) <= result['timing']['end_to_end_seconds']+1e-9
            item = {'path':str(d.relative_to(root)),**r}
            if r['included']:
                item['reference_seconds'] = result['phase_seconds']['full_reference_verification']; timing[c['id']].append(item)
            rows_all.append(item)
        stage = plan['experiment']; assert stage not in batches; gg = {}
        repeats = 3 if stage == 'V4A-reference-screen' else 5
        for cid, rr in timing.items():
            assert sorted(r['repeat'] for r in rr) == list(range(1,repeats+1))
            gg[cid] = {**cs[cid], 'app':stats([r['timing']['end_to_end_seconds'] for r in rr]),
                       'epoch':stats([r['timing']['epoch_seconds'] for r in rr]), 'reference':stats([r['reference_seconds'] for r in rr]),
                       'process':stats([r['elapsed_process_seconds'] for r in rr]), 'run_paths':[r['path'] for r in rr]}
        groups[stage] = gg; batches[stage] = {'path':str(directory.relative_to(root)), 'plan':plan,'completion':done}
    assert all(len(v) == 1 for v in identities.values())
    screen_path = root/batches['V4A-reference-screen']['path']; selected = winners(screen_path); selection = {}
    assert len(groups['V4A-reference-screen']) == 20
    for k in KINDS:
        assert {c['config']['measurement']['reference_workers'] for c in groups['V4A-reference-screen'].values() if c['kind'] == k} == {1,4,8,16,32}
        c = selected[k]; ref = c['config']['measurement']['reference_workers']; heldout = []
        if ref != 1:
            batch = batches['V4B-heldout']; assert batch['plan']['selected'][k] == c
            lookup = {(r['condition'],r['repeat']):r for r in read(root/batch['path']/'records.json') if r['included']}
            for seed,n in ((1709,196608),(4001,393216)):
                base_c = case(k,1,seed,n,suffix=f'-s{seed}-base'); new_c = case(k,ref,seed,n,suffix=f'-s{seed}-candidate')
                bg = groups['V4B-heldout'][base_c['id']]; cg = groups['V4B-heldout'][new_c['id']]
                assert all(bg[x] == base_c[x] and cg[x] == new_c[x] for x in ('kind','build','config'))
                pairs = [{'repeat':rep,'base':lookup[(base_c['id'],rep)]['timing']['end_to_end_seconds'],
                          'candidate':lookup[(new_c['id'],rep)]['timing']['end_to_end_seconds']} for rep in range(1,6)]
                wins = sum(p['candidate'] < p['base'] for p in pairs)
                heldout.append({'seed':seed,'base':bg,'candidate':cg,'pairs':pairs,'wins':wins,
                    'app_speedup':bg['app']['median']/cg['app']['median'],
                    'reference_speedup':bg['reference']['median']/cg['reference']['median'],
                    'accepted':wins >= 4 and cg['app']['median'] <= .95*bg['app']['median']})
        accepted = ref != 1 and all(h['accepted'] for h in heldout)
        selection[k] = {'accepted':accepted,'screen_winner':c,'heldout':heldout,'reference_workers':ref if accepted else 1}
    result = {'complete':True,'metric':'application end_to_end_seconds','batches':batches,'groups':groups,'selection':selection,
              'processes':len(rows_all),'timing_samples':sum(r['included'] for r in rows_all),'hash_checks':checked,
              'limits':['bounded local search','WSL1 logical masks only','verification improvement is not work-stealing epoch speedup','gate is not statistical significance']}
    (root/'results').mkdir(exist_ok=True)
    (root/'results/verification-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (root/'results/runs.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows_all),encoding='utf-8')
    print(json.dumps({'processes':result['processes'],'timing_samples':result['timing_samples'],'selection':{k:{'accepted':v['accepted'],'workers':v['reference_workers'],'speedups':[h['app_speedup'] for h in v['heldout']]} for k,v in selection.items()}}),flush=True)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('action',choices=('run','analyze','export')); ap.add_argument('--root',required=True); ap.add_argument('--target'); a = ap.parse_args(); root = pathlib.Path(a.root).resolve()
    if a.action == 'run':
        origin = lab.ROOT; root.mkdir(parents=True,exist_ok=False)
        for f in lab.source_files():
            d = root/f.relative_to(origin); d.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(f,d)
        lab.ROOT = root; versions(); path = screen(); confirm(path); analyze(root)
    else:
        lab.ROOT = root
        if a.action == 'analyze': analyze(root)
        else: lab.export(argparse.Namespace(target=a.target))

if __name__ == '__main__': main()
