#!/usr/bin/env python3
"""Predeclared mechanism studies, bounded policy screening, paired held-out confirmation."""
import argparse,copy,json,pathlib,random,statistics,sys
from lab import Batch,ROOT,config,write,digest

def interleave(conditions,repeats=3,seed=20261016):
    order=list(range(len(conditions)));random.Random(seed).shuffle(order)
    result=[('warmup',0,conditions[i]) for i in order]
    for r in range(repeats):
        shift=(r*len(order))//max(1,repeats);block=order[shift:]+order[:shift]
        result += [('timing',r+1,conditions[i]) for i in block]
    return result

def execute(name,conditions,exe,extra=None,diagnostics=(),budget=900):
    order=interleave(conditions)
    plan={'experiment':name,'conditions':[{'id':cid,'config':c} for cid,c in conditions],
          'order':[(purpose,rep,cid) for purpose,rep,(cid,_) in order],
          'diagnostics':[{'id':cid,'config':c} for cid,c in diagnostics],
          'statistics':'three timing processes screening; all successful slow runs retained; warmup separate',**(extra or {})}
    batch=Batch(name,plan,exe,budget)
    try:
        for purpose,rep,(cid,c) in order:batch.run(c,cid,purpose,rep,timeout=90)
        for cid,c in diagnostics:
            c=copy.deepcopy(c);c['measurement']['mode']='diagnostic';batch.run(c,cid,'diagnostic',timeout=90)
        return batch.finish()
    except Exception as e:batch.finish('failed',str(e));raise

def w02(exe,k):
    conditions=[];diagnostics=[]
    for layout in ('concentrated','spread','shuffled'):
        for m in ('static','central','off','on'):
            cid=f'{layout}-{m}';c=config(m,4,64,k,workload='compute_skewed',layout=layout)
            conditions.append((cid,c))
            if m in ('off','on'):diagnostics.append((cid,c))
    return execute('W02',conditions,exe,{'hypothesis':'stealing reduces tail cost in concentrated fixed task placement; balanced placement may not benefit',
      'frozen_grain':64,'fixed_costs':'first N//8 ElementIds cost 9K, remaining K; all layouts use exactly same multiset and output',
      'identity_checks':'off/on queues and task hashes must agree within layout; element input/cost/output hashes agree across layouts'},diagnostics)

def w02_diagnostics(exe,k):
    cases=[]
    for layout in ('concentrated','spread','shuffled'):
        for m in ('off','on'):
            cases.append((layout+'-'+m,config(m,4,64,k,workload='compute_skewed',layout=layout)))
    return execute('W02-diagnostics-v3',[],exe,{'purpose':'additional actual work-unit/executor records on the final validated binary; never subtract or pool with v1 timing'},cases)

# Per-task byte scales: 1/72, 1/8 and 8 times the CPUID-reported 36 MiB LLC.
SCALES=(('small',512*1024,64,16),('middle',4608*1024,16,8),('large',288*1024*1024,4,2))
def memory_config(m,scale,layout='policy',seed=42):
    _,size,n,passes=scale;c=config(m,4,1,1,n,seed,'memory_reuse',layout=layout)
    c['workload'].update(bytes_per_element=size,passes=passes);return c
def w03(exe):
    conditions=[];diagnostics=[]
    for scale in SCALES:
        for layout in ('policy','concentrated'):
            for m in ('off','on'):
                c=memory_config(m,scale,layout);cid=f'{scale[0]}-{layout}-{m}';conditions.append((cid,c));diagnostics.append((cid,c))
    # Controlled experiment: one fixed block; symmetric home0/1 vs executor0/1.
    for scale in SCALES:
        for home in (0,1):
            for executor in (home,1-home):
                c=memory_config('off',scale);c['workload']['elements']=1
                c['measurement'].update(home_worker=home,controlled_worker=executor)
                conditions.append((f'{scale[0]}-controlled-h{home}-e{executor}',c))
    return execute('W03',conditions,exe,{'hypothesis':'home versus foreign executor may differ when reuse fits caches; zero effect is allowed',
       'reported_llc_bytes':36*1024*1024,'scales':SCALES,'affinity_limit':'WSL1 hardware residency unproven; no PMU; report worker/time association, not exact cache-miss causality',
       'memory_limit':'max active payload 4 * 288 MiB = 1.125 GiB; no swapping intentionally requested',
       'preprocess':'same-process home-worker read, no stealing; input hashes before pre-read; result verification after timed epoch'},diagnostics)

def variants():
    return {
      'base':{},
      'random':{'victim':{'name':'seeded_random','seed':17}},
      'backoff':{'steal_timing':{'name':'bounded_backoff'}},
      'half':{'migration':{'name':'capped_half','cap':32}},
      'unbound':{'affinity':{'name':'unbound'}},
      'balanced_chunks':{'partition':{'name':'balanced_chunks','chunks_per_worker':8}},
      'random_half':{'victim':{'name':'seeded_random','seed':17},'migration':{'name':'capped_half','cap':32}},
      'backoff_half':{'steal_timing':{'name':'bounded_backoff'},'migration':{'name':'capped_half','cap':32}},
    }
