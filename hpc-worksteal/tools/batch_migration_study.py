#!/usr/bin/env python3
"""V14 bounded batch migration screen, single-candidate heldout and archive."""
import argparse
import collections
import copy
import hashlib
import json
import pathlib
import random
import shutil
import statistics
import threading
import uuid

import confirm_idle as guard
import lab
import stealing_boundary_study as model

PROTOCOL='docs/39-第十四轮有界批量窃取协议.md'
CAPS=(1,4,16,64)
LAYOUTS=('concentrated','spread')
INPUTS=((116009,73728),(122011,106496))
EXE=model.EXE
SHA=model.SHA


def read(path):
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig'))


def config(seed,n,k,cap,layout,diagnostic=False):
    c=lab.config('on',16,8,k,n,seed,'compute_skewed',layout=layout)
    c['measurement']['reference_workers']=16
    if diagnostic:c['measurement']['mode']='diagnostic'
    c['policies']['migration']={'name':'single'} if cap==1 else {'name':'capped_half','cap':cap}
    return c


def item(stage,seed,n,k,cap,layout):
    return {'id':f'{stage}-s{seed}-{layout}-cap{cap}', 'stage':stage, 'cap':cap,
            'config':config(seed,n,k,cap,layout,stage=='control')}


def design():
    controls=[item('control',108007,1031,7,cap,layout) for layout in LAYOUTS for cap in CAPS]
    screen=[item('screen',110017,81920,256,cap,layout) for layout in LAYOUTS for cap in CAPS]
    ids=[c['id'] for c in screen];random.Random(2026102514).shuffle(ids)
    order=[('control',0,c['id']) for c in controls]
    order += [('diagnostic',0,cid) for cid in ids]+[('warmup',0,cid) for cid in ids]
    for rep in range(1,4):
        shift=(rep-1)*len(ids)//3
        order += [('timing',rep,cid) for cid in ids[shift:]+ids[:shift]]
    branches={}
    for cap in CAPS[1:]:
        cases,pairs=[],[]
        for seed,n in INPUTS:
            for layout in LAYOUTS:
                pair=[]
                for actual in (1,cap):
                    c=item('confirm',seed,n,256,actual,layout);cases.append(c);pair.append(c['id'])
                pairs.append(pair)
        border=[('diagnostic',0,cid) for pair in pairs for cid in pair]
        border += [('warmup',0,cid) for pair in pairs for cid in pair]
        for rep in range(1,8):
            border += [('timing',rep,cid) for pair in pairs for cid in (pair if rep%2 else pair[::-1])]
        branches[str(cap)]={'conditions':cases,'pairs':pairs,'order':border}
    return {'stage':'V14-batch-migration','conditions':controls+screen,'order':order,
        'confirmation_branches':branches,'screen_processes':48,'max_processes':120,'max_timing_samples':80}


def selection(timing):
    table=[]
    for cap in CAPS:
        metrics={layout:{metric:statistics.median(timing[(f'screen-s110017-{layout}-cap{cap}',rep)][metric] for rep in range(1,4))
                         for metric in ('epoch','app','process')} for layout in LAYOUTS}
        table.append({'cap':cap,'medians':metrics})
    base=table[0]['medians']
    for row in table:
        m=row['medians']
        row['eligible']=row['cap']!=1 and m['concentrated']['epoch']<=.95*base['concentrated']['epoch'] and m['spread']['epoch']<=1.10*base['spread']['epoch'] and all(m[l]['app']<=1.05*base[l]['app'] for l in LAYOUTS)
    eligible=sorted((r for r in table if r['eligible']),key=lambda r:(r['medians']['concentrated']['epoch'],r['medians']['concentrated']['app'],r['cap']))
    return {'selected_cap':eligible[0]['cap'] if eligible else None,'table':table,
        'rule':'target concentrated epoch<=95%; spread epoch<=110%; app both<=105%; sort target epoch,app,cap'}


