#!/usr/bin/env python3
"""Round-three bounded search; reuse frozen binaries, compare with current best."""
import argparse, collections, copy, json, pathlib, random, shutil, statistics, subprocess, sys
import lab
import optimize

KINDS = ('light', 'uniform', 'skewed')
OLD = {'light': ('runtime', 16, 256), 'uniform': ('lanes8', 32, 1024),
       'skewed': ('full_lanes8', 32, 256), 'memory': ('full_lanes8', 16, 4)}

def read(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))
def condition(kind, build, p, g, seed=811, n=262144, suffix=''):
    c = optimize.case(kind, p, g, seed, n)
    return {'id': f'{kind}-{build}-p{p}-g{g}{suffix}', 'kind': kind, 'build': build, 'config': c}

def prepare(destination):
    original = lab.ROOT
    destination.mkdir(parents=True, exist_ok=False)
    for f in lab.source_files():
        dst = destination/f.relative_to(original)
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, dst)
    lab.write(destination/'prior-summary.json', read(original/'optimization/results/optimization-summary.json'))
    lab.ROOT = destination; optimize.ROOT = destination

def preflight():
    versions = optimize.builds(); checks = {}
    for name in sorted({v[0] for v in OLD.values()}):
        exe = pathlib.Path(versions[name]['exe']); records = []
        for cmd in ([str(exe.parent/'runtime_checks')],
                    [sys.executable, str(lab.ROOT/'tests/cli_checks.py'), str(exe), str(exe.parent/'worksteal_extension')]):
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            records.append({'argv': cmd, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
            if p.returncode: raise RuntimeError(records)
        checks[name] = {'binary_sha256': lab.digest(exe), 'records': records}
    lab.write(lab.ROOT/'results/preflight.json', checks)

def ordered(cases):
    ids = list(range(len(cases))); random.Random(2026101603).shuffle(ids)
    result = [('warmup', 0, cases[i]) for i in ids]
    for rep in range(1, 4):
        shift = (rep-1)*len(ids)//3
        result += [('timing', rep, cases[i]) for i in ids[shift:]+ids[:shift]]
    return result

def screen():
    cs = [condition('light', b, 16, g) for b in ('runtime', 'lanes8', 'full_lanes8')
          for g in (256, 512, 1024, 4096)]
    for kind, grains in (('uniform', (1024, 2048, 4096, 8192)), ('skewed', (256, 512, 1024, 2048))):
        cs += [condition(kind, OLD[kind][0], p, g) for p in (16, 24, 32) for g in grains]
    return optimize.run('R3A-joint-screen', cs, ordered(cs), {
        'protocol': 'docs/16-第三轮补充实验协议.md', 'screen_seed': 811,
        'selection': 'minimum median per class, condition id tie break',
        'heldout_inputs': [[601, 229376], [3001, 360448]], 'current_recommendations': OLD,
        'gate': 'both inputs >=4/5 paired wins and median <=0.95 current recommendation'})

def candidates(screen_path):
    med = optimize.medians(screen_path); plan = read(screen_path/'plan.json')
    return {k: min((c for c in plan['conditions'] if c['kind'] == k), key=lambda c: (med[c['id']], c['id'])) for k in KINDS}

def confirm(screen_path):
    selected = candidates(screen_path); cs = []; pairs = []
    for k, winner in selected.items():
        b, p, g = OLD[k]
        if winner['build'] == b and winner['config'] == condition(k, b, p, g)['config']: continue
        for seed, n in ((601, 229376), (3001, 360448)):
            base = condition(k, b, p, g, seed, n, f'-s{seed}-base')
            cfg = winner['config']
            cand = condition(k, winner['build'], cfg['workers'], cfg['policies']['partition']['grain'], seed, n, f'-s{seed}-candidate')
            cs.extend((base, cand)); pairs.append((base, cand))
    if not cs: return None
    steps = [('warmup', 0, c) for c in cs]
    for rep in range(1, 6):
        for pair in pairs: steps += [('timing', rep, c) for c in (pair if rep % 2 else pair[::-1])]
    return optimize.run('R3B-heldout', cs, steps, {'selected': selected, 'screen_path': str(screen_path),
        'gate': 'both inputs >=4/5 paired wins and median <=0.95 current recommendation',
        'no_adaptation': True, 'current_recommendations': OLD})

def analyze(root):
    groups = {}; batches = {}; hash_checks = 0; processes = 0; samples = 0
    all_records = []; signatures = {}; all_ids = set()
    for directory in sorted((root/'runs').iterdir()):
        plan = read(directory/'plan.json'); done = read(directory/'completion.json'); rr = read(directory/'records.json')
        assert done['status'] == 'completed' and done['processes'] == len(rr)
        assert [(r['purpose'], r['repeat'], r['condition']) for r in rr] == [tuple(x) for x in plan['order']]
        assert len({tuple(x) for x in plan['order']}) == len(rr)
        assert {p.name for p in directory.iterdir() if p.is_dir()} == {r['run_id'] for r in rr}
        cs = {c['id']: c for c in plan['conditions']}; assert len(cs) == len(plan['conditions'])
        for manifest in [directory/'checksums.json'] + list(directory.glob('*/checksums.json')):
            hashes = read(manifest)
            assert set(hashes) == {str(p.relative_to(manifest.parent)).replace('\\', '/') for p in manifest.parent.rglob('*') if p.is_file() and p.name != 'checksums.json'}
            for rel, h in hashes.items(): assert lab.digest(manifest.parent/rel) == h; hash_checks += 1
        work = collections.defaultdict(set); timing = collections.defaultdict(list)
        for r in rr:
            assert r['run_id'] not in all_ids; all_ids.add(r['run_id'])
            d = directory/r['run_id']; c = cs[r['condition']]; b = plan['builds'][c['build']]
            assert r == read(d/'metadata.json') and read(d/'config.json') == c['config']
            assert r['status'] == 'completed' and r['included'] == (r['purpose'] == 'timing')
            assert r['binary_sha256'] == b['binary_sha256'] and r['source_id'] == b['source_id']
            assert b['validation']['pass'] and read(d/'command.txt')['argv'][0] == b['exe']
            result = read(d/'result.json'); assert result['correctness']['pass'] and result['timing'] == r['timing']
            cfg = copy.deepcopy(c['config']); cfg['steal_enabled'] = True
            assert result['resolved_config'] == cfg and len(result['epochs']) == 1
            e = result['epochs'][0]; assert e['correctness']['pass']
            i = e['identity']; output = e['correctness']['output_hash_fnv1a64']
            sig = (json.dumps(i, sort_keys=True), output); key = (plan['experiment'], c['id'])
            assert key not in signatures or signatures[key] == sig; signatures[key] = sig
            work[(c['kind'], c['config']['workload']['seed'])].add((i['input_hash_fnv1a64'], i['cost_hash_fnv1a64'], i['data_hash_fnv1a64'], i['total_cost_units'], output))
            # Exact same partition/worker configurations also retain task/queue identities across builds.
            work[('partition', c['kind'], c['config']['workload']['seed'], c['config']['workers'], c['config']['policies']['partition']['grain'])].add(sig)
            if r['included']: timing[c['id']].append(r)
            all_records.append({'path': str(d.relative_to(root)), **r})
        assert all(len(v) == 1 for v in work.values()) and set(timing) == set(cs)
        repeats = 3 if plan['experiment'] == 'R3A-joint-screen' else 5
        gg = {}
        for cid, rows in timing.items():
            assert sorted(r['repeat'] for r in rows) == list(range(1, repeats+1))
            gg[cid] = {**cs[cid], 'epoch_median': statistics.median(r['timing']['epoch_seconds'] for r in rows),
                       'app_median': statistics.median(r['timing']['end_to_end_seconds'] for r in rows),
                       'epoch_values': [r['timing']['epoch_seconds'] for r in rows],
                       'app_values': [r['timing']['end_to_end_seconds'] for r in rows],
                       'run_paths': [str((directory/r['run_id']).relative_to(root)) for r in rows]}
        stage = plan['experiment']; assert stage not in batches
        batches[stage] = {'path': str(directory.relative_to(root)), 'plan': plan, 'completion': done}
        groups[stage] = gg; processes += len(rr); samples += sum(len(v) for v in timing.values())
    screen_batch = root/batches['R3A-joint-screen']['path']; selected = candidates(screen_batch)
    assert len(groups['R3A-joint-screen']) == 36
    selection = {}
    for k, c in selected.items():
        b, p, g = OLD[k]; anchor = condition(k, b, p, g); heldout = []
        unchanged = c['build'] == b and c['config'] == anchor['config']
        if not unchanged:
            batch = batches['R3B-heldout']; assert batch['plan']['selected'][k] == c
            rows = read(root/batch['path']/'records.json')
            lookup = {(r['condition'], r['repeat']): r for r in rows if r['included']}
            for seed, n in ((601, 229376), (3001, 360448)):
                base = condition(k, b, p, g, seed, n, f'-s{seed}-base')
                cfg = c['config']; cand = condition(k, c['build'], cfg['workers'], cfg['policies']['partition']['grain'], seed, n, f'-s{seed}-candidate')
                base_g = groups['R3B-heldout'][base['id']]; cand_g = groups['R3B-heldout'][cand['id']]
                assert all(base_g[x] == base[x] and cand_g[x] == cand[x] for x in ('build','config','kind'))
                pairs = [{'repeat': rep, 'base': lookup[(base['id'], rep)]['timing']['epoch_seconds'], 'candidate': lookup[(cand['id'], rep)]['timing']['epoch_seconds']} for rep in range(1, 6)]
                wins = sum(x['candidate'] < x['base'] for x in pairs)
                heldout.append({'seed': seed, 'wins': wins, 'speedup': base_g['epoch_median']/cand_g['epoch_median'],
                    'app_speedup': base_g['app_median']/cand_g['app_median'], 'base': base_g, 'candidate': cand_g, 'pairs': pairs,
                    'accepted': wins >= 4 and cand_g['epoch_median'] <= .95*base_g['epoch_median']})
        accepted = not unchanged and all(h['accepted'] for h in heldout)
        winner = c if accepted else anchor
        selection[k] = {'accepted': accepted, 'unchanged_in_screen': unchanged, 'screen_winner': c, 'heldout': heldout, 'recommendation': winner}
    summary = {'complete': True, 'batches': batches, 'groups': groups, 'selection': selection,
               'processes': processes, 'timing_samples': samples, 'hash_checks': hash_checks,
               'limitations': ['finite local search', 'WSL1 logical masks only', 'engineering gate is not significance test', 'old binary source differs from collector snapshot']}
    # Derived results are regenerated; raw process directories are never rewritten.
    (root/'results').mkdir(exist_ok=True)
    (root/'results/refinement-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (root/'results/runs.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in all_records), encoding='utf-8')
    print(json.dumps({'processes': processes, 'timing_samples': samples, 'hash_checks': hash_checks,
                      'selection': {k: {'accepted': v['accepted'], 'winner': v['recommendation']['id'], 'ratios': [h['speedup'] for h in v['heldout']]} for k, v in selection.items()}}), flush=True)
    return summary

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('action', choices=('run', 'analyze', 'export')); ap.add_argument('--root', required=True); ap.add_argument('--target'); a = ap.parse_args()
    root = pathlib.Path(a.root).resolve()
    if a.action == 'run':
        prepare(root); preflight(); path = screen(); confirm(path); analyze(root)
    else:
        lab.ROOT = root; optimize.ROOT = root
        if a.action == 'analyze': analyze(root)
        else: lab.export(argparse.Namespace(target=a.target))

if __name__ == '__main__': main()
