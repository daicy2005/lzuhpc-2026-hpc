#!/usr/bin/env python3
"""Audit cross-build optimization experiments and materialize held-out decisions."""
import argparse, collections, hashlib, json, math, pathlib, statistics

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,j):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def stats(v):
    v=sorted(v)
    def q(t):
        x=(len(v)-1)*t;lo=math.floor(x);hi=math.ceil(x);return v[lo]+(v[hi]-v[lo])*(x-lo)
    return {'n':len(v),'median':statistics.median(v),'min':min(v),'max':max(v),'iqr':q(.75)-q(.25),'values':v}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);a=ap.parse_args();root=pathlib.Path(a.root).resolve();lab=root/'optimization'
    batches={};groups=[];records_all=[];hash_checks=0;by_key={};all_records={}
    for directory in sorted((lab/'runs').iterdir()):
        if not (directory/'completion.json').exists():continue
        plan=read(directory/'plan.json');done=read(directory/'completion.json');records=read(directory/'records.json')
        assert done['status']=='completed' and len(records)==done['processes']
        assert len(records)==len({r['run_id'] for r in records})
        assert [(r['purpose'],r['repeat'],r['condition']) for r in records]==[tuple(x) for x in plan['order']]
        assert len({tuple(x) for x in plan['order']})==len(records)
        assert {p.name for p in directory.iterdir() if p.is_dir()}=={r['run_id'] for r in records}
        assert len({c['id'] for c in plan['conditions']})==len(plan['conditions'])
        for manifest in [directory/'checksums.json']+list(directory.glob('*/checksums.json')):
            m=read(manifest)
            expected={str(p.relative_to(manifest.parent)).replace('\\','/') for p in manifest.parent.rglob('*') if p.is_file() and p.name!='checksums.json'}
            assert set(m)==expected
            for rel,h in m.items():assert sha(manifest.parent/rel)==h;hash_checks+=1
        conditions={c['id']:c for c in plan['conditions']};samples=collections.defaultdict(list);signatures={};results={}
        for r in records:
            d=directory/r['run_id'];c=conditions[r['condition']];build=plan['builds'][c['build']]
            assert read(d/'metadata.json')==r and read(d/'config.json')==c['config']
            assert r['status']=='completed' and r['included']==(r['purpose']=='timing')
            assert r['binary_sha256']==build['binary_sha256'] and r['source_id']==build['source_id']
            assert read(d/'command.txt')['argv'][0]==build['exe']
            assert build['validation']['pass']
            res=read(d/'result.json');assert res['correctness']['pass']
            assert all(e['correctness']['pass'] for e in res['epochs'])
            assert r['timing']==res['timing']
            sig={'config':res['resolved_config'],'identity':res['epochs'][0]['identity'],
                 'output':[e['correctness']['output_hash_fnv1a64'] for e in res['epochs']]}
            if r['condition'] in signatures:assert signatures[r['condition']]==sig
            signatures[r['condition']]=sig;results[r['condition']]=res
            if r['purpose']=='timing':samples[r['condition']].append(r)
            records_all.append({'path':str(d.relative_to(root)),**r})
        stage=plan['experiment'];assert stage not in batches
        repeats=5 if stage=='OPT3-heldout' else 3
        assert set(samples)==set(conditions)
        for cid,rr in samples.items():
            assert sorted(r['repeat'] for r in rr)==list(range(1,repeats+1))
            c=conditions[cid];res=results[cid];group={'stage':stage,**c,'binary_sha256':plan['builds'][c['build']]['binary_sha256'],
                'identity':res['epochs'][0]['identity'],'output_hash':res['epochs'][0]['correctness']['output_hash_fnv1a64'],
                'epoch_seconds':stats([r['timing']['epoch_seconds'] for r in rr]),
                'end_to_end_seconds':stats([r['timing']['end_to_end_seconds'] for r in rr]),
                'run_paths':[str((directory/r['run_id']).relative_to(root)) for r in rr]}
            groups.append(group);by_key[(stage,cid)]=group
        # Same mathematical work across variants, threads and grain, within each input.
        identities=collections.defaultdict(set)
        for cid,sig in signatures.items():
            c=conditions[cid];key=(c['kind'],c['config']['workload']['seed']);i=sig['identity']
            identities[key].add((i['input_hash_fnv1a64'],i['cost_hash_fnv1a64'],i['data_hash_fnv1a64'],i['total_cost_units'],tuple(sig['output'])))
        assert all(len(s)==1 for s in identities.values())
        if stage=='OPT1-build-screen':
            for kind in ('light','uniform','skewed','memory'):
                assert len({json.dumps(g['identity'],sort_keys=True) for g in groups if g['stage']==stage and g['kind']==kind})==1
        batches[stage]={'path':str(directory.relative_to(root)),'plan':plan,'completion':done,'pass':True};all_records[stage]=records
    expected_counts={'OPT1-build-screen':40,'OPT2-parameter-screen':90,'OPT3-heldout':16}
    for name,b in batches.items():assert len(b['plan']['conditions'])==expected_counts[name]
    winners={}
    for stage_name in ('OPT1-build-screen','OPT2-parameter-screen'):
        if stage_name not in batches:continue
        winners[stage_name]={}
        for kind in ('light','uniform','skewed','memory'):
            eligible=[g for g in groups if g['stage']==stage_name and g['kind']==kind]
            winners[stage_name][kind]=min(eligible,key=lambda g:(g['epoch_seconds']['median'],g['id']))
    if 'OPT2-parameter-screen' in batches:
        b=batches['OPT2-parameter-screen']
        for kind in ('light','uniform','skewed','memory'):
            winner=winners['OPT1-build-screen'][kind]
            assert b['plan']['selected_builds'][kind]['id']==winner['id']
            cs=[c for c in b['plan']['conditions'] if c['kind']==kind]
            grains=(1,16,64,256) if kind=='light' else (1,2,4) if kind=='memory' else (16,64,256,1024)
            assert {(c['config']['workers'],c['config']['policies']['partition']['grain']) for c in cs}=={(p,g) for p in (1,2,4,8,16,32) for g in grains}
            assert all(c['build']==winner['build'] for c in cs)
    selected={};stage='OPT3-heldout'
    if stage in batches:
        b=batches[stage];rr={(r['condition'],r['repeat']):r for r in all_records[stage] if r['purpose']=='timing'}
        for kind in ('light','uniform','skewed','memory'):
            assert b['plan']['selected'][kind]['id']==winners['OPT2-parameter-screen'][kind]['id']
            heldout=[]
            for seed in (137,2027):
                prefix=f'{kind}-s{seed}';base=by_key[(stage,prefix+'-base')];cand=by_key[(stage,prefix+'-candidate')]
                screen=b['plan']['selected'][kind];expected=copy_config(screen['config'])
                expected['workload']['seed']=seed;expected['layout_seed']=seed;expected['workload']['elements']=(48 if seed==137 else 80) if kind=='memory' else (196608 if seed==137 else 327680)
                assert cand['config']==expected and cand['build']==screen['build']
                assert base['build']=='baseline' and base['config']['workers']==4
                assert base['config']['policies']['partition']['grain']==(1 if kind in ('memory','light') else 64)
                pairs=[{'repeat':r,'base':rr[(prefix+'-base',r)]['timing']['epoch_seconds'],
                        'candidate':rr[(prefix+'-candidate',r)]['timing']['epoch_seconds']} for r in range(1,6)]
                wins=sum(p['candidate']<p['base'] for p in pairs);ratio=base['epoch_seconds']['median']/cand['epoch_seconds']['median']
                heldout.append({'seed':seed,'wins':wins,'base_over_candidate':ratio,'accepted':wins>=4 and cand['epoch_seconds']['median']<=.95*base['epoch_seconds']['median'],
                    'base':base,'candidate':cand,'pairs':pairs})
            accepted=all(c['accepted'] for c in heldout)
            screen=b['plan']['selected'][kind];source=screen if accepted else {'build':'baseline','config':heldout[0]['base']['config']}
            c=copy_config(source['config']);c['workload']['seed']=42;c['layout_seed']=42;c['workload']['elements']=64 if kind=='memory' else 262144
            selected[kind]={'accepted':accepted,'build':source['build'],'config':c,'heldout':heldout,'screening_candidate':screen}
            save(root/'configs/optimized'/f'{kind}.json',c)
    complete=set(batches)=={'OPT1-build-screen','OPT2-parameter-screen','OPT3-heldout'}
    summary={'complete':complete,'batches':batches,'groups':groups,'selection':selected,'hash_checks':hash_checks,
        'processes':len(records_all),'timing_samples':sum(g['epoch_seconds']['n'] for g in groups),
        'limits':['finite screening; no global optimum proof','WSL1 physical residency unproven','cross-build implementation gains differ from scheduling strategy gains','heldout 4/5 and 5% gate is not a significance test']}
    save(lab/'results/optimization-summary.json',summary)
    (lab/'results/runs.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records_all),encoding='utf-8')
    if complete:
        versions=batches[stage]['plan']['builds'];recommended={}
        for kind,d in selected.items():
            build=versions[d['build']];commands=build['validation']['records'];snapshot=root/'evidence'/('opt-'+d['build'])/'snapshots/builds'/build['binary_sha256']
            if d['build']=='baseline':snapshot=lab/'snapshots/builds'/build['binary_sha256']
            build_info=read(snapshot/'build.json');configure=build_info[0]['argv']
            recommended[kind]={'build':d['build'],'config':f'configs/optimized/{kind}.json','config_sha256':sha(root/'configs/optimized'/f'{kind}.json'),
                'cmake_options':[s for s in configure if s.startswith('-D')],'binary_sha256':build['binary_sha256'],'snapshot':str(snapshot.relative_to(root)),
                'accepted':d['accepted']}
        save(root/'configs/optimized/builds.json',recommended)
    print(json.dumps({'complete':complete,'processes':len(records_all),'timing_samples':summary['timing_samples'],
        'selected':{k:{'build':v['build'],'accepted':v['accepted'],'workers':v['config']['workers'],'grain':v['config']['policies']['partition']['grain'],
                          'speedups':[c['base_over_candidate'] for c in v['heldout']]} for k,v in selected.items()}},ensure_ascii=False,indent=2))
def copy_config(c):return json.loads(json.dumps(c))
if __name__=='__main__':main()