def diagnostic(c,e,cap):
    tasks,costs,lists,initial=model.task_model(c)
    owner_of={tid:w for w,q in enumerate(lists) for tid in q}
    owners=e['execution']['task_executor'];stats=e['worker_stats']
    assert len(owners)==len(tasks) and len(stats)==16
    work,elements,count=[0]*16,[0]*16,[0]*16
    mismatch,relocated=0,0
    for (tid,begin,end,home),cost,owner in zip(tasks,costs,owners):
        assert type(owner) is int and 0<=owner<16
        work[owner]+=cost;elements[owner]+=end-begin;count[owner]+=1
        mismatch+=(end-begin)*(owner!=home);relocated+=owner!=owner_of[tid]
    assert e['execution']=={'worker_cost_units':work,'worker_elements':elements,'task_executor':owners,
        'element_home_mismatches':mismatch,'cost_unit':'mix_iterations'}
    assert [s['tasks'] for s in stats]==count
    for s in stats:
        assert 0<=s['steals']<=s['tasks'] and s['steals']<=s['moved']<=cap*s['steals']
    steals,moved=sum(s['steals'] for s in stats),sum(s['moved'] for s in stats)
    assert relocated<=moved
    if cap==1:assert steals==moved==relocated
    return {'initial_cost_units':initial,'actual_cost_units':work,'task_count':len(tasks),
        'total_cost_units':sum(costs),'initial_cost_balance':sum(initial)/(16*max(initial)),
        'actual_cost_balance':sum(work)/(16*max(work)),'steals':steals,'moved_transfer_visits':moved,
        'final_owner_changed_tasks':relocated,'home_mismatched_elements':mismatch,
        'note':'batched moved may include repeated transfers; final ownership is not an event trace'}