def class_config(kind,k,seed=42,n=262144):
    if kind=='uniform':return config('on',4,64,k,n,seed)
    if kind=='skewed':return config('on',4,64,k,n,seed,'compute_skewed',layout='concentrated')
    if kind=='memory':return memory_config('on',SCALES[0],seed=seed)
    raise ValueError(kind)
def apply_variant(c,name):
    c=copy.deepcopy(c)
    for key,value in variants()[name].items():c['policies'][key]=copy.deepcopy(value)
    return c
def w04(exe,k):
    conditions=[]
    for kind in ('uniform','skewed','memory'):
        for variant in variants():
            # Memory partition/home is frozen; partition alternatives are studied on compute workloads.
            if kind=='memory' and variant=='balanced_chunks':continue
            conditions.append((f'{kind}--{variant}',apply_variant(class_config(kind,k),variant)))
    return execute('W04',conditions,exe,{'hypothesis':'small predeclared policy set; baseline retained unless paired held-out evidence supports replacement',
       'candidate_count_per_class':{'uniform':8,'skewed':8,'memory':7},'selection_rule':'minimum screening median among declared variants in each class, deterministic name tie-break; confirm on held-out data',
       'heldout':{'inputs':[{'seed':73,'elements':196608},{'seed':991,'elements':327680}],
                  'memory_inputs':[{'seed':73,'elements':48},{'seed':991,'elements':80}],
                  'pairs_per_input':5,'threshold':'candidate beats base in >=4/5 pairs and median >=5% faster on every held-out input; otherwise retain base'},
       'limited_search':'one-factor changes and two declared combinations; no claim of global optimum'})

def select_screen(path):
    path=pathlib.Path(path);completion=json.loads((path/'completion.json').read_text());assert completion['status']=='completed'
    records=json.loads((path/'records.json').read_text());groups={}
    for r in records:
        if r['purpose']=='timing' and r['included']:groups.setdefault(r['condition'],[]).append(r['timing']['epoch_seconds'])
    selected={}
    for kind in ('uniform','skewed','memory'):
        eligible=[(statistics.median(v),cid.split('--')[1]) for cid,v in groups.items() if cid.startswith(kind+'--') and len(v)==3]
        selected[kind]=min(eligible)[1]
    return selected
def confirm(exe,k,screen_path):
    selected=select_screen(screen_path);conditions={};order=[];inputs=[(73,196608),(991,327680)]
    for kind in ('uniform','skewed','memory'):
        candidate=selected[kind]
        for seed,n in inputs:
            c=class_config(kind,k,seed,n)
            if kind=='memory':c['workload']['elements']=48 if seed==73 else 80
            cid=f'{kind}-s{seed}'
            conditions[cid+'-base']=c;conditions[cid+'-candidate']=apply_variant(c,candidate)
            # Always compare default stealing against disabled on the same held-out input.
            off=copy.deepcopy(c);off['policies']['steal_timing']={'name':'disabled'};conditions[cid+'-off']=off
    for cid,c in conditions.items():order.append(('warmup',0,cid))
    for rep in range(1,6):
        for kind in ('uniform','skewed','memory'):
            for seed,n in inputs:
                cid=f'{kind}-s{seed}';pair=[cid+'-base',cid+'-candidate'] if rep%2 else [cid+'-candidate',cid+'-base']
                order += [('timing',rep,x) for x in pair]
                order.append(('timing',rep,cid+'-off'))
    plan={'experiment':'W05-confirm','screen_batch':str(screen_path),'selected':selected,
          'conditions':[{'id':cid,'config':c} for cid,c in conditions.items()],'order':order,
          'threshold':'every input: >=4/5 paired wins and candidate median <=0.95*base median; otherwise retain base',
          'note':'candidate may equal base; still record pair variation, not an improvement claim; off comparison is secondary and not interleaved as a strict AB/BA pair'}
    batch=Batch('W05',plan,exe,900)
    try:
        for purpose,rep,cid in order:batch.run(conditions[cid],cid,purpose,rep,timeout=90)
        return batch.finish()
    except Exception as e:batch.finish('failed',str(e));raise
def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=('W02','W02-diagnostics','W03','W04','W05'));ap.add_argument('--exe',required=True);ap.add_argument('--k',type=int,required=True);ap.add_argument('--screen')
    a=ap.parse_args();exe=pathlib.Path(a.exe).resolve();v=json.loads((exe.parent/'validation.json').read_text());assert v['pass'] and v['binary_sha256']==digest(exe)
    if a.stage=='W05':path=confirm(exe,a.k,a.screen)
    else:path={'W02':lambda:w02(exe,a.k),'W02-diagnostics':lambda:w02_diagnostics(exe,a.k),'W03':lambda:w03(exe),'W04':lambda:w04(exe,a.k)}[a.stage]()
    print(json.dumps({'batch':str(path),'status':'completed'}))
if __name__=='__main__':main()
