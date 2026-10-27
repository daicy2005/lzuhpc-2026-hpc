#!/usr/bin/env python3
"""Bounded cross-build optimization, parameter screening and fresh paired holdouts."""
import argparse, collections, copy, json, pathlib, random, statistics, sys
from lab import Batch, ROOT, config, digest, write

NAMES=('baseline','batch32','scratch','lto','runtime','full','lanes4','lanes8','full_lanes4','full_lanes8')
KINDS=('light','uniform','skewed','memory')
def read(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))
def exe(name):return ROOT.parent/('ws-20261016-opt-'+name)/'build-none/worksteal'
def builds():
    result={}
    for name in NAMES:
        path=exe(name);v=read(path.parent/'validation.json');assert v['pass'] and v['binary_sha256']==digest(path)
        result[name]={'exe':str(path),'binary_sha256':digest(path),'source_id':v['source_id'], 'validation':v}
    return result
def case(kind,p=4,grain=None,seed=42,n=262144):
    if kind=='memory':
        c=config('on',p,grain or 1,1,64 if seed==42 else (48 if seed==137 else 80),seed,'memory_reuse')
        c['workload'].update(bytes_per_element=512*1024,passes=16);return c
    return config('on',p,grain or (1 if kind=='light' else 64),16 if kind=='light' else 1024,n,seed,
                  'compute_skewed' if kind=='skewed' else 'compute_uniform', layout='concentrated' if kind=='skewed' else 'policy')
def order(cases,repeats=3):
    indexes=list(range(len(cases)));random.Random(2026101602).shuffle(indexes)
    steps=[('warmup',0,cases[i]) for i in indexes]
    for rep in range(1,repeats+1):
        shift=((rep-1)*len(indexes))//repeats;rot=indexes[shift:]+indexes[:shift]
        steps += [('timing',rep,cases[i]) for i in rot]
    return steps
def run(stage,cases,steps,extra):
    versions=builds();plan={'experiment':stage,'builds':versions,'conditions':cases,
        'order':[(purpose,rep,c['id']) for purpose,rep,c in steps],
        'scope':'WSL1 logical-mask optimization; identical mathematical inputs, output and total cost across builds',**extra}
    b=Batch(stage,plan,exe('baseline'),budget=600)
    try:
        for purpose,rep,c in steps:
            build=versions[c['build']];b.exe=pathlib.Path(build['exe']);b.binary=build['binary_sha256'];b.source=build['source_id']
            b.run(c['config'],c['id'],purpose,rep,timeout=90)
        path=b.finish()
    except Exception as e:b.finish('failed',str(e));raise
    print(json.dumps({'batch':str(path),'status':'completed'}));return path
def medians(path):
    path=pathlib.Path(path);assert read(path/'completion.json')['status']=='completed'
    samples=collections.defaultdict(list)
    for r in read(path/'records.json'):
        if r['included']:samples[r['condition']].append(r['timing']['epoch_seconds'])
    assert all(len(v)==3 for v in samples.values())
    return {cid:statistics.median(v) for cid,v in samples.items()}
def select(path):
    m=medians(path);plan=read(pathlib.Path(path)/'plan.json');result={}
    for kind in KINDS:
        cs=[c for c in plan['conditions'] if c['kind']==kind]
        winner=min(cs,key=lambda c:(m[c['id']],c['id']));result[kind]=winner
    return result
def screen():
    cases=[{'id':kind+'--'+name,'kind':kind,'build':name,'config':case(kind)} for kind in KINDS for name in NAMES]
    return run('OPT1-build-screen',cases,order(cases),{'heldout_seeds':[137,2027],
        'gate':'every heldout input: candidate >=4/5 paired wins and median <=0.95*baseline',
        'selection':'lowest screen median per class; no dropping slow successful runs',
        'next_stage':'parameter screen at seed42 then one joint fresh heldout confirmation; no further selection after holdout',
        'variants':{'baseline':[1,False,False],'batch32':[32,False,False],'scratch':[1,True,False],
            'lto':[1,False,True],'runtime':[32,True,False],'full':[32,True,True],
            'lanes4':[1,False,True,4],'lanes8':[1,False,True,8],
            'full_lanes4':[32,True,True,4],'full_lanes8':[32,True,True,8]}})
def tune(screen):
    selected=select(screen);cases=[]
    for kind,c in selected.items():
        grains=(1,16,64,256) if kind=='light' else (1,2,4) if kind=='memory' else (16,64,256,1024)
        for p in (1,2,4,8,16,32):
            for g in grains:
                cases.append({'id':f'{kind}--{c["build"]}-p{p}-g{g}','kind':kind,'build':c['build'],'config':case(kind,p,g)})
    return run('OPT2-parameter-screen',cases,order(cases),{'build_screen':str(screen),'selected_builds':selected,
        'parameter_scope':'p=1,2,4,8,16,32 logical masks; light grain1/16/64/256, compute16/64/256/1024, memory1/2/4',
        'selection':'minimum screen median, deterministic condition-ID tie-break; retain old base unless both holdouts pass'})
def confirm(tuning):
    selected=select(tuning);cases=[];steps=[];pairs=[]
    for kind,c in selected.items():
        for seed,n in ((137,196608),(2027,327680)):
            base={'id':f'{kind}-s{seed}-base','kind':kind,'build':'baseline','config':case(kind,seed=seed,n=n)}
            cand=copy.deepcopy(c);cand['id']=f'{kind}-s{seed}-candidate'
            cand['config']['workload']['seed']=seed;cand['config']['layout_seed']=seed
            cand['config']['workload']['elements']=(48 if seed==137 else 80) if kind=='memory' else n
            cases.extend((base,cand));pairs.append((base,cand))
    steps=[('warmup',0,c) for c in cases]
    for rep in range(1,6):
        for pair in pairs:
            steps += [('timing',rep,c) for c in (pair if rep%2 else pair[::-1])]
    return run('OPT3-heldout',cases,steps,{'parameter_screen':str(tuning),'selected':selected,
        'gate':'both inputs: >=4/5 paired wins AND candidate median <=0.95*baseline median',
        'prohibition':'no choosing second place, no new parameters, no dropping slow successful samples after heldout'})
def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('screen','tune','confirm'));p.add_argument('--previous');a=p.parse_args()
    if a.stage=='screen':screen()
    elif a.stage=='tune':tune(a.previous)
    else:confirm(a.previous)
if __name__=='__main__':main()