def check(c,r,cap,small,cache,outputs):
    resolved=copy.deepcopy(c);resolved['steal_enabled']=True
    assert r['resolved_config']==resolved and r['correctness']['pass'] and len(r['epochs'])==1
    e=r['epochs'][0];cc=e['correctness'];w=c['workload']
    key=(w['seed'],w['elements'],w['iterations'])
    ikey=(*key,c['layout'])
    if ikey not in cache:cache[ikey]=model.identities(c,cache)
    assert e['identity']==cache[ikey]
    assert cc['pass'] and cc['mismatches']==0 and cc['compared_elements']==w['elements']
    assert cc['reference_tile_elements']==256 and cc['reference_workers_used']==min(16,(w['elements']+255)//256)
    if key not in outputs:outputs[key]=model.small_output(c) if small else cc['output_hash_fnv1a64']
    assert cc['output_hash_fnv1a64']==outputs[key]
    assert e['pretouch_hash_fnv1a64'] is None and not e['local_only']
    cpus=c['policies']['affinity']['cpus']
    assert r['affinity']['requested']==cpus and r['affinity']['actual_workers']==[[cpu] for cpu in cpus]
    assert r['initialization']['workers_used']==0 and r['initialization']['data_allocation_used']=='none'
    assert r['data_fill']['lanes_used']==0 and r['data_identity']['used']=='none' and r['execution_kernel']['memory_lanes_used']==0
    assert all(v>=0 for v in r['phase_seconds'].values())
    assert sum(r['phase_seconds'].values())<=r['timing']['end_to_end_seconds']+1e-9
    diagnostic_mode=c['measurement']['mode']=='diagnostic'
    assert cc['exact_once']==(True if diagnostic_mode else None)
    if diagnostic_mode:return diagnostic(c,e,cap)
    assert e['execution'] is None and e['worker_stats'] is None
    return None


def prepare(root):
    origin=lab.ROOT;root.mkdir(parents=True,exist_ok=False)
    for src in lab.source_files():
        dest=root/src.relative_to(origin);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
    lab.ROOT=root;source=lab.snapshot();exe=pathlib.Path(EXE);v=read(exe.parent/'validation.json')
    assert v['pass'] and v['binary_sha256']==lab.digest(exe)==SHA
    assert all(r['returncode']==0 and not r['stderr'] for r in v['records'])
    assert 'warning:' not in (exe.parent/'build-1.log').read_text().lower()
    old=read(exe.parent.parent/'snapshots/source'/v['source_id']/'manifest.json')
    for rel,sha in old['files'].items():
        if rel.startswith(('src/','include/')) or rel.startswith(('tests/','configs/')) and rel.endswith(('.cpp','.hpp','.py','.json')) or rel in ('CMakeLists.txt','CMakePresets.json'):
            assert lab.digest(root/rel)==sha
    for folder,identifier in (('source',v['source_id']),('builds',SHA)):
        shutil.copytree(exe.parent.parent/'snapshots'/folder/identifier,root/'snapshots'/folder/identifier)
    lab.write(root/'results/frozen-plan.json',{'created':lab.now(),'collector_source_id':source,
        'protocol':PROTOCOL,'protocol_sha256':lab.digest(root/PROTOCOL),'study':design(),
        'build':{'exe':EXE,'binary_sha256':SHA,'source_id':v['source_id']}})
    lab.write(root/'results/preparation.json',{'plan_sha256':lab.digest(root/'results/frozen-plan.json'),'created':lab.now()})
    print(json.dumps({'prepared':str(root),'source_id':source,'max_processes':120}),flush=True)


def load(root):
    path=root/'results/frozen-plan.json'
    assert lab.digest(path)==read(root/'results/preparation.json')['plan_sha256']
    p=read(path);assert p['study']==json.loads(json.dumps(design()))
    assert lab.digest(root/'snapshots/source'/p['collector_source_id']/PROTOCOL)==p['protocol_sha256']
    return p


def run(root,wait_seconds):
    p=load(root);assert not list((root/'runs').glob('*')),'no retry of started batch'
    assert len(list((root/'results').glob('availability-*.json')))<2
    assert lab.digest(pathlib.Path(EXE))==SHA
    status,receipt=guard.availability(root,wait_seconds)
    if status!='ready':return 3
    stage=p['study'];b=p['build']
    batch=lab.Batch(stage['stage'],{**stage,'build':b,'availability_receipt':receipt.relative_to(root).as_posix(),
        'frozen_plan_sha256':lab.digest(root/'results/frozen-plan.json')},pathlib.Path(EXE),budget=600)
    batch.source,batch.binary=b['source_id'],b['binary_sha256']
    own,stop,samples,lock=guard.ancestors(),threading.Event(),[],threading.Lock()
    def clean():
        with lock:samples.append(guard.observe(own))
        return all(s['clear'] for s in samples)
    def monitor():
        while not stop.wait(.5):
            if not clean():break
    cache,outputs,timing,diags={},{},{},[]
    def execute(conditions,order):
        cases={c['id']:c for c in conditions}
        for purpose,rep,cid in order:
            if not clean():raise RuntimeError('resource_contamination')
            item=cases[cid];c=copy.deepcopy(item['config'])
            if purpose=='diagnostic':c['measurement']['mode']='diagnostic'
            r=batch.run(c,cid,purpose,rep,timeout=90)
            d=check(c,r,item['cap'],item['stage']=='control',cache,outputs)
            if d is not None:diags.append({'condition':cid,'purpose':purpose,**d})
            if purpose=='timing':
                row=batch.records[-1]
                timing[(cid,rep)]={'epoch':r['timing']['epoch_seconds'],'app':r['timing']['end_to_end_seconds'],
                    'process':row['elapsed_process_seconds'],'run_path':(batch.path/row['run_id']).relative_to(root).as_posix()}
            if not clean():raise RuntimeError('resource_contamination')
    worker=threading.Thread(target=monitor,daemon=True);worker.start();state,reason='completed',None
    try:
        execute(stage['conditions'],stage['order'])
        choice=selection(timing);lab.write(batch.path/'selection.json',choice)
        print(json.dumps({'selection':choice}),flush=True)
        if choice['selected_cap'] is not None:
            branch=stage['confirmation_branches'][str(choice['selected_cap'])]
            execute(branch['conditions'],branch['order'])
        lab.write(batch.path/'diagnostic-reconstruction.json',diags)
    except Exception as exc:
        reason=str(exc);state='contaminated' if reason=='resource_contamination' else 'failed'
    finally:
        stop.set();worker.join(timeout=15)
        if worker.is_alive():state,reason='failed','monitor_did_not_stop'
        lab.write(batch.path/'resource-observations.json',{'samples':samples,'clean':all(s['clear'] for s in samples),'interval_seconds':.5})
        batch.finish(state,reason)
    print(json.dumps({'batch':str(batch.path),'status':state,'processes':len(batch.records)}),flush=True)
    return 0 if state=='completed' else 4


def confirmation(choice,timing,stage):
    cap=choice['selected_cap']
    if cap is None:return {'accepted':False,'reason':'no_screen_candidate','groups':[]}
    branch=stage['confirmation_branches'][str(cap)];groups=[]
    for base,candidate in branch['pairs']:
        item=next(c for c in branch['conditions'] if c['id']==base);c=item['config']
        pairs=[{'repeat':rep,'base':timing[(base,rep)],'candidate':timing[(candidate,rep)]} for rep in range(1,8)]
        medians={mode:{metric:statistics.median(pair[mode][metric] for pair in pairs) for metric in ('epoch','app','process')} for mode in ('base','candidate')}
        wins=sum(pair['candidate']['epoch']<pair['base']['epoch'] for pair in pairs)
        target=c['layout']=='concentrated';a,b=medians['base'],medians['candidate']
        passed=b['app']<=1.05*a['app'] and ((wins>=6 and b['epoch']<=.95*a['epoch']) if target else b['epoch']<=1.10*a['epoch'])
        groups.append({'seed':c['workload']['seed'],'elements':c['workload']['elements'],'layout':c['layout'],
            'cap':cap,'epoch_wins':wins,'medians':medians,'epoch_speedup':a['epoch']/b['epoch'],
            'app_speedup':a['app']/b['app'],'pass':passed,'pairs':pairs})
    return {'accepted':all(g['pass'] for g in groups),'reason':'all_gates_passed' if all(g['pass'] for g in groups) else 'heldout_gate_not_met','groups':groups}


def audit(root):
    p=load(root);checked=0
    for manifest in (root/'snapshots/source').glob('*/manifest.json'):
        m=read(manifest)
        assert hashlib.sha256(json.dumps(m['files'],sort_keys=True).encode()).hexdigest()==m['source_id']==manifest.parent.name
        for rel,sha in m['files'].items():assert lab.digest(manifest.parent/rel)==sha;checked+=1
    build=root/'snapshots/builds'/SHA;v=read(build/'validation.json')
    assert v['pass'] and v['source_id']==p['build']['source_id'] and v['binary_sha256']==lab.digest(build/'worksteal')==SHA
    assert all(r['returncode']==0 and not r['stderr'] for r in v['records'])
    directories=list((root/'runs').iterdir());assert len(directories)==1;directory=directories[0]
    rows,done,plan=read(directory/'records.json'),read(directory/'completion.json'),read(directory/'plan.json')
    assert plan['source_id']==p['collector_source_id'] and plan['build']==p['build']
    assert {k:plan[k] for k in p['study']}==p['study'] and plan['frozen_plan_sha256']==lab.digest(root/'results/frozen-plan.json')
    manifests=list((root/'snapshots/builds').glob('*/checksums.json'))+[directory/'checksums.json']+list(directory.glob('*/checksums.json'))
    for manifest in manifests:
        hashes=read(manifest)
        assert set(hashes)=={f.relative_to(manifest.parent).as_posix() for f in manifest.parent.rglob('*') if f.is_file() and f.name!='checksums.json'}
        for rel,sha in hashes.items():assert lab.digest(manifest.parent/rel)==sha;checked+=1
    cases={c['id']:c for c in p['study']['conditions']}
    for branch in p['study']['confirmation_branches'].values():
        for c in branch['conditions']:
            if c['id'] in cases:assert c==cases[c['id']]
            cases[c['id']]=c
    assert len(rows)==done['processes'] and len({r['run_id'] for r in rows})==len(rows)
    assert {d.name for d in directory.iterdir() if d.is_dir()}=={r['run_id'] for r in rows}
    cache,outputs,timing,diags={},{},{},[]
    for row in rows:
        rd=directory/row['run_id'];item=cases[row['condition']];c=copy.deepcopy(item['config'])
        if row['purpose']=='diagnostic':c['measurement']['mode']='diagnostic'
        assert read(rd/'metadata.json')==row and read(rd/'config.json')==c
        assert row['source_id']==p['build']['source_id'] and row['binary_sha256']==SHA
        assert row['collector_sha256']==lab.digest(root/'snapshots/source'/p['collector_source_id']/'tools/lab.py')
        cmd=read(rd/'command.txt');original=pathlib.PurePosixPath(cmd['cwd'])/'runs'/directory.name/row['run_id']
        assert cmd['argv']==[EXE,'--config',str(original/'config.json'),'--output',str(original/'result.json')] and not cmd['explicit_environment']
        if row['status']!='completed':assert done['status']!='completed' and not row['included'];continue
        assert row['exit_code']==0 and not (rd/'stderr.log').read_bytes()
        r=read(rd/'result.json');assert json.loads((rd/'stdout.log').read_bytes())==r
        assert row['timing']==r['timing'] and row['included']==(row['purpose']=='timing')
        d=check(c,r,item['cap'],item['stage']=='control',cache,outputs)
        if d is not None:diags.append({'condition':row['condition'],'purpose':row['purpose'],**d})
        if row['included']:timing[(row['condition'],row['repeat'])]={'epoch':r['timing']['epoch_seconds'],'app':r['timing']['end_to_end_seconds'],
            'process':row['elapsed_process_seconds'],'run_path':rd.relative_to(root).as_posix()}
    resource=read(directory/'resource-observations.json');assert resource['samples'] and resource['clean']==all(s['clear'] for s in resource['samples'])
    av=read(root/plan['availability_receipt']);assert av['status']=='ready' and all(s['clear'] for s in av['observations'][-3:])
    clean=done['status']=='completed' and resource['clean'];choice,result=None,None
    order=p['study']['order']
    if len(rows)>=48:
        choice=selection(timing);assert read(directory/'selection.json')==choice
        if choice['selected_cap'] is not None:order=order+p['study']['confirmation_branches'][str(choice['selected_cap'])]['order']
    assert [(r['purpose'],r['repeat'],r['condition']) for r in rows]==[tuple(step) for step in order[:len(rows)]]
    if clean:
        assert len(rows)==len(order) and read(directory/'diagnostic-reconstruction.json')==diags
        result=confirmation(choice,timing,p['study'])
        assert len(timing)==(24 if choice['selected_cap'] is None else 80)
    a={'created':lab.now(),'audit_pass':True,'complete':clean,'accepted':result['accepted'] if result else False,
       'batch':directory.name,'processes':len(rows),'timing_samples':len(timing),'diagnostic_samples':len(diags),
       'hash_checks':checked,'resource_samples':len(resource['samples']),'selection':choice,'confirmation':result,'diagnostics':diags}
    path=root/'results'/('audit-'+uuid.uuid4().hex+'.json');lab.write(path,a)
    print(json.dumps({'audit':str(path),'complete':clean,'accepted':a['accepted'],'processes':len(rows),'hash_checks':checked}),flush=True)
    return a,path


def report(root):
    receipts=list((root/'results').glob('export-*.json'));assert len(receipts)==1
    receipt=read(receipts[0])
    for rel,sha in receipt['files'].items():assert lab.digest(root/rel)==sha
    a,path=audit(root);target=lab.ROOT/'report/batch-migration'/('第十四轮批量窃取报告-'+uuid.uuid4().hex[:8]+'.md')
    lines=['# 第十四轮：有界批量窃取','',f"批次`{a['batch']}`，{a['processes']}进程/{a['timing_samples']}计时，complete={a['complete']}、accepted={a['accepted']}。",'',
        '固定原Release/16worker/grain8/K256，只改single与capped_half。保留全部慢成功样本，诊断与预热不进入正式计时。结果只适用此范围，不能替换原32worker/grain256推荐。','',
        '## 筛选','', '|cap|集中epoch ms|分散epoch ms|集中app ms|分散app ms|合格|','|---:|---:|---:|---:|---:|---|']
    if a['selection']:
        for row in a['selection']['table']:
            c,s=row['medians']['concentrated'],row['medians']['spread']
            lines.append(f"|{row['cap']}|{c['epoch']*1000:.4f}|{s['epoch']*1000:.4f}|{c['app']*1000:.4f}|{s['app']*1000:.4f}|{row['eligible']}|")
        lines += ['',f"唯一候选cap={a['selection']['selected_cap']}。无合格候选则停止，确认失败不重选。"]
    result=a['confirmation'] or {'groups':[]}
    lines += ['', '## 独立输入确认','','|seed/N|布局|epoch base→candidate ms|epoch比|胜对|app比|通过|','|---|---|---:|---:|---:|---:|---|']
    for g in result['groups']:
        b,c=g['medians']['base'],g['medians']['candidate']
        lines.append(f"|{g['seed']}/{g['elements']}|{g['layout']}|{b['epoch']*1000:.4f}→{c['epoch']*1000:.4f}|{g['epoch_speedup']:.3f}|{g['epoch_wins']}/7|{g['app_speedup']:.3f}|{g['pass']}|")
    lines += ['', '主门槛：集中布局双输入各6/7胜且中位数至少快5%；分散epoch≤110%，两布局app≤105%。工程门槛不是显著性检验。moved可含重复搬运，不等于最终换owner任务数，steals减少也不独立证明加速。', '',
        f"[独立审计](../../batch-migration/{path.relative_to(root).as_posix()})；[冻结计划](../../batch-migration/results/frozen-plan.json)；[全部run索引](../../batch-migration/runs/{a['batch']}/records.json)。",'', '## 全部确认配对','']
    for g in result['groups']:
        lines += [f"### seed{g['seed']} {g['layout']}",'']
        for pair in g['pairs']:
            b,c=pair['base'],pair['candidate']
            lines.append(f"- 第{pair['repeat']}对：[single](../../batch-migration/{b['run_path']}/result.json) {b['epoch']*1000:.4f}ms → [candidate](../../batch-migration/{c['run_path']}/result.json) {c['epoch']*1000:.4f}ms。")
        lines.append('')
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
    print(json.dumps({'report':str(target),'exported_files_verified':len(receipt['files'])},ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','run','audit','export','report'))
    parser.add_argument('--root',required=True);parser.add_argument('--target');parser.add_argument('--wait-seconds',type=int,default=600)
    args=parser.parse_args();root=pathlib.Path(args.root).resolve()
    if args.action=='prepare':prepare(root)
    else:
        if args.action!='report':lab.ROOT=root
        if args.action=='run':return run(root,args.wait_seconds)
        if args.action=='audit':audit(root)
        if args.action=='export':lab.export(argparse.Namespace(target=args.target))
        if args.action=='report':report(root)
    return 0


if __name__=='__main__':raise SystemExit(main())
